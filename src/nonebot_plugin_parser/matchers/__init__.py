import re
from typing import TypeVar
from pathlib import Path

from nonebot import logger, get_driver
from nonebot_plugin_alconna import Args, Match, Alconna, on_alconna
from nonebot.adapters.onebot.v11 import NoticeEvent

from .rule import SUPER_PRIVATE, Searched, SearchResult, on_keyword_regex
from ..utils import LimitedSizeDict
from ..config import pconfig
from ..helper import UniHelper, UniMessage
from ..parsers import BaseParser, ParseResult, BilibiliParser
from ..renders import RENDERER
from ..download import DOWNLOADER
from ..parsers.data import AudioContent, VideoContent
from nonebot import on_notice
from nonebot_plugin_alconna.uniseg import message_reaction


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
    return KEYWORD_PARSER_MAP[keyword]


def get_parser_by_type(parser_type: type[T]) -> T:
    for parser in KEYWORD_PARSER_MAP.values():
        if isinstance(parser, parser_type):
            return parser
    raise ValueError(f"未找到类型为 {parser_type} 的 parser 实例")


@get_driver().on_startup
def register_parser_matcher():
    enabled_classes = _get_enabled_parser_classes()

    enabled_platforms = []
    for _cls in enabled_classes:
        parser = _cls()
        enabled_platforms.append(parser.platform.display_name)
        for keyword, _ in _cls._key_patterns:
            KEYWORD_PARSER_MAP[keyword] = parser
    logger.info(f"启用平台: {', '.join(sorted(enabled_platforms))}")

    patterns = [p for _cls in enabled_classes for p in _cls._key_patterns]
    matcher = on_keyword_regex(*patterns)
    matcher.append_handler(parser_handler)


# 缓存结果
_RESULT_CACHE = LimitedSizeDict[str, ParseResult](max_size=50)
# 消息ID与解析结果的关联缓存，用于多用户场景
_MSG_ID_RESULT_MAP = LimitedSizeDict[str, ParseResult](max_size=100)


def clear_result_cache():
    _RESULT_CACHE.clear()
    _MSG_ID_RESULT_MAP.clear()


@UniHelper.with_reaction
async def parser_handler(
    sr: SearchResult = Searched(),
):
    """统一的解析处理器"""
    # 1. 获取缓存结果
    cache_key = sr.searched.group(0)
    result = _RESULT_CACHE.get(cache_key)

    if result is None:
        # 2. 获取对应平台 parser
        parser = get_parser(sr.keyword)
        result = await parser.parse(sr.keyword, sr.searched)
        logger.debug(f"解析结果: {result}")
    else:
        logger.debug(f"命中缓存: {cache_key}, 结果: {result}")

    # 3. 渲染内容消息并发送，保存消息ID
    try:
        async for message in RENDERER.render_messages(result):
            msg_sent = await message.send()
            # 保存消息ID与解析结果的关联
            if msg_sent:
                msg_id = None
                try:
                    # 处理Receipt对象的msg_ids属性
                    receipt_msg_ids = msg_sent.msg_ids
                    logger.debug(f"Receipt.msg_ids: {receipt_msg_ids}")
                    if receipt_msg_ids:
                        for msg_id_info in receipt_msg_ids:
                            if (
                                isinstance(msg_id_info, dict)
                                and "message_id" in msg_id_info
                            ):
                                msg_id = str(msg_id_info["message_id"])
                                logger.debug(
                                    f"通过Receipt.msg_ids[0]['message_id']获取到消息ID: {msg_id}"
                                )
                                break
                    if msg_id:
                        _MSG_ID_RESULT_MAP[msg_id] = result
                        logger.debug(
                            f"保存消息ID与解析结果的关联: msg_id={msg_id}, url={cache_key}"
                        )
                        logger.debug(
                            f"当前_MSG_ID_RESULT_MAP大小: {len(_MSG_ID_RESULT_MAP)}"
                        )
                    else:
                        logger.debug("未获取到消息ID")
                except (NotImplementedError, TypeError, AttributeError) as e:
                    # 某些适配器可能不支持获取消息ID，忽略此错误
                    logger.debug(f"获取消息ID失败: {e}")
    except Exception as e:
        # 渲染失败时，尝试直接发送解析结果
        logger.error(f"渲染失败: {e}")
        # from ..helper import UniMessage
        # await UniMessage(f"解析成功，但渲染失败: {e!s}").send()

    # 4. 缓存解析结果
    _RESULT_CACHE[cache_key] = result


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

    if pconfig.need_upload:
        await UniMessage(UniHelper.file_seg(audio_path)).send()


@on_alconna(Alconna("blogin"), block=True, permission=SUPER_PRIVATE).handle()
async def _():
    parser = get_parser_by_type(BilibiliParser)
    qrcode = await parser.login_with_qrcode()
    await UniMessage(UniHelper.img_seg(raw=qrcode)).send()
    async for msg in parser.check_qr_state():
        await UniMessage(msg).send()


on_notice_ = on_notice(priority=1, block=False)


@on_notice_.handle()
async def handle_group_msg_emoji_like(event: NoticeEvent):
    from ..helper import UniHelper, UniMessage

    # 检查是否是group_msg_emoji_like事件
    is_group_emoji_like = False
    emoji_id = 0
    liked_message_id = 0
    is_add = True  # 默认值，避免Pylance警告

    # 处理不同形式的事件对象（字典或对象）
    if isinstance(event, dict):
        # 字典形式的事件
        if event.get("notice_type") == "group_msg_emoji_like":
            is_group_emoji_like = True
            emoji_id = event["likes"][0]["emoji_id"]
            liked_message_id = event["message_id"]
            is_add = event.get("is_add", True)
    elif hasattr(event, "notice_type") and event.notice_type == "group_msg_emoji_like":
        is_group_emoji_like = True
        if likes := getattr(event, "likes", None):
            emoji_id = (
                likes[0].get("emoji_id", "")
                if isinstance(likes[0], dict)
                else likes[0].emoji_id
            )
        if msg_id := getattr(event, "message_id", None):
            liked_message_id = msg_id
        is_add = getattr(event, "is_add", True)
    emoji_id = int(emoji_id)
    liked_message_id = int(liked_message_id)
    logger.debug(
        f"emoji_id:{emoji_id} | liked_message_id:{liked_message_id} | is_add:{is_add}"
    )
    # 检查是否是group_msg_emoji_like事件且表情ID有效
    if not is_group_emoji_like or not emoji_id:
        return

    # 只有当is_add为True时才处理点赞事件，忽略取消点赞事件
    if not is_add:
        return

    # 检查表情ID是否在配置列表中
    if emoji_id not in pconfig.delay_send_emoji_ids:
        return

    # 发送"听到需求"的表情（使用用户指定的表情ID 282）
    try:
        # 只有当liked_message_id有效时，才发送表情反馈
        if liked_message_id:
            await message_reaction("282", message_id=str(liked_message_id))
    except Exception as e:
        logger.warning(f"Failed to send resolving reaction: {e}")

    try:
        logger.debug(
            f"收到表情点赞事件: emoji_id={emoji_id}, message_id={liked_message_id}, event={event}"
        )
        logger.debug(f"当前_MSG_ID_RESULT_MAP: {list(_MSG_ID_RESULT_MAP.keys())}")

        # 根据消息ID获取对应的解析结果
        result = _MSG_ID_RESULT_MAP.get(str(liked_message_id))
        if not result:
            # 发送"失败"的表情（使用用户指定的表情ID 10060）
            logger.debug(f"未找到消息ID {liked_message_id} 对应的解析结果")
            try:
                if liked_message_id:
                    await message_reaction("10060", message_id=str(liked_message_id))
            except Exception as e:
                logger.warning(f"Failed to send fail reaction: {e}")
            return

        # 尝试获取媒体内容，无论media_contents是否为空
        sent = False
        remaining_media = []
        current_sent = False  # 记录当前媒体是否发送成功

        # 检查result的contents属性，看看是否有媒体内容
        if not result.media_contents:
            # 如果media_contents为空，尝试从result.contents中获取媒体内容
            logger.debug("尝试从result.contents中获取媒体内容")
            for content in result.content:
                if isinstance(content, VideoContent):
                    result.media_contents.append(content)
                    logger.debug("添加VideoContent到media_contents")
                elif isinstance(content, AudioContent):
                    result.media_contents.append(content)
                    logger.debug("添加AudioContent到media_contents")

        # 如果仍然没有媒体内容，返回但不移除消息ID
        if not result.media_contents:
            logger.debug(
                f"消息ID {liked_message_id} 对应的解析结果中没有可发送的媒体内容"
            )
            # 发送"失败"的表情（使用用户指定的表情ID 10060）
            try:
                if liked_message_id:
                    await message_reaction("10060", message_id=str(liked_message_id))
            except Exception as e:
                logger.warning(f"Failed to send fail reaction: {e}")
            # 不删除消息ID，等待媒体下载完成
            return

        # 发送延迟的媒体内容
        for media_item in result.media_contents:
            try:
                path = None
                is_media_ready = False

                # 检查媒体是否已经准备好发送
                if isinstance(media_item, Path):
                    # 已经是 Path 类型，直接使用
                    path = media_item
                    is_media_ready = True
                    logger.debug(f"发送已下载的延迟媒体: {path}")
                else:
                    # 是 MediaContent 类型，使用get_path()方法统一处理下载状态
                    try:
                        path = await media_item.get_path()
                        is_media_ready = True
                        logger.debug(f"获取延迟媒体路径成功: {path}")
                    except Exception as e:
                        logger.error(f"获取延迟媒体路径失败: {e}")
                        # 添加到剩余媒体列表，以便后续重试
                        remaining_media.append(media_item)
                        continue

                if is_media_ready and path:
                    if isinstance(media_item, VideoContent):
                        try:
                            # 尝试直接发送视频
                            await UniMessage(UniHelper.video_seg(path)).send()
                            # 如果需要上传视频文件，且没有因为大小问题发送失败
                            if pconfig.need_upload_video:
                                await UniMessage(UniHelper.file_seg(path)).send()
                            current_sent = True
                        except Exception as e:
                            # 直接发送失败，可能是因为文件太大，尝试使用群文件发送
                            logger.debug(f"直接发送视频失败，尝试使用群文件发送: {e}")
                            try:
                                await UniMessage(UniHelper.file_seg(path)).send()
                                current_sent = True
                            except Exception as file_e:
                                logger.error(f"使用群文件发送视频失败: {file_e}")
                                current_sent = False
                    elif isinstance(media_item, AudioContent):
                        try:
                            # 尝试直接发送音频
                            await UniMessage(UniHelper.record_seg(path)).send()
                            # 如果需要上传音频文件，且没有因为大小问题发送失败
                            if pconfig.need_upload_audio:
                                await UniMessage(UniHelper.file_seg(path)).send()
                            current_sent = True
                        except Exception as e:
                            # 直接发送失败，可能是因为文件太大，尝试使用群文件发送
                            logger.debug(f"直接发送音频失败，尝试使用群文件发送: {e}")
                            try:
                                await UniMessage(UniHelper.file_seg(path)).send()
                                current_sent = True
                            except Exception as file_e:
                                logger.error(f"使用群文件发送音频失败: {file_e}")
                                current_sent = False

                    if current_sent:
                        sent = True
                    else:
                        # 发送失败，添加到剩余媒体列表，以便后续重试
                        remaining_media.append(media_item)
                else:
                    # 媒体未准备好，添加到剩余媒体列表
                    remaining_media.append(media_item)
            except Exception as e:
                logger.error(f"发送延迟媒体失败: {e}")
                # 添加到剩余媒体列表，以便后续重试
                remaining_media.append(media_item)

        # 更新媒体内容列表，保留未发送成功的媒体
        result.media_contents = remaining_media

        logger.debug(f"处理完成，剩余媒体数量: {len(remaining_media)}")

        # 只有当所有媒体都发送成功时，才从缓存中移除消息ID
        if remaining_media:
            # 如果还有未发送成功的媒体，更新缓存中的解析结果
            _MSG_ID_RESULT_MAP[str(liked_message_id)] = result
            logger.debug(
                f"更新_MSG_ID_RESULT_MAP中的消息ID: {liked_message_id}（剩余{len(remaining_media)}个媒体）"
            )

        elif str(liked_message_id) in _MSG_ID_RESULT_MAP:
            del _MSG_ID_RESULT_MAP[str(liked_message_id)]
            logger.debug(
                f"从_MSG_ID_RESULT_MAP中移除消息ID: {liked_message_id}（所有媒体发送成功）"
            )
        # 发送对应的表情
        if sent:
            # 发送"完成"的表情（使用用户指定的表情ID 124）
            try:
                if liked_message_id:
                    await message_reaction("124", message_id=str(liked_message_id))
            except Exception as e:
                logger.warning(f"Failed to send done reaction: {e}")
        else:
            # 没有可发送的媒体内容，发送"失败"的表情（使用用户指定的表情ID 10060）
            try:
                if liked_message_id:
                    await message_reaction("10060", message_id=str(liked_message_id))
            except Exception as e:
                logger.warning(f"Failed to send fail reaction: {e}")
    except Exception as e:
        # 发送"失败"的表情（使用用户指定的表情ID 10060）
        try:
            if liked_message_id:
                await message_reaction("10060", message_id=str(liked_message_id))
        except Exception as reaction_e:
            logger.warning(f"Failed to send fail reaction: {reaction_e}")
        logger.error(f"Failed to send media content: {e}")
