"""
语种识别工具模块

功能特性：
    1. 基于 Unicode 字符特征识别任意语种
    2. 支持白名单过滤：爬虫可指定只抓取特定语言
    3. 返回识别置信度
    4. 支持批量识别和过滤

识别原理：
    通过分析文本中的 Unicode 字符范围来判断语种，
    每种语言有独特的字符集特征（如中文使用汉字、日文使用假名等）。
"""

import re
from typing import Optional, List, Tuple, Dict, Union

from .enums import LanguageType


# =====================================================
# Unicode 字符范围定义
# =====================================================

class UnicodeRanges:
    """Unicode 字符范围常量定义"""
    
    # 拉丁字母（西欧语言）
    LATIN_BASIC = r"[\u0041-\u005A\u0061-\u007A]"
    LATIN_EXTENDED_A = r"[\u0100-\u017F]"
    LATIN_EXTENDED_B = r"[\u0180-\u024F]"
    LATIN_EXTENDED_ADDITIONAL = r"[\u1E00-\u1EFF]"
    
    # 中文
    CJK_UNIFIED = r"[\u4E00-\u9FFF]"
    CJK_EXTENDED_A = r"[\u3400-\u4DBF]"
    CJK_EXTENDED_B = r"[\u20000-\u2A6DF]"
    CJK_SYMBOLS = r"[\u3000-\u303F]"
    CJK_PUNCTUATION = r"[\uFF00-\uFFEF]"
    
    # 日文
    HIRAGANA = r"[\u3040-\u309F]"
    KATAKANA = r"[\u30A0-\u30FF]"
    KANJI = r"[\u4E00-\u9FFF]"  # 与中文共用汉字
    
    # 韩文
    HANGUL_SYLLABLES = r"[\uAC00-\uD7AF]"
    HANGUL_JAMO = r"[\u1100-\u11FF]"
    HANGUL_COMPATIBILITY = r"[\u3130-\u318F]"
    
    # 西里尔字母（俄语等）
    CYRILLIC = r"[\u0400-\u04FF]"
    CYRILLIC_EXTENDED_A = r"[\u0500-\u052F]"
    
    # 希腊字母
    GREEK = r"[\u0370-\u03FF]"
    
    # 阿拉伯字母
    ARABIC = r"[\u0600-\u06FF]"
    ARABIC_EXTENDED = r"[\u0750-\u077F]"
    
    # 印度语系
    DEVANAGARI = r"[\u0900-\u097F]"  # 印地语等
    
    # 泰语
    THAI = r"[\u0E00-\u0E7F]"
    
    # 越南语
    VIETNAMESE = r"[\u0EA0-\u0EFF]"
    
    # 希伯来语
    HEBREW = r"[\u0590-\u05FF]"
    
    # 其他
    COMMON_PUNCTUATION = r"[\u0020-\u0040\u005B-\u0060\u007B-\u007E]"
    DIGITS = r"[\u0030-\u0039]"


# =====================================================
# 语言特征配置
# =====================================================

_LANGUAGE_FEATURES: Dict[LanguageType, List[Dict[str, str]]] = {
    LanguageType.CHINESE: [
        {"pattern": UnicodeRanges.CJK_UNIFIED, "weight": 100.0},
        {"pattern": UnicodeRanges.CJK_EXTENDED_A, "weight": 90.0},
        {"pattern": UnicodeRanges.CJK_SYMBOLS, "weight": 50.0},
        {"pattern": UnicodeRanges.CJK_PUNCTUATION, "weight": 30.0},
    ],
    LanguageType.JAPANESE: [
        {"pattern": UnicodeRanges.HIRAGANA, "weight": 100.0},
        {"pattern": UnicodeRanges.KATAKANA, "weight": 100.0},
        {"pattern": UnicodeRanges.KANJI, "weight": 70.0},
    ],
    LanguageType.KOREAN: [
        {"pattern": UnicodeRanges.HANGUL_SYLLABLES, "weight": 100.0},
        {"pattern": UnicodeRanges.HANGUL_JAMO, "weight": 80.0},
        {"pattern": UnicodeRanges.HANGUL_COMPATIBILITY, "weight": 50.0},
    ],
    LanguageType.RUSSIAN: [
        {"pattern": UnicodeRanges.CYRILLIC, "weight": 100.0},
        {"pattern": UnicodeRanges.CYRILLIC_EXTENDED_A, "weight": 80.0},
    ],
    LanguageType.GREEK: [
        {"pattern": UnicodeRanges.GREEK, "weight": 100.0},
    ],
    LanguageType.ARABIC: [
        {"pattern": UnicodeRanges.ARABIC, "weight": 100.0},
        {"pattern": UnicodeRanges.ARABIC_EXTENDED, "weight": 80.0},
    ],
    LanguageType.HINDI: [
        {"pattern": UnicodeRanges.DEVANAGARI, "weight": 100.0},
    ],
    LanguageType.THAI: [
        {"pattern": UnicodeRanges.THAI, "weight": 100.0},
    ],
    LanguageType.VIETNAMESE: [
        {"pattern": UnicodeRanges.VIETNAMESE, "weight": 100.0},
    ],
    LanguageType.GERMAN: [
        {"pattern": r"ß", "weight": 200.0},
        {"pattern": r"[äöüÄÖÜ]", "weight": 100.0},
        {"pattern": r"\b(die|der|das|ein|eine|ist|sind|haben|hat|werden|wird|und|oder|aber|doch|nicht)\b", "weight": 50.0},
    ],
    LanguageType.FRENCH: [
        {"pattern": r"ç", "weight": 200.0},
        {"pattern": r"[éèêëàâäôùûüîïÉÈÊËÀÂÄÔÙÛÜÎÏ]", "weight": 100.0},
        {"pattern": r"\b(le|la|les|un|une|des|est|sont|et|ou|mais|donc|pas)\b", "weight": 50.0},
    ],
    LanguageType.SPANISH: [
        {"pattern": r"[ñÑ]", "weight": 200.0},
        {"pattern": r"¿|¡", "weight": 200.0},
        {"pattern": r"[áéíóúüÁÉÍÓÚÜ]", "weight": 100.0},
        {"pattern": r"\b(el|la|los|las|un|una|unos|unas|es|son|y|o|pero|no)\b", "weight": 50.0},
    ],
    LanguageType.ITALIAN: [
        {"pattern": r"[àèéìíòóùúÀÈÉÌÍÒÓÙÚ]", "weight": 100.0},
        {"pattern": r"\b(il|la|i|le|un|una|uno|è|sono|e|o|ma|non)\b", "weight": 50.0},
    ],
    LanguageType.PORTUGUESE: [
        {"pattern": r"ç", "weight": 200.0},
        {"pattern": r"[áàâãéèêíìîóòôõúùûÁÀÂÃÉÈÊÍÌÎÓÒÔÕÚÙÛ]", "weight": 100.0},
        {"pattern": r"\b(o|a|os|as|um|uma|é|são|e|ou|mas|não)\b", "weight": 50.0},
    ],
    LanguageType.DUTCH: [
        {"pattern": r"[äëïöüÄËÏÖÜ]", "weight": 100.0},
        {"pattern": r"\b(de|het|een|is|zijn|en|of|maar|niet)\b", "weight": 50.0},
    ],
    LanguageType.SWEDISH: [
        {"pattern": r"[åäöÅÄÖ]", "weight": 100.0},
        {"pattern": r"\b(den|det|en|ett|är|vara|och|eller|men|inte)\b", "weight": 50.0},
    ],
    LanguageType.NORWEGIAN: [
        {"pattern": r"[æøåÆØÅ]", "weight": 100.0},
    ],
    LanguageType.DANISH: [
        {"pattern": r"[æøåÆØÅ]", "weight": 100.0},
    ],
    LanguageType.FINNISH: [
        {"pattern": r"[äöÄÖ]", "weight": 100.0},
        {"pattern": r"\b(ja|tai|mutta|ei|on|ovat)\b", "weight": 50.0},
    ],
    LanguageType.POLISH: [
        {"pattern": r"[ąćęłńóśźżĄĆĘŁŃÓŚŹŻ]", "weight": 100.0},
    ],
    LanguageType.CZECH: [
        {"pattern": r"[áčďéěíóřšťúůýžÁČĎÉĚÍÓŘŠŤÚŮÝŽ]", "weight": 100.0},
    ],
    LanguageType.HUNGARIAN: [
        {"pattern": r"[áéíóöőúüűÁÉÍÓÖŐÚÜŰ]", "weight": 100.0},
    ],
    LanguageType.ROMANIAN: [
        {"pattern": r"[ăâîșțĂÂÎȘȚ]", "weight": 100.0},
    ],
    LanguageType.TURKISH: [
        {"pattern": r"[çğıİöşüÇĞİİÖŞÜ]", "weight": 100.0},
    ],
    LanguageType.INDONESIAN: [
        {"pattern": r"\b(saya|kamu|dia|dan|atau|tapi|tidak)\b", "weight": 50.0},
    ],
    LanguageType.MALAY: [
        {"pattern": r"\b(saya|kamu|dia|dan|atau|tetapi|tidak)\b", "weight": 50.0},
    ],
    LanguageType.TAGALOG: [
        {"pattern": r"[ñÑ]", "weight": 100.0},
        {"pattern": r"\b(ang|ng|at|o|pero|hindi)\b", "weight": 50.0},
    ],
    LanguageType.ENGLISH: [
        {"pattern": r"\b(the|a|an|is|are|was|were|be|been|being|have|has|had|do|does|did|will|would|could|should|may|might|must|and|or|but|not)\b", "weight": 50.0},
        {"pattern": r"[a-zA-Z]", "weight": 1.0},
    ],
}


# =====================================================
# 语种识别核心函数
# =====================================================

def detect_language(text: str) -> Tuple[Optional[LanguageType], float]:
    """识别文本的语种
    
    识别策略：
        1. 优先识别有独特字符特征的语言（非 ASCII 字母）
        2. 如果文本只包含基本 ASCII 字母，识别为英语
        3. 如果有多种语言的独特字符，选择得分最高的
    
    Args:
        text: 待识别的文本
        
    Returns:
        (语种枚举, 置信度)，无法识别返回 (None, 0.0)
    """
    if not text or not isinstance(text, str):
        return None, 0.0
    
    text = text.strip()
    if not text:
        return None, 0.0
    
    scores: Dict[LanguageType, float] = {}
    total_chars = len(text)
    
    if total_chars == 0:
        return None, 0.0
    
    has_unique_chars = False
    
    for lang, features in _LANGUAGE_FEATURES.items():
        score = 0.0
        match_count = 0
        
        for feature in features:
            pattern = feature["pattern"]
            weight = feature["weight"]
            
            matches = re.findall(pattern, text)
            if matches:
                match_count += len(matches)
                score += len(matches) * weight
                
                if weight > 1.0:
                    has_unique_chars = True
        
        if match_count > 0:
            scores[lang] = score / total_chars
    
    if not scores:
        return None, 0.0
    
    if has_unique_chars:
        max_lang = max(scores, key=scores.get)
        max_score = scores[max_lang]
    else:
        if LanguageType.ENGLISH in scores:
            max_lang = LanguageType.ENGLISH
            max_score = scores[LanguageType.ENGLISH]
        else:
            max_lang = max(scores, key=scores.get)
            max_score = scores[max_lang]
    
    return max_lang, max_score


def detect_language_top_n(text: str, n: int = 3) -> List[Tuple[LanguageType, float]]:
    """识别文本的前N种可能语种
    
    Args:
        text: 待识别的文本
        n: 返回前N个结果
        
    Returns:
        [(语种枚举, 置信度), ...]，按置信度降序排列
    """
    if not text or not isinstance(text, str):
        return []
    
    text = text.strip()
    if not text:
        return []
    
    scores: Dict[LanguageType, float] = {}
    total_chars = len(text)
    
    for lang, features in _LANGUAGE_FEATURES.items():
        score = 0.0
        
        for feature in features:
            pattern = feature["pattern"]
            weight = feature["weight"]
            
            matches = re.findall(pattern, text)
            if matches:
                score += len(matches) * weight
        
        if score > 0:
            scores[lang] = score / total_chars
    
    sorted_langs = sorted(scores.items(), key=lambda x: x[1], reverse=True)
    return sorted_langs[:n]


# =====================================================
# 语言过滤函数（爬虫专用）
# =====================================================

def is_language_allowed(
    text: str,
    allowed_languages: Optional[List[LanguageType]] = None,
    threshold: float = 0.3
) -> bool:
    """判断文本语言是否在允许的白名单内
    
    Args:
        text: 待判断的文本
        allowed_languages: 允许的语言白名单，None表示允许所有语言
        threshold: 识别置信度阈值
        
    Returns:
        True表示允许，False表示不允许
    """
    if allowed_languages is None or len(allowed_languages) == 0:
        return True
    
    lang, confidence = detect_language(text)
    
    if lang is None:
        return False
    
    if confidence < threshold:
        return False
    
    return lang in allowed_languages


def filter_by_language(
    texts: List[str],
    allowed_languages: Optional[List[LanguageType]] = None,
    threshold: float = 0.3
) -> List[Tuple[str, LanguageType, float]]:
    """批量过滤文本，只保留白名单内的语言
    
    Args:
        texts: 待过滤的文本列表
        allowed_languages: 允许的语言白名单，None表示允许所有语言
        threshold: 识别置信度阈值
        
    Returns:
        [(文本, 语种枚举, 置信度), ...]，仅包含白名单内的语言
    """
    results = []
    
    for text in texts:
        lang, confidence = detect_language(text)
        
        if lang is None or confidence < threshold:
            continue
        
        if allowed_languages is None or lang in allowed_languages:
            results.append((text, lang, confidence))
    
    return results


def get_language_name(lang: Union[LanguageType, str]) -> str:
    """获取语种的中文名称
    
    Args:
        lang: 语种枚举或语种代码
        
    Returns:
        中文名称
    """
    if isinstance(lang, LanguageType):
        return lang.display_name
    
    try:
        lang_enum = LanguageType(lang)
        return lang_enum.display_name
    except ValueError:
        return lang


# =====================================================
# 便捷函数
# =====================================================

def detect_video_language(
    title: str,
    description: Optional[str] = None
) -> Tuple[Optional[LanguageType], float]:
    """识别视频的语种（组合标题和描述）
    
    Args:
        title: 视频标题
        description: 视频描述（可选）
        
    Returns:
        (语种枚举, 置信度)
    """
    full_text = title
    
    if description:
        full_text += "\n" + description
    
    return detect_language(full_text)


def is_video_language_allowed(
    title: str,
    description: Optional[str] = None,
    allowed_languages: Optional[List[LanguageType]] = None,
    threshold: float = 0.3
) -> bool:
    """判断视频语言是否在允许的白名单内
    
    Args:
        title: 视频标题
        description: 视频描述（可选）
        allowed_languages: 允许的语言白名单
        threshold: 识别置信度阈值
        
    Returns:
        True表示允许，False表示不允许
    """
    full_text = title
    
    if description:
        full_text += "\n" + description
    
    return is_language_allowed(full_text, allowed_languages, threshold)
