"""
字幕文件解析工具（SRT / VTT 通用）

功能特性：
    1. 自动识别文件格式（扩展名 + 文件头）
    2. 正确解析时间戳
    3. 支持双语字幕（自动识别原文/译文）
    4. 字段名统一归一化
"""

import os
import re
from typing import List, Dict, Any, Optional


_TS_RE = re.compile(
    r"(\d{1,2}):(\d{2}):(\d{2})[,.](\d{1,3})\s*-->\s*(\d{1,2}):(\d{2}):(\d{2})[,.](\d{1,3})"
)
_TS_RE_SHORT = re.compile(
    r"(\d{1,2}):(\d{2})[,.](\d{1,3})\s*-->\s*(\d{1,2}):(\d{2})[,.](\d{1,3})"
)


def _ts_to_seconds(h: str, m: str, s: str, ms: str) -> float:
    ms = ms.ljust(3, "0")[:3]
    return int(h) * 3600 + int(m) * 60 + int(s) + int(ms) / 1000.0


def _parse_timestamps(ts_line: str) -> Optional[tuple]:
    """从时间戳行提取 (start_seconds, end_seconds)。支持完整和缩写格式。"""
    ts_line = ts_line.strip()
    m = _TS_RE.match(ts_line)
    if m:
        g = m.groups()
        return (_ts_to_seconds(g[0], g[1], g[2], g[3]),
                _ts_to_seconds(g[4], g[5], g[6], g[7]))

    m = _TS_RE_SHORT.match(ts_line)
    if m:
        g = m.groups()
        start = int(g[0]) * 60 + int(g[1]) + int(g[2].ljust(3, "0")[:3]) / 1000.0
        end = int(g[3]) * 60 + int(g[4]) + int(g[5].ljust(3, "0")[:3]) / 1000.0
        return (start, end)

    return None


def _classify_text(text_lines: List[str]) -> tuple:
    """把一组文本行分成 (原文, 译文)。"""
    original_text = ""
    translated_text = ""
    for line in text_lines:
        line = line.strip()
        if not line:
            continue
        # 清理 HTML tag（VTT 里经常有 <c>, <i> 等）
        line_clean = re.sub(r"<[^>]+>", "", line).strip()
        if not line_clean:
            continue
        if _is_latin_text(line_clean):
            if not original_text:
                original_text = line_clean
        else:
            if not translated_text:
                translated_text = line_clean

    if not original_text and translated_text:
        original_text = translated_text
        translated_text = ""

    return original_text, translated_text


def parse_subtitle_file(path: str) -> List[Dict[str, Any]]:
    """通用入口：根据扩展名/文件头自动选择解析器。"""
    ext = os.path.splitext(path)[1].lower()
    if ext in (".vtt", ".webvtt"):
        return _parse_vtt(path)
    if ext in (".srt", ".sub"):
        return parse_srt_file(path)

    # 扩展名未知：读文件头判断
    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            head = f.read(200).lstrip("\ufeff")
        if head.startswith("WEBVTT"):
            return _parse_vtt(path)
    except Exception:
        pass

    # 兜底：先按 SRT 试，再按 VTT 试
    result = parse_srt_file(path)
    if not result:
        result = _parse_vtt(path)
    return result


def parse_srt_file(srt_path: str) -> List[Dict[str, Any]]:
    """解析 SRT 文件。"""
    subtitles: List[Dict[str, Any]] = []

    try:
        with open(srt_path, "r", encoding="utf-8", errors="ignore") as f:
            content = f.read()
    except Exception:
        return subtitles

    content = content.replace("\r\n", "\n").replace("\r", "\n").lstrip("\ufeff").strip()
    if not content:
        return subtitles

    for block in re.split(r"\n\s*\n", content):
        lines = [ln.rstrip() for ln in block.strip().split("\n") if ln.strip()]
        if len(lines) < 2:
            continue

        idx = 0
        if lines[0].isdigit():
            idx = 1

        if idx >= len(lines):
            continue

        ts_pair = _parse_timestamps(lines[idx].strip())
        if ts_pair is None:
            continue
        start, end = ts_pair

        original_text, translated_text = _classify_text(lines[idx + 1:])
        if original_text or translated_text:
            subtitles.append({
                "start_time": round(start, 3),
                "end_time": round(end, 3),
                "text": original_text,
                "translated_text": translated_text,
            })

    return subtitles


def _parse_vtt(vtt_path: str) -> List[Dict[str, Any]]:
    """解析 WebVTT 文件。"""
    subtitles: List[Dict[str, Any]] = []

    try:
        with open(vtt_path, "r", encoding="utf-8", errors="ignore") as f:
            content = f.read()
    except Exception:
        return subtitles

    content = content.replace("\r\n", "\n").replace("\r", "\n").lstrip("\ufeff")

    # 去掉 WEBVTT 头部到第一个空行
    vtt_re = re.compile(r"WEBVTT[^\n]*\n(?:NOTE[^\n]*\n)?", re.IGNORECASE)
    content = vtt_re.sub("", content, count=1).strip()
    if not content:
        return subtitles

    for block in re.split(r"\n\s*\n", content):
        lines = [ln.rstrip() for ln in block.strip().split("\n") if ln.strip()]
        if len(lines) < 1:
            continue

        idx = 0
        # Cue identifier（非时间戳行且不以数字开头）
        if not _TS_RE.match(lines[0]) and not _TS_RE_SHORT.match(lines[0]):
            idx = 1

        if idx >= len(lines):
            continue

        ts_pair = _parse_timestamps(lines[idx].strip())
        if ts_pair is None:
            continue
        start, end = ts_pair

        original_text, translated_text = _classify_text(lines[idx + 1:])
        if original_text or translated_text:
            subtitles.append({
                "start_time": round(start, 3),
                "end_time": round(end, 3),
                "text": original_text,
                "translated_text": translated_text,
            })

    return subtitles


def normalize_subtitle_items(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """把各种来源的字幕 dict 归一化为统一字段名。

    统一格式:
        start_time (float, 秒)
        end_time (float, 秒)
        text (str, 原文)
        translated_text (str, 译文)

    兼容输入格式:
        - Gemini: start_time, end_time, source_text, target_text
        - page_recognize 本地 ASR: start_time, end_time, source_text, target_text
        - SRT 文件解析: start_time, end_time, text, translated_text
    """
    out: List[Dict[str, Any]] = []
    for it in items:
        start = float(it.get("start_time", it.get("start", 0.0)) or 0.0)
        end = float(it.get("end_time", it.get("end", 0.0)) or 0.0)
        text = it.get("text") or it.get("source_text") or ""
        translated = it.get("translated_text") or it.get("target_text") or ""

        out.append({
            "start_time": start,
            "end_time": end,
            "text": text.strip() if isinstance(text, str) else str(text),
            "translated_text": translated.strip() if isinstance(translated, str) else str(translated),
        })
    return out


def _fmt_time(seconds: float) -> str:
    t = max(0.0, float(seconds))
    h = int(t // 3600)
    m = int((t % 3600) // 60)
    s = int(t % 60)
    ms = int(round((t - int(t)) * 1000))
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def write_srt_file(
    subtitles: List[Dict[str, Any]],
    srt_path: str,
    bilingual: bool = True,
) -> None:
    """将字幕列表写入 SRT 文件（正确使用时间戳）。"""
    with open(srt_path, "w", encoding="utf-8") as f:
        seq = 0
        for sub in subtitles:
            text = sub.get("text") or sub.get("source_text") or ""
            translated = sub.get("translated_text") or sub.get("target_text") or ""
            if not text and not translated:
                continue

            seq += 1
            start = _fmt_time(sub.get("start_time", 0))
            end = _fmt_time(sub.get("end_time", 0))

            f.write(f"{seq}\n")
            f.write(f"{start} --> {end}\n")
            # ★ 双语输出：永远先写原文行，后写译文行
            # 即使 source_text 和 target_text 相同（极端 fallback），也强制写两行
            # 这样 SRT 格式始终正确，播放端能正确渲染双语
            if text:
                f.write(f"{text}\n")
            if bilingual and translated:
                f.write(f"{translated}\n")
            f.write("\n")


def merge_srt_files(
    original_path: str,
    translated_path: str,
    output_path: str,
) -> bool:
    """合并原文+译文 SRT 为双语 SRT。"""
    original_subs = parse_srt_file(original_path)
    translated_subs = parse_srt_file(translated_path)

    merged: List[Dict[str, Any]] = []
    for i, orig in enumerate(original_subs):
        merged.append({
            "start_time": orig.get("start_time", 0),
            "end_time": orig.get("end_time", 0),
            "text": orig.get("text", ""),
            "translated_text": (
                translated_subs[i].get("text", "")
                if i < len(translated_subs)
                else ""
            ),
        })

    write_srt_file(merged, output_path)
    return True


def _is_latin_text(text: str) -> bool:
    """判断文本是否主要由拉丁字符构成（含带重音的欧洲语言字符）。

    使用 Unicode 范围而非 re.ASCII，因为德语 ü/ö/ä、法语 é/ê/ç、西班牙语 ñ 等
    带重音字符在 ASCII 模式下不被 \w 匹配，会被误判为"非拉丁"。

    Latin 相关 Unicode 块:
        Basic Latin         U+0020-U+007E  (英文 + 标点)
        Latin-1 Supplement  U+00A0-U+00FF  (é, ñ, ü 等带重音)
        Latin Extended-A    U+0100-U+017F  (ā, ę, ń 等中欧)
        Latin Extended-B    U+0180-U+024F  (特殊拉丁)

    中文字符范围: U+4E00-U+9FFF + U+3400-U+4DBF 等
    日文字符: U+3040-U+30FF (假名) + U+4E00-U+9FFF (汉字)
    韩文字符: U+AC00-U+D7AF + U+1100-U+11FF
    """
    latin_re = re.compile(
        r"[\u0020-\u007E\u00A0-\u024F\s\,\.\!\?\:\;\'\"\-\\/\(\)\[\]\{\}\<\>"
        r"\&\@\#\$\%\^\*\~\+\=\|\`\´\u2000-\u206F]"  # 通用标点
    )
    non_latin_re = re.compile(
        r"[\u3400-\u4DBF\u4E00-\u9FFF\uAC00-\uD7AF"  # CJK + 韩文
        r"\u3040-\u309F\u30A0-\u30FF]"  # 日文假名
    )
    # 先用 Latin 正则匹配整串
    if latin_re.match(text):
        return True
    # 再用非 Latin 正则检查是否含中日韩字符
    if non_latin_re.search(text):
        return False
    # 兜底：检查是否有 ASCII 字母
    return bool(re.match(r"^[A-Za-z]", text))
