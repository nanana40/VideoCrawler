"""yt-dlp 共享常量和工厂（AUDIT-0045）

之前 download.py（3 处）和 youtube_spider.py（1 处）各自手写同一份 UA + Accept-Language + Referer headers，
Chrome 升级时要改 4 处。统一放这里。
"""

# 当前（2025）YouTube 对 UA 不算很严格，但太旧的 UA 会被 API 拒
_YOUTUBE_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/131.0.0.0 Safari/537.36"
)

# yt-dlp http_headers 统一字典：Chrome 伪装 + YouTube 自己的 Referer
# 既用于 download，也用于 youtube_spider 的 probe
YTDLP_YOUTUBE_HEADERS = {
    "User-Agent": _YOUTUBE_UA,
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://www.youtube.com/",
}
