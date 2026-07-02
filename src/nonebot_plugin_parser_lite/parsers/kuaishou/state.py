from re import compile
from typing import Any

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
    photoType: str
    mainMvUrls: list[MvorCoverCdnUrl] | None = None
    duration: int = 0
    shareCount: int = 0

    @property
    def author(self):
        return Creator.author(
            name=self.userName.replace("\u3164", "").strip(),
            avatar_url=self.headUrl,
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
    def content(self):
        content: list[ContentItem] = [self.caption]
        if video := self.mainMvUrls:
            content.append(
                Creator.video(
                    url_or_task=video[0].url,
                    duration=self.duration // 1000,
                    cover_url=self.coverUrls[0].url,
                )
            )
        elif atlas := self.ext_params.atlas:
            content.extend(Creator.images(atlas.img_urls))
        return content


class Info(Struct):
    photo: Photo


class Data(Struct):
    info: Info = field(name="/rest/wd/ugH5App/photo/simple/info")


RE_PATH = compile(r"0sftu[^.\-@]*")
_FROM_CHARS = "".join(chr(i) for i in range(256))
_TO_CHARS = "".join(chr((i - 1) % 256) for i in range(256))
DECRYPT_TRANS = str.maketrans(_FROM_CHARS, _TO_CHARS)


# NOTE: 此解密不会正确解析 author 路径，因为我不需要它
def get_final_stable_path_ultimate(text: str) -> str:
    match_path = RE_PATH.search(text)
    return match_path.group(0).translate(DECRYPT_TRANS) if match_path else text


def decode_init_state(input_dict: dict[str, Any] | str | bytes):
    if isinstance(input_dict, (str, bytes)):
        input_dict = msgspec.json.decode(input_dict, type=dict[str, Any])
    return convert(
        {get_final_stable_path_ultimate(k): v for k, v in input_dict.items()}, Data
    ).info.photo
