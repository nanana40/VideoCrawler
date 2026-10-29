"""
统一流程协调器

负责协调爬取、下载、字幕处理、内容分析等完整流程。

架构设计：
    Stage 1  清理未下载旧记录 + 爬取（串行）
    Stage 2  收集候选 + 同频道内聚排序
    Stage 3  ThreadPoolExecutor 跨视频并发执行：
             download → subtitle → analyze → format
             每个视频内部严格顺序，但视频 A 下载时视频 B 可以在做字幕。

    统一的数据类：PipelineConfig / PipelineResult
"""

import os
import re
import time
import threading
from utils.thread_spawn import spawn  # AUDIT-0033
from utils.youtube_url import build_watch_url  # AUDIT-0051
from utils.video_url import detect_video_site, to_pipeline_video
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Optional, Dict, List, Any, Callable, Tuple

from core.spiders import create_spider
from core.download import VideoDownloader
from core.subtitle_processor import process_video_subtitle
from core.video_analyzer import get_video_analyzer, AnalysisMode
from core.social_media_formatter import SocialMediaFormatter, SocialStyle
from utils.enums import LanguageType, VideoCategory
from utils.file_sort import get_file_sorter, get_subtitle_path
from utils.path_helper import get_output_dir
from utils.srt_parser import parse_srt_file
from utils.logger import get_crawler_logger, get_error_logger

logger = get_crawler_logger()
error_logger = get_error_logger()

_YOUTUBE_ID_RE = re.compile(r"[?&]v=([a-zA-Z0-9_-]{6,})")
_YOUTUBE_ID_ONLY_RE = re.compile(r"^([a-zA-Z0-9_-]{11})$")
_YOUTUBE_URL_RE = re.compile(
    r"(?:https?://)?(?:www\.)?youtube\.com/(?:watch\?v=|embed/|v/|shorts/)([a-zA-Z0-9_-]{11})"
)
_YOUTUBE_MOBILE_RE = re.compile(r"m\.youtube\.com/(?:watch\?v=)([a-zA-Z0-9_-]{11})")


def parse_video_id(raw: str) -> str:
    """从 URL 或 11 位 id 提取 YouTube video_id，失败返回空串"""
    if not raw:
        return ""
    s = raw.strip()
    # 纯 11 位 id
    m = _YOUTUBE_ID_ONLY_RE.match(s)
    if m:
        return m.group(1)
    # 完整 watch URL
    m = _YOUTUBE_URL_RE.search(s)
    if m:
        return m.group(1)
    # mobile 域名
    m = _YOUTUBE_MOBILE_RE.search(s)
    if m:
        return m.group(1)
    # youtu.be 短链
    m = re.search(r"youtu\.be/([a-zA-Z0-9_-]{11})", s)
    if m:
        return m.group(1)
    # 兜底：原来的 ?v= 模式
    m = _YOUTUBE_ID_RE.search(s)
    return m.group(1) if m else ""


def _extract_youtube_id(source_url: str, fallback_id: Any = None) -> str:
    """从 YouTube URL 提取 video id，解析失败则回退到 fallback_id 或 'video_N'"""
    m = _YOUTUBE_ID_RE.search(source_url)
    if m:
        return m.group(1)
    if fallback_id is not None:
        return str(fallback_id)
    return ""


class PipelineConfig:
    """流程配置"""

    # 搜索模式常量
    SEARCH_MODE_LANGUAGE = "language"   # 按语言/地区过滤（默认）
    SEARCH_MODE_KEYWORD = "keyword"     # 按关键词
    SEARCH_MODE_CHANNEL = "channel"     # 按频道
    SEARCH_MODE_SINGLE = "single"       # 单视频精准下载

    def __init__(self) -> None:
        self.video_site: str = "youtube"
        self.language: str = "en"
        self.category_default: str = ""         # GUI 指定的默认分类（空字符串=让爬虫决定）
        self.video_count: int = 10
        self.max_parallel: int = 4
        self.analyze_content: bool = True
        self.analysis_mode: str = "both"
        self.social_style: str = "xiaohongshu"
        self.target_lang: str = "zh-CN"
        self.min_duration: int = 90
        self.max_duration: int = 600

        # ===== 搜索模式扩展 =====
        self.search_mode: str = self.SEARCH_MODE_LANGUAGE
        self.search_keyword: str = ""           # 关键词模式
        self.channel_identifier: str = ""       # 频道名 / @handle / channelId
        self.search_order: str = "relevance"    # relevance / date / viewCount
        self.single_video_url: str = ""         # 单视频模式：URL 或 11 位 id


class PipelineResult:
    """流程结果"""

    def __init__(self) -> None:
        self.crawled: int = 0
        self.downloaded: int = 0
        self.subtitled: int = 0
        self.analyzed: int = 0
        self.errors: List[str] = []
        self.status: str = "running"
        self.downloaded_videos: List[Dict[str, Any]] = []

    def to_dict(self) -> Dict[str, Any]:
        return {
            "crawled": self.crawled,
            "downloaded": self.downloaded,
            "subtitled": self.subtitled,
            "analyzed": self.analyzed,
            "errors": self.errors,
            "status": self.status,
        }


class PipelineRunner:
    """流程执行器：协调爬取、下载、字幕处理、内容分析"""

    def __init__(self) -> None:
        import threading
        self._progress_callback: Optional[Callable[[str], None]] = None
        self._running = False
        self._lock = threading.Lock()  # 保护 _running 检查-置位的原子性
        self._file_sorter = get_file_sorter()

    def set_progress_callback(self, callback: Callable[[str], None]) -> None:
        self._progress_callback = callback

    def _log(self, message: str) -> None:
        line = f"[{time.strftime('%H:%M:%S')}] {message}"
        logger.info(message)
        if self._progress_callback:
            self._progress_callback(line)

    def _get_existing_urls(self) -> set:
        """从 output 目录提取已下载视频的 source_url 集合（不再查数据库）

        去重只看磁盘：output 目录下的 mp4 文件才算"已下载"。
        不再把 .vtt/.srt/.md/.txt 等副产物当作下载完成的依据——
        否则 mp4 下载失败但 yt-dlp 附带下了 .vtt 的视频会被错误去重。
        """
        try:
            output_root = get_output_dir()  # AUDIT-0061: 收口路径，禁硬编码
            if not output_root.is_dir():
                return set()
            seen_ids: set = set()
            for p in output_root.rglob("*.mp4"):
                if not p.is_file():
                    continue
                m = re.match(r"^([A-Za-z0-9_-]{11})_", p.name)
                if m:
                    seen_ids.add(m.group(1))
            return {
                    build_watch_url(vid) for vid in seen_ids
            }
        except Exception as e:
            error_logger.error(f"扫描 output 目录去重失败: {e}")
            return set()

    def _crawl_videos(self, config: PipelineConfig) -> List[Dict[str, Any]]:
        """爬取视频（按 search_mode 分派搜索路径 → 直接返回候选列表）"""
        search_mode = getattr(config, "search_mode", PipelineConfig.SEARCH_MODE_LANGUAGE)

        # 单视频模式：先按链接判断平台，TikTok/抖音走 TiktokSpider
        single_site = ""
        if search_mode == PipelineConfig.SEARCH_MODE_SINGLE:
            single_site = detect_video_site(config.single_video_url or "")
            if single_site == "tiktok":
                config.video_site = "tiktok"
                # 短视频平台不套 YouTube 的 90s ~ 5min 时长限制
                config.min_duration = None
                config.max_duration = None

        crawler = create_spider(config.video_site)
        exclude_urls = self._get_existing_urls()

        # ===== Step 1: 分派搜索路径 =====
        videos: List[Dict[str, Any]] = []

        try:
            if search_mode == PipelineConfig.SEARCH_MODE_KEYWORD:
                keyword = (config.search_keyword or "").strip()
                if not keyword:
                    self._log("❌ 关键词模式未填写")
                    videos = []
                elif not hasattr(crawler, "search_by_keyword"):
                    self._log(f"❌ 当前平台 {config.video_site} 不支持关键词搜索")
                    videos = []
                else:
                    self._log(
                        f"🔍 关键词搜索：q='{keyword}' → 目标 {config.video_count} 条"
                    )
                    videos = crawler.search_by_keyword(
                        keyword=keyword,
                        filter_languages=[LanguageType.from_code(config.language)],
                        min_duration=config.min_duration,
                        max_duration=config.max_duration,
                        target_count=max(config.video_count * 3, 20),
                        order=config.search_order or "relevance",
                        exclude_source_urls=exclude_urls,
                    )

            elif search_mode == PipelineConfig.SEARCH_MODE_CHANNEL:
                channel = (config.channel_identifier or "").strip()
                if not channel:
                    self._log("❌ 频道模式未填写")
                    videos = []
                elif not hasattr(crawler, "search_channel"):
                    self._log(f"❌ 当前平台 {config.video_site} 不支持频道订阅")
                    videos = []
                else:
                    self._log(
                        f"📺 频道订阅：'{channel}' → 目标 {config.video_count} 条"
                    )
                    videos = crawler.search_channel(
                        channel_identifier=channel,
                        min_duration=config.min_duration,
                        max_duration=config.max_duration,
                        target_count=max(config.video_count * 3, 20),
                        order=config.search_order or "date",
                        exclude_source_urls=exclude_urls,
                    )

            elif search_mode == PipelineConfig.SEARCH_MODE_SINGLE:
                raw = (config.single_video_url or "").strip()
                if single_site == "tiktok":
                    # TikTok / 抖音：用 yt-dlp 解析元数据（需 config.yaml 的 crawler.proxy）
                    self._log(f"🎯 TikTok/抖音 单视频：{raw[:80]}")
                    info = None
                    try:
                        info = crawler.get_video_info(raw)
                    except Exception as e:
                        error_logger.error(f"TikTok 单视频解析失败: {e}")
                    if not info:
                        self._log(
                            "❌ 解析失败：链接无效、需要代理（config.yaml → crawler.proxy）"
                            "或视频为私密/已删除"
                        )
                        videos = []
                    else:
                        videos = [to_pipeline_video(info, raw)]
                        self._log(
                            f"    ✓ [{videos[0]['youtube_id']}] "
                            f"{(videos[0].get('title') or '（无标题）')[:60]}"
                        )
                else:
                    vid = parse_video_id(raw)
                    if not vid:
                        self._log(
                            f"❌ 单视频模式无法解析 video_id：'{raw[:60]}'，"
                            "请输入 YouTube / TikTok 完整链接或 11 位 video_id"
                        )
                        videos = []
                    else:
                        source_url = build_watch_url(vid)
                        title = ""
                        description = ""
                        try:
                            from core.spiders.youtube_api_client import YouTubeAPIClient
                            api = YouTubeAPIClient()
                            if api.is_available():
                                snippets = api.get_video_snippets([vid])
                                snip = snippets.get(vid, {})
                                title = snip.get("title", "")
                                description = snip.get("description", "")
                                self._log(
                                    f"🎯 单视频精准：{source_url}"
                                    f" → {title[:60] if title else '（无标题）'}"
                                )
                            else:
                                self._log(f"🎯 单视频精准：{source_url}（API 未配置，标题留空）")
                        except Exception as e:
                            error_logger.error(f"单视频 title 获取失败: {e}")
                            self._log(f"🎯 单视频精准：{source_url}（标题获取失败）")

                        videos = [{
                            "source_url": source_url,
                            "yt_video_id": vid,
                            "title": title,
                            "duration": 0,
                            "description": description,
                            "is_asr": True,
                        }]

            elif search_mode == PipelineConfig.SEARCH_MODE_LANGUAGE:
                self._log(
                    f"🌐 按语言过滤："
                    f"{LanguageType.from_code(config.language).display_name}"
                )
                self._log("使用 YouTube Data API v3 语言过滤")
                videos = crawler.search_with_api(
                    filter_languages=[LanguageType.from_code(config.language)],
                    min_duration=config.min_duration,
                    max_duration=config.max_duration,
                    target_count=config.video_count,
                    exclude_source_urls=exclude_urls,
                )
                if not videos:
                    self._log("API 无结果，回退热门页抓取...")
                    videos = crawler.search_trending(
                        filter_languages=[LanguageType.from_code(config.language)],
                        min_duration=config.min_duration,
                        max_duration=config.max_duration,
                    )
        except Exception as e:
            error_logger.error(f"搜索阶段异常: {e}")
            self._log(f"✗ 搜索异常: {str(e)[:100]}")
            videos = []

        # ===== Step 2: 磁盘去重 + 构造候选 =====
        if not videos:
            self._log("⚠ 未获取到任何视频")
            return []

        error_logger.info(f"爬虫返回 {len(videos)} 个视频")
        if exclude_urls:
            self._log(f"output 目录已有 {len(exclude_urls)} 条，磁盘去重")

        candidates: List[Dict[str, Any]] = []
        skipped_dup = 0
        for video in videos:
            source_url = video.get("source_url", "")

            if not source_url:
                error_logger.warning(
                    f"跳过无URL的视频: {video.get('title', '')[:30]}"
                )
                continue

            if source_url in exclude_urls:
                skipped_dup += 1
                continue

            candidates.append(video)

        # 补全 lang / category / youtube_id 字段（爬虫不一定都给）
        for v in candidates:
            v.setdefault("lang", config.language)
            if config.category_default:
                v["category"] = config.category_default
            else:
                v.setdefault("category", "daily")
            if not v.get("youtube_id"):
                v["youtube_id"] = _extract_youtube_id(
                    v.get("source_url", ""), v.get("yt_video_id")
                )

        if skipped_dup > 0:
            self._log(
                f"✅ 爬取完成：{len(candidates)} 个新候选"
                f"（磁盘去重跳过 {skipped_dup} 个）"
            )
        else:
            self._log(f"✅ 爬取完成：{len(candidates)} 个候选")

        return candidates

    # =====================================================
    # 并行流水线辅助方法
    # =====================================================
    def _subtitle_single(
        self, config: PipelineConfig, video: Dict[str, Any]
    ) -> Tuple[bool, str]:
        """单视频字幕处理（线程安全）

        Returns:
            (是否成功, 实际生成的 SRT 绝对路径)；失败时路径为空串
        """
        video_id = video.get("youtube_id") or ""
        file_path = video.get("local_video_path", "")
        lang_code = video.get("lang")
        category_str = video.get("category")

        if not file_path or not os.path.exists(file_path):
            self._log(f"    ⚠ [{video_id}] 字幕跳过：文件不存在")
            return False, ""

        language = LanguageType.from_code(lang_code) if lang_code else None
        category = (
            VideoCategory.from_code(category_str) if category_str else None
        )

        try:
            result = process_video_subtitle(
                video_id=video_id,
                video_path=file_path,
                language=language,
                category=category,
                source_lang=lang_code if lang_code else "auto",
                target_lang=config.target_lang,
                # channel 必须与下载归档时一致，否则 SRT 会落到少一层频道目录的
                # 兄弟文件夹里（视频在 output/<lang>/<cat>/<channel>/<id>/）
                channel=video.get("channel") or None,
            )

            if not result.success:
                self._log(
                    f"    ⚠ [{video_id}] 字幕失败: "
                    f"{(result.error_message or '')[:80]}"
                )
                return False, ""

            final_video = result.embedded_video_path
            if final_video and final_video != file_path and os.path.exists(final_video):
                video["local_video_path"] = final_video

            return True, result.subtitle_path or ""
        except Exception as e:
            error_logger.error(f"字幕异常 [{video_id}]: {e}")
            self._log(f"    ✗ [{video_id}] 字幕异常: {str(e)[:80]}")
            return False, ""

    def _analyze_single(
        self, config: PipelineConfig, video: Dict[str, Any]
    ) -> bool:
        """单视频内容分析（线程安全）"""
        video_id = video.get("youtube_id") or ""
        lang_code = video.get("lang", "en")
        category_str = video.get("category", "daily")

        category = (
            VideoCategory.from_code(category_str)
            if category_str
            else VideoCategory.DAILY
        )
        language = (
            LanguageType.from_code(lang_code)
            if lang_code
            else LanguageType.ENGLISH
        )

        channel = video.get("channel") or None
        video_dir = self._file_sorter.get_video_dir(
            language, category, video_id, channel
        )
        srt_path = get_subtitle_path(
            video_id, language, category, config.target_lang, channel=channel
        )

        if not os.path.exists(srt_path):
            self._log(f"    ⚠ [{video_id}] 分析跳过：字幕文件不存在")
            return False

        subtitles = parse_srt_file(srt_path)
        if not subtitles:
            self._log(f"    ⚠ [{video_id}] 分析跳过：字幕为空")
            return False

        try:
            analyzer = get_video_analyzer()
            formatter = SocialMediaFormatter()

            if config.analysis_mode in ("oral", "both"):
                analyzer.analyze(
                    video_id=video_id,
                    subtitles=subtitles,
                    mode=AnalysisMode.ORAL_SPOKEN,
                    output_dir=video_dir,
                    use_ai_fallback=False,
                    language=lang_code,
                )
            if config.analysis_mode in ("exam", "both"):
                analyzer.analyze(
                    video_id=video_id,
                    subtitles=subtitles,
                    mode=AnalysisMode.EXAM_PREP,
                    output_dir=video_dir,
                    use_ai_fallback=False,
                    language=lang_code,
                )

            if config.social_style in ("xiaohongshu", "all"):
                formatter.format(
                    video_id=video_id,
                    subtitles=subtitles,
                    analysis_mode="口语学习",
                    style=SocialStyle.XIAOHONGSHU,
                    output_dir=video_dir,
                    use_ai_fallback=False,
                    language=lang_code,
                )
            # 2026-08-14: 只生成小红书文案，WEIBO / ZHIHU 暂停以节省 AI 调用配额
            # if config.social_style in ("weibo", "all"):
            #     formatter.format(
            #         video_id=video_id,
            #         subtitles=subtitles,
            #         analysis_mode="应试学习",
            #         style=SocialStyle.WEIBO,
            #         output_dir=video_dir,
            #         use_ai_fallback=False,
            #         language=lang_code,
            #     )
            # if config.social_style in ("zhihu", "all"):
            #     formatter.format(
            #         video_id=video_id,
            #         subtitles=subtitles,
            #         analysis_mode="应试学习",
            #         style=SocialStyle.ZHIHU,
            #         output_dir=video_dir,
            #         use_ai_fallback=False,
            #         language=lang_code,
            #     )

            self._log(f"    ✓ [{video_id}] 分析+文案完成")
            return True
        except Exception as e:
            error_logger.error(f"分析异常 [{video_id}]: {e}")
            self._log(f"    ✗ [{video_id}] 分析异常: {str(e)[:80]}")
            return False

    def run(self, config: PipelineConfig) -> PipelineResult:
        with self._lock:
            if self._running:
                result = PipelineResult()
                result.status = "error"
                result.errors.append("已有任务正在执行中")
                return result
            self._running = True

        result = PipelineResult()
        executor = None

        try:
            self._log("开始爬取视频...")
            candidates = self._crawl_videos(config)

            # AUDIT-0048: result.crawled 之前恒为 0，实际上 candidates 就是爬取到的数量
            result.crawled = len(candidates)

            if not candidates:
                self._log("⚠ 没有可用的候选视频")
                result.status = "completed"
                return result

            target = config.video_count
            if len(candidates) > target:
                _cohesion_sort(candidates)
                candidates = candidates[:target]

            self._log(
                f"✅ 确定 {len(candidates)} 个候选视频，"
                f"启动并行流水线（max_parallel={config.max_parallel}）..."
            )

            newly_downloaded: List[Dict[str, Any]] = []
            subtitled_ok = 0
            analyzed_ok = 0
            download_fail = 0

            downloader = VideoDownloader()
            executor = ThreadPoolExecutor(max_workers=config.max_parallel)
            futures = []

            def _process_one(video: Dict[str, Any]) -> Dict[str, Any]:
                """单视频全流程：下载 → 字幕 → 分析"""
                source_url = video["source_url"]
                lang_code = video.get("lang")
                category_str = video.get("category")
                title = video.get("title", "")

                youtube_id = video.get("youtube_id") or _extract_youtube_id(source_url)

                language = (
                    LanguageType.from_code(lang_code) if lang_code else None
                )
                category = (
                    VideoCategory.from_code(category_str)
                    if category_str
                    else None
                )

                dl_result = downloader.download_video(
                    url=source_url,
                    video_id=youtube_id,
                    title=title,
                    language=language,
                    category=category,
                    min_duration=config.min_duration,
                    max_duration=config.max_duration,
                )

                if not dl_result.success and not dl_result.skipped:
                    err = dl_result.error_message or "unknown"
                    self._log(
                        f"    ✗ [{youtube_id}] 下载失败: {err[:100]}"
                    )
                    return {
                        "ok": False,
                        "youtube_id": youtube_id,
                        "error": err,
                    }

                file_path = dl_result.file_path or dl_result.local_path or ""

                # 从 DownloadResult 回传：自动检测补齐的 lang / cat / channel / title
                # 优先级：显式 video[] 字段 > DownloadResult 自动检测结果
                if not lang_code and dl_result.language:
                    lang_code = dl_result.language.value
                if not category_str and dl_result.category:
                    category_str = dl_result.category.value
                if not title and dl_result.title:
                    title = dl_result.title

                video_info_for_subtitle = {
                    "youtube_id": youtube_id,
                    "source_url": source_url,
                    "lang": lang_code,
                    "category": category_str,
                    "title": title,
                    "local_video_path": file_path,
                    "channel": dl_result.channel,
                }

                sub_ok, srt_path = self._subtitle_single(config, video_info_for_subtitle)

                ana_ok = False
                if config.analyze_content:
                    ana_ok = self._analyze_single(config, video_info_for_subtitle)

                # SRT 路径直接取字幕步骤的真实产物，不再二次拼路径
                # （供 web 层把烧录成品登记进视频候选池）
                if srt_path and not os.path.exists(srt_path):
                    srt_path = ""

                return {
                    "ok": True,
                    "youtube_id": youtube_id,
                    "file_path": video_info_for_subtitle["local_video_path"],
                    "sub_ok": sub_ok,
                    "ana_ok": ana_ok,
                    # 发布池登记所需的元数据
                    "title": title,
                    "source_url": source_url,
                    "lang": lang_code or "",
                    "category": category_str or "",
                    "channel": video_info_for_subtitle.get("channel", ""),
                    "srt_path": srt_path,
                }

            for cand in candidates:
                futures.append(executor.submit(_process_one, cand))

            for f in as_completed(futures):
                try:
                    info = f.result()
                except Exception as e:
                    self._log(f"    ✗ 线程异常: {str(e)[:100]}")
                    download_fail += 1
                    continue

                if not info.get("ok"):
                    download_fail += 1
                    continue

                newly_downloaded.append({
                    "youtube_id": info["youtube_id"],
                    "local_video_path": info["file_path"],
                    # 完整元数据（web 层据此把成品登记进视频候选池）
                    "title": info.get("title", ""),
                    "source_url": info.get("source_url", ""),
                    "lang": info.get("lang", ""),
                    "category": info.get("category", ""),
                    "channel": info.get("channel", ""),
                    "srt_path": info.get("srt_path", ""),
                    "sub_ok": bool(info.get("sub_ok")),
                })
                if info.get("sub_ok"):
                    subtitled_ok += 1
                if info.get("ana_ok"):
                    analyzed_ok += 1

            executor.shutdown(wait=True)

            result.downloaded_videos = newly_downloaded
            result.downloaded = len(newly_downloaded)
            result.subtitled = subtitled_ok
            result.analyzed = analyzed_ok
            result.status = "completed"

            self._log(
                f"✅ 并行流水线完成："
                f"下载成功 {result.downloaded}, 字幕 {subtitled_ok}, 分析 {analyzed_ok}, "
                f"下载失败 {download_fail}"
            )

        except Exception as e:
            error_logger.error(f"流程执行异常: {e}")
            result.status = "error"
            result.errors.append(str(e))
            self._log(f"❌ 流程执行异常: {str(e)}")

        finally:
            # 无论正常还是异常，都确保 executor 被关闭（cancel_futures=True：Python 3.9+ 支持）
            if executor is not None:
                try:
                    executor.shutdown(wait=False, cancel_futures=True)
                except TypeError:
                    # Python < 3.9 没有 cancel_futures 参数
                    executor.shutdown(wait=False)
            self._running = False

        return result

    def run_async(
        self,
        config: PipelineConfig,
        callback: Optional[Callable[[PipelineResult], None]] = None,
    ) -> None:
        def _run():
            result = self.run(config)
            if callback:
                callback(result)

        thread = spawn(target=_run, daemon=True)
        thread.start()


_pipeline_runner: Optional[PipelineRunner] = None


def get_pipeline_runner() -> PipelineRunner:
    global _pipeline_runner
    if _pipeline_runner is None:
        _pipeline_runner = PipelineRunner()
    return _pipeline_runner


def run_pipeline(config: PipelineConfig) -> PipelineResult:
    return get_pipeline_runner().run(config)


def run_pipeline_async(
    config: PipelineConfig,
    callback: Optional[Callable[[PipelineResult], None]] = None,
) -> None:
    get_pipeline_runner().run_async(config, callback)


def _cohesion_sort(videos: List[Dict[str, Any]]) -> None:
    """
    把未下载视频按强相关字段聚在一起（in-place 稳定排序）。

    优先级：
      1. channel_id 非空的优先聚（同频道适合一次发完）
      2. series_id 非空的次聚（同系列适合一条 social thread）
      3. related_cluster_id 非空的再聚（同话题桶）
      4. create_ts DESC 保证较新的优先
    """
    channel_count: Dict[str, int] = {}
    series_count: Dict[str, int] = {}
    cluster_count: Dict[str, int] = {}
    for v in videos:
        cid = v.get("channel_id") or v.get("channelId")
        sid = v.get("series_id")
        rid = v.get("related_cluster_id")
        if cid:
            channel_count[cid] = channel_count.get(cid, 0) + 1
        if sid:
            series_count[sid] = series_count.get(sid, 0) + 1
        if rid:
            cluster_count[rid] = cluster_count.get(rid, 0) + 1

    def _key(v: Dict[str, Any]):
        cid = v.get("channel_id") or v.get("channelId") or ""
        sid = v.get("series_id") or ""
        rid = v.get("related_cluster_id") or ""
        ts = v.get("create_ts") or v.get("created_at") or 0
        return (
            0 if cid else 1, -(channel_count.get(cid, 0)), cid,
            0 if sid else 1, -(series_count.get(sid, 0)), sid,
            0 if rid else 1, -(cluster_count.get(rid, 0)), rid,
            -int(ts),
        )

    videos.sort(key=_key)
