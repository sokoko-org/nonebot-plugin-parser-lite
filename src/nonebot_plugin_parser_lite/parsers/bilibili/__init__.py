import asyncio
from collections.abc import AsyncGenerator
import contextlib
import json
import re
from typing import Any, ClassVar

import aiofiles
from anyio import Path
from bilibili_api import HEADERS, Credential, request_settings, select_client
from bilibili_api.article import Article
from bilibili_api.dynamic import Dynamic
from bilibili_api.exceptions import CookiesRefreshException
from bilibili_api.favorite_list import get_video_favorite_list_content
from bilibili_api.live import LiveRoom
from bilibili_api.login_v2 import QrCodeLogin, QrCodeLoginEvents
from bilibili_api.opus import Opus
from bilibili_api.utils.network import get_buvid
from bilibili_api.video import Video
from msgspec import convert
from nonebot import logger

from ...exception import DownloadException, TipException
from ...utils.cookie import ck2dict
from ...utils.format import format_num
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
    Stats,
    handle,
    pconfig,
)
from .dynamic import DynamicData, DynamicInfo
from .favlist import FavData
from .live import RoomData
from .opus import ImageNode, OpusItem, TextNode
from .utils import (
    AudioStreamDownloadURL,
    VideoDownloadURLDataDetecter,
    VideoStreamDownloadURL,
)
from .video import AIConclusion, VideoInfo

# 选择客户端
select_client("curl_cffi")
# 模拟浏览器，第二参数数值参考 curl_cffi 文档
# https://curl-cffi.readthedocs.io/en/latest/impersonate.html
request_settings.set("impersonate", "chrome131")


class BilibiliParser(BaseParser):
    platform: ClassVar[Platform] = Platform(
        name=PlatformEnum.BILIBILI, display_name="哔哩哔哩"
    )

    def __init__(self):
        super().__init__()
        self.headers = HEADERS.copy()
        self._credential: Credential | None = None
        self._cookies_file = pconfig.config_dir / "bilibili_cookies.json"
        self.ck_header = self.headers.copy()
        self.black_mids: list[int] | None = None
        """黑名单作者列表"""
        self._black_list_job_added: bool = False

    async def load_black_list(self) -> None:
        """初始化黑名单"""
        ck = await self.credential
        if not ck:
            logger.info("B站未登录，跳过黑名单加载")
            self.black_mids = []
            return

        cookies = ck.get_cookies()
        if not cookies:
            logger.info("B站 Cookie 为空，跳过黑名单加载")
            self.black_mids = []
            return

        self.ck_header["Cookie"] = "; ".join(f"{k}={v}" for k, v in cookies.items())

        base_url = "https://api.bilibili.com/x/relation/blacks"
        page_size = 50
        black_mids: list[int] = []

        try:
            resp = await self.httpx.get(
                base_url,
                headers=self.ck_header,
                params={"ps": page_size, "pn": 1},
            )
            resp.raise_for_status()
            data: dict[str, Any] = resp.json()

            code = data.get("code")
            if code != 0:
                logger.error(f"获取B站黑名单列表失败: code={code}, data={data}")
                self.black_mids = []
                return

            data_root = data.get("data", {})
            first_list = data_root.get("list", [])
            total = data_root.get("total", 0)

            black_mids.extend(obj["mid"] for obj in first_list)

            # 计算剩余页数
            pages = (total + page_size - 1) // page_size if total > page_size else 1
            for pn in range(2, pages + 1):
                try:
                    resp = await self.httpx.get(
                        base_url,
                        headers=self.ck_header,
                        params={"ps": page_size, "pn": pn},
                    )
                    resp.raise_for_status()
                    page_data: dict[str, Any] = resp.json()
                    if page_data.get("code") != 0:
                        logger.warning(f"获取B站黑名单第 {pn} 页失败: {page_data!r}")
                        continue
                    page_list = page_data.get("data", {}).get("list", [])
                    black_mids.extend(obj["mid"] for obj in page_list)
                    logger.debug(
                        f"黑名单第 {pn} 页加载完成, 当前共 {len(black_mids)} 个"
                    )
                    await asyncio.sleep(0.2)
                except Exception as e:
                    logger.warning(f"请求B站黑名单第 {pn} 页异常: {e}")
                    continue

            self.black_mids = black_mids
            logger.debug(f"B站黑名单列表: {black_mids}")
            logger.info(
                f"已加载 {len(self.black_mids)} 个 B 站黑名单用户 (pages={pages})"
            )

            # 首次成功加载黑名单后，注册定时刷新任务（最多注册一次）
            if not self._black_list_job_added:
                try:
                    from nonebot_plugin_apscheduler import scheduler

                    scheduler.add_job(
                        self.load_black_list,
                        "interval",
                        hours=1,
                        id="sync-bili-black-list",
                        replace_existing=True,
                    )
                    self._black_list_job_added = True
                    logger.info("已注册 B 站黑名单定时同步任务（每 1 小时刷新一次）")
                except Exception as e:
                    logger.warning(f"注册 B 站黑名单定时任务失败: {e}")

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
        dynamic_id = int(searched["dynamic_id"])
        return await self.parse_dynamic_or_opus(dynamic_id)

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

    XOR_CODE = 23442827791579
    MASK_CODE = 2251799813685247
    MAX_AID = 1 << 51
    ALPHABET = "FcwAPNKTMug3GV5Lj7EJnHpWsx4tb8haYeviqBz6rkCy12mUSDQX9RdoZf"
    ENCODE_MAP = (8, 7, 0, 5, 1, 3, 2, 4, 6)
    DECODE_MAP = tuple(reversed(ENCODE_MAP))

    BASE = len(ALPHABET)
    PREFIX = "BV1"
    PREFIX_LEN = len(PREFIX)
    CODE_LEN = len(ENCODE_MAP)

    @classmethod
    def av2bv(cls, aid: int) -> str:
        """将AV号转换为BV号"""
        bvid = [""] * 9
        tmp = (cls.MAX_AID | aid) ^ cls.XOR_CODE
        for i in range(cls.CODE_LEN):
            bvid[cls.ENCODE_MAP[i]] = cls.ALPHABET[tmp % cls.BASE]
            tmp //= cls.BASE
        return cls.PREFIX + "".join(bvid)

    @classmethod
    def bv2av(cls, bvid: str) -> int:
        """将BV号转换为AV号"""
        assert bvid[: cls.PREFIX_LEN] == cls.PREFIX

        bvid = bvid[cls.PREFIX_LEN :]
        tmp = 0
        for i in range(cls.CODE_LEN):
            idx = cls.ALPHABET.index(bvid[cls.DECODE_MAP[i]])
            tmp = tmp * cls.BASE + idx
        return (tmp & cls.MASK_CODE) ^ cls.XOR_CODE

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
        # 转换为 msgspec struct
        video_info = convert(await video.get_info(), VideoInfo)

        await self.raise_if_in_black_list(video_info.owner.mid)

        # 获取简介
        text = f"简介: {video_info.desc}" if video_info.desc else ""
        # up
        author = self.create_author(
            name=video_info.owner.name,
            avatar_url=video_info.owner.face,
            id=str(video_info.owner.mid),
        )
        # 处理分 p
        page_info = video_info.extract_info_with_page(page_num)

        # 获取 AI 总结
        if self._credential:
            cid = await video.get_cid(page_info.index)
            ai_conclusion = await video.get_ai_conclusion(cid)
            ai_conclusion = convert(ai_conclusion, AIConclusion)
            ai_summary = ai_conclusion.summary
        else:
            ai_summary: str = "哔哩哔哩 cookie 未配置或失效, 无法使用 AI 总结"

        url = f"https://bilibili.com/{video_info.bvid}"
        url += f"?p={page_info.index + 1}" if page_info.index > 0 else ""

        # 获取真实视频 / 音频 URL
        v_url, a_url = await self.extract_download_urls(
            video=video, page_index=page_info.index
        )

        class BiliVideoDownloader:
            def __init__(
                self,
                video_url: str,
                audio_url: str | None,
                ext_headers: dict[str, str] | None,
            ):
                self.video_url = video_url
                self._audio_url = audio_url
                self.ext_headers = ext_headers

            async def __call__(self) -> Path:
                file_base = f"{video_info.bvid}-{page_num}"
                # 有单独音频流时，走 av 合并
                if self._audio_url:
                    return await DOWNLOADER.download_av_and_merge(
                        self.video_url,
                        self._audio_url,
                        file_name=file_base,
                        ext_headers=self.ext_headers,
                    )
                # 否则直接用流式下载
                return await DOWNLOADER.streamd(
                    url=self.video_url,
                    file_name=f"{file_base}.mp4",
                    ext_headers=self.ext_headers,
                )

        downloader = BiliVideoDownloader(v_url, a_url, self.headers)

        # 创建视频下载内容（传递自定义下载器，而非立即执行）
        video_content = self.create_video(
            url_or_task=downloader,
            cover_url=page_info.cover,
            duration=page_info.duration,
            ext_headers=self.headers,
        )

        # 提取统计数据
        stats = self.create_stats()
        try:
            if video_info.stat:
                stats.view_count = format_num(video_info.stat.view)
                stats.like_count = format_num(video_info.stat.like)
                stats.collect_count = format_num(video_info.stat.favorite)
                stats.share_count = format_num(video_info.stat.share)
                stats.comment_count = format_num(video_info.stat.reply)
                stats.extra = {
                    "danmaku": format_num(video_info.stat.danmaku),
                    "coin": format_num(video_info.stat.coin),
                }
                logger.debug(f"视频统计数据: {stats}")
        except Exception as e:
            logger.warning(f"统计数据提取异常: {e}")

        # 使用BV-AV转换算法将BV号转换为AV号
        bvid = video_info.bvid
        try:
            if bvid.startswith("BV"):
                # 使用类中已封装的bv2av方法进行转换
                video_oid = self.bv2av(bvid)
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
        comments = await self._fetch_comments(video_oid, 1)  # type=1 表示视频
        processed_comments = comments

        # 构造 extra_data
        extra_data = {
            "type": "video",
            "type_tag": "视频",
            "type_icon": "fa-circle-play",
            "content_id": video_info.bvid,
        }
        logger.debug(f"Video extra data: {extra_data}")

        return self.result(
            url=url,
            title=page_info.title,
            timestamp=page_info.timestamp,
            author=author,
            content=[video_content, text],
            stats=stats,
            comments=processed_comments,
            extra=extra_data,
            ai_summary=ai_summary,
        )

    async def parse_dynamic_or_opus(self, dynamic_id: int):
        """解析动态和图文信息"""

        dynamic = Dynamic(dynamic_id, await self.credential)
        logger.debug(f"B站解析 动态链接 原始：{dynamic}")

        # 纯专栏：直接走 opus 逻辑
        if await dynamic.is_article():
            return await self._parse_opus_obj(dynamic.turn_to_opus())

        dynamic_info_data = await dynamic.get_info()
        logger.debug(f"B站动态链接 dynamic_info_data 原始：{dynamic_info_data}")
        dynamic_info = convert(dynamic_info_data, DynamicData).item

        await self.raise_if_in_black_list(dynamic_info.modules.module_author.mid)

        # 作者
        author = self.create_author(
            name=dynamic_info.name,
            avatar_url=dynamic_info.avatar,
            id=str(dynamic_info.modules.module_author.mid),
        )

        # 标题 & 文本
        dynamic_title = dynamic_info.title

        # 主体内容：文字 + 图片
        contents: list[ContentItem] = []
        contents.extend(await self._build_dynamic_contents(dynamic_info))
        # 统计数据
        stats = self._extract_dynamic_stats(dynamic_info)

        extra_data: dict[str, Any] = {
            "type": "dynamic",
            "type_tag": "动态",
            "type_icon": "fa-quote-left",
            "content_id": str(dynamic_id),
        }

        # 转发内容
        repost_result = await self._resolve_repost(dynamic_info)

        # 构建动态URL，用于二维码生成（使用t.bilibili.com格式）
        dynamic_url = f"https://t.bilibili.com/{dynamic_id}"

        # 评论
        comments = await self._fetch_dynamic_comments_safe(
            dynamic_id, dynamic_info, dynamic_info_data
        )
        if comments:
            logger.debug(f"成功获取 {len(comments)} 条动态评论")
        else:
            logger.debug("未获取到动态评论")

        return self.result(
            url=dynamic_url,
            title=dynamic_title,
            timestamp=dynamic_info.timestamp,
            author=author,
            content=contents,
            comments=comments,
            extra=extra_data,
            repost=repost_result,
            stats=stats,
        )

    async def _build_dynamic_contents(
        self, dynamic_info: DynamicInfo
    ) -> list[ContentItem]:
        """构建动态主体 contents：文字 + 图片。

        - 连续文本节点合并为一个字符串
        - 表情与图片保持独立元素
        """
        rich_nodes = dynamic_info.rich_text_nodes
        medias = dynamic_info.medias
        if not rich_nodes and not medias:
            return []

        contents: list[ContentItem] = []
        text_buffer: list[str] = []

        def flush_text_buffer() -> None:
            if text_buffer:
                contents.append("".join(text_buffer))
                text_buffer.clear()

        for node in rich_nodes:
            node_type = node.get("type")
            if node_type == "RICH_TEXT_NODE_TYPE_EMOJI":
                flush_text_buffer()
                e = node["emoji"]
                size = "small" if e["size"] == 1 else "medium"
                contents.append(self.create_sticker(e["icon_url"], size, e["text"]))
                continue
            if node_type == "RICH_TEXT_NODE_TYPE_VIEW_PICTURE":
                flush_text_buffer()
                for pic in node["pics"]:
                    medias.append(self.create_image(pic["src"]))
                continue

            text = node.get("text")
            if text:
                text_buffer.append(text)

        flush_text_buffer()

        contents.extend(medias)

        return contents

    def _extract_dynamic_stats(self, dynamic_info: DynamicInfo) -> Stats:
        """提取动态统计数据"""
        stats = self.create_stats()
        with contextlib.suppress(Exception):
            if dynamic_info.modules.module_stat:
                m_stat = dynamic_info.modules.module_stat
                stats.like_count = format_num(m_stat.get("like", {}).get("count", 0))
                stats.comment_count = format_num(
                    m_stat.get("comment", {}).get("count", 0)
                )
                stats.share_count = format_num(
                    m_stat.get("forward", {}).get("count", 0)
                )
                stats.collect_count = format_num(
                    m_stat.get("favorite", {}).get("count", 0)
                )
            modules = dynamic_info.modules
            if hasattr(modules, "module_author") and hasattr(
                modules.module_author, "views_text"
            ):
                views_value = modules.module_author.views_text
                if views_value is not None:
                    stats.view_count = views_value
        return stats

    async def _resolve_repost(self, dynamic_info: DynamicInfo):
        """处理转发动态，返回 repost_result"""
        if dynamic_info.type != "DYNAMIC_TYPE_FORWARD" or not dynamic_info.orig:
            return None

        orig_item = dynamic_info.orig
        if not orig_item.visible:
            # 源动态失效，按当前逻辑直接跳过
            return None

        # 尝试解析转发的主体类型信息
        major_type, _opus_jump_url, archive_bvid = self._get_repost_major_type(
            orig_item
        )

        # 图文 / 专栏
        # if major_type == "OPUS" and _opus_jump_url:
        #     return await self._handle_repost_article(_opus_jump_url)

        # 视频
        if major_type == "ARCHIVE" and archive_bvid:
            return await self._handle_repost_archive(archive_bvid)

        # 其他动态：递归解析原动态
        try:
            return await self.parse_dynamic_or_opus(int(orig_item.id_str))
        except Exception as e:
            logger.warning(f"解析转发动态失败: {e}")
            return None

    def _get_repost_major_type(
        self,
        orig_item: DynamicInfo,
    ) -> tuple[str | None, str | None, str | None]:
        """从转发的 orig_item 中识别主体类型和关键字段.

        返回:
            (major_type, opus_jump_url, archive_bvid)
            major_type: "OPUS" / "ARCHIVE" / None
        """
        major_info = orig_item.modules.major_info
        if not major_info:
            return None, None, None

        major_type_raw = major_info.get("type")
        opus_jump_url: str | None = None
        archive_bvid: str | None = None
        major_type: str | None = None

        if major_type_raw == "MAJOR_TYPE_OPUS":
            opus_data = major_info.get("opus", {}) or {}
            opus_jump_url = opus_data.get("jump_url")
            if opus_jump_url:
                major_type = "OPUS"
        elif major_type_raw == "MAJOR_TYPE_ARCHIVE":
            archive_data = major_info.get("archive", {}) or {}
            archive_bvid = archive_data.get("bvid")
            if archive_bvid:
                major_type = "ARCHIVE"

        return major_type, opus_jump_url, archive_bvid

    async def _handle_repost_article(self, jump_url: str):
        """处理转发的图文 / 专栏"""
        match = re.search(r"/opus/(\d+)", jump_url)
        opus_id = int(match[1]) if match else None
        if opus_id is None:
            return None
        try:
            return await self.parse_opus(opus_id)
        except Exception as e:
            logger.warning(f"解析转发专栏失败: {e}")
            return None

    async def _handle_repost_archive(self, bvid: str):
        """处理转发的视频"""
        try:
            return await self.parse_video(bvid=bvid)
        except Exception as e:
            logger.warning(f"解析转发视频失败: {e}")
            return None

    async def _fetch_dynamic_comments_safe(
        self,
        dynamic_id: int,
        dynamic_info: DynamicInfo,
        dynamic_info_data: dict[str, Any],
    ):
        """统一封装动态评论获取逻辑，减少 parse_dynamic_or_opus 的分支复杂度"""
        oid, ctype = self._resolve_comment_params(
            dynamic_id, dynamic_info, dynamic_info_data
        )
        comments = await self._fetch_comments(oid, ctype)
        logger.debug(f"动态评论参数: oid={oid}, type={ctype}, got={len(comments)}")
        return comments

    def _resolve_comment_params(
        self,
        dynamic_id: int,
        dynamic_info: DynamicInfo,
        dynamic_info_data: dict[str, Any],
    ) -> tuple[int, int]:
        """根据动态类型确定评论 oid / type"""
        # 1. 优先使用接口返回的 basic.comment_id_str / comment_type
        basic_info = dynamic_info_data.get("item", {}).get("basic", {}) or {}
        comment_id_str = basic_info.get("comment_id_str")
        comment_type = basic_info.get("comment_type")
        if comment_id_str and comment_type:
            return int(comment_id_str), int(comment_type)

        # 2. 再根据 major_type 猜测
        major_info = (
            dynamic_info.modules.major_info
            if hasattr(dynamic_info.modules, "major_info")
            else {}
        )
        major_type = major_info.get("type") if isinstance(major_info, dict) else None

        if major_type == "MAJOR_TYPE_ARCHIVE" and major_info:
            archive_data = major_info.get("archive", {})
            if aid := archive_data.get("aid"):
                return int(aid), 1  # 视频

        if major_type == "MAJOR_TYPE_OPUS" and major_info:
            opus_data = major_info.get("opus", {})
            if opus_id := opus_data.get("id") or opus_data.get("opus_id"):
                return int(opus_id), 12  # 专栏 / 图文

        if major_type == "MAJOR_TYPE_DRAW" and major_info:
            return dynamic_id, 11  # 图片动态

        # 3. 默认：普通动态
        return dynamic_id, 17

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

        article = Article(read_id)
        bili_opus = await article.turn_to_opus()
        logger.debug(f"B站OPUS解析 专栏 原始：{bili_opus}")
        return await self._parse_opus_obj(bili_opus)

    async def _parse_opus_obj(self, bili_opus: Opus):
        """解析图文信息

        :param opus_id: 图文 id
        """

        opus_info = await bili_opus.get_info()
        logger.debug(f"B站OPUS解析原始：{opus_info}")
        if not isinstance(opus_info, dict):
            raise ParseException("获取图文信息失败")
        # 转换为结构体
        opus_data = convert(opus_info, OpusItem)
        logger.debug(f"opus_data: {opus_data}")

        # 提取作者信息
        author_name = ""
        author_face = ""
        author_mid = 0

        if hasattr(opus_data.item, "modules"):
            for module in opus_data.item.modules:
                if module.module_type == "MODULE_TYPE_AUTHOR" and module.module_author:
                    author_name = module.module_author.name
                    author_face = module.module_author.face
                    author_mid = module.module_author.mid
                    break

        if author_mid:
            await self.raise_if_in_black_list(author_mid)

        if not author_name and hasattr(opus_data, "name_avatar"):
            author_name, author_face = opus_data.name_avatar

        author = self.create_author(
            name=author_name, id=str(author_mid), avatar_url=author_face
        )

        # 按顺序处理图文内容（参考 parse_read 的逻辑）
        contents: list[ContentItem] = []

        for node in opus_data.gen_text_img():
            if isinstance(node, ImageNode):
                # 使用 DOWNLOADER 下载并封装为 GraphicsContent
                contents.append(self.create_graphic(node.url, node.alt))

            elif isinstance(node, TextNode):
                contents.append(node.text)

        # 提取统计数据
        stats = self.create_stats()
        with contextlib.suppress(Exception):
            if hasattr(opus_data.item, "modules"):
                for module in opus_data.item.modules:
                    if module.module_type == "MODULE_TYPE_STAT" and module.module_stat:
                        st = module.module_stat
                        stats.like_count = format_num(
                            st.get("like", {}).get("count", 0)
                        )
                        stats.comment_count = format_num(
                            st.get("comment", {}).get("count", 0)
                        )
                        stats.share_count = format_num(
                            st.get("forward", {}).get("count", 0)
                        )
                        stats.collect_count = format_num(
                            st.get("favorite", {}).get("count", 0)
                        )
                    # 检查是否有浏览量字段
                    elif (
                        module.module_type == "MODULE_TYPE_AUTHOR"
                        and module.module_author
                    ):
                        if hasattr(module.module_author, "views_text"):
                            views_value = module.module_author.views_text
                            if views_value is not None:
                                stats.view_count = views_value
        # 构造 Extra 数据
        extra_data = {
            "type": "opus",
            "type_tag": "图文",
            "type_icon": "fa-file-pen",
            "content_id": opus_data.item.id_str,
        }

        # 优先使用basic.title作为标题，如果没有则使用提取的文本或默认值
        # 如果标题和文本内容一致，则将文本置空，避免重复展示
        basic_title = opus_data.title

        # 构建图文动态URL，用于二维码生成
        opus_id = bili_opus.get_opus_id()
        opus_url = f"https://www.bilibili.com/opus/{opus_id}"

        # 获取opus原始数据，用于提取评论参数
        opus_info = await bili_opus.get_info() if hasattr(bili_opus, "get_info") else {}
        # 确保opus_info是字典类型
        opus_info = opus_info if isinstance(opus_info, dict) else {}
        # 尝试从原始opus数据中获取评论参数
        comment_id_str = None
        comment_type = None
        item_info = opus_info.get("item", {})
        # 确保item_info是字典类型
        item_info = item_info if isinstance(item_info, dict) else {}
        basic_info = item_info.get("basic", {})
        # 确保basic_info是字典类型
        basic_info = basic_info if isinstance(basic_info, dict) else {}
        comment_id_str = basic_info.get("comment_id_str")
        comment_type = basic_info.get("comment_type")

        # 根据opus类型选择正确的评论参数
        if comment_id_str and comment_type:
            # 使用opus数据中提供的comment_id_str和comment_type
            comments = await self._fetch_comments(int(comment_id_str), comment_type)
            logger.debug(
                f"使用opus数据中提供的评论参数: oid={comment_id_str}, type={comment_type}"  # noqa: E501
            )
        else:
            content_id = str(opus_data.item.id_str)

            # 默认为图文动态，使用content_id作为oid，type=12
            comments = await self._fetch_comments(
                int(content_id), 12
            )  # type=12 表示专栏/图文
            logger.debug(f"使用content_id作为opus评论参数: oid={content_id}, type=12")

        if comments:
            logger.debug(f"成功获取 {len(comments)} 条专栏/图文评论")
        else:
            logger.debug("未获取到专栏/图文评论")

        return self.result(
            url=opus_url,
            title=basic_title,
            author=author,
            timestamp=opus_data.timestamp,
            content=contents,
            stats=stats,
            comments=comments,
            extra=extra_data,
        )

    async def parse_live(self, room_id: int):
        """解析直播信息

        :param room_id: 直播 id
        """

        room = LiveRoom(room_display_id=room_id, credential=await self.credential)
        logger.debug(f"B站直播解析原始：{room}")
        info_dict = await room.get_room_info()

        room_data = convert(info_dict, RoomData)

        await self.raise_if_in_black_list(room_data.mid)

        contents: list[ContentItem] = [room_data.detail]
        # 下载封面
        if cover := room_data.cover:
            contents.append(self.create_image(cover))

        # 下载关键帧
        if keyframe := room_data.keyframe:
            contents.append(self.create_image(keyframe))

        author = self.create_author(
            name=room_data.name, avatar_url=room_data.avatar, id=str(room_data.mid)
        )

        url = f"https://www.bilibili.com/blackboard/live/live-activity-player.html?enterTheRoom=0&cid={room_id}"

        extra_data = {
            "type": "live",
            "type_tag": f"直播·{room_data.room_info.parent_area_name}",
            "type_icon": "fa-tower-broadcast",
            "content_id": f"ROOM{room_id}",
            "tags": str(room_data.room_info.tags),
            "live_info": {
                "level": str(room_data.anchor_info.live_info.level),
                "level_color": str(room_data.anchor_info.live_info.level_color),
                "score": str(room_data.anchor_info.live_info.score),
            },
        }

        return self.result(
            url=url,
            title=room_data.title,
            content=contents,
            author=author,
            extra=extra_data,
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

    async def extract_download_urls(
        self,
        video: Video | None = None,
        *,
        bvid: str | None = None,
        avid: int | None = None,
        page_index: int = 0,
    ) -> tuple[str, str | None]:
        """解析视频下载链接

        :param bvid: bvid
        :param avid: avid
        :param page_index: 页索引 = 页码 - 1
        """

        if video is None:
            video = await self._get_video(bvid=bvid, avid=avid)

        # 获取下载数据
        download_url_data = await video.get_download_url(page_index=page_index)
        detecter = VideoDownloadURLDataDetecter(download_url_data)
        streams = detecter.detect_best_streams(
            video_max_quality=pconfig.bili_video_quality,
            codecs=pconfig.bili_video_codes,
            no_dolby_video=True,
            no_hdr=True,
        )
        video_stream = streams[0]
        if not isinstance(video_stream, VideoStreamDownloadURL):
            raise DownloadException("未找到可下载的视频流")
        logger.debug(
            f"视频流质量: {video_stream.video_quality.name}, 编码: {video_stream.video_codecs}"  # noqa: E501
        )
        audio_stream = streams[1]
        if not isinstance(audio_stream, AudioStreamDownloadURL):
            return video_stream.url, None
        logger.debug(f"音频流质量: {audio_stream.audio_quality.name}")
        return video_stream.url, audio_stream.url

    async def _save_credential(self):
        """存储哔哩哔哩登录凭证"""
        if self._credential is None:
            return

        async with aiofiles.open(self._cookies_file, "w", encoding="utf-8") as f:
            await f.write(json.dumps(await self._credential.get_buvid_cookies()))

    async def login_with_qrcode(self) -> bytes:
        """通过二维码登录获取哔哩哔哩登录凭证"""
        self._qr_login = QrCodeLogin()
        await self._qr_login.generate_qrcode()

        qr_pic = self._qr_login.get_qrcode_picture()
        return qr_pic.content

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
        if await self._cookies_file.exists():
            try:
                async with aiofiles.open(self._cookies_file, encoding="utf-8") as f:
                    cookies_raw = await f.read()
                cookies = json.loads(cookies_raw)
                self._credential = Credential.from_cookies(cookies)
                return
            except Exception as e:
                logger.warning(f"读取本地 cookies 失败，将尝试使用配置 ck: {e!r}")

        if not pconfig.bili_ck:
            return

        credential = Credential.from_cookies(ck2dict(pconfig.bili_ck))
        if await credential.check_valid():
            logger.info(f"`parser_bili_ck` 有效, 保存到 {self._cookies_file}")
            self._credential = credential
            await self._save_credential()
        else:
            logger.warning("`parser_bili_ck` 已过期, 请更新 ck")

    async def _fetch_comments(self, oid: int, type: int) -> list[Comment]:
        """从 Bilibili API 获取评论数据，优先热评，失败时兜底普通评论"""

        try:
            response = await self.httpx.get(
                "https://api.bilibili.com/x/v2/reply",
                headers=self.ck_header,
                params={
                    "oid": oid,
                    "type": type,
                    "sort": 1,  # 按点赞数排序
                    "ps": 7,
                    "pn": 1,
                    "nohot": 1,
                },
            )
            response.raise_for_status()
            data = response.json()

            if data.get("code") != 0 or not data.get("data"):
                logger.warning(
                    f"bili评论返回数据为空或错误: code={data.get('code')}, message={data.get('message')}"  # noqa: E501
                )
                return []

            data_root = data["data"] or {}
            upper_top = data_root.get("upper", {}).get("top")
            replies_raw: list[dict[str, Any]] = data_root.get("replies") or []

            upper_list: list[dict[str, Any]] = [upper_top] if upper_top else []

            def _append_unique(
                src: list[dict[str, Any]], out: list[dict[str, Any]], seen: set[int]
            ) -> None:
                for item in src:
                    try:
                        rpid: int = item["rpid"]
                    except Exception:
                        # 没有 rpid 的异常项直接跳过
                        continue
                    if rpid in seen:
                        continue
                    seen.add(rpid)
                    out.append(item)

            merged: list[dict[str, Any]] = []
            seen_rpids: set[int] = set()

            has_upper = bool(upper_list)

            if has_upper:
                # 置顶 + 普通
                _append_unique(upper_list, merged, seen_rpids)
                _append_unique(replies_raw, merged, seen_rpids)
            else:
                # 没有置顶 → 普通
                _append_unique(replies_raw, merged, seen_rpids)

            logger.debug(
                f"bili获得评论: upper={len(upper_list)}, replies={len(replies_raw)}, merged={len(merged)}",  # noqa: E501
            )
            return self._process_reply_list(merged)

        except Exception as e:
            logger.error(f"[Bilibili] 获取评论失败: {e!r}")
            return []

    def _format_content_with_emote(
        self, raw: str, emote: dict[str, Any]
    ) -> list[ContentItem]:
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
        for e in emote.values():
            if e.get("type") == 4:
                continue

            text = e.get("text") or ""
            if not text:
                continue

            size = "small" if e.get("meta", {}).get("size") == 1 else "medium"
            sticker = self.create_sticker(e["url"], size)
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

    def _process_reply_list(self, replies: list[dict[str, Any]]) -> list[Comment]:
        """将 B 站评论列表转换为 Comment 列表"""

        def _build_single_comment(
            raw: dict[str, Any], parent_author: Author | None = None
        ) -> Comment:
            reply_control = raw.get("reply_control", {})
            content = raw.get("content", {})
            message = content.get("message", "")
            emote = content.get("emote", {})
            processed_content = self._format_content_with_emote(message, emote)

            if pictures := content.get("pictures"):
                for pic in pictures:
                    if url := pic.get("img_src"):
                        processed_content.append(self.create_image(url))

            member = raw.get("member", {})
            return self.create_comment(
                author=self.create_author(
                    name=member.get("uname", ""),
                    avatar_url=member.get("avatar"),
                    location=reply_control.get("location"),
                ),
                content=processed_content,
                timestamp=raw.get("ctime", 0),
                stats=self.create_stats(like_count=raw.get("like", 0)),
                parent_author=parent_author,
            )

        processed_comments: list[Comment] = []

        for comment in replies[:10]:
            comment_obj = _build_single_comment(comment)
            # 子回复
            child_posts: list[Comment] = []
            replies_list = comment.get("replies") or []
            for reply in replies_list[:5]:
                child_posts.append(_build_single_comment(reply, comment_obj.author))

            comment_obj.stats.comment_count = comment.get("count", 0)
            comment_obj.replies = child_posts

            processed_comments.append(comment_obj)

        return processed_comments

    @property
    async def credential(self) -> Credential | None:
        """哔哩哔哩登录凭证"""

        if self._credential is None:
            await self._init_credential()
            return self._credential

        if not await self._credential.check_valid():
            logger.warning("哔哩哔哩凭证已过期, 请重新配置")
            return None

        if await self._credential.check_refresh():
            logger.info("哔哩哔哩凭证需要刷新")
            if self._credential.has_ac_time_value() and self._credential.has_bili_jct():
                if not (
                    self._credential.has_buvid3() and self._credential.has_buvid4()
                ):
                    self._credential.buvid3, self._credential.buvid4 = await get_buvid()
                try:
                    await self._credential.refresh()
                except CookiesRefreshException as e:
                    logger.warning(f"刷新哔哩哔哩凭证失败: {e.msg}")
                    if "correspondPath" in e.msg:
                        raise TipException(
                            "刷新哔哩哔哩凭证失败, 可能是设备时间不正确"
                        ) from e
                    raise TipException(f"刷新哔哩哔哩凭证失败: {e.msg}") from e
                logger.info(f"哔哩哔哩凭证刷新成功, 保存到 {self._cookies_file}")
                await self._save_credential()
            else:
                logger.warning(
                    "哔哩哔哩凭证刷新需要包含 `SESSDATA`, `ac_time_value` 项"
                )

        return self._credential
