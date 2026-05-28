import io
import zipfile

from bs4 import BeautifulSoup
from msgspec import Struct
from msgspec.json import Decoder

from ...download import DOWNLOADER
from .models import File, Time, User


async def fetch_html_text_from_file(file: File) -> list[str]:
    """
    从 contentFile 提供的 zip 中异步读取 HTML，并提取正文文本

    :param file: contentFile
    :return: 去掉第一个文本节点（标题）后的正文文本
    """
    zip_bytes = await DOWNLOADER.content(file.url)
    html_name = file.filename.replace("_html.zip", "_html.html")
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
        try:
            html_bytes = zf.read(html_name)
        except KeyError as e:
            if html_name := next(
                (name for name in zf.namelist() if name.lower().endswith(".html")),
                None,
            ):
                html_bytes = zf.read(html_name)
            else:
                raise RuntimeError("no html file found in content zip") from e
    html = html_bytes.decode("utf-8", errors="ignore")
    soup = BeautifulSoup(html, "html.parser")
    full_text = soup.get_text("\n", strip=True)
    if not full_text:
        return []
    lines = [line for line in full_text.splitlines() if line.strip()]
    return lines if len(lines) <= 1 else lines[1:]


class DataObject(Struct):
    author: User
    contentFile: File
    publishDate: Time
    modifyDate: Time
    objectId: str
    title: str
    description: str
    """摘要，看起来是作者自己写的"""
    readCount: int
    rewardCoin: int
    thumbUpCount: int
    commentCount: int

    async def get_content(self) -> list[str]:
        return await fetch_html_text_from_file(self.contentFile)


class ArticleByIdV2(Struct):
    dataObject: DataObject
    msg: str


decoder = Decoder(ArticleByIdV2)
