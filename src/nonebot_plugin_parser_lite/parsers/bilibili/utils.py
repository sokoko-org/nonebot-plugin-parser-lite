from dataclasses import dataclass
from enum import Enum
from functools import cmp_to_key
import re

RE_PCDN_HOST = re.compile(
    r"\.mcdn\.bilivideo\.cn|szbdyd\.com|cos\.bilibili\.com/.+pcdn", re.IGNORECASE
)
RE_PCDN_PATH = re.compile(r"xy\d+x\d+x\d+x\d+xy|/pcdn/|/mcdn/", re.IGNORECASE)
RE_PRIVATE_IP = re.compile(
    r"^https?://(10\.|172\.(1[6-9]|2\d|3[01])\.|192\.168\.|127\.)", re.IGNORECASE
)


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


class VideoQuality(Enum):
    """
    视频的视频流分辨率枚举

    :cvar _360P: 流畅 360P
    :cvar _480P: 清晰 480P
    :cvar _720P: 高清 720P60
    :cvar _1080P: 高清 1080P
    :cvar AI_REPAIR: 智能修复（人工智能修复画质）
    :cvar _1080P_PLUS: 高清 1080P 高码率
    :cvar _1080P_60: 高清 1080P 60 帧码率
    :cvar _4K: 超清 4K
    :cvar HDR: 真彩 HDR
    :cvar DOLBY: 杜比视界
    :cvar _8K: 超高清 8K
    """

    _360P = 16
    _480P = 32
    _720P = 64
    _1080P = 80
    AI_REPAIR = 100
    _1080P_PLUS = 112
    _1080P_60 = 116
    _4K = 120
    HDR = 125
    DOLBY = 126
    _8K = 127


class VideoCodecs(Enum):
    """
    视频的视频流编码枚举

    :cvar HEV: HEVC(H.265)
    :cvar AVC: AVC(H.264)
    :cvar AV1: AV1
    """

    HEV = "hev"
    AVC = "avc"
    AV1 = "av01"


class AudioQuality(Enum):
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
    video_quality: VideoQuality
    video_codecs: VideoCodecs
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
    audio_quality: AudioQuality
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
) -> tuple[
    VideoStreamDownloadURL | FLVStreamDownloadURL | MP4StreamDownloadURL | None,
    AudioStreamDownloadURL | None,
]:
    """
    基于 PCDN 规则清洗视频/音频流 URL，尽量避免使用 PCDN 节点。

    逻辑：

    1. 若 base_url 为 PCDN，则优先使用 backup_url 中第一个非 PCDN 链接；
    2. 若 backup_url 里也没有非 PCDN，则保留原 base_url (真倒霉)

    :param video: 视频流 URL 信息
    :param audio: 音频流 URL 信息
    :return: (清洗后的 video, audio)
    """

    def _sanitize_video(
        v: VideoStreamDownloadURL | FLVStreamDownloadURL | MP4StreamDownloadURL | None,
    ):
        if v is None:
            return None

        base_url = v.url
        backups = v.backup_url

        # 如果主 URL 不是 PCDN，则优先使用它
        if not is_pcdn_url(base_url):
            return v

        # 主 URL 是 PCDN，尝试从 backup_url 里找干净的替换
        clean_backups = [u for u in backups if not is_pcdn_url(u)]
        if clean_backups:
            new_base = clean_backups[0]
            rest_backups = clean_backups[1:]
            if isinstance(v, VideoStreamDownloadURL):
                return VideoStreamDownloadURL(
                    url=new_base,
                    video_quality=v.video_quality,
                    video_codecs=v.video_codecs,
                    backup_url=rest_backups,
                )
            if isinstance(v, FLVStreamDownloadURL):
                return FLVStreamDownloadURL(url=new_base, backup_url=rest_backups)
            return MP4StreamDownloadURL(url=new_base, backup_url=rest_backups)

        return v

    def _sanitize_audio(a: AudioStreamDownloadURL | None):
        if a is None:
            return None

        base_url = a.url
        backups = a.backup_url

        if not is_pcdn_url(base_url):
            return a

        clean_backups = [u for u in backups if not is_pcdn_url(u)]
        if clean_backups:
            new_base = clean_backups[0]
            rest_backups = clean_backups[1:]
            return AudioStreamDownloadURL(
                url=new_base,
                audio_quality=a.audio_quality,
                backup_url=rest_backups,
            )

        return a

    return _sanitize_video(video), _sanitize_audio(audio)


class VideoDownloadURLDataDetecter:
    """
    用于解析 `Video.get_download_url` 返回结果的解析器

    该解析器会自动清洗 PCDN 链接
    """

    def __init__(self, data: dict):
        """
        用于解析 `Video.get_download_url` 返回结果的解析器

        该解析器会自动清洗 PCDN 链接

        :param data: `Video.get_download_url` 返回的原始数据
        """
        self.__data = data
        if video_info := self.__data.get("video_info"):  # bangumi
            self.__data = video_info

    def detect_best_streams(
        self,
        video_max_quality: VideoQuality = VideoQuality._8K,
        audio_max_quality: AudioQuality = AudioQuality._192K,
        video_min_quality: VideoQuality = VideoQuality._360P,
        audio_min_quality: AudioQuality = AudioQuality._64K,
        video_accepted_qualities: list[VideoQuality] = [
            item
            for _, item in VideoQuality.__dict__.items()
            if isinstance(item, VideoQuality)
        ],
        audio_accepted_qualities: list[AudioQuality] = [
            item
            for _, item in AudioQuality.__dict__.items()
            if isinstance(item, AudioQuality)
        ],
        codecs: list[VideoCodecs] = [VideoCodecs.AV1, VideoCodecs.AVC, VideoCodecs.HEV],
        no_dolby_video: bool = False,
        no_dolby_audio: bool = False,
        no_hdr: bool = False,
        no_hires: bool = False,
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
        :param video_accepted_qualities: 允许的视频清晰度列表
        :param audio_accepted_qualities: 允许的音频清晰度列表
        :param codecs: 允许的视频编码优先级列表（越靠前优先级越高）
        :param no_dolby_video: 是否禁用杜比视频流
        :param no_dolby_audio: 是否禁用杜比音频流
        :param no_hdr: 是否禁用 HDR 视频流
        :param no_hires: 是否禁用 Hi-Res 音频流
        :return: (最佳视频流, 最佳音频流)，若不存在则对应位置为 `None`
        """
        # FLV / MP4 情况
        if "durl" in self.__data.keys():
            url = self.__data["durl"][0]["url"]
            backup_url = self.__data["durl"][0]["backup_url"]
            if self.__data["format"].startswith("flv"):
                return FLVStreamDownloadURL(url=url, backup_url=backup_url), None
            return MP4StreamDownloadURL(url=url, backup_url=backup_url), None

        # DASH 正常情况
        videos_data = self.__data["dash"]["video"]
        audios_data = self.__data["dash"].get("audio")
        flac_data = self.__data["dash"].get("flac")
        dolby_data = self.__data["dash"].get("dolby")

        # 收集所有候选视频流
        video_streams: list[VideoStreamDownloadURL] = []
        for video_data in videos_data:
            vq = VideoQuality(video_data["id"])

            # HDR / 杜比过滤
            if (vq == VideoQuality.HDR and no_hdr) or (
                vq == VideoQuality.DOLBY and no_dolby_video
            ):
                continue

            # 非 HDR / 杜比的视频质量范围过滤
            if vq not in (VideoQuality.DOLBY, VideoQuality.HDR):
                if not (video_min_quality.value <= vq.value <= video_max_quality.value):
                    continue
                if vq not in video_accepted_qualities:
                    continue

            # 编码过滤
            codecs_str: str = video_data["codecs"]
            video_stream_codecs: VideoCodecs | None = None
            for val in VideoCodecs:
                if val.value in codecs_str:
                    video_stream_codecs = val
                    break
            if video_stream_codecs is None or video_stream_codecs not in codecs:
                continue

            video_streams.append(
                VideoStreamDownloadURL(
                    url=video_data["base_url"],
                    video_quality=vq,
                    video_codecs=video_stream_codecs,
                    backup_url=video_data["backup_url"],
                )
            )

        # 收集所有候选音频流
        audio_streams: list[AudioStreamDownloadURL] = []
        if audios_data:
            for audio_data in audios_data:
                aq = AudioQuality(audio_data["id"])
                if not (audio_min_quality.value <= aq.value <= audio_max_quality.value):
                    continue
                if aq not in audio_accepted_qualities:
                    continue
                audio_streams.append(
                    AudioStreamDownloadURL(
                        url=audio_data["base_url"],
                        audio_quality=aq,
                        backup_url=audio_data["backup_url"],
                    )
                )

        if flac_data and (not no_hires) and flac_data["audio"]:
            audio = flac_data["audio"]
            aq = AudioQuality(audio["id"])
            audio_streams.append(
                AudioStreamDownloadURL(
                    url=audio["base_url"],
                    audio_quality=aq,
                    backup_url=audio["backup_url"],
                )
            )

        if dolby_data and (not no_dolby_audio) and dolby_data["audio"]:
            audio = dolby_data["audio"][0]
            aq = AudioQuality(audio["id"])
            audio_streams.append(
                AudioStreamDownloadURL(
                    url=audio["base_url"],
                    audio_quality=aq,
                    backup_url=audio["backup_url"],
                )
            )

        # 选择最优视频流
        def video_stream_cmp(
            s1: VideoStreamDownloadURL, s2: VideoStreamDownloadURL
        ) -> int:
            # 杜比/HDR 优先
            if s1.video_quality == VideoQuality.DOLBY and not no_dolby_video:
                return 1
            if s2.video_quality == VideoQuality.DOLBY and not no_dolby_video:
                return -1
            if s1.video_quality == VideoQuality.HDR and not no_hdr:
                return 1
            if s2.video_quality == VideoQuality.HDR and not no_hdr:
                return -1

            # 其余按清晰度数值排序
            if s1.video_quality.value != s2.video_quality.value:
                return s1.video_quality.value - s2.video_quality.value

            # 同清晰度下，按 codecs 顺序（codecs 列表越靠前越优先）
            if s1.video_codecs != s2.video_codecs:
                return codecs.index(s2.video_codecs) - codecs.index(s1.video_codecs)

            return 0

        # 选择最优音频流
        def audio_stream_cmp(
            s1: AudioStreamDownloadURL, s2: AudioStreamDownloadURL
        ) -> int:
            # 杜比/Hi-Res 优先
            if s1.audio_quality == AudioQuality.DOLBY and not no_dolby_audio:
                return 1
            if s2.audio_quality == AudioQuality.DOLBY and not no_dolby_audio:
                return -1
            if s1.audio_quality == AudioQuality.HI_RES and not no_hires:
                return 1
            if s2.audio_quality == AudioQuality.HI_RES and not no_hires:
                return -1

            return s1.audio_quality.value - s2.audio_quality.value

        # 排序 + 取最优
        best_video: (
            VideoStreamDownloadURL | FLVStreamDownloadURL | MP4StreamDownloadURL | None
        ) = None
        best_audio: AudioStreamDownloadURL | None = None

        best_video = (
            max(video_streams, key=cmp_to_key(video_stream_cmp))
            if video_streams
            else None
        )
        best_audio = (
            max(audio_streams, key=cmp_to_key(audio_stream_cmp))
            if audio_streams
            else None
        )

        # 清洗 PCDN URL，尽量替换为正规 CDN
        best_video, best_audio = sanitize_stream_urls(best_video, best_audio)
        return best_video, best_audio
