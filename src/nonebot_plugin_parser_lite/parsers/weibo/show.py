from bs4 import BeautifulSoup
from msgspec import Struct
from msgspec.json import Decoder


class PlayInfo(Struct):
    title: str
    text: str
    author: str
    avatar: str
    cover_image: str
    stream_url: str
    real_date: int
    urls: dict[str, str]
    duration_time: float
    attitudes_count: int
    comments_count: str
    reposts_count: str
    play_count: str
    ip_info_str: str

    @property
    def avatar_url(self) -> str:
        return f"https:{self.avatar}"

    @property
    def description(self) -> str:
        soup = BeautifulSoup(self.text, "html.parser")
        return soup.get_text(separator="\n", strip=True)

    @property
    def cover_url(self) -> str:
        return f"https:{self.cover_image}"

    @property
    def video_url(self) -> str:
        url = next(iter(self.urls.values()), None)
        return f"https:{url}" if url else self.stream_url


class Data(Struct):
    Component_Play_Playinfo: PlayInfo


class DataWrapper(Struct):
    data: Data


decoder = Decoder(DataWrapper)
