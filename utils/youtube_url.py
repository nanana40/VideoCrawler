"""
utils/youtube_url.py — YouTube URL 构造与解析

AUDIT-0051: 消除全仓重复的 f"https://www.youtube.com/watch?v={id}" 拼接
与 video_id 提取逻辑。
"""

from __future__ import annotations

import re
from typing import Optional

# YouTube watch URL 前缀
WATCH_URL_PREFIX = "https://www.youtube.com/watch?v="
# 备选短域名
_SHORT_HOSTS = {"youtu.be", "youtube", "m.youtube.com", "music.youtube.com"}

# video_id 的正则：11 位字母数字（含下划线和减号）
_VIDEO_ID_RE = re.compile(r"[a-zA-Z0-9_-]{11}")


def build_watch_url(video_id: str) -> str:
    """把 video_id 转成完整的 YouTube watch URL"""
    return f"{WATCH_URL_PREFIX}{video_id}"


def extract_video_id(url_or_id: str) -> Optional[str]:
    """从 URL 或裸 video_id 中提取 11 位 video_id

    支持的格式：
      - https://www.youtube.com/watch?v=dQw4w9WgXcQ
      - https://youtu.be/dQw4w9WgXcQ
      - https://www.youtube.com/embed/dQw4w9WgXcQ
      - dQw4w9WgXcQ（裸 id）

    返回 None 表示无法识别。
    """
    if not url_or_id:
        return None

    s = url_or_id.strip()

    # 如果已经是 11 位纯 id
    if re.fullmatch(r"[a-zA-Z0-9_-]{11}", s):
        return s

    # watch?v= 形式
    m = re.search(r"[?&]v=([a-zA-Z0-9_-]{11})", s)
    if m:
        return m.group(1)

    # youtu.be/xxx 或 embed/xxx 或 /shorts/xxx
    for pat in [r"youtu\.be/([a-zA-Z0-9_-]{11})", r"/embed/([a-zA-Z0-9_-]{11})", r"/shorts/([a-zA-Z0-9_-]{11})"]:
        m = re.search(pat, s)
        if m:
            return m.group(1)

    return None
