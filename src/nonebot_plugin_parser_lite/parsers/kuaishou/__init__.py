import re
from typing import ClassVar

from msgspec import convert

from ...utils.browser import BROWSER, DataPacket
from ...utils.format import format_num, replace_placeholder_to_sticker
from ..base import (
    BaseParser,
    Comment,
    MediaContent,
    ParseException,
    Platform,
    PlatformEnum,
    handle,
)
from .decode import decode_init_state
from .states import CommentList, Data, KsComment

KUAISHOU_PATTERN = re.compile(r"\[(?P<name>[^]]+)\]")


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

        tab = BROWSER.new_tab()
        tab.set.user_agent(
            self.ios_headers["User-Agent"],
            "iPhone",
        )
        tab.set.load_mode.none()
        tab.listen.start("/rest/wd/photo/comment/list")
        tab.get(url)
        cms = tab.listen.wait()
        assert isinstance(cms, DataPacket)
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
        video_url = photo.video_url
        img_urls = photo.img_urls
        cover_url = photo.cover_url

        # 添加视频内容
        if video_url:
            contents.append(
                self.create_video(
                    url_or_task=video_url,
                    cover_url=cover_url,
                    duration=photo.duration,
                )
            )

        # 添加图片内容
        if img_urls:
            contents.extend(self.create_images(img_urls))

        # 既没有视频也没有图集时，兜底使用封面图
        if not video_url and not img_urls and cover_url:
            contents.append(self.create_image(url=cover_url))


        # 构建作者
        author = self.create_author(name=photo.name, avatar_url=photo.headUrl)
        comments = self.format_comments(data_map.comments)

        return self.result(
            author=author,
            content=contents,
            stats=self.create_stats(
                view_count=format_num(photo.viewCount),
                like_count=format_num(photo.likeCount),
                comment_count=format_num(photo.commentCount),
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
                content=replace_placeholder_to_sticker(
                    rc.content, KUAISHOU_PATTERN, "kuaishou"
                ),
                timestamp=rc.timestamp // 1000,
                stats=self.create_stats(
                    like_count=format_num(rc.likedCount),
                    comment_count=format_num(rc.subCommentCount),
                ),
                location=rc.authorArea,
            )

            for sc in comments.subCommentsMap.get(str(rc.comment_id), [])[:3]:
                sc: KsComment
                rootComment.replies.append(
                    self.create_comment(
                        author=self.create_author(
                            name=sc.author_name,
                            avatar_url=sc.headurl,
                        ),
                        content=replace_placeholder_to_sticker(
                            sc.content, KUAISHOU_PATTERN, "kuaishou"
                        ),
                        timestamp=sc.timestamp // 1000,
                        stats=self.create_stats(
                            like_count=format_num(sc.likedCount),
                        ),
                        location=sc.authorArea,
                    )
                )
            result.append(rootComment)
        return result
