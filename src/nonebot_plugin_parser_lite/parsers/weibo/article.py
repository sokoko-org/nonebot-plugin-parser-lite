from bs4 import BeautifulSoup, Tag
from msgspec import Struct, field
from msgspec.json import Decoder

from ...creator import Creator
from ...data import ContentItem


class UserInfo(Struct):
    id: int
    screen_name: str
    profile_image_url: str


class RegionInfo(Struct):
    region_name: str


class Data(Struct):
    url: str
    title: str
    html: str = field(name="content")
    userinfo: UserInfo
    create_at_unix: int
    read_count: str
    region_info: RegionInfo

    @property
    def content(self):
        soup = BeautifulSoup(self.html, "html.parser")
        content: list[ContentItem] = []

        for element in soup.find_all(["p", "img"]):
            if not isinstance(element, Tag):
                continue
            if element.name == "p":
                if text := element.get_text(separator="\n", strip=True):
                    content.append(text)
            elif element.name == "img":
                src = element.get("src")
                if isinstance(src, str):
                    content.append(
                        Creator.image(
                            url=src, ext_headers={"Referer": "https://weibo.com/"}
                        )
                    )
        return content


class Detail(Struct):
    code: str
    msg: str
    data: Data


decoder = Decoder(Detail)
