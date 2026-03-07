import asyncio
from dataclasses import dataclass
import re
from typing import ClassVar, TypeVar

from nonebot import get_driver, logger
from nonebot_plugin_alconna import Alconna, Args, Match, on_alconna
from nonebot_plugin_uninfo import Uninfo
from nonebot.adapters import Event

from ..config import pconfig
from ..download import DOWNLOADER
from ..helper import UniHelper, UniMessage
from ..parsers import BaseParser, BilibiliParser, ParseResult
from ..renders import RENDERER
from ..utils.browser import BROWSER
from ..utils.common import LimitedSizeDict
from .rule import SUPER_PRIVATE, Searched, SearchResult, on_keyword_regex


class LazyManager:
    """管理每个用户的懒下载会话，支持超时自动清理。"""

    TIMEOUT_SECONDS: ClassVar[int] = pconfig.lazy_download_timeout

    @dataclass
    class Session:
        result: ParseResult
        task: asyncio.Task[None]

    # user_id -> Session
    SESSIONS: ClassVar[dict[str, "LazyManager.Session"]] = {}

    @classmethod
    def add(cls, user_id: str, parse_result: ParseResult) -> None:
        """为用户创建/刷新懒下载会话。"""
        # 取消之前的会话
        cls.remove(user_id)

        task: asyncio.Task[None] = asyncio.create_task(cls._timeout_handler(user_id))
        session: LazyManager.Session = cls.Session(
            result=parse_result,
            task=task,
        )
        cls.SESSIONS[user_id] = session

    @classmethod
    def get(cls, user_id: str) -> ParseResult | None:
        """获取用户当前的懒下载解析结果。"""
        session = cls.SESSIONS.get(user_id)
        return session.result if session else None

    @classmethod
    def has(cls, user_id: str) -> bool:
        return user_id in cls.SESSIONS

    @classmethod
    def remove(cls, user_id: str, *, current_task: asyncio.Task | None = None) -> None:
        """删除用户的懒下载会话并取消超时任务。

        current_task 用于避免在超时回调中自我取消，减少 CancelledError 噪音。
        """
        session = cls.SESSIONS.pop(user_id, None)
        if session is None:
            return

        # 只有在不是当前正在运行的任务时才取消
        if session.task is not current_task and not session.task.done():
            session.task.cancel()

    @classmethod
    async def _timeout_handler(cls, user_id: str) -> None:
        """会话超时自动清理。"""
        self_task = asyncio.current_task()

        await asyncio.sleep(cls.TIMEOUT_SECONDS)

        # 理论上 current_task 不会为 None，这里仅做防御性处理
        if user_id not in cls.SESSIONS:
            return

        if self_task is None:
            cls.remove(user_id)
        else:
            cls.remove(user_id, current_task=self_task)


def _get_enabled_parser_classes() -> list[type[BaseParser]]:
    disabled_platforms = set(pconfig.disabled_platforms)
    all_subclass = BaseParser.get_all_subclass()
    return [
        _cls for _cls in all_subclass if _cls.platform.name not in disabled_platforms
    ]


# 关键词 -> Parser 映射
KEYWORD_PARSER_MAP: dict[str, BaseParser] = {}
T = TypeVar("T", bound=BaseParser)


def get_parser(keyword: str) -> BaseParser:
    """根据注册的关键字获取对应的解析器实例。"""
    parser = KEYWORD_PARSER_MAP.get(keyword)
    if parser is None:
        raise KeyError(f"未找到关键字 {keyword!r} 对应的 parser")
    return parser


def get_parser_by_type(parser_type: type[T]) -> T:
    """根据解析器类型获取已注册的解析器实例。"""
    for parser in KEYWORD_PARSER_MAP.values():
        if isinstance(parser, parser_type):
            return parser
    raise ValueError(f"未找到类型为 {parser_type.__name__} 的 parser 实例")


driver = get_driver()


@driver.on_startup
def register_parser_matcher() -> None:
    """在启动时注册各平台解析器及其匹配规则。"""
    enabled_classes = _get_enabled_parser_classes()

    enabled_platforms: list[str] = []
    for parser_cls in enabled_classes:
        parser = parser_cls()
        enabled_platforms.append(parser.platform.display_name)
        for keyword, _ in parser_cls._key_patterns:
            KEYWORD_PARSER_MAP[keyword] = parser

    logger.info(f"启用平台: {', '.join(sorted(enabled_platforms))}")

    patterns = [pattern for cls_ in enabled_classes for pattern in cls_._key_patterns]
    matcher = on_keyword_regex(*patterns)
    matcher.append_handler(parser_handler)


@driver.on_shutdown
def close_browser():
    BROWSER.quit()


# 缓存结果
_RESULT_CACHE = LimitedSizeDict[str, ParseResult](max_size=50)


def clear_result_cache():
    _RESULT_CACHE.clear()


@UniHelper.with_reaction
async def parser_handler(
    session: Uninfo,
    sr: SearchResult = Searched(),
):
    """统一的解析处理器"""
    cache_key = sr.searched[0]

    # 1. 从缓存获取或重新解析
    result = _RESULT_CACHE.get(cache_key)
    if result is None:
        parser = get_parser(sr.keyword)
        result = await parser.parse(sr.keyword, sr.searched)
        logger.debug("解析结果: %r", result)
        _RESULT_CACHE[cache_key] = result
    else:
        logger.debug("命中缓存: %s, 结果: %r", cache_key, result)

    # 2. 渲染并发送
    try:
        message = await RENDERER.render_messages(result)
        if pconfig.lazy_download:
            # 懒下载模式：只发送渲染结果 + 下载提示，由 lazy_matcher 负责后续内容发送
            download_cmd = ", ".join(pconfig.download_command)
            tips = UniMessage(
                f"请在{LazyManager.TIMEOUT_SECONDS}秒内发送以下命令之一来下载媒体资源: \n{download_cmd}"
            )
            LazyManager.add(session.user.id, result)

            # 当前 RENDERER.render_messages 返回的是单条消息
            await (message + tips).send()
        else:
            # 非懒下载模式：先发送渲染内容，再发送下载内容
            await message.send()

            async for content_msg in RENDERER.send_content(result):
                await content_msg.send()
    except Exception as e:
        # 渲染或发送失败时的兜底日志
        logger.error("渲染或发送失败: %s", e, exc_info=True)
        # 如需可在此补发纯文本提示：
        # await UniMessage(f"解析成功，但渲染/发送失败: {e!s}").send()


@on_alconna(Alconna("bm", Args["bv?", str, ""]), priority=3, block=True).handle()
@UniHelper.with_reaction
async def _(bv: Match[str]):
    text = bv.result
    matched = re.search(r"(BV[A-Za-z0-9]{10})(\s\d{1,3})?", text)
    if not matched:
        await UniMessage("请发送正确的 BV 号").finish()

    bvid, page_num = matched[1], matched[2]
    page_idx = int(page_num) if page_num else 0

    parser = get_parser_by_type(BilibiliParser)

    _, audio_url = await parser.extract_download_urls(bvid=bvid, page_index=page_idx)
    if not audio_url:
        await UniMessage("未找到可下载的音频").finish()

    audio_path = await DOWNLOADER.download_audio(
        audio_url, audio_name=f"{bvid}-{page_idx}.mp3", ext_headers=parser.headers
    )
    await UniMessage(UniHelper.record_seg(audio_path)).send()

    if pconfig.need_upload_audio:
        await UniMessage(UniHelper.file_seg(audio_path)).send()


@on_alconna(Alconna("blogin"), block=True, permission=SUPER_PRIVATE).handle()
async def _():
    parser = get_parser_by_type(BilibiliParser)
    qrcode = await parser.login_with_qrcode()
    await UniMessage(UniHelper.img_seg(raw=qrcode)).send()
    async for msg in parser.check_qr_state():
        await UniMessage(msg).send()


if pconfig.lazy_download:

    def has_lazy(session: Uninfo) -> bool:
        return LazyManager.has(session.user.id)

    lazy_matcher = on_alconna(
        Alconna(pconfig.download_command[0]),
        block=True,
        aliases=set(pconfig.download_command[1:]),
        rule=has_lazy,
    )

    @lazy_matcher.handle()
    async def _(event: Event, session: Uninfo):
        try:
            result = LazyManager.get(session.user.id)
            if not result:
                return
            await UniHelper.message_reaction(event, "resolving")
            async for message in RENDERER.send_content(result):
                await message.send()
            await UniHelper.message_reaction(event, "done")
            LazyManager.remove(session.user.id)
        except Exception:
            await UniHelper.message_reaction(event, "fail")
            LazyManager.remove(session.user.id)
