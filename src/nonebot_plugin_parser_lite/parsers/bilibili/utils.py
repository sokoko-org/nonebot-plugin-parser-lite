from dataclasses import dataclass
import re

from ...constants import BiliAudioQuality, BiliVideoCodecs, BiliVideoQuality

RE_PCDN_HOST = re.compile(
    r"\.mcdn\.bilivideo\.cn|szbdyd\.com|cos\.bilibili\.com/.+pcdn", re.IGNORECASE
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
        self.__data = data.get("video_info") or data

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
        # FLV / MP4 情况
        if "durl" in self.__data.keys():
            url = self.__data["durl"][0]["url"]
            backup_url = self.__data["durl"][0]["backup_url"]

            if self.__data["format"].startswith("flv"):
                video_stream = FLVStreamDownloadURL(
                    url=url,
                    backup_url=backup_url,
                )
            else:
                video_stream = MP4StreamDownloadURL(
                    url=url,
                    backup_url=backup_url,
                )

            video_stream, _ = sanitize_stream_urls(video_stream, None)
            return video_stream, None

        # DASH 正常情况
        videos_data = self.__data["dash"]["video"]
        audios_data = self.__data["dash"].get("audio")
        flac_data = self.__data["dash"].get("flac")
        dolby_data = self.__data["dash"].get("dolby")

        # 收集所有候选视频流
        video_streams: list[VideoStreamDownloadURL] = []
        for video_data in videos_data:
            vq = BiliVideoQuality(video_data["id"])

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
            codecs_str: str = video_data["codecs"]
            video_stream_codecs = BiliVideoCodecs.from_codec(codecs_str)
            if video_stream_codecs not in codecs:
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
                aq = BiliAudioQuality(audio_data["id"])
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
            aq = BiliAudioQuality(audio["id"])
            audio_streams.append(
                AudioStreamDownloadURL(
                    url=audio["base_url"],
                    audio_quality=aq,
                    backup_url=audio["backup_url"],
                )
            )

        if dolby_data and (not no_dolby_audio) and dolby_data["audio"]:
            audio = dolby_data["audio"][0]
            aq = BiliAudioQuality(audio["id"])
            audio_streams.append(
                AudioStreamDownloadURL(
                    url=audio["base_url"],
                    audio_quality=aq,
                    backup_url=audio["backup_url"],
                )
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

        # 清洗 PCDN URL，尽量替换为正规 CDN
        best_video, best_audio = sanitize_stream_urls(best_video, best_audio)
        return best_video, best_audio
