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


class KuaiShouParser(BaseParser):
    """快手解析器"""

    # 平台信息
    platform: ClassVar[Platform] = Platform(
        name=PlatformEnum.KUAISHOU, display_name="快手"
    )

    def __init__(self):
        super().__init__()
        self.ios_headers["Referer"] = "https://v.kuaishou.com/"

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
            "Mozilla/5.0 (iPhone; CPU iPhone OS 16_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.6 Mobile/15E148 Safari/604.1 Edg/132.0.0.0",
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
                content=[rc.content],
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
                        content=[sc.content],
                        timestamp=sc.timestamp // 1000,
                        stats=self.create_stats(
                            like_count=format_num(sc.likedCount),
                        ),
                    )
                )
            result.append(rootComment)
        return result
