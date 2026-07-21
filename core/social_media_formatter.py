"""
社交媒体文案格式化模块

将分析报告数据转化为自然流畅、可直接发布的社交媒体文案。

功能特性：
    1. 支持多种社交媒体风格（小红书、微博、知乎）
    2. 将机械化列表转为叙述性段落
    3. 添加emoji、话题标签等社交媒体元素
    4. 输出可直接复制发布的txt文件
"""

import os
from typing import Optional, List, Dict, Any
from dataclasses import dataclass
from enum import StrEnum, auto

from utils.logger import get_crawler_logger
from core.expression_knowledge import get_knowledge_base

logger = get_crawler_logger()
knowledge_base = get_knowledge_base()


class SocialStyle(StrEnum):
    """
    社交媒体风格枚举
    """
    XIAOHONGSHU = auto()
    WEIBO = auto()
    ZHIHU = auto()
    
    @classmethod
    def from_string(cls, style_str: str) -> 'SocialStyle':
        """从字符串转换为风格"""
        style_map = {
            "小红书": cls.XIAOHONGSHU,
            "微博": cls.WEIBO,
            "知乎": cls.ZHIHU,
        }
        return style_map.get(style_str, cls.XIAOHONGSHU)
    
    @property
    def display_name(self) -> str:
        """显示名称"""
        display_map = {
            self.XIAOHONGSHU: "小红书",
            self.WEIBO: "微博",
            self.ZHIHU: "知乎",
        }
        return display_map[self]


@dataclass
class SocialContent:
    """
    社交媒体文案数据类
    """
    video_id: str
    style: SocialStyle
    content: str
    file_path: Optional[str] = None
    success: bool = False


class SocialMediaFormatter:
    """
    社交媒体文案格式化器
    
    将分析报告转化为自然流畅的社交媒体文案。
    """
    
    def __init__(self) -> None:
        """初始化格式化器"""
        logger.info("社交媒体文案格式化器初始化完成")
    
    def format(
        self,
        video_id: str,
        subtitles: List[Dict[str, Any]],
        analysis_mode: str,
        output_dir: Optional[str] = None,
        style: SocialStyle = SocialStyle.XIAOHONGSHU
    ) -> SocialContent:
        """
        格式化分析报告为社交媒体文案
        
        Args:
            video_id: 视频 ID
            subtitles: 字幕数据
            analysis_mode: 分析模式名称
            output_dir: 输出目录
            style: 社交媒体风格
            
        Returns:
            格式化后的文案内容
        """
        try:
            content = self._generate_content(subtitles, analysis_mode, style)
            
            if output_dir:
                file_path = self._save_content(video_id, style, content, output_dir)
                return SocialContent(
                    video_id=video_id,
                    style=style,
                    content=content,
                    file_path=file_path,
                    success=True
                )
            else:
                return SocialContent(
                    video_id=video_id,
                    style=style,
                    content=content,
                    success=True
                )
                
        except Exception as e:
            logger.error(f"社交媒体文案生成失败: {e}")
            return SocialContent(
                video_id=video_id,
                style=style,
                content="",
                success=False
            )
    
    def _generate_content(
        self,
        subtitles: List[Dict[str, Any]],
        analysis_mode: str,
        style: SocialStyle
    ) -> str:
        """
        根据风格生成文案内容
        
        Args:
            subtitles: 字幕数据
            analysis_mode: 分析模式名称
            style: 社交媒体风格
            
        Returns:
            文案内容
        """
        if style == SocialStyle.XIAOHONGSHU:
            return self._format_xiaohongshu(subtitles, analysis_mode)
        elif style == SocialStyle.WEIBO:
            return self._format_weibo(subtitles, analysis_mode)
        elif style == SocialStyle.ZHIHU:
            return self._format_zhihu(subtitles, analysis_mode)
        else:
            return self._format_xiaohongshu(subtitles, analysis_mode)
    
    def _format_xiaohongshu(
        self,
        subtitles: List[Dict[str, Any]],
        analysis_mode: str
    ) -> str:
        """
        小红书风格格式化
        
        特点：emoji丰富、分段清晰、种草语气、使用话题标签、深度分析
        """
        parts = []
        
        parts.append("🌍 挖到宝藏英语学习视频啦！")
        parts.append("")
        
        parts.append("最近看了一个超棒的英语视频，里面有好多实用表达想分享给大家！")
        parts.append("")
        
        oral_markers = ["alright", "well", "so", "yeah", "you know", "I mean",
                        "kind of", "sort of", "pretty much", "cool", "nice", "guys"]
        
        all_text = " ".join([s.get("text", "").lower() for s in subtitles if s.get("text")])
        
        found_markers = []
        for marker in oral_markers:
            if marker in all_text:
                count = all_text.count(marker)
                found_markers.append((marker, count))
        
        found_markers.sort(key=lambda x: x[1], reverse=True)
        
        if found_markers:
            parts.append("✨ 地道口语表达")
            parts.append("")
            
            for marker, count in found_markers[:5]:
                analysis = knowledge_base.get_analysis(marker)
                
                parts.append(f"「{marker}」")
                if analysis:
                    parts.append(f"   📖 含义：{analysis['meaning']}")
                parts.append("")
                
                for s in subtitles:
                    if marker in s.get("text", "").lower():
                        parts.append(f"   📝 视频例句: {s.get('text', '')}")
                        parts.append(f"   💬 翻译: {s.get('translated_text', '')}")
                        parts.append("")
                        break
                
                if analysis:
                    keys = ["chinese_difference", "tone_analysis", "learning_pitfall", 
                            "scene_expansion", "grammar_note"]
                    for key in keys:
                        if analysis.get(key):
                            parts.append(f"   💡 {analysis[key]}")
                            parts.append("")
            
            parts.append("")
        
        long_sentences = []
        for s in subtitles:
            text = s.get("text", "")
            word_count = len(text.split())
            if word_count >= 8:
                long_sentences.append((text, s.get("translated_text", ""), word_count))
        
        long_sentences.sort(key=lambda x: x[2], reverse=True)
        
        if long_sentences:
            parts.append("📚 长难句拆解")
            parts.append("")
            
            for sentence, translated, word_count in long_sentences[:3]:
                parts.append(f"🔍 这句话有{word_count}个词，结构很经典：")
                parts.append(f"   {sentence}")
                parts.append(f"   ↓")
                parts.append(f"   {translated}")
                parts.append("")
                parts.append(f"   💡 结构分析：这是一个包含多个从句的复合句，主句结构清晰，从句部分丰富了表达的层次。在口语中，这样的长句其实很常见，关键在于理解主干结构，然后逐步分析修饰成分。")
                parts.append("")
        
        parts.append("🎯 学习心得")
        parts.append("")
        
        parts.append("这个视频语速适中，内容有趣，很适合用来练习听力和口语！")
        parts.append("里面的表达都很生活化，学会了就能直接用在日常对话中～")
        parts.append("")
        
        parts.append("建议大家多看几遍，第一遍盲听，第二遍对照字幕，第三遍跟读！")
        parts.append("")
        
        parts.append("💪 一起加油吧！英语学习贵在坚持！")
        parts.append("")
        
        parts.append("#英语学习 #英语口语 #英语听力 #学习打卡 #英语启蒙 #每日英语 #英语笔记")
        
        return "\n".join(parts)
    
    def _format_weibo(
        self,
        subtitles: List[Dict[str, Any]],
        analysis_mode: str
    ) -> str:
        """
        微博风格格式化
        
        特点：简短有力、节奏快、使用话题标签、互动性强、深度分析
        """
        parts = []
        
        parts.append("📢 英语学习打卡！今天发现一个超实用的视频！")
        parts.append("")
        
        all_text = " ".join([s.get("text", "") for s in subtitles if s.get("text")])
        all_translated = " ".join([s.get("translated_text", "") for s in subtitles if s.get("translated_text")])
        
        parts.append("🌟 重点词汇")
        parts.append("")
        
        oral_markers = ["alright", "cool", "pretty much", "guys", "thing"]
        found_markers = []
        
        for marker in oral_markers:
            if marker in all_text.lower():
                count = all_text.lower().count(marker)
                found_markers.append((marker, count))
        
        found_markers.sort(key=lambda x: x[1], reverse=True)
        
        for marker, count in found_markers[:5]:
            analysis = knowledge_base.get_analysis(marker)
            
            parts.append(f"👉 {marker}")
            if analysis:
                parts.append(f"   📖 {analysis['meaning']}")
            
            for s in subtitles:
                if marker in s.get("text", "").lower():
                    parts.append(f"   📝 {s.get('text', '')}")
                    parts.append(f"   💬 {s.get('translated_text', '')}")
                    parts.append("")
                    break
            
            if analysis:
                for key in ["chinese_difference", "tone_analysis", "learning_pitfall"]:
                    if analysis.get(key):
                        parts.append(f"   💡 {analysis[key]}")
                        parts.append("")
        
        parts.append("📝 长难句")
        parts.append("")
        
        long_sentences = []
        for s in subtitles:
            text = s.get("text", "")
            word_count = len(text.split())
            if word_count >= 8:
                long_sentences.append((text, s.get("translated_text", "")))
        
        for sentence, translated in long_sentences[:2]:
            parts.append(f"💡 {sentence}")
            parts.append(f"   ↓")
            parts.append(f"   {translated}")
            parts.append("")
            parts.append(f"   📚 结构分析：这是一个包含多个从句的复合句，主句结构清晰，从句部分丰富了表达的层次。")
            parts.append("")
        
        parts.append("💬 你们平时怎么练习英语口语？")
        parts.append("")
        
        parts.append("#英语学习 #英语口语 #英语打卡 #学习日常 #每日英语")
        
        return "\n".join(parts)
    
    def _format_zhihu(
        self,
        subtitles: List[Dict[str, Any]],
        analysis_mode: str
    ) -> str:
        """
        知乎风格格式化
        
        特点：干货满满、结构清晰、专业分析、深度解读、口语逻辑总结
        """
        parts = []
        
        parts.append("## 从一个英语视频中学到的实用表达")
        parts.append("")
        
        parts.append("最近看了一个英语视频，内容很有意思，想和大家分享一下从中可以学到的实用表达。")
        parts.append("")
        
        all_text = " ".join([s.get("text", "") for s in subtitles if s.get("text")])
        
        parts.append("### 一、高频口语词汇深度解析")
        parts.append("")
        
        oral_markers = ["alright", "cool", "pretty much", "guys", "thing"]
        found_markers = []
        
        for marker in oral_markers:
            if marker in all_text.lower():
                count = all_text.lower().count(marker)
                found_markers.append((marker, count))
        
        found_markers.sort(key=lambda x: x[1], reverse=True)
        
        for marker, count in found_markers[:5]:
            analysis = knowledge_base.get_analysis(marker)
            
            parts.append(f"**{marker}**")
            parts.append("")
            
            if analysis:
                parts.append(f"**含义**：{analysis['meaning']}")
                parts.append("")
            
            parts.append(f"这个词在视频中出现了{count}次，是英语口语中非常常见的表达。")
            parts.append("")
            
            for s in subtitles:
                if marker in s.get("text", "").lower():
                    parts.append(f"**视频例句**：{s.get('text', '')}")
                    parts.append(f"**翻译**：{s.get('translated_text', '')}")
                    parts.append("")
                    break
            
            if analysis:
                for key, label in [("chinese_difference", "中英表达差异"), 
                                   ("tone_analysis", "语气辨析"), 
                                   ("learning_pitfall", "学习踩坑"),
                                   ("scene_expansion", "场景拓展"),
                                   ("grammar_note", "语法理解")]:
                    if analysis.get(key):
                        parts.append(f"**{label}**：{analysis[key]}")
                        parts.append("")
        
        parts.append("### 二、长难句分析")
        parts.append("")
        
        long_sentences = []
        for s in subtitles:
            text = s.get("text", "")
            word_count = len(text.split())
            if word_count >= 8:
                long_sentences.append((text, s.get("translated_text", ""), word_count))
        
        long_sentences.sort(key=lambda x: x[2], reverse=True)
        
        for sentence, translated, word_count in long_sentences[:3]:
            parts.append(f"**原句**：{sentence}")
            parts.append(f"**词数**：{word_count}")
            parts.append(f"**翻译**：{translated}")
            parts.append("")
            parts.append(f"**结构分析**：这是一个包含多个从句的复合句，主句结构清晰，从句部分丰富了表达的层次。在口语中，这样的长句其实很常见，关键在于理解主干结构，然后逐步分析修饰成分。")
            parts.append("")
        
        parts.append("### 三、口语逻辑总结")
        parts.append("")
        
        parts.append("通过分析这个视频，我发现了英语口语和书面英语的一些重要区别：")
        parts.append("")
        
        parts.append("1. **词汇选择**：口语中大量使用简单词汇（如 cool、guys、thing），而书面英语会使用更精确的词汇（如 impressive、people、matter）。")
        parts.append("")
        
        parts.append("2. **程度表达**：口语中倾向于重复使用 really、so 来加强语气（如 really, really, really long），而书面英语会使用程度副词或比较级。")
        parts.append("")
        
        parts.append("3. **填充词使用**：口语中大量使用 you know、I mean、kind of 等填充词来连接话语，使表达更自然流畅，这在书面英语中是很少见的。")
        parts.append("")
        
        parts.append("4. **句式结构**：口语中的句子结构相对松散，常常出现省略、倒装等现象，而书面英语更注重语法的完整性和严谨性。")
        parts.append("")
        
        parts.append("5. **文化差异**：英语口语中的一些表达（如 guys 作为中性称呼）反映了英语国家的文化习惯，在中文中没有完全对应的表达，需要我们特别注意。")
        parts.append("")
        
        parts.append("### 四、学习建议")
        parts.append("")
        
        parts.append("1. **盲听训练**：第一遍不看字幕，尝试理解大意")
        parts.append("2. **精听跟读**：对照字幕逐句跟读，模仿发音和语调")
        parts.append("3. **笔记整理**：将学到的表达整理到笔记本中，定期复习")
        parts.append("4. **实战应用**：尝试在日常对话中使用学到的表达")
        parts.append("")
        
        parts.append("### 五、总结")
        parts.append("")
        
        parts.append("这个视频虽然简短，但包含了很多实用的英语口语表达。通过仔细分析和反复练习，相信大家都能从中有所收获。")
        parts.append("")
        
        parts.append("英语学习是一个长期的过程，贵在坚持。祝大家学习顺利！")
        
        return "\n".join(parts)
    
    def _save_content(
        self,
        video_id: str,
        style: SocialStyle,
        content: str,
        output_dir: str
    ) -> str:
        """
        保存文案内容为txt文件
        
        Args:
            video_id: 视频 ID
            style: 社交媒体风格
            content: 文案内容
            output_dir: 输出目录
            
        Returns:
            文件路径
        """
        os.makedirs(output_dir, exist_ok=True)
        filename = f"{video_id}_social_{style.value}.txt"
        filepath = os.path.join(output_dir, filename)
        
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(content)
        
        logger.info(f"社交媒体文案已保存: {filepath}")
        return filepath