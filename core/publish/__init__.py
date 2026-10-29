"""
core.publish — 视频发布模块

三层结构：
  storage.py     — 账号 / 视频池 / 发布记录 的 DB 操作（模块级函数）
  pool.py        — 视频候选池管理（入池、清理过期、查询）
  accounts.py    — 平台账号管理（cookie 加密存储、CDP 提取、有效性探测）
  clients.py     — 各平台 API 客户端（抽象基类 + 4 个具体实现）
  service.py     — 上层编排：取账号 → 上传视频 → 发布

UI 入口：gui/pages/page_publish.py（第 5 页）
管线挂钩：auto_pipeline.py（全自动）、page_subtitle.py（非全自动烧录完成后）
"""

from .pool import VideoPool
from .accounts import AccountManager
from .clients import (
    BasePlatformClient,
    BilibiliClient,
    DouyinClient,
    XiaohongshuClient,
    KuaishouClient,
    PlatformClientFactory,
    VideoMeta,
    PublishResult,
)
from .service import PublishService

__all__ = [
    "VideoPool",
    "AccountManager",
    "BasePlatformClient",
    "BilibiliClient",
    "DouyinClient",
    "XiaohongshuClient",
    "KuaishouClient",
    "PlatformClientFactory",
    "VideoMeta",
    "PublishResult",
    "PublishService",
]

# 平台常量
PLATFORMS = {
    "bilibili":    {"label": "哔哩哔哩", "color": "#4e8cff"},
    "douyin":      {"label": "抖音",     "color": "#ffffff"},
    "xiaohongshu": {"label": "小红书",   "color": "#b97a95"},
    "kuaishou":    {"label": "快手",     "color": "#52b788"},
}

# video_pool.publish_status
POOL_STATUS = {
    0: "待发布",
    1: "已发布",
    2: "已跳过",
    3: "发布失败",
}

# publish_record.status
RECORD_STATUS = {
    1: "成功",
    2: "失败",
}
