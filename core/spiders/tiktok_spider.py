"""
TikTok / Douyin 视频爬虫（含 trending 无关键词抓取）

yt-dlp 原生 extractor 已覆盖：
    - TikTok (单个视频 URL)
    - tiktok:user (用户主页所有视频)
    - tiktok:collection (合集)
    - Douyin (抖音)
    - vm.tiktok (移动端短链)

⚠️ 关键限制：
    1. tiktok:tag / tiktok:sound 在 yt-dlp 里标记为 CURRENTLY BROKEN
    2. TikTok Web 端对大陆 IP 硬墙（所有请求返回 /about 页面），需要代理才能访问
    3. TikTok App 端 API 需要 X-Bogus / X-Argus 签名（反爬极强）

TikTok Trending 无关键词抓取策略（三层降级链）：
    Layer 1: 有代理 + cookies → curl_cffi + Web 端 /api/recommend/item_list/ API
              按 region 参数（US/GB/DE/JP/KR/FR/ES/BR/...）抓不同地区的热门页
    Layer 2: 有代理 → 预设热门用户列表（按地区分组），用 yt-dlp tiktok:user 逐个爬
    Layer 3: 无代理 → 返回空 + 明确错误提示

使用方式：
    spider = TiktokSpider()
    videos = spider.get_video_info("https://www.tiktok.com/@user/video/123456")
    videos = spider.crawl("https://www.tiktok.com/@someuser")  # 用户主页
    videos = spider.crawl_trending(region="US", max_videos=50)   # 无关键词抓美国热门
    videos = spider.crawl_trending(max_videos=30)                # 全球热门
"""

import os
import re
import json
import random
import string
import time
import threading
from datetime import date
from pathlib import Path
from typing import Dict, Any, List, Optional
from urllib.parse import urlparse

from .base_spider import VideoSpider
from utils.logger import get_crawler_logger
from utils.config_loader import load_config

logger = get_crawler_logger()


_TIKTOK_HOSTS = (
    "tiktok.com",
    "vm.tiktok.com",
    "vt.tiktok.com",
    "douyin.com",
    "iesdouyin.com",
    "xigua.com",
)

# TikTok 支持的地区代码（用于按语言/地区分类热门）
# 这些地区代码会被传入 API 请求，TikTok 会返回该地区的热门内容
TIKTOK_REGIONS = [
    "US",   # 英语 - 美国
    "GB",   # 英语 - 英国
    "DE",   # 德语 - 德国
    "FR",   # 法语 - 法国
    "ES",   # 西班牙语 - 西班牙
    "MX",   # 西班牙语 - 墨西哥
    "BR",   # 葡萄牙语 - 巴西
    "JP",   # 日语 - 日本
    "KR",   # 韩语 - 韩国
    "RU",   # 俄语 - 俄罗斯
    "IT",   # 意大利语 - 意大利
    "CA",   # 英语/法语 - 加拿大
    "AU",   # 英语 - 澳洲
    "NL",   # 荷兰语
    "SE",   # 瑞典语
    "NO",   # 挪威语
    "DK",   # 丹麦语
    "FI",   # 芬兰语
    "PL",   # 波兰语
    "TR",   # 土耳其语
    "ID",   # 印尼语
    "TH",   # 泰语
    "VN",   # 越南语
    "PH",   # 菲律宾
    "SA",   # 阿拉伯语
    "EG",   # 阿拉伯语 - 埃及
    "ZA",   # 英语 - 南非
    "AR",   # 西班牙语 - 阿根廷
    "CO",   # 西班牙语 - 哥伦比亚
    "CL",   # 西班牙语 - 智利
]

# region → language 映射（用于 Spider 分类时打标签）
REGION_TO_LANGUAGE = {
    "US": "en", "GB": "en", "CA": "en", "AU": "en", "ZA": "en", "IE": "en", "NZ": "en",
    "DE": "de", "AT": "de", "CH": "de",
    "FR": "fr", "BE": "fr", "CA-fR": "fr",
    "ES": "es", "MX": "es", "AR": "es", "CO": "es", "CL": "es", "PE": "es", "DO": "es", "VE": "es", "CU": "es",
    "BR": "pt", "PT": "pt",
    "JP": "ja",
    "KR": "ko",
    "RU": "ru", "BY": "ru", "UA": "uk",
    "IT": "it",
    "NL": "nl", "BE": "nl",
    "SE": "sv",
    "NO": "no",
    "DK": "da",
    "FI": "fi",
    "PL": "pl",
    "TR": "tr",
    "ID": "id",
    "TH": "th",
    "VN": "vi",
    "PH": "tl",
    "SA": "ar", "EG": "ar", "AE": "ar", "MA": "ar", "TN": "ar",
}


def _is_tiktok_url(url: str) -> bool:
    try:
        host = urlparse(url).netloc.lower()
        return any(h in host for h in _TIKTOK_HOSTS)
    except Exception:
        return False


def _classify_tiktok_url(url: str) -> str:
    """把 TikTok URL 分类成 extractor 类型：single / user / collection / live"""
    parsed = urlparse(url)
    path = parsed.path
    if any(h in parsed.netloc for h in ("douyin",)):
        if "/user/" in path or "/profile/" in path or "/@" in path:
            return "user"
        return "single"
    # TikTok —— 先更具体的（collection/live），再宽泛的（/@ user）
    if "/@" in path and "/video/" in path:
        return "single"
    if "/collection/" in path:
        return "collection"
    if "/live" in path:
        return "live"
    if "/@" in path:
        return "user"
    return "single"


def _get_proxy_from_config() -> str:
    """从 config.yaml 读取代理地址"""
    try:
        cfg = load_config()
        return cfg.get("crawler", {}).get("proxy", "") or ""
    except Exception:
        return ""


def _detect_cookie_browser(configured: str) -> str:
    """校验配置的浏览器是否可用，否则自动退到本机已安装的浏览器

    配置成 chrome 但机器上只装了 Edge 时，yt-dlp 会直接报
    "could not find chrome cookies database"，导致所有解析失败。
    """
    local = Path(os.environ.get("LOCALAPPDATA", ""))
    roaming = Path(os.environ.get("APPDATA", ""))
    candidates = {
        "edge": local / "Microsoft" / "Edge" / "User Data",
        "chrome": local / "Google" / "Chrome" / "User Data",
        "firefox": roaming / "Mozilla" / "Firefox",
    }
    name = (configured or "").strip().lower()
    if name in candidates and candidates[name].exists():
        return name
    for fallback in ("edge", "chrome", "firefox"):
        if candidates[fallback].exists():
            return fallback
    return ""


class TiktokSpider(VideoSpider):
    """
    TikTok / Douyin 爬虫

    实现策略：yt-dlp 原生 extractor 已经能正确识别和下载 TikTok/Douyin，
    本爬虫仅做一层薄封装，把 URL 分类好交给 yt-dlp 处理，
    再把返回的 info_dict 统一成 VideoSpider 约定的 dict 格式。

    Trending（无关键词抓取）：
        TikTok 没有公开的 trending extractor，本爬虫通过三层降级链实现：
            Layer 1: curl_cffi + Web 端 API（/api/recommend/item_list/）
            Layer 2: yt-dlp tiktok:user 爬预设热门用户列表
            Layer 3: 返回空 + 报错
        语言分类：通过 region 参数（US/GB/DE/JP/...）实现按地区/语言分类。

    搜索能力：❌ 不支持关键词搜索（tiktok:tag/sound 在 yt-dlp 里标记为 BROKEN）。
    """

    PLATFORM = "tiktok"

    def __init__(self, **kwargs: Any):
        super().__init__(**kwargs)
        try:
            import yt_dlp
            self._ydlp = yt_dlp
        except ImportError:
            raise ImportError("yt-dlp 未安装，请先 pip install yt-dlp")
        # 初始化代理
        self._proxy = _get_proxy_from_config()
        # 初始化 curl_cffi（用于 trending Web API 调用）
        self._has_curl_cffi = False
        try:
            from curl_cffi import requests as cffi_requests
            self._cffi_requests = cffi_requests
            self._has_curl_cffi = True
        except ImportError:
            pass

        # ---------- 安全配置（防封核心）----------
        cfg = load_config()
        safety = cfg.get("tiktok_safety", {})
        self._request_delay_min: float = float(safety.get("request_delay_min", 3.0))
        self._request_delay_max: float = float(safety.get("request_delay_max", 5.0))
        self._daily_cap: int = int(safety.get("daily_cap", 50))
        self._daily_cap_enabled: bool = bool(safety.get("daily_cap_enabled", True))
        self._cookies_from_browser: str = safety.get("cookies_from_browser", "chrome")
        self._cookie_expire_threshold: int = int(safety.get("cookie_expire_threshold", 3))

        # ---------- 运行时安全状态 ----------
        self._safety_lock = threading.Lock()
        self._today = date.today()
        self._today_count = self._load_today_count()
        self._consecutive_failures = 0  # 连续 cookie 失效计数
        self._requests_since_last_sleep = 0

    # ==============================================================
    #  安全机制（节流 + 日限额 + Cookie 过期检测）
    # ==============================================================

    def _throttle(self):
        """请求节流：每次真实请求前随机 sleep 3-5s，模拟人类浏览速度"""
        delay = random.uniform(self._request_delay_min, self._request_delay_max)
        logger.debug(f"Tiktok 节流等待 {delay:.1f}s")
        time.sleep(delay)

    def _check_daily_cap(self) -> bool:
        """日限额检查：今天已爬 N 条，超过则返回 False"""
        if not self._daily_cap_enabled:
            return True
        today = date.today()
        if today != self._today:
            self._today = today
            self._today_count = 0
            self._save_today_count()
        if self._today_count >= self._daily_cap:
            logger.warning(
                f"⚠️ 今日 TikTok 采集已达上限 {self._daily_cap} 条，"
                f"明天再继续（或在 config.yaml 调整 daily_cap）"
            )
            return False
        return True

    def _bump_daily_count(self, n: int = 1):
        """成功采集到一条后，累加日计数"""
        with self._safety_lock:
            self._today_count += n
            self._save_today_count()

    def _check_cookie_health(self, success: bool):
        """
        Cookie 健康度检测：
        - 连续 _cookie_expire_threshold 次 yt-dlp 失败 → 判定 Cookie 过期
        - 成功则重置计数
        """
        if success:
            self._consecutive_failures = 0
            return
        self._consecutive_failures += 1
        if self._consecutive_failures >= self._cookie_expire_threshold:
            logger.warning(
                f"⚠️ 连续 {self._cookie_expire_threshold} 次 TikTok 请求失败 — "
                f"Cookie 可能已过期。\n"
                f"请：1) 打开 Chrome 访问 https://www.tiktok.com 确认已登录\n"
                f"     2) 如果已登录但仍失败，Chrome 完全关闭后重试\n"
                f"     3) 或在 config.yaml 把 cookies_from_browser 改成 \"edge\"/\"firefox\""
            )

    def _load_today_count(self) -> int:
        """从磁盘加载今日采集数（程序重启也不丢）"""
        try:
            from utils.path_helper import get_tmp_dir
            path = os.path.join(get_tmp_dir(), ".tiktok_daily_count.json")
            if os.path.exists(path):
                with open(path, encoding="utf-8") as f:
                    data = json.load(f)
                if data.get("date") == str(self._today):
                    return int(data.get("count", 0))
        except Exception:
            pass
        return 0

    def _save_today_count(self):
        """保存今日采集数到磁盘"""
        try:
            from utils.path_helper import get_tmp_dir
            os.makedirs(get_tmp_dir(), exist_ok=True)
            path = os.path.join(get_tmp_dir(), ".tiktok_daily_count.json")
            with open(path, "w", encoding="utf-8") as f:
                json.dump({"date": str(self._today), "count": self._today_count}, f)
        except Exception:
            pass

    @property
    def safety_status(self) -> Dict[str, Any]:
        """安全状态摘要（给外部查询）"""
        return {
            "proxy_configured": bool(self._proxy),
            "cookies_from_browser": self._cookies_from_browser,
            "today_collected": self._today_count,
            "daily_cap": self._daily_cap,
            "daily_cap_enabled": self._daily_cap_enabled,
            "request_delay_range": f"{self._request_delay_min}-{self._request_delay_max}s",
            "consecutive_failures": self._consecutive_failures,
            "cookie_status": "healthy" if self._consecutive_failures < self._cookie_expire_threshold else "possibly_expired",
        }

    # ==============================================================
    #  基类接口实现
    # ==============================================================

    def search(
        self,
        query: str,
        max_pages: int = 5,
        filter_languages: Optional[List] = None,
        **kwargs: Any,
    ) -> List[Dict[str, Any]]:
        """
        TikTok 无稳定公开搜索接口，search 方法不实现。

        建议：在 YouTube 上用同关键词搜索，或直接传入具体 TikTok URL 使用 crawl/get_video_info。
        """
        logger.warning(
            "TiktokSpider.search() 不支持关键词搜索 — "
            "tiktok:tag/sound 在 yt-dlp 里标记为 BROKEN。"
            "请改用 YouTube 爬虫同关键词搜索，或用 crawl_trending() 抓热门页，"
            "或直接用 crawl() 爬具体 TikTok URL / 用户主页 / 合集。"
        )
        return []

    def get_video_info(self, video_url: str) -> Optional[Dict[str, Any]]:
        """
        获取单个 TikTok/Douyin 视频元数据（不下载）

        内部已接入：请求节流 + Cookie 过期检测
        """
        if not _is_tiktok_url(video_url):
            logger.warning(f"非 TikTok/Douyin URL: {video_url}")
            return None
        if not self._check_daily_cap():
            return None

        ydl_opts = self._build_ydl_opts()
        self._throttle()
        try:
            with self._ydlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(video_url, download=False)
            if not info:
                self._check_cookie_health(success=False)
                return None
            self._check_cookie_health(success=True)
            self._bump_daily_count(1)
            return self._normalize(info)
        except Exception as e:
            msg = str(e)
            # 浏览器 cookie 库被占用 / 不存在时，降级为无 cookies 再试一次
            if ydl_opts.get("cookies_from_browser") and (
                "cookie" in msg.lower() or "database" in msg.lower()
            ):
                logger.warning(f"读取浏览器 cookies 失败，改为无 cookies 重试: {msg[:120]}")
                retry_opts = {k: v for k, v in ydl_opts.items() if k != "cookies_from_browser"}
                try:
                    with self._ydlp.YoutubeDL(retry_opts) as ydl:
                        info = ydl.extract_info(video_url, download=False)
                    if info:
                        self._check_cookie_health(success=True)
                        self._bump_daily_count(1)
                        return self._normalize(info)
                except Exception as e2:
                    msg = f"{msg} | retry: {e2}"
            logger.error(f"Tiktok get_video_info 失败: {msg}")
            self._check_cookie_health(success=False)
            return None

    def crawl(
        self,
        url: str,
        headers: Optional[Dict[str, str]] = None,
        params: Optional[Dict[str, Any]] = None,
        filter_languages: Optional[List] = None,
        use_buffer: bool = True,
    ) -> List[Dict[str, Any]]:
        """
        爬取 TikTok URL —— 自动识别是单视频 / 用户主页 / 合集 / 直播

        内部已接入：请求节流 + 日限额 + Cookie 过期检测
        """
        if not _is_tiktok_url(url):
            logger.warning(f"非 TikTok/Douyin URL: {url}")
            return []
        if not self._check_daily_cap():
            return []

        url_type = _classify_tiktok_url(url)
        logger.info(f"Tiktok crawl: url_type={url_type}, url={url[:80]}")

        ydl_opts = self._build_ydl_opts()
        results: List[Dict[str, Any]] = []
        self._throttle()
        try:
            with self._ydlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)
            if not info:
                self._check_cookie_health(success=False)
                return []

            self._check_cookie_health(success=True)

            if info.get("_type") == "playlist":
                entries = info.get("entries") or []
                for entry in entries:
                    if not entry:
                        continue
                    # 日限额检查（用户主页可能几百条）
                    if not self._check_daily_cap():
                        break
                    # playlist 里的 entry 可能只有 url 没有完整元数据
                    if entry.get("_type") == "url":
                        self._throttle()
                        try:
                            with self._ydlp.YoutubeDL({**ydl_opts, "extract_flat": False}) as ydl2:
                                full = ydl2.extract_info(entry["url"], download=False)
                                if full:
                                    results.append(self._normalize(full))
                                    self._bump_daily_count(1)
                        except Exception as e:
                            logger.warning(f"Tiktok entry 详情获取失败: {e}")
                            self._check_cookie_health(success=False)
                    else:
                        results.append(self._normalize(entry))
                        self._bump_daily_count(1)
            else:
                results.append(self._normalize(info))
                self._bump_daily_count(1)

            logger.info(f"Tiktok crawl 完成: {len(results)} 条")
            return results

        except Exception as e:
            logger.error(f"Tiktok crawl 失败: {e}")
            self._check_cookie_health(success=False)
            return []

    def parse(self, html: str, url: str) -> List[Dict[str, Any]]:
        """Tiktok 不解析 HTML（yt-dlp 原生处理 API 请求和签名）"""
        return []

    def get_channel_videos(
        self,
        channel_url: str,
        max_pages: int = 5,
        filter_languages: Optional[List] = None,
    ) -> List[Dict[str, Any]]:
        """
        获取 TikTok 用户主页所有视频

        TikTok 用户主页 URL 格式：
            https://www.tiktok.com/@username
            https://www.tiktok.com/@username?lang=zh-Hans-CN

        委托给 crawl() 处理，yt-dlp 会自动识别为用户主页并拉取全部视频。
        """
        return self.crawl(channel_url, filter_languages=filter_languages)

    # ==============================================================
    #  Trending（无关键词抓取）—— 三层降级链
    # ==============================================================

    def crawl_trending(
        self,
        region: Optional[str] = None,
        language: Optional[str] = None,
        max_videos: int = 50,
        **kwargs: Any,
    ) -> List[Dict[str, Any]]:
        """
        TikTok 热门页无关键词抓取。

        三层降级链：
            Layer 1: curl_cffi + Web 端 API（需要代理 + 浏览器 cookies）
            Layer 2: yt-dlp tiktok:user 爬预设热门用户列表（需要代理）
            Layer 3: 无代理 → 返回空 + 明确报错

        参数：
            region: 地区代码（如 US/GB/DE/JP/KR），决定抓哪个地区的热门内容
                    不传则抓全球热门
            language: 语言代码（如 en/de/ja），仅用于给爬虫结果打标签，
                     不传则根据 region 自动推断
            max_videos: 最多返回多少条视频

        返回：
            List[Dict] 标准化后的视频元数据列表
        """
        region_upper = (region or "").upper()

        if region_upper and region_upper not in TIKTOK_REGIONS:
            logger.warning(
                f"未知 TikTok 地区代码: {region_upper}，将尝试全球热门。"
                f"支持的地区: {', '.join(TIKTOK_REGIONS[:10])}..."
            )

        # region → language 自动推断
        effective_lang = language or (
            REGION_TO_LANGUAGE.get(region_upper, "")
        )

        logger.info(
            f"Tiktok crawl_trending: region={region_upper or 'GLOBAL'}, "
            f"language={effective_lang or 'auto'}, max={max_videos}, "
            f"proxy={'YES' if self._proxy else 'NO'}"
        )

        # ---- Layer 1: 代理 + curl_cffi Web API ----
        results = self._trending_via_web_api(
            region_upper, effective_lang, max_videos
        )
        if results:
            logger.info(f"Tiktok trending Layer 1 成功: {len(results)} 条")
            return results

        # ---- Layer 2: 代理 + 预设热门用户列表 ----
        results = self._trending_via_hot_users(
            region_upper, effective_lang, max_videos
        )
        if results:
            logger.info(f"Tiktok trending Layer 2 成功: {len(results)} 条")
            return results

        # ---- Layer 3: 无代理 → 明确报错 ----
        if not self._proxy:
            logger.error(
                "⚠️ TikTok 抓取失败：未检测到代理配置。\n"
                "TikTok 国际版对中国大陆 IP 硬墙（所有请求被重定向到 /about 页面）。\n"
                "请在 config.yaml 的 crawler.proxy 字段配置代理地址，例如：\n"
                "    crawler:\n      proxy: 'http://127.0.0.1:7890'\n"
                "配置代理后重启爬虫即可。"
            )
        else:
            logger.error(
                "⚠️ TikTok trending 抓取失败（两层降级均失败）。\n"
                "可能原因：代理不可用 / TikTok API 变更 / cookies 过期。\n"
                "建议：检查代理连通性，或尝试通过 cookies_from_browser 导入浏览器登录态。"
            )

        return []

    # --------------------------------------------------------------
    #  Layer 1: curl_cffi + Web 端 API
    # --------------------------------------------------------------

    def _trending_via_web_api(
        self,
        region: str,
        language: str,
        max_videos: int,
    ) -> List[Dict[str, Any]]:
        """
        通过 TikTok Web 端推荐 API 抓热门内容。

        使用 curl_cffi 模拟浏览器，请求 /api/recommend/item_list/ endpoint。
        需要代理（绕过 IP 墙）和基础 cookies。
        """
        if not self._proxy or not self._has_curl_cffi:
            logger.debug("Layer 1 跳过: 无代理或无 curl_cffi")
            return []
        if not self._check_daily_cap():
            return []

        try:
            self._throttle()
            session = self._cffi_requests.Session()
            session.headers.update({
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/125.0.0.0 Safari/537.36"
                ),
                "Accept-Language": f"{language}-US,{language};q=0.9,en;q=0.8",
            })

            # 先访问首页拿基础 cookies（ttwid 等）
            session.get(
                "https://www.tiktok.com/",
                impersonate="chrome124",
                proxy=self._proxy,
                timeout=15,
                allow_redirects=True,
            )

            # 调推荐 API
            params = {
                "aid": "1988",
                "count": min(max_videos, 30),  # 单页最多 30
                "version_code": "170400",
                "version_name": "17.4.0",
                "device_platform": "webapp",
                "os": "windows",
                "region": region or "US",
                "language": language or "en",
            }
            r = session.get(
                "https://www.tiktok.com/api/recommend/item_list/",
                params=params,
                impersonate="chrome124",
                proxy=self._proxy,
                timeout=15,
            )

            # 检查是不是被墙了（返回 HTML /about 页）
            if not r.text.strip().startswith("{"):
                logger.warning("Layer 1 失败: 返回非 JSON（可能仍被墙）")
                return []

            data = r.json()
            items = data.get("items") or data.get("itemList") or []
            if not items:
                sc = data.get("status_code", "?")
                logger.warning(f"Layer 1 API 返回空 items (status_code={sc})")
                return []

            logger.info(f"Layer 1 API 返回 {len(items)} 条原始数据")

            results: List[Dict[str, Any]] = []
            for item in items[:max_videos]:
                try:
                    parsed = self._parse_web_item(item, region, language)
                    if parsed:
                        results.append(parsed)
                except Exception as e:
                    logger.debug(f"Layer 1 item 解析跳过: {e}")

            return results

        except Exception as e:
            logger.warning(f"Layer 1 异常: {type(e).__name__}: {e}")
            return []

    def _parse_web_item(
        self,
        item: Dict[str, Any],
        region: str,
        language: str,
    ) -> Optional[Dict[str, Any]]:
        """把 TikTok Web API 的 item 字段转成统一 dict"""
        aweme_info = item.get("awemeInfo") or item.get("itemInfo") or item
        aweme_id = aweme_info.get("awemeId") or aweme_info.get("id")
        if not aweme_id:
            return None

        author = aweme_info.get("authorInfo") or {}
        video_info = aweme_info.get("videoInfo") or aweme_info.get("video") or {}

        uploader_name = author.get("nickname") or author.get("uniqueId") or ""
        uploader_id = author.get("uniqueId") or author.get("secUid") or author.get("id") or ""

        desc = aweme_info.get("desc") or aweme_info.get("title") or ""

        # thumbnail
        cover = video_info.get("cover") or video_info.get("dynamicCover") or {}
        thumb_list = cover.get("urlList") or []
        thumbnail = thumb_list[0] if thumb_list else ""

        # views
        stats = aweme_info.get("stats") or {}
        views = stats.get("playCount") or stats.get("diggCount") or 0

        # duration
        duration_ms = video_info.get("duration") or 0
        duration_seconds = duration_ms / 1000 if duration_ms else 0
        duration_str = self._format_duration(int(duration_seconds)) if duration_seconds else ""

        video_url = f"https://www.tiktok.com/@{uploader_name}/video/{aweme_id}" if uploader_name else ""

        return {
            "source_url": video_url,
            "title": desc[:100],
            "description": desc,
            "thumbnail": thumbnail,
            "duration": duration_str,
            "views": views,
            "author": uploader_name,
            "language": language,
            "channel_id": uploader_id,
            "channel_name": uploader_name,
            "published_at": "",
            "yt_category_id": None,
            "platform": self.PLATFORM,
            "format_id": "",
            "is_short": True,  # TikTok 全是 short
            "tags_raw": aweme_info.get("hashtagNameList") or [],
            # trending 特有字段
            "trending_region": region,
        }

    # --------------------------------------------------------------
    #  Layer 2: 预设热门用户列表 + yt-dlp tiktok:user
    # --------------------------------------------------------------

    def _trending_via_hot_users(
        self,
        region: str,
        language: str,
        max_videos: int,
    ) -> List[Dict[str, Any]]:
        """
        预设一批各地区的 TikTok 头部创作者，用 yt-dlp 的 tiktok:user 逐个爬。

        这个方案不完美（预设名单不是实时热门），但稳定可靠，
        在代理可用但签名库不可用时作为 fallback。
        """
        # 每个地区预设几个头部创作者（@username）
        HOT_USERS = {
            "US": [
                "charlidamelio", "khaby.lame", "bellapoarch",
                "addisonrae", "mrbeast", "mark.rober", "jimmyfallon",
            ],
            "GB": [
                "khaby.lame", "charlidamelio", "bellapoarch", "mrbeast",
            ],
            "DE": [
                "felipecastillo", "isaac.longsong", "marc.010",
            ],
            "FR": [
                "squeezie", "amixem", "cyprien", "misterv",
            ],
            "JP": [
                "junya1gou", "koki.25", "kaori_o_natsu",
            ],
            "KR": [
                "noel.campbell777", "ox_zung", "sunghoo_jung",
            ],
            "BR": [
                "wagnermouraa", "nathanzinho", "luqueta",
            ],
            "ES": [
                "elrubiusomg", "auronplay", "mangelrogel",
            ],
        }

        users = HOT_USERS.get(region or "", HOT_USERS.get("US", []))
        if not users:
            return []

        ydl_opts = self._build_ydl_opts()
        collected: List[Dict[str, Any]] = []

        per_user = max(1, max_videos // len(users))

        for username in users:
            if len(collected) >= max_videos:
                break
            if not self._check_daily_cap():
                break

            self._throttle()
            user_url = f"https://www.tiktok.com/@{username}"
            logger.info(f"Layer 2 爬用户: {username}")

            try:
                with self._ydlp.YoutubeDL(ydl_opts) as ydl:
                    info = ydl.extract_info(user_url, download=False)
                if not info:
                    self._check_cookie_health(success=False)
                    continue

                self._check_cookie_health(success=True)

                entries = []
                if info.get("_type") == "playlist":
                    entries = info.get("entries") or []
                else:
                    entries = [info]

                count = 0
                for entry in entries:
                    if len(collected) >= max_videos or count >= per_user:
                        break
                    if not self._check_daily_cap():
                        break
                    if not entry or entry.get("_type") == "url":
                        continue
                    normalized = self._normalize(entry)
                    if normalized:
                        normalized["trending_region"] = region or "US"
                        collected.append(normalized)
                        self._bump_daily_count(1)
                        count += 1

            except Exception as e:
                logger.warning(f"Layer 2 用户 {username} 爬取失败: {e}")
                self._check_cookie_health(success=False)

        logger.info(f"Layer 2 爬取完成: {len(collected)} 条")
        return collected

    # ==============================================================
    #  内部辅助
    # ==============================================================

    def _build_ydl_opts(self) -> Dict[str, Any]:
        """构建 yt-dlp 通用 opts（含代理 + cookies + 安全配置）"""
        opts: Dict[str, Any] = {
            "quiet": True,
            "no_warnings": True,
            "skip_download": True,
            "geo_bypass": True,
            "geo_bypass_country": "US",
            # yt-dlp 内部请求节流（每次 yt-dlp 自己发请求前也 sleep 一下）
            "sleep_interval": self._request_delay_min,
            "max_sleep_interval": self._request_delay_max,
        }
        if self._proxy:
            opts["proxy"] = self._proxy
        # cookies_from_browser 让 yt-dlp 从浏览器拿 sid_tt / msToken / ttwid
        # 可选值: "chrome" / "edge" / "firefox" / ""（空则不启用）
        if self._cookies_from_browser:
            browser = _detect_cookie_browser(self._cookies_from_browser)
            if browser:
                opts["cookies_from_browser"] = browser
            else:
                logger.warning(
                    "未找到可用的浏览器 cookie 库，本次不使用 cookies（TikTok/抖音可能要求登录态）"
                )
        return opts

    def _normalize(self, info: Dict[str, Any]) -> Dict[str, Any]:
        """yt-dlp info_dict → VideoSpider 统一 dict"""
        source_url = info.get("webpage_url") or info.get("url", "")
        channel_id = info.get("uploader_id") or info.get("channel_id") or info.get("creator")
        channel_name = info.get("uploader") or info.get("channel") or info.get("creator")

        description = info.get("description") or info.get("caption") or ""

        tags = info.get("tags") or []
        if isinstance(tags, str):
            tags = [t.strip() for t in tags.split(",") if t.strip()]

        duration = info.get("duration") or 0
        duration_str = self._format_duration(int(duration)) if duration else ""

        return {
            "source_url": source_url,
            "title": info.get("title", ""),
            "description": description,
            "thumbnail": info.get("thumbnail", ""),
            "duration": duration_str,
            "views": info.get("view_count") or 0,
            "author": channel_name or info.get("uploader") or "",
            "language": info.get("language") or info.get("uploader_language") or "",
            "channel_id": channel_id,
            "channel_name": channel_name,
            "published_at": info.get("upload_date", ""),
            "yt_category_id": info.get("categories", [None])[0] if info.get("categories") else None,
            "platform": self.PLATFORM,
            "format_id": info.get("format_id", ""),
            "is_short": self._looks_like_short(info),
            "tags_raw": tags,
        }

    @staticmethod
    def _format_duration(seconds: int) -> str:
        h, rem = divmod(seconds, 3600)
        m, s = divmod(rem, 60)
        if h > 0:
            return f"{h}:{m:02d}:{s:02d}"
        return f"{m}:{s:02d}"

    @staticmethod
    def _looks_like_short(info: Dict[str, Any]) -> bool:
        duration = info.get("duration") or 0
        return duration > 0 and duration <= 180
