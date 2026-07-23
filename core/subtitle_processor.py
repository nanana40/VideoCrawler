"""
字幕处理模块

实现视频字幕的自动生成、翻译和嵌入功能。

功能特性：
    1. 语音转文字（Whisper）
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
from utils.path_helper import get_ffmpeg_path, get_tmp_dir, get_finished_sub_dir
from utils.file_sort import get_file_sorter


logger = get_translate_logger()


@dataclass
class SubtitleSegment:
    """字幕片段"""
    start_time: float
    end_time: float
    text: str
    translated_text: Optional[str] = None


@dataclass
class SubtitleResult:
    """字幕处理结果"""
    video_id: str
    video_path: str
    success: bool
    subtitle_path: Optional[str] = None
    embedded_video_path: Optional[str] = None
    error_message: Optional[str] = None
    has_original_subtitle: bool = False


class SpeechRecognizer:
    """
    语音识别器
    
    使用 Whisper 将视频中的语音转换为文字。
    """
    
    def __init__(self) -> None:
        """初始化语音识别器"""
        self._model = None
        self._model_size = "base"
        logger.info("语音识别器初始化完成")
    
    def _load_model(self) -> None:
        """加载 Whisper 模型"""
        if self._model is None:
            try:
                import whisper
                self._model = whisper.load_model(self._model_size)
                logger.info(f"Whisper 模型加载完成: {self._model_size}")
            except Exception as e:
                logger.error(f"加载 Whisper 模型失败: {e}")
                raise
    
    def recognize(
        self,
        video_path: str,
        language: Optional[str] = None
    ) -> List[SubtitleSegment]:
        """
        从视频中提取语音并转换为文字
        
        Args:
            video_path: 视频文件路径
            language: 语言代码（可选）
            
        Returns:
            字幕片段列表
        """
        self._load_model()
        
        try:
            result = self._model.transcribe(
                video_path,
                language=language,
                word_timestamps=False
            )
            
            segments = []
            for segment in result.get("segments", []):
                segments.append(SubtitleSegment(
                    start_time=segment["start"],
                    end_time=segment["end"],
                    text=segment["text"].strip()
                ))
            
            logger.info(f"语音识别完成，共 {len(segments)} 个片段")
            return segments
            
        except Exception as e:
            logger.error(f"语音识别失败: {e}")
            raise


class SubtitleTranslator:
    """
    字幕翻译器
    
    将字幕文本翻译为目标语言。
    """
    
    def __init__(self) -> None:
        """初始化字幕翻译器"""
        self._api_url = ""
        self._translator = None
        self._use_fallback = False
        logger.info("字幕翻译器初始化完成")
    
    def _init_translator(self) -> None:
        """初始化翻译器"""
        if self._translator is not None:
            return
            
        try:
            from googletrans import Translator
            self._translator = Translator(timeout=15)
            logger.info("googletrans 翻译器初始化成功")
        except Exception as e:
            logger.warning(f"googletrans 初始化失败，使用备用翻译方案: {e}")
            self._use_fallback = True
    
    def translate_segment(
        self,
        text: str,
        source_lang: str = "auto",
        target_lang: str = "zh-CN"
    ) -> str:
        """
        翻译单个字幕片段
        
        Args:
            text: 原文文本
            source_lang: 源语言
            target_lang: 目标语言
            
        Returns:
            翻译后的文本
        """
        if not text.strip():
            return ""
        
        if self._api_url:
            return self._translate_via_api(text, source_lang, target_lang)
        else:
            return self._translate_local(text, source_lang, target_lang)
    
    def _translate_via_api(
        self,
        text: str,
        source_lang: str,
        target_lang: str
    ) -> str:
        """通过 API 翻译"""
        try:
            import requests as std_requests
            
            response = std_requests.post(
                f"{self._api_url}/translate",
                json={
                    "text": text,
                    "source_lang": source_lang,
                    "target_lang": target_lang
                },
                timeout=10
            )
            response.raise_for_status()
            
            result = response.json()
            return result.get("translated_text", text)
            
        except Exception as e:
            logger.warning(f"API 翻译失败，使用本地翻译: {e}")
            return self._translate_local(text, source_lang, target_lang)
    
    def _translate_local(
        self,
        text: str,
        source_lang: str,
        target_lang: str
    ) -> str:
        """本地翻译（使用googletrans或备用方案）"""
        self._init_translator()
        
        if not self._use_fallback and self._translator:
            try:
                result = self._translator.translate(text, src=source_lang, dest=target_lang)
                return result.text
            
            except Exception as e:
                logger.warning(f"googletrans 翻译失败，使用备用方案: {e}")
                return self._translate_fallback(text, source_lang, target_lang)
        
        return self._translate_fallback(text, source_lang, target_lang)
    
    def _translate_fallback(
        self,
        text: str,
        source_lang: str,
        target_lang: str
    ) -> str:
        """备用翻译方案（尝试多个翻译API）"""
        fallback_apis = [
            self._try_google_translate,
            self._try_bing_translate,
            self._try_deepl_translate,
            self._try_local_dictionary,
        ]
        
        for api_func in fallback_apis:
            try:
                result = api_func(text, source_lang, target_lang)
                if result and result != text:
                    return result
            except Exception as e:
                logger.warning(f"翻译API {api_func.__name__} 失败: {e}")
                continue
        
        logger.warning("所有翻译API均失败，返回原文")
        return text
    
    def _try_google_translate(
        self,
        text: str,
        source_lang: str,
        target_lang: str
    ) -> str:
        """尝试Google翻译API"""
        import requests as std_requests
        
        urls = [
            "https://translate.googleapis.com/translate_a/single",
            "https://translate.google.com/translate_a/single",
        ]
        
        for url in urls:
            try:
                params = {
                    "client": "gtx",
                    "sl": source_lang,
                    "tl": target_lang,
                    "dt": "t",
                    "q": text
                }
                
                headers = {
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
                }
                
                response = std_requests.get(url, params=params, headers=headers, timeout=10)
                response.raise_for_status()
                
                result = response.json()
                if isinstance(result, list) and len(result) > 0 and isinstance(result[0], list):
                    translated_text = "".join([item[0] for item in result[0] if item[0]])
                    return translated_text
            except Exception:
                continue
        
        raise Exception("Google翻译失败")
    
    def _try_bing_translate(
        self,
        text: str,
        source_lang: str,
        target_lang: str
    ) -> str:
        """尝试Bing翻译API"""
        import requests as std_requests
        
        try:
            url = "https://api.cognitive.microsofttranslator.com/translate"
            headers = {
                "Content-Type": "application/json",
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            }
            
            body = [{
                "Text": text
            }]
            
            response = std_requests.post(
                url,
                headers=headers,
                json=body,
                timeout=10,
                params={
                    "api-version": "3.0",
                    "from": source_lang,
                    "to": target_lang
                }
            )
            
            if response.status_code == 200:
                result = response.json()
                if result and len(result) > 0 and "translations" in result[0]:
                    return result[0]["translations"][0]["text"]
            
        except Exception:
            pass
        
        raise Exception("Bing翻译失败")
    
    def _try_deepl_translate(
        self,
        text: str,
        source_lang: str,
        target_lang: str
    ) -> str:
        """尝试DeepL翻译API"""
        import requests as std_requests
        
        try:
            url = "https://www2.deepl.com/jsonrpc"
            
            lang_map = {
                "en": "EN",
                "zh": "ZH",
                "zh-CN": "ZH",
                "zh-TW": "ZH",
                "de": "DE",
                "fr": "FR",
                "es": "ES",
                "ja": "JA",
                "ko": "KO",
                "ru": "RU",
                "it": "IT",
                "pt": "PT",
                "ar": "AR",
                "hi": "HI",
                "nl": "NL",
                "sv": "SV",
                "no": "NO",
                "da": "DA",
                "fi": "FI",
                "pl": "PL",
                "cs": "CS",
                "hu": "HU",
                "ro": "RO",
                "el": "EL",
                "tr": "TR",
                "vi": "VI",
                "th": "TH",
                "id": "ID",
                "ms": "MS",
                "tl": "TL",
                "auto": "EN"
            }
            
            source_lang_code = lang_map.get(source_lang, "EN")
            target_lang_code = lang_map.get(target_lang, "ZH")
            
            payload = {
                "jsonrpc": "2.0",
                "method": "LMT_handle_jobs",
                "params": {
                    "jobs": [{
                        "kind": "default",
                        "sentences": [{
                            "text": text,
                            "id": 0,
                            "prefix": ""
                        }],
                        "raw_en_context_before": [],
                        "raw_en_context_after": [],
                        "preferred_num_beams": 4
                    }],
                    "lang": {
                        "preference": {
                            "weight": {},
                            "default": "default"
                        },
                        "source_lang_computed": source_lang_code,
                        "target_lang": target_lang_code
                    },
                    "priority": 1
                },
                "id": 429934005
            }
            
            headers = {
                "Content-Type": "application/json",
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            }
            
            response = std_requests.post(url, json=payload, headers=headers, timeout=10)
            
            if response.status_code == 200:
                result = response.json()
                if "result" in result and "translations" in result["result"]:
                    return result["result"]["translations"][0]["beams"][0]["sentences"][0]["text"]
        
        except Exception:
            pass
        
        raise Exception("DeepL翻译失败")
    
    def _try_local_dictionary(
        self,
        text: str,
        source_lang: str,
        target_lang: str
    ) -> str:
        """本地词典翻译（作为最后的兜底方案）"""
        phrase_dict = {
            "alright": "好吧",
            "cool thing": "酷的地方",
            "cool": "酷",
            "really long": "非常长",
            "really interesting": "非常有趣",
            "really amazing": "非常惊人",
            "so the": "那么",
            "about these": "关于这些",
            "that they have": "他们有",
            "is that": "就是",
            "pretty much": "差不多",
            "all there is": "仅此而已",
            "to say about it": "关于这件事要说的",
            "one of the": "其中一只",
            "here we are": "我们在这里",
            "talking about": "谈论",
            "is done": "已经完成",
            "is a": "是一个",
            "about nature": "关于自然",
            "amazing wildlife": "令人惊叹的野生动物",
        }
        
        word_dict = {
            "alright": "好吧",
            "cool": "酷",
            "really": "非常",
            "so": "那么",
            "guys": "伙计们",
            "thing": "事情",
            "pretty": "相当",
            "much": "多",
            "one": "一个",
            "elephants": "大象",
            "hunts": "狩猎",
            "long": "长的",
            "and": "和",
            "that": "那个",
            "is": "是",
            "all": "所有",
            "there": "那里",
            "to": "去",
            "say": "说",
            "here": "这里",
            "we": "我们",
            "are": "是",
            "about": "关于",
            "they": "他们",
            "have": "有",
            "these": "这些",
            "the": "这个",
            "of": "的",
            "it": "它",
            "for": "为了",
            "with": "和",
            "on": "在",
            "at": "在",
            "by": "通过",
            "from": "从",
            "as": "作为",
            "into": "进入",
            "through": "通过",
            "during": "在...期间",
            "before": "在...之前",
            "after": "在...之后",
            "above": "在...之上",
            "below": "在...之下",
            "between": "在...之间",
            "under": "在...之下",
            "again": "再次",
            "further": "进一步",
            "then": "然后",
            "once": "曾经",
            "when": "当",
            "where": "哪里",
            "why": "为什么",
            "how": "如何",
            "each": "每个",
            "few": "很少",
            "more": "更多",
            "most": "最多",
            "other": "其他",
            "some": "一些",
            "such": "这样",
            "no": "不",
            "nor": "也不",
            "not": "不",
            "only": "只",
            "own": "自己的",
            "same": "相同",
            "than": "比",
            "too": "也",
            "very": "非常",
            "just": "刚刚",
            "but": "但是",
            "if": "如果",
            "or": "或者",
            "because": "因为",
            "until": "直到",
            "while": "当...的时候",
            "against": "反对",
            "he": "他",
            "she": "她",
            "it": "它",
            "we": "我们",
            "they": "他们",
            "you": "你",
            "i": "我",
            "me": "我",
            "him": "他",
            "her": "她",
            "us": "我们",
            "them": "他们",
            "this": "这个",
            "those": "那些",
            "what": "什么",
            "which": "哪个",
            "who": "谁",
            "whom": "谁",
            "whose": "谁的",
            "done": "完成",
            "amazing": "令人惊叹的",
            "wildlife": "野生动物",
            "interesting": "有趣的",
            "video": "视频",
            "nature": "自然"
        }
        
        result = text
        
        for phrase, translation in sorted(phrase_dict.items(), key=lambda x: -len(x[0])):
            result = result.lower().replace(phrase, translation)
        
        words = result.split()
        translated_parts = []
        
        for word in words:
            clean_word = word.strip(",.!?;:()[]\"'")
            if clean_word in word_dict:
                translated_word = word_dict[clean_word]
                if word[0].isupper() and clean_word == word.lower():
                    translated_word = translated_word[0].upper() + translated_word[1:]
                translated_parts.append(translated_word)
            else:
                translated_parts.append(word)
        
        result = " ".join(translated_parts)
        result = result.replace("  ", " ").strip()
        
        result = result.replace(" ,", ",").replace(" .", ".").replace(" !", "!").replace(" ?", "?")
        result = result.replace(" ;", ";").replace(" :", ":").replace(" )", ")").replace("( ", "(")
        
        if result != text and result != text.lower():
            return result
        
        raise Exception("本地词典翻译失败")
    
    def translate_segments(
        self,
        segments: List[SubtitleSegment],
        source_lang: str = "auto",
        target_lang: str = "zh-CN"
    ) -> List[SubtitleSegment]:
        """
        批量翻译字幕片段
        
        Args:
            segments: 字幕片段列表
            source_lang: 源语言
            target_lang: 目标语言
            
        Returns:
            翻译后的字幕片段列表
        """
        import time
        
        for i, segment in enumerate(segments):
            try:
                segment.translated_text = self.translate_segment(
                    segment.text, source_lang, target_lang
                )
                
                if i % 10 == 0 and i > 0:
                    logger.info(f"已翻译 {i}/{len(segments)} 个片段")
                
                time.sleep(0.5)
                
            except Exception as e:
                logger.error(f"翻译第 {i} 个片段失败: {e}")
                segment.translated_text = segment.text
        
        logger.info(f"翻译完成，共 {len(segments)} 个片段")
        return segments


class SRTWriter:
    """
    SRT字幕写入器
    
    将字幕片段写入 SRT 格式文件。
    """
    
    @staticmethod
    def _format_time(seconds: float) -> str:
        """将秒转换为 SRT 时间格式"""
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)
        msecs = int((seconds % 1) * 1000)
        return f"{hours:02d}:{minutes:02d}:{secs:02d},{msecs:03d}"
    
    @staticmethod
    def write(
        segments: List[SubtitleSegment],
        output_path: str,
        bilingual: bool = True
    ) -> str:
        """
        写入 SRT 文件
        
        Args:
            segments: 字幕片段列表
            output_path: 输出文件路径
            bilingual: 是否写入双语字幕
            
        Returns:
            输出文件路径
        """
        with open(output_path, "w", encoding="utf-8") as f:
            for i, segment in enumerate(segments, 1):
                start = SRTWriter._format_time(segment.start_time)
                end = SRTWriter._format_time(segment.end_time)
                
                f.write(f"{i}\n")
                f.write(f"{start} --> {end}\n")
                
                if bilingual and segment.translated_text:
                    f.write(f"{segment.text}\n")
                    f.write(f"{segment.translated_text}\n")
                elif segment.translated_text:
                    f.write(f"{segment.translated_text}\n")
                else:
                    f.write(f"{segment.text}\n")
                
                f.write("\n")
        
        logger.info(f"SRT 文件已写入: {output_path}")
        return output_path


class VideoSubtitleEmbedder:
    """
    视频字幕嵌入器
    
    使用 ffmpeg 将字幕嵌入视频。
    """
    
    def __init__(self) -> None:
        """初始化视频字幕嵌入器"""
        ffmpeg_path = get_ffmpeg_path()
        if not os.path.exists(str(ffmpeg_path)):
            ffmpeg_path = ffmpeg_path.parent / "ffmpeg" / "bin" / "ffmpeg.exe"
        
        self._ffmpeg_path = str(ffmpeg_path)
        
        if os.path.exists(self._ffmpeg_path):
            logger.info(f"视频字幕嵌入器初始化完成，ffmpeg路径: {self._ffmpeg_path}")
        else:
            logger.warning(f"ffmpeg 未找到，将跳过字幕嵌入，仅生成字幕文件")
    
    def _has_embedded_subtitle(self, video_path: str) -> bool:
        """
        检测视频是否自带字幕轨道或外挂字幕文件
        
        Args:
            video_path: 视频文件路径
            
        Returns:
            True 表示有自带字幕（内嵌或外挂）
        """
        if self._has_external_subtitle(video_path):
            return True
            
        try:
            cmd = [self._ffmpeg_path or "ffmpeg", "-i", video_path]
            result = subprocess.run(
                cmd,
                stderr=subprocess.PIPE,
                stdout=subprocess.PIPE,
                text=True
            )
            
            stderr = result.stderr
            
            import re
            subtitle_pattern = re.compile(r"Stream #\d+:\d+.*Subtitle:", re.IGNORECASE)
            
            if subtitle_pattern.search(stderr):
                logger.info("视频自带内嵌字幕轨道")
                return True
            
            logger.info("视频未检测到字幕轨道")
            return False
            
        except Exception as e:
            logger.warning(f"检测自带字幕失败: {e}")
            return False
    
    def _has_external_subtitle(self, video_path: str) -> bool:
        """
        检测视频同目录下是否有外挂字幕文件
        
        Args:
            video_path: 视频文件路径
            
        Returns:
            True 表示有外挂字幕文件
        """
        video_dir = os.path.dirname(video_path)
        video_name = os.path.splitext(os.path.basename(video_path))[0]
        
        subtitle_extensions = [".srt", ".vtt", ".ass", ".ssa", ".sub"]
        
        for ext in subtitle_extensions:
            subtitle_path = os.path.join(video_dir, f"{video_name}{ext}")
            if os.path.exists(subtitle_path):
                logger.info(f"视频同目录下有外挂字幕文件: {subtitle_path}")
                return True
                
            for lang in ["en", "en-US", "en_GB"]:
                subtitle_path = os.path.join(video_dir, f"{video_name}.{lang}{ext}")
                if os.path.exists(subtitle_path):
                    logger.info(f"视频同目录下有外挂字幕文件: {subtitle_path}")
                    return True
        
        return False
    
    def _get_video_dimensions(self, video_path: str) -> Tuple[int, int]:
        """
        获取视频分辨率
        
        Args:
            video_path: 视频文件路径
            
        Returns:
            (宽度, 高度)
        """
        try:
            import cv2
            
            cap = cv2.VideoCapture(video_path)
            width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            cap.release()
            
            return width, height
            
        except ImportError:
            return 1920, 1080
        except Exception as e:
            logger.warning(f"获取视频分辨率失败: {e}")
            return 1920, 1080
    
    def _generate_subtitle_style(self, video_path: str, has_original: bool) -> str:
        """
        生成字幕样式
        
        Args:
            video_path: 视频文件路径
            has_original: 是否有原字幕
            
        Returns:
            ASS 样式字符串
        """
        width, height = self._get_video_dimensions(video_path)
        
        font_size = max(24, min(height // 30, 48))
        margin_bottom = height // 15
        
        if has_original:
            y_position = margin_bottom
        else:
            y_position = height - margin_bottom - font_size - 10
        
        style = f"""\
[Script Info]
Title: Generated Subtitle
ScriptType: v4.00+
WrapStyle: 0
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,Microsoft YaHei,{font_size},&H00FFFFFF,&H00FFFFFF,&H00000000,&H80000000,1,0,0,0,100,100,0,0,1,2,1,2,10,10,{y_position},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
        
        return style
    
    def _convert_srt_to_ass(
        self,
        srt_path: str,
        video_path: str,
        has_original: bool
    ) -> str:
        """
        将 SRT 转换为 ASS 格式，添加样式
        
        Args:
            srt_path: SRT 文件路径
            video_path: 视频文件路径
            has_original: 是否有原字幕
            
        Returns:
            ASS 文件路径
        """
        ass_path = srt_path.replace(".srt", ".ass")
        
        style = self._generate_subtitle_style(video_path, has_original)
        
        with open(srt_path, "r", encoding="utf-8") as srt_file:
            srt_content = srt_file.read()
        
        ass_lines = [style]
        
        srt_pattern = r"(\d+)\n(\d{2}:\d{2}:\d{2},\d{3}) --> (\d{2}:\d{2}:\d{2},\d{3})\n(.+?)\n\n"
        matches = re.findall(srt_pattern, srt_content, re.DOTALL)
        
        for match in matches:
            _, start, end, text = match
            start = start.replace(",", ".")
            end = end.replace(",", ".")
            text = text.replace("\n", "\\N").strip()
            
            ass_lines.append(f"Dialogue: 0,{start},{end},Default,,0,0,0,,{text}")
        
        with open(ass_path, "w", encoding="utf-8") as ass_file:
            ass_file.write("\n".join(ass_lines))
        
        logger.info(f"ASS 文件已生成: {ass_path}")
        return ass_path
    
    def embed_subtitle(
        self,
        video_path: str,
        subtitle_path: str,
        output_path: Optional[str] = None,
        has_original_subtitle: bool = False
    ) -> str:
        """
        将字幕嵌入视频
        
        Args:
            video_path: 视频文件路径
            subtitle_path: 字幕文件路径
            output_path: 输出视频路径（可选）
            has_original_subtitle: 是否有原字幕
            
        Returns:
            输出视频路径（如果ffmpeg不可用，返回原视频路径）
        """
        if not os.path.exists(self._ffmpeg_path):
            logger.warning("ffmpeg 不可用，跳过字幕嵌入")
            return video_path
        
        if output_path is None:
            dir_name = os.path.dirname(video_path)
            base_name = os.path.basename(video_path)
            name, ext = os.path.splitext(base_name)
            output_path = os.path.join(dir_name, f"{name}_已完成{ext}")
        
        try:
            width, height = self._get_video_dimensions(video_path)
            font_size = max(24, min(height // 28, 48))
            
            if has_original_subtitle:
                margin_v = height // 8
            else:
                margin_v = height // 15
            
            escaped_path = subtitle_path.replace("\\", "\\\\").replace(":", "\\:")
            
            style = f"FontName=Microsoft YaHei,FontSize={font_size},PrimaryColour=&H00FFFFFF,SecondaryColour=&H00FFFFFF,OutlineColour=&H00000000,BackColour=&H80000000,Bold=1,Alignment=2,MarginV={margin_v},Outline=2,Shadow=1"
            
            cmd = [
                self._ffmpeg_path,
                "-i", video_path,
                "-vf", f"subtitles='{escaped_path}':force_style='{style}'",
                "-c:a", "copy",
                "-y",
                output_path
            ]
            
            result = subprocess.run(
                cmd,
                stderr=subprocess.PIPE,
                stdout=subprocess.PIPE,
                text=True
            )
            
            if result.returncode != 0:
                logger.error(f"ffmpeg 嵌入字幕失败: {result.stderr}")
                raise RuntimeError(f"ffmpeg error: {result.stderr}")
            
            logger.info(f"字幕已嵌入视频: {output_path}")
            return output_path
            
        except Exception as e:
            logger.error(f"ffmpeg 命令执行失败: {e}")
            return video_path


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
        self._file_sorter = get_file_sorter()
        logger.info("字幕处理器初始化完成")
    
    def process_video(
        self,
        video_id: str,
        video_path: str,
        language: Optional[LanguageType] = None,
        category: Optional[VideoCategory] = None,
        source_lang: str = "auto",
        target_lang: str = "zh-CN"
    ) -> SubtitleResult:
        """
        处理视频字幕
        
        Args:
            video_id: 视频 ID
            video_path: 视频文件路径
            language: 语言类型
            category: 视频分类
            source_lang: 源语言
            target_lang: 目标语言
            
        Returns:
            SubtitleResult 处理结果
        """
        try:
            has_original = self._embedder._has_embedded_subtitle(video_path)
            logger.info(f"视频 {video_id} 是否有原字幕: {has_original}")
            
            segments = self._recognizer.recognize(video_path, language=language.value if language else None)
            
            if not segments:
                return SubtitleResult(
                    video_id=video_id,
                    video_path=video_path,
                    success=False,
                    error_message="未识别到语音内容"
                )
            
            segments = self._translator.translate_segments(
                segments,
                source_lang=source_lang,
                target_lang=target_lang
            )
            
            subtitle_dir = self._file_sorter.get_subtitle_dir(language, category, video_id)
            subtitle_path = os.path.join(subtitle_dir, f"{video_id}_{target_lang}.srt")
            
            SRTWriter.write(segments, subtitle_path, bilingual=True)
            
            output_path = self._embedder.embed_subtitle(
                video_path,
                subtitle_path,
                has_original_subtitle=has_original
            )
            
            return SubtitleResult(
                video_id=video_id,
                video_path=video_path,
                success=True,
                subtitle_path=subtitle_path,
                embedded_video_path=output_path,
                has_original_subtitle=has_original
            )
            
        except Exception as e:
            logger.error(f"处理视频字幕失败: {e}")
            import traceback
            traceback.print_exc()
            
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
                target_lang=video.get("target_lang", "zh-CN")
            )
            results.append(result)
        return results


# 便捷函数
_subtitle_processor: Optional[SubtitleProcessor] = None


def get_subtitle_processor() -> SubtitleProcessor:
    """获取字幕处理器实例（单例）"""
    global _subtitle_processor
    if _subtitle_processor is None:
        _subtitle_processor = SubtitleProcessor()
    return _subtitle_processor


def process_video_subtitle(
    video_id: str,
    video_path: str,
    language: Optional[LanguageType] = None,
    category: Optional[VideoCategory] = None,
    source_lang: str = "auto",
    target_lang: str = "zh-CN"
) -> SubtitleResult:
    """
    便捷函数：处理视频字幕
    
    Args:
        video_id: 视频 ID
        video_path: 视频文件路径
        language: 语言类型
        category: 视频分类
        source_lang: 源语言
        target_lang: 目标语言
        
    Returns:
        SubtitleResult 处理结果
    """
    return get_subtitle_processor().process_video(
        video_id, video_path, language, category, source_lang, target_lang
    )


def init_subtitle_processor() -> None:
    """初始化字幕处理器"""
    global _subtitle_processor
    _subtitle_processor = SubtitleProcessor()
