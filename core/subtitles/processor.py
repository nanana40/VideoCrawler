from __future__ import annotations
"""core/subtitles/processor.py — SubtitleProcessor"""

"""
字幕处理模块

实现视频字幕的自动提取、翻译和嵌入功能。

功能特性：
    1. 字幕文件提取（外挂字幕 + ffmpeg 内嵌字幕）
    2. 字幕翻译（API + 本地）
    3. 字幕嵌入（ffmpeg）
    4. 自带字幕检测
    5. 双语/纯汉语字幕处理
"""

import os
import re
import subprocess
import json
from typing import Optional, Dict, Any, List, Tuple

from utils.enums import LanguageType, VideoCategory, TaskStatus
from utils.logger import get_translate_logger
from utils.path_helper import get_ffmpeg_path, get_tmp_dir, get_finished_sub_dir, get_asr_model_dir
from utils.file_sort import get_file_sorter
from utils.resource_locks import FFMPEG_LOCK
from core.subtitles.asr import SpeechRecognizer
from core.subtitles.models import SubtitleSegment, SubtitleSentence, SubtitleResult
from core.subtitles.sentence_merger import SentenceMerger
from core.subtitles.writer import SRTWriter
from core.subtitles.quality_gate import SubtitleQualityGate
from core.subtitles.embedder import VideoSubtitleEmbedder
from core.subtitles.translator import SubtitleTranslator


logger = get_translate_logger()


class SubtitleProcessor:
    """
    字幕处理器
    
    整合语音识别、翻译、字幕嵌入功能。
    """
    
    def __init__(self) -> None:
        """初始化字幕处理器"""
        self._recognizer = SpeechRecognizer()
        self._translator = SubtitleTranslator()
        self._embedder = VideoSubtitleEmbedder()
        self._quality_gate = SubtitleQualityGate()
        self._file_sorter = get_file_sorter()
        logger.info("字幕处理器初始化完成")

    # ---------------------------------------------------------------
    # Gemini 全托管路径
    # ---------------------------------------------------------------

    @staticmethod
    def _gemini_items_to_sentences(
        items: List[Dict[str, Any]]
    ) -> List[SubtitleSentence]:
        """把 Gemini 返回的 dict 列表转成 SubtitleSentence 列表

        Gemini 输出已经是句子级别（source_text + target_text + 时间戳），
        每个 item 直接映射成一个 SubtitleSentence + 一个 SubtitleSegment。
        """
        sentences: List[SubtitleSentence] = []
        for item in items:
            try:
                start = float(item.get("start_time", 0))
                end = float(item.get("end_time", 0))
                src = str(item.get("source_text", "")).strip()
                tgt = str(item.get("target_text", "")).strip()
                if not src and not tgt:
                    continue
                seg = SubtitleSegment(
                    start_time=start, end_time=end, text=src
                )
                sentences.append(SubtitleSentence(
                    start_time=start,
                    end_time=end,
                    text=src,
                    translated_text=tgt or None,
                    source_segments=[seg],
                ))
            except (ValueError, TypeError) as e:
                logger.warning(f"[Gemini] 跳过无效 item: {item} ({e})")
        return sentences

    def _try_gemini_pipeline(
        self,
        gemini_transcriber,
        video_id: str,
        video_path: str,
        source_lang: str,
        target_lang: str,
        language,
        category,
        has_original: bool,
        channel: Optional[str] = None,
        local_asr_segments: Optional[List[SubtitleSegment]] = None,
    ) -> Optional[SubtitleResult]:
        """尝试 Gemini 全托管管线。失败返回 None（让调用方回退本地管线）"""
        asr_for_gemini = None
        if local_asr_segments:
            asr_for_gemini = self._subtitlesegments_to_asr_dict(local_asr_segments)
            logger.info(
                f"[Gemini] 将 {len(local_asr_segments)} 条本地 ASR 作为参考输入"
            )

        try:
            gemini_items = gemini_transcriber.transcribe_and_translate(
                video_path=video_path,
                source_lang=source_lang,
                asr_segments=asr_for_gemini,
            )
        except Exception as e:
            logger.error(f"[Gemini] transcribe_and_translate 失败: {e}")
            return None

        if not gemini_items:
            logger.warning("[Gemini] 返回空列表")
            return None

        sentences = self._gemini_items_to_sentences(gemini_items)
        if not sentences:
            logger.warning("[Gemini] 转换后 sentences 为空")
            return None

        logger.info(
            f"[Gemini] 转换完成: {len(sentences)} 个句子（已带翻译）"
        )

        # Gemini 已经返回分句后的带翻译句子，跳过步骤1-2.5（段落分割、翻译引擎、LLM对齐）
        # 但仍然保留后处理链：
        #   步骤3(切分兜底) + 步骤4(硬限≤18字) + 步骤5(合并重复) + 关卡校验 + 写SRT + 烧录

        merger = SentenceMerger()

        # 步骤4: 拆分过长的中文句子（硬限兜底，防止 Gemini 返回超长句）
        sentences = merger.split_long_sentences(sentences)
        logger.info(
            f"[Gemini] 步骤4 超长句拆分: {len(sentences)} 句"
        )

        # 步骤5: 合并相邻重复原文
        sentences = merger.merge_duplicate_originals(sentences)

        # 关卡校验: 全部跳过（信任上游 Gemini+ASR 合并产出）
        sentences = self._quality_gate.run(
            sentences,
            source_lang=source_lang,
            target_lang=target_lang,
            enabled=False,
        )

        if not sentences:
            logger.warning("[Gemini] sentences 为空，放弃写 SRT")
            return None

        # 写 SRT
        subtitle_dir = self._file_sorter.get_subtitle_dir(
            language, category, video_id, channel
        )
        subtitle_path = os.path.join(subtitle_dir, f"{video_id}_{target_lang}.srt")
        SRTWriter.write_sentences(sentences, subtitle_path, bilingual=True)
        logger.info(
            f"[Gemini] SRT 写入完成: {len(sentences)} 句 → {subtitle_path}"
        )

        # 烧录
        try:
            output_path = self._embedder.embed_subtitle(
                video_path, subtitle_path, has_original_subtitle=has_original
            )
        except Exception as e:
            logger.error(f"[Gemini] 烧录失败: {e}")
            # SRT 已经写好了，烧录失败不算全败
            return SubtitleResult(
                video_id=video_id,
                video_path=video_path,
                success=False,
                subtitle_path=subtitle_path,
                error_message=f"烧录失败: {e}",
                has_original_subtitle=has_original,
            )

        logger.info(f"[Gemini] 全托管完成 ✅: {video_id}")

        # ---- 第二步：校对（烧录后二次审核） ----
        if self._is_proofread_enabled():
            try:
                output_path = self._run_gemini_proofread(
                    gemini_transcriber, video_id,
                    video_path, output_path, sentences,
                    subtitle_path, merger,
                    source_lang, target_lang, has_original,
                    asr_segments=asr_for_gemini,
                )
                if output_path:
                    return SubtitleResult(
                        video_id=video_id,
                        video_path=video_path,
                        success=True,
                        subtitle_path=subtitle_path,
                        embedded_video_path=output_path,
                        has_original_subtitle=has_original,
                    )
            except Exception as e:
                logger.warning(f"[Gemini] 校对失败，沿用初版结果: {e}")
                # 校对失败不算全败，返回初版结果

        return SubtitleResult(
            video_id=video_id,
            video_path=video_path,
            success=True,
            subtitle_path=subtitle_path,
            embedded_video_path=output_path,
            has_original_subtitle=has_original,
        )

    def _run_gemini_proofread(
        self,
        gemini_transcriber,
        video_id: str,
        raw_video_path: str,
        embedded_video_path: str,
        sentences: List["SubtitleSentence"],
        subtitle_path: str,
        merger: "SentenceMerger",
        source_lang: str,
        target_lang: str,
        has_original: bool,
        asr_segments: Optional[List[Dict[str, Any]]] = None,
    ) -> Optional[str]:
        """执行 Gemini 校对流程：烧录视频 → 校对 → 重写 SRT → 重烧录

        Args:
            raw_video_path: 原始未烧录的视频路径（用于二次烧录）
            embedded_video_path: 已烧录字幕的视频路径（送给 Gemini 看）
            asr_segments: 本地 ASR 参考（可选，对照补漏更准）

        Returns:
            新的烧录视频路径，失败则返回 None
        """
        logger.info("=== [Gemini 校对] 开始二次审核 ===")

        existing_items = self._sentences_to_gemini_items(sentences)
        logger.info(f"[Gemini 校对] 输入: {len(existing_items)} 条字幕")

        try:
            corrected_items = gemini_transcriber.proofread_subtitles(
                video_path=embedded_video_path,
                existing_items=existing_items,
                source_lang=source_lang,
                asr_segments=asr_segments,
            )
        except Exception as e:
            logger.warning(f"[Gemini 校对] API 失败: {e}")
            return None

        if not corrected_items:
            logger.warning("[Gemini 校对] 返回空列表 → 放弃校对")
            return None

        new_sentences = self._gemini_items_to_sentences(corrected_items)
        if not new_sentences:
            logger.warning("[Gemini 校对] 转换后 sentences 为空 → 放弃校对")
            return None

        logger.info(
            f"[Gemini 校对] 新字幕: {len(new_sentences)} 条 "
            f"(原版 {len(sentences)} 条, "
            f"+{len(new_sentences) - len(sentences)} 差)"
        )

        # 重跑后处理链
        new_sentences = merger.split_long_sentences(new_sentences)
        logger.info(f"[Gemini 校对] 步骤4 超长句拆分: {len(new_sentences)} 句")
        new_sentences = merger.merge_duplicate_originals(new_sentences)

        # 关卡校验: 全部跳过（校对已关，这里仅是防御）
        new_sentences = self._quality_gate.run(
            new_sentences, source_lang=source_lang, target_lang=target_lang,
            enabled=False,
        )
        if not new_sentences:
            logger.warning("[Gemini 校对] 关卡过滤后为空 → 放弃校对")
            return None

        SRTWriter.write_sentences(new_sentences, subtitle_path, bilingual=True)
        logger.info(f"[Gemini 校对] SRT 重写完成: {len(new_sentences)} 句")

        # 用**原始视频** + 更新后的 SRT 重新烧录（覆盖旧烧录视频）
        try:
            new_output_path = self._embedder.embed_subtitle(
                raw_video_path, subtitle_path,
                output_path=embedded_video_path,
                has_original_subtitle=has_original,
            )
        except Exception as e:
            logger.warning(f"[Gemini 校对] 重烧录失败: {e}")
            return None

        logger.info(f"[Gemini 校对] 重烧录完成 ✅: {video_id}")
        return new_output_path

    # ---------------------------------------------------------------
    # Gemini 校对辅助
    # ---------------------------------------------------------------

    @staticmethod
    def _sentences_to_gemini_items(sentences: List["SubtitleSentence"]) -> List[Dict[str, Any]]:
        """把 SubtitleSentence 列表反向转成 gemini_engine 需要的 dict 列表"""
        items: List[Dict[str, Any]] = []
        for s in sentences:
            items.append({
                "start_time": round(s.start_time, 2),
                "end_time": round(s.end_time, 2),
                "source_text": s.text,
                "target_text": s.translated_text or "",
            })
        return items

    @staticmethod
    def _subtitlesegments_to_asr_dict(
        segments: List[SubtitleSegment],
    ) -> List[Dict[str, Any]]:
        """把本地 SubtitleSegment 列表转成 gemini_engine 接受的 ASR 参考 dict 列表"""
        result: List[Dict[str, Any]] = []
        for seg in segments:
            txt = seg.text.strip() if seg.text else ""
            if not txt:
                continue
            result.append({
                "start_time": round(seg.start_time, 2),
                "end_time": round(seg.end_time, 2),
                "text": txt,
            })
        return result

    @staticmethod
    def _is_proofread_enabled() -> bool:
        try:
            from utils.config_loader import load_config
            cfg = load_config()
            return bool(cfg.get("gemini", {}).get("proofread", False))
        except Exception:
            return False

    def process_video(
        self,
        video_id: str,
        video_path: str,
        language: Optional[LanguageType] = None,
        category: Optional[VideoCategory] = None,
        source_lang: str = "auto",
        target_lang: str = "zh-CN",
        channel: Optional[str] = None,
    ) -> SubtitleResult:
        """
        处理视频字幕（纯 ffmpeg 方案，无需 Whisper）
        
        流程：外挂字幕文件 → 内嵌字幕提取 → 翻译 → 嵌入视频
        
        Args:
            video_id: 视频 ID
            video_path: 视频文件路径
            language: 语言类型
            category: 视频分类
            source_lang: 源语言
            target_lang: 目标语言
            channel: 频道名（决定 SRT 归档目录，须与视频归档目录一致）
            
        Returns:
            SubtitleResult 处理结果
        """
        logger.info(f"开始处理视频字幕: {video_id}, language={language.value if language else 'unknown'}, source_lang={source_lang}")
        
        if not video_path or not os.path.exists(video_path):
            logger.error(f"视频文件不存在，跳过字幕处理: {video_path}")
            return SubtitleResult(
                video_id=video_id,
                video_path=video_path,
                success=False,
                error_message=f"视频文件不存在: {video_path}"
            )
        
        try:
            has_original = self._embedder._has_embedded_subtitle(video_path)
            logger.info(f"视频 {video_id} 是否有原字幕: {has_original}")
            
            detected_lang = language.value if language else None
            effective_source_lang = source_lang
            if source_lang == "auto" and detected_lang:
                effective_source_lang = detected_lang

            # ===== Gemini 全托管分支（可选开关） =====
            try:
                from core.gemini_engine import get_gemini_transcriber
                gemini_transcriber = get_gemini_transcriber()
                gemini_available = gemini_transcriber.is_available
            except Exception:
                gemini_available = False

            if gemini_available:
                logger.info(
                    "=== 走 Gemini 全托管路径（先跑本地 ASR 作为参考，"
                    "再交给 Gemini 对照翻译+补漏） ==="
                )
                local_asr_segments: Optional[List[SubtitleSegment]] = None
                try:
                    logger.info("--- 步骤 0: 本地 faster-whisper ASR（作为 Gemini 参考） ---")
                    local_asr_segments = (
                        self._recognizer._generate_subtitles_via_asr(
                            video_path, detected_lang
                        )
                    )
                    if local_asr_segments:
                        coverage = self._recognizer._compute_segments_coverage(
                            local_asr_segments, video_path
                        )
                        logger.info(
                            f"本地 ASR 完成: {len(local_asr_segments)} 段，"
                            f"覆盖率 {coverage:.0%} → 作为 Gemini 参考"
                        )
                    else:
                        logger.warning("本地 ASR 无结果，Gemini 将独立识别")
                except Exception as asr_err:
                    logger.warning(f"本地 ASR 异常（不影响 Gemini）: {asr_err}")
                    local_asr_segments = None

                gemini_ok = self._try_gemini_pipeline(
                    gemini_transcriber, video_id, video_path,
                    effective_source_lang, target_lang,
                    language, category, has_original,
                    channel=channel,
                    local_asr_segments=local_asr_segments,
                )
                if gemini_ok is not None:
                    return gemini_ok
                # Gemini 失败 → 回退到原有本地管线，继续往下走
                logger.warning("Gemini 全托管失败，回退本地管线")
            else:
                logger.info("=== 走本地管线（ASR + 翻译引擎 + 关卡） ===")

            # ===== 原有本地管线 =====

            segments = self._recognizer.recognize(
                video_path,
                language=detected_lang
            )
            
            if not segments:
                logger.warning(f"视频 {video_id} 未识别到字幕内容")
                return SubtitleResult(
                    video_id=video_id,
                    video_path=video_path,
                    success=False,
                    error_message="未识别到字幕内容"
                )
            
            effective_source_lang = source_lang
            if source_lang == "auto" and detected_lang:
                effective_source_lang = detected_lang
                logger.info(f"自动设置源语言为: {effective_source_lang}")

            # 步骤1: 段落分割（优先 LLM 语义分割，失败回退规则引擎）
            # LLM 分割能识别真正的语义边界，避免规则引擎的各种边角问题：
            #   - 源语言被粗暴切断（如 "El se ño" 字母级碎片）
            #   - 时间间隔启发式失效（ASR 在句中频繁断句）
            #   - 大写字母判断对德语/法语等不适用
            merger = SentenceMerger()
            paragraphs = None

            # 2026-08-14: 禁用 LLM 语义段落分割
            # 原因：GLM 429 频繁 + 多次返回空响应 → 平均分 3 段，质量差且浪费配额
            # 直接跳过，用规则引擎分段（SentenceMerger.merge_to_paragraphs）
            # 未来恢复：把下面 try/except 块取消注释即可
            # ---- disabled ----
            # try:
            #     llm_splitter = LLMSentenceSplitter()
            #     if llm_splitter.is_available:
            #         paragraphs = llm_splitter.split_into_paragraphs(
            #             segments, language_code=effective_source_lang
            #         )
            #         if paragraphs is not None:
            #             logger.info(
            #                 f"LLM 段落分割成功: {len(segments)} 片段 → {len(paragraphs)} 段落"
            #             )
            # except Exception as llm_err:
            #     logger.warning(f"LLM 段落分割异常（回退规则引擎）: {llm_err}")
            #     paragraphs = None

            # 规则引擎段落分割（目前唯一使用的分段方式）
            paragraphs = merger.merge_to_paragraphs(segments)
            logger.info(
                f"规则引擎段落分割: {len(segments)} 片段 → {len(paragraphs)} 段落"
            )

            # 步骤1.5: 给段落原文按时间间隔插句末标点（伪标点）
            # ASR 经常输出无标点的 run-on，翻译引擎看到 blob 输出也是 blob
            # 这一步在翻译前插 `.`，让引擎更容易识别句子边界 → 输出带句号中文
            merger.insert_pseudo_punctuation(paragraphs)

            # 步骤2: 整体翻译每个段落（段落级翻译，保证语义完整）
            logger.info(
                f"开始翻译字幕（段落级）: source_lang={effective_source_lang}, "
                f"target_lang={target_lang}, 段落数={len(paragraphs)}"
            )
            paragraphs = self._translator.translate_sentences(
                paragraphs,
                source_lang=effective_source_lang,
                target_lang=target_lang
            )

            # 2026-08-14: 禁用段落级 LLM 对齐校验（verify_paragraphs）
            # 原因：连续 ReadTimeout + GLM 429，浪费配额且无实质收益
            # （规则引擎 + API 翻译质量关卡已足够）
            # ---- disabled ----
            # paragraphs = self._quality_gate.verify_paragraphs(
            #     paragraphs,
            #     source_lang=effective_source_lang,
            #     target_lang=target_lang
            # )

            # 步骤3: 按中文句号切分每个段落的翻译（先翻译后按中文逻辑切分）
            # 这样切分基于中文标点，不会出现源语言层面的词切断
            sentences: List[SubtitleSentence] = []
            for paragraph in paragraphs:
                cn_sentences = merger.split_translation_to_sentences(paragraph)
                sentences.extend(cn_sentences)
            logger.info(
                f"中文切分: {len(paragraphs)} 个段落 → {len(sentences)} 个中文句子"
            )

            # 步骤4: 拆分过长的中文句子（每段≤18字，按中文语义拆分）
            sentences = merger.split_long_sentences(sentences)

            # 步骤5: 合并相邻重复原文的子句（解决"同一句源语言配两行中文"问题）
            sentences = merger.merge_duplicate_originals(sentences)

            # 关卡校验: 全部跳过（信任上游产出）
            sentences = self._quality_gate.run(
                sentences,
                source_lang=effective_source_lang,
                target_lang=target_lang,
                enabled=False,
            )

            # 步骤6: 按拆分后的句子输出 SRT
            subtitle_dir = self._file_sorter.get_subtitle_dir(
                language, category, video_id, channel
            )
            subtitle_path = os.path.join(subtitle_dir, f"{video_id}_{target_lang}.srt")

            SRTWriter.write_sentences(sentences, subtitle_path, bilingual=True)
            
            output_path = self._embedder.embed_subtitle(
                video_path,
                subtitle_path,
                has_original_subtitle=has_original
            )
            
            logger.info(f"视频 {video_id} 字幕处理成功")
            return SubtitleResult(
                video_id=video_id,
                video_path=video_path,
                success=True,
                subtitle_path=subtitle_path,
                embedded_video_path=output_path,
                has_original_subtitle=has_original
            )
            
        except FileNotFoundError as e:
            logger.error(f"视频 {video_id} 文件不存在或已丢失: {e}")
            return SubtitleResult(
                video_id=video_id,
                video_path=video_path,
                success=False,
                error_message=str(e)
            )
        except ValueError as e:
            logger.error(f"视频 {video_id} 文件为空或无效: {e}")
            return SubtitleResult(
                video_id=video_id,
                video_path=video_path,
                success=False,
                error_message=str(e)
            )
        except Exception as e:
            logger.error(f"视频 {video_id} 字幕处理失败: {e}")
            logger.exception(f"详细异常堆栈: {e}")
            
            return SubtitleResult(
                video_id=video_id,
                video_path=video_path,
                success=False,
                error_message=str(e)
            )
    
    def process_batch(
        self,
        videos: List[Dict[str, Any]]
    ) -> List[SubtitleResult]:
        """
        批量处理视频字幕
        
        Args:
            videos: 视频列表
            
        Returns:
            处理结果列表
        """
        results = []
        for video in videos:
            result = self.process_video(
                video_id=video.get("video_id", ""),
                video_path=video.get("video_path", ""),
                language=video.get("language"),
                category=video.get("category"),
                source_lang=video.get("source_lang", "auto"),
                target_lang=video.get("target_lang", "zh-CN"),
                channel=video.get("channel") or None,
            )
            results.append(result)
        return results

def process_video_subtitle(
    video_id: str,
    video_path: str,
    language: Optional[LanguageType] = None,
    category: Optional[VideoCategory] = None,
    source_lang: str = 'auto',
    target_lang: str = 'zh-CN',
    channel: Optional[str] = None,
) -> 'SubtitleResult':
    """模块级便捷入口：创建 SubtitleProcessor 并处理单视频字幕"""
    processor = SubtitleProcessor()
    return processor.process_video(
        video_id=video_id,
        video_path=video_path,
        language=language,
        category=category,
        source_lang=source_lang,
        target_lang=target_lang,
        channel=channel,
    )
