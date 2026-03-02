import re
from typing import ClassVar

from msgspec import convert

from ..base import (
    BaseParser,
    PlatformEnum,
    ParseException,
    handle,
    Comment,
    Platform,
    MediaContent,
)
from .decode import decode_init_state
from .states import Data, CommentList
from ...utils import format_num
from ...browser import BROWSER
from .sticker_map import EMOJI_MAP

_STICKER_PATTERN = re.compile(r"\[(?P<name>[^]]+)\]")


class KuaiShouParser(BaseParser):
    """快手解析器"""

    # 平台信息
    platform: ClassVar[Platform] = Platform(
        name=PlatformEnum.KUAISHOU, display_name="快手"
    )

    # https://v.kuaishou.com/2yAnzeZ
    @handle("v.kuaishou", r"v\.kuaishou\.com/[A-Za-z\d._?%&+\-=/#]+")
    @handle("kuaishou", r"(?:www\.)?kuaishou\.com/[A-Za-z\d._?%&+\-=/#]+")
    @handle("chenzhongtech", r"(?:v\.m\.)?chenzhongtech\.com/fw/[A-Za-z\d._?%&+\-=/#]+")
    async def _parse_v_kuaishou(self, searched: re.Match[str]):
        # 从匹配对象中获取原始URL
        url = f"https://{searched.group(0)}"
        real_url = await self.get_redirect_url(url, headers=self.ios_headers)

        if len(real_url) <= 0:
            raise ParseException("failed to get location url from url")

        # /fw/long-video/ 返回结果不一样, 统一替换为 /fw/photo/ 请求
        real_url = real_url.replace("/fw/long-video/", "/fw/photo/")
        tab = BROWSER.new_tab()
        tab.set.user_agent(
            self.ios_headers["User-Agent"],
            "iPhone",
        )
        tab.set.load_mode.none()
        tab.listen.start("/rest/wd/photo/comment/list")
        tab.get(real_url)
        cms = tab.listen.wait()
        assert cms
        assert not isinstance(cms, list)
        tab.listen.stop()
        tab.stop_loading()
        data = tab.run_js("window.INIT_STATE", as_expr=True)
        raw = decode_init_state(data)
        tab.close()
        data_map = convert(raw, Data)
        data_map.comments = convert(cms.response.body, CommentList)

        photo = data_map.info.photo
        if photo is None:
            raise ParseException("window.init_state don't contains videos or pics")

        # 简洁的构建方式
        contents: list[MediaContent | str] = [photo.caption]

        # 添加视频内容
        if video_url := photo.video_url:
            contents.append(
                self.create_video(video_url, photo.cover_url, photo.duration)
            )

        # 添加图片内容
        if img_urls := photo.img_urls:
            contents.extend(self.create_images(img_urls))

        # 构建作者
        author = self.create_author(name=photo.name, avatar_url=photo.headUrl)
        comments = self.format_comments(data_map.comments)

        return self.result(
            title=photo.caption,
            author=author,
            content=contents,
            stats=self.create_stats(
                view_count=format_num(photo.viewCount),
                like_count=format_num(photo.likeCount),
                comment_count=format_num(photo.commentCount),
                share_count=format_num(photo.shareCount),
            ),
            timestamp=photo.timestamp // 1000,
            comments=comments,
        )

    def format_comments(self, comments: CommentList) -> list[Comment]:
        """格式化评论"""
        result: list[Comment] = []
        parent_comments = comments.rootComments[:5]
        for rc in parent_comments:
            rootComment = self.create_comment(
                author=self.create_author(
                    name=rc.author_name,
                    avatar_url=rc.headurl,
                ),
                content=self.format_sticker(rc.content),
                timestamp=rc.timestamp // 1000,
                stats=self.create_stats(
                    like_count=format_num(rc.likedCount),
                    comment_count=format_num(rc.subCommentCount),
                ),
            )

            for sc in comments.subCommentsMap.get(str(rc.comment_id), [])[:3]:
                rootComment.replies.append(
                    self.create_comment(
                        author=self.create_author(
                            name=sc.author_name,
                            avatar_url=sc.headurl,
                        ),
                        content=self.format_sticker(sc.content),
                        timestamp=sc.timestamp // 1000,
                        stats=self.create_stats(
                            like_count=format_num(sc.likedCount),
                        ),
                    )
                )
            result.append(rootComment)
        return result

    def format_sticker(self, text: str) -> list[MediaContent | str]:
        """
        将包含小黑盒表情占位符的文本拆分为文本与图片。表情格式形如「[勤洗手]」，先整体按中括号匹配，再解析内部的 group_name 和 code。

        :param text: 可能包含表情占位符的原始文本，如 "你好[勤洗手]呀"。
        :return: 由普通文本和 MediaContent 组成的列表，顺序与原字符串一致。
        """
        if "[" not in text or "]" not in text or not _STICKER_PATTERN.search(text):
            return [text]

        result: list[MediaContent | str] = []
        last_pos = 0

        for match in _STICKER_PATTERN.finditer(text):
            start, end = match.span()
            if start > last_pos:
                if plain := text[last_pos:start]:
                    result.append(plain)

            group_name = match["name"]
            if img_url := EMOJI_MAP.get(group_name):
                result.append(self.create_sticker(url=img_url, size="small"))
            else:
                result.append(match[0])

            last_pos = end

        # 最后剩余的纯文本
        if last_pos < len(text):
            if tail := text[last_pos:]:
                result.append(tail)

        return result
