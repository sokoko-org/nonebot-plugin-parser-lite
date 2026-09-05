from msgspec import Struct


class PlayInfo(Struct):
    main: str
    backup: str
    poster_url: str


class UserInfo(Struct):
    user_id: int
    user_name: str
    nickname: str


class Data(Struct):
    play_info: PlayInfo
    user_info: UserInfo
    prompt: str
