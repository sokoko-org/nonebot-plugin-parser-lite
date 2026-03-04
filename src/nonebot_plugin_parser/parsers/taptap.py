# TODO: 大重构或大删除

# import re
# import json
# import asyncio
# import contextlib
# from typing import Any
# from datetime import datetime

# from nonebot import logger
# from ..utils.http_utils import get_async_client

# from .base import BaseParser, handle
# from .data import Platform
# from ..constants import PlatformEnum
# from ..exception import ParseException

# from nonebot_plugin_htmlrender import get_new_page


# class TapTapParser(BaseParser):
#     """TapTap 解析器"""

#     platform = Platform(PlatformEnum.TAPTAP, "TapTap")

#     def __init__(self):
#         super().__init__()
#         self.base_url = "https://www.taptap.cn"
#         self.headers = {
#             "User-Agent": (
#                 "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
#                 "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
#             ),
#             "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
#         }

#     def _resolve_nuxt_value(self, root_data: list, value: Any) -> Any:
#         """Nuxt数据解压"""
#         if isinstance(value, int):
#             return root_data[value] if 0 <= value < len(root_data) else value
#         return value

#     async def _fetch_nuxt_data(self, url: str) -> list:
#         """获取页面的 Nuxt 数据"""
#         max_retries = 3
#         retry_count = 0

#         while retry_count <= max_retries:
#             try:
#                 async with get_new_page() as page:
#                     # 导航到 URL，增加等待时间确保页面完全加载
#                     await page.goto(
#                         url, wait_until="networkidle"
#                     )  # 等待网络空闲，确保资源加载完成
#                     await page.wait_for_timeout(
#                         5000
#                     )  # 增加等待时间到5秒，确保页面完全渲染

#                     # 获取页面内容
#                     response_text = await page.content()

#                     # 调试：记录页面基本信息
#                     logger.debug(f"页面 URL: {url}")
#                     logger.debug(f"页面大小: {len(response_text)} 字节")

#                     # 尝试多种方式提取 Nuxt 数据
#                     nuxt_data: list = []  # 明确类型标注为列表

#                     if "__NUXT_DATA__" in response_text:
#                         # 尝试多种正则表达式匹配
#                         patterns = [
#                             r'<script id="__NUXT_DATA__"[^>]*>(.*?)</script>',
#                             r'<script[^>]*id=["\']__NUXT_DATA__["\'][^>]*>(.*?)</script>',
#                             r"<script[^>]*>(.*?__NUXT_DATA__.*?)</script>",
#                         ]

#                         for pattern in patterns:
#                             if match := re.search(pattern, response_text, re.DOTALL):
#                                 logger.debug(
#                                     f"使用正则表达式匹配成功: {pattern[:50]}..."
#                                 )
#                                 try:
#                                     if json_match := re.search(
#                                         r"__NUXT_DATA__\s*=\s*(\[.*?\])",
#                                         match[1],
#                                         re.DOTALL,
#                                     ):
#                                         parsed_data = json.loads(json_match[1])
#                                         if isinstance(parsed_data, list):
#                                             nuxt_data = parsed_data
#                                             break
#                                     # 尝试直接解析整个匹配内容
#                                     parsed_data = json.loads(match[1])
#                                     if isinstance(parsed_data, list):
#                                         nuxt_data = parsed_data
#                                         break
#                                 except json.JSONDecodeError as e:
#                                     logger.debug(
#                                         f"解析 Nuxt 数据失败，尝试下一个正则表达式: {e}"
#                                     )
#                                     continue

#                     # 方式2: 如果找不到 __NUXT_DATA__，尝试从 window.__NUXT__ 中提取
#                     if not nuxt_data and "window.__NUXT__" in response_text:
#                         logger.debug("尝试从 window.__NUXT__ 中提取数据")
#                         if match := re.search(
#                             r"window\.__NUXT__\s*=\s*(\[.*?\])",
#                             response_text,
#                             re.DOTALL,
#                         ):
#                             try:
#                                 parsed_data = json.loads(match[1])
#                                 if isinstance(parsed_data, list):
#                                     nuxt_data = parsed_data
#                             except json.JSONDecodeError as e:
#                                 logger.debug(f"解析 window.__NUXT__ 失败: {e}")

#                     # 方式3: 尝试从 window.__NUXT_DATA__ 中提取
#                     if not nuxt_data and "window.__NUXT_DATA__" in response_text:
#                         logger.debug("尝试从 window.__NUXT_DATA__ 中提取数据")
#                         if match := re.search(
#                             r"window\.__NUXT_DATA__\s*=\s*(\[.*?\])",
#                             response_text,
#                             re.DOTALL,
#                         ):
#                             try:
#                                 parsed_data = json.loads(match[1])
#                                 if isinstance(parsed_data, list):
#                                     nuxt_data = parsed_data
#                             except json.JSONDecodeError as e:
#                                 logger.debug(f"解析 window.__NUXT_DATA__ 失败: {e}")

#                     # 如果仍然没有找到数据，抛出异常
#                     if not nuxt_data:
#                         # # 保存页面内容到临时文件，便于调试
#                         # temp_file = f"taptap_debug_{datetime.now().strftime('%Y%m%d_%H%M%S')}.html"
#                         # with open(temp_file, "w", encoding="utf-8") as f:
#                         #     f.write(response_text)
#                         # logger.debug(f"页面内容已保存到临时文件: {temp_file}")
#                         raise ParseException(f"无法找到 Nuxt 数据: {url}")

#                     # 确保返回的是列表
#                     return nuxt_data

#             except Exception as e:
#                 retry_count += 1
#                 if retry_count > max_retries:
#                     logger.error(
#                         f"获取 Nuxt 数据失败，已重试 {max_retries} 次 | url: {url}, error: {e}"
#                     )
#                     raise ParseException(
#                         f"获取 Nuxt 数据失败: {url}, error: {e}"
#                     ) from e

#                 logger.warning(
#                     f"获取 Nuxt 数据失败，正在重试 ({retry_count}/{max_retries}) | url: {url}, error: {e}"
#                 )
#                 await asyncio.sleep(1 * retry_count)  # 指数退避

#         # 这个代码路径理论上不会执行，因为循环中要么返回要么抛出异常
#         return []

#     async def _fetch_api_data(self, post_id: str) -> dict[str, Any] | None:
#         """从TapTap API获取动态详情"""
#         api_url = "https://www.taptap.cn/webapiv2/moment/v3/detail"
#         params = {
#             "id": post_id,
#             "X-UA": "V=1&PN=WebApp&LANG=zh_CN&VN_CODE=102&LOC=CN&PLT=PC&DS=Android&"
#             "UID=f69478c8-27a3-4581-877b-45ade0e61b0b&OS=Windows&OSV=10&DT=PC",
#         }

#         try:
#             async with get_async_client() as client:
#                 response = await client.get(
#                     api_url, params=params, headers=self.headers
#                 )
#                 response.raise_for_status()
#                 return response.json()
#         except Exception as e:
#             logger.error(f"[TapTap] API请求失败: {e}")
#             return None

#     async def _fetch_comments(self, post_id: str) -> list[dict[str, Any]] | None:
#         """从TapTap API获取评论数据"""
#         api_url = "https://www.taptap.cn/webapiv2/moment-comment/v1/by-moment"
#         params = {
#             "moment_id": post_id,
#             "sort": "rank",
#             "order": "desc",
#             "regulate_all": "false",
#             "X-UA": "V=1&PN=WebApp&LANG=zh_CN&VN_CODE=102&LOC=CN&PLT=PC&DS=Android&"
#             "UID=f69478c8-27a3-4581-877b-45ade0e61b0b&OS=Windows&OSV=10&DT=PC",
#         }

#         try:
#             async with get_async_client() as client:
#                 response = await client.get(
#                     api_url, params=params, headers=self.headers
#                 )
#                 response.raise_for_status()
#                 data = response.json()
#                 if data.get("success") and data.get("data"):
#                     return data["data"].get("list", [])
#                 return []
#         except Exception as e:
#             logger.error(f"[TapTap] 获取评论数据失败: {e}")
#             return None

#     async def _parse_post_detail(self, post_id: str) -> dict[str, Any]:
#         """解析动态详情"""
#         url = f"{self.base_url}/moment/{post_id}"

#         # 初始化结果结构
#         result = {
#             "id": post_id,
#             "url": url,
#             "title": "",
#             "summary": "",
#             "content_items": [],
#             "images": [],
#             "videos": [],
#             "video_id": None,
#             "video_duration": None,
#             "author": {
#                 "name": "",
#                 "avatar": "",
#                 "app_title": "",
#                 "app_icon": "",
#                 "honor_title": "",
#                 "honor_obj_id": "",
#                 "honor_obj_type": "",
#             },
#             "created_time": "",
#             "publish_time": "",
#             "stats": {"likes": 0, "comments": 0, "shares": 0, "views": 0, "plays": 0},
#             "video_cover": "",
#             "comments": [],
#             "seo_keywords": "",
#             "footer_images": [],
#             "app": {},
#             "extra": {},
#         }

#         api_success = False

#         # ==========================================================
#         # 1. 尝试使用API获取数据
#         # ==========================================================
#         api_data = await self._fetch_api_data(post_id)
#         if api_data and api_data.get("success"):
#             logger.info("[TapTap] 使用API获取数据成功")
#             data = api_data.get("data", {})
#             moment_data = data.get("moment", {})

#             # 基础信息
#             topic = moment_data.get("topic", {})
#             result["title"] = topic.get("title", "TapTap 动态分享")
#             result["seo_keywords"] = moment_data.get("seo", {}).get("keywords", "")

#             # 底部图片
#             footer_images = topic.get("footer_images", [])
#             result["footer_images"] = footer_images
#             for img_item in footer_images:
#                 original_url = img_item.get("original_url")
#                 if original_url and original_url not in result["images"]:
#                     result["images"].append(original_url)

#             # 时间
#             result["created_time"] = moment_data.get("created_time", "")
#             result["publish_time"] = moment_data.get("publish_time", "")

#             # 作者信息
#             author_data = moment_data.get("author", {})
#             user_data = author_data.get("user", {})
#             result["author"]["name"] = user_data.get("name", "")
#             result["author"]["avatar"] = user_data.get("avatar", "")

#             app_data = author_data.get("app", {})
#             result["author"]["app_title"] = app_data.get("title", "")
#             result["author"]["app_icon"] = app_data.get("icon", {}).get(
#                 "original_url", ""
#             )

#             # 游戏信息
#             moment_app = moment_data.get("app", {})
#             if moment_app:
#                 result["app"] = {
#                     "title": moment_app.get("title", ""),
#                     "icon": moment_app.get("icon", {}).get("original_url", ""),
#                     "rating": moment_app.get("stat", {})
#                     .get("rating", {})
#                     .get("score", ""),
#                     "latest_score": moment_app.get("stat", {})
#                     .get("rating", {})
#                     .get("latest_score", ""),
#                     "tags": moment_app.get("tags", []),
#                 }

#             # 统计信息
#             stats_data = moment_data.get("stat", {})
#             result["stats"]["likes"] = stats_data.get("ups", 0)
#             result["stats"]["comments"] = stats_data.get("comments", 0)
#             result["stats"]["shares"] = stats_data.get("shares", 0) or 0
#             result["stats"]["views"] = stats_data.get("pv_total", 0)
#             result["stats"]["plays"] = stats_data.get("play_total", 0)

#             # 视频检测 (Step 1: Get Video ID)
#             pin_video = topic.get("pin_video", {})
#             video_id = pin_video.get("video_id")
#             if video_id:
#                 logger.debug(f"[TapTap] 从API获取到视频ID: {video_id}")
#                 result["video_id"] = video_id

#                 thumbnail = pin_video.get("thumbnail", {})
#                 if thumbnail:
#                     result["video_cover"] = thumbnail.get("original_url", "")

#                 # Step 2: Try fetch video url directly via API
#                 play_info_url = "https://www.taptap.cn/video/v1/play-info"
#                 play_info_params = {"video_id": video_id}

#                 try:
#                     async with get_async_client() as client:
#                         play_response = await client.get(
#                             play_info_url, params=play_info_params, headers=self.headers
#                         )
#                         play_response.raise_for_status()
#                         play_data = play_response.json()

#                         if play_data.get("data") and play_data["data"].get("url"):
#                             real_url = play_data["data"]["url"]
#                             result["videos"].append(real_url)
#                             logger.success(
#                                 f"[TapTap] 从play-info接口获取到视频链接: {real_url[:50]}..."
#                             )
#                 except Exception as e:
#                     logger.warning(
#                         f"[TapTap] 获取视频play-info失败，将尝试浏览器嗅探: {e}"
#                     )

#             # 内容解析 (Text & Images)
#             first_post = data.get("first_post", {})
#             contents = first_post.get("contents", {})
#             json_contents = contents.get("json", [])

#             text_parts = []

#             for content_item in json_contents:
#                 item_type = content_item.get("type")
#                 result["content_items"].append(
#                     {"type": item_type, "data": content_item}
#                 )

#                 if item_type == "paragraph":
#                     paragraph_text = []
#                     children = content_item.get("children", [])
#                     for child in children:
#                         if isinstance(child, dict):
#                             # 先检查type字段，确保表情和话题标签能被正确处理
#                             child_type = child.get("type")
#                             # 处理表情
#                             if child_type == "tap_emoji":
#                                 img_info = child.get("info", {}).get("img", {})
#                                 original_url = img_info.get("original_url")
#                                 if original_url:
#                                     # 将表情转换为HTML img标签，与文字一起渲染
#                                     paragraph_text.append(
#                                         f'<img src="{original_url}" alt="表情" style="width: 20px;'
#                                         " height: 20px; vertical-align: middle; margin: 0 2px; "
#                                         'object-fit: contain;">'
#                                     )
#                             # 处理话题标签
#                             elif child_type == "hashtag":
#                                 tag_text = child.get("text", "")
#                                 if tag_text:
#                                     web_url = child.get("info", {}).get("web_url", "")
#                                     if web_url:
#                                         # 移除URL中的空格
#                                         web_url = web_url.strip()
#                                         # 将话题标签转换为HTML超链接
#                                         paragraph_text.append(
#                                             f'<a href="{web_url}" style="color: #3498db; text-decoration: none;'
#                                             " background-color: #f0f8ff; padding: 2px 6px; border-radius: 4px;"
#                                             f' font-weight: 500; margin: 0 2px;">{tag_text}</a>'
#                                         )
#                                     else:
#                                         # 如果没有URL，只显示标签文本
#                                         paragraph_text.append(
#                                             '<span style="color: #3498db; background-color: #f0f8ff; '
#                                             "padding: 2px 6px; border-radius: 4px; font-weight: 500; "
#                                             f'margin: 0 2px;">{tag_text}</span>'
#                                         )
#                             # 处理普通文本
#                             elif "text" in child:
#                                 paragraph_text.append(child["text"])
#                         # 处理字符串类型的child
#                         elif isinstance(child, str):
#                             paragraph_text.append(child)
#                     # 拼接当前段落内容，并添加换行符
#                     if paragraph_text:
#                         text_parts.append("".join(paragraph_text))
#                         # 添加换行符，区分不同段落
#                         text_parts.append("\n")

#                 elif item_type == "image":
#                     image_info = content_item.get("info", {}).get("image", {})
#                     original_url = image_info.get("original_url")
#                     if original_url:
#                         result["images"].append(original_url)

#             # 合并文本部分
#             if text_parts:
#                 result["text"] = "".join(text_parts)

#             api_success = True
#             logger.debug(
#                 f"API解析结果: videos={len(result['videos'])}, "
#                 f"images={len(result['images'])}, content_items={len(result['content_items'])}, "
#                 f"text={result['text']}"
#             )
#         else:
#             logger.error("[TapTap] API获取数据失败，准备使用浏览器解析")
#             api_success = False

#         # ==========================================================
#         # 2. 获取评论数据 (独立逻辑)
#         # ==========================================================
#         comments = await self._fetch_comments(post_id)
#         if comments:
#             logger.debug(f"评论：{comments}")
#             # 处理评论数据，提取纯文本内容
#             processed_comments = []
#             for comment in comments[:10]:  # 只保留前10条评论
#                 # 获取评论时间
#                 created_time = comment.get("created_time") or comment.get(
#                     "updated_time"
#                 )
#                 formatted_time = ""
#                 if created_time:
#                     try:
#                         dt = datetime.fromtimestamp(created_time)
#                         formatted_time = dt.strftime("%Y-%m-%d %H:%M")
#                     except (ValueError, TypeError):
#                         formatted_time = ""

#                 # 处理作者徽章，转换为HTML标签
#                 author = comment.get("author", {})
#                 badges = author.get("badges", [])

#                 # 创建处理后的徽章HTML
#                 processed_badges = []
#                 for badge in badges:
#                     if badge.get("title"):
#                         # 如果有徽章图片，显示图片+文字，否则只显示文字
#                         if badge.get("icon", {}).get("small"):
#                             badge_icon = badge["icon"]["small"]
#                             processed_badges.append(
#                                 f'<img src="{badge_icon}" alt="{badge["title"]}" title="{badge["title"]}" '
#                                 'style="width: 16px; height: 16px; vertical-align: middle;'
#                                 ' margin: 0 2px; object-fit: contain;">'
#                             )
#                         processed_badges.append(
#                             '<span class="badge-text" style="color: #3498db;'
#                             f' font-size: 12px; margin: 0 2px;">{badge["title"]}</span>'
#                         )

#                 processed_comment = {
#                     "id": comment.get("id", ""),
#                     "author": {
#                         "id": author.get("id", ""),
#                         "name": author.get("name", ""),
#                         "avatar": author.get("avatar", ""),
#                         "badges": badges,
#                         "processed_badges": "".join(
#                             processed_badges
#                         ),  # 添加处理后的徽章HTML
#                     },
#                     "content": "",
#                     "created_time": created_time,
#                     "formatted_time": formatted_time,
#                     "ups": comment.get("ups", 0),
#                     "comments": comment.get("comments", 0),
#                     "child_posts": [],
#                 }

#                 # 提取评论内容
#                 if comment.get("contents", {}).get("json"):
#                     content_json = comment["contents"]["json"]
#                     for item in content_json:
#                         item_type = item.get("type")
#                         if item_type == "paragraph":
#                             for child in item.get("children", []):
#                                 if child.get("text"):
#                                     processed_comment["content"] += child["text"]
#                                 if child.get("type", "") == "tap_emoji":
#                                     image_info = child.get("info", {}).get("image", {})
#                                     original_url = image_info.get("original_url")
#                                     if original_url:
#                                         tap_emoji_text = child.get("children", [])[0][
#                                             "text"
#                                         ]
#                                         processed_comment["content"] += (
#                                             f'<img src="{original_url}" alt="表情" class="comment-badge"'
#                                             f' title="{tap_emoji_text}" style="width: 20px; height: 20px;'
#                                             ' vertical-align: middle; margin: 0 2px; object-fit: contain;">'
#                                         )
#                         # 处理评论中的图片
#                         elif item_type == "image":
#                             image_info = item.get("info", {}).get("image", {})
#                             original_url = image_info.get("original_url")
#                             if original_url:
#                                 # 将图片转换为HTML img标签，添加到评论内容中
#                                 processed_comment["content"] += (
#                                     '<div class="comment-image" style="margin: 10px 0;">'
#                                     f'<img src="{original_url}" alt="评论图片" style="max-width: 100%;'
#                                     ' height: auto; border-radius: 8px;"></div>'
#                                 )
#                 # 处理回复
#                 if "child_posts" in comment:
#                     for reply in comment["child_posts"][:5]:  # 只保留前5条回复
#                         # 获取回复时间
#                         reply_created_time = reply.get("created_time") or reply.get(
#                             "updated_time"
#                         )
#                         reply_formatted_time = ""
#                         if reply_created_time:
#                             try:
#                                 dt = datetime.fromtimestamp(reply_created_time)
#                                 reply_formatted_time = dt.strftime("%Y-%m-%d %H:%M")
#                             except (ValueError, TypeError):
#                                 reply_formatted_time = ""

#                         # 处理回复者徽章，转换为HTML标签
#                         reply_author = reply.get("author", {})
#                         reply_badges = reply_author.get("badges", [])

#                         # 创建处理后的徽章HTML
#                         processed_reply_badges = []
#                         for badge in reply_badges:
#                             if badge.get("title"):
#                                 # 如果有徽章图片，显示图片+文字，否则只显示文字
#                                 if badge.get("icon", {}).get("small"):
#                                     badge_icon = badge["icon"]["small"]
#                                     processed_reply_badges.append(
#                                         f'<img src="{badge_icon}" alt="{badge["title"]}" title="{badge["title"]}"'
#                                         ' style="width: 16px; height: 16px; vertical-align: middle; '
#                                         'margin: 0 2px; object-fit: contain;">'
#                                     )
#                                 processed_reply_badges.append(
#                                     '<span class="badge-text" style="color: #3498db; font-size: 12px;'
#                                     f' margin: 0 2px;">{badge["title"]}</span>'
#                                 )

#                         processed_reply = {
#                             "id": reply.get("id", ""),
#                             "author": {
#                                 "id": reply_author.get("id", ""),
#                                 "name": reply_author.get("name", ""),
#                                 "avatar": reply_author.get("avatar", ""),
#                                 "badges": reply_badges,
#                                 "processed_badges": "".join(
#                                     processed_reply_badges
#                                 ),  # 添加处理后的徽章HTML
#                             },
#                             "content": "",
#                             "created_time": reply_created_time,
#                             "formatted_time": reply_formatted_time,
#                             "ups": reply.get("ups", 0),
#                         }

#                         # 提取回复内容
#                         if reply.get("contents", {}).get("json"):
#                             reply_json = reply["contents"]["json"]
#                             for item in reply_json:
#                                 item_type = item.get("type")
#                                 if item_type == "paragraph":
#                                     for child in item.get("children", []):
#                                         if child.get("text"):
#                                             processed_reply["content"] += child["text"]
#                                         if child.get("type", "") == "tap_emoji":
#                                             image_info = child.get("info", {}).get(
#                                                 "image", {}
#                                             )
#                                             original_url = image_info.get(
#                                                 "original_url"
#                                             )
#                                             if original_url:
#                                                 tap_emoji_text = child.get(
#                                                     "children", []
#                                                 )[0]["text"]
#                                                 processed_reply["content"] += (
#                                                     f'<img src="{original_url}" alt="表情" class="comment-badge"'
#                                                     f' title="{tap_emoji_text}" style="width: 20px; height: 20px;'
#                                                     ' vertical-align: middle; margin: 0 2px; object-fit: contain;">'
#                                                 )
#                                 # 处理回复中的图片
#                                 elif item_type == "image":
#                                     image_info = item.get("info", {}).get("image", {})
#                                     original_url = image_info.get("original_url")
#                                     if original_url:
#                                         # 将图片转换为HTML img标签，添加到回复内容中
#                                         processed_reply["content"] += (
#                                             '<div class="comment-image" style="margin: 10px 0;">'
#                                             f'<img src="{original_url}" alt="回复图片" style="max-width: 100%; '
#                                             'height: auto; border-radius: 8px;"></div>'
#                                         )

#                         processed_comment["child_posts"].append(processed_reply)

#                 processed_comments.append(processed_comment)

#             result["comments"] = processed_comments
#             logger.debug(f"[TapTap] 获取到 {len(processed_comments)} 条热门评论")
#         else:
#             logger.error("[TapTap] 获取评论数据失败")

#         # ==========================================================
#         # 3. 判断是否需要浏览器处理
#         # 条件：
#         # A. API 完全失败 (api_success 为 False)
#         # B. 有视频ID，但是没有获取到播放链接 (需要去嗅探)
#         # ==========================================================
#         has_video_id = bool(result.get("video_id"))
#         has_video_url = len(result["videos"]) > 0

#         need_browser = (not api_success) or (has_video_id and not has_video_url)

#         if need_browser:
#             logger.info(
#                 f"[TapTap] 启动浏览器处理 (API成功: {api_success}, 缺视频: {has_video_id and not has_video_url})"
#             )

#             # 使用 set 自动去重完全相同的 URL
#             captured_videos: set[str] = set()

#             async with get_new_page() as page:
#                 try:
#                     # 注入防检测脚本
#                     await page.add_init_script(
#                         "Object.defineProperty(navigator, 'webdriver', {get: () => undefined});"
#                     )
#                     await page.add_init_script(
#                         "Object.defineProperty(navigator, 'plugins', {get: () => [1, 2, 3, 4, 5]});"
#                     )

#                     page.set_default_timeout(40000)

#                     # --- 定义监听器 ---
#                     async def handle_response(response):
#                         with contextlib.suppress(Exception):
#                             resp_url = response.url

#                             # 1. 捕获 .m3u8 (含签名)
#                             if (
#                                 ".m3u8" in resp_url
#                                 and "sign=" in resp_url
#                                 and "taptap.cn" in resp_url
#                             ):
#                                 logger.debug(
#                                     f"[TapTap] 嗅探到 M3U8: {resp_url[:50]}..."
#                                 )
#                                 captured_videos.add(resp_url)

#                             # 2. 捕获 play-info 接口
#                             if (
#                                 "video/v1/play-info" in resp_url
#                                 and response.status == 200
#                             ):
#                                 with contextlib.suppress(Exception):
#                                     json_data = await response.json()
#                                     if json_data.get("data") and json_data["data"].get(
#                                         "url"
#                                     ):
#                                         real_url = json_data["data"]["url"]
#                                         captured_videos.add(real_url)

#                     page.on("response", handle_response)

#                     # --- 访问页面 ---
#                     logger.info(f"[TapTap] 正在访问详情页(开启嗅探): {url}")
#                     await page.goto(url, wait_until="domcontentloaded")

#                     # --- 获取 Nuxt 数据 (仅当 API 失败时，才进行完整的 Nuxt 解析来填补内容) ---
#                     if not api_success:
#                         logger.info("[TapTap] API失败，执行完整 Nuxt 数据提取兜底")
#                         data = []
#                         try:
#                             await page.wait_for_selector(
#                                 "#__NUXT_DATA__", timeout=25000, state="attached"
#                             )
#                             json_str = await page.evaluate(
#                                 'document.getElementById("__NUXT_DATA__").textContent'
#                             )
#                             if json_str:
#                                 data = json.loads(json_str)
#                         except Exception as e:
#                             logger.error(f"[TapTap] 提取 Nuxt 数据异常: {e}")

#                         # 补全标题、文本内容、作者信息和发布时间 (完整保留原逻辑)
#                         if data:
#                             # 提取所有可能的文本内容
#                             all_text_parts = []

#                             for item in data:
#                                 if not isinstance(item, dict):
#                                     continue

#                                 # 处理包含 user 字段的对象，提取作者信息
#                                 if "user" in item:
#                                     user_ref = item["user"]
#                                     user_obj = self._resolve_nuxt_value(data, user_ref)
#                                     if isinstance(user_obj, dict):
#                                         # 提取作者名称
#                                         result["author"]["name"] = (
#                                             self._resolve_nuxt_value(
#                                                 data, user_obj.get("name", "")
#                                             )
#                                             or ""
#                                         )
#                                         # 提取作者头像
#                                         if "avatar" in user_obj:
#                                             avatar = self._resolve_nuxt_value(
#                                                 data, user_obj["avatar"]
#                                             )
#                                             if isinstance(
#                                                 avatar, str
#                                             ) and avatar.startswith("http"):
#                                                 result["author"]["avatar"] = avatar
#                                             elif (
#                                                 isinstance(avatar, dict)
#                                                 and "original_url" in avatar
#                                             ):
#                                                 result["author"]["avatar"] = (
#                                                     self._resolve_nuxt_value(
#                                                         data, avatar["original_url"]
#                                                     )
#                                                     or ""
#                                                 )

#                                 # 处理包含 title 和 summary 字段的对象，提取标题和完整摘要
#                                 if "title" in item and "summary" in item:
#                                     title = self._resolve_nuxt_value(
#                                         data, item["title"]
#                                     )
#                                     summary = self._resolve_nuxt_value(
#                                         data, item["summary"]
#                                     )
#                                     if title and isinstance(title, str):
#                                         result["title"] = title
#                                     if summary and isinstance(summary, str):
#                                         # 将摘要添加到所有文本部分
#                                         all_text_parts.append(summary)

#                                 # 处理包含 stat 字段的对象，提取统计信息
#                                 if "stat" in item:
#                                     stat_ref = item["stat"]
#                                     stat_obj = self._resolve_nuxt_value(data, stat_ref)
#                                     if isinstance(stat_obj, dict):
#                                         result["stats"]["likes"] = stat_obj.get(
#                                             "supports", 0
#                                         ) or stat_obj.get("likes", 0)
#                                         result["stats"]["comments"] = stat_obj.get(
#                                             "comments", 0
#                                         )
#                                         result["stats"]["shares"] = stat_obj.get(
#                                             "shares", 0
#                                         )
#                                         result["stats"]["views"] = stat_obj.get(
#                                             "pv_total", 0
#                                         )
#                                         result["stats"]["plays"] = stat_obj.get(
#                                             "play_total", 0
#                                         )

#                                 # 直接处理包含统计数据的对象
#                                 if "supports" in item or "likes" in item:
#                                     result["stats"]["likes"] = item.get(
#                                         "supports", 0
#                                     ) or item.get("likes", 0)
#                                     result["stats"]["comments"] = item.get(
#                                         "comments", 0
#                                     )
#                                     result["stats"]["shares"] = item.get("shares", 0)
#                                     result["stats"]["views"] = item.get("pv_total", 0)
#                                     result["stats"]["plays"] = item.get("play_total", 0)

#                                 # 处理包含 contents 字段的对象，提取额外文本内容
#                                 if "contents" in item:
#                                     contents = self._resolve_nuxt_value(
#                                         data, item["contents"]
#                                     )
#                                     if isinstance(contents, list):
#                                         for content_item in contents:
#                                             if isinstance(content_item, dict):
#                                                 # 处理文本内容
#                                                 if "text" in content_item:
#                                                     text = self._resolve_nuxt_value(
#                                                         data, content_item["text"]
#                                                     )
#                                                     if text and isinstance(text, str):
#                                                         all_text_parts.append(text)
#                                                 # 处理段落内容
#                                                 elif (
#                                                     content_item.get("type")
#                                                     == "paragraph"
#                                                 ):
#                                                     children = content_item.get(
#                                                         "children"
#                                                     )
#                                                     if isinstance(children, list):
#                                                         for child in children:
#                                                             if (
#                                                                 isinstance(child, dict)
#                                                                 and "text" in child
#                                                             ):
#                                                                 child_text = self._resolve_nuxt_value(
#                                                                     data, child["text"]
#                                                                 )
#                                                                 if (
#                                                                     child_text
#                                                                     and isinstance(
#                                                                         child_text, str
#                                                                     )
#                                                                 ):
#                                                                     all_text_parts.append(
#                                                                         child_text
#                                                                     )
#                                                 # 处理带有text引用的内容项
#                                                 elif "text" in self._resolve_nuxt_value(
#                                                     data, content_item
#                                                 ):
#                                                     text = self._resolve_nuxt_value(
#                                                         data, content_item["text"]
#                                                     )
#                                                     if text and isinstance(text, str):
#                                                         all_text_parts.append(text)

#                                 # 处理包含 description 字段的对象，可能包含文本内容
#                                 if "description" in item:
#                                     description = self._resolve_nuxt_value(
#                                         data, item["description"]
#                                     )
#                                     if description and isinstance(description, str):
#                                         all_text_parts.append(description)

#                                 # 处理包含 content 字段的对象，可能包含文本内容
#                                 if "content" in item:
#                                     content = self._resolve_nuxt_value(
#                                         data, item["content"]
#                                     )
#                                     if content and isinstance(content, str):
#                                         all_text_parts.append(content)

#                                 # 处理包含 body 字段的对象，可能包含文本内容
#                                 if "body" in item:
#                                     body = self._resolve_nuxt_value(data, item["body"])
#                                     if body and isinstance(body, str):
#                                         all_text_parts.append(body)

#                                 # 提取发布时间
#                                 if "created_at" in item or "publish_time" in item:
#                                     publish_time = self._resolve_nuxt_value(
#                                         data,
#                                         item.get("created_at")
#                                         or item.get("publish_time"),
#                                     )
#                                     if publish_time:
#                                         result["publish_time"] = publish_time

#                                 # 提取视频信息 (API失败时从Nuxt补全)
#                                 if "pin_video" in item:
#                                     video_info = self._resolve_nuxt_value(
#                                         data, item["pin_video"]
#                                     )
#                                     if isinstance(video_info, dict):
#                                         if "duration" in video_info:
#                                             result["video_duration"] = (
#                                                 self._resolve_nuxt_value(
#                                                     data, video_info["duration"]
#                                                 )
#                                             )
#                                         if "video_id" in video_info:
#                                             result["video_id"] = (
#                                                 self._resolve_nuxt_value(
#                                                     data, video_info["video_id"]
#                                                 )
#                                             )

#                                 # 提取作者等级和标签
#                                 if "honor_title" in item:
#                                     result["author"]["honor_title"] = (
#                                         self._resolve_nuxt_value(
#                                             data, item["honor_title"]
#                                         )
#                                         or ""
#                                     )
#                                 if "honor_obj_id" in item:
#                                     result["author"]["honor_obj_id"] = (
#                                         self._resolve_nuxt_value(
#                                             data, item["honor_obj_id"]
#                                         )
#                                         or ""
#                                     )
#                                 if "honor_obj_type" in item:
#                                     result["author"]["honor_obj_type"] = (
#                                         self._resolve_nuxt_value(
#                                             data, item["honor_obj_type"]
#                                         )
#                                         or ""
#                                     )

#                             # 合并所有文本部分，去重并保留顺序
#                             seen_text = set()
#                             unique_text_parts = []
#                             for text in all_text_parts:
#                                 if text not in seen_text:
#                                     seen_text.add(text)
#                                     unique_text_parts.append(text)

#                             # 构建完整的摘要
#                             if unique_text_parts:
#                                 result["summary"] = "\n".join(unique_text_parts)

#                             if not result["title"]:
#                                 result["title"] = "TapTap 动态分享"

#                             # 图片处理 (API失败时从Nuxt补全)
#                             images = []
#                             img_blacklist = [
#                                 "appicon",
#                                 "avatars",
#                                 "logo",
#                                 "badge",
#                                 "emojis",
#                                 "market",
#                             ]

#                             for item in data:
#                                 if not isinstance(item, dict):
#                                     continue

#                                 if "original_url" in item:
#                                     img_url = self._resolve_nuxt_value(
#                                         data, item["original_url"]
#                                     )
#                                     if (
#                                         img_url
#                                         and isinstance(img_url, str)
#                                         and img_url.startswith("http")
#                                     ):
#                                         lower_url = img_url.lower()
#                                         if (
#                                             all(
#                                                 k not in lower_url
#                                                 for k in img_blacklist
#                                             )
#                                             and img_url not in images
#                                         ):
#                                             images.append(img_url)

#                                 # 尝试从 Nuxt 数据中找 MP4 直链 (并加入嗅探集合)
#                                 if "video_url" in item or "url" in item:
#                                     u = self._resolve_nuxt_value(
#                                         data, item.get("video_url") or item.get("url")
#                                     )
#                                     if (
#                                         isinstance(u, str)
#                                         and (".mp4" in u)
#                                         and u.startswith("http")
#                                     ):
#                                         captured_videos.add(u)

#                             result["images"] = images

#                     # 额外等待，确保视频请求发出
#                     with contextlib.suppress(Exception):
#                         await page.evaluate("window.scrollTo(0, 200)")
#                         await asyncio.sleep(3)
#                     # === 视频去重和智能选择逻辑 (适用于所有浏览器模式) ===
#                     unique_videos = []

#                     # 将捕获的视频链接转换为列表，并优先处理主M3U8
#                     video_list = list(captured_videos)

#                     # 首先，提取所有视频ID并分类
#                     video_dict = {}  # video_id -> [urls]
#                     for v_url in video_list:
#                         # 尝试提取 TapTap 视频 ID
#                         match = re.search(r"/hls/([a-zA-Z0-9\-_]+)", v_url)

#                         if match:
#                             vid_id = match[1]
#                             if vid_id not in video_dict:
#                                 video_dict[vid_id] = []
#                             video_dict[vid_id].append(v_url)
#                         else:
#                             # 如果没有匹配到ID (可能是 MP4 直链或其他 CDN 格式)，则单独处理
#                             if (
#                                 v_url not in unique_videos
#                                 and v_url not in result["videos"]
#                             ):
#                                 unique_videos.append(v_url)

#                     # 对于每个视频ID，优先选择最高分辨率的M3U8
#                     for vid_id, urls in video_dict.items():
#                         if len(urls) == 1:
#                             unique_videos.append(urls[0])
#                         else:
#                             # 多个URL，优先选择最高分辨率
#                             # 清晰度优先级：2208 1080P > 2206 720P > 2204 540P > 2202 360P
#                             quality_priority = ["2208", "2206", "2204", "2202"]

#                             # 按清晰度优先级排序
#                             def get_quality_priority(url):
#                                 for i, quality in enumerate(quality_priority):
#                                     if f"/{quality}.m3u8" in url:
#                                         return i
#                                 return len(quality_priority)  # 默认优先级最低

#                             urls.sort(key=get_quality_priority)
#                             # 选择优先级最高的URL
#                             highest_priority_url = urls[0]
#                             unique_videos.append(highest_priority_url)
#                             logger.debug(
#                                 f"[TapTap] 视频 {vid_id} 选择最高分辨率: {highest_priority_url}"
#                             )

#                     # 合并嗅探到的视频到结果中 (去重)
#                     for v in unique_videos:
#                         if v not in result["videos"]:
#                             result["videos"].append(v)

#                     if result["videos"]:
#                         logger.success(
#                             f"[TapTap] 最终捕获视频数: {len(result['videos'])}"
#                         )
#                     else:
#                         logger.warning("[TapTap] 未检测到视频链接")

#                 except Exception as e:
#                     logger.error(f"[TapTap] 详情页抓取流程失败: {e}")
#                 finally:
#                     if page:
#                         await page.close()

#         logger.debug(
#             f"解析结果: videos={len(result['videos'])}, images={len(result['images'])},"
#             f" comments={len(result['comments'])}"
#         )
#         return result

#     async def _parse_user_latest_post(self, user_id: str) -> dict[str, Any] | None:
#         """获取用户最新动态"""
#         url = f"{self.base_url}/user/{user_id}"
#         data = await self._fetch_nuxt_data(url)

#         candidates = []
#         moment_signature = ["id_str", "author", "topic", "created_time"]

#         for item in data:
#             if isinstance(item, dict) and all(key in item for key in moment_signature):
#                 moment_id = self._resolve_nuxt_value(data, item.get("id_str"))
#                 if not (
#                     moment_id
#                     and isinstance(moment_id, str)
#                     and moment_id.isdigit()
#                     and len(moment_id) > 10
#                 ):
#                     continue

#                 topic_index = item.get("topic")
#                 if not isinstance(topic_index, int) or topic_index >= len(data):
#                     continue
#                 topic_obj = data[topic_index]
#                 if not isinstance(topic_obj, dict):
#                     continue

#                 candidates.append(
#                     {
#                         "id": moment_id,
#                         "title": self._resolve_nuxt_value(data, topic_obj.get("title")),
#                         "summary": self._resolve_nuxt_value(
#                             data, topic_obj.get("summary")
#                         ),
#                     }
#                 )

#         return max(candidates, key=lambda x: int(x["id"])) if candidates else None

#     async def _fetch_review_comments(self, review_id: str) -> list[dict[str, Any]]:
#         """获取评论的评论列表"""
#         api_url = "https://www.taptap.cn/webapiv2/review-comment/v1/by-review"
#         params = {
#             "review_id": review_id,
#             "show_top": "true",
#             "regulate_all": "false",
#             "order": "asc",
#             "X-UA": "V=1&PN=WebApp&LANG=zh_CN&VN_CODE=102&LOC=CN&PLT=PC&DS=Android&"
#             "UID=f69478c8-27a3-4581-877b-45ade0e61b0b&OS=Windows&OSV=10&DT=PC",
#         }

#         comments = []
#         try:
#             async with get_async_client() as client:
#                 response = await client.get(
#                     api_url, params=params, headers=self.headers
#                 )
#                 response.raise_for_status()
#                 api_data = response.json()

#                 if api_data and api_data.get("success"):
#                     data = api_data.get("data", {})
#                     comment_list = data.get("list", [])

#                     for comment in comment_list:
#                         # 格式化时间
#                         created_time = comment.get("created_time")
#                         formatted_time = ""
#                         if created_time:
#                             try:
#                                 dt = datetime.fromtimestamp(created_time)
#                                 formatted_time = dt.strftime("%Y-%m-%d %H:%M")
#                             except (ValueError, TypeError):
#                                 formatted_time = ""

#                         # 处理作者徽章
#                         author = comment.get("author", {})
#                         badges = author.get("badges", [])
#                         processed_badges = []
#                         for badge in badges:
#                             if badge.get("title"):
#                                 if badge.get("icon", {}).get("small"):
#                                     badge_icon = badge["icon"]["small"]
#                                     processed_badges.append(
#                                         f'<img src="{badge_icon}" alt="{badge["title"]}" title="{badge["title"]}"'
#                                         ' style="width: 16px; height: 16px; vertical-align: middle; '
#                                         'margin: 0 2px; object-fit: contain;">'
#                                     )
#                                 processed_badges.append(
#                                     '<span class="badge-text" style="color: #3498db; font-size: 12px; '
#                                     f'margin: 0 2px;">{badge["title"]}</span>'
#                                 )

#                         processed_comment = {
#                             "id": comment.get("id", ""),
#                             "author": {
#                                 "id": author.get("id", ""),
#                                 "name": author.get("name", ""),
#                                 "avatar": author.get("avatar", ""),
#                                 "badges": badges,
#                                 "processed_badges": "".join(processed_badges),
#                             },
#                             "content": comment.get("contents", {}).get("text", ""),
#                             "created_time": created_time,
#                             "formatted_time": formatted_time,
#                             "ups": comment.get("ups", 0),
#                             "comments": 0,
#                             "child_posts": [],
#                         }

#                         comments.append(processed_comment)

#                     logger.info(f"[TapTap] 获取评论的评论成功: {len(comments)} 条")
#         except Exception as e:
#             logger.error(f"[TapTap] 获取评论的评论失败: {e}")

#         return comments

#     async def _parse_review_detail(self, review_id: str) -> dict[str, Any]:
#         """解析评论详情"""
#         url = f"{self.base_url}/review/{review_id}"

#         # 初始化结果结构
#         result = {
#             "id": review_id,
#             "url": url,
#             "title": "TapTap 评论详情",
#             "summary": "",
#             "content_items": [],
#             "images": [],
#             "videos": [],
#             "video_id": None,
#             "video_duration": None,
#             "author": {
#                 "name": "",
#                 "avatar": "",
#                 "app_title": "",
#                 "app_icon": "",
#                 "honor_title": "",
#                 "honor_obj_id": "",
#                 "honor_obj_type": "",
#             },
#             "created_time": "",
#             "publish_time": "",
#             "stats": {"likes": 0, "comments": 0, "shares": 0, "views": 0, "plays": 0},
#             "video_cover": "",
#             "comments": [],
#             "seo_keywords": "",
#             "footer_images": [],
#             "app": {},
#             "extra": {},
#         }

#         # 从API获取评论详情
#         api_url = "https://www.taptap.cn/webapiv2/review/v2/detail"
#         params = {
#             "id": review_id,
#             "X-UA": "V=1&PN=WebApp&LANG=zh_CN&VN_CODE=102&LOC=CN&PLT=PC&DS=Android&"
#             "UID=f69478c8-27a3-4581-877b-45ade0e61b0b&OS=Windows&OSV=10&DT=PC",
#         }

#         try:
#             async with get_async_client() as client:
#                 response = await client.get(
#                     api_url, params=params, headers=self.headers
#                 )
#                 response.raise_for_status()
#                 api_data = response.json()

#                 if api_data and api_data.get("success"):
#                     data = api_data.get("data", {})
#                     moment_data = data.get("moment", {})
#                     review_data = moment_data.get("review", {})
#                     app_data = moment_data.get("app", {})
#                     author_data = moment_data.get("author", {})
#                     user_data = author_data.get("user", {})

#                     # 作者信息
#                     result["author"]["name"] = user_data.get("name", "")
#                     result["author"]["avatar"] = user_data.get("avatar", "")

#                     # 评论内容
#                     result["summary"] = review_data.get("contents", {}).get("text", "")

#                     # 评论图片
#                     for img_item in review_data.get("images", []):
#                         if original_url := img_item.get("original_url"):
#                             result["images"].append(original_url)

#                     # 发布时间
#                     result["created_time"] = moment_data.get("created_time", "")
#                     result["publish_time"] = moment_data.get("publish_time", "")

#                     # 统计信息
#                     stat_data = moment_data.get("stat", {})
#                     result["stats"]["likes"] = stat_data.get("ups", 0)
#                     result["stats"]["views"] = stat_data.get("pv_total", 0)
#                     result["stats"]["comments"] = stat_data.get("comments", 0) or 0

#                     # 游戏信息
#                     result["app"] = {
#                         "title": app_data.get("title", ""),
#                         "icon": app_data.get("icon", {}).get("original_url", ""),
#                         "rating": app_data.get("stat", {})
#                         .get("rating", {})
#                         .get("score", ""),
#                         "tags": app_data.get("tags", []),
#                     }

#                     # 评论额外信息
#                     result["extra"]["extra"] = {
#                         "review": review_data,
#                         "author": {
#                             "device": moment_data.get("device", ""),
#                             "released_time": moment_data.get("release_time", ""),
#                         },
#                         "ratings": review_data.get("ratings", []),
#                         "stage": review_data.get("stage", 0),
#                         "stage_label": review_data.get("stage_label", ""),
#                     }

#                     # 获取评论的评论
#                     result["comments"] = await self._fetch_review_comments(review_id)

#                     logger.info(
#                         f"[TapTap] 评论详情解析成功: {result['author']['name']} - {result['app']['title']}"
#                     )
#                 else:
#                     logger.error("[TapTap] 评论详情API获取失败")
#         except Exception as e:
#             logger.error(f"[TapTap] 解析评论详情失败: {e}")
#             raise ParseException(f"获取评论详情失败: {url}") from e

#         return result

#     @handle(keyword="taptap.cn/user", pattern=r"taptap\.cn/user/(\d+)")
#     async def handle_user(self, matched):
#         """处理用户链接，返回最新动态"""
#         user_id = matched.group(1)
#         latest_post = await self._parse_user_latest_post(user_id)

#         if not latest_post:
#             raise ParseException(f"用户 {user_id} 暂无动态")

#         detail = await self._parse_post_detail(latest_post["id"])
#         return self._build_result(detail)

#     @handle(keyword="taptap.cn/moment", pattern=r"taptap\.cn/moment/(\d+)")
#     async def handle_moment(self, matched):
#         """处理动态链接"""
#         post_id = matched.group(1)
#         detail = await self._parse_post_detail(post_id)
#         return self._build_result(detail)

#     @handle(keyword="taptap.cn/topic", pattern=r"taptap\.cn/topic/(\d+)")
#     async def handle_topic(self, matched):
#         """处理话题链接"""
#         topic_id = matched.group(1)
#         # 话题链接暂时返回动态列表，这里简化处理
#         url = f"{self.base_url}/topic/{topic_id}"
#         data = await self._fetch_nuxt_data(url)

#         # 简单提取话题名称
#         topic_name = "TapTap 话题"
#         for item in data:
#             if isinstance(item, dict) and "title" in item:
#                 title = self._resolve_nuxt_value(data, item["title"])
#                 if title and isinstance(title, str):
#                     topic_name = title
#                     break

#         return self.result(title=topic_name, content=[f"查看话题详情: {url}"], url=url)

#     @handle(keyword="taptap.cn/review", pattern=r"taptap\.cn/review/(\d+)")
#     async def handle_review(self, matched):
#         """处理评论详情链接"""
#         review_id = matched.group(1)
#         detail = await self._parse_review_detail(review_id)
#         return self._build_result(detail)

#     def _build_result(self, detail: dict[str, Any]):
#         """构建解析结果"""
#         contents = [detail.get("text", detail["summary"])]

#         # 添加图片
#         for img_url in detail["images"]:
#             contents.append(self.create_image(img_url))

#         # 添加视频
#         for video_url in detail["videos"]:
#             # 简单处理，不获取封面和时长
#             video_content = self.create_video(video_url)
#             contents.append(video_content)

#         # 构建作者对象
#         author = self.create_author(
#             name=detail["author"]["name"], avatar_url=detail["author"]["avatar"]
#         )

#         # 处理发布时间，转换为时间戳
#         timestamp = None
#         publish_time = detail["publish_time"]
#         if publish_time:
#             # 如果已经是整数，直接使用
#             if isinstance(publish_time, int):
#                 timestamp = publish_time
#             else:
#                 # 尝试解析不同格式的时间字符串
#                 with contextlib.suppress(ValueError, TypeError):
#                     # 示例：2023-12-25T14:30:00+08:00
#                     dt = datetime.fromisoformat(
#                         str(publish_time).replace("Z", "+00:00")
#                     )
#                     timestamp = int(dt.timestamp())

#         # 格式化时间函数
#         def format_time(timestamp):
#             if timestamp:
#                 with contextlib.suppress(ValueError, TypeError):
#                     if isinstance(timestamp, int):
#                         dt = datetime.fromtimestamp(timestamp)
#                         return dt.strftime("%Y-%m-%d %H:%M:%S")
#             return ""

#         # 格式化时间
#         formatted_publish_time = format_time(detail.get("publish_time"))
#         formatted_created_time = format_time(detail.get("created_time"))

#         # 评论时间已经在_fetch_comments中格式化好了，这里直接使用
#         formatted_comments = detail.get("comments", [])

#         # 构建解析结果，先准备extra数据
#         extra_data = {
#             "stats": detail["stats"],
#             "images": detail["images"],  # 将图片列表放入extra，用于模板渲染
#             "content_items": detail.get("content_items", []),
#             "created_time": detail.get("created_time", ""),
#             "publish_time": detail.get("publish_time", ""),
#             "formatted_created_time": formatted_created_time,
#             "formatted_publish_time": formatted_publish_time,
#             "video_cover": detail.get("video_cover", ""),
#             "app": detail.get("app", {}),  # 添加游戏信息
#             "seo_keywords": detail.get("seo_keywords", ""),  # 添加SEO关键词
#             "footer_images": detail.get("footer_images", []),  # 添加footer_images
#             "comments": formatted_comments,  # 添加格式化后的评论数据
#         }

#         # 合并原始detail中的extra字段内容，用于标识游戏评论
#         if detail.get("extra"):
#             extra_data.update(detail["extra"])

#         result = self.result(
#             title=detail["title"],
#             url=detail["url"],
#             author=author,
#             timestamp=timestamp,
#             content=contents,
#             extra=extra_data,
#         )

#         # 设置media_contents，用于延迟发送
#         logger.debug(
#             f"构建解析结果完成: title={detail['title']}, images={len(detail['images'])}, "
#             f"videos={len(detail['videos'])}"
#         )

#         return result
