"""
全自动流水线 + 多视频排队下载机制

单例 AutoPipelineManager：
  - 维护一个 FIFO 任务队列
  - 单个后台工作线程串行执行每个任务的完整流水线：
        下载 → 语音识别(SRT) → 字幕烧录 → 文案写作
  - 不占用 TaskManager._running（保持搜索/下载页面可用，允许边处理边录入下一个视频）

设置：
  - GUI 层（page_download）在「全自动」模式下调用 enqueue(job) 入队
  - 入队后页面立即释放，可继续编辑下一个视频并再次 enqueue
  - 使用 status observer 通知 GUI 刷新队列数量
"""

import os
import threading
from utils.thread_spawn import spawn  # AUDIT-0033
from utils.youtube_url import build_watch_url  # AUDIT-0051
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

from utils.logger import get_crawler_logger

logger = get_crawler_logger()

# 单个任务的整体处理超时（秒）。超过则跳过该任务以释放队列，
# 避免某个视频在下载/识别/烧录阶段长时间卡死而拖住后续所有视频。
JOB_TIMEOUT = 1800  # 30 分钟（正常全流程通常在数分钟内完成）


@dataclass
class AutoJob:
    """单个视频的全自动处理参数（入队时从 GUI 各页控件快照）"""
    url: str = ""
    video_id: str = ""
    language: str = "auto"        # 下载页源语言
    quality: Optional[str] = None  # None = 用 download.py 默认格式选择器（最高清 4K 封顶）
    category: str = "other"
    target_lang: str = "zh-CN"    # 识别页目标语言
    proofread: bool = False       # 识别页校对开关

    # 字幕样式（跟随字幕页控件，硬烧录用）
    font_size: int = 12
    margin_v: int = 16
    primary_color: str = "#FFFFFF"
    outline_color: str = "#000000"

    # ★ 双语参数（跟随字幕页控件）
    bilingual: bool = True
    bilingual_pos: str = "src_top"    # "src_top" | "src_bottom"
    secondary_scale: float = 0.85     # 译文字号相对主字号比例

    # 文案（跟随文案页控件）
    platform: str = "xiaohongshu"
    style: str = "oral"           # 'oral' | 'exam'
    analyze: bool = True


class AutoPipelineManager:
    """全自动流水线单例：任务队列 + 串行工作线程"""

    _instance: Optional["AutoPipelineManager"] = None
    _instance_lock = threading.Lock()

    def __init__(self) -> None:
        self._queue: deque = deque()
        self._queue_lock = threading.Lock()
        self._worker_thread: Optional[threading.Thread] = None
        self._processing = False                # 是否正在处理一个任务
        self._current_job_id: Optional[str] = None  # 正在处理的任务 id（用于阶段提示）
        self._status_observers: List[Callable[[int], None]] = []
        self._observers_lock = threading.Lock()
        self._text_observers: List[Callable[[str], None]] = []
        self._text_lock = threading.Lock()
        self._stop_event = threading.Event()    # AUDIT-0011: 关窗时通知 worker 退出

    # ---------- 单例 ----------
    @classmethod
    def instance(cls) -> "AutoPipelineManager":
        with cls._instance_lock:
            if cls._instance is None:
                cls._instance = cls()
        return cls._instance

    # ---------- 观察者（GUI 刷新队列数） ----------
    def add_status_observer(self, cb: Callable[[int], None]) -> None:
        with self._observers_lock:
            if cb not in self._status_observers:
                self._status_observers.append(cb)

    def remove_status_observer(self, cb: Callable[[int], None]) -> None:
        with self._observers_lock:
            if cb in self._status_observers:
                self._status_observers.remove(cb)

    def add_text_observer(self, cb: Callable[[str], None]) -> None:
        """注册阶段文本观察者（worker 线程回调，需自行转发到主线程）"""
        with self._text_lock:
            if cb not in self._text_observers:
                self._text_observers.append(cb)

    def remove_text_observer(self, cb: Callable[[str], None]) -> None:
        with self._text_lock:
            if cb in self._text_observers:
                self._text_observers.remove(cb)

    def _notify_text(self, text: str) -> None:
        with self._text_lock:
            obs = list(self._text_observers)
        for cb in obs:
            try:
                cb(text)
            except Exception:
                pass

    def _set_phase(self, phase: str, pct: Optional[int] = None) -> None:
        """更新当前处理阶段并广播（pct 可选百分比）"""
        label = phase if pct is None else f"{phase} {pct}%"
        self._notify_text(label)

    def _notify_status(self) -> None:
        with self._observers_lock:
            observers = list(self._status_observers)
        for cb in observers:
            try:
                cb(self.queue_size())
            except Exception:
                pass

    # ---------- 队列 ----------
    def enqueue(self, job: AutoJob) -> int:
        with self._queue_lock:
            self._queue.append(job)
            if not self._worker_thread or not self._worker_thread.is_alive():
                self._worker_thread = spawn(target=self._worker, daemon=True)
                self._worker_thread.start()
        self._notify_status()
        return self.queue_size()

    def queue_size(self) -> int:
        with self._queue_lock:
            return len(self._queue)

    def is_busy(self) -> bool:
        return self._processing or self.queue_size() > 0

    # ---------- 工作线程 ----------
    def stop(self) -> None:
        """AUDIT-0011: 关窗时调用 — 通知 worker 退出 + 清空队列"""
        self._stop_event.set()
        with self._queue_lock:
            self._queue.clear()
        self._notify_status()

    def _worker(self) -> None:
        while not self._stop_event.is_set():
            with self._queue_lock:
                if not self._queue:
                    break
                job = self._queue.popleft()
            self._notify_status()
            self._processing = True
            self._current_job_id = job.video_id
            self._set_phase(f"▶ 开始处理 {job.video_id}")
            logger.info(f"[AutoPipeline] 出队处理: {job.video_id}")

            # 每个任务在独立线程中运行，便于看门狗超时跳过，不拖住整个队列
            job_thread = spawn(self._run_job, job, daemon=True)
            job_thread.start()
            job_thread.join(timeout=JOB_TIMEOUT)
            if job_thread.is_alive():
                logger.error(
                    f"[AutoPipeline] 任务超时 (> {JOB_TIMEOUT}s)，已跳过，继续处理下一个: {job.video_id}")
                self._set_phase(f"⏱ 任务超时，已跳过 {job.video_id}")
                # 超时后不再等待（超时线程作为 daemon 留在后台，进程退出即回收）

            self._current_job_id = None
            self._processing = False
            self._notify_status()
        self._notify_status()

    # ------------------------------------------------------------------
    # 流水线四阶段
    # ------------------------------------------------------------------
    def _run_job(self, job: AutoJob) -> None:
        import traceback
        logger.info(f"[AutoPipeline] ⚡ 开始自动处理: {job.video_id}")

        try:
            # ============== 1. 下载 ==============
            self._set_phase(f"⬇ 下载中… {job.video_id}")
            logger.info(f"[AutoPipeline] [1/4] 下载: url={job.url[:60]} language={job.language} quality={job.quality}")
            fp, meta = self._download_step(job)
            if not fp:
                logger.error(f"[AutoPipeline] 下载失败，跳过后续步骤: {job.video_id}")
                self._set_phase(f"✖ 下载失败：{job.video_id}")
                return
            if not os.path.exists(fp):
                logger.error(f"[AutoPipeline] 下载返回的文件路径不存在：{fp}")
                self._set_phase(f"✖ 下载产物丢失：{job.video_id}")
                return
            logger.info(f"[AutoPipeline] [1/4] 下载完成: {fp}")
            if meta:
                logger.info(f"[AutoPipeline]   video info: title={meta.get('title', '')[:40]} lang={meta.get('language')}")

            # ============== 2. 语音识别 + 翻译 ==============
            self._set_phase(f"🎙 识别+翻译中… {job.video_id}")
            logger.info(f"[AutoPipeline] [2/4] 开始识别+翻译: {job.video_id}")
            segments, srt_path = self._recognize_step(fp, job)
            if not segments or not srt_path:
                logger.warning(
                    f"[AutoPipeline] [2/4] 识别未完整产出: segments={len(segments) if segments else 0}, "
                    f"srt_path={srt_path}，尝试继续烧录"
                )
            else:
                logger.info(f"[AutoPipeline] [2/4] 识别+翻译完成: {len(segments)} 段 → {os.path.basename(srt_path)}")

            # ============== 3. 字幕烧录 ==============
            if not srt_path or not os.path.exists(srt_path):
                logger.error(
                    f"[AutoPipeline] [3/4] 缺少有效 SRT，无法烧录: "
                    f"srt_path={srt_path}, exists={os.path.exists(srt_path) if srt_path else False}"
                )
                self._set_phase(f"✖ 缺少字幕，无法烧录：{job.video_id}")
                return
            self._set_phase(f"🎨 字幕烧录中… {job.video_id}")
            logger.info(f"[AutoPipeline] [3/4] 开始字幕烧录: video={os.path.basename(fp)} srt={os.path.basename(srt_path)}")
            final_video = self._burn_step(fp, srt_path, job)
            if not final_video:
                logger.error(f"[AutoPipeline] [3/4] 烧录失败，跳过文案生成: {job.video_id}")
                self._set_phase(f"✖ 字幕烧录失败：{job.video_id}")
                return
            logger.info(f"[AutoPipeline] [3/4] 烧录完成: {os.path.basename(final_video)}")

            # ============== 4. 文案写作 ==============
            self._set_phase(f"📝 文案生成中… {job.video_id}")
            logger.info(f"[AutoPipeline] [4/4] 开始文案生成: platform={job.platform} style={job.style}")
            content = self._write_copy_step(final_video, srt_path, job, segments=segments)
            copy_path = self._find_copy_file(final_video, job)
            if content:
                logger.info(f"[AutoPipeline] [4/4] 文案生成完成: {len(content)} 字 ({job.video_id})")
            else:
                logger.warning(f"[AutoPipeline] [4/4] 文案生成未产出内容: {job.video_id}")

            # ============== 5. 入视频候选池（全自动模式） ==============
            self._auto_add_to_pool(job, final_video, srt_path, copy_path, meta, fp)

            logger.info(f"[AutoPipeline] ✅ 全部完成 [1/4→4/4]: {job.video_id}")
            self._set_phase(f"✅ 完成：{job.video_id}")

        except Exception as e:
            # ★ 顶层兜底：任何未被步骤内捕获的异常 → 完整 traceback + 阶段标记
            tb = traceback.format_exc()
            logger.error(
                f"[AutoPipeline] 💥 流水线异常（job={job.video_id}）: {e}\n{tb}"
            )
            self._set_phase(f"✖ 流水线异常：{job.video_id}")

    # ------------------------------------------------------------------
    # 1. 下载
    # ------------------------------------------------------------------
    def _download_step(self, job: AutoJob):
        from core.download import VideoDownloader
        from utils.enums import LanguageType, VideoCategory

        url = job.url if job.url.startswith("http") else build_watch_url(job.video_id)
        downloader = VideoDownloader()

        lang_obj = None
        if job.language and job.language != "auto":
            try:
                lang_obj = LanguageType(job.language)
            except Exception:
                lang_obj = None
        cat_obj = None
        if job.category and job.category != "other":
            try:
                cat_obj = VideoCategory(job.category)
            except Exception:
                cat_obj = None

        try:
            result = downloader.download_video(
                url=url,
                video_id=job.video_id,
                language=lang_obj,
                category=cat_obj,
                format_selector=job.quality,
                progress_callback=lambda p: self._on_download_progress(p),
            )
        except Exception as e:
            logger.error(f"[AutoPipeline] 下载异常: {e}")
            return None, None

        fp = result.file_path or result.local_path or ""
        if not fp:
            logger.error(f"[AutoPipeline] 下载无产出: {result.error_message}")
            return None, None

        meta = {
            "title": getattr(result, "title", "") or "",
            "description": getattr(result, "description", "") or "",
            "duration": getattr(result, "duration", 0) or 0,
            "channel": getattr(result, "channel", "") or "",
            "language": job.language or "auto",
        }
        return fp, meta

    def _on_download_progress(self, p) -> None:
        """下载进度回调 → 阶段文本（尽力解析百分比）"""
        pct: Optional[int] = None
        try:
            raw = getattr(p, "progress", None)
            if isinstance(raw, str):
                raw = raw.strip().rstrip("%").strip()
                if raw:
                    pct = int(float(raw))
            elif isinstance(raw, (int, float)):
                pct = int(raw)
        except Exception:
            pct = None
        vid = f" {self._current_job_id}" if self._current_job_id else ""
        self._set_phase(f"⬇ 下载中{vid}", pct)

    # ------------------------------------------------------------------
    # 2. 语音识别 + 翻译 → SRT（调 core 统一入口，与 UI 页面共通路）
    # ------------------------------------------------------------------
    def _recognize_step(self, video_path: str, job: AutoJob):
        from core.gemini_engine import GeminiTranscriber
        transcriber = GeminiTranscriber()
        srt_path = transcriber.transcribe_to_srt_file(
            video_path, source_lang=job.language, proofread=job.proofread)
        if not srt_path:
            return None, None
        # 返回 SRT 路径 + segments（文案写作需要 source_text）
        try:
            from utils.srt_parser import parse_subtitle_file, normalize_subtitle_items
            blocks = normalize_subtitle_items(parse_subtitle_file(srt_path))
            segments = []
            for b in blocks:
                segments.append({
                    "start_time": b.get("start_time", 0),
                    "end_time": b.get("end_time", 0),
                    "source_text": b.get("text", ""),
                    "target_text": b.get("translated_text", ""),
                })
            return segments, srt_path
        except Exception as e:
            logger.warning(f"[AutoPipeline] 解析 SRT 给文案失败（不影响烧录）: {e}")
            return [], srt_path

    # ------------------------------------------------------------------
    # 3. 字幕烧录
    # ------------------------------------------------------------------
    def _burn_step(self, video_path: str, srt_path: str, job: AutoJob):
        from core.subtitle_render import burn_mp4
        return burn_mp4(
            video_path,
            srt_path,
            font_size=job.font_size,
            margin_v=job.margin_v,
            primary_color=job.primary_color,
            outline_color=job.outline_color,
            progress_cb=lambda pct, desc: self._set_phase("🎨 字幕烧录中", pct),
            # ★ 全部双语参数从 AutoJob 取
            bilingual=job.bilingual,
            bilingual_pos=job.bilingual_pos,
            secondary_scale=job.secondary_scale,
        )

    # ------------------------------------------------------------------
    # 4. 文案写作
    # ------------------------------------------------------------------
    def _write_copy_step(
        self, final_video: str, srt_path: str, job: AutoJob,
        segments: Optional[List[Dict[str, Any]]] = None,
    ):
        """生成文案。

        ★ 优先使用上游传来的 segments（含 source_text/target_text），
        直接把 source_text 喂给 AI，绕过 SRT 文件序列化→解析这条脆弱链路。
        只有 segments 不可用时才 fallback 到 SRT 解析。
        """
        subtitles: List[Dict[str, Any]] = []

        # 路径 A（优先）：直接用 segments 的 source_text → text
        if segments:
            for seg in segments:
                src = seg.get("source_text", "").strip() or seg.get("text", "").strip()
                tgt = seg.get("target_text", "").strip() or seg.get("translated_text", "").strip()
                if src or tgt:
                    subtitles.append({"text": src, "translated_text": tgt})
            logger.info(f"[AutoPipeline] 文案：使用 segments 直取 {len(subtitles)} 条字幕")

        # 路径 B（兜底）：segments 不可用时从 SRT 文件解析
        if not subtitles and srt_path and os.path.exists(srt_path):
            try:
                from utils.srt_parser import parse_subtitle_file, normalize_subtitle_items
                blocks = normalize_subtitle_items(parse_subtitle_file(srt_path))
                for b in blocks:
                    src = b.get("text", "")
                    tgt = b.get("translated_text", "")
                    if src or tgt:
                        subtitles.append({"text": src, "translated_text": tgt})
                logger.info(f"[AutoPipeline] 文案：fallback SRT 解析 {len(subtitles)} 条")
            except Exception as e:
                logger.warning(f"[AutoPipeline] 解析 SRT 失败: {e}")

        if not subtitles:
            logger.warning("[AutoPipeline] 文案：无可用字幕素材")
            return ""

        save_dir = os.path.dirname(final_video) if os.path.exists(final_video) else os.path.dirname(srt_path)
        try:
            from core.copy_writer import generate_copy
            return generate_copy(
                subtitles=subtitles,
                language=job.language,
                video_save_dir=save_dir,
                video_id=job.video_id,
                platform=job.platform,
                style=job.style,
                analyze=job.analyze,
            )
        except Exception as e:
            import traceback
            logger.error(f"[AutoPipeline] 文案生成异常: {e}\n{traceback.format_exc()}")
            return ""

    # ------------------------------------------------------------------
    # 5. 视频候选池
    # ------------------------------------------------------------------

    def _find_copy_file(self, final_video: str, job: AutoJob) -> str:
        """文案保存规则: video_dir/{video_id}_{platform}_{style}.txt"""
        save_dir = os.path.dirname(final_video) if os.path.exists(final_video) else ""
        if not save_dir:
            return ""
        safe_id = (job.video_id or "context")[:20]
        fname = f"{safe_id}_{job.platform}_{job.style}.txt"
        fpath = os.path.join(save_dir, fname)
        return fpath if os.path.exists(fpath) else ""

    def _find_cover_file(self, final_video: str, raw_video: str) -> str:
        """尝试找封面: 优先 final_video 同目录 jpg，其次 raw_video 同目录 jpg"""
        candidates_dirs = [os.path.dirname(final_video)]
        if raw_video and raw_video != final_video:
            candidates_dirs.append(os.path.dirname(raw_video))
        for d in candidates_dirs:
            if not os.path.isdir(d):
                continue
            base = os.path.splitext(os.path.basename(final_video))[0]
            for ext in (".jpg", ".jpeg", ".png", ".webp"):
                cand = os.path.join(d, base + ext)
                if os.path.exists(cand):
                    return cand
            # 再试原始文件名
            base2 = os.path.splitext(os.path.basename(raw_video))[0] if raw_video else ""
            if base2 and base2 != base:
                for ext in (".jpg", ".jpeg", ".png", ".webp"):
                    cand = os.path.join(d, base2 + ext)
                    if os.path.exists(cand):
                        return cand
        return ""

    def _auto_add_to_pool(
        self, job: AutoJob, final_video: str, srt_path: str,
        copy_path: str, meta: dict, raw_video: str,
    ) -> None:
        """全自动管线完成烧录后 → 入视频候选池（静默，不弹窗）"""
        try:
            from core.publish.pool import VideoPool

            if not os.path.exists(final_video):
                logger.warning(f"[AutoPipeline] final_video 不存在，不入池: {final_video}")
                return

            # 找封面
            cover_path = self._find_cover_file(final_video, raw_video)

            # 找源 URL（从 download 结果）
            source_url = job.url if job.url.startswith("http") else ""

            pool_id = VideoPool.add(
                final_video_path=final_video,
                source_url=source_url,
                video_id=job.video_id,
                cover_path=cover_path,
                srt_path=srt_path if os.path.exists(srt_path) else "",
                title_original=(meta or {}).get("title", "") or "",
                title_translated="",  # 自动管线未额外翻译标题，留给发布页让用户从 SRT 或手动填
                desc_original=(meta or {}).get("description", "") or "",
                desc_translated="",
                lang=(meta or {}).get("language") or job.language or "",
                category=(meta or {}).get("category") or job.category or "",
                channel_name=(meta or {}).get("channel", "") or "",
                duration_sec=int((meta or {}).get("duration", 0) or 0),
                pipeline_source="auto",
                copy_path=copy_path,
            )
            if pool_id:
                logger.info(f"[AutoPipeline] 入池成功: pool_id={pool_id}")
        except Exception as e:
            import traceback
            logger.error(f"[AutoPipeline] 入池失败（不影响主流程）: {e}\n{traceback.format_exc()}")