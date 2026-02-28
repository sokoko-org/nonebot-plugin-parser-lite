from random import choice

from msgspec import Struct, field


class CdnUrl(Struct):
    cdn: str
    url: str | None = None


class Atlas(Struct):
    musicCdnList: list[CdnUrl] = field(default_factory=list)
    cdnList: list[CdnUrl] = field(default_factory=list)
    size: list[dict] = field(default_factory=list)
    img_route_list: list[str] = field(name="list", default_factory=list)

    @property
    def img_urls(self):
        if len(self.cdnList) == 0 or len(self.img_route_list) == 0:
            return []
        cdn = choice(self.cdnList).cdn
        return [f"https://{cdn}/{url}" for url in self.img_route_list]


class ExtParams(Struct):
    atlas: Atlas = field(default_factory=Atlas)


class Photo(Struct):
    caption: str
    """标题"""
    timestamp: int
    """发布时间"""
    duration: int = 0
    """时长"""
    userName: str = "未知用户"
    """用户名"""
    headUrl: str | None = None
    """头像"""
    likeCount: int = 0
    """点赞数"""
    commentCount: int = 0
    """评论数"""
    viewCount: int = 0
    """浏览数"""
    shareCount: int = 0
    """分享数"""
    coverUrls: list[CdnUrl] = field(default_factory=list)
    mainMvUrls: list[CdnUrl] = field(default_factory=list)
    ext_params: ExtParams = field(default_factory=ExtParams)

    @property
    def name(self) -> str:
        return self.userName.replace("\u3164", "").strip()

    @property
    def cover_url(self):
        """封面链接"""
        return choice(self.coverUrls).url if len(self.coverUrls) != 0 else None

    @property
    def video_url(self):
        """视频链接"""
        return choice(self.mainMvUrls).url if len(self.mainMvUrls) != 0 else None

    @property
    def img_urls(self):
        """图片链接列表"""
        return self.ext_params.atlas.img_urls


class Info(Struct):
    photo: Photo | None = None


# class EmotionConfigList(Struct):
#     emojiCode: str
#     emojiUrlList: list[str]


# class SystemStartup(Struct):
#     emotionConfigList: list[EmotionConfigList]
#     """贴纸映射列表(不全)"""


class Comment(Struct):
    content: str
    timestamp: int
    likedCount: int
    authorArea: str
    """归属地"""
    comment_id: int
    """评论id"""
    headurl: str
    """头像"""
    user_sex: str
    author_name: str
    subCommentCount: int = 0
    """子评论数量"""


class SubCommentList(Struct):
    subComments: list[Comment]
    """子评论列表"""

    def __iter__(self):
        return iter(self.subComments)

    def __getitem__(self, index):
        return self.subComments[index]

    def __len__(self):
        return len(self.subComments)


class CommentList(Struct):
    subCommentsMap: dict[str, SubCommentList]
    """子评论映射map, {父评论id: 子评论列表}"""
    rootComments: list[Comment]
    """父评论列表"""


class Data(Struct):
    """
    若不是等待加载完成，而是直接fetch源码，则数据项只有

    - `/rest/wd/system/startup` 系统信息
    - `/rest/zt/share/w/web` 没用的信息
    - `/rest/wd/user/profile` 链接分享者信息
    - `/rest/wd/ugH5App/photo/simple/info` 视频/图集信息
    - `/rest/wd/user/profile/author` 作者信息
    """

    # startup: SystemStartup = field(name="/rest/wd/system/startup")
    # """系统信息"""
    info: Info = field(name="/rest/wd/ugH5App/photo/simple/info")
    """视频/图集信息"""
    comments: CommentList | None = field(
        default=None, name="/rest/wd/photo/comment/list"
    )
    """评论信息，为页面二次加载赋值
    """
