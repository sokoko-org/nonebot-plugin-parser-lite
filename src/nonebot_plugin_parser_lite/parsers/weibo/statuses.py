from datetime import datetime
import re

from msgspec import Struct
from msgspec.json import Decoder

from ...creator import Creator
from ...utils.format import replace_placeholder_to_sticker
from .auth import AuthHelper
from .longText import decoder as longTextDecoder

_URL_PATTERN = re.compile(r" http://t\.cn/\S+\u200b$")

WEIBO_PATTERN = re.compile(r"\[(?P<name>[^]]+)\]")


class OriginalPic(Struct):
    url: str


class Pic(Struct):
    original: OriginalPic
    pic_id: str
    type: str
    """pic/livephoto"""
    video: str = ""
    """Live动图"""

    @property
    def content(self):
        if self.video:
            return Creator.live_photo(
                video_url=self.video,
                image_url=self.original.url,
                ext_headers={"Referer": "https://weibo.com/"},
            )
        return Creator.image(
            url=self.original.url, ext_headers={"Referer": "https://weibo.com/"}
        )


class MediaInfo(Struct):
    name: str
    stream_url_hd: str


class PageInfo(Struct):
    page_pic: str
    page_title: str
    media_info: MediaInfo

    @property
    def content(self):
        return Creator.video(
            url_or_task=self.media_info.stream_url_hd,
            cover_url=self.page_pic,
            ext_headers={"Referer": "https://weibo.com/"},
        )


class User(Struct):
    idstr: str
    screen_name: str
    """用户昵称"""
    profile_image_url: str
    """头像"""


class WeiboData(Struct):
    user: User
    text_raw: str
    """正文，需去除末尾链接"""
    idstr: str
    created_at: str
    """`Thu Oct 02 14:39:33 +0800 2025`"""
    region_name: str
    reposts_count: int
    """转发数"""
    comments_count: int
    """评论数"""
    attitudes_count: int
    """点赞数"""
    isLongText: bool
    """是否需要请求长文"""
    pic_num: int
    pic_infos: dict[str, Pic] | None = None
    page_info: PageInfo | None = None
    """视频信息"""
    retweeted_status: "WeiboData | None" = None
    """转发微博"""

    async def get_content(self):
        if self.isLongText:
            res = await AuthHelper.get(
                "https://weibo.com/ajax/statuses/longtext",
                params={"id": self.idstr},
            )
            text = longTextDecoder.decode(res.content).data.longTextContent_raw
        else:
            text = self.text_raw
        cleaned_text = _URL_PATTERN.sub("", text).strip()
        content = replace_placeholder_to_sticker(cleaned_text, WEIBO_PATTERN, "weibo")
        if self.pic_infos:
            content.extend(pic.content for pic in self.pic_infos.values())
        if self.page_info:
            content.append(self.page_info.content)
        return content

    @property
    def url(self) -> str:
        return f"https://weibo.com/{self.user.idstr}/{self.idstr}"

    @property
    def timestamp(self) -> int:
        dt = datetime.strptime(self.created_at, "%a %b %d %H:%M:%S %z %Y")
        dt = dt.astimezone()
        return int(dt.timestamp())


decoder = Decoder(WeiboData)
