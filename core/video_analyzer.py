"""
视频内容分析模块 - AI增强版

扩展功能：在下载视频前询问用户分析提炼方向，下载并翻译后根据用户要求
对内容进行分析并输出，将原视频、翻译视频、分析文案保存在同一文件夹内。

功能特性：
    1. 支持多种分析模式（语言学习、内容总结、关键词提取等）
    2. 根据字幕内容生成分析报告
    3. 将分析结果保存为Markdown文件
    4. 与文件归档器集成，每个视频独立文件夹存储
    5. AI增强：支持调用外部AI服务生成高质量分析报告（最多8次重构尝试）
"""

import os
import re
from typing import Optional, List, Dict, Any
from dataclasses import dataclass
from enum import auto
import sys as _sys
if _sys.version_info >= (3, 11):
    from enum import StrEnum
else:
    from enum import Enum as _Enum
    class StrEnum(str, _Enum):
        pass

from utils.logger import get_crawler_logger
from utils.path_helper import get_output_dir
from core.ai_writer import get_ai_writer, ContentType


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
    支持多语言分析：英语、德语、法语、西班牙语、中文、日语等。
    """
    
    def __init__(self) -> None:
        """初始化视频内容分析器"""
        self._ai_writer = get_ai_writer()
        self._language_data = self._init_language_data()
        logger.info("视频内容分析器初始化完成")
    
    def _init_language_data(self) -> Dict[str, Dict[str, Any]]:
        """初始化多语言数据"""
        return {
            "en": {
                "oral_markers": ["alright", "well", "so", "yeah", "yep", "nope", "uh", "um",
                               "like", "you know", "I mean", "kind of", "sort of", "pretty much",
                               "gonna", "wanna", "gotta", "lemme", "gimme", "ain't"],
                "contractions": {
                    "gonna": "going to", "wanna": "want to", "gotta": "got to",
                    "lemme": "let me", "gimme": "give me", "'cause": "because",
                    "d'you": "do you", "whatcha": "what are you", "y'all": "you all",
                    "kinda": "kind of", "sorta": "sort of", "ain't": "am not/is not/are not"
                },
                "informal_words": ["cool", "awesome", "nice", "great", "amazing", "sweet",
                                  "guy", "guys", "dude", "buddy", "pal", "stuff", "thing"],
                "oral_patterns": [
                    (r"Alright,? so", "开场白"), (r"You know", "填充词"),
                    (r"I mean", "填充词"), (r"kind of", "模糊表达"),
                    (r"sort of", "模糊表达"), (r"pretty much", "程度表达"),
                    (r"That's cool", "评价"), (r"You got it", "确认"),
                    (r"No problem", "回应"), (r"Got it", "理解")
                ],
                "complex_patterns": [
                    (r"It is .+ that", "强调句型"), (r"There be .+", "存在句型"),
                    (r"The reason why .+ is that", "原因句型"),
                    (r"Not only .+ but also", "并列强调"),
                    (r"It seems that", "推测句型"), (r"What .+ is", "名词性从句"),
                    (r"That is why", "结论句型"), (r"In order to", "目的状语"),
                    (r"Although .+ ,", "让步状语"), (r"Because .+ ,", "原因状语")
                ],
                "collocations": {
                    "significant": ["significant impact", "significant change", "significant amount"],
                    "influence": ["have an influence on", "influence decision", "influence behavior"],
                    "achieve": ["achieve goal", "achieve success", "achieve result"],
                    "contribute": ["contribute to", "make contribution", "contribute significantly"],
                    "determine": ["determine outcome", "determine cause", "determine factor"],
                    "potential": ["potential for", "have potential", "potential market"],
                    "perspective": ["from perspective", "different perspective", "new perspective"],
                    "analyze": ["analyze data", "analyze situation", "analyze problem"],
                    "evaluate": ["evaluate performance", "evaluate options", "evaluate quality"],
                    "establish": ["establish relationship", "establish rule", "establish system"],
                },
                "formal_alternatives": {
                    "cool": "impressive / remarkable", "guy": "person / individual",
                    "stuff": "materials / items", "thing": "matter / aspect",
                    "kind of": "to some extent", "sort of": "to a certain degree",
                    "pretty much": "essentially / largely", "gotta": "have to / must",
                    "wanna": "want to", "gonna": "going to"
                }
            },
            "de": {
                "oral_markers": ["also", "mal", "ja", "ne", "einfach", "so",
                                "halt", "eben", "naja", "tschüss", "tschüssi",
                                "na", "ach", "uhu", "äh", "hm", "nicht wahr",
                                "wissen Sie", "denn", "jawohl", "nein", "guten Tag"],
                "contractions": {
                    "'s": "es", "'re": "seid", "'ve": "habt", "ich'm": "ich bin",
                    "du'm": "du bist", "er'm": "er ist", "sie'm": "sie ist",
                    "wir'm": "wir sind", "ihr'm": "ihr seid", "sie'm": "sie sind",
                    "ich've": "ich habe", "du've": "du hast", "er've": "er hat",
                    "sie've": "sie hat", "wir've": "wir haben", "ihr've": "ihr habt",
                    "sie've": "sie haben", "dass": "daß", "kann't": "kann nicht",
                    "will't": "will nicht", "darf't": "darf nicht", "muss't": "muss nicht"
                },
                "informal_words": ["cool", "super", "geil", "mega", "krasse",
                                  "ding", "sache", "typ", "leute", "freund",
                                  "kumpel", "alter", "bruder", "schwein",
                                  "hammer", "klasse", "top", "fantastisch", "cool"],
                "oral_patterns": [
                    (r"Na ja", "语气词"), (r"So,", "开场白"),
                    (r"Also,", "连接词"), (r"Einfach", "强调"),
                    (r"Halt", "强调"), (r"Naja", "犹豫"),
                    (r"Mal", "语气词"), (r"Gut", "过渡"),
                    (r"Schau mal", "看"), (r"Komm schon", "来吧"),
                    (r"Nicht wahr", "确认"), (r"Wissen Sie", "填充"),
                    (r"Na dann", "过渡"), (r"Ach so", "理解"),
                    (r"So geht's", "问候"), (r"Wie geht's", "问候"),
                    (r"Ich meine", "填充"), (r"Äh", "犹豫"),
                    (r"Hm", "思考"), (r"Uhu", "回应")
                ],
                "complex_patterns": [
                    (r"Es ist .+ ,? dass", "主语从句"), (r"Dass .+ ,", "主语从句"),
                    (r"Obwohl .+ ,", "让步状语"), (r"Weil .+ ,", "原因状语"),
                    (r"Wenn .+ ,", "条件状语"), (r"Damit .+ ,", "目的状语"),
                    (r"Als .+ ,", "时间状语"), (r"Ob .+ ,", "疑问从句"),
                    (r"Wann .+ ,", "时间从句"), (r"Wo .+ ,", "地点从句"),
                    (r"Das ist der Grund, warum", "原因句型"),
                    (r"Es scheint, dass", "推测句型"),
                    (r"Nicht nur .+ sondern auch", "并列强调"),
                    (r"In order to", "目的状语"),
                    (r"Während .+ ,", "对比状语"),
                    (r"Bis .+ ,", "时间状语"),
                    (r"Sobald .+ ,", "时间状语"),
                    (r"Damit .+ ,", "目的状语")
                ],
                "collocations": {
                    "signifikant": ["signifikanten Einfluss", "signifikante Veränderung", "signifikante Bedeutung",
                                   "signifikante Unterschiede", "signifikante Rolle", "signifikante Mengen"],
                    "einfluss": ["Einfuss auf", "großen Einfluss", "positiven Einfluss",
                                 "negativen Einfluss", "erheblichen Einfluss", "keinen Einfluss"],
                    "erreichen": ["Ziel erreichen", "Erfolg erreichen", "Zweck erreichen",
                                   "Ziel zu erreichen", "Ergebnis erreichen", "Spielplan erreichen"],
                    "beitragen": ["beitragen zu", "positiven Beitrag leisten", "signifikant beitragen",
                                  "zur Verbesserung beitragen", "zur Entwicklung beitragen"],
                    "bestimmen": ["Ergebnis bestimmen", "Ursache bestimmen", "Preis bestimmen",
                                 "Geschwindigkeit bestimmen", "Richtung bestimmen", "Wert bestimmen"],
                    "potenzial": ["Potenzial haben", "Potenzial erkennen", "Potenzial ausschöpfen",
                                  "größtes Potenzial", "hohes Potenzial", "langfristiges Potenzial"],
                    "perspektive": ["aus Perspektive", "andere Perspektive", "neue Perspektive",
                                    "eigene Perspektive", "kritische Perspektive"],
                    "analysieren": ["Daten analysieren", "Situation analysieren", "Problem analysieren",
                                   "Resultat analysieren", "Trend analysieren", "Markt analysieren"],
                    "evaluieren": ["Leistung evaluieren", "Optionen evaluieren", "Qualität evaluieren",
                                   "Effektivität evaluieren", "Auswirkungen evaluieren"],
                    "etablieren": ["Beziehung etablieren", "Regel etablieren", "System etablieren",
                                   "Verbindung etablieren", "Reputation etablieren"],
                    "erhalten": ["Gleichgewicht erhalten", "Beziehung erhalten", "Qualität erhalten",
                                  "Standard erhalten", "Fokus erhalten", "Integrität erhalten"],
                    "transformieren": ["in etwas transformieren", "Prozess transformieren", "Branche transformieren",
                                       "Geschäft transformieren", "Technologie transformieren"],
                    "fördern": ["Entwicklung fördern", "Produkt fördern", "Wachstum fördern",
                                 "Verständnis fördern", "Zusammenarbeit fördern"],
                    "realisieren": ["Ziel realisieren", "Traum realisieren", "Potenzial realisieren",
                                     "Fehler realisieren", "Gelegenheit realisieren"],
                    "reduzieren": ["Kosten reduzieren", "Risiko reduzieren", "Abfall reduzieren",
                                   "Zeit reduzieren", "Auswirkungen reduzieren"],
                    "reflektieren": ["über etwas reflektieren", "Situation reflektieren", "Veränderung reflektieren",
                                     "Trend reflektieren", "Haltung reflektieren"],
                    "unterstützen": ["Entscheidung unterstützen", "Unterstützung leisten", "Idee unterstützen",
                                     "Projekt unterstützen", "Entwicklung unterstützen"],
                    "auswirkung": ["Auswirkung haben", "signifikante Auswirkung", "positive Auswirkung",
                                   "negative Auswirkung", "langfristige Auswirkung"],
                    "konzentrieren": ["sich auf etwas konzentrieren", "Aufmerksamkeit konzentrieren",
                                      "Anstrengung konzentrieren", "Ressource konzentrieren"],
                    "explorieren": ["Optionen explorieren", "Möglichkeiten explorieren", "Markt explorieren",
                                     "Gelegenheiten explorieren", "Ansatz explorieren"],
                },
                "synonyms": {
                    "signifikant": ["bemerkenswert", "wesentlich", "substantiell", "beträchtlich", "wichtig"],
                    "einfluss": ["auswirkung", "effekt", "beeinflussung", "gestaltung", "bestimmung"],
                    "erreichen": ["erlangen", "erreichen", "erhalten", "verwirklichen", "realisieren"],
                    "beitragen": ["beisteuern", "mitwirken", "helfen", "unterstützen", "kombinieren"],
                    "bestimmen": ["festlegen", "bestimmen", "einflussen", "definieren", "etablieren"],
                    "potenzial": ["möglichkeit", "kapazität", "fähigkeit", "potential", "gelegenheit"],
                    "perspektive": ["ansicht", "aussicht", "standpunkt", "winkel", "ansatz"],
                    "analysieren": ["untersuchen", "studieren", "bewerten", "abschätzen", "prüfen"],
                    "evaluieren": ["bewerten", "urteilen", "messen", "abschätzen", "prüfen"],
                    "etablieren": ["schaffen", "aufbauen", "einrichten", "gründen", "entwickeln"],
                    "erhalten": ["halten", "bewahren", "aufrechterhalten", "fortsetzen", "beibehalten"],
                    "transformieren": ["verändern", "umwandeln", "ändern", "überarbeiten", "modifizieren"],
                    "fördern": ["begünstigen", "unterstützen", "steigern", "vorantreiben", "verbessern"],
                    "realisieren": ["verwirken", "erreichen", "erfüllen", "verstehen", "erkennen"],
                    "reduzieren": ["verringern", "senken", "kürzen", "vermindern", "minimieren"],
                    "reflektieren": ["zeigen", "demonstrieren", "anzeigen", "offenbaren", "spiegeln"],
                    "unterstützen": ["stützen", "unterstützen", "helfen", "befürworten", "verfechten"],
                    "auswirkung": ["einfluss", "effekt", "wirkung", "änderung", "umwandlung"],
                    "konzentrieren": ["sich konzentrieren", "zusammenfassen", "richten", "zielen", "priorisieren"],
                    "explorieren": ["untersuchen", "prüfen", "studieren", "forschen", "entdecken"],
                },
                "word_families": {
                    "signifikant": ["signifikant", "signifikant", "signifikanz", "signifikant"],
                    "einfluss": ["einfluss", "einflussreich", "einflussreich"],
                    "erreichen": ["erreichen", "erreichung", "erreichbar", "erreicht"],
                    "beitragen": ["beitragen", "beitrag", "beitragend", "beiträger"],
                    "bestimmen": ["bestimmen", "bestimmung", "bestimmt", "bestimmend"],
                    "potenzial": ["potenzial", "potenziell", "potenzieren"],
                    "perspektive": ["perspektive", "perspektivisch", "perspektivisch"],
                    "analysieren": ["analysieren", "analyse", "analytisch", "analytisch"],
                    "evaluieren": ["evaluieren", "evaluation", "evaluativ", "evaluator"],
                    "etablieren": ["etablieren", "etablierung", "etabliert"],
                    "erhalten": ["erhalten", "erhaltung", "erhaltbar", "erhalten"],
                    "transformieren": ["transformieren", "transformation", "transformativ", "transformator"],
                    "fördern": ["fördern", "förderung", "förderlich", "förderer"],
                    "realisieren": ["realisieren", "realisierung", "realisierbar", "realisiert"],
                    "reduzieren": ["reduzieren", "reduktion", "reduktiv", "reduziert"],
                    "reflektieren": ["reflektieren", "reflexion", "reflektierend", "reflektierend"],
                    "unterstützen": ["unterstützen", "unterstützend", "unterstützend", "unterstützer"],
                    "auswirkung": ["auswirkung", "auswirkend", "auswirkend"],
                    "konzentrieren": ["konzentrieren", "konzentriert", "konzentrierend", "konzentriert"],
                    "explorieren": ["explorieren", "exploration", "explorativ", "explorer"],
                },
                "formal_alternatives": {
                    "cool": "impressiv / bemerkenswert", "typ": "person / einzelne",
                    "ding": "objekt / sache", "sache": "angelegenheit / aspekt",
                    "geil": "fantastisch / hervorragend", "mega": "extrem / sehr",
                    "krasse": "extreme / außergewöhnliche", "freund": "kollege / mitarbeiter",
                    "kumpel": "kollege / mitarbeiter", "alter": "herr / gentleman",
                    "bruder": "freund / kollege", "hammer": "exzellent / hervorragend",
                    "klasse": "exzellent / hervorragend", "top": "optimal / erstklassig",
                    "naja": "nun / ja", "halt": "einfach / gerade",
                    "mal": "einmal / kurz", "eben": "einfach / gerade",
                    "einfach": "schlicht / einfach", "so": "also / daher"
                }
            },
            "fr": {
                "oral_markers": ["eh", "ben", "alors", "donc", "mais", "bon",
                                "voilà", "hein", "tu sais", "genre", "quoi",
                                "salut", "au revoir", "merci", "s'il vous plaît",
                                "excusez-moi", "pardon", "ah", "oh", "ah bon",
                                "vous savez", "je pense", "je crois", "en fait",
                                "finalement", "en effet", "effectivement"],
                "contractions": {
                    "d'accord": "d'accord", "c'est": "ce est", "j'ai": "je ai",
                    "on va": "on va", "qu'est-ce": "qu'est-ce", "t'es": "tu es",
                    "j'suis": "je suis", "t'as": "tu as", "il a": "il a",
                    "elle a": "elle a", "nous avons": "nous avons", "vous avez": "vous avez",
                    "ils ont": "ils ont", "elles ont": "elles ont", "j'me": "je me",
                    "t'te": "tu te", "s'est": "se est", "nous nous": "nous nous",
                    "vous vous": "vous vous", "sont": "sont", "d'un": "de un",
                    "d'une": "de une", "d'le": "de le", "d'les": "de les",
                    "qu'est-ce que": "qu'est-ce que", "qu'est-ce qui": "qu'est-ce qui",
                    "ne...pas": "ne pas", "ne...plus": "ne plus", "ne...jamais": "ne jamais",
                    "n'est-ce pas": "n'est-ce pas", "non plus": "non plus",
                    "si": "si", "mais si": "mais si", "ah bon": "ah bon",
                    "ah oui": "ah oui", "ah non": "ah non", "et puis": "et puis",
                    "donc": "donc", "alors": "alors", "mais": "mais", "ou": "ou",
                    "et": "et", "donc": "donc", "mais": "mais", "ou": "ou"
                },
                "informal_words": ["super", "génial", "cool", "top", "sympa",
                                  "truc", "machin", "gars", "meuf", "mon pote",
                                  "copain", "copine", "ami", "amie", "frère",
                                  "soeur", "bonhomme", "type", "personne", "grosse",
                                  "mince", "drôle", "rigolo", "mignon", "chouette"],
                "oral_patterns": [
                    (r"Bon,", "开场白"), (r"Alors,", "开场白"),
                    (r"Donc,", "结论"), (r"Voilà", "总结"),
                    (r"Tu sais", "填充"), (r"Genre", "举例"),
                    (r"Quoi", "语气词"), (r"Ben", "语气词"),
                    (r"En fait", "事实上"), (r"Finalement", "最终"),
                    (r"Ah bon", "惊讶"), (r"Ah oui", "理解"),
                    (r"Ah non", "否定"), (r"Vous savez", "填充"),
                    (r"Je pense", "表达"), (r"Je crois", "推测"),
                    (r"En effet", "确认"), (r"Effectivement", "确认"),
                    (r"Tout à fait", "完全同意"), (r"Pas du tout", "完全否定"),
                    (r"Je ne sais pas", "不知道"), (r"Je ne sais plus", "忘记"),
                    (r"Je comprends", "理解"), (r"Je vois", "明白"),
                    (r"Ça va", "问候"), (r"Comment ça va", "问候"),
                    (r"Très bien", "很好"), (r"Pas mal", "不错"),
                    (r"Comme ci comme ça", "马马虎虎"), (r"Bof", "一般"),
                    (r"C'est bon", "好了"), (r"C'est fini", "结束")
                ],
                "complex_patterns": [
                    (r"C'est .+ que", "强调句型"), (r"Il y a .+", "存在句型"),
                    (r"Le fait que", "名词从句"), (r"Alors que", "对比"),
                    (r"Bien que", "让步"), (r"Parce que", "原因"),
                    (r"Afin de", "目的"), (r"Pour que", "目的从句"),
                    (r"Lorsque", "时间"), (r"Si .+ ,", "条件"),
                    (r"La raison pour laquelle", "原因句型"),
                    (r"Il semble que", "推测句型"),
                    (r"Non seulement .+ mais aussi", "并列强调"),
                    (r"Avant de", "目的状语"),
                    (r"Pendant que", "对比状语"),
                    (r"Jusqu'à ce que", "时间状语"),
                    (r"Dès que", "时间状语"),
                    (r"De sorte que", "目的状语"),
                    (r"De manière à ce que", "目的状语"),
                    (r"De façon à ce que", "目的状语"),
                    (r"En sorte que", "目的状语"),
                    (r"Si bien que", "结果状语"),
                    (r"Tant que", "条件状语"),
                    (r"Pourvu que", "条件状语"),
                    (r"À condition que", "条件状语"),
                    (r"Supposé que", "条件状语"),
                    (r"En admettant que", "条件状语"),
                    (r"Quand même", "让步"),
                    (r"Encore que", "让步"),
                    (r"Malgré que", "让步"),
                    (r"Nonobstant que", "让步"),
                    (r"Quant à", "关于"),
                    (r"En ce qui concerne", "关于"),
                    (r"Concernant", "关于"),
                    (r"Relativement à", "关于")
                ],
                "collocations": {
                    "significatif": ["impact significatif", "changement significatif", "importance significative",
                                   "différence significative", "rôle significatif", "montant significatif"],
                    "influence": ["avoir une influence sur", "grande influence", "influence positive",
                                 "influence négative", "influence considérable", "aucune influence"],
                    "atteindre": ["atteindre un objectif", "atteindre le succès", "atteindre un but",
                                   "atteindre un niveau", "atteindre un résultat", "atteindre un record"],
                    "contribuer": ["contribuer à", "faire une contribution", "contribuer significativement",
                                  "contribuer à l'amélioration", "contribuer au développement"],
                    "déterminer": ["déterminer le résultat", "déterminer la cause", "déterminer le prix",
                                 "déterminer la vitesse", "déterminer la direction", "déterminer la valeur"],
                    "potentiel": ["avoir du potentiel", "reconnaître le potentiel", "exploiter le potentiel",
                                  "maximum de potentiel", "haut potentiel", "potentiel à long terme"],
                    "perspective": ["dans une perspective", "autre perspective", "nouvelle perspective",
                                    "propre perspective", "perspective critique"],
                    "analyser": ["analyser des données", "analyser une situation", "analyser un problème",
                                   "analyser un résultat", "analyser une tendance", "analyser un marché"],
                    "évaluer": ["évaluer une performance", "évaluer des options", "évaluer une qualité",
                                   "évaluer une efficacité", "évaluer des impacts"],
                    "établir": ["établir une relation", "établir une règle", "établir un système",
                                   "établir une connexion", "établir une réputation"],
                    "maintenir": ["maintenir un équilibre", "maintenir une relation", "maintenir une qualité",
                                  "maintenir un standard", "maintenir un focus", "maintenir une intégrité"],
                    "transformer": ["transformer en quelque chose", "transformer un processus", "transformer une industrie",
                                       "transformer une entreprise", "transformer une technologie"],
                    "promouvoir": ["promouvoir le développement", "promouvoir un produit", "promouvoir la croissance",
                                 "promouvoir la compréhension", "promouvoir la collaboration"],
                    "réaliser": ["réaliser un objectif", "réaliser un rêve", "réaliser son potentiel",
                                     "réaliser une erreur", "réaliser une opportunité"],
                    "réduire": ["réduire les coûts", "réduire un risque", "réduire les déchets",
                                   "réduire le temps", "réduire les impacts"],
                    "refléter": ["refléter sur quelque chose", "refléter une situation", "refléter un changement",
                                     "refléter une tendance", "refléter une attitude"],
                    "soutenir": ["soutenir une décision", "apporter un soutien", "soutenir une idée",
                                     "soutenir un projet", "soutenir le développement"],
                    "impact": ["avoir un impact", "impact significatif", "impact positif",
                                   "impact négatif", "impact à long terme"],
                    "concentrer": ["se concentrer sur quelque chose", "concentrer l'attention",
                                      "concentrer les efforts", "concentrer les ressources"],
                    "explorer": ["explorer des options", "explorer des possibilités", "explorer un marché",
                                     "explorer des opportunités", "explorer une approche"],
                },
                "synonyms": {
                    "significatif": ["remarquable", "essentiel", "substantiel", "considérable", "important"],
                    "influence": ["impact", "effet", "influence", "détermination", "gestion"],
                    "atteindre": ["parvenir à", "obtenir", "acquérir", "réaliser", "conquérir"],
                    "contribuer": ["apporter", "participer", "aider", "soutenir", "collaborer"],
                    "déterminer": ["fixer", "décider", "influencer", "définir", "établir"],
                    "potentiel": ["possibilité", "capacité", "aptitude", "potentialité", "opportunité"],
                    "perspective": ["point de vue", "vision", "approche", "angle", "orientation"],
                    "analyser": ["examiner", "étudier", "évaluer", "juger", "inspecter"],
                    "évaluer": ["juger", "apprécier", "mesurer", "estimer", "vérifier"],
                    "établir": ["créer", "construire", "organiser", "fondre", "développer"],
                    "maintenir": ["garder", "préserver", "soutenir", "continuer", "conserver"],
                    "transformer": ["changer", "convertir", "modifier", "réorganiser", "adapter"],
                    "promouvoir": ["encourager", "soutenir", "accélérer", "développer", "améliorer"],
                    "réaliser": ["concrétiser", "atteindre", "accomplir", "comprendre", "reconnaître"],
                    "réduire": ["diminuer", "baisser", "rétrécir", "limiter", "minimiser"],
                    "refléter": ["montrer", "démontrer", "indiquer", "révéler", "mirror"],
                    "soutenir": ["appuyer", "soutenir", "aider", "défendre", "promouvoir"],
                    "impact": ["influence", "effet", "conséquence", "changement", "transformation"],
                    "concentrer": ["se focaliser", "rassembler", "diriger", "prioriser", "centrer"],
                    "explorer": ["investiguer", "examiner", "étudier", "chercher", "découvrir"],
                },
                "word_families": {
                    "significatif": ["significatif", "signification", "signifier", "signifiant"],
                    "influence": ["influence", "influent", "influençant"],
                    "atteindre": ["atteindre", "atteinte", "atteignable", "atteint"],
                    "contribuer": ["contribuer", "contribution", "contribuant", "contributeur"],
                    "déterminer": ["déterminer", "détermination", "déterminé", "déterminant"],
                    "potentiel": ["potentiel", "potentiellement", "potencialiser"],
                    "perspective": ["perspective", "perspectif", "perspective"],
                    "analyser": ["analyser", "analyse", "analytique", "analyste"],
                    "évaluer": ["évaluer", "évaluation", "évaluatif", "évaluateur"],
                    "établir": ["établir", "établissement", "établi"],
                    "maintenir": ["maintenir", "maintenance", "maintenable", "maintenu"],
                    "transformer": ["transformer", "transformation", "transformatif", "transformateur"],
                    "promouvoir": ["promouvoir", "promotion", "promouvant", "promoteur"],
                    "réaliser": ["réaliser", "réalisation", "réalisable", "réalisé"],
                    "réduire": ["réduire", "réduction", "réductif", "réduit"],
                    "refléter": ["refléter", "réflexion", "reflétant", "réflecteur"],
                    "soutenir": ["soutenir", "soutien", "soutien", "soutien"],
                    "impact": ["impact", "impactant", "impactant"],
                    "concentrer": ["concentrer", "concentration", "concentré", "concentré"],
                    "explorer": ["explorer", "exploration", "explorateur", "exploratoire"],
                },
                "formal_alternatives": {
                    "cool": "impressionnant / remarquable", "gars": "personne / individu",
                    "truc": "objet / chose", "machin": "élément / article",
                    "génial": "fantastique / excellent", "super": "très / extrêmement",
                    "sympa": "agréable / charmant", "copain": "ami / collègue",
                    "copine": "amie / collègue", "frère": "ami / associé",
                    "soeur": "amie / associée", "bonhomme": "homme / individu",
                    "type": "personne / individu", "personne": "individu / être humain",
                    "grosse": "importante / considérable", "mince": "petite / faible",
                    "drôle": "amusant / comique", "rigolo": "divertissant / amusant",
                    "mignon": "charmant / agréable", "chouette": "sympa / agréable",
                    "bon": "bien / acceptable", "mais": "cependant / néanmoins",
                    "donc": "par conséquent / ainsi", "alors": "donc / alors",
                    "eh": "ah / oh", "ben": "eh bien / maintenant",
                    "hein": "n'est-ce pas / non", "quoi": "n'est-ce pas / ou quoi",
                    "tu sais": "vous savez", "genre": "par exemple / comme",
                    "voilà": "voici / en voilà", "ah bon": "vraiment / oh"
                }
            },
            "es": {
                "oral_markers": ["eh", "bueno", "pues", "entonces", "pero",
                                "vamos", "o sea", "¿sabes?", "tipo", "carajo",
                                "hola", "adiós", "gracias", "por favor",
                                "disculpe", "lo siento", "ah", "oh", "ah bueno",
                                "usted sabe", "yo pienso", "yo creo", "en realidad",
                                "finalmente", "en efecto", "efectivamente"],
                "contractions": {
                    "del": "de el", "al": "a el", "d'onde": "de donde",
                    "pa": "para", "tú eres": "eres", "yo soy": "soy",
                    "tú tienes": "tienes", "yo tengo": "tengo",
                    "él tiene": "tiene", "ella tiene": "tiene",
                    "nosotros tenemos": "tenemos", "vosotros tenéis": "tenéis",
                    "ellos tienen": "tienen", "ellas tienen": "tienen",
                    "me": "me", "te": "te", "se": "se",
                    "nos": "nos", "os": "os", "se": "se",
                    "un": "un", "una": "una", "unos": "unos",
                    "unas": "unas", "lo": "lo", "la": "la",
                    "los": "los", "las": "las", "le": "le",
                    "les": "les", "se": "se", "no": "no",
                    "si": "si", "pero": "pero", "y": "y",
                    "o": "o", "que": "que", "quien": "quien",
                    "cual": "cual", "donde": "donde", "cuando": "cuando",
                    "como": "como", "porque": "porque", "aunque": "aunque",
                    "mientras": "mientras", "siempre": "siempre", "nunca": "nunca",
                    "tambien": "tambien", "ademas": "ademas", "pero": "pero",
                    "sin embargo": "sin embargo", "por lo tanto": "por lo tanto",
                    "así que": "así que", "entonces": "entonces"
                },
                "informal_words": ["guay", "genial", "chulo", "tío", "mola",
                                  "cosa", "asunto", "poco", "mucho", "tipo",
                                  "amigo", "amiga", "hermano", "hermana",
                                  "casa", "tiempo", "dinero", "trabajo", "vida",
                                  "bueno", "malo", "grande", "pequeño", "nuevo"],
                "oral_patterns": [
                    (r"Bueno,", "开场白"), (r"Pues,", "语气"),
                    (r"Entonces,", "连接"), (r"¿Sabes?", "填充"),
                    (r"O sea", "解释"), (r"Vamos", "提议"),
                    (r"En fin", "总结"), (r"De hecho", "事实上"),
                    (r"Como sea", "无论如何"), (r"Mejor dicho", "更准确地说"),
                    (r"Ah bueno", "惊讶"), (r"Ah si", "理解"),
                    (r"Ah no", "否定"), (r"Usted sabe", "填充"),
                    (r"Yo pienso", "表达"), (r"Yo creo", "推测"),
                    (r"En efecto", "确认"), (r"Efectivamente", "确认"),
                    (r"Totalmente", "完全同意"), (r"Para nada", "完全否定"),
                    (r"No sé", "不知道"), (r"No recuerdo", "忘记"),
                    (r"Entiendo", "理解"), (r"Veo", "明白"),
                    (r"¿Cómo estás?", "问候"), (r"Muy bien", "很好"),
                    (r"No mal", "不错"), (r"Así así", "马马虎虎"),
                    (r"Regular", "一般"), (r"Está bien", "好了"),
                    (r"Terminado", "结束"), (r"Listo", "准备好了")
                ],
                "complex_patterns": [
                    (r"Es .+ que", "强调"), (r"Hay .+", "存在"),
                    (r"El hecho de que", "名词从句"), (r"Aunque", "让步"),
                    (r"Porque", "原因"), (r"Para que", "目的"),
                    (r"Cuando", "时间"), (r"Si", "条件"),
                    (r"Mientras", "对比"), (r"Tan .+ que", "结果"),
                    (r"La razón por la que", "原因句型"),
                    (r"Parece que", "推测句型"),
                    (r"No solo .+ sino también", "并列强调"),
                    (r"Para", "目的状语"),
                    (r"Mientras tanto", "对比状语"),
                    (r"Hasta que", "时间状语"),
                    (r"En cuanto", "时间状语"),
                    (r"De modo que", "目的状语"),
                    (r"De manera que", "目的状语"),
                    (r"De forma que", "目的状语"),
                    (r"De tal modo que", "结果状语"),
                    (r"Con tal que", "条件状语"),
                    (r"A condición de que", "条件状语"),
                    (r"Suponiendo que", "条件状语"),
                    (r"Admitiendo que", "条件状语"),
                    (r"Incluso aunque", "让步"),
                    (r"Aun cuando", "让步"),
                    (r"A pesar de que", "让步"),
                    (r"No obstante", "让步"),
                    (r"Respecto a", "关于"),
                    (r"En cuanto a", "关于"),
                    (r"Con respecto a", "关于"),
                    (r"En lo que se refiere a", "关于")
                ],
                "collocations": {
                    "significativo": ["impacto significativo", "cambio significativo", "importancia significativa",
                                   "diferencia significativa", "rol significativo", "monto significativo"],
                    "influenciar": ["influenciar en", "gran influencia", "influencias positiva",
                                 "influencias negativa", "influencias considerable", "ninguna influencia"],
                    "alcanzar": ["alcanzar un objetivo", "alcanzar el éxito", "alcanzar un meta",
                                   "alcanzar un nivel", "alcanzar un resultado", "alcanzar un récord"],
                    "contribuir": ["contribuir a", "hacer una contribución", "contribuir significativamente",
                                  "contribuir a la mejora", "contribuir al desarrollo"],
                    "determinar": ["determinar el resultado", "determinar la causa", "determinar el precio",
                                 "determinar la velocidad", "determinar la dirección", "determinar el valor"],
                    "potencial": ["tener potencial", "reconocer el potencial", "explotar el potencial",
                                  "máximo potencial", "alto potencial", "potencial a largo plazo"],
                    "perspectiva": ["en una perspectiva", "otra perspectiva", "nueva perspectiva",
                                    "propia perspectiva", "perspectiva crítica"],
                    "analizar": ["analizar datos", "analizar una situación", "analizar un problema",
                                   "analizar un resultado", "analizar una tendencia", "analizar un mercado"],
                    "evaluar": ["evaluar un rendimiento", "evaluar opciones", "evaluar una calidad",
                                   "evaluar una efectividad", "evaluar impactos"],
                    "establecer": ["establecer una relación", "establecer una regla", "establecer un sistema",
                                   "establecer una conexión", "establecer una reputación"],
                    "mantener": ["mantener un equilibrio", "mantener una relación", "mantener una calidad",
                                  "mantener un estándar", "mantener un enfoque", "mantener una integridad"],
                    "transformar": ["transformar en algo", "transformar un proceso", "transformar una industria",
                                       "transformar una empresa", "transformar una tecnología"],
                    "promover": ["promover el desarrollo", "promover un producto", "promover el crecimiento",
                                 "promover la comprensión", "promover la colaboración"],
                    "realizar": ["realizar un objetivo", "realizar un sueño", "realizar el potencial",
                                     "realizar un error", "realizar una oportunidad"],
                    "reducir": ["reducir costos", "reducir un riesgo", "reducir residuos",
                                   "reducir tiempo", "reducir impactos"],
                    "reflejar": ["reflejar sobre algo", "reflejar una situación", "reflejar un cambio",
                                     "reflejar una tendencia", "reflejar una actitud"],
                    "soportar": ["soportar una decisión", "proporcionar apoyo", "soportar una idea",
                                     "soportar un proyecto", "soportar el desarrollo"],
                    "impacto": ["tener un impacto", "impacto significativo", "impacto positivo",
                                   "impacto negativo", "impacto a largo plazo"],
                    "concentrar": ["concentrarse en algo", "concentrar la atención",
                                      "concentrar esfuerzos", "concentrar recursos"],
                    "explorar": ["explorar opciones", "explorar posibilidades", "explorar un mercado",
                                     "explorar oportunidades", "explorar un enfoque"],
                },
                "synonyms": {
                    "significativo": ["notable", "esencial", "substancial", "considerable", "importante"],
                    "influenciar": ["impactar", "efecto", "influencia", "determinación", "gestión"],
                    "alcanzar": ["lograr", "obtener", "adquirir", "realizar", "conseguir"],
                    "contribuir": ["aportar", "participar", "ayudar", "soportar", "colaborar"],
                    "determinar": ["fijar", "decidir", "influir", "definir", "establecer"],
                    "potencial": ["posibilidad", "capacidad", "aptitud", "potencialidad", "oportunidad"],
                    "perspectiva": ["punto de vista", "visión", "enfoque", "ángulo", "orientación"],
                    "analizar": ["examinar", "estudiar", "evaluar", "juzgar", "inspeccionar"],
                    "evaluar": ["juzgar", "apreciar", "medir", "estimar", "verificar"],
                    "establecer": ["crear", "construir", "organizar", "fundar", "desarrollar"],
                    "mantener": ["mantener", "preservar", "soportar", "continuar", "conservar"],
                    "transformar": ["cambiar", "convertir", "modificar", "reorganizar", "adaptar"],
                    "promover": ["fomentar", "soportar", "acelerar", "desarrollar", "mejorar"],
                    "realizar": ["concretizar", "alcanzar", "cumplir", "comprender", "reconocer"],
                    "reducir": ["disminuir", "bajar", "reducir", "limitar", "minimizar"],
                    "reflejar": ["mostrar", "demostrar", "indicar", "revelar", "espejar"],
                    "soportar": ["apoyar", "soportar", "ayudar", "defender", "promover"],
                    "impacto": ["influencia", "efecto", "consecuencia", "cambio", "transformación"],
                    "concentrar": ["enfocarse", "reunir", "dirigir", "priorizar", "centrar"],
                    "explorar": ["investigar", "examinar", "estudiar", "buscar", "descubrir"],
                },
                "word_families": {
                    "significativo": ["significativo", "significación", "significar", "significativo"],
                    "influenciar": ["influenciar", "influyente", "influyendo"],
                    "alcanzar": ["alcanzar", "alcanzado", "alcanzable", "alcanzado"],
                    "contribuir": ["contribuir", "contribución", "contribuyendo", "contribuidor"],
                    "determinar": ["determinar", "determinación", "determinado", "determinante"],
                    "potencial": ["potencial", "potencialmente", "potencializar"],
                    "perspectiva": ["perspectiva", "perspectiva", "perspectiva"],
                    "analizar": ["analizar", "análisis", "analítico", "analista"],
                    "evaluar": ["evaluar", "evaluación", "evaluativo", "evaluador"],
                    "establecer": ["establecer", "establecimiento", "establecido"],
                    "mantener": ["mantener", "mantenimiento", "manteniendo", "mantenido"],
                    "transformar": ["transformar", "transformación", "transformador", "transformando"],
                    "promover": ["promover", "promoción", "promoviendo", "promotor"],
                    "realizar": ["realizar", "realización", "realizable", "realizado"],
                    "reducir": ["reducir", "reducción", "reductivo", "reducido"],
                    "reflejar": ["reflejar", "reflexión", "reflejando", "reflectante"],
                    "soportar": ["soportar", "soporte", "soportando", "soporte"],
                    "impacto": ["impacto", "impactando", "impactante"],
                    "concentrar": ["concentrar", "concentración", "concentrado", "concentrando"],
                    "explorar": ["explorar", "exploración", "explorador", "explorando"],
                },
                "formal_alternatives": {
                    "guay": "impresionante / notable", "tío": "persona / individuo",
                    "cosa": "objeto / asunto", "chulo": "atractivo / interesante",
                    "genial": "fantástico / excelente", "mola": "es genial / es interesante",
                    "poco": "poca / escasa", "mucho": "mucha / abundante",
                    "tipo": "persona / tipo de", "amigo": "compañero / colega",
                    "amiga": "compañera / colega", "hermano": "compañero / asociado",
                    "hermana": "compañera / asociada", "casa": "residencia / domicilio",
                    "tiempo": "momento / período", "dinero": "recursos / fondos",
                    "trabajo": "empleo / labor", "vida": "existencia / vida cotidiana",
                    "bueno": "adecuado / satisfactorio", "malo": "insatisfactorio / deficiente",
                    "grande": "importante / considerable", "pequeño": "reducido / modesto",
                    "nuevo": "reciente / moderno", "pues": "por lo tanto / así que",
                    "entonces": "por consiguiente / así", "pero": "sin embargo / no obstante",
                    "eh": "ah / oh", "bueno": "por lo tanto / así que",
                    "¿sabes?": "usted sabe", "tipo": "por ejemplo / como",
                    "vamos": "procedamos / empecemos", "o sea": "es decir / esto es",
                    "ah bueno": "en efecto / de verdad", "ah si": "en efecto / sí"
                }
            },
            "zh": {
                "oral_markers": ["嗯", "啊", "哦", "嘛", "吧", "呢", "嘿",
                                "那个", "就是说", "其实", "然后", "真的"],
                "contractions": {},
                "informal_words": ["挺好", "不错", "厉害", "牛",
                                  "事儿", "东西", "家伙", "哥们儿",
                                  "棒棒的", "给力", "赞", "超", "巨"],
                "oral_patterns": [
                    (r"那个", "语气词"), (r"就是说", "解释"),
                    (r"其实", "转折"), (r"然后", "连接"),
                    (r"嗯", "思考"), (r"吧", "建议"),
                    (r"呢", "疑问"), (r"啊", "感叹"),
                    (r"真的", "强调"), (r"挺", "程度")
                ],
                "complex_patterns": [
                    (r"之所以是因为", "原因"), (r"如果那么", "条件"),
                    (r"虽然但是", "让步"), (r"不仅而且", "递进"),
                    (r"无论都", "条件"), (r"只要就", "条件"),
                    (r"因为所以", "因果"), (r"即使也", "让步"),
                    (r"与其不如", "选择"), (r"不是而是", "否定肯定"),
                    (r"一方面另一方面", "并列"), (r"总而言之", "总结"),
                    (r"换句话说", "重述"), (r"相比之下", "对比"),
                    (r"随着", "伴随"), (r"根据", "依据"),
                    (r"为了", "目的"), (r"由于", "原因"),
                    (r"通过", "方式"), (r"使得", "结果"),
                    (r"只要就", "条件"), (r"只有才", "条件"),
                    (r"除非否则", "条件"), (r"一旦就", "条件")
                ],
                "collocations": {
                    "显著": ["显著影响", "显著变化", "显著差异", "显著提高", "显著下降", "显著改善"],
                    "影响": ["产生影响", "重大影响", "积极影响", "消极影响", "深远影响", "造成影响"],
                    "实现": ["实现目标", "实现突破", "实现增长", "实现价值", "实现跨越", "实现发展"],
                    "贡献": ["做出贡献", "重要贡献", "积极贡献", "突出贡献", "贡献力量", "贡献智慧"],
                    "决定": ["决定因素", "决定作用", "决定意义", "决定方向", "决定成败", "决定命运"],
                    "潜力": ["发挥潜力", "挖掘潜力", "巨大潜力", "发展潜力", "市场潜力", "增长潜力"],
                    "视角": ["不同视角", "全新视角", "独特视角", "客观视角", "多角度", "宏观视角"],
                    "分析": ["分析问题", "分析数据", "分析趋势", "分析原因", "分析结果", "深入分析"],
                    "评估": ["评估效果", "评估风险", "评估价值", "评估能力", "评估方法", "综合评估"],
                    "建立": ["建立关系", "建立体系", "建立标准", "建立联系", "建立信任", "建立机制"],
                    "保持": ["保持稳定", "保持平衡", "保持优势", "保持联系", "保持专注", "保持创新"],
                    "转变": ["转变观念", "转变方式", "转变思路", "转变发展", "转型升级", "转变角色"],
                    "促进": ["促进发展", "促进合作", "促进交流", "促进增长", "促进改革", "促进创新"],
                    "认识": ["认识问题", "认识规律", "深刻认识", "充分认识", "提高认识", "重新认识"],
                    "减少": ["减少成本", "减少风险", "减少浪费", "减少污染", "减少差距", "减少负担"],
                    "反映": ["反映问题", "反映情况", "反映需求", "反映现实", "真实反映", "客观反映"],
                    "支持": ["支持发展", "支持创新", "支持改革", "提供支持", "大力支持", "积极支持"],
                    "冲击": ["受到冲击", "造成冲击", "巨大冲击", "市场冲击", "经济冲击", "社会冲击"],
                    "聚焦": ["聚焦问题", "聚焦目标", "聚焦发展", "聚焦重点", "聚焦核心", "聚焦需求"],
                    "探索": ["探索方法", "探索路径", "探索模式", "探索创新", "深入探索", "积极探索"],
                },
                "synonyms": {
                    "显著": ["明显", "突出", "重大", "重要", "巨大"],
                    "影响": ["作用", "效果", "后果", "效应", "冲击"],
                    "实现": ["达成", "完成", "取得", "达到", "兑现"],
                    "贡献": ["奉献", "付出", "出力", "助力", "支援"],
                    "决定": ["抉择", "选定", "裁定", "确定", "决策"],
                    "潜力": ["潜能", "潜质", "潜力", "前景", "潜力股"],
                    "视角": ["角度", "立场", "观点", "眼界", "视野"],
                    "分析": ["剖析", "解析", "研究", "探讨", "研判"],
                    "评估": ["评价", "估量", "估算", "衡量", "评定"],
                    "建立": ["构建", "创立", "创建", "设立", "组建"],
                    "保持": ["维持", "坚持", "保留", "持续", "维系"],
                    "转变": ["转换", "变更", "调整", "改革", "改造"],
                    "促进": ["推动", "带动", "激励", "助力", "助长"],
                    "认识": ["了解", "理解", "明白", "懂得", "领悟"],
                    "减少": ["降低", "削减", "缩减", "减轻", "压缩"],
                    "反映": ["体现", "表现", "映照", "折射", "映射"],
                    "支持": ["支撑", "援助", "拥护", "鼓励", "帮助"],
                    "冲击": ["震荡", "冲击", "影响", "打击", "挑战"],
                    "聚焦": ["集中", "专注", "瞄准", "对准", "聚焦"],
                    "探索": ["摸索", "探寻", "探寻", "研究", "考察"],
                },
                "word_families": {
                    "显著": ["显著", "显著地", "显著性", "显著差异"],
                    "影响": ["影响", "影响力", "影响因素", "受到影响"],
                    "实现": ["实现", "实现方式", "实现途径", "可实现"],
                    "贡献": ["贡献", "贡献率", "贡献者", "贡献度"],
                    "决定": ["决定", "决定性", "决定因素", "决策者"],
                    "潜力": ["潜力", "潜力股", "潜力巨大", "挖掘潜力"],
                    "视角": ["视角", "多角度", "视角独特", "换个视角"],
                    "分析": ["分析", "分析师", "分析方法", "分析报告"],
                    "评估": ["评估", "评估师", "评估标准", "评估体系"],
                    "建立": ["建立", "建立者", "建立过程", "建立机制"],
                    "保持": ["保持", "保持者", "保持状态", "保持稳定"],
                    "转变": ["转变", "转变过程", "转变方式", "转变观念"],
                    "促进": ["促进", "促进者", "促进作用", "促进发展"],
                    "认识": ["认识", "认识水平", "认识过程", "认识能力"],
                    "减少": ["减少", "减少量", "减少幅度", "减少成本"],
                    "反映": ["反映", "反映情况", "反映问题", "反映真实"],
                    "支持": ["支持", "支持者", "支持力度", "支持体系"],
                    "冲击": ["冲击", "冲击力", "冲击波", "受冲击"],
                    "聚焦": ["聚焦", "聚焦点", "聚焦目标", "聚焦核心"],
                    "探索": ["探索", "探索者", "探索精神", "探索创新"],
                },
                "formal_alternatives": {
                    "挺好": "相当不错 / 令人满意", "厉害": "出色 / 卓越",
                    "牛": "出色 / 卓越", "事儿": "事情 / 事项",
                    "东西": "物品 / 事物", "家伙": "人 / 个体",
                    "哥们儿": "朋友 / 同事", "棒棒的": "出色 / 优秀",
                    "给力": "有效 / 出色", "赞": "优秀 / 极好",
                    "超": "非常 / 极其", "巨": "非常 / 极其",
                    "那个": "那个 / 那个事物", "就是说": "也就是说",
                    "其实": "实际上", "然后": "接着 / 随后",
                    "真的": "确实 / 的确", "挺": "相当 / 较为"
                }
            },
            "ja": {
                "oral_markers": ["えー", "あの", "えっと", "まあ", "ね",
                                "よ", "ぜ", "な", "さ", "って"],
                "contractions": {},
                "informal_words": ["すごい", "めちゃくちゃ", "超", "最高",
                                  "これ", "それ", "あれ", "の", "のね"],
                "oral_patterns": [
                    (r"えー", "犹豫"), (r"あの", "犹豫"),
                    (r"えっと", "思考"), (r"まあ", "语气"),
                    (r"ね", "确认"), (r"よ", "强调"),
                    (r"な", "语气"), (r"さ", "语气"),
                    (r"って", "引用"), (r"ちょっと", "轻微")
                ],
                "complex_patterns": [
                    (r"のは", "主题"), (r"のが", "主题"),
                    (r"けど", "转折"), (r"から", "原因"),
                    (r"ので", "原因"), (r"と", "条件"),
                    (r"ば", "条件"), (r"たら", "条件"),
                    (r"なら", "条件"), (r"まで", "范围")
                ],
                "collocations": {
                    "重要": ["重要な影響", "重要な変化", "重要な違い",
                             "重要な役割", "重要な問題", "重要な結果"],
                    "影響": ["影響を与える", "大きな影響", "積極的な影響",
                             "消極的な影響", "重要な影響", "影響がない"],
                    "達成": ["目標を達成", "成功を達成", "結果を達成",
                             "レベルを達成", "記録を達成"],
                    "貢献": ["貢献する", "貢献をする", "重要な貢献",
                             "改善に貢献", "発展に貢献"],
                    "決定": ["結果を決定", "原因を決定", "価格を決定",
                             "速度を決定", "方向を決定"],
                    "可能性": ["可能性がある", "可能性を認識", "可能性を活用",
                               "最大の可能性", "高い可能性", "長期的な可能性"],
                    "視点": ["視点から", "他の視点", "新しい視点",
                             "独自の視点", "批判的な視点"],
                    "分析": ["データを分析", "状況を分析", "問題を分析",
                             "結果を分析", "傾向を分析"],
                    "評価": ["パフォーマンスを評価", "選択肢を評価", "品質を評価",
                             "効果を評価"],
                    "確立": ["関係を確立", "ルールを確立", "システムを確立",
                             "接続を確立"],
                    "維持": ["均衡を維持", "関係を維持", "品質を維持",
                             "基準を維持"],
                    "変革": ["何かに変革", "プロセスを変革", "産業を変革",
                             "ビジネスを変革"],
                    "促進": ["発展を促進", "製品を促進", "成長を促進"],
                    "実現": ["目標を実現", "夢を実現", "可能性を実現"],
                    "削減": ["コストを削減", "リスクを削減", "廃棄物を削減"],
                    "反映": ["何かを反映", "状況を反映", "変化を反映"],
                    "支援": ["決定を支援", "支援を提供", "アイデアを支援"],
                    "影響": ["影響がある", "重要な影響", "積極的な影響"],
                    "集中": ["何かに集中", "注意力を集中"],
                    "探索": ["選択肢を探索", "可能性を探索", "市場を探索"],
                },
                "synonyms": {
                    "重要": ["重大", "大切", "不可欠", "主要", "鍵"],
                    "影響": ["効果", "作用", "結果", "変化", "波及"],
                    "達成": ["実現", "完成", "獲得", "達する", "達成"],
                    "貢献": ["寄与", "参加", "援助", "支援", "協力"],
                    "決定": ["判断", "選択", "確定", "定める", "規定"],
                    "可能性": ["機会", "能力", "資質", "見込み", "余地"],
                    "視点": ["見方", "立場", "観点", "角度", "視野"],
                    "分析": ["検討", "研究", "評価", "調査", "解析"],
                    "評価": ["判断", "見積もり", "測定", "検証", "評定"],
                    "確立": ["創設", "構築", "組織", "設立", "発展"],
                    "維持": ["保持", "保全", "継続", "維持", "保守"],
                    "変革": ["変化", "転換", "改変", "転換", "再編"],
                    "促進": ["推進", "支援", "加速", "発展", "改善"],
                    "実現": ["達成", "実行", "実施", "達成", "認識"],
                    "削減": ["減少", "低下", "制限", "最小化", "節減"],
                    "反映": ["表現", "示す", "反映", "表す", "映す"],
                    "支援": ["援助", "支持", "補助", "後援", "応援"],
                    "影響": ["効果", "結果", "影響", "変化", "変革"],
                    "集中": ["焦点", "収束", "優先", "中心", "集約"],
                    "探索": ["調査", "検証", "研究", "発見", "探検"],
                },
                "word_families": {
                    "重要": ["重要", "重要性", "重要な"],
                    "影響": ["影響", "影響力", "影響する"],
                    "達成": ["達成", "達成度", "達成可能"],
                    "貢献": ["貢献", "貢献度", "貢献者"],
                    "決定": ["決定", "決定的", "決定する"],
                    "可能性": ["可能性", "可能", "可能化"],
                    "視点": ["視点", "視点の", "視点から"],
                    "分析": ["分析", "分析者", "分析的"],
                    "評価": ["評価", "評価者", "評価的"],
                    "確立": ["確立", "確立された", "確立する"],
                    "維持": ["維持", "維持者", "維持可能"],
                    "変革": ["変革", "変革者", "変革する"],
                    "促進": ["促進", "促進者", "促進的"],
                    "実現": ["実現", "実現可能", "実現する"],
                    "削減": ["削減", "削減率", "削減する"],
                    "反映": ["反映", "反映度", "反映する"],
                    "支援": ["支援", "支援者", "支援的"],
                    "影響": ["影響", "影響的", "影響する"],
                    "集中": ["集中", "集中度", "集中する"],
                    "探索": ["探索", "探索者", "探索的"],
                },
                "formal_alternatives": {
                    "すごい": "非常に / 極めて", "めちゃくちゃ": "非常に / 極端に",
                    "超": "非常に / 極めて", "最高": "優れた / 素晴らしい",
                    "これ": "このもの", "それ": "そのもの",
                    "あれ": "あのもの", "の": "のです",
                    "のね": "ですね", "えー": "ええと",
                    "あの": "あの", "えっと": "ええと",
                    "まあ": "まあ / いまいち", "ね": "ですね",
                    "よ": "ですよ", "ぜ": "ですぜ",
                    "な": "ですね", "さ": "ですね",
                    "って": "という", "ちょっと": "少々"
                }
            },
            "ko": {
                "oral_markers": ["음", "아", "어", "오", "으음",
                                "그래", "그니까", "맞아", "아니"],
                "contractions": {},
                "informal_words": ["대박", "짱", "고마", "안녕",
                                  "이거", "저거", "그거", "거"],
                "oral_patterns": [
                    (r"음", "思考"), (r"아", "感叹"),
                    (r"어", "感叹"), (r"오", "惊讶"),
                    (r"그래", "同意"), (r"그니까", "解释"),
                    (r"맞아", "确认"), (r"아니", "否定"),
                    (r"근데", "转折"), (r"그래서", "所以")
                ],
                "complex_patterns": [
                    (r"는/은", "主题"), (r"이/가", "主格"),
                    (r"을/를", "宾格"), (r"에", "位置"),
                    (r"에서", "场所"), (r"으로/로", "工具"),
                    (r"와/과", "并列"), (r"이나/나", "选择"),
                    (r"보다", "比较"), (r"만", "限定")
                ],
                "collocations": {
                    "중요": ["중요한 영향", "중요한 변화", "중요한 차이",
                             "중요한 역할", "중요한 문제", "중요한 결과"],
                    "영향": ["영향을 미치다", "큰 영향", "긍정적인 영향",
                             "부정적인 영향", "중요한 영향", "영향이 없다"],
                    "달성": ["목표를 달성", "성공을 달성", "결과를 달성",
                             "수준을 달성", "기록을 달성"],
                    "기여": ["기여하다", "기여를 하다", "중요한 기여",
                             "개선에 기여", "발전에 기여"],
                    "결정": ["결과를 결정", "원인을 결정", "가격을 결정",
                             "속도를 결정", "방향을 결정"],
                    "가능성": ["가능성이 있다", "가능성을 인식", "가능성을 활용",
                               "최대 가능성", "높은 가능성", "장기적인 가능성"],
                    "시각": ["시각에서", "다른 시각", "새로운 시각",
                             "독자적인 시각", "비판적인 시각"],
                    "분석": ["데이터를 분석", "상황을 분석", "문제를 분석",
                             "결과를 분석", "추세를 분석"],
                    "평가": ["성과를 평가", "옵션을 평가", "품질을 평가",
                             "효과를 평가"],
                    "확립": ["관계를 확립", "규칙을 확립", "시스템을 확립",
                             "연결을 확립"],
                    "유지": ["균형을 유지", "관계를 유지", "품질을 유지",
                             "기준을 유지"],
                    "변화": ["뭔가에 변화", "프로세스를 변화", "산업을 변화",
                             "비즈니스를 변화"],
                    "촉진": ["발전을 촉진", "제품을 촉진", "성장을 촉진"],
                    "실현": ["목표를 실현", "꿈을 실현", "가능성을 실현"],
                    "감소": ["비용을 감소", "위험을 감소", "폐기물을 감소"],
                    "반영": ["뭔가를 반영", "상황을 반영", "변화를 반영"],
                    "지원": ["결정을 지원", "지원을 제공", "아이디어를 지원"],
                    "영향": ["영향이 있다", "중요한 영향", "긍정적인 영향"],
                    "집중": ["뭔가에 집중", "주의를 집중"],
                    "탐색": ["옵션을 탐색", "가능성을 탐색", "시장을 탐색"],
                },
                "synonyms": {
                    "중요": ["중대", "핵심", "필수", "주요", "중요"],
                    "영향": ["효과", "작용", "결과", "변화", "영향"],
                    "달성": ["실현", "완성", "획득", "도달", "성취"],
                    "기여": ["기부", "참여", "도움", "지원", "협력"],
                    "결정": ["판단", "선택", "확정", "규정", "결정"],
                    "가능성": ["기회", "능력", "자질", "전망", "여지"],
                    "시각": ["관점", "입장", "시점", "각도", "시야"],
                    "분석": ["검토", "연구", "평가", "조사", "해석"],
                    "평가": ["판단", "추정", "측정", "검증", "평가"],
                    "확립": ["설립", "구축", "조직", "창설", "발전"],
                    "유지": ["보존", "보호", "계속", "유지", "보수"],
                    "변화": ["변동", "전환", "개변", "전환", "재편"],
                    "촉진": ["추진", "지원", "가속", "발전", "개선"],
                    "실현": ["달성", "수행", "실시", "이행", "인식"],
                    "감소": ["감축", "하락", "제한", "최소화", "절감"],
                    "반영": ["표현", "보여주다", "반영", "나타내다", "비추다"],
                    "지원": ["원조", "지지", "보조", "후원", "응원"],
                    "영향": ["효과", "결과", "영향", "변화", "변혁"],
                    "집중": ["초점", "수렴", "우선", "중심", "집약"],
                    "탐색": ["조사", "검증", "연구", "발견", "탐험"],
                },
                "word_families": {
                    "중요": ["중요", "중요성", "중요한"],
                    "영향": ["영향", "영향력", "영향을 미치다"],
                    "달성": ["달성", "달성도", "달성 가능"],
                    "기여": ["기여", "기여도", "기여자"],
                    "결정": ["결정", "결정적인", "결정하다"],
                    "가능성": ["가능성", "가능하다", "가능화"],
                    "시각": ["시각", "시각의", "시각에서"],
                    "분석": ["분석", "분석가", "분석적"],
                    "평가": ["평가", "평가자", "평가적"],
                    "확립": ["확립", "확립된", "확립하다"],
                    "유지": ["유지", "유지자", "유지 가능"],
                    "변화": ["변화", "변화자", "변화하다"],
                    "촉진": ["촉진", "촉진자", "촉진적"],
                    "실현": ["실현", "실현 가능", "실현하다"],
                    "감소": ["감소", "감소율", "감소하다"],
                    "반영": ["반영", "반영도", "반영하다"],
                    "지원": ["지원", "지원자", "지원적"],
                    "영향": ["영향", "영향적", "영향을 미치다"],
                    "집중": ["집중", "집중도", "집중하다"],
                    "탐색": ["탐색", "탐색자", "탐색적"],
                },
                "formal_alternatives": {
                    "대박": "매우 / 극도로", "짱": "매우 / 극도로",
                    "고마": "감사합니다", "안녕": "안녕하세요",
                    "이거": "이것", "저거": "저것",
                    "그거": "그것", "거": "것",
                    "음": "음", "아": "아",
                    "어": "어", "오": "오",
                    "으음": "음", "그래": "그렇습니다",
                    "그니까": "그러니까", "맞아": "맞습니다",
                    "아니": "아니요", "근데": "그러나",
                    "그래서": "그래서"
                }
            },
            "ru": {
                "oral_markers": ["ну", "в общем", "типа", "вот", "да",
                                "нет", "ага", "хорошо", "нужно",
                                "привет", "пока", "спасибо", "пожалуйста",
                                "извини", "простите", "ах", "о", "ну да",
                                "ты знаешь", "я думаю", "я считаю", "на самом деле",
                                "в итоге", "даже", "всё же", "ещё"],
                "contractions": {
                    "ну": "ну", "да": "да", "нет": "нет", "ага": "ага",
                    "хорошо": "хорошо", "нужно": "нужно", "можно": "можно",
                    "бы": "бы", "же": "же", "всё": "всё", "ещё": "ещё",
                    "уж": "уж", "всё же": "всё же", "даже": "даже",
                    "как бы": "как бы", "что бы": "что бы", "если бы": "если бы",
                    "хотя бы": "хотя бы", "даже бы": "даже бы", "только бы": "только бы",
                    "ни": "ни", "ни то": "ни то", "ни это": "ни это",
                    "никогда": "никогда", "нигде": "нигде", "ничто": "ничто",
                    "ни один": "ни один", "ничего": "ничего", "нисколько": "нисколько",
                    "очень": "очень", "крайне": "крайне", "чрезвычайно": "чрезвычайно",
                    "довольно": "довольно", "достаточно": "достаточно", "больше": "больше",
                    "меньше": "меньше", "лучше": "лучше", "хуже": "хуже",
                    "раньше": "раньше", "позже": "позже", "ближе": "ближе",
                    "дальше": "дальше", "вперёд": "вперёд", "назад": "назад"
                },
                "informal_words": ["круто", "класс", "вещь", "штука",
                                  "человек", "ребята", "друг", "подруга",
                                  "брат", "сестра", "дом", "время",
                                  "деньги", "работа", "жизнь", "хорошо",
                                  "плохо", "большой", "маленький", "новый"],
                "oral_patterns": [
                    (r"Ну", "开场白"), (r"В общем", "总结"),
                    (r"Типа", "举例"), (r"Вот", "指向"),
                    (r"Да", "同意"), (r"Нет", "否定"),
                    (r"Ага", "确认"), (r"Хорошо", "同意"),
                    (r"Нужно", "需要"), (r"Можно", "可以"),
                    (r"Ну да", "确认"), (r"Ты знаешь", "填充"),
                    (r"Я думаю", "表达"), (r"Я считаю", "推测"),
                    (r"На самом деле", "事实上"), (r"В итоге", "最终"),
                    (r"Даже", "强调"), (r"Всё же", "转折"),
                    (r"Ещё", "补充"), (r"Итак", "总结"),
                    (r"В общем-то", "大体"), (r"Дело в том, что", "解释"),
                    (r"Проблема в том, что", "问题"), (r"Кстати", "顺便"),
                    (r"Например", "举例"), (r"То есть", "解释"),
                    (r"Иными словами", "换句话说"), (r"В общем", "总结"),
                    (r"Конечно", "当然"), (r"Нет, конечно", "否定"),
                    (r"Давай", "提议"), (r"Пойдём", "提议"),
                    (r"Смотри", "提醒"), (r"Послушай", "注意")
                ],
                "complex_patterns": [
                    (r"что .+ ,", "定语从句"), (r"который", "关系代词"),
                    (r"если", "条件"), (r"хотя", "让步"),
                    (r"поскольку", "原因"), (r"чтобы", "目的"),
                    (r"когда", "时间"), (r"пока", "直到"),
                    (r"как", "方式"), (r"что бы", "虚拟"),
                    (r"Причина в том, что", "原因句型"),
                    (r"Похоже, что", "推测句型"),
                    (r"Не только .+ но и", "并列强调"),
                    (r"Для того чтобы", "目的状语"),
                    (r"В то время как", "对比状语"),
                    (r"До тех пор пока", "时间状语"),
                    (r"С того момента как", "时间状语"),
                    (r"Так что", "目的状语"),
                    (r"То есть", "目的状语"),
                    (r"Иными словами", "目的状语"),
                    (r"Так что бы", "结果状语"),
                    (r"При условии что", "条件状语"),
                    (r"Если бы", "条件状语"),
                    (r"Предположим что", "条件状语"),
                    (r"Даже если", "让步"),
                    (r"Хотя и", "让步"),
                    (r"Несмотря на то что", "让步"),
                    (r"Однако", "让步"),
                    (r"Относительно", "关于"),
                    (r"Что касается", "关于"),
                    (r"В отношении", "关于"),
                    (r"К вопросу о", "关于")
                ],
                "collocations": {
                    "значительный": ["значительный impacto", "значительный changement", "значительная importance",
                                   "значительная difference", "значительная роль", "значительный montant"],
                    "влияние": ["иметь влияние на", "большое влияние", "положительное влияние",
                                 "отрицательное влияние", "значительное влияние", "никакого влияния"],
                    "достичь": ["достичь цели", "достичь успеха", "достичь цели",
                                   "достичь уровня", "достичь результата", "достичь рекорда"],
                    "вносить": ["вносить вклад", "вносить свой вклад", "вносить значительный вклад",
                                  "вносить вклад в улучшение", "вносить вклад в развитие"],
                    "определять": ["определять результат", "определять причину", "определять цену",
                                 "определять скорость", "определять направление", "определять значение"],
                    "потенциал": ["иметь потенциал", "узнать потенциал", "использовать потенциал",
                                  "максимальный потенциал", "высокий потенциал", "долгосрочный потенциал"],
                    "перспектива": ["с точки зрения", "другая перспектива", "новая перспектива",
                                    "собственная перспектива", "критическая перспектива"],
                    "анализировать": ["анализировать данные", "анализировать ситуацию", "анализировать проблему",
                                   "анализировать результат", "анализировать тенденцию", "анализировать рынок"],
                    "оценивать": ["оценивать производительность", "оценивать варианты", "оценивать качество",
                                   "оценивать эффективность", "оценивать последствия"],
                    "устанавливать": ["устанавливать отношения", "устанавливать правила", "устанавливать систему",
                                   "устанавливать соединение", "устанавливать репутацию"],
                    "сохранять": ["сохранять равновесие", "сохранять отношения", "сохранять качество",
                                  "сохранять стандарт", "сохранять фокус", "сохранять целостность"],
                    "трансформировать": ["трансформировать в что-то", "трансформировать процесс", "трансформировать отрасль",
                                       "трансформировать бизнес", "трансформировать технологию"],
                    "способствовать": ["способствовать развитию", "способствовать продукту", "способствовать росту",
                                 "способствовать пониманию", "способствовать сотрудничеству"],
                    "реализовать": ["реализовать цель", "реализовать мечту", "реализовать потенциал",
                                     "реализовать ошибку", "реализовать возможность"],
                    "снижать": ["снижать затраты", "снижать риск", "снижать отходы",
                                   "снижать время", "снижать последствия"],
                    "отражать": ["отражать на что-то", "отражать ситуацию", "отражать изменение",
                                     "отражать тенденцию", "отражать позицию"],
                    "поддерживать": ["поддерживать решение", "оказывать поддержку", "поддерживать идею",
                                     "поддерживать проект", "поддерживать развитие"],
                    "влияние": ["иметь влияние", "значительное влияние", "положительное влияние",
                                   "отрицательное влияние", "долгосрочное влияние"],
                    "концентрироваться": ["концентрироваться на чем-то", "концентрировать внимание",
                                      "концентрировать усилия", "концентрировать ресурсы"],
                    "исследовать": ["исследовать варианты", "исследовать возможности", "исследовать рынок",
                                     "исследовать возможности", "исследовать подход"],
                },
                "synonyms": {
                    "значительный": ["заметный", "существенный", "важный", "большой", "ключевой"],
                    "влияние": ["воздействие", "эффект", "импакт", "роль", "уровень"],
                    "достичь": ["получить", "достичь", "обрести", "сделать", "осуществить"],
                    "вносить": ["приносить", "вкладывать", "добавлять", "вносить", "включать"],
                    "определять": ["устанавливать", "определять", "фиксировать", "выбирать", "решать"],
                    "потенциал": ["возможности", "качество", "способности", "ресурсы", "шанс"],
                    "перспектива": ["видение", "понимание", "положение", "направление", "обзор"],
                    "анализировать": ["изучать", "исследовать", "оценивать", "рассматривать", "проверять"],
                    "оценивать": ["оценивать", "анализировать", "считать", "определять", "проверять"],
                    "устанавливать": ["создавать", "формировать", "организовывать", "основывать", "развивать"],
                    "сохранять": ["держать", "охранять", "поддерживать", "продолжать", "консервовать"],
                    "трансформировать": ["изменять", "преобразовывать", "модифицировать", "реорганизовывать", "адаптировать"],
                    "способствовать": ["провоцировать", "поддерживать", "ускорять", "развивать", "улучшать"],
                    "реализовать": ["осуществить", "достичь", "выполнить", "понимать", "узнать"],
                    "снижать": ["уменьшать", "сокращать", "снижать", "ограничивать", "минимизировать"],
                    "отражать": ["показывать", "демонстрировать", "указывать", "раскрывать", "зеркалить"],
                    "поддерживать": ["держать", "поддерживать", "помогать", "защищать", "пропагандировать"],
                    "влияние": ["воздействие", "эффект", "результат", "изменение", "трансформация"],
                    "концентрироваться": ["сосредотачиваться", "собираться", "направляться", "приоритетизировать", "центрироваться"],
                    "исследовать": ["исследовать", "проверять", "изучать", "искать", "открывать"],
                },
                "word_families": {
                    "значительный": ["значительный", "значение", "значить", "значимый"],
                    "влияние": ["влияние", "влиятельный", "влияющий"],
                    "достичь": ["достичь", "достижение", "достижимый", "достигнутый"],
                    "вносить": ["вносить", "вклад", "вносящий", "вкладчик"],
                    "определять": ["определять", "определение", "определённый", "определяющий"],
                    "потенциал": ["потенциал", "потенциальный", "потенциализировать"],
                    "перспектива": ["перспектива", "перспективный", "перспективный"],
                    "анализировать": ["анализировать", "анализ", "аналитический", "аналитик"],
                    "оценивать": ["оценивать", "оценка", "оценочный", "оценщик"],
                    "устанавливать": ["устанавливать", "установка", "установленный"],
                    "сохранять": ["сохранять", "сохранение", "сохраняемый", "сохранённый"],
                    "трансформировать": ["трансформировать", "трансформация", "трансформационный", "трансформатор"],
                    "способствовать": ["способствовать", "способствование", "способствующий", "промотор"],
                    "реализовать": ["реализовать", "реализация", "реализуемый", "реализованный"],
                    "снижать": ["снижать", "снижение", "снижающий", "сниженный"],
                    "отражать": ["отражать", "отражение", "отражающий", "отражатель"],
                    "поддерживать": ["поддерживать", "поддержка", "поддерживающий", "партнёр"],
                    "влияние": ["влияние", "влияющий", "влияющий"],
                    "концентрироваться": ["концентрироваться", "концентрация", "концентрированный", "концентрирующий"],
                    "исследовать": ["исследовать", "исследование", "исследователь", "исследовательский"],
                },
                "formal_alternatives": {
                    "круто": "впечатляюще / замечательно", "класс": "высокое качество / превосходно",
                    "вещь": "объект / предмет", "штука": "вещь / изделие",
                    "человек": "человек / индивид", "ребята": "люди / коллеги",
                    "друг": "друг / товарищ", "подруга": "друг / товарищ",
                    "брат": "брат / коллега", "сестра": "сестра / коллега",
                    "дом": "дом / жильё", "время": "время / период",
                    "деньги": "деньги / ресурсы", "работа": "работа / деятельность",
                    "жизнь": "жизнь / существование", "хорошо": "удовлетворительно / хорошо",
                    "плохо": "неудовлетворительно / плохо", "большой": "значительный / обширный",
                    "маленький": "небольшой / компактный", "новый": "новый / современный",
                    "ну": "да / так", "да": "да / действительно",
                    "нет": "нет / не", "ага": "да / верно",
                    "ты знаешь": "ты знаешь", "типа": "например / как",
                    "вот": "вот / это", "нужно": "необходимо / требуется",
                    "можно": "можно / разрешено", "в общем": "в целом / итого"
                }
            },
            "it": {
                "oral_markers": ["eh", "beh", "allora", "quindi", "ma", "bene",
                                "ecco", "sai", "tipo", "che", "guarda",
                                "ciao", "arrivederci", "grazie", "per favore",
                                "scusa", "mi dispiace", "ah", "oh", "ah bene"],
                "contractions": {
                    "d'accordo": "d'accordo", "c'è": "ci è", "c'era": "ci era",
                    "c'erano": "ci erano", "c'è stato": "ci è stato",
                    "non è": "non è", "non sono": "non sono",
                    "l'ho": "lo ho", "l'ha": "lo ha", "l'hanno": "li hanno",
                    "d'ha": "di ha", "d'hanno": "di hanno",
                    "s'ha": "si ha", "s'hanno": "si hanno",
                    "m'ha": "mi ha", "ti ha": "ti ha", "ci ha": "ci ha",
                    "vi ha": "vi ha", "gli ha": "gli ha", "le ha": "le ha",
                    "mi sono": "mi sono", "ti sei": "ti sei", "si è": "si è",
                    "ci siamo": "ci siamo", "vi siete": "vi siete", "si sono": "si sono",
                    "d'altra parte": "d'altra parte", "d'un lato": "d'un lato",
                    "d'altro canto": "d'altro canto", "perciò": "perciò",
                    "pertanto": "pertanto", "quindi": "quindi", "dunque": "dunque",
                    "ecco perché": "ecco perché", "ecco come": "ecco come",
                    "ecco che": "ecco che", "ecco quello": "ecco quello",
                    "proprio": "proprio", "vero": "vero", "davvero": "davvero",
                    "abbastanza": "abbastanza", "molto": "molto", "poco": "poco",
                    "troppo": "troppo", "meno": "meno", "più": "più",
                    "quanto": "quanto", "quanta": "quanta", "quanti": "quanti",
                    "quante": "quante"
                },
                "informal_words": ["figo", "bellissimo", "super", "top", "carino",
                                  "cosa", "cose", "tipo", "ragazzo", "ragazza",
                                  "amico", "amica", "fratello", "sorella", "casa",
                                  "tempo", "soldi", "lavoro", "vita", "bene",
                                  "male", "grande", "piccolo", "nuovo", "vecchio"],
                "oral_patterns": [
                    (r"Bene,", "开场白"), (r"Allora,", "开场白"),
                    (r"Quindi,", "结论"), (r"Ecco", "总结"),
                    (r"Sai", "填充"), (r"Tipo", "举例"),
                    (r"Guarda", "提醒"), (r"Beh", "语气词"),
                    (r"In realtà", "事实上"), (r"Finalmente", "最终"),
                    (r"Ah bene", "惊讶"), (r"Ah si", "理解"),
                    (r"Ah no", "否定"), (r"Tu sai", "填充"),
                    (r"Io penso", "表达"), (r"Io credo", "推测"),
                    (r"Infatti", "确认"), (r"Effettivamente", "确认"),
                    (r"Assolutamente", "完全同意"), (r"Per niente", "完全否定"),
                    (r"Non so", "不知道"), (r"Non ricordo", "忘记"),
                    (r"Capisco", "理解"), (r"Vedo", "明白"),
                    (r"Come stai?", "问候"), (r"Molto bene", "很好"),
                    (r"Non male", "不错"), (r"Così così", "马马虎虎"),
                    (r"Regolare", "一般"), (r"È fatto", "好了")
                ],
                "complex_patterns": [
                    (r"È .+ che", "强调句型"), (r"C'è .+", "存在句型"),
                    (r"Il fatto che", "名词从句"), (r"Sebbene", "让步"),
                    (r"Perché", "原因"), (r"Per fare in modo che", "目的"),
                    (r"Quando", "时间"), (r"Se", "条件"),
                    (r"Mentre", "对比"), (r"Tanto .+ che", "结果"),
                    (r"La ragione per cui", "原因句型"),
                    (r"Sembra che", "推测句型"),
                    (r"Non solo .+ ma anche", "并列强调"),
                    (r"Per", "目的状语"),
                    (r"Mentre tanto", "对比状语"),
                    (r"Finché", "时间状语"),
                    (r"Appena", "时间状语"),
                    (r"In modo che", "目的状语"),
                    (r"In modo tale che", "结果状语"),
                    (r"A condizione che", "条件状语"),
                    (r"Supponendo che", "条件状语"),
                    (r"Anche se", "让步"),
                    (r"Nonostante", "让步"),
                    (r"In merito a", "关于"),
                    (r"Per quanto riguarda", "关于")
                ],
                "collocations": {
                    "significativo": ["impatto significativo", "cambio significativo", "importanza significativa",
                                   "differenza significativa", "ruolo significativo", "importo significativo"],
                    "influenza": ["avere un'influenza su", "grande influenza", "influenza positiva",
                                 "influenza negativa", "influenza considerevole", "nessuna influenza"],
                    "raggiungere": ["raggiungere un obiettivo", "raggiungere il successo", "raggiungere un livello",
                                   "raggiungere un risultato", "raggiungere un record"],
                    "contribuire": ["contribuire a", "fare un contributo", "contribuire significativamente",
                                  "contribuire all'ottimizzazione", "contribuire allo sviluppo"],
                    "determinare": ["determinare il risultato", "determinare la causa", "determinare il prezzo",
                                 "determinare la velocità", "determinare la direzione"],
                    "potenziale": ["avere potenziale", "riconoscere il potenziale", "sfruttare il potenziale",
                                  "massimo potenziale", "alto potenziale", "potenziale a lungo termine"],
                    "prospettiva": ["in una prospettiva", "altra prospettiva", "nuova prospettiva",
                                    "propria prospettiva", "prospettiva critica"],
                    "analizzare": ["analizzare dati", "analizzare una situazione", "analizzare un problema",
                                   "analizzare un risultato", "analizzare una tendenza"],
                    "valutare": ["valutare una performance", "valutare opzioni", "valutare una qualità",
                                   "valutare un'efficacia"],
                    "stabilire": ["stabilire una relazione", "stabilire una regola", "stabilire un sistema",
                                   "stabilire una connessione"],
                    "mantenere": ["mantenere un equilibrio", "mantenere una relazione", "mantenere una qualità",
                                  "mantenere uno standard"],
                    "trasformare": ["trasformare in qualcosa", "trasformare un processo", "trasformare un'industria",
                                       "trasformare un business"],
                    "promuovere": ["promuovere lo sviluppo", "promuovere un prodotto", "promuovere la crescita"],
                    "realizzare": ["realizzare un obiettivo", "realizzare un sogno", "realizzare il potenziale"],
                    "ridurre": ["ridurre i costi", "ridurre un rischio", "ridurre i rifiuti"],
                    "riflettere": ["riflettere su qualcosa", "riflettere una situazione", "riflettere un cambiamento"],
                    "supportare": ["supportare una decisione", "fornire supporto", "supportare un'idea"],
                    "impatto": ["avere un impatto", "impatto significativo", "impatto positivo"],
                    "concentrarsi": ["concentrarsi su qualcosa", "concentrare l'attenzione"],
                    "esplorare": ["esplorare opzioni", "esplorare possibilità", "esplorare un mercato"],
                },
                "synonyms": {
                    "significativo": ["notevole", "essenziale", "sostanziale", "considerabile", "importante"],
                    "influenza": ["impatto", "effetto", "influenza", "determinazione"],
                    "raggiungere": ["ottenere", "conseguire", "alcanzare", "realizzare"],
                    "contribuire": ["apportare", "partecipare", "aiutare", "supportare"],
                    "determinare": ["fissare", "decidere", "influenzare", "definire"],
                    "potenziale": ["possibilità", "capacità", "aptitudine", "opportunità"],
                    "prospettiva": ["punto di vista", "visione", "approccio", "angolazione"],
                    "analizzare": ["esaminare", "studiare", "valutare", "investigare"],
                    "valutare": ["giudicare", "apprezzare", "misurare", "verificare"],
                    "stabilire": ["creare", "costruire", "organizzare", "fondare"],
                    "mantenere": ["tenere", "preservare", "sostenere", "continuare"],
                    "trasformare": ["cambiare", "convertire", "modificare", "adattare"],
                    "promuovere": ["incoraggiare", "supportare", "accelerare", "migliorare"],
                    "realizzare": ["concretizzare", "raggiungere", "compiere", "riconoscere"],
                    "ridurre": ["diminuire", "abbassare", "limitare", "minimizzare"],
                    "riflettere": ["mostrare", "dimostrare", "indicare", "rivelare"],
                    "supportare": ["appoggiare", "assistere", "aiutare", "difendere"],
                    "impatto": ["influenza", "effetto", "conseguenza", "cambiamento"],
                    "concentrarsi": ["focalizzarsi", "raggruppare", "priorizzare", "centrarsi"],
                    "esplorare": ["investigare", "esaminare", "studiare", "scoprire"],
                },
                "word_families": {
                    "significativo": ["significativo", "significazione", "significare"],
                    "influenza": ["influenza", "influente", "influenzare"],
                    "raggiungere": ["raggiungere", "raggiungimento", "raggiungibile"],
                    "contribuire": ["contribuire", "contributo", "contributivo"],
                    "determinare": ["determinare", "determinazione", "determinato"],
                    "potenziale": ["potenziale", "potenzialmente", "potenziare"],
                    "prospettiva": ["prospettiva", "prospettico", "prospettivamente"],
                    "analizzare": ["analizzare", "analisi", "analitico"],
                    "valutare": ["valutare", "valutazione", "valutativo"],
                    "stabilire": ["stabilire", "stabilizzazione", "stabilito"],
                    "mantenere": ["mantenere", "mantenimento", "mantenibile"],
                    "trasformare": ["trasformare", "trasformazione", "trasformativo"],
                    "promuovere": ["promuovere", "promozione", "promozionale"],
                    "realizzare": ["realizzare", "realizzazione", "realizzabile"],
                    "ridurre": ["ridurre", "riduzione", "riduttivo"],
                    "riflettere": ["riflettere", "riflessione", "riflessivo"],
                    "supportare": ["supportare", "supporto", "supportivo"],
                    "impatto": ["impatto", "impattante", "impattare"],
                    "concentrarsi": ["concentrarsi", "concentrazione", "concentrato"],
                    "esplorare": ["esplorare", "esplorazione", "esplorativo"],
                },
                "formal_alternatives": {
                    "figo": "impressionante / notevole", "tipo": "persona / individuo",
                    "cosa": "oggetto / questione", "carino": "attraente / piacevole",
                    "super": "molto / estremamente", "top": "ottimo / eccellente",
                    "bellissimo": "fantastico / eccellente", "ragazzo": "giovane / persona",
                    "ragazza": "giovane / persona", "amico": "amico / collega",
                    "amica": "amica / collega", "fratello": "fratello / collega",
                    "sorella": "sorella / collega", "casa": "residenza / abitazione",
                    "tempo": "momento / periodo", "soldi": "risorse / fondi",
                    "lavoro": "occupazione / lavoro", "vita": "esistenza / vita quotidiana",
                    "bene": "adeguato / soddisfacente", "male": "insoddisfacente / negativo",
                    "grande": "importante / considerevole", "piccolo": "ridotto / modesto",
                    "nuovo": "recente / moderno", "vecchio": "antico / datato",
                    "beh": "ora / quindi", "allora": "quindi / pertanto",
                    "quindi": "perciò / quindi", "ecco": "ecco / questo è",
                    "sai": "tu sai", "tipo": "per esempio / come"
                }
            },
            "pt": {
                "oral_markers": ["eh", "bem", "então", "portanto", "mas", "bom",
                                "olha", "você sabe", "tipo", "que", "vamos",
                                "olá", "adeus", "obrigado", "por favor",
                                "desculpe", "sinto muito", "ah", "oh", "ah bom"],
                "contractions": {
                    "d'accordo": "concordo", "há": "há", "houve": "houve",
                    "houveram": "houveram", "será": "será", "serão": "serão",
                    "não é": "não é", "não são": "não são",
                    "l'hei": "lo hei", "l'ha": "lo ha", "l'hem": "os hem",
                    "d'ha": "de ha", "d'hem": "de hem",
                    "s'ha": "se ha", "s'hem": "se hem",
                    "m'ha": "me ha", "t'ha": "te ha", "n'ha": "nos ha",
                    "v'ha": "vos ha", "l'hes": "os hes", "l'hes": "as hes",
                    "me sinto": "me sinto", "te sentes": "te sentes", "se sente": "se sente",
                    "nos sentimos": "nos sentimos", "vos sentis": "vos sentis", "se sentem": "se sentem",
                    "por outro lado": "por outro lado", "por um lado": "por um lado",
                    "portanto": "portanto", "consequentemente": "consequentemente",
                    "assim que": "assim que", "logo que": "logo que",
                    "por isso": "por isso", "por causa disso": "por causa disso",
                    "é por isso que": "é por isso que", "é assim que": "é assim que",
                    "realmente": "realmente", "verdadeiramente": "verdadeiramente",
                    "bastante": "bastante", "muito": "muito", "pouco": "pouco",
                    "demais": "demais", "menos": "menos", "mais": "mais",
                    "quanto": "quanto", "quantos": "quantos", "quantas": "quantas"
                },
                "informal_words": ["legal", "maneiro", "top", "bacana", "legal",
                                  "coisa", "coisas", "tipo", "cara", "garota",
                                  "amigo", "amiga", "irmão", "irmã", "casa",
                                  "tempo", "dinheiro", "trabalho", "vida", "bom",
                                  "ruim", "grande", "pequeno", "novo", "velho"],
                "oral_patterns": [
                    (r"Bom,", "开场白"), (r"Então,", "开场白"),
                    (r"Portanto,", "结论"), (r"Olha", "总结"),
                    (r"Você sabe", "填充"), (r"Tipo", "举例"),
                    (r"Vamos", "提议"), (r"Bem", "语气词"),
                    (r"Na verdade", "事实上"), (r"Finalmente", "最终"),
                    (r"Ah bom", "惊讶"), (r"Ah sim", "理解"),
                    (r"Ah não", "否定"), (r"Você sabe", "填充"),
                    (r"Eu acho", "表达"), (r"Eu creio", "推测"),
                    (r"De fato", "确认"), (r"Efetivamente", "确认"),
                    (r"Totalmente", "完全同意"), (r"Para nada", "完全否定"),
                    (r"Não sei", "不知道"), (r"Não me lembro", "忘记"),
                    (r"Entendo", "理解"), (r"Vejo", "明白"),
                    (r"Como você está?", "问候"), (r"Muito bem", "很好"),
                    (r"Não mal", "不错"), (r"Mais ou menos", "马马虎虎"),
                    (r"Regular", "一般"), (r"Está feito", "好了")
                ],
                "complex_patterns": [
                    (r"É .+ que", "强调句型"), (r"Há .+", "存在句型"),
                    (r"O facto de que", "名词从句"), (r"Apesar de", "让步"),
                    (r"Porque", "原因"), (r"Para que", "目的"),
                    (r"Quando", "时间"), (r"Se", "条件"),
                    (r"Enquanto", "对比"), (r"Tão .+ que", "结果"),
                    (r"A razão pela qual", "原因句型"),
                    (r"Parece que", "推测句型"),
                    (r"Não só .+ mas também", "并列强调"),
                    (r"Para", "目的状语"),
                    (r"Enquanto isso", "对比状语"),
                    (r"Até que", "时间状语"),
                    (r"Assim que", "时间状语"),
                    (r"De modo que", "目的状语"),
                    (r"De forma que", "结果状语"),
                    (r"Na condição de que", "条件状语"),
                    (r"Suponha que", "条件状语"),
                    (r"Mesmo que", "让步"),
                    (r"Não obstante", "让步"),
                    (r"Em relação a", "关于"),
                    (r"Quanto a", "关于")
                ],
                "collocations": {
                    "significativo": ["impacto significativo", "mudança significativa", "importância significativa",
                                   "diferença significativa", "papel significativo", "valor significativo"],
                    "influência": ["ter uma influência em", "grande influência", "influência positiva",
                                 "influência negativa", "influência considerável", "nenhuma influência"],
                    "atingir": ["atingir um objetivo", "atingir o sucesso", "atingir um nível",
                                   "atingir um resultado", "atingir um recorde"],
                    "contribuir": ["contribuir para", "fazer uma contribuição", "contribuir significativamente",
                                  "contribuir para a melhoria", "contribuir para o desenvolvimento"],
                    "determinar": ["determinar o resultado", "determinar a causa", "determinar o preço",
                                 "determinar a velocidade", "determinar a direção"],
                    "potencial": ["ter potencial", "reconhecer o potencial", "exploitar o potencial",
                                  "máximo potencial", "alto potencial", "potencial de longo prazo"],
                    "perspectiva": ["em uma perspectiva", "outra perspectiva", "nova perspectiva",
                                    "própria perspectiva", "perspectiva crítica"],
                    "analisar": ["analisar dados", "analisar uma situação", "analisar um problema",
                                   "analisar um resultado", "analisar uma tendência"],
                    "avaliar": ["avaliar um desempenho", "avaliar opções", "avaliar uma qualidade",
                                   "avaliar uma eficácia"],
                    "estabelecer": ["estabelecer uma relação", "estabelecer uma regra", "estabelecer um sistema",
                                   "estabelecer uma conexão"],
                    "manter": ["manter um equilíbrio", "manter uma relação", "manter uma qualidade",
                                  "manter um padrão"],
                    "transformar": ["transformar em algo", "transformar um processo", "transformar uma indústria",
                                       "transformar um negócio"],
                    "promover": ["promover o desenvolvimento", "promover um produto", "promover o crescimento"],
                    "realizar": ["realizar um objetivo", "realizar um sonho", "realizar o potencial"],
                    "reduzir": ["reduzir custos", "reduzir um risco", "reduzir resíduos"],
                    "refletir": ["refletir sobre algo", "refletir uma situação", "refletir uma mudança"],
                    "suportar": ["suportar uma decisão", "fornecer suporte", "suportar uma ideia"],
                    "impacto": ["ter um impacto", "impacto significativo", "impacto positivo"],
                    "concentrar": ["concentrar-se em algo", "concentrar a atenção"],
                    "explorar": ["explorar opções", "explorar possibilidades", "explorar um mercado"],
                },
                "synonyms": {
                    "significativo": ["notável", "essencial", "substancial", "considerável", "importante"],
                    "influência": ["impacto", "efeito", "influência", "determinação"],
                    "atingir": ["alcançar", "conseguir", "atingir", "realizar"],
                    "contribuir": ["aportar", "participar", "ajudar", "suportar"],
                    "determinar": ["fixar", "decidir", "influenciar", "definir"],
                    "potencial": ["possibilidade", "capacidade", "aptidão", "oportunidade"],
                    "perspectiva": ["ponto de vista", "visão", "abordagem", "ângulo"],
                    "analisar": ["examinar", "estudar", "avaliar", "investigar"],
                    "avaliar": ["julgar", "apreciar", "medir", "verificar"],
                    "estabelecer": ["criar", "construir", "organizar", "fundar"],
                    "manter": ["manter", "preservar", "sustentar", "continuar"],
                    "transformar": ["mudar", "converter", "modificar", "adaptar"],
                    "promover": ["encorajar", "suportar", "acelerar", "melhorar"],
                    "realizar": ["concretizar", "alcançar", "cumprir", "reconhecer"],
                    "reduzir": ["diminuir", "baixar", "limitar", "minimizar"],
                    "refletir": ["mostrar", "demonstrar", "indicar", "revelar"],
                    "suportar": ["apoiar", "suportar", "ajudar", "defender"],
                    "impacto": ["influência", "efeito", "consequência", "mudança"],
                    "concentrar": ["focar", "reunir", "priorizar", "centrar"],
                    "explorar": ["investigar", "examinar", "estudar", "descobrir"],
                },
                "word_families": {
                    "significativo": ["significativo", "significação", "significar"],
                    "influência": ["influência", "influenciador", "influenciar"],
                    "atingir": ["atingir", "atingimento", "atingível"],
                    "contribuir": ["contribuir", "contribuição", "contributivo"],
                    "determinar": ["determinar", "determinação", "determinado"],
                    "potencial": ["potencial", "potencialmente", "potencializar"],
                    "perspectiva": ["perspectiva", "perspectivo", "perspectivamente"],
                    "analisar": ["analisar", "análise", "analítico"],
                    "avaliar": ["avaliar", "avaliação", "avaliativo"],
                    "estabelecer": ["estabelecer", "estabelecimento", "estabelecido"],
                    "manter": ["manter", "manutenção", "manutenível"],
                    "transformar": ["transformar", "transformação", "transformador"],
                    "promover": ["promover", "promoção", "promocional"],
                    "realizar": ["realizar", "realização", "realizável"],
                    "reduzir": ["reduzir", "redução", "redutivo"],
                    "refletir": ["refletir", "reflexão", "reflexivo"],
                    "suportar": ["suportar", "suporte", "suportivo"],
                    "impacto": ["impacto", "impactante", "impactar"],
                    "concentrar": ["concentrar", "concentração", "concentrado"],
                    "explorar": ["explorar", "exploração", "exploratório"],
                },
                "formal_alternatives": {
                    "legal": "impressionante / notável", "tipo": "pessoa / indivíduo",
                    "coisa": "objeto / questão", "bacana": "atraente / interessante",
                    "top": "ótimo / excelente", "maneiro": "fantástico / excelente",
                    "cara": "homem / pessoa", "garota": "mulher / pessoa",
                    "amigo": "amigo / colega", "amiga": "amiga / colega",
                    "irmão": "irmão / colega", "irmã": "irmã / colega",
                    "casa": "residência / moradia", "tempo": "momento / período",
                    "dinheiro": "recursos / fundos", "trabalho": "emprego / atividade",
                    "vida": "existência / vida cotidiana", "bom": "adequado / satisfatório",
                    "ruim": "insatisfatório / negativo", "grande": "importante / considerável",
                    "pequeno": "reduzido / modesto", "novo": "recente / moderno",
                    "velho": "antigo / desatualizado", "bem": "agora / então",
                    "então": "portanto / consequentemente", "portanto": "assim / portanto",
                    "olha": "veja / observe", "você sabe": "você sabe",
                    "tipo": "por exemplo / como"
                }
            },
            "nl": {
                "oral_markers": ["eh", "nou", "dus", "dan", "maar", "goed",
                                "kijk", "weet je", "zoals", "dat", "kom",
                                "hallo", "tot ziens", "dank je", "alsjeblieft",
                                "sorry", "excuses", "ah", "oh", "nou ja"],
                "contractions": {
                    "'k": "ik", "'t": "het", "'m": "hem", "'n": "een",
                    "'s": "des", "'r": "der", "'v": "van", "'d": "de",
                    "'t is": "het is", "'t was": "het was", "'t zal": "het zal",
                    "ik ben": "ik ben", "jij bent": "jij bent", "hij is": "hij is",
                    "zij is": "zij is", "wij zijn": "wij zijn", "jullie zijn": "jullie zijn",
                    "ze zijn": "ze zijn", "ik heb": "ik heb", "jij hebt": "jij hebt",
                    "hij heeft": "hij heeft", "zij heeft": "zij heeft", "wij hebben": "wij hebben",
                    "jullie hebben": "jullie hebben", "ze hebben": "ze hebben",
                    "ik doe": "ik doe", "jij doet": "jij doet", "hij doet": "hij doet",
                    "zij doet": "zij doet", "wij doen": "wij doen", "jullie doen": "jullie doen",
                    "ze doen": "ze doen", "dat is": "dat is", "dat was": "dat was",
                    "dat heeft": "dat heeft", "dat doet": "dat doet",
                    "die is": "die is", "die was": "die was", "die heeft": "die heeft",
                    "die doet": "die doet", "wat is": "wat is", "wat was": "wat was",
                    "wat heeft": "wat heeft", "wat doet": "wat doet",
                    "wie is": "wie is", "wie was": "wie was", "wie heeft": "wie heeft",
                    "wie doet": "wie doet", "waar is": "waar is", "waar was": "waar was",
                    "waar heeft": "waar heeft", "waar doet": "waar doet",
                    "wanneer is": "wanneer is", "wanneer was": "wanneer was",
                    "wanneer heeft": "wanneer heeft", "wanneer doet": "wanneer doet"
                },
                "informal_words": ["leuk", "super", "tof", "goed", "mooi",
                                  "ding", "zaak", "type", "kerel", "meisje",
                                  "vriend", "vriendin", "broer", "zus", "huis",
                                  "tijd", "geld", "werk", "leven", "goed",
                                  "slecht", "groot", "klein", "nieuw", "oud"],
                "oral_patterns": [
                    (r"Goed,", "开场白"), (r"Nou,", "开场白"),
                    (r"Dus,", "结论"), (r"Kijk", "总结"),
                    (r"Weet je", "填充"), (r"Zoals", "举例"),
                    (r"Kom", "提议"), (r"Nou ja", "语气词"),
                    (r"In feite", "事实上"), (r"Uiteindelijk", "最终"),
                    (r"Ah", "惊讶"), (r"O", "理解"),
                    (r"Nee", "否定"), (r"Weet je", "填充"),
                    (r"Ik denk", "表达"), (r"Ik geloof", "推测"),
                    (r"Inderdaad", "确认"), (r"Eigenlijk", "确认"),
                    (r"Absoluut", "完全同意"), (r"Geen enkele", "完全否定"),
                    (r"Ik weet niet", "不知道"), (r"Ik herinner me niet", "忘记"),
                    (r"Ik begrijp", "理解"), (r"Ik zie", "明白"),
                    (r"Hoe gaat het?", "问候"), (r"Heel goed", "很好"),
                    (r"Niet slecht", "不错"), (r"Zo zo", "马马虎虎"),
                    (r"Redelijk", "一般"), (r"Het is klaar", "好了")
                ],
                "complex_patterns": [
                    (r"Het is .+ dat", "强调句型"), (r"Er is .+", "存在句型"),
                    (r"Het feit dat", "名词从句"), (r"Hoewel", "让步"),
                    (r"Omdat", "原因"), (r"Om te", "目的"),
                    (r"Wanneer", "时间"), (r"Als", "条件"),
                    (r"Terwijl", "对比"), (r"Dus .+ dat", "结果"),
                    (r"De reden waarom", "原因句型"),
                    (r"Ik denk dat", "推测句型"),
                    (r"Niet alleen .+ maar ook", "并列强调"),
                    (r"Om", "目的状语"),
                    (r"Terwijl daarentegen", "对比状语"),
                    (r"Totdat", "时间状语"),
                    (r"Zodra", "时间状语"),
                    (r"Opdat", "目的状语"),
                    (r"Zodat", "结果状语"),
                    (r"Op voorwaarde dat", "条件状语"),
                    (r"Stel dat", "条件状语"),
                    (r"Zelfs als", "让步"),
                    (r"Niettemin", "让步"),
                    (r"Met betrekking tot", "关于"),
                    (r"Wat betreft", "关于")
                ],
                "collocations": {
                    "significant": ["significante impact", "significante verandering", "significante belang",
                                   "significante verschillen", "significante rol", "significante hoeveelheid"],
                    "invloed": ["invloed hebben op", "grote invloed", "positieve invloed",
                                 "negatieve invloed", "aanzienlijke invloed", "geen invloed"],
                    "bereiken": ["doel bereiken", "succes bereiken", "niveau bereiken",
                                   "resultaat bereiken", "record bereiken"],
                    "bijdragen": ["bijdragen aan", "een bijdrage leveren", "significante bijdrage leveren",
                                  "bijdragen aan verbetering", "bijdragen aan ontwikkeling"],
                    "bepalen": ["resultaat bepalen", "oorzaak bepalen", "prijs bepalen",
                                 "snelheid bepalen", "richting bepalen"],
                    "potentieel": ["potentieel hebben", "potentieel herkennen", "potentieel benutten",
                                  "maximaal potentieel", "hoog potentieel", "langetermijn potentieel"],
                    "perspectief": ["uit perspectief", "ander perspectief", "nieuw perspectief",
                                    "eigen perspectief", "kritisch perspectief"],
                    "analyseren": ["gegevens analyseren", "situatie analyseren", "probleem analyseren",
                                   "resultaat analyseren", "trend analyseren"],
                    "evalueren": ["prestatie evalueren", "opties evalueren", "kwaliteit evalueren",
                                   "effectiviteit evalueren"],
                    "opzetten": ["relatie opzetten", "regel opzetten", "systeem opzetten",
                                   "verbinding opzetten"],
                    "onderhouden": ["evenwicht onderhouden", "relatie onderhouden", "kwaliteit onderhouden",
                                  "standaard onderhouden"],
                    "transformeren": ["transformeren in iets", "proces transformeren", "industrie transformeren",
                                       "bedrijf transformeren"],
                    "promoveren": ["ontwikkeling promoten", "product promoten", "groei promoten"],
                    "realiseren": ["doel realiseren", "droom realiseren", "potentieel realiseren"],
                    "reduceren": ["kosten reduceren", "risico reduceren", "afval reduceren"],
                    "reflecteren": ["reflecteren op iets", "situatie reflecteren", "verandering reflecteren"],
                    "ondersteunen": ["beslissing ondersteunen", "ondersteuning bieden", "idee ondersteunen"],
                    "impact": ["impact hebben", "significante impact", "positieve impact"],
                    "concentreren": ["concentreren op iets", "aandacht concentreren"],
                    "onderzoeken": ["opties onderzoeken", "mogelijkheden onderzoeken", "markt onderzoeken"],
                },
                "synonyms": {
                    "significant": ["opmerkelijk", "essentieel", "substantieel", "aanzienlijk", "belangrijk"],
                    "invloed": ["impact", "effect", "invloed", "bepaling"],
                    "bereiken": ["halen", "verwezenlijken", "realiseren", "consequeren"],
                    "bijdragen": ["toevoegen", "meewerken", "helpen", "ondersteunen"],
                    "bepalen": ["vaststellen", "beslissen", "invloeden", "definiëren"],
                    "potentieel": ["mogelijkheid", "capaciteit", "vaardigheid", "kans"],
                    "perspectief": ["standpunt", "visie", "benadering", "hoek"],
                    "analyseren": ["onderzoeken", "studeren", "evalueren", "onderzoeken"],
                    "evalueren": ["beoordelen", "schatten", "meten", "verifiëren"],
                    "opzetten": ["creëren", "bouwen", "organiseren", "stichten"],
                    "onderhouden": ["houden", "preserveren", "ondersteunen", "doorgaan"],
                    "transformeren": ["veranderen", "converteren", "aanpassen", "modificeren"],
                    "promoveren": ["bevorderen", "ondersteunen", "versnellen", "verbeteren"],
                    "realiseren": ["verwezenlijken", "bereiken", "uitvoeren", "herkennen"],
                    "reduceren": ["verlagen", "verminderen", "beperken", "minimaliseren"],
                    "reflecteren": ["weergeven", "aantonen", "aanwijzen", "ontdekken"],
                    "ondersteunen": ["ondersteunen", "helpen", "ondersteunen", "verdedigen"],
                    "impact": ["invloed", "effect", "gevolg", "verandering"],
                    "concentreren": ["focussen", "samenbrengen", "prioriteren", "centreren"],
                    "onderzoeken": ["onderzoeken", "onderzoeken", "studeren", "ontdekken"],
                },
                "word_families": {
                    "significant": ["significant", "significantie", "significeren"],
                    "invloed": ["invloed", "invloedrijk", "invloeden"],
                    "bereiken": ["bereiken", "bereiking", "bereikbaar"],
                    "bijdragen": ["bijdragen", "bijdrage", "bijdragend"],
                    "bepalen": ["bepalen", "bepaling", "bepaald"],
                    "potentieel": ["potentieel", "potentieel", "potentiëren"],
                    "perspectief": ["perspectief", "perspectief", "perspectief"],
                    "analyseren": ["analyseren", "analyse", "analytisch"],
                    "evalueren": ["evalueren", "evaluatie", "evaluatief"],
                    "opzetten": ["opzetten", "opzetting", "opgezet"],
                    "onderhouden": ["onderhouden", "onderhoud", "onderhoudbaar"],
                    "transformeren": ["transformeren", "transformatie", "transformatief"],
                    "promoveren": ["promoveren", "promotie", "promotie"],
                    "realiseren": ["realiseren", "realisatie", "realiseerbaar"],
                    "reduceren": ["reduceren", "reductie", "reductief"],
                    "reflecteren": ["reflecteren", "reflectie", "reflecterend"],
                    "ondersteunen": ["ondersteunen", "ondersteuning", "ondersteunend"],
                    "impact": ["impact", "impactvol", "impacteren"],
                    "concentreren": ["concentreren", "concentratie", "geconcentreerd"],
                    "onderzoeken": ["onderzoeken", "onderzoek", "onderzoeks-"],
                },
                "formal_alternatives": {
                    "leuk": "interessant / opmerkelijk", "type": "persoon / individu",
                    "ding": "object / kwestie", "tof": "aantrekkelijk / leuk",
                    "super": "zeer / uitermate", "goed": "uitstekend / goed",
                    "mooi": "aantrekkelijk / prachtig", "kerel": "man / individu",
                    "meisje": "vrouw / individu", "vriend": "vriend / collega",
                    "vriendin": "vriendin / collega", "broer": "broer / collega",
                    "zus": "zus / collega", "huis": "woning / verblijf",
                    "tijd": "moment / periode", "geld": "middelen / fondsen",
                    "werk": "beroep / activiteit", "leven": "bestaan / dagelijks leven",
                    "goed": "voldoende / bevredigend", "slecht": "onvoldoende / negatief",
                    "groot": "beduidend / aanzienlijk", "klein": "beperkt / bescheiden",
                    "nieuw": "recent / modern", "oud": "ouderwets / verouderd",
                    "nou": "nu / dus", "dus": "daarom / daarom",
                    "dan": "dan / vervolgens", "kijk": "kijk / let op",
                    "weet je": "weet je", "zoals": "bijvoorbeeld / zoals"
                }
            },
            "sv": {
                "oral_markers": ["eh", "ja", "jo", "nej", "även", "så",
                                "typ", "du vet", "gäller", "alltså", "va",
                                "hej", "hej då", "tack", "snälla",
                                "förlåt", "förlåt mig", "ah", "åh", "ja visst"],
                "contractions": {
                    "'s": "es", "'re": "är", "'ve": "har", "jag'm": "jag är",
                    "du'm": "du är", "han'm": "han är", "hon'm": "hon är",
                    "vi'm": "vi är", "ni'm": "ni är", "de'm": "de är",
                    "jag've": "jag har", "du've": "du har", "han've": "han har",
                    "hon've": "hon har", "vi've": "vi har", "ni've": "ni har",
                    "de've": "de har", "det's": "det är", "den's": "den är",
                    "de's": "de är", "vad's": "vad är", "var's": "var är",
                    "när's": "när är", "hur's": "hur är", "vilken's": "vilken är",
                    "vilka's": "vilka är", "ingen's": "ingen är", "ingen've": "ingen har",
                    "någon's": "någon är", "någon've": "någon har",
                    "allting's": "allting är", "allting've": "allting har",
                    "något's": "något är", "något've": "något har",
                    "ingenting's": "ingenting är", "ingenting've": "ingenting har"
                },
                "informal_words": ["cool", "bra", "super", "nice", "fantastisk",
                                  "sak", "grej", "typ", "kille", "tjej",
                                  "vän", "väninna", "bror", "syster", "hus",
                                  "tid", "pengar", "jobb", "liv", "bra",
                                  "dålig", "stor", "liten", "ny", "gammal"],
                "oral_patterns": [
                    (r"Okej,", "开场白"), (r"Så,", "开场白"),
                    (r"Alltså,", "结论"), (r"Va", "总结"),
                    (r"Du vet", "填充"), (r"Typ", "举例"),
                    (r"Gäller", "提醒"), (r"Ja visst", "语气词"),
                    (r"Egentligen", "事实上"), (r"Sist", "最终"),
                    (r"Ah", "惊讶"), (r"Åh", "理解"),
                    (r"Nej", "否定"), (r"Du vet", "填充"),
                    (r"Jag tror", "表达"), (r"Jag antar", "推测"),
                    (r"Så sant", "确认"), (r"Egentligen", "确认"),
                    (r"Helt klart", "完全同意"), (r"Inga", "完全否定"),
                    (r"Jag vet inte", "不知道"), (r"Jag minns inte", "忘记"),
                    (r"Jag förstår", "理解"), (r"Jag ser", "明白"),
                    (r"Hur mår du?", "问候"), (r"Jättebra", "很好"),
                    (r"Inte dålig", "不错"), (r"Så så", "马马虎虎"),
                    (r"Okej", "一般"), (r"Det är klart", "好了")
                ],
                "complex_patterns": [
                    (r"Det är .+ att", "强调句型"), (r"Det finns .+", "存在句型"),
                    (r"Faktumet att", "名词从句"), (r"Även om", "让步"),
                    (r"Eftersom", "原因"), (r"För att", "目的"),
                    (r"När", "时间"), (r"Om", "条件"),
                    (r"Medan", "对比"), (r"Så .+ att", "结果"),
                    (r"Anledningen till att", "原因句型"),
                    (r"Det verkar som", "推测句型"),
                    (r"Inte bara .+ utan också", "并列强调"),
                    (r"För att", "目的状语"),
                    (r"Medan å andra sidan", "对比状语"),
                    (r"Tills", "时间状语"),
                    (r"Så fort", "时间状语"),
                    (r"Så att", "目的状语"),
                    (r"På så sätt att", "结果状语"),
                    (r"Under förutsättning att", "条件状语"),
                    (r"Antag att", "条件状语"),
                    (r"Även om", "让步"),
                    (r"Trots att", "让步"),
                    (r"Avseende", "关于"),
                    (r"När det gäller", "关于")
                ],
                "collocations": {
                    "signifikant": ["signifikant effekt", "signifikant förändring", "signifikant betydelse",
                                   "signifikant skillnad", "signifikant roll", "signifikant mängd"],
                    "influens": ["ha en influens på", "stor influens", "positiv influens",
                                 "negativ influens", "betydelsefull influens", "ingen influens"],
                    "uppnå": ["uppnå ett mål", "uppnå framgång", "uppnå ett resultat",
                                   "uppnå ett nivå", "uppnå ett rekord"],
                    "bidra": ["bidra till", "ge ett bidrag", "bidra betydelsefullt",
                                  "bidra till förbättring", "bidra till utveckling"],
                    "bestämma": ["bestämma resultatet", "bestämma orsaken", "bestämma priset",
                                 "bestämma hastigheten", "bestämma riktningen"],
                    "potential": ["ha potential", "upptäcka potential", "utnyttja potential",
                                  "maximal potential", "hög potential", "långsiktig potential"],
                    "perspektiv": ["från ett perspektiv", "ett annat perspektiv", "ett nytt perspektiv",
                                    "ett eget perspektiv", "ett kritiskt perspektiv"],
                    "analysera": ["analysera data", "analysera en situation", "analysera ett problem",
                                   "analysera ett resultat", "analysera en trend"],
                    "utvärdera": ["utvärdera en prestanda", "utvärdera alternativ", "utvärdera en kvalitet",
                                   "utvärdera en effektivitet"],
                    "etablera": ["etablera en relation", "etablera en regel", "etablera ett system",
                                   "etablera en anslutning"],
                    "upprätthålla": ["upprätthålla jämvikt", "upprätthålla en relation", "upprätthålla en kvalitet",
                                  "upprätthålla en standard"],
                    "transformera": ["transformera till något", "transformera en process", "transformera en bransch",
                                       "transformera ett företag"],
                    "promotera": ["promotera utveckling", "promotera ett produkt", "promotera tillväxt"],
                    "realisera": ["realisera ett mål", "realisera en dröm", "realisera potential"],
                    "reducera": ["reducera kostnader", "reducera ett risk", "reducera avfall"],
                    "reflektera": ["reflektera över något", "reflektera en situation", "reflektera en förändring"],
                    "stödja": ["stödja ett beslut", "ge stöd", "stödja en idé"],
                    "effekt": ["ha en effekt", "signifikant effekt", "positiv effekt"],
                    "koncentrera": ["koncentrera sig på något", "koncentrera uppmärksamhet"],
                    "utforska": ["utforska alternativ", "utforska möjligheter", "utforska en marknad"],
                },
                "synonyms": {
                    "signifikant": ["märkvärdig", "essentiell", "substantiell", "betydelsefull", "viktig"],
                    "influens": ["effekt", "påverkan", "influens", "determination"],
                    "uppnå": ["nå", "verkligöra", "realisera", "attaina"],
                    "bidra": ["tillföra", "medverka", "hjälpa", "stödja"],
                    "bestämma": ["fastställa", "besluta", "påverka", "definiera"],
                    "potential": ["möjlighet", "kapacitet", "förmåga", "chans"],
                    "perspektiv": ["synpunkt", "vision", "ansats", "vinkel"],
                    "analysera": ["undersöka", "studera", "utvärdera", "investigera"],
                    "utvärdera": ["bedöma", "värdera", "mätta", "verifiera"],
                    "etablera": ["skapa", "bygga", "organisera", "grunda"],
                    "upprätthålla": ["hålla", "bevara", "stödja", "fortsätta"],
                    "transformera": ["ändra", "konvertera", "anpassa", "modifiera"],
                    "promotera": ["främja", "stödja", "accelerera", "förbättra"],
                    "realisera": ["verkligöra", "uppnå", "utföra", "upptäcka"],
                    "reducera": ["minska", "sänka", "begränsa", "minimera"],
                    "reflektera": ["visa", "demonstra", "indikera", "upptäcka"],
                    "stödja": ["stödja", "hjälpa", "underställa", "försvara"],
                    "effekt": ["influens", "resultat", "konsekvens", "förändring"],
                    "koncentrera": ["fokuser", "sammanslå", "prioritera", "centrera"],
                    "utforska": ["utforska", "undersöka", "studera", "upptäcka"],
                },
                "word_families": {
                    "signifikant": ["signifikant", "signifikans", "signifiera"],
                    "influens": ["influens", "inflytelserik", "influerera"],
                    "uppnå": ["uppnå", "uppnåelse", "uppnåbar"],
                    "bidra": ["bidra", "bidrag", "bidragsgivande"],
                    "bestämma": ["bestämma", "bestämmelse", "bestämd"],
                    "potential": ["potential", "potentiellt", "potentialisera"],
                    "perspektiv": ["perspektiv", "perspektivisk", "perspektiviskt"],
                    "analysera": ["analysera", "analys", "analytisk"],
                    "utvärdera": ["utvärdera", "utvärdering", "utvärderande"],
                    "etablera": ["etablera", "etablering", "etablerad"],
                    "upprätthålla": ["upprätthålla", "upprätthållande", "upprätthållbar"],
                    "transformera": ["transformera", "transformation", "transformerande"],
                    "promotera": ["promotera", "promotion", "promotionell"],
                    "realisera": ["realisera", "realisering", "realiserbar"],
                    "reducera": ["reducera", "reducering", "reducerande"],
                    "reflektera": ["reflektera", "reflektion", "reflekterande"],
                    "stödja": ["stödja", "stöd", "stödjande"],
                    "effekt": ["effekt", "effektfull", "effektuera"],
                    "koncentrera": ["koncentrera", "koncentration", "koncentrerad"],
                    "utforska": ["utforska", "utforskning", "utforskande"],
                },
                "formal_alternatives": {
                    "cool": "imponerande / märkvärdig", "typ": "person / individ",
                    "sak": "objekt / fråga", "grej": "saker / artikel",
                    "super": "mycket / extremt", "bra": "utmärkt / bra",
                    "fantastisk": "fantastisk / utmärkt", "kille": "man / individ",
                    "tjej": "kvinna / individ", "vän": "vän / kollega",
                    "väninna": "väninna / kollega", "bror": "bror / kollega",
                    "syster": "syster / kollega", "hus": "hem / bostad",
                    "tid": "moment / period", "pengar": "medel / pengar",
                    "jobb": "yrke / aktivitet", "liv": "liv / daglig liv",
                    "bra": "tillräcklig / tillfredsställande", "dålig": "otillräcklig / negativ",
                    "stor": "betydelsefull / stor", "liten": "begränsad / bescheiden",
                    "ny": "ny / modern", "gammal": "gammal / föråldrad",
                    "ja": "ja / visst", "nej": "nej / inte",
                    "så": "så / därför", "va": "vad / va",
                    "du vet": "du vet", "typ": "t.ex. / som"
                }
            },
            "no": {
                "oral_markers": ["eh", "ja", "jo", "nei", "også", "så",
                                "typ", "du vet", "gjelder", "altså", "va",
                                "hei", "ha det bra", "takk", "vær så snill",
                                "unnskyld", "unnskyld meg", "ah", "å", "ja visst"],
                "contractions": {
                    "'s": "es", "'re": "er", "'ve": "har", "jeg'm": "jeg er",
                    "du'm": "du er", "han'm": "han er", "hun'm": "hun er",
                    "vi'm": "vi er", "dere'm": "dere er", "de'm": "de er",
                    "jeg've": "jeg har", "du've": "du har", "han've": "han har",
                    "hun've": "hun har", "vi've": "vi har", "dere've": "dere har",
                    "de've": "de har", "det's": "det er", "den's": "den er",
                    "de's": "de er", "hva's": "hva er", "hvor's": "hvor er",
                    "når's": "når er", "hvordan's": "hvordan er", "hvilken's": "hvilken er",
                    "hvilke's": "hvilke er", "ingen's": "ingen er", "ingen've": "ingen har",
                    "noen's": "noen er", "noen've": "noen har",
                    "alt's": "alt er", "alt've": "alt har",
                    "noe's": "noe er", "noe've": "noe har",
                    "ingen's": "ingen er", "ingen've": "ingen har"
                },
                "informal_words": ["kjekt", "bra", "super", "nice", "fantastisk",
                                  "ting", "greie", "typ", "gutt", "jente",
                                  "venn", "veninne", "bror", "søster", "hus",
                                  "tid", "penger", "jobb", "liv", "bra",
                                  "dårlig", "stor", "liten", "ny", "gammel"],
                "oral_patterns": [
                    (r"OK,", "开场白"), (r"Så,", "开场白"),
                    (r"Altså,", "结论"), (r"Va", "总结"),
                    (r"Du vet", "填充"), (r"Typ", "举例"),
                    (r"Gjelder", "提醒"), (r"Ja visst", "语气词"),
                    (r"Egentlig", "事实上"), (r"Sist", "最终"),
                    (r"Ah", "惊讶"), (r"Å", "理解"),
                    (r"Nei", "否定"), (r"Du vet", "填充"),
                    (r"Jeg tror", "表达"), (r"Jeg antar", "推测"),
                    (r"Så sant", "确认"), (r"Egentlig", "确认"),
                    (r"Helt klart", "完全同意"), (r"Ingen", "完全否定"),
                    (r"Jeg vet ikke", "不知道"), (r"Jeg husker ikke", "忘记"),
                    (r"Jeg forstår", "理解"), (r"Jeg ser", "明白"),
                    (r"Hvordan har du det?", "问候"), (r"Jettebra", "很好"),
                    (r"Ikke dårlig", "不错"), (r"Så så", "马马虎虎"),
                    (r"OK", "一般"), (r"Det er klart", "好了")
                ],
                "complex_patterns": [
                    (r"Det er .+ at", "强调句型"), (r"Det finnes .+", "存在句型"),
                    (r"Faktaen at", "名词从句"), (r"Selv om", "让步"),
                    (r"Fordi", "原因"), (r"For å", "目的"),
                    (r"Når", "时间"), (r"Hvis", "条件"),
                    (r"Mens", "对比"), (r"Så .+ at", "结果"),
                    (r"Grunnen til at", "原因句型"),
                    (r"Det virker som", "推测句型"),
                    (r"Ikke bare .+ men også", "并列强调"),
                    (r"For å", "目的状语"),
                    (r"Mens derimot", "对比状语"),
                    (r"Inntil", "时间状语"),
                    (r"Så snart", "时间状语"),
                    (r"Så at", "目的状语"),
                    (r"På denne måten at", "结果状语"),
                    (r"Under forutsetning at", "条件状语"),
                    (r"Anta at", "条件状语"),
                    (r"Selv om", "让步"),
                    (r"Trots at", "让步"),
                    (r"Når det gjelder", "关于"),
                    (r"Angående", "关于")
                ],
                "collocations": {
                    "signifikant": ["signifikant effekt", "signifikant endring", "signifikant betydning",
                                   "signifikant forskjell", "signifikant rolle", "signifikant mengde"],
                    "innflytelse": ["ha innflytelse på", "stor innflytelse", "positiv innflytelse",
                                 "negativ innflytelse", "betydningsfull innflytelse", "ingen innflytelse"],
                    "nå": ["nå en mål", "nå suksess", "nå et resultat",
                                   "nå et nivå", "nå en rekord"],
                    "bidra": ["bidra til", "gi en bidrag", "bidra betydningsfullt",
                                  "bidra til forbedring", "bidra til utvikling"],
                    "bestemme": ["bestemme resultatet", "bestemme årsaken", "bestemme prisen",
                                 "bestemme hastigheten", "bestemme retningen"],
                    "potensial": ["ha potensial", "oppdage potensial", "utnytte potensial",
                                  "maksimal potensial", "høy potensial", "langvarig potensial"],
                    "perspektiv": ["fra et perspektiv", "et annet perspektiv", "et nytt perspektiv",
                                    "et eget perspektiv", "et kritisk perspektiv"],
                    "analysere": ["analysere data", "analysere en situasjon", "analysere et problem",
                                   "analysere et resultat", "analysere en trend"],
                    "evaluere": ["evaluere en ytelse", "evaluere alternativer", "evaluere en kvalitet",
                                   "evaluere en effektivitet"],
                    "etablere": ["etablere en relasjon", "etablere en regel", "etablere et system",
                                   "etablere en kobling"],
                    "opprettholde": ["opprettholde likevekt", "opprettholde en relasjon", "opprettholde en kvalitet",
                                  "opprettholde en standard"],
                    "transformere": ["transformere til noe", "transformere en prosess", "transformere en bransje",
                                       "transformere et selskap"],
                    "promovere": ["promovere utvikling", "promovere et produkt", "promovere vekst"],
                    "realisere": ["realisere en mål", "realisere en drøm", "realisere potensial"],
                    "redusere": ["redusere kostnader", "redusere en risiko", "redusere avfall"],
                    "reflektere": ["reflektere over noe", "reflektere en situasjon", "reflektere en endring"],
                    "støtte": ["støtte en beslutning", "gi støtte", "støtte en idé"],
                    "effekt": ["ha en effekt", "signifikant effekt", "positiv effekt"],
                    "koncentrere": ["koncentrere seg på noe", "koncentrere oppmerksomhet"],
                    "utforske": ["utforske alternativer", "utforske muligheter", "utforske en marked"],
                },
                "synonyms": {
                    "signifikant": ["merknadsverdig", "essensiell", "substantiell", "betydningsfull", "viktig"],
                    "innflytelse": ["effekt", "påvirkning", "innflytelse", "bestemmelse"],
                    "nå": ["nå", "verkliggjøre", "realisere", "oppnå"],
                    "bidra": ["tilføye", "medvirke", "hjelpe", "støtte"],
                    "bestemme": ["fastsette", "beslutte", "påvirke", "definere"],
                    "potensial": ["mulighet", "kapasitet", "evne", "mulighet"],
                    "perspektiv": ["synspunkt", "visjon", "innfallsvinkel", "vinkel"],
                    "analysere": ["undersøke", "studere", "evaluere", "undersøke"],
                    "evaluere": ["vurdere", "evaluere", "måle", "verifisere"],
                    "etablere": ["opprette", "bygge", "organisere", "grunne"],
                    "opprettholde": ["beholde", "bevare", "støtte", "vedlikeholde"],
                    "transformere": ["endre", "konvertere", "tilpasse", "modifisere"],
                    "promovere": ["framme", "støtte", "akselerere", "forbedre"],
                    "realisere": ["verkliggjøre", "nå", "utføre", "oppdage"],
                    "redusere": ["minskere", "senke", "begrense", "minimere"],
                    "reflektere": ["vise", "demonstrere", "indikere", "utsette"],
                    "støtte": ["støtte", "hjelpe", "støtte", "forsvære"],
                    "effekt": ["påvirkning", "resultat", "konsekvens", "endring"],
                    "koncentrere": ["fokuser", "samle", "prioritere", "sentrere"],
                    "utforske": ["utforske", "undersøke", "studere", "oppdage"],
                },
                "word_families": {
                    "signifikant": ["signifikant", "signifikans", "signifisere"],
                    "innflytelse": ["innflytelse", "innflytelsesrik", "innfluere"],
                    "nå": ["nå", "nåelse", "nåbar"],
                    "bidra": ["bidra", "bidrag", "bidragsgivende"],
                    "bestemme": ["bestemme", "bestemmelse", "bestemt"],
                    "potensial": ["potensial", "potensiellt", "potensialisere"],
                    "perspektiv": ["perspektiv", "perspektivisk", "perspektivisk"],
                    "analysere": ["analysere", "analyse", "analytisk"],
                    "evaluere": ["evaluere", "evaluering", "evaluerende"],
                    "etablere": ["etablere", "etablering", "etablert"],
                    "opprettholde": ["opprettholde", "opprettholdelse", "opprettholdbar"],
                    "transformere": ["transformere", "transformation", "transformerende"],
                    "promovere": ["promovere", "promotion", "promotionell"],
                    "realisere": ["realisere", "realisering", "realiserbar"],
                    "redusere": ["redusere", "reduksjon", "reduksjonell"],
                    "reflektere": ["reflektere", "refleksjon", "reflekterende"],
                    "støtte": ["støtte", "støtte", "støttende"],
                    "effekt": ["effekt", "effektiv", "effektivisere"],
                    "koncentrere": ["koncentrere", "koncentrering", "koncentrert"],
                    "utforske": ["utforske", "utforskning", "utforskende"],
                },
                "formal_alternatives": {
                    "kjekt": "imponerende / merknadsverdig", "typ": "person / individ",
                    "ting": "objekt / sak", "greie": "ting / artikkel",
                    "super": "mye / ekstremt", "bra": "utmerket / bra",
                    "fantastisk": "fantastisk / utmerket", "gutt": "gutt / person",
                    "jente": "jente / person", "venn": "venn / kollega",
                    "veninne": "veninne / kollega", "bror": "bror / kollega",
                    "søster": "søster / kollega", "hus": "hjem / bolig",
                    "tid": "tidspunkt / periode", "penger": "midler / penger",
                    "jobb": "jobb / aktivitet", "liv": "liv / daglig liv",
                    "bra": "tilstrekkelig / tilfredsstillende", "dårlig": "utilstrekkelig / negativ",
                    "stor": "betydningsfull / stor", "liten": "begrenset / bescheiden",
                    "ny": "ny / moderne", "gammel": "gammel / utdatert",
                    "ja": "ja / visst", "nei": "nei / ikke",
                    "så": "så / derfor", "va": "hva / va",
                    "du vet": "du vet", "typ": "f.eks. / som"
                }
            },
            "da": {
                "oral_markers": ["eh", "ja", "jo", "nej", "også", "så",
                                "typ", "du ved", "gælder", "altså", "va",
                                "hej", "hej da", "tak", "vær venlig",
                                "undskyld", "undskyld mig", "ah", "å", "ja visst"],
                "contractions": {
                    "'s": "es", "'re": "er", "'ve": "har", "jeg'm": "jeg er",
                    "du'm": "du er", "han'm": "han er", "hun'm": "hun er",
                    "vi'm": "vi er", "i'm": "i er", "de'm": "de er",
                    "jeg've": "jeg har", "du've": "du har", "han've": "han har",
                    "hun've": "hun har", "vi've": "vi har", "i've": "i har",
                    "de've": "de har", "det's": "det er", "den's": "den er",
                    "de's": "de er", "hvad's": "hvad er", "hvor's": "hvor er",
                    "når's": "når er", "hvordan's": "hvordan er", "hvilken's": "hvilken er",
                    "hvilke's": "hvilke er", "ingen's": "ingen er", "ingen've": "ingen har",
                    "nogen's": "nogen er", "nogen've": "nogen har",
                    "alt's": "alt er", "alt've": "alt har",
                    "noget's": "noget er", "noget've": "noget har",
                    "intet's": "intet er", "intet've": "intet har"
                },
                "informal_words": ["fint", "godt", "super", "nice", "fantastisk",
                                  "ting", "ting", "typ", "dreng", "pige",
                                  "ven", "veninde", "broder", "søster", "hus",
                                  "tid", "penge", "job", "liv", "godt",
                                  "dårligt", "stor", "lille", "ny", "gamle"],
                "oral_patterns": [
                    (r"OK,", "开场白"), (r"Så,", "开场白"),
                    (r"Altså,", "结论"), (r"Va", "总结"),
                    (r"Du ved", "填充"), (r"Typ", "举例"),
                    (r"Gælder", "提醒"), (r"Ja visst", "语气词"),
                    (r"Egentlig", "事实上"), (r"Sidst", "最终"),
                    (r"Ah", "惊讶"), (r"Å", "理解"),
                    (r"Nej", "否定"), (r"Du ved", "填充"),
                    (r"Jeg tror", "表达"), (r"Jeg antar", "推测"),
                    (r"Så sandt", "确认"), (r"Egentlig", "确认"),
                    (r"Helt klart", "完全同意"), (r"Ingen", "完全否定"),
                    (r"Jeg ved ikke", "不知道"), (r"Jeg husker ikke", "忘记"),
                    (r"Jeg forstår", "理解"), (r"Jeg ser", "明白"),
                    (r"Hvordan har du det?", "问候"), (r"Meget godt", "很好"),
                    (r"Ikke dårligt", "不错"), (r"Så så", "马马虎虎"),
                    (r"OK", "一般"), (r"Det er klart", "好了")
                ],
                "complex_patterns": [
                    (r"Det er .+ at", "强调句型"), (r"Der findes .+", "存在句型"),
                    (r"Faktaen at", "名词从句"), (r"Selvom", "让步"),
                    (r"Fordi", "原因"), (r"For at", "目的"),
                    (r"Når", "时间"), (r"Hvis", "条件"),
                    (r"Mens", "对比"), (r"Så .+ at", "结果"),
                    (r"Grunnen til at", "原因句型"),
                    (r"Det virker som", "推测句型"),
                    (r"Ikke bare .+ men også", "并列强调"),
                    (r"For at", "目的状语"),
                    (r"Mens derimod", "对比状语"),
                    (r"Inntil", "时间状语"),
                    (r"Så snart", "时间状语"),
                    (r"Så at", "目的状语"),
                    (r"På denne måde at", "结果状语"),
                    (r"Under forudsætning at", "条件状语"),
                    (r"Antag at", "条件状语"),
                    (r"Selvom", "让步"),
                    (r"Trods at", "让步"),
                    (r"Når det gælder", "关于"),
                    (r"Angående", "关于")
                ],
                "collocations": {
                    "signifikant": ["signifikant effekt", "signifikant ændring", "signifikant betydning",
                                   "signifikant forskel", "signifikant rolle", "signifikant mængde"],
                    "indflydelse": ["have indflydelse på", "stor indflydelse", "positiv indflydelse",
                                 "negativ indflydelse", "betydningsfuld indflydelse", "ingen indflydelse"],
                    "nå": ["nå et mål", "nå succes", "nå et resultat",
                                   "nå et niveau", "nå en rekord"],
                    "bidrage": ["bidrage til", "give en bidrag", "bidrage betydningsfuldt",
                                  "bidrage til forbedring", "bidrage til udvikling"],
                    "bestemme": ["bestemme resultatet", "bestemme årsagen", "bestemme prisen",
                                 "bestemme hastigheden", "bestemme retningen"],
                    "potential": ["have potential", "opdage potential", "udnytte potential",
                                  "maksimal potential", "høj potential", "langvarig potential"],
                    "perspektiv": ["fra et perspektiv", "et andet perspektiv", "et nyt perspektiv",
                                    "et eget perspektiv", "et kritisk perspektiv"],
                    "analysere": ["analysere data", "analysere en situation", "analysere et problem",
                                   "analysere et resultat", "analysere en trend"],
                    "evaluere": ["evaluere en ydeevne", "evaluere alternativer", "evaluere en kvalitet",
                                   "evaluere en effektivitet"],
                    "etablere": ["etablere en relation", "etablere en regel", "etablere et system",
                                   "etablere en forbindelse"],
                    "opretholde": ["opretholde ligevægt", "opretholde en relation", "opretholde en kvalitet",
                                  "opretholde en standard"],
                    "transformere": ["transformere til noget", "transformere en proces", "transformere en branche",
                                       "transformere et selskab"],
                    "promovere": ["promovere udvikling", "promovere et produkt", "promovere vækst"],
                    "realisere": ["realisere et mål", "realisere en drøm", "realisere potential"],
                    "reducere": ["reducere omkostninger", "reducere en risiko", "reducere affald"],
                    "reflektere": ["reflektere over noget", "reflektere en situation", "reflektere en ændring"],
                    "støtte": ["støtte en beslutning", "give støtte", "støtte en idé"],
                    "effekt": ["have en effekt", "signifikant effekt", "positiv effekt"],
                    "koncentrere": ["koncentrere sig om noget", "koncentrere opmærksomhed"],
                    "undersøge": ["undersøge alternativer", "undersøge muligheder", "undersøge en markeds"],
                },
                "synonyms": {
                    "signifikant": ["bemærkelsesværdig", "essentiell", "substantiell", "betydningsfuld", "vigtig"],
                    "indflydelse": ["effekt", "påvirkning", "indflydelse", "bestemmelse"],
                    "nå": ["nå", "realisere", "opnå", "verkliggøre"],
                    "bidrage": ["tilføje", "medvirke", "hjælpe", "støtte"],
                    "bestemme": ["fastlægge", "beslutte", "påvirke", "definere"],
                    "potential": ["mulighed", "kapacitet", "evne", "chance"],
                    "perspektiv": ["synspunkt", "vision", "indsatsvinkel", "vinkel"],
                    "analysere": ["undersøge", "studere", "evaluere", "undersøge"],
                    "evaluere": ["vurder", "evaluere", "måle", "bekræfte"],
                    "etablere": ["oprette", "bygge", "organisere", "grunde"],
                    "opretholde": ["beholde", "bevare", "støtte", "vedligeholde"],
                    "transformere": ["ændre", "konvertere", "tilpasse", "modificere"],
                    "promovere": ["framme", "støtte", "accelerere", "forbedre"],
                    "realisere": ["realisere", "nå", "udføre", "opdage"],
                    "reducere": ["mindske", "senke", "begrænse", "minimere"],
                    "reflektere": ["vise", "demonstrere", "indikere", "afsløre"],
                    "støtte": ["støtte", "hjælpe", "støtte", "forsvare"],
                    "effekt": ["påvirkning", "resultat", "konsekvens", "ændring"],
                    "koncentrere": ["fokuser", "samle", "prioritere", "centrere"],
                    "undersøge": ["undersøge", "undersøge", "studere", "opdage"],
                },
                "word_families": {
                    "signifikant": ["signifikant", "signifikans", "significere"],
                    "indflydelse": ["indflydelse", "indflydelsesrig", "indre"],
                    "nå": ["nå", "nåelse", "nåbar"],
                    "bidrage": ["bidrage", "bidrag", "bidragsgydende"],
                    "bestemme": ["bestemme", "bestemmelse", "bestemt"],
                    "potential": ["potential", "potentielt", "potentialisere"],
                    "perspektiv": ["perspektiv", "perspektivisk", "perspektivisk"],
                    "analysere": ["analysere", "analyse", "analytisk"],
                    "evaluere": ["evaluere", "evaluering", "evaluerende"],
                    "etablere": ["etablere", "etablering", "etableret"],
                    "opretholde": ["opretholde", "opretholdelse", "opretholdbar"],
                    "transformere": ["transformere", "transformation", "transformerende"],
                    "promovere": ["promovere", "promotion", "promotionel"],
                    "realisere": ["realisere", "realisering", "realiserbar"],
                    "reducere": ["reducere", "reduktion", "reduktionel"],
                    "reflektere": ["reflektere", "refleksion", "reflekterende"],
                    "støtte": ["støtte", "støtte", "støttende"],
                    "effekt": ["effekt", "effektiv", "effektivisere"],
                    "koncentrere": ["koncentrere", "koncentration", "koncentreret"],
                    "undersøge": ["undersøge", "undersøgelse", "undersøgende"],
                },
                "formal_alternatives": {
                    "fint": ["imponerende", "bemærkelsesværdig"], "typ": ["person", "individ"],
                    "ting": ["objekt", "emne"], "godt": ["udmerket", "godt"],
                    "super": ["meget", "ekstremt"], "fantastisk": ["fantastisk", "udmerket"],
                    "dreng": ["dreng", "person"], "pige": ["pige", "person"],
                    "ven": ["ven", "kollega"], "veninde": ["veninde", "kollega"],
                    "broder": ["broder", "kollega"], "søster": ["søster", "kollega"],
                    "hus": ["hjem", "bolig"], "tid": ["tidspunkt", "periode"],
                    "penge": ["midler", "penge"], "job": ["job", "aktivitet"],
                    "liv": ["liv", "daglig liv"], "godt": ["tilstrækkelig", "tilfredsstillende"],
                    "dårligt": ["utilstrækkelig", "negativ"], "stor": ["betydningsfuld", "stor"],
                    "lille": ["begrænset", "bescheiden"], "ny": ["ny", "modern"],
                    "gamle": ["gamle", "uddateret"], "ja": ["ja", "visst"],
                    "nej": ["nej", "ikke"], "så": ["så", "derfor"],
                    "va": ["hvad", "va"], "du ved": ["du ved"],
                    "typ": ["f.eks.", "som"]
                }
            },
            "fi": {
                "oral_markers": ["eh", "no", "niin", "mutta", "joo", "ei",
                                "vittu", "perkele", "voi", "tosi", "todella",
                                "terve", "moikka", "kiitos", "kiitos paljon",
                                "anteeksi", "pahoittelen", "ah", "oi", "no niin"],
                "contractions": {
                    "'s": "es", "'re": "olet", "'ve": "on", "minä'm": "minä olen",
                    "sinä'm": "sinä olet", "hän'm": "hän on", "me'm": "me olemme",
                    "te'm": "te olette", "he'm": "he ovat",
                    "minä've": "minä olen", "sinä've": "sinä olet", "hän've": "hän on",
                    "me've": "me olemme", "te've": "te olette", "he've": "he ovat",
                    "se's": "se on", "ne's": "ne ovat",
                    "mikä's": "mikä on", "mitkä's": "mitkä ovat",
                    "missä's": "missä on", "missä's": "missä ovat",
                    "milloin's": "milloin on", "miten's": "miten on",
                    "kuka's": "kuka on", "ketkä's": "ketkä ovat",
                    "kenelle's": "kenelle on", "kenelle's": "kenelle ovat",
                    "mille's": "mille on", "mille's": "mille ovat",
                    "mitä's": "mitä on", "mitä's": "mitä ovat"
                },
                "informal_words": ["cool", "hyvä", "super", "nice", "uskomaton",
                                  "asia", "juttu", "tyyppi", "tytär", "poika",
                                  "ystävä", "ystävät", "veli", "sisar", "kotka",
                                  "aika", "raha", "työ", "elämä", "hyvä",
                                  "huono", "suuri", "pieni", "uusi", "vanha"],
                "oral_patterns": [
                    (r"OK,", "开场白"), (r"No,", "开场白"),
                    (r"Niin,", "结论"), (r"Voi", "总结"),
                    (r"Tosi", "填充"), (r"Todella", "举例"),
                    (r"Joo", "提醒"), (r"No niin", "语气词"),
                    (r"Itse asiassa", "事实上"), (r"Viimeksi", "最终"),
                    (r"Ah", "惊讶"), (r"Oi", "理解"),
                    (r"Ei", "否定"), (r"Joo", "填充"),
                    (r"Mä luulen", "表达"), (r"Mä arvaan", "推测"),
                    (r"Niinpä", "确认"), (r"Itse asiassa", "确认"),
                    (r"Absoluuttisesti", "完全同意"), (r"Ei mitään", "完全否定"),
                    (r"En tiedä", "不知道"), (r"En muista", "忘记"),
                    (r"Ymmärrän", "理解"), (r"Näen", "明白"),
                    (r"Mitä kuuluu?", "问候"), (r"Hyvin kiitos", "很好"),
                    (r"Ei pahalta", "不错"), (r"Niin ja näin", "马马虎虎"),
                    (r"OK", "一般"), (r"Se on valmis", "好了")
                ],
                "complex_patterns": [
                    (r"Se on .+ että", "强调句型"), (r"Siellä on .+", "存在句型"),
                    (r"Se, että", "名词从句"), (r"Vaikka", "让步"),
                    (r"Koska", "原因"), (r"Jotta", "目的"),
                    (r"Kun", "时间"), (r"Jos", "条件"),
                    (r"Samanaikaisesti", "对比"), (r"Niin .+ että", "结果"),
                    (r"Syy siihen, että", "原因句型"),
                    (r"Näyttää siltä, että", "推测句型"),
                    (r"Ei vain .+ vaan myös", "并列强调"),
                    (r"Jotta", "目的状语"),
                    (r"Samanaikaisesti toisaalta", "对比状语"),
                    (r"Kunnes", "时间状语"),
                    (r"Vastaan kun", "时间状语"),
                    (r"Niin että", "目的状语"),
                    (r"Niinpä", "结果状语"),
                    (r"Ehdolla, että", "条件状语"),
                    (r"Oletetaan, että", "条件状语"),
                    (r"Vaikka", "让步"),
                    (r"Huolimatta siitä, että", "让步"),
                    (r"Siitä, että", "关于"),
                    (r"Mikäli kyseessä on", "关于")
                ],
                "collocations": {
                    "merkittävä": ["merkittävä vaikutus", "merkittävä muutos", "merkittävä merkitys",
                                   "merkittävä ero", "merkittävä rooli", "merkittävä määrä"],
                    "vaikutus": ["vaikuttaa", "suuri vaikutus", "positiivinen vaikutus",
                                 "negatiivinen vaikutus", "merkittävä vaikutus", "ei vaikutusta"],
                    " saavuttaa": ["saavuttaa tavoite", "saavuttaa menestyys", "saavuttaa tulos",
                                   "saavuttaa taso", "saavuttaa ennätys"],
                    "osallistua": ["osallistua", "antaa panos", "osallistua merkittävästi",
                                  "osallistua parannukseen", "osallistua kehitykseen"],
                    "määrittää": ["määrittää tulos", "määrittää syy", "määrittää hinta",
                                 "määrittää nopeus", "määrittää suunta"],
                    "potentiaali": ["olla potentiaalinen", "havaita potentiaali", "hyödyntää potentiaali",
                                  "maksimaalinen potentiaali", "korkea potentiaali", "pitkäaikainen potentiaali"],
                    "näkökulma": ["näkökulma", "toinen näkökulma", "uusi näkökulma",
                                    "oma näkökulma", "kriittinen näkökulma"],
                    "analysoida": ["analysoida data", "analysoida tilanne", "analysoida ongelma",
                                   "analysoida tulos", "analysoida trendi"],
                    "arvioida": ["arvioida suorituskyky", "arvioida vaihtoehdot", "arvioida laatu",
                                   "arvioida tehokkuus"],
                    "luoda": ["luoda suhde", "luoda sääntö", "luoda järjestelmä",
                                   "luoda yhteys"],
                    "ylläpitää": ["ylläpitää tasapaino", "ylläpitää suhde", "ylläpitää laatu",
                                  "ylläpitää standardi"],
                    "muuttaa": ["muuttaa jotain", "muuttaa prosessi", "muuttaa ala",
                                       "muuttaa yritys"],
                    "edistää": ["edistää kehitystä", "edistää tuotetta", "edistää kasvua"],
                    "realisoida": ["realisoida tavoite", "realisoida unelma", "realisoida potentiaali"],
                    "vähentää": ["vähentää kustannuksia", "vähentää riskiä", "vähentää jätteet"],
                    "heijastaa": ["heijastaa jotain", "heijastaa tilanne", "heijastaa muutos"],
                    "tukea": ["tukea päätöstä", "antaa tukea", "tukea ideaa"],
                    "vaikutus": ["vaikuttaa", "merkittävä vaikutus", "positiivinen vaikutus"],
                    "keskittyä": ["keskittyä jotain", "keskittyä huomio"],
                    "tutkia": ["tutkia vaihtoehdot", "tutkia mahdollisuudet", "tutkia markkina"],
                },
                "synonyms": {
                    "merkittävä": ["huomattava", "keskeinen", "substantiaalinen", "merkittävä", "tärkeä"],
                    "vaikutus": ["vaikutus", "vaikutus", "vaikutus", "määritys"],
                    " saavuttaa": ["saavuttaa", "realisoida", "saavuttaa", "suorittaa"],
                    "osallistua": ["osallistua", "osallistua", "apua", "tukea"],
                    "määrittää": ["määrittää", "määrittää", "vaikuttaa", "määritellä"],
                    "potentiaali": ["mahdollisuus", "kyky", "taito", "mahdollisuus"],
                    "näkökulma": ["näkökulma", "visio", "lähestymistapa", "kulma"],
                    "analysoida": ["analysoida", "tutkia", "arvioida", "selvittää"],
                    "arvioida": ["arvioida", "arvioida", "mitata", "vahvistaa"],
                    "luoda": ["luoda", "rakentaa", "organisoida", "perustaa"],
                    "ylläpitää": ["ylläpitää", "säilyttää", "tukea", "jatkaa"],
                    "muuttaa": ["muuttaa", "muuttaa", "sopivasti", "muuttaa"],
                    "edistää": ["edistää", "tukea", "nopeuttaa", "parantaa"],
                    "realisoida": ["realisoida", "saavuttaa", "suorittaa", "huomaamaan"],
                    "vähentää": ["vähentää", "laskea", "rajoittaa", "minimoida"],
                    "heijastaa": ["heijastaa", "näytellä", "osoittaa", "jäljittää"],
                    "tukea": ["tukea", "apua", "tukea", "puoltaa"],
                    "vaikutus": ["vaikutus", "tulos", "seuraus", "muutos"],
                    "keskittyä": ["keskittyä", "kerätä", "priorisoida", "keskittyä"],
                    "tutkia": ["tutkia", "tutkia", "tutkia", "löytää"],
                },
                "word_families": {
                    "merkittävä": ["merkittävä", "merkitys", "merkittää"],
                    "vaikutus": ["vaikutus", "vaikuttava", "vaikuttaa"],
                    " saavuttaa": ["saavuttaa", "saavutus", "saavutettava"],
                    "osallistua": ["osallistua", "osallistuminen", "osallistuva"],
                    "määrittää": ["määrittää", "määritys", "määrittävä"],
                    "potentiaali": ["potentiaali", "potentiaalinen", "potentiaalinen"],
                    "näkökulma": ["näkökulma", "näkökulma", "näkökulma"],
                    "analysoida": ["analysoida", "analyysi", "analyyttinen"],
                    "arvioida": ["arvioida", "arvio", "arvioitu"],
                    "luoda": ["luoda", "luonti", "luotu"],
                    "ylläpitää": ["ylläpitää", "ylläpito", "ylläpitävä"],
                    "muuttaa": ["muuttaa", "muutos", "muuttuva"],
                    "edistää": ["edistää", "edistys", "edistävä"],
                    "realisoida": ["realisoida", "realisointi", "realisoitu"],
                    "vähentää": ["vähentää", "vähennys", "vähentävä"],
                    "heijastaa": ["heijastaa", "heijastus", "heijastava"],
                    "tukea": ["tukea", "tuki", "tukeva"],
                    "vaikutus": ["vaikutus", "vaikuttava", "vaikuttaa"],
                    "keskittyä": ["keskittyä", "keskittyminen", "keskittynyt"],
                    "tutkia": ["tutkia", "tutkimus", "tutkiva"],
                },
                "formal_alternatives": {
                    "cool": ["impressioivinen", "huomattava"], "tyyppi": ["henkilö", "individu"],
                    "asia": ["kohte", "asia"], "juttu": ["asia", "artikkeli"],
                    "super": ["erittäin", "erittäin"], "hyvä": ["erittäin hyvä", "hyvä"],
                    "uskomaton": ["uskomaton", "erittäin hyvä"], "poika": ["poika", "henkilö"],
                    "tytär": ["tytär", "henkilö"], "ystävä": ["ystävä", "kollega"],
                    "ystävät": ["ystävät", "kollegat"], "veli": ["veli", "kollega"],
                    "sisar": ["sisar", "kollega"], "kotka": ["koti", "asunto"],
                    "aika": ["aika", "jakso"], "raha": ["varat", "raha"],
                    "työ": ["työ", "työ"], "elämä": ["elämä", "päivittäinen elämä"],
                    "hyvä": ["tyydyttävä", "tyydyttävä"], "huono": ["huono", "negatiivinen"],
                    "suuri": ["suuri", "merkittävä"], "pieni": ["pieni", "rajallinen"],
                    "uusi": ["uusi", "moderni"], "vanha": ["vanha", "vanhentunut"],
                    "joo": ["kyllä", "joo"], "ei": ["ei", "ei"],
                    "no": ["nykyään", "no"], "niin": ["niin", "siis"],
                    "voit": ["voit"], "tosi": ["tosi"]
                }
            },
            "pl": {
                "oral_markers": ["eh", "no", "więc", "ale", "tak", "nie",
                                "jak wiesz", "tipo", "no cóż", "no to", "okej",
                                "cześć", "do widzenia", "dziękuję", "proszę",
                                "przepraszam", "przepraszam", "ach", "o", "no cóż"],
                "contractions": {
                    "'s": "es", "'re": "jesteś", "'ve": "masz", "ja'm": "ja jestem",
                    "ty'm": "ty jesteś", "on'm": "on jest", "ona'm": "ona jest",
                    "my'm": "my jesteśmy", "wy'm": "wy jesteście", "oni'm": "oni są",
                    "ja've": "ja mam", "ty've": "ty masz", "on've": "on ma",
                    "ona've": "ona ma", "my've": "my mamy", "wy've": "wy macie",
                    "oni've": "oni mają", "to's": "to jest", "ono's": "ono jest",
                    "co's": "co jest", "gdzie's": "gdzie jest",
                    "kiedy's": "kiedy jest", "jak's": "jak jest", "który's": "który jest",
                    "którzy's": "którzy są", "nikt's": "nikt nie jest", "nikt've": "nikt nie ma",
                    "ktoś's": "ktoś jest", "ktoś've": "ktoś ma",
                    "wszystko's": "wszystko jest", "wszystko've": "wszystko ma",
                    "coś's": "coś jest", "coś've": "coś ma",
                    "nic's": "nic nie jest", "nic've": "nic nie ma"
                },
                "informal_words": ["fajny", "super", "świetny", "cool", "genialny",
                                  "rzecz", "sprawa", "typ", "chłopak", "dziewczyna",
                                  "przyjaciel", "przyjaciółka", "brat", "siostra", "dom",
                                  "czas", "pieniądze", "praca", "życie", "dobry",
                                  "zły", "duży", "mały", "nowy", "stary"],
                "oral_patterns": [
                    (r"Okej,", "开场白"), (r"No,", "开场白"),
                    (r"Więc,", "结论"), (r"No to", "总结"),
                    (r"Jak wiesz", "填充"), (r"Tipo", "举例"),
                    (r"No cóż", "提醒"), (r"Tak", "语气词"),
                    (r"Właściwie", "事实上"), (r"W końcu", "最终"),
                    (r"Ach", "惊讶"), (r"O", "理解"),
                    (r"Nie", "否定"), (r"Jak wiesz", "填充"),
                    (r"Myślę", "表达"), (r"Sądzę", "推测"),
                    (r"Tak naprawdę", "确认"), (r"Właściwie", "确认"),
                    (r"Absolutnie", "完全同意"), (r"Zupełnie", "完全否定"),
                    (r"Nie wiem", "不知道"), (r"Nie pamiętam", "忘记"),
                    (r"Rozumiem", "理解"), (r"Widzę", "明白"),
                    (r"Jak leci?", "问候"), (r"Bardzo dobrze", "很好"),
                    (r"Nieźle", "不错"), (r"Tak sobie", "马马虎虎"),
                    (r"Średnio", "一般"), (r"Gotowe", "好了")
                ],
                "complex_patterns": [
                    (r"To jest .+ że", "强调句型"), (r"Istnieje .+", "存在句型"),
                    (r"Fakt, że", "名词从句"), (r"Chociaż", "让步"),
                    (r"Ponieważ", "原因"), (r"Aby", "目的"),
                    (r"Kiedy", "时间"), (r"Jeśli", "条件"),
                    (r"Podczas gdy", "对比"), (r"Taki .+ że", "结果"),
                    (r"Powód, dla którego", "原因句型"),
                    (r"Wygląda na to, że", "推测句型"),
                    (r"Nie tylko .+ ale także", "并列强调"),
                    (r"Aby", "目的状语"),
                    (r"Podczas gdy z drugiej strony", "对比状语"),
                    (r"Do momentu, aż", "时间状语"),
                    (r"Jak tylko", "时间状语"),
                    (r"Taki", "目的状语"),
                    (r"W taki sposób, że", "结果状语"),
                    (r"Pod warunkiem, że", "条件状语"),
                    (r"Załóżmy, że", "条件状语"),
                    (r"Chociaż", "让步"),
                    (r"Mimo tego, że", "让步"),
                    (r"Jeśli chodzi o", "关于"),
                    (r"Dotyczące", "关于")
                ],
                "collocations": {
                    "istotny": ["istotny wpływ", "istotna zmiana", "istotna znaczenie",
                                   "istotna różnica", "istotna rola", "istotna ilość"],
                    "wpływ": ["mieć wpływ na", "duży wpływ", "pozytywny wpływ",
                                 "negatywny wpływ", "istotny wpływ", "żaden wpływ"],
                    "osiągnąć": ["osiągnąć cel", "osiągnąć sukces", "osiągnąć wynik",
                                   "osiągnąć poziom", "osiągnąć rekord"],
                    "współpracować": ["współpracować", "współpracować", "współpracować istotnie",
                                  "współpracować w celu poprawy", "współpracować w celu rozwoju"],
                    "określić": ["określić wynik", "określić przyczynę", "określić cenę",
                                 "określić prędkość", "określić kierunek"],
                    "potencjał": ["mieć potencjał", "zidentyfikować potencjał", "wykorzystać potencjał",
                                  "maksymalny potencjał", "wysoki potencjał", "długoterminowy potencjał"],
                    "perspektywa": ["z perspektywy", "inna perspektywa", "nowa perspektywa",
                                    "własna perspektywa", "krytyczna perspektywa"],
                    "analizować": ["analizować dane", "analizować sytuację", "analizować problem",
                                   "analizować wynik", "analizować trend"],
                    "oceniać": ["oceniać wydajność", "oceniać opcje", "oceniać jakość",
                                   "oceniać skuteczność"],
                    "ustawić": ["ustawić relację", "ustawić regułę", "ustawić system",
                                   "ustawić połączenie"],
                    "utrzymywać": ["utrzymywać równowagę", "utrzymywać relację", "utrzymywać jakość",
                                  "utrzymywać standard"],
                    "przekształcać": ["przekształcać w coś", "przekształcać proces", "przekształcać branżę",
                                       "przekształcać biznes"],
                    "promować": ["promować rozwój", "promować produkt", "promować wzrost"],
                    "realizować": ["realizować cel", "realizować sen", "realizować potencjał"],
                    "redukować": ["redukować koszty", "redukować ryzyko", "redukować odpadki"],
                    "odzwierciedlać": ["odzwierciedlać coś", "odzwierciedlać sytuację", "odzwierciedlać zmianę"],
                    "wspierać": ["wspierać decyzję", "wspierać", "wspierać ideę"],
                    "wpływ": ["mieć wpływ", "istotny wpływ", "pozytywny wpływ"],
                    "skupiać": ["skupiać się na czymś", "skupiać uwagę"],
                    "badac": ["badac opcje", "badac możliwości", "badac rynek"],
                },
                "synonyms": {
                    "istotny": ["znaczny", "podstawowy", "substancjalny", "ważny", "kluczowy"],
                    "wpływ": ["wpływ", "efekt", "wpływ", "determinacja"],
                    "osiągnąć": ["osiągnąć", "osiągnąć", "realizować", "osiągnąć"],
                    "współpracować": ["współpracować", "współpracować", "pomagać", "wspierać"],
                    "określić": ["określić", "określić", "wpływać", "definiować"],
                    "potencjał": ["możliwość", "zdolność", "umiejętność", "szansa"],
                    "perspektywa": ["punkt widzenia", "wizja", "podejście", "kąt"],
                    "analizować": ["analizować", "badac", "oceniać", "badac"],
                    "oceniać": ["oceniać", "oceniać", "mierzyć", "weryfikować"],
                    "ustawić": ["ustawić", "budować", "organizować", "założyć"],
                    "utrzymywać": ["utrzymywać", "trzymać", "wspierać", "kontynuować"],
                    "przekształcać": ["przekształcać", "przekształcać", "dostosowywać", "modyfikować"],
                    "promować": ["promować", "wspierać", "przyspieszać", "poprawiać"],
                    "realizować": ["realizować", "osiągnąć", "wykonywać", "rozpoznawać"],
                    "redukować": ["redukować", "zmniejszać", "ograniczać", "minimalizować"],
                    "odzwierciedlać": ["odzwierciedlać", "pokazywać", "wskazywać", "ujawniać"],
                    "wspierać": ["wspierać", "pomagać", "wspierać", "bronzić"],
                    "wpływ": ["wpływ", "efekt", "konsekwencja", "zmiana"],
                    "skupiać": ["skupiać", "zbierać", "priorytetyzować", "centrować"],
                    "badac": ["badac", "badac", "badac", "odkrywać"],
                },
                "word_families": {
                    "istotny": ["istotny", "istota", "istotny"],
                    "wpływ": ["wpływ", "wpływowy", "wpływać"],
                    "osiągnąć": ["osiągnąć", "osiągnięcie", "osiągalny"],
                    "współpracować": ["współpracować", "współpraca", "współpracujący"],
                    "określić": ["określić", "określenie", "określony"],
                    "potencjał": ["potencjał", "potencjalny", "potencjalny"],
                    "perspektywa": ["perspektywa", "perspektywiczny", "perspektywiczny"],
                    "analizować": ["analizować", "analiza", "analityczny"],
                    "oceniać": ["oceniać", "ocena", "oceniający"],
                    "ustawić": ["ustawić", "ustawienie", "ustawiony"],
                    "utrzymywać": ["utrzymywać", "utrzymanie", "utrzymywany"],
                    "przekształcać": ["przekształcać", "przekształcenie", "przekształcający"],
                    "promować": ["promować", "promocja", "promocyjny"],
                    "realizować": ["realizować", "realizacja", "realizowalny"],
                    "redukować": ["redukować", "redukcja", "redukcyjny"],
                    "odzwierciedlać": ["odzwierciedlać", "odzwierciedlenie", "odzwierciedlający"],
                    "wspierać": ["wspierać", "wsparcie", "wspierający"],
                    "wpływ": ["wpływ", "wpływowy", "wpływać"],
                    "skupiać": ["skupiać", "skupienie", "skupiony"],
                    "badac": ["badac", "badanie", "badający"],
                },
                "formal_alternatives": {
                    "fajny": ["impresyjny", "znaczny"], "typ": ["osoba", "indywidualność"],
                    "rzecz": ["przedmiot", "sprawa"], "sprawa": ["sprawa", "artykuł"],
                    "super": ["bardzo", "ekstremalnie"], "świetny": ["fantastyczny", "doskonały"],
                    "cool": ["impresyjny", "fajny"], "chłopak": ["mężczyzna", "osoba"],
                    "dziewczyna": ["kobieta", "osoba"], "przyjaciel": ["przyjaciel", "kollega"],
                    "przyjaciółka": ["przyjaciółka", "kollega"], "brat": ["brat", "kollega"],
                    "siostra": ["siostra", "kollega"], "dom": ["dom", "mieszkanie"],
                    "czas": ["czas", "okres"], "pieniądze": ["środki", "fundusze"],
                    "praca": ["praca", "działanie"], "życie": ["życie", "codzienne życie"],
                    "dobry": ["dostateczny", "zadowalający"], "zły": ["niezadowalający", "negatywny"],
                    "duży": ["znaczny", "imponujący"], "mały": ["ograniczony", "umiarkowany"],
                    "nowy": ["nowy", "nowoczesny"], "stary": ["stary", "przestarzały"],
                    "tak": ["tak", "rzeczywiście"], "nie": ["nie", "nie"],
                    "no": ["teraz", "więc"], "więc": ["więc", "ponieważ"],
                    "jak wiesz": ["jak wiesz"], "tipo": ["np.", "jak"]
                }
            },
            "cs": {
                "oral_markers": ["eh", "no", "takže", "ale", "ano", "ne",
                                "víš", "typ", "no tak", "dobre", "okej",
                                "ahoj", "na shledanou", "děkuji", "prosím",
                                "promiň", "promiňte", "ah", "oh", "no tak"],
                "contractions": {
                    "'s": "es", "'re": "jsi", "'ve": "máš", "já'm": "já jsem",
                    "ty'm": "ty jsi", "on'm": "on je", "ona'm": "ona je",
                    "my'm": "my jsme", "vy'm": "vy jste", "oni'm": "oni jsou",
                    "já've": "já mám", "ty've": "ty máš", "on've": "on má",
                    "ona've": "ona má", "my've": "my máme", "vy've": "vy máte",
                    "oni've": "oni mají", "to's": "to je", "ono's": "ono je",
                    "co's": "co je", "kde's": "kde je",
                    "kdy's": "kdy je", "jak's": "jak je", "který's": "který je",
                    "kteří's": "kteří jsou", "nikdo's": "nikdo není", "nikdo've": "nikdo nemá",
                    "někdo's": "někdo je", "někdo've": "někdo má",
                    "všechno's": "všechno je", "všechno've": "všechno má",
                    "něco's": "něco je", "něco've": "něco má",
                    "nic's": "nic není", "nic've": "nic nemá"
                },
                "informal_words": ["fajn", "super", "skvělý", "cool", "geniální",
                                  "věc", "vec", "typ", "chlap", "dívka",
                                  "přítel", "přítelkyně", "bratr", "sestra", "dům",
                                  "čas", "peníze", "práce", "život", "dobrý",
                                  "špatný", "velký", "malý", "nový", "starý"],
                "oral_patterns": [
                    (r"Okej,", "开场白"), (r"No,", "开场白"),
                    (r"Takže,", "结论"), (r"No tak", "总结"),
                    (r"Víš", "填充"), (r"Typ", "举例"),
                    (r"Dobre", "提醒"), (r"Ano", "语气词"),
                    (r"Ve skutečnosti", "事实上"), (r"Nakonec", "最终"),
                    (r"Ah", "惊讶"), (r"Oh", "理解"),
                    (r"Ne", "否定"), (r"Víš", "填充"),
                    (r"Myslím", "表达"), (r"Domnívám se", "推测"),
                    (r"Ve skutečnosti", "确认"), (r"Opravdu", "确认"),
                    (r"Absolutně", "完全同意"), (r"Zcela", "完全否定"),
                    (r"Nevím", "不知道"), (r"Nepamatuji", "忘记"),
                    (r"Rozumím", "理解"), (r"Vidím", "明白"),
                    (r"Jak se máš?", "问候"), (r"Velmi dobře", "很好"),
                    (r"Není špatně", "不错"), (r"Tak tak", "马马虎虎"),
                    (r"Průměrně", "一般"), (r"Hotovo", "好了")
                ],
                "complex_patterns": [
                    (r"To je .+ že", "强调句型"), (r"Existuje .+", "存在句型"),
                    (r"Skutečnost, že", "名词从句"), (r"Ačkoli", "让步"),
                    (r"Protože", "原因"), (r"Aby", "目的"),
                    (r"Když", "时间"), (r"Pokud", "条件"),
                    (r"Zatímco", "对比"), (r"Takový .+ že", "结果"),
                    (r"Důvod, proč", "原因句型"),
                    (r"Vypadá to, že", "推测句型"),
                    (r"Nejen .+ ale také", "并列强调"),
                    (r"Aby", "目的状语"),
                    (r"Zatímco na druhé straně", "对比状语"),
                    (r"Dokud", "时间状语"),
                    (r"Hned když", "时间状语"),
                    (r"Takový", "目的状语"),
                    (r"Takže", "结果状语"),
                    (r"Za podmínkou, že", "条件状语"),
                    (r"Předpokládejme, že", "条件状语"),
                    (r"Ačkoli", "让步"),
                    (r"Navzdory tomu, že", "让步"),
                    (r"Pokud jde o", "关于"),
                    (r"Související s", "关于")
                ],
                "collocations": {
                    "signifikantní": ["signifikantní vliv", "signifikantní změna", "signifikantní význam",
                                   "signifikantní rozdíl", "signifikantní role", "signifikantní množství"],
                    "vliv": ["mít vliv na", "velký vliv", "pozitivní vliv",
                                 "negativní vliv", "signifikantní vliv", "žádný vliv"],
                    "dosáhnout": ["dosáhnout cíle", "dosáhnout úspěchu", "dosáhnout výsledku",
                                   "dosáhnout úrovně", "dosáhnout rekordu"],
                    "přispět": ["přispět", "přispět", "přispět signifikantně",
                                  "přispět ke zlepšení", "přispět k rozvoji"],
                    "určit": ["určit výsledek", "určit příčinu", "určit cenu",
                                 "určit rychlost", "určit směr"],
                    "potenciál": ["mít potenciál", "identifikovat potenciál", "využít potenciál",
                                  "maximální potenciál", "vysoký potenciál", "dlouhodobý potenciál"],
                    "perspektiva": ["z perspektivy", "jiná perspektiva", "nová perspektiva",
                                    "vlastní perspektiva", "kritická perspektiva"],
                    "analyzovat": ["analyzovat data", "analyzovat situaci", "analyzovat problém",
                                   "analyzovat výsledek", "analyzovat trend"],
                    "hodnotit": ["hodnotit výkon", "hodnotit možnosti", "hodnotit kvalitu",
                                   "hodnotit efektivitu"],
                    "nastavit": ["nastavit vztah", "nastavit pravidlo", "nastavit systém",
                                   "nastavit spojení"],
                    "udržet": ["udržet rovnováhu", "udržet vztah", "udržet kvalitu",
                                  "udržet standard"],
                    "transformovat": ["transformovat do něčeho", "transformovat proces", "transformovat odvětví",
                                       "transformovat podnik"],
                    "propagovat": ["propagovat rozvoj", "propagovat produkt", "propagovat růst"],
                    "realizovat": ["realizovat cíl", "realizovat sen", "realizovat potenciál"],
                    "snížit": ["snížit náklady", "snížit riziko", "snížit odpad"],
                    "odrážet": ["odrážet něco", "odrážet situaci", "odrážet změnu"],
                    "podporovat": ["podporovat rozhodnutí", "poskytnout podporu", "podporovat myšlenku"],
                    "vliv": ["mít vliv", "signifikantní vliv", "pozitivní vliv"],
                    "soustředit": ["soustředit se na něco", "soustředit pozornost"],
                    "zkoumat": ["zkoumat možnosti", "zkoumat potenciály", "zkoumat trh"],
                },
                "synonyms": {
                    "signifikantní": ["překvapivý", "podstatný", "substanční", "významný", "důležitý"],
                    "vliv": ["vliv", "efekt", "vliv", "determinace"],
                    "dosáhnout": ["dosáhnout", "dosáhnout", "realizovat", "dosáhnout"],
                    "přispět": ["přispět", "přispět", "pomoci", "podporovat"],
                    "určit": ["určit", "určit", "vlivnit", "definovat"],
                    "potenciál": ["možnost", "schopnost", "dovednost", "šance"],
                    "perspektiva": ["pohled", "vizion", "přístup", "úhel"],
                    "analyzovat": ["analyzovat", "zkoumat", "hodnotit", "zkoumat"],
                    "hodnotit": ["hodnotit", "hodnotit", "měřit", "verifikovat"],
                    "nastavit": ["nastavit", "stavět", "organizovat", "zakládat"],
                    "udržet": ["udržet", "držet", "podporovat", "pokračovat"],
                    "transformovat": ["transformovat", "transformovat", "přizpůsobovat", "modifikovat"],
                    "propagovat": ["propagovat", "podporovat", "rychlit", "zlepšit"],
                    "realizovat": ["realizovat", "dosáhnout", "provést", "rozpoznat"],
                    "snížit": ["snížit", "snížit", "omezit", "minimalizovat"],
                    "odrážet": ["odrážet", "ukazovat", "indikovat", "objevovat"],
                    "podporovat": ["podporovat", "pomoci", "podporovat", "bránit"],
                    "vliv": ["vliv", "důsledek", "následek", "změna"],
                    "soustředit": ["soustředit", "shromáždit", "prioritizovat", "centrovat"],
                    "zkoumat": ["zkoumat", "zkoumat", "zkoumat", "objevovat"],
                },
                "word_families": {
                    "signifikantní": ["signifikantní", "signifikance", "signifikantní"],
                    "vliv": ["vliv", "vlivný", "vlivnit"],
                    "dosáhnout": ["dosáhnout", "dosažení", "dosažitelný"],
                    "přispět": ["přispět", "příspěvek", "přispívající"],
                    "určit": ["určit", "určení", "určený"],
                    "potenciál": ["potenciál", "potenciální", "potenciální"],
                    "perspektiva": ["perspektiva", "perspektivní", "perspektivní"],
                    "analyzovat": ["analyzovat", "analýza", "analytický"],
                    "hodnotit": ["hodnotit", "hodnocení", "hodnotící"],
                    "nastavit": ["nastavit", "nastavení", "nastavený"],
                    "udržet": ["udržet", "udržování", "udržovaný"],
                    "transformovat": ["transformovat", "transformace", "transformující"],
                    "propagovat": ["propagovat", "propagace", "propagační"],
                    "realizovat": ["realizovat", "realizace", "realizovatelný"],
                    "snížit": ["snížit", "snížení", "snížující"],
                    "odrážet": ["odrážet", "odraz", "odrážející"],
                    "podporovat": ["podporovat", "podpora", "podporující"],
                    "vliv": ["vliv", "vlivný", "vlivnit"],
                    "soustředit": ["soustředit", "soustředění", "soustředěný"],
                    "zkoumat": ["zkoumat", "zkouška", "zkoumající"],
                },
                "formal_alternatives": {
                    "fajn": ["impresivní", "významný"], "typ": ["osoba", "individuum"],
                    "věc": ["předmět", "věc"], "vec": ["věc", "článek"],
                    "super": ["velmi", "extremně"], "skvělý": ["fantastický", "dokonalý"],
                    "cool": ["impresivní", "fajn"], "chlap": ["muž", "osoba"],
                    "dívka": ["žena", "osoba"], "přítel": ["přítel", "kolega"],
                    "přítelkyně": ["přítelkyně", "kolega"], "bratr": ["bratr", "kolega"],
                    "sestra": ["sestra", "kolega"], "dům": ["dům", "být"],
                    "čas": ["čas", "období"], "peníze": ["prostředky", "peníze"],
                    "práce": ["práce", "aktivita"], "život": ["život", "denní život"],
                    "dobrý": ["dostatečný", "uspokojivý"], "špatný": ["neuspokojivý", "negativní"],
                    "velký": ["významný", "impresivní"], "malý": ["omezený", "mírný"],
                    "nový": ["nový", "moderní"], "starý": ["starý", "zastaralý"],
                    "ano": ["ano", "opravdu"], "ne": ["ne", "ne"],
                    "no": ["nyní", "takže"], "takže": ["takže", "protože"],
                    "víš": ["víš"], "typ": ["např.", "jak"]
                }
            },
            "hu": {
                "oral_markers": ["eh", "no", "szóval", "de", "igen", "nem",
                                "tudod", "tipus", "no", "jól", "oké",
                                "szia", "viszlát", "köszönöm", "kérlek",
                                "sajnálom", "sajnálom", "ah", "ó", "no"],
                "contractions": {
                    "'s": "es", "'re": "vagy", "'ve": "van", "én'm": "én vagyok",
                    "te'm": "te vagy", "ő'm": "ő van", "mi'm": "mi vagyunk",
                    "ti'm": "ti vagytok", "ők'm": "ők vannak",
                    "én've": "én vagyok", "te've": "te vagy", "ő've": "ő van",
                    "mi've": "mi vagyunk", "ti've": "ti vagytok", "ők've": "ők vannak",
                    "az's": "az van", "ez's": "ez van",
                    "mi's": "mi van", "mely's": "mely van",
                    "hol's": "hol van", "mikor's": "mikor van", "hogyan's": "hogyan van",
                    "ki's": "ki van", "kik's": "kik vannak",
                    "senki's": "senki nincs", "senki've": "senki nincs",
                    "valaki's": "valaki van", "valaki've": "valaki van",
                    "mindent's": "mindent van", "mindent've": "mindent van",
                    "valami's": "valami van", "valami've": "valami van",
                    "semmi's": "semmi nincs", "semmi've": "semmi nincs"
                },
                "informal_words": ["nagyon", "szuper", "fantasztikus", "cool", "geniális",
                                  "dolog", "cica", "típus", "fiú", "lány",
                                  "barát", "barátnő", "báty", "lány", "ház",
                                  "idő", "pénz", "munka", "élet", "jó",
                                  "rossz", "nagy", "kicsi", "új", "öreg"],
                "oral_patterns": [
                    (r"Oké,", "开场白"), (r"No,", "开场白"),
                    (r"Szóval,", "结论"), (r"Jól", "总结"),
                    (r"Tudod", "填充"), (r"Tipus", "举例"),
                    (r"Jól", "提醒"), (r"Igen", "语气词"),
                    (r"Valójában", "事实上"), (r"Végül", "最终"),
                    (r"Ah", "惊讶"), (r"Ó", "理解"),
                    (r"Nem", "否定"), (r"Tudod", "填充"),
                    (r"Azt hiszem", "表达"), (r"Azt gondolom", "推测"),
                    (r"Valójában", "确认"), (r"Valóban", "确认"),
                    (r"Teljesen", "完全同意"), (r"Egyáltalán", "完全否定"),
                    (r"Nem tudom", "不知道"), (r"Nem emlékszem", "忘记"),
                    (r"Értem", "理解"), (r"Látom", "明白"),
                    (r"Hogy vagy?", "问候"), (r"Jól", "很好"),
                    (r"Nem rossz", "不错"), (r"Közepes", "马马虎虎"),
                    (r"Átlagos", "一般"), (r"Kész", "好了")
                ],
                "complex_patterns": [
                    (r"Ez .+ hogy", "强调句型"), (r"Van .+", "存在句型"),
                    (r"A tény, hogy", "名词从句"), (r"Bár", "让步"),
                    (r"Mert", "原因"), (r"Hogy", "目的"),
                    (r"Amikor", "时间"), (r"Ha", "条件"),
                    (r"Míg", "对比"), (r"Annyira .+ hogy", "结果"),
                    (r"Az oka, hogy", "原因句型"),
                    (r"Úgy tűnik, hogy", "推测句型"),
                    (r"Nem csak .+ hanem", "并列强调"),
                    (r"Hogy", "目的状语"),
                    (r"Míg másrészt", "对比状语"),
                    (r"Amíg", "时间状语"),
                    (r"Amint", "时间状语"),
                    (r"Annyira", "目的状语"),
                    (r"Így", "结果状语"),
                    (r"Feltéve, hogy", "条件状语"),
                    (r"Tegyük fel, hogy", "条件状语"),
                    (r"Bár", "让步"),
                    (r"Ellenére, hogy", "让步"),
                    (r"Amint a", "关于"),
                    (r"Kérdezésben", "关于")
                ],
                "collocations": {
                    "signifikáns": ["signifikáns hatás", "signifikáns változás", "signifikáns jelentőség",
                                   "signifikáns különbség", "signifikáns szerep", "signifikáns mennyiség"],
                    "hatás": ["hatásolni", "nagy hatás", "pozitív hatás",
                                 "negatív hatás", "signifikáns hatás", "nincs hatás"],
                    "elérni": ["elérni egy cél", "elérni sikert", "elérni egy eredmény",
                                   "elérni egy szint", "elérni egy rekord"],
                    "hozzájárul": ["hozzájárulni", "hozzájárulni", "hozzájárulni signifikánsan",
                                  "hozzájárulni a javításához", "hozzájárulni a fejlesztéshez"],
                    "meghatározni": ["meghatározni az eredményt", "meghatározni az okot", "meghatározni az árat",
                                 "meghatározni a sebességet", "meghatározni az irányt"],
                    "potenciál": ["potenciál", "felismerni a potenciált", "kihasználni a potenciált",
                                  "maximális potenciál", "magas potenciál", "hosszú távú potenciál"],
                    "perspektíva": ["egy perspektívából", "más perspektíva", "új perspektíva",
                                    "saját perspektíva", "kritikus perspektíva"],
                    "elemzés": ["adatokat elemezni", "helyzetet elemezni", "problémát elemezni",
                                   "eredményt elemezni", "tendenciát elemezni"],
                    "értékelés": ["teljesítményt értékelni", "lehetőségeket értékelni", "minőséget értékelni",
                                   "hatékonyságot értékelni"],
                    "beállítás": ["kapcsolatot beállítani", "szabályt beállítani", "rendszert beállítani",
                                   "kapcsolatot beállítani"],
                    "fenntartás": ["egyensúlyt fenntartani", "kapcsolatot fenntartani", "minőséget fenntartani",
                                  "szabványt fenntartani"],
                    "transzformáció": ["transzformálni valamibe", "folyamatot transzformálni", "ipart transzformálni",
                                       "üzletet transzformálni"],
                    "promóció": ["fejlesztést promálni", "terméket promálni", "növekedést promálni"],
                    "realizáció": ["celt realizálni", "történést realizálni", "potenciált realizálni"],
                    "csökkentés": ["költségeket csökkenteni", "kockázatot csökkenteni", "hulladékot csökkenteni"],
                    "tükrözés": ["valamit tükrözni", "helyzetet tükrözni", "változást tükrözni"],
                    "támogatás": ["döntést támogatni", "támogatást nyújtani", "ötletet támogatni"],
                    "hatás": ["hatásolni", "signifikáns hatás", "pozitív hatás"],
                    "fókusz": ["fókuszálni valamire", "fókuszálni a figyelemre"],
                    "kutatás": ["lehetőségeket kutatni", "lehetőségeket kutatni", "piacot kutatni"],
                },
                "synonyms": {
                    "signifikáns": ["figyelemre méltó", "alapvető", "subszanciális", "fontos", "kulcsfontosságú"],
                    "hatás": ["hatás", "effekt", "hatás", "meghatározás"],
                    "elérni": ["elérni", "realizálni", "elérni", "elérni"],
                    "hozzájárul": ["hozzájárulni", "hozzájárulni", "segíteni", "támogatni"],
                    "meghatározni": ["meghatározni", "meghatározni", "befolyásolni", "meghatározni"],
                    "potenciál": ["lehetőség", "képesség", "készség", "esély"],
                    "perspektíva": ["kilátás", "viszió", "közelítés", "szög"],
                    "elemzés": ["elemzés", "kutatás", "értékelés", "vizsgálat"],
                    "értékelés": ["értékelés", "értékelés", "mérés", "ellenőrzés"],
                    "beállítás": ["beállítás", "építés", "szervezés", "alapítás"],
                    "fenntartás": ["fenntartás", "megőrzés", "támogatás", "folytatás"],
                    "transzformáció": ["transzformáció", "transzformáció", "alkalmazás", "módosítás"],
                    "promóció": ["promóció", "támogatás", "gyorsítás", "javítás"],
                    "realizáció": ["realizáció", "elérés", "végrehajtás", "felismerés"],
                    "csökkentés": ["csökkentés", "csökkentés", "korlátozás", "minimalizálás"],
                    "tükrözés": ["tükrözés", "mutatás", "jelzés", "felderítés"],
                    "támogatás": ["támogatás", "segítség", "támogatás", "védelem"],
                    "hatás": ["hatás", "eredmény", "következmény", "változás"],
                    "fókusz": ["fókusz", "gyűjtemény", "prioritás", "központosítás"],
                    "kutatás": ["kutatás", "kutatás", "kutatás", "felderítés"],
                },
                "word_families": {
                    "signifikáns": ["signifikáns", "signifikancia", "signifikáns"],
                    "hatás": ["hatás", "hatásos", "hatásol"],
                    "elérni": ["elérni", "elérés", "elérhető"],
                    "hozzájárul": ["hozzájárulni", "hozzájárulás", "hozzájáruló"],
                    "meghatározni": ["meghatározni", "meghatározás", "meghatározott"],
                    "potenciál": ["potenciál", "potenciális", "potenciális"],
                    "perspektíva": ["perspektíva", "perspektívás", "perspektívás"],
                    "elemzés": ["elemzés", "elemzés", "analitikus"],
                    "értékelés": ["értékelés", "értékelés", "értékelő"],
                    "beállítás": ["beállítás", "beállítás", "beállított"],
                    "fenntartás": ["fenntartás", "fenntartás", "fenntartható"],
                    "transzformáció": ["transzformáció", "transzformáció", "transzformáló"],
                    "promóció": ["promóció", "promóció", "promóciós"],
                    "realizáció": ["realizáció", "realizáció", "realizálható"],
                    "csökkentés": ["csökkentés", "csökkentés", "csökkentő"],
                    "tükrözés": ["tükrözés", "tükrözés", "tükröző"],
                    "támogatás": ["támogatás", "támogatás", "támogató"],
                    "hatás": ["hatás", "hatásos", "hatásol"],
                    "fókusz": ["fókusz", "fókusz", "fókusz"],
                    "kutatás": ["kutatás", "kutatás", "kutató"],
                },
                "formal_alternatives": {
                    "nagyon": ["impresszív", "figyelemre méltó"], "típus": ["ember", "individuum"],
                    "dolog": ["dolog", "cím"], "cica": ["dolog", "cica"],
                    "szuper": ["nagyon", "extrem"], "fantasztikus": ["fantasztikus", "tökéletes"],
                    "cool": ["impresszív", "nagyon"], "fiú": ["fiú", "ember"],
                    "lány": ["lány", "ember"], "barát": ["barát", "munkatárs"],
                    "barátnő": ["barátnő", "munkatárs"], "báty": ["báty", "munkatárs"],
                    "ház": ["ház", "lakás"], "idő": ["idő", "szakasz"],
                    "pénz": ["pénz", "források"], "munka": ["munka", "tevékenység"],
                    "élet": ["élet", "napi élet"], "jó": ["megfelelő", "elégséges"],
                    "rossz": ["elégtelen", "negatív"], "nagy": ["fontos", "impresszív"],
                    "kicsi": ["korlátozott", "mérsékelt"], "új": ["új", "modern"],
                    "öreg": ["öreg", "elavult"], "igen": ["igen", "valóban"],
                    "nem": ["nem", "nem"], "no": ["most", "szóval"],
                    "szóval": ["szóval", "mivel"], "tudod": ["tudod"],
                    "tipus": ["pl.", "ahogy"]
                }
            },
            "ro": {
                "oral_markers": ["eh", "bine", "asa", "dar", "da", "nu",
                                "sti", "tip", "bine", "ok", "bine",
                                "salut", "pa", "multumesc", "te rog",
                                "scuze", "mi pare rau", "ah", "oh", "bine"],
                "contractions": {
                    "'s": "es", "'re": "esti", "'ve": "ai", "eu'm": "eu sunt",
                    "tu'm": "tu esti", "el'm": "el este", "ea'm": "ea este",
                    "noi'm": "noi suntem", "voi'm": "voi sunteti", "ei'm": "ei sunt",
                    "eu've": "eu am", "tu've": "tu ai", "el've": "el are",
                    "ea've": "ea are", "noi've": "noi avem", "voi've": "voi aveti",
                    "ei've": "ei au", "aceasta's": "aceasta este", "acesta's": "acesta este",
                    "ce's": "ce este", "unde's": "unde este",
                    "cand's": "cand este", "cum's": "cum este", "care's": "care este",
                    "cari's": "cari sunt", "nimeni's": "nimeni nu este", "nimeni've": "nimeni nu are",
                    "cineva's": "cineva este", "cineva've": "cineva are",
                    "tot's": "tot este", "tot've": "tot are",
                    "ceva's": "ceva este", "ceva've": "ceva are",
                    "nimic's": "nimic nu este", "nimic've": "nimic nu are"
                },
                "informal_words": ["cool", "super", "fantastic", "nice", "genial",
                                  "lucru", "chestie", "tip", "băiat", "fată",
                                  "prieten", "prietenă", "frate", "soră", "casă",
                                  "timp", "bani", "lucru", "viață", "bine",
                                  "rau", "mare", "mic", "nou", "vechi"],
                "oral_patterns": [
                    (r"OK,", "开场白"), (r"Bine,", "开场白"),
                    (r"Deci,", "结论"), (r"Bine", "总结"),
                    (r"Sti", "填充"), (r"Tip", "举例"),
                    (r"Bine", "提醒"), (r"Da", "语气词"),
                    (r"De fapt", "事实上"), (r"In final", "最终"),
                    (r"Ah", "惊讶"), (r"Oh", "理解"),
                    (r"Nu", "否定"), (r"Sti", "填充"),
                    (r"Cred", "表达"), (r"Presupun", "推测"),
                    (r"De fapt", "确认"), (r"Chiar", "确认"),
                    (r"Absolut", "完全同意"), (r"Deloc", "完全否定"),
                    (r"Nu stiu", "不知道"), (r"Nu ma amintesc", "忘记"),
                    (r"Intelesc", "理解"), (r"Vad", "明白"),
                    (r"Ce mai faci?", "问候"), (r"Foarte bine", "很好"),
                    (r"Nu rau", "不错"), (r"Asa si asa", "马马虎虎"),
                    (r"Mediu", "一般"), (r"Gata", "好了")
                ],
                "complex_patterns": [
                    (r"Este .+ ca", "强调句型"), (r"Există .+", "存在句型"),
                    (r"Faptul că", "名词从句"), (r"Deși", "让步"),
                    (r"Pentru că", "原因"), (r"Pentru a", "目的"),
                    (r"Când", "时间"), (r"Dacă", "条件"),
                    (r"În timp ce", "对比"), (r"Atât .+ încât", "结果"),
                    (r"Motivul pentru care", "原因句型"),
                    (r"Se pare că", "推测句型"),
                    (r"Nu numai .+ dar și", "并列强调"),
                    (r"Pentru a", "目的状语"),
                    (r"În timp ce pe de altă parte", "对比状语"),
                    (r"Până când", "时间状语"),
                    (r"De îndată ce", "时间状语"),
                    (r"Atât", "目的状语"),
                    (r"În așa fel încât", "结果状语"),
                    (r"În condițiile în care", "条件状语"),
                    (r"Să presupunem că", "条件状语"),
                    (r"Deși", "让步"),
                    (r"In ciuda faptului că", "让步"),
                    (r"Când vine vorba de", "关于"),
                    (r"Referitor la", "关于")
                ],
                "collocations": {
                    "semnificativ": ["impact semnificativ", "schimbare semnificativa", "importanță semnificativă",
                                   "diferență semnificativă", "rol semnificativ", "cantitate semnificativă"],
                    "influenta": ["avea influenta asupra", "mare influenta", "influenta pozitiva",
                                 "influenta negativa", "influenta semnificativa", "nici o influenta"],
                    "atinge": ["atinge un obiectiv", "atinge succesul", "atinge un rezultat",
                                   "atinge un nivel", "atinge un record"],
                    "contribui": ["contribui la", "face o contribuție", "contribui semnificativ",
                                  "contribui la imbunatatire", "contribui la dezvoltare"],
                    "determina": ["determina rezultatul", "determina cauza", "determina pretul",
                                 "determina viteza", "determina directia"],
                    "potential": ["avea potential", "recunoaste potential", "exploateaza potential",
                                  "maxim potential", "high potential", "potential pe termen lung"],
                    "perspectiva": ["dintr-o perspectiva", "alta perspectiva", "noua perspectiva",
                                    "propria perspectiva", "perspectiva critica"],
                    "analiza": ["analiza date", "analiza o situatie", "analiza un problem",
                                   "analiza un rezultat", "analiza o tendinta"],
                    "evalueaza": ["evalueaza o performanta", "evalueaza optiuni", "evalueaza o calitate",
                                   "evalueaza o eficacitate"],
                    "stabilește": ["stabilește o relatie", "stabilește o regula", "stabilește un sistem",
                                   "stabilește o conexiune"],
                    "mentine": ["mentine echilibrul", "mentine o relatie", "mentine o calitate",
                                  "mentine un standard"],
                    "transforma": ["transforma in ceva", "transforma un proces", "transforma o industria",
                                       "transforma un afacere"],
                    "promoveaza": ["promoveaza dezvoltarea", "promoveaza un produs", "promoveaza cresterea"],
                    "realizeaza": ["realizeaza un obiectiv", "realizeaza un vis", "realizeaza potential"],
                    "reduci": ["reduci costurile", "reduci un risc", "reduci deșeurile"],
                    "reflecta": ["reflecta asupra ceva", "reflecta o situatie", "reflecta o schimbare"],
                    "sprijina": ["sprijina o decizie", "ofere sprijin", "sprijina o idee"],
                    "impact": ["avea un impact", "impact semnificativ", "impact pozitiv"],
                    "concentreaza": ["concentreaza-te asupra ceva", "concentreaza atentia"],
                    "exploreaza": ["exploreaza optiuni", "exploreaza posibilitati", "exploreaza un piata"],
                },
                "synonyms": {
                    "semnificativ": ["notabil", "esential", "substancial", "considerabil", "important"],
                    "influenta": ["impact", "efect", "influenta", "determinare"],
                    "atinge": ["realizeaza", "consegue", "atinge", "realizeaza"],
                    "contribui": ["aduce", "participa", "ajuta", "sprijina"],
                    "determina": ["fixeaza", "decide", "influeaza", "defineste"],
                    "potential": ["posibilitate", "capacitate", "aptitudine", "oportunitate"],
                    "perspectiva": ["punct de vedere", "viziune", "abordare", "unghi"],
                    "analiza": ["examineaza", "studia", "evalueaza", "investigheaza"],
                    "evalueaza": ["judeca", "aprecieaza", "masoara", "verifica"],
                    "stabilește": ["creeaza", "construieste", "organizeste", "infiinteaza"],
                    "mentine": ["pastreaza", "preserva", "sustin", "continua"],
                    "transforma": ["schimba", "convertește", "modifica", "adauga"],
                    "promoveaza": ["incurajeaza", "sprijina", "accelereaza", "imbunatateste"],
                    "realizeaza": ["concretizeaza", "atinge", "implmenteaza", "recunoaste"],
                    "reduci": ["diminueaza", "scade", "limita", "minimizeaza"],
                    "reflecta": ["arata", "demonstreaza", "indica", "reveala"],
                    "sprijina": ["apoiata", "sprijina", "ajuta", "apara"],
                    "impact": ["influenta", "efect", "consecinta", "schimbare"],
                    "concentreaza": ["focalizeaza", "groupeaza", "prioritizeaza", "centru"],
                    "exploreaza": ["investigheaza", "examineaza", "studia", "descopera"],
                },
                "word_families": {
                    "semnificativ": ["semnificativ", "semnificatie", "semnifica"],
                    "influenta": ["influenta", "influențator", "influență"],
                    "atinge": ["atinge", "atingere", "atingibil"],
                    "contribui": ["contribui", "contributie", "contribuitor"],
                    "determina": ["determina", "determinare", "determinat"],
                    "potential": ["potential", "potencial", "potencializa"],
                    "perspectiva": ["perspectiva", "perspectivă", "perspectivă"],
                    "analiza": ["analiza", "analiza", "analitic"],
                    "evalueaza": ["evalueaza", "evaluare", "evaluator"],
                    "stabilește": ["stabilește", "stabilire", "stabilit"],
                    "mentine": ["mentine", "mentinere", "mentinut"],
                    "transforma": ["transforma", "transformare", "transformator"],
                    "promoveaza": ["promoveaza", "promotie", "promotional"],
                    "realizeaza": ["realizeaza", "realizare", "realizabil"],
                    "reduci": ["reduci", "reducere", "reductiv"],
                    "reflecta": ["reflecta", "reflectare", "reflectant"],
                    "sprijina": ["sprijina", "sprijin", "sprijitor"],
                    "impact": ["impact", "impactant", "impacta"],
                    "concentreaza": ["concentreaza", "concentrare", "concentrat"],
                    "exploreaza": ["exploreaza", "explorare", "explorator"],
                },
                "formal_alternatives": {
                    "cool": ["impresionant", "notabil"], "tip": ["persoana", "individual"],
                    "lucru": ["obiect", "subiect"], "chestie": ["lucru", "articol"],
                    "super": ["foarte", "extrem"], "fantastic": ["fantastic", "excellent"],
                    "nice": ["agrabil", "placut"], "băiat": ["bărbat", "persoana"],
                    "fată": ["femeie", "persoana"], "prieten": ["prieten", "coleg"],
                    "prietenă": ["prietenă", "coleg"], "frate": ["frate", "coleg"],
                    "soră": ["soră", "coleg"], "casă": ["casă", "locuință"],
                    "timp": ["moment", "perioadă"], "bani": ["resurse", "fonduri"],
                    "lucru": ["lucru", "activitate"], "viață": ["viață", "viața cotidiană"],
                    "bine": ["adevat", "satisfacator"], "rau": ["nesatisfacator", "negativ"],
                    "mare": ["important", "considerabil"], "mic": ["redus", "modest"],
                    "nou": ["nou", "modern"], "vechi": ["vechi", "depasit"],
                    "da": ["da", "adevat"], "nu": ["nu", "nu"],
                    "bine": ["acum", "deci"], "asa": ["asa", "astfel"],
                    "sti": ["sti"], "tip": ["de ex.", "ca"]
                }
            },
            "ar": {
                "oral_markers": ["أم", "أي", "أنا", "أوه", "حسنا",
                                "مثل", "أعلم", "أرى", "حقا", "بالطبع",
                                "مرحبا", "مع السلامة", "شكرا", "من فضلك",
                                "عفو", "أسف", "أوه", "آه", "أيها"],
                "contractions": {},
                "informal_words": ["جيد", "رائع", "ممتاز", "عظيم", "مذهل",
                                  "شيء", "حاجة", "شخص", "صديق", "أخ",
                                  "أخت", "بيت", "وقت", "مال", "عمل",
                                  "حياة", "جيد", "سيء", "كبير", "صغير"],
                "oral_patterns": [
                    (r"حسنا", "开场白"), (r"أم", "语气词"),
                    (r"أي", "疑问"), (r"أنا", "表达"),
                    (r"أوه", "惊讶"), (r"حقا", "强调"),
                    (r"بالطبع", "同意"), (r"مثل", "举例"),
                    (r"أعلم", "填充"), (r"أرى", "明白"),
                    (r"مرحبا", "问候"), (r"مع السلامة", "告别"),
                    (r"شكرا", "感谢"), (r"عفو", "回应"),
                    (r"أسف", "道歉"), (r"من فضلك", "请求"),
                    (r"آه", "理解"), (r"أيها", "称呼")
                ],
                "complex_patterns": [
                    (r"ال것", "强调"), (r"هناك", "存在"),
                    (r"السبب", "原因"), (r"قد", "可能"),
                    (r"إذا", "条件"), (r"على الرغم من", "让步"),
                    (r"لأن", "原因"), (r"حتى", "直到"),
                    (r"عندما", "时间"), (r"أنه", "强调"),
                    (r"الموجه إلى", "目的"), (r"النتيجة", "结果"),
                    (r"المقارنة", "对比"), (r"بالنسبة إلى", "关于")
                ],
                "collocations": {
                    "مهم": ["تأثير مهم", "تغيير مهم", "فرق مهم", "دور مهم", "نتيجة مهم"],
                    "تأثير": ["تأثير كبير", "تأثير إيجابي", "تأثير سلبي", "تأثير深远", "تأثير محدود"],
                    "تحقيق": ["تحقيق هدف", "تحقيق نجاح", "تحقيق نتائج", "تحقيق مستوى"],
                    "مساهمة": ["مساهمة في", "مساهمة كبيرة", "مساهمة إيجابية", "مساهمة في التنمية"],
                    "تحديد": ["تحديد النتيجة", "تحديد السبب", "تحديد السعر", "تحديد الاتجاه"],
                    "قدرة": ["قدرة على", "قدرة كبيرة", "قدرة محدودة", "قدرة الطاقة"],
                    "منظور": ["منظور مختلف", "منظور جديد", "منظور موضوعي", "منظور نقدي"],
                    "تحليل": ["تحليل البيانات", "تحليل الوضع", "تحليل المشكلة", "تحليل الاتجاه"],
                    "تقييم": ["تقييم الأداء", "تقييم الخيارات", "تقييم الجودة", "تقييم الفعالية"],
                    "إنشاء": ["إنشاء علاقة", "إنشاء قاعدة", "إنشاء نظام", "إنشاء اتصال"],
                    "الاحتفاظ": ["الاحتفاظ بالتوازن", "الاحتفاظ بالعلاقة", "الاحتفاظ بالجودة", "الاحتفاظ بالمعايير"],
                    "تحول": ["تحول إلى", "تحول العملية", "تحول الصناعة", "تحول الأعمال"],
                    "التعزيز": ["التعزيز للتطوير", "التعزيز للمنتج", "التعزيز للنمو"],
                    "الوصول": ["الوصول إلى الهدف", "الوصول إلى الحلم", "الوصول إلى القدرة"],
                    "الحد": ["الحد من التكلفة", "الحد من المخاطر", "الحد من النفايات"],
                    "العكس": ["العكس في", "العكس للوضع", "العكس للتغيير"],
                    "الدعم": ["الدعم للقرار", "الدعم للفكرة", "الدعم للمشروع"],
                    "التركيز": ["التركيز على", "التركيز على الانتباه"],
                    "الاستكشاف": ["الاستكشاف للخيارات", "الاستكشاف للاحتمالات", "الاستكشاف للسوق"]
                },
                "synonyms": {
                    "مهم": ["أساسي", "حاسم", "عظيم", "مؤثر"],
                    "تأثير": ["ảnh hưởng", "نتيجة", "عواقب", "ผล"],
                    "تحقيق": ["الوصول", "النجاح", "التوفير", "الإنجاز"],
                    "مساهمة": ["المساعدة", "الدعم", "المشاركة", "الإسهام"],
                    "تحديد": ["القرار", "التعيين", "العرف", "التحديد"],
                    "قدرة": ["القوة", "القدرة", "الإمكانية", "الطاقة"],
                    "منظور": ["الرأي", "المنظور", "النظرة", "الجانب"],
                    "تحليل": ["الدراسة", "التحليل", "الاستعراض", "التحقيق"],
                    "تقييم": ["التقييم", "الدراسة", "المعايرة", "التحقق"],
                    "إنشاء": ["التصميم", "البناء", "التأسيس", "الانشاء"],
                    "الاحتفاظ": ["الاستمرار", "الحفاظ", "الإبقاء", "الترسيخ"],
                    "تحول": ["التبديل", "التحول", "التغيير", "الاستبدال"],
                    "التعزيز": ["التوسيع", "الازدهار", "النمو", "التحفيز"],
                    "الوصول": ["الوصول", "الوصول", "التحقيق", "الاستحقاق"],
                    "الحد": ["الاقصاء", "الحد", "القصر", "الاستبعاد"],
                    "العكس": ["الاستعارة", "العكس", "التدليس", "الانعكاس"],
                    "الدعم": ["المساندة", "الدعم", "الشجاعة", "القوة"],
                    "التركيز": ["الالتزام", "التركيز", "الانخراط", "الملامح"],
                    "الاستكشاف": ["الاستكشاف", "البحث", "الدراسة", "الاكتشاف"]
                },
                "word_families": {
                    "مهم": ["مهم", "أهمية", "مهم"],
                    "تأثير": ["تأثير", "تأثيري", "تأثير"],
                    "تحقيق": ["تحقيق", "تحقيق", "مُحقّق"],
                    "مساهمة": ["مساهمة", "مساهم", "مساهم"],
                    "تحديد": ["تحديد", "محدد", "تحديد"],
                    "قدرة": ["قدرة", "قادر", "قدرة"],
                    "منظور": ["منظور", "منظوري", "منظور"],
                    "تحليل": ["تحليل", "محلل", "تحليلي"],
                    "تقييم": ["تقييم", "مقيّم", "تقييمي"],
                    "إنشاء": ["إنشاء", "مُنشئ", "إنشائي"],
                    "الاحتفاظ": ["الاحتفاظ", "مُحتفظ", "احتفاظي"],
                    "تحول": ["تحول", "مُحول", "تحولي"],
                    "التعزيز": ["التعزيز", "مُعزّز", "تعزيزي"],
                    "الوصول": ["الوصول", "مُرُدّ", "وصولي"],
                    "الحد": ["الحد", "مُحدِّد", "حدّي"],
                    "العكس": ["العكس", "مُعكس", "عكسي"],
                    "الدعم": ["الدعم", "مُدعم", "دعمي"],
                    "التركيز": ["التركيز", "مُركّز", "تركيزي"],
                    "الاستكشاف": ["الاستكشاف", "مُستكشف", "استكشافي"]
                },
                "formal_alternatives": {
                    "جيد": "ممتاز / رائع", "رائع": "ممتاز / فائق",
                    "ممتاز": "ممتاز / استثنائي", "عظيم": "عظيم / هائل",
                    "مذهل": "مذهل / رائع", "شيء": "مادة / عنصر",
                    "حاجة": "مهمة / قضية", "شخص": "شخص / فرد",
                    "صديق": "صديق / زميل", "أخ": "أخ / زميل",
                    "أخت": "أخت / زميلة", "بيت": "منزل / مسكن",
                    "وقت": "момент / فترة", "مال": "مصادر / أموال",
                    "عمل": "وظيفة / نشاط", "حياة": "حياة / الحياة اليومية",
                    "جيد": "مقبول / مرضٍ", "سيء": "غير مرضٍ / سلبي",
                    "كبير": "مهم / ضخم", "صغير": "محدود / معتدل"
                }
            },
            "hi": {
                "oral_markers": ["अरे", "अरे है", "उम्म", "ओह", "ठीक है",
                                "जैसे", "तुम्हें पता है", "मैं मानता हूं", "वास्तव में", "अंत में"],
                "contractions": {},
                "informal_words": ["अच्छा", "बहुत अच्छा", "रहस्यमय", "शानदार", "सुपर",
                                  "चीज़", "वस्तु", "लड़का", "लड़की", "दोस्त",
                                  "भाई", "बहन", "घर", "समय", "पैसे",
                                  "काम", "जिंदगी", "अच्छा", "बुरा", "बड़ा"],
                "oral_patterns": [
                    (r"अरे", "惊讶"), (r"उम्म", "犹豫"),
                    (r"ओह", "理解"), (r"ठीक है", "同意"),
                    (r"जैसे", "举例"), (r"तुम्हें पता है", "填充"),
                    (r"मैं मानता हूं", "表达"), (r"वास्तव में", "强调"),
                    (r"अंत में", "总结"), (r"नमस्ते", "问候"),
                    (r"अलविदा", "告别"), (r"धन्यवाद", "感谢"),
                    (r"कृपया", "请求"), (r"माफ कीजिए", "道歉"),
                    (r"हाँ", "同意"), (r"नहीं", "否定")
                ],
                "complex_patterns": [
                    (r"यह है", "强调"), (r"वहाँ है", "存在"),
                    (r"कारण है", "原因"), (r"यदि", "条件"),
                    (r"हालांकि", "让步"), (r"क्योंकि", "原因"),
                    (r"जब", "时间"), (r"ताकि", "目的"),
                    (r"जिससे", "结果"), (r"के बावजूद", "让步"),
                    (r"के अनुसार", "根据"), (r"के बारे में", "关于"),
                    (r"के साथ", "伴随"), (r"के बाद", "之后")
                ],
                "collocations": {
                    "महत्वपूर्ण": ["महत्वपूर्ण प्रभाव", "महत्वपूर्ण परिवर्तन", "महत्वपूर्ण अंतर", "महत्वपूर्ण भूमिका"],
                    "प्रभाव": ["प्रभाव डालना", "बड़ा प्रभाव", "सकारात्मक प्रभाव", "नकारात्मक प्रभाव", "महत्वपूर्ण प्रभाव"],
                    "प्राप्त": ["लक्ष्य प्राप्त", "सफलता प्राप्त", "परिणाम प्राप्त", "स्तर प्राप्त"],
                    "योगदान": ["योगदान देना", "महत्वपूर्ण योगदान", "सकारात्मक योगदान", "विकास में योगदान"],
                    "निर्धारित": ["परिणाम निर्धारित", "कारण निर्धारित", "मूल्य निर्धारित", "दिशा निर्धारित"],
                    "क्षमता": ["क्षमता होना", "क्षमता पहचानना", "क्षमता का उपयोग", "अधिकतम क्षमता"],
                    "दृष्टिकोण": ["दृष्टिकोण से", "दूसरा दृष्टिकोण", "नया दृष्टिकोण", "स्वयं का दृष्टिकोण"],
                    "विश्लेषण": ["डेटा विश्लेषण", "स्थिति विश्लेषण", "समस्या विश्लेषण", "प्रवृत्ति विश्लेषण"],
                    "मूल्यांकन": ["प्रदर्शन मूल्यांकन", "विकल्प मूल्यांकन", "गुणवत्ता मूल्यांकन", "प्रभावशीलता मूल्यांकन"],
                    "स्थापित": ["रिश्ता स्थापित", "नियम स्थापित", "प्रणाली स्थापित", "संपर्क स्थापित"],
                    "बनाए रखना": ["संतुलन बनाए रखना", "रिश्ता बनाए रखना", "गुणवत्ता बनाए रखना", "मानक बनाए रखना"],
                    "रूपांतर": ["रूपांतर करना", "प्रक्रिया रूपांतर", "उद्योग रूपांतर", "व्यवसाय रूपांतर"],
                    "प्रोत्साहन": ["विकास प्रोत्साहन", "उत्पाद प्रोत्साहन", "विकास प्रोत्साहन"],
                    "वास्तविक": ["लक्ष्य वास्तविक", "सपना वास्तविक", "क्षमता वास्तविक"],
                    "कम करना": ["लागतें कम करना", "जोखिम कम करना", "कचरा कम करना"],
                    "प्रतिबिंब": ["प्रतिबिंबित करना", "स्थिति प्रतिबिंबित", "परिवर्तन प्रतिबिंबित"],
                    "समर्थन": ["निर्णय का समर्थन", "समर्थन प्रदान", "विचार का समर्थन"],
                    "ध्यान": ["ध्यान केंद्रित", "ध्यान देना"],
                    "अन्वेषण": ["विकल्पों का अन्वेषण", "संभावनाओं का अन्वेषण", "बाजार का अन्वेषण"]
                },
                "synonyms": {
                    "महत्वपूर्ण": ["अनिवार्य", "मुख्य", "प्रमुख", "आवश्यक"],
                    "प्रभाव": ["प्रभाव", "परिणाम", "प्रभाव", "नतीजा"],
                    "प्राप्त": ["प्राप्त करना", "पहुँचना", "प्राप्त करना", "प्राप्त"],
                    "योगदान": ["योगदान", "सहभागिता", "मदद", "समर्थन"],
                    "निर्धारित": ["निर्धारित", "निर्धारण", "निर्धारित", "निर्धारित"],
                    "क्षमता": ["संभावनाएँ", "क्षमता", "सक्षमता", "समय"],
                    "दृष्टिकोण": ["दृष्टिकोण", "विचार", "दृष्टिकोण", "दिशा"],
                    "विश्लेषण": ["विश्लेषण", "अध्ययन", "मूल्यांकन", "जांच"],
                    "मूल्यांकन": ["मूल्यांकन", "मूल्यांकन", "मापन", "सत्यापन"],
                    "स्थापित": ["स्थापित", "निर्माण", "संगठन", "स्थापना"],
                    "बनाए रखना": ["बनाए रखना", "संरक्षित", "समर्थन", "जारी रखना"],
                    "रूपांतर": ["रूपांतर", "परिवर्तन", "परिवर्तन", "अनुकूलन"],
                    "प्रोत्साहन": ["प्रोत्साहन", "समर्थन", "त्वरण", "सुधार"],
                    "वास्तविक": ["वास्तविक", "प्राप्त", "पालन", "पहचान"],
                    "कम करना": ["कम करना", "कम करना", "सीमित", "न्यूनतम"],
                    "प्रतिबिंब": ["प्रतिबिंब", "दिखाना", "संकेत", "प्रकट"],
                    "समर्थन": ["समर्थन", "मदद", "समर्थन", "पक्ष"],
                    "ध्यान": ["ध्यान", "एकत्र", "प्राथमिकता", "केंद्र"],
                    "अन्वेषण": ["अन्वेषण", "जांच", "अध्ययन", "खोज"]
                },
                "word_families": {
                    "महत्वपूर्ण": ["महत्वपूर्ण", "महत्व", "महत्वपूर्ण"],
                    "प्रभाव": ["प्रभाव", "प्रभावी", "प्रभाव"],
                    "प्राप्त": ["प्राप्त", "प्राप्ति", "प्राप्त"],
                    "योगदान": ["योगदान", "योगदानकर्ता", "योगदान"],
                    "निर्धारित": ["निर्धारित", "निर्धारण", "निर्धारित"],
                    "क्षमता": ["क्षमता", "क्षमता", "क्षमता"],
                    "दृष्टिकोण": ["दृष्टिकोण", "दृष्टिकोण", "दृष्टिकोण"],
                    "विश्लेषण": ["विश्लेषण", "विश्लेषक", "विश्लेषण"],
                    "मूल्यांकन": ["मूल्यांकन", "मूल्यांकक", "मूल्यांकन"],
                    "स्थापित": ["स्थापित", "स्थापन", "स्थापित"],
                    "बनाए रखना": ["बनाए रखना", "बनाए रखना", "बनाए रखना"],
                    "रूपांतर": ["रूपांतर", "रूपांतर", "रूपांतर"],
                    "प्रोत्साहन": ["प्रोत्साहन", "प्रोत्साहन", "प्रोत्साहन"],
                    "वास्तविक": ["वास्तविक", "वास्तविक", "वास्तविक"],
                    "कम करना": ["कम करना", "कमी", "कम करना"],
                    "प्रतिबिंब": ["प्रतिबिंब", "प्रतिबिंब", "प्रतिबिंब"],
                    "समर्थन": ["समर्थन", "समर्थन", "समर्थन"],
                    "ध्यान": ["ध्यान", "ध्यान", "ध्यान"],
                    "अन्वेषण": ["अन्वेषण", "अन्वेषक", "अन्वेषण"]
                },
                "formal_alternatives": {
                    "अच्छा": "उत्कृष्ट / प्रशंसनीय", "बहुत अच्छा": "विशेष रूप से अच्छा / उत्कृष्ट",
                    "रहस्यमय": "अद्भुत / विस्मयकारी", "शानदार": "उदाहरणात्मक / शानदार",
                    "सुपर": "बहुत / अत्यधिक", "चीज़": "वस्तु / मुद्दा",
                    "वस्तु": "वस्तु / विषय", "लड़का": "पुरुष / व्यक्ति",
                    "लड़की": "महिला / व्यक्ति", "दोस्त": "मित्र / सहकर्मी",
                    "भाई": "भाई / सहकर्मी", "बहन": "बहन / सहकर्मी",
                    "घर": "निवास / आवास", "समय": "समय / अवधि",
                    "पैसे": "संसाधन / धन", "काम": "कार्य / गतिविधि",
                    "जिंदगी": "जीवन / दैनिक जीवन", "अच्छा": "स्वीकार्य / संतुष्टिकारक",
                    "बुरा": "असंतोषजनक / नकारात्मक", "बड़ा": "महत्वपूर्ण / विशाल"
                }
            },
            "el": {
                "oral_markers": ["ε", "μα", "ω", "ναι", "όχι",
                                "ξερετε", "ουτως", "ετσι", "αλλα", "ωραία",
                                "γεια", "αντίο", "ευχαριστώ", "παρακαλώ",
                                "συγγνώμη", "ω", "α", "ε"],
                "contractions": {},
                "informal_words": ["κρύο", "υπέροχο", "ωραίο", "μεγάλο", "μικρό",
                                  "πράγμα", "πράγματα", "άνθρωπος", "φίλος", "αδελφός",
                                  "αδελφή", "σπίτι", "χρόνος", "χρήματα", "δουλειά",
                                  "ζωή", "καλός", "κακός", "μεγάλος", "μικρός"],
                "oral_patterns": [
                    (r"Ε", "语气词"), (r"Μα", "转折"),
                    (r"Ω", "感叹"), (r"Ναι", "同意"),
                    (r"Όχι", "否定"), (r"Ξέρεις", "填充"),
                    (r"Ούτως", "解释"), (r"Ετσι", "结论"),
                    (r"Αλλά", "转折"), (r"Ωραία", "评价"),
                    (r"Γεια", "问候"), (r"Αντίο", "告别"),
                    (r"Ευχαριστώ", "感谢"), (r"Παρακαλώ", "请求"),
                    (r"Συγγνώμη", "道歉"), (r"Ω", "惊讶"),
                    (r"Α", "理解"), (r"Ε", "语气词")
                ],
                "complex_patterns": [
                    (r"Είναι", "强调"), (r"Υπάρχει", "存在"),
                    (r"Ο λόγος", "原因"), (r"Αν", "条件"),
                    (r"Παρόλο που", "让步"), (r"Γιατί", "原因"),
                    (r"Όταν", "时间"), (r"Για να", "目的"),
                    (r"Έτσι", "结果"), (r"Αν και", "让步"),
                    (r"Σύμφωνα με", "根据"), (r"Σχετικά με", "关于"),
                    (r"Με", "伴随"), (r"Μετά", "之后")
                ],
                "collocations": {
                    "σημαντικός": ["σημαντική επίδραση", "σημαντική αλλαγή", "σημαντική διαφορά", "σημαντικός ρόλος"],
                    "επίδραση": ["μεγάλη επίδραση", "θετική επίδραση", "αρνητική επίδραση", "σημαντική επίδραση"],
                    "πετύχει": ["πετύχει στόχο", "πετύχει επιτυχία", "πετύχει αποτέλεσμα", "πετύχει επίπεδο"],
                    "συνεισφέρει": ["συνεισφέρει σε", "σημαντική συνεισφορά", "θετική συνεισφορά", "συνεισφέρει στην ανάπτυξη"],
                    "καθορίζει": ["καθορίζει το αποτέλεσμα", "καθορίζει την αιτία", "καθορίζει την τιμή", "καθορίζει την κατεύθυνση"],
                    "δύναμη": ["δύναμη να", "μεγάλη δύναμη", "περιορισμένη δύναμη", "μεγιστή δύναμη"],
                    "προσπέκτιβα": ["από άλλης προσπέκτιβας", "νέα προσπέκτιβα", "σωστή προσπέκτιβα", "κριτική προσπέκτιβα"],
                    "αναλύει": ["αναλύει δεδομένα", "αναλύει την κατάσταση", "αναλύει το πρόβλημα", "αναλύει την τάση"],
                    "εκτιμά": ["εκτιμά την απόδοση", "εκτιμά τις επιλογές", "εκτιμά την ποιότητα", "εκτιμά την αποτελεσματικότητα"],
                    "καθιστά": ["καθιστά σχέση", "καθιστά κανόνα", "καθιστά σύστημα", "καθιστά σύνδεση"],
                    "διατηρεί": ["διατηρεί την ισορροπία", "διατηρεί την σχέση", "διατηρεί την ποιότητα", "διατηρεί το πρότυπο"],
                    "μεταμορφώνει": ["μεταμορφώνει σε", "μεταμορφώνει την διαδικασία", "μεταμορφώνει την βιομηχανία", "μεταμορφώνει τις επιχειρήσεις"],
                    "προωθεί": ["προωθεί την ανάπτυξη", "προωθεί το προϊόν", "προωθεί την ανάπτυξη"],
                    "πραγματοποιεί": ["πραγματοποιεί τον στόχο", "πραγματοποιεί το όνειρο", "πραγματοποιεί την δύναμη"],
                    "μειώνει": ["μειώνει το κόστος", "μειώνει τον κίνδυνο", "μειώνει τα απορρίμματα"],
                    "αντιπροσωπεύει": ["αντιπροσωπεύει κάτι", "αντιπροσωπεύει την κατάσταση", "αντιπροσωπεύει την αλλαγή"],
                    "υποστηρίζει": ["υποστηρίζει την απόφαση", "προσφέρει υποστήριξη", "υποστηρίζει την ιδέα"],
                    "εστία": ["εστία σε", "εστία στην προσοχή"],
                    "εξερευνά": ["εξερευνά τις επιλογές", "εξερευνά τις δυνατότητες", "εξερευνά την αγορά"]
                },
                "synonyms": {
                    "σημαντικός": ["οριστικός", " βασικός", "προσφάτως", "επιφανής"],
                    "επίδραση": ["οφέλος", "αποτέλεσμα", "παράγωγο", "αλλάζοντας"],
                    "πετύχει": ["αναλαμβάνει", "πρόσβαση", "αναλαμβάνει", "εκτελεί"],
                    "συνεισφέρει": ["προσφέρει", "συμμετέχει", "βοηθά", "υποστηρίζει"],
                    "καθορίζει": ["καθορίζει", "ορίζει", "δηλώνει", "ορισμός"],
                    "δύναμη": ["δύναμη", "ανάπτυξη", "εργαλείο", "δύναμη"],
                    "προσπέκτιβα": ["προσπέκτιβα", "πρόσθετος", "αντιπροσωπεύει", "προσπέκτιβα"],
                    "αναλύει": ["επισκεπτόμενος", "εκτιμά", "καταγράφει", "αναλύει"],
                    "εκτιμά": ["εκτιμά", "καταγράφει", "μετρά", "ελέγχει"],
                    "καθιστά": ["κατασκευάζει", "κατασκευάζει", "οργανώνει", "εγκαθιστώντας"],
                    "διατηρεί": ["διατηρεί", "συντηρεί", "συντηρεί", "συντηρεί"],
                    "μεταμορφώνει": ["μεταμορφώνει", "μεταμορφώνει", "προσαρμόζει", "τροποποιεί"],
                    "προωθεί": ["προωθεί", "συντηρεί", "ταχύνει", "βελτιώνει"],
                    "πραγματοποιεί": ["πραγματοποιεί", "αναλαμβάνει", "εκτελεί", "αναγνωρίζει"],
                    "μειώνει": ["μειώνει", "μειώνει", "περιορίζει", "ελαχιστοποιεί"],
                    "αντιπροσωπεύει": ["προσφέρεται", "δηλώνει", "επισημαίνει", "καταφέρει"],
                    "υποστηρίζει": ["συντηρεί", "βοηθά", "συντηρεί", "εκπροσωπεί"],
                    "εστία": ["συνδυάζει", "συγκεντρώνεται", "προτεραιότητα", "κέντρο"],
                    "εξερευνά": ["ανακαλύπτει", "εξετάζει", "μελετά", "ανακαλύπτει"]
                },
                "word_families": {
                    "σημαντικός": ["σημαντικός", "σημαντικότητα", "σημαντικός"],
                    "επίδραση": ["επίδραση", "επιδραστικός", "επιδραστικός"],
                    "πετύχει": ["πετύχει", "πετυχία", "πετυχία"],
                    "συνεισφέρει": ["συνεισφέρει", "συνεισφορά", "συνεισφορά"],
                    "καθορίζει": ["καθορίζει", "καθορισμός", "καθορισμός"],
                    "δύναμη": ["δύναμη", "δυναμικός", "δυναμικός"],
                    "προσπέκτιβα": ["προσπέκτιβα", "προσπεκτικός", "προσπεκτικός"],
                    "αναλύει": ["αναλύει", "ανάλυση", "αναλυτικός"],
                    "εκτιμά": ["εκτιμά", "εκτίμηση", "εκτιμητικός"],
                    "καθιστά": ["καθιστά", "κατάσταση", "κατάσταση"],
                    "διατηρεί": ["διατηρεί", "διατήρηση", "διατηρητικός"],
                    "μεταμορφώνει": ["μεταμορφώνει", "μεταμόρφωση", "μεταμορφικός"],
                    "προωθεί": ["προωθεί", "προώθηση", "προωθητικός"],
                    "πραγματοποιεί": ["πραγματοποιεί", "πραγματοποίηση", "πραγματοποιητικός"],
                    "μειώνει": ["μειώνει", "μείωση", "μειωτικός"],
                    "αντιπροσωπεύει": ["αντιπροσωπεύει", "αντιπροσώπευση", "αντιπροσωπευτικός"],
                    "υποστηρίζει": ["υποστηρίζει", "υποστήριξη", "υποστηρικτικός"],
                    "εστία": ["εστία", "εστίαση", "εστιατικός"],
                    "εξερευνά": ["εξερευνά", "εξερεύνηση", "εξερευνητικός"]
                },
                "formal_alternatives": {
                    "κρύο": "επιβεβαιωμένο / εξαιρετικό", "υπέροχο": "σπουδαίο / εξαιρετικό",
                    "ωραίο": "καλός / ευτυχισμένος", "μεγάλο": "σημαντικό / μεγάλο",
                    "μικρό": "περιορισμένο / μικρό", "πράγμα": "προϊόν / θέμα",
                    "πράγματα": "προϊόντα / θέματα", "άνθρωπος": "προσωπικό / άτομο",
                    "φίλος": "φίλος / συνεργάτης", "αδελφός": "αδελφός / συνεργάτης",
                    "αδελφή": "αδελφή / συνεργάτης", "σπίτι": "σπίτι / κατοικία",
                    "χρόνος": "χρόνος / περίοδος", "χρήματα": "ποροι / χρηματικά",
                    "δουλειά": "δουλειά / δραστηριότητα", "ζωή": "ζωή / καθημερινή ζωή",
                    "καλός": "καλός / ικανοποιητικός", "κακός": "κακός / αρνητικός",
                    "μεγάλος": "μεγάλος / σημαντικός", "μικρός": "μικρός / περιορισμένος"
                }
            },
            "tr": {
                "oral_markers": ["eh", "ha", "şey", "yani", "tamam",
                                "bilirsin", "gibi", "işte", "ama", "de",
                                "merhaba", "hoşça kal", "teşekkürler", "lütfen",
                                "üzgünüm", "afedersiniz", "ah", "oh", "ey"],
                "contractions": {},
                "informal_words": ["harika", "güzel", "super", "cool", "muhteşem",
                                  "şey", "şeyler", "adam", "kız", "arkadaş",
                                  "abi", "abla", "ev", "zaman", "para",
                                  "iş", "hayat", "güzel", "kötü", "büyük"],
                "oral_patterns": [
                    (r"Eh", "语气词"), (r"Ha", "感叹"),
                    (r"Şey", "填充"), (r"Yani", "解释"),
                    (r"Tamam", "同意"), (r"Bilirsin", "填充"),
                    (r"Gibi", "举例"), (r"İşte", "总结"),
                    (r"Ama", "转折"), (r"De", "强调"),
                    (r"Merhaba", "问候"), (r"Hoşça kal", "告别"),
                    (r"Teşekkürler", "感谢"), (r"Lütfen", "请求"),
                    (r"Üzgünüm", "道歉"), (r"Ah", "惊讶"),
                    (r"Oh", "理解"), (r"Ey", "称呼")
                ],
                "complex_patterns": [
                    (r"O", "强调"), (r"Var", "存在"),
                    (r"Sebep", "原因"), (r"Eğer", "条件"),
                    (r"Rakipsiz", "让步"), (r"Çünkü", "原因"),
                    (r"Ne zaman", "时间"), (r"Için", "目的"),
                    (r"Böylece", "结果"), (r"Yine de", "让步"),
                    (r"Göre", "根据"), (r"Hakkında", "关于"),
                    (r"İle", "伴随"), (r"Sonra", "之后")
                ],
                "collocations": {
                    "önemli": ["önemli etki", "önemli değişiklik", "önemli fark", "önemli rol"],
                    "etki": ["etki etmek", "büyük etki", "olumlu etki", "negatif etki", "önemli etki"],
                    "başarmak": ["hedefi başarmak", "başarıya ulaşmak", "sonucu başarmak", "seviyeye ulaşmak"],
                    "katkıda bulunmak": ["katkıda bulunmak", "önemli katkı", "olumlu katkı", "gelişime katkıda bulunmak"],
                    "belirlemek": ["sonucu belirlemek", "nedenini belirlemek", "fiyatı belirlemek", "yönü belirlemek"],
                    "potansiyel": ["potansiyel vardır", "potansiyeli tanımak", "potansiyeli kullanmak", "maksimum potansiyel"],
                    "perspektif": ["perspektiften", "başka perspektif", "yeni perspektif", "kendi perspektifi"],
                    "analiz etmek": ["verileri analiz etmek", "durumu analiz etmek", "sorunu analiz etmek", "trendi analiz etmek"],
                    "değerlendirmek": ["performansı değerlendirmek", "seçenekleri değerlendirmek", "kaliteyi değerlendirmek", "etkinliği değerlendirmek"],
                    "kurmak": ["ilişki kurmak", "kural kurmak", "sistem kurmak", "bağlantı kurmak"],
                    "sürdürmek": ["dengeni sürdürmek", "ilişkiyi sürdürmek", "kaliteyi sürdürmek", "standartı sürdürmek"],
                    "dönüştürmek": ["dönüştürmek", "süreci dönüştürmek", "endüstriyi dönüştürmek", "işi dönüştürmek"],
                    "teşvik etmek": ["gelişimi teşvik etmek", "ürünü teşvik etmek", "büyümeyi teşvik etmek"],
                    "gerçekleştirmek": ["hedefi gerçekleştirmek", "rüya gerçekleştirmek", "potansiyeli gerçekleştirmek"],
                    "azaltmak": ["maliyetleri azaltmak", "riski azaltmak", "atıkları azaltmak"],
                    "yansıtmak": ["yansıtmak", "durumu yansıtmak", "değişimi yansıtmak"],
                    "desteklemek": ["kararı desteklemek", "destek sağlamak", "fikri desteklemek"],
                    "odaklanmak": ["odaklanmak", "dikkati odaklanmak"],
                    "keşfetmek": ["seçenekleri keşfetmek", "olasıılıkları keşfetmek", "piyasayı keşfetmek"]
                },
                "synonyms": {
                    "önemli": ["temel", "ana", "kilit", "vital"],
                    "etki": ["etki", "sonuç", "etki", "sonuç"],
                    "başarmak": ["başarmak", "ulaşmak", "gerçekleştirmek", "tamamlamak"],
                    "katkıda bulunmak": ["katkıda bulunmak", "katkıda bulunmak", "yardımcı olmak", "desteklemek"],
                    "belirlemek": ["belirlemek", "belirlemek", "etkilemek", "tanımlamak"],
                    "potansiyel": ["potansiyel", "fırsat", "kabiliyet", "olasıılık"],
                    "perspektif": ["perspektif", "bakış açısı", "yaklaşım", "açısından"],
                    "analiz etmek": ["analiz etmek", "incelemek", "değerlendirmek", "araştırmak"],
                    "değerlendirmek": ["değerlendirmek", "değerlendirmek", "ölçmek", "doğrulamak"],
                    "kurmak": ["kurmak", "inşa etmek", "organize etmek", "kurmak"],
                    "sürdürmek": ["sürdürmek", "korumak", "desteklemek", "devam ettirmek"],
                    "dönüştürmek": ["dönüştürmek", "dönüştürmek", "uyarlamak", "değiştirmek"],
                    "teşvik etmek": ["teşvik etmek", "desteklemek", "hızlandırmak", "iyileştirmek"],
                    "gerçekleştirmek": ["gerçekleştirmek", "başarmak", "yapmak", "tanımak"],
                    "azaltmak": ["azaltmak", "azaltmak", "sınırlamak", "en aza indirmek"],
                    "yansıtmak": ["yansıtmak", "göstermek", "göstermek", "ortaya çıkarmak"],
                    "desteklemek": ["desteklemek", "yardımcı olmak", "desteklemek", "savunmak"],
                    "odaklanmak": ["odaklanmak", "toplanmak", "önceliklendirmek", "merkezlemek"],
                    "keşfetmek": ["keşfetmek", "araştırmak", "incelemek", "bulmak"]
                },
                "word_families": {
                    "önemli": ["önemli", "önem", "önemli"],
                    "etki": ["etki", "etkili", "etkili"],
                    "başarmak": ["başarmak", "başarı", "başarı"],
                    "katkıda bulunmak": ["katkıda bulunmak", "katkı", "katkı"],
                    "belirlemek": ["belirlemek", "belirleme", "belirleme"],
                    "potansiyel": ["potansiyel", "potansiyel", "potansiyel"],
                    "perspektif": ["perspektif", "perspektif", "perspektif"],
                    "analiz etmek": ["analiz etmek", "analiz", "analitik"],
                    "değerlendirmek": ["değerlendirmek", "değerlendirme", "değerlendirme"],
                    "kurmak": ["kurmak", "kurulum", "kurulum"],
                    "sürdürmek": ["sürdürmek", "sürdürme", "sürdürme"],
                    "dönüştürmek": ["dönüştürmek", "dönüşüm", "dönüşüm"],
                    "teşvik etmek": ["teşvik etmek", "teşvik", "teşvik"],
                    "gerçekleştirmek": ["gerçekleştirmek", "gerçekleştirme", "gerçekleştirme"],
                    "azaltmak": ["azaltmak", "azaltma", "azaltma"],
                    "yansıtmak": ["yansıtmak", "yansıtma", "yansıtma"],
                    "desteklemek": ["desteklemek", "destek", "destek"],
                    "odaklanmak": ["odaklanmak", "odaklanma", "odaklanma"],
                    "keşfetmek": ["keşfetmek", "keşif", "keşif"]
                },
                "formal_alternatives": {
                    "harika": "muazzam / etkileyici", "güzel": "harika / mükemmel",
                    "super": "çok / aşırı", "cool": "etkileyici / harika",
                    "muhteşem": "muhteşem / harika", "şey": "nesne / konu",
                    "şeyler": "nesneler / konular", "adam": "adam / kişi",
                    "kız": "kız / kişi", "arkadaş": "arkadaş / iş arkadaşı",
                    "abi": "abi / kardeş", "abla": "abla / kardeş",
                    "ev": "ev / konut", "zaman": "zaman / dönem",
                    "para": "para / kaynaklar", "iş": "iş / faaliyet",
                    "hayat": "hayat / günlük hayat", "güzel": "kabul edilebilir / tatmin edici",
                    "kötü": "kötü / negatif", "büyük": "büyük / önemli"
                }
            },
            "vi": {
                "oral_markers": ["ừ", "à", "ạ", "ơi", "này",
                                "thì", "cũng", "như", "vậy", "chà",
                                "chào", "tạm biệt", "cảm ơn", "làm ơn",
                                "xin lỗi", "ah", "oh", "ừ"],
                "contractions": {},
                "informal_words": ["ngầu", "tuyệt", "hay", "cool", "chất",
                                  "cái", "của", "người", "bạn", "cậu",
                                  "anh", "chị", "em", "nhà", "giờ",
                                  "tiền", "công việc", "cuộc sống", "tốt", "xấu"],
                "oral_patterns": [
                    (r"Ừ", "同意"), (r"À", "感叹"),
                    (r"Ọi", "惊讶"), (r"Này", "称呼"),
                    (r"Thì", "连接"), (r"Cũng", "强调"),
                    (r"Như", "举例"), (r"Vậy", "总结"),
                    (r"Chà", "语气"), (r"Chào", "问候"),
                    (r"Tạm biệt", "告别"), (r"Cảm ơn", "感谢"),
                    (r"Làm ơn", "请求"), (r"Xin lỗi", "道歉"),
                    (r"Ah", "惊讶"), (r"Oh", "理解")
                ],
                "complex_patterns": [
                    (r"Nếu", "条件"), (r"Mặc dù", "让步"),
                    (r"Vì", "原因"), (r"Để", "目的"),
                    (r"Khi", "时间"), (r"Đến khi", "直到"),
                    (r"Như vậy", "结果"), (r"Lại", "重复"),
                    (r"Về", "关于"), (r"Đối với", "对于"),
                    (r"Bằng", "方式"), (r"Giữa", "之间"),
                    (r"Sau", "之后"), (r"Trước", "之前")
                ],
                "collocations": {
                    "quan trọng": ["ảnh hưởng quan trọng", "sự thay đổi quan trọng", "sự khác biệt quan trọng", "vai trò quan trọng"],
                    "ảnh hưởng": ["có ảnh hưởng đến", "ảnh hưởng lớn", "ảnh hưởng tích cực", "ảnh hưởng tiêu cực"],
                    "đạt được": ["đạt được mục tiêu", "đạt được thành công", "đạt được kết quả"],
                    "cống hiến": ["cống hiến cho", "cống hiến lớn", "cống hiến tích cực"],
                    "xác định": ["xác định kết quả", "xác định nguyên nhân", "xác định hướng"],
                    "tiềm năng": ["có tiềm năng", "phát hiện tiềm năng", "tiềm năng lớn"],
                    "góc nhìn": ["từ góc nhìn", "góc nhìn mới", "góc nhìn khác"],
                    "phân tích": ["phân tích dữ liệu", "phân tích tình huống", "phân tích vấn đề"],
                    "đánh giá": ["đánh giá hiệu suất", "đánh giá lựa chọn", "đánh giá chất lượng"],
                    "xây dựng": ["xây dựng mối quan hệ", "xây dựng quy tắc", "xây dựng hệ thống"],
                    "duy trì": ["duy trì sự cân bằng", "duy trì mối quan hệ", "duy trì chất lượng"],
                    "biến đổi": ["biến đổi quy trình", "biến đổi ngành", "biến đổi kinh doanh"],
                    "xúc tiến": ["xúc tiến sự phát triển", "xúc tiến sản phẩm", "xúc tiến tăng trưởng"],
                    "thực hiện": ["thực hiện mục tiêu", "thực hiện ước mơ", "thực hiện tiềm năng"],
                    "giảm": ["giảm chi phí", "giảm rủi ro", "giảm chất thải"],
                    "phản ánh": ["phản ánh tình huống", "phản ánh sự thay đổi"],
                    "hỗ trợ": ["hỗ trợ quyết định", "cung cấp hỗ trợ", "hỗ trợ ý tưởng"],
                    "tập trung": ["tập trung vào", "tập trung sự chú ý"],
                    "khám phá": ["khám phá lựa chọn", "khám phá khả năng", "khám phá thị trường"]
                },
                "synonyms": {
                    "quan trọng": ["cực kỳ", "vital", "đắt giá", "một phần"],
                    "ảnh hưởng": ["tác động", "kết quả", "hiệu ứng", "sự thay đổi"],
                    "đạt được": ["thành công", "lấy được", "hoàn thành", "thực hiện"],
                    "cống hiến": ["phát triển", "tham gia", "hỗ trợ", "tổ chức"],
                    "xác định": ["chỉ định", "chọn", "quyết định", "thiết lập"],
                    "tiềm năng": ["khả năng", "kỳ vọng", "sự phát triển", "điểm mạnh"],
                    "góc nhìn": ["ý kiến", "quan điểm", "nhìn nhận", "quan sát"],
                    "phân tích": ["điều tra", "kiểm tra", "thảo luận", "khảo sát"],
                    "đánh giá": ["phân tích", "phát biểu", "đo lường", "xác minh"],
                    "xây dựng": ["sửa chữa", "thiết lập", "phát triển", "tổ chức"],
                    "duy trì": ["bảo quản", "bảo tồn", "tiếp tục", "bổ sung"],
                    "biến đổi": ["chuyển đổi", "thay đổi", "làm mới", "sửa đổi"],
                    "xúc tiến": ["hỗ trợ", "kích thích", "tăng tốc", "cải thiện"],
                    "thực hiện": ["tương tác", "làm", "xây dựng", "phát hiện"],
                    "giảm": ["suy giảm", "giảm thiểu", "hạn chế", "giảm xuống"],
                    "phản ánh": ["biểu thị", "phát hiện", "cân nhắc", "phát biểu"],
                    "hỗ trợ": ["giúp đỡ", "sủng hộ", "bảo vệ", "tăng cường"],
                    "tập trung": ["tập hợp", "chú ý", "ưu tiên", "tập trung"],
                    "khám phá": ["phát hiện", "thực hiện", "thu thập", "nhận biết"]
                },
                "word_families": {
                    "quan trọng": ["quan trọng", "sự quan trọng", "quan trọng"],
                    "ảnh hưởng": ["ảnh hưởng", "ảnh hưởng", "ảnh hưởng"],
                    "đạt được": ["đạt được", "sự đạt được", "đạt được"],
                    "cống hiến": ["cống hiến", "sự cống hiến", "cống hiến"],
                    "xác định": ["xác định", "sự xác định", "xác định"],
                    "tiềm năng": ["tiềm năng", "tiềm năng", "tiềm năng"],
                    "góc nhìn": ["góc nhìn", "góc nhìn", "góc nhìn"],
                    "phân tích": ["phân tích", "sự phân tích", "phân tích"],
                    "đánh giá": ["đánh giá", "sự đánh giá", "đánh giá"],
                    "xây dựng": ["xây dựng", "sự xây dựng", "xây dựng"],
                    "duy trì": ["duy trì", "sự duy trì", "duy trì"],
                    "biến đổi": ["biến đổi", "sự biến đổi", "biến đổi"],
                    "xúc tiến": ["xúc tiến", "sự xúc tiến", "xúc tiến"],
                    "thực hiện": ["thực hiện", "sự thực hiện", "thực hiện"],
                    "giảm": ["giảm", "sự giảm", "giảm"],
                    "phản ánh": ["phản ánh", "sự phản ánh", "phản ánh"],
                    "hỗ trợ": ["hỗ trợ", "sự hỗ trợ", "hỗ trợ"],
                    "tập trung": ["tập trung", "sự tập trung", "tập trung"],
                    "khám phá": ["khám phá", "sự khám phá", "khám phá"]
                },
                "formal_alternatives": {
                    "ngầu": "ấn tượng / tuyệt vời", "tuyệt": "tuyệt vời / xuất sắc",
                    "hay": "thú vị / ấn tượng", "cool": "ấn tượng / tuyệt vời",
                    "chất": "tốt / tuyệt vời", "cái": "vật thể / mục",
                    "của": "của", "người": "cá nhân / người",
                    "bạn": "bạn / đồng nghiệp", "cậu": "bạn / người",
                    "anh": "anh / người", "chị": "chị / người",
                    "em": "em / người", "nhà": "căn hộ / nơi ở",
                    "giờ": "thời gian / khoảng thời gian", "tiền": "tài nguyên / tiền tệ",
                    "công việc": "việc làm / hoạt động", "cuộc sống": "cuộc sống / cuộc sống hàng ngày",
                    "tốt": "tốt / khả thi", "xấu": "xấu / tiêu cực"
                }
            },
            "th": {
                "oral_markers": ["เออ", "อืม", "อ่ะ", "นะ", "นี่",
                                "แล้ว", "ก็", "เหมือน", "อย่างนั้น", "ช่าง",
                                "สวัสดี", "ลาก่อน", "ขอบคุณ", "กรุณา",
                                "ขอโทษ", "อ้า", "โอ", "เออ"],
                "contractions": {},
                "informal_words": ["เจ๋ง", "สุดยอด", "เยี่ยม", "เก๋", "เท่",
                                  "ของ", "เรื่อง", "คน", "เพื่อน", "พวกเรา",
                                  "พี่", "น้อง", "บ้าน", "เวลา", "เงิน",
                                  "งาน", "ชีวิต", "ดี", "ร้าย", "ใหญ่"],
                "oral_patterns": [
                    (r"เออ", "语气"), (r"อืม", "思考"),
                    (r"อ่ะ", "确认"), (r"นะ", "强调"),
                    (r"นี่", "指向"), (r"แล้ว", "连接"),
                    (r"ก็", "强调"), (r"เหมือน", "举例"),
                    (r"อย่างนั้น", "解释"), (r"ช่าง", "语气"),
                    (r"สวัสดี", "问候"), (r"ลาก่อน", "告别"),
                    (r"ขอบคุณ", "感谢"), (r"กรุณา", "请求"),
                    (r"ขอโทษ", "道歉"), (r"อ้า", "惊讶"),
                    (r"โอ", "理解"), (r"เออ", "同意")
                ],
                "complex_patterns": [
                    (r"ถ้า", "条件"), (r"แม้ว่า", "让步"),
                    (r"เพราะ", "原因"), (r"เพื่อ", "目的"),
                    (r"เมื่อ", "时间"), (r"จนกระทั่ง", "直到"),
                    (r"ดังนั้น", "结果"), (r"อีกครั้ง", "重复"),
                    (r"เกี่ยวกับ", "关于"), (r"สำหรับ", "对于"),
                    (r"ด้วย", "方式"), (r"ระหว่าง", "之间"),
                    (r"หลัง", "之后"), (r"ก่อน", "之前")
                ],
                "collocations": {
                    "สำคัญ": ["ผลกระทบสำคัญ", "การเปลี่ยนแปลงสำคัญ", "ความแตกต่างสำคัญ", "บทบาทสำคัญ"],
                    "ผลกระทบ": ["มีผลกระทบต่อ", "ผลกระทบใหญ่", "ผลกระทบเชิงบวก", "ผลกระทบเชิงลบ"],
                    "บรรลุ": ["บรรลุเป้าหมาย", "บรรลุความสำเร็จ", "บรรลุผลลัพธ์"],
                    "มีส่วนร่วม": ["มีส่วนร่วมต่อ", "มีส่วนร่วมใหญ่", "มีส่วนร่วมเชิงบวก"],
                    "กำหนด": ["กำหนดผลลัพธ์", "กำหนดสาเหตุ", "กำหนดทิศทาง"],
                    "ศักยภาพ": ["มีศักยภาพ", "ค้นพบศักยภาพ", "ศักยภาพใหญ่"],
                    "มุมมอง": ["จากมุมมอง", "มุมมองใหม่", "มุมมองที่แตกต่าง"],
                    "วิเคราะห์": ["วิเคราะห์ข้อมูล", "วิเคราะห์สถานการณ์", "วิเคราะห์ปัญหา"],
                    "ประเมิน": ["ประเมินประสิทธิภาพ", "ประเมินทางเลือก", "ประเมินคุณภาพ"],
                    "สร้าง": ["สร้างความสัมพันธ์", "สร้างกฎ", "สร้างระบบ"],
                    "รักษา": ["รักษาสมดุล", "รักษาความสัมพันธ์", "รักษาคุณภาพ"],
                    "เปลี่ยนแปลง": ["เปลี่ยนแปลงกระบวนการ", "เปลี่ยนแปลงอุตสาหกรรม", "เปลี่ยนแปลงธุรกิจ"],
                    "ส่งเสริม": ["ส่งเสริมการพัฒนา", "ส่งเสริมผลิตภัณฑ์", "ส่งเสริมการเติบโต"],
                    "ดำเนินการ": ["ดำเนินการเป้าหมาย", "ดำเนินการความฝัน", "ดำเนินการศักยภาพ"],
                    "ลด": ["ลดต้นทุน", "ลดความเสี่ยง", "ลดขยะ"],
                    "สะท้อน": ["สะท้อนสถานการณ์", "สะท้อนการเปลี่ยนแปลง"],
                    "สนับสนุน": ["สนับสนุนการตัดสินใจ", "ให้การสนับสนุน", "สนับสนุนไอเดีย"],
                    "มุ่งเน้น": ["มุ่งเน้นไปที่", "มุ่งเน้นความสนใจ"],
                    "สำรวจ": ["สำรวจทางเลือก", "สำรวจความเป็นไปได้", "สำรวจตลาด"]
                },
                "synonyms": {
                    "สำคัญ": ["สำคัญ", "สําคัญ", "สําคัญ", "สําคัญ"],
                    "ผลกระทบ": ["ผลกระทบ", "ผลกระทบ", "ผลกระทบ", "ผลกระทบ"],
                    "บรรลุ": ["บรรลุ", "บรรลุ", "บรรลุ", "บรรลุ"],
                    "มีส่วนร่วม": ["มีส่วนร่วม", "มีส่วนร่วม", "มีส่วนร่วม", "มีส่วนร่วม"],
                    "กำหนด": ["กำหนด", "กำหนด", "กำหนด", "กำหนด"],
                    "ศักยภาพ": ["ศักยภาพ", "ศักยภาพ", "ศักยภาพ", "ศักยภาพ"],
                    "มุมมอง": ["มุมมอง", "มุมมอง", "มุมมอง", "มุมมอง"],
                    "วิเคราะห์": ["วิเคราะห์", "วิเคราะห์", "วิเคราะห์", "วิเคราะห์"],
                    "ประเมิน": ["ประเมิน", "ประเมิน", "ประเมิน", "ประเมิน"],
                    "สร้าง": ["สร้าง", "สร้าง", "สร้าง", "สร้าง"],
                    "รักษา": ["รักษา", "รักษา", "รักษา", "รักษา"],
                    "เปลี่ยนแปลง": ["เปลี่ยนแปลง", "เปลี่ยนแปลง", "เปลี่ยนแปลง", "เปลี่ยนแปลง"],
                    "ส่งเสริม": ["ส่งเสริม", "ส่งเสริม", "ส่งเสริม", "ส่งเสริม"],
                    "ดำเนินการ": ["ดำเนินการ", "ดำเนินการ", "ดำเนินการ", "ดำเนินการ"],
                    "ลด": ["ลด", "ลด", "ลด", "ลด"],
                    "สะท้อน": ["สะท้อน", "สะท้อน", "สะท้อน", "สะท้อน"],
                    "สนับสนุน": ["สนับสนุน", "สนับสนุน", "สนับสนุน", "สนับสนุน"],
                    "มุ่งเน้น": ["มุ่งเน้น", "มุ่งเน้น", "มุ่งเน้น", "มุ่งเน้น"],
                    "สำรวจ": ["สำรวจ", "สำรวจ", "สำรวจ", "สำรวจ"]
                },
                "word_families": {
                    "สำคัญ": ["สำคัญ", "สําคัญ", "สําคัญ"],
                    "ผลกระทบ": ["ผลกระทบ", "ผลกระทบ", "ผลกระทบ"],
                    "บรรลุ": ["บรรลุ", "บรรลุ", "บรรลุ"],
                    "มีส่วนร่วม": ["มีส่วนร่วม", "มีส่วนร่วม", "มีส่วนร่วม"],
                    "กำหนด": ["กำหนด", "กำหนด", "กำหนด"],
                    "ศักยภาพ": ["ศักยภาพ", "ศักยภาพ", "ศักยภาพ"],
                    "มุมมอง": ["มุมมอง", "มุมมอง", "มุมมอง"],
                    "วิเคราะห์": ["วิเคราะห์", "วิเคราะห์", "วิเคราะห์"],
                    "ประเมิน": ["ประเมิน", "ประเมิน", "ประเมิน"],
                    "สร้าง": ["สร้าง", "สร้าง", "สร้าง"],
                    "รักษา": ["รักษา", "รักษา", "รักษา"],
                    "เปลี่ยนแปลง": ["เปลี่ยนแปลง", "เปลี่ยนแปลง", "เปลี่ยนแปลง"],
                    "ส่งเสริม": ["ส่งเสริม", "ส่งเสริม", "ส่งเสริม"],
                    "ดำเนินการ": ["ดำเนินการ", "ดำเนินการ", "ดำเนินการ"],
                    "ลด": ["ลด", "ลด", "ลด"],
                    "สะท้อน": ["สะท้อน", "สะท้อน", "สะท้อน"],
                    "สนับสนุน": ["สนับสนุน", "สนับสนุน", "สนับสนุน"],
                    "มุ่งเน้น": ["มุ่งเน้น", "มุ่งเน้น", "มุ่งเน้น"],
                    "สำรวจ": ["สำรวจ", "สำรวจ", "สำรวจ"]
                },
                "formal_alternatives": {
                    "เจ๋ง": "น่าประทับใจ / สุดยอด", "สุดยอด": "สุดยอด / เยี่ยม",
                    "เยี่ยม": "เยี่ยม / มีคุณภาพ", "เก๋": "น่าประทับใจ / เยี่ยม",
                    "เท่": "น่าประทับใจ / สวยงาม", "ของ": "สิ่งของ / วัตถุ",
                    "เรื่อง": "เรื่อง / สิ่ง", "คน": "บุคคล / คน",
                    "เพื่อน": "เพื่อน / เพื่อนร่วมงาน", "พวกเรา": "เรา / หมู่หนึ่ง",
                    "พี่": "พี่ / เพื่อนร่วมงาน", "น้อง": "น้อง / เพื่อนร่วมงาน",
                    "บ้าน": "บ้าน / ที่อยู่อาศัย", "เวลา": "เวลา / ช่วงเวลา",
                    "เงิน": "เงิน / ทรัพยากร", "งาน": "งาน / กิจกรรม",
                    "ชีวิต": "ชีวิต / ชีวิตประจำวัน", "ดี": "ดี / มีคุณภาพ",
                    "ร้าย": "ร้าย / ป้องกัน", "ใหญ่": "ใหญ่ / มีความสำคัญ"
                }
            },
            "id": {
                "oral_markers": ["eh", "yah", "ya", "loh", "deh",
                                "jadi", "dan", "seperti", "itu", "nih",
                                "halo", "selamat tinggal", "terima kasih", "tolong",
                                "maaf", "ah", "oh", "eh"],
                "contractions": {},
                "informal_words": ["keren", "bagus", "mantap", "cool", "heboh",
                                  "hal", "benda", "orang", "teman", "kamu",
                                  "kakak", "adik", "rumah", "waktu", "uang",
                                  "pekerjaan", "hidup", "baik", "buruk", "besar"],
                "oral_patterns": [
                    (r"Eh", "语气"), (r"Yah", "同意"),
                    (r"Ya", "确认"), (r"Loh", "强调"),
                    (r"Deh", "语气"), (r"Jadi", "结论"),
                    (r"Dan", "连接"), (r"Seperti", "举例"),
                    (r"Itu", "指向"), (r"Nih", "强调"),
                    (r"Halo", "问候"), (r"Selamat tinggal", "告别"),
                    (r"Terima kasih", "感谢"), (r"Tolong", "请求"),
                    (r"Maaf", "道歉"), (r"Ah", "惊讶"),
                    (r"Oh", "理解"), (r"Eh", "语气")
                ],
                "complex_patterns": [
                    (r"Jika", "条件"), (r"Meskipun", "让步"),
                    (r"Karena", "原因"), (r"Untuk", "目的"),
                    (r"Saat", "时间"), (r"Hingga", "直到"),
                    (r"Jadi", "结果"), (r"Lagi", "重复"),
                    (r"Tentang", "关于"), (r"Untuk", "对于"),
                    (r"Dengan", "方式"), (r"Antara", "之间"),
                    (r"Setelah", "之后"), (r"Sebelum", "之前")
                ],
                "collocations": {
                    "penting": ["dampak penting", "perubahan penting", "perbedaan penting", "peran penting"],
                    "dampak": ["mempunyai dampak pada", "dampak besar", "dampak positif", "dampak negatif"],
                    "mencapai": ["mencapai tujuan", "mencapai kesuksesan", "mencapai hasil"],
                    "berkontribusi": ["berkontribusi pada", "kontribusi besar", "kontribusi positif"],
                    "menentukan": ["menentukan hasil", "menentukan alasan", "menentukan arah"],
                    "potensi": ["memiliki potensi", "mengenali potensi", "potensi besar"],
                    "perspektif": ["dari perspektif", "perspektif baru", "perspektif berbeda"],
                    "menganalisis": ["menganalisis data", "menganalisis situasi", "menganalisis masalah"],
                    "mengevaluasi": ["mengevaluasi kinerja", "mengevaluasi pilihan", "mengevaluasi kualitas"],
                    "membangun": ["membangun hubungan", "membangun aturan", "membangun sistem"],
                    "mempertahankan": ["mempertahankan keseimbangan", "mempertahankan hubungan", "mempertahankan kualitas"],
                    "mengubah": ["mengubah proses", "mengubah industri", "mengubah bisnis"],
                    "mendorong": ["mendorong pengembangan", "mendorong produk", "mendorong pertumbuhan"],
                    "melaksanakan": ["melaksanakan tujuan", "melaksanakan impian", "melaksanakan potensi"],
                    "mengurangi": ["mengurangi biaya", "mengurangi risiko", "mengurangi limbah"],
                    "mencerminkan": ["mencerminkan situasi", "mencerminkan perubahan"],
                    "mendukung": ["mendukung keputusan", "memberikan dukungan", "mendukung ide"],
                    "berfokus": ["berfokus pada", "berfokus perhatian"],
                    "menjelajahi": ["menjelajahi pilihan", "menjelajahi kemungkinan", "menjelajahi pasar"]
                },
                "synonyms": {
                    "penting": ["krusial", "vital", "utama", "esensial"],
                    "dampak": ["efek", "pengaruh", "hasil", "konsekuensi"],
                    "mencapai": ["capai", "raih", "sampai", "lakukan"],
                    "berkontribusi": ["bantu", "partisipasi", "dukung", "terlibat"],
                    "menentukan": ["pilih", "tetapkan", "identifikasi", "definisikan"],
                    "potensi": ["kemungkinan", "kapasitas", "talenta", "kesempatan"],
                    "perspektif": ["sudut pandang", "gagasan", "pandangan", "pendapat"],
                    "menganalisis": ["teliti", "pelajari", "evaluasi", "kajian"],
                    "mengevaluasi": ["nilai", "ukur", "periksa", "taksir"],
                    "membangun": ["bangun", "ciptakan", "organisir", "didirikan"],
                    "mempertahankan": ["jaga", "simpan", "kelola", "lanjutkan"],
                    "mengubah": ["ubah", "transformasi", "adaptasi", "perbarui"],
                    "mendorong": ["dorong", "cepatkan", "promosikan", "tingkatkan"],
                    "melaksanakan": ["lakukan", "realisasikan", "eksekusi", "implementasi"],
                    "mengurangi": ["kurangi", "batas", "minimalkan", "reduksi"],
                    "mencerminkan": ["cerminkan", "tunjukkan", "gambarkan", "wakili"],
                    "mendukung": ["dukung", "bantu", "sokong", "pertahankan"],
                    "berfokus": ["fokus", "pusat", "prioritaskan", "konsentrasikan"],
                    "menjelajahi": ["jelajahi", "teliti", "eksplorasi", "temukan"]
                },
                "word_families": {
                    "penting": ["penting", "pentingnya", "penting"],
                    "dampak": ["dampak", "dampaknya", "dampak"],
                    "mencapai": ["mencapai", "capainya", "mencapai"],
                    "berkontribusi": ["berkontribusi", "kontribusi", "berkontribusi"],
                    "menentukan": ["menentukan", "penentuan", "menentukan"],
                    "potensi": ["potensi", "potensinya", "potensi"],
                    "perspektif": ["perspektif", "perspektifnya", "perspektif"],
                    "menganalisis": ["menganalisis", "analisis", "menganalisis"],
                    "mengevaluasi": ["mengevaluasi", "evaluasi", "mengevaluasi"],
                    "membangun": ["membangun", "pembangunan", "membangun"],
                    "mempertahankan": ["mempertahankan", "pertahanan", "mempertahankan"],
                    "mengubah": ["mengubah", "perubahan", "mengubah"],
                    "mendorong": ["mendorong", "dorongan", "mendorong"],
                    "melaksanakan": ["melaksanakan", "pelaksanaan", "melaksanakan"],
                    "mengurangi": ["mengurangi", "pengurangan", "mengurangi"],
                    "mencerminkan": ["mencerminkan", "cerminan", "mencerminkan"],
                    "mendukung": ["mendukung", "dukungan", "mendukung"],
                    "berfokus": ["berfokus", "fokus", "berfokus"],
                    "menjelajahi": ["menjelajahi", "jelajah", "menjelajahi"]
                },
                "formal_alternatives": {
                    "keren": "mengesankan / luar biasa", "bagus": "baik / luar biasa",
                    "mantap": "bagus / hebat", "cool": "mengesankan / bagus",
                    "heboh": "menarik / sensation", "hal": "perkara / topik",
                    "benda": "barang / objek", "orang": "manusia / individu",
                    "teman": "teman / rekan kerja", "kamu": "anda / kamu",
                    "kakak": "kakak / rekan", "adik": "adik / rekan",
                    "rumah": "rumah / hunian", "waktu": "waktu / periode",
                    "uang": "uang / sumber daya", "pekerjaan": "pekerjaan / aktivitas",
                    "hidup": "hidup / kehidupan sehari-hari", "baik": "baik / memuaskan",
                    "buruk": "buruk / negatif", "besar": "besar / penting"
                }
            },
            "ms": {
                "oral_markers": ["eh", "ya", "lah", "loh", "deh",
                                "jadi", "dan", "seperti", "itu", "ini",
                                "hai", "selamat tinggal", "terima kasih", "tolong",
                                "maaf", "ah", "oh", "eh"],
                "contractions": {},
                "informal_words": ["best", "bagus", "cool", "hebat", "awesome",
                                  "perkara", "barang", "orang", "kawan", "awak",
                                  "kakak", "adik", "rumah", "masa", "duit",
                                  "kerja", "hidup", "baik", "buruk", "besar"],
                "oral_patterns": [
                    (r"Eh", "语气"), (r"Ya", "同意"),
                    (r"Lah", "强调"), (r"Loh", "语气"),
                    (r"Deh", "语气"), (r"Jadi", "结论"),
                    (r"Dan", "连接"), (r"Seperti", "举例"),
                    (r"Itu", "指向"), (r"Ini", "强调"),
                    (r"Hai", "问候"), (r"Selamat tinggal", "告别"),
                    (r"Terima kasih", "感谢"), (r"Tolong", "请求"),
                    (r"Maaf", "道歉"), (r"Ah", "惊讶"),
                    (r"Oh", "理解"), (r"Eh", "语气")
                ],
                "complex_patterns": [
                    (r"Jika", "条件"), (r"Walaupun", "让步"),
                    (r"Kerana", "原因"), (r"Untuk", "目的"),
                    (r"Apabila", "时间"), (r"Hingga", "直到"),
                    (r"Oleh itu", "结果"), (r"Lagi", "重复"),
                    (r"Tentang", "关于"), (r"Bagi", "对于"),
                    (r"Dengan", "方式"), (r"Antara", "之间"),
                    (r"Selepas", "之后"), (r"Sebelum", "之前")
                ],
                "collocations": {
                    "penting": ["impak penting", "perubahan penting", "perbezaan penting", "peranan penting"],
                    "impak": ["mempunyai impak ke atas", "impak besar", "impak positif", "impak negatif"],
                    "capai": ["capai matlamat", "capai kejayaan", "capai hasil"],
                    "membantu": ["membantu kepada", "sumbangan besar", "sumbangan positif"],
                    "tentukan": ["tentukan hasil", "tentukan sebab", "tentukan arah"],
                    "potensi": ["mempunyai potensi", "kenali potensi", "potensi besar"],
                    "perspektif": ["dari perspektif", "perspektif baharu", "perspektif berbeza"],
                    "analisis": ["analisis data", "analisis situasi", "analisis masalah"],
                    "penilaian": ["penilaian prestasi", "penilaian pilihan", "penilaian kualiti"],
                    "bina": ["bina hubungan", "bina peraturan", "bina sistem"],
                    "kekalkan": ["kekalkan keseimbangan", "kekalkan hubungan", "kekalkan kualiti"],
                    "ubah": ["ubah proses", "ubah industri", "ubah perniagaan"],
                    "galakkan": ["galakkan pembangunan", "galakkan produk", "galakkan pertumbuhan"],
                    "laksana": ["laksana matlamat", "laksana impian", "laksana potensi"],
                    "kurangkan": ["kurangkan kos", "kurangkan risiko", "kurangkan sisa"],
                    "cerminkan": ["cerminkan situasi", "cerminkan perubahan"],
                    "sokong": ["sokong keputusan", "beri sokongan", "sokong idea"],
                    "fokus": ["fokus kepada", "fokus perhatian"],
                    "terokai": ["terokai pilihan", "terokai kemungkinan", "terokai pasaran"]
                },
                "synonyms": {
                    "penting": ["krusial", "utama", "asas", "vital"],
                    "impak": ["kesan", "pengaruh", "hasil", "akibat"],
                    "capai": ["raih", "sampai", "lakukan", "realisasikan"],
                    "membantu": ["sumbang", "bantu", "terlibat", "dukung"],
                    "tentukan": ["pilih", "set", "identifikasikan", "definisikan"],
                    "potensi": ["kemungkinan", "kebolehan", "talenta", "peluang"],
                    "perspektif": ["sudut pandang", "gambaran", "pandangan", "pendapat"],
                    "analisis": ["kajian", "telitian", "penilaian", "tinjauan"],
                    "penilaian": ["nilai", "ukur", "periksa", "taksir"],
                    "bina": ["bangun", "cipta", "organisir", "didirikan"],
                    "kekalkan": ["jaga", "simpan", "sokong", "teruskan"],
                    "ubah": ["transformasi", "adaptasi", "perbarui", "ubahsuai"],
                    "galakkan": ["dorong", "cepatkan", "promosikan", "tingkatkan"],
                    "laksana": ["jalankan", "realisasikan", "eksekusi", "implementasi"],
                    "kurangkan": ["batas", "minimalkan", "reduksi", "cuti"],
                    "cerminkan": ["tunjukkan", "gambarkan", "wakili", "gambar"],
                    "sokong": ["bantu", "sokong", "pertahankan", "dukung"],
                    "fokus": ["pusat", "prioritaskan", "konsentrasikan", "fokus"],
                    "terokai": ["jelajahi", "teliti", "eksplorasi", "temukan"]
                },
                "word_families": {
                    "penting": ["penting", "pentingnya", "penting"],
                    "impak": ["impak", "impaknya", "impak"],
                    "capai": ["capai", "capainya", "capai"],
                    "membantu": ["membantu", "bantuan", "membantu"],
                    "tentukan": ["tentukan", "penentuan", "tentukan"],
                    "potensi": ["potensi", "potensinya", "potensi"],
                    "perspektif": ["perspektif", "perspektifnya", "perspektif"],
                    "analisis": ["analisis", "analisisnya", "analisis"],
                    "penilaian": ["penilaian", "penilaiannya", "penilaian"],
                    "bina": ["bina", "binaan", "bina"],
                    "kekalkan": ["kekalkan", "kekalan", "kekalkan"],
                    "ubah": ["ubah", "perubahan", "ubah"],
                    "galakkan": ["galakkan", "galakan", "galakkan"],
                    "laksana": ["laksana", "pelaksanaan", "laksana"],
                    "kurangkan": ["kurangkan", "pengurangan", "kurangkan"],
                    "cerminkan": ["cerminkan", "cerminan", "cerminkan"],
                    "sokong": ["sokong", "sokongan", "sokong"],
                    "fokus": ["fokus", "fokus", "fokus"],
                    "terokai": ["terokai", "terokaian", "terokai"]
                },
                "formal_alternatives": {
                    "best": "hebat / luar biasa", "bagus": "baik / hebat",
                    "cool": "mengagumkan / bagus", "hebat": "hebat / luar biasa",
                    "awesome": "menakjubkan / hebat", "perkara": "perkara / topik",
                    "barang": "barang / objek", "orang": "individu / manusia",
                    "kawan": "kawan / rakan kerja", "awak": "anda / awak",
                    "kakak": "kakak / rakan", "adik": "adik / rakan",
                    "rumah": "rumah / kediaman", "masa": "masa / tempoh",
                    "duit": "duit / sumber", "kerja": "kerja / aktiviti",
                    "hidup": "hidup / kehidupan seharian", "baik": "baik / memuaskan",
                    "buruk": "buruk / negatif", "besar": "besar / penting"
                }
            },
            "tl": {
                "oral_markers": ["ah", "eh", "oh", "ay", "ha",
                                "kaya", "at", "tulad", "ito", "iyan",
                                "kumusta", "paalam", "salamat", "pakiusap",
                                "paumanhin", "ah", "oh", "ay"],
                "contractions": {},
                "informal_words": ["astig", "cool", "ganda", "maganda", "totoong",
                                  "bagay", "bagay", "tao", "kaibigan", "ikaw",
                                  "kuya", "ate", "bahay", "oras", "pera",
                                  "trabaho", "buhay", "maganda", "masama", "malaki"],
                "oral_patterns": [
                    (r"Ah", "语气"), (r"Eh", "语气"),
                    (r"Oh", "惊讶"), (r"Ay", "感叹"),
                    (r"Ha", "疑问"), (r"Kaya", "结论"),
                    (r"At", "连接"), (r"Tulad", "举例"),
                    (r"Ito", "指向"), (r"Iyan", "强调"),
                    (r"Kumusta", "问候"), (r"Paalam", "告别"),
                    (r"Salamat", "感谢"), (r"Pakiusap", "请求"),
                    (r"Paumanhin", "道歉"), (r"Ah", "惊讶"),
                    (r"Oh", "理解"), (r"Ay", "语气")
                ],
                "complex_patterns": [
                    (r"Kung", "条件"), (r"Kahit", "让步"),
                    (r"Dahil", "原因"), (r"Upang", "目的"),
                    (r"Kapag", "时间"), (r"Hanggang", "直到"),
                    (r"Kaya", "结果"), (r"Muli", "重复"),
                    (r"Tungkol sa", "关于"), (r"Para sa", "对于"),
                    (r"Gamit", "方式"), (r"Sa pagitan ng", "之间"),
                    (r"Pagkatapos", "之后"), (r"Bago", "之前")
                ],
                "collocations": {
                    "mahalaga": ["epekto mahalaga", "pagbabago mahalaga", "pagkakaiba mahalaga", " papel mahalaga"],
                    "epekto": ["may epekto sa", "malaking epekto", "positibong epekto", "negatibong epekto"],
                    "maabot": ["maabot ang layunin", "maabot ang tagumpay", "maabot ang resulta"],
                    "mag-ambag": ["mag-ambag sa", "malaking ambag", "positibong ambag"],
                    "matukoy": ["matukoy ang resulta", "matukoy ang dahilan", "matukoy ang direksyon"],
                    "potensyal": ["may potensyal", "kilalanin ang potensyal", "malaking potensyal"],
                    "pananaw": ["mula sa pananaw", "bagong pananaw", "ibang pananaw"],
                    "analyze": ["analyze ang data", "analyze ang sitwasyon", "analyze ang problema"],
                    "evaluate": ["evaluate ang performance", "evaluate ang mga opsyon", "evaluate ang kalidad"],
                    "bumuo": ["bumuo ng relasyon", "bumuo ng panuntunan", "bumuo ng sistema"],
                    "panatilihin": ["panatilihin ang balanse", "panatilihin ang relasyon", "panatilihin ang kalidad"],
                    "baguhin": ["baguhin ang proseso", "baguhin ang industriya", "baguhin ang negosyo"],
                    "itaguyod": ["itaguyod ang pag-unlad", "itaguyod ang produkto", "itaguyod ang paglago"],
                    "maisakatuparan": ["maisakatuparan ang layunin", "maisakatuparan ang pangarap", "maisakatuparan ang potensyal"],
                    "bawasan": ["bawasan ang gastos", "bawasan ang panganib", "bawasan ang basura"],
                    "sumasalamin": ["sumasalamin sa sitwasyon", "sumasalamin sa pagbabago"],
                    "suportahan": ["suportahan ang desisyon", "magbigay ng suporta", "suportahan ang ideya"],
                    "tumutok": ["tumutok sa", "tumutok ang atensyon"],
                    "galugarin": ["galugarin ang mga opsyon", "galugarin ang mga posibilidad", "galugarin ang merkado"]
                },
                "synonyms": {
                    "mahalaga": ["kritikal", "pangunahin", "essensyal", "vital"],
                    "epekto": ["impluwensya", "resulta", "bunga", "consequence"],
                    "maabot": ["makamit", "kamtan", "abot", "realizar"],
                    "mag-ambag": ["tumulong", "makilahok", "sumuporta", "participate"],
                    "matukoy": ["piliin", "takda", "identihin", "tukuyin"],
                    "potensyal": ["posibilidad", "kapabilidad", "talento", "opportunity"],
                    "pananaw": ["pananaw", "salaysay", "perspektibo", "view"],
                    "analyze": ["suriin", "pag-aralan", "evaluate", "pag-aaral"],
                    "evaluate": ["timbangin", "biguin", "suriin", "check"],
                    "bumuo": ["gumawa", "itayo", "organisahin", "establisher"],
                    "panatilihin": ["panatilihin", "ingatan", "sustain", "maintain"],
                    "baguhin": ["palitan", "transform", "adjust", "pagbabago"],
                    "itaguyod": ["palakasin", "pabilisin", "promote", "boost"],
                    "maisakatuparan": ["maisakatuparan", "gawin", "execute", "implement"],
                    "bawasan": ["pagbawasan", "limitahan", "minimize", "reduce"],
                    "sumasalamin": ["ipakita", "ilabas", "reflect", "mirror"],
                    "suportahan": ["sumuporta", "tumulong", "back", "support"],
                    "tumutok": ["tumutok", "concentrate", "focus", "center"],
                    "galugarin": ["galugarin", "explore", "investigate", "discover"]
                },
                "word_families": {
                    "mahalaga": ["mahalaga", "kahalagahan", "mahalaga"],
                    "epekto": ["epekto", "epekto", "epekto"],
                    "maabot": ["maabot", "abot", "maabot"],
                    "mag-ambag": ["mag-ambag", "ambag", "mag-ambag"],
                    "matukoy": ["matukoy", "tukoy", "matukoy"],
                    "potensyal": ["potensyal", "potensyal", "potensyal"],
                    "pananaw": ["pananaw", "pananaw", "pananaw"],
                    "analyze": ["analyze", "analysis", "analyze"],
                    "evaluate": ["evaluate", "evaluation", "evaluate"],
                    "bumuo": ["bumuo", "buo", "bumuo"],
                    "panatilihin": ["panatilihin", "panatili", "panatilihin"],
                    "baguhin": ["baguhin", "pagbabago", "baguhin"],
                    "itaguyod": ["itaguyod", "pagtaguyod", "itaguyod"],
                    "maisakatuparan": ["maisakatuparan", "katuparan", "maisakatuparan"],
                    "bawasan": ["bawasan", "pagbawas", "bawasan"],
                    "sumasalamin": ["sumasalamin", "salamin", "sumasalamin"],
                    "suportahan": ["suportahan", "suporta", "suportahan"],
                    "tumutok": ["tumutok", "tuok", "tumutok"],
                    "galugarin": ["galugarin", "galugad", "galugarin"]
                },
                "formal_alternatives": {
                    "astig": "nakamamangha / kahanga-hanga", "cool": "nakamamangha / cool",
                    "ganda": "maganda / kaakit-akit", "maganda": "maganda / kaakit-akit",
                    "totoong": "talagang / totoo", "bagay": "bagay / kagamitan",
                    "tao": "tao / indibidwal", "kaibigan": "kaibigan / kasamahan",
                    "ikaw": "ikaw / iyo", "kuya": "kuya / kapatid",
                    "ate": "ate / kapatid", "bahay": "bahay / tirahan",
                    "oras": "oras / panahon", "pera": "pera / kayamanan",
                    "trabaho": "trabaho / gawain", "buhay": "buhay / pang-araw-araw na buhay",
                    "masama": "masama / negatibo", "malaki": "malaki / mahalaga"
                }
            },
        }
    
    @staticmethod
    def _detect_language_from_text(text: str) -> str:
        """从文本内容检测语言
        
        通过分析文本中的字符特征来判断语言：
        - 包含中文字符(CJK) → zh
        - 包含日文字符(平假名/片假名) → ja
        - 包含韩文字符 → ko
        - 包含德语特殊字符(äöüß) → de
        - 包含法语特殊字符(éèêëàâîïôûùüÿç) → fr
        - 包含西班牙语特殊字符(ñ¿¡) → es
        - 默认 → en
        
        Args:
            text: 输入文本
            
        Returns:
            语言代码
        """
        import re
        
        if not text:
            return "en"
        
        # 计算各种语言特征字符的比例
        text_len = len(text) if text else 1
        
        # 中文：CJK统一汉字
        chinese_chars = len(re.findall(r'[\u4e00-\u9fff]', text))
        if chinese_chars / text_len > 0.1:
            return "zh"
        
        # 日文：平假名 + 片假名 + 汉字
        hiragana = len(re.findall(r'[\u3040-\u309f]', text))
        katakana = len(re.findall(r'[\u30a0-\u30ff]', text))
        kanji = len(re.findall(r'[\u4e00-\u9fff]', text))
        jp_score = (hiragana + katakana) * 2 + kanji
        if jp_score / text_len > 0.05:
            return "ja"
        
        # 韩文
        korean_chars = len(re.findall(r'[\uac00-\ud7af]', text))
        if korean_chars / text_len > 0.1:
            return "ko"
        
        # 德语：ä ö ü ß
        german_chars = len(re.findall(r'[äöüßÄÖÜ]', text))
        german_score = german_chars
        # 德语常见词
        german_words = ["der", "die", "das", "und", "ist", "ein", "eine", "nicht", "auch", "ich"]
        for word in german_words:
            if re.search(rf'\b{word}\b', text, re.IGNORECASE):
                german_score += 2
        if german_score > 3:
            return "de"
        
        # 法语：é è ê ë à â î ï ô û ù ü ÿ ç
        french_chars = len(re.findall(r'[éèêëàâîïôûùüÿçÉÈÊËÀÂÎÏÔÛÙÜÝÇ]', text))
        french_score = french_chars
        # 法语常见词
        french_words = ["le", "la", "les", "et", "est", "dans", "pour", "pas", "sur", "avec"]
        for word in french_words:
            if re.search(rf'\b{word}\b', text, re.IGNORECASE):
                french_score += 2
        if french_score > 3:
            return "fr"
        
        # 西班牙语：ñ ¿ ¡
        spanish_chars = len(re.findall(r'[ñ¿¡Ñ¿¡]', text))
        spanish_score = spanish_chars
        # 西班牙语常见词
        spanish_words = ["el", "la", "los", "las", "y", "es", "en", "para", "con", "no"]
        for word in spanish_words:
            if re.search(rf'\b{word}\b', text, re.IGNORECASE):
                spanish_score += 2
        if spanish_score > 3:
            return "es"
        
        # 默认英语
        return "en"
    
    def analyze(
        self,
        video_id: str,
        subtitles: List[Dict[str, Any]],
        mode: AnalysisMode,
        output_dir: Optional[str] = None,
        use_ai_fallback: bool = True,
        language: str = "en"
    ) -> AnalysisResult:
        """
        分析视频内容
        
        Args:
            video_id: 视频 ID
            subtitles: 字幕片段列表
            mode: 分析模式
            output_dir: 输出目录
            use_ai_fallback: 是否使用AI作为备选方案
            language: 视频语言代码（en/de/fr/es/zh/ja/ko/ru等）
            
        Returns:
            分析结果
        """
        try:
            # 合并字幕文本用于语言检测
            full_text = " ".join([s.get("text", "") for s in subtitles])
            
            # 从文本自动检测语言
            detected_lang = self._detect_language_from_text(full_text)
            
            # 如果检测到的语言与传入的不一致，记录日志
            if detected_lang != language:
                logger.warning(f"语言不匹配: 传入={language}, 检测到={detected_lang}, video_id={video_id}, 将使用检测到的语言")
                language = detected_lang
            else:
                logger.info(f"语言确认: {language}, video_id={video_id}")
            
            report_content = self._generate_report(subtitles, mode, language)

            # 学习类模式（ORAL_SPOKEN/EXAM_PREP/LANGUAGE_LEARNING）强制使用AI，
            # 不受 use_ai_fallback 控制（pipeline 传 False 也会走AI路径）；
            # 其他模式仍受 use_ai_fallback 控制。
            force_ai_modes = [AnalysisMode.EXAM_PREP, AnalysisMode.LANGUAGE_LEARNING, AnalysisMode.ORAL_SPOKEN]
            if (mode in force_ai_modes or use_ai_fallback) and self._should_use_ai(report_content, subtitles, mode):
                ai_content = self._generate_with_ai(subtitles, mode, language=language)
                if ai_content:
                    report_content = ai_content
                else:
                    # LLM 生成失败（未配置/超时/质量不达标）→ 标记失败，不生成报告
                    error_msg = (
                        f"LLM 分析报告生成失败（mode={mode.value}, language={language}）。"
                        f"可能原因：ai_writer 未启用 / API 调用失败 / 质量评分不达标。"
                        f"请检查 config.yaml 的 ai_writer 配置和网络连接。"
                    )
                    logger.error(error_msg)
                    return AnalysisResult(
                        video_id=video_id,
                        mode=mode,
                        success=False,
                        error_message=error_msg
                    )

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
    
    def _should_use_ai(self, content: str, subtitles: List[Dict[str, Any]], mode: AnalysisMode) -> bool:
        """判断是否应该使用AI生成

        对 ORAL_SPOKEN / EXAM_PREP / LANGUAGE_LEARNING 三种学习类模式，
        一律优先使用 AI 生成（硬编码模板只作为 LLM 失败时的兜底数据源，
        不再作为最终输出）。
        """
        if mode in [AnalysisMode.EXAM_PREP, AnalysisMode.LANGUAGE_LEARNING, AnalysisMode.ORAL_SPOKEN]:
            return True
        return False

    def _generate_with_ai(self, subtitles: List[Dict[str, Any]], mode: AnalysisMode, language: str = "en") -> str:
        """使用AI生成分析报告

        Args:
            subtitles: 字幕列表
            mode: 分析模式（决定调用哪种 prompt）
            language: 视频源语言代码，传给 AIWriter 让 prompt 用对应语言作示例
        """
        # 根据分析模式映射到对应的 ContentType
        if mode == AnalysisMode.ORAL_SPOKEN:
            content_type = ContentType.ORAL_ANALYSIS
        elif mode == AnalysisMode.EXAM_PREP:
            content_type = ContentType.EXAM_ANALYSIS
        else:
            # LANGUAGE_LEARNING 及其他模式用通用分析报告
            content_type = ContentType.ANALYSIS_REPORT

        return self._ai_writer.generate_content(
            subtitles,
            content_type,
            language=language
        )
    
    def _generate_report(
        self,
        subtitles: List[Dict[str, Any]],
        mode: AnalysisMode,
        language: str = "en"
    ) -> str:
        """
        生成分析报告
        
        Args:
            subtitles: 字幕片段列表
            mode: 分析模式
            language: 视频语言代码
            
        Returns:
            报告内容（Markdown格式）
        """
        report_parts = []
        
        lang_data = self._language_data.get(language, self._language_data["en"])
        
        report_parts.append(f"# 视频内容分析报告")
        report_parts.append(f"## 分析模式: {mode.display_name}")
        report_parts.append(f"")
        
        if mode == AnalysisMode.LANGUAGE_LEARNING:
            report_parts.extend(self._analyze_language_learning(subtitles, language))
        elif mode == AnalysisMode.CONTENT_SUMMARY:
            report_parts.extend(self._analyze_content_summary(subtitles))
        elif mode == AnalysisMode.KEYWORDS:
            report_parts.extend(self._analyze_keywords(subtitles, language))
        elif mode == AnalysisMode.GRAMMAR_POINTS:
            report_parts.extend(self._analyze_grammar_points(subtitles, language))
        elif mode == AnalysisMode.FULL_ANALYSIS:
            report_parts.extend(self._analyze_full(subtitles, language))
        elif mode == AnalysisMode.ORAL_SPOKEN:
            report_parts.extend(self._analyze_oral_spoken(subtitles, language))
        elif mode == AnalysisMode.EXAM_PREP:
            report_parts.extend(self._analyze_exam_prep(subtitles, language))
        elif mode == AnalysisMode.SENTENCE_ANALYSIS:
            report_parts.extend(self._analyze_sentence_analysis(subtitles))
        
        return "\n".join(report_parts)
    
    def _analyze_language_learning(
        self,
        subtitles: List[Dict[str, Any]],
        language: str = "en"
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
        words = self._extract_words(use_text, language=language)
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
        subtitles: List[Dict[str, Any]],
        language: str = "en"
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
        words = self._extract_words(all_text, language=language)
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
        subtitles: List[Dict[str, Any]],
        language: str = "en"
    ) -> List[str]:
        """
        语法要点模式分析
        
        分析视频中的语法结构和句型。
        支持多语言：英语、德语、法语、西班牙语、中文、日语等。
        """
        parts = []
        parts.append("## 语法要点分析")
        parts.append("")
        
        lang_data = self._language_data.get(language, self._language_data["en"])
        complex_patterns = lang_data.get("complex_patterns", [])
        
        parts.append("### 一、句子类型分析")
        sentence_types = self._analyze_sentence_types(subtitles, language=language)
        for stype, count in sentence_types.items():
            parts.append(f"- **{stype}**: {count}句")
        parts.append("")
        
        parts.append("### 二、时态/体分布")
        tenses = self._analyze_tenses(subtitles, language=language)
        for tense, count in tenses.items():
            parts.append(f"- **{tense}**: {count}次")
        parts.append("")
        
        parts.append("### 三、常用句型")
        all_text = " ".join([s.get("text", "").lower() for s in subtitles if s.get("text")])
        
        found_patterns = []
        for pattern, desc in complex_patterns:
            matches = re.findall(pattern, all_text)
            if matches:
                found_patterns.append((desc, len(matches), pattern))
        
        if found_patterns:
            found_patterns.sort(key=lambda x: x[1], reverse=True)
            for i, (desc, count, pattern) in enumerate(found_patterns[:10], 1):
                parts.append(f"{i}. **{desc}** ({count}次)")
                for s in subtitles:
                    if re.search(pattern, s.get("text", "").lower()):
                        parts.append(f"   - {s.get('text', '')}")
                        break
                parts.append("")
        else:
            parts.append("- 未检测到明显的句型模式")
            parts.append("")
        
        return parts
    
    def _analyze_full(
        self,
        subtitles: List[Dict[str, Any]],
        language: str = "en"
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
        parts.extend(self._analyze_language_learning(subtitles, language))
        parts.append("")
        parts.extend(self._analyze_grammar_points(subtitles, language))
        
        return parts
    
    def _analyze_oral_spoken(
        self,
        subtitles: List[Dict[str, Any]],
        language: str = "en"
    ) -> List[str]:
        """
        口语学习模式分析
        
        分析视频中的口语化表达、非正式用语、缩略语、填充词等，
        帮助学习者掌握真实语境中的口语用法。
        支持多语言：英语、德语、法语、西班牙语、中文、日语等。
        """
        parts = []
        parts.append("## 口语学习分析")
        parts.append("")
        
        lang_data = self._language_data.get(language, self._language_data["en"])
        oral_markers = lang_data.get("oral_markers", [])
        contractions = lang_data.get("contractions", {})
        informal_words = lang_data.get("informal_words", [])
        oral_patterns = lang_data.get("oral_patterns", [])
        
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
        found_patterns = []
        for pattern, desc in oral_patterns:
            matches = re.findall(pattern, all_text)
            if matches:
                found_patterns.append((desc, len(matches), pattern))
        
        if found_patterns:
            found_patterns.sort(key=lambda x: x[1], reverse=True)
            for desc, count, pattern in found_patterns[:10]:
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
        subtitles: List[Dict[str, Any]],
        language: str = "en"
    ) -> List[str]:
        """
        应试学习模式分析 - 深度增强版
        
        分析视频中的高难度词汇、复杂句式、值得学习的有难度词句，
        帮助学习者提升应试能力。包含词汇搭配、同义替换、记忆技巧、
        长难句学习感悟和仿写建议。
        支持多语言：英语、德语、法语、西班牙语、中文、日语等。
        """
        parts = []
        parts.append("## 应试学习分析")
        parts.append("")
        
        lang_data = self._language_data.get(language, self._language_data["en"])
        collocations = lang_data.get("collocations", {})
        complex_patterns = lang_data.get("complex_patterns", [])
        formal_alternatives = lang_data.get("formal_alternatives", {})
        
        all_text = " ".join([s.get("text", "").lower() for s in subtitles if s.get("text")])
        
        parts.append("### 一、高级词汇深度解析")
        parts.append("")
        
        found_advanced = []
        for word in collocations.keys():
            if word in all_text.split():
                count = all_text.split().count(word)
                found_advanced.append((word, count))
        
        if found_advanced:
            found_advanced.sort(key=lambda x: x[1], reverse=True)
            for word, count in found_advanced[:10]:
                parts.append(f"**{word}**")
                parts.append("")
                
                for s in subtitles:
                    if word in s.get("text", "").lower().split():
                        parts.append(f"   - 例句: {s.get('text', '')}")
                        parts.append(f"   - 翻译: {s.get('translated_text', '')}")
                        break
                
                if word in collocations:
                    parts.append(f"   - 常用搭配: {', '.join(collocations[word][:5])}")
                
                memory_tip = self._generate_memory_tip(word, collocations.get(word, []))
                parts.append(f"   - 记忆技巧: {memory_tip}")
                
                parts.append("")
        else:
            parts.append("- 未检测到高级词汇，建议使用更长的视频进行分析")
        parts.append("")
        
        parts.append("### 二、复杂句式")
        
        found_complex = []
        for pattern, desc in complex_patterns:
            matches = re.findall(pattern, all_text)
            if matches:
                found_complex.append((desc, len(matches), pattern))
        
        if found_complex:
            found_complex.sort(key=lambda x: x[1], reverse=True)
            for desc, count, pattern in found_complex[:10]:
                parts.append(f"- **{desc}**: {count}次")
                for s in subtitles:
                    if re.search(pattern, s.get("text", "").lower()):
                        parts.append(f"  *例句: {s.get('text', '')}*")
                        parts.append(f"  *翻译: {s.get('translated_text', '')}*")
                        parts.append(f"  *考点提示: {self._generate_grammar_tip(desc)}*")
                        break
                parts.append("")
        else:
            parts.append("- 未检测到复杂句式")
        parts.append("")
        
        parts.append("### 三、长难句深度分析")
        long_sentences = []
        for s in subtitles:
            text = s.get("text", "")
            word_count = len(text.split())
            if word_count >= 8:
                translated = s.get("translated_text", "")
                long_sentences.append((text, translated, word_count))
        
        long_sentences.sort(key=lambda x: x[2], reverse=True)
        
        if long_sentences:
            for i, (sentence, translated, word_count) in enumerate(long_sentences[:5], 1):
                parts.append(f"{i}. **{sentence}**")
                parts.append(f"   词数: {word_count}")
                if translated:
                    parts.append(f"   翻译: {translated}")
                
                structure = self._analyze_sentence_structure(sentence)
                parts.append(f"   结构分析: {structure}")
                
                learning_thinking = self._generate_sentence_thinking(sentence, structure)
                parts.append(f"   学习感悟: {learning_thinking}")
                
                imitation = self._generate_imitation(sentence)
                parts.append(f"   仿写练习: {imitation}")
                
                parts.append("")
        else:
            parts.append("- 未检测到长难句")
        parts.append("")
        
        parts.append("### 四、书面表达推荐")
        
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
        
        parts.append("")
        parts.append("### 五、写作技巧总结")
        parts.append("")
        # 写作技巧根据源语言动态生成（用该语言的词汇作示例，避免英文示例出现在非英文视频中）
        writing_tips = self._get_writing_tips(language)
        for i, tip in enumerate(writing_tips, 1):
            parts.append(f"{i}. {tip}")
            parts.append("")

        return parts

    def _get_writing_tips(self, language: str) -> List[str]:
        """根据视频源语言返回对应的写作技巧（用该语言的词汇作示例）

        避免在非英文视频中出现英文词汇示例（如 significant/however），
        每种语言使用自己的高级词汇、连接词和搭配作示例。
        """
        tips_by_lang = {
            "en": [
                "**词汇升级**：用高级词汇替换简单词汇，比如用 significant 代替 important，用 contribute to 代替 help with",
                "**句式多样**：适当使用复合句（如 Not only...but also...、It is...that...）展示语言能力，但不要过度追求复杂",
                "**连接词**：使用 however、moreover、therefore、nevertheless 等连接词使逻辑更清晰",
                "**搭配积累**：记住常用搭配（如 make a contribution、play a significant role），避免中式英语直译",
                "**同义替换**：写作中避免重复使用同一个词，使用同义词增加词汇多样性",
            ],
            "de": [
                "**词汇升级**：用高级词汇替换简单词汇，比如用 bedeutsam 代替 wichtig，用 tragen zu 代替 helfen",
                "**句式多样**：适当使用从句（如 Relativsatz、Kausalsatz mit weil/da）展示语言能力，但不要过度追求复杂",
                "**连接词**：使用 jedoch、außerdem、daher、dennoch、trotzdem 等连接词使逻辑更清晰",
                "**搭配积累**：记住常用搭配（如 einen Beitrag leisten、eine Rolle spielen、in Betracht ziehen），避免母语直译",
                "**同义替换**：写作中避免重复使用同一个词，使用同义词增加词汇多样性（如 gut → hervorragend/ausgezeichnet）",
            ],
            "fr": [
                "**词汇升级**：用高级词汇替换简单词汇，比如用 remarquable 代替 important，用 contribuer à 代替 aider",
                "**句式多样**：适当使用从句（如 proposition subordonnée、subjonctif）展示语言能力，但不要过度追求复杂",
                "**连接词**：使用 cependant、de plus、par conséquent、néanmoins、toutefois 等连接词使逻辑更清晰",
                "**搭配积累**：记住常用搭配（如 jouer un rôle、apporter une contribution、tenir compte de），避免母语直译",
                "**同义替换**：写作中避免重复使用同一个词，使用同义词增加词汇多样性（如 bon → excellent/remarquable）",
            ],
            "es": [
                "**词汇升级**：用高级词汇替换简单词汇，比如用 significativo 代替 importante，用 contribuir a 代替 ayudar",
                "**句式多样**：适当使用从句（如 oraciones subordinadas、subjuntivo）展示语言能力，但不要过度追求复杂",
                "**连接词**：使用 sin embargo、además、por lo tanto、no obstante、por consiguiente 等连接词使逻辑更清晰",
                "**搭配积累**：记住常用搭配（如 jugar un papel、aportar una contribución、tener en cuenta），避免母语直译",
                "**同义替换**：写作中避免重复使用同一个词，使用同义词增加词汇多样性（如 bueno → excelente/notable）",
            ],
            "it": [
                "**词汇升级**：用高级词汇替换简单词汇，比如用 significativo 代替 importante，用 contribuire a 代替 aiutare",
                "**句式多样**：适当使用从句（如 proposizioni subordinata、congiuntivo）展示语言能力，但不要过度追求复杂",
                "**连接词**：使用 tuttavia、inoltre、pertanto、ciononostante、d'altra parte 等连接词使逻辑更清晰",
                "**搭配积累**：记住常用搭配（come svolgere un ruolo、apportare un contributo、tenere conto di），避免母语直译",
                "**同义替换**：写作中避免重复使用同一个词，使用同义词增加词汇多样性（如 buono → eccellente/notevole）",
            ],
            "pt": [
                "**词汇升级**：用高级词汇替换简单词汇，比如用 significativo 代替 importante，用 contribuir para 代替 ajudar",
                "**句式多样**：适当使用从句（如 orações subordinadas、subjuntivo）展示语言能力，但不要过度追求复杂",
                "**连接词**：使用 no entanto、além disso、portanto、não obstante、por conseguinte 等连接词使逻辑更清晰",
                "**搭配积累**：记住常用搭配（如 desempenhar um papel、aportar uma contribuição、levar em conta），避免母语直译",
                "**同义替换**：写作中避免重复使用同一个词，使用同义词增加词汇多样性（如 bom → excelente/notável）",
            ],
            "nl": [
                "**词汇升级**：用高级词汇替换简单词汇，比如用 aanzienlijk 代替 belangrijk，用 bijdragen aan 代替 helpen",
                "**句式多样**：适当使用从句（如 bijzin、onderschikkend voegwoord）展示语言能力，但不要过度追求复杂",
                "**连接词**：使用 echter、bovendien、daarom、niettemin、desondanks 等连接词使逻辑更清晰",
                "**搭配积累**：记住常用搭配（如 een rol spelen、een bijdrage leveren、rekening houden met），避免母语直译",
                "**同义替换**：写作中避免重复使用同一个词，使用同义词增加词汇多样性（如 goed → uitstekend/opmerkelijk）",
            ],
        }
        return tips_by_lang.get(language, tips_by_lang["en"])

    def _generate_memory_tip(self, word: str, collocations: List[str]) -> str:
        """生成记忆技巧"""
        if collocations:
            return f"把 '{word}' 和它的常用搭配一起记，比如：{', '.join(collocations[:3])}"
        return f"把 '{word}' 造3个不同场景的句子，加深印象"
    
    def _generate_grammar_tip(self, grammar_desc: str) -> str:
        """生成语法考点提示"""
        tips = {
            "强调句型": "强调句型的结构是：It is/was + 被强调部分 + that/who + 其他。注意：去掉It is/was...that后句子仍然完整。",
            "存在句型": "there be句型看似简单，但考试中经常考主谓一致和否定形式。记住：be动词的数要和后面的主语保持一致。",
            "原因句型": "The reason why...is that...是一个常用的原因表达句型，注意不要把that省略。",
            "并列强调": "Not only...but also...连接两个并列成分，当Not only位于句首时，句子需要部分倒装。",
            "推测句型": "It seems that...表示推测，类似的表达还有It appears that...、It looks like...。",
            "名词性从句": "名词性从句包括主语从句、宾语从句、表语从句和同位语从句。注意区分that和what在从句中的作用。",
            "结论句型": "That is why...表示结论，前面通常有原因说明。类似的表达还有Therefore...、Thus...。",
            "目的状语": "In order to...表示目的，放在句首或句中都可以。注意不要和so that混淆。",
            "让步状语": "Although/Though引导让步状语从句，不能和but连用。记住：'虽然...但是'在英语中只能用一个连词。",
            "原因状语": "Because表示直接原因，语气最强；since表示已知原因，语气较弱，常用于句首。",
        }
        return tips.get(grammar_desc, "这个句型在考试中经常出现，建议重点掌握。")
    
    def _generate_sentence_thinking(self, sentence: str, structure: str) -> str:
        """生成句子学习感悟"""
        thinkings = []
        
        if "从句" in structure and "并列" not in structure:
            thinkings.append("🎯 这句话包含从句结构，建议先找出主干，再分析修饰成分。拆解后会发现逻辑其实很清晰。")
        
        if "强调句型" in structure:
            thinkings.append("💡 强调句型是考试中的高频考点！记住结构：It is/was + 被强调部分 + that/who + 其他。")
        
        if "让步状语从句" in structure:
            thinkings.append("🌐 让步状语从句中，although/though 不能和 but 连用！这是一个非常容易犯的错误。")
        
        if "原因状语从句" in structure:
            thinkings.append("🔥 because 和 since 的区别：because 表示直接原因，语气最强；since 表示已知原因，语气较弱。")
        
        if "条件状语从句" in structure:
            thinkings.append("❓ 条件状语从句的时态规则：主将从现。主句用将来时，从句用现在时表示将来。")
        
        if "并列结构" in structure:
            thinkings.append("📝 并列结构要注意平行原则！and、but、or 连接的成分必须是同类的。")
        
        if "倒装结构" in structure:
            thinkings.append("🔄 倒装结构在写作中可以提升句型多样性，但要注意使用条件和主谓一致。")
        
        if "名词性从句" in structure:
            thinkings.append("🧠 名词性从句可以充当主语、宾语、表语或同位语，是展示语言能力的重要句型。")
        
        if not thinkings:
            thinkings.append("📚 这句话的结构虽然看起来简单，但用词很地道。建议重点关注词汇搭配和表达方式。")
        
        return thinkings[0]
    
    def _generate_imitation(self, sentence: str) -> str:
        """生成多样化的仿写练习建议"""
        s_lower = sentence.lower()
        
        if re.search(r"The .+ thing about .+ is that", s_lower):
            return "仿写练习：仿照 'The ... thing about ... is that ...' 结构写一个句子，描述你喜欢的事物。"
        elif re.search(r"that's .+ all", s_lower):
            return "仿写练习：用 'That's ... all ...' 结构写一个句子，总结你今天的学习收获。"
        elif re.search(r"here we are", s_lower):
            return "仿写练习：用 'Here we are...' 结构写一个句子，描述你当前的状态或位置。"
        elif "Although" in sentence or "though" in s_lower:
            return "仿写练习：用 'Although..., ...' 结构写一个句子，描述一个困难但成功的经历。"
        elif "Not only" in sentence:
            return "仿写练习：用 'Not only..., but also...' 结构写一个句子，描述一个事物的两个优点。"
        elif re.search(r"What .+ is", s_lower):
            return "仿写练习：用 'What ... is ...' 结构写一个句子，表达你的观点或看法。"
        elif "there be" in s_lower:
            return "仿写练习：用 'There be ...' 结构写一个句子，描述你身边的环境或情况。"
        elif "in order to" in s_lower:
            return "仿写练习：用 'In order to..., ...' 结构写一个句子，描述你的学习或工作目标。"
        elif "if" in s_lower and re.search(r"if we", s_lower):
            return "仿写练习：用 'If we..., ... will...' 结构写一个句子，描述一个假设的情况。"
        elif "about" in s_lower and "is" in s_lower:
            return "仿写练习：仿照 '... about ... is ...' 结构写一个句子，描述你对某个话题的看法。"
        elif len(sentence.split()) >= 10:
            return "仿写练习：仿照这句话的复杂结构，写一个描述你学习经历的长句。"
        
        return f"仿写练习：仿照 '{sentence[:30]}...' 的结构，写一个关于你日常生活的句子。"
    
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
    
    def _extract_words(self, text: str, language: str = "en") -> List[str]:
        """提取单词/词汇列表（支持多语言分词）
        
        Args:
            text: 输入文本
            language: 语言代码 (en/de/fr/es/zh/ja/ko/ru等)
            
        Returns:
            词汇列表
        """
        import re
        
        # 多语言停用词
        stop_words_map = {
            "en": {"the", "and", "a", "an", "is", "are", "was", "were", "be", "been", "being",
                   "have", "has", "had", "do", "does", "did", "will", "would", "could", "should",
                   "may", "might", "must", "shall", "can", "need", "dare", "ought", "used",
                   "to", "of", "in", "for", "on", "with", "at", "by", "from", "as", "into",
                   "through", "during", "before", "after", "above", "below", "between", "under",
                   "again", "further", "then", "once", "here", "there", "when", "where", "why",
                   "how", "all", "each", "few", "more", "most", "other", "some", "such", "no",
                   "nor", "not", "only", "own", "same", "so", "than", "too", "very", "just",
                   "but", "if", "or", "because", "until", "while", "about", "against",
                   "this", "that", "these", "those", "what", "which", "who", "whom", "whose",
                   "cool", "nice", "good", "great", "yeah", "yes", "no", "okay", "ok", "well",
                   "back", "way", "say", "go", "get", "make", "know", "take", "see", "come"},
            "de": {"der", "die", "das", "und", "oder", "ist", "sind", "war", "waren", "sein",
                   "haben", "hat", "hatte", "wird", "werden", "kann", "können", "muss", "soll",
                   "zu", "in", "auf", "für", "mit", "ohne", "bei", "nach", "von", "vom",
                   "den", "dem", "des", "ein", "eine", "einer", "eines", "einige", "manche",
                   "ich", "du", "er", "sie", "es", "wir", "ihr", "sie", "mein", "dein",
                   "sein", "haben", "wollen", "mögen", "dürfen", "können", "sollen", "müssen",
                   "ja", "nein", "vielleicht", "sicher", "natürlich", "klar", "doch", "mal",
                   "auch", "immer", "oft", "schon", "noch", "erst", "nicht", "nie", "nichts",
                   "alles", "etwas", "jeder", "jede", "jedes", "viel", "mehr", "minder",
                   "schön", "gut", "groß", "klein", "schnell", "langsam", "leicht", "schwer"},
            "fr": {"le", "la", "les", "un", "une", "des", "de", "du", "et", "ou", "est",
                   "sont", "était", "étaient", "être", "avoir", "été", "fait", "dans", "sur",
                   "pour", "par", "avec", "sans", "chez", "vers", "depuis", "pendant", "avant",
                   "après", "entre", "sous", "au-dessus", "au-dessous", "tout", "tous", "toute",
                   "toutes", "chaque", "certain", "quelque", "je", "tu", "il", "elle", "nous",
                   "vous", "ils", "elles", "mon", "ton", "son", "notre", "votre", "leur",
                   "oui", "non", "peut-être", "bien sûr", "bien", "mal", "trop", "assez",
                   "peu", "beaucoup", "plus", "moins", "autre", "autres", "même", "aussi",
                   "toujours", "jamais", "rien", "personne", "tout", "chose", "faire", "aller"},
            "es": {"el", "la", "los", "las", "un", "una", "unos", "unas", "y", "o", "es",
                   "son", "era", "eran", "ser", "estar", "estado", "hecho", "en", "sobre",
                   "para", "por", "con", "sin", "entre", "bajo", "todo", "todos", "toda",
                   "todas", "cada", "cierto", "alguno", "alguna", "yo", "tú", "él", "ella",
                   "nosotros", "vosotros", "ellos", "ellas", "mi", "tu", "su", "nuestro",
                   "vuestro", "sí", "no", "quizás", "claro", "bien", "mal", "mucho", "poco",
                   "más", "menos", "otro", "otra", "otros", "otras", "mismo", "misma", "también",
                   "siempre", "nunca", "nada", "nadie", "todo", "cosa", "hacer", "ir", "ver",
                   "dar", "saber", "querer", "poder", "decir", "comer", "beber"},
            "zh": {"的", "了", "和", "是", "就", "都", "而", "及", "与", "着", "或", "一个",
                   "没有", "我们", "你们", "他们", "它们", "这个", "那个", "这些", "那些",
                   "什么", "怎么", "为什么", "因为", "所以", "但是", "如果", "虽然", "不过",
                   "还是", "又", "也", "很", "太", "更", "最", "还", "再", "不",
                   "要", "会", "能", "可以", "应该", "必须", "可能", "得", "有", "在",
                   "上", "下", "前", "后", "左", "右", "里", "外", "中", "间", "之", "乎",
                   "者", "也", "曰", "哉", "矣", "焉", "耳", "而已", "于", "以", "而",
                   "则", "乃", "其", "所", "然", "吧", "呢", "啊", "哦", "嗯",
                   "好", "坏", "大", "小", "多", "少", "快", "慢", "来", "去",
                   "说", "看", "听", "做", "走", "跑", "吃", "喝", "睡", "醒"},
            "ja": {"です", "だ", "である", "します", "います", "あります", "は", "が", "を",
                   "に", "で", "と", "の", "も", "まで", "から", "より", "など", "でも",
                   "しか", "さえ", "すら", "だけ", "ばかり", "ながら", "ついでに", "かわりに",
                   "私", "君", "彼", "彼女", "私たち", "あなたたち", "彼ら", "彼女ら",
                   "はい", "いいえ", "たぶん", "きっと", "たしかに", "もちろん",
                   "いい", "悪い", "大きい", "小さい", "多い", "少ない", "早い", "遅い",
                   "来る", "行く", "見る", "聞く", "話す", "書く", "読む", "食べる", "飲む",
                   "する", "した", "して", "している", "ある", "いる", "なる", "なった"},
            "ko": {"이다", "다", "해요", "요", "은", "는", "이", "가", "을", "를",
                   "에", "에서", "과", "와", "도", "까지", "부터", "보다", "같이",
                   "그리고", "하지만", "그래서", "그러나", "그런데", "만약", "왜냐하면",
                   "저", "너", "그", "그녀", "우리", "너희", "그들", "그녀들",
                   "네", "아니요", "아마", "분명", "당연하지",
                   "좋다", "나쁘다", "크다", "작다", "많다", "적다", "빠르다", "느리다",
                   "오다", "가다", "보다", "듣다", "말하다", "쓰다", "읽다", "먹다", "마시다"},
        }
        
        stop_words = stop_words_map.get(language, stop_words_map["en"])
        
        # 中文使用 jieba 分词
        if language == "zh":
            chinese_pattern = re.compile(r'[\u4e00-\u9fff]+')
            chinese_text = "".join(chinese_pattern.findall(text))
            
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
            return all_words
        
        # 日文：简单的字符级分词（实际项目中建议使用 MeCab 等日文分词器）
        if language == "ja":
            # 提取平假名、片假名和汉字组合
            words = re.findall(r'[\u3040-\u30ff\u4e00-\u9fff]+', text)
            # 按句号分割，提取有意义的短语
            phrases = re.split(r'[。、！？\s]+', text)
            result = []
            for phrase in phrases:
                if len(phrase) >= 2 and phrase not in stop_words:
                    result.append(phrase)
            # 同时添加提取的词
            for w in words:
                if len(w) >= 2 and w not in stop_words:
                    result.append(w)
            return result
        
        # 韩文：按空格和标点分词
        if language == "ko":
            words = re.findall(r'[가-힣]+', text)
            return [w for w in words if w not in stop_words and len(w) >= 2]
        
        # 拉丁语系语言（英、德、法、西、意等）：基于空格和标点分词
        # 支持变音字符（äöüßéèêëàâäùûüñ等）
        word_pattern = r'\b[a-zA-Zäöüßéèêëàâäùûüññç]+[a-zA-Zäöüßéèêëàâäùûüññç\-]*\b'
        words = re.findall(word_pattern, text.lower())
        
        filtered_words = [w for w in words if w not in stop_words and len(w) > 2]
        
        return filtered_words
    
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
    
    def _analyze_sentence_types(self, subtitles: List[Dict[str, Any]], language: str = "en") -> Dict[str, int]:
        """句子类型分析（支持多语言）"""
        types = {"陈述句": 0, "疑问句": 0, "感叹句": 0, "祈使句": 0}
        
        imperative_starters = {
            "en": ("Please", "please", "Don't", "don't", "Let's", "let's", "Go", "Come", "Start"),
            "de": ("Bitte", "bitte", "Nicht", "nicht", "Lass", "lass", "Geh", "Komm", "Starte"),
            "fr": ("Veuillez", "veuillez", "Ne", "ne", "Laisse", "laisse", "Va", "Viens", "Commence"),
            "es": ("Por favor", "por favor", "No", "no", "Deja", "deja", "Ve", "Ven", "Empieza"),
            "zh": ("请", "不要", "让", "我们", "走", "来", "开始"),
            "ja": ("ください", "な", "しましょう", "行こう", "来い", "始め"),
            "ko": ("주세요", "하지마", "합시다", "가", "와", "시작"),
        }
        
        starters = imperative_starters.get(language, imperative_starters["en"])
        
        for s in subtitles:
            text = s.get("text", "")
            if text.endswith("?") or text.endswith("？"):
                types["疑问句"] += 1
            elif text.endswith("!") or text.endswith("！"):
                types["感叹句"] += 1
            elif any(text.startswith(starter) for starter in starters):
                types["祈使句"] += 1
            else:
                types["陈述句"] += 1
        
        return types
    
    def _analyze_tenses(self, subtitles: List[Dict[str, Any]], language: str = "en") -> Dict[str, int]:
        """时态/体分析（支持多语言）"""
        tense_patterns = {
            "en": {
                "现在时": ["is", "are", "am", "do", "does", "go", "goes", "like", "likes"],
                "过去时": ["was", "were", "did", "went", "liked", "had", "got"],
                "进行时": ["is doing", "are doing", "was doing", "were doing", "am doing"],
                "将来时": ["will", "going to", "shall", "is gonna", "is gonna"],
                "完成时": ["have", "has", "had"],
                "现在完成时": ["have been", "has been", "have done", "has done"],
                "过去完成时": ["had been", "had done", "had finished"],
                "现在进行时": ["is being", "are being", "am being"],
                "现在完成进行时": ["have been doing", "has been doing"],
                "将来进行时": ["will be doing", "will be going"],
                "将来完成时": ["will have", "will have done"],
            },
            "de": {
                "现在时": ["ist", "sind", "bin", "tue", "tust", "geht", "mag", "kann"],
                "过去时": ["war", "waren", "tat", "ging", "mochte", "hatte", "wollte"],
                "进行时": ["ist am", "sind am", "bin am", "wird"],
                "将来时": ["wird", "werden", "wollte", "werde"],
                "完成时": ["haben", "hat", "wird haben"],
                "过去完成时": ["hatte", "hatte gemacht", "hatte gegangen"],
                "现在完成时": ["habe", "hast", "hat", "haben gemacht", "haben gegangen"],
                "现在进行时": ["ist am machen", "sind am machen", "bin am machen"],
                "将来进行时": ["wird machen", "werden machen", "wird gehen"],
                "将来完成时": ["wird haben", "wird gemacht haben"],
            },
            "fr": {
                "现在时": ["est", "sont", "suis", "fais", "fais", "vais", "aime", "peux"],
                "过去时": ["etait", "etaient", "ai fait", "suis alle", "ai aime", "avais", "ai voulu"],
                "进行时": ["est en train", "sont en train", "suis en train", "fait"],
                "将来时": ["va", "vais", "fera", "ferai", "ira", "irai"],
                "完成时": ["ai", "as", "a", "avons", "avez", "ont"],
                "过去完成时": ["avais", "avait", "avions", "aviez", "avaient", "avais fait"],
                "现在完成时": ["ai fait", "as fait", "a fait", "avons fait", "avez fait", "ont fait"],
                "现在进行时": ["est en train de", "sont en train de", "suis en train de"],
                "将来进行时": ["va faire", "vais faire", "va aller", "vais aller"],
                "将来完成时": ["aurai", "aura", "aurons", "aurez", "auront"],
            },
            "es": {
                "现在时": ["es", "son", "soy", "hago", "vas", "voy", "me gusta", "puedo"],
                "过去时": ["era", "eran", "hice", "fui", "me guste", "tuve", "quise"],
                "进行时": ["esta", "estan", "estoy", "haciendo", "yendo"],
                "将来时": ["va", "voy", "hara", "hare", "ira", "ire"],
                "完成时": ["he", "has", "ha", "hemos", "habeis", "han"],
                "过去完成时": ["habia", "habias", "habia hecho", "habia ido"],
                "现在完成时": ["he hecho", "has hecho", "ha hecho", "hemos hecho"],
                "现在进行时": ["esta haciendo", "estan haciendo", "estoy haciendo"],
                "将来进行时": ["va a hacer", "voy a hacer", "va a ir"],
                "将来完成时": ["habre", "habra", "habremos", "habreis", "habran"],
            },
            "zh": {
                "现在时": ["是", "为", "做", "去", "喜欢", "能", "会"],
                "过去时": ["了", "曾", "曾经", "过", "以前"],
                "进行时": ["正在", "在", "着", "呢"],
                "将来时": ["将", "要", "会", "打算", "以后", "将来"],
                "完成时": ["了", "完成", "已经", "都"],
                "过去完成时": ["已经", "早就", "都", "曾"],
                "现在完成时": ["已经", "完成了", "做完了", "做好了"],
                "现在进行时": ["正在", "在", "着", "呢"],
                "将来进行时": ["将在", "将要", "会在", "打算"],
                "将来完成时": ["将完成", "会完成", "到时候", "就"],
            },
            "ja": {
                "现在时": ["です", "である", "します", "いきます", "好きです", "できます"],
                "过去时": ["でした", "だった", "しました", "いきました", "好きでした", "できました"],
                "进行时": ["しています", "います", "いる", "ています"],
                "将来时": ["します", "いきます", "でしょう", "つもりです"],
                "完成时": ["しました", "いきました", "終わりました"],
                "过去完成时": ["していました", "いました", "た"],
                "现在完成时": ["もう", "すでに", "ちょうど"],
                "现在进行时": ["しています", "います", "ています"],
                "将来进行时": ["しているでしょう", "いているでしょう"],
                "将来完成时": ["終わっているでしょう", "しているでしょう"],
            },
        }
        
        tenses = tense_patterns.get(language, tense_patterns["en"])
        tense_counts = {k: 0 for k in tenses.keys()}
        
        for s in subtitles:
            text = s.get("text", "").lower()
            for tense, keywords in tenses.items():
                for kw in keywords:
                    if kw.lower() in text:
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