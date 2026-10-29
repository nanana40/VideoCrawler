"""
全局资源锁与并发节流

解决的问题：
  1. FFmpeg 吃 CPU → 全局串行锁，同时只跑一个 ffmpeg subprocess
     其它流水线阶段（download / analyze / LLM 打标）继续并行不受影响。
  2. 外部 API 并发请求风暴 → 按 endpoint 分类的 Semaphore + 指数退避重试。

使用方式：
    from utils.resource_locks import FFMPEG_LOCK, api_retry

    # 方式 A：with 语句（ffmpeg subprocess）
    with FFMPEG_LOCK:
        subprocess.run(["ffmpeg", "-i", ...])

    # 方式 B：装饰器（给 requests 调用加重试）
    @api_retry(max_retries=3, name="llm_api")
    def call_llm(...):
        requests.post(...)
"""

from __future__ import annotations

import threading
import time
import random
import functools
from typing import Callable, Any, Dict, Optional, Tuple, Iterable

# ================================================================
# 全局 FFmpeg 串行锁
# ----------------------------------------------------------------
# 为什么用 Semaphore(1) 而不是 Lock()：
#   Semaphore 可以在创建时指定并发度，未来如果有多核机器想放宽到 2
#   只需改这个数字，不用换类型。
# ================================================================

FFMPEG_LOCK = threading.Semaphore(1)

# 用于识别哪些错误是 ffmpeg 调用点（便于日志打印排队信息）
_ffmpeg_wait_log_lock = threading.Lock()


class _FFMPEGLockCtx:
    """with FFMPEG_LOCK 的可选包装：额外打印排队日志"""

    def __enter__(self):
        acquired = FFMPEG_LOCK.acquire(blocking=False)
        if not acquired:
            tid = threading.current_thread().ident
            with _ffmpeg_wait_log_lock:
                print(f"[FFmpeg Lock] 线程 {tid} 等待 ffmpeg 空闲...")
            FFMPEG_LOCK.acquire(blocking=True)
            with _ffmpeg_wait_log_lock:
                print(f"[FFmpeg Lock] 线程 {tid} 获得 ffmpeg 锁")
        return self

    def __exit__(self, *args):
        FFMPEG_LOCK.release()


def ffmpeg_guard(func: Callable = None):
    """
    装饰器版本的 FFmpeg 锁：

    @ffmpeg_guard
    def burn_subtitle(...):
        subprocess.run(["ffmpeg", ...])
    """
    def _decorate(fn: Callable) -> Callable:
        @functools.wraps(fn)
        def _wrapper(*args, **kwargs):
            with FFMPEG_LOCK:
                return fn(*args, **kwargs)
        return _wrapper
    if func is None:
        return _decorate
    return _decorate(func)


# ================================================================
# 外部 API 统一重试
# ----------------------------------------------------------------
# 重试条件：错误消息中含以下关键词之一
#   HTTP 状态码:     503 500 429 UNAVAILABLE overloaded
#   连接级错误:      Server disconnected RemoteProtocolError
#                    ReadTimeout ConnectTimeout timeout
#                    EOF occurred Connection reset Broken pipe
#                    Temporary failure Name resolution
#                    RemoteDisconnected BadStatusLine
#   系统级:          ConnectionError OSError（底层 socket 断开）
# ================================================================

_DEFAULT_RETRYABLE_KEYWORDS: Tuple[str, ...] = (
    # --- HTTP 状态码 ---
    "503", "500", "429", "502",
    "UNAVAILABLE", "overloaded",
    # --- HTTPX / HTTPCORE 连接类错误（VPN TUN 重连导致 WinError 10054 等）---
    "WinError 10054", "WinError 10053", "WinError 10049", "WinError 10060",
    "ConnectError", "ConnectTimeout", "TransportError", "ReadError", "WriteError",
    "PoolTimeout", "ProtocolError", "RemoteDisconnected",
    "ECONNRESET", "ECONNABORTED", "EPIPE",
    # --- 老关键词（requests / socket 原生）---
    "Server disconnected",
    "ReadTimeout", "timeout", "timed out",
    "EOF occurred", "Connection reset", "Broken pipe",
    "Temporary failure", "Name resolution",
    "BadStatusLine", "ConnectionError", "ChunkedEncodingError",
)


def is_retryable_error(exc: BaseException, extra_keywords: Iterable[str] = ()) -> bool:
    """判断异常是否属于可重试类型"""
    if isinstance(exc, (ConnectionError, TimeoutError, OSError)):
        return True
    msg = str(exc)
    haystack = msg.upper()
    keywords = set(_DEFAULT_RETRYABLE_KEYWORDS) | set(k.upper() for k in extra_keywords)
    for kw in keywords:
        if kw.upper() in haystack:
            return True
    return False


def _backoff_seconds(attempt: int, max_cap: float = 16.0, jitter: float = 1.5) -> float:
    """指数退避 + 抖动：1s → 2s → 4s → 8s → min(cap, 2^n) + random(0, jitter)"""
    base = min(2 ** max(attempt - 1, 0), max_cap)
    return base + random.uniform(0, jitter)


def api_retry(
    max_retries: int = 3,
    name: str = "api_call",
    extra_keywords: Iterable[str] = (),
    re_raise_non_retryable: bool = True,
):
    """
    通用重试装饰器。

    Args:
        max_retries: 最多重试次数（不含首次）
        name: 日志里显示的调用名
        extra_keywords: 额外的可重试错误关键词
        re_raise_non_retryable: 不可重试的错误是否立即抛出（True=立即抛，False=记录后继续降级）
    """
    def _decorate(fn: Callable) -> Callable:
        @functools.wraps(fn)
        def _wrapper(*args, **kwargs):
            last_exc: Optional[BaseException] = None
            total_attempts = max_retries + 1
            for attempt in range(1, total_attempts + 1):
                try:
                    return fn(*args, **kwargs)
                except BaseException as e:
                    last_exc = e
                    if is_retryable_error(e, extra_keywords):
                        if attempt <= max_retries:
                            wait = _backoff_seconds(attempt)
                            _log_retry(name, attempt, max_retries, wait, e)
                            time.sleep(wait)
                            continue
                    if re_raise_non_retryable or attempt <= max_retries:
                        raise
                    # 最后一次且不可重试 → 也抛
                    raise
            # 理论不会到这里
            raise last_exc  # type: ignore[misc]
        return _wrapper
    return _decorate


def _log_retry(name: str, attempt: int, max_retries: int, wait: float, exc: BaseException) -> None:
    try:
        from utils.logger import get_crawler_logger
        get_crawler_logger().warning(
            f"[RETRY] [{name}] (retry {attempt}/{max_retries}): "
            f"{str(exc)[:100]} — {wait:.1f}s 后重试"
        )
    except Exception:
        print(f"[RETRY] [{name}] (retry {attempt}/{max_retries}): {str(exc)[:100]} — {wait:.1f}s")


# ================================================================
# 模块级 API 并发节流器（可选，默认不启用）
# ----------------------------------------------------------------
# 对某些有严格 RPM/QPS 限制的 endpoint（如 YouTube Data API v3），
# 可以给它包一层 RateLimiter。示例：
#
#   youtube_api_limiter = AsyncRateLimiter(max_calls=10000, period=86400)
#   with youtube_api_limiter:
#       response = requests.get(...)
# ================================================================


class AsyncRateLimiter:
    """
    滚动窗口限流器（线程安全）。

    相比简单固定窗口的改进：
      1. 滚动窗口：用真实时间戳清理过期条目，窗口边界不会出现"突发"
      2. retryDelay：429 响应里带 retryDelay 时，主动把它并入等待队列
      3. 排队日志：排队等待时打印一次，避免日志刷屏
      4. 与 ThreadPoolExecutor 配合：Semaphore(1) 让所有线程串行进 API 调用区，
         滚动窗口再把频率压到配额以内

    典型用法：
        limiter = AsyncRateLimiter(max_calls=12, period=60.0, name="Gemini")
        with limiter:
            client.models.generate_content(...)
        # 429 时
        limiter.set_retry_delay(10.0)   # 下次进入前至少等 10s
    """

    def __init__(
        self,
        max_calls: int,
        period: float = 60.0,
        name: str = "api",
        global_serial: bool = True,
    ) -> None:
        self._max = max_calls
        self._period = period
        self._name = name
        self._timestamps: list = []
        self._lock = threading.Lock()
        # 服务端建议的最小等待时间（秒），429 时写入，下次 acquire 时并入
        self._retry_delay = 0.0
        self._next_allowed_ts = 0.0  # 与 retry_delay 配合：绝对时间戳
        self._wait_log_lock = threading.Lock()
        # 全局串行锁：让同一个 endpoint 的所有 API 调用严格串行
        self._serial_lock = threading.Lock() if global_serial else None

    # --- 公共 API -------------------------------------------------

    def set_retry_delay(self, delay: float) -> None:
        """
        收到 429 / retryDelay 时调用。
        写入后，下一个排队进来的线程至少要等 delay 秒才能放行。
        用绝对时间戳存储，避免 set_retry_delay 与排队线程 race。
        """
        delay = max(0.0, float(delay))
        with self._lock:
            self._next_allowed_ts = max(self._next_allowed_ts, time.time() + delay)
            self._retry_delay = delay  # 兼容旧字段

    def __enter__(self):
        # 全局串行锁：保证同一 endpoint 同一时间只有一个线程在真正发请求
        if self._serial_lock is not None:
            self._serial_lock.acquire()
        try:
            self._wait_for_slot()
        except Exception:
            if self._serial_lock is not None:
                self._serial_lock.release()
            raise
        return self

    def __exit__(self, *args):
        if self._serial_lock is not None:
            self._serial_lock.release()

    # --- 内部 -----------------------------------------------------

    def _wait_for_slot(self) -> None:
        """阻塞直到拿到滚动窗口内的一个调用槽"""
        waited = False
        last_log_ts = 0.0
        while True:
            with self._lock:
                now = time.time()

                # 先处理服务端建议的 retryDelay（绝对时间戳）
                if self._next_allowed_ts > now:
                    wait_sec = self._next_allowed_ts - now
                    if not waited:
                        self._log_queue(wait_sec)
                        waited = True
                        last_log_ts = now
                    time.sleep(wait_sec)
                    continue

                # 清理过期时间戳（滚动窗口）
                self._timestamps = [
                    t for t in self._timestamps if now - t < self._period
                ]

                if len(self._timestamps) < self._max:
                    self._timestamps.append(time.time())
                    return

                # 窗口满 → 等最旧的过期
                oldest = self._timestamps[0]
                wait_sec = self._period - (now - oldest)
                wait_sec = max(wait_sec, 0.05)

            # 控制排队日志频率：每 5s 最多打一条
            if not waited or (time.time() - last_log_ts >= 5.0):
                self._log_queue(wait_sec)
                waited = True
                last_log_ts = time.time()
            time.sleep(wait_sec)

    def _log_queue(self, wait_sec: float) -> None:
        try:
            from utils.logger import get_crawler_logger
            get_crawler_logger().info(
                f"[RateLimiter:{self._name}] 排队中，预计等待 {wait_sec:.1f}s "
                f"(滚动窗口 {self._max}/{self._period:.0f}s)"
            )
        except Exception:
            with self._wait_log_lock:
                print(
                    f"[RateLimiter:{self._name}] 排队中，预计等待 {wait_sec:.1f}s "
                    f"(滚动窗口 {self._max}/{self._period:.0f}s)"
                )

    # --- 状态查询（诊断用） ---------------------------------------

    def stats(self) -> Dict[str, Any]:
        with self._lock:
            now = time.time()
            self._timestamps = [
                t for t in self._timestamps if now - t < self._period
            ]
            return {
                "name": self._name,
                "used_in_window": len(self._timestamps),
                "max": self._max,
                "period": self._period,
                "serial": self._serial_lock is not None,
                "retry_delay_pending": max(0.0, self._next_allowed_ts - now),
            }


# 向后兼容别名
RateLimiter = AsyncRateLimiter


# ================================================================
# Gemini API 全局限流器（模块单例）
# ----------------------------------------------------------------
# 免费层硬限制：
#   - 15 RPM / 1,500 RPD / 1M TPM
#   - 20 requests/day/模型（这个按模型分，但 upload 也算）
#
# 策略：
#   1. 全局串行锁 → 所有线程的 generate_content + files.upload + files.delete
#      严格排队，永远不会并发打到 Gemini endpoint
#   2. 滚动窗口 12 次 / 60s → 留 3 次 buffer 给 cleanup/upload 抢的时候
#   3. 429 响应里的 retryDelay 会被写入，强制整个队列一起等
# ================================================================

GEMINI_RATE_LIMITER = AsyncRateLimiter(
    max_calls=12,
    period=60.0,
    name="Gemini",
    global_serial=True,
)

