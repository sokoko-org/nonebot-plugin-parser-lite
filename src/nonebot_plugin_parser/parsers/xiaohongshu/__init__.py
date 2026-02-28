import re
from typing import ClassVar
from urllib.parse import parse_qsl

from curl_cffi import AsyncSession

from ..base import (
    Platform,
    BaseParser,
    PlatformEnum,
    ParseException,
    handle,
    pconfig,
    Comment,
    MediaContent,
)
from .explore import InitialState as exploreInitialState
from .explore import decoder as exploreDecoder

EMOJI_PATTERN = re.compile(r"(\[[\u4e00-\u9fff]{1,4}R\])")


class XiaoHongShuParser(BaseParser):
    # 平台信息
    platform: ClassVar[Platform] = Platform(
        name=PlatformEnum.XIAOHONGSHU, display_name="小红书"
    )
    session: AsyncSession
    # 小红书笔记详情页对真实浏览器仍有速率限制，达到限制后需要时间恢复
    # 暂时不知ck能否缓解此问题

    def __init__(self):
        super().__init__()
        explore_headers = {
            "accept": (
                "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,"
                "image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7"
            )
        }
        self.headers.update(explore_headers)

        discovery_headers = {
            "origin": "https://www.xiaohongshu.com",
            "x-requested-with": "XMLHttpRequest",
            "sec-fetch-site": "same-origin",
            "sec-fetch-mode": "cors",
            "sec-fetch-dest": "empty",
        }
        self.ios_headers.update(discovery_headers)

        if pconfig.xhs_ck:
            self.headers["cookie"] = pconfig.xhs_ck
            self.ios_headers["cookie"] = pconfig.xhs_ck
        self.session = AsyncSession(
            headers=self.headers, timeout=15, impersonate="chrome131"
        )

    @handle("xhslink.com", r"xhslink\.com/[A-Za-z0-9._?%&+=/#@-]+")
    async def _parse_short_link(self, searched: re.Match[str]):
        url = f"https://{searched[0]}"
        return await self.parse_with_redirect(url, self.ios_headers)

    # https://www.xiaohongshu.com/discovery/item/691e68a8000000001e02bcda?xsec_token=CBunzr4Cq8N7jbcXqpWDxGn11k7XwVIJ59KOvkRS_Qabw=
    @handle(
        "xiaohongshu.com",
        r"(?P<type>explore|search_result|discovery/item)/(?P<note_id>[0-9a-zA-Z]+)\?(?P<qs>[A-Za-z0-9._%&+=/#@-]+)",
    )
    async def _parse_common(self, searched: re.Match[str]):
        xhs_domain = "https://www.xiaohongshu.com"
        # parse_type = searched["type"]
        note_id = searched["note_id"]
        qs = searched["qs"]

        # 原始 URL（保留所有 query 参数）
        full_url = f"{xhs_domain}/explore/{note_id}"

        # 解析 query string，检查 xsec_token
        params_dict = dict(parse_qsl(qs, keep_blank_values=True))
        xsec_token = params_dict.get("xsec_token")
        if not xsec_token:
            # TODO: 无需 xsec_token 解析, 即自动搜索获取 xsec_token
            # 参考 https://github.com/Cloxl/xhshow
            # 使用搜索 API 进行获取, 但极易死号
            raise ParseException("缺少 xsec_token, 无法解析小红书链接")

        full_url += f"?xsec_token={xsec_token}&xsec_source=pc_share"

        return await self.parse_explore(full_url, note_id)

    async def _fetch_initial_state(self, url: str) -> exploreInitialState:
        """
        mode: "explore"
        """
        response = await self.session.get(url)
        # may be 302
        if response.status_code > 400:
            response.raise_for_status()
        html = response.text
        pattern = r"window\.__INITIAL_STATE__=(.*?)</script>"
        if matched := re.search(pattern, html):
            raw = matched[1].replace("undefined", "null")
        else:
            raise ParseException("小红书分享链接失效或内容已删除")
        return exploreDecoder.decode(raw)

    async def parse_explore(self, url: str, note_id: str):
        init_state = await self._fetch_initial_state(url)
        note_data = init_state.note.noteDetailMap[note_id]
        note_detail = note_data.note
        contents: list[MediaContent | str] = [note_detail.desc]
        image_urls = note_detail.image_urls

        if video_url := note_detail.video_url:
            cover_url = image_urls[0] if image_urls else None
            contents.append(self.create_video(video_url, cover_url))
        elif image_urls:
            contents.extend(self.create_images(image_urls))

        contents.extend(
            self.create_video(live_url, live_cover_url)
            for live_url, live_cover_url in note_detail.live_urls
        )
        author = self.create_author(
            name=note_detail.nickname, avatar_url=note_detail.avatar_url
        )

        def parse_text_with_stickers(text: str) -> list[str | MediaContent]:
            """
            :param text: 原始文本
            :return: [str | MediaContent]
            """
            mapping = init_state.redMoji.mojiData.redmojiMap
            if not mapping:  # 映射为空则不处理
                return [text]
            result: list[str | MediaContent] = []
            last_end = 0
            has_replacement = False  # 是否真的替换出了 sticker

            for m in EMOJI_PATTERN.finditer(text):
                start, end = m.span()
                key = m.group(1)  # 如 "[大笑R]"

                url = mapping.get(key)

                if not url:
                    # 没有映射就直接跳过这次匹配：
                    continue

                # 走到这里说明至少有一次成功替换
                has_replacement = True

                # 先把上一个匹配结束到这次匹配开始之间的文本加入
                if start > last_end:
                    if segment := text[last_end:start]:
                        result.append(segment)

                # 加入 sticker
                result.append(
                    self.create_sticker(
                        url=url,
                        desc=key,
                    )
                )

                last_end = end

            # 如果没有任何成功替换，直接返回整段文本
            if not has_replacement:
                return [text] if text else []

            # 处理最后一段普通文本
            if last_end < len(text):
                if tail := text[last_end:]:
                    result.append(tail)

            return result

        commentList: list[Comment] = []

        for c in note_data.comments.comments:
            comment = self.create_comment(
                author=self.create_author(
                    name=c.userInfo.nickname,
                    avatar_url=c.userInfo.image,
                ),
                content=parse_text_with_stickers(c.content),
                timestamp=c.createTime,
                stats=self.create_stats(
                    like_count=c.likeCount,
                    comment_count=c.subCommentCount,
                ),
                location=c.ipLocation,
            )

            for sub in c.subComments:
                comment.replies.append(
                    self.create_comment(
                        author=self.create_author(
                            name=sub.userInfo.nickname,
                            avatar_url=sub.userInfo.image,
                        ),
                        content=parse_text_with_stickers(sub.content),
                        timestamp=sub.createTime,
                        stats=self.create_stats(
                            like_count=sub.likeCount,
                            comment_count=sub.subCommentCount,
                        ),
                    )
                )
            commentList.append(comment)

        return self.result(
            title=note_detail.title,
            author=author,
            stats=self.create_stats(
                like_count=note_detail.interactInfo.likedCount,
                comment_count=note_detail.interactInfo.commentCount,
                share_count=note_detail.interactInfo.shareCount,
                collect_count=note_detail.interactInfo.collectedCount,
            ),
            comments=commentList,
            content=contents,
            timestamp=note_detail.lastUpdateTime // 1000,
        )
