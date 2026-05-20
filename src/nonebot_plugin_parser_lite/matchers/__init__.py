import asyncio
from dataclasses import dataclass
from itertools import chain
from typing import ClassVar, TypeVar

from nonebot import get_driver, logger
from nonebot.permission import SUPERUSER
from nonebot.rule import Rule, to_me
from nonebot_plugin_alconna import Alconna, Args, Match, on_alconna
from nonebot_plugin_uninfo import Uninfo

from ..config import pconfig
from ..download import DOWNLOADER
from ..helper import UniHelper, UniMessage
from ..parsers import BaseParser, BilibiliParser, ParseResult
from ..render import RENDERER
from ..utils.common import LimitedSizeDict
from .rule import Searched, SearchResult, on_keyword_regex


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
    def get(cls, user_id: str) -> ParseResult:
        """获取用户当前的懒下载解析结果（调用方保证一定存在）。"""
        session = cls.SESSIONS.get(user_id)
        assert session is not None, "LazyManager.get: session should exist"
        return session.result

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

        # 会话已被手动清理
        if user_id not in cls.SESSIONS:
            return

        cls.remove(user_id, current_task=self_task)


def _get_enabled_parser_classes() -> list[type[BaseParser]]:
    disabled_platforms = set(pconfig.disabled_platforms)
    all_subclass = BaseParser.get_all_subclass()
    return [
        _cls for _cls in all_subclass if _cls.platform.name not in disabled_platforms
    ]


# 关键词 / 类型 -> Parser 映射
T = TypeVar("T", bound=BaseParser)
# 已启用的解析器类（启动时确定，不含被禁用的平台）
_ENABLED_PARSER_CLASSES: list[type[BaseParser]] = []
# 解析器实例注册表：class -> instance（惰性创建）
_PARSER_INSTANCES: dict[type[BaseParser], BaseParser] = {}
# 关键字 -> 解析器类（由 _key_patterns 派生）
_KEYWORD_CLASS_MAP: dict[str, type[BaseParser]] = {}
# 已实例化的 parser（用于 on_shutdown 统一关闭 http 客户端）
_ALL_PARSERS: list[BaseParser] = []


def _ensure_parser_instance(parser_cls: type[BaseParser]) -> BaseParser:
    """按需实例化 parser，并缓存结果。"""
    parser = _PARSER_INSTANCES.get(parser_cls)
    if parser is not None:
        return parser

    parser = parser_cls()
    _PARSER_INSTANCES[parser_cls] = parser
    _ALL_PARSERS.append(parser)
    return parser


def get_parser(keyword: str) -> BaseParser:
    """根据注册的关键字获取解析器实例（惰性加载）。"""
    parser_cls = _KEYWORD_CLASS_MAP.get(keyword)
    if parser_cls is None:
        raise KeyError(f"未找到关键字 {keyword!r} 对应的 parser")
    return _ensure_parser_instance(parser_cls)


def get_parser_by_type(parser_type: type[T]) -> T:
    """根据解析器类型获取解析器实例（惰性加载）。"""
    # 已经有实例的情况下，直接从实例表中找
    for cls, inst in _PARSER_INSTANCES.items():
        if issubclass(cls, parser_type):
            return inst  # type: ignore[return-value]

    # 否则在启用的解析器类列表中找
    for cls in _ENABLED_PARSER_CLASSES:
        if issubclass(cls, parser_type):
            return _ensure_parser_instance(cls)  # type: ignore[return-value]

    raise ValueError(f"未找到类型为 {parser_type.__name__} 的 parser 实例")


driver = get_driver()


@driver.on_startup
def register_parser_matcher() -> None:
    """在启动时注册各平台解析器及其匹配规则（惰性实例化）。"""
    global _ENABLED_PARSER_CLASSES, _KEYWORD_CLASS_MAP

    enabled_classes = _get_enabled_parser_classes()
    _ENABLED_PARSER_CLASSES = enabled_classes

    enabled_platforms: list[str] = []
    keyword_class_map: dict[str, type[BaseParser]] = {}

    for parser_cls in enabled_classes:
        enabled_platforms.append(parser_cls.platform.display_name)
        for keyword, _ in parser_cls._key_patterns:
            keyword_class_map[keyword] = parser_cls

    _KEYWORD_CLASS_MAP = keyword_class_map

    logger.info(f"启用平台: {', '.join(sorted(enabled_platforms))}")

    patterns = [pattern for cls_ in enabled_classes for pattern in cls_._key_patterns]
    matcher = on_keyword_regex(*patterns)
    matcher.append_handler(parser_handler)


@driver.on_shutdown
async def close_httpx() -> None:
    if not _ALL_PARSERS:
        return

    await asyncio.gather(*(parser.aclose() for parser in _ALL_PARSERS))


# 缓存结果
_RESULT_CACHE = LimitedSizeDict[str, ParseResult](max_size=50)


def clear_result_cache():
    _RESULT_CACHE.clear()


async def _send_parse_result(session: Uninfo, result: ParseResult) -> None:
    """根据配置发送解析结果：先发总结图，再根据懒下载配置决定是否发送媒体。"""
    summary_msg = await RENDERER.render_messages(result)
    await summary_msg.send()
    # 全文本内容，无需再发送媒体
    if all(
        isinstance(c, str)
        for c in chain(result.content, result.repost.content if result.repost else [])
    ):
        return
    if pconfig.lazy_download:
        download_cmd = ", ".join(pconfig.download_command)
        await UniMessage(
            f"请在{LazyManager.TIMEOUT_SECONDS}秒内发送以下命令之一来获取媒体资源: "
            f"\n{download_cmd}"
        ).send()
        LazyManager.add(session.user.id, result)
        return

    async for content_msg in RENDERER.send_content(result):
        await content_msg.send()


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
        logger.debug(f"解析结果: {result!r}")
        _RESULT_CACHE[cache_key] = result
    else:
        logger.debug(f"命中缓存: {cache_key}, 结果: {result!r}")

    # 2. 渲染并发送
    await _send_parse_result(session, result)


@driver.on_startup
async def register_bili_matcher():

    bilip: BilibiliParser | None
    try:
        bilip = get_parser_by_type(BilibiliParser)
    except ValueError:
        bilip = None

    if bilip is not None:

        @on_alconna(
            Alconna("bm", Args["bv", r"re:(BV[A-Za-z0-9]{10})"]["page?", int, 0]),
            priority=3,
            block=True,
        ).handle()
        @UniHelper.with_reaction
        async def _(bv: Match[str], page: Match[int]):
            bvid = bv.result
            page_idx = page.result - 1 if page.result > 0 else 0
            _, audio_url = await bilip.extract_download_urls(
                bvid=bvid, page_index=page_idx
            )
            if not audio_url:
                await UniMessage("未找到可下载的音频").finish()

            audio_path = await DOWNLOADER.download_audio(
                url=audio_url,
                audio_name=f"{bvid}-{page_idx}.m4s",
                ext_headers=bilip.headers,
            )

            if pconfig.need_upload_audio:
                await UniMessage(await UniHelper.file_seg(audio_path)).send()
            else:
                await UniMessage(await UniHelper.record_seg(audio_path)).send()

        @on_alconna(
            Alconna("blogin"), block=True, permission=SUPERUSER, rule=to_me()
        ).handle()
        async def _():
            qrcode = await bilip.login_with_qrcode()
            await UniMessage(await UniHelper.img_seg(qrcode)).send()
            async for msg in bilip.check_qr_state():
                await UniMessage(msg).send()


if pconfig.lazy_download:

    async def has_lazy(session: Uninfo) -> bool:
        return LazyManager.has(session.user.id)

    lazy_matcher = on_alconna(
        Alconna(pconfig.download_command[0]),
        block=True,
        aliases=set(pconfig.download_command[1:]),
        rule=Rule(has_lazy),
    )

    @lazy_matcher.handle()
    @UniHelper.with_reaction
    async def _(session: Uninfo):
        """懒下载命令：发送上次解析结果中的媒体内容。"""
        user_id = session.user.id
        result = LazyManager.get(user_id)
        try:
            async for message in RENDERER.send_content(result):
                await message.send()
        finally:
            LazyManager.remove(user_id)
