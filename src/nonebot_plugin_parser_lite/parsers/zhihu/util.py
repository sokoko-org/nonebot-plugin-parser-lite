from bs4 import BeautifulSoup
from bs4.element import NavigableString, Tag

from ...creator import Creator
from ...data import ContentItem
from ...download import DOWNLOADER

VIDEO_HEADER = {**DOWNLOADER.headers, "x-app-za": "OS=webplayer", "x-referer": ""}


def _quality_rank(q: str) -> int:
    """把 'FHD'/'HD'/'SD' 映射到数值，越大越好。"""
    q = q.upper()
    if q == "FHD":
        return 3
    if q == "HD":
        return 2
    return 1 if q == "SD" else 0


async def fetch_video(video_id: str, content_type: str):
    res = await DOWNLOADER.client.post(
        "https://www.zhihu.com/api/v4/video/play_info",
        headers=VIDEO_HEADER,
        json={
            "content_id": video_id,
            "video_id": video_id,
            "content_type_str": content_type,
            "is_only_video": True,
            "scene_code": "answer_detail_web",
        },
    )
    data = res.json()
    video_play = data["video_play"]
    mp4_list = video_play.get("playlist", {}).get("mp4")
    if not mp4_list:
        return None

    # 至少保证有一个条目，所以直接用 max 推导出最佳条目
    best_item = max(
        mp4_list,
        key=lambda item: _quality_rank(item["quality"]),
    )

    return Creator.video(
        url_or_task=best_item["url"][0],
        cover_url=video_play["default_cover"],
        duration=best_item["duration"],
    )


async def parse_rich_content(html: str, content_type: str) -> list[ContentItem]:
    """
    将知乎内容 HTML 解析为有顺序的文本 + 媒体列表
    """
    soup = BeautifulSoup(html.replace(r"\"", '"'), "html.parser")
    _clean_soup(soup)

    result: list[ContentItem] = []
    buffer: list[str] = []

    async for item in _iter_media_and_text(soup, content_type):
        if isinstance(item, str):
            buffer.append(item)
        else:
            if buffer:
                text_block = "".join(buffer)
                lines = [line.rstrip() for line in text_block.splitlines()]
                if normalized := "\n".join(lines).strip():
                    result.append(normalized)
                buffer.clear()
            result.append(item)

    if buffer:
        text_block = "".join(buffer)
        lines = [line.rstrip() for line in text_block.splitlines()]
        if normalized := "\n".join(lines).strip():
            result.append(normalized)

    return result


def _clean_soup(soup: BeautifulSoup) -> None:
    """预清洗 DOM：移除 noscript 等无效节点。"""
    for noscript in soup.find_all("noscript"):
        noscript.decompose()


async def _iter_media_and_text(soup: BeautifulSoup, content_type: str):
    """
    按 DOM 顺序依次产出文本 / 图片 / 视频等内容。
    这是一个 async 生成器，方便内部按需 await。
    """
    for element in soup.descendants:
        if isinstance(element, Tag):
            if element.name == "p":
                yield "\n"
                continue

            if element.name == "br":
                yield "\n"
                continue

            if element.name == "a" and "video-box" in (element.get("class") or []):
                video = await _parse_video_box(element, content_type)
                if video:
                    yield video

                if data_name := element.get("data-name"):
                    if text := str(data_name).strip():
                        yield text

                element.decompose()
                continue

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
                    yield Creator.graphic(url=src)

        elif isinstance(element, NavigableString):
            text = str(element)
            if text.strip():
                yield text


async def _parse_video_box(tag: Tag, content_type: str):
    """
    解析知乎 <a class="video-box">，根据 data-lens-id 拉取视频信息
    """
    video_id = tag.get("data-lens-id")
    if not isinstance(video_id, str) or not video_id:
        # data-lens-id 缺失或类型异常时，认为无法解析该视频节点
        return None
    return await fetch_video(video_id, content_type) if video_id else None
