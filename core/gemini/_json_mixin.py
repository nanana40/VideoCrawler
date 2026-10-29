"""JsonMixin — 7 个方法, 全部实例方法 (非 static)"""
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

try:
    from core.image_provider import try_inpaint_translate as _try_inpaint
except Exception:  # pragma: no cover
    _try_inpaint = None

logger = get_translate_logger()


class JsonMixin:
    """JsonMixin — 7 个方法 (全部实例方法)"""

    # ----------------------------------------------------------------
    # 字段名 & 值类型容错表 — Gemini 经常不听 prompt schema
    # ----------------------------------------------------------------
    _TIME_KEYS = ("start_time", "startTime", "start", "from", "begin")
    _END_KEYS = ("end_time", "endTime", "end", "to", "finish", "stop")
    _SOURCE_KEYS = ("source_text", "sourceText", "original", "source", "from_text", "src_text")
    _TARGET_KEYS = ("target_text", "targetText", "translated_text", "translation", "translated", "to_text")
    _TEXT_KEYS = ("text", "content", "line")  # 兜底: 当只有一个 text 字段时用作文本

    @staticmethod
    def _parse_time(val: Any) -> float:
        """把各种时间格式统一转成 float 秒

        处理:
          - float / int 秒数:  1.9 / 12 / 12.345       → 直接转
          - HH:MM:SS.mmm 字符串: "00:01.9" / "00:00:01.900" → 解析
          - 纯数字字符串:  "1.9" / "1900"             → 区分秒/毫秒
          - None / 非法:                                   → 0.0
        """
        if val is None:
            return 0.0
        if isinstance(val, (int, float)):
            v = float(val)
            # 过大的数字很可能是毫秒 (15000ms vs 15s)
            if v > 1000.0:
                v = v / 1000.0
            return max(0.0, v)
        s = str(val).strip()
        if not s:
            return 0.0
        # HH:MM:SS.mmm 或 MM:SS.mmm
        m = re.match(
            r"^(?:(\d{1,2}):)?(\d{1,2}):(\d{1,2})(?:[.,](\d{1,9}))?$", s
        )
        if m:
            hours = int(m.group(1) or 0)
            minutes = int(m.group(2))
            seconds = int(m.group(3))
            frac = m.group(4) or "0"
            frac = float("0." + frac)
            return hours * 3600 + minutes * 60 + seconds + frac
        # 纯数字
        try:
            v = float(s)
            if v > 1000.0:
                v = v / 1000.0
            return max(0.0, v)
        except ValueError:
            return 0.0

    def _normalize_item(self, raw: Dict[str, Any]) -> Dict[str, Any]:
        """把一条字幕 dict 规范化成 write_srt_file 能吃的格式

        目标:
          {'start_time': float, 'end_time': float,
           'source_text': str, 'target_text': str}

        容错: Gemini 可能输出 start/end (字符串)、text (唯一文本)、
              任意 key 大小写、缺失 source/target 等
        """
        # 1. 找 start / end
        start = 0.0
        end = 0.0
        for k in self._TIME_KEYS:
            if k in raw:
                start = self._parse_time(raw[k])
                break
        for k in self._END_KEYS:
            if k in raw:
                end = self._parse_time(raw[k])
                break

        # 2. 找 source_text (原文)
        source_text = ""
        for k in self._SOURCE_KEYS:
            v = raw.get(k)
            if v:
                source_text = str(v).strip()
                break

        # 3. 找 target_text (译文)
        target_text = ""
        for k in self._TARGET_KEYS:
            v = raw.get(k)
            if v:
                target_text = str(v).strip()
                break

        # 4. 如果只有 source 没有 target, 或只有 target 没有 source,
        #    尝试找通用 text/content 字段
        raw_keys = list(raw.keys())
        if not source_text or not target_text:
            for k in self._TEXT_KEYS:
                v = raw.get(k)
                if v:
                    txt = str(v).strip()
                    # 如果已有 source 但没有 target → text 很可能是译文
                    if source_text and not target_text:
                        target_text = txt
                        logger.warning(
                            f"[Gemini] ⚠️ 缺少 target_text，用 text 字段兜底. "
                            f"raw keys={raw_keys}"
                        )
                        break
                    # 如果已有 target 但没有 source → text 很可能是原文
                    elif target_text and not source_text:
                        source_text = txt
                        logger.warning(
                            f"[Gemini] ⚠️ 缺少 source_text，用 text 字段兜底. "
                            f"raw keys={raw_keys}"
                        )
                        break
                    # 都没有 → ⚠️ 只有一个 text 字段
                    # 把同一个值同时填给 source 和 target，保证 SRT 两行都有东西
                    # （具体哪个是原文哪个是译文已经不可知，但至少不丢信息）
                    elif not source_text and not target_text:
                        source_text = txt
                        target_text = txt
                        logger.warning(
                            f"[Gemini] ⚠️ JSON 只有一个 text 字段（缺少 source_text/target_text），"
                            f"已复制为双语两行. raw keys={raw_keys}, "
                            f"text片段={txt[:80]!r}"
                        )
                        break

        # 5. 兜底：source_text 和 target_text 完全相同 → 用同一值补空
        if source_text and not target_text:
            target_text = source_text
            logger.warning(
                f"[Gemini] ⚠️ 最终兜底补 target_text（用 source_text 复制）. raw keys={raw_keys}"
            )
        elif target_text and not source_text:
            source_text = target_text
            logger.warning(
                f"[Gemini] ⚠️ 最终兜底补 source_text（用 target_text 复制）. raw keys={raw_keys}"
            )

        return {
            "start_time": start,
            "end_time": end,
            "source_text": source_text,
            "target_text": target_text,
        }

    def _normalize_items(self, raw_items: List[Dict]) -> List[Dict]:
        """批量规范化 + 日志汇总"""
        normalized = []
        for raw in raw_items:
            if not isinstance(raw, dict):
                continue
            norm = self._normalize_item(raw)
            # 跳过完全空的条目
            if not norm["source_text"] and not norm["target_text"]:
                continue
            normalized.append(norm)

        if raw_items and normalized:
            first_raw = raw_items[0]
            first_norm = normalized[0]
            logger.info(
                f"[Gemini] JSON 字段规范化: {len(raw_items)} → {len(normalized)} 条\n"
                f"  raw keys: {list(first_raw.keys())}\n"
                f"  norm: start={first_norm['start_time']}, end={first_norm['end_time']}, "
                f"source={first_norm['source_text'][:30]!r}, "
                f"target={first_norm['target_text'][:30]!r}"
            )
        elif raw_items and not normalized:
            logger.warning(
                f"[Gemini] JSON 解析到 {len(raw_items)} 条但全部规范化后丢弃 "
                f"(可能全部为空文本). 第一条: {raw_items[0]}"
            )
        return normalized

    # ----------------------------------------------------------------
    # 以下 4 个是原来的解析方法 (全实例方法, 互相 self. 调用)
    # ----------------------------------------------------------------
    def _safe_json_list(self, text: str) -> Optional[List[Dict[str, Any]]]:
        """从 Gemini 文本中尽力解析 JSON 对象数组, 失败返回 None"""
        if not text:
            return None
        s = text.strip()
        s = re.sub(r"^```(?:json)?\s*", "", s, flags=re.I)
        s = re.sub(r"\s*```$", "", s)
        arr = None
        try:
            arr = json.loads(s)
        except Exception:
            m = re.search(r"\[.*\]", s, re.S)
            if not m:
                return None
            try:
                arr = json.loads(m.group(0))
            except Exception:
                return None
        if isinstance(arr, list):
            return arr
        return None

    def _parse_response(self, response) -> List[Dict]:
        # 尝试多种方式提取文本（Gemini SDK 多模态返回结构不稳定）
        raw_text = ""

        try:
            raw_text = response.text or ""
        except Exception:
            raw_text = ""

        if not raw_text:
            try:
                parts = getattr(response, "parts", None) or []
                for part in parts:
                    txt = getattr(part, "text", None)
                    if txt:
                        raw_text += txt
            except Exception:
                pass

        if not raw_text:
            try:
                candidates = getattr(response, "candidates", None) or []
                for cand in candidates:
                    content = getattr(cand, "content", None)
                    if content:
                        for part in getattr(content, "parts", []) or []:
                            txt = getattr(part, "text", None)
                            if txt:
                                raw_text += txt
            except Exception:
                pass

        if not raw_text.strip():
            raw_text = str(response)

        logger.info(
            f"[Gemini] _parse_response 获取文本: {len(raw_text)} 字符, "
            f"前200: {repr(raw_text[:200])}"
        )

        if not raw_text.strip():
            logger.warning("[Gemini] 响应 text 为空（所有提取方式均失败）")
            return []

        # 1️⃣ 先尝试 JSON 解析
        raw_items: Optional[List[Dict]] = None
        raw_items = self._try_json_parse(raw_text)
        if raw_items is None:
            raw_items = self._extract_json_array(raw_text)

        if raw_items is not None:
            return self._normalize_items(raw_items)

        # 2️⃣ JSON 彻底不行 → 回退到纯文本行解析 (已是规范字段)
        items = self._fallback_line_parse(raw_text)
        if items:
            return items

        logger.error(f"[Gemini] 无法解析响应:\n{raw_text[:500]}")
        return []

    def _try_json_parse(self, text: str) -> Optional[List[Dict]]:
        text = text.strip()
        if text.startswith("```"):
            text = re.sub(r"^```[\w]*\s*", "", text)
            text = re.sub(r"\s*```$", "", text)
        try:
            data = json.loads(text)
            if isinstance(data, list) and data and isinstance(data[0], dict):
                return data
        except json.JSONDecodeError as e:
            pos = e.pos
            nearby_start = max(0, pos - 30)
            nearby_end = min(len(text), pos + 30)
            nearby = text[nearby_start:nearby_end].replace("\n", "\\n")
            marker = " " * (pos - nearby_start) + "^"
            logger.error(
                f"[Gemini] JSON 解析失败: {e.msg} (line {e.lineno}, col {e.colno}, pos {pos})\n"
                f"  附近内容: ...{nearby}...\n"
                f"  位置标记:   {marker}"
            )
            fixed = self._fix_common_json_issues(text)
            if fixed != text:
                try:
                    data = json.loads(fixed)
                    if isinstance(data, list) and data and isinstance(data[0], dict):
                        logger.info("[Gemini] 修复 trailing comma 后 JSON 解析成功")
                        return data
                except json.JSONDecodeError:
                    pass
        return None

    def _extract_json_array(self, text: str) -> Optional[List[Dict]]:
        start = text.find("[")
        if start < 0:
            return None
        depth = 0
        end = -1
        for i in range(start, len(text)):
            c = text[i]
            if c == "[":
                depth += 1
            elif c == "]":
                depth -= 1
                if depth == 0:
                    end = i + 1
                    break
        if end < 0:
            return None
        try:
            data = json.loads(text[start:end])
            if isinstance(data, list) and data:
                return data
        except json.JSONDecodeError:
            pass
        fixed = self._fix_common_json_issues(text[start:end])
        try:
            data = json.loads(fixed)
            if isinstance(data, list) and data:
                return data
        except json.JSONDecodeError:
            pass
        return None

    def _fix_common_json_issues(self, text: str) -> str:
        """修复 LLM 输出 JSON 的常见语法问题（非字符串内的）：
        - trailing comma  (,}  ,])
        """
        result = []
        i = 0
        n = len(text)
        in_string = False
        escape_next = False
        while i < n:
            c = text[i]
            if escape_next:
                result.append(c)
                escape_next = False
                i += 1
                continue
            if c == "\\":
                result.append(c)
                escape_next = True
                i += 1
                continue
            if c == '"':
                in_string = not in_string
                result.append(c)
                i += 1
                continue
            if not in_string and c == ",":
                j = i + 1
                while j < n and text[j] in " \t\n\r":
                    j += 1
                if j < n and text[j] in "}]":
                    i = j
                    continue
                result.append(c)
                i += 1
                continue
            result.append(c)
            i += 1
        return "".join(result)

    def _fallback_line_parse(self, text: str) -> List[Dict]:
        items: List[Dict] = []
        for line in text.splitlines():
            line = line.strip()
            if not line:
                continue
            m = re.match(
                r"(\d+\.?\d*)\s*[-~]\s*(\d+\.?\d*)\s*\|\s*(.+?)\s*\|\s*(.+)$",
                line,
            )
            if m:
                items.append({
                    "start_time": float(m.group(1)),
                    "end_time": float(m.group(2)),
                    "source_text": m.group(3).strip(),
                    "target_text": m.group(4).strip(),
                })
        return items
