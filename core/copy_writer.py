"""
共享文案生成功能

从字幕素材生成社交媒体文案（小红书/微博/知乎，口语/应试风格）并保存为 .txt，
供：
  - 文案生成页（page_writer）手动调用
  - 全自动流水线（auto_pipeline）复用
两者使用完全一致的语言检测 / 内容类型映射 / 保存规则。
"""

import os
from typing import Any, Dict, List, Optional

from loguru import logger
from core.ai_writer import AIWriter, ContentType
from utils.enums import LanguageType
from utils.language_check import detect_language_rich as detect_language


def _content_type_for(platform: str, style: str) -> ContentType:
    if platform == "xiaohongshu":
        return ContentType.XIAOHONGSHU_ORAL if style == "oral" else ContentType.XIAOHONGSHU_EXAM
    if platform == "weibo":
        return ContentType.WEIBO_ORAL if style == "oral" else ContentType.WEIBO_EXAM
    if platform == "zhihu":
        return ContentType.ZHIHU_ORAL if style == "oral" else ContentType.ZHIHU_EXAM
    return ContentType.XIAOHONGSHU_ORAL


def generate_copy(
    subtitles: List[Dict[str, Any]],
    language: str,
    video_save_dir: Optional[str],
    video_id: str,
    platform: str,
    style: str,
    analyze: bool = True,
) -> str:
    """
    从字幕生成文案并保存。

    Args:
        subtitles: [{"text": 原文, "translated_text": 译文}, ...]
        language: 指定源语言（auto/空则自动检测，需是 enum value）
        video_save_dir: 保存目录（视频所在目录，可为 None 则不落盘）
        video_id: 视频 id，用于命名
        platform: 平台 ('xiaohongshu'|'weibo'|'zhihu')
        style: 'oral' | 'exam'
        analyze: 是否启用深度分析（信息性参数，映射到内容类型）

    Returns:
        生成的内容字符串；失败返回空串
    """
    if not subtitles:
        logger.warning("[copy_writer] 没有可用字幕素材")
        return ""

    ctype = _content_type_for(platform, style)

    # ---- 语言自动识别 ----
    lang_code = (language or "").strip()
    if not lang_code or lang_code == "auto" or not LanguageType.from_code(lang_code):
        sample_parts = []
        for s in subtitles[:80]:
            t = (s.get("text") or "").strip()
            if t:
                sample_parts.append(t)
        sample_text = "\n".join(sample_parts)
        detected = detect_language(title="", subtitle_text=sample_text)
        lang_code = detected.value
        logger.info(f"[copy_writer] 自动识别源语言: {getattr(detected, 'display_name', lang_code)} ({lang_code})")
    else:
        logger.info(f"[copy_writer] 使用指定语言: {lang_code}")

    writer = AIWriter()
    try:
        result = writer.generate_content(
            subtitles=subtitles,
            content_type=ctype,
            language=lang_code,
        )
        if not result:
            logger.warning("[copy_writer] AIWriter 返回空内容")
            return ""
    except Exception as e:
        import traceback
        logger.error(f"[copy_writer] AIWriter 调用失败: {e}\n{traceback.format_exc()}")
        return ""

    # ---- 保存为 .txt ----
    if video_save_dir and os.path.isdir(video_save_dir):
        safe_id = (video_id or "context")[:20]
        fname = f"{safe_id}_{platform}_{style}.txt"
        fpath = os.path.join(video_save_dir, fname)
        try:
            with open(fpath, "w", encoding="utf-8") as f:
                f.write(result)
            logger.success(f"文案已保存: {fpath}")
        except Exception as e:
            logger.warning(f"文案保存失败: {e}")

    return result