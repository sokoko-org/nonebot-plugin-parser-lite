import msgspec
from msgspec import Struct, convert, field

from ...creator import Creator
from ...data import ContentItem
from ...utils.format import format_num


class CdnUrl(Struct):
    cdn: str


class MvorCoverCdnUrl(Struct):
    url: str


class Atlas(Struct):
    musicCdnList: list[CdnUrl]
    music: str
    cdnList: list[CdnUrl]
    img_list: list[str] = field(name="list")

    @property
    def img_urls(self) -> list[str]:
        if not self.img_list:
            return []

        cdn = self.cdnList[0].cdn
        return [f"https://{cdn}/{route}" for route in self.img_list]


class ExtParams(Struct):
    atlas: Atlas | None = None


class Photo(Struct):
    caption: str
    timestamp: int
    userName: str
    userSex: str
    headUrl: str
    likeCount: int
    commentCount: int
    viewCount: int
    coverUrls: list[MvorCoverCdnUrl]
    ext_params: ExtParams
    photoId: str
    userId: int
    photoType: str
    mainMvUrls: list[MvorCoverCdnUrl] | None = None
    duration: int = 0
    shareCount: int = 0

    @property
    def author(self):
        return Creator.author(
            name=self.userName.replace("\u3164", "").strip(),
            avatar_url=self.headUrl,
            avatar_cache_key=f"kuaishou:{self.userId}",
        )

    @property
    def stats(self):
        return Creator.stats(
            view_count=format_num(self.viewCount),
            like_count=format_num(self.likeCount),
            share_count=format_num(self.shareCount),
            comment_count=format_num(self.commentCount),
        )

    @property
    def content(self) -> list[ContentItem]:
        content: list[ContentItem] = [self.caption]
        if video := self.mainMvUrls:
            content.append(
                Creator.video(
                    url_or_task=video[0].url,
                    duration=self.duration // 1000,
                    cover_url=self.coverUrls[0].url,
                    cache_key=f"kuaishou:{self.photoId}",
                )
            )
        elif atlas := self.ext_params.atlas:
            content.extend(
                Creator.images(
                    atlas.img_urls,
                    cache_keys=[
                        f"kuaishou:{self.photoId}:{route}"
                        for route in atlas.img_list
                    ],
                )
            )
        return content


class Info(Struct):
    photo: Photo


PHOTO_INFO_PATH = "/rest/wd/ugH5App/photo/simple/info"
ENCODED_PHOTO_INFO_PATH = "0sftu0xe0vhI6Bqq0qipup0tjnqmf"


def decode_init_state(data: str) -> Photo:
    init_state = msgspec.json.decode(data, type=dict[str, object])

    for key, value in init_state.items():
        if ENCODED_PHOTO_INFO_PATH in key:
            return convert(value, Info).photo

    raise ValueError(f"INIT_STATE 中未找到作品信息接口: {PHOTO_INFO_PATH}")
