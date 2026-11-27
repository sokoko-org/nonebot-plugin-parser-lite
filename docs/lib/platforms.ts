/**
 * 支持矩阵：与仓库 README 的「支持的平台」表格保持一致
 * true = 支持，false = 尚未适配，null = 平台暂无此类内容
 */
export type Support = boolean | null

export interface ContentPlatform {
  id: string
  name: string
  color: string
  graphic: Support
  comments: Support
  video: Support
  livePhoto: Support
}

export interface MusicPlatform {
  id: string
  name: string
  color: string
  audio: Support
  comments: Support
}

export const contentPlatforms: ContentPlatform[] = [
  { id: 'bilibili', name: 'B 站', color: '#FB7299', graphic: true, comments: true, video: true, livePhoto: true },
  { id: 'douyin', name: '抖音', color: '#FE2C55', graphic: true, comments: true, video: true, livePhoto: true },
  { id: 'weibo', name: '微博', color: '#E6162D', graphic: true, comments: true, video: true, livePhoto: true },
  { id: 'rednote', name: '小红书', color: '#FF2442', graphic: true, comments: true, video: true, livePhoto: true },
  { id: 'kuaishou', name: '快手', color: '#FF4906', graphic: true, comments: true, video: true, livePhoto: null },
  { id: 'acfun', name: 'AcFun', color: '#FD4C5D', graphic: true, comments: false, video: true, livePhoto: null },
  { id: 'x', name: 'X (Twitter)', color: '#71767B', graphic: true, comments: false, video: true, livePhoto: null },
  { id: 'tieba', name: '百度贴吧', color: '#3388FF', graphic: true, comments: true, video: true, livePhoto: null },
  { id: 'zhihu', name: '知乎', color: '#1772F6', graphic: true, comments: true, video: true, livePhoto: null },
  { id: 'duitang', name: '堆糖', color: '#FF5E5E', graphic: true, comments: true, video: null, livePhoto: null },
  { id: 'heybox', name: '小黑盒', color: '#5B5BEF', graphic: true, comments: true, video: true, livePhoto: true },
  { id: 'illu', name: 'ILLU', color: '#8B5CF6', graphic: true, comments: true, video: null, livePhoto: null },
  { id: 'lofter', name: 'LOFTER', color: '#20B2AA', graphic: true, comments: true, video: null, livePhoto: null },
  { id: 'buff', name: '网易 BUFF', color: '#F5A623', graphic: true, comments: true, video: null, livePhoto: null },
  { id: 'coolapk', name: '酷安', color: '#11AA55', graphic: true, comments: true, video: null, livePhoto: null },
  { id: 'hupu', name: '虎扑', color: '#C60100', graphic: true, comments: true, video: true, livePhoto: null },
  { id: 'miyoushe', name: '米游社', color: '#00B7FF', graphic: true, comments: true, video: true, livePhoto: null },
  { id: 'douban', name: '豆瓣', color: '#2E963D', graphic: true, comments: true, video: null, livePhoto: null },
  { id: '5eplay', name: '5EPlay', color: '#F0A020', graphic: true, comments: true, video: true, livePhoto: null },
  { id: 'doubao', name: '豆包', color: '#3C7BFF', graphic: null, comments: null, video: true, livePhoto: null },
  { id: 'linuxdo', name: 'Linux Do', color: '#F9B208', graphic: true, comments: true, video: null, livePhoto: null },
  { id: 'wmpvp', name: '完美世界竞技平台', color: '#E8B04B', graphic: true, comments: true, video: true, livePhoto: null },
  { id: 'zlb', name: '壁吧专楼吧', color: '#4A90E2', graphic: true, comments: true, video: null, livePhoto: null },
  { id: 'taptap', name: 'TapTap', color: '#15C5CE', graphic: true, comments: true, video: true, livePhoto: null },
  { id: 'ds', name: '网易大神', color: '#E43F3F', graphic: true, comments: true, video: true, livePhoto: null },
  { id: 'skyland', name: '森空岛', color: '#FFD100', graphic: true, comments: true, video: true, livePhoto: null }
]

export const musicPlatforms: MusicPlatform[] = [
  { id: 'netease', name: '网易云音乐', color: '#E60026', audio: true, comments: false },
  { id: 'kugou', name: '酷狗音乐', color: '#2CA2F9', audio: true, comments: false },
  { id: 'qsmusic', name: '汽水音乐', color: '#8A8F98', audio: true, comments: false },
  { id: 'kuwo', name: '酷我音乐', color: '#FFB300', audio: true, comments: true },
  { id: 'qqmusic', name: 'QQ音乐', color: '#31C27C', audio: true, comments: false },
  { id: 'migu', name: '咪咕音乐', color: '#E4007F', audio: true, comments: true }
]

export const allPlatforms = [...contentPlatforms, ...musicPlatforms]
