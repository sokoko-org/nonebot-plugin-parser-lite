from dataclasses import dataclass
from enum import Enum, IntEnum
import re
from typing import Any
from urllib.parse import urlsplit

from .a2v import av2bv, bv2av
from .bilibili.app.playurl.v1 import playurl_pb2
from .bilibili.app.view.v1 import view_pb2
from .cdn import choose_cdn_domain, normalize_cdn_domain
from .client import GRPC_CLIENT, HTTP_CLIENT
from .credential import Credential
from .exceptions import BiliHelperException
from .sign import encWbi, getWbiKeys


class BiliVideoQuality(IntEnum):
    """
    视频的视频流分辨率枚举

    :cvar _144P: 流畅 144P
    :cvar _240P: 流畅 240P
    :cvar _360P: 流畅 360P
    :cvar _480P: 清晰 480P
    :cvar _720P: 高清 720P
    :cvar _720P_PLUS: 高清 720P 高码率
    :cvar _1080P: 高清 1080P
    :cvar AI_REPAIR: 智能修复（人工智能修复画质）
    :cvar _1080P_PLUS: 高清 1080P 高码率
    :cvar _1080P_60: 高清 1080P 60 帧码率
    :cvar _4K: 超清 4K
    :cvar HDR: 真彩 HDR
    :cvar DOLBY: 杜比视界
    :cvar _8K: 超高清 8K
    """

    _144P = 5
    _240P = 6
    _360P = 16
    _480P = 32
    _720P = 64
    _720P_PLUS = 74
    _1080P = 80
    AI_REPAIR = 100
    _1080P_PLUS = 112
    _1080P_60 = 116
    _4K = 120
    HDR = 125
    DOLBY = 126
    _8K = 127


class BiliVideoCodecs(str, Enum):
    """
    视频的视频流编码枚举

    :cvar HEV: HEVC(H.265)
    :cvar AVC: AVC(H.264)
    :cvar AV1: AV1
    :cvar UNKNOWN: 未知
    """

    HEV = "hev"
    AVC = "avc"
    AV1 = "av01"
    UNKNOWN = "unknown"

    @classmethod
    def from_codecid(cls, codecid: int) -> "BiliVideoCodecs":
        """根据返回的 codec_id 推断枚举值"""
        return {
            7: cls.AVC,
            12: cls.HEV,
            13: cls.AV1,
        }.get(codecid, cls.UNKNOWN)


class BiliAudioQuality(IntEnum):
    """
    视频的音频流清晰度枚举

    :cvar _64K: 64K
    :cvar _132K: 132K
    :cvar _192K: 192K
    :cvar HI_RES: Hi-Res 无损
    :cvar DOLBY: 杜比全景声
    """

    _64K = 30216
    _132K = 30232
    DOLBY = 30250
    HI_RES = 30251
    _192K = 30280


class Video:
    """
    视频类，各种对视频的操作均在里面
    """

    bvid: str
    aid: int

    def __init__(
        self,
        bvid: str | None = None,
        aid: int | None = None,
        credential: Credential | None = None,
    ):
        """
        :param bvid: BV 号. bvid 和 aid 必须提供其中之一, defaults to None
        :param aid: AV 号. bvid 和 aid 必须提供其中之一, defaults to None
        :param credential: Credential 类, defaults to None
        """
        if bvid:
            self.bvid = bvid
            self.aid = bv2av(bvid)
        elif aid:
            self.aid = aid
            self.bvid = av2bv(aid)
        else:
            raise BiliHelperException("请至少提供 bvid 和 aid 中的其中一个参数")
        self.credential = credential
        self.info: view_pb2.ViewReply | None = None

    async def get_info(self) -> view_pb2.ViewReply:
        """
        获取视频信息

        :return: 调用 API 返回的结果
        """
        if not self.info:
            from .bilibili.app.view.v1 import view_pb2
            from .client import GRPC_CLIENT

            req = view_pb2.ViewReq(bvid=self.bvid)
            access_token = self.credential.access_token if self.credential else ""
            self.info = await GRPC_CLIENT.request(
                "/bilibili.app.view.v1.View/View",
                req,
                view_pb2.ViewReply,
                access_token=access_token,
                user_mid=self.credential.mid
                if self.credential and access_token
                else None,
            )
        return self.info

    async def get_up_mid(self) -> int:
        """
        获取视频 up 主的 mid

        :return: up_mid
        """
        info = await self.get_info()
        return info.arc.author.mid

    async def is_episode(self) -> bool:
        """
        判断视频是否是番剧

        :return: 是否是番剧
        """
        info = await self.get_info()
        return info.HasField("season")

    async def get_cid(self, page_index: int) -> int:
        """
        根据分 p 号获取稿件 cid

        :param page_index: 分 p 号
        :raises BiliHelperError: 参数不正确
        :raises BiliHelperError: 分 p 不存在
        :return: _description_
        """
        if page_index < 0:
            raise BiliHelperException("分 p 号必须大于或等于 0")

        info = await self.get_info()
        pages = info.pages

        if len(pages) <= page_index:
            raise BiliHelperException("不存在该分 p")

        page = pages[page_index].page
        return page.cid

    async def get_download_url(
        self,
        page_index: int | None = None,
        cid: int | None = None,
        prefer_codecs: list[BiliVideoCodecs] | None = None,
    ) -> playurl_pb2.PlayViewReply:
        """
        获取视频下载信息

        返回结果可以传入 `VideoDownloadURLDataDetecter` 进行解析

        page_index 和 cid 至少提供其中一个，其中 cid 优先级最高

        :param page_index: 分 P 号，从 0 开始, defaults to None
        :param cid: 分 P 的 ID, defaults to None
        :raises BiliHelperException: 传参有误
        :return: 调用 API 返回的结果
        """
        if cid is None:
            if page_index is None:
                raise BiliHelperException("page_index 和 cid 至少提供一个")

            cid = await self.get_cid(page_index)

        match prefer_codecs[0] if prefer_codecs else None:
            case "hev":
                prefer_codec_type = playurl_pb2.CODE265
            case "avc":
                prefer_codec_type = playurl_pb2.CODE264
            case "av01":
                prefer_codec_type = playurl_pb2.CODEAV1
            case _:
                prefer_codec_type = playurl_pb2.NOCODE
        req = playurl_pb2.PlayViewReq(
            aid=self.aid,
            cid=cid,
            qn=127,
            fnval=4048,
            fourk=True,
            spmid="main.ugc-video-detail.0.0",
            from_spmid="main.my-history.0.0",
            prefer_codec_type=prefer_codec_type,
            download=0,
            force_host=2,
        )
        access_token = self.credential.access_token if self.credential else ""
        return await GRPC_CLIENT.request(
            "/bilibili.app.playurl.v1.PlayURL/PlayView",
            req,
            playurl_pb2.PlayViewReply,
            access_token=access_token,
            user_mid=self.credential.mid if self.credential and access_token else None,
        )

    async def get_ai_conclusion(
        self,
        cid: int | None = None,
        page_index: int | None = None,
        up_mid: int | None = None,
    ) -> dict[str, Any]:
        """
        获取稿件 AI 总结结果

        cid 和 page_index 至少提供其中一个，其中 cid 优先级最高

        :param cid: 分 P 的 cid, defaults to None
        :param page_index: 分 P 号，从 0 开始, defaults to None
        :param up_mid: up 主的 mid, defaults to None
        :raises BiliHelperError: 参数不正确
        :return: 调用 API 返回的结果
        """
        if cid is None:
            if page_index is None:
                raise BiliHelperException("page_index 和 cid 至少提供一个")

            cid = await self.get_cid(page_index)

        params = {
            "aid": self.aid,
            "bvid": self.bvid,
            "cid": cid,
            "up_mid": up_mid or await self.get_up_mid(),
            "web_location": "333.788",
        }

        result = (
            await HTTP_CLIENT.get(
                url="https://api.bilibili.com/x/web-interface/view/conclusion/get",
                params=encWbi(params, *(await getWbiKeys())),
                cookies=self.credential.get_cookies() if self.credential else None,
            )
        ).json()
        if result["code"] != 0:
            raise BiliHelperException(result)
        return result["data"]


RE_PCDN_HOST = re.compile(
    r"\.mcdn\.bilivideo\.cn|szbdyd\.com|cos\.bilibili\.com/.+pcdn|\.edge\.mountaintoys\.cn",
    re.IGNORECASE,
)
RE_PCDN_PATH = re.compile(r"xy\d+x\d+x\d+x\d+xy|/pcdn/|/mcdn/", re.IGNORECASE)
RE_PRIVATE_IP = re.compile(
    r"^https?://(10\.|172\.(1[6-9]|2\d|3[01])\.|192\.168\.|127\.)", re.IGNORECASE
)
# 枚举默认集合：用于 detect_best_streams 的默认允许清晰度列表
DEFAULT_VIDEO_QUALITIES: list[BiliVideoQuality] = list(BiliVideoQuality)
DEFAULT_AUDIO_QUALITIES: list[BiliAudioQuality] = list(BiliAudioQuality)


def is_pcdn_url(url: str | None) -> bool:
    """
    检测给定 URL 是否为 PCDN / P2P 节点 URL

    :param url: 待检测的 URL 字符串
    :return: 若为 PCDN 地址则返回 True，否则 False
    """
    if not url:
        return False
    return bool(
        RE_PCDN_HOST.search(url) or RE_PCDN_PATH.search(url) or RE_PRIVATE_IP.match(url)
    )


@dataclass
class VideoStreamDownloadURL:
    """
    视频流 URL 信息

    :param url: 视频流 URL
    :param video_quality: 视频流清晰度
    :param video_codecs: 视频流编码
    :param backup_url: 备用视频流 URL 列表
    """

    url: str
    video_quality: BiliVideoQuality
    video_codecs: BiliVideoCodecs
    backup_url: list[str]


@dataclass
class AudioStreamDownloadURL:
    """
    音频流 URL 信息

    :param url: 音频流 URL
    :param audio_quality: 音频流清晰度
    :param backup_url: 备用音频流 URL 列表
    """

    url: str
    audio_quality: BiliAudioQuality
    backup_url: list[str]


@dataclass
class FLVStreamDownloadURL:
    """
    FLV 视频流

    :param url: FLV 流 URL
    :param backup_url: 备用视频流 URL 列表
    """

    url: str
    backup_url: list[str]


@dataclass
class MP4StreamDownloadURL:
    """
    MP4 视频流

    :param url: HTML5 MP4 视频流 URL
    :param backup_url: 备用视频流 URL 列表
    """

    url: str
    backup_url: list[str]


def sanitize_stream_urls(
    video: VideoStreamDownloadURL | FLVStreamDownloadURL | MP4StreamDownloadURL | None,
    audio: AudioStreamDownloadURL | None,
    *,
    cdn_region: str = "zh",
    cdn_domain: str | None = None,
) -> tuple[
    VideoStreamDownloadURL | FLVStreamDownloadURL | MP4StreamDownloadURL | None,
    AudioStreamDownloadURL | None,
]:
    """
    基于 PCDN 规则清洗视频/音频流 URL，尽量避免使用 PCDN 节点

    逻辑：

    1. 过滤 PCDN 链接，优先使用 B 站返回的非 PCDN 地址；
    2. 将地区或自定义 CDN 放在首位；
    3. 保留 B 站返回的非 PCDN 原始地址作为故障切换线路

    :param video: 视频流 URL 信息
    :param audio: 音频流 URL 信息
    :param cdn_region: CDN 地区；在线列表不可用时仍可使用 zh、en、ja
    :param cdn_domain: 自定义 CDN 域名，设置后优先于地区配置
    :return: (清洗后的 video, audio)
    """
    replacement_domain = (
        normalize_cdn_domain(cdn_domain) if cdn_domain and cdn_domain.strip() else None
    ) or choose_cdn_domain(cdn_region)

    def _replace_host(url: str) -> str:
        return urlsplit(url)._replace(netloc=replacement_domain).geturl()

    for stream in (video, audio):
        if stream is None:
            continue

        source_urls = [stream.url, *stream.backup_url]
        clean_urls = [url for url in source_urls if not is_pcdn_url(url)] or [
            stream.url
        ]
        download_urls = list(dict.fromkeys([_replace_host(clean_urls[0]), *clean_urls]))
        stream.url = download_urls[0]
        stream.backup_url = download_urls[1:]
    return video, audio


class VideoDownloadURLDataDetecter:
    """
    用于解析 `Video.get_download_url` 返回结果的解析器

    该解析器会自动清洗 PCDN 链接
    """

    def __init__(self, data: playurl_pb2.PlayViewReply):
        """
        用于解析 `Video.get_download_url` 返回结果的解析器

        该解析器会自动清洗 PCDN 链接

        :param data: `Video.get_download_url` 返回的 protobuf 响应
        """
        self.__data = data.video_info

    @staticmethod
    def _append_audio_stream(
        streams: list[AudioStreamDownloadURL],
        url: str,
        backup_url: list[str],
        quality_id: int,
        min_quality: BiliAudioQuality,
        max_quality: BiliAudioQuality,
        accepted_qualities: list[BiliAudioQuality],
    ) -> None:
        if not url:
            return
        try:
            quality = BiliAudioQuality(quality_id)
        except ValueError:
            return
        if not (min_quality.value <= quality.value <= max_quality.value):
            return
        if quality not in accepted_qualities:
            return
        streams.append(
            AudioStreamDownloadURL(
                url=url,
                audio_quality=quality,
                backup_url=backup_url,
            )
        )

    def detect_best_streams(
        self,
        video_max_quality: BiliVideoQuality = BiliVideoQuality._8K,
        audio_max_quality: BiliAudioQuality = BiliAudioQuality._192K,
        video_min_quality: BiliVideoQuality = BiliVideoQuality._360P,
        audio_min_quality: BiliAudioQuality = BiliAudioQuality._64K,
        video_accepted_qualities: list[BiliVideoQuality] | None = None,
        audio_accepted_qualities: list[BiliAudioQuality] | None = None,
        codecs: list[BiliVideoCodecs] | None = None,
        no_dolby_video: bool = False,
        no_dolby_audio: bool = False,
        no_hdr: bool = False,
        no_hires: bool = False,
        cdn_region: str = "zh",
        cdn_domain: str | None = None,
    ) -> tuple[
        VideoStreamDownloadURL | FLVStreamDownloadURL | MP4StreamDownloadURL | None,
        AudioStreamDownloadURL | None,
    ]:
        """
        解析数据并返回“最优视频流 + 最优音频流”

        - 对于 FLV/MP4/试看流：只返回一个 FLV/MP4 流作为视频，音频为 `None`
        - 对于 DASH 流：在所有可用流中选出一条“质量最高”的视频流和音频流

        :param video_max_quality: 可接受的视频最高清晰度
        :param audio_max_quality: 可接受的音频最高清晰度
        :param video_min_quality: 可接受的视频最低清晰度
        :param audio_min_quality: 可接受的音频最低清晰度
        :param video_accepted_qualities: 允许的视频清晰度列表，默认为所有值
        :param audio_accepted_qualities: 允许的音频清晰度列表，默认为所有值
        :param codecs: 允许的视频编码优先级列表（越靠前优先级越高），默认为 AV1 > AVC > HEV
        :param no_dolby_video: 是否禁用杜比视频流
        :param no_dolby_audio: 是否禁用杜比音频流
        :param no_hdr: 是否禁用 HDR 视频流
        :param no_hires: 是否禁用 Hi-Res 音频流
        :param cdn_region: CDN 地区
        :param cdn_domain: 自定义 CDN 域名，设置后优先于地区配置

        :return: (最佳视频流, 最佳音频流)，若不存在则对应位置为 `None`
        """  # noqa: E501
        if video_accepted_qualities is None:
            video_accepted_qualities = DEFAULT_VIDEO_QUALITIES
        if audio_accepted_qualities is None:
            audio_accepted_qualities = DEFAULT_AUDIO_QUALITIES
        if codecs is None:
            codecs = [
                BiliVideoCodecs.AV1,
                BiliVideoCodecs.AVC,
                BiliVideoCodecs.HEV,
            ]
        # 收集所有候选视频流
        video_streams: list[VideoStreamDownloadURL] = []
        for stream in self.__data.stream_list:
            content_kind = stream.WhichOneof("content")
            if content_kind == "dash_video":
                video_data = stream.dash_video
                url = video_data.base_url
                backup_url = list(video_data.backup_url)
                codecid = video_data.codecid
            elif content_kind == "segment_video" and stream.segment_video.segment:
                segment = stream.segment_video.segment[0]
                url = segment.url
                backup_url = list(segment.backup_url)
                if stream.stream_info.format.startswith("flv"):
                    return sanitize_stream_urls(
                        FLVStreamDownloadURL(url=url, backup_url=backup_url),
                        None,
                        cdn_region=cdn_region,
                        cdn_domain=cdn_domain,
                    )
                if stream.stream_info.format.startswith("mp4"):
                    return sanitize_stream_urls(
                        MP4StreamDownloadURL(url=url, backup_url=backup_url),
                        None,
                        cdn_region=cdn_region,
                        cdn_domain=cdn_domain,
                    )
                codecid = self.__data.video_codecid
            else:
                continue

            try:
                vq = BiliVideoQuality(stream.stream_info.quality)
            except ValueError:
                continue

            # HDR / 杜比过滤
            if (vq == BiliVideoQuality.HDR and no_hdr) or (
                vq == BiliVideoQuality.DOLBY and no_dolby_video
            ):
                continue

            # 非 HDR / 杜比的视频质量范围过滤
            if vq not in (BiliVideoQuality.DOLBY, BiliVideoQuality.HDR):
                if not (video_min_quality.value <= vq.value <= video_max_quality.value):
                    continue
                if vq not in video_accepted_qualities:
                    continue

            # 编码过滤
            video_stream_codecs = BiliVideoCodecs.from_codecid(codecid)
            if video_stream_codecs not in codecs:
                continue
            video_streams.append(
                VideoStreamDownloadURL(
                    url=url,
                    video_quality=vq,
                    video_codecs=video_stream_codecs,
                    backup_url=backup_url,
                )
            )

        # 收集所有候选音频流
        audio_streams: list[AudioStreamDownloadURL] = []
        for audio in self.__data.dash_audio:
            self._append_audio_stream(
                audio_streams,
                audio.baseUrl,
                list(audio.backup_url),
                audio.id,
                audio_min_quality,
                audio_max_quality,
                audio_accepted_qualities,
            )

        if not no_hires and self.__data.HasField("loss_less_item"):
            audio = self.__data.loss_less_item.audio
            self._append_audio_stream(
                audio_streams,
                audio.baseUrl,
                list(audio.backup_url),
                audio.id,
                audio_min_quality,
                audio_max_quality,
                audio_accepted_qualities,
            )

        if not no_dolby_audio and self.__data.HasField("dolby"):
            audio = self.__data.dolby.audio
            self._append_audio_stream(
                audio_streams,
                audio.baseUrl,
                list(audio.backup_url),
                audio.id,
                audio_min_quality,
                audio_max_quality,
                audio_accepted_qualities,
            )

        # 选择最优视频流：基于评分的 key 函数
        def video_score(s: VideoStreamDownloadURL) -> tuple[int, int, int]:
            """
            :return: (杜比/HDR 优先级, 清晰度权重, 编码优先级)
            """
            # 杜比/HDR 优先级（越大越优先）
            dolby_hdr_priority = 0
            if not no_dolby_video and s.video_quality == BiliVideoQuality.DOLBY:
                dolby_hdr_priority = 2
            elif not no_hdr and s.video_quality == BiliVideoQuality.HDR:
                dolby_hdr_priority = 1

            # 清晰度（越高越好）
            quality_weight = s.video_quality.value

            # 编码优先级（codecs 列表越靠前越优先）
            try:
                codec_priority = len(codecs) - codecs.index(s.video_codecs)
            except ValueError:
                codec_priority = 0

            return dolby_hdr_priority, quality_weight, codec_priority

        # 选择最优音频流：基于评分的 key 函数
        def audio_score(s: AudioStreamDownloadURL) -> tuple[int, int]:
            """
            :return: (杜比/Hi-Res 优先级, 清晰度权重)
            """
            dolby_hires_priority = 0
            if not no_dolby_audio and s.audio_quality == BiliAudioQuality.DOLBY:
                dolby_hires_priority = 2
            elif not no_hires and s.audio_quality == BiliAudioQuality.HI_RES:
                dolby_hires_priority = 1

            quality_weight = s.audio_quality.value
            return dolby_hires_priority, quality_weight

        # 取最优（线性扫描）
        best_video: (
            VideoStreamDownloadURL | FLVStreamDownloadURL | MP4StreamDownloadURL | None
        )
        best_audio: AudioStreamDownloadURL | None

        best_video = max(video_streams, key=video_score) if video_streams else None
        best_audio = max(audio_streams, key=audio_score) if audio_streams else None

        return sanitize_stream_urls(
            best_video,
            best_audio,
            cdn_region=cdn_region,
            cdn_domain=cdn_domain,
        )
