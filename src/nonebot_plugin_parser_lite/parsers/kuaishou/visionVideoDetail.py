from msgspec import Struct, field


class Author(Struct):
    id: str
    name: str
    headerUrl: str


class Representation(Struct):
    backupUrl: list[str]
    url: str


class AdaptationSet(Struct):
    representation: list[Representation]


class Manifest(Struct):
    adaptationSet: list[AdaptationSet] = field(default_factory=list)


class Photo(Struct):
    id: str
    duration: int
    """ms"""
    caption: str
    likeCount: str
    realLikeCount: int
    coverUrl: str
    photoUrl: str
    viewCount: str
    timestamp: int
    """ms"""
    manifest: Manifest

    @property
    def media_url(self) -> str:
        if "kwaicdn.com" not in self.photoUrl:
            return self.manifest.adaptationSet[0].representation[0].backupUrl[0]
        return self.photoUrl


class VisionVideoDetail(Struct):
    author: Author
    photo: Photo
