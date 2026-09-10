import asyncio
from dataclasses import dataclass
import re
from typing import ClassVar, TypeVar

from nonebot import get_driver, logger
from nonebot.permission import SUPERUSER
from nonebot.rule import Rule, to_me
from nonebot_plugin_alconna import (
    Alconna,
    Args,
    Extension,
    Match,
    UniMessage,
    on_alconna,
)
from nonebot_plugin_alconna.extension import cache_msg
from nonebot_plugin_alconna.uniseg import Receipt, get_message_id, reply_fetch
from nonebot_plugin_uninfo import Uninfo
from tarina import LRU

from ..config import pconfig
from ..download import DOWNLOADER
from ..helper import UniHelper
from ..parsers.base import BaseParser, ParseResult
from ..render import RENDERER
from ..utils.common import LimitedSizeDict
from .rule import Searched, SearchResult, _extract_text, on_keyword_regex

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
# 缓存结果
_RESULT_CACHE = LimitedSizeDict[str, ParseResult](max_size=50)
_PARSE_TASKS: dict[str, asyncio.Task[ParseResult]] = {}
_BV_PATTERN = re.compile(r"BV[0-9A-Za-z]{10}")
_URL_PATTERN = re.compile(r"https?://[^\s]+", re.IGNORECASE)


def _ensure_parser_instance(parser_cls: type[BaseParser]) -> BaseParser:
    """按需实例化 parser，并缓存结果"""
    parser = _PARSER_INSTANCES.get(parser_cls)
    if parser is not None:
        return parser

    parser = parser_cls()
    _PARSER_INSTANCES[parser_cls] = parser
    _ALL_PARSERS.append(parser)
    return parser


def get_parser(keyword: str) -> BaseParser:
    """根据注册的关键字获取解析器实例（惰性加载）"""
    parser_cls = _KEYWORD_CLASS_MAP.get(keyword)
    if parser_cls is None:
        raise KeyError(f"未找到关键字 {keyword!r} 对应的 parser")
    return _ensure_parser_instance(parser_cls)


def get_parser_by_type(parser_type: type[T]) -> T:
    """根据解析器类型获取解析器实例（惰性加载）"""
    # 已经有实例的情况下，直接从实例表中找
    for cls, inst in _PARSER_INSTANCES.items():
        if issubclass(cls, parser_type):
            return inst  # type: ignore[return-value]

    # 否则在启用的解析器类列表中找
    for cls in _ENABLED_PARSER_CLASSES:
        if issubclass(cls, parser_type):
            return _ensure_parser_instance(cls)  # type: ignore[return-value]

    raise ValueError(f"未找到类型为 {parser_type.__name__} 的 parser 实例")


def clear_result_cache():
    _RESULT_CACHE.clear()


driver = get_driver()


@driver.on_startup
def register_parser_matcher() -> None:
    """在启动时注册各平台解析器及其匹配规则（惰性实例化）"""
    from ..parsers import load_enabled_parsers

    global _ENABLED_PARSER_CLASSES, _KEYWORD_CLASS_MAP

    _ENABLED_PARSER_CLASSES = load_enabled_parsers()

    enabled_platforms: list[str] = []
    keyword_class_map: dict[str, type[BaseParser]] = {}
    for parser_cls in _ENABLED_PARSER_CLASSES:
        enabled_platforms.append(parser_cls.platform.display_name)
        for keyword, _, _ in parser_cls._key_patterns:
            keyword_class_map[keyword] = parser_cls

    _KEYWORD_CLASS_MAP = keyword_class_map

    logger.info(f"启用平台: {', '.join(sorted(enabled_platforms))}")

    patterns = [
        pattern for cls_ in _ENABLED_PARSER_CLASSES for pattern in cls_._key_patterns
    ]
    matcher = on_keyword_regex(*patterns)
    matcher.append_handler(parser_handler)


@driver.on_shutdown
async def close_http_clients() -> None:
    await asyncio.gather(
        *(parser.aclose() for parser in _ALL_PARSERS),
        DOWNLOADER.aclose(),
    )


async def _get_or_parse_result(sr: SearchResult) -> ParseResult:
    cache_key = sr.cache_key
    if result := _RESULT_CACHE.get(cache_key):
        logger.debug(f"命中缓存: {cache_key}, 结果: {result!r}")
        return result

    task = _PARSE_TASKS.get(cache_key)
    if task is None:

        async def parse_and_cache() -> ParseResult:
            parser = get_parser(sr.keyword)
            parsed = await parser.parse(sr.keyword, sr.searched)
            logger.debug(f"解析结果: {parsed!r}")
            _RESULT_CACHE[cache_key] = parsed
            return parsed

        task = asyncio.create_task(parse_and_cache())
        _PARSE_TASKS[cache_key] = task

        def discard_finished(finished: asyncio.Task[ParseResult]) -> None:
            if _PARSE_TASKS.get(cache_key) is finished:
                _PARSE_TASKS.pop(cache_key, None)

        task.add_done_callback(discard_finished)

    return await asyncio.shield(task)


@UniHelper.with_reaction
async def parser_handler(
    session: Uninfo,
    sr: SearchResult = Searched(),
):
    """统一的解析处理器"""
    result = await _get_or_parse_result(sr)

    summary_msg = await RENDERER.render_messages(result)
    await summary_msg.send()
    if pconfig.lazy_download:
        if pconfig.lazy_download_tip:
            download_cmd = ", ".join(pconfig.download_command)
            await UniMessage(
                f"请在{LazyManager.TIMEOUT_SECONDS}秒内发送以下命令之一来获取媒体资源: "
                f"\n{download_cmd}"
            ).send()
        await LazyManager.add(LazyManager.session_key(session), result)
    else:
        async for content_msg in RENDERER.send_content(result):
            await content_msg.send()


@driver.on_startup
async def register_bili_matcher():
    from ..parsers.bilibili import BilibiliParser

    bilip: BilibiliParser | None
    try:
        bilip = get_parser_by_type(BilibiliParser)
    except ValueError:
        bilip = None

    if bilip is not None:

        @on_alconna(
            Alconna(
                "bm",
                Args["bv", r"re:BV[A-Za-z0-9]{10}"]["page?", int, 1],
            ),
            priority=3,
            block=True,
            extensions=[BvReplyMergeExtension()],
        ).handle()
        @UniHelper.with_reaction
        async def _(bv: Match[str], page: Match[int]):
            bvid = bv.result

            page_idx = page.result - 1 if page.result > 0 else 0
            _, audio_stream = await bilip.get_download_streams(
                bvid=bvid, page_index=page_idx
            )
            if audio_stream is None:
                await UniMessage("未找到可下载的音频").finish()

            audio_path = await DOWNLOADER.download_audio(
                url=audio_stream.url,
                fallback_urls=audio_stream.backup_url,
                retry_http_statuses=bilip.BILI_RETRYABLE_HTTP_STATUSES,
                cache_key=f"bilibili:{bvid}:{page_idx + 1}",
                cache_variant="source",
                ext_headers=bilip.headers,
                convert_to_mp3=True,
            )
            if pconfig.need_upload_audio:
                await UniMessage(await UniHelper.file_seg(audio_path)).send()
            else:
                await UniMessage(await UniHelper.record_seg(audio_path)).send()

        @on_alconna(
            Alconna("blogin"), block=True, permission=SUPERUSER, rule=to_me()
        ).handle()
        async def _():
            last_receipt: Receipt | None = None
            qrcode = await bilip.login_with_qrcode()
            last_receipt = await UniMessage(await UniHelper.img_seg(qrcode)).send()
            async for msg in bilip.check_qr_state():
                if last_receipt is not None:
                    try:
                        await last_receipt.recall()
                    except Exception:
                        logger.exception("尝试撤回上一条消息失败")
                last_receipt = await UniMessage(msg).send()


if pconfig.lazy_download:

    async def has_lazy(session: Uninfo) -> bool:
        return await LazyManager.has(LazyManager.session_key(session))

    lazy_matcher = on_alconna(
        Alconna(pconfig.download_command[0]),
        block=True,
        aliases=set(pconfig.download_command[1:]),
        rule=Rule(has_lazy),
    )

    @lazy_matcher.handle()
    @UniHelper.with_reaction
    async def _(session: Uninfo):
        """懒下载命令：发送上次解析结果中的媒体内容"""
        session_key = LazyManager.session_key(session)
        result = await LazyManager.claim(session_key)
        if result is None:
            await UniMessage("资源正在下载或发送中，请勿重复请求").send()
            return

        try:
            async for message in RENDERER.send_content(result):
                await message.send()
        finally:
            await LazyManager.release(session_key)


class LazyManager:
    """管理每个用户的懒下载会话，支持超时自动清理"""

    TIMEOUT_SECONDS: ClassVar[int] = pconfig.lazy_download_timeout

    @dataclass
    class Session:
        result: ParseResult

    SessionKey = tuple[str, str, str, str]
    SESSIONS: ClassVar[dict[SessionKey, "LazyManager.Session"]] = {}
    ACTIVE_USERS: ClassVar[set[SessionKey]] = set()
    LOCK: ClassVar[asyncio.Lock] = asyncio.Lock()
    TIMEOUT_TASKS: ClassVar[set[asyncio.Task[None]]] = set()

    @classmethod
    def session_key(cls, session: Uninfo) -> SessionKey:
        return (
            str(session.scope),
            session.self_id,
            session.scene_path,
            session.user.id,
        )

    @classmethod
    async def add(cls, key: SessionKey, parse_result: ParseResult) -> None:
        """为用户创建/刷新懒下载会话"""
        session = cls.Session(result=parse_result)
        async with cls.LOCK:
            cls.SESSIONS[key] = session
            task = asyncio.create_task(cls._timeout_handler(key, session))
            cls.TIMEOUT_TASKS.add(task)
            task.add_done_callback(cls.TIMEOUT_TASKS.discard)

    @classmethod
    async def claim(cls, key: SessionKey) -> ParseResult | None:
        """原子领取待下载结果；同一用户已有任务运行时返回 None"""
        async with cls.LOCK:
            if key in cls.ACTIVE_USERS:
                return None

            session = cls.SESSIONS.pop(key, None)
            if session is None:
                return None

            cls.ACTIVE_USERS.add(key)
            return session.result

    @classmethod
    async def has(cls, key: SessionKey) -> bool:
        async with cls.LOCK:
            return key in cls.SESSIONS or key in cls.ACTIVE_USERS

    @classmethod
    async def release(cls, key: SessionKey) -> None:
        """标记该用户的下载发送流程结束"""
        async with cls.LOCK:
            cls.ACTIVE_USERS.discard(key)

    @classmethod
    async def _timeout_handler(cls, key: SessionKey, session: Session) -> None:
        """会话超时自动清理"""
        await asyncio.sleep(cls.TIMEOUT_SECONDS)
        async with cls.LOCK:
            if cls.SESSIONS.get(key) is session:
                cls.SESSIONS.pop(key)


class BvReplyMergeExtension(Extension):
    """
    将消息事件中的回复内容合并到当前消息中，并在解析前尝试从文本/短链接中抽取 BV 参数

    行为：
    - message_provider: 把「当前消息 + 回复消息」合成一个 UniMessage
    - before_parse: 若命令参数中未显式提供 BV，则尝试
        1. 从合成文本中直接匹配 BV；
        2. 若无 BV，则从文本中取第一个 URL并展开，随后从最终 URL 中匹配 BV
       解析成功后，将 BV 字符串填入 argv 中对应位置
    """

    cache: "LRU[str, UniMessage]" = LRU(20)

    @property
    def priority(self) -> int:
        return 10

    @property
    def id(self) -> str:
        return "nonebot_plugin_parser_lite:BvReplyMergeExtension"

    async def message_provider(self, event, state, bot, use_origin: bool = False):
        if event.get_type() != "message":
            return None
        try:
            msg = event.get_message()
        except (NotImplementedError, ValueError):
            return None

        msg_id = get_message_id(event, bot)
        if cache_msg and msg_id in self.cache:
            return self.cache[msg_id]
        uni_msg = UniMessage.of(msg, bot=bot)
        src_text = uni_msg.extract_plain_text() or ""
        if _BV_PATTERN.search(src_text):
            self.cache[msg_id] = uni_msg
            return uni_msg
        reply = await reply_fetch(event, bot)
        if reply and reply.msg:
            reply_msg = reply.msg
            if isinstance(reply_msg, str):
                reply_msg = msg.__class__(reply_msg)
            uni_msg_reply = UniMessage.of(reply_msg, bot=bot)
            text = _extract_text(uni_msg_reply) or ""

            if m := _BV_PATTERN.search(text):
                uni_msg.extend(" ")
                uni_msg.extend(m.group(0))
            elif url_match := _URL_PATTERN.search(text):
                url = url_match.group(0)
                try:
                    final_url = await BaseParser.get_final_url(url)
                    if m2 := _BV_PATTERN.search(final_url):
                        uni_msg.extend(" ")
                        uni_msg.extend(m2.group(0))
                except Exception as e:
                    logger.warning(
                        f"BvReplyMergeExtension: 展开短链接失败 url={url!r}: {e}"
                    )

        self.cache[msg_id] = uni_msg
        return uni_msg
