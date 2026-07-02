from typing import ClassVar

from msgspec import convert
from nonebot.log import logger

from ...utils.browser import BrowserManager
from ...utils.format import format_num
from ..base import (
    BaseParser,
    Comment,
    MatchWithParams,
    ParseException,
    Platform,
    PlatformEnum,
    handle,
    pconfig,
)
from .encrypt import build_url
from .model import BaseResult


class HeyBoxParser(BaseParser):
    platform: ClassVar[Platform] = Platform(
        name=PlatformEnum.HEYBOX, display_name="小黑盒"
    )

    def __init__(self):
        super().__init__()
        self.headers.update(
            {
                "Referer": "https://www.xiaoheihe.cn/",
                "Host": "api.xiaoheihe.cn",
                "Origin": "https://www.xiaoheihe.cn",
                "Accept": "application/json, text/plain, */*",
            }
        )
        self.device_path = pconfig.config_dir / "heybox_device.txt"
        self.device_id: str = ""

    async def ensure_token(self):
        if not self.device_id:
            if await self.device_path.exists():
                self.device_id = (
                    await self.device_path.read_text(encoding="utf-8")
                ).strip()
            else:
                tab = await BrowserManager.new_tab(url="https://www.xiaoheihe.cn/")
                self.device_id = tab.run_js("window.SMSdk.getDeviceId()", as_expr=True)
                tab.close()
                logger.info(f"成功获取到小黑盒tokenid: {self.device_id[:5]}...")
                await self.device_path.write_text(self.device_id.strip())

    @handle("api.xiaoheihe.cn/v3/bbs/app/api/web/share", params={"link_id": {}})
    @handle("xiaoheihe.cn/bbs/post_share", params={"link_id": {}})
    @handle("xiaoheihe.cn/app/bbs", r"link\/(?P<link_id>[A-Za-z0-9]+)")
    async def _parse(self, searched: MatchWithParams):
        link_id = searched["link_id"]
        await self.ensure_token()
        response = await self.httpx.get(
            build_url(link_id),
            headers=self.headers,
            cookies={"x_xhh_tokenid": self.device_id},
        )
        response.raise_for_status()
        res = response.json()

        if res.get("status") != "ok":
            raise ParseException(f"小黑盒解析失败: {res}")

        data = convert(res["result"], BaseResult)
        comments = self._build_comments(data)

        return self.result(
            title=data.link.title,
            content=data.link.content,
            timestamp=data.link.create_at,
            url=f"https://www.xiaoheihe.cn/app/bbs/link/{link_id}",
            author=self.create_author(
                name=data.link.user.username,
                avatar_url=data.link.user.avatar_url,
            ),
            comments=comments,
            stats=self.create_stats(
                view_count=format_num(data.link.click),
                like_count=format_num(data.link.link_award_num),
                comment_count=format_num(data.link.comment_num),
                share_count=format_num(data.link.forward_num),
                collect_count=format_num(data.link.favour_count),
            ),
        )

    def _build_comments(self, data: BaseResult) -> list[Comment]:
        """
        根据小黑盒返回的数据构建评论和子回复列表。该方法会处理根评论和其下的所有子评论。

        :param data: 已转换好的帖子结果数据。
        :return: Comment 列表。
        """
        comments: list[Comment] = []

        for wrapper in data.comments:
            comment_list = wrapper.comment
            if not comment_list:
                continue

            root = comment_list[0]
            root_comment = self.create_comment(
                author=self.create_author(
                    name=root.user.username,
                    avatar_url=root.user.avatar_url,
                    location=root.ip_location,
                ),
                content=root.content,
                timestamp=root.create_at,
                stats=self.create_stats(
                    like_count=format_num(root.up),
                    comment_count=format_num(root.child_num),
                ),
            )

            for child in comment_list[1:]:
                root_comment.replies.append(
                    self.create_comment(
                        author=self.create_author(
                            name=child.user.username,
                            avatar_url=child.user.avatar_url,
                            location=child.ip_location,
                        ),
                        content=child.content,
                        timestamp=child.create_at,
                        stats=self.create_stats(
                            like_count=format_num(child.up),
                            comment_count=format_num(child.child_num),
                        ),
                    )
                )

            comments.append(root_comment)

        return comments
