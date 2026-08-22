from datetime import datetime
from urllib.parse import urljoin

from bs4 import BeautifulSoup
from msgspec import Struct, field
from msgspec.json import Decoder

from ...creator import Creator
from ...data import Comment, PollContent
from ...data import PollOption as ContentPollOption
from ...utils.format import format_num
from .util import parse_date, parse_rich_content


class EventTopic(Struct):
    title: str


class EventPost(Struct):
    url: str
    topic: EventTopic


class Event(Struct):
    name: str | None
    starts_at: str
    ends_at: str | None
    timezone: str | None
    post: EventPost

    @property
    def display_time(self) -> str:
        start_at = datetime.fromisoformat(self.starts_at)
        if self.ends_at:
            end_at = datetime.fromisoformat(self.ends_at)
            if start_at.date() == end_at.date():
                value = f"{start_at:%Y-%m-%d %H:%M} - {end_at:%H:%M}"
            else:
                value = (
                    f"{start_at:%Y-%m-%d %H:%M} - "
                    f"{end_at:%Y-%m-%d %H:%M}"
                )
        else:
            value = start_at.strftime("%Y-%m-%d %H:%M")
        return f"{value} ({self.timezone})" if self.timezone else value

    def create_link(self):
        return Creator.link(
            url=urljoin("https://bb.zlb.ink/", self.post.url),
            title=self.name or self.post.topic.title,
            site_name="壁吧专楼吧",
            description=f"活动时间：{self.display_time}",
        )


class PollOption(Struct):
    id: str
    html: str
    votes: int

    @property
    def text(self) -> str:
        return BeautifulSoup(self.html, "html.parser").get_text(" ", strip=True)


class Poll(Struct):
    name: str
    type: str
    status: str
    options: list[PollOption]
    voters: int
    title: str | None = None
    close: str | None = None

    def create_content(self) -> PollContent:
        return Creator.poll(
            options=[
                ContentPollOption(text=item.text, votes=item.votes)
                for item in self.options
            ],
            title=self.title,
            total_votes=sum(item.votes for item in self.options),
            total_voters=self.voters,
            multiple=self.type == "multiple",
            closed=self.status == "closed",
            close_at=self.close,
        )


class Post(Struct):
    username: str
    """用户名"""
    display_username: str | None
    """昵称(可能没设置)"""
    created_at: str
    cooked: str
    """html(空需要过滤)"""
    avatar_template: str
    reply_count: int
    """该post的回复数"""
    reaction_users_count: int
    """可以当成该post的点赞数"""
    event: Event | None = None
    polls: list[Poll] = field(default_factory=list)

    @property
    def timestamp(self) -> int:
        return parse_date(self.created_at)

    @property
    def avatar_url(self) -> str:
        return urljoin("https://zlb.ink/", self.avatar_template.format(size=288))

    @property
    def content(self):
        return parse_rich_content(
            self.cooked,
            event_link=self.event.create_link() if self.event else None,
            polls={poll.name: poll.create_content() for poll in self.polls},
        )


class PostStream(Struct):
    posts: list[Post]


class Response(Struct):
    post_stream: PostStream
    title: str
    id: int
    posts_count: int
    """跟帖数,包含主贴"""
    reply_count: int
    """所有跟贴的总回复数"""
    views: int
    """所有跟帖总浏览数"""
    like_count: int

    @property
    def detail(self):
        return self.post_stream.posts[0]

    @property
    def comment_list(self) -> list[Comment]:
        return [
            Creator.comment(
                author=Creator.author(
                    name=c.display_username or c.username, avatar_url=c.avatar_url
                ),
                content=c.content,
                stats=Creator.stats(
                    like_count=format_num(c.reaction_users_count),
                    comment_count=format_num(c.reply_count),
                ),
                timestamp=c.timestamp,
            )
            for c in self.post_stream.posts[1:]
            if c.cooked
        ]


decoder = Decoder(Response)
