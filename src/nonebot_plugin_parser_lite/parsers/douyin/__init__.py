import re
import time
from typing import ClassVar

from msgspec import convert

from ...utils.format import format_num
from ...utils.log import logger
from ..base import (
    BaseParser,
    ContentItem,
    HandlerFunc,
    MatchWithParams,
    ParseException,
    Platform,
    PlatformEnum,
    handle,
    pconfig,
)
from .aweme import Response
from .comment import decoder as commentDecoder
from .live import Room

WEB_RID_RE = re.compile(r'\\"webRid\\":\\"(\d+)\\"')

SHARE_CODE_PATTERNS = [
    r"%%([0-9a-zA-Z]{11})%%",
    r"ππ([0-9a-zA-Z]{11})ππ",
    r"[ωω|ÊÊ|ΨΨ|ΘΘ|ππ|ㄍㄍ|ΦΦ|ÑÑ|ŠŠ|▽▽|ÄÄ|ΔΔ|￠￠|ηη|Э|Ю|Я|д|ё|ζ|ξ|ǐ|爱|哈|喽|嗨|嗯|好|么|哒|吗|我|︽︽|∏∏|※※|➝➝|ǚǚ|бб|жж|ˇˇ|êê|йй|¥¥|^^]([0-9a-zA-Z]{11,16})[ωω|ÊÊ|ΨΨ|ΘΘ|ππ|ㄍㄍ|ΦΦ|ÑÑ|ŠŠ|▽▽|ÄÄ|ΔΔ|￠￠|ηη|Э|Ю|Я|д|ё|ζ|ξ|ǐ|爱|哈|喽|嗨|嗯|好|么|哒|吗|我|︽︽|∏∏|※※|➝➝|ǚǚ|бб|жж|ˇˇ|êê|йй|¥¥|^^]",
    r"ΞΞ([0-9a-zA-Z]{11})ΞΞ",
    r"ωω([0-9a-zA-Z]{11})ωω",
    r"ΔΔ([0-9a-zA-Z]{11})ΔΔ",
    r"▽▽([0-9a-zA-Z]{11})▽▽",
    r"\$\$([0-9a-zA-Z]{11})\$\$",
    r"ΨΨ([0-9a-zA-Z]{11})ΨΨ",
    r"ÀÀ([0-9a-zA-Z]{11})ÀÀ",
    r"αα([0-9a-zA-Z]{11})αα",
    r"%%([0-9a-zA-Z]{11,16})%%",
    r"(€[0-9A-Za-z]{4}€[0-9A-Za-z]{7}€)",
    r"ΦΦ([0-9a-zA-Z]{11})ΦΦ",
    r"ÊÊ([0-9a-zA-Z]{11})ÊÊ",
    r"ㄍㄍ([0-9a-zA-Z]{11})ㄍㄍ",
    r"##([0-9a-zA-Z]{11,16})##",
    r"##([0-9a-zA-Z]{11})##",
    r"ÑÑ([0-9a-zA-Z]{11})ÑÑ",
    r"฿฿([0-9a-zA-Z]{11})฿฿",
    r"ΣΣ([0-9a-zA-Z]{11})ΣΣ",
    r"ÄÄ([0-9a-zA-Z]{11})ÄÄ",
    r"ŠŠ([0-9a-zA-Z]{11})ŠŠ",
    r"ββ([0-9a-zA-Z]{11})ββ",
    r"#([0-9a-zA-Z]{11,16})#",
    r"￠￠([0-9a-zA-Z]{11})￠￠",
    r"ΘΘ([0-9a-zA-Z]{11})ΘΘ",
    r"ηη([0-9a-zA-Z]{11})ηη",
    r"(€[0-9A-Za-z]{4}€[0-9A-Za-z]{7}€|(€|З|Л|Ж|€€|ЗЗ|ЛЛ|ЖЖ|Ⓐ|Ⓑ|Ⓒ|Ⓓ|Ⓔ|Ⓕ|Ⓖ|Ⓗ|Ⓘ|Ⓙ|Ⓚ|Ⓛ|Ⓜ|Ⓝ|Ⓞ|Ⓟ|Ⓠ|Ⓡ|Ⓢ|Ⓣ|Ⓤ|Ⓥ|Ⓦ|Ⓧ|Ⓨ|Ⓩ|ⓐ|ⓑ|ⓒ|ⓓ|ⓔ|ⓕ|ⓖ|ⓗ|ⓘ|ⓙ|ⓚ|ⓛ|ⓜ|ⓝ|ⓞ|ⓟ|ⓠ|ⓡ|ⓢ|ⓣ|ⓤ|ⓥ|ⓦ|ⓧ|ⓨ|ⓩ|¿|¶|†|‡|←|♠|♣|♥|↑|◊|↔|∞|≠|∫|→|▣|▤|▥|▦|▩|▧|▨|◘|◙|◈|◐|◑|◎|⊙|ﻬ|ஐ|▶|ண|ゅ|ღ|๑|۩|۞|❈|✲|➹|◕|✿|☽|☾|❥|♡|★|♧|➳|➴|➵|❁|ஓ|☜|☞|✡|♦|◘|◙|▣|♟|■|▓|∏|☃|☇|☈|☊|☋|☍|☑|☒|✉|✎|✐|✰|❦|❧|➽|♝|➳|➴|♈|₪|௫|✪|✣|✤|✥|✦|✧|〆|〾)([0-9A-Za-z]{4})(€|З|Л|Ж|€€|ЗЗ|ЛЛ|ЖЖ|Ⓐ|Ⓑ|Ⓒ|Ⓓ|Ⓔ|Ⓕ|Ⓖ|Ⓗ|Ⓘ|Ⓙ|Ⓚ|Ⓛ|Ⓜ|Ⓝ|Ⓞ|Ⓟ|Ⓠ|Ⓡ|Ⓢ|Ⓣ|Ⓤ|Ⓥ|Ⓦ|Ⓧ|Ⓨ|Ⓩ|ⓐ|ⓑ|ⓒ|ⓓ|ⓔ|ⓕ|ⓖ|ⓗ|ⓘ|ⓙ|ⓚ|ⓛ|ⓜ|ⓝ|ⓞ|ⓟ|ⓠ|ⓡ|ⓢ|ⓣ|ⓤ|ⓥ|ⓦ|ⓧ|ⓨ|ⓩ|¿|¶|†|‡|←|♠|♣|♥|↑|◊|↔|∞|≠|∫|→|▣|▤|▥|▦|▩|▧|▨|◘|◙|◈|◐|◑|◎|⊙|ﻬ|ஐ|▶|ண|ゅ|ღ|๑|۩|۞|❈|✲|➹|◕|✿|☽|☾|❥|♡|★|♧|➳|➴|➵|❁|ஓ|☜|☞|✡|♦|◘|◙|▣|♟|■|▓|∏|☃|☇|☈|☊|☋|☍|☑|☒|✉|✎|✐|✰|❦|❧|➽|♝|➳|➴|♈|₪|௫|✪|✣|✤|✥|✦|✧|〆|〾)([0-9A-Za-z]{7})(€|З|Л|Ж|€€|ЗЗ|ЛЛ|ЖЖ|Ⓐ|Ⓑ|Ⓒ|Ⓓ|Ⓔ|Ⓕ|Ⓖ|Ⓗ|Ⓘ|Ⓙ|Ⓚ|Ⓛ|Ⓜ|Ⓝ|Ⓞ|Ⓟ|Ⓠ|Ⓡ|Ⓢ|Ⓣ|Ⓤ|Ⓥ|Ⓦ|Ⓧ|Ⓨ|Ⓩ|ⓐ|ⓑ|ⓒ|ⓓ|ⓔ|ⓕ|ⓖ|ⓗ|ⓘ|ⓙ|ⓚ|ⓛ|ⓜ|ⓝ|ⓞ|ⓟ|ⓠ|ⓡ|ⓢ|ⓣ|ⓤ|ⓥ|ⓦ|ⓧ|ⓨ|ⓩ|¿|¶|†|‡|←|♠|♣|♥|↑|◊|↔|∞|≠|∫|→|▣|▤|▥|▦|▩|▧|▨|◘|◙|◈|◐|◑|◎|⊙|ﻬ|ஐ|▶|ண|ゅ|ღ|๑|۩|۞|❈|✲|➹|◕|✿|☽|☾|❥|♡|★|♧|➳|➴|➵|❁|ஓ|☜|☞|✡|♦|◘|◙|▣|♟|■|▓|∏|☃|☇|☈|☊|☋|☍|☑|☒|✉|✎|✐|✰|❦|❧|➽|♝|➳|➴|♈|₪|௫|✪|✣|✤|✥|✦|✧|〆|〾)|activity_[0-9A-Za-z]{11})",
]


def _extract_share_code(match: re.Match[str]) -> str:
    groups = match.groups()
    # 分段规则的第 1 组是整段，第 3、5 组才是两段口令。
    if len(groups) == 6 and groups[2] is not None and groups[4] is not None:
        return groups[2] + groups[4]

    code = match[1]
    # 简单欧元分段规则只有一个捕获组，需去掉内部的分隔符。
    if code.startswith("€") and code.endswith("€"):
        code = code.replace("€", "")
    return code.removeprefix("activity_")


def _handle_share_codes(func: HandlerFunc) -> HandlerFunc:
    for pattern in SHARE_CODE_PATTERNS:
        func = handle("", pattern)(func)
    return func


class DouyinParser(BaseParser):
    platform: ClassVar[Platform] = Platform(
        name=PlatformEnum.DOUYIN, display_name="抖音"
    )
    ttwid: str = ""
    ttwid_update_at: float = 0

    def __init__(self):
        super().__init__()
        self.httpx.headers.update(
            {
                "Referer": "https://www.douyin.com/",
            }
        )

    async def ensure_ttwid(self):
        if self.ttwid and time.time() - self.ttwid_update_at < 3600:
            return
        resp = await self.httpx.post(
            "https://ttwid.bytedance.com/ttwid/union/register/",
            json={
                "region": "cn",
                "aid": 1768,
                "needFid": False,
                "service": "www.douyin.com",
                "migrate_info": {"ticket": "", "source": "node"},
                "cbUrlProtocol": "https",
                "union": True,
            },
        )
        resp.raise_for_status()
        ttwid = resp.cookies.get("ttwid", domain=".bytedance.com")
        if ttwid is None:
            raise ParseException(f"抖音 ttwid 注册成功但未返回 cookie: {resp.cookies}")
        self.ttwid = ttwid
        self.ttwid_update_at = time.time()

    # https://v.douyin.com/_2ljF4AmKL8
    @handle("v.douyin", r"v\.douyin\.com/[a-zA-Z0-9_\-]+")
    @handle("jx.douyin", r"jx\.douyin\.com/[a-zA-Z0-9_\-]+")
    async def _parse_short_link(self, searched: MatchWithParams):
        url = f"https://{searched.url}"
        return await self.parse_with_redirect(url)

    @_handle_share_codes
    async def _parse_share_code(self, searched: MatchWithParams):
        # NOTE: by @soloxiaoye2022
        response = await self.httpx.get(
            "https://parse-api.sokoko.org/api/douyin/resolve",
            params={"code": _extract_share_code(searched.match)},
        )
        data = response.json()
        if data["code"] != 200:
            raise ParseException(f"口令解析失败: {data}")
        return await self.parse_aweme_id(data["data"]["item_id"])

    @handle("webcast.amemv.com", r"douyin/webcast/reflow/(?P<room_id>\d+)")
    async def parse_live_by_room_id(self, searched: MatchWithParams):
        await self.ensure_ttwid()
        room_id = searched["room_id"]
        html = (
            await self.httpx.get(
                f"https://webcast.amemv.com/douyin/webcast/reflow/{room_id}",
                cookies={"ttwid": self.ttwid},
            )
        ).text
        if rid := WEB_RID_RE.search(html):
            return await self.parse_web_rid(rid[1])
        raise ParseException("提取 web_rid 失败")

    @handle("live.douyin.com", r"live\.douyin\.com/(?P<rid>\d+)")
    async def parse_live(self, searched: MatchWithParams):
        await self.ensure_ttwid()
        return await self.parse_web_rid(searched["rid"])

    async def parse_web_rid(self, web_rid: str):
        resp = await self.httpx.get(
            "https://live.douyin.com/webcast/room/web/enter/",
            params={
                "aid": 6383,
                "device_platform": "web",
                "browser_language": "zh-CN",
                "browser_platform": "Win32",
                "browser_name": "Chrome",
                "browser_version": "95.0.4638.69",
                "web_rid": web_rid,
            },
            cookies={"ttwid": self.ttwid},
        )
        if not resp.is_success:
            raise ParseException(f"解析抖音直播失败, 可能是直播不存在: {resp.text}")
        data = resp.json()
        if rooms := data.get("data", {}).get("data"):
            room = convert(rooms[0], Room)
            return self.result(
                author=self.create_author(
                    name=room.owner.nickname,
                    avatar_url=room.owner.avatar_thumb.url_list[-1],
                    id=room.owner.id_str,
                ),
                content=[
                    self.create_image(url=room.cover.url_list[-1]),
                    "直播中" if room.status == 2 else "未开播",
                ],
                url=f"https://live.douyin.com/{web_rid}",
                title=room.title,
                stats=self.create_stats(
                    view_count=format_num(room.room_view_stats.display_value),
                    like_count=format_num(room.like_count),
                ),
            )
        raise ParseException(f"获取直播间信息失败: {data}")

    # https://www.douyin.com/video/7521023890996514083
    # https://www.douyin.com/note/7469411074119322899
    # https://m.douyin.com/share/note/7591875747808560613
    @handle("douyin.com", r"douyin\.com/[a-z]+/(?P<aweme_id>\d+)")
    @handle(
        "iesdouyin.com",
        r"iesdouyin\.com/share/[a-z]+/(?P<aweme_id>\d+)",
    )
    @handle(
        "m.douyin.com",
        r"m\.douyin\.com/share/[a-z]+/(?P<aweme_id>\d+)",
    )
    # https://jingxuan.douyin.com/m/video/7574300896016862490?app=yumme&utm_source=copy_link
    @handle(
        "jingxuan.douyin.com",
        r"jingxuan\.douyin.com/m/[a-z]+/(?P<aweme_id>\d+)",
    )
    async def parse_work(self, searched: MatchWithParams):
        return await self.parse_aweme_id(searched["aweme_id"])

    async def parse_aweme_id(self, aweme_id: str):
        note = await self.httpx.get(
            "https://www.douyin.com/aweme/v1/web/aweme/detail/",
            params={
                "aweme_id": aweme_id,
                "aid": "6383",
            },
            headers={
                "Origin": "https://open.douyin.com",
                "Referer": "https://open.douyin.com/",
            },
        )
        if not note.is_success:
            raise ParseException(f"解析抖音内容失败, 可能是作品已删除: {note.text}")

        if pconfig.max_comments:
            try:
                await self.ensure_ttwid()
                resp = await self.httpx.get(
                    "https://www.douyin.com/aweme/v1/web/comment/list/",
                    params={
                        "device_platform": "webapp",
                        "aid": 6383,
                        "channel": "channel_pc_web",
                        "aweme_id": aweme_id,
                        "cursor": 0,
                        "count": pconfig.max_comments,
                        "msToken": "",
                        "X-Bogus": "",
                    },
                    cookies={"ttwid": self.ttwid},
                )
                comments = commentDecoder.decode(resp.content).comment_list
            except Exception:
                logger.exception(f"抖音获取评论失败, aweme_id: {aweme_id}")
                comments = []
        else:
            comments = []

        aweme = convert(note.json(), Response).aweme_detail
        content: list[ContentItem] = aweme.content
        return self.result(
            author=self.create_author(
                name=aweme.author.nickname,
                avatar_url=aweme.author.avatar_thumb.url_list[0],
                description=aweme.author.signature,
                id=aweme.author.uid,
                avatar_cache_key=f"douyin:{aweme.author.uid}",
                location=aweme.region,
                ext_headers={"Referer": "https://www.douyin.com/"},
            ),
            content=content,
            stats=self.create_stats(
                like_count=format_num(aweme.stats.digg_count),
                comment_count=format_num(aweme.stats.comment_count),
                share_count=format_num(aweme.stats.share_count),
                collect_count=format_num(aweme.stats.collect_count),
            ),
            timestamp=aweme.create_time,
            url=aweme.share_url.split("?")[0],
            comments=comments,
            embed_url=f"https://open.douyin.com/player/video?vid={aweme_id}&autoplay=1",
        )
