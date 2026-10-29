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
        {"pattern": r"(?i)\b(die|der|das|ein|eine|ist|sind|haben|hat|werden|wird|und|oder|aber|doch|nicht|zu|mit|auf|aus|bei|von|nach|vor|zwischen|unter|durch|gegen|ohne|statt|während|bis|seit|ausser|außer)\b", "weight": 80.0},
        {"pattern": r"(?i)\b(ich|du|er|sie|es|wir|ihr|sich|mich|dich|ihn|ihm|uns|euch|ihnen|mein|dein|sein|ihr|unser|euer)\b", "weight": 60.0},
        {"pattern": r"(?i)\b(war|wurde|sein|hatte|gehabt|worden|gewesen|geworden)\b", "weight": 60.0},
        {"pattern": r"(?i)\b(denn|weil|obwohl|wenn|als|während|dass|ob|damit|sodass)\b", "weight": 70.0},
        {"pattern": r"(?i)\b(kein|keine|keinen|keinem|keiner|keines)\b", "weight": 70.0},
        {"pattern": r"(?i)\b(schon|nur|auch|immer|selbst|bereits|wieder)\b", "weight": 60.0},
        {"pattern": r"(?i)\b(tipps|anfänger|fortgeschrittene|lernen|sprache|unterricht|übung|aufgaben|grammatik|wortschatz|rechtschreibung|aussprache)\b", "weight": 90.0},
        {"pattern": r"(?i)\b(deutsch|Deutschland|Berlin|München|Hamburg|Wien|Zürich|Österreich|Schweiz)\b", "weight": 100.0},
        {"pattern": r"(?i)\b(jetzt|heute|gestern|morgen|manchmal|oft|selten)\b", "weight": 50.0},
        {"pattern": r"(?i)\b(für|über|neben|hinter|gegenüber)\b", "weight": 60.0},
        {"pattern": r"(?i)\b(leicht|schwer|einfach|schwierig|möglich|notwendig)\b", "weight": 60.0},
        {"pattern": r"(?i)\b(Bundesliga|Bayern|Dortmund|Leipzig|Stuttgart|Bremen|Frankfurt|Köln|Borussia)\b", "weight": 150.0},
        {"pattern": r"(?i)\b(Lied|Lieder|Sänger|Sängerin|Konzert|Festival|Band)\b", "weight": 100.0},
        {"pattern": r"(?i)\b(Groß|Groesse|Größe|Klein|Schön|Schein)\b", "weight": 80.0},
        {"pattern": r"(?i)\b(Serie|Folge|Teil|Sendung|Kapitel|Stunde|Minuten)\b", "weight": 60.0},
        {"pattern": r"(?i)\b(Monat|Woche|Tag|Mal|Alt|Altstadt|Altmann)\b", "weight": 50.0},
    ],
    LanguageType.FRENCH: [
        # 法语独特字符（大小写均已覆盖）
        {"pattern": r"ç", "weight": 200.0},
        {"pattern": r"[éèêëàâäôùûüîïÉÈÊËÀÂÄÔÙÛÜÎÏ]", "weight": 100.0},
        # 法语高频功能词（冠词、连词、介词）—— 不区分大小写以适配视频标题 Title Case
        {"pattern": r"(?i)\b(le|la|les|un|une|des|est|sont|étiez|était|étaient|étions)\b", "weight": 60.0},
        {"pattern": r"(?i)\b(et|ou|mais|donc|car|parce|puis|ensuite|cependant|néanmoins|pourtant)\b", "weight": 70.0},
        {"pattern": r"(?i)\b(que|qui|quoi|où|quand|comment|pourquoi|dont|lequel|laquelle|lesquels|lesquelles)\b", "weight": 80.0},
        # 法语人称代词
        {"pattern": r"(?i)\b(je|tu|il|elle|nous|vous|ils|elles|me|te|lui|y|en)\b", "weight": 80.0},
        # 法语自反代词和宾语
        {"pattern": r"(?i)\b(moi|toi|soi|nous|vous|leur|leurs)\b", "weight": 60.0},
        # 法语动词être和avoir的各种时态
        {"pattern": r"(?i)\b(je suis|tu es|il est|elle est|nous sommes|vous êtes|ils sont|elles sont)\b", "weight": 100.0},
        {"pattern": r"(?i)\b(j'ai|tu as|il a|elle a|nous avons|vous avez|ils ont|elles ont)\b", "weight": 100.0},
        {"pattern": r"(?i)\b(étais|était|étions|étiez|étaient|été|étant|fus|fut|fûmes|fûtes|furent)\b", "weight": 80.0},
        {"pattern": r"(?i)\b(avais|avait|avions|aviez|avaient|eu|ayant|eut|eûmes|eûtes|eurent)\b", "weight": 80.0},
        # 法语时态标记
        {"pattern": r"(?i)\b(je|tu|il|elle|nous|vous|ils|elles)\s+(vais|vas|va|allons|allez|vont)\b", "weight": 70.0},
        # 法语介词
        {"pattern": r"(?i)\b(dans|sur|sous|entre|parmi|autre|avant|après|pendant|durant|depuis|vers)\b", "weight": 60.0},
        {"pattern": r"(?i)\b(pour|contre|avec|sans|chez|de|du|des|en|à|au|aux)\b", "weight": 50.0},
        # 法语副词
        {"pattern": r"(?i)\b(toujours|jamais|souvent|parfois|rarement|déjà|encore|bien|mal|peu|beaucoup|assez)\b", "weight": 70.0},
        {"pattern": r"(?i)\b(vraiment|peut-être|probablement|certainement|sûrement|apparemment|évidemment|bien sûr)\b", "weight": 70.0},
        # 法语否定结构
        {"pattern": r"(?i)\b(ne|pas|plus|jamais|rien|personne|aucun|aucune|nul|nulle)\b", "weight": 60.0},
        # 法语学习/教学相关词汇
        {"pattern": r"(?i)\b(français|française|françaises|apprendre|apprentissage|cours|classe|école|étudiant|professeur)\b", "weight": 100.0},
        {"pattern": r"(?i)\b(grammaire|vocabulaire|conjugaison|prononciation|orthographe|expression|règle|exercice|évaluation)\b", "weight": 100.0},
        # 法语特有的科技/学习词汇（与英语形近但不同）
        {"pattern": r"(?i)\b(tutoriel|tutoriels|informatique|logiciel|matériel|clavier|souris|écran|imprimante|réseau)\b", "weight": 150.0},
        # 法语专有名词
        {"pattern": r"(?i)\b(France|Paris|Lyon|Marseille|Nice|Bordeaux|Toulouse|Strasbourg|Lille|Nantes)\b", "weight": 150.0},
        {"pattern": r"(?i)\b(Français|Française|Françaises|hexagone|hexagonal|métropole|outre-mer)\b", "weight": 120.0},
        # 法语常用短语
        {"pattern": r"(?i)\b(c'est|s'il vous plaît|merci|bonjour|au revoir|à bientôt|enchanté|salut|coucou)\b", "weight": 120.0},
        {"pattern": r"(?i)\b(comment ça va|comment allez-vous|je ne sais pas|je comprends|d'accord|bien sûr|peut-être)\b", "weight": 100.0},
        # 法语形容词
        {"pattern": r"(?i)\b(grand|grande|grands|grandes|petit|petite|petits|petites|beau|belle|beaux|belles)\b", "weight": 60.0},
        {"pattern": r"(?i)\b(bon|bonne|bons|bonnes|mauvais|mauvaise|mauvais|mauvaises|jeune|jeunes|vieux|vieille)\b", "weight": 60.0},
        # 法语动词（常用）
        {"pattern": r"(?i)\b(aller|venir|faire|dire|pouvoir|vouloir|devoir|savoir|connaître|aimer)\b", "weight": 70.0},
        {"pattern": r"(?i)\b(chercher|trouver|regarder|écouter|parler|écrire|lire|comprendre|expliquer|démontrer)\b", "weight": 70.0},
        # 法语文化相关
        {"pattern": r"(?i)\b(cinéma|musique|littérature|art|culture|patrimoine|gourmet|gastronomie|mode|luxe)\b", "weight": 80.0},
        {"pattern": r"(?i)\b(Sorbonne|Louvre|Versailles|Montmartre|Champs-Élysées|Tour Eiffel|Notre-Dame)\b", "weight": 150.0},
        # 法语数字和时间
        {"pattern": r"(?i)\b(aujourd'hui|hier|demain|matin|soir|nuit|jour|semaine|mois|année)\b", "weight": 50.0},
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
        # 英语高频功能词（介词、连词、助动词等）
        {"pattern": r"\b(the|a|an|is|are|was|were|be|been|being|have|has|had|do|does|did|will|would|could|should|may|might|must|and|or|but|not|this|that|these|those|it|its|of|to|in|for|on|with|at|by|from|as|into|through|during|before|after|above|below|between|under|again|further|then|once|here|there|when|where|why|how|all|each|few|more|most|other|some|such|no|nor|not|only|own|same|so|than|too|very|just)\b", "weight": 60.0},
        # 英语人称代词
        {"pattern": r"\b(I|you|he|she|we|they|me|him|her|us|them|my|your|his|our|their|what|which|who|whom|whose)\b", "weight": 50.0},
        # 英语学习/教学相关词汇（爬虫关键词匹配）
        {"pattern": r"\b(english|learn|learning|language|tutorial|course|class|lesson|teacher|student|school|education|bilingual|monolingual)\b", "weight": 100.0},
        # 英语常用动词和时态
        {"pattern": r"\b(go|going|gone|come|coming|see|seeing|seen|say|saying|said|get|getting|got|make|making|made|take|taking|took|think|thinking|thought|know|knowing|knew|knew|want|wanting|wanted|give|giving|gave|find|finding|found|tell|telling|told|ask|asking|asked|work|working|worked|seem|seeming|seemed|feel|feeling|felt|try|trying|tried|leave|leaving|left|call|calling|called|keep|keeping|kept|let|lets|begin|began|started|starting|started)\b", "weight": 60.0},
    ],
}


# =====================================================
# 语种识别核心函数
# =====================================================

def detect_language(text: str) -> Tuple[Optional[LanguageType], float]:
    """识别文本的语种
    
    识别策略：
        1. 优先识别有独特字符特征的语言（非 ASCII 字母）
        2. 如果文本只包含基本 ASCII 字母，选择得分最高的语言（不再默认英语）
        3. 如果有多种语言的独特字符，选择得分最高的
        4. 如果无法识别但文本为拉丁字符，默认判定为英语
    
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
    
    # 检测是否包含非 ASCII 字符（独特语种特征）
    has_non_ascii = any(ord(c) > 127 for c in text)
    
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
        
        if match_count > 0:
            scores[lang] = score / total_chars
    
    if not scores:
        # 无匹配特征时，检测是否为拉丁字符文本，若是则默认为英语
        alpha_chars = len(re.findall(r"[a-zA-Z]", text))
        if alpha_chars > 0 and alpha_chars / total_chars > 0.3:
            # 纯拉丁字符文本默认为英语，给予较高置信度
            # （因为其他主要语言都有独特的非 ASCII 字符特征）
            return LanguageType.ENGLISH, 0.8
        return None, 0.0
    
    # 纯 ASCII 文本处理逻辑
    # 策略：纯拉丁字母文本默认倾向英语（因为英德法西意等都共享拉丁字母，
    # 但英语是互联网/YouTube 上最主流的语言），只有当某语言有明确的
    # 高置信特征（大量独特词汇、特定字符）才判为非英语。
    if not has_non_ascii:
        alpha_chars = len(re.findall(r"[a-zA-Z]", text))
        is_latin = alpha_chars > 0 and alpha_chars / total_chars > 0.3

        if is_latin:
            # 给英语一个基准分（因为纯拉丁文本大概率英语）
            en_floor_score = 0.5

            # 如果英语本身有命中特征，用实际得分
            if LanguageType.ENGLISH in scores:
                en_score = max(scores[LanguageType.ENGLISH], en_floor_score)
            else:
                en_score = en_floor_score

            # 找非英语语言的最高分
            other_scores = {k: v for k, v in scores.items() if k != LanguageType.ENGLISH}
            if other_scores:
                max_other_lang = max(other_scores, key=other_scores.get)
                max_other = other_scores[max_other_lang]
                # 非英语语言得分必须显著超过英语基准分才判为该语言
                # （至少 2.5×，过滤掉 "Song"/"Video" 等共享词的弱信号）
                if max_other >= en_score * 2.5 and max_other >= 1.2:
                    return max_other_lang, max_other
                return LanguageType.ENGLISH, en_score
            # 没有其他语言得分，直接判英语
            return LanguageType.ENGLISH, en_score

        # 非拉丁字母的纯 ASCII 文本（罕见），返回最高分
        max_lang = max(scores, key=scores.get)
        return max_lang, scores[max_lang]
    
    # 有非 ASCII 字符，直接返回得分最高的语言
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


# =====================================================
# 视频多信号语言检测（原 lang_detector.py）
# 优先级：YouTube元数据 > Unicode字符范围 > 特征词 > 兜底English
# =====================================================

# --- Unicode 字符范围（只看真实字符，忽略标点数字） ---
_CJK_UNIFIED = re.compile(r"[\u4e00-\u9fff\u3400-\u4dbf]")
_KOREAN = re.compile(r"[\uac00-\ud7af\u1100-\u11ff]")
_JAPANESE_KANA = re.compile(r"[\u3040-\u30ff\u31f0-\u31ff]")
_RUSSIAN_CYRILLIC = re.compile(r"[\u0410-\u044f\u0400-\u04FF]")
_GREEK = re.compile(r"[\u0370-\u03FF]")
_ARABIC = re.compile(r"[\u0600-\u06FF\u0750-\u077F\u08A0-\u08FF]")
_THAI = re.compile(r"[\u0E00-\u0E7F]")
_VIETNAMESE_DIACRITIC = re.compile(r"[ắằẳẵặặầầẩẫậứừửữự]")
_INDIC_DEVANAGARI = re.compile(r"[\u0900-\u097F]")

# --- 拉丁字母扩展字符（欧语独有变音符号） ---
_GERMAN_DIACRITIC = re.compile(r"[äöüÄÖÜß]")
_FRENCH_DIACRITIC = re.compile(r"[çœàâêîôûëïüÿè]")
_SPANISH_DIACRITIC = re.compile(r"[ñ¿¡]")
_PORTUGUESE_DIACRITIC = re.compile(r"[ãõÃÕ]")
_NORDIC_DIACRITIC = re.compile(r"[åæøÅÆØ]")
_TURKISH_DIACRITIC = re.compile(r"[ıİşğŞĞ]")

# --- 语言特征词（冠词/高频功能词） ---
_FEATURE_WORDS = {
    LanguageType.GERMAN: [
        "der ", "die ", "das ", " den ", " dem ", " des ",
        " und ", " oder ", " ist ", " nicht ", " mit ", " aus ",
        " auch ", " nur ", " noch ", " schon ", " von ", " zu ",
        " über ", " unter ", " beim ", " im ", " am ", " wir ",
        " ihr ", " ihnen ", " seine ", " meine ", " diese ",
        " wie ", " was ", " wenn ", " weil ", " dass ", " ich ",
        " du ", " er ", " sie ", " es ",
        " deutsch", "german", "deutschland", "österreich", "schweiz",
        "lernen", "lektion", "stunde", "vokabel", "grammatik",
        "erklären", "sprechen", "unterricht", "einfach", "üben",
    ],
    LanguageType.FRENCH: [
        " le ", " la ", " les ", " du ", " de la ", " des ",
        " et ", " ou ", " mais ", " pas ", " non ", " est ",
        " avec ", " sans ", " sous ", " sur ", " dans ", " pour ",
        " que ", " qui ", " quoi ", " quand ", " comment ",
        " je ", " tu ", " il ", " elle ", " nous ", " vous ",
        " ils ", " elles ", " ce ", " cette ", " mon ", " ton ",
        " très ", " toujours ", " encore ", " aujourd'hui ",
    ],
    LanguageType.SPANISH: [
        " el ", " la ", " los ", " las ", " un ", " una ",
        " unos ", " unas ", " del ", " al ",
        " y ", " o ", " pero ", " no ", " sí ", " es ",
        " con ", " sin ", " en ", " por ", " para ", " que ",
        " cuando ", " como ", " donde ",
        " yo ", " tu ", " el ", " ella ", " nosotros ", " ellos ",
        " este ", " esta ", " ese ", " esa ", " muy ",
        "español", "españa", "méxico", "argentina", "colombia",
        "aprender", "hablar", "fácil", "receta", "lección",
        "bienvenido", "mejor", "amigo", "hola",
    ],
    LanguageType.ITALIAN: [
        " il ", " lo ", " la ", " i ", " gli ", " le ",
        " un ", " uno ", " una ", " del ", " della ", " dei ",
        " e ", " o ", " ma ", " non ", " è ",
        " con ", " senza ", " su ", " tra ", " fra ", " per ",
        " che ", " chi ", " come ", " quando ", " dove ",
        " io ", " tu ", " lui ", " lei ", " noi ", " voi ", " loro ",
        " questo ", " questa ", " molto ", " sempre ", " ancora ",
        "italiano", "italia", "roma", "milano", "napoli", "firenze",
        "imparare", "parlare", "facile", "lezione", "corso",
        "ricetta", "pasta", "cucina", "pizza",
    ],
    LanguageType.PORTUGUESE: [
        " o ", " a ", " os ", " as ", " um ", " uma ",
        " uns ", " umas ", " do ", " da ", " no ", " na ",
        " e ", " ou ", " mas ", " não ", " sim ", " é ",
        " com ", " sem ", " em ", " por ", " para ", " que ",
        " quando ", " como ", " onde ",
        " eu ", " tu ", " ele ", " ela ", " nós ", " vocês ",
        " este ", " esta ", " esse ", " essa ", " muito ",
        "português", "portuguesa", "brasil", "brasileiro", "brasileira",
        "aprender", "fácil", "aula", "curso", "ensinar",
    ],
    LanguageType.DUTCH: [
        " de ", " het ", " een ", " en ", " of ", " niet ",
        " is ", " met ", " voor ", " door ", " naar ", " van ",
        " te ", " aan ", " op ", " in ", " bij ", " om ",
        " ik ", " je ", " hij ", " zij ", " het ", " wij ",
        " deze ", " dit ", " daar ", " hier ",
    ],
    LanguageType.SWEDISH: [
        " en ", " ett ", " det ", " de ", " den ",
        " och ", " eller ", " inte ", " är ", " med ",
        " för ", " av ", " till ", " från ", " på ", " i ",
        " om ", " han ", " hon ", " vi ", " ni ", " de ",
    ],
    LanguageType.NORWEGIAN: [
        " en ", " et ", " den ", " det ", " de ",
        " og ", " eller ", " ikke ", " er ", " med ",
        " for ", " til ", " fra ", " på ", " i ", " av ",
        " jeg ", " du ", " han ", " hun ", " vi ", " dere ",
    ],
    LanguageType.DANISH: [
        " en ", " et ", " den ", " det ", " de ",
        " og ", " eller ", " ikke ", " er ", " med ",
        " for ", " til ", " fra ", " på ", " i ", " af ",
        " jeg ", " du ", " han ", " hun ", " vi ", " I ",
    ],
    LanguageType.FINNISH: [
        " ja ", " tai ", " ei ", " on ", " kanssa ",
        " minä ", " sinä ", " hän ", " me ", " te ", " he ",
        " tämä ", " tuo ", " se ", " eikä ", " sekä ",
    ],
    LanguageType.POLISH: [
        " i ", " lub ", " ale ", " nie ", " jest ",
        " z ", " do ", " na ", " w ", " po ", " za ",
        " że ", " kto ", " co ", " jak ", " gdzie ", " kiedy ",
        " ja ", " ty ", " on ", " ona ", " my ", " wy ", " oni ",
    ],
    LanguageType.CZECH: [
        " a ", " nebo ", " ale ", " ne ", " je ",
        " s ", " do ", " na ", " v ", " po ", " za ",
        " že ", " kdo ", " co ", " jak ", " kde ", " kdy ",
        " já ", " ty ", " on ", " ona ", " my ", " vy ", " oni ",
    ],
    LanguageType.ROMANIAN: [
        " și ", " sau ", " dar ", " nu ", " este ",
        " cu ", " în ", " pe ", " pentru ", " de ", " la ",
        " că ", " cine ", " ce ", " cum ", " unde ", " când ",
        " eu ", " tu ", " el ", " ea ", " noi ", " voi ", " ei ",
    ],
    LanguageType.HUNGARIAN: [
        " és ", " vagy ", " de ", " nem ", " van ",
        " az ", " a ", " egy ", " benne ", " alatt ",
        " hogy ", " ki ", " mi ", " hol ", " mikor ",
        " én ", " te ", " ő ", " mi ", " ti ", " ők ",
    ],
    LanguageType.TURKISH: [
        " ve ", " veya ", " ama ", " değil ", " mi ",
        " ile ", " için ", " tarafından ", " üzerinde ", " altında ",
        " ben ", " sen ", " o ", " biz ", " siz ", " onlar ",
        " çok ", " gibi ", " burada ", " şimdi ",
    ],
    LanguageType.ARABIC: [
        " و ", " و", " أو ", " لكن ", " لا ", " نعم ",
        " إلى ", " من ", " على ", " في ", " مع ", " عن ",
        " أنا ", " أنت ", " هو ", " هي ", " نحن ", " أنتم ", " هم ",
        " هذا ", " هذه ", " ذلك ", " تلك ", " ما ", " لماذا ",
    ],
    LanguageType.INDONESIAN: [
        " dan ", " atau ", " tetapi ", " tidak ", " ya ",
        " di ", " ke ", " dari ", " dengan ", " untuk ", " oleh ",
        " saya ", " kamu ", " dia ", " kami ", " kalian ", " mereka ",
        " ini ", " itu ", " sangat ", " sudah ", " belum ",
        "bahasa", "indonesia", "pemula", "berbicara", "pelajaran",
        "mempelajari", "mudah", "cepat", "hari ini",
    ],
    LanguageType.MALAY: [
        " dan ", " atau ", " tetapi ", " tidak ", " ya ",
        " di ", " ke ", " dari ", " dengan ", " untuk ", " oleh ",
        " saya ", " awak ", " dia ", " kami ", " kamu ", " mereka ",
        " ini ", " itu ", " sangat ", " sudah ", " belum ",
        "bahasa", "melayu", "malaysia", "kuala lumpur",
        "pembelajaran", "permulaan", "bercakap",
    ],
    LanguageType.VIETNAMESE: [
        " và ", " hoặc ", " nhưng ", " không ", " phải ",
        " trong ", " trên ", " dưới ", " với ", " cho ",
        " tôi ", " bạn ", " anh ", " chị ", " họ ", " chúng ta ",
        " đây ", " đó ", " rất ", " đã ", " đang ", " sẽ ",
    ],
    LanguageType.TAGALOG: [
        " at ", " o ", " pero ", " hindi ", " oo ",
        " sa ", " ng ", " para sa ", " mula sa ", " na ",
        " ako ", " ikaw ", " siya ", " tayo ", " kami ", " kayo ", " sila ",
        " ito ", " iyan ", " doon ", " dito ",
    ],
    LanguageType.THAI: [
        " และ ", " หรือ ", " แต่ ", " ไม่ ", " ใช่ ",
        " ใน ", " บน ", " ใต้ ", " กับ ", " สำหรับ ", " จาก ", " ถึง ",
        " ฉัน ", " คุณ ", " เขา ", " เรา ", " พวกเขา ",
        " นี่ ", " นั่น ", " ที่นี่ ", " ที่นั่น ", " มาก ",
    ],
    LanguageType.HINDI: [
        " और ", " या ", " लेकिन ", " नहीं ", " हाँ ",
        " में ", " पर ", " से ", " के लिए ", " के साथ ", " को ",
        " मैं ", " तुम ", " वह ", " हम ", " तुम्हें ", " वे ",
        " यह ", " वह ", " यहाँ ", " वहाँ ", " बहुत ",
    ],
}


def _count_chars(text: str, regex) -> int:
    return len(regex.findall(text))


def detect_language_rich(
    title: str = "",
    description: Optional[str] = None,
    subtitle_text: Optional[str] = None,
    youtube_language_code: Optional[str] = None,
    subtitle_langs_hint: Optional[list] = None,
) -> LanguageType:
    """
    综合多信号检测视频源语言。

    优先级（从高到低）：
        1. YouTube 元数据明确给的 language_code
        2. Unicode 字符范围检测（中日韩 / 阿拉伯 / 西里尔 / 希腊 / 泰 / 印度 / 越南等）
        3. 语言高辨识度特征词（冠词、高频功能词）
        4. 都没命中 → 兜底 English

    Returns:
        LanguageType — 永远不会返回 None
    """

    text = " ".join(filter(None, [title or "", description or "", subtitle_text or ""])).strip()
    lower_text = f" {text.lower()} "

    # === 优先级1: YouTube 明确语言标记 ===
    if youtube_language_code:
        yt_code = str(youtube_language_code).strip().lower()
        if "-" in yt_code:
            yt_code = yt_code.split("-")[0]
        lt = LanguageType.from_code(yt_code)
        if lt is not None:
            return lt

    # === 优先级2: 字幕语言列表 ===
    if subtitle_langs_hint:
        for lang in subtitle_langs_hint:
            code = str(lang).lower()
            if "-" in code:
                code = code.split("-")[0]
            if code in ("zh", "zh-cn", "zh-hans"):
                continue
            lt = LanguageType.from_code(code)
            if lt is not None:
                return lt

    # === 优先级3: Unicode 字符范围 ===
    cjk = _count_chars(text, _CJK_UNIFIED)
    kana = _count_chars(text, _JAPANESE_KANA)
    hangul = _count_chars(text, _KOREAN)
    cyrillic = _count_chars(text, _RUSSIAN_CYRILLIC)
    arabic = _count_chars(text, _ARABIC)
    thai = _count_chars(text, _THAI)
    greek = _count_chars(text, _GREEK)
    deva = _count_chars(text, _INDIC_DEVANAGARI)
    viet_diac = _count_chars(text, _VIETNAMESE_DIACRITIC)

    if kana >= 2:
        return LanguageType.JAPANESE
    if hangul >= 2:
        return LanguageType.KOREAN
    if cjk >= 4:
        return LanguageType.CHINESE
    if arabic >= 2:
        return LanguageType.ARABIC
    if thai >= 2:
        return LanguageType.THAI
    if deva >= 2:
        return LanguageType.HINDI
    if greek >= 2:
        return LanguageType.GREEK
    if cyrillic >= 2:
        return LanguageType.RUSSIAN
    if viet_diac >= 2:
        return LanguageType.VIETNAMESE

    # === 优先级3.5: 拉丁字母变音符号 ===
    if _count_chars(text, _GERMAN_DIACRITIC) >= 1:
        tr_diac = _count_chars(text, _TURKISH_DIACRITIC)
        if ("ß" in text) or ("ẞ" in text) or tr_diac == 0:
            if _count_chars(text, _GERMAN_DIACRITIC) >= 2 or _count_chars(lower_text, _GERMAN_DIACRITIC) >= 1:
                return LanguageType.GERMAN
    if _count_chars(text, _SPANISH_DIACRITIC) >= 1:
        return LanguageType.SPANISH
    if _count_chars(text, _PORTUGUESE_DIACRITIC) >= 1:
        return LanguageType.PORTUGUESE
    if _count_chars(text, _TURKISH_DIACRITIC) >= 1:
        return LanguageType.TURKISH
    if _count_chars(text, _NORDIC_DIACRITIC) >= 1:
        return LanguageType.NORWEGIAN
    if _count_chars(text, _FRENCH_DIACRITIC) >= 2:
        return LanguageType.FRENCH

    # === 优先级3.6: 字符种类占比 ===
    letters = [c for c in text if c.isalpha()]
    if letters:
        lat_count = sum(1 for c in letters if '\u0000' <= c <= '\u024f' or
                        '\u1e00' <= c <= '\u1eff')
        cjk_count = sum(1 for c in letters if _CJK_UNIFIED.search(c))
        total_letters = len(letters)
        if cjk_count >= 4:
            return LanguageType.CHINESE
        if cjk_count >= 2 and (cjk_count / total_letters) >= 0.30 and cjk_count * 2 >= lat_count:
            return LanguageType.CHINESE

    # === 优先级4: 特征词打分 ===
    if lower_text and len(lower_text) >= 10:
        scores: dict = {}
        for lang, words in _FEATURE_WORDS.items():
            s = 0
            for w in words:
                if w in lower_text:
                    s += 1
            if s >= 1:
                scores[lang] = s
        if scores:
            top = max(scores, key=scores.get)
            top_s = scores[top]
            others = [v for k, v in scores.items() if k != top]
            second_s = max(others) if others else 0
            if top_s >= 1 and top_s >= second_s + 1:
                return top
            if len(scores) == 1 and top_s >= 2:
                return top

    # === 兜底：ENGLISH ===
    return LanguageType.ENGLISH


def detect_language_from_info(info: dict, subtitle_text: Optional[str] = None) -> LanguageType:
    """从 yt-dlp 提取的 info dict 综合检测语言。"""
    if not isinstance(info, dict):
        return LanguageType.ENGLISH

    title = str(info.get("title") or "")
    description = str(info.get("description") or "")

    yt_lang = info.get("language") or info.get("language_code")
    if not yt_lang and isinstance(info.get("playlist"), dict):
        yt_lang = info["playlist"].get("language")

    subtitle_langs: list = []
    for k in ("subtitles", "requested_subtitles", "automatic_captions"):
        obj = info.get(k)
        if isinstance(obj, dict):
            subtitle_langs.extend(obj.keys())

    return detect_language_rich(
        title=title,
        description=description,
        subtitle_text=subtitle_text,
        youtube_language_code=yt_lang,
        subtitle_langs_hint=subtitle_langs or None,
    )
