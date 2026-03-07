import re
from typing import ClassVar


from ...utils.format import format_num

from .answer import decoder as answerDecoder
from ..base import (
    PlatformEnum,
    Platform,
    BaseParser,
    handle,
    ParseException,
    MediaContent,
)
from ...utils.browser import BROWSER
from bs4 import BeautifulSoup
from bs4.element import Tag, NavigableString

INITIAL_DATA = re.compile(
    pattern=r'<script id="js-initialData" type="text/json">(.*?)</script>',
    flags=re.DOTALL,
)


class ZhiHuParser(BaseParser):
    platform: ClassVar[Platform] = Platform(
        name=PlatformEnum.ZHIHU, display_name="知乎"
    )

    @handle(
        "www.zhihu.com/question",
        r"www\.zhihu\.com/question/(?P<question_id>\d+)/answer/(?P<answer_id>\d+)",
    )
    async def _parse_short_link(self, searched: re.Match[str]):
        question_id = searched["question_id"]
        answer_id = searched["answer_id"]
        url = f"https://www.zhihu.com/question/{question_id}/answer/{answer_id}"
        data = await self.fetch_initial_state(url)
        question = data.initialState.entities.questions[question_id]
        answer = data.initialState.entities.answers[answer_id]
        return self.result(
            title=question.title.replace(r"\"", '"'),
            content=self._extract_text_and_images(question.detail),
            timestamp=question.created,
            url=f"https://www.zhihu.com/question/{question_id}/answer/{answer_id}",
            author=self.create_author(
                name=question.author.name,
                avatar_url=question.author.avatarUrl,
                id=question.author.urlToken,
                description=question.author.headline,
            ),
            stats=self.create_stats(
                view_count=format_num(question.visitCount),
                like_count=format_num(question.voteupCount),
                collect_count=format_num(question.followerCount),
                comment_count=format_num(question.commentCount),
            ),
            comments=[
                self.create_comment(
                    author=self.create_author(
                        name=answer.author.name,
                        avatar_url=answer.author.avatarUrl,
                        id=answer.author.urlToken,
                        description=answer.author.headline,
                    ),
                    content=self._extract_text_and_images(answer.content),
                    timestamp=answer.createdTime,
                    stats=self.create_stats(
                        like_count=format_num(answer.voteupCount),
                        comment_count=format_num(answer.commentCount),
                    ),
                )
            ],
        )

    async def fetch_initial_state(self, url: str):
        tab = BROWSER.new_tab(url)
        html = tab.html
        tab.close()
        if matched := INITIAL_DATA.search(html):
            raw = matched[1].replace("undefined", "null")
        else:
            raise ParseException("知乎分享链接失效或内容已删除")
        return answerDecoder.decode(raw)

    def _extract_text_and_images(self, html: str) -> list[MediaContent | str]:
        """
        从知乎 HTML 内容中按顺序提取纯文本和图片。该方法通过遍历 HTML 节点，将图片节点转换为 MediaContent，并与周围文本一并按原顺序返回。

        :param html: 包含知乎内容的 HTML 字符串。
        :return: 由纯文本字符串和 MediaContent 对象组成的列表，顺序与原始 HTML 中的展示顺序一致
        """

        soup = BeautifulSoup(html.replace(r"\"", '"'), "html.parser")

        # 忽略 <noscript> 中的内容，避免重复或无效的占位文本干扰顺序
        for noscript in soup.find_all("noscript"):
            noscript.decompose()

        result: list[MediaContent | str] = []

        for element in soup.descendants:
            # 处理图片标签
            if isinstance(element, Tag) and element.name == "img":
                attrs: dict[str, str] = {
                    str(k): str(v[0] if isinstance(v, list) and v else v)
                    for k, v in (element.attrs or {}).items()
                    if v is not None
                }
                if src := (
                    attrs.get("data-original")
                    or attrs.get("data-actualsrc")
                    or attrs.get("data-default-watermark-src")
                ):
                    result.append(
                        self.create_image(
                            url=src,
                        )
                    )
            # 处理纯文本节点
            elif isinstance(element, NavigableString):
                if text := str(element).strip():
                    result.append(text)

        return result
