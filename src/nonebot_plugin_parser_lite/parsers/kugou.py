import base64
import contextlib
import json
import re
from typing import ClassVar

from msgspec import Struct, field
from msgspec.json import Decoder

from ..data import ContentItem, Platform
from .base import BaseParser, MatchWithParams, ParseException, PlatformEnum, handle


class PlayInfo(Struct):
    errcode: int
    """错误码，0无错。如果出错了，后面那些都是默认值，没出错就不可能是默认值"""
    album_img: str = ""
    """歌曲封面，需要把中间的{size}替换"""
    bitRate: int = 0
    """比特率"""
    choricSinger: str = ""
    """合唱歌手"""
    error: str = ""
    """错误信息"""
    fileName: str = ""
    """下载文件名"""
    fileSize: int = 0
    """文件大小"""
    extName: str = ""
    """文件扩展名"""
    hash: str = ""
    """歌曲hash"""
    imgUrl: str = ""
    """作者头像，需要把中间的{size}替换"""
    intro: str = ""
    """简介?, 可能是mv的东西"""
    mvhash: str = ""
    """
    mv的hash
    应该可以通过
    `http://mobilecdnbj.kugou.com/api/v3/mv/detail?area_code=1&plat=0&mvhash={mvhash}&with_res_tag=1`
    获取到mv，没找到测试用例
    """
    pay_type: int = 0
    """歌曲类型 0,免费; 3,付费"""
    singerId: int = 0
    """歌手id"""
    singerName: str = ""
    """歌手名称"""
    songName: str = ""
    """歌曲名称"""
    timeLength: int = 0
    """歌曲时长，单位秒"""
    url: str = ""
    """歌曲下载地址"""


class CandidatesList(Struct):
    id: str
    """歌词id"""
    accesskey: str
    """accessKey"""
    singer: str
    """歌手名称"""
    song: str
    """歌曲名称"""
    language: str
    """歌词语言"""


class KrcsSearch(Struct):
    errcode: int
    """错误码, 200无错"""
    errmsg: str
    """错误信息"""
    expire: int
    """accessKey过期时间(应该是秒)"""
    candidates: list[CandidatesList] = field(default_factory=list)
    """歌词结果列表"""


class Lyrics(Struct):
    error_code: int
    """错误码, 0无错"""
    info: str
    """信息"""
    fmt: str
    """歌词格式, 由url传参决定"""
    _source: str
    """来源"""
    charset: str
    """字符集"""
    content: str
    """歌词base64内容"""
    id: str
    """歌词id"""


class KuGouParser(BaseParser):
    platform: ClassVar[Platform] = Platform(
        name=PlatformEnum.KUGOU, display_name="酷狗音乐"
    )

    def _extract_hash(self, html_text: str) -> str:
        """获取歌曲hash"""
        if smarty_match := re.search(
            r"var dataFromSmarty\s*=\s*(\[.*?\]),", html_text, re.DOTALL
        ):
            with contextlib.suppress(json.JSONDecodeError):
                smarty_data = json.loads(smarty_match[1])
                if isinstance(smarty_data, list) and smarty_data:
                    return smarty_data[0].get("hash", "").upper()
        return ""

    @handle(
        "kugou.com",
        r"https?://[^\s]*?kugou\.com.*?(?:/(?:share|mixsong)/[a-zA-Z0-9]+\.html|(?:id|chain)=[a-zA-Z0-9]+)",
    )
    async def _parse_kugou_share(self, searched: MatchWithParams):
        """解析酷狗分享链接"""
        share_url = searched.url
        response = await self.httpx.get(share_url)
        response.raise_for_status()
        html_text = response.text

        # 提取歌曲hash
        _hash = self._extract_hash(html_text)

        if not _hash:
            raise ParseException(f"未找到歌曲hash: {share_url}")

        response = await self.httpx.get(
            f"https://m.kugou.com/app/i/getSongInfo.php?cmd=playInfo&hash={_hash}"
        )
        playinfo = Decoder(PlayInfo).decode(response.content)
        if playinfo.errcode != 0:
            raise ParseException(
                f"酷狗音乐解析失败: {playinfo.errcode} {playinfo.error}"
            )

        audio_url = playinfo.url
        if not audio_url:
            raise ParseException("未找到音频资源")

        audio_name = f"{playinfo.fileName}.{playinfo.extName}"

        audio_content = self.create_audio(
            url=audio_url,
            duration=playinfo.timeLength,
            audio_name=audio_name,
        )
        author = self.create_author(
            name=playinfo.singerName  # , playinfo.imgUrl.format(size=480)
        )

        response = await self.httpx.get(
            f"https://krcs.kugou.com/search?hash={playinfo.hash}"
        )
        krcs = Decoder(KrcsSearch).decode(response.content)
        if krcs.errcode != 200:
            raise ParseException(f"酷狗音乐解析失败: 歌词搜索失败: {krcs.errmsg}")
        if not krcs.candidates:
            raise ParseException("未找到歌词")

        response = await self.httpx.get(
            f"https://lyrics.kugou.com/download?ver=1&id={krcs.candidates[0].id}&accesskey={krcs.candidates[0].accesskey}&fmt=lrc"
        )
        lyrics = Decoder(Lyrics).decode(response.content)
        if lyrics.error_code != 0:
            raise ParseException(f"酷狗音乐解析失败: 歌词获取失败: {lyrics.info}")
        lyric = base64.b64decode(lyrics.content).decode(lyrics.charset)
        cover_url = playinfo.album_img.format(size=480)
        contents: list[ContentItem] = [
            self.create_image(url=cover_url, need_send=False)
        ]

        contents.append(audio_content)

        # 构建额外信息
        extra = {
            "info": f"比特率: {playinfo.bitRate}K | "
            f"时长: {int(float(playinfo.timeLength) // 60)}"
            f":{int(float(playinfo.timeLength) % 60):02d}",
            "lyric": lyric,
            "type": "audio",
            "type_tag": "音乐",
            "type_icon": "fa-music",
        }

        return self.result(
            title=playinfo.songName,
            author=author,
            url=share_url,
            content=contents,
            extra=extra,
        )
