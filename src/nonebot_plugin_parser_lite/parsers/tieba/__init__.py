from re import Match
from typing import ClassVar

from ..base import BaseParser, handle, Platform
from .utils import get_post, build_comments, build_content
from ...constants import PlatformEnum


class TiebaParser(BaseParser):
    platform: ClassVar[Platform] = Platform(
        name=PlatformEnum.TIEBA, display_name="百度贴吧"
    )

    @handle("tieba.baidu.com", r"tieba\.baidu\.com/p/(?P<post_id>\d+)")
    async def _parse(self, searched: Match[str]):
        # TODO: 显示吧头像
        post_id = searched.group("post_id")

        posts = await get_post(int(post_id))

        # 提取主题帖信息
        thread = posts.thread
        forum = posts.forum

        # 提取作者信息
        author = self.create_author(
            name=thread.user.show_name,
            avatar_url=f"http://tb.himg.baidu.com/sys/portraith/item/{thread.user.portrait}",
        )
        stats = self.create_stats(
            view_count=str(thread.view_num),
            like_count=str(thread.agree),
            comment_count=str(thread.reply_num),
            share_count=str(thread.share_num),
        )

        # 主楼正文内容
        contents = build_content(posts)
        comments = build_comments(posts.objs[1:], thread.user.user_id)
        extra = {
            "forum": {
                "name": forum.fname,
            },
        }

        return self.result(
            title=thread.title,
            author=author,
            content=contents,
            stats=stats,
            timestamp=thread.create_time,
            url=f"https://tieba.baidu.com/p/{post_id}",
            comments=comments,
            extra=extra,
        )
