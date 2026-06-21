import re
from typing import ClassVar

from ...data import Comment
from ..base import (
    BaseParser,
    MatchWithParams,
    ParseException,
    Platform,
    PlatformEnum,
    handle,
)
from .discovery import decoder as discoveryDecoder

INITIAL_STATE = re.compile(
    pattern=r"window\.__INITIAL_STATE__=(.*?)</script>",
    flags=re.DOTALL,
)


class RedNoteParser(BaseParser):
    platform: ClassVar[Platform] = Platform(
        name=PlatformEnum.REDNOTE, display_name="小红书"
    )

    def __init__(self):
        super().__init__()
        self.ios_headers.update(
            {
                "origin": "https://www.xiaohongshu.com",
                "x-requested-with": "XMLHttpRequest",
                "sec-fetch-site": "same-origin",
                "sec-fetch-mode": "cors",
                "sec-fetch-dest": "empty",
            }
        )

    @handle("xhslink.com", r"xhslink\.com/[A-Za-z0-9._?%&+=/#@-]+")
    async def _parse_short_link(self, searched: MatchWithParams):
        url = f"https://{searched.url}"
        return await self.parse_with_redirect(url, self.ios_headers)

    # https://www.xiaohongshu.com/explore/6a33df40000000001101fce5?xsec_token=ABoRHhYoIhXV24zUz64kWg8vu6u8D4zLUjIFRBf8fcf54=
    # https://www.xiaohongshu.com/explore/6a355d090000000021018c66?xsec_token=CBC_w7YSZbQP_uKutDlmX7iqXuEzWJJ8x8_nfNNfFWoHU=
    @handle(
        "xiaohongshu.com",
        r"(?P<type>explore|search_result|discovery/item)/(?P<note_id>[0-9a-zA-Z]+)",
        params={"xsec_token": {}},
    )
    async def _parse_common(self, searched: MatchWithParams):
        # parse_type = searched["type"]
        note_id = searched["note_id"]
        xsec_token = searched["xsec_token"]

        url = f"https://www.xiaohongshu.com/discovery/item/{note_id}?xsec_token={xsec_token}&xsec_source=pc_share"

        response = await self.httpx.get(
            url,
            headers=self.ios_headers,
        )
        response.raise_for_status()
        html = response.text

        if matched := INITIAL_STATE.search(html):
            raw = matched[1].replace("undefined", "null")
        else:
            raise ParseException("小红书分享链接失效或内容已删除")
        init_state = discoveryDecoder.decode(raw)
        note_detail = init_state.noteData.data.noteData
        comment_data = init_state.noteData.data.commentData
        author = self.create_author(
            name=note_detail.nickname,
            avatar_url=note_detail.avatar_url,
        )
        comment_list: list[Comment] = []

        for c in comment_data.comments:
            comment = self.create_comment(
                author=self.create_author(
                    name=c.user.nickname, avatar_url=c.user.image, location=c.ipLocation
                ),
                content=c.content,
                timestamp=c.time // 1000,
                stats=self.create_stats(
                    like_count=c.likeViewCount,
                    comment_count=str(len(c.subComments)),
                ),
            )

            for sub in c.subComments:
                comment.replies.append(
                    self.create_comment(
                        author=self.create_author(
                            name=sub.user.nickname,
                            avatar_url=sub.user.image,
                        ),
                        content=sub.content,
                        timestamp=sub.time // 1000,
                        stats=self.create_stats(
                            like_count=sub.likeViewCount,
                        ),
                    )
                )

            comment_list.append(comment)

        return self.result(
            title=note_detail.title,
            author=author,
            stats=self.create_stats(
                like_count=note_detail.interactInfo.likedCount,
                comment_count=note_detail.interactInfo.commentCount,
                share_count=note_detail.interactInfo.shareCount,
                collect_count=note_detail.interactInfo.collectedCount,
            ),
            comments=comment_list,
            content=note_detail.content,
            timestamp=note_detail.lastUpdateTime // 1000,
            url=url,
        )
