"""
视频下载模块

封装 yt-dlp 下载逻辑，支持多线程下载、进度回调、失败重试。

功能特性：
    1. yt-dlp 下载封装
    2. 外置 bin 路径适配
    3. 下载进度回调
    4. 多线程下载池
    5. 下载失败重试逻辑
    6. 按语言/分类自动存储到对应目录
"""

import os
import glob
import time
import threading
from utils.thread_spawn import spawn  # AUDIT-0033
import re
import subprocess
from typing import Optional, Dict, Any, Callable, List
from dataclasses import dataclass

from utils.enums import TaskStatus, LanguageType, VideoCategory
from utils.logger import get_download_logger
from utils.path_helper import get_ytdlp_path, get_output_dir, get_tmp_dir, get_ffmpeg_path
from utils.config_loader import get_download_config, load_config
from utils.file_sort import get_file_sorter


logger = get_download_logger()


class PermanentDownloadError(Exception):
    """永久下载失败（视频不可用/地区锁/版权等），重试也不会成功"""
    pass


def _probe_stream_kinds(file_path: str) -> Optional[set]:
    """探测媒体文件包含哪些流类型（挡纯音频/合并不完整产物的关键闸门）。

    Returns:
        {"video", "audio", ...} = ffprobe 明确解析出的流类型集合
        None                     = 探测工具不可用或结果不确定，由调用方决定是否放行

    优先用 ffprobe 机器可读输出（可靠、无本地化歧义）；
    ffprobe 不可用时退回 ffmpeg -i 解析 stderr。子进程异常各重试 1 次。
    """
    ffmpeg_exe = str(get_ffmpeg_path()) if get_ffmpeg_path() else "ffmpeg"
    # ★ 只能替换文件名：路径目录本身也叫 bin\ffmpeg，全局 replace 会把目录改坏
    ffprobe_exe = os.path.join(
        os.path.dirname(ffmpeg_exe),
        os.path.basename(ffmpeg_exe).replace("ffmpeg", "ffprobe"),
    )

    # ---- 1) ffprobe：逐流输出 codec_type（video/audio/subtitle/data） ----
    for attempt in range(2):
        try:
            probe = subprocess.run(
                [ffprobe_exe, "-v", "error",
                 "-show_entries", "stream=codec_type", "-of", "csv=p=0", file_path],
                capture_output=True, encoding="utf-8", errors="replace",
                timeout=30,
            )
            if probe.returncode == 0:
                kinds = {ln.strip() for ln in (probe.stdout or "").splitlines() if ln.strip()}
                if kinds:
                    return kinds
                # 有正常输出但为空 = 容器里一条流都没有（纯音频时会输出 "audio"）
                return set()
            # rc!=0：文件损坏/不可读，再确认一次，避免偶发 IO 抖动误判
            if attempt == 1:
                return set()
        except Exception:
            break  # ffprobe 可能不存在，转 ffmpeg 兜底
        time.sleep(0.5)

    # ---- 2) ffmpeg -i stderr 正则兜底 ----
    try:
        probe = subprocess.run(
            [ffmpeg_exe, "-i", file_path],
            capture_output=True, encoding="utf-8", errors="replace",
            timeout=30,
        )
        stderr = probe.stderr or ""
        if re.search(r"(Duration|Stream\s+#)", stderr):
            kinds = set()
            if re.search(r"Stream\s+#\d+:\d+.*:\s*Video:", stderr):
                kinds.add("video")
            if re.search(r"Stream\s+#\d+:\d+.*:\s*Audio:", stderr):
                kinds.add("audio")
            return kinds
    except Exception:
        pass
    return None


def _probe_has_video_stream(file_path: str) -> Optional[bool]:
    """是否明确含视频流。False=明确无视频流；None=探测工具不可用/不确定。"""
    kinds = _probe_stream_kinds(file_path)
    if kinds is None:
        return None
    return "video" in kinds


def _site_headers(url: str, base: Dict[str, str]) -> Dict[str, str]:
    """按平台微调 yt-dlp 请求头

    YouTube 伪装头里带 Referer: youtube.com，套在 TikTok/抖音请求上会被判异常，
    因此非 YouTube 链接去掉 Referer。
    """
    try:
        from utils.video_url import detect_video_site
        if detect_video_site(url) == "tiktok":
            headers = dict(base)
            headers.pop("Referer", None)
            return headers
    except Exception:
        pass
    return {**base}


@dataclass
class DownloadProgress:
    """下载进度信息"""
    video_id: str
    url: str
    title: str
    downloaded_bytes: int
    total_bytes: int
    progress: str
    speed: str
    eta: str
    status: str


@dataclass
class DownloadResult:
    """下载结果"""
    video_id: str
    url: str
    success: bool
    file_path: Optional[str] = None
    local_path: Optional[str] = None
    error_message: Optional[str] = None
    duration: Optional[float] = None
    skipped: bool = False
    # ---- 自动检测字段（供后续流水线使用） ----
    language: Optional[Any] = None   # LanguageType
    category: Optional[Any] = None   # VideoCategory
    channel: Optional[str] = None    # 频道名（已 sanitize）
    title: str = ""                  # 解析到的真实标题
    description: str = ""            # 视频简介
    thumbnail_url: Optional[str] = None  # 封面 URL


class VideoDownloader:
    """
    视频下载器
    
    封装 yt-dlp 下载逻辑，支持进度回调和失败重试。
    """
    
    def __init__(self) -> None:
        """初始化视频下载器"""
        full_cfg = load_config()
        config = get_download_config(full_cfg)
        self._max_threads = config.get("max_download_thread", 3)
        self._ytdlp_path = get_ytdlp_path()
        self._output_dir = get_output_dir()
        self._tmp_dir = get_tmp_dir()
        self._downloading = set()
        self._lock = threading.Lock()
        # 代理：优先下载段 proxy，其次 crawler 段 proxy
        self._proxy: str = ""
        try:
            p = (config.get("proxy") or "").strip()
            if not p:
                p = (full_cfg.get("crawler", {}).get("proxy") or "").strip()
            self._proxy = p
        except Exception:
            self._proxy = ""
        logger.info(
            "视频下载器初始化完成"
            + (f"  proxy={self._proxy}" if self._proxy else "")
        )
    
    @staticmethod
    def _build_subtitleslangs(
        language: Optional[LanguageType] = None
    ) -> List[str]:
        """
        构建字幕语言列表，优先包含目标语言
        
        对于非英语视频，只下载源语言字幕，不强制下载英文字幕
        （避免 YouTube 限流英文字幕下载导致整个下载失败）。
        
        Args:
            language: 目标语言类型
            
        Returns:
            yt-dlp 字幕语言代码列表
        """
        if language is not None:
            lang_code = language.value
            lang_regions = {
                "de": ["de-DE"],
                "fr": ["fr-FR"],
                "es": ["es-ES"],
                "en": ["en-US", "en-GB"],
                "zh": ["zh-CN", "zh-TW"],
                "ja": ["ja-JP"],
                "ko": ["ko-KR"],
                "ru": ["ru-RU"],
                "it": ["it-IT"],
            }
            langs_to_add = [lang_code]
            langs_to_add.extend(lang_regions.get(lang_code, []))
            
            result = []
            for lang in langs_to_add:
                if lang not in result:
                    result.append(lang)
            
            # 仅对英语视频添加英语变体，非英语视频不强制下载英文字幕
            if lang_code == "en":
                for lang in ["en-US", "en-GB"]:
                    if lang not in result:
                        result.append(lang)
            
            return result
        
        # 未指定语言时默认英语
        return ["en", "en-US"]

    @staticmethod
    def _detect_browser_cookie() -> Optional[str]:
        """智能探测本机浏览器 cookies，返回 yt-dlp `cookies_from_browser` 值。

        先文件系统快速检查，再用 yt-dlp extract_cookies_from_browser() 实际读一次
        验证可用性（浏览器运行时 DB 被锁的话直接跳过）。

        探测顺序：Edge → Chrome → Brave → Firefox
        """
        import os

        candidates = [
            ("edge", os.path.expandvars(r"%LOCALAPPDATA%\Microsoft\Edge\User Data"), ["Default", "Profile 1"]),
            ("chrome", os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\User Data"), ["Default", "Profile 1"]),
            ("brave", os.path.expandvars(r"%LOCALAPPDATA%\BraveSoftware\Brave-Browser\User Data"), ["Default", "Profile 1"]),
            ("firefox", os.path.expandvars(r"%APPDATA%\Mozilla\Firefox\Profiles"), None),
        ]

        # 第一轮：文件系统快速过滤
        available_browsers: List[str] = []
        for browser, ud_path, profiles in candidates:
            if not os.path.exists(ud_path):
                continue
            found = False
            if profiles:
                for p in profiles:
                    db = os.path.join(ud_path, p, "Cookies")
                    db2 = os.path.join(ud_path, p, "Network", "Cookies")
                    if os.path.exists(db) or os.path.exists(db2):
                        found = True
                        break
            else:
                for entry in os.listdir(ud_path):
                    if os.path.isdir(os.path.join(ud_path, entry)):
                        db = os.path.join(ud_path, entry, "cookies.sqlite")
                        if os.path.exists(db):
                            found = True
                            break
            if found:
                available_browsers.append(browser)

        # 第二轮：实际尝试 extract（跳过被锁的）
        if available_browsers:
            try:
                from yt_dlp.cookies import extract_cookies_from_browser
                for browser in available_browsers:
                    try:
                        jar = extract_cookies_from_browser(browser)
                        # 至少要有几个 cookie 才算有效
                        if len(list(jar)) > 0:
                            logger.info(f"cookies_from_browser 探测: {browser} 可用 ({len(list(jar))} cookies)")
                            return browser
                        else:
                            logger.debug(f"cookies_from_browser 探测: {browser} 读到 0 cookies，跳过")
                    except Exception as e:
                        logger.debug(f"cookies_from_browser 探测: {browser} 失败 ({e})，浏览器可能正在运行")
            except Exception:
                pass

        return None

    @staticmethod
    def _pick_thumb_url(info: Dict[str, Any]) -> Optional[str]:
        """从 yt-dlp info 中选最高清的封面 URL

        优先用 info['thumbnail']（通常是 maxresdefault.jpg），
        如果没有则遍历 thumbnails 列表找分辨率最高的。
        """
        if info.get("thumbnail"):
            return info["thumbnail"]
        thumbs = info.get("thumbnails") or []
        best_url = None
        best_area = 0
        for t in thumbs:
            w = t.get("width") or 0
            h = t.get("height") or 0
            area = w * h
            url = t.get("url")
            if url and area > best_area:
                best_area = area
                best_url = url
        return best_url

    @staticmethod
    def _youtube_thumb_url(video_id: str) -> Optional[str]:
        """通过 video_id 直接构建 YouTube 封面 URL（无需调 yt-dlp）

        按分辨率从高到低尝试：maxresdefault → hqdefault → mqdefault → default
        """
        candidates = [
            f"https://i.ytimg.com/vi/{video_id}/maxresdefault.jpg",
            f"https://i.ytimg.com/vi/{video_id}/hqdefault.jpg",
            f"https://i.ytimg.com/vi/{video_id}/mqdefault.jpg",
            f"https://i.ytimg.com/vi/{video_id}/default.jpg",
        ]
        import requests
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
        for url in candidates:
            try:
                resp = requests.head(url, timeout=10, headers=headers, allow_redirects=True)
                if resp.status_code == 200:
                    return url
            except Exception:
                continue
        return None

    @staticmethod
    def _download_thumbnail(
        video_path: str,
        info: Optional[Dict[str, Any]] = None,
        video_id: Optional[str] = None,
    ) -> None:
        """下载视频封面，保存为视频同名 .jpg

        两种获取 URL 的方式（自动选择第一个可用的）：
          1. 从 yt-dlp info['thumbnail'] / info['thumbnails'] 取
          2. 通过 video_id 构造 YouTube 封面 URL（无需调 yt-dlp，更快）
        失败不影响主流程（封面是附加物）。
        """
        base, _ = os.path.splitext(video_path)
        thumb_path = base + ".jpg"
        if os.path.exists(thumb_path) and os.path.getsize(thumb_path) > 1024:
            return

        thumb_url = None
        if info:
            thumb_url = VideoDownloader._pick_thumb_url(info)
        if not thumb_url and video_id:
            thumb_url = VideoDownloader._youtube_thumb_url(video_id)
        if not thumb_url:
            return

        try:
            import requests
            resp = requests.get(thumb_url, timeout=15, headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            })
            if resp.status_code == 200 and len(resp.content) > 512:
                with open(thumb_path, "wb") as f:
                    f.write(resp.content)
                logger.info(f"封面下载完成: {thumb_path} [{len(resp.content)//1024}KB]")
            else:
                logger.warning(f"封面下载失败: HTTP {resp.status_code}, size={len(resp.content)}")
        except Exception as e:
            logger.warning(f"封面下载异常（不影响主流程）: {e}")

    def _find_video_in_output(self, video_id: str) -> Optional[str]:
        """在 output 文件夹中查找已下载的视频文件
        
        通过遍历 output 目录，查找文件名包含 video_id 的视频文件。
        支持多种可能的目录结构。
        
        Args:
            video_id: 视频 ID
            
        Returns:
            找到的视频文件路径，未找到返回 None
        """
        output_dir = str(self._output_dir)
        
        # 支持的视频扩展名
        video_extensions = ['.mp4', '.mkv', '.webm', '.flv', '.avi', '.mov', '.m4v']
        
        try:
            # 策略1: 查找以 video_id 命名的文件夹
            # output/**/video_id/ 目录结构
            id_dir_patterns = [
                os.path.join(output_dir, "**", video_id),
                os.path.join(output_dir, "**", f"*{video_id}*"),
            ]
            
            for pattern in id_dir_patterns:
                try:
                    matches = glob.glob(pattern, recursive=True)
                    for match in matches:
                        if os.path.isdir(match):
                            # 在该文件夹内查找视频文件
                            for ext in video_extensions:
                                video_files = glob.glob(os.path.join(match, f"*{ext}"))
                                for vf in video_files:
                                    if os.path.isfile(vf) and os.path.getsize(vf) > 0:
                                        logger.info(f"找到已下载视频: {vf}")
                                        return vf
                except Exception:
                    pass
            
            # 策略2: 直接在 output 目录下搜索文件名包含 video_id 的视频文件
            # 可能是 output/xxx_video_id_xxx.mp4 或 output/**/video_id_xxx.mp4
            for ext in video_extensions:
                # 匹配 output 目录下所有视频文件
                search_patterns = [
                    os.path.join(output_dir, "**", f"*{video_id}*{ext}"),
                ]
                
                for pattern in search_patterns:
                    try:
                        matches = glob.glob(pattern, recursive=True)
                        for match in matches:
                            if os.path.isfile(match) and os.path.getsize(match) > 0:
                                # 排除缩略图和临时文件
                                if not any(x in match.lower() for x in ['.thumb', '.tmp', '.part', '.ytdl']):
                                    logger.info(f"找到已下载视频: {match}")
                                    return match
                    except Exception:
                        pass
            
            logger.info(f"在 output 目录中未找到视频: {video_id}")
            return None
            
        except Exception as e:
            logger.error(f"搜索已下载视频时出错: video_id={video_id}, error={e}")
            return None
    
    def get_video_metadata(self, url: str, video_id: str) -> Dict[str, Any]:
        """仅提取视频元数据（不下载），供 GUI 预览标题/简介/时长

        返回 dict 字段：title, description, duration, channel, thumbnail_url, language
        失败时返回空 dict。
        """
        import yt_dlp
        from utils.path_helper import get_cookies_file_path
        from utils.ytdlp_common import YTDLP_YOUTUBE_HEADERS
        from utils.language_check import detect_language_from_info

        _cookies_file = str(get_cookies_file_path())

        probe_opts: Dict[str, Any] = {
            "quiet": True, "noplaylist": True, "no_warnings": True,
            "ignoreerrors": True, "extract_flat": False, "skip_download": True,
            "geo_bypass": True, "geo_bypass_country": "US",
            "extractor_args": {"youtube": {"player_client": ["android", "web_embedded"]}},
            "http_headers": _site_headers(url, YTDLP_YOUTUBE_HEADERS),
        }
        if os.path.exists(_cookies_file) and os.path.getsize(_cookies_file) > 100:
            probe_opts["cookies"] = _cookies_file
        try:
            _browser = self._detect_browser_cookie()
            if _browser:
                probe_opts["cookies_from_browser"] = _browser
        except Exception:
            pass

        info: Optional[dict] = None
        try:
            with yt_dlp.YoutubeDL(probe_opts) as probe_ydl:
                info = probe_ydl.extract_info(url, download=False)
        except Exception as e:
            logger.warning(f"[元数据] 提取失败: {e}")
            return {}

        if not isinstance(info, dict):
            return {}

        lang = detect_language_from_info(info)
        lang_code = getattr(lang, "value", str(lang)) if lang else "auto"

        return {
            "title": str(info.get("title") or "").strip(),
            "description": str(info.get("description") or "").strip(),
            "duration": float(info.get("duration") or 0),
            "channel": str(
                info.get("channel") or info.get("uploader")
                or info.get("channel_name") or info.get("uploader_name") or ""
            ).strip(),
            "thumbnail_url": self._pick_thumb_url(info),
            "language": lang_code,
        }

    def download_video(
        self,
        url: str,
        video_id: str,
        title: str = "",
        language: Optional[LanguageType] = None,
        category: Optional[VideoCategory] = None,
        output_path: Optional[str] = None,
        progress_callback: Optional[Callable[[DownloadProgress], None]] = None,
        max_retries: int = 3,
        min_duration: Optional[float] = None,
        max_duration: Optional[float] = None,
        format_selector: Optional[str] = None,
        overwrite: bool = False,
    ) -> DownloadResult:
        """
        下载单个视频（含视频查重机制）
        
        在 output 文件夹中检查是否已存在对应 video_id 的视频文件，
        如果存在则跳过下载。
        
        Args:
            url: 视频 URL
            video_id: 视频 ID
            title: 视频标题（用于生成文件名）
            language: 语言类型（用于自动选择存储目录）
            category: 视频分类（用于自动选择存储目录）
            output_path: 输出路径（可选，如果提供则覆盖语言/分类目录）
            progress_callback: 进度回调函数
            max_retries: 最大重试次数
            min_duration: 最小视频时长（秒），默认90秒（1分30秒）
            max_duration: 最大视频时长（秒），默认300秒（5分钟）
            
        Returns:
            DownloadResult 下载结果
        """
        if output_path is None:
            file_sorter = get_file_sorter()
            effective_lang = language or None  # None 时走默认 other 目录
            # get_video_dir 要求 LanguageType，language=None 时手动构造路径
            if effective_lang is not None:
                output_path = file_sorter.get_video_dir(effective_lang, category, video_id)
            else:
                base = file_sorter.get_output_root()
                output_path = os.path.join(base, "other", video_id)
                os.makedirs(output_path, exist_ok=True)
            logger.info(f"自动选择输出目录: {output_path}")
        
        # 视频查重检查：overwrite=True 时跳过
        existing_video_path = None if overwrite else self._find_video_in_output(video_id)
        if existing_video_path:
            # ★ 历史缓存必须同样通过视频流校验：早期缺陷版本可能把纯音频 webm 误归档，
            # 若直接复用会一路跑到烧录才失败。确认无视频流则删除残留，重新下载。
            if _probe_has_video_stream(existing_video_path) is False:
                logger.warning(
                    f"命中的历史缓存无视频流（疑似旧版纯音频误归档），删除后重新下载: "
                    f"{existing_video_path}"
                )
                try:
                    os.remove(existing_video_path)
                except Exception as e:
                    logger.error(f"删除无效缓存失败，中止下载: {e}")
                    return DownloadResult(
                        video_id=video_id, url=url, success=False,
                        error_message=f"历史缓存无视频流且删除失败: {existing_video_path}",
                    )
                existing_video_path = None
        if existing_video_path:
            logger.info(f"视频已存在于 output 目录，跳过下载: {video_id}")
            self._download_thumbnail(video_path=existing_video_path, video_id=video_id)
            return DownloadResult(
                video_id=video_id,
                url=url,
                file_path=existing_video_path,
                local_path=existing_video_path,
                success=True,
                skipped=True,
                error_message="视频已存在于 output 目录，跳过下载"
            )
        
        with self._lock:
            if video_id in self._downloading:
                logger.warning(f"视频 {video_id} 正在下载中，跳过")
                return DownloadResult(
                    video_id=video_id,
                    url=url,
                    success=False,
                    error_message="视频正在下载中"
                )
            self._downloading.add(video_id)
        
        try:
            last_error_msg = f"下载失败，已达最大重试次数 {max_retries}"
            # ★ 预取缓存：首轮成功预取的 info 在重试间复用，避免每轮重试双发
            # extract_info 放大 YouTube 限流面；预取失败不缓存（下轮仍重试预取）
            prefetch_cache: Dict[str, Any] = {}
            for attempt in range(max_retries):
                try:
                    return self._do_download(url, video_id, title, language, category, output_path, progress_callback, min_duration, max_duration, format_selector, overwrite, prefetch_cache)
                except PermanentDownloadError as e:
                    # 永久失败（视频不可用/地区锁/版权等）：不重试，直接返回
                    logger.warning(f"下载永久失败（不重试）: {video_id}, error={e}")
                    return DownloadResult(
                        video_id=video_id,
                        url=url,
                        success=False,
                        error_message=str(e)
                    )
                except Exception as e:
                    last_error_msg = str(e)
                    logger.warning(f"下载失败 (尝试 {attempt + 1}/{max_retries}): {video_id}, error={e}")
                    if attempt < max_retries - 1:
                        time.sleep(2 ** attempt)

            return DownloadResult(
                video_id=video_id,
                url=url,
                success=False,
                error_message=last_error_msg
            )
            
        finally:
            with self._lock:
                self._downloading.discard(video_id)
    
    def _do_download(
        self,
        url: str,
        video_id: str,
        title: str = "",
        language: Optional[LanguageType] = None,
        category: Optional[VideoCategory] = None,
        output_path: Optional[str] = None,
        progress_callback: Optional[Callable[[DownloadProgress], None]] = None,
        min_duration: Optional[float] = None,
        max_duration: Optional[float] = None,
        format_selector: Optional[str] = None,
        overwrite: bool = False,
        prefetch_cache: Optional[Dict[str, Any]] = None,
    ) -> DownloadResult:
        """执行实际下载（三阶段法）：
            阶段1：预取 info → 自动补齐 language/category/channel/title
            阶段2：实际下载到 tmp 目录
            阶段3：用 FileSorter 归档到 output/<lang>/<cat>/<channel>/<id>/
        """
        import yt_dlp
        from utils.language_check import detect_language_from_info
        from utils.ytdlp_common import YTDLP_YOUTUBE_HEADERS
        from core.classify import classify_video

        # ========== 阶段1：预取元数据 ==========
        from utils.path_helper import get_cookies_file_path
        _cookies_file = str(get_cookies_file_path())

        probe_opts: Dict[str, Any] = {
            "quiet": True, "noplaylist": True, "no_warnings": True,
            "ignoreerrors": True, "extract_flat": False, "skip_download": True,
            "geo_bypass": True, "geo_bypass_country": "US",
            "extractor_args": {"youtube": {"player_client": ["android", "web_embedded"]}},
            "http_headers": _site_headers(url, YTDLP_YOUTUBE_HEADERS),
        }
        if os.path.exists(_cookies_file) and os.path.getsize(_cookies_file) > 100:
            probe_opts["cookies"] = _cookies_file
        # cookies_from_browser 也带上
        try:
            _browser = self._detect_browser_cookie()
            if _browser:
                probe_opts["cookies_from_browser"] = _browser
        except Exception:
            pass

        info: Optional[dict] = None
        # ★ 复用首轮预取结果（0085）：重试不再双发 extract_info；预取失败不缓存，下轮仍重试
        if prefetch_cache is not None and prefetch_cache.get("info"):
            info = prefetch_cache["info"]
            logger.info("[下载] 复用首轮预取元数据（重试不重发 extract_info）")
        else:
            try:
                with yt_dlp.YoutubeDL(probe_opts) as probe_ydl:
                    info = probe_ydl.extract_info(url, download=False)
                if info and prefetch_cache is not None:
                    prefetch_cache["info"] = info
            except Exception as e:
                logger.warning(f"[下载] 预取元数据失败（不放弃下载）: {e}")
                info = None

        # --- 1a. 自动补齐 language（显式指定优先，否则从 info/标题/字幕识别）---
        resolved_language = language
        if resolved_language is None and info:
            resolved_language = detect_language_from_info(info)
            logger.info(
                f"[下载] 自动检测语言: "
                f"{getattr(resolved_language, 'display_name', resolved_language)}"
            )
        if resolved_language is None:
            resolved_language = LanguageType.ENGLISH  # 最终兜底：不再落入 other

        # --- 1b. 自动补齐 title + channel + description + thumbnail ---
        resolved_title = (title or "").strip()
        channel_name: Optional[str] = None
        resolved_description: str = ""
        resolved_thumbnail: Optional[str] = None
        if isinstance(info, dict):
            if not resolved_title:
                resolved_title = str(info.get("title") or "").strip()
            for k in ("channel", "uploader", "channel_name", "uploader_name"):
                v = info.get(k)
                if v:
                    channel_name = str(v).strip() or None
                    if channel_name:
                        break
            resolved_description = str(info.get("description") or "").strip()
            resolved_thumbnail = self._pick_thumb_url(info)

        # --- 1c. 自动补齐 category ---
        resolved_category = category
        if resolved_category is None and (resolved_title or isinstance(info, dict)):
            desc = str(info.get("description") or "") if isinstance(info, dict) else ""
            resolved_category = classify_video(
                resolved_title or "Untitled",
                desc or None,
            )
            logger.info(
                f"[下载] 自动分类: "
                f"{getattr(resolved_category, 'display_name', resolved_category)} "
                f"← title='{(resolved_title or '')[:60]}'"
            )
        if resolved_category is None:
            resolved_category = VideoCategory.DAILY

        # --- 1d. 时长校验 ---
        duration = float(info.get("duration") or 0) if isinstance(info, dict) else 0.0
        if min_duration is not None and duration > 0 and duration < min_duration:
            logger.warning(f"视频时长 {duration:.1f}s < 最小 {min_duration:.1f}s，跳过")
            return DownloadResult(
                video_id=video_id, url=url, success=False,
                error_message=f"时长不足 {duration:.1f}s",
                language=resolved_language, category=resolved_category,
                channel=channel_name, title=resolved_title,
            )
        if max_duration is not None and duration > 0 and duration > max_duration:
            logger.warning(f"视频时长 {duration:.1f}s > 最大 {max_duration:.1f}s，跳过")
            return DownloadResult(
                video_id=video_id, url=url, success=False,
                error_message=f"时长过长 {duration:.1f}s",
                language=resolved_language, category=resolved_category,
                channel=channel_name, title=resolved_title,
            )

        logger.info(
            f"[下载] 解析到 title='{(resolved_title or '')[:80]}' → "
            f"lang={getattr(resolved_language, 'value', resolved_language)}, "
            f"cat={getattr(resolved_category, 'value', resolved_category)}, "
            f"channel='{channel_name or '-'}', duration={duration:.0f}s"
        )

        # ========== 阶段2：实际下载到 tmp/<video_id>/ ==========
        import shutil as _shutil
        download_workdir = os.path.join(self._tmp_dir, video_id)
        # 重试前先清空旧半成品，避免 yt-dlp 基于陈旧 .part 文件续传错误数据（AUDIT-0018）
        if os.path.exists(download_workdir):
            _shutil.rmtree(download_workdir, ignore_errors=True)
        os.makedirs(download_workdir, exist_ok=True)
        outtmpl = os.path.join(download_workdir, "%(id)s_%(title)s.%(ext)s")

        ydl_opts: Dict[str, Any] = {
            "format": format_selector or "bestvideo[height<=2160]+bestaudio/best[height<=2160]/best",
            "merge_output_format": "mp4",
            # ★ 显式指定 ffmpeg 目录：bestvideo+bestaudio 必须靠它合并，
            # 不能依赖系统 PATH（换机器/打包环境可能缺失）
            "ffmpeg_location": os.path.dirname(str(get_ffmpeg_path())) if get_ffmpeg_path() else None,
            "outtmpl": outtmpl,
            "noplaylist": True,
            "overwrites": overwrite,
            "quiet": True,
            "no_warnings": True,
            "progress_with_newline": False,
            # 字幕由后续 ASR（faster-whisper）+ 翻译处理，不靠 yt-dlp 下载
            "writesubtitles": False,
            "writeautomaticsub": False,
            "embed_subtitles": False,
            "ignoreerrors": True,
            "skip_unavailable_fragments": True,
            "retries": 3,
            "geo_bypass": True,
            "geo_bypass_country": "US",
            "extractor_args": {"youtube": {"player_client": ["android", "web_embedded"]}},
            "http_headers": _site_headers(url, YTDLP_YOUTUBE_HEADERS),
        }

        # ---- cookies ----
        try:
            from core.cdp_cookies import auto_refresh_cookies
            if auto_refresh_cookies(port=9222, out_path=_cookies_file):
                ydl_opts["cookies"] = _cookies_file
                logger.info("[下载] yt-dlp cookies = CDP 实时拉取")
            elif os.path.exists(_cookies_file) and os.path.getsize(_cookies_file) > 100:
                ydl_opts["cookies"] = _cookies_file
        except Exception:
            if os.path.exists(_cookies_file) and os.path.getsize(_cookies_file) > 100:
                ydl_opts["cookies"] = _cookies_file
        else:
            if "cookies" not in ydl_opts:
                try:
                    _browser = self._detect_browser_cookie()
                    if _browser:
                        ydl_opts["cookies_from_browser"] = _browser
                except Exception:
                    pass

        # ---- proxy ----
        if self._proxy:
            ydl_opts["proxy"] = self._proxy
            logger.info(f"[下载] yt-dlp proxy = {self._proxy}")

        # ---- JS runtime ----
        from utils.path_helper import get_node_path
        _node_path = get_node_path()
        _node_exe = str(_node_path) if _node_path.exists() else None
        if _node_exe:
            ydl_opts["js_runtimes"] = {"node": {"path": _node_exe}}
            ydl_opts["remote_components"] = ["ejs:github"]

        # 注意：yt-dlp 2026.8+ 不再支持把 yt-dlp.EXE 自己当成 external_downloader
        # （会尝试调 .can_download() 方法），直接让内置下载器工作即可


        def _progress_hook(d: Dict[str, Any]) -> None:
            if progress_callback and d.get("status") in ("downloading", "finished"):
                progress_callback(DownloadProgress(
                    video_id=video_id, url=url,
                    title=d.get("info_dict", {}).get("title", resolved_title) or resolved_title,
                    downloaded_bytes=d.get("downloaded_bytes", 0),
                    total_bytes=d.get("total_bytes", 0),
                    progress=str(d.get("_percent_str", "0%")).strip("%"),
                    speed=str(d.get("_speed_str", "0 B/s")),
                    eta=str(d.get("_eta_str", "00:00")),
                    status=d.get("status", ""),
                ))

        ydl_opts["progress_hooks"] = [_progress_hook]

        # AUDIT-0018: success 标志 + try/finally 收口——仅当本次下载最终失败
        # （抛异常或未成功归档）时才清理 tmp 工作目录，防止 .part 残盘；
        # 成功路径只走"清理空 workdir"，不会误删尚未归档的副产物。
        download_success = False
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info2 = ydl.extract_info(url, download=True)
                if info2 is None:
                    raise ValueError("yt-dlp 下载返回 None（下载中断，已触发重试）")
                file_path = ydl.prepare_filename(info2)
                actual_duration = float(info2.get("duration") or duration or 0)

                # ★ 记录 yt-dlp 选中的格式（用于排查纯音频兜底等问题）
                sel_fmt = info2.get("format_id", "?")
                sel_ext = info2.get("ext", "?")
                all_formats = info2.get("formats") or []
                video_formats = [f for f in all_formats if f.get("vcodec") not in (None, "none")]
                audio_formats = [f for f in all_formats if f.get("acodec") not in (None, "none")]
                logger.info(
                    f"[下载] yt-dlp 选中 format_id={sel_fmt} ext={sel_ext} "
                    f"(可用视频格式={len(video_formats)}, 音频格式={len(audio_formats)})"
                )

                logger.info(f"[下载] 完成: {os.path.basename(file_path)} ({actual_duration:.0f}s)")
                try:
                    self._download_thumbnail(video_path=file_path, info=info2, video_id=video_id)
                except Exception:
                    pass

            # ========== 阶段2.5：确定实际产物 + 视频流闸门 ==========
            # yt-dlp 合并成功时 prepare_filename 指向最终成品；但本配置 ignoreerrors=True，
            # 视频流中断时不抛错，可能只剩纯音频（prepare 路径的 mp4 根本不存在）。
            # 因此必须先在 workdir 中确定真正存在的候选文件，且归档前强制验流。
            video_exts = {".mp4", ".mkv", ".webm", ".flv", ".mov", ".m4v", ".avi"}
            candidate_video = ""
            if file_path and os.path.exists(file_path):
                candidate_video = file_path
            elif os.path.isdir(download_workdir):
                media_cands = []
                for fn in os.listdir(download_workdir):
                    fp = os.path.join(download_workdir, fn)
                    if os.path.isfile(fp) and os.path.splitext(fn)[1].lower() in video_exts:
                        media_cands.append((os.path.getsize(fp), fp))
                if media_cands:
                    # 最大文件最可能是成品；合并失败时视频分片通常也大于纯音频
                    _, candidate_video = max(media_cands)
                logger.warning(
                    f"[下载] prepare 产物不存在（视频流中断或合并失败），"
                    f"workdir 回退候选: {os.path.basename(candidate_video) if candidate_video else '无'}"
                )

            def _abort_incomplete(reason: str, permanent: bool = False) -> None:
                """拒绝归档半成品并抛错：交给 download_video 的重试循环，绝不静默归档垃圾文件。

                permanent=True（无视频流/合并不完整等地区锁、cookies 过期类永久问题）
                抛 PermanentDownloadError 直接返回不重试；瞬时问题保留 RuntimeError 走重试。
                工作目录清理统一由外层 try/finally 收口（AUDIT-0018），此处不再重复清理。
                """
                bad = candidate_video or file_path or ""
                logger.error(f"[下载] ⚠ {reason}: {os.path.basename(bad) if bad else video_id}")
                if permanent:
                    raise PermanentDownloadError(reason)
                raise RuntimeError(reason)

            if not candidate_video or not os.path.exists(candidate_video):
                _abort_incomplete("yt-dlp 未产出任何媒体文件（视频流中断/合并失败），拒绝归档")

            kinds = _probe_stream_kinds(candidate_video)
            if kinds is None:
                # ffprobe/ffmpeg 都不可用才会到这（正常 bundling 不会）；放行但醒目告警
                logger.warning("[下载] ffprobe/ffmpeg 均不可用，未能校验视频流即放行（请检查 bin/ffmpeg 部署）")
            elif "video" not in kinds:
                _abort_incomplete(
                    f"下载产物无视频流（纯音频兜底，format_id={sel_fmt}；"
                    "多为视频流被地区/年龄限制阻断、cookies 过期或视频流中断），拒绝归档",
                    permanent=True,
                )
            elif "audio" not in kinds:
                # 有视频无音频：若 workdir 还躺着独立音频文件 → bestvideo+bestaudio 合并不完整；
                # 否则可能源视频本身无声，放行
                merge_incomplete = False
                if os.path.isdir(download_workdir):
                    for fn in os.listdir(download_workdir):
                        fp = os.path.join(download_workdir, fn)
                        if (fp != candidate_video and os.path.isfile(fp)
                                and os.path.splitext(fn)[1].lower() in video_exts):
                            k2 = _probe_stream_kinds(fp)
                            if k2 and "audio" in k2 and "video" not in k2:
                                merge_incomplete = True
                                break
                if merge_incomplete:
                    _abort_incomplete(
                        "产物缺音频流且存在独立音频文件（bestvideo+bestaudio 合并不完整），拒绝归档",
                        permanent=True,
                    )
                else:
                    logger.warning("[下载] 产物无音频流且无独立音频候选（源可能本身无声），放行")

            # ========== 阶段3：归档到 output/<lang>/<cat>/<channel>/<id>/ ==========
            file_sorter = get_file_sorter()
            archived_video = file_sorter.organize_file(
                candidate_video, video_id, resolved_title,
                resolved_language, resolved_category, channel_name,
            )

            # 3b. 副产物（字幕/缩略图）一起归档
            if os.path.isdir(download_workdir):
                sub_exts = {"srt", "vtt", "ass", "ssa", "sub"}
                thumb_exts = {"jpg", "jpeg", "png", "webp", "bmp"}
                for fn in os.listdir(download_workdir):
                    fp = os.path.join(download_workdir, fn)
                    if not os.path.isfile(fp):
                        continue
                    ext = os.path.splitext(fn)[1].lower().lstrip(".")
                    if ext in sub_exts:
                        file_sorter.organize_file(
                            fp, video_id, resolved_title,
                            resolved_language, resolved_category, channel_name,
                        )
                    elif ext in thumb_exts:
                        file_sorter.organize_file(
                            fp, video_id, resolved_title,
                            resolved_language, resolved_category, channel_name,
                            target_name=fn,
                        )

            # 清理空 workdir（成功路径仅清空目录，不删未归档副产物）
            try:
                if os.path.isdir(download_workdir) and not os.listdir(download_workdir):
                    os.rmdir(download_workdir)
            except Exception:
                pass

            download_success = bool(archived_video)
            return DownloadResult(
                video_id=video_id, url=url,
                success=download_success,
                file_path=archived_video or None,
                local_path=archived_video or None,
                duration=actual_duration,
                language=resolved_language,
                category=resolved_category,
                channel=channel_name,
                title=resolved_title,
                description=resolved_description,
                thumbnail_url=resolved_thumbnail,
            )
        finally:
            if not download_success and os.path.isdir(download_workdir):
                logger.info(f"[下载] 本次下载未成功，清理 tmp 工作目录: {download_workdir}")
                _shutil.rmtree(download_workdir, ignore_errors=True)
    
    def download_batch(
        self,
        videos: List[Dict[str, Any]],
        progress_callback: Optional[Callable[[DownloadProgress], None]] = None
    ) -> List[DownloadResult]:
        """
        批量下载视频（单线程）
        
        Args:
            videos: 视频列表，每个视频包含 url、video_id、title、language、category 字段
            progress_callback: 进度回调函数
            
        Returns:
            下载结果列表
        """
        results = []
        for video in videos:
            language = video.get("language")
            category = video.get("category")
            
            if isinstance(language, str):
                language = LanguageType.from_code(language)
            if isinstance(category, str):
                category = VideoCategory.from_code(category)
            
            result = self.download_video(
                url=video.get("url", ""),
                video_id=video.get("video_id", ""),
                title=video.get("title", ""),
                language=language,
                category=category,
                progress_callback=progress_callback
            )
            results.append(result)
        return results


class DownloadPool:
    """
    多线程下载池
    
    管理多个并发下载任务，控制并发数。
    """
    
    def __init__(self, max_threads: Optional[int] = None) -> None:
        """
        初始化下载池
        
        Args:
            max_threads: 最大并发线程数
        """
        if max_threads is None:
            config = get_download_config(load_config())
            max_threads = config.get("max_download_thread", 3)
        
        self._max_threads = max_threads
        self._downloader = VideoDownloader()
        self._threads: List[threading.Thread] = []
        self._results: List[DownloadResult] = []
        self._lock = threading.Lock()
        logger.info(f"下载池初始化完成，最大并发数: {max_threads}")
    
    def download(
        self,
        url: str,
        video_id: str,
        title: str = "",
        language: Optional[LanguageType] = None,
        category: Optional[VideoCategory] = None,
        output_path: Optional[str] = None,
        progress_callback: Optional[Callable[[DownloadProgress], None]] = None,
        min_duration: float = 90.0,
        max_duration: float = 600.0
    ) -> None:
        """
        提交下载任务（阻塞直到有可用线程）
        
        Args:
            url: 视频 URL
            video_id: 视频 ID
            title: 视频标题（用于生成文件名）
            language: 语言类型（用于自动选择存储目录）
            category: 视频分类（用于自动选择存储目录）
            output_path: 输出路径
            progress_callback: 进度回调
            min_duration: 最小视频时长（秒）
            max_duration: 最大视频时长（秒）
        """
        # AUDIT-0019: "检查+登记"原子化——持锁内清理已完成线程、检查闸门并先
        # append 线程对象，出锁后再 start()，避免并发提交超出 max_threads
        while True:
            with self._lock:
                self._threads = [t for t in self._threads if t.is_alive()]
                if len(self._threads) < self._max_threads:
                    thread = spawn(
                        target=self._download_worker,
                        args=(url, video_id, title, language, category, output_path, progress_callback, min_duration, max_duration),
                        daemon=True
                    )
                    self._threads.append(thread)
                    break
            time.sleep(0.1)

        thread.start()
    
    def download_batch(
        self,
        videos: List[Dict[str, Any]],
        progress_callback: Optional[Callable[[DownloadProgress], None]] = None,
        min_duration: float = 90.0,
        max_duration: float = 600.0
    ) -> None:
        """
        批量提交下载任务（非阻塞）
        
        Args:
            videos: 视频列表，每个视频包含 url、video_id、title、language、category 字段
            progress_callback: 进度回调函数
            min_duration: 最小视频时长（秒）
            max_duration: 最大视频时长（秒）
        """
        for video in videos:
            language = video.get("language")
            category = video.get("category")
            
            if isinstance(language, str):
                language = LanguageType.from_code(language)
            if isinstance(category, str):
                category = VideoCategory.from_code(category)
            
            self.download(
                url=video.get("url", ""),
                video_id=video.get("video_id", ""),
                title=video.get("title", ""),
                language=language,
                category=category,
                progress_callback=progress_callback,
                min_duration=min_duration,
                max_duration=max_duration
            )
    
    def _download_worker(
        self,
        url: str,
        video_id: str,
        title: str,
        language: Optional[LanguageType],
        category: Optional[VideoCategory],
        output_path: Optional[str],
        progress_callback: Optional[Callable[[DownloadProgress], None]],
        min_duration: float = 90.0,
        max_duration: float = 600.0
    ) -> None:
        """下载工作线程"""
        result = self._downloader.download_video(
            url=url,
            video_id=video_id,
            title=title,
            language=language,
            category=category,
            output_path=output_path,
            progress_callback=progress_callback,
            min_duration=min_duration,
            max_duration=max_duration
        )
        with self._lock:
            self._results.append(result)
    
    def _cleanup_finished(self) -> None:
        """清理已完成的线程"""
        with self._lock:
            self._threads = [t for t in self._threads if t.is_alive()]
    
    def wait_all(self) -> List[DownloadResult]:
        """等待所有下载任务完成并返回结果"""
        while True:
            with self._lock:
                alive = any(t.is_alive() for t in self._threads)
            if not alive:
                break
            time.sleep(0.5)

        with self._lock:
            results = self._results[:]
            self._results.clear()
            return results
    
    def clear(self) -> None:
        """清空下载池状态（线程和结果）
        
        会先等待所有正在运行的线程完成，避免线程孤儿化
        """
        self.wait_all()
    
    def find_existing_video(self, video_id: str) -> Optional[str]:
        """在 output 目录中查找已下载的视频
        
        Args:
            video_id: 视频 ID
            
        Returns:
            视频文件路径，未找到返回 None
        """
        return self._downloader._find_video_in_output(video_id)
    
    def is_busy(self) -> bool:
        """检查是否有正在进行的下载任务"""
        self._cleanup_finished()
        return len(self._threads) > 0
    
    def get_progress(self) -> Dict[str, Any]:
        """获取下载池进度"""
        self._cleanup_finished()
        return {
            "active_threads": len(self._threads),
            "completed_tasks": len(self._results),
            "max_threads": self._max_threads,
        }


# 便捷函数
_download_pool: Optional[DownloadPool] = None


def get_download_pool() -> DownloadPool:
    """获取下载池实例（单例）"""
    global _download_pool
    if _download_pool is None:
        _download_pool = DownloadPool()
    return _download_pool


def download_video(
    url: str,
    video_id: str,
    title: str = "",
    language: Optional[LanguageType] = None,
    category: Optional[VideoCategory] = None,
    output_path: Optional[str] = None,
    progress_callback: Optional[Callable[[DownloadProgress], None]] = None,
    min_duration: float = 90.0,
    max_duration: float = 300.0
) -> DownloadResult:
    """
    便捷函数：下载单个视频
    
    Args:
        url: 视频 URL
        video_id: 视频 ID
        title: 视频标题（用于生成文件名）
        language: 语言类型（用于自动选择存储目录）
        category: 视频分类（用于自动选择存储目录）
        output_path: 输出路径
        progress_callback: 进度回调
        min_duration: 最小视频时长（秒），默认90秒（1分30秒）
        max_duration: 最大视频时长（秒），默认300秒（5分钟）
        
    Returns:
        DownloadResult 下载结果
    """
    downloader = VideoDownloader()
    return downloader.download_video(url, video_id, title, language, category, output_path, progress_callback, min_duration=min_duration, max_duration=max_duration)


def init_download_pool(max_threads: Optional[int] = None) -> None:
    """
    初始化下载池
    
    Args:
        max_threads: 最大并发线程数
    """
    global _download_pool
    _download_pool = DownloadPool(max_threads)



