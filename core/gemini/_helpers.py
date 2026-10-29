"""
core.gemini._helpers — 模块级辅助函数

从 core/gemini_engine.py 的顶层 helper 函数迁移而来。
门面文件 core/gemini_engine.py 和 mixin 都从这里引用。
"""
from __future__ import annotations

import os
import re
import json
import time
import threading
from typing import List, Optional, Dict, Any

from utils.logger import get_translate_logger
from utils.resource_locks import (
    is_retryable_error,
    _backoff_seconds,
    GEMINI_RATE_LIMITER,
)
import json as _json_std

logger = get_translate_logger()


def _wrap_text(text: str, cpl: int) -> List[str]:
    """把文本按字符数 cpl 每行换行（对中英混排友好：优先空格切，必要时按字符截断）"""
    cpl = max(1, int(cpl))
    lines: List[str] = []
    remainder = text.strip()
    while remainder:
        if len(remainder) <= cpl:
            lines.append(remainder)
            break
        chunk = remainder[:cpl]
        space = chunk.rfind(" ")
        cut = space if space > cpl // 3 else cpl
        lines.append(chunk[:cut].rstrip())
        remainder = remainder[cut:].lstrip()
    return lines


def _is_429(exc: BaseException) -> bool:
    """判断异常是否为 429 rate limit 错误（兼容 google-genai SDK 的不同 error 结构）"""
    msg = str(exc).upper()
    if "429" in msg or "RATE_LIMIT" in msg or "RATELIMIT" in msg:
        return True
    resp = getattr(exc, "response", None)
    if resp is not None:
        code = getattr(resp, "status_code", None)
        if code == 429:
            return True
        status = getattr(resp, "status", None)
        if status is not None and ("429" in str(status) or "RATE" in str(status).upper()):
            return True
    return False


def _parse_duration(raw: str) -> float:
    """把各种 Duration 字符串转成秒数（float）"""
    raw = str(raw).strip().lower()
    if not raw:
        return 0.0
    multipliers = [
        (0.000_000_001, "ns"), (0.000_001, "µs"), (0.000_001, "us"),
        (0.001, "ms"), (1.0, "s"), (60.0, "m"), (3600.0, "h"),
    ]
    for mult, suffix in multipliers:
        if raw.endswith(suffix):
            num_part = raw[: -len(suffix)].strip()
            try:
                return float(num_part) * mult
            except ValueError:
                continue
    m = re.search(r"(\d+(?:\.\d+)?)", raw)
    if m:
        try:
            return float(m.group(1))
        except ValueError:
            pass
    return 0.0


def _apply_unit(num: float, unit: str) -> float:
    """按单位转秒"""
    unit = (unit or "").lower()
    mapping = {
        "ns": 1e-9, "µs": 1e-6, "us": 1e-6,
        "ms": 1e-3, "s": 1.0, "sec": 1.0, "seconds": 1.0,
        "m": 60.0, "min": 60.0, "minutes": 60.0,
        "h": 3600.0, "hr": 3600.0, "hours": 3600.0,
    }
    mult = mapping.get(unit, 1.0)
    return num * mult


def _walk_for_retry_delay(node) -> Optional[float]:
    """递归遍历 dict/list，寻找 'retry_delay' 或 'retryDelay' 字段"""
    if isinstance(node, dict):
        for k, v in node.items():
            kl = str(k).lower().replace("_", "")
            if kl in ("retrydelay", "retry", "retryafter"):
                return _parse_duration(str(v)) if isinstance(v, str) else None
            r = _walk_for_retry_delay(v)
            if r:
                return r
    elif isinstance(node, list):
        for item in node:
            r = _walk_for_retry_delay(item)
            if r:
                return r
    return None


def _extract_retry_delay(exc: BaseException) -> float:
    """从 429 响应中提取服务端建议的重试延迟（秒）

    ★ 返回值强制 cap 在 [0, MAX_RETRY_DELAY_CAP] 之间
      Google 正常不会建议等超过 120 秒，返回更大值一定是解析出了问题
      （毫秒被当成秒 / 纯数字无单位被误判等）
    """
    MAX_RETRY_DELAY_CAP = 120.0  # 超过 2 分钟一律按 2  分钟计

    resp = getattr(exc, "response", None)
    if resp is not None:
        headers = getattr(resp, "headers", None)
        if headers:
            ra = headers.get("Retry-After") or headers.get("retry-after")
            if ra:
                d = _parse_duration(ra)
                if d > 0:
                    return min(d, MAX_RETRY_DELAY_CAP)
            for k, v in getattr(resp, "headers", {}).items():
                if "retry" in k.lower() and v:
                    d = _parse_duration(str(v))
                    if d > 0:
                        return min(d, MAX_RETRY_DELAY_CAP)
        try:
            body = getattr(resp, "json", None)
            if callable(body):
                j = body()
                d = _walk_for_retry_delay(j)
                if d:
                    return min(d, MAX_RETRY_DELAY_CAP)
            elif isinstance(body, dict):
                d = _walk_for_retry_delay(body)
                if d:
                    return min(d, MAX_RETRY_DELAY_CAP)
        except Exception:
            pass
    txt = str(exc)
    patterns = [
        r"retry\s*(?:in|after|delay|within)\s*[:=]?\s*(\d+(?:\.\d+)?)\s*(ns|us|µs|ms|s|sec|seconds|m|min|minutes|h|hr|hours)",
        r"in\s+(\d+(?:\.\d+)?)\s*(ns|us|µs|ms|s|sec|seconds|m|min|minutes|h|hr|hours)",
        r"retry\s*in\s+(\d+(?:\.\d+)?)\s*(?:seconds?|minutes?|hours?)",
    ]
    for pat in patterns:
        m = re.search(pat, txt, re.IGNORECASE)
        if m:
            num = float(m.group(1))
            unit = m.group(2) if m.lastindex >= 2 else "s"
            d = _apply_unit(num, unit)
            return min(d, MAX_RETRY_DELAY_CAP)
    return 0.0


def _is_quota_exhausted(exc: BaseException) -> bool:
    """判断 429 是否是真的'今日配额耗尽'（不是普通 RPM 超限）

    区分依据:
      - message 里含 "quota" / "daily" / "monthly" / "exceeded your current quota"
      - 纯 "RESOURCE_EXHAUSTED" / "RATE_LIMIT_EXCEEDED" 是暂时的 RPM 超限
    """
    msg = str(exc).lower()
    quota_keywords = (
        "quota", "daily limit", "monthly", "exceeded your current",
        "free tier", "billing", "plan",
    )
    return any(kw in msg for kw in quota_keywords)


def _extract_exhausted_model(exc: BaseException) -> Optional[str]:
    """从异常中提取 exhausted 的模型名（用于标记今日配额耗尽）"""
    msg = str(exc)
    m = re.search(r"model\s+['\"]?([a-zA-Z0-9._\-]+)['\"]?\s+(?:quota|rate|limit|exhaust)", msg, re.IGNORECASE)
    if m:
        return m.group(1)
    resp = getattr(exc, "response", None)
    if resp is not None:
        try:
            body = getattr(resp, "json", None)
            if callable(body):
                j = body()
                def _walk(n):
                    if isinstance(n, dict):
                        for k, v in n.items():
                            if str(k).lower() in ("model", "model_name") and isinstance(v, str):
                                return v
                            r = _walk(v)
                            if r:
                                return r
                    elif isinstance(n, list):
                        for item in n:
                            r = _walk(item)
                            if r:
                                return r
                    return None
                return _walk(j)
        except Exception:
            pass
    return None


def _today_end_epoch() -> float:
    """本地时间当天 23:59:59 的 epoch 秒"""
    now = time.localtime()
    end = time.mktime(time.struct_time((now.tm_year, now.tm_mon, now.tm_mday, 23, 59, 59, 0, 0, now.tm_isdst)))
    return end


_EXHAUSTED: Dict[str, float] = {}
_EXHAUSTED_LOCK = threading.Lock()


def _is_model_exhausted(model: str) -> bool:
    with _EXHAUSTED_LOCK:
        expiry = _EXHAUSTED.get(model, 0.0)
        if expiry and expiry > time.time():
            return True
        return False


def _mark_model_exhausted(model: str, seconds: float = 0.0) -> None:
    if not model:
        return
    expiry = time.time() + seconds if seconds > 0 else _today_end_epoch()
    with _EXHAUSTED_LOCK:
        _EXHAUSTED[model] = expiry
    logger.warning(f"[Gemini] 模型 {model} 已标记为今日配额耗尽，跳过直到 {time.strftime('%H:%M:%S', time.localtime(expiry))}")
