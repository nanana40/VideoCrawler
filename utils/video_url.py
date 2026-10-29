"""
utils/video_url.py — 多平台视频 URL 识别与 ID 解析

目前支持：
  - YouTube（11 位 video_id）
  - TikTok / 抖音（数字 id；vm.tiktok.com、v.douyin.com 短链需先解析重定向）

用途：pipeline 的单视频模式靠这里判断"这条链接该用哪个爬虫"。
"""

from __future__ import annotations

import hashlib
import re
from typing import Any, Dict, Optional
from urllib.parse import urlparse

# YouTube 域名（短链与镜像）
_YOUTUBE_HOSTS = {
    "youtube.com", "www.youtube.com", "m.youtube.com",
    "music.youtube.com", "youtu.be",
}

# TikTok 域名（含短链）
_TIKTOK_HOSTS = {
    "tiktok.com", "www.tiktok.com", "m.tiktok.com",
    "vm.tiktok.com", "vt.tiktok.com",
}

# 抖音域名（含短链）
_DOUYIN_HOSTS = {
    "douyin.com", "www.douyin.com", "v.douyin.com",
    "iesdouyin.com", "www.iesdouyin.com",
}

# /video/1234567890 或 /note/123... 或 /photo/123...
_TIKTOK_ID_RE = re.compile(r"/(?:video|note|photo|slides)/(\d{6,})")


def _host(url: str) -> str:
    try:
        return (urlparse(url.strip()).hostname or "").lower()
    except Exception:
        return ""


def detect_video_site(url: str) -> str:
    """识别链接所属平台

    Returns:
        "youtube" | "tiktok"（抖音与 TikTok 共用同一套爬虫，统一返回 tiktok）
        "" 表示无法识别
    """
    host = _host(url or "")
    if not host:
        return ""
    if host in _YOUTUBE_HOSTS:
        return "youtube"
    if host in _TIKTOK_HOSTS or host in _DOUYIN_HOSTS:
        return "tiktok"
    return ""


def is_tiktok_url(url: str) -> bool:
    return detect_video_site(url) == "tiktok"


def extract_tiktok_video_id(url: str) -> Optional[str]:
    """从 TikTok / 抖音链接中提取数字视频 id

    短链（vm.tiktok.com/xxx、v.douyin.com/xxx）拿不到 id，返回 None，
    调用方应等 yt-dlp 解析出网页地址后再提取。
    """
    if not url:
        return None
    m = _TIKTOK_ID_RE.search(url)
    return m.group(1) if m else None


def fallback_tiktok_id(url: str) -> str:
    """短链等场景下生成稳定的兜底 id（同一链接每次结果一致）"""
    return "tt_" + hashlib.md5((url or "").encode("utf-8")).hexdigest()[:16]


def resolve_tiktok_url(url: str, timeout: float = 10.0) -> str:
    """跟随短链重定向，拿到含 /video/<id> 的规范地址

    短链（vm.tiktok.com/xxx、v.douyin.com/xxx）本身没有 id，
    必须请求一次让服务端 302 到规范地址。失败时原样返回。
    """
    try:
        import requests

        resp = requests.get(
            url,
            timeout=timeout,
            allow_redirects=True,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/131.0.0.0 Safari/537.36"
                )
            },
        )
        return resp.url or url
    except Exception:
        return url


def resolve_tiktok_id(url: str) -> Optional[str]:
    """提取 TikTok / 抖音视频 id；短链会先跟随一次重定向"""
    vid = extract_tiktok_video_id(url)
    if vid:
        return vid
    return extract_tiktok_video_id(resolve_tiktok_url(url))


def to_pipeline_video(info: Dict[str, Any], fallback_url: str = "") -> Dict[str, Any]:
    """把 TiktokSpider.get_video_info 的返回统一成 pipeline 的 candidate 结构

    pipeline 下游统一用 ``youtube_id`` 作为目录名/文件名，这里复用该字段
    （TikTok 的数字 id 与 YouTube 的 11 位 id 在路径层面等价）。
    """
    canonical = str(info.get("source_url") or fallback_url or "")
    vid = (
        extract_tiktok_video_id(canonical)
        or extract_tiktok_video_id(fallback_url)
        or fallback_tiktok_id(canonical or fallback_url)
    )

    lang = str(info.get("language") or "").strip().lower()
    if lang:
        lang = lang.replace("_", "-").split("-")[0]

    duration = info.get("duration")
    if not isinstance(duration, str):
        duration = ""

    return {
        "source_url": canonical or fallback_url,
        "youtube_id": vid,
        "yt_video_id": vid,
        "title": str(info.get("title") or ""),
        "channel": str(info.get("channel_name") or info.get("author") or ""),
        "duration": duration,
        "lang": lang or None,
        "is_asr": True,
        "platform": str(info.get("platform") or "tiktok"),
        "thumbnail": str(info.get("thumbnail") or ""),
    }
