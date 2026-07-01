from typing import ClassVar

from msgspec import convert
from nonebot.log import logger

from ...exception import TipException
from ...utils.cookie import ck2dict
from ..base import (
    BaseParser,
    ContentItem,
    MatchWithParams,
    ParseException,
    Platform,
    PlatformEnum,
    handle,
    pconfig,
)
from .commentListQuery import VisionRootCommentFeed
from .visionVideoDetail import VisionVideoDetail


class KuaiShouParser(BaseParser):
    """快手解析器"""

    platform: ClassVar[Platform] = Platform(
        name=PlatformEnum.KUAISHOU, display_name="快手"
    )

    def __init__(self):
        super().__init__()
        self.headers.update(
            {
                "Referer": "https://www.kuaishou.com/",
                "Origin": "https://www.kuaishou.com/",
                "X-Requested-With": "mixiaba.com.Browser",
                "Content-Type": "application/json",
                "Accept": "*/*",
                "Host": "www.kuaishou.com",
                "Connection": "keep-alive",
            }
        )
        self.ck: str | None = pconfig.ks_ck

    # https://v.kuaishou.com/2yAnzeZ
    @handle("v.kuaishou", r"v\.kuaishou\.com/[A-Za-z\d._?%&+\-=/#]+")
    @handle("kuaishou", r"(?:www\.)?kuaishou\.com/[A-Za-z\d._?%&+\-=/#]+")
    @handle("chenzhongtech", r"(?:v\.m\.)?chenzhongtech\.com/fw/[A-Za-z\d._?%&+\-=/#]+")
    async def _parse_v_kuaishou(self, searched: MatchWithParams):
        if self.ck is None:
            raise ParseException("请配置快手 Cookie")
        url = f"https://{searched.url}"
        final_url = await self.get_final_url(url)
        photo_id = final_url.split("?", maxsplit=1)[0].split("/")[-1]
        response = await self.httpx.post(
            "https://www.kuaishou.com/graphql",
            json={
                "operationName": "visionVideoDetail",
                "variables": {"photoId": f"{photo_id}", "page": "detail"},
                "query": "query visionVideoDetail($photoId: String, $type: String, $page: String, $webPageArea: String) {  visionVideoDetail(photoId: $photoId, type: $type, page: $page, webPageArea: $webPageArea) { status type author { id name following headerUrl __typename } photo { id duration caption likeCount realLikeCount coverUrl photoUrl liked timestamp expTag llsid viewCount videoRatio stereoType musicBlocked manifest {  mediaType  businessType  version  adaptationSet {  id  duration  representation { id defaultSelect backupUrl codecs url height width avgBitrate maxBitrate m3u8Slice qualityType qualityLabel frameRate featureP2sp hidden disableAdaptive __typename  }  __typename  }  __typename } manifestH265 photoH265Url coronaCropManifest coronaCropManifestH265 croppedPhotoH265Url croppedPhotoUrl videoResource __typename } tags { type name __typename } commentLimit { canAddComment __typename } llsid  danmakuSwitch __typename  }}",  # noqa: E501
            },
            cookies=ck2dict(self.ck),
            headers=self.headers,
        )
        data = response.json()
        vision_video_detail_data = data.get("data", {}).get("visionVideoDetail")

        if not isinstance(vision_video_detail_data, dict):
            raise ParseException(data)

        status = vision_video_detail_data.get("status")
        if status != 1:
            raise TipException("不支持解析的视频")  # 比如图集

        try:
            response = await self.httpx.post(
                "https://www.kuaishou.com/graphql",
                json={
                    "operationName": "commentListQuery",
                    "variables": {"photoId": f"{photo_id}", "pcursor": ""},
                    "query": "query commentListQuery($photoId: String, $pcursor: String) { visionCommentList(photoId: $photoId, pcursor: $pcursor) { commentCountV2 rootCommentsV2 {   commentId   authorId   authorName   content   headurl   timestamp   hasSubComments   likedCount  __typename } pcursorV2  __typename }}",  # noqa: E501
                },
                cookies=ck2dict(self.ck),
                headers=self.headers,
            )
            data = response.json()
            vision_root_comment_feed = data.get("data", {}).get("visionCommentList")
            if not isinstance(vision_root_comment_feed, dict):
                raise ParseException(data)

            comments = [
                self.create_comment(
                    author=self.create_author(
                        name=c.authorName,
                        avatar_url=c.headurl,
                        id=c.authorId,
                    ),
                    content=c.content,
                    timestamp=c.timestamp // 1000,
                    stats=self.create_stats(
                        like_count=c.likedCount,
                    ),
                )
                for c in convert(
                    vision_root_comment_feed, VisionRootCommentFeed
                ).rootCommentsV2
            ]
        except Exception as e:
            logger.error(f"Failed to get commentList: {photo_id}, error: {e!r}")
            logger.error(f"Raw response: {response.text}")
            comments = []

        visionVideoDetail = convert(vision_video_detail_data, VisionVideoDetail)
        content: list[ContentItem] = [visionVideoDetail.photo.caption]
        photoUrl = visionVideoDetail.photo.media_url
        cover_url = visionVideoDetail.photo.coverUrl

        if photoUrl:
            content.append(
                self.create_video(
                    url_or_task=photoUrl,
                    cover_url=cover_url,
                    duration=visionVideoDetail.photo.duration // 1000,
                )
            )

        if not photoUrl and cover_url:
            content.append(self.create_image(url=cover_url))

        author = self.create_author(
            name=visionVideoDetail.author.name,
            avatar_url=visionVideoDetail.author.headerUrl,
            id=visionVideoDetail.author.id,
        )
        return self.result(
            author=author,
            content=content,
            stats=self.create_stats(
                view_count=visionVideoDetail.photo.viewCount,
                like_count=visionVideoDetail.photo.likeCount,
            ),
            timestamp=visionVideoDetail.photo.timestamp // 1000,
            url=url,
            comments=comments,
        )
