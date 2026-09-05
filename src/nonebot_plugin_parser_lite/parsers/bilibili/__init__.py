import asyncio
from collections.abc import AsyncGenerator, Iterable
from typing import ClassVar

import aiofiles
from anyio import Path
from google.protobuf.json_format import MessageToJson
from msgspec import convert

from ...exception import DownloadException, TipException
from ...utils.bilibili.a2v import bv2av
from ...utils.bilibili.bangumi import Bangumi
from ...utils.bilibili.bilibili.app.dynamic.v2 import dynamic_pb2, opus_pb2
from ...utils.bilibili.bilibili.app.view.v1 import view_pb2
from ...utils.bilibili.bilibili.main.community.reply.v1 import reply_pb2
from ...utils.bilibili.client import HEADERS
from ...utils.bilibili.comment import CommentResourceType, get_comments
from ...utils.bilibili.credential import Credential
from ...utils.bilibili.dynamic import Dynamic
from ...utils.bilibili.exceptions import (
    BiliHelperException,
    CookiesRefreshException,
)
from ...utils.bilibili.favorite_list import get_video_favorite_list_content
from ...utils.bilibili.live import LiveRoom
from ...utils.bilibili.login import QrCodeLogin, QrCodeLoginEvents
from ...utils.bilibili.opus import Opus
from ...utils.bilibili.user import get_black_list, get_user_info
from ...utils.bilibili.video import (
    AudioStreamDownloadURL,
    FLVStreamDownloadURL,
    MP4StreamDownloadURL,
    Video,
    VideoDownloadURLDataDetecter,
    VideoStreamDownloadURL,
)
from ...utils.format import format_num
from ...utils.log import logger
from ..base import (
    DOWNLOADER,
    Author,
    BaseParser,
    Comment,
    ContentItem,
    MatchWithParams,
    ParseException,
    Platform,
    PlatformEnum,
    handle,
    pconfig,
)
from .bangumi import BangumiInfo
from .dynamic import (
    _append_dynamic_payload,
    _append_opus_summary,
    _append_paragraph,
    _apply_stat,
    # _description_items,
    _parse_timestamp,
    _text_node_plain_text,
    build_dynamic,
)
from .favlist import FavData
from .live import RoomData
from .size import probe_source_size
from .video import AIConclusion


class BilibiliParser(BaseParser):
    platform: ClassVar[Platform] = Platform(
        name=PlatformEnum.BILIBILI, display_name="哔哩哔哩"
    )

    BILI_RETRYABLE_HTTP_STATUSES = frozenset(
        {403, 404, 408, 425, 429, *range(500, 600)}
    )

    def __init__(self):
        super().__init__()
        self.headers = HEADERS.copy()
        self._credential: Credential | None = None
        self._credential_file = pconfig.config_dir / "bilibili_credential.json"
        self.black_mids: list[int] | None = None
        """黑名单作者列表"""
        self._black_list_job_added: bool = False

    async def load_black_list(self) -> None:
        """初始化黑名单"""
        credential = await self.credential
        if not credential:
            logger.info("B站未登录，跳过黑名单加载")
            self.black_mids = []
            return
        black_mids: list[int] = []
        page_size = 50

        try:
            try:
                data = await get_black_list(page_size=page_size, credential=credential)
            except BiliHelperException as e:
                logger.error(f"获取B站黑名单列表失败: {e.msg}")
                self.black_mids = []
                return

            first_list = data["list"]
            total = data["total"]

            black_mids.extend(obj["mid"] for obj in first_list)
            pages = (total + page_size - 1) // page_size if total > page_size else 1
            for page_index in range(2, pages + 1):
                try:
                    try:
                        data = await get_black_list(
                            page_size=page_size,
                            page_index=page_index,
                            credential=credential,
                        )
                    except BiliHelperException as e:
                        logger.warning(f"获取B站黑名单第 {page_index} 页失败: {e.msg}")
                        continue
                    page_list = data["list"]
                    black_mids.extend(obj["mid"] for obj in page_list)
                    logger.debug(
                        f"黑名单第 {page_index} 页加载完成, 当前共 {len(black_mids)} 个"
                    )
                    await asyncio.sleep(0.2)
                except Exception as e:
                    logger.warning(f"请求B站黑名单第 {page_index} 页异常: {e}")
                    continue

            self.black_mids = black_mids
            logger.debug(f"B站黑名单列表: {black_mids}")
            logger.info(
                f"已加载 {len(self.black_mids)} 个 B 站黑名单用户 (pages={pages})"
            )

            # 首次成功加载黑名单后注册小时刷新任务
            if not self._black_list_job_added:
                from ...utils.scheduler import scheduler

                scheduler.add_job(
                    self.load_black_list,
                    seconds=60 * 60,
                    id="sync-bili-black-list",
                )
                self._black_list_job_added = True
                logger.info("已注册 B 站黑名单异步同步任务（每 1 小时刷新一次）")

        except Exception as e:
            logger.exception(f"请求 B 站黑名单接口异常: {e}")
            if self.black_mids is None:
                self.black_mids = []

    async def raise_if_in_black_list(self, mid: int):
        """
        检查用户是否在黑名单中

        :raise TipException: 用户在黑名单中
        """
        if self.black_mids is None:
            await self.load_black_list()
            assert self.black_mids is not None
        if mid in self.black_mids:
            raise TipException("该up属于黑名单")

    @handle("bilibili.com/bangumi/play", r"ep(?P<ep_id>\d+)")
    @handle("bilibili.com/bangumi/play", r"ss(?P<season_id>\d+)")
    async def _parse_bangumi(self, searched: MatchWithParams):
        ep_id = searched.get("ep_id")
        season_id = searched.get("season_id")
        bangumi = await Bangumi(ep_id=ep_id, season_id=season_id).get_info()
        bangumi_info = convert(bangumi, BangumiInfo)

        def format_stat(value: int) -> str:
            return format_num(value)

        return self.result(
            author=self.create_author(
                name=bangumi_info.season_title,
                avatar_url=bangumi_info.square_cover,
            ),
            content=[
                self.create_graphic(url=bangumi_info.cover),
                bangumi_info.evaluate,
            ],
            stats=self.create_stats(
                view_count=format_stat(bangumi_info.stat.views),
                like_count=format_stat(bangumi_info.stat.likes),
                collect_count=format_stat(bangumi_info.stat.favorite),
                share_count=format_stat(bangumi_info.stat.share),
                comment_count=format_stat(bangumi_info.stat.reply),
                extra={
                    "danmaku": format_stat(bangumi_info.stat.danmakus),
                    "coin": format_stat(bangumi_info.stat.coins),
                },
            ),
            title=bangumi_info.title,
            url=bangumi_info.share_url,
        )

    @handle("b23.tv", r"b23\.tv/[0-9a-zA-Z._?%&+\-=/#]+")
    @handle("bili2233", r"bili2233\.cn/[0-9a-zA-Z._?%&+\-=/#]+")
    async def _parse_short_link(self, searched: MatchWithParams):
        """解析短链"""
        url = f"https://{searched.url}"
        return await self.parse_with_redirect(url)

    @handle(
        "/BV",
        r"bilibili\.com(?:/video)?/(?P<bvid>BV[0-9A-Za-z]{10})",
        params={"p": {"default": "1", "as_int": True, "required": False}},
    )
    @handle("BV", r"^(?P<bvid>BV[0-9a-zA-Z]{10})(?:\s)?(?P<p>\d{1,3})?$")
    @handle("bilibili.com/list/watchlater", params={"bvid": {}})
    async def _parse_bv(self, searched: MatchWithParams):
        """解析视频信息"""
        bvid = searched["bvid"]
        page_num = int(searched.get("p", 1))

        return await self.parse_video(bvid=bvid, page_num=page_num)

    @handle(
        "/av",
        r"bilibili\.com(?:/video)?/av(?P<avid>\d{6,})",
        params={"p": {"default": "1", "as_int": True, "required": False}},
    )
    @handle("av", r"^av(?P<avid>\d{6,})(?:\s)?(?P<p>\d{1,3})?$")
    async def _parse_av(self, searched: MatchWithParams):
        """解析视频信息"""
        avid = int(searched["avid"])
        page_num = int(searched["p"])

        return await self.parse_video(avid=avid, page_num=page_num)

    @handle("/dynamic/", r"bilibili\.com/dynamic/(?P<dynamic_id>\d+)")
    @handle("t.bili", r"t\.bilibili\.com/(?P<dynamic_id>\d+)")
    @handle("/opus/", r"bilibili\.com/opus/(?P<dynamic_id>\d+)")
    async def _parse_dynamic(self, searched: MatchWithParams):
        """解析动态信息"""
        return await self.parse_dynamic_or_opus(searched["dynamic_id"])

    @handle("live.bili", r"live\.bilibili\.com/(?P<room_id>\d+)")
    async def _parse_live(self, searched: MatchWithParams):
        """解析直播信息"""
        room_id = int(searched["room_id"])
        return await self.parse_live(room_id)

    @handle("/favlist", r"favlist\?fid=(?P<fav_id>\d+)")
    async def _parse_favlist(self, searched: MatchWithParams):
        """解析收藏夹信息"""
        fav_id = int(searched["fav_id"])
        return await self.parse_favlist(fav_id)

    @handle("/read/", r"bilibili\.com/read/cv(?P<read_id>\d+)")
    async def _parse_read(self, searched: MatchWithParams):
        """解析专栏信息"""
        read_id = int(searched["read_id"])
        return await self.parse_read(read_id)

    async def parse_video(
        self,
        *,
        bvid: str | None = None,
        avid: int | None = None,
        page_num: int = 1,
    ):
        """解析视频信息

        :param bvid: bvid
        :param avid: avid
        :param page_num: 页码
        """

        video = await self._get_video(bvid=bvid, avid=avid)
        video_info: view_pb2.ViewReply = await video.get_info()
        arc = video_info.arc

        await self.raise_if_in_black_list(arc.author.mid)

        text = f"简介: {arc.desc}" if arc.desc else ""
        author = self.create_author(
            name=arc.author.name,
            avatar_url=arc.author.face,
            id=str(arc.author.mid),
            avatar_cache_key=f"bilibili:{arc.author.mid}",
        )

        page_index = page_num - 1
        title = arc.title
        duration = arc.duration
        timestamp = arc.pubdate
        cover = arc.pic or None
        if len(video_info.pages) > 1:
            page_index %= len(video_info.pages)
            page = video_info.pages[page_index].page
            title = f"{title} | 分集 - {page.part}"
            duration = page.duration
            cover = page.first_frame or cover
        elif video_info.pages:
            page_index = 0

        if self._credential:
            cid = await video.get_cid(page_index)
            ai_conclusion = await video.get_ai_conclusion(cid)
            ai_conclusion = convert(ai_conclusion, AIConclusion)
            ai_summary = ai_conclusion.summary
        else:
            ai_summary: str = "哔哩哔哩 cookie 未配置或失效, 无法使用 AI 总结"

        bvid = video_info.bvid or video.bvid
        url = f"https://bilibili.com/{bvid}"
        url += f"?p={page_index + 1}" if page_index > 0 else ""

        video_stream, audio_stream = await self.get_download_streams(
            video=video, page_index=page_index
        )
        video_urls = (video_stream.url, *video_stream.backup_url)
        audio_urls = (
            (audio_stream.url, *audio_stream.backup_url) if audio_stream else None
        )
        cache_key = f"bilibili:{bvid}:{page_index + 1}"
        retryable_http_statuses = self.BILI_RETRYABLE_HTTP_STATUSES

        class BiliVideoDownloader:
            def __init__(
                self,
                video_urls: tuple[str, ...],
                audio_urls: tuple[str, ...] | None,
                ext_headers: dict[str, str] | None,
            ):
                self.url = video_urls[0]
                self.video_urls = video_urls
                self.audio_urls = audio_urls
                self.ext_headers = ext_headers

            async def __call__(self) -> Path:
                # 有单独音频流时，走 av 合并
                if self.audio_urls:
                    return await DOWNLOADER.download_av_and_merge(
                        video_url=self.url,
                        audio_url=self.audio_urls[0],
                        video_fallback_urls=self.video_urls[1:],
                        audio_fallback_urls=self.audio_urls[1:],
                        retry_http_statuses=retryable_http_statuses,
                        cache_key=cache_key,
                        ext_headers=self.ext_headers,
                    )
                # 否则直接用流式下载
                return await DOWNLOADER.download_video(
                    url=self.url,
                    fallback_urls=self.video_urls[1:],
                    retry_http_statuses=retryable_http_statuses,
                    cache_key=cache_key,
                    cache_variant="source",
                    ext_headers=self.ext_headers,
                )

        downloader = BiliVideoDownloader(video_urls, audio_urls, self.headers)

        video_content = self.create_video(
            url_or_task=downloader,
            cover_url=cover,
            duration=duration,
            ext_headers=self.headers,
            cache_key=cache_key,
        )

        async def probe_head_size(url: str) -> int | None:
            return await DOWNLOADER.head_size(
                url=url,
                ext_headers=self.headers,
            )

        source_sizes = await asyncio.gather(
            *(
                probe_source_size(urls, probe_head_size)
                for urls in (video_urls, audio_urls)
            ),
        )
        total_size = sum(filter(None, source_sizes))
        if total_size:
            video_content._size_bytes = total_size

        # 提取统计数据
        stats = self.create_stats()
        try:
            if video_info.HasField("arc") and arc.HasField("stat"):
                stats.view_count = format_num(arc.stat.view)
                stats.like_count = format_num(arc.stat.like)
                stats.collect_count = format_num(arc.stat.fav)
                stats.share_count = format_num(arc.stat.share)
                stats.comment_count = format_num(arc.stat.reply)
                stats.extra = {
                    "danmaku": format_num(arc.stat.danmaku),
                    "coin": format_num(arc.stat.coin),
                }
                logger.debug(f"视频统计数据: {stats}")
        except Exception as e:
            logger.warning(f"统计数据提取异常: {e}")

        try:
            if bvid.startswith("BV"):
                video_oid = bv2av(bvid)
                logger.debug(f"BV号 {bvid} 转换为AV号 {video_oid}")
            else:
                # 如果不是BV号，直接使用
                video_oid = int(bvid)
        except Exception as e:
            logger.error(f"BV-AV转换失败: {e}")
            # 转换失败时使用BV号的数值形式作为oid
            video_oid = int(bvid.replace("BV", ""), 36)
            logger.debug(f"使用备用方法获取oid: {video_oid}")

        # 获取评论数据 - _fetch_comments方法已经处理好所有数据
        comments = await self._fetch_comments(video_oid, CommentResourceType.VIDEO)
        processed_comments = comments

        return self.result(
            url=url,
            title=title,
            timestamp=timestamp,
            author=author,
            content=[video_content, text],
            stats=stats,
            comments=processed_comments,
            ai_summary=ai_summary,
            embed_url=f"https://player.bilibili.com/player.html?aid={video.aid}&autoplay=1&p={page_num}",
        )

    async def parse_dynamic_or_opus(self, dynamic_id: str):
        """解析动态和图文信息"""

        dynamic = Dynamic(dynamic_id, await self.credential)
        logger.debug(f"B站解析 动态链接 原始：{dynamic}")

        # 图文/专栏类型统一走 Opus 逻辑
        if await dynamic.is_opus():
            return await self._parse_opus_obj(dynamic.turn_to_opus())

        dynamic_info_data = await dynamic.get_info()
        logger.debug(f"B站动态链接 dynamic_info_data 原始：{dynamic_info_data}")

        result = self.result(
            author=self.create_author(name=""),
            url=f"https://t.bilibili.com/{dynamic_id}",
            content=[],
        )
        build_dynamic(result, dynamic_info_data)

        if result.author.id:
            await self.raise_if_in_black_list(int(result.author.id))

        comment_oid = int(dynamic_id)
        comment_type = CommentResourceType.DYNAMIC
        if dynamic_info_data.item.card_type == dynamic_pb2.av:
            for module in dynamic_info_data.item.modules:
                if module.WhichOneof("module_item") != "module_dynamic":
                    continue
                module_dynamic = module.module_dynamic
                if module_dynamic.WhichOneof("module_item") != "dyn_archive":
                    continue
                if module_dynamic.dyn_archive.avid:
                    comment_oid = module_dynamic.dyn_archive.avid
                    comment_type = CommentResourceType.VIDEO
                break

        comments = await self._fetch_comments(comment_oid, comment_type)
        if comments:
            logger.debug(f"成功获取 {len(comments)} 条动态评论")
        else:
            logger.debug("未获取到动态评论")

        result.comments = comments
        return result

    async def parse_opus(self, opus_id: int):
        """解析图文信息

        :param opus_id: 图文动态 id
        :param is_repost: 是否为转发动态. 转发则使用九宫格排版图片
        """
        opus = Opus(opus_id, await self.credential)
        logger.debug(f"B站OPUS解析 图文 原始：{opus}")
        return await self._parse_opus_obj(opus)

    async def parse_read(self, read_id: int):
        """解析专栏信息, 使用 Opus 接口

        :param read_id: 专栏 id
        """

        bili_opus = Opus(read_id, await self.credential)
        logger.debug(f"B站OPUS解析 专栏 原始：{bili_opus}")
        return await self._parse_opus_obj(bili_opus)

    async def _parse_opus_obj(self, bili_opus: Opus):
        """渲染 OpusDetail protobuf 返回的模块"""
        response = await bili_opus.get_info()
        if not response.HasField("opus_item"):
            raise ParseException("获取图文信息失败")
        item = response.opus_item
        result = self.result(
            url=f"https://www.bilibili.com/opus/{item.opus_id or item.oid}",
            content=[],
            author=self.create_author(name=""),
        )
        title = ""
        for module in item.modules:
            kind = module.WhichOneof("module_item")
            if kind == "module_author":
                author = module.module_author
                result.author = self.create_author(
                    name=author.author.name,
                    avatar_url=author.author.face or None,
                    id=str(author.mid),
                    avatar_cache_key=f"bilibili:{author.mid}",
                )
                if result.timestamp is None:
                    result.timestamp = _parse_timestamp(author.ptime_label_text)
                if author.mid:
                    await self.raise_if_in_black_list(author.mid)
            # elif kind == "module_desc":
            #     result.content.extend(_description_items(module.module_desc))
            elif kind == "module_dynamic":
                _append_dynamic_payload(result, module.module_dynamic, set())
            elif kind == "module_opus_summary":
                summary = module.module_opus_summary
                _append_opus_summary(result, summary)
                if (
                    summary.HasField("title")
                    and summary.title.WhichOneof("content") == "text"
                ):
                    title = _text_node_plain_text(summary.title.text.nodes)
            elif kind == "module_paragraph":
                _append_paragraph(result, module.module_paragraph, paragraph_break=True)
            elif kind == "module_stat":
                _apply_stat(result, module.module_stat)
            elif kind == "module_buttom":
                if module.module_buttom.HasField("module_stat"):
                    _apply_stat(result, module.module_buttom.module_stat)

        if title:
            result.title = title
        oid = item.oid or item.opus_id
        comment_type = (
            CommentResourceType.ARTICLE
            if item.opus_type == opus_pb2.OPUS_TYPE_ARTICLE
            else CommentResourceType.OPUS
        )
        result.comments = await self._fetch_comments(int(oid), comment_type)
        return result

    async def parse_live(self, room_id: int):
        """解析直播信息

        :param room_id: 直播 id
        """

        room = LiveRoom(room_display_id=room_id)
        logger.debug(f"B站直播解析原始：{room}")
        info_dict = await room.get_room_info()

        room_data = convert(info_dict, RoomData)

        await self.raise_if_in_black_list(room_data.uid)

        content: list[ContentItem] = []
        # 下载封面
        if cover := room_data.cover:
            content.append(self.create_graphic(cover))

        # 下载关键帧
        if keyframe := room_data.keyframe:
            content.append(self.create_graphic(keyframe))

        try:
            user_info = await get_user_info(room_data.uid)
        except BiliHelperException as error:
            logger.warning(f"获取直播主播资料失败: {error}")
            user_info = None
        author = self.create_author(
            name=user_info.name if user_info else str(room_data.uid),
            avatar_url=user_info.face if user_info else None,
            id=user_info.mid if user_info else str(room_data.uid),
            avatar_cache_key=f"bilibili:{room_data.uid}",
        )

        url = f"https://www.bilibili.com/blackboard/live/live-activity-player.html?enterTheRoom=0&cid={room_id}"

        return self.result(
            url=url,
            title=room_data.title,
            content=content,
            author=author,
        )

    async def parse_favlist(self, fav_id: int):
        """解析收藏夹信息

        :param fav_id (int): 收藏夹 id
        """

        # 只会取一页，20 个
        fav_dict = await get_video_favorite_list_content(fav_id)

        if fav_dict["medias"] is None:
            raise ParseException("收藏夹内容为空, 或被风控")

        favdata = convert(fav_dict, FavData)

        await self.raise_if_in_black_list(favdata.info.upper.mid)

        return self.result(
            title=favdata.title,
            timestamp=favdata.timestamp,
            author=self.create_author(
                name=favdata.info.upper.name,
                avatar_url=favdata.info.upper.face,
                id=str(favdata.info.upper.mid),
                avatar_cache_key=f"bilibili:{favdata.info.upper.mid}",
            ),
            content=[
                self.create_graphic(fav.cover, fav.desc) for fav in favdata.medias
            ],
            url=f"https://space.bilibili.com/{favdata.info.upper.mid}/favlist?fid={fav_id}",
        )

    async def _get_video(
        self, *, bvid: str | None = None, avid: int | None = None
    ) -> Video:
        """解析视频信息

        :param bvid: bvid
        :param avid: avid
        """
        if avid:
            return Video(aid=avid, credential=await self.credential)
        elif bvid:
            return Video(bvid=bvid, credential=await self.credential)
        else:
            raise ParseException("avid 和 bvid 至少指定一项")

    async def get_download_streams(
        self,
        video: Video | None = None,
        *,
        bvid: str | None = None,
        avid: int | None = None,
        page_index: int = 0,
    ) -> tuple[
        VideoStreamDownloadURL | FLVStreamDownloadURL | MP4StreamDownloadURL,
        AudioStreamDownloadURL | None,
    ]:
        """获取最佳视频和音频下载流，并保留备用 CDN 地址

        :param bvid: bvid
        :param avid: avid
        :param page_index: 页索引 = 页码 - 1
        """

        if video is None:
            video = await self._get_video(bvid=bvid, avid=avid)

        download_url_data = await video.get_download_url(page_index=page_index)
        detecter = VideoDownloadURLDataDetecter(download_url_data)
        streams = detecter.detect_best_streams(
            video_max_quality=pconfig.bili_video_quality,
            codecs=pconfig.bili_video_codes,
            no_dolby_video=True,
            no_hdr=True,
            cdn_region=pconfig.bili_cdn_region,
            cdn_domain=pconfig.bili_cdn_domain,
        )
        video_stream = streams[0]
        if video_stream is None:
            async with aiofiles.open(
                f"{video.bvid}_not_found.json", "w", encoding="utf-8"
            ) as f:
                await f.write(MessageToJson(download_url_data))
            raise DownloadException(
                "未找到可下载的视频流, "
                f"你可以将Bot目录下的 '{video.bvid}_not_found.json'"
                " 文件提供给开发者以定位问题"
            )
        logger.debug(
            f"视频流 {type(video_stream)}"
            + (
                f" 视频流质量: {video_stream.video_quality.name},"
                f" 编码: {video_stream.video_codecs}"
                if isinstance(video_stream, VideoStreamDownloadURL)
                else ""
            )
        )
        audio_stream = streams[1]
        if audio_stream is not None:
            logger.debug(f"音频流质量: {audio_stream.audio_quality.name}")
        return video_stream, audio_stream

    async def _save_credential(self):
        """存储哔哩哔哩登录凭证"""
        if self._credential is None:
            return

        await self._credential.save_file(self._credential_file)

    async def login_with_qrcode(self) -> bytes:
        """通过二维码登录获取哔哩哔哩登录凭证"""
        self._qr_login = QrCodeLogin()
        return await self._qr_login.generate_qrcode()

    async def check_qr_state(self) -> AsyncGenerator[str]:
        """检查二维码登录状态"""
        scan_tip_pending = True

        for _ in range(30):
            state = await self._qr_login.check_state()
            match state:
                case QrCodeLoginEvents.DONE:
                    yield "登录成功"
                    self._credential = self._qr_login.get_credential()
                    await self._save_credential()
                    await self.load_black_list()
                    break
                case QrCodeLoginEvents.CONF:
                    if scan_tip_pending:
                        yield "二维码已扫描, 请确认登录"
                        scan_tip_pending = False
                case QrCodeLoginEvents.TIMEOUT:
                    yield "二维码过期, 请重新生成"
                    break
            await asyncio.sleep(2)
        else:
            yield "二维码登录超时, 请重新生成"

    async def _init_credential(self) -> None:
        """初始化哔哩哔哩登录凭证.

        优先顺序:
        1. 本地 cookies 文件
        2. 配置中的 bili_ck
        """
        if await self._credential_file.exists():
            try:
                self._credential = await Credential.from_file(self._credential_file)
                return
            except Exception as e:
                logger.warning(f"读取本地凭证失败，将尝试使用配置 ck: {e!r}")
        logger.warning("凭证文件不存在")

    async def _fetch_comments(
        self, oid: int, type: CommentResourceType
    ) -> list[Comment]:
        """从 Bilibili API 获取评论数据，优先热评，失败时兜底普通评论"""

        try:
            try:
                data = await get_comments(
                    oid=oid,
                    type=type,
                    credential=await self.credential,
                )
            except BiliHelperException as e:
                logger.warning(f"bili评论返回数据错误: {e.msg}")
                return []

            merged: list[reply_pb2.ReplyInfo] = []
            seen_rpids: set[int] = set()

            def _append_unique(src: Iterable[reply_pb2.ReplyInfo]) -> None:
                for item in src:
                    if not item.id or item.id in seen_rpids:
                        continue
                    seen_rpids.add(item.id)
                    merged.append(item)

            has_upper = data.HasField("up_top") and bool(data.up_top.id)
            if has_upper:
                _append_unique((data.up_top,))
            _append_unique(data.top_replies)
            _append_unique(data.replies)

            logger.debug(
                f"bili获得评论: upper={int(has_upper)}, "
                f"replies={len(data.replies)}, merged={len(merged)}",
            )
            # upper 置顶评论始终首位，其余按 like 数降序排序
            if merged:
                if has_upper and len(merged) > 1:
                    head = merged[0]
                    tail = merged[1:]
                    tail.sort(
                        key=lambda item: item.like,
                        reverse=True,
                    )
                    merged = [head, *tail]
                else:
                    merged.sort(
                        key=lambda item: item.like,
                        reverse=True,
                    )
            return self._process_reply_list(merged[: pconfig.max_comments])

        except Exception as e:
            logger.error(f"[Bilibili] 获取评论失败: {e!r}")
            return []

    def _format_content_with_emote(self, raw: str, emote) -> list[ContentItem]:
        """将原始 message + emote 渲染为媒体列表"""
        if not raw:
            return [""]
        if not emote:
            return [raw]

        length = len(raw)
        cursor = 0
        parts: list[ContentItem] = []

        # 预处理所有可用表情：表情文本及封装好的 ContentItem
        emote_entries: list[tuple[str, ContentItem]] = []
        for key, e in emote.items():
            text = e.text or key
            if not text:
                continue

            size = "small" if e.size == 1 else "medium"
            sticker = self.create_sticker(e.url, size, text)
            emote_entries.append((text, sticker))

        if not emote_entries:
            return [raw]

        while cursor < length:
            best_pos = length  # 当前找到的最近表情位置
            best_end = cursor
            best_media = None

            # 在 [cursor, length) 范围内寻找「起始位置最靠前」的一次表情命中
            for text, media in emote_entries:
                idx = raw.find(text, cursor, best_pos + len(text))
                if idx == -1:
                    continue

                # 起始位置更靠前则更新；相同位置时略过，保持首次命中即可
                if idx < best_pos:
                    best_pos = idx
                    best_end = idx + len(text)
                    best_media = media

                    # 已经在 cursor 命中，无法再更早，直接退出
                    if best_pos == cursor:
                        break

            # 没找到任何后续表情，剩余部分整体作为文本
            if best_media is None:
                if tail := raw[cursor:]:
                    parts.append(tail)
                break

            # 先追加文本段
            if best_pos > cursor:
                if text_part := raw[cursor:best_pos]:
                    parts.append(text_part)

            # 再追加表情段
            parts.append(best_media)
            cursor = best_end

        return parts

    def _process_reply_list(self, replies: list[reply_pb2.ReplyInfo]) -> list[Comment]:
        """将 B 站评论列表转换为 Comment 列表"""

        def _build_single_comment(
            raw: reply_pb2.ReplyInfo, parent_author: Author | None = None
        ) -> Comment:
            content = raw.content
            processed_content = self._format_content_with_emote(
                content.message, content.emote
            )

            for picture in content.pictures:
                if picture.img_src:
                    processed_content.append(self.create_image(picture.img_src))

            member = raw.member
            return self.create_comment(
                author=self.create_author(
                    name=member.name,
                    avatar_url=member.face or None,
                    id=str(member.mid) if member.mid else None,
                    location=raw.reply_control.location or None,
                ),
                content=processed_content,
                timestamp=raw.ctime,
                stats=self.create_stats(like_count=format_num(raw.like)),
                parent_author=parent_author,
            )

        processed_comments: list[Comment] = []

        for comment in replies:
            comment_obj = _build_single_comment(comment)
            # 子回复
            child_posts: list[Comment] = []
            for reply in comment.replies[:5]:
                child_posts.append(_build_single_comment(reply, comment_obj.author))

            comment_obj.stats.comment_count = format_num(comment.count)
            comment_obj.replies = child_posts

            processed_comments.append(comment_obj)

        return processed_comments

    @property
    async def credential(self) -> Credential | None:
        """哔哩哔哩登录凭证"""

        if self._credential is None:
            await self._init_credential()
            return self._credential

        if self._credential.check_refresh():
            logger.info("哔哩哔哩凭证需要刷新")
            if self._credential.access_token and self._credential.refresh_token:
                try:
                    await self._credential.refresh()
                except CookiesRefreshException as e:
                    logger.warning(f"刷新哔哩哔哩凭证失败: {e.msg}")
                    if "correspondPath" in e.msg:
                        raise TipException(
                            "刷新哔哩哔哩凭证失败, 可能是设备时间不正确"
                        ) from e
                    raise TipException(f"刷新哔哩哔哩凭证失败: {e.msg}") from e
                logger.info(f"哔哩哔哩凭证刷新成功, 保存到 {self._credential_file}")
                await self._save_credential()
            else:
                logger.warning(
                    "哔哩哔哩凭证刷新需要包含 `access_token`, `refresh_token` 项"
                )

        return self._credential
