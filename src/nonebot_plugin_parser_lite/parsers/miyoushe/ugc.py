from __future__ import annotations

from msgspec import Struct
from msgspec.json import Decoder

from ...creator import Creator
from ...data import Author, Comment, ContentItem, Stats
from ...utils.format import format_num
from .sticker import replace_sticker


class UserInfo(Struct):
    uid: str
    avatar: str
    nickname: str


class ReplyStat(Struct):
    like_count: str
    reply_count: str


class Reply(Struct):
    user_info: UserInfo
    level_id: str
    reply_id: str
    content: str
    is_owner: bool
    created_at: int
    client_ip: str
    floor_id: int
    sub_replies: list[Reply]
    reply_stat: ReplyStat

    @property
    def author(self) -> Author:
        return Creator.author(
            name=self.user_info.nickname,
            id=self.user_info.uid,
            avatar_url=self.user_info.avatar,
            avatar_cache_key=f"miyoushe:{self.user_info.uid}",
            location=self.client_ip,
        )

    @property
    def stats(self) -> Stats:
        return Creator.stats(
            like_count=self.reply_stat.like_count,
            comment_count=self.reply_stat.reply_count,
        )

    def to_comment(self, parent_author: Author | None = None) -> Comment:
        author = self.author
        return Creator.comment(
            author=author,
            content=replace_sticker(self.content),
            timestamp=self.created_at,
            stats=self.stats,
            replies=[reply.to_comment(author) for reply in self.sub_replies],
            parent_author=parent_author,
        )


class ReplyCardResponse(Struct):
    reply_count: int
    reply_list: list[Reply]

    @property
    def comment_list(self) -> list[Comment]:
        return [reply.to_comment() for reply in self.reply_list]


class ReplyCardData(Struct):
    reply_card_response: ReplyCardResponse


class ReplyCard(Struct):
    data: ReplyCardData


class MysUserInfo(Struct):
    aid: str
    avatar_url: str
    nickname: str
    is_following: bool


class Developer(Struct):
    aid: str
    uid: str
    mys_user_info: MysUserInfo
    game_avatar: str
    game_nickname: str


class UpdateInfo(Struct):
    version: str
    content: str


class DeveloperNewsResponse(Struct):
    developer: Developer
    latest_update: UpdateInfo
    update_list: list[UpdateInfo]

    @property
    def author(self) -> Author:
        return Creator.author(
            name=self.developer.mys_user_info.nickname,
            avatar_url=self.developer.mys_user_info.avatar_url,
            id=self.developer.mys_user_info.aid,
            avatar_cache_key=f"miyoushe:{self.developer.mys_user_info.aid}",
        )


class DeveloperInfoData(Struct):
    developer_news_response: DeveloperNewsResponse


class DeveloperInfo(Struct):
    data: DeveloperInfoData


class Image(Struct):
    url: str


class VideoInfo(Struct):
    video_id: str
    video_url: str
    video_cover: str


class LevelInfo(Struct):
    level_id: str
    region: str
    level_name: str
    images: list[Image]
    limit_play_num_min: int
    """最小人数"""
    limit_play_num_max: int
    """最大人数"""
    hot_score: str
    """热度"""
    hot_score_icon: str
    good_rate: str
    """好评率"""
    good_rate_icon: str
    play_type: str
    desc: str
    level_intro: str
    video_info: VideoInfo

    @property
    def content(self) -> list[ContentItem]:
        content: list[ContentItem] = []
        if self.level_intro:
            content.append(self.level_intro)
        if self.desc:
            if content:
                content.append("\n")
            content.append(self.desc)
        content.extend(Creator.image(url=image.url) for image in self.images)
        if video_url := self.video_info.video_url:
            content.append(
                Creator.video(
                    url_or_task=video_url,
                    cover_url=self.video_info.video_cover,
                    cache_key=f"miyoushe:{self.video_info.video_id}",
                )
            )
        return content

    @property
    def title(self) -> str:
        return f"{self.level_name} - {self.play_type}"


class LevelDetailResponse(Struct):
    level_info: LevelInfo


class LevelDetailData(Struct):
    level_detail_response: LevelDetailResponse


class LevelDetail(Struct):
    data: LevelDetailData


class RespMap(Struct):
    reply_card: ReplyCard
    developer_info: DeveloperInfo
    level_detail: LevelDetail

    @property
    def reply_card_response(self) -> ReplyCardResponse:
        return self.reply_card.data.reply_card_response

    @property
    def developer_news_response(self) -> DeveloperNewsResponse:
        return self.developer_info.data.developer_news_response

    @property
    def level_info(self) -> LevelInfo:
        return self.level_detail.data.level_detail_response.level_info

    @property
    def author(self) -> Author:
        return self.developer_news_response.author

    @property
    def title(self) -> str:
        return self.level_info.title

    @property
    def content(self) -> list[ContentItem]:
        return self.level_info.content

    @property
    def stats(self) -> Stats:
        return Creator.stats(
            like_count=self.level_info.good_rate,
            comment_count=format_num(self.reply_card_response.reply_count),
            extra={
                "hot": self.level_info.hot_score,
            },
        )

    @property
    def comments(self) -> list[Comment]:
        return self.reply_card_response.comment_list


class Data(Struct):
    resp_map: RespMap


class Response(Struct):
    data: Data


decoder = Decoder(Response)
