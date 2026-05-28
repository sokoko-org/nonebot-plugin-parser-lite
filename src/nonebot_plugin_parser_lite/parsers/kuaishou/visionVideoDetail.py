from msgspec import Struct, field


class VisionVideoDetailAuthor(Struct):
    id: str
    name: str
    headerUrl: str


class VisionVideoSetRepresentation(Struct):
    backupUrl: list[str]
    url: str


class VisionVideoAdaptationSet(Struct):
    representation: list[VisionVideoSetRepresentation]


class VisionVideoManifest(Struct):
    adaptationSet: list[VisionVideoAdaptationSet] = field(default_factory=list)


class VisionVideoDetailPhoto(Struct):
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
    manifest: VisionVideoManifest

    @property
    def media_url(self) -> str:
        if "kwaicdn.com" not in self.photoUrl:
            return self.manifest.adaptationSet[0].representation[0].backupUrl[0]
        return self.photoUrl


class VisionVideoDetail(Struct):
    author: VisionVideoDetailAuthor
    photo: VisionVideoDetailPhoto
