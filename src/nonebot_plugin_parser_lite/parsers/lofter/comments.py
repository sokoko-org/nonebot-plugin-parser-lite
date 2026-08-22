from __future__ import annotations

from bs4 import BeautifulSoup
from msgspec import Struct, field

from ...creator import Creator
from ...data import ContentItem


class BlogInfo(Struct):
    blogNickName: str
    """用户昵称"""
    bigAvaImg: str
    """用户头像"""
    blogName: str
    """用户名"""
    blogId: int
    """用户id"""


class Emote(Struct):
    name: str
    """表情名称"""
    url: str
    """表情图片链接"""
    sizeType: int
    """尺寸信息，暂时不知道"""


class Comment(Struct):
    publisherBlogInfo: BlogInfo
    raw: str = field(name="content")
    """原始评论内容（HTML，可能包含表情占位）"""
    likeCount: int
    """点赞数"""
    publishTime: int
    """发布时间(ms)"""
    ipLocation: str
    """IP归属地"""
    emotes: list[Emote] = field(default_factory=list)
    l2Comments: list[Comment] = field(default_factory=list)
    """子评论"""

    @property
    def content(self) -> list[ContentItem]:
        """
        将 Lofter 评论内容解析为 [文本/贴纸] 序列。

        规则：
        - raw 是 HTML，可能包含表情占位，如 [doge] 等；
        - emotes 列表提供了 name -> url 的映射；
        - 对纯文本中的表情名称进行搜索，拆分成 文本 + StickerContent。
        """
        soup = BeautifulSoup(self.raw, "html.parser")
        text = soup.get_text(strip=True)

        # 没有表情或文本为空：直接返回纯文本
        if not text or not self.emotes:
            return [text] if text else []

        # emotes 只包含当前文本里实际出现过的表情，不需要再过滤 / 排序
        emote_map: dict[str, Emote] = {e.name: e for e in self.emotes if e.name}
        if not emote_map:
            return [text]

        contents: list[ContentItem] = []
        text_len = len(text)
        i = 0
        last_plain_start = 0

        # 线性扫描文本，遇到任一 emote.name 就切分为 文本 + 贴纸
        while i < text_len:
            matched_name: str | None = None

            # 尝试匹配所有表情名
            for name, emote in emote_map.items():
                if text.startswith(name, i):
                    matched_name = name
                    break

            if matched_name is None:
                # 当前无表情命中，继续向后
                i += 1
                continue

            # 先输出前面累积的纯文本
            if i > last_plain_start:
                if plain := text[last_plain_start:i]:
                    contents.append(plain)

            emote = emote_map[matched_name]
            contents.append(
                Creator.sticker(
                    url=emote.url,
                    size="small",
                    desc=emote.name,
                )
            )

            # 跳过这段表情文本
            i += len(matched_name)
            last_plain_start = i

        # 末尾剩余文本
        if last_plain_start < text_len:
            if tail := text[last_plain_start:]:
                contents.append(tail)

        return contents


class CommentList(Struct):
    hotList: list[Comment]
    default: list[Comment] = field(name="list")

    @property
    def comments(self) -> list[Comment]:
        return self.hotList + self.default
