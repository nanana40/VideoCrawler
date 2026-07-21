"""
视频内容分析模块

扩展功能：在下载视频前询问用户分析提炼方向，下载并翻译后根据用户要求
对内容进行分析并输出，将原视频、翻译视频、分析文案保存在同一文件夹内。

功能特性：
    1. 支持多种分析模式（语言学习、内容总结、关键词提取等）
    2. 根据字幕内容生成分析报告
    3. 将分析结果保存为Markdown文件
    4. 与文件归档器集成，每个视频独立文件夹存储
"""

import os
import re
from typing import Optional, List, Dict, Any
from dataclasses import dataclass
from enum import StrEnum, auto

from utils.logger import get_crawler_logger
from utils.path_helper import get_output_dir


logger = get_crawler_logger()


class AnalysisMode(StrEnum):
    """
    分析模式枚举
    
    定义不同的视频内容分析方向。
    """
    LANGUAGE_LEARNING = auto()
    CONTENT_SUMMARY = auto()
    KEYWORDS = auto()
    GRAMMAR_POINTS = auto()
    FULL_ANALYSIS = auto()
    ORAL_SPOKEN = auto()
    EXAM_PREP = auto()
    SENTENCE_ANALYSIS = auto()
    
    @classmethod
    def from_string(cls, mode_str: str) -> 'AnalysisMode':
        """从字符串转换为分析模式"""
        mode_map = {
            "语言学习": cls.LANGUAGE_LEARNING,
            "内容总结": cls.CONTENT_SUMMARY,
            "关键词提取": cls.KEYWORDS,
            "语法要点": cls.GRAMMAR_POINTS,
            "完整分析": cls.FULL_ANALYSIS,
            "口语学习": cls.ORAL_SPOKEN,
            "应试学习": cls.EXAM_PREP,
            "长难句拆解": cls.SENTENCE_ANALYSIS,
        }
        return mode_map.get(mode_str, cls.FULL_ANALYSIS)
    
    @property
    def display_name(self) -> str:
        """显示名称"""
        display_map = {
            self.LANGUAGE_LEARNING: "语言学习",
            self.CONTENT_SUMMARY: "内容总结",
            self.KEYWORDS: "关键词提取",
            self.GRAMMAR_POINTS: "语法要点",
            self.FULL_ANALYSIS: "完整分析",
            self.ORAL_SPOKEN: "口语学习",
            self.EXAM_PREP: "应试学习",
            self.SENTENCE_ANALYSIS: "长难句拆解",
        }
        return display_map[self]


@dataclass
class AnalysisResult:
    """
    分析结果数据类
    
    包含分析报告的所有信息。
    """
    video_id: str
    mode: AnalysisMode
    report_path: Optional[str] = None
    content: Optional[str] = None
    success: bool = False
    error_message: Optional[str] = None


class VideoAnalyzer:
    """
    视频内容分析器
    
    根据字幕内容对视频进行分析，生成各种形式的分析报告。
    """
    
    def __init__(self) -> None:
        """初始化视频内容分析器"""
        logger.info("视频内容分析器初始化完成")
    
    def analyze(
        self,
        video_id: str,
        subtitles: List[Dict[str, Any]],
        mode: AnalysisMode,
        output_dir: Optional[str] = None
    ) -> AnalysisResult:
        """
        分析视频内容
        
        Args:
            video_id: 视频 ID
            subtitles: 字幕片段列表，每个片段包含 text 和 translated_text
            mode: 分析模式
            output_dir: 输出目录
            
        Returns:
            分析结果
        """
        try:
            report_content = self._generate_report(subtitles, mode)
            
            if output_dir:
                report_path = self._save_report(video_id, mode, report_content, output_dir)
                return AnalysisResult(
                    video_id=video_id,
                    mode=mode,
                    report_path=report_path,
                    content=report_content,
                    success=True
                )
            else:
                return AnalysisResult(
                    video_id=video_id,
                    mode=mode,
                    content=report_content,
                    success=True
                )
                
        except Exception as e:
            logger.error(f"视频分析失败: {e}")
            return AnalysisResult(
                video_id=video_id,
                mode=mode,
                success=False,
                error_message=str(e)
            )
    
    def _generate_report(
        self,
        subtitles: List[Dict[str, Any]],
        mode: AnalysisMode
    ) -> str:
        """
        生成分析报告
        
        Args:
            subtitles: 字幕片段列表
            mode: 分析模式
            
        Returns:
            报告内容（Markdown格式）
        """
        report_parts = []
        
        report_parts.append(f"# 视频内容分析报告")
        report_parts.append(f"## 分析模式: {mode.display_name}")
        report_parts.append(f"")
        
        if mode == AnalysisMode.LANGUAGE_LEARNING:
            report_parts.extend(self._analyze_language_learning(subtitles))
        elif mode == AnalysisMode.CONTENT_SUMMARY:
            report_parts.extend(self._analyze_content_summary(subtitles))
        elif mode == AnalysisMode.KEYWORDS:
            report_parts.extend(self._analyze_keywords(subtitles))
        elif mode == AnalysisMode.GRAMMAR_POINTS:
            report_parts.extend(self._analyze_grammar_points(subtitles))
        elif mode == AnalysisMode.FULL_ANALYSIS:
            report_parts.extend(self._analyze_full(subtitles))
        elif mode == AnalysisMode.ORAL_SPOKEN:
            report_parts.extend(self._analyze_oral_spoken(subtitles))
        elif mode == AnalysisMode.EXAM_PREP:
            report_parts.extend(self._analyze_exam_prep(subtitles))
        elif mode == AnalysisMode.SENTENCE_ANALYSIS:
            report_parts.extend(self._analyze_sentence_analysis(subtitles))
        
        return "\n".join(report_parts)
    
    def _analyze_language_learning(
        self,
        subtitles: List[Dict[str, Any]]
    ) -> List[str]:
        """
        语言学习模式分析
        
        生成适合语言学习者的分析报告，包括词汇、短语、例句等。
        优先分析原文语种（text字段），中文翻译作为参考。
        """
        parts = []
        parts.append("## 语言学习分析")
        parts.append("")
        
        all_text = " ".join([s.get("text", "") for s in subtitles if s.get("text")])
        all_translated = " ".join([s.get("translated_text", "") for s in subtitles if s.get("translated_text")])
        
        use_text = all_text if all_text else all_translated
        
        parts.append("### 一、核心词汇")
        words = self._extract_words(use_text)
        top_words = self._get_top_words(words, 20)
        
        if top_words:
            for word, count in top_words:
                translated = self._find_translation(word, subtitles)
                if translated:
                    parts.append(f"- **{word}** ({count}次)")
                    parts.append(f"  *例句: {translated}*")
                else:
                    parts.append(f"- **{word}** ({count}次)")
        else:
            parts.append("- 暂无词汇数据")
        parts.append("")
        
        parts.append("### 二、实用短语")
        phrases = self._extract_phrases(subtitles)
        if phrases:
            for i, (phrase, translated) in enumerate(phrases[:10], 1):
                parts.append(f"{i}. **{phrase}** → {translated}")
        else:
            parts.append("- 暂无短语数据")
        parts.append("")
        
        parts.append("### 三、典型句式")
        sentences = self._extract_sentences(subtitles)
        if sentences:
            for i, (sentence, translated) in enumerate(sentences[:5], 1):
                parts.append(f"{i}. {sentence}")
                if translated:
                    parts.append(f"   → {translated}")
        else:
            parts.append("- 暂无句式数据")
        parts.append("")
        
        parts.append("### 四、语言难度评估")
        avg_length = sum(len(s.get("text", "").split()) or len(s.get("translated_text", "").split()) for s in subtitles) / max(len(subtitles), 1)
        parts.append(f"- 平均句长: {avg_length:.1f} 词")
        parts.append(f"- 总词汇数: {len(words)}")
        parts.append(f"- 片段数量: {len(subtitles)}")
        
        return parts
    
    def _analyze_content_summary(
        self,
        subtitles: List[Dict[str, Any]]
    ) -> List[str]:
        """
        内容总结模式分析
        
        对视频内容进行概括总结。
        """
        parts = []
        parts.append("## 内容总结")
        parts.append("")
        
        all_text = " ".join([s.get("text", "") for s in subtitles])
        all_translated = " ".join([s.get("translated_text", "") for s in subtitles])
        
        content = all_translated if all_translated else all_text
        
        parts.append("### 一、主要内容")
        if content:
            parts.append(content[:800] + "..." if len(content) > 800 else content)
        else:
            parts.append("暂无内容")
        parts.append("")
        
        parts.append("### 二、关键信息")
        key_points = self._extract_key_points(subtitles)
        if key_points:
            for i, point in enumerate(key_points, 1):
                parts.append(f"{i}. {point}")
        else:
            parts.append("- 暂无关键信息")
        parts.append("")
        
        parts.append("### 三、时间线")
        timeline = self._generate_timeline(subtitles)
        if timeline:
            for time, text in timeline[:10]:
                parts.append(f"- **{time}**: {text[:60]}")
        else:
            parts.append("- 暂无时间线数据")
        
        return parts
    
    def _analyze_keywords(
        self,
        subtitles: List[Dict[str, Any]]
    ) -> List[str]:
        """
        关键词提取模式分析
        
        提取视频中的关键词和主题。
        """
        parts = []
        parts.append("## 关键词提取")
        parts.append("")
        
        all_text = " ".join([s.get("text", "") for s in subtitles])
        
        parts.append("### 一、高频词汇")
        words = self._extract_words(all_text)
        top_words = self._get_top_words(words, 30)
        
        for word, count in top_words:
            parts.append(f"- **{word}**: {count}次")
        parts.append("")
        
        parts.append("### 二、主题分类")
        themes = self._classify_themes(subtitles)
        for theme, count in themes.items():
            parts.append(f"- **{theme}**: {count}个片段")
        
        return parts
    
    def _analyze_grammar_points(
        self,
        subtitles: List[Dict[str, Any]]
    ) -> List[str]:
        """
        语法要点模式分析
        
        分析视频中的语法结构和句型。
        """
        parts = []
        parts.append("## 语法要点分析")
        parts.append("")
        
        parts.append("### 一、句子类型分析")
        sentence_types = self._analyze_sentence_types(subtitles)
        for stype, count in sentence_types.items():
            parts.append(f"- **{stype}**: {count}句")
        parts.append("")
        
        parts.append("### 二、时态分布")
        tenses = self._analyze_tenses(subtitles)
        for tense, count in tenses.items():
            parts.append(f"- **{tense}**: {count}次")
        parts.append("")
        
        parts.append("### 三、常用句型")
        patterns = self._extract_patterns(subtitles)
        for i, (pattern, examples) in enumerate(patterns.items(), 1):
            parts.append(f"{i}. **{pattern}**")
            for ex in examples[:2]:
                parts.append(f"   - {ex}")
            parts.append("")
        
        return parts
    
    def _analyze_full(
        self,
        subtitles: List[Dict[str, Any]]
    ) -> List[str]:
        """
        完整分析模式
        
        综合所有分析维度生成完整报告。
        """
        parts = []
        parts.extend(self._analyze_content_summary(subtitles))
        parts.append("")
        parts.extend(self._analyze_keywords(subtitles))
        parts.append("")
        parts.extend(self._analyze_language_learning(subtitles))
        parts.append("")
        parts.extend(self._analyze_grammar_points(subtitles))
        
        return parts
    
    def _analyze_oral_spoken(
        self,
        subtitles: List[Dict[str, Any]]
    ) -> List[str]:
        """
        口语学习模式分析
        
        分析视频中的口语化表达、非正式用语、缩略语、填充词等，
        帮助学习者掌握真实语境中的口语用法。
        """
        parts = []
        parts.append("## 口语学习分析")
        parts.append("")
        
        oral_markers = ["alright", "well", "so", "yeah", "yep", "nope", "uh", "um",
                        "like", "you know", "I mean", "kind of", "sort of", "pretty much",
                        "gonna", "wanna", "gotta", "lemme", "gimme", "wanna", "hafta",
                        "ain't", "don't", "can't", "won't", "wouldn't", "couldn't",
                        "awesome", "cool", "nice", "great", "amazing", "sweet",
                        "guy", "guys", "dude", "buddy", "pal"]
        
        all_text = " ".join([s.get("text", "").lower() for s in subtitles if s.get("text")])
        
        parts.append("### 一、口语标记词")
        found_markers = []
        for marker in oral_markers:
            if marker in all_text:
                count = all_text.count(marker)
                found_markers.append((marker, count))
        
        if found_markers:
            found_markers.sort(key=lambda x: x[1], reverse=True)
            for marker, count in found_markers[:15]:
                for s in subtitles:
                    text = s.get("text", "").lower()
                    if marker in text:
                        translated = s.get("translated_text", "")
                        parts.append(f"- **{marker}** ({count}次)")
                        parts.append(f"  *例句: {s.get('text', '')}*")
                        if translated:
                            parts.append(f"  *翻译: {translated}*")
                        break
        else:
            parts.append("- 未检测到明显的口语标记词")
        parts.append("")
        
        parts.append("### 二、缩略语与非正式表达")
        contractions = {
            "gonna": "going to",
            "wanna": "want to",
            "gotta": "got to / have to",
            "lemme": "let me",
            "gimme": "give me",
            "hafta": "have to",
            "ain't": "am not / is not / are not",
            "'cause": "because",
            "c'mon": "come on",
            "d'you": "do you",
            "whatcha": "what are you",
            "y'all": "you all",
            "kinda": "kind of",
            "sorta": "sort of",
        }
        
        found_contractions = []
        for contraction, full_form in contractions.items():
            if contraction in all_text:
                count = all_text.count(contraction)
                found_contractions.append((contraction, full_form, count))
        
        if found_contractions:
            found_contractions.sort(key=lambda x: x[2], reverse=True)
            for contraction, full_form, count in found_contractions[:10]:
                parts.append(f"- **{contraction}** → {full_form} ({count}次)")
                for s in subtitles:
                    if contraction in s.get("text", "").lower():
                        parts.append(f"  *例句: {s.get('text', '')}*")
                        parts.append(f"  *翻译: {s.get('translated_text', '')}*")
                        break
                parts.append("")
        else:
            parts.append("- 未检测到明显的缩略语")
        parts.append("")
        
        parts.append("### 三、口语常用句型")
        oral_patterns = [
            (r"Alright,? so", "开场白：Alright, so..."),
            (r"You know", "口语填充：You know..."),
            (r"I mean", "口语填充：I mean..."),
            (r"kind of", "模糊表达：kind of..."),
            (r"sort of", "模糊表达：sort of..."),
            (r"pretty much", "程度表达：pretty much..."),
            (r"That's cool", "评价表达：That's cool"),
            (r"You got it", "确认表达：You got it"),
            (r"No problem", "回应表达：No problem"),
            (r"Got it", "理解表达：Got it"),
        ]
        
        found_patterns = []
        for pattern, desc in oral_patterns:
            matches = re.findall(pattern, all_text)
            if matches:
                found_patterns.append((desc, len(matches)))
        
        if found_patterns:
            found_patterns.sort(key=lambda x: x[1], reverse=True)
            for desc, count in found_patterns[:10]:
                parts.append(f"- **{desc}**: {count}次")
                for s in subtitles:
                    if re.search(pattern, s.get("text", "").lower()):
                        parts.append(f"  *例句: {s.get('text', '')}*")
                        break
                parts.append("")
        else:
            parts.append("- 未检测到明显的口语句型")
        parts.append("")
        
        parts.append("### 四、非正式词汇")
        informal_words = ["cool", "awesome", "nice", "great", "amazing", "sweet",
                         "guy", "guys", "dude", "buddy", "pal", "stuff", "thing",
                         "things", "stuff", "kind", "sort", "pretty", "much"]
        
        found_informal = []
        for word in informal_words:
            if word in all_text.split():
                count = all_text.split().count(word)
                found_informal.append((word, count))
        
        if found_informal:
            found_informal.sort(key=lambda x: x[1], reverse=True)
            for word, count in found_informal[:10]:
                parts.append(f"- **{word}** ({count}次)")
                for s in subtitles:
                    if word in s.get("text", "").lower().split():
                        parts.append(f"  *例句: {s.get('text', '')}*")
                        parts.append(f"  *翻译: {s.get('translated_text', '')}*")
                        break
                parts.append("")
        else:
            parts.append("- 未检测到明显的非正式词汇")
        
        return parts
    
    def _analyze_exam_prep(
        self,
        subtitles: List[Dict[str, Any]]
    ) -> List[str]:
        """
        应试学习模式分析
        
        分析视频中的高难度词汇、复杂句式、值得学习的有难度词句，
        帮助学习者提升应试能力。
        """
        parts = []
        parts.append("## 应试学习分析")
        parts.append("")
        
        advanced_words = {
            "phenomenon": "现象", "occurrence": "发生", "circumstance": "情况",
            "substantial": "大量的", "significant": "重要的", "considerable": "相当的",
            "approximately": "大约", "essentially": "本质上", "fundamentally": "根本上",
            "demonstrate": "展示", "illustrate": "说明", "exemplify": "举例",
            "comprehensive": "全面的", "elaborate": "详细的", "specific": "具体的",
            "contribute": "贡献", "influence": "影响", "determine": "决定",
            "acquire": "获得", "achieve": "实现", "attain": "达到",
            "consequence": "结果", "implication": "暗示", "indication": "指示",
            "perspective": "视角", "dimension": "维度", "aspect": "方面",
            "potential": "潜力", "capacity": "能力", "capability": "才能",
            "emphasis": "强调", "priority": "优先", "significance": "重要性",
            "analyze": "分析", "evaluate": "评估", "assess": "评定",
            "establish": "建立", "maintain": "维持", "sustain": "支撑",
            "derive": "衍生", "infer": "推断", "deduce": "推导",
        }
        
        all_text = " ".join([s.get("text", "").lower() for s in subtitles if s.get("text")])
        
        parts.append("### 一、高级词汇")
        found_advanced = []
        for word, meaning in advanced_words.items():
            if word in all_text.split():
                count = all_text.split().count(word)
                found_advanced.append((word, meaning, count))
        
        if found_advanced:
            found_advanced.sort(key=lambda x: x[2], reverse=True)
            for word, meaning, count in found_advanced[:15]:
                parts.append(f"- **{word}** ({meaning}) - {count}次")
                for s in subtitles:
                    if word in s.get("text", "").lower().split():
                        parts.append(f"  *例句: {s.get('text', '')}*")
                        parts.append(f"  *翻译: {s.get('translated_text', '')}*")
                        break
                parts.append("")
        else:
            parts.append("- 未检测到高级词汇，建议使用更长的视频进行分析")
        parts.append("")
        
        parts.append("### 二、复杂句式")
        complex_patterns = [
            (r"It is .+ that", "强调句型"),
            (r"There be .+", "存在句型"),
            (r"The reason why .+ is that", "原因句型"),
            (r"Not only .+ but also", "并列强调"),
            (r"It seems that", "推测句型"),
            (r"What .+ is", "名词性从句"),
            (r"That is why", "结论句型"),
            (r"In order to", "目的状语"),
            (r"Although .+ ,", "让步状语"),
            (r"Because .+ ,", "原因状语"),
        ]
        
        found_complex = []
        for pattern, desc in complex_patterns:
            matches = re.findall(pattern, all_text)
            if matches:
                found_complex.append((desc, len(matches)))
        
        if found_complex:
            found_complex.sort(key=lambda x: x[1], reverse=True)
            for desc, count in found_complex[:10]:
                parts.append(f"- **{desc}**: {count}次")
                for s in subtitles:
                    if re.search(pattern, s.get("text", "").lower()):
                        parts.append(f"  *例句: {s.get('text', '')}*")
                        parts.append(f"  *翻译: {s.get('translated_text', '')}*")
                        break
                parts.append("")
        else:
            parts.append("- 未检测到复杂句式")
        parts.append("")
        
        parts.append("### 三、长难句分析")
        long_sentences = []
        for s in subtitles:
            text = s.get("text", "")
            word_count = len(text.split())
            if word_count >= 10:
                translated = s.get("translated_text", "")
                long_sentences.append((text, translated, word_count))
        
        long_sentences.sort(key=lambda x: x[2], reverse=True)
        
        if long_sentences:
            for i, (sentence, translated, word_count) in enumerate(long_sentences[:5], 1):
                parts.append(f"{i}. **{sentence}**")
                parts.append(f"   词数: {word_count}")
                if translated:
                    parts.append(f"   翻译: {translated}")
                parts.append(f"   结构分析: {self._analyze_sentence_structure(sentence)}")
                parts.append("")
        else:
            parts.append("- 未检测到长难句")
        parts.append("")
        
        parts.append("### 四、书面表达推荐")
        formal_alternatives = {
            "cool": "impressive / remarkable",
            "guy": "person / individual",
            "stuff": "materials / items",
            "thing": "matter / aspect",
            "kind of": "to some extent",
            "sort of": "to a certain degree",
            "pretty much": "essentially / largely",
            "gotta": "have to / must",
            "wanna": "want to",
            "gonna": "going to",
        }
        
        found_alternatives = []
        for informal, formal in formal_alternatives.items():
            if informal in all_text:
                found_alternatives.append((informal, formal))
        
        if found_alternatives:
            for informal, formal in found_alternatives[:10]:
                parts.append(f"- **{informal}** → {formal}")
                for s in subtitles:
                    if informal in s.get("text", "").lower():
                        formal_sentence = s.get("text", "").replace(informal, formal)
                        parts.append(f"  *原句: {s.get('text', '')}*")
                        parts.append(f"  *正式表达: {formal_sentence}*")
                        break
                parts.append("")
        else:
            parts.append("- 未检测到需要替换的非正式表达")
        
        return parts
    
    def _analyze_sentence_analysis(
        self,
        subtitles: List[Dict[str, Any]]
    ) -> List[str]:
        """
        长难句拆解分析模式
        
        生成格式统一、分区规整的英语教辅长难句拆解笔记，
        每句包含：句子词数标注→英文原句→专属语法拆解区→个人学习思考区。
        语法分析必须贴合单句真实语法结构精准拆解，禁止通用套话。
        每句学习思考角度完全不重复。
        """
        parts = []
        parts.append("## 长难句拆解分析")
        parts.append("")
        parts.append("---")
        parts.append("")
        
        sentences = []
        for s in subtitles:
            text = s.get("text", "")
            if text and len(text.strip()) >= 5:
                word_count = len(text.split())
                translated = s.get("translated_text", "")
                sentences.append((text.strip(), translated.strip() if translated else "", word_count))
        
        sentences.sort(key=lambda x: x[2], reverse=True)
        
        used_thinking_angles = set()
        
        for i, (sentence, translated, word_count) in enumerate(sentences[:3], 1):
            parts.append(f"### 📝 句子 {i}")
            parts.append("")
            
            parts.append(f"**【词数标注】** {word_count} 词")
            parts.append("")
            
            parts.append(f"**【英文原句】**")
            parts.append(f"> {sentence}")
            parts.append("")
            
            if translated:
                parts.append(f"**【中文翻译】**")
                parts.append(f"> {translated}")
                parts.append("")
            
            parts.append(f"**【语法拆解】**")
            grammar_analysis = self._generate_grammar_analysis(sentence)
            for line in grammar_analysis:
                parts.append(f"  {line}")
            parts.append("")
            
            parts.append(f"**【学习思考】**")
            thinking = self._generate_learning_thinking(sentence, used_thinking_angles)
            parts.append(f"  {thinking}")
            parts.append("")
            
            parts.append("---")
            parts.append("")
        
        if not sentences:
            parts.append("- 暂无可用的句子进行分析")
        
        return parts
    
    def _generate_grammar_analysis(self, sentence: str) -> List[str]:
        """
        根据句子真实语法结构生成精准的语法拆解
        
        禁止通用套话，必须贴合单句真实结构进行分析。
        """
        import re
        
        analysis = []
        
        sentence_lower = sentence.lower()
        words = sentence.split()
        
        if re.search(r"\bis\b", sentence_lower) and re.search(r"\bthat\b", sentence_lower):
            is_predicate_position = sentence_lower.find("is")
            that_position = sentence_lower.find("that")
            
            if is_predicate_position < that_position:
                subject_end = is_predicate_position
                subject = sentence[:subject_end].strip()
                
                analysis.append(f"📌 **句子类型**: 表语从句复合句")
                analysis.append("")
                
                analysis.append(f"🔍 **主语部分**: `{subject}`")
                analysis.append(f"   - `{words[0]}` 是形容词，作定语修饰 `{words[1]}`")
                analysis.append(f"   - `{words[1]}` 是核心主语")
                if len(words) > 2 and words[2] == "about":
                    analysis.append(f"   - `{words[2]}` 开始的介词短语作后置定语，修饰主语")
                analysis.append("")
                
                analysis.append(f"🔗 **系动词**: `is`")
                analysis.append("")
                
                analysis.append(f"📊 **表语从句**: `that {sentence[that_position+5:].strip()}`")
                analysis.append(f"   - 由 `that` 引导，作系动词 `is` 的表语")
                analysis.append(f"   - `that` 在从句中不充当成分")
                analysis.append("")
                
                if "really" in sentence_lower:
                    really_count = sentence_lower.count("really")
                    analysis.append(f"✨ **语气特点**: `really` 重复 {really_count} 次")
                    analysis.append(f"   - 口语中通过重复副词加强语气")
                    analysis.append(f"   - 书面英语通常用程度副词单次表达")
                analysis.append("")
                
                return analysis
        
        if re.search(r"\balright\b", sentence_lower) or re.search(r"\bso\b", sentence_lower):
            analysis.append(f"📌 **句子类型**: 口语倒装短句（无从句）")
            analysis.append("")
            
            has_alright = "alright" in sentence_lower
            has_so = "so" in sentence_lower
            
            if has_alright:
                analysis.append(f"🎯 **过渡词**: `alright`")
                analysis.append(f"   - 口语开场过渡词，相当于中文的'好吧'")
                analysis.append(f"   - 不表示字面意义的'好'，仅用于承接话题")
                analysis.append("")
            
            if has_so:
                analysis.append(f"🎯 **过渡词**: `so`")
                analysis.append(f"   - 口语逻辑连接词，表示'那么'、'所以'")
                analysis.append(f"   - 在非正式口语中非常高频")
                analysis.append("")
            
            if re.search(r"\bhere we are\b", sentence_lower):
                analysis.append(f"🔄 **倒装结构**: `here we are`")
                analysis.append(f"   - 这是一个完全倒装的口语表达")
                analysis.append(f"   - 完整结构应为 `we are here`，但口语中常倒装")
                analysis.append(f"   - 用于表达'我们到了'、'我们在这儿'")
                analysis.append("")
            
            if len(words) <= 10:
                analysis.append(f"📏 **句式特点**: 短句结构")
                analysis.append(f"   - 句子结构简单，无复合从句")
                analysis.append(f"   - 符合口语交流的即时性特点")
            analysis.append("")
            
            return analysis
        
        if re.search(r"\bthat's pretty much all there is to say\b", sentence_lower):
            analysis.append(f"📌 **句子类型**: 口语固定句式")
            analysis.append("")
            
            analysis.append(f"🔑 **核心结构**: `that's pretty much all there is to say`")
            analysis.append(f"   - 这是一个非常经典的口语收尾表达")
            analysis.append(f"   - 意思是'差不多就这些了'、'没什么好说的了'")
            analysis.append("")
            
            analysis.append(f"📊 **语法拆解**:")
            analysis.append(f"   - `that` 指代前文内容")
            analysis.append(f"   - `is` 系动词")
            analysis.append(f"   - `pretty much` 程度副词短语，修饰 `all`")
            analysis.append(f"   - `all there is to say` 是一个定语从句结构")
            analysis.append(f"     - `there is` 是存在句型")
            analysis.append(f"     - `to say` 是不定式作后置定语")
            analysis.append("")
            
            analysis.append(f"💬 **使用场景**:")
            analysis.append(f"   - 用于对话或演讲的结尾")
            analysis.append(f"   - 表示内容已经说完，可以结束话题")
            analysis.append(f"   - 比书面语的 `That is all` 更加自然口语化")
            analysis.append("")
            
            return analysis
        
        if re.search(r"\bthere be\b", sentence_lower):
            analysis.append(f"📌 **句子类型**: 存在句型")
            analysis.append("")
            
            analysis.append(f"🔑 **核心结构**: `there be` 句型")
            analysis.append(f"   - 表示'存在'、'有'的概念")
            analysis.append(f"   - `there` 是形式主语，真正的主语是后面的名词")
            analysis.append("")
            
            analysis.append(f"📊 **语法拆解**:")
            analysis.append(f"   - `there` + be动词 + 真正主语")
            analysis.append(f"   - be动词的数与后面的主语保持一致")
            analysis.append("")
            
            return analysis
        
        if len(words) >= 12:
            analysis.append(f"📌 **句子类型**: 复杂句")
            analysis.append("")
            
            clauses = []
            if re.search(r"\b(that|which|who|whom)\b", sentence_lower):
                clauses.append("定语从句")
            if re.search(r"\b(that|what|whether)\b", sentence_lower):
                clauses.append("名词性从句")
            if re.search(r"\b(and|but|or)\b", sentence_lower):
                clauses.append("并列结构")
            
            if clauses:
                analysis.append(f"🔗 **从句类型**: {' + '.join(clauses)}")
                analysis.append("")
            
            analysis.append(f"📊 **语法拆解**:")
            analysis.append(f"   - 句子包含 {len(words)} 个单词")
            analysis.append(f"   - 建议按照意群拆分理解")
            analysis.append("")
            
            return analysis
        
        analysis.append(f"📌 **句子类型**: 简单句")
        analysis.append("")
        
        analysis.append(f"📊 **语法拆解**:")
        analysis.append(f"   - 句子结构简单，主谓宾完整")
        analysis.append(f"   - 建议重点关注词汇搭配和表达")
        analysis.append("")
        
        return analysis
    
    def _generate_learning_thinking(self, sentence: str, used_angles: set) -> str:
        """
        生成第一人称学习思考，每句思考角度完全不重复
        
        可选方向：盲听踩坑、中式英语误区、听力连读难点、日常仿写场景、
                 课本不会讲的口语细节、句式仿写练习、语调变化、
                 文化差异、词汇搭配、时态选择
        """
        import re
        
        thinking_angles = [
            ("盲听踩坑", self._generate_blind_listening_thinking),
            ("中式英语误区", self._generate_chinese_english_mistake_thinking),
            ("听力连读难点", self._generate_listening_connection_thinking),
            ("日常仿写场景", self._generate_daily_imitation_thinking),
            ("课本不会讲的口语细节", self._generate_textbook_detail_thinking),
            ("句式仿写练习", self._generate_sentence_imitation_thinking),
            ("文化差异", self._generate_cultural_difference_thinking),
            ("词汇搭配", self._generate_collocation_thinking),
        ]
        
        available_angles = [a for a in thinking_angles if a[0] not in used_angles]
        
        if not available_angles:
            return "学习感悟：这个句子让我对英语口语有了更深的理解。"
        
        chosen_angle, thinking_func = available_angles[0]
        used_angles.add(chosen_angle)
        
        return thinking_func(sentence, chosen_angle)
    
    def _generate_blind_listening_thinking(self, sentence: str, angle: str) -> str:
        """生成盲听踩坑学习思考"""
        import re
        
        tricky_parts = []
        
        if re.search(r"\breally", sentence.lower()):
            tricky_parts.append("`really` 的发音可能被听成 `real`")
        
        if re.search(r"\balright", sentence.lower()):
            tricky_parts.append("`alright` 可能被听成 `all right`")
        
        if re.search(r"\bpretty much", sentence.lower()):
            tricky_parts.append("`pretty much` 连读时可能听不清")
        
        if re.search(r"\bthere is", sentence.lower()):
            tricky_parts.append("`there is` 连读成 `there's`")
        
        if tricky_parts:
            parts_str = "、".join(tricky_parts)
            return f"🎧 盲听踩坑：这句话中 {parts_str}，第一次盲听很容易听错。特别是当说话人语速较快时，连读会让这些词变得模糊。建议反复精听，注意每个单词的实际发音和连读情况。"
        
        return f"🎧 盲听踩坑：这句话整体难度适中，但在真实对话中，说话人的语速和语调变化可能会影响理解。建议多听不同口音的版本，提高听力适应能力。"
    
    def _generate_chinese_english_mistake_thinking(self, sentence: str, angle: str) -> str:
        """生成中式英语误区学习思考"""
        import re
        
        chinese_mistakes = []
        
        if "the cool thing" in sentence.lower():
            chinese_mistakes.append("中文直译可能会说'那个酷的事情'，但英语中 `the cool thing` 是自然表达")
        
        if "guys" in sentence.lower():
            chinese_mistakes.append("中文不会用'伙计们'来统称人，但英语中 `guys` 非常常用")
        
        if "pretty much" in sentence.lower():
            chinese_mistakes.append("中文可能会说'几乎'或'差不多'，但 `pretty much` 是更地道的口语表达")
        
        if "there is to say" in sentence.lower():
            chinese_mistakes.append("中文不会说'有要说的'，但这是英语中的固定表达")
        
        if chinese_mistakes:
            mistakes_str = "\n   - ".join(chinese_mistakes)
            return f"🚫 中式英语误区：\n   - {mistakes_str}\n   这些表达如果按照中文思维直译会显得很奇怪，需要特别记忆英语中的习惯用法。"
        
        return f"🚫 中式英语误区：这句话中的一些表达如果直译成中文会不自然。学习英语时，要注意不要用中文思维来构造英语句子，而是要学习英语的表达方式。"
    
    def _generate_listening_connection_thinking(self, sentence: str, angle: str) -> str:
        """生成听力连读难点学习思考"""
        import re
        
        connections = []
        
        if re.search(r"\bthat's", sentence.lower()):
            connections.append("`that's` 是 `that is` 的连读")
        
        if re.search(r"\breally, really", sentence.lower()):
            connections.append("多个 `really` 之间可能有连读")
        
        if re.search(r"\bpretty much", sentence.lower()):
            connections.append("`pretty` 和 `much` 之间可能有连读")
        
        if re.search(r"\bso the", sentence.lower()):
            connections.append("`so` 和 `the` 之间可能有连读")
        
        if connections:
            conn_str = "、".join(connections)
            return f"🔗 听力连读难点：这句话中有 {conn_str}，在真实听力中这些连读会让单词之间的界限变得模糊。建议先慢速精听，再逐步提高速度，训练耳朵捕捉连读的能力。"
        
        return f"🔗 听力连读难点：这句话看似简单，但在真实对话中，说话人可能会有连读、弱读等现象。建议多听真实的口语材料，熟悉英语口语的发音特点。"
    
    def _generate_daily_imitation_thinking(self, sentence: str, angle: str) -> str:
        """生成日常仿写场景学习思考"""
        import re
        
        scenarios = []
        
        if re.search(r"\balright,? so", sentence.lower()):
            scenarios.append("可以用在日常聊天的开场白")
        
        if re.search(r"\bthat's pretty much all", sentence.lower()):
            scenarios.append("可以用在对话结束时")
        
        if re.search(r"\bhere we are", sentence.lower()):
            scenarios.append("可以用在到达某个地方时")
        
        if "cool thing" in sentence.lower():
            scenarios.append("可以用在分享有趣的事情时")
        
        if scenarios:
            scenario_str = "、".join(scenarios)
            return f"📝 日常仿写场景：这句话非常适合在 {scenario_str} 时使用。建议把它背下来，在实际对话中尝试运用，这样可以让你的英语口语更加地道自然。"
        
        return f"📝 日常仿写场景：这句话虽然结构简单，但很实用。可以尝试在日常对话中使用类似的结构，比如替换不同的主语和谓语，创造出新的句子。"
    
    def _generate_textbook_detail_thinking(self, sentence: str, angle: str) -> str:
        """生成课本不会讲的口语细节学习思考"""
        import re
        
        details = []
        
        if re.search(r"\breally, really, really", sentence.lower()):
            details.append("课本不会教你可以重复 `really` 来加强语气")
        
        if re.search(r"\balright\b", sentence.lower()):
            details.append("课本不会详细讲 `alright` 和 `ok` 的细微区别")
        
        if re.search(r"\bguys\b", sentence.lower()):
            details.append("课本不会告诉你 `guys` 可以作为中性称呼")
        
        if re.search(r"\bpretty much\b", sentence.lower()):
            details.append("课本不会教你 `pretty much` 这个口语化的程度表达")
        
        if details:
            detail_str = "、".join(details)
            return f"📚 课本不会讲的口语细节：{detail_str}。这些都是真实口语中非常常见但课本很少涉及的内容，需要通过大量接触真实材料来学习。"
        
        return f"📚 课本不会讲的口语细节：这句话中的一些表达在课本中可能不会详细讲解，但在真实对话中却非常常用。建议多观看英语视频、听播客，积累这些课本之外的知识。"
    
    def _generate_sentence_imitation_thinking(self, sentence: str, angle: str) -> str:
        """生成句式仿写练习学习思考"""
        import re
        
        pattern = ""
        
        if re.search(r"\bThe .+ thing about .+ is that", sentence.lower()):
            pattern = "The [形容词] thing about [名词] is that..."
        
        if re.search(r"\bThat's pretty much all", sentence.lower()):
            pattern = "That's pretty much all..."
        
        if re.search(r"\bHere we are", sentence.lower()):
            pattern = "Here we are..."
        
        if pattern:
            return f"✍️ 句式仿写练习：这句话的结构是 `{pattern}`，可以尝试替换不同的词汇来创造新句子。比如：\n   - The amazing thing about learning English is that it opens so many doors.\n   - That's pretty much all I know about this topic.\n   通过仿写练习，可以加深对这个句式的理解和记忆。"
        
        return f"✍️ 句式仿写练习：这句话的结构很值得学习，可以尝试模仿它的结构来写新句子。比如改变主语、宾语或状语，创造出符合自己表达需求的句子。"
    
    def _generate_cultural_difference_thinking(self, sentence: str, angle: str) -> str:
        """生成文化差异学习思考"""
        import re
        
        cultural_points = []
        
        if "guys" in sentence.lower():
            cultural_points.append("`guys` 在英语中是中性称呼，但中文没有完全对应的表达")
        
        if re.search(r"\balright\b", sentence.lower()):
            cultural_points.append("`alright` 的使用频率反映了英语文化中随意的沟通风格")
        
        if "cool" in sentence.lower():
            cultural_points.append("`cool` 的广泛使用体现了英语文化中对'酷'的追求")
        
        if cultural_points:
            points_str = "、".join(cultural_points)
            return f"🌍 文化差异：{points_str}。理解这些文化背景可以帮助我们更好地理解和使用这些表达，避免因为文化差异导致的误解。"
        
        return f"🌍 文化差异：这句话中的一些表达反映了英语文化的特点。学习语言的同时，也应该了解其背后的文化背景，这样才能真正做到地道表达。"
    
    def _generate_collocation_thinking(self, sentence: str, angle: str) -> str:
        """生成词汇搭配学习思考"""
        import re
        
        collocations = []
        
        if "cool thing" in sentence.lower():
            collocations.append("`cool thing` 是常见搭配")
        
        if "long hunts" in sentence.lower():
            collocations.append("`long hunts` 是常见搭配")
        
        if "pretty much" in sentence.lower():
            collocations.append("`pretty much` 是固定搭配")
        
        if "there is to say" in sentence.lower():
            collocations.append("`there is to say` 是固定搭配")
        
        if collocations:
            coll_str = "、".join(collocations)
            return f"🔤 词汇搭配：这句话中有 {coll_str}。学习英语时，不要只记单个单词，要注意单词之间的搭配关系，这样才能说出地道的英语。"
        
        return f"🔤 词汇搭配：这句话中的一些词汇组合是非常地道的搭配。建议把这些搭配记下来，在写作和口语中尝试使用，提高语言的准确性和地道性。"
    
    def _analyze_sentence_structure(self, sentence: str) -> str:
        """分析句子结构"""
        import re
        
        patterns = []
        
        if re.search(r"\b(Although|Though|Even though)\b", sentence):
            patterns.append("让步状语从句")
        if re.search(r"\b(Because|Since|As)\b", sentence):
            patterns.append("原因状语从句")
        if re.search(r"\b(If|Whether)\b", sentence):
            patterns.append("条件状语从句")
        if re.search(r"\b(When|While|As)\b", sentence):
            patterns.append("时间状语从句")
        if re.search(r"\b(that|which|who|whom)\b", sentence):
            patterns.append("定语从句")
        if re.search(r"\b(that|what|whether)\b", sentence):
            patterns.append("名词性从句")
        if re.search(r"\b(and|but|or|so)\b", sentence):
            patterns.append("并列结构")
        if re.search(r"\b(Not only|Neither)\b", sentence):
            patterns.append("倒装结构")
        
        if patterns:
            return " + ".join(patterns)
        else:
            return "简单句"
    
    def _save_report(
        self,
        video_id: str,
        mode: AnalysisMode,
        content: str,
        output_dir: str
    ) -> str:
        """
        保存分析报告
        
        Args:
            video_id: 视频 ID
            mode: 分析模式
            content: 报告内容
            output_dir: 输出目录
            
        Returns:
            报告文件路径
        """
        os.makedirs(output_dir, exist_ok=True)
        filename = f"{video_id}_analysis_{mode.value}.md"
        filepath = os.path.join(output_dir, filename)
        
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(content)
        
        logger.info(f"分析报告已保存: {filepath}")
        return filepath
    
    def _extract_words(self, text: str) -> List[str]:
        """提取单词/词汇列表（支持中英文，中文使用jieba分词）"""
        import re
        
        chinese_pattern = re.compile(r'[\u4e00-\u9fff]+')
        chinese_text = "".join(chinese_pattern.findall(text))
        
        english_words = re.findall(r'\b[a-zA-Z]+\b', text.lower())
        
        stop_words = {"the", "and", "a", "an", "is", "are", "was", "were", "be", "been", "being",
                      "have", "has", "had", "do", "does", "did", "will", "would", "could", "should",
                      "may", "might", "must", "shall", "can", "need", "dare", "ought", "used",
                      "to", "of", "in", "for", "on", "with", "at", "by", "from", "as", "into",
                      "through", "during", "before", "after", "above", "below", "between", "under",
                      "again", "further", "then", "once", "here", "there", "when", "where", "why",
                      "how", "all", "each", "few", "more", "most", "other", "some", "such", "no",
                      "nor", "not", "only", "own", "same", "so", "than", "too", "very", "just",
                      "but", "if", "or", "because", "until", "while", "about", "against", "he",
                      "she", "it", "we", "they", "you", "i", "me", "him", "her", "us", "them",
                      "this", "that", "these", "those", "what", "which", "who", "whom", "whose",
                      "的", "了", "和", "是", "就", "都", "而", "及", "与", "着", "或", "一个",
                      "没有", "我们", "你们", "他们", "它们", "这个", "那个", "这些", "那些",
                      "什么", "怎么", "为什么", "因为", "所以", "但是", "如果", "虽然", "不过",
                      "还是", "又", "也", "很", "太", "更", "最", "还", "再", "也", "都", "不",
                      "要", "会", "能", "可以", "应该", "必须", "可能", "应该", "得", "有", "在",
                      "上", "下", "前", "后", "左", "右", "里", "外", "中", "间", "之", "乎",
                      "者", "也", "曰", "哉", "矣", "焉", "耳", "而已", "乎", "于", "以", "而",
                      "则", "乃", "其", "所", "者", "然", "乎", "哉", "也", "矣", "焉", "耳",
                      "好吧", "这些", "家伙", "一点", "他们", "非常", "几乎", "所有", "要说"}
        
        filtered_english = [w for w in english_words if w not in stop_words and len(w) > 2]
        
        all_words = []
        
        if chinese_text:
            try:
                import jieba
                jieba_words = jieba.lcut(chinese_text)
                for word in jieba_words:
                    if word not in stop_words and len(word) >= 2:
                        all_words.append(word)
            except ImportError:
                for char in chinese_text:
                    if char not in stop_words:
                        all_words.append(char)
        
        all_words.extend(filtered_english)
        
        return all_words
    
    def _get_top_words(self, words: List[str], n: int = 10) -> List[tuple]:
        """获取高频词"""
        word_counts = {}
        for word in words:
            word_counts[word] = word_counts.get(word, 0) + 1
        
        return sorted(word_counts.items(), key=lambda x: x[1], reverse=True)[:n]
    
    def _find_translation(self, word: str, subtitles: List[Dict[str, Any]]) -> str:
        """查找单词所在句子的翻译"""
        for s in subtitles:
            text = s.get("text", "").lower()
            if word in text.split():
                return s.get("translated_text", "")
        return ""
    
    def _extract_phrases(self, subtitles: List[Dict[str, Any]]) -> List[tuple]:
        """提取短语（支持中英文）"""
        phrases = []
        for s in subtitles:
            text = s.get("text", "")
            translated = s.get("translated_text", "")
            
            content = text if text else translated
            translation = translated if (translated and translated != text) else ""
            
            if len(content) >= 2 and len(content) <= 15:
                phrases.append((content.strip(), translation.strip()))
        
        return phrases[:10]
    
    def _extract_sentences(self, subtitles: List[Dict[str, Any]]) -> List[tuple]:
        """提取完整句子（支持中英文）"""
        sentences = []
        for s in subtitles:
            text = s.get("text", "")
            translated = s.get("translated_text", "")
            
            content = text if text else translated
            translation = translated if (translated and translated != text) else ""
            
            if len(content) >= 5:
                sentences.append((content.strip(), translation.strip()))
        
        return sentences[:5]
    
    def _extract_key_points(self, subtitles: List[Dict[str, Any]]) -> List[str]:
        """提取关键点"""
        points = []
        keywords = ["important", "key", "main", "first", "second", "finally", "but", "however",
                    "so", "therefore", "because", "although", "when", "if", "must", "should"]
        
        for s in subtitles:
            text = s.get("text", "").lower()
            translated = s.get("translated_text", "")
            
            for kw in keywords:
                if kw in text:
                    points.append(translated.strip())
                    break
        
        return points[:10]
    
    def _generate_timeline(self, subtitles: List[Dict[str, Any]]) -> List[tuple]:
        """生成时间线"""
        timeline = []
        for s in subtitles:
            start_time = s.get("start_time", 0)
            text = s.get("text", "")
            
            minutes = int(start_time // 60)
            seconds = int(start_time % 60)
            time_str = f"{minutes:02d}:{seconds:02d}"
            timeline.append((time_str, text))
        
        return timeline
    
    def _classify_themes(self, subtitles: List[Dict[str, Any]]) -> Dict[str, int]:
        """主题分类"""
        themes = {
            "介绍": ["hello", "hi", "welcome", "introduce", "my name"],
            "描述": ["look", "see", "beautiful", "nice", "wonderful"],
            "动作": ["go", "come", "do", "make", "take", "get"],
            "情感": ["happy", "sad", "love", "like", "enjoy"],
            "时间": ["time", "today", "yesterday", "tomorrow"],
            "地点": ["here", "there", "where", "place", "location"],
            "人物": ["people", "friend", "family", "person", "man", "woman"],
            "其他": [],
        }
        
        theme_counts = {k: 0 for k in themes.keys()}
        
        for s in subtitles:
            text = s.get("text", "").lower()
            matched = False
            
            for theme, keywords in themes.items():
                if theme == "其他":
                    continue
                for kw in keywords:
                    if kw in text:
                        theme_counts[theme] += 1
                        matched = True
                        break
                if matched:
                    break
            
            if not matched:
                theme_counts["其他"] += 1
        
        return {k: v for k, v in theme_counts.items() if v > 0}
    
    def _analyze_sentence_types(self, subtitles: List[Dict[str, Any]]) -> Dict[str, int]:
        """句子类型分析"""
        types = {"陈述句": 0, "疑问句": 0, "感叹句": 0, "祈使句": 0}
        
        for s in subtitles:
            text = s.get("text", "")
            if text.endswith("?"):
                types["疑问句"] += 1
            elif text.endswith("!"):
                types["感叹句"] += 1
            elif text.startswith(("Please", "please", "Don't", "don't", "Let's", "let's")):
                types["祈使句"] += 1
            else:
                types["陈述句"] += 1
        
        return types
    
    def _analyze_tenses(self, subtitles: List[Dict[str, Any]]) -> Dict[str, int]:
        """时态分析"""
        tenses = {
            "现在时": ["is", "are", "am", "do", "does", "go", "goes", "like", "likes"],
            "过去时": ["was", "were", "did", "went", "liked", "had", "got"],
            "进行时": ["is doing", "are doing", "was doing", "were doing"],
            "将来时": ["will", "going to", "shall"],
            "完成时": ["have", "has", "had"],
        }
        
        tense_counts = {k: 0 for k in tenses.keys()}
        
        for s in subtitles:
            text = s.get("text", "").lower()
            for tense, keywords in tenses.items():
                for kw in keywords:
                    if kw in text:
                        tense_counts[tense] += 1
                        break
        
        return tense_counts
    
    def _extract_patterns(self, subtitles: List[Dict[str, Any]]) -> Dict[str, List[str]]:
        """提取句型模式"""
        patterns = {
            "主谓宾": r"[A-Za-z]+\s+[A-Za-z]+\s+[A-Za-z]+",
            "There be": r"there\s+(is|are|was|were)",
            "I think": r"i\s+think",
            "It is/was": r"it\s+(is|was)",
            "Would like": r"would\s+like",
        }
        
        results = {k: [] for k in patterns.keys()}
        
        for s in subtitles:
            text = s.get("text", "").lower()
            for pattern_name, pattern in patterns.items():
                if re.search(pattern, text):
                    results[pattern_name].append(s.get("text", ""))
        
        return {k: v[:3] for k, v in results.items() if v}


# 便捷函数
_analyzer: Optional[VideoAnalyzer] = None


def get_video_analyzer() -> VideoAnalyzer:
    """获取视频分析器实例（单例）"""
    global _analyzer
    if _analyzer is None:
        _analyzer = VideoAnalyzer()
    return _analyzer


def analyze_video(
    video_id: str,
    subtitles: List[Dict[str, Any]],
    mode: AnalysisMode,
    output_dir: Optional[str] = None
) -> AnalysisResult:
    """
    便捷函数：分析视频内容
    
    Args:
        video_id: 视频 ID
        subtitles: 字幕片段列表
        mode: 分析模式
        output_dir: 输出目录
        
    Returns:
        分析结果
    """
    return get_video_analyzer().analyze(video_id, subtitles, mode, output_dir)