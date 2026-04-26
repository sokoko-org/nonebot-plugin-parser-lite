from msgspec import Struct, field
from msgspec.json import Decoder


class Word(Struct):
    startMs: int
    endMs: int
    text: str


class Sentence(Word):
    words: list[Word]


class Lyrics(Struct):
    sentences: list[Sentence] = field(default_factory=list)


class Stats(Struct):
    count_collected: int = 0
    """收藏数"""
    count_comment: int = 0
    """评论数"""
    count_shared: int = 0
    """分享数"""

class AlbumInfo(Struct):
    name: str
    id: str

class TrackInfo(Struct):
    stats: Stats
    """统计信息"""
    album: AlbumInfo
    """专辑信息"""


class Urls(Struct):
    urls: list[str]


class User(Struct):
    id: str
    nickname: str
    medium_avatar_url: Urls

    @property
    def avatar_url(self) -> str:
        return self.medium_avatar_url.urls[0]


class Comment(Struct):
    content: str
    count_digged: int
    """点赞数"""
    time_created: int
    """发布时间戳"""
    count_reply: int
    """回复数"""
    ip_label: str
    """归属地"""


class CommentsStruct(Struct):
    comments: list[Comment] = field(default_factory=list)


class AudioWithLyricsOption(Struct):
    url: str
    """音乐资源url"""
    duration: float
    """时长(s)"""
    artistName: str
    """歌手名称"""
    trackName: str
    """歌曲名称"""
    trackInfo: TrackInfo
    """歌曲信息"""
    coverURL: str
    """封面url"""
    create_time: str
    """发布时间戳"""
    commentsStruct: CommentsStruct = field(default_factory=CommentsStruct)
    _lyrics: Lyrics = field(name="lyrics", default_factory=Lyrics)

    @property
    def comments(self) -> list[Comment]:
        """评论列表"""
        return self.commentsStruct.comments

    @property
    def lyrics(self) -> str:
        """将KRC歌词转换为 LRC 格式（句时间 + 整句文本）"""
        lrc_lines: list[str] = []

        for sentence in self._lyrics.sentences:
            start_ms = sentence.startMs
            sentence_text = (sentence.text or "").strip()

            # 如果整句为空，再退回到按 words 拼接
            if not sentence_text and sentence.words:
                sentence_text = "".join(word.text for word in sentence.words).strip()

            if not sentence_text:
                continue

            # 毫秒转 LRC 时间标签 [mm:ss.xx]
            minutes = start_ms // 60000
            seconds = (start_ms % 60000) // 1000
            centiseconds = (start_ms % 1000) // 10  # 00–99

            time_tag = f"[{minutes:02d}:{seconds:02d}.{centiseconds:02d}]"
            lrc_lines.append(time_tag + sentence_text)

        return "\n".join(lrc_lines)


class TrackPage(Struct):
    audioWithLyricsOption: AudioWithLyricsOption


class LoaderData(Struct):
    track_page: TrackPage


class RouterData(Struct):
    loaderData: LoaderData


decoder = Decoder(RouterData)
