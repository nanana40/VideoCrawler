"""
publish_queue.py — 发布队列管理器

把多个视频排队串行发布，避免同时上传导致账号被风控。

核心类 PublishQueueManager（单例）:
  - enqueue(job)     入队（支持批量）
  - start() / stop()  控制 worker 线程
  - snapshot()       查询当前队列 + 进度
  - clear()          清空队列

队列项 PublishJob:
  - pool_id          video_pool.id（必填）
  - account_id       publish_account.id（必填）
  - title / desc ... 可选覆盖（None 表示用池里的数据兜底）
  - retry_count      当前已重试次数
  - max_retry        最大重试（默认 2）
  - scheduled_ts     定时发布时间戳（None=立即）

观察者模式：外部（web/main.py）注册回调，每次状态变化时广播，
由 web 的 TASKS.push_log 转发到 SSE 给手机端看。
"""

from __future__ import annotations

import os
import random
import threading
import time
import uuid
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple

from loguru import logger

from .service import PublishService
from .clients import VideoMeta, normalize_tags
from .pool import VideoPool


# =====================================================
# 数据结构
# =====================================================

@dataclass
class PublishJob:
    """单个发布任务"""
    pool_id: int
    account_id: int
    # 可选覆盖字段（None 表示用池里的）
    title: Optional[str] = None
    description: Optional[str] = None
    tags: Optional[List[str]] = None
    cover_path: Optional[str] = None
    scheduled_ts: Optional[int] = None
    original: bool = True
    # 运行时状态
    job_id: str = field(default_factory=lambda: uuid.uuid4().hex[:8])
    retry_count: int = 0
    max_retry: int = 2
    status: str = "pending"  # pending / waiting / uploading / done / failed / skipped
    result: Optional[Dict[str, Any]] = None
    created_at: float = field(default_factory=time.time)
    started_at: Optional[float] = None
    finished_at: Optional[float] = None

    def is_scheduled(self) -> bool:
        return self.scheduled_ts is not None and self.scheduled_ts > time.time()


# =====================================================
# 队列管理器
# =====================================================

class PublishQueueManager:
    """发布队列单例"""

    _instance: Optional["PublishQueueManager"] = None
    _instance_lock = threading.Lock()

    def __init__(self) -> None:
        self._queue: deque[PublishJob] = deque()
        self._queue_lock = threading.Lock()
        self._worker_thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._processing = False
        self._current_job: Optional[PublishJob] = None
        # 已完成历史（环形缓冲，最多 200 条）
        self._history: deque[PublishJob] = deque(maxlen=200)
        # 日志观察者（web/main.py 注册后转发到 SSE）
        self._log_observers: List[Callable[[str], None]] = []
        self._observer_lock = threading.Lock()
        # 风控保护参数: (冷却下限秒, 冷却上限秒, 每日发布上限; 0=不限)
        self._cooldown_range, self._daily_limit = self._load_risk_config()

    # ---------- 风控保护配置 ----------
    @staticmethod
    def _load_risk_config() -> Tuple[Tuple[int, int], int]:
        """从 config.yaml 的 publish 段读取风控参数（软读取，缺省走默认值）。

        publish:
          cooldown_min_sec: 600   # 相邻两次发布最小间隔
          cooldown_max_sec: 1800  # 相邻两次发布最大间隔（随机取值，拟人节奏）
          daily_limit: 5          # 每日成功发布上限（0=不限）
        """
        try:
            from utils.config_loader import load_config
            pub = (load_config() or {}).get("publish", {}) or {}
            lo = max(0, int(pub.get("cooldown_min_sec", 600)))
            hi = max(lo, int(pub.get("cooldown_max_sec", 1800)))
            limit = max(0, int(pub.get("daily_limit", 5)))
            return (lo, hi), limit
        except Exception:
            return (600, 1800), 5

    def _today_done_count(self) -> int:
        """统计今天已成功发布的条数（基于内存历史，环形 200 条足够覆盖一天）"""
        today = time.strftime("%Y-%m-%d")
        return sum(
            1 for j in self._history
            if j.status == "done" and j.finished_at
            and time.strftime("%Y-%m-%d", time.localtime(j.finished_at)) == today
        )

    # ---------- 单例 ----------
    @classmethod
    def instance(cls) -> "PublishQueueManager":
        with cls._instance_lock:
            if cls._instance is None:
                cls._instance = cls()
        return cls._instance

    # ---------- 观察者 ----------
    def add_log_observer(self, cb: Callable[[str], None]) -> None:
        with self._observer_lock:
            if cb not in self._log_observers:
                self._log_observers.append(cb)

    def remove_log_observer(self, cb: Callable[[str], None]) -> None:
        with self._observer_lock:
            if cb in self._log_observers:
                self._log_observers.remove(cb)

    def _log(self, msg: str) -> None:
        """内部日志 → 广播给所有观察者"""
        logger.info(f"[PublishQueue] {msg}")
        with self._observer_lock:
            obs = list(self._log_observers)
        for cb in obs:
            try:
                cb(f"📤 [发布队列] {msg}")
            except Exception:
                pass

    # ---------- 队列操作 ----------
    def enqueue(self, job: PublishJob) -> str:
        """入队，返回 job_id"""
        with self._queue_lock:
            self._queue.append(job)
            self._log(f"➕ 入队 job={job.job_id} pool={job.pool_id} account={job.account_id}"
                      + (" (定时 {})".format(time.strftime("%m-%d %H:%M", time.localtime(job.scheduled_ts))) if job.is_scheduled() else ""))
            if not self._worker_thread or not self._worker_thread.is_alive():
                self._worker_thread = threading.Thread(target=self._worker_loop, name="publish-queue", daemon=True)
                self._worker_thread.start()
        return job.job_id

    def enqueue_batch(self, jobs: List[PublishJob]) -> List[str]:
        """批量入队"""
        ids = []
        for j in jobs:
            ids.append(self.enqueue(j))
        return ids

    def queue_size(self) -> int:
        with self._queue_lock:
            return len(self._queue)

    def is_busy(self) -> bool:
        return self._processing or self.queue_size() > 0

    def clear(self) -> int:
        """清空待发布队列（不影响正在上传的），返回清掉多少条"""
        with self._queue_lock:
            n = len(self._queue)
            self._queue.clear()
            if n > 0:
                self._log(f"🗑 已清空队列（{n} 条待发布）")
            return n

    def cancel_job(self, job_id: str) -> bool:
        """取消队列中的某个 job（还没开始的）"""
        with self._queue_lock:
            for i, j in enumerate(self._queue):
                if j.job_id == job_id:
                    self._queue.remove(j)
                    self._log(f"✖ 已取消 job={job_id}")
                    return True
        return False

    # ---------- Worker ----------
    def _worker_loop(self) -> None:
        self._log("🚀 发布队列 worker 启动")
        while not self._stop_event.is_set():
            # 取任务：跳过未到时间的定时任务，找队列里第一个可执行项，
            # 避免队首定时任务阻塞其后的立即任务（AUDIT-0062）
            job: Optional[PublishJob] = None
            with self._queue_lock:
                if not self._queue:
                    break
                for i, j in enumerate(self._queue):
                    if not j.is_scheduled():
                        job = j
                        del self._queue[i]
                        break

            if job is None:
                # 队列只剩未到时间的定时任务：等到最早的到点时间。
                # 分段 sleep（每 30 秒检查 stop_event），期间新入队的立即任务
                # 会在下一轮扫描被立即取到，不会被整段等待卡住。
                with self._queue_lock:
                    next_ts = min(
                        (j.scheduled_ts for j in self._queue if j.scheduled_ts is not None),
                        default=None,
                    )
                if next_ts is None:
                    continue  # 极端竞态：等待期间队列被清空，回到循环重新判断
                wait_sec = next_ts - time.time()
                if wait_sec <= 0:
                    continue  # 已到点，重新扫描取任务
                self._log(f"⏰ 队列仅剩定时任务，最早 {time.strftime('%m-%d %H:%M', time.localtime(next_ts))}，等待 {int(wait_sec)}s")
                end_time = time.time() + wait_sec
                while time.time() < end_time and not self._stop_event.is_set():
                    time.sleep(min(30, end_time - time.time()))
                continue

            # 风控保护: 达到每日发布上限的剩余任务直接跳过（不计失败，不重试）
            if self._daily_limit > 0 and self._today_done_count() >= self._daily_limit:
                job.status = "skipped"
                job.result = {"error": f"已达每日发布上限 {self._daily_limit}（风控保护，可在 config.yaml publish.daily_limit 调整）"}
                self._log(f"🛡 job={job.job_id} 跳过: {job.result['error']}")
                job.finished_at = time.time()
                self._history.append(job)
                continue

            # 执行发布
            self._processing = True
            self._current_job = job
            job.status = "uploading"
            job.started_at = time.time()

            try:
                ok = self._execute_one(job)
                if ok:
                    job.status = "done"
                    self._log(f"✅ job={job.job_id} 发布成功 → {job.result.get('remote_url', '')}")
                else:
                    # 失败 → 重试
                    if job.retry_count < job.max_retry:
                        job.retry_count += 1
                        job.status = "pending"
                        self._log(f"⚠ job={job.job_id} 失败，第 {job.retry_count}/{job.max_retry} 次重试...")
                        with self._queue_lock:
                            self._queue.append(job)
                        # 退避等待：3s, 6s, 12s
                        time.sleep(3 * job.retry_count)
                    else:
                        job.status = "failed"
                        self._log(f"❌ job={job.job_id} 最终失败: {job.result.get('error', 'unknown')}")

            except Exception as e:
                import traceback
                job.status = "failed"
                job.result = {"error": f"{e}\n{traceback.format_exc()}"}
                self._log(f"💥 job={job.job_id} 异常: {e}")

            job.finished_at = time.time()
            # 放入历史
            self._history.append(job)
            self._current_job = None
            self._processing = False

            # 风控保护: 相邻两次发布之间强制随机冷却（拟人节奏，可被 stop 打断）
            lo, hi = self._cooldown_range
            if hi > 0:
                wait = random.uniform(lo, hi)
                self._log(f"🛡 风控保护: 冷却 {int(wait)}s 后处理下一条（config.yaml publish.cooldown_*_sec 可调）")
                end_time = time.time() + wait
                while time.time() < end_time and not self._stop_event.is_set():
                    time.sleep(min(5.0, max(0.1, end_time - time.time())))

        self._log("🛑 发布队列 worker 退出")

    def _execute_one(self, job: PublishJob) -> bool:
        """执行单个 job，返回是否成功。job.result 会被填充。"""
        # 1. 视频池校验
        pool_item = VideoPool.get(job.pool_id)
        if not pool_item:
            job.result = {"error": f"video_pool 条目不存在: pool_id={job.pool_id}"}
            return False

        video_path = pool_item["final_video_path"]
        if not os.path.exists(video_path):
            job.result = {"error": f"视频文件不存在: {video_path}"}
            return False

        # 2. 账号校验（PublishService.publish 里会再校验一次，但这里先打日志）
        from .accounts import AccountManager
        acc = AccountManager.get_account(job.account_id)
        if not acc:
            job.result = {"error": f"账号不存在: account_id={job.account_id}"}
            return False

        platform = acc["platform"]
        nickname = acc.get("nickname") or acc.get("uid") or "?"
        self._log(f"📤 开始发布 → {platform} · {nickname} · {os.path.basename(video_path)}")

        # 3. 组装 VideoMeta（job 覆盖 > pool 兜底）
        meta = VideoMeta()
        meta.title = job.title or pool_item.get("title_translated") or pool_item.get("title_original") or os.path.basename(video_path)
        meta.description = job.description or pool_item.get("desc_translated") or pool_item.get("desc_original") or ""
        meta.tags = normalize_tags(job.tags)
        meta.original_declaration = job.original
        meta.scheduled_ts = job.scheduled_ts

        # 封面
        if job.cover_path and os.path.exists(job.cover_path):
            meta.cover_path = job.cover_path
        elif pool_item.get("cover_path") and os.path.exists(pool_item["cover_path"]):
            meta.cover_path = pool_item["cover_path"]

        # 4. 进度回调
        def _progress(uploaded: int, total: int):
            if total > 0:
                pct = round(uploaded / total * 100, 1)
                self._log(f"📊 job={job.job_id} 上传进度: {pct}% ({uploaded}/{total})")

        # 5. 调用 PublishService
        result = PublishService.publish(
            pool_id=job.pool_id,
            account_id=job.account_id,
            meta=meta,
            on_progress=_progress,
        )

        job.result = result
        return bool(result.get("ok"))

    # ---------- 状态查询 ----------
    @staticmethod
    def _pool_title(pool_id: int) -> str:
        """查视频池标题 (快照展示用; 查不到回退空串, 由前端显示 job_id)"""
        try:
            it = VideoPool.get(pool_id)
            if it:
                return (
                    it.get("title_translated")
                    or it.get("title_original")
                    or os.path.basename(it.get("final_video_path", "") or "")
                )
        except Exception:
            pass
        return ""

    def snapshot(self) -> Dict[str, Any]:
        """当前状态快照"""
        with self._queue_lock:
            pending = list(self._queue)
        cur = self._current_job

        return {
            "busy": self._processing or len(pending) > 0,
            "processing": self._processing,
            "current": {
                "job_id": cur.job_id if cur else None,
                "pool_id": cur.pool_id if cur else None,
                "account_id": cur.account_id if cur else None,
                "status": cur.status if cur else None,
                "title": self._pool_title(cur.pool_id) if cur else "",
                "elapsed_sec": round(time.time() - cur.started_at, 1) if cur and cur.started_at else 0,
            },
            "pending_count": len(pending),
            "pending": [
                {
                    "job_id": j.job_id,
                    "pool_id": j.pool_id,
                    "account_id": j.account_id,
                    "status": j.status,
                    "retry": j.retry_count,
                    "title": self._pool_title(j.pool_id),
                    "scheduled_ts": j.scheduled_ts,
                    "created_at": time.strftime("%m-%d %H:%M", time.localtime(j.created_at)),
                }
                for j in pending
            ],
            "history_count": len(self._history),
            "history": [
                {
                    "job_id": j.job_id,
                    "pool_id": j.pool_id,
                    "account_id": j.account_id,
                    "status": j.status,
                    "retry": j.retry_count,
                    "result": {k: v for k, v in (j.result or {}).items() if k in ("ok", "remote_id", "remote_url", "error")},
                    "finished_at": time.strftime("%m-%d %H:%M:%S", time.localtime(j.finished_at)) if j.finished_at else None,
                }
                for j in list(self._history)[-30:]
            ],
        }

    # ---------- 生命周期 ----------
    def start(self) -> None:
        """如有待处理任务则启动 worker"""
        if not self._worker_thread or not self._worker_thread.is_alive():
            with self._queue_lock:
                if self._queue:
                    self._worker_thread = threading.Thread(target=self._worker_loop, name="publish-queue", daemon=True)
                    self._worker_thread.start()

    def stop(self) -> None:
        """请求 worker 退出（正在上传的那个会继续跑完）"""
        self._stop_event.set()


# 便捷函数
def get_publish_queue() -> PublishQueueManager:
    return PublishQueueManager.instance()
