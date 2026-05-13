from msgspec import Struct
from msgspec.json import Decoder


class Author(Struct):
    urlToken: str
    """用户主页的urlToken"""
    name: str
    """用户名称"""
    avatarUrl: str
    """用户头像"""
    headline: str
    """一句话介绍(可以理解为签名)"""
    gender: int
    """性别"""


class QuestionTopic(Struct):
    id: str
    """话题ID"""
    name: str
    """话题名称"""
    avatarUrl: str
    """话题图标"""


class Question(Struct):
    title: str
    """标题"""
    created: int
    """创建时间"""
    updatedTime: int
    """更新时间"""
    answerCount: int
    """回答数"""
    visitCount: int
    """浏览数"""
    followerCount: int
    """关注数"""
    commentCount: int
    """评论数"""
    detail: str
    """详细HTML内容(已知仅包含图片和文本，图片一定在文本前排布)"""
    topics: list[QuestionTopic]
    """话题信息"""
    author: Author
    """作者信息"""
    id: str
    """问题ID"""
    voteupCount: int
    """赞同数"""


class Answer(Struct):
    author: Author
    """作者信息"""
    commentCount: int
    """评论数"""
    content: str
    """内容HTML"""
    createdTime: int
    """创建时间"""
    updatedTime: int
    """更新时间"""
    ipInfo: str
    """IP归属地"""
    voteupCount: int
    """赞同数"""


class AnswerData(Struct):
    questions: dict[str, Question]
    """问题信息"""
    answers: dict[str, Answer]
    """回答信息"""


class InitStateData(Struct):
    entities: AnswerData


class InitState(Struct):
    initialState: InitStateData


decoder = Decoder(InitState)
