from typing import Any, ClassVar, TypeVar  # noqa: I001

from msgspec.json import Decoder
from nonebot import logger

from ...utils.format import format_num
from ..base import (
    BaseParser,
    MatchWithParams,
    ParseException,
    Platform,
    PlatformEnum,
    handle,
)
from .answer import decoder as answerDecoder
from .question import decoder as questionDecoder
from .article import decoder as articleDecoder
from .root_comment import decoder as rootCommentDecoder
from .sign import sign_zhihu_fetch_request

T = TypeVar("T")


class ZhiHuParser(BaseParser):
    platform: ClassVar[Platform] = Platform(
        name=PlatformEnum.ZHIHU, display_name="知乎"
    )

    @handle(
        "zhuanlan.zhihu.com/p",
        r"zhuanlan\.zhihu\.com/p/(?P<article_id>\d+)",
    )
    async def parse_zhuanlan(self, searched: MatchWithParams):
        article_id = searched["article_id"]
        article_data = await self.fetch(
            f"https://www.zhihu.com/api/v4/articles/{article_id}?include=content,topics,paid_info,can_comment,excerpt,thanks_count,voteup_count,comment_count,visited_count,relationship,ip_info,relationship.vote,author.badge_v2",
            articleDecoder,
        )

        statistics = article_data.reaction.statistics

        try:
            comment_data = await self.fetch(
                f"https://www.zhihu.com/api/v4/comment_v5/articles/{article_id}/root_comment?order_by=score&limit=20",
                rootCommentDecoder,
            )
            comments = [
                self.create_comment(
                    author=self.create_author(
                        name=c.author.name,
                        avatar_url=c.author.avatar_url,
                        id=c.author.url_token,
                        location=c.ip_info,
                    ),
                    content=c.content,
                    timestamp=c.created_time,
                    stats=self.create_stats(
                        like_count=format_num(c.like_count),
                        comment_count=format_num(c.child_comment_count),
                    ),
                )
                for c in comment_data.data
            ]
        except Exception as e:
            logger.warning(f"知乎获取评论失败, {type(e)}:{e!r}")
            comments = []

        return self.result(
            title=article_data.title,
            content=await article_data.get_content(),
            timestamp=article_data.updated,
            url=f"https://zhuanlan.zhihu.com/p/{article_data.id}",
            author=self.create_author(
                name=article_data.author.name,
                avatar_url=article_data.author.avatar_url,
                id=article_data.author.url_token,
                description=article_data.author.headline,
                location=article_data.ip_info,
            ),
            stats=self.create_stats(
                like_count=format_num(statistics.like_count),
                comment_count=format_num(statistics.comment_count),
                collect_count=format_num(statistics.favorites),
                extra={
                    "down_vote": format_num(statistics.down_vote_count),
                    "up_vote": format_num(statistics.up_vote_count),
                },
            ),
            comments=comments,
        )

    @handle(
        "www.zhihu.com/question",
        r"www\.zhihu\.com/question/\d+/answer/(?P<answer_id>\d+)",
    )
    async def parse_answer(self, searched: MatchWithParams):
        answer_id = searched["answer_id"]
        answer_data = await self.fetch(
            f"https://www.zhihu.com/api/v4/answers/{answer_id}?include=content,paid_info,can_comment,excerpt,thanks_count,voteup_count,comment_count,visited_count,attachment,reaction,ip_info,pagination_info,question.topics,reaction.relation.voting,author.badge_v2",
            answerDecoder,
        )

        question = answer_data.question
        statistics = answer_data.reaction.statistics

        try:
            comment_data = await self.fetch(
                f"https://www.zhihu.com/api/v4/comment_v5/answers/{answer_id}/root_comment?order_by=score&limit=20",
                rootCommentDecoder,
                {
                    "Referer": f"https://www.zhihu.com/question/{question.id}/answer/{answer_id}"
                },
            )
            comments = [
                self.create_comment(
                    author=self.create_author(
                        name=c.author.name,
                        avatar_url=c.author.avatar_url,
                        id=c.author.url_token,
                        location=c.ip_info,
                    ),
                    content=c.content,
                    timestamp=c.created_time,
                    stats=self.create_stats(
                        like_count=format_num(c.like_count),
                        comment_count=format_num(c.child_comment_count),
                    ),
                )
                for c in comment_data.data
            ]
        except Exception as e:
            logger.warning(f"知乎获取评论失败, {type(e)}:{e!r}")
            comments = []

        return self.result(
            title=question.title,
            content=await answer_data.get_content(),
            timestamp=answer_data.updated_time,
            url=f"https://www.zhihu.com/question/{question.id}/answer/{answer_id}",
            author=self.create_author(
                name=answer_data.author.name,
                avatar_url=answer_data.author.avatar_url,
                id=answer_data.author.url_token,
                description=answer_data.author.headline,
                location=answer_data.ip_info,
            ),
            stats=self.create_stats(
                like_count=format_num(statistics.like_count),
                comment_count=format_num(statistics.comment_count),
                collect_count=format_num(statistics.favorites),
                extra={
                    "down_vote": format_num(statistics.down_vote_count),
                    "up_vote": format_num(statistics.up_vote_count),
                },
            ),
            comments=comments,
        )

    @handle(
        "www.zhihu.com/question",
        r"www\.zhihu\.com/question/(?P<question_id>\d+)$",
    )
    async def parse_question(self, searched: MatchWithParams):
        question_id = searched["question_id"]
        question_data = await self.fetch(
            f"https://www.zhihu.com/api/v4/questions/{question_id}?include=read_count,visit_count,answer_count,voteup_count,comment_count,follower_count,detail,excerpt,author,relationship.is_following,topics",
            questionDecoder,
        )

        try:
            comment_data = await self.fetch(
                f"https://www.zhihu.com/api/v4/comment_v5/questions/{question_id}/root_comment?order_by=score&limit=20",
                rootCommentDecoder,
                {"Referer": f"https://www.zhihu.com/question/{question_id}"},
            )
            comments = [
                self.create_comment(
                    author=self.create_author(
                        name=c.author.name,
                        avatar_url=c.author.avatar_url,
                        id=c.author.url_token,
                        location=c.ip_info,
                    ),
                    content=c.content,
                    timestamp=c.created_time,
                    stats=self.create_stats(
                        like_count=format_num(c.like_count),
                        comment_count=format_num(c.child_comment_count),
                    ),
                )
                for c in comment_data.data
            ]
        except Exception as e:
            logger.warning(f"知乎获取评论失败, {type(e)}:{e!r}")
            comments = []
        return self.result(
            title=question_data.title,
            content=await question_data.get_content(),
            timestamp=question_data.updated_time,
            url=f"https://www.zhihu.com/question/{question_id}",
            author=self.create_author(
                name=question_data.author.name,
                avatar_url=question_data.author.avatar_url,
                id=question_data.author.url_token,
                description=question_data.author.headline,
            ),
            stats=self.create_stats(
                view_count=format_num(question_data.visit_count),
                comment_count=format_num(question_data.comment_count),
                extra={
                    "up_vote": format_num(question_data.voteup_count),
                    "follow": format_num(question_data.follower_count),
                },
            ),
            comments=comments,
        )

    async def fetch(
        self, url: str, decoder: Decoder[T], ext_header: dict[str, Any] | None = None
    ) -> T:
        res = await self.httpx.get(
            url,
            headers={
                **self.headers,
                **sign_zhihu_fetch_request(url),
                **(ext_header or {}),
            },
        )
        if res.status_code != 200:
            raise ParseException(res.text)
        return decoder.decode(res.content)
