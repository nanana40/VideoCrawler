from __future__ import annotations
"""core/subtitles/sentence_merger.py — SentenceMerger"""

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
from dataclasses import dataclass

from utils.enums import LanguageType, VideoCategory, TaskStatus
from utils.logger import get_translate_logger
from utils.path_helper import get_ffmpeg_path, get_tmp_dir, get_finished_sub_dir, get_asr_model_dir
from utils.file_sort import get_file_sorter
from utils.resource_locks import FFMPEG_LOCK
from core.subtitles.models import SubtitleSegment, SubtitleSentence


logger = get_translate_logger()


@dataclass


class SentenceMerger:
    """字幕句子合并器

    将基于时间分段的字幕片段合并为语义完整的句子。

    YouTube/ASR 字幕的分段基于显示时间，常在句子中间切断
    （如 "...une forêt" | "créée artificiellement..."），
    导致逐段翻译时丢失句法结构和上下文。

    合并策略：
        1. 检测片段是否以句末标点结尾（. ! ? 。 ？ ！ …）
        2. 若未结尾，且与下一片段时间相邻（间隔 < max_gap 秒），则合并
        3. 合并后文本用空格连接（保留原语种分词）
        4. 句子时间范围 = 首片段 start ~ 末片段 end
    """

    # 句末标点（多语言，覆盖拉丁/中日韩标点）
    SENTENCE_ENDINGS = frozenset(".!?。？！…\u2026")

    # 片段间最大时间间隔（秒），超过则视为句子边界
    MAX_GAP_SECONDS = 2.0

    # 单个句子最大字符数（超过则强制分割）
    MAX_SENTENCE_CHARS = 100

    # 段落合并参数
    # 每个段落最大字符数（控制在翻译器单次处理范围内）
    PARAGRAPH_MAX_CHARS = 800
    # 段落最大持续时间（秒，超过则切分段落）
    PARAGRAPH_MAX_DURATION = 60.0
    # 段落间最大时间间隔（秒，超过则强制分段落）
    PARAGRAPH_MAX_GAP = 3.0

    def merge_to_paragraphs(
        self,
        segments: List[SubtitleSegment]
    ) -> List[SubtitleSentence]:
        """将字幕片段合并成大段落（用于先翻译后切分的新流程）

        与 merge() 不同，这里合并成更大的段落单元：
            - 每个段落包含多个原始片段
            - 段落边界基于：时间间隔、字符数上限、持续时间上限
            - 不依赖源语言标点或大写字母判断（避免源语言层面切断词）

        段落作为翻译单元，确保翻译器能看到完整的上下文，
        不会出现 "荒原没有" / "并不总是" 这种源语言片段切断导致的翻译截断。

        Args:
            segments: 原始字幕片段列表（按时间排序）

        Returns:
            段落列表，每个段落是一个 SubtitleSentence（text=合并原文，source_segments=原始片段）
        """
        if not segments:
            return []

        paragraphs: List[SubtitleSentence] = []
        current_segments: List[SubtitleSegment] = [segments[0]]

        for i in range(1, len(segments)):
            prev_seg = current_segments[-1]
            curr_seg = segments[i]

            # 计算当前段落的状态
            current_text = " ".join(s.text.strip() for s in current_segments if s.text.strip())
            current_chars = len(current_text)
            current_duration = curr_seg.end_time - current_segments[0].start_time
            gap = curr_seg.start_time - prev_seg.end_time

            # 判断是否应该结束当前段落
            should_end = (
                current_chars >= self.PARAGRAPH_MAX_CHARS       # 字符数超限
                or current_duration >= self.PARAGRAPH_MAX_DURATION  # 持续时间超限
                or gap > self.PARAGRAPH_MAX_GAP                  # 时间间隔过大
            )

            if should_end:
                paragraphs.append(self._build_sentence(current_segments))
                current_segments = [curr_seg]
            else:
                current_segments.append(curr_seg)

        # 收尾
        if current_segments:
            paragraphs.append(self._build_sentence(current_segments))

        logger.info(
            f"段落合并完成: {len(segments)} 个片段 → {len(paragraphs)} 个段落"
            f"（平均每段 {len(segments) / max(len(paragraphs), 1):.1f} 片段）"
        )
        return paragraphs

    def split_translation_to_sentences(
        self,
        paragraph: SubtitleSentence
    ) -> List[SubtitleSentence]:
        """将段落的中文翻译按中文句号切分成完整句子，并分配时间戳和原文

        核心思路（基于 source_segments 时间段分配，避免源语言碎片化）：
            1. 段落已经整体翻译完成（translated_text 是完整中文）
            2. 按中文句末标点（。！？）切分成多个完整中文句子
            3. 按中文字数比例计算每个句子应分到的"目标持续时间"
            4. 贪心地把 source_segments 分配到各中文句子：
               - 每个句子拿到一组完整的 source_segments
               - 句子的时间范围 = 组内 source_segments 的时间范围
               - 句子的原文 = 组内 source_segments 的文本合并
            5. 这样原文基于原始字幕片段，不会被切成单词/字母碎片

        Args:
            paragraph: 已翻译完成的段落（translated_text 已填充）

        Returns:
            按中文句号切分后的句子列表
        """
        translated = paragraph.translated_text or ""
        if not translated:
            return [paragraph]

        # 按中文句末标点切分（。！？；… 以及对应的全角/半角）
        # 保留标点在句子末尾
        import re
        # 先规范化翻译文本：换行符/多余空白替换为单个空格
        # 避免翻译API返回的换行符导致意外切分
        translated = re.sub(r'\s+', ' ', translated).strip()
        # 切分模式：在句末标点后切分
        split_pattern = r'([。！？；…!?;]+)'
        parts = re.split(split_pattern, translated)

        # 重新组合：标点附加到前面的文本
        sentences_text: List[str] = []
        i = 0
        while i < len(parts):
            text = parts[i]
            # 如果下一个是标点，附加到当前文本
            if i + 1 < len(parts) and re.match(split_pattern, parts[i + 1]):
                text = text + parts[i + 1]
                i += 2
            else:
                i += 1
            text = text.strip()
            if text:
                sentences_text.append(text)

        if not sentences_text:
            return [paragraph]

        # 合并过短的片段（<4字的碎片合并到相邻句）
        # 关键：如果前一句已以句末标点（。！？!?）结尾，说明是完整句子，
        # 短碎片应合并到**后一句**（因为后一句可能缺少这个碎片就不完整）
        # 例如："法律...荒野。" + "凉爽的" + "在公社中..." → "凉爽的" 合并到 "在公社中..."
        MIN_SENTENCE_CHARS = 4
        sentence_end_pattern = r'[。！？!?]+$'
        merged: List[str] = []
        for text in sentences_text:
            eff_len = len(text.replace(' ', ''))
            if merged and eff_len < MIN_SENTENCE_CHARS:
                # 检查前一句是否以句末标点结尾
                prev_ends_with_sentence_mark = bool(re.search(sentence_end_pattern, merged[-1]))
                if prev_ends_with_sentence_mark:
                    # 前一句是完整句子，短碎片合并到后一句（如果有）
                    # 先暂存，等下一句出现时加到开头
                    if len(merged) > 0:
                        # 检查是否已有暂存碎片
                        # 直接插入到列表，等下一句时合并
                        merged.append(text)  # 暂时单独存放
                    else:
                        merged.append(text)
                else:
                    # 前一句不是完整句子，合并到前一句
                    merged[-1] = merged[-1] + text
            else:
                # 检查前一个"暂存"的短碎片，合并到当前句开头
                if merged:
                    prev = merged[-1]
                    prev_eff = len(prev.replace(' ', ''))
                    if prev_eff < MIN_SENTENCE_CHARS and re.search(sentence_end_pattern, prev) is None:
                        # 前一个是短碎片且不以句末标点结尾 → 合并到当前句
                        merged.pop()
                        text = prev + text
                merged.append(text)

        # 再次检查：如果最后一个元素是短碎片（不以句末标点结尾），
        # 合并到前一个以句末标点结尾的句子
        if len(merged) >= 2:
            last = merged[-1]
            last_eff = len(last.replace(' ', ''))
            if last_eff < MIN_SENTENCE_CHARS and re.search(sentence_end_pattern, last) is None:
                merged[-2] = merged[-2] + last
                merged.pop()

        sentences_text = merged

        if len(sentences_text) == 1:
            # ===== 降级策略: P0(句号) 切不动 → 试 P1(逗号/顿号/冒号) =====
            cn_text = sentences_text[0]
            cn_text_no_ws = re.sub(r'\s+', '', cn_text)
            # 如果文本本身很短，直接返回
            if len(cn_text_no_ws) <= self.SOFT_MAX_HINT:
                return [paragraph]
            # P1 切: 逗号、顿号、冒号、破折号、空格过多
            p1_parts = re.split(r'([，,、:：\-—])', cn_text)
            p1_recombined = []
            i = 0
            while i < len(p1_parts):
                t = p1_parts[i]
                if i + 1 < len(p1_parts) and re.match(r'[，,、:：\-—]', p1_parts[i + 1]):
                    t = t + p1_parts[i + 1]
                    i += 2
                else:
                    i += 1
                t = t.strip()
                if t:
                    p1_recombined.append(t)
            if len(p1_recombined) > 1:
                sentences_text = p1_recombined
                logger.info(
                    f"[split] P0 无句末标点, P1 逗号切分: 1 → {len(sentences_text)} 句"
                )
            else:
                # ===== P2 硬限强制切: 按 ~15 字硬切 =====
                hard_parts = []
                remaining = cn_text
                while remaining:
                    stripped = remaining.strip()
                    if not stripped:
                        break
                    # 按有效字数（去空格）在 ~15 位置切
                    cut_idx = self._find_hard_cut_index(stripped, self.SOFT_MAX_HINT)
                    hard_parts.append(stripped[:cut_idx])
                    remaining = stripped[cut_idx:]
                if len(hard_parts) > 1:
                    sentences_text = hard_parts
                    logger.info(
                        f"[split] P0/P1 都无标点, P2 硬限切分: 1 → {len(sentences_text)} 句"
                    )
                else:
                    return [paragraph]

        # ===== 基于 source_segments 时间段分配原文和时间戳 =====
        # 策略：按时间均分，而非按中文字数比例。
        # 原因：翻译引擎把一个西语段落翻成中文后，中文句子的长度分布
        #       可能和西语句子的时间分布完全不对应（引擎可能合并/拆分句子）。
        #       按中文字数贪心 → 某个翻译引擎输出的一句超长中文就会吃掉
        #       大量 source_segments，导致相邻短句分到的 segments 极少，
        #       原文与译文完全错配，LLM 关卡1 拿到的"原文→翻译"对噪声巨大。
        #       按时间均分则不受翻译引擎输出长度影响，稳定、可预测。
        source_segments = paragraph.source_segments or []

        if not source_segments:
            return self._split_translation_no_segments(paragraph, sentences_text)

        n = len(sentences_text)
        segment_durations = [
            max(0.001, seg.end_time - seg.start_time) for seg in source_segments
        ]
        total_seg_duration = sum(segment_durations) or 1.0

        # 按时间均分 —— 每个中文句子分到总时长的 1/n
        seg_idx = 0
        cum_duration = 0.0
        result: List[SubtitleSentence] = []

        for i, cn_text in enumerate(sentences_text):
            target_cum = total_seg_duration * (i + 1) / n
            group_segments: List[SubtitleSegment] = []

            while seg_idx < len(source_segments):
                seg = source_segments[seg_idx]
                seg_dur = segment_durations[seg_idx]

                if cum_duration < target_cum or not group_segments:
                    group_segments.append(seg)
                    cum_duration += seg_dur
                    seg_idx += 1
                else:
                    break

                if cum_duration >= target_cum:
                    break

            if group_segments:
                start_time = group_segments[0].start_time
                end_time = group_segments[-1].end_time
                orig_text = ' '.join(
                    s.text.strip() for s in group_segments if s.text.strip()
                )
            else:
                start_time = paragraph.start_time
                end_time = paragraph.end_time
                orig_text = paragraph.text or ""

            result.append(SubtitleSentence(
                start_time=start_time,
                end_time=end_time,
                text=orig_text,
                translated_text=cn_text,
                source_segments=group_segments
            ))

        # 确保所有 source_segments 都被分配（剩余的归到最后一句）
        if seg_idx < len(source_segments) and result:
            last = result[-1]
            remaining = list(source_segments[seg_idx:])
            last.source_segments = (last.source_segments or []) + remaining
            last.end_time = remaining[-1].end_time
            remaining_text = ' '.join(
                s.text.strip() for s in remaining if s.text.strip()
            )
            if last.text:
                last.text = last.text + ' ' + remaining_text
            else:
                last.text = remaining_text

        # 修正最后一段的 end_time，保证与段落一致
        if result:
            result[-1].end_time = paragraph.end_time

        return result

    def _split_translation_no_segments(
        self,
        paragraph: SubtitleSentence,
        sentences_text: List[str]
    ) -> List[SubtitleSentence]:
        """退化路径：没有 source_segments 时按中文字数比例分配时间和原文

        每个子句的原文按时间比例切分（优先在空格处），避免所有子句共享整句原文
        导致显示时相同源语言出现多行。
        时间戳按中文字数比例在段落时间范围内分配。
        """
        total_cn_chars = sum(len(s.replace(' ', '')) for s in sentences_text) or 1
        paragraph_duration = paragraph.end_time - paragraph.start_time
        total_orig_chars = len(paragraph.text or "")
        cum_ratio = 0.0
        orig_consumed = 0
        result: List[SubtitleSentence] = []
        for cn_text in sentences_text:
            ratio = len(cn_text.replace(' ', '')) / total_cn_chars
            sub_duration = paragraph_duration * ratio
            start_time = paragraph.start_time + paragraph_duration * cum_ratio
            end_time = start_time + sub_duration
            cum_ratio += ratio

            # 按比例切分原文（优先在空格处，避免切断单词）
            orig_len = max(1, int(total_orig_chars * ratio))
            if orig_consumed + orig_len > total_orig_chars:
                orig_len = total_orig_chars - orig_consumed
            orig_end = self._adjust_orig_to_word_boundary(
                paragraph.text, orig_consumed, orig_consumed + orig_len
            )
            orig_part = paragraph.text[orig_consumed:orig_end].strip() if paragraph.text else ""
            orig_consumed = orig_end

            result.append(SubtitleSentence(
                start_time=start_time,
                end_time=end_time,
                text=orig_part,
                translated_text=cn_text,
                source_segments=paragraph.source_segments
            ))
        if result:
            result[-1].end_time = paragraph.end_time
            # 原文剩余部分归到最后一句
            if orig_consumed < total_orig_chars and paragraph.text:
                result[-1].text = (
                    result[-1].text + ' ' + paragraph.text[orig_consumed:].strip()
                ).strip()
        return result

    def merge(
        self,
        segments: List[SubtitleSegment]
    ) -> List[SubtitleSentence]:
        """将字幕片段合并为完整句子

        Args:
            segments: 原始字幕片段列表（按时间排序）

        Returns:
            合并后的句子列表，每个句子包含 1~N 个原始片段
        """
        if not segments:
            return []

        sentences: List[SubtitleSentence] = []
        current_segments: List[SubtitleSegment] = [segments[0]]

        for i in range(1, len(segments)):
            prev_seg = current_segments[-1]
            curr_seg = segments[i]

            # 判断是否应该结束当前句子
            should_end = self._should_end_sentence(prev_seg, curr_seg, current_segments)

            if should_end:
                sentences.append(self._build_sentence(current_segments))
                current_segments = [curr_seg]
            else:
                current_segments.append(curr_seg)

        # 收尾：最后一批片段组成一个句子
        if current_segments:
            sentences.append(self._build_sentence(current_segments))

        logger.info(
            f"句子合并完成: {len(segments)} 个片段 → {len(sentences)} 个句子"
            f"（平均每句 {len(segments) / max(len(sentences), 1):.1f} 片段）"
        )
        return sentences

    def _should_end_sentence(
        self,
        prev_seg: SubtitleSegment,
        curr_seg: SubtitleSegment,
        current_segments: List[SubtitleSegment]
    ) -> bool:
        """判断是否应在当前片段后结束句子

        结束条件（任一满足即结束）：
            1. 前一片段以句末标点结尾
            2. 两片段时间间隔超过 MAX_GAP_SECONDS
            3. 当前片段以大写字母开头（新句子标志，仅对拉丁语系）
            4. 当前句子总字符数超过 MAX_SENTENCE_CHARS（强制分割）

        Args:
            prev_seg: 前一片段
            curr_seg: 当前片段
            current_segments: 当前正在构建的句子片段列表

        Returns:
            True 表示应结束当前句子
        """
        # 条件1：前一片段以句末标点结尾
        prev_text = prev_seg.text.rstrip()
        if prev_text and prev_text[-1] in self.SENTENCE_ENDINGS:
            return True

        # 条件2：时间间隔过大
        gap = curr_seg.start_time - prev_seg.end_time
        if gap > self.MAX_GAP_SECONDS:
            return True

        # 条件3：当前片段以大写字母开头（新句子标志）
        curr_text = curr_seg.text.lstrip()
        if curr_text and curr_text[0].isupper():
            # 只有当当前句子已有一定长度时才结束（避免太短的句子）
            current_text = " ".join(s.text for s in current_segments)
            if len(current_text) > 20:
                return True

        # 条件4：当前句子总字符数超过阈值（强制分割）
        current_text = " ".join(s.text for s in current_segments)
        total_chars = len(current_text) + len(curr_seg.text)
        if total_chars > self.MAX_SENTENCE_CHARS:
            return True

        return False

    def _build_sentence(
        self,
        segments: List[SubtitleSegment]
    ) -> SubtitleSentence:
        """由多个片段构建一个完整句子

        Args:
            segments: 构成该句子的片段列表

        Returns:
            合并后的 SubtitleSentence
        """
        text_parts = [seg.text.strip() for seg in segments if seg.text.strip()]
        merged_text = " ".join(text_parts)

        return SubtitleSentence(
            start_time=segments[0].start_time,
            end_time=segments[-1].end_time,
            text=merged_text,
            source_segments=segments
        )

    # 最长字符数（原文，超过则拆分显示）
    MAX_CHARS_PER_DISPLAY = 80
    # 最长持续时间（秒，超过则拆分显示）
    MAX_DURATION_PER_DISPLAY = 10.0
    # 翻译后中文字数上限（超过则强制拆分）
    MAX_CN_CHARS_PER_DISPLAY = 18
    # split_translation_to_sentences 降级硬切的软目标字数
    SOFT_MAX_HINT = 18

    def split_long_sentences(
        self,
        sentences: List[SubtitleSentence]
    ) -> List[SubtitleSentence]:
        """拆分过长的句子为多个显示段（先完整翻译，后按中文语义拆分）

        拆分条件（满足任一）：
            1. 原文长度 > MAX_CHARS_PER_DISPLAY
            2. 持续时间 > MAX_DURATION_PER_DISPLAY
            3. 翻译后中文字数 > MAX_CN_CHARS_PER_DISPLAY（核心条件）

        核心流程：
            - 翻译是完整整句做的（已在外部完成）
            - 翻译完成后，这里按中文语义拆分：P0句末标点 > P1逗号顿号 > P2连接词
            - 使用贪心算法组合语义断点，每段≤18字
            - 原文不再按字符比例切分（避免源语言碎片化）：
              * _split_by_translation_chars 内部已基于 source_segments 分配原文和时间戳
              * _split_by_punctuation 分支按原文长度比例分配时间

        Args:
            sentences: 已翻译完成的句子列表

        Returns:
            拆分后的句子列表（每段中文翻译≤18字，按语义切开）
        """
        result: List[SubtitleSentence] = []

        for sentence in sentences:
            # 检查是否需要拆分
            cn_chars = len(sentence.translated_text) if sentence.translated_text else 0
            should_split = (
                len(sentence.text) > self.MAX_CHARS_PER_DISPLAY
                or (sentence.end_time - sentence.start_time) > self.MAX_DURATION_PER_DISPLAY
                or cn_chars > self.MAX_CN_CHARS_PER_DISPLAY
            )

            if not should_split:
                result.append(sentence)
                continue

            # 按中文语义拆分（翻译已完整生成，此处只做按内容切分）
            # _split_by_translation_chars 内部已基于 source_segments 分配原文和时间戳
            if sentence.translated_text:
                sub_sentences = self._split_by_translation_chars(sentence)
            else:
                sub_sentences = self._split_by_punctuation(sentence)

            if len(sub_sentences) <= 1:
                result.append(sentence)
                continue

            # 为子句分配时间：
            # - 如果子句已经有 source_segments（来自 _split_by_translation_chars），
            #   时间戳已基于 source_segments 分配，不再覆盖
            # - 如果子句没有 source_segments（来自 _split_by_punctuation），
            #   按原文长度比例分配时间
            has_seg = any(sub.source_segments for sub in sub_sentences)
            if not has_seg:
                total_chars = len(sentence.text)
                if total_chars == 0:
                    total_chars = 1
                duration = sentence.end_time - sentence.start_time
                cum_ratio = 0.0
                for sub in sub_sentences:
                    ratio = len(sub.text) / total_chars
                    sub_duration = duration * ratio
                    sub.start_time = sentence.start_time + duration * cum_ratio
                    sub.end_time = sub.start_time + sub_duration
                    cum_ratio += ratio
                if sub_sentences:
                    sub_sentences[-1].end_time = sentence.end_time

            # 合并过短的碎片（<4有效字的片段合并到相邻段）
            # 关键：如果前一段以句末标点（。！？!?）结尾，短碎片合并到**后一段**
            # 避免把后一句开头的词错误地附加到前一句末尾
            MIN_FRAGMENT_CHARS = 4
            import re as _re
            _sent_end = r'[。！？!?]+$'
            merged_subs: List[SubtitleSentence] = []
            for sub in sub_sentences:
                sub_eff = len((sub.translated_text or "").replace(' ', ''))
                if merged_subs and sub_eff < MIN_FRAGMENT_CHARS:
                    prev = merged_subs[-1]
                    prev_text = prev.translated_text or ""
                    prev_ends_with_mark = bool(_re.search(_sent_end, prev_text))
                    if prev_ends_with_mark:
                        # 前一段是完整句子，短碎片暂存（等下一段合并）
                        merged_subs.append(sub)
                    else:
                        # 前一段不是完整句子，合并到前一段
                        prev.translated_text = prev_text + (sub.translated_text or "")
                        prev.text = (prev.text or "") + " " + (sub.text or "")
                        prev.end_time = sub.end_time
                else:
                    # 检查前一个暂存的短碎片，合并到当前段开头
                    if merged_subs:
                        prev = merged_subs[-1]
                        prev_eff = len((prev.translated_text or "").replace(' ', ''))
                        prev_text = prev.translated_text or ""
                        if prev_eff < MIN_FRAGMENT_CHARS and not _re.search(_sent_end, prev_text):
                            merged_subs.pop()
                            sub.translated_text = prev_text + (sub.translated_text or "")
                            sub.text = (prev.text or "") + " " + (sub.text or "")
                            sub.start_time = prev.start_time
                    merged_subs.append(sub)

            result.extend(merged_subs)

        logger.info(
            f"长句拆分: 输入 {len(sentences)} 句 → 输出 {len(result)} 句"
        )
        return result

    def _split_by_translation_chars(
        self,
        sentence: SubtitleSentence
    ) -> List[SubtitleSentence]:
        """按中文语义拆分翻译文本（先完整翻译，后按中文语义断点拆）

        核心策略：语义完整 > 字数限制。
            - 软目标：≤ 15 字有效汉语字（ASCII 空格不计入字数）
            - 硬上限：≤ 18 字有效汉语字
            - 绝对底线：绝不切在词中间，保证每段都是有意义的片段
              （"6月"、"1857年"、"1989 年"、"保时捷火灾，" 保持整体）

        算法流程：
        1. 扫描全文所有语义候选点：
           P0(3分) 句号/问号/感叹号/分号 → 后切
           P1(2分) 逗号/顿号/冒号 → 后切
           P2(1分) 中文连接词（但是、所以...）→ 词前切
        2. 基于「有效汉语字数」(去除 ASCII 空格后的字数) 计算窗口位置：
           这样 "1989 年" 中间的空格不算字数，避免 "是 1989"/"年的..." 这种年份切断
        3. 贪心选点：
           A. 先看 [15, 18] 有效字数区间，刚好有 P0/P1 → 用
           B. 否则在 (5, 15] 选分数最高、最靠右的点
           C. 没找到 → (5, 18] 找 P0/P1（宁超不拆词）
           D. 兜底：友好硬切（虚词后 / 数字→非数字不含年月日 等）
        """
        translated = sentence.translated_text or sentence.text
        SOFT_MAX = self.MAX_CN_CHARS_PER_DISPLAY  # 18
        HARD_MAX = SOFT_MAX + 3                   # 21 硬上限
        MIN_LEN = 5                               # 单段不少于 5 有效字

        if len(translated.replace(' ', '')) <= SOFT_MAX:
            return [sentence]

        candidates = self._collect_semantic_candidates(translated)

        # 预计算：每个原始字符位置对应的「有效字数累计」(ASCII空格跳过计数)
        # pos_effective[i] 表示 translated[0:i] 中的有效字符数（不含空格）
        n = len(translated)
        pos_effective = [0] * (n + 1)
        eff = 0
        for i in range(n):
            if translated[i] != ' ':
                eff += 1
            pos_effective[i + 1] = eff
        total_effective = eff

        def effective_len(slice_start: int, slice_end: int) -> int:
            """计算 translated[slice_start:slice_end] 的有效汉语字数"""
            if slice_end > n:
                slice_end = n
            if slice_start < 0:
                slice_start = 0
            return pos_effective[slice_end] - pos_effective[slice_start]

        def find_pos_by_effective(start_pos: int, target_eff: int) -> int:
            """从 start_pos 往后找，使累计有效字数达到 target_eff 的位置"""
            accum = 0
            for i in range(start_pos, n):
                if translated[i] != ' ':
                    accum += 1
                    if accum >= target_eff:
                        return i + 1  # 切在该字符之后
            return n

        trans_parts: List[str] = []
        start = 0

        while start < n:
            remaining_eff = total_effective - pos_effective[start]
            if remaining_eff <= HARD_MAX:
                part = translated[start:].strip()
                if part:
                    trans_parts.append(part)
                break

            # 基于有效汉语字数计算窗口位置（空格不算字数）
            soft_end_pos = find_pos_by_effective(start, SOFT_MAX)
            hard_end_pos = find_pos_by_effective(start, HARD_MAX)

            cut_pos = -1

            # ============ 阶段A：[SOFT_MAX, HARD_MAX] 有效字数区间刚好有 P0/P1 ============
            stage_a_pos = -1
            for pos, score in candidates:
                if soft_end_pos < pos <= hard_end_pos and score >= 2:
                    if stage_a_pos < 0 or pos < stage_a_pos:
                        stage_a_pos = pos
            if stage_a_pos > start:
                cut_pos = stage_a_pos

            # ============ 阶段B：在 (MIN_LEN, SOFT_MAX] 有效字区间选最佳点 ============
            if cut_pos <= start:
                best_b_pos = -1
                best_b_score = -1
                for pos, score in candidates:
                    part_eff = effective_len(start, pos)
                    if start < pos <= soft_end_pos and MIN_LEN <= part_eff:
                        if score > best_b_score or (score == best_b_score and pos > best_b_pos):
                            best_b_score = score
                            best_b_pos = pos
                if best_b_pos > start:
                    cut_pos = best_b_pos

            # ============ 阶段C：B没找到 → (MIN_LEN, HARD_MAX] 内找 P0/P1 ============
            if cut_pos <= start:
                for pos, score in candidates:
                    part_eff = effective_len(start, pos)
                    if MIN_LEN <= part_eff and pos <= hard_end_pos and score >= 2:
                        if cut_pos < 0 or pos < cut_pos:
                            cut_pos = pos

            # ============ 阶段D：友好硬切 ============
            if cut_pos <= start:
                cut_pos = self._find_friendly_hard_cut(
                    translated, start,
                    min(hard_end_pos, n),
                    MIN_LEN
                )

            if cut_pos > min(hard_end_pos, n):
                cut_pos = min(hard_end_pos, n)
            if cut_pos <= start:
                cut_pos = min(hard_end_pos, n)

            part = translated[start:cut_pos].strip()
            if part:
                trans_parts.append(part)
            start = cut_pos

        if len(trans_parts) <= 1:
            return [sentence]

        # ===== 原文分配：基于 source_segments 时间段，不按字符比例切分原文 =====
        # 核心原则：绝不把源语言切成单词/字母碎片。
        #   - 如果句子有多个 source_segments，按持续时间贪心分配到各翻译片段
        #   - 如果句子只有 0~1 个 source_segments，所有子句共享完整原文
        sub_sentences: List[SubtitleSentence] = []
        source_segments = sentence.source_segments or []

        if len(source_segments) >= len(trans_parts):
            # 有足够的 source_segments，按持续时间贪心分配
            seg_durations = [
                max(0.001, seg.end_time - seg.start_time) for seg in source_segments
            ]
            total_seg_dur = sum(seg_durations) or 1.0
            trans_total_eff = sum(len(p.replace(' ', '')) for p in trans_parts) or 1

            # 每个翻译片段的目标累计持续时间
            target_cum: List[float] = []
            cum_t = 0.0
            for p in trans_parts:
                cum_t += total_seg_dur * (len(p.replace(' ', '')) / trans_total_eff)
                target_cum.append(cum_t)

            sub_sentences = []
            seg_idx = 0
            cum_dur = 0.0
            for i, trans_part in enumerate(trans_parts):
                target = target_cum[i]
                group: List[SubtitleSegment] = []
                while seg_idx < len(source_segments):
                    seg = source_segments[seg_idx]
                    seg_dur = seg_durations[seg_idx]
                    if cum_dur < target or not group:
                        group.append(seg)
                        cum_dur += seg_dur
                        seg_idx += 1
                    else:
                        break
                    if cum_dur >= target:
                        break

                if group:
                    start_time = group[0].start_time
                    end_time = group[-1].end_time
                    orig_text = ' '.join(s.text.strip() for s in group if s.text.strip())
                else:
                    start_time = sentence.start_time
                    end_time = sentence.end_time
                    orig_text = sentence.text or ""
                sub_sentences.append(SubtitleSentence(
                    start_time=start_time,
                    end_time=end_time,
                    text=orig_text,
                    translated_text=trans_part,
                    source_segments=group
                ))

            # 剩余 source_segments 归到最后一句
            if seg_idx < len(source_segments) and sub_sentences:
                last = sub_sentences[-1]
                remaining = list(source_segments[seg_idx:])
                last.source_segments = (last.source_segments or []) + remaining
                last.end_time = remaining[-1].end_time
                rem_text = ' '.join(s.text.strip() for s in remaining if s.text.strip())
                last.text = (last.text + ' ' + rem_text).strip() if last.text else rem_text
        else:
            # source_segments 不足：时间和原文均按翻译字数比例切分
            # 每个子句只带对应时间段内的原文片段（按字符比例切分，优先在空格处）
            trans_total_eff = sum(len(p.replace(' ', '')) for p in trans_parts) or 1
            duration = sentence.end_time - sentence.start_time
            total_orig_chars = len(sentence.text or "")
            cum_ratio = 0.0
            orig_consumed = 0
            for trans_part in trans_parts:
                part_eff = len(trans_part.replace(' ', ''))
                ratio = part_eff / trans_total_eff
                sub_duration = duration * ratio
                start_time = sentence.start_time + duration * cum_ratio
                end_time = start_time + sub_duration
                cum_ratio += ratio

                # 按比例切分原文（优先在空格处，避免切断单词）
                orig_len = max(1, int(total_orig_chars * ratio))
                if orig_consumed + orig_len > total_orig_chars:
                    orig_len = total_orig_chars - orig_consumed
                orig_end = self._adjust_orig_to_word_boundary(
                    sentence.text, orig_consumed, orig_consumed + orig_len
                )
                orig_part = sentence.text[orig_consumed:orig_end].strip() if sentence.text else ""
                orig_consumed = orig_end

                sub_sentences.append(SubtitleSentence(
                    start_time=start_time,
                    end_time=end_time,
                    text=orig_part,
                    translated_text=trans_part,
                    source_segments=sentence.source_segments
                ))
            if sub_sentences:
                sub_sentences[-1].end_time = sentence.end_time
                # 原文剩余部分归到最后一句
                if orig_consumed < total_orig_chars and sentence.text:
                    sub_sentences[-1].text = (
                        sub_sentences[-1].text + ' ' + sentence.text[orig_consumed:].strip()
                    ).strip()

        return sub_sentences

    @classmethod
    def _find_friendly_hard_cut(
        cls, text: str, start: int, window_end: int, min_len: int
    ) -> int:
        """兜底找「尽量友好」的硬切位置（避免切在词中间、切断年份/月份等）

        优先级从高到低：
            1. [min_len, window_end] 范围内，从右向左找 ASCII 空格（"1989 年"）
            2. 找「数字→非数字」的交界，但如果非数字是 年/月/日/号/时/分/秒 等时间量词，
               则跳过（因为 "6月" "1857年" 是完整词，中间不能切）。
               只接受 大数字 后接普通汉字 的情况，如 "造成82|人死亡" 的 2→人 可切；
               但 "6|月" "1857|年" 不可切。
            3. 找常用**语气/时态助词**之后（这些词属于前一词，切在后面合理）：
               「的、了、着、过、中、后、前、上、下、里、外」
               注意：不含「和、与、及、或」等连接词（它们属于后一词，应切在前面）
            4. 找常用**并列/转折连接词**之前（这些词属于后一词，切在前面合理）：
               「和、与、及、或、但、而、则、又、且」
            5. 兜底在 window_end 切
        """
        search_start = start + min_len
        if search_start > window_end:
            search_start = start + 1
        if search_start > window_end or search_start >= len(text):
            return window_end

        TIME_QT = "年月日号时分秒点个万"  # 时间/数量量词，前面接数字时不能切断

        # 1. ASCII 空格（从右向左），但如果空格后是时间量词（年/月/日...）则跳过
        for i in range(min(window_end, len(text)) - 1, search_start - 1, -1):
            if text[i] == ' ':
                # 检查空格后面的字符是不是时间量词
                next_pos = i + 1
                if next_pos < len(text) and text[next_pos] in TIME_QT:
                    continue  # 比如 "6 月" 中间的空格，不能切，跳过
                return i + 1

        # 2. 「数字→非数字」交界，且非数字不是时间/数量量词（从右向左）
        for i in range(min(window_end, len(text)) - 1, search_start - 1, -1):
            if i > 0:
                prev_digit = text[i-1].isdigit()
                curr_digit = text[i].isdigit()
                if prev_digit and not curr_digit:
                    # 数字后接的汉字如果是时间量词，跳过（"1857年"不切，"6月"不切）
                    if text[i] in TIME_QT:
                        continue
                    return i  # 如 "造成82|人死亡" 这种切是合理的

        # 3. 语气/时态助词之后（从右向左）—— 这些词属于前一词，切在后面
        particle_suffixes = "的了着过中后前上下里外"
        for i in range(min(window_end, len(text)) - 1, search_start - 1, -1):
            if text[i] in particle_suffixes:
                return i + 1  # 切在助词之后

        # 4. 并列/转折连接词之前（从右向左）—— 这些词属于后一词，切在前面
        #    如 "荒废和遗弃" → 切在 "和" 之前 → "荒废" + "和遗弃"
        conjunction_prefixes = "和与及或但而则又且"
        for i in range(min(window_end, len(text)) - 1, search_start - 1, -1):
            if text[i] in conjunction_prefixes:
                return i  # 切在连接词之前

        # 5. 兜底：在 window_end 切
        return min(window_end, len(text))

    @staticmethod
    def _adjust_orig_to_word_boundary(
        text: str, start: int, end: int
    ) -> int:
        """调整原文切分位置到最近的单词边界（空格处），保证单词完整

        源语言（法语/德语等）以空格分词，直接按字符数切会在单词中间断开。
        此方法在 end 附近向前/向后找最近的空格，保证切分不破坏单词。

        策略：
            1. 如果 end 刚好在空格处或文本末尾，直接返回
            2. 优先向前找空格（最多找 12 字符），保证前一段单词完整
            3. 向前找不到则向后找空格（最多找 12 字符），保证后一段单词完整
            4. 都找不到（无空格的文本），保持原位置

        Args:
            text: 完整原文
            start: 当前段起始位置
            end: 原始切分位置

        Returns:
            调整后的切分位置（在单词边界处）
        """
        if end >= len(text) or end <= start:
            return end

        # 如果刚好在空格处或文本末尾，直接返回
        if end == len(text) or text[end] == ' ' or text[end - 1] == ' ':
            return end

        # 向前找最近的空格（最多 12 字符，避免段太短）
        search_back = max(start + 1, end - 12)
        for i in range(end - 1, search_back - 1, -1):
            if text[i] == ' ':
                return i + 1  # 切在空格后

        # 向后找最近的空格（最多 12 字符）
        search_fwd = min(len(text), end + 12)
        for i in range(end, search_fwd):
            if text[i] == ' ':
                return i + 1  # 切在空格后

        # 找不到空格，保持原位置
        return end

    # 中文语义连接词：在这些词**之前**可以断句（弱断点，P2 级）
    CN_SEMANTIC_CONNECTORS = [
        # 转折类
        "但是", "可是", "然而", "不过", "却", "反倒", "反而",
        # 因果/结果类
        "所以", "因此", "于是", "因而", "从而", "结果",
        # 原因/条件类
        "因为", "由于", "既然", "如果", "假如", "假设", "要是",
        "虽然", "尽管", "即使", "就算", "哪怕", "除非", "只要",
        "无论", "不管", "只有",
        # 递进/并列类
        "而且", "并且", "同时", "另外", "此外", "还有", "甚至",
        "尤其", "特别", "何况", "况且", "就是",
        # 选择类
        "或者", "还是", "要么",
        # 时序/顺序类
        "然后", "接着", "随后", "首先", "其次", "最后", "接下来",
        "第一", "第二", "第三", "一方面", "另一方面",
        # 举例/解释类
        "比如", "例如", "譬如", "即", "也就是说", "换句话说",
        # 总结类
        "总之", "总而言之", "总的来说", "综上所述", "最终",
    ]

    def _collect_semantic_candidates(self, text: str) -> List[tuple[int, int]]:
        """扫描全文，收集所有语义切分候选点（位置, 分数）

        分数定义（越高越优先）：
            3 = P0：句号、问号、感叹号、分号 → 切在标点**之后**
            2 = P1：逗号、顿号、冒号 → 切在标点**之后**
            1 = P2：中文连接词 → 切在词**之前**

        Args:
            text: 中文翻译文本

        Returns:
            候选切分点列表 [(pos, score), ...]
        """
        candidates: List[tuple[int, int]] = []
        n = len(text)
        if n == 0:
            return candidates

        # P0：强句末标点（。！？；!?.;）→ 切在标点之后
        p0_punctuation = "。！？；!?.;"
        for i in range(n):
            if text[i] in p0_punctuation:
                candidates.append((i + 1, 3))

        # P1：次级停顿标点（，、，,:：）→ 切在标点之后
        p1_punctuation = "，、,:："
        for i in range(n):
            if text[i] in p1_punctuation:
                candidates.append((i + 1, 2))

        # P2：中文语义连接词 → 切在词**之前**
        for conn in self.CN_SEMANTIC_CONNECTORS:
            clen = len(conn)
            idx = 0
            while idx <= n - clen:
                pos = text.find(conn, idx)
                if pos == -1:
                    break
                # 避免和标点位置重复（如连接词前已有逗号）
                candidates.append((pos, 1))
                idx = pos + 1

        return candidates

    def _split_by_punctuation(
        self,
        sentence: SubtitleSentence
    ) -> List[SubtitleSentence]:
        """按标点符号拆分句子

        优先按分号、逗号等次级标点拆分，
        保持语义完整。

        Args:
            sentence: 待拆分的句子

        Returns:
            拆分后的子句列表
        """
        text = sentence.text

        # 拆分优先级：分号 > 逗号
        # 分号：强分隔，表示并列子句
        # 逗号：弱分隔，表示停顿
        separators = [";", ",", "，", "；"]

        # 找到所有可拆分点
        split_points: List[int] = []
        for sep in separators:
            idx = 0
            while idx < len(text):
                pos = text.find(sep, idx)
                if pos == -1:
                    break
                split_points.append(pos)
                idx = pos + 1

        if not split_points:
            return [sentence]

        # 按位置排序并去重
        split_points = sorted(set(split_points))

        # 检查每个片段是否过大
        segments: List[SubtitleSentence] = []
        last_cut = 0

        for pos in split_points:
            # 从上次切割点到当前分隔符位置
            candidate_end = pos + 1  # 包含分隔符
            sub_text = text[last_cut:candidate_end].strip()

            if len(sub_text) >= 20:  # 最小片段长度
                sub = SubtitleSentence(
                    start_time=sentence.start_time,
                    end_time=sentence.end_time,
                    text=sub_text
                )
                segments.append(sub)
                last_cut = candidate_end

        # 添加最后一段
        if last_cut < len(text):
            remaining = text[last_cut:].strip()
            if remaining:
                sub = SubtitleSentence(
                    start_time=sentence.start_time,
                    end_time=sentence.end_time,
                    text=remaining
                )
                segments.append(sub)

        # 如果只拆出一段，说明没有合适的拆分点
        if len(segments) <= 1:
            return [sentence]

        return segments

    def _split_translated_text(
        self,
        full_translation: str,
        sub_sentences: List[SubtitleSentence],
        index: int
    ) -> str:
        """为指定子句分配翻译文本

        简化策略：将完整翻译按子句数量平均分配，
        或根据各子句原文长度按比例分配。

        Args:
            full_translation: 完整翻译文本
            sub_sentences: 所有子句
            index: 当前子句索引

        Returns:
            分配给当前子句的翻译
        """
        total = len(sub_sentences)
        if total == 0 or not full_translation:
            return full_translation

        # 按原文长度比例分配翻译
        text_lengths = [len(s.text) for s in sub_sentences]
        total_len = sum(text_lengths)

        if total_len == 0:
            return full_translation

        # 粗略按字符数切分翻译
        trans_len = len(full_translation)
        start = sum(text_lengths[:index]) / total_len * trans_len
        end = sum(text_lengths[:index + 1]) / total_len * trans_len

        # 尝试在标点处切割
        start = self._find_nearest_punctuation(full_translation, int(start), -1)
        end = self._find_nearest_punctuation(full_translation, int(end), 1)

        return full_translation[start:end].strip()

    @staticmethod
    def _find_nearest_punctuation(
        text: str,
        pos: int,
        direction: int
    ) -> int:
        """在指定方向找到最近的标点符号位置

        Args:
            text: 文本
            pos: 起始位置
            direction: 搜索方向（-1向左，1向右）

        Returns:
            标点符号位置
        """
        punctuation = "，。！？；,.!?;:："
        pos = max(0, min(pos, len(text)))

        if direction > 0:
            # 向右找
            for i in range(pos, min(pos + 20, len(text))):
                if text[i] in punctuation:
                    return i + 1
            return min(pos + 10, len(text))
        else:
            # 向左找
            for i in range(pos, max(pos - 20, 0), -1):
                if text[i] in punctuation:
                    return i + 1
            return max(pos - 5, 0)

    def merge_duplicate_originals(
        self,
        sentences: List[SubtitleSentence]
    ) -> List[SubtitleSentence]:
        """SRT 写入前去重：合并相邻且共享同一段原文的子句，跳过时间完全重叠的重复条目

        核心规则：
        1. 完全重复（时间和原文都相同）→ 合并：中文拼接，保留一个时间/原文
        2. 时间重叠度 > 80% 且原文相似度（非空交集/整体长度）很高 → 合并
        3. 相邻子句的中文合并后不超过 30 字时直接合并；超过则按字数重新分配时间并切分原文

        目的：修复 "相同源语言句子时汉语被分成两行，每行都配了整句源语言" 的问题。
        """
        if not sentences:
            return sentences

        # 先按时间排序，避免乱序
        sents = sorted(sentences, key=lambda s: s.start_time)

        result: List[SubtitleSentence] = []
        i = 0
        n = len(sents)

        def overlap_ratio(a: SubtitleSentence, b: SubtitleSentence) -> float:
            """两句子的时间重叠度（相对于较短的一句）"""
            ov = max(0.0, min(a.end_time, b.end_time) - max(a.start_time, b.start_time))
            min_dur = min(a.end_time - a.start_time, b.end_time - b.start_time)
            return ov / min_dur if min_dur > 0 else 0.0

        def text_similar(a: str, b: str) -> float:
            """用 "原文前缀匹配比例" 做简单相似度（拉丁语系按单词匹配）"""
            if not a or not b:
                return 0.0
            words_a = a.split()
            words_b = b.split()
            if not words_a or not words_b:
                return 0.0
            common = 0
            # 取较短的那个，按位置逐个单词比较
            min_len = min(len(words_a), len(words_b))
            for k in range(min_len):
                if words_a[k] == words_b[k]:
                    common += 1
                else:
                    break
            return common / max(len(words_a), len(words_b))

        def merge_two(a: SubtitleSentence, b: SubtitleSentence) -> SubtitleSentence:
            """合并两句：取更宽的时间范围，原文选更长的，中文用空格拼接"""
            merged_orig = a.text if len(a.text or "") >= len(b.text or "") else b.text
            cn_a = a.translated_text or ""
            cn_b = b.translated_text or ""
            # 如果 cn_b 紧接在 cn_a 语义后，不需要分隔符
            merged_cn = (cn_a + cn_b).strip()
            return SubtitleSentence(
                start_time=min(a.start_time, b.start_time),
                end_time=max(a.end_time, b.end_time),
                text=merged_orig,
                translated_text=merged_cn,
                source_segments=(a.source_segments or []) + (b.source_segments or [])
            )

        while i < n:
            current = sents[i]
            # 向后看能合并多少个
            j = i + 1
            merged = current
            while j < n:
                cand = sents[j]
                ovr = overlap_ratio(merged, cand)
                sim = text_similar(merged.text or "", cand.text or "")
                # 合并条件：重叠度>0.8 或 原文高度相似(>0.7)或完全相同
                if ovr > 0.8 or (merged.text and cand.text and (merged.text == cand.text or sim > 0.7)):
                    merged = merge_two(merged, cand)
                    j += 1
                else:
                    break
            result.append(merged)
            i = j

        logger.info(
            f"重复原文合并: {len(sentences)} 条 → {len(result)} 条"
            f"（合并 {len(sentences) - len(result)} 条重复或高度相似条目）"
        )
        return result

    @staticmethod
    def _find_hard_cut_index(text: str, soft_max: int) -> int:
        """在硬限切分场景下，在 soft_max 附近找一个相对合理的切点

        优先级：标点 > 空格 > 硬切
        """
        import re
        # 先规范化
        text = text.strip()
        if len(text) <= soft_max:
            return len(text)
        # 先数有效字数位置
        target = soft_max
        pos = 0
        effective = 0
        # 找到 target 有效字数对应的原始位置
        for i, c in enumerate(text):
            if c != ' ':
                effective += 1
                if effective >= target:
                    pos = i + 1
                    break
        # 如果后面还有空格，尝试切到空格
        if pos < len(text) - 1:
            # 往后找标点或空格，最多往后找 5 字符
            for j in range(pos, min(pos + 8, len(text))):
                if text[j] in '，,。！？.!?；;、:：—- ':
                    return j + 1
        return max(pos, 1)

    @staticmethod
    def insert_pseudo_punctuation(paragraphs: List[SubtitleSentence]) -> int:
        """给段落原文按 source_segments 之间的时间间隔插入句末标点（伪标点）

        ASR 输出的文本经常没有任何句末标点，导致：
        1. 翻译引擎看到一个 run-on blob，输出的中文也没有句号
        2. split_translation_to_sentences 按中文句号切不动
        3. split_long_sentences 也救不了因为关卡1已经用过 run-on 了

        解决思路：在翻译前给 paragraph.text 按以下规则插 `.`：
        - source_segments[i] 和 source_segments[i+1] 之间 gap >= 1.0s
        - source_segments[i] 自身时长 >= 3.0s
        且 seg.text 末尾还没有句末标点时才加。

        加的是 `.`（西语句号），让翻译引擎更容易识别句子边界。
        翻译完成后 split_translation_to_sentences 按中文句号切分会更准。
        """
        import re as _re
        sentence_enders = _re.compile(r'[。！？.!?…¿¡\.\s]$')
        SEP = ' '

        insert_count = 0
        for para in paragraphs:
            segs = para.source_segments
            if not segs or len(segs) < 2:
                continue
            text_parts = []
            for i, seg in enumerate(segs):
                t = seg.text.strip()
                if not t:
                    continue
                gap_next = (
                    segs[i + 1].start_time - seg.end_time
                    if i + 1 < len(segs) else 0.0
                )
                seg_dur = seg.end_time - seg.start_time
                needs_punct = (
                    gap_next >= 1.0          # 下一段间隔大 → 句末
                    or seg_dur >= 3.0         # 本段较长 → 句末
                )
                if needs_punct and not sentence_enders.search(t):
                    t = t.rstrip() + '.'
                    insert_count += 1
                text_parts.append(t)
            if text_parts:
                para.text = SEP.join(text_parts)
        if insert_count:
            logger.info(
                f"[伪标点] 向 {len(paragraphs)} 个段落插入 {insert_count} 个句末标点"
            )
        return insert_count
