import re
from typing import ClassVar
from urllib.parse import parse_qsl

from ...utils.format import replace_placeholder_to_sticker

from ..base import (
    BaseParser,
    Comment,
    ParseException,
    Platform,
    PlatformEnum,
    handle,
    pconfig,
)
from ..cookie import ck2dict
from .discovery import NoteDetailWrapper, decoder as discoveryDecoder, REDNOTE_PATTERN

INITIAL_STATE = re.compile(
    pattern=r"window\.__INITIAL_STATE__=(.*?)</script>",
    flags=re.DOTALL,
)


class RedNoteParser(BaseParser):
    # 平台信息
    platform: ClassVar[Platform] = Platform(
        name=PlatformEnum.REDNOTE, display_name="小红书"
    )
    # 小红书笔记详情页对真实浏览器仍有速率限制，达到限制后需要时间恢复
    # 暂时不知ck能否缓解此问题

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
    async def _parse_short_link(self, searched: re.Match[str]):
        url = f"https://{searched[0]}"
        return await self.parse_with_redirect(url, self.ios_headers)

    # https://www.xiaohongshu.com/discovery/item/691e68a8000000001e02bcda?xsec_token=CBwYRkYkdf7BHsEy2bVC9-ZYDHXJDjIRl6QI8xzqm-gEg
    @handle(
        "xiaohongshu.com",
        r"(?P<type>explore|search_result|discovery/item)/(?P<note_id>[0-9a-zA-Z]+)\?(?P<qs>[A-Za-z0-9._%&+=/#@-]+)",
    )
    async def _parse_common(self, searched: re.Match[str]):
        # parse_type = searched["type"]
        note_id = searched["note_id"]
        qs = searched["qs"]

        # 原始 URL（保留所有 query 参数）
        url = f"https://www.xiaohongshu.com/discovery/item/{note_id}"

        # 解析 query string，检查 xsec_token
        params_dict = dict(parse_qsl(qs, keep_blank_values=True))
        xsec_token = params_dict.get("xsec_token")
        if not xsec_token:
            # TODO: 直接请求 xhs api获取数据，但是需要计算 sign
            raise ParseException("缺少 xsec_token, 无法解析小红书链接")

        url += f"?xsec_token={xsec_token}&xsec_source=pc_share"

        response = await self.httpx.get(
            url,
            headers=self.ios_headers,
            cookies=ck2dict(pconfig.xhs_ck) if pconfig.xhs_ck else None,
        )
        response.raise_for_status()
        html = response.text

        if matched := INITIAL_STATE.search(html):
            raw = matched[1].replace("undefined", "null")
        else:
            raise ParseException("小红书分享链接失效或内容已删除")
        init_state = discoveryDecoder.decode(raw)
        note_data = init_state.noteData.data

        result = self._build_result(note_data)
        result.url = f"https://www.xiaohongshu.com/discovery/item/{note_id}?xsec_token={xsec_token}"
        return result

    def _build_result(self, note_data: NoteDetailWrapper):
        """从 note_data 构建最终解析结果"""
        note_detail = note_data.noteData

        contents = replace_placeholder_to_sticker(
            note_detail.desc, REDNOTE_PATTERN, "rednote"
        )
        contents.extend(note_detail.medias)

        author = self.create_author(
            name=note_detail.nickname,
            avatar_url=note_detail.avatar_url,
        )

        comment_list = self._build_comments(note_data)

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
            content=contents,
            timestamp=note_detail.lastUpdateTime // 1000,
        )

    def _build_comments(self, note_data: NoteDetailWrapper) -> list[Comment]:
        """从 note_data.comments_list 构建标准 Comment 列表"""
        comment_list: list[Comment] = []

        for c in note_data.commentData.comments:
            comment = self.create_comment(
                author=self.create_author(
                    name=c.user.nickname,
                    avatar_url=c.user.image,
                ),
                content=c.content,
                timestamp=c.time // 1000,
                stats=self.create_stats(
                    like_count=c.likeViewCount,
                    comment_count=str(len(c.subComments)),
                ),
                location=c.ipLocation,
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

        return comment_list
