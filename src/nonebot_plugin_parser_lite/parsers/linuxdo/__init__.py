from typing import ClassVar

from nonebot import logger

from ...utils.format import format_num
from ..base import (
    DOWNLOADER,
    BaseParser,
    MatchWithParams,
    Platform,
    PlatformEnum,
    handle,
    pconfig,
)
from .auth import LinuxDoAuth, format_response_diagnostics
from .topic import decoder as postDecoder


class LinuxDoParser(BaseParser):
    platform: ClassVar[Platform] = Platform(
        name=PlatformEnum.LINUXDO, display_name="LINUX DO"
    )

    def __init__(self):
        super().__init__()
        self.auth = LinuxDoAuth(DOWNLOADER.client, self.headers)

    @handle("linux.do", r"topic/(?P<topic_id>\d+)")
    async def parse_topic(self, searched: MatchWithParams):
        topic_id = searched["topic_id"]
        auth = self.auth
        cookies = await auth.cookies()
        res = await DOWNLOADER.client.get(
            f"https://linux.do/t/topic/{topic_id}.json",
            use_curl_cffi=True,
            headers=auth.headers,
            cookies=cookies,
        )
        await auth.update_from_response(res)
        response_diagnostics = format_response_diagnostics(res)
        if not res.is_success:
            logger.warning(f"Linux.do 帖子响应异常: {response_diagnostics}")
            raise await auth.tip_for_status(res.status_code)
        logger.info(f"Linux.do 帖子响应成功: {response_diagnostics}")
        post = postDecoder.decode(res.content)
        return self.result(
            author=self.create_author(
                name=post.detail.display_username or post.detail.username,
                avatar_url=post.detail.avatar_url,
                ext_headers={"Referer": "https://linux.do/"},
                use_curl_cffi=True,
            ),
            url=f"https://linux.do/t/topic/{post.id}",
            title=post.title,
            content=post.detail.content,
            comments=post.comment_list if pconfig.max_comments else [],
            stats=self.create_stats(
                like_count=format_num(post.like_count),
                view_count=format_num(post.views),
                comment_count=format_num(post.posts_count - 1),
            ),
            timestamp=post.detail.timestamp,
        )
