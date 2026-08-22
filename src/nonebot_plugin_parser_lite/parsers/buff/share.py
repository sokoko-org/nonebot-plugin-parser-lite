from msgspec import Struct


class ShareData(Struct):
    title: str
    url: str
