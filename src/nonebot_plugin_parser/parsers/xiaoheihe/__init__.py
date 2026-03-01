from typing import ClassVar

from msgspec import convert

from ...utils import format_num

from .model import BaseResult

from .encrypt import build_url

from ..base import BaseParser, handle, Platform, PlatformEnum, ParseException, Comment
from re import Match
from httpx import AsyncClient


class XiaoHeiHeParser(BaseParser):
    platform: ClassVar[Platform] = Platform(
        name=PlatformEnum.XIAOHEIHE, display_name="小黑盒"
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

    @handle(
        "api.xiaoheihe.cn/v3/bbs/app/api/web/share",
        r"link_id=(?P<link_id>[A-Za-z0-9]+)",
    )
    @handle("xiaoheihe.cn/bbs/post_share", r"link_id=(?P<link_id>[A-Za-z0-9]+)")
    @handle("xiaoheihe.cn/app/bbs", r"link\/(?P<link_id>[A-Za-z0-9]+)")
    async def _parse(self, searched: Match[str]):
        link_id = searched["link_id"]

        async with AsyncClient(
            headers=self.headers,
            timeout=self.timeout,
            verify=False,
            cookies={
                "x_xhh_tokenid": "Boy7mxr15+ckLj3nTzhgH++a/0Vy5ROaW3gisfLeO+9Ptp+KBpKSpkBSANOiQs4p0oFx3r/xrlKAOCghvrqGDqw=="
            },
            # 自定义 x_xhh_tokenid 获取方式，使用无痕浏览器，打开小黑盒首页，控制台输入 window.SMSdk.getDeviceId()
            # 每次无痕都是随机的，随便造
        ) as client:
            response = await client.get(build_url(link_id))
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
            stats=self.create_stats(
                view_count=format_num(data.link.click),
                like_count=format_num(data.link.link_award_num),
                comment_count=format_num(data.link.comment_num),
                share_count=format_num(data.link.forward_num),
                collect_count=format_num(data.link.favour_count),
            ),
            comments=comments,
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
                ),
                content=root.content,
                timestamp=root.create_at,
                stats=self.create_stats(
                    like_count=format_num(root.up),
                    comment_count=format_num(root.child_num),
                ),
                location=root.ip_location,
            )

            for child in comment_list[1:]:
                root_comment.replies.append(
                    self.create_comment(
                        author=self.create_author(
                            name=child.user.username,
                            avatar_url=child.user.avatar_url,
                        ),
                        content=child.content,
                        timestamp=child.create_at,
                        stats=self.create_stats(
                            like_count=format_num(child.up),
                            comment_count=format_num(child.child_num),
                        ),
                        location=child.ip_location,
                    )
                )

            comments.append(root_comment)

        return comments
