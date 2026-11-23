from msgspec import Struct, field
from msgspec.json import Decoder

from ...creator import ContentItem, Creator
from ...data import Author, Stats
from ...download import DOWNLOADER
from ...utils.format import format_num
from .util import InlineElement, merge_text, render_inline


def to_int(value: str | int | None) -> int | None:
    """森空岛大量数字字段是字符串，统一转成 int"""
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


class Image(Struct):
    """图片资源"""

    id: str = ""
    url: str = ""
    description: str = ""


class VideoInfo(Struct):
    """视频码流，按清晰度从高到低排列"""

    url: str = ""
    duration: str | int = 0
    resolution: str = ""
    width: str | int = 0
    height: str | int = 0


class Video(Struct):
    """视频资源"""

    id: str = ""
    cover: Image | None = None
    description: str = ""
    infos: list[VideoInfo] = field(default_factory=list)

    @property
    def content(self) -> list[ContentItem]:
        """构造视频内容，优先使用最高清晰度"""
        if not self.infos:
            return []
        info = self.infos[0]
        if not info.url:
            return []

        cache_key = f"skyland:{self.id}"
        task = DOWNLOADER.download_m3u8_video(url=info.url, cache_key=cache_key)
        duration = to_int(info.duration) or 0
        return [
            Creator.video(
                url_or_task=task,
                cover_url=self.cover.url if self.cover else None,
                duration=duration / 1000,
                cache_key=cache_key,
            )
        ]


class TextBlock(Struct):
    """文本区块载荷"""

    inlineElements: list[InlineElement] = field(default_factory=list)
    kind: str = ""


class Block(Struct):
    """文档区块"""

    id: str = ""
    kind: str = ""
    text: TextBlock | None = None
    image: Image | None = None
    video: Video | None = None

    @property
    def content(self) -> list[ContentItem]:
        """渲染单个区块"""
        match self.kind:
            case "text":
                if content := render_inline(
                    self.text.inlineElements if self.text else None
                ):
                    return [*content, "\n"]
            case "image":
                if self.image and self.image.url:
                    return [
                        Creator.graphic(
                            url=self.image.url,
                            alt=self.image.description or None,
                            cache_key=f"skyland:{self.image.id}",
                        )
                    ]
            case "video":
                if self.video:
                    return self.video.content
            case _:
                pass
        return []


class Document(Struct):
    """文章富文本文档"""

    id: str = ""
    blockIds: list[str] = field(default_factory=list)
    blockMap: dict[str, Block] = field(default_factory=dict)

    @property
    def content(self) -> list[ContentItem]:
        """按 `blockIds` 的顺序渲染区块"""
        content: list[ContentItem] = []
        for block_id in self.blockIds:
            if block := self.blockMap.get(block_id):
                content.extend(block.content)
        return content


class Item(Struct):
    """文章主体"""

    id: str = ""
    userId: str = ""
    title: str = ""
    viewKind: int = 0
    cover: Image | None = None
    imageList: list[Image] = field(default_factory=list)
    videoList: list[Video] = field(default_factory=list)
    document: Document | None = None
    caption: list[InlineElement] = field(default_factory=list)
    createdAtTs: str | int = 0
    publishedAtTs: str | int = 0
    firstIpLocation: str = ""

    @property
    def timestamp(self) -> int | None:
        """发布时间，单位秒"""
        return to_int(self.publishedAtTs) or to_int(self.createdAtTs)

    @property
    def text_content(self) -> list[ContentItem]:
        """正文文字（含贴纸），`document` 优先，其次 `caption`"""
        if self.document and (content := self.document.content):
            return content
        return render_inline(self.caption)

    @property
    def content(self) -> list[ContentItem]:
        """完整内容：正文 + 媒体"""
        content = self.text_content
        document_ids = self._document_media_ids()

        for video in self.videoList:
            if video.id in document_ids:
                continue
            content.extend(video.content)

        for image in self.imageList:
            if not image.url or image.id in document_ids:
                continue
            content.append(
                Creator.image(
                    url=image.url,
                    cache_key=f"skyland:{image.id}",
                )
            )

        return merge_text(content)

    def _document_media_ids(self) -> set[str]:
        """收集已在正文中渲染过的媒体 id，避免重复附加"""
        if not self.document:
            return set()
        ids: set[str] = set()
        for block in self.document.blockMap.values():
            if block.image and block.image.id:
                ids.add(block.image.id)
            if block.video and block.video.id:
                ids.add(block.video.id)
        return ids


class User(Struct):
    """作者信息"""

    id: str = ""
    nickname: str = ""
    profile: str = ""
    avatar: str = ""
    latestIpLocation: str = ""


class ItemRts(Struct):
    """互动计数，均为字符串"""

    liked: str = "0"
    collected: str = "0"
    reposted: str = "0"
    commented: str = "0"


class Tag(Struct):
    """话题标签"""

    name: str = ""


class Data(Struct):
    """文章详情数据"""

    item: Item
    user: User | None = None
    tags: list[Tag] = field(default_factory=list)
    itemRts: ItemRts | None = None

    @property
    def url(self) -> str:
        """文章网页地址"""
        return f"https://www.skland.com/article?id={self.item.id}"

    @property
    def author(self) -> Author:
        """作者"""
        user = self.user
        if user is None:
            return Creator.author(name="森空岛用户")
        return Creator.author(
            name=user.nickname or "森空岛用户",
            avatar_url=user.avatar or None,
            description=user.profile or None,
            id=user.id or None,
            location=user.latestIpLocation or self.item.firstIpLocation or None,
            avatar_cache_key=f"skyland:{user.id}" if user.id else None,
        )

    @property
    def stats(self) -> Stats:
        """互动数据"""
        rts = self.itemRts
        if rts is None:
            return Creator.stats()
        return Creator.stats(
            like_count=format_num(to_int(rts.liked)),
            collect_count=format_num(to_int(rts.collected)),
            share_count=format_num(to_int(rts.reposted)),
            comment_count=format_num(to_int(rts.commented)),
        )

    @property
    def title(self) -> str | None:
        """标题，附带话题标签"""
        title = self.item.title.strip()
        if tags := [f"#{tag.name}" for tag in self.tags if tag.name]:
            tag_text = " ".join(tags)
            return f"{title} {tag_text}" if title else tag_text
        return title or None

    @property
    def content(self) -> list[ContentItem]:
        """正文内容"""
        return self.item.content


class Response(Struct):
    """接口响应"""

    code: int = 0
    message: str = ""
    data: Data | None = None


decoder = Decoder(Response)
