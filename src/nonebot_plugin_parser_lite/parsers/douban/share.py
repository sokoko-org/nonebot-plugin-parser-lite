from msgspec import Struct


class LargeImage(Struct):
    url: str


class Image(Struct):
    is_animated: bool
    large: LargeImage
    is_live: bool = False


class Photo(Struct):
    image: Image


class Author(Struct):
    avatar: str
    gender: str
    uid: str
    name: str
