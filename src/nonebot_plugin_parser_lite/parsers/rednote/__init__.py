import re
from typing import ClassVar
from urllib.parse import parse_qsl

from msgspec import convert
from nonebot.log import logger
from xhshow import SessionManager, Xhshow

from ...utils.http_utils import AsyncSession, get_async_client
from ..base import (
    BaseParser,
    Comment,
    MediaContent,
    ParseException,
    Platform,
    PlatformEnum,
    handle,
    pconfig,
)
from .explore import CommentList, NoteDetailWrapper
from .explore import decoder as exploreDecoder

CLIENT = Xhshow()
SESSION = SessionManager()


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
        self.comment_headers = self.headers.copy()

        if pconfig.xhs_ck:
            self.comment_headers["cookie"] = pconfig.xhs_ck
            self.ios_headers["cookie"] = pconfig.xhs_ck

    @handle("xhslink.com", r"xhslink\.com/[A-Za-z0-9._?%&+=/#@-]+")
    async def _parse_short_link(self, searched: re.Match[str]):
        url = f"https://{searched[0]}"
        return await self.parse_with_redirect(url, self.ios_headers)

    # https://www.xiaohongshu.com/discovery/item/691e68a8000000001e02bcda?xsec_token=CBunzr4Cq8N7jbcXqpWDxGn11k7XwVIJ59KOvkRS_Qabw=
    @handle(
        "xiaohongshu.com",
        r"(?P<type>explore|search_result|discovery/item)/(?P<note_id>[0-9a-zA-Z]+)\?(?P<qs>[A-Za-z0-9._%&+=/#@-]+)",
    )
    async def _parse_common(self, searched: re.Match[str]):
        xhs_domain = "https://www.xiaohongshu.com"
        # parse_type = searched["type"]
        note_id = searched["note_id"]
        qs = searched["qs"]

        # 原始 URL（保留所有 query 参数）
        full_url = f"{xhs_domain}/explore/{note_id}"

        # 解析 query string，检查 xsec_token
        params_dict = dict(parse_qsl(qs, keep_blank_values=True))
        xsec_token = params_dict.get("xsec_token")
        if not xsec_token:
            # TODO: 直接请求 xhs api获取数据，但是需要计算 sign
            raise ParseException("缺少 xsec_token, 无法解析小红书链接")

        full_url += f"?xsec_token={xsec_token}&xsec_source=pc_share"

        return await self.parse_explore(full_url, note_id, xsec_token)

    async def parse_explore(self, url: str, note_id: str, xsec_token: str):
        """解析小红书笔记详情页"""
        async with get_async_client(headers=self.headers) as client:
            raw = await self._fetch_init_state(client, url)
            com_data = await self._fetch_comments(client, note_id, xsec_token)

        init_state = exploreDecoder.decode(raw)
        note_data = init_state.note.noteDetailMap[note_id]
        note_data.comments_list = convert(com_data, CommentList)

        result = self._build_result(note_data)
        result.url = (
            f"https://www.xiaohongshu.com/explore/{note_id}?xsec_token={xsec_token}"
        )
        return result

    async def _fetch_init_state(self, client: AsyncSession, url: str) -> str:
        """获取并提取页面中的 __INITIAL_STATE__ 原始 JSON 字符串"""
        response = await client.get(url)
        response.raise_for_status()
        html = response.text

        if matched := INITIAL_STATE.search(html):
            # 将 undefined 替换为空字符串，避免 JSON 解析失败
            return matched[1].replace("undefined", '""')

        raise ParseException("小红书分享链接失效或内容已删除")

    async def _fetch_comments(
        self, client: AsyncSession, note_id: str, xsec_token: str
    ) -> dict:
        """获取笔记评论原始数据字典形式"""
        self.comment_headers.update(
            CLIENT.sign_headers_get(
                "https://edith.xiaohongshu.com/api/sns/web/v2/comment/page",
                cookies=pconfig.xhs_ck or "",
                params={
                    "note_id": note_id,
                    "cursor": "",
                    "top_comment_id": "",
                    "image_formats": "jpg,webp,avif",
                    "xsec_token": xsec_token,
                },
                session=SESSION,
            )
        )
        response = await client.get(
            "https://edith.xiaohongshu.com/api/sns/web/v2/comment/page",
            params={
                "note_id": note_id,
                "cursor": "",
                "top_comment_id": "",
                "image_formats": "jpg,webp,avif",
                "xsec_token": xsec_token,
            },
            headers=self.comment_headers,
        )
        data = response.json()
        if data.get("code") != 0:
            logger.warning("获取小红书评论数据失败")
            logger.error(response.text)
            return {"comments": []}

        return data.get("data", {"comments": []})

    def _build_result(self, note_data: NoteDetailWrapper):
        """从 note_data 构建最终解析结果"""
        note_detail = note_data.note

        contents: list[MediaContent | str] = [note_detail.desc]
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

        for c in note_data.comments_list.comments:
            comment = self.create_comment(
                author=self.create_author(
                    name=c.user_info.nickname,
                    avatar_url=c.user_info.image,
                ),
                content=c.content,
                timestamp=c.create_time // 1000,
                stats=self.create_stats(
                    like_count=c.like_count,
                    comment_count=str(len(c.sub_comments)),
                ),
                location=c.ip_location,
            )

            for sub in c.sub_comments:
                comment.replies.append(
                    self.create_comment(
                        author=self.create_author(
                            name=sub.user_info.nickname,
                            avatar_url=sub.user_info.image,
                        ),
                        content=sub.content,
                        timestamp=sub.create_time // 1000,
                        stats=self.create_stats(
                            like_count=sub.like_count,
                        ),
                    )
                )

            comment_list.append(comment)

        return comment_list
