import re
from typing import ClassVar

from bs4 import BeautifulSoup
from bs4.element import NavigableString, Tag

from ...utils.browser import BrowserManager
from ...utils.format import format_num
from ..base import (
    BaseParser,
    MatchWithParams,
    MediaContent,
    ParseException,
    Platform,
    PlatformEnum,
    handle,
)
from .answer import decoder as answerDecoder

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
    async def _parse_short_link(self, searched: MatchWithParams):
        question_id = searched["question_id"]
        answer_id = searched["answer_id"]
        url = f"https://www.zhihu.com/question/{question_id}/answer/{answer_id}"
        data = await self.fetch_initial_state(url)
        question = data.initialState.entities.questions[question_id]
        answer = data.initialState.entities.answers[answer_id]
        return self.result(
            title=question.title.replace(r"\"", '"'),
            content=await self._parse_rich_content(answer.content),
            timestamp=answer.createdTime,
            url=f"https://www.zhihu.com/question/{question_id}/answer/{answer_id}",
            author=self.create_author(
                name=answer.author.name,
                avatar_url=answer.author.avatarUrl,
                id=answer.author.urlToken,
                description=answer.author.headline,
            ),
            stats=self.create_stats(
                like_count=format_num(answer.voteupCount),
                comment_count=format_num(answer.commentCount),
            ),
        )

    async def fetch_initial_state(self, url: str):
        tab = await BrowserManager.new_tab()
        tab.set.load_mode.eager()
        tab.get(url)
        html = tab.html
        tab.close()
        if matched := INITIAL_DATA.search(html):
            raw = matched[1].replace("undefined", "null")
        else:
            raise ParseException("知乎分享链接失效或内容已删除")
        return answerDecoder.decode(raw)

    async def fetch_video(self, video_id: str):
        res = await self.httpx.post(
            "https://www.zhihu.com/api/v4/video/play_info",
            json={
                "content_id": video_id,
                "video_id": video_id,
                "content_type_str": "answer",
                "is_only_video": True,
            },
        )
        data = res.json()
        if "video_play" not in data:
            raise ValueError(f"Invalid video data: {data}")

        video_play = data["video_play"]

        mp4_list = video_play["playlist"]["mp4"]

        def _quality_rank(q: str) -> int:
            """把 'FHD'/'HD'/'SD' 映射到数值，越大越好。"""
            q = q.upper()
            if q == "FHD":
                return 3
            if q == "HD":
                return 2
            return 1 if q == "SD" else 0

        # 至少保证有一个条目，所以直接用 max 推导出最佳条目
        best_item = max(
            mp4_list,
            key=lambda item: _quality_rank(item["quality"]),
        )

        return self.create_video(
            url_or_task=best_item["url"][0],
            cover_url=video_play["default_cover"],
            duration=best_item["duration"],
        )

    async def _parse_rich_content(self, html: str) -> list[MediaContent | str]:
        """
        将知乎内容 HTML 解析为有顺序的文本 + 媒体列表。
        """
        soup = BeautifulSoup(html.replace(r"\"", '"'), "html.parser")
        self._clean_soup(soup)

        result: list[MediaContent | str] = []
        async for item in self._iter_media_and_text(soup):
            result.append(item)
        return result

    def _clean_soup(self, soup: BeautifulSoup) -> None:
        """预清洗 DOM：移除 noscript 等无效节点。"""
        for noscript in soup.find_all("noscript"):
            noscript.decompose()

    async def _iter_media_and_text(self, soup: BeautifulSoup):
        """
        按 DOM 顺序依次产出文本 / 图片 / 视频等内容。
        这是一个 async 生成器，方便内部按需 await。
        """
        for element in soup.descendants:
            # 标签节点
            if isinstance(element, Tag):
                # 视频卡片：整体视为一个单元，处理完后从 DOM 移除以避免重复产出
                if element.name == "a" and "video-box" in (element.get("class") or []):
                    video = await self._parse_video_box(element)
                    if video:
                        yield video

                    if data_name := element.get("data-name"):
                        if text := str(data_name).strip():
                            yield text

                    # 从 DOM 树移除该节点及其所有子节点，后续遍历不会再碰到
                    element.decompose()
                    continue

                # 图片
                if element.name == "img":
                    attrs: dict[str, str] = {
                        str(k): str(v[0] if isinstance(v, list) and v else v)
                        for k, v in (element.attrs or {}).items()
                        if v
                    }
                    if src := (
                        attrs.get("data-original")
                        or attrs.get("data-actualsrc")
                        or attrs.get("data-default-watermark-src")
                        or attrs.get("src")
                    ):
                        yield self.create_image(url=src)

            elif isinstance(element, NavigableString):
                if text := str(element).strip():
                    yield text

    async def _parse_video_box(self, tag: Tag):
        """
        解析知乎 <a class="video-box">，根据 data-lens-id 拉取视频信息
        """
        video_id = tag.get("data-lens-id")
        if not isinstance(video_id, str) or not video_id:
            # data-lens-id 缺失或类型异常时，认为无法解析该视频节点
            return None
        return await self.fetch_video(video_id) if video_id else None
