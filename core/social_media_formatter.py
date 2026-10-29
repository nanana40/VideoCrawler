"""
社交媒体文案格式化器 - AI增强版

核心改进：
1. 词汇深度解析：词源、搭配、同义替换、使用场景、记忆技巧
2. 句子精准分析：针对具体句子的语法拆解，拒绝通用模板
3. 真实学习感悟：基于expression_knowledge的多维度深度思考
4. 实用练习设计：仿写、背诵、应用等多种形式
5. 针对性学习建议：根据不同学习目标提供定制化建议
6. AI增强：支持调用外部AI服务生成高质量文案（最多8次重构尝试）
"""

import os
import re
from enum import auto
import sys as _sys
if _sys.version_info >= (3, 11):
    from enum import StrEnum
else:
    from enum import Enum as _Enum
    class StrEnum(str, _Enum):
        pass
from typing import List, Dict, Any, Optional

from core.expression_knowledge import get_knowledge_base
from core.ai_writer import get_ai_writer, ContentType


class SocialStyle(StrEnum):
    XIAOHONGSHU = auto()
    WEIBO = auto()
    ZHIHU = auto()
    
    @property
    def display_name(self) -> str:
        names = {
            "xiaohongshu": "小红书",
            "weibo": "微博",
            "zhihu": "知乎"
        }
        return names.get(self.value, self.value)


class SocialContent:
    
    def __init__(self, success: bool, file_path: Optional[str] = None, content: Optional[str] = None, error_message: Optional[str] = None):
        self.success = success
        self.file_path = file_path
        self.content = content
        self.error_message = error_message


class LanguageAnalyzer:
    """深度语言分析器 - 真正有学习价值的分析逻辑
    支持多语言：英语、德语、法语、西班牙语、中文、日语等。
    """
    
    def __init__(self) -> None:
        self._knowledge_base = get_knowledge_base()
        self._lang_data = self._init_language_data()
    
    def _init_language_data(self) -> Dict[str, Dict[str, Any]]:
        """初始化多语言数据"""
        return {
            "en": {
                "simple_words": {"the", "and", "a", "an", "is", "are", "was", "were", "be", "been",
                               "have", "has", "had", "do", "does", "did", "will", "would", "could",
                               "should", "may", "might", "must", "to", "of", "in", "for", "on", "with",
                               "at", "by", "from", "as", "into", "through", "during", "before", "after",
                               "he", "she", "it", "we", "they", "you", "i", "me", "him", "her", "us",
                               "them", "this", "that", "these", "those", "what", "which", "who", "whom",
                               "so", "but", "if", "or", "because", "when", "where", "why", "how",
                               "all", "each", "few", "more", "most", "other", "some", "such", "no",
                               "not", "only", "own", "same", "than", "too", "very", "just", "now",
                               "can", "need", "time", "make", "take", "get", "go", "come", "know",
                               "think", "see", "want", "give", "use", "find", "tell", "ask", "work",
                               "seem", "feel", "look", "try", "say", "call", "help", "let", "keep",
                               "put", "run", "set", "turn", "thing", "things", "stuff", "guy", "guys",
                               "really", "pretty", "cool", "long", "short", "big", "small", "good", "bad",
                               "great", "nice", "well", "better", "best", "little", "lot", "lots", "many",
                               "much", "more", "most", "some", "any", "all", "none", "every", "each"},
                "vocabulary_groups": {
                    "高频口语词": ["really", "so", "well", "yeah", "alright", "cool", 
                                  "like", "just", "actually", "basically"],
                    "程度副词": ["very", "quite", "really", "pretty", "extremely", 
                                "absolutely", "completely", "totally", "fairly", "somewhat"],
                    "连接词": ["and", "but", "so", "because", "although", "however", 
                             "therefore", "nevertheless", "moreover", "furthermore"],
                    "日常动词": ["get", "make", "take", "give", "go", "come", "do", 
                               "have", "see", "think", "know", "want", "need", "feel"],
                    "描述性形容词": ["good", "great", "nice", "cool", "beautiful", "amazing",
                                  "wonderful", "interesting", "important", "different"],
                },
                "collocations": {
                    "significant": ["significant impact", "significant change", "significant amount", 
                                   "significant difference", "significant role"],
                    "influence": ["have an influence on", "influence decision", "influence behavior",
                                 "major influence", "strong influence"],
                    "achieve": ["achieve goal", "achieve success", "achieve result", 
                               "achieve objective", "achieve target"],
                    "contribute": ["contribute to", "make contribution", "contribute significantly",
                                  "contribute positively", "contribute greatly"],
                    "determine": ["determine outcome", "determine cause", "determine factor",
                                 "determine value", "determine direction"],
                    "potential": ["potential for", "have potential", "potential market",
                                 "potential customer", "potential problem"],
                    "perspective": ["from perspective", "different perspective", "new perspective",
                                   "unique perspective", "personal perspective"],
                    "analyze": ["analyze data", "analyze situation", "analyze problem",
                               "analyze result", "analyze trend"],
                    "evaluate": ["evaluate performance", "evaluate options", "evaluate quality",
                                "evaluate effectiveness", "evaluate impact"],
                    "establish": ["establish relationship", "establish rule", "establish system",
                                 "establish connection", "establish reputation"],
                    "maintain": ["maintain balance", "maintain relationship", "maintain quality",
                                "maintain standard", "maintain focus"],
                    "transform": ["transform into", "transform process", "transform industry",
                                 "transform business", "transform technology"],
                    "promote": ["promote development", "promote product", "promote growth",
                               "promote understanding", "promote cooperation"],
                    "realize": ["realize goal", "realize dream", "realize potential",
                               "realize mistake", "realize opportunity"],
                    "reduce": ["reduce cost", "reduce risk", "reduce waste", "reduce time",
                              "reduce impact"],
                    "reflect": ["reflect on", "reflect situation", "reflect change",
                               "reflect trend", "reflect attitude"],
                    "support": ["support decision", "provide support", "support idea",
                               "support project", "support development"],
                    "impact": ["impact on", "have impact", "significant impact",
                              "positive impact", "negative impact"],
                    "focus": ["focus on", "focus attention", "focus effort", "focus resource",
                             "focus strategy"],
                    "explore": ["explore option", "explore possibility", "explore market",
                               "explore opportunity", "explore approach"],
                },
                "synonyms": {
                    "significant": ["remarkable", "notable", "substantial", "considerable", "important"],
                    "influence": ["impact", "effect", "affect", "shape", "determine"],
                    "achieve": ["accomplish", "attain", "reach", "fulfill", "realize"],
                    "contribute": ["help", "add", "give", "provide", "support"],
                    "determine": ["decide", "shape", "influence", "define", "establish"],
                    "potential": ["possibility", "capability", "ability", "capacity", "opportunity"],
                    "perspective": ["viewpoint", "outlook", "standpoint", "angle", "approach"],
                    "analyze": ["examine", "study", "evaluate", "assess", "investigate"],
                    "evaluate": ["assess", "judge", "measure", "appraise", "examine"],
                    "establish": ["create", "build", "set up", "found", "develop"],
                    "maintain": ["keep", "preserve", "sustain", "continue", "retain"],
                    "transform": ["change", "convert", "alter", "revise", "modify"],
                    "promote": ["encourage", "support", "boost", "advance", "improve"],
                    "realize": ["fulfill", "achieve", "accomplish", "understand", "recognize"],
                    "reduce": ["decrease", "lower", "cut", "lessen", "minimize"],
                    "reflect": ["show", "demonstrate", "indicate", "reveal", "mirror"],
                    "support": ["back up", "assist", "aid", "help", "uphold"],
                    "impact": ["affect", "influence", "effect", "change", "transform"],
                    "focus": ["concentrate", "center", "direct", "target", "prioritize"],
                    "explore": ["investigate", "examine", "study", "research", "discover"],
                },
                "word_families": {
                    "significance": ["significant", "significantly", "signify", "significance"],
                    "influence": ["influence", "influential", "influentially"],
                    "achievement": ["achieve", "achievement", "achievable", "achieved"],
                    "contribution": ["contribute", "contribution", "contributory", "contributor"],
                    "determination": ["determine", "determination", "determined", "determining"],
                    "potential": ["potential", "potentially", "potentiate"],
                    "perspective": ["perspective", "perspective", "perspectively"],
                    "analysis": ["analyze", "analysis", "analytical", "analytically"],
                    "evaluation": ["evaluate", "evaluation", "evaluative", "evaluator"],
                    "establishment": ["establish", "establishment", "established"],
                    "maintenance": ["maintain", "maintenance", "maintainable", "maintained"],
                    "transformation": ["transform", "transformation", "transformative", "transformer"],
                    "promotion": ["promote", "promotion", "promotional", "promoter"],
                    "realization": ["realize", "realization", "realizable", "realized"],
                    "reduction": ["reduce", "reduction", "reductive", "reduced"],
                    "reflection": ["reflect", "reflection", "reflective", "reflectively"],
                    "support": ["support", "supportive", "supportively", "supporter"],
                    "impact": ["impact", "impactful", "impactfully"],
                    "focus": ["focus", "focused", "focusing", "focused"],
                    "exploration": ["explore", "exploration", "exploratory", "explorer"],
                },
                "word_pattern": r'\b[a-zA-Z]{6,}\b',
            },
            "de": {
                "simple_words": {"der", "die", "das", "ein", "eine", "einer", "einem", "einen",
                               "ist", "sind", "war", "waren", "sein", "haben", "hat", "hatte",
                               "werden", "wird", "wurde", "kann", "muss", "will", "soll", "darf",
                               "mag", "möchte", "von", "zu", "auf", "aus", "bei", "mit", "ohne",
                               "durch", "gegen", "zwischen", "unter", "nicht", "auch", "noch",
                               "schon", "so", "nur", "wieder", "immer", "sehr", "gut", "schlecht",
                               "lang", "kurz", "hoch", "niedrig", "neu", "alt", "klein", "groß",
                               "viel", "wenig", "mehr", "weniger", "ganz", "fast", "nicht",
                               "hier", "da", "dort", "wo", "wann", "warum", "wie", "was",
                               "ich", "du", "er", "sie", "es", "wir", "ihr", "sie", "sie",
                               "mich", "dich", "ihn", "ihm", "uns", "euch", "ihnen", "mir",
                               "dir", "haben", "sein", "werden", "machen", "gehen", "kommen",
                               "sehen", "hören", "sprechen", "schreiben", "lesen", "arbeiten",
                               "lernen", "kaufen", "verkaufen", "essen", "trinken", "schlafen",
                               "finden", "geben", "nehmen", "halten", "schließen", "öffnen"},
                "vocabulary_groups": {
                    "高频口语词": ["also", "mal", "ja", "ne", "einfach", "so", "halt", "eben", "naja", "tschüss"],
                    "程度副词": ["sehr", "ziemlich", "wirklich", "total", "extrem", "absolut", "völlig", "fast", "beinahe"],
                    "连接词": ["und", "aber", "also", "denn", "weil", "obwohl", "jedoch", "deshalb", "außerdem", "ferner"],
                    "日常动词": ["machen", "gehen", "kommen", "sehen", "hören", "sprechen", "schreiben", "lesen", "arbeiten", "lernen"],
                    "描述性形容词": ["gut", "schlecht", "groß", "klein", "lang", "kurz", "neu", "alt", "schön", "hässlich"],
                },
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
                "word_pattern": r'\b[a-zA-ZäöüßÄÖÜ]{6,}\b',
            },
            "fr": {
                "simple_words": {"le", "la", "les", "un", "une", "des", "du", "de", "au", "aux",
                               "est", "sont", "était", "étaient", "être", "avoir", "a", "ont",
                               "ai", "as", "avais", "avait", "aurai", "pourrait", "peut", "doit",
                               "veut", "devrait", "pourrait", "sera", "seront", "serait", "seraient",
                               "dans", "sur", "sous", "avec", "sans", "par", "pour", "en", "et",
                               "ou", "mais", "donc", "or", "ni", "car", "que", "qui", "quoi",
                               "dont", "où", "ce", "cette", "ces", "mon", "ma", "mes", "ton",
                               "ta", "tes", "son", "sa", "ses", "notre", "votre", "leur", "leurs",
                               "je", "tu", "il", "elle", "on", "nous", "vous", "ils", "elles",
                               "moi", "toi", "lui", "elle", "nous", "vous", "eux", "elles",
                               "bon", "mauvais", "grand", "petit", "long", "court", "haute",
                               "basse", "nouveau", "vieux", "bon", "très", "tres", "bien", "aussi"},
                "vocabulary_groups": {
                    "高频口语词": ["eh", "ben", "alors", "donc", "mais", "bon", "voilà", "hein", "tu sais", "genre"],
                    "程度副词": ["très", "assez", "vraiment", "complètement", "absolument", "totalement", "relativement", "peu"],
                    "连接词": ["et", "mais", "donc", "alors", "car", "parce que", "bien que", "tandis que", "ainsi", "cependant"],
                    "日常动词": ["être", "avoir", "faire", "aller", "venir", "voir", "dire", "savoir", "connaître", "pouvoir"],
                    "描述性形容词": ["bon", "mauvais", "grand", "petit", "long", "court", "nouveau", "vieux", "beau", "laid"],
                },
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
                "word_pattern": r'\b[a-zA-Zéèêëàâäçôùûüîïñ]{6,}\b',
            },
            "es": {
                "simple_words": {"el", "la", "los", "las", "un", "una", "unos", "unas", "de", "del",
                               "al", "a", "en", "y", "o", "pero", "que", "cual", "cuyo", "donde",
                               "cuando", "porque", "como", "si", "no", "más", "menos", "muy",
                               "bien", "mal", "bueno", "buena", "buenos", "buenas", "malo", "mala",
                               "grande", "pequeño", "alto", "bajo", "largo", "corto", "nuevo",
                               "viejo", "ser", "estar", "haber", "tener", "hacer", "ir", "venir",
                               "ver", "decir", "saber", "conocer", "dar", "pasar", "deber", "poder",
                               "querer", "llevar", "dejar", "poner", "parecer", "creer", "hablar",
                               "llevar", "pasar", "encontrar", "llevar", "decir", "ver", "hacer",
                               "yo", "tu", "usted", "nosotros", "vosotros", "ellos", "ellas",
                               "me", "te", "se", "nos", "os", "se", "mi", "tu", "su", "nuestro",
                               "vuestro", "sus", "este", "esta", "estos", "estas", "ese", "esa",
                               "esos", "esas", "aquel", "aquella", "aquellos", "aquellas"},
                "vocabulary_groups": {
                    "高频口语词": ["eh", "bueno", "pues", "entonces", "pero", "vamos", "o sea", "¿sabes?", "tipo", "carajo"],
                    "程度副词": ["muy", "bastante", "realmente", "completamente", "absolutamente", "totalmente", "relativamente", "poco"],
                    "连接词": ["y", "pero", "entonces", "porque", "aunque", "mientras", "por lo tanto", "sin embargo", "además", "también"],
                    "日常动词": ["ser", "estar", "haber", "tener", "hacer", "ir", "venir", "ver", "decir", "saber"],
                    "描述性形容词": ["bueno", "malo", "grande", "pequeño", "alto", "bajo", "nuevo", "viejo", "bueno", "bonito"],
                },
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
                "word_pattern": r'\b[a-zA-ZáéíóúüñÁÉÍÓÚÜÑ]{6,}\b',
            },
            "zh": {
                "simple_words": {"的", "了", "是", "在", "我", "有", "和", "他", "她", "它",
                               "这", "那", "都", "而", "及", "与", "等", "就", "也", "还",
                               "很", "太", "更", "最", "不", "没", "无", "要", "会", "能",
                               "可", "应", "该", "可以", "必须", "应该", "需要", "已经",
                               "正在", "将要", "曾经", "从来", "总是", "经常", "偶尔",
                               "什么", "怎么", "为什么", "哪里", "何时", "如何", "多少",
                               "几", "一些", "许多", "所有", "任何", "每", "各", "某",
                               "好", "坏", "大", "小", "多", "少", "长", "短", "高", "低",
                               "远", "近", "快", "慢", "早", "晚", "今", "昨", "明", "后"},
                "vocabulary_groups": {
                    "高频口语词": ["嗯", "啊", "哦", "好吧", "那个", "就是说", "其实", "基本上", "怎么说呢", "随便"],
                    "程度副词": ["非常", "特别", "十分", "相当", "极其", "完全", "绝对", "稍微", "有点", "比较"],
                    "连接词": ["和", "但是", "所以", "因为", "虽然", "然而", "因此", "另外", "而且", "不过"],
                    "日常动词": ["是", "有", "做", "去", "来", "看", "听", "说", "知道", "想"],
                    "描述性形容词": ["好", "坏", "大", "小", "长", "短", "新", "旧", "漂亮", "难看"],
                },
                "collocations": {
                    "重要": ["重要影响", "重要变化", "重要差异", "重要作用", "重要意义"],
                    "影响": ["影响决策", "影响行为", "重大影响", "积极影响", "消极影响"],
                    "实现": ["实现目标", "实现成功", "实现结果", "实现价值", "实现梦想"],
                    "贡献": ["贡献力量", "做出贡献", "积极贡献", "贡献发展", "贡献创新"],
                    "确定": ["确定结果", "确定原因", "确定方向", "确定因素", "确定方案"],
                    "潜力": ["潜力巨大", "发挥潜力", "发掘潜力", "潜力市场", "潜力发展"],
                    "视角": ["从视角", "新视角", "不同视角", "独特视角", "客观视角"],
                    "分析": ["分析数据", "分析情况", "分析问题", "分析结果", "分析趋势"],
                    "评估": ["评估绩效", "评估选项", "评估质量", "评估效果", "评估影响"],
                    "建立": ["建立关系", "建立规则", "建立系统", "建立联系", "建立信誉"],
                    "保持": ["保持平衡", "保持关系", "保持质量", "保持标准", "保持专注"],
                    "转变": ["转变过程", "转变行业", "转变业务", "转变思维", "转变观念"],
                    "促进": ["促进发展", "促进产品", "促进增长", "促进理解", "促进合作"],
                    "实现": ["实现目标", "实现梦想", "实现潜力", "实现机会", "实现价值"],
                    "减少": ["减少成本", "减少风险", "减少浪费", "减少时间", "减少影响"],
                    "反映": ["反映情况", "反映变化", "反映趋势", "反映态度", "反映问题"],
                    "支持": ["支持决策", "提供支持", "支持想法", "支持项目", "支持发展"],
                    "关注": ["关注焦点", "关注问题", "关注趋势", "关注发展", "关注变化"],
                    "探索": ["探索选项", "探索可能", "探索市场", "探索机会", "探索方法"],
                },
                "synonyms": {
                    "重要": ["关键", "核心", "主要", "重大", "紧要"],
                    "影响": ["作用", "效果", "效应", "后果", "冲击"],
                    "实现": ["达成", "完成", "做到", "兑现", "落实"],
                    "贡献": ["奉献", "付出", "投入", "出力", "助力"],
                    "确定": ["明确", "肯定", "确认", "断定", "判定"],
                    "潜力": ["潜能", "潜力", "潜质", "能力", "可能性"],
                    "视角": ["观点", "角度", "看法", "立场", "态度"],
                    "分析": ["剖析", "解析", "研究", "探讨", "研判"],
                    "评估": ["评价", "估量", "考量", "审核", "鉴定"],
                    "建立": ["创建", "设立", "构建", "创设", "组建"],
                    "保持": ["维持", "坚持", "保留", "维系", "延续"],
                    "转变": ["改变", "转换", "变革", "转型", "改观"],
                    "促进": ["推动", "助长", "助力", "增进", "加速"],
                    "减少": ["降低", "缩减", "削减", "减轻", "节约"],
                    "反映": ["体现", "表现", "折射", "映照", "映射"],
                    "支持": ["支撑", "援助", "拥护", "赞助", "扶助"],
                    "关注": ["重视", "关心", "留意", "注意", "聚焦"],
                    "探索": ["探究", "摸索", "探寻", "发掘", "钻研"],
                },
                "word_families": {
                    "重要": ["重要", "重要性", "重要地"],
                    "影响": ["影响", "影响", "影响"],
                    "实现": ["实现", "实现", "实现"],
                    "贡献": ["贡献", "贡献", "贡献"],
                    "确定": ["确定", "确定", "确定"],
                    "潜力": ["潜力", "潜力", "潜力"],
                    "视角": ["视角", "视角", "视角"],
                    "分析": ["分析", "分析", "分析"],
                    "评估": ["评估", "评估", "评估"],
                    "建立": ["建立", "建立", "建立"],
                    "保持": ["保持", "保持", "保持"],
                    "转变": ["转变", "转变", "转变"],
                    "促进": ["促进", "促进", "促进"],
                    "减少": ["减少", "减少", "减少"],
                    "反映": ["反映", "反映", "反映"],
                    "支持": ["支持", "支持", "支持"],
                    "关注": ["关注", "关注", "关注"],
                    "探索": ["探索", "探索", "探索"],
                },
                "word_pattern": r'[\u4e00-\u9fa5]{2,}',
            },
            "ja": {
                "simple_words": {"の", "は", "が", "を", "に", "で", "から", "まで", "と", "や",
                               "も", "か", "よ", "ね", "な", "です", "ます", "だ", "だった",
                               "でした", "ました", "ません", "ませんでした", "ではありません",
                               "いる", "ある", "する", "できる", "なる", "見る", "聞く", "話す",
                               "読む", "書く", "食べる", "飲む", "行く", "来る", "帰る", "待つ",
                               "考える", "思う", "知る", "分かる", "この", "その", "あの", "どの",
                               "これ", "それ", "あれ", "どれ", "ここ", "そこ", "あそこ", "どこ",
                               "いつ", "どう", "なぜ", "何", "私", "あなた", "彼", "彼女",
                               "私たち", "あなたたち", "彼ら", "彼女ら", "いい", "悪い", "大きい",
                               "小さい", "長い", "短い", "高い", "低い", "速い", "遅い", "多い",
                               "少ない", "新しい", "古い", "かわいい"},
                "vocabulary_groups": {
                    "高频口语词": ["ええ", "うん", "まあ", "そう", "ね", "よ", "な", "か", "ごめん", "すみません"],
                    "程度副词": ["とても", "非常に", "かなり", "だいぶ", "めちゃくちゃ", "まったく", "少し", "ちょっと"],
                    "连接词": ["そして", "でも", "だから", "なぜなら", "けれども", "しかし", "それで", "それに"],
                    "日常动词": ["する", "いる", "ある", "見る", "聞く", "話す", "食べる", "飲む", "行く", "来る"],
                    "描述性形容词": ["いい", "悪い", "大きい", "小さい", "長い", "短い", "新しい", "古い", "かわいい", "きれい"],
                },
                "collocations": {
                    "重要": ["重要な影響", "重要な変化", "重要な違い", "重要な役割", "重要な意味"],
                    "影響": ["影響を与える", "大きな影響", "プラスの影響", "マイナスの影響"],
                    "達成": ["目標を達成", "成功を達成", "結果を達成", "価値を達成"],
                    "貢献": ["貢献する", "大きな貢献", "積極的な貢献", "発展への貢献"],
                    "確定": ["結果を確定", "原因を確定", "方向を確定", "要因を確定"],
                    "潜在": ["潜在能力", "潜在市場", "潜在的な可能性", "潜在的なリスク"],
                    "視点": ["視点から", "新しい視点", "異なる視点", "客観的な視点"],
                    "分析": ["データを分析", "状況を分析", "問題を分析", "結果を分析"],
                    "評価": ["パフォーマンスを評価", "選択肢を評価", "品質を評価", "効果を評価"],
                    "構築": ["関係を構築", "ルールを構築", "システムを構築", "信用を構築"],
                    "維持": ["均衡を維持", "関係を維持", "品質を維持", "基準を維持"],
                    "変革": ["プロセスを変革", "産業を変革", "ビジネスを変革", "考え方を変革"],
                    "促進": ["発展を促進", "製品を促進", "成長を促進", "理解を促進"],
                    "実現": ["目標を実現", "夢を実現", "可能性を実現", "機会を実現"],
                    "削減": ["コストを削減", "リスクを削減", "無駄を削減", "時間を削減"],
                    "反映": ["状況を反映", "変化を反映", "傾向を反映", "態度を反映"],
                    "支援": ["意思決定を支援", "支援を提供", "アイデアを支援", "プロジェクトを支援"],
                    "集中": ["焦点を集中", "注意を集中", "努力を集中", "リソースを集中"],
                    "探求": ["選択肢を探求", "可能性を探求", "市場を探求", "機会を探求"],
                },
                "synonyms": {
                    "重要": ["重大", "不可欠", "主要", "肝心", "必須"],
                    "影響": ["作用", "効果", "結果", "波及", "衝撃"],
                    "達成": ["達する", "実現", "完成", "成就", "実行"],
                    "貢献": ["寄与", "助力", "支援", "協力", "参加"],
                    "確定": ["明確", "確認", "判断", "決定", "選択"],
                    "潜在": ["可能性", "能力", "資質", "見込み", "期待"],
                    "視点": ["観点", "角度", "見方", "立場", "態度"],
                    "分析": ["解析", "研究", "検討", "調査", "評価"],
                    "評価": ["判断", "見積もり", "検証", "鑑定", "検査"],
                    "構築": ["構成", "創設", "建設", "設立", "形成"],
                    "維持": ["持続", "保持", "保全", "継続", "守る"],
                    "変革": ["変化", "転換", "改革", "転換", "変遷"],
                    "促進": ["推進", "加速", "増進", "支援", "活性化"],
                    "削減": ["減少", "低減", "削除", "抑制", "節約"],
                    "反映": ["表現", "示す", "映す", "表示", "示唆"],
                    "支援": ["援助", "後援", "協力", "補助", "応援"],
                    "集中": ["集約", "注目", "重視", "優先", "特化"],
                    "探求": ["探索", "追究", "調査", "発見", "研究"],
                },
                "word_families": {
                    "重要": ["重要", "重要性", "重要"],
                    "影響": ["影響", "影響", "影響"],
                    "達成": ["達成", "達成", "達成"],
                    "貢献": ["貢献", "貢献", "貢献"],
                    "確定": ["確定", "確定", "確定"],
                    "潜在": ["潜在", "潜在", "潜在"],
                    "視点": ["視点", "視点", "視点"],
                    "分析": ["分析", "分析", "分析"],
                    "評価": ["評価", "評価", "評価"],
                    "構築": ["構築", "構築", "構築"],
                    "維持": ["維持", "維持", "維持"],
                    "変革": ["変革", "変革", "変革"],
                    "促進": ["促進", "促進", "促進"],
                    "削減": ["削減", "削減", "削減"],
                    "反映": ["反映", "反映", "反映"],
                    "支援": ["支援", "支援", "支援"],
                    "集中": ["集中", "集中", "集中"],
                    "探求": ["探求", "探求", "探求"],
                },
                "word_pattern": r'[\u3040-\u30ff\u3400-\u4dbf\u4e00-\u9fff]{2,}',
            },
            "ko": {
                "simple_words": {"의", "이", "가", "을", "를", "에", "에서", "로", "으로", "와",
                               "과", "이나", "나", "도", "만", "밖에", "까지", "부터", "보다",
                               "는", "은", "이다", "있다", "없다", "되다", "하다", "않다",
                               "라고", "이라고", "라", "이라", "私", "あなた", "彼", "彼女",
                               "私たち", "あなたたち", "彼ら", "彼女ら", "いい", "悪い",
                               "大きい", "小さい", "長い", "短い", "高い", "低い", "速い",
                               "遅い", "多い", "少ない", "新しい", "古い", "かわいい"},
                "vocabulary_groups": {
                    "高频口语词": ["어", "아", "그래", "응", "음", "뭐", "그냥", "어쩌다", "어디", "무슨"],
                    "程度副词": ["매우", "아주", "정말", "참", "상당히", "완전히", "약간", "조금"],
                    "连接词": ["그리고", "하지만", "그래서", "왜냐하면", "비록", "그러나", "따라서", "또한"],
                    "日常动词": ["하다", "있다", "되다", "가다", "오다", "보다", "듣다", "말하다", "알다", "생각하다"],
                    "描述性形容词": ["좋다", "나쁘다", "크다", "작다", "길다", "짧다", "새롭다", "오래되다", "예쁘다", "못생기다"],
                },
                "collocations": {
                    "중요": ["중요한 영향", "중요한 변화", "중요한 차이", "중요한 역할", "중요한 의미"],
                    "영향": ["영향을 미치다", "큰 영향", "긍정적인 영향", "부정적인 영향"],
                    "달성": ["목표를 달성", "성공을 달성", "결과를 달성", "가치를 달성"],
                    "기여": ["기여하다", "큰 기여", "긍정적인 기여", "발전에 기여"],
                    "확정": ["결과를 확정", "원인을 확정", "방향을 확정", "요인을 확정"],
                    "잠재": ["잠재력", "잠재 시장", "잠재 가능성", "잠재 위험"],
                    "시각": ["시각에서", "새로운 시각", "다른 시각", "객관적인 시각"],
                    "분석": ["데이터를 분석", "상황을 분석", "문제를 분석", "결과를 분석"],
                    "평가": ["성과를 평가", "선택지를 평가", "품질을 평가", "효과를 평가"],
                    "구축": ["관계를 구축", "규칙을 구축", "시스템을 구축", "신용을 구축"],
                    "유지": ["균형을 유지", "관계를 유지", "품질을 유지", "기준을 유지"],
                    "변혁": ["과정을 변혁", "산업을 변혁", "비즈니스를 변혁", "사고방식을 변혁"],
                    "촉진": ["발전을 촉진", "제품을 촉진", "성장을 촉진", "이해를 촉진"],
                    "실현": ["목표를 실현", "꿈을 실현", "가능성을 실현", "기회를 실현"],
                    "감소": ["비용을 감소", "위험을 감소", "낭비를 감소", "시간을 감소"],
                    "반영": ["상황을 반영", "변화를 반영", "추세를 반영", "태도를 반영"],
                    "지원": ["의사결정을 지원", "지원을 제공", "아이디어를 지원", "프로젝트를 지원"],
                    "집중": ["초점을 집중", "주의를 집중", "노력을 집중", "자원을 집중"],
                    "탐구": ["선택지를 탐구", "가능성을 탐구", "시장을 탐구", "기회를 탐구"],
                },
                "synonyms": {
                    "중요": ["핵심", "주요", "중대", "필수", "중심"],
                    "영향": ["효과", "작용", "결과", "영향력", "충격"],
                    "달성": ["성취", "완성", "실현", "성공", "수행"],
                    "기여": ["공헌", "도움", "지원", "협력", "참여"],
                    "확정": ["명확", "확인", "판단", "결정", "선택"],
                    "잠재": ["가능성", "역량", "자질", "전망", "희망"],
                    "시각": ["관점", "각도", "견해", "입장", "태도"],
                    "분석": ["해석", "연구", "검토", "조사", "평가"],
                    "평가": ["판단", "추정", "검증", "감정", "검사"],
                    "구축": ["구성", "설립", "건설", "형성", "조직"],
                    "유지": ["지속", "보존", "연장", "보호", "유지"],
                    "변혁": ["변화", "전환", "개혁", "개편", "변모"],
                    "촉진": ["추진", "가속", "증진", "활성화", "지원"],
                    "감소": ["감축", "하락", "축소", "억제", "절감"],
                    "반영": ["표현", "나타내다", "비추다", "보이다", "암시"],
                    "지원": ["원조", "후원", "협력", "보조", "응원"],
                    "집중": ["집약", "주목", "중시", "우선", "특화"],
                    "탐구": ["탐색", "연구", "조사", "발견", "분석"],
                },
                "word_families": {
                    "중요": ["중요", "중요성", "중요"],
                    "영향": ["영향", "영향", "영향"],
                    "달성": ["달성", "달성", "달성"],
                    "기여": ["기여", "기여", "기여"],
                    "확정": ["확정", "확정", "확정"],
                    "잠재": ["잠재", "잠재", "잠재"],
                    "시각": ["시각", "시각", "시각"],
                    "분석": ["분석", "분석", "분석"],
                    "평가": ["평가", "평가", "평가"],
                    "구축": ["구축", "구축", "구축"],
                    "유지": ["유지", "유지", "유지"],
                    "변혁": ["변혁", "변혁", "변혁"],
                    "촉진": ["촉진", "촉진", "촉진"],
                    "감소": ["감소", "감소", "감소"],
                    "반영": ["반영", "반영", "반영"],
                    "지원": ["지원", "지원", "지원"],
                    "집중": ["집중", "집중", "집중"],
                    "탐구": ["탐구", "탐구", "탐구"],
                },
                "word_pattern": r'[\uac00-\ud7af]{2,}',
            },
            "ru": {
                "simple_words": {"и", "в", "не", "на", "я", "с", "он", "со", "что", "его",
                               "наш", "тот", "к", "а", "но", "да", "ты", "который", "из",
                               "у", "весь", "же", "бы", "о", "за", "тот", "так", "как",
                               "этот", "еще", "был", "все", "ещё", "она", "ты", "не", "а",
                               "но", "да", "и", "а", "но", "да", "есть", "быть", "иметь",
                               "делать", "говорить", "идти", "приходить", "уходить", "видеть",
                               "слышать", "знать", "думать", "хотеть", "мочь", "надо", "хотеть",
                               "я", "ты", "он", "она", "оно", "мы", "вы", "они", "меня", "тебя",
                               "его", "ее", "нас", "вас", "их", "мой", "твой", "его", "ее",
                               "наш", "ваш", "их", "этот", "тот", "такой", "какой", "сам"},
                "vocabulary_groups": {
                    "高频口语词": ["ну", "в общем", "типа", "вот", "да", "нет", "ага", "хорошо", "нужно", "можно"],
                    "程度副词": ["очень", "крайне", "чрезвычайно", "довольно", "достаточно", "больше", "меньше", "лучше", "хуже"],
                    "连接词": ["и", "но", "а", "так", "как", "если", "хотя", "поскольку", "чтобы", "когда"],
                    "日常动词": ["есть", "быть", "иметь", "делать", "говорить", "идти", "приходить", "уходить", "видеть", "слышать"],
                    "描述性形容词": ["хорошо", "плохо", "большой", "маленький", "новый", "старый", "длинный", "короткий", "высокий", "низкий"],
                },
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
                "word_pattern": r'\b[а-яА-ЯёЁ]{6,}\b',
            },
            "it": {
                "simple_words": {"il", "lo", "la", "i", "gli", "le", "un", "uno", "una", "dei",
                               "degli", "delle", "di", "del", "dalla", "dall'", "allo", "nelle",
                               "che", "chi", "cui", "quale", "quali", "non", "sì", "no", "e", "ma",
                               "o", "perché", "quando", "come", "dove", "che", "cosa", "qual", "quanto",
                               "sono", "è", "era", "erano", "essere", "avere", "ho", "hai", "ha", "abbiamo",
                               "avete", "hanno", "ho", "avevo", "aveva", "avevano", "potere", "dovere",
                               "volere", "sapere", "conoscere", "fare", "andare", "venire", "vedere", "dire",
                               "leggere", "scrivere", "parlare", "ascoltare", "capire", "mi", "ti", "si", "ci",
                               "vi", "gli", "loro", "me", "te", "se", "lo", "la", "li", "le"},
                "vocabulary_groups": {
                    "高频口语词": ["eh", "beh", "quindi", "perciò", "ma", "allora", "dunque", "insomma", "tipo", "guarda"],
                    "程度副词": ["molto", "abbastanza", "veramente", "completamente", "assolutamente", "totalmente", "relativamente", "poco"],
                    "连接词": ["e", "ma", "quindi", "perché", "anche se", "mentre", "perciò", "tuttavia", "inoltre", "anche"],
                    "日常动词": ["essere", "avere", "fare", "andare", "venire", "vedere", "dire", "sapere", "conoscere", "potere"],
                    "描述性形容词": ["buono", "cattivo", "grande", "piccolo", "lungo", "corto", "nuovo", "vecchio", "bello", "brutto"],
                },
                "collocations": {
                    "significativo": ["impatto significativo", "cambiamento significativo", "importanza significativa",
                                   "differenza significativa", "ruolo significativo", "importo significativo"],
                    "influenza": ["avere influenza su", "grande influenza", "influenza positiva",
                                 "influenza negativa", "influenza considerevole", "nessuna influenza"],
                    "raggiungere": ["raggiungere un obiettivo", "raggiungere il successo", "raggiungere un goal",
                                   "raggiungere un livello", "raggiungere un risultato", "raggiungere un record"],
                    "contribuire": ["contribuire a", "fare un contributo", "contribuire significativamente",
                                  "contribuire all'innovazione", "contribuire allo sviluppo"],
                    "determinare": ["determinare il risultato", "determinare la causa", "determinare il prezzo",
                                 "determinare la velocità", "determinare la direzione", "determinare il valore"],
                    "potenziale": ["avere potenziale", "riconoscere il potenziale", "sfruttare il potenziale",
                                  "massimo potenziale", "alto potenziale", "potenziale a lungo termine"],
                    "prospettiva": ["da una prospettiva", "altra prospettiva", "nuova prospettiva",
                                    "prospettiva personale", "prospettiva critica"],
                    "analizzare": ["analizzare dati", "analizzare una situazione", "analizzare un problema",
                                   "analizzare un risultato", "analizzare una tendenza", "analizzare un mercato"],
                    "valutare": ["valutare una performance", "valutare opzioni", "valutare una qualità",
                                   "valutare un'efficacia", "valutare impatti"],
                    "stabilire": ["stabilire una relazione", "stabilire una regola", "stabilire un sistema",
                                   "stabilire una connessione", "stabilire una reputazione"],
                    "mantenere": ["mantenere un equilibrio", "mantenere una relazione", "mantenere una qualità",
                                  "mantenere uno standard", "mantenere un focus", "mantenere un'integrità"],
                    "trasformare": ["trasformare in qualcosa", "trasformare un processo", "trasformare un'industria",
                                       "trasformare un business", "trasformare una tecnologia"],
                    "promuovere": ["promuovere lo sviluppo", "promuovere un prodotto", "promuovere la crescita",
                                 "promuovere la comprensione", "promuovere la collaborazione"],
                    "realizzare": ["realizzare un obiettivo", "realizzare un sogno", "realizzare il potenziale",
                                     "realizzare un errore", "realizzare un'opportunità"],
                    "ridurre": ["ridurre costi", "ridurre un rischio", "ridurre rifiuti",
                                   "ridurre tempo", "ridurre impatti"],
                    "riflettere": ["riflettere su qualcosa", "riflettere una situazione", "riflettere un cambiamento",
                                     "riflettere una tendenza", "riflettere un atteggiamento"],
                    "supportare": ["supportare una decisione", "fornire supporto", "supportare un'idea",
                                     "supportare un progetto", "supportare lo sviluppo"],
                    "impatto": ["avere un impatto", "impatto significativo", "impatto positivo",
                                   "impatto negativo", "impatto a lungo termine"],
                    "concentrarsi": ["concentrarsi su qualcosa", "concentrare l'attenzione",
                                      "concentrare sforzi", "concentrare risorse"],
                    "esplorare": ["esplorare opzioni", "esplorare possibilità", "esplorare un mercato",
                                     "esplorare opportunità", "esplorare un approccio"],
                },
                "synonyms": {
                    "significativo": ["notevole", "essenziale", "substantiale", "considerevole", "importante"],
                    "influenza": ["impatto", "effetto", "influenza", "determinazione", "gestione"],
                    "raggiungere": ["ottenere", "conseguire", "acquisire", "realizzare", "conquista"],
                    "contribuire": ["apportare", "partecipare", "aiutare", "supportare", "collaborare"],
                    "determinare": ["fissare", "decidere", "influenzare", "definire", "stabilire"],
                    "potenziale": ["possibilità", "capacità", "aptitudine", "potenzialità", "opportunità"],
                    "prospettiva": ["punto di vista", "visione", "approccio", "angolo", "orientamento"],
                    "analizzare": ["esaminare", "studiare", "valutare", "giudicare", "ispezionare"],
                    "valutare": ["giudicare", "apprezzare", "misurare", "stimare", "verificare"],
                    "stabilire": ["creare", "costruire", "organizzare", "fondare", "sviluppare"],
                    "mantenere": ["tenere", "preservare", "supportare", "continuare", "conservare"],
                    "trasformare": ["cambiare", "convertire", "modificare", "riorganizzare", "adattare"],
                    "promuovere": ["incoraggiare", "supportare", "accelerare", "sviluppare", "migliorare"],
                    "realizzare": ["concretizzare", "raggiungere", "compiere", "capire", "riconoscere"],
                    "ridurre": ["diminuire", "abbassare", "restringere", "limitare", "minimizzare"],
                    "riflettere": ["mostrare", "dimostrare", "indicare", "rivelare", "specchiare"],
                    "supportare": ["appoggiare", "supportare", "aiutare", "difendere", "promuovere"],
                    "impatto": ["influenza", "effetto", "conseguenza", "cambiamento", "trasformazione"],
                    "concentrarsi": ["focalizzarsi", "riunire", "direzionare", "priorizzare", "centrare"],
                    "esplorare": ["investigare", "esaminare", "studiare", "cercare", "scoprire"],
                },
                "word_families": {
                    "significativo": ["significativo", "significato", "significare", "significativo"],
                    "influenza": ["influenza", "influente", "influenzante"],
                    "raggiungere": ["raggiungere", "raggiungimento", "raggiungibile", "raggiunto"],
                    "contribuire": ["contribuire", "contributo", "contribuente", "contributore"],
                    "determinare": ["determinare", "determinazione", "determinato", "determinante"],
                    "potenziale": ["potenziale", "potenzialmente", "potenzializzare"],
                    "prospettiva": ["prospettiva", "prospettico", "prospettivo"],
                    "analizzare": ["analizzare", "analisi", "analitico", "analista"],
                    "valutare": ["valutare", "valutazione", "valutativo", "valutatore"],
                    "stabilire": ["stabilire", "stabilimento", "stabilito"],
                    "mantenere": ["mantenere", "mantenimento", "mantenibile", "mantenuto"],
                    "trasformare": ["trasformare", "trasformazione", "trasformativo", "trasformatore"],
                    "promuovere": ["promuovere", "promozione", "promuovente", "promotore"],
                    "realizzare": ["realizzare", "realizzazione", "realizzabile", "realizzato"],
                    "ridurre": ["ridurre", "riduzione", "riduttivo", "ridotto"],
                    "riflettere": ["riflettere", "riflessione", "riflettente", "riflettore"],
                    "supportare": ["supportare", "supporto", "supportante", "supporto"],
                    "impatto": ["impatto", "impattante", "impattante"],
                    "concentrarsi": ["concentrarsi", "concentrazione", "concentrato", "concentrato"],
                    "esplorare": ["esplorare", "esplorazione", "esploratore", "esplorativo"],
                },
                "word_pattern": r'\b[a-zA-Zàèéìíòóùúâêîôûäëïöüç]{6,}\b',
            },
            "pt": {
                "simple_words": {"o", "a", "os", "as", "um", "uma", "uns", "umas", "de", "do",
                               "da", "dos", "das", "no", "na", "nos", "nas", "por", "para",
                               "com", "sem", "em", "e", "mas", "ou", "que", "qual", "cujo", "onde",
                               "quando", "porque", "como", "se", "não", "mais", "menos", "muito",
                               "bem", "mal", "bom", "boa", "bons", "boas", "ruim", "grande",
                               "pequeno", "alto", "baixo", "longo", "curto", "novo", "velho",
                               "ser", "estar", "ter", "fazer", "ir", "vir", "ver", "dizer", "saber",
                               "conhecer", "dar", "passar", "dever", "poder", "querer", "levar",
                               "deixar", "por", "parecer", "crever", "falar", "eu", "tu", "você",
                               "nosso", "vosso", "eles", "elas", "me", "te", "se", "nos", "os", "se"},
                "vocabulary_groups": {
                    "高频口语词": ["eh", "bom", "então", "pois", "mas", "vamos", "tipo", "sabe?", "né", "gente"],
                    "程度副词": ["muito", "bastante", "realmente", "completamente", "absolutamente", "totalmente", "relativamente", "pouco"],
                    "连接词": ["e", "mas", "então", "porque", "embora", "enquanto", "portanto", "no entanto", "além disso", "também"],
                    "日常动词": ["ser", "estar", "ter", "fazer", "ir", "vir", "ver", "dizer", "saber", "conhecer"],
                    "描述性形容词": ["bom", "ruim", "grande", "pequeno", "alto", "baixo", "novo", "velho", "bonito", "feio"],
                },
                "collocations": {
                    "significativo": ["impacto significativo", "mudança significativa", "importância significativa",
                                   "diferença significativa", "papel significativo", "valor significativo"],
                    "influência": ["ter influência em", "grande influência", "influência positiva",
                                 "influência negativa", "influência considerável", "nenhuma influência"],
                    "atingir": ["atingir um objetivo", "atingir o sucesso", "atingir uma meta",
                                   "atingir um nível", "atingir um resultado", "atingir um recorde"],
                    "contribuir": ["contribuir para", "fazer uma contribuição", "contribuir significativamente",
                                  "contribuir para a melhoria", "contribuir para o desenvolvimento"],
                    "determinar": ["determinar o resultado", "determinar a causa", "determinar o preço",
                                 "determinar a velocidade", "determinar a direção", "determinar o valor"],
                    "potencial": ["ter potencial", "reconhecer o potencial", "explotar o potencial",
                                  "máximo potencial", "alto potencial", "potencial de longo prazo"],
                    "perspectiva": ["em uma perspectiva", "outra perspectiva", "nova perspectiva",
                                    "própria perspectiva", "perspectiva crítica"],
                    "analisar": ["analisar dados", "analisar uma situação", "analisar um problema",
                                   "analisar um resultado", "analisar uma tendência", "analisar um mercado"],
                    "avaliar": ["avaliar um desempenho", "avaliar opções", "avaliar uma qualidade",
                                   "avaliar uma eficácia", "avaliar impactos"],
                    "estabelecer": ["estabelecer uma relação", "estabelecer uma regra", "estabelecer um sistema",
                                   "estabelecer uma conexão", "estabelecer uma reputação"],
                    "manter": ["manter um equilíbrio", "manter uma relação", "manter uma qualidade",
                                  "manter um padrão", "manter um foco", "manter uma integridade"],
                    "transformar": ["transformar em algo", "transformar um processo", "transformar uma indústria",
                                       "transformar um negócio", "transformar uma tecnologia"],
                    "promover": ["promover o desenvolvimento", "promover um produto", "promover o crescimento",
                                 "promover a compreensão", "promover a colaboração"],
                    "realizar": ["realizar um objetivo", "realizar um sonho", "realizar o potencial",
                                     "realizar um erro", "realizar uma oportunidade"],
                    "reduzir": ["reduzir custos", "reduzir um risco", "reduzir resíduos",
                                   "reduzir tempo", "reduzir impactos"],
                    "refletir": ["refletir sobre algo", "refletir uma situação", "refletir uma mudança",
                                     "refletir uma tendência", "refletir uma atitude"],
                    "suportar": ["suportar uma decisão", "fornecer suporte", "suportar uma ideia",
                                     "suportar um projeto", "suportar o desenvolvimento"],
                    "impacto": ["ter um impacto", "impacto significativo", "impacto positivo",
                                   "impacto negativo", "impacto de longo prazo"],
                    "concentrar": ["concentrar-se em algo", "concentrar a atenção",
                                      "concentrar esforços", "concentrar recursos"],
                    "explorar": ["explorar opções", "explorar possibilidades", "explorar um mercado",
                                     "explorar oportunidades", "explorar uma abordagem"],
                },
                "synonyms": {
                    "significativo": ["notável", "essencial", "substancial", "considerável", "importante"],
                    "influência": ["impacto", "efeito", "influência", "determinação", "gestão"],
                    "atingir": ["alcançar", "obter", "adquirir", "realizar", "conseguir"],
                    "contribuir": ["aporten", "participar", "ajudar", "suportar", "colaborar"],
                    "determinar": ["fixar", "decidir", "influenciar", "definir", "estabelecer"],
                    "potencial": ["possibilidade", "capacidade", "aptidão", "potencialidade", "oportunidade"],
                    "perspectiva": ["ponto de vista", "visão", "enfoque", "ângulo", "orientação"],
                    "analisar": ["examinar", "estudar", "avaliar", "julgar", "inspecionar"],
                    "avaliar": ["julgar", "apreciar", "medir", "estimar", "verificar"],
                    "estabelecer": ["criar", "construir", "organizar", "fundar", "desenvolver"],
                    "manter": ["manter", "preservar", "suportar", "continuar", "conservar"],
                    "transformar": ["mudar", "converter", "modificar", "reorganizar", "adaptar"],
                    "promover": ["fomentar", "suportar", "acelerar", "desenvolver", "melhorar"],
                    "realizar": ["concretizar", "atingir", "cumprir", "compreender", "reconhecer"],
                    "reduzir": ["diminuir", "baixar", "reduzir", "limitar", "minimizar"],
                    "refletir": ["mostrar", "demonstrar", "indicar", "revelar", "espelhar"],
                    "suportar": ["apoiar", "suportar", "ajudar", "defender", "promover"],
                    "impacto": ["influência", "efeito", "consequência", "mudança", "transformação"],
                    "concentrar": ["focar-se", "reunir", "dirigir", "priorizar", "centralizar"],
                    "explorar": ["investigar", "examinar", "estudar", "buscar", "descobrir"],
                },
                "word_families": {
                    "significativo": ["significativo", "significado", "significar", "significativo"],
                    "influência": ["influência", "influenciador", "influenciando"],
                    "atingir": ["atingir", "atingimento", "atingível", "atingido"],
                    "contribuir": ["contribuir", "contribuição", "contribuindo", "contribuidor"],
                    "determinar": ["determinar", "determinação", "determinado", "determinante"],
                    "potencial": ["potencial", "potencialmente", "potencializar"],
                    "perspectiva": ["perspectiva", "perspectiva", "perspectiva"],
                    "analisar": ["analisar", "análise", "analítico", "analista"],
                    "avaliar": ["avaliar", "avaliação", "avaliativo", "avaliador"],
                    "estabelecer": ["estabelecer", "estabelecimento", "estabelecido"],
                    "manter": ["manter", "manutenção", "mantendo", "mantido"],
                    "transformar": ["transformar", "transformação", "transformador", "transformando"],
                    "promover": ["promover", "promoção", "promovendo", "promotor"],
                    "realizar": ["realizar", "realização", "realizável", "realizado"],
                    "reduzir": ["reduzir", "redução", "reductivo", "reduzido"],
                    "refletir": ["refletir", "reflexão", "refletindo", "reflectante"],
                    "suportar": ["suportar", "suporte", "suportando", "suporte"],
                    "impacto": ["impacto", "impactando", "impactante"],
                    "concentrar": ["concentrar", "concentração", "concentrado", "concentrando"],
                    "explorar": ["explorar", "exploração", "explorador", "explorando"],
                },
                "word_pattern": r'\b[a-zA-ZàèéìíòóùúâêîôûäëïöüçãõñÁÉÍÓÚÃÕÑ]{6,}\b',
            },
            "da": {
                "simple_words": {"en", "et", "en", "de", "dem", "den", "det", "der", "som", "og",
                               "men", "eller", "for", "da", "hvor", "når", "hvis", "at", "ikke",
                               "jo", "nej", "ja", "så", "nu", "der", "denne", "dette", "disse",
                               "ham", "hende", "dem", "sig", "mig", "dig", "os", "jer", "min",
                               "din", "sin", "vor", "deres", "en", "et", "en", "den", "det",
                               "er", "var", "blev", "blive", "have", "har", "havde", "hadde",
                               "kunne", "ville", "skulle", "må", "bør", "magne", "være", "gøre",
                               "gå", "komme", "se", "sige", "vide", "kende", "give", "tag",
                               "få", "gå", "komme", "se", "sige", "vide", "kende", "give", "tag"},
                "vocabulary_groups": {
                    "高频口语词": ["eh", "altså", "så", "vel", "ja", "nej", "nå", "okay", "jo", "nu"],
                    "程度副词": ["meget", "temmelig", "virkelig", "helt", "absolut", "total", "relativt", "lidt"],
                    "连接词": ["og", "men", "så", "da", "fordi", "selvom", "mens", "derfor", "desuden", "også"],
                    "日常动词": ["være", "have", "gøre", "gå", "komme", "se", "sige", "vide", "kende", "kunne"],
                    "描述性形容词": ["god", "dårlig", "stor", "lille", "lang", "kort", "ny", "gamle", "smuk", "grim"],
                },
                "collocations": {
                    "betydningfuld": ["betydningfuld indflydelse", "betydningfuld ændring", "betydningfuld betydning",
                                   "betydningfuld forskel", "betydningfuld rolle", "betydningfuld mængde"],
                    "indflydelse": ["have indflydelse på", "stor indflydelse", "positiv indflydelse",
                                 "negativ indflydelse", "betydningsfuld indflydelse", "ingen indflydelse"],
                    "nå": ["nå et mål", "nå succes", "nå et mål",
                                   "nå et niveau", "nå et resultat", "nå en rekord"],
                    "bidrage": ["bidrage til", "give en bidrag", "bidrage betydningsfuldt",
                                  "bidrage til forbedring", "bidrage til udvikling"],
                    "bestemme": ["bestemme resultat", "bestemme årsag", "bestemme pris",
                                 "bestemme hastighed", "bestemme retning", "bestemme værdi"],
                    "potentiale": ["have potentiale", "genkende potentiale", "udnytte potentiale",
                                  "maksimalt potentiale", "højt potentiale", "langtidspotentiale"],
                    "perspektiv": ["fra et perspektiv", "andet perspektiv", "nyt perspektiv",
                                    "egen perspektiv", "kritisk perspektiv"],
                    "analysere": ["analysere data", "analysere en situation", "analysere et problem",
                                   "analysere et resultat", "analysere en tendens", "analysere en markeds"],
                    "evaluere": ["evaluere en ydeevne", "evaluere muligheder", "evaluere kvalitet",
                                   "evaluere effektivitet", "evaluere indflydelser"],
                    "etablere": ["etablere en relation", "etablere en regel", "etablere et system",
                                   "etablere en forbindelse", "etablere en reputation"],
                    "opretholde": ["opretholde et ligevægt", "opretholde en relation", "opretholde kvalitet",
                                  "opretholde et standard", "opretholde et fokus", "opretholde integritet"],
                    "transformere": ["transformere til noget", "transformere en proces", "transformere en industri",
                                       "transformere en forretning", "transformere en teknologi"],
                    "fremme": ["fremme udvikling", "fremme et produkt", "fremme vækst",
                                 "fremme forståelse", "fremme samarbejde"],
                    "realisere": ["realisere et mål", "realisere en drøm", "realisere potentiale",
                                     "realisere en fejl", "realisere en mulighed"],
                    "reducere": ["reducere omkostninger", "reducere et risiko", "reducere affald",
                                   "reducere tid", "reducere indflydelser"],
                    "reflektere": ["reflektere over noget", "reflektere en situation", "reflektere en ændring",
                                     "reflektere en tendens", "reflektere en holdning"],
                    "understøtte": ["understøtte en beslutning", "give støtte", "understøtte en idé",
                                     "understøtte et projekt", "understøtte udvikling"],
                    "indflydelse": ["have indflydelse", "betydningsfuld indflydelse", "positiv indflydelse",
                                   "negativ indflydelse", "langtidlig indflydelse"],
                    "koncentrere": ["koncentrere sig om noget", "koncentrere opmærksomhed",
                                      "koncentrere indsats", "koncentrere ressourcer"],
                    "undersøge": ["undersøge muligheder", "undersøge muligheder", "undersøge en markeds",
                                     "undersøge muligheder", "undersøge en tilgang"],
                },
                "synonyms": {
                    "betydningfuld": ["bemærkelsesværdig", "vigtig", "substantiel", "betragtelig", "central"],
                    "indflydelse": ["virknings", "effekt", "indflydelse", "bestemmelse", "styrrelse"],
                    "nå": ["opnå", "få", "vinde", "realisere", "udføre"],
                    "bidrage": ["tilføje", "medvirke", "hjælpe", "understøtte", "samarbejde"],
                    "bestemme": ["afgøre", "fastlægge", "indføre", "definere", "etablere"],
                    "potentiale": ["mulighed", "kapacitet", "evne", "potentialitet", "mulighed"],
                    "perspektiv": ["synspunkt", "udsigt", "standpunkt", "vinkel", "tilgang"],
                    "analysere": ["undersøge", "studere", "vurdere", "bedømme", "inspektere"],
                    "evaluere": ["bedømme", "vurder", "måle", "estimere", "bekræfte"],
                    "etablere": ["oprette", "bygge", "organisere", "grundlægge", "udvikle"],
                    "opretholde": ["bevare", "vedligeholde", "understøtte", "fortsætte", "konservere"],
                    "transformere": ["ændre", "omdanne", "modificere", "reorganisere", "tilpasse"],
                    "fremme": ["stimuler", "understøtte", "accelerere", "udvikle", "forbedre"],
                    "realisere": ["udføre", "nå", "komme i mål", "forstå", "anerkende"],
                    "reducere": ["formindske", "nedsætte", "begrænse", "minimere", "reduktion"],
                    "reflektere": ["vise", "demonstrere", "indikere", "afsløre", "spejle"],
                    "understøtte": ["støtte", "hjælpe", "bekræfte", "beskytte", "propagere"],
                    "indflydelse": ["virknings", "effekt", "resultat", "ændring", "transformation"],
                    "koncentrere": ["fokuser", "sammenslutte", "rette", "prioritere", "centralisere"],
                    "undersøge": ["undersøge", "undersøge", "studere", "søge", "opdage"],
                },
                "word_families": {
                    "betydningfuld": ["betydningfuld", "betydning", "betydningfuldt", "betydningfuld"],
                    "indflydelse": ["indflydelse", "indflydelsesfuld", "indflydelsesfuld"],
                    "nå": ["nå", "nået", "nåelig", "nået"],
                    "bidrage": ["bidrage", "bidrag", "bidragende", "bidrager"],
                    "bestemme": ["bestemme", "bestemmelse", "bestemt", "bestemmende"],
                    "potentiale": ["potentiale", "potentielt", "potentialisere"],
                    "perspektiv": ["perspektiv", "perspektivisk", "perspektivisk"],
                    "analysere": ["analysere", "analyse", "analytisk", "analytiker"],
                    "evaluere": ["evaluere", "evaluering", "evaluativ", "evaluator"],
                    "etablere": ["etablere", "etablering", "etableret"],
                    "opretholde": ["opretholde", "opretholdelse", "opretholdelig", "opretholdt"],
                    "transformere": ["transformere", "transformation", "transformativ", "transformator"],
                    "fremme": ["fremme", "fremmelse", "fremmende", "fremmer"],
                    "realisere": ["realisere", "realisering", "realiserbar", "realiseret"],
                    "reducere": ["reducere", "reduktion", "reducerende", "reduceret"],
                    "reflektere": ["reflektere", "refleksion", "reflekterende", "reflektor"],
                    "understøtte": ["understøtte", "understøttelse", "understøttende", "understøtter"],
                    "indflydelse": ["indflydelse", "indflydelsesfuld", "indflydelsesfuld"],
                    "koncentrere": ["koncentrere", "koncentration", "koncentreret", "koncentrerende"],
                    "undersøge": ["undersøge", "undersøgelse", "undersøger", "undersøgende"],
                },
                "word_pattern": r'\b[a-zA-ZæøåÆØÅ]{6,}\b',
            },
            "fi": {
                "simple_words": {"ja", "ei", "se", "on", "ole", "olla", "me", "sinä", "hän", "he",
                               "ne", "minä", "me", "te", "he", "ni", "minun", "sinun", "hänen", "meidän",
                               "teidän", "heidän", "tämä", "tuo", "se", "nämä", "tuot", "ne", "joka", "jotka",
                               "mikä", "mitkä", "missä", "missä", "milloin", "milloin", "miksi", "miksi",
                               "kuinka", "kuinka", "ja", "mutta", "tai", "jos", "vaikka", "koska", "kun",
                               "ja", "mutta", "tai", "jos", "vaikka", "koska", "kun", "on", "ei", "voi",
                               "pitäisi", "halua", "voida", "pystyä", "tulla", "menna", "nähdä", "kuulla",
                               "sanoa", "tietää", "ajattaa", "haluta", "voida", "pystyä", "olla", "olla"},
                "vocabulary_groups": {
                    "高频口语词": ["no", "niin", "tosin", "eli", "mutta", "voi", "joo", "ei", "no", "vittu"],
                    "程度副词": ["erittäin", "hyvin", "melko", "aivan", "täysin", "suuresti", "vähän", "paljon"],
                    "连接词": ["ja", "mutta", "tai", "jos", "vaikka", "koska", "kun", "siksi", "lisäksi", "myös"],
                    "日常动词": ["olla", "voida", "pystyä", "menna", "tulla", "nähdä", "kuulla", "sanoa", "tietää", "ajattaa"],
                    "描述性形容词": ["hyvä", "huono", "suuri", "pieni", "pitkä", "lyhyt", "uusi", "vanha", "kaunis", "pahankaunis"],
                },
                "collocations": {
                    "merkittävä": ["merkittävä vaikutus", "merkittävä muutos", "merkittävä merkitys",
                                   "merkittävä ero", "merkittävä rooli", "merkittävä määrä"],
                    "vaikutus": ["vaikuttaa", "suuri vaikutus", "positiivinen vaikutus",
                                 "negatiivinen vaikutus", "merkittävä vaikutus", "ei vaikutusta"],
                    "saavuttaa": ["saavuttaa tavoite", "saavuttaa onnistuminen", "saavuttaa tavoite",
                                   "saavuttaa taso", "saavuttaa tulos", "saavuttaa ennätys"],
                    "auttaa": ["auttaa", "antaa panos", "antaa merkittävä panos",
                                  "antaa panos kehittämiseen", "antaa panos edistämiseen"],
                    "määrittää": ["määrittää tulos", "määrittää syy", "määrittää hinta",
                                 "määrittää nopeus", "määrittää suunta", "määrittää arvo"],
                    "potentiaali": ["olla potentiaalinen", "tunnistaa potentiaali", "hyödyntää potentiaali",
                                  "maksimi potentiaali", "korkea potentiaali", "pitkäaikainen potentiaali"],
                    "näkökulma": ["näkökulmasta", "toinen näkökulma", "uusi näkökulma",
                                    "oma näkökulma", "kriittinen näkökulma"],
                    "analysoida": ["analysoida dataa", "analysoida tilanne", "analysoida ongelma",
                                   "analysoida tulos", "analysoida trendi", "analysoida markkina"],
                    "arvioida": ["arvioida suorituskyky", "arvioida vaihtoehdot", "arvioida laatu",
                                   "arvioida tehokkuus", "arvioida vaikutukset"],
                    "luoda": ["luoda yhteys", "luoda sääntö", "luoda järjestelmä",
                                   "luoda yhteys", "luoda maine"],
                    "sääntää": ["sääntää tasapaino", "sääntää yhteys", "sääntää laatu",
                                  "sääntää standardi", "sääntää fokus", "sääntää eheyys"],
                    "muuttaa": ["muuttaa jotakin", "muuttaa prosessi", "muuttaa teollisuus",
                                       "muuttaa yritys", "muuttaa teknologia"],
                    "edistää": ["edistää kehittämistä", "edistää tuotetta", "edistää kasvua",
                                 "edistää ymmärtämistä", "edistää yhteistyötä"],
                    "toteuttaa": ["toteuttaa tavoite", "toteuttaa unelma", "toteuttaa potentiaali",
                                     "toteuttaa virhe", "toteuttaa mahdollisuus"],
                    "vähentää": ["vähentää kustannuksia", "vähentää riskiä", "vähentää jätettä",
                                   "vähentää aikaa", "vähentää vaikutuksia"],
                    "heijastaa": ["heijastaa jotakin", "heijastaa tilanne", "heijastaa muutos",
                                     "heijastaa trendi", "heijastaa asenne"],
                    "tukea": ["tukea päätöstä", "tarjota tukea", "tukea ideaa",
                                     "tukea projektia", "tukea kehittämistä"],
                    "vaikutus": ["vaikuttaa", "merkittävä vaikutus", "positiivinen vaikutus",
                                   "negatiivinen vaikutus", "pitkäaikainen vaikutus"],
                    "keskittyä": ["keskittyä johonkin", "keskittyä huomiota",
                                      "keskittyä ponnisteluihin", "keskittyä resursseihin"],
                    "tutkia": ["tutkia vaihtoehdot", "tutkia mahdollisuudet", "tutkia markkina",
                                     "tutkia mahdollisuudet", "tutkia lähestymistapa"],
                },
                "synonyms": {
                    "merkittävä": ["huomattava", "keskeinen", "substantiaalinen", "merkittävä", "tärkeä"],
                    "vaikutus": ["vaikutus", "teho", "vaikutus", "determinaatio", "hallinta"],
                    "saavuttaa": ["saavuttaa", "onnistua", "tulla", "realisoida", "suorittaa"],
                    "auttaa": ["avata", "osallistua", "apu", "tukea", "yhteistyö"],
                    "määrittää": ["määrittää", "valita", "influenssi", "määritellä", "luoda"],
                    "potentiaali": ["mahdollisuus", "kyky", "taito", "potentiaalisuus", "tilaisuus"],
                    "näkökulma": ["näkökulma", "visio", "lähestymistapa", "kulma", "suunta"],
                    "analysoida": ["tutkia", "opiskella", "arvioida", "luonnos", "inspektoida"],
                    "arvioida": ["luonnos", "arvata", "mitta", "estimoida", "tarkistaa"],
                    "luoda": ["luoda", "rakentaa", "organisoida", "perustaa", "kehittää"],
                    "sääntää": ["säilyttää", "suojata", "tukea", "jatkaa", "konservoimaan"],
                    "muuttaa": ["muuttaa", "muuntaa", "muuttaa", "järjestelmällisesti", "sovittaa"],
                    "edistää": ["edistää", "tukea", "kiinnittää", "kehittää", "parantaa"],
                    "toteuttaa": ["suorittaa", "saavuttaa", "suorittaa", "ymmärtää", "tunnistaa"],
                    "vähentää": ["vähentää", "laskea", "rajoittaa", "minimalisoida", "vähentää"],
                    "heijastaa": ["näytellä", "demonoida", "osoittaa", "paljastaa", "peili"],
                    "tukea": ["tukea", "apu", "tuki", "suojata", "suosia"],
                    "vaikutus": ["vaikutus", "vaikutus", "tulos", "muutos", "transformaatio"],
                    "keskittyä": ["keskittyä", "kerätä", "suunta", "priorisoida", "keskittyä"],
                    "tutkia": ["tutkia", "tutkia", "opiskella", "hakea", "löytää"],
                },
                "word_families": {
                    "merkittävä": ["merkittävä", "merkitys", "merkittävästi", "merkittävä"],
                    "vaikutus": ["vaikutus", "vaikutusvaltainen", "vaikutusvaltainen"],
                    "saavuttaa": ["saavuttaa", "saavuttaminen", "saavutettavissa", "saavutettu"],
                    "auttaa": ["auttaa", "avustus", "avustava", "avustaja"],
                    "määrittää": ["määrittää", "määrittely", "määritetty", "määrittävä"],
                    "potentiaali": ["potentiaali", "potentiaalisesti", "potentiaalistaa"],
                    "näkökulma": ["näkökulma", "näkökulmaisesti", "näkökulmaisesti"],
                    "analysoida": ["analysoida", "analyysi", "analyyttinen", "analyytikko"],
                    "arvioida": ["arvioida", "arviointi", "arvioiva", "arvioija"],
                    "luoda": ["luoda", "luominen", "luotu"],
                    "sääntää": ["sääntää", "säännöt", "sääntöinen", "sääntö"],
                    "muuttaa": ["muuttaa", "muutos", "muuttava", "muuttaja"],
                    "edistää": ["edistää", "edistäminen", "edistävä", "edistäjä"],
                    "toteuttaa": ["toteuttaa", "toteutus", "toteutettavissa", "toteutettu"],
                    "vähentää": ["vähentää", "vähennys", "vähentävä", "vähennetty"],
                    "heijastaa": ["heijastaa", "heijastus", "heijastava", "heijastin"],
                    "tukea": ["tukea", "tuki", "tukeva", "tukeva"],
                    "vaikutus": ["vaikutus", "vaikutusvaltainen", "vaikutusvaltainen"],
                    "keskittyä": ["keskittyä", "keskittyminen", "keskittynyt", "keskittyvä"],
                    "tutkia": ["tutkia", "tutkimus", "tutkija", "tutkiva"],
                },
                "word_pattern": r'\b[a-zA-ZäöåÄÖÅ]{6,}\b',
            },
            "pl": {
                "simple_words": {"i", "w", "na", "z", "o", "do", "ze", "po", "za", "pod",
                               "przy", "między", "nad", "gdzie", "kiedy", "jak", "dlaczego", "co",
                               "który", "która", "które", "którzy", "których", "mój", "twój", "jego", "jej",
                               "nasz", "wasz", "ich", "ten", "ta", "to", "te", "ten", "ta", "to", "te",
                               "jest", "są", "był", "była", "były", "być", "mieć", "mam", "masz", "ma",
                               "mamy", "macie", "mają", "miałem", "miałaś", "mieliśmy", "mieliście", "mieli",
                               "móc", "powinien", "chcieć", "znać", "umieć", "powiedzieć", "pobrać", "iść",
                               "przyjść", "zobaczyć", "usłyszeć", "mówić", "czytać", "piśmiennictwo", "robić"},
                "vocabulary_groups": {
                    "高频口语词": ["eh", "no", "więc", "no", "ale", "no", "no", "no", "no", "no"],
                    "程度副词": ["bardzo", "dość", "naprawdę", "całkowicie", "absolutnie", "zupełnie", "relatywnie", "trochę"],
                    "连接词": ["i", "ale", "więc", "ponieważ", "chociaż", "podczas gdy", "dlatego", "jednak", "ponadto", "również"],
                    "日常动词": ["być", "mieć", "robić", "iść", "przyjść", "zobaczyć", "usłyszeć", "mówić", "znać", "umieć"],
                    "描述性形容词": ["dobry", "zły", "duży", "mały", "długi", "krótki", "nowy", "stary", "piękny", "brzydki"],
                },
                "collocations": {
                    "znaczący": ["znaczący wpływ", "znacząca zmiana", "znacząca znaczenie",
                                   "znacząca różnica", "znacząca rola", "znaczna kwota"],
                    "wpływ": ["wpływać na", "duży wpływ", "pozytywny wpływ",
                                 "negatywny wpływ", "znaczny wpływ", "żadny wpływ"],
                    "osiągnąć": ["osiągnąć cel", "osiągnąć sukces", "osiągnąć cel",
                                   "osiągnąć poziom", "osiągnąć wynik", "osiągnąć rekord"],
                    "przyczynić": ["przyczynić się do", "przyczynić się znacząco",
                                  "przyczynić się do rozwoju", "przyczynić się do poprawy"],
                    "określić": ["określić wynik", "określić przyczynę", "określić cenę",
                                 "określić prędkość", "określić kierunek", "określić wartość"],
                    "potencjał": ["mieć potencjał", "rozpoznać potencjał", "wykorzystać potencjał",
                                  "maksymalny potencjał", "wysoki potencjał", "długoterminowy potencjał"],
                    "perspektywa": ["z perspektywy", "inna perspektywa", "nowa perspektywa",
                                    "własna perspektywa", "krytyczna perspektywa"],
                    "analizować": ["analizować dane", "analizować sytuację", "analizować problem",
                                   "analizować wynik", "analizować trend", "analizować rynek"],
                    "oceniać": ["oceniać wydajność", "oceniać opcje", "oceniać jakość",
                                   "oceniać skuteczność", "oceniać wpływy"],
                    "ustalić": ["ustalić relację", "ustalić regułę", "ustalić system",
                                   "ustalić połączenie", "ustalić reputację"],
                    "utrzymywać": ["utrzymywać równowagę", "utrzymywać relację", "utrzymywać jakość",
                                  "utrzymywać standard", "utrzymywać fokus", "utrzymywać integralność"],
                    "przekształcać": ["przekształcać w coś", "przekształcać proces", "przekształcać przemysł",
                                       "przekształcać biznes", "przekształcać technologię"],
                    "promować": ["promować rozwój", "promować produkt", "promować rozwój",
                                 "promować zrozumienie", "promować współpracę"],
                    "realizować": ["realizować cel", "realizować sen", "realizować potencjał",
                                     "realizować błąd", "realizować możliwość"],
                    "zmniejszać": ["zmniejszać koszty", "zmniejszać ryzyko", "zmniejszać odpady",
                                   "zmniejszać czas", "zmniejszać wpływy"],
                    "odbijać": ["odbijać się na czymś", "odbijać sytuację", "odbijać zmianę",
                                     "odbijać trend", "odbijać postawę"],
                    "wspierać": ["wspierać decyzję", "dostarczać wsparcia", "wspierać ideę",
                                     "wspierać projekt", "wspierać rozwój"],
                    "wpływ": ["mieć wpływ", "znaczny wpływ", "pozytywny wpływ",
                                   "negatywny wpływ", "długoterminowy wpływ"],
                    "skupiać": ["skupiać się na czymś", "skupiać uwagę",
                                      "skupiać wysiłki", "skupiać zasoby"],
                    "badac": ["badac opcje", "badac możliwości", "badac rynek",
                                     "badac możliwości", "badac podejście"],
                },
                "synonyms": {
                    "znaczący": ["istotny", "podstawowy", "substancjalny", "ważny", "kluczowy"],
                    "wpływ": ["wpływ", "efekt", "wpływ", "determinacja", "kontrola"],
                    "osiągnąć": ["osiągnąć", "udzielić", "dotrzeć", "zrealizować", "wykonać"],
                    "przyczynić": ["przyczynić", "współpracować", "pomóc", "wspierać", "współpracować"],
                    "określić": ["określić", "wybrać", "wpływać", "zdefiniować", "ustalić"],
                    "potencjał": ["możliwość", "zdolność", "talent", "potencjał", "szansa"],
                    "perspektywa": ["perspektywa", "wizja", "podejście", "kąt", "orientacja"],
                    "analizować": ["analizować", "studować", "oceniać", "przeglądać", "inspekować"],
                    "oceniać": ["oceniać", "szacować", "mierzyć", "estymować", "sprawdzić"],
                    "ustalić": ["ustalić", "stworzyć", "zorganizować", "założyć", "rozwijać"],
                    "utrzymywać": ["utrzymywać", "chronić", "wspierać", "kontynuować", "konserwować"],
                    "przekształcać": ["przekształcać", "przekształcać", "modyfikować", "reorganizować", "dostosowywać"],
                    "promować": ["promować", "wspierać", "przyspieszać", "rozwijać", "lepszyć"],
                    "realizować": ["realizować", "osiągnąć", "wykonać", "rozumieć", "uznać"],
                    "zmniejszać": ["zmniejszać", "obniżać", "ograniczać", "minimalizować", "zmniejszać"],
                    "odbijać": ["odbijać", "demonstrować", "wskazywać", "ujawniać", "odbijać"],
                    "wspierać": ["wspierać", "pomagać", "wspierać", "bronić", "promować"],
                    "wpływ": ["wpływ", "efekt", "wynik", "zmiana", "transformacja"],
                    "skupiać": ["skupiać", "zbierać", "skierowywać", "priorytetować", "centrować"],
                    "badac": ["badac", "badac", "studować", "szukać", "odkryć"],
                },
                "word_families": {
                    "znaczący": ["znaczący", "znaczenie", "znacznie", "znaczący"],
                    "wpływ": ["wpływ", "wpływowy", "wpływowy"],
                    "osiągnąć": ["osiągnąć", "osiągnięcie", "osiągalny", "osiągnięty"],
                    "przyczynić": ["przyczynić", "przyczynek", "przyczyniający", "przyczyniciel"],
                    "określić": ["określić", "określenie", "określony", "określający"],
                    "potencjał": ["potencjał", "potencjalnie", "potencjalizować"],
                    "perspektywa": ["perspektywa", "perspektywiczny", "perspektywiczny"],
                    "analizować": ["analizować", "analiza", "analityczny", "analityk"],
                    "oceniać": ["oceniać", "ocena", "oceniający", "ocenior"],
                    "ustalić": ["ustalić", "ustalenie", "ustalony"],
                    "utrzymywać": ["utrzymywać", "utrzymanie", "utrzymywany", "utrzymany"],
                    "przekształcać": ["przekształcać", "przekształcenie", "przekształcający", "przekształcator"],
                    "promować": ["promować", "promocja", "promujący", "promotor"],
                    "realizować": ["realizować", "realizacja", "realizowalny", "realizowany"],
                    "zmniejszać": ["zmniejszać", "zmniejszenie", "zmniejszający", "zmniejszony"],
                    "odbijać": ["odbijać", "odbicie", "odbijający", "odbicie"],
                    "wspierać": ["wspierać", "wsparcie", "wspierający", "wspierający"],
                    "wpływ": ["wpływ", "wpływowy", "wpływowy"],
                    "skupiać": ["skupiać", "skupienie", "skupiony", "skupiający"],
                    "badac": ["badac", "badanie", "badacz", "badający"],
                },
                "word_pattern": r'\b[a-zA-ZąćęłńóśźżĄĆĘŁŃÓŚŹŻ]{6,}\b',
            },
            "cs": {
                "simple_words": {"a", "v", "na", "z", "do", "s", "k", "o", "pro", "od",
                               "u", "mezi", "nad", "pod", "před", "za", "po", "kde", "kdy", "jak",
                               "proč", "co", "který", "která", "které", "kteří", "můj", "tvůj", "jeho", "její",
                               "náš", "vaš", "jejich", "ten", "ta", "to", "tyto", "ten", "ta", "to", "tyto",
                               "je", "jsou", "byl", "byla", "byly", "být", "mít", "mám", "máš", "má",
                               "máme", "máte", "mají", "měl", "měla", "měli", "mohu", "můžeš", "může",
                               "můžeme", "můžete", "můžou", "měl bych", "měla by", "měli bychom", "chtěl", "chtěla",
                               "chtěli", "znát", "umět", "říct", "brat", "jít", "přicházet", "vidět", "slýchat"},
                "vocabulary_groups": {
                    "高频口语词": ["eh", "no", "tak", "že", "ale", "no", "no", "no", "no", "no"],
                    "程度副词": ["velmi", "docela", "skutečně", "plně", "absolutně", "vůbec", "relativně", "trochu"],
                    "连接词": ["a", "ale", "tak", "protože", "i když", "zatímco", "proto", "nicméně", "navíc", "také"],
                    "日常动词": ["být", "mít", "dělat", "jít", "přicházet", "vidět", "slýchat", "říct", "znát", "umět"],
                    "描述性形容词": ["dobrý", "špatný", "velký", "malý", "dlouhý", "krátký", "nový", "starý", "krásný", "špatný"],
                },
                "collocations": {
                    "signifikantní": ["signifikantní vliv", "signifikantní změna", "signifikantní význam",
                                   "signifikantní rozdíl", "signifikantní role", "signifikantní částka"],
                    "vliv": ["mít vliv na", "velký vliv", "kladný vliv",
                                 "záporný vliv", "signifikantní vliv", "žádný vliv"],
                    "dosáhnout": ["dosáhnout cíle", "dosáhnout úspěchu", "dosáhnout cíle",
                                   "dosáhnout úrovně", "dosáhnout výsledku", "dosáhnout rekordu"],
                    "přispět": ["přispět k", "přispět signifikančně",
                                  "přispět ke zlepšení", "přispět k rozvoji"],
                    "určit": ["určit výsledek", "určit příčinu", "určit cenu",
                                 "určit rychlost", "určit směr", "určit hodnotu"],
                    "potenciál": ["mít potenciál", "rozpoznat potenciál", "využít potenciál",
                                  "maximální potenciál", "vysoký potenciál", "dlouhodobý potenciál"],
                    "perspektiva": ["z perspektivy", "jiná perspektiva", "nová perspektiva",
                                    "vlastní perspektiva", "kritická perspektiva"],
                    "analyzovat": ["analyzovat data", "analyzovat situaci", "analyzovat problém",
                                   "analyzovat výsledek", "analyzovat trend", "analyzovat trh"],
                    "hodnotit": ["hodnotit výkon", "hodnotit možnosti", "hodnotit kvalitu",
                                   "hodnotit účinnost", "hodnotit vlivy"],
                    "založit": ["založit vztah", "založit pravidlo", "založit systém",
                                   "založit spojení", "založit reputaci"],
                    "udržet": ["udržet rovnováhu", "udržet vztah", "udržet kvalitu",
                                  "udržet standard", "udržet fokus", "udržet integritu"],
                    "transformovat": ["transformovat v něco", "transformovat proces", "transformovat průmysl",
                                       "transformovat podnik", "transformovat technologii"],
                    "podporovat": ["podporovat rozvoj", "podporovat produkt", "podporovat růst",
                                 "podporovat porozumění", "podporovat spolupráci"],
                    "realizovat": ["realizovat cíl", "realizovat sen", "realizovat potenciál",
                                     "realizovat chybu", "realizovat příležitost"],
                    "snížit": ["snížit náklady", "snížit riziko", "snížit odpadky",
                                   "snížit čas", "snížit vlivy"],
                    "odrážet": ["odrážet na něčem", "odrážet situaci", "odrážet změnu",
                                     "odrážet trend", "odrážet postoj"],
                    "podporovat": ["podporovat rozhodnutí", "poskytnout podporu", "podporovat myšlenku",
                                     "podporovat projekt", "podporovat rozvoj"],
                    "vliv": ["mít vliv", "signifikantní vliv", "kladný vliv",
                                   "záporný vliv", "dlouhodobý vliv"],
                    "soustředit": ["soustředit se na něco", "soustředit pozornost",
                                      "soustředit úsilí", "soustředit zdroje"],
                    "zkoumat": ["zkoumat možnosti", "zkoumat možnosti", "zkoumat trh",
                                     "zkoumat možnosti", "zkoumat přístup"],
                },
                "synonyms": {
                    "signifikantní": ["významný", "podstatný", "substanciální", "důležitý", "klíčový"],
                    "vliv": ["vliv", "efekt", "vliv", "determinace", "kontrola"],
                    "dosáhnout": ["dosáhnout", "dosažit", "dosáhnout", "realizovat", "provést"],
                    "přispět": ["přispět", "spolupracovat", "pomoci", "podporovat", "spolupracovat"],
                    "určit": ["určit", "vybrat", "vliv", "definovat", "založit"],
                    "potenciál": ["možnost", "schopnost", "talent", "potenciál", "příležitost"],
                    "perspektiva": ["perspektiva", "vize", "přístup", "úhel", "orientace"],
                    "analyzovat": ["analyzovat", "studovat", "hodnotit", "prozkoumat", "inspektovat"],
                    "hodnotit": ["hodnotit", "odhadnout", "změřit", "estimovat", "ověřit"],
                    "založit": ["založit", "vytvořit", "organizovat", "zakládat", "rozvíjet"],
                    "udržet": ["udržet", "chránit", "podporovat", "pokračovat", "konservovat"],
                    "transformovat": ["transformovat", "přeměnit", "modyfikovat", "reorganizovat", "přizpůsobit"],
                    "podporovat": ["podporovat", "podporovat", "rychlit", "rozvíjet", "zlepšit"],
                    "realizovat": ["realizovat", "dosáhnout", "provést", "pochopit", "uznat"],
                    "snížit": ["snížit", "snížit", "omezit", "minimalizovat", "snížit"],
                    "odrážet": ["odrážet", "demonstrovat", "ukazovat", "odhalit", "odrážet"],
                    "podporovat": ["podporovat", "pomoci", "podporovat", "bránit", "propagovat"],
                    "vliv": ["vliv", "efekt", "výsledek", "změna", "transformace"],
                    "soustředit": ["soustředit", "shromáždit", "směřovat", "prioritizovat", "centrovat"],
                    "zkoumat": ["zkoumat", "zkoumat", "studovat", "hledat", "objevit"],
                },
                "word_families": {
                    "signifikantní": ["signifikantní", "signifikance", "signifikantně", "signifikantní"],
                    "vliv": ["vliv", "vlivný", "vlivný"],
                    "dosáhnout": ["dosáhnout", "dosažení", "dosažitelný", "dosáhnutý"],
                    "přispět": ["přispět", "přispěvek", "přispívající", "přispěvatel"],
                    "určit": ["určit", "určení", "určitý", "určující"],
                    "potenciál": ["potenciál", "potenciálně", "potenciálovat"],
                    "perspektiva": ["perspektiva", "perspektivní", "perspektivní"],
                    "analyzovat": ["analyzovat", "analýza", "analytický", "analytik"],
                    "hodnotit": ["hodnotit", "hodnocení", "hodnotící", "hodnocov"],
                    "založit": ["založit", "založení", "založený"],
                    "udržet": ["udržet", "udržování", "udržovatelný", "udržený"],
                    "transformovat": ["transformovat", "transformace", "transformační", "transformátor"],
                    "podporovat": ["podporovat", "podpora", "podporující", "podporovatel"],
                    "realizovat": ["realizovat", "realizace", "realizovatelný", "realizovaný"],
                    "snížit": ["snížit", "snížení", "snížující", "snížený"],
                    "odrážet": ["odrážet", "odraz", "odrážející", "odraz"],
                    "podporovat": ["podporovat", "podpora", "podporující", "podporovatel"],
                    "vliv": ["vliv", "vlivný", "vlivný"],
                    "soustředit": ["soustředit", "soustředění", "soustředěný", "soustřeďující"],
                    "zkoumat": ["zkoumat", "zkoumání", "zkoumatel", "zkoumající"],
                },
                "word_pattern": r'\b[a-zA-ZáčďéěíjklmnňópršťúůýžÁČĎÉĚÍJKLMNŇÓPRŠŤÚŮÝŽ]{6,}\b',
            },
            "hu": {
                "simple_words": {"és", "a", "az", "egy", "egy", "már", "még", "nem", "is", "mint",
                               "ha", "mivel", "de", "s", "vagy", "pedig", "hogy", "milyen", "hol", "mikor",
                               "miért", "hogyan", "aki", "amely", "amelyek", "ennek", "ezen", "ezek", "azt", "azokat",
                               "én", "te", "ő", "mi", "ti", "ők", "magam", "magad", "magát", "magunk",
                               "magatok", "magukat", "van", "vannak", "volt", "voltak", "lenni", "van", "vannak",
                               "lenni", "tudni", "még", "már", "sem", "se", "ha", "más", "egy", "egy"},
                "vocabulary_groups": {
                    "高频口语词": ["he", "na", "szóval", "de", "pedig", "szóval", "na", "he", "na", "szóval"],
                    "程度副词": ["nagyon", "egész", "valóban", "teljesen", "abszolút", "teljesen", "viszonylag", "kissé"],
                    "连接词": ["és", "de", "szóval", "mivel", "bár", "miközben", "ezért", "azonban", "emellett", "illetve"],
                    "日常动词": ["lenni", "tudni", "már", "még", "sem", "se", "ha", "más", "egy", "egy"],
                    "描述性形容词": ["jó", "rossz", "nagy", "kicsi", "hosszú", "rövid", "új", "öreg", "szép", "csúnya"],
                },
                "collocations": {
                    "signifikáns": ["signifikáns hatás", "signifikáns változás", "signifikáns jelentőség",
                                   "signifikáns különbség", "signifikáns szerep", "signifikáns összeg"],
                    "hatás": ["hatásolni", "nagy hatás", "pozitív hatás",
                                 "negatív hatás", "signifikáns hatás", "semmilyen hatás"],
                    "elérni": ["elérni egy cél", "elérni sikert", "elérni egy cél",
                                   "elérni egy szint", "elérni egy eredmény", "elérni egy rekordot"],
                    "hozzájárulni": ["hozzájárulni", "hozzájárulni jelentősen",
                                  "hozzájárulni a fejlesztéshez", "hozzájárulni a javításához"],
                    "meghatározni": ["meghatározni az eredményt", "meghatározni az okot", "meghatározni az árat",
                                 "meghatározni a sebességet", "meghatározni az irányt", "meghatározni az értéket"],
                    "potenciál": ["potenciálja van", "felismerni a potenciált", "kiaknázni a potenciált",
                                  "maximum potenciál", "magas potenciál", "hosszú távú potenciál"],
                    "perspektíva": ["egy perspektívából", "másik perspektíva", "új perspektíva",
                                    "saját perspektíva", "kritikus perspektíva"],
                    "elemz": ["elemz a adatokat", "elemz a helyzetet", "elemz a problémát",
                                   "elemz az eredményt", "elemz a tendenciát", "elemz a piacot"],
                    "értékel": ["értékel a teljesítményt", "értékel a lehetőségeket", "értékel a minőséget",
                                   "értékel a hatékonyságot", "értékel a hatásokat"],
                    "megalapozni": ["megalapozni egy kapcsolatot", "megalapozni egy szabályt", "megalapozni egy rendszert",
                                   "megalapozni egy kapcsolatot", "megalapozni egy hírnevet"],
                    "fenntartani": ["fenntartani egy egyensúlyt", "fenntartani egy kapcsolatot", "fenntartani a minőséget",
                                  "fenntartani egy standardot", "fenntartani egy fókuszt", "fenntartani az integritást"],
                    "transzformálni": ["transzformálni valamibe", "transzformálni egy folyamatot", "transzformálni egy ipart",
                                       "transzformálni egy üzletet", "transzformálni egy technológiát"],
                    "mozgatni": ["mozgatni a fejlesztést", "mozgatni a terméket", "mozgatni a növekedést",
                                 "mozgatni az értelmezést", "mozgatni a együttműködést"],
                    "megvalósítani": ["megvalósítani egy cél", "megvalósítani egy álmot", "megvalósítani a potenciált",
                                     "megvalósítani egy hibát", "megvalósítani egy lehetőséget"],
                    "csökkenteni": ["csökkenteni a költségeket", "csökkenteni a kockázatot", "csökkenteni a hulladékot",
                                   "csökkenteni az időt", "csökkenteni a hatásokat"],
                    "tükrözni": ["tükrözni valamit", "tükrözni a helyzetet", "tükrözni a változást",
                                     "tükrözni a tendenciát", "tükrözni a hozzáállást"],
                    "támogatni": ["támogatni egy döntést", "támogatást nyújtani", "támogatni egy ötletet",
                                     "támogatni egy projektet", "támogatni a fejlesztést"],
                    "hatás": ["hatásolni", "signifikáns hatás", "pozitív hatás",
                                   "negatív hatás", "hosszú távú hatás"],
                    "fókuszálni": ["fókuszálni valamire", "fókuszálni a figyelmet",
                                      "fókuszálni az erőfeszítéseket", "fókuszálni az erőforrásokat"],
                    "feltárni": ["feltárni a lehetőségeket", "feltárni a lehetőségeket", "feltárni a piacot",
                                     "feltárni a lehetőségeket", "feltárni egy megközelítést"],
                },
                "synonyms": {
                    "signifikáns": ["fontos", "alapvető", "szubstanciális", "meredek", "kulcsfontosságú"],
                    "hatás": ["hatás", "effektus", "hatás", "determináció", "kontroll"],
                    "elérni": ["elérni", "megkapni", "megérkezni", "megvalósítani", "elvégezni"],
                    "hozzájárulni": ["hozzájárulni", "közreműködni", "segíteni", "támogatni", "közreműködni"],
                    "meghatározni": ["meghatározni", "választani", "befolyásolni", "meghatározni", "megalapozni"],
                    "potenciál": ["lehetőség", "képesség", "tehetség", "potenciál", "alkalom"],
                    "perspektíva": ["perspektíva", "vízió", "megközelítés", "szög", "orientáció"],
                    "elemz": ["elemz", "tanulmányozni", "értékel", "vizsgálni", "vizsgálni"],
                    "értékel": ["értékel", "becsülni", "mérni", "becsülni", "ellenőrizni"],
                    "megalapozni": ["megalapozni", "létrehozni", "szervezni", "alapítani", "fejleszteni"],
                    "fenntartani": ["fenntartani", "védeni", "támogatni", "folytatni", "megőrizni"],
                    "transzformálni": ["transzformálni", "átalakítani", "módosítani", "újszervezni", "alkalmazni"],
                    "mozgatni": ["mozgatni", "támogatni", "gyorsítani", "fejleszteni", "javítani"],
                    "megvalósítani": ["megvalósítani", "elérni", "elvégezni", "megérteni", "elismerni"],
                    "csökkenteni": ["csökkenteni", "csökkenteni", "korlátozni", "minimalizálni", "csökkenteni"],
                    "tükrözni": ["tükrözni", "bemutatni", "mutatni", "felderíteni", "tükrözni"],
                    "támogatni": ["támogatni", "segíteni", "támogatni", "védeni", "hirdetni"],
                    "hatás": ["hatás", "effektus", "eredmény", "változás", "transzformáció"],
                    "fókuszálni": ["fókuszálni", "összegyűjteni", "irányítani", "prioritizálni", "központosítani"],
                    "feltárni": ["feltárni", "vizsgálni", "tanulmányozni", "keresni", "felderíteni"],
                },
                "word_families": {
                    "signifikáns": ["signifikáns", "signifikancia", "signifikánsan", "signifikáns"],
                    "hatás": ["hatás", "hatásos", "hatásos"],
                    "elérni": ["elérni", "elérés", "elérhető", "elért"],
                    "hozzájárulni": ["hozzájárulni", "hozzájárulás", "hozzájáruló", "hozzájáruló"],
                    "meghatározni": ["meghatározni", "meghatározás", "meghatározott", "meghatározó"],
                    "potenciál": ["potenciál", "potenciálisan", "potenciálni"],
                    "perspektíva": ["perspektíva", "perspektívás", "perspektívás"],
                    "elemz": ["elemz", "elemzés", "elemző", "elemző"],
                    "értékel": ["értékel", "értékelés", "értékelő", "értékelő"],
                    "megalapozni": ["megalapozni", "megalapozás", "megalapozott"],
                    "fenntartani": ["fenntartani", "fenntartás", "fenntartható", "fenntartott"],
                    "transzformálni": ["transzformálni", "transzformáció", "transzformáló", "transzformátor"],
                    "mozgatni": ["mozgatni", "mozgatás", "mozgató", "mozgató"],
                    "megvalósítani": ["megvalósítani", "megvalósítás", "megvalósítható", "megvalósított"],
                    "csökkenteni": ["csökkenteni", "csökkentés", "csökkentő", "csökkentett"],
                    "tükrözni": ["tükrözni", "tükrözés", "tükröző", "tükröző"],
                    "támogatni": ["támogatni", "támogatás", "támogató", "támogató"],
                    "hatás": ["hatás", "hatásos", "hatásos"],
                    "fókuszálni": ["fókuszálni", "fókusz", "fókuszált", "fókuszáló"],
                    "feltárni": ["feltárni", "feltárás", "feltáró", "feltáró"],
                },
                "word_pattern": r'\b[a-zA-ZáéíóöőúüűÁÉÍÓÖŐÚÜŰ]{6,}\b',
            },
            "ro": {
                "simple_words": {"și", "în", "pe", "cu", "pentru", "de", "la", "a", "o", "un",
                               "unei", "unui", "unor", "unele", "aceasta", "acesta", "acestea", "acești", "aceste",
                               "care", "ce", "cât", "câtă", "câte", "câți", "cum", "când", "unde", "de ce",
                               "este", "sunt", "era", "erau", "a fi", "a avea", "am", "ai", "are", "avem",
                               "aveți", "au", "am avut", "ai avut", "a avut", "am avut", "ai avut", "a avut",
                               "pot", "trebuie", "vrei", "știu", "știi", "știe", "știm", "știți", "știu",
                               "vorbesc", "citesti", "scrii", "iau", "pun", "fac", "merge", "vin", "vedem"},
                "vocabulary_groups": {
                    "高频口语词": ["eh", "noi", "deci", "dar", "și", "noi", "noi", "noi", "noi", "noi"],
                    "程度副词": ["foarte", "destul", "într-adevăr", "complet", "absolut", "total", "relativ", "puțin"],
                    "连接词": ["și", "dar", "deci", "pentru că", "deși", "în timp ce", "prin urmare", "totuși", "în plus", "de asemenea"],
                    "日常动词": ["a fi", "a avea", "a face", "a merge", "a veni", "a vedea", "a spune", "a ști", "a cunoaște", "a putea"],
                    "描述性形容词": ["bine", "rau", "mare", "mic", "lung", "scurt", "nou", "vechi", "frumos", "urât"],
                },
                "collocations": {
                    "semnificativ": ["impact semnificativ", "schimbare semnificativă", "importanță semnificativă",
                                   "diferență semnificativă", "rol semnificativ", "suma semnificativă"],
                    "influenc": ["avea influență asupra", "mare influență", "influență pozitivă",
                                 "influență negativă", "influență semnificativă", "nici o influență"],
                    "atinge": ["atinge un obiectiv", "atinge succesul", "atinge un obiectiv",
                                   "atinge un nivel", "atinge un rezultat", "atinge un record"],
                    "contribui": ["contribui la", "face o contribuție", "contribui semnificativ",
                                  "contribui la îmbunătățire", "contribui la dezvoltare"],
                    "determina": ["determina rezultatul", "determina cauza", "determina prețul",
                                 "determina viteza", "determina direcția", "determina valoarea"],
                    "potențial": ["avea potențial", "recunoaște potențialul", "exploatează potențialul",
                                  "potențial maxim", "potențial înalt", "potențial pe termen lung"],
                    "perspectiv": ["din perspectivă", "altă perspectivă", "nouă perspectivă",
                                    "perspectivă proprie", "perspectivă critică"],
                    "analiza": ["analiza datele", "analiza situația", "analiza problema",
                                   "analiza rezultatul", "analiza tendința", "analiza piața"],
                    "evalua": ["evalua performanța", "evalua opțiunile", "evalua calitatea",
                                   "evalua eficacitatea", "evalua impacturile"],
                    "stabilește": ["stabilește o relație", "stabilește o regulă", "stabilește un sistem",
                                   "stabilește o conexiune", "stabilește o reputație"],
                    "menține": ["menține echilibrul", "menține relația", "menține calitatea",
                                  "menține standardul", "menține concentrarea", "menține integritatea"],
                    "transforma": ["transforma în ceva", "transforma un proces", "transforma o industrie",
                                       "transforma o afacere", "transforma o tehnologie"],
                    "promovează": ["promovează dezvoltarea", "promovează produsul", "promovează creșterea",
                                 "promovează înțelegerea", "promovează colaborarea"],
                    "realizează": ["realizează un obiectiv", "realizează un vis", "realizează potențialul",
                                     "realizează o greșeală", "realizează o oportunitate"],
                    "reduce": ["reduce costurile", "reduce riscul", "reduce deșeurile",
                                   "reduce timpul", "reduce impacturile"],
                    "reflectă": ["reflectă asupra ceva", "reflectă situația", "reflectă schimbarea",
                                     "reflectă tendința", "reflectă atitudinea"],
                    "susține": ["susține o decizie", "oferește susținere", "susține o idee",
                                     "susține un proiect", "susține dezvoltarea"],
                    "impact": ["avea un impact", "impact semnificativ", "impact pozitiv",
                                   "impact negativ", "impact pe termen lung"],
                    "se concentrează": ["se concentrează asupra ceva", "concentrează atenția",
                                      "concentrează eforturile", "concentrează resursele"],
                    "explorează": ["explorează opțiunile", "explorează posibilitățile", "explorează piața",
                                     "explorează oportunitățile", "explorează o abordare"],
                },
                "synonyms": {
                    "semnificativ": ["notabil", "esențial", "substanțial", "considerabil", "important"],
                    "influenc": ["impact", "efect", "influenc", "determinare", "gestiune"],
                    "atinge": ["alcătuiește", "obține", "acquierează", "realizează", "conseguinte"],
                    "contribui": ["aporta", "participa", "ajută", "susține", "colaborează"],
                    "determina": ["fixează", "decidează", "influențează", "definește", "stabilește"],
                    "potențial": ["posibilitate", "capacitate", "aptitudine", "potențialitate", "oportunitate"],
                    "perspectiv": ["punct de vedere", "viziune", "abordare", "unghi", "orientare"],
                    "analiza": ["examinează", "studiază", "evaluează", "judește", "inspecționează"],
                    "evalua": ["judește", "apreciere", "măsoară", "estimează", "verifică"],
                    "stabilește": ["crează", "construiește", "organizează", "înființează", "dezvoltă"],
                    "menține": ["menține", "preservă", "susține", "continuă", "conservă"],
                    "transforma": ["schimbă", "convertește", "modifică", "reorganiză", "adaptează"],
                    "promovează": ["încurajează", "susține", "accelerează", "dezvoltă", "îmbunătățește"],
                    "realizează": ["concretizează", "atinge", "completează", "înțelege", "recunoaște"],
                    "reduce": ["scade", "bajează", "reduce", "limitează", "minimizează"],
                    "reflectă": ["arată", "demonstrează", "indică", "revelează", "reflectă"],
                    "susține": ["apoi", "susține", "ajută", "apără", "promovează"],
                    "impact": ["influenc", "efect", "consecință", "schimbare", "transformare"],
                    "se concentrează": ["se concentrează", "reunește", "dirijează", "priorizează", "centr"],
                    "explorează": ["investighează", "examinează", "studiază", "căută", "descoperă"],
                },
                "word_families": {
                    "semnificativ": ["semnificativ", "semnificație", "semnifica", "semnificativ"],
                    "influenc": ["influenc", "influențator", "influențând"],
                    "atinge": ["atinge", "atingere", "atingibil", "atingut"],
                    "contribui": ["contribui", "contribuție", "contribuind", "contributor"],
                    "determina": ["determina", "determinare", "determinat", "determinant"],
                    "potențial": ["potențial", "potențial", "potențializa"],
                    "perspectiv": ["perspectiv", "perspectivă", "perspectivă"],
                    "analiza": ["analiza", "analiză", "analitic", "analist"],
                    "evalua": ["evalua", "evaluare", "evaluativ", "evaluator"],
                    "stabilește": ["stabilește", "stabilire", "stabilit"],
                    "menține": ["menține", "menținere", "menținibil", "menținut"],
                    "transforma": ["transforma", "transformare", "transformator", "transformând"],
                    "promovează": ["promovează", "promovare", "promovând", "promotor"],
                    "realizează": ["realizează", "realizare", "realizabil", "realizat"],
                    "reduce": ["reduce", "reducere", "reductiv", "redus"],
                    "reflectă": ["reflectă", "reflecție", "reflectând", "reflectant"],
                    "susține": ["susține", "susținere", "susținând", "susținere"],
                    "impact": ["impact", "impactând", "impactant"],
                    "se concentrează": ["se concentrează", "concentrare", "concentrat", "concentrând"],
                    "explorează": ["explorează", "explorare", "explorator", "explorând"],
                },
                "word_pattern": r'\b[a-zA-ZăâîșțĂÂÎȘȚ]{6,}\b',
            },
            "ar": {
                "simple_words": {"ال", "و", "في", "من", "إلى", "على", "مع", "ب", "لا", "ه",
                               "هي", "هو", "هم", "هما", "هن", "أنا", "أنت", "أنتما", "أنتن",
                               "نحن", "ي", "ت", "ن", "م", "ك", "ه"},
                "vocabulary_groups": {
                    "高频口语词": ["أم", "أي", "أنا", "أوه", "حسنا", "مثل", "أعلم", "أرى", "حقا", "بالطبع"],
                    "程度副词": ["بشكل كبير", "حقا", "كثيرا", "قليلا", "ضد", "بالكامل", "جزئيا", "أساسا"],
                    "连接词": ["و", "لكن", "أو", "لأن", "إذا", "على الرغم من", "حتى", "عندما"],
                    "日常动词": ["يكون", "يحمل", "يذهب", "يأتي", "يرى", "يسمع", "يتكلم", "يقرأ", "يحفظ", "يعرف"],
                    "描述性形容词": ["جيد", "سيء", "كبير", "صغير", "طويل", "قصير", "جديد", "قديم", "جميل", "قبيح"],
                },
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
                    "الدعم": ["الدعم للقرار", "الدعم للفكرة", "الدعم للمشروع"],
                    "التركيز": ["التركيز على", "التركيز على الانتباه"],
                    "الاستكشاف": ["الاستكشاف للخيارات", "الاستكشاف للاحتمالات", "الاستكشاف للسوق"],
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
                    "الدعم": ["المساندة", "الدعم", "الشجاعة", "القوة"],
                    "التركيز": ["الالتزام", "التركيز", "الانخراط", "الملامح"],
                    "الاستكشاف": ["الاستكشاف", "البحث", "الدراسة", "الاكتشاف"],
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
                    "الدعم": ["الدعم", "مُدعم", "دعمي"],
                    "التركيز": ["التركيز", "مُركّز", "تركيزي"],
                    "الاستكشاف": ["الاستكشاف", "مُستكشف", "استكشافي"],
                },
                "word_pattern": r'[\u0600-\u06FF]{2,}',
            },
            "hi": {
                "simple_words": {"का", "की", "के", "को", "में", "से", "पर", "ने", "न",
                               "है", "हैं", "था", "थी", "थे", "होगा", "होगी", "होंगे",
                               "हो", "जा", "जाए", "जाएगा", "जाएगी", "जाएंगे", "कर",
                               "करता", "करती", "करते", "करना", "मैं", "तुम", "वह",
                               "वह", "हम", "आप", "वे", "मुझे", "तुम्हें", "उन्हें"},
                "vocabulary_groups": {
                    "高频口语词": ["अरे", "अरे", "हाँ", "नहीं", "अच्छा", "ठीक", "क्या", "कैसे", "क्यों", "कब"],
                    "程度副词": ["बहुत", "अत्यंत", "पूरी तरह", "काफी", "थोड़ा", "कम", "अधिक", "बिल्कुल"],
                    "连接词": ["और", "लेकिन", "या", "क्योंकि", "अगर", "जबकि", "तो", "फिर"],
                    "日常动词": ["होना", "करना", "जाना", "आना", "देखना", "सुनना", "बोलना", "पढ़ना", "लिखना", "जानना"],
                    "描述性形容词": ["अच्छा", "बुरा", "बड़ा", "छोटा", "लंबा", "छोटा", "नया", "पुराना", "सुंदर", "बुरा"],
                },
                "collocations": {
                    "महत्वपूर्ण": ["महत्वपूर्ण प्रभाव", "महत्वपूर्ण परिवर्तन", "महत्वपूर्ण अंतर", "महत्वपूर्ण भूमिका"],
                    "प्रभाव": ["प्रभाव डालना", "बड़ा प्रभाव", "सकारात्मक प्रभाव", "नकारात्मक प्रभाव"],
                    "पूरा": ["लक्ष्य पूरा करना", "सफलता पूरा करना", "परिणाम पूरा करना"],
                    "योगदान": ["योगदान देना", "बड़ा योगदान", "सकारात्मक योगदान", "विकास में योगदान"],
                    "निर्धारित": ["परिणाम निर्धारित करना", "कारण निर्धारित करना", "दिशा निर्धारित करना"],
                    "क्षमता": ["क्षमता होना", "क्षमता खोजना", "बड़ी क्षमता"],
                    "दृष्टिकोण": ["दृष्टिकोण से", "नया दृष्टिकोण", "अलग दृष्टिकोण", "वस्तुनिष्ठ दृष्टिकोण"],
                    "विश्लेषण": ["डेटा विश्लेषण करना", "स्थिति विश्लेषण करना", "समस्या विश्लेषण करना"],
                    "मूल्यांकन": ["प्रदर्शन मूल्यांकन करना", "विकल्प मूल्यांकन करना", "गुणवत्ता मूल्यांकन करना"],
                    "स्थापित": ["संबंध स्थापित करना", "नियम स्थापित करना", "प्रणाली स्थापित करना"],
                    "बनाए रखना": ["संतुलन बनाए रखना", "संबंध बनाए रखना", "गुणवत्ता बनाए रखना"],
                    "परिवर्तन": ["प्रक्रिया परिवर्तन करना", "उद्योग परिवर्तन करना", "व्यवसाय परिवर्तन करना"],
                    "प्रोत्साहन": ["विकास प्रोत्साहन देना", "उत्पाद प्रोत्साहन देना", "विकास प्रोत्साहन देना"],
                    "व्यवहार": ["लक्ष्य व्यवहार करना", "सपना व्यवहार करना", "क्षमता व्यवहार करना"],
                    "कम करना": ["लागत कम करना", "जोखिम कम करना", "अपशिष्ट कम करना"],
                    "प्रतिबिंबित": ["स्थिति प्रतिबिंबित करना", "परिवर्तन प्रतिबिंबित करना"],
                    "समर्थन": ["निर्णय को समर्थन देना", "समर्थन प्रदान करना", "विचार को समर्थन देना"],
                    "ध्यान केंद्रित": ["ध्यान केंद्रित करना", "ध्यान केंद्रित रखना"],
                    "अन्वेषण": ["विकल्प अन्वेषण करना", "संभावनाएं अन्वेषण करना", "बाजार अन्वेषण करना"],
                },
                "synonyms": {
                    "महत्वपूर्ण": ["मुख्य", "निजी", "अनिवार्य", "केंद्रीय"],
                    "प्रभाव": ["प्रभाव", "परिणाम", "प्रभाव", "प्रभाव"],
                    "पूरा": ["पूरा", "पूर्ण", "पूर्ण", "पूर्ण"],
                    "योगदान": ["योगदान", "योगदान", "योगदान", "योगदान"],
                    "निर्धारित": ["निर्धारित", "निर्धारित", "निर्धारित", "निर्धारित"],
                    "क्षमता": ["क्षमता", "क्षमता", "क्षमता", "क्षमता"],
                    "दृष्टिकोण": ["दृष्टिकोण", "दृष्टिकोण", "दृष्टिकोण", "दृष्टिकोण"],
                    "विश्लेषण": ["विश्लेषण", "विश्लेषण", "विश्लेषण", "विश्लेषण"],
                    "मूल्यांकन": ["मूल्यांकन", "मूल्यांकन", "मूल्यांकन", "मूल्यांकन"],
                    "स्थापित": ["स्थापित", "स्थापित", "स्थापित", "स्थापित"],
                    "बनाए रखना": ["बनाए रखना", "बनाए रखना", "बनाए रखना", "बनाए रखना"],
                    "परिवर्तन": ["परिवर्तन", "परिवर्तन", "परिवर्तन", "परिवर्तन"],
                    "प्रोत्साहन": ["प्रोत्साहन", "प्रोत्साहन", "प्रोत्साहन", "प्रोत्साहन"],
                    "व्यवहार": ["व्यवहार", "व्यवहार", "व्यवहार", "व्यवहार"],
                    "कम करना": ["कम करना", "कम करना", "कम करना", "कम करना"],
                    "प्रतिबिंबित": ["प्रतिबिंबित", "प्रतिबिंबित", "प्रतिबिंबित", "प्रतिबिंबित"],
                    "समर्थन": ["समर्थन", "समर्थन", "समर्थन", "समर्थन"],
                    "ध्यान केंद्रित": ["ध्यान केंद्रित", "ध्यान केंद्रित", "ध्यान केंद्रित", "ध्यान केंद्रित"],
                    "अन्वेषण": ["अन्वेषण", "अन्वेषण", "अन्वेषण", "अन्वेषण"],
                },
                "word_families": {
                    "महत्वपूर्ण": ["महत्वपूर्ण", "महत्व", "महत्वपूर्ण"],
                    "प्रभाव": ["प्रभाव", "प्रभाव", "प्रभाव"],
                    "पूरा": ["पूरा", "पूर्णता", "पूरा"],
                    "योगदान": ["योगदान", "योगदान", "योगदान"],
                    "निर्धारित": ["निर्धारित", "निर्धारण", "निर्धारित"],
                    "क्षमता": ["क्षमता", "क्षमता", "क्षमता"],
                    "दृष्टिकोण": ["दृष्टिकोण", "दृष्टिकोण", "दृष्टिकोण"],
                    "विश्लेषण": ["विश्लेषण", "विश्लेषण", "विश्लेषण"],
                    "मूल्यांकन": ["मूल्यांकन", "मूल्यांकन", "मूल्यांकन"],
                    "स्थापित": ["स्थापित", "स्थापना", "स्थापित"],
                    "बनाए रखना": ["बनाए रखना", "बनाए रखना", "बनाए रखना"],
                    "परिवर्तन": ["परिवर्तन", "परिवर्तन", "परिवर्तन"],
                    "प्रोत्साहन": ["प्रोत्साहन", "प्रोत्साहन", "प्रोत्साहन"],
                    "व्यवहार": ["व्यवहार", "व्यवहार", "व्यवहार"],
                    "कम करना": ["कम करना", "कमी", "कम"],
                    "प्रतिबिंबित": ["प्रतिबिंबित", "प्रतिबिंबित", "प्रतिबिंबित"],
                    "समर्थन": ["समर्थन", "समर्थन", "समर्थन"],
                    "ध्यान केंद्रित": ["ध्यान केंद्रित", "ध्यान", "ध्यान"],
                    "अन्वेषण": ["अन्वेषण", "अन्वेषण", "अन्वेषण"],
                },
                "word_pattern": r'[\u0900-\u097F]{2,}',
            },
            "el": {
                "simple_words": {"και", "στην", "στη", "τους", "των", "του", "της", "την", "σου",
                               "μου", "τους", "των", "στη", "στην", "στο", "στα", "στη", "στους"},
                "vocabulary_groups": {
                    "高频口语词": ["ε", "ει", "ναι", "χι", "μπράβο", "καλά", "όχι", "ναι", "πως", "πώς"],
                    "程度副词": ["πολύ", "λίγο", "πολύ", "ολόκληρο", "μεγάλο", "σχεδόν", "καθόλου", "αρκετά"],
                    "连接词": ["και", "αλλά", "ή", "γιατί", "αν", "όμως", "έτσι", "επίσης"],
                    "日常动词": ["είμαι", "έχω", "κάνω", "πηγαίνω", "έρχομαι", "βλέπω", "ακούω", "λέω", "γνωρίζω", "σκέφτομαι"],
                    "描述性形容词": ["καλός", "κακός", "μεγάλος", "μικρός", "μακρύς", "βραχύς", "νέος", "παλαιός", "όμορφος", "ασχέμος"],
                },
                "collocations": {
                    "σημαντικός": ["σημαντική επίδραση", "σημαντική αλλαγή", "σημαντική διαφορά", "σημαντικός ρόλος"],
                    "επίδραση": ["έχει επίδραση", "μεγάλη επίδραση", "θετική επίδραση", "αρνητική επίδραση"],
                    "εκπληρώ": ["εκπληρώ έναν στόχο", "εκπληρώ την επιτυχία", "εκπληρώ τα αποτελέσματα"],
                    "συνεισφέρ": ["συνεισφέρ σε", "μεγάλη συνεισφορά", "θετική συνεισφορά"],
                    "καθορίζω": ["καθορίζω το αποτέλεσμα", "καθορίζω την αιτία", "καθορίζω την κατεύθυνση"],
                    "δυνατότητα": ["έχει δυνατότητα", "ανακαλύπτει δυνατότητα", "μεγάλη δυνατότητα"],
                    "προσπέκτιβ": ["από προοπτική", "νέα προοπτική", "διαφορετική προοπτική"],
                    "αναλύω": ["αναλύω δεδομένα", "αναλύω την κατάσταση", "αναλύω το πρόβλημα"],
                    "εκτιμώ": ["εκτιμώ την απόδοση", "εκτιμώ τις επιλογές", "εκτιμώ την ποιότητα"],
                    "καθιστώ": ["καθιστώ σχέση", "καθιστώ κανόνα", "καθιστώ σύστημα"],
                    "διατηρώ": ["διατηρώ ισορροπία", "διατηρώ σχέση", "διατηρώ ποιότητα"],
                    "μεταμορφώνω": ["μεταμορφώνω την διαδικασία", "μεταμορφώνω την βιομηχανία"],
                    "προάγω": ["προάγω την ανάπτυξη", "προάγω το προϊόν", "προάγω την ανάπτυξη"],
                    "πραγματοποιώ": ["πραγματοποιώ έναν στόχο", "πραγματοποιώ ένα όνειρο"],
                    "μειώνω": ["μειώνω το κόστος", "μειώνω τον κίνδυνο", "μειώνω την απόρριψη"],
                    "αντιπροσωπεύω": ["αντιπροσωπεύω την κατάσταση", "αντιπροσωπεύω την αλλαγή"],
                    "υποστηρίζω": ["υποστηρίζω μια απόφαση", "υποστηρίζω την ιδέα", "υποστηρίζω το έργο"],
                    "ενώνω": ["ενώνω την προσοχή", "ενώνω τις προσπάθειες"],
                    "εξερευνάω": ["εξερευνάω τις επιλογές", "εξερευνάω τις δυνατότητες", "εξερευνάω την αγορά"],
                },
                "synonyms": {
                    "σημαντικός": ["κυρίως", "ισχυρός", "σπουδαίος", "αναγκαστικός"],
                    "επίδραση": ["αποτελεσματικότητα", "πίεση", "προσπέκτιβ", "αντίδραση"],
                    "εκπληρώ": ["πληρώ", "επιτυγχάνω", "να πετύχει", "να ολοκληρώ"],
                    "συνεισφέρ": ["προσθέτω", "συμμετέχω", "βοηθώ", "συνεργάζομαι"],
                    "καθορίζω": ["ορίζω", "προσδιορίζω", "επιλέγω", "διατάσσω"],
                    "δυνατότητα": ["δύναμη", "ισχύς", "ικανότητα", "επικίνδυνος"],
                    "προσπέκτιβ": ["οπτική γωνία", "προσπέκτιβ", "προοπτική", "κατεύθυνση"],
                    "αναλύω": ["διασκεδάζω", "εξετάζω", "μελετώνω", "εκτιμώ"],
                    "εκτιμώ": ["εκτιμώ", "αναλογίζομαι", "μετρο", "εξομολογώ"],
                    "καθιστώ": ["καθιστώ", "δημιουργώ", "οργανώνω", "επιβάλλω"],
                    "διατηρώ": ["διατηρώ", "φυλάσσω", "συντηρώ", "συνεχίζω"],
                    "μεταμορφώνω": ["μεταμορφώνω", "αντιστρέφω", "αλλάζω", "διαμορφώνω"],
                    "προάγω": ["προάγω", "προωθώ", "ταχύνω", "αναπτύσσω"],
                    "πραγματοποιώ": ["πραγματοποιώ", "εκτελώ", "υλοποιώ", "κατασκευάζω"],
                    "μειώνω": ["μειώνω", "καταργώ", "περιορίζω", "ελαχιστοποιώ"],
                    "αντιπροσωπεύω": ["προσδιορίζω", "προσδιορίζω", "δηλώνω", "προβολώ"],
                    "υποστηρίζω": ["υποστηρίζω", "βοηθώ", "συντηρώ", "προωθώ"],
                    "ενώνω": ["ενώνω", "συνάπτω", "συνενώνω", "συγκεντρώνω"],
                    "εξερευνάω": ["εξερευνάω", "συζητώ", "μελετώνω", "ανακαλύπτω"],
                },
                "word_families": {
                    "σημαντικός": ["σημαντικός", "σημασία", "σημαντικός"],
                    "επίδραση": ["επίδραση", "επιδραστικός", "επιδραστικός"],
                    "εκπληρώ": ["εκπληρώ", "εκπλήρωση", "εκπληρωμένος"],
                    "συνεισφέρ": ["συνεισφέρ", "συνεισφορά", "συνεισφέρων"],
                    "καθορίζω": ["καθορίζω", "καθορισμός", "καθορισμός"],
                    "δυνατότητα": ["δυνατότητα", "δυναμικός", "δυναμικός"],
                    "προσπέκτιβ": ["προσπέκτιβ", "προσπεκτικός", "προσπεκτικός"],
                    "αναλύω": ["αναλύω", "ανάλυση", "αναλυτικός"],
                    "εκτιμώ": ["εκτιμώ", "εκτίμηση", "εκτιμητικός"],
                    "καθιστώ": ["καθιστώ", "καθισμός", "καθισμός"],
                    "διατηρώ": ["διατηρώ", "διατήρηση", "διατηρημένος"],
                    "μεταμορφώνω": ["μεταμορφώνω", "μεταμόρφωση", "μεταμορφωτικός"],
                    "προάγω": ["προάγω", "προώθηση", "προωθητικός"],
                    "πραγματοποιώ": ["πραγματοποιώ", "πραγματοποίηση", "πραγματοποιημένος"],
                    "μειώνω": ["μειώνω", "μείωση", "μειωτικός"],
                    "αντιπροσωπεύω": ["αντιπροσωπεύω", "αντιπροσωπευτικό", "αντιπροσωπευτικός"],
                    "υποστηρίζω": ["υποστηρίζω", "υπόstütξη", "υποστηρικτικός"],
                    "ενώνω": ["ενώνω", "ένωση", "ενωτικός"],
                    "εξερευνάω": ["εξερευνάω", "έρευνα", "ερευνητικός"],
                },
                "word_pattern": r'\b[αβγδεζηθικλμνξοπρστυφχψωΑΒΓΔΕΖΗΘΙΚΛΜΝΞΟΠΡΣΤΥΦΧΨΩ]{6,}\b',
            },
            "tr": {
                "simple_words": {"ve", "bir", "i", "de", "ki", "bu", "şu", "o", "ben", "sen",
                               "o", "biz", "siz", "onlar", "m", "n", "n", "n", "n",
                               "dir", "dir", "dir", "dir", "dir", "dir", "dir", "dir", "dir", "dir"},
                "vocabulary_groups": {
                    "高频口语词": ["eh", "ha", "ya", "ama", "yani", "peki", "tamam", "hayır", "evet", "kesin"],
                    "程度副词": ["çok", "oldukça", "gerçekten", "tamamen", "mutlak", "tamamen", "nispi", "biraz"],
                    "连接词": ["ve", "ama", "yani", "çünkü", "eğer", "halbuki", "ancak", "bu yüzden", "ayrıca", "da"],
                    "日常动词": ["olmak", "var", "gitmek", "gelmek", "görmek", "duymak", "konuşmak", "okumak", "yazmak", "bilmek"],
                    "描述性形容词": ["iyi", "kötü", "büyük", "küçük", "uzun", "kısa", "yeni", "eski", "güzel", "çirkin"],
                },
                "collocations": {
                    "önemli": ["önemli etkisi", "önemli değişiklik", "önemli önem",
                                   "önemli fark", "önemli rol", "önemli miktar"],
                    "etki": ["etki etmek", "büyük etki", "olumlu etki",
                                 "negatif etki", "önemli etki", "hiçbir etki"],
                    "başarmak": ["bir hedefi başarmak", "başarıyı başarmak", "bir hedefi başarmak",
                                   "bir seviyeye ulaşmak", "bir sonuç almak", "bir rekor kırmak"],
                    "katkıda bulunmak": ["katkıda bulunmak", "önemli katkıda bulunmak",
                                  "gelişime katkıda bulunmak", "iyileştirmeye katkıda bulunmak"],
                    "belirlemek": ["sonucu belirlemek", "nedeni belirlemek", "fiyatı belirlemek",
                                 "hızı belirlemek", "yönü belirlemek", "değeri belirlemek"],
                    "potansiyel": ["potansiyeli var", "potansiyeli tanımak", "potansiyeli kullanmak",
                                  "maksimum potansiyel", "yüksek potansiyel", "uzun vadeli potansiyel"],
                    "perspektif": ["bir perspektiften", "başka perspektif", "yeni perspektif",
                                    "kendi perspektifi", "eleştirel perspektif"],
                    "analiz etmek": ["verileri analiz etmek", "durumu analiz etmek", "sorunu analiz etmek",
                                   "sonucu analiz etmek", "trendi analiz etmek", "piyasa analiz etmek"],
                    "değerlendirmek": ["performansı değerlendirmek", "seçenekleri değerlendirmek", "kaliteyi değerlendirmek",
                                   "etkinliği değerlendirmek", "etkileri değerlendirmek"],
                    "kurmak": ["bir ilişki kurmak", "bir kural kurmak", "bir sistem kurmak",
                                   "bir bağlantı kurmak", "bir itibar kurmak"],
                    "sürdürmek": ["dengesi sürdürmek", "ilişki sürdürmek", "kalite sürdürmek",
                                  "standardı sürdürmek", "fokusu sürdürmek", "integriteyi sürdürmek"],
                    "dönüştürmek": ["bir şeye dönüştürmek", "bir süreç dönüştürmek", "bir endüstri dönüştürmek",
                                       "bir iş dönüştürmek", "bir teknoloji dönüştürmek"],
                    "teşvik etmek": ["gelişimi teşvik etmek", "ürünü teşvik etmek", "büyümeyi teşvik etmek",
                                 "anlayışı teşvik etmek", "işbirliğini teşvik etmek"],
                    "gerçekleştirmek": ["bir hedefi gerçekleştirmek", "bir hayali gerçekleştirmek", "potansiyeli gerçekleştirmek",
                                     "bir hatayı gerçekleştirmek", "bir fırsatı gerçekleştirmek"],
                    "azaltmak": ["maliyetleri azaltmak", "riski azaltmak", "atıkları azaltmak",
                                   "süreyi azaltmak", "etkileri azaltmak"],
                    "yansıtmak": ["bir şeye yansıtmak", "durumu yansıtmak", "değişimi yansıtmak",
                                     "trendi yansıtmak", "davranışı yansıtmak"],
                    "desteklemek": ["bir karar desteklemek", "destek sağlamak", "bir fikir desteklemek",
                                     "bir proje desteklemek", "gelişimi desteklemek"],
                    "etki": ["etki etmek", "önemli etki", "olumlu etki",
                                   "negatif etki", "uzun vadeli etki"],
                    "odaklanmak": ["bir şeye odaklanmak", "dikkati odaklanmak",
                                      "çabaları odaklanmak", "kaynakları odaklanmak"],
                    "keşfetmek": ["seçenekleri keşfetmek", "olasıılıkları keşfetmek", "piyasayı keşfetmek",
                                     "fırsatları keşfetmek", "bir yaklaşım keşfetmek"],
                },
                "synonyms": {
                    "önemli": ["notable", "temel", "substantial", "considerable", "anahtar"],
                    "etki": ["etki", "etki", "etki", "belirleme", "kontrol"],
                    "başarmak": ["başarmak", "al", "ulaşmak", "gerçekleştirmek", "yapmak"],
                    "katkıda bulunmak": ["katkıda bulunmak", "katılmak", "yardımcı olmak", "desteklemek", "işbirliği"],
                    "belirlemek": ["belirlemek", "seçmek", "etki", "tanımlamak", "kurmak"],
                    "potansiyel": ["potansiyel", "kapasite", "yetenek", "potansiyel", "fırsat"],
                    "perspektif": ["perspektif", "görünüm", "yaklaşım", "açısı", "yönelim"],
                    "analiz etmek": ["analiz etmek", "incelemek", "değerlendirmek", "dene", "inspect"],
                    "değerlendirmek": ["değerlendirmek", "derecelendirmek", "ölçmek", "tahmin etmek", "doğrulamak"],
                    "kurmak": ["kurmak", "oluşturmak", "organize etmek", "temel oluşturmak", "geliştirmek"],
                    "sürdürmek": ["sürdürmek", "korumak", "desteklemek", "devam etmek", "korumak"],
                    "dönüştürmek": ["dönüştürmek", "değiştirmek", "değiştir", "yeniden organize", "uyarlamak"],
                    "teşvik etmek": ["teşvik etmek", "desteklemek", "hızlandırmak", "geliştirmek", "iyileştirmek"],
                    "gerçekleştirmek": ["gerçekleştirmek", "başarmak", "tamamlamak", "anlamak", "tanımak"],
                    "azaltmak": ["azaltmak", "düşürmek", "sınırlandırmak", "en aza indirmek", "azaltmak"],
                    "yansıtmak": ["yansıtmak", "göstermek", "göstermek", "gözlemlemek", "yansıtmak"],
                    "desteklemek": ["desteklemek", "yardımcı olmak", "desteklemek", "korumak", "teşvik etmek"],
                    "etki": ["etki", "etki", "sonuç", "değişiklik", "dönüşüm"],
                    "odaklanmak": ["odaklanmak", "toplanmak", "yönlendirmek", "önceliklendirmek", "merkez"],
                    "keşfetmek": ["keşfetmek", "araştırmak", "incelemek", "araştırmak", "bulmak"],
                },
                "word_families": {
                    "önemli": ["önemli", "önem", "önemle", "önemli"],
                    "etki": ["etki", "etkili", "etkili"],
                    "başarmak": ["başarmak", "başarı", "başarılabilir", "başarı"],
                    "katkıda bulunmak": ["katkıda bulunmak", "katkı", "katkıda bulunan", "katkıda bulunan"],
                    "belirlemek": ["belirlemek", "belirleme", "belirlenmiş", "belirleyen"],
                    "potansiyel": ["potansiyel", "potansiyel olarak", "potansiyel"],
                    "perspektif": ["perspektif", "perspektifsel", "perspektifsel"],
                    "analiz etmek": ["analiz etmek", "analiz", "analitik", "analist"],
                    "değerlendirmek": ["değerlendirmek", "değerlendirme", "değerlendiren", "değerlendiren"],
                    "kurmak": ["kurmak", "kurulum", "kurulmuş"],
                    "sürdürmek": ["sürdürmek", "sürdürme", "sürdürülebilir", "sürdürülen"],
                    "dönüştürmek": ["dönüştürmek", "dönüşüm", "dönüştüren", "dönüştürücü"],
                    "teşvik etmek": ["teşvik etmek", "teşvik", "teşvik eden", "teşvikci"],
                    "gerçekleştirmek": ["gerçekleştirmek", "gerçekleştirme", "gerçekleştirilebilir", "gerçekleştirilmiş"],
                    "azaltmak": ["azaltmak", "azaltma", "azaltan", "azaltılmış"],
                    "yansıtmak": ["yansıtmak", "yansıma", "yansıtan", "yansıtıcı"],
                    "desteklemek": ["desteklemek", "destek", "destekleyen", "destekleyen"],
                    "etki": ["etki", "etkili", "etkili"],
                    "odaklanmak": ["odaklanmak", "odaklanma", "odaklanmış", "odaklayan"],
                    "keşfetmek": ["keşfetmek", "keşif", "keşifçi", "keşfeden"],
                },
                "word_pattern": r'\b[a-zA-ZçğşıöüÇĞŞİÖÜ]{6,}\b',
            },
            "vi": {
                "simple_words": {"à", "ạ", "ơi", "này", "thì", "cũng", "như", "vậy", "chà",
                               "chào", "tạm", "biệt", "cảm", "ơn", "làm", "ơn", "xin", "lỗi",
                               "ah", "oh", "ừ", "và", "nhưng", "hoặc", "vì", "nếu", "mặc", "dù"},
                "vocabulary_groups": {
                    "高频口语词": ["ừ", "à", "ạ", "ơi", "này", "thì", "cũng", "như", "vậy", "chà"],
                    "程度副词": ["rất", "cực", "kỳ", "đặc", "biệt", "hơi", "chút", "ít", "nhiều", "phần"],
                    "连接词": ["và", "nhưng", "hoặc", "vì", "nếu", "mặc dù", "để", "khi", "trước", "sau"],
                    "日常动词": ["là", "có", "làm", "đi", "đến", "nhìn", "nghe", "nói", "biết", "nhớ"],
                    "描述性形容词": ["tốt", "xấu", "lớn", "nhỏ", "dài", "ngắn", "mới", "cũ", "đẹp", "xấu"],
                },
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
                    "khám phá": ["khám phá lựa chọn", "khám phá khả năng", "khám phá thị trường"],
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
                    "khám phá": ["phát hiện", "thực hiện", "thu thập", "nhận biết"],
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
                    "khám phá": ["khám phá", "sự khám phá", "khám phá"],
                },
                "word_pattern": r'[a-zA-ZàáảãạăắằẳẵặâấầẩẫậèéẻẽẹêếềểễệìíỉĩịòóỏõọôốồổỗộơớờởỡợùúủũụưứừửữựỳýỷỹỵđÀÁẢÃẠĂẮẰẲẴẶÂẤẦẨẪẬÈÉẺẼẸÊẾỀỂỄỆÌÍỈĨỊÒÓỎÕỌÔỐỒỔỖỘƠỚỜỞỠỢÙÚỦŨỤƯỨỪỬỮỰỲÝỶỸỴĐ]{2,}',
            },
            "th": {
                "simple_words": {"เออ", "อืม", "อ่ะ", "นะ", "นี่", "แล้ว", "ก็", "เหมือน", "อย่าง", "นั้น",
                               "ช่าง", "สวัสดี", "ลาก่อน", "ขอบคุณ", "กรุณา", "ขอโทษ", "อ้า", "โอ"},
                "vocabulary_groups": {
                    "高频口语词": ["เออ", "อืม", "อ่ะ", "นะ", "นี่", "แล้ว", "ก็", "เหมือน", "อย่างนั้น", "ช่าง"],
                    "程度副词": ["มาก", "สวย", "จริงๆ", "ก็", "เยอะ", "น้อย", "พอ", "สุด"],
                    "连接词": ["และ", "แต่", "หรือ", "เพราะ", "ถ้า", "แม้ว่า", "เพื่อ", "เมื่อ"],
                    "日常动词": ["เป็น", "มี", "ทำ", "ไป", "มา", "ดู", "ฟัง", "พูด", "รู้", "คิด"],
                    "描述性形容词": ["ดี", "ร้าย", "ใหญ่", "เล็ก", "ยาว", "สั้น", "ใหม่", "เก่า", "สวย", "ไม่สวย"],
                },
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
                    "สำรวจ": ["สำรวจทางเลือก", "สำรวจความเป็นไปได้", "สำรวจตลาด"],
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
                    "สำรวจ": ["สำรวจ", "สำรวจ", "สำรวจ", "สำรวจ"],
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
                    "สำรวจ": ["สำรวจ", "สำรวจ", "สำรวจ"],
                },
                "word_pattern": r'[\u0E00-\u0E7F]{2,}',
            },
            "id": {
                "simple_words": {"dan", "di", "dengan", "dan", "atau", "tetapi", "karena", "jika", "sehingga",
                               "saya", "kamu", "dia", "kami", "kita", "mereka", "ini", "itu", "apa", "dimana"},
                "vocabulary_groups": {
                    "高频口语词": ["eh", "yah", "nah", "ya", "deh", "dong", "kok", "lo", "kayak", "gak"],
                    "程度副词": ["sangat", "cukup", "sungguhan", "seluruhnya", "relatif", "sedikit", "banyak", "cuma"],
                    "连接词": ["dan", "tetapi", "atau", "karena", "jika", "meskipun", "supaya", "ketika"],
                    "日常动词": ["ada", "membuat", "pergi", "datang", "melihat", "mendengar", "berbicara", "membaca", "menulis", "mengetahui"],
                    "描述性形容词": ["baik", "buruk", "besar", "kecil", "panjang", "pendek", "baru", "lama", "cantik", "jelek"],
                },
                "collocations": {
                    "penting": ["dampak penting", "perubahan penting", "perbedaan penting", "peran penting"],
                    "dampak": ["mempunyai dampak", "dampak besar", "dampak positif", "dampak negatif"],
                    "mencapai": ["mencapai tujuan", "mencapai kesuksesan", "mencapai hasil"],
                    "berkontribusi": ["berkontribusi pada", "kontribusi besar", "kontribusi positif"],
                    "menentukan": ["menentukan hasil", "menentukan alasan", "menentukan arah"],
                    "potensi": ["memiliki potensi", "mengidentifikasi potensi", "potensi besar"],
                    "perspektif": ["dari perspektif", "perspektif baru", "perspektif berbeda"],
                    "menganalisis": ["menganalisis data", "menganalisis situasi", "menganalisis masalah"],
                    "mengevaluasi": ["mengevaluasi kinerja", "mengevaluasi pilihan", "mengevaluasi kualitas"],
                    "membangun": ["membangun hubungan", "membangun aturan", "membangun sistem"],
                    "mempertahankan": ["mempertahankan keseimbangan", "mempertahankan hubungan", "mempertahankan kualitas"],
                    "mengubah": ["mengubah proses", "mengubah industri", "mengubah bisnis"],
                    "mempromosikan": ["mempromosikan pengembangan", "mempromosikan produk", "mempromosikan pertumbuhan"],
                    "mewujudkan": ["mewujudkan tujuan", "mewujudkan impian", "mewujudkan potensi"],
                    "mengurangi": ["mengurangi biaya", "mengurangi risiko", "mengurangi limbah"],
                    "mencerminkan": ["mencerminkan situasi", "mencerminkan perubahan"],
                    "mendukung": ["mendukung keputusan", "memberikan dukungan", "mendukung ide"],
                    "fokus": ["fokus pada", "fokus perhatian"],
                    "menjelajah": ["menjelajah pilihan", "menjelajah kemungkinan", "menjelajah pasar"],
                },
                "synonyms": {
                    "penting": ["utama", "kritis", "fundamental", "esensial"],
                    "dampak": ["akibat", "efek", "pengaruh", "konsekuensi"],
                    "mencapai": ["meraih", "mencapai", "menghasilkan", "mewujudkan"],
                    "berkontribusi": ["membantu", "berpartisipasi", "memberikan", "menyumbangkan"],
                    "menentukan": ["memutuskan", "menentukan", "memilih", "menetapkan"],
                    "potensi": ["kemampuan", "kapasitas", "peluang", "kemungkinan"],
                    "perspektif": ["sudut pandang", "pandangan", "sikap", "gaya"],
                    "menganalisis": ["menelaah", "meninjau", "mengkaji", "meneliti"],
                    "mengevaluasi": ["menilai", "mengukur", "menaksir", "memeriksa"],
                    "membangun": ["menciptakan", "membentuk", "mendirikan", "mengembangkan"],
                    "mempertahankan": ["menjaga", "melestarikan", "berlanjut", "menetapkan"],
                    "mengubah": ["mengubah", "menukar", "memodifikasi", "mengadaptasi"],
                    "mempromosikan": ["mendorong", "meningkatkan", "memfasilitasi", "mengembangkan"],
                    "mewujudkan": ["menjalankan", "melaksanakan", "membuat", "menemukan"],
                    "mengurangi": ["mengurangi", "menurunkan", "membatasi", "meminimalkan"],
                    "mencerminkan": ["menunjukkan", "mewakili", "menyimbolkan", "mengecilkan"],
                    "mendukung": ["membantu", "memfasilitasi", "melindungi", "menyokong"],
                    "fokus": ["terpusat", "terfokus", "prioritaskan", "pusatkan"],
                    "menjelajah": ["menelusuri", "menemukan", "mencari", "mengungkap"],
                },
                "word_families": {
                    "penting": ["penting", "pentingnya", "penting"],
                    "dampak": ["dampak", "dampak", "dampak"],
                    "mencapai": ["mencapai", "capai", "mencapai"],
                    "berkontribusi": ["berkontribusi", "kontribusi", "berkontribusi"],
                    "menentukan": ["menentukan", "determinasi", "menentukan"],
                    "potensi": ["potensi", "potensi", "potensi"],
                    "perspektif": ["perspektif", "perspektif", "perspektif"],
                    "menganalisis": ["menganalisis", "analisis", "menganalisis"],
                    "mengevaluasi": ["mengevaluasi", "evaluasi", "mengevaluasi"],
                    "membangun": ["membangun", "bangunan", "membangun"],
                    "mempertahankan": ["mempertahankan", "pertahanan", "mempertahankan"],
                    "mengubah": ["mengubah", "perubahan", "mengubah"],
                    "mempromosikan": ["mempromosikan", "promosi", "mempromosikan"],
                    "mewujudkan": ["mewujudkan", "wujud", "mewujudkan"],
                    "mengurangi": ["mengurangi", "pengurangan", "mengurangi"],
                    "mencerminkan": ["mencerminkan", "cerminan", "mencerminkan"],
                    "mendukung": ["mendukung", "dukungan", "mendukung"],
                    "fokus": ["fokus", "fokus", "fokus"],
                    "menjelajah": ["menjelajah", "jelajah", "menjelajah"],
                },
                "word_pattern": r'\b[a-zA-Z]{4,}\b',
            },
            "ms": {
                "simple_words": {"dan", "di", "dengan", "dan", "atau", "tetapi", "kerana", "jika", "supaya",
                               "saya", "kamu", "dia", "kami", "kita", "mereka", "ini", "itu", "apa", "di mana"},
                "vocabulary_groups": {
                    "高频口语词": ["eh", "yah", "nah", "ya", "la", "lah", "mah", "lo", "cam", "tak"],
                    "程度副词": ["sangat", "cukup", "benar-benar", "sepenuhnya", "relatif", "sedikit", "banyak", "hanya"],
                    "连接词": ["dan", "tetapi", "atau", "kerana", "jika", "walaupun", "supaya", "apabila"],
                    "日常动词": ["ada", "membuat", "pergi", "datang", "melihat", "mendengar", "berbicara", "membaca", "menulis", "mengetahui"],
                    "描述性形容词": ["baik", "buruk", "besar", "kecil", "panjang", "pendek", "baru", "lama", "cantik", "jelek"],
                },
                "collocations": {
                    "penting": ["impak penting", "perubahan penting", "perbezaan penting", "peranan penting"],
                    "impak": ["mempunyai impak", "impak besar", "impak positif", "impak negatif"],
                    "mencapai": ["mencapai matlamat", "mencapai kejayaan", "mencapai hasil"],
                    "berkumbang": ["berkumbang kepada", "sumbangan besar", "sumbangan positif"],
                    "menentukan": ["menentukan hasil", "menentukan sebab", "menentukan arah"],
                    "potensi": ["mempunyai potensi", "mengenalpasti potensi", "potensi besar"],
                    "perspektif": ["dari perspektif", "perspektif baru", "perspektif berbeza"],
                    "menganalisis": ["menganalisis data", "menganalisis situasi", "menganalisis masalah"],
                    "mengevaluasi": ["mengevaluasi prestasi", "mengevaluasi pilihan", "mengevaluasi kualiti"],
                    "membina": ["membina hubungan", "membina peraturan", "membina sistem"],
                    "mengekalkan": ["mengekalkan keseimbangan", "mengekalkan hubungan", "mengekalkan kualiti"],
                    "menukar": ["menukar proses", "menukar industri", "menukar perniagaan"],
                    "mempromosikan": ["mempromosikan pembangunan", "mempromosikan produk", "mempromosikan pertumbuhan"],
                    "mewujudkan": ["mewujudkan matlamat", "mewujudkan impian", "mewujudkan potensi"],
                    "mengurangkan": ["mengurangkan kos", "mengurangkan risiko", "mengurangkan sisa"],
                    "mencerminkan": ["mencerminkan situasi", "mencerminkan perubahan"],
                    "menyokong": ["menyokong keputusan", "memberi sokongan", "menyokong idea"],
                    "fokus": ["fokus pada", "fokus perhatian"],
                    "meneroka": ["meneroka pilihan", "meneroka kemungkinan", "meneroka pasaran"],
                },
                "synonyms": {
                    "penting": ["utama", "kritikal", "asas", "esensial"],
                    "impak": ["kesan", "akibat", "pengaruh", "konsekuensi"],
                    "mencapai": ["mencapai", "meraih", "mewujudkan", "menghasilkan"],
                    "berkumbang": ["menyumbang", "membantu", "berpartisipasi", "memberi"],
                    "menentukan": ["menentukan", "memutuskan", "memilih", "menetapkan"],
                    "potensi": ["kemampuan", "keupayaan", "peluang", "kemungkinan"],
                    "perspektif": ["sudut pandang", "pandangan", "sikap", "gaya"],
                    "menganalisis": ["meneliti", "meninjau", "mengkaji", "menelaah"],
                    "mengevaluasi": ["menilai", "mengukur", "menaksir", "memeriksa"],
                    "membina": ["membina", "mencipta", "mendirikan", "mengembangkan"],
                    "mengekalkan": ["mengekalkan", "menjaga", "melestarikan", "berlanjut"],
                    "menukar": ["menukar", "mengubah", "memodifikasi", "mengadaptasi"],
                    "mempromosikan": ["mempromosikan", "mendorong", "meningkatkan", "mengembangkan"],
                    "mewujudkan": ["mewujudkan", "melaksanakan", "menjalankan", "membuat"],
                    "mengurangkan": ["mengurangkan", "menurunkan", "membatasi", "meminimumkan"],
                    "mencerminkan": ["mencerminkan", "menunjukkan", "mewakili", "menyimbolkan"],
                    "menyokong": ["menyokong", "membantu", "melindungi", "mempengaruhi"],
                    "fokus": ["fokus", "terpusat", "prioritaskan", "pusatkan"],
                    "meneroka": ["meneroka", "menjelajah", "menemukan", "mencari"],
                },
                "word_families": {
                    "penting": ["penting", "keutamaan", "penting"],
                    "impak": ["impak", "impak", "impak"],
                    "mencapai": ["mencapai", "capai", "mencapai"],
                    "berkumbang": ["berkumbang", "sumbangan", "berkumbang"],
                    "menentukan": ["menentukan", "penentuan", "menentukan"],
                    "potensi": ["potensi", "potensi", "potensi"],
                    "perspektif": ["perspektif", "perspektif", "perspektif"],
                    "menganalisis": ["menganalisis", "analisis", "menganalisis"],
                    "mengevaluasi": ["mengevaluasi", "penilaian", "mengevaluasi"],
                    "membina": ["membina", "pembinaan", "membina"],
                    "mengekalkan": ["mengekalkan", "pemeliharaan", "mengekalkan"],
                    "menukar": ["menukar", "perubahan", "menukar"],
                    "mempromosikan": ["mempromosikan", "promosi", "mempromosikan"],
                    "mewujudkan": ["mewujudkan", "wujud", "mewujudkan"],
                    "mengurangkan": ["mengurangkan", "pengurangan", "mengurangkan"],
                    "mencerminkan": ["mencerminkan", "pencerminan", "mencerminkan"],
                    "menyokong": ["menyokong", "sokongan", "menyokong"],
                    "fokus": ["fokus", "fokus", "fokus"],
                    "meneroka": ["meneroka", "penyelidikan", "meneroka"],
                },
                "word_pattern": r'\b[a-zA-Z]{4,}\b',
            },
            "tl": {
                "simple_words": {"at", "ang", "ng", "sa", "ay", "na", "pero", "kung", "kapag", "dahil",
                               "ako", "ikaw", "siya", "kami", "tayo", "sila", "ito", "iyon", "ano", "saan"},
                "vocabulary_groups": {
                    "高频口语词": ["eh", "ay", "o", "naman", "lang", "ba", "kasi", "daw", "raw", "yun"],
                    "程度副词": ["napaka", "sobra", "talaga", "ganun", "medyo", "kaunti", "marami", "lamang"],
                    "连接词": ["at", "pero", "o", "dahil", "kung", "bagaman", "upang", "kapag"],
                    "日常动词": ["magkaroon", "gawin", "punta", "dating", "makita", "marinig", "mag-usap", "basahin", "isulat", "malaman"],
                    "描述性形容词": ["maganda", "masama", "malaki", "maliit", "mahaba", "maikli", "bago", "lumang", "maganda", "panget"],
                },
                "collocations": {
                    "mahalaga": ["epekto mahalaga", "pagbabago mahalaga", "pagkakaiba mahalaga", "papel mahalaga"],
                    "epekto": ["may epekto", "malaking epekto", "positibong epekto", "negatibong epekto"],
                    "makamit": ["makamit ang layunin", "makamit ang tagumpay", "makamit ang resulta"],
                    "mag-ambag": ["mag-ambag sa", "malaking ambag", "positibong ambag"],
                    "tukuyin": ["tukuyin ang resulta", "tukuyin ang dahilan", "tukuyin ang direksyon"],
                    "potensyal": ["may potensyal", "makilala ang potensyal", "malaking potensyal"],
                    "pananaw": ["mula sa pananaw", "bagong pananaw", "ibang pananaw"],
                    "pag-aralan": ["pag-aralan ang data", "pag-aralan ang sitwasyon", "pag-aralan ang problema"],
                    "masuri": ["masuri ang pagganap", "masuri ang mga opsyon", "masuri ang kalidad"],
                    "itatag": ["itatag ang relasyon", "itatag ang patakaran", "itatag ang sistema"],
                    "panatilihin": ["panatilihin ang balanse", "panatilihin ang relasyon", "panatilihin ang kalidad"],
                    "baguhin": ["baguhin ang proseso", "baguhin ang industriya", "baguhin ang negosyo"],
                    "isulong": ["isulong ang pag-unlad", "isulong ang produkto", "isulong ang paglago"],
                    "maisakatuparan": ["maisakatuparan ang layunin", "maisakatuparan ang pangarap", "maisakatuparan ang potensyal"],
                    "bawasan": ["bawasan ang gastos", "bawasan ang panganib", "bawasan ang basura"],
                    "masalamin": ["masalamin ang sitwasyon", "masalamin ang pagbabago"],
                    "suportahan": ["suportahan ang desisyon", "magbigay ng suporta", "suportahan ang ideya"],
                    "tumutok": ["tumutok sa", "tumutok sa atensyon"],
                    "galugarin": ["galugarin ang mga opsyon", "galugarin ang mga posibilidad", "galugarin ang merkado"],
                },
                "synonyms": {
                    "mahalaga": ["pangunahin", "kritikal", "fundamental", "esensyal"],
                    "epekto": ["resulta", "impluwensya", "pagbabago", "konsekuwensya"],
                    "makamit": ["kamtan", "makamit", "maisakatuparan", "makuha"],
                    "mag-ambag": ["tumulong", "magbigay", "makilahok", "magkontribyu"],
                    "tukuyin": ["matukoy", "piliin", "pasya", "itatag"],
                    "potensyal": ["kakayahan", "potensyal", "pagkakataon", "posibilidad"],
                    "pananaw": ["pananaw", "opinyon", "tingin", "sulok"],
                    "pag-aralan": ["pag-aralan", "siyasatin", "suriin", "mag-imbestiga"],
                    "masuri": ["masuri", "timbangin", "hulaan", "suriin"],
                    "itatag": ["itatag", "lumikha", "organisahin", "itataguyod"],
                    "panatilihin": ["panatilihin", "ingatan", "patuloy", "mapanatili"],
                    "baguhin": ["baguhin", "palitan", "iba", "ibalik"],
                    "isulong": ["isulong", "pagbutihin", "bilisin", "pag-unlad"],
                    "maisakatuparan": ["maisakatuparan", "gawin", "makumpleto", "maisakatuparan"],
                    "bawasan": ["bawasan", "ibaba", "limitahan", "paliitin"],
                    "masalamin": ["masalamin", "ipakita", "ipahiwatig", "salamin"],
                    "suportahan": ["suportahan", "tumulong", "panigan", "palakasin"],
                    "tumutok": ["tumutok", "mag-ipon", "pangunahan", "tuunan"],
                    "galugarin": ["galugarin", "mag-imbestiga", "hanapin", "makita"],
                },
                "word_families": {
                    "mahalaga": ["mahalaga", "kahalagahan", "mahalaga"],
                    "epekto": ["epekto", "epekto", "epekto"],
                    "makamit": ["makamit", "kamtan", "makamit"],
                    "mag-ambag": ["mag-ambag", "ambag", "mag-ambag"],
                    "tukuyin": ["tukuyin", "pagtukoy", "tukuyin"],
                    "potensyal": ["potensyal", "potensyal", "potensyal"],
                    "pananaw": ["pananaw", "pananaw", "pananaw"],
                    "pag-aralan": ["pag-aralan", "pag-aaral", "pag-aralan"],
                    "masuri": ["masuri", "pagsusuri", "masuri"],
                    "itatag": ["itatag", "pagtatatag", "itatag"],
                    "panatilihin": ["panatilihin", "pagpapanatili", "panatilihin"],
                    "baguhin": ["baguhin", "pagbabago", "baguhin"],
                    "isulong": ["isulong", "pagsulong", "isulong"],
                    "maisakatuparan": ["maisakatuparan", "pagsasakatuparan", "maisakatuparan"],
                    "bawasan": ["bawasan", "pagbabawas", "bawasan"],
                    "masalamin": ["masalamin", "pagsasalamin", "masalamin"],
                    "suportahan": ["suportahan", "suporta", "suportahan"],
                    "tumutok": ["tumutok", "pagtutok", "tumutok"],
                    "galugarin": ["galugarin", "paggalugad", "galugarin"],
                },
                "word_pattern": r'\b[a-zA-Z]{4,}\b',
            },
        }
    
    def analyze_content(self, subtitles: List[Dict[str, Any]], language: str = "en") -> Dict[str, Any]:
        """深度分析视频内容，提取真正有学习价值的语言点
        
        Args:
            subtitles: 字幕片段列表
            language: 视频语言代码（en/de/fr/es/zh/ja/ko/ru等）
            
        Returns:
            分析结果字典
        """
        all_text = " ".join([s.get("text", "").lower() for s in subtitles if s.get("text")])
        
        expression_knowledge = self._find_expression_knowledge(subtitles)
        phrase_insights = self._find_phrase_insights(subtitles)
        
        exclude_words = set()
        for expr in expression_knowledge:
            exclude_words.add(expr["expression"].lower())
        for phrase in phrase_insights:
            for word in phrase["phrase"].split():
                exclude_words.add(word.lower())
        
        analysis = {
            "vocabulary_insights": self._find_vocabulary_insights(subtitles, exclude_words, language),
            "phrase_insights": phrase_insights,
            "sentence_insights": self._find_sentence_insights(subtitles),
            "expression_knowledge": expression_knowledge,
            "collocation_insights": self._find_collocation_insights(subtitles, language),
        }
        
        return analysis
    
    def _find_vocabulary_insights(self, subtitles: List[Dict[str, Any]], exclude_words: Optional[set] = None, language: str = "en") -> List[Dict[str, Any]]:
        """发现有深度学习价值的词汇
        
        Args:
            subtitles: 字幕片段列表
            exclude_words: 需要排除的词汇集合
            language: 视频语言代码
            
        Returns:
            词汇洞察列表
        """
        insights = []
        seen = set()
        exclude = exclude_words or set()
        
        lang_data = self._lang_data.get(language, self._lang_data["en"])
        simple_words = lang_data.get("simple_words", set())
        word_pattern = lang_data.get("word_pattern", r'\b[a-zA-Z]{6,}\b')
        
        for s in subtitles:
            text = s.get("text", "")
            translated = s.get("translated_text", "")
            
            for word in re.findall(word_pattern, text.lower()):
                if word not in simple_words and word not in seen and word not in exclude:
                    seen.add(word)
                    
                    word_info = self._get_word_info(word, text, translated, language)
                    if word_info:
                        insights.append(word_info)
        
        return sorted(insights, key=lambda x: x.get("value_score", 0), reverse=True)[:8]
    
    def _get_word_info(self, word: str, text: str, translated: str, language: str = "en") -> Optional[Dict[str, Any]]:
        """获取单词的深度信息
        
        Args:
            word: 单词
            text: 原文句子
            translated: 翻译句子
            language: 语言代码
            
        Returns:
            单词信息字典
        """
        info = {}
        
        lang_data = self._lang_data.get(language, self._lang_data["en"])
        collocations = lang_data.get("collocations", {})
        synonyms = lang_data.get("synonyms", {})
        word_families = lang_data.get("word_families", {})
        
        if word in collocations:
            info["word"] = word
            info["example"] = text
            info["translated"] = translated
            info["collocations"] = collocations[word]
            info["synonyms"] = synonyms.get(word, [])
            info["word_family"] = word_families.get(word, [])
            info["value_score"] = 3
        elif language == "en" and word in self._knowledge_base.get_expression_list():
            kb_info = self._knowledge_base.get_analysis(word)
            if kb_info:
                info["word"] = word
                info["example"] = text
                info["translated"] = translated
                info["meaning"] = kb_info.get("meaning", "")
                info["chinese_difference"] = kb_info.get("chinese_difference", "")
                info["tone_analysis"] = kb_info.get("tone_analysis", "")
                info["learning_pitfall"] = kb_info.get("learning_pitfall", "")
                info["scene_expansion"] = kb_info.get("scene_expansion", "")
                info["grammar_note"] = kb_info.get("grammar_note", "")
                info["is_expression"] = True
                info["value_score"] = 5
        else:
            info["word"] = word
            info["example"] = text
            info["translated"] = translated
            info["value_score"] = 1
        
        if info:
            info["memory_tip"] = self._generate_memory_tip(word, info)
        
        return info if info else None
    
    def _generate_memory_tip(self, word: str, info: Dict[str, Any]) -> str:
        """生成多样化的记忆技巧"""
        tips = []
        
        if "collocations" in info:
            tips.append(f"把 '{word}' 和它的常用搭配一起记，比如：{', '.join(info['collocations'][:3])}")
        
        if "synonyms" in info and info["synonyms"]:
            tips.append(f"区分近义词：{word} vs {', '.join(info['synonyms'][:2])}，注意使用场景的差异")
        
        if "word_family" in info and len(info["word_family"]) > 1:
            tips.append(f"记单词家族：{', '.join(info['word_family'])}，举一反三扩大词汇量")
        
        if "is_expression" in info:
            tips.append("这是一个高频口语表达，建议把它放在真实对话场景中记忆")
        
        if len(word) >= 6:
            tips.append(f"拆分词根词缀：{word}，分析它的构成部分，理解词源有助于记忆")
        
        if info.get("example"):
            tips.append(f"结合例句记忆：'{info['example']}'，在语境中理解用法更深刻")
        
        tips.append(f"把 '{word}' 造3个不同场景的句子，加深印象")
        
        tips.append(f"使用间隔重复法：今天记一次，明天复习一次，一周后再回顾")
        
        if not tips:
            tips.append(f"把 '{word}' 造3个不同场景的句子，加深印象")
        
        return tips[hash(word) % len(tips)]
    
    def _find_phrase_insights(self, subtitles: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """发现短语动词和常用表达"""
        pvs = [
            "break down", "break out", "break up", "bring up", "carry out", "catch up",
            "check out", "clear up", "cut down", "cut off", "die down", "draw up",
            "drop off", "drop out", "fall apart", "fall behind", "fall through", "get around",
            "get away", "get back", "get in", "get off", "get on", "get out", "get over",
            "get through", "give up", "go back", "go by", "go down", "go out", "go through",
            "grow up", "hold on", "keep on", "leave out", "let down", "let go", "look after",
            "look forward", "look out", "look up", "make out", "make up", "pass away",
            "pick up", "point out", "put off", "put on", "put out", "put up", "run into",
            "run out", "set up", "show up", "slow down", "speed up", "stand up", "take off",
            "take over", "think over", "throw away", "turn down", "turn off", "turn on",
            "turn out", "turn up", "use up", "wake up", "watch out", "work out", "write down",
            "kind of", "sort of", "pretty much", "a lot of", "a little", "a bit",
            "you know", "I mean", "let's see", "what's up", "how come", "no way",
            "by the way", "in fact", "actually", "basically", "essentially",
        ]
        
        insights = []
        seen = set()
        all_text = " ".join([s.get("text", "").lower() for s in subtitles if s.get("text")])
        
        for pv in pvs:
            if pv in all_text and pv not in seen:
                seen.add(pv)
                for s in subtitles:
                    if pv in s.get("text", "").lower():
                        kb_info = self._knowledge_base.get_analysis(pv)
                        insight = {
                            "phrase": pv,
                            "example": s.get("text", ""),
                            "translated": s.get("translated_text", ""),
                        }
                        if kb_info:
                            insight["meaning"] = kb_info.get("meaning", "")
                            insight["chinese_difference"] = kb_info.get("chinese_difference", "")
                            insight["tone_analysis"] = kb_info.get("tone_analysis", "")
                            insight["learning_pitfall"] = kb_info.get("learning_pitfall", "")
                            insight["scene_expansion"] = kb_info.get("scene_expansion", "")
                        insights.append(insight)
                        break
        
        return insights[:6]
    
    def _find_sentence_insights(self, subtitles: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """发现有深度分析价值的句子"""
        sentences = []
        
        for s in subtitles:
            text = s.get("text", "")
            word_count = len(text.split())
            
            if word_count >= 6:
                analysis = self._analyze_sentence_structure(text)
                if analysis.get("complexity", 0) >= 1:
                    sentences.append({
                        "text": text,
                        "translated": s.get("translated_text", ""),
                        "word_count": word_count,
                        "structure": analysis.get("structure", ""),
                        "features": analysis.get("features", []),
                        "parsing": analysis.get("parsing", ""),
                        "thinking": self._generate_sentence_thinking(text, analysis),
                    })
        
        sentences.sort(key=lambda x: x["word_count"], reverse=True)
        return sentences[:5]
    
    def _analyze_sentence_structure(self, sentence: str) -> Dict[str, Any]:
        """精准分析句子结构，拒绝通用模板"""
        s_lower = sentence.lower()
        words = sentence.split()
        
        analysis = {"complexity": 0, "structure": "简单句", "features": [], "parsing": ""}
        
        features = []
        parsing_parts = []
        
        if re.search(r"\bthat\b", s_lower) and re.search(r"\bis\b|\bare\b|\bwas\b|\bwere\b", s_lower):
            is_pos = s_lower.find(" is ")
            are_pos = s_lower.find(" are ")
            was_pos = s_lower.find(" was ")
            were_pos = s_lower.find(" were ")
            that_pos = s_lower.find(" that ")
            
            verb_pos = -1
            verb_word = ""
            if is_pos > 0:
                verb_pos = is_pos
                verb_word = "is"
            elif are_pos > 0:
                verb_pos = are_pos
                verb_word = "are"
            elif was_pos > 0:
                verb_pos = was_pos
                verb_word = "was"
            elif were_pos > 0:
                verb_pos = were_pos
                verb_word = "were"
            
            if verb_pos > 0 and that_pos > verb_pos:
                subject = sentence[:verb_pos].strip()
                analysis["structure"] = "表语从句复合句"
                features.append("that引导表语从句")
                parsing_parts.append(f"主语: {subject}")
                parsing_parts.append(f"系动词: {verb_word}")
                parsing_parts.append(f"表语从句: that + {sentence[that_pos+6:].strip()}")
                analysis["complexity"] += 2
        
        if re.search(r"\bwho\b|\bwhich\b|\bwhom\b|\bwhose\b", s_lower):
            analysis["structure"] = "定语从句复合句"
            features.append("定语从句修饰名词")
            analysis["complexity"] += 1
            
            match = re.search(r"\b(\w+)\s+(who|which|whom|whose)\b", s_lower)
            if match:
                parsing_parts.append(f"先行词: {match.group(1)}")
                parsing_parts.append(f"关系词: {match.group(2)}")
        
        if re.search(r"\bif\b|\bwhen\b|\bwhile\b|\balthough\b|\bbecause\b|\bsince\b|\bunless\b", s_lower):
            if "although" in s_lower or "though" in s_lower:
                analysis["structure"] = "让步状语从句"
                features.append("although/though引导让步状语")
            elif "because" in s_lower or "since" in s_lower:
                analysis["structure"] = "原因状语从句"
                features.append("because/since引导原因状语")
            elif "if" in s_lower or "unless" in s_lower:
                analysis["structure"] = "条件状语从句"
                features.append("if/unless引导条件状语")
            elif "when" in s_lower or "while" in s_lower:
                analysis["structure"] = "时间状语从句"
                features.append("when/while引导时间状语")
            analysis["complexity"] += 1
        
        if re.search(r"\band\b|\bbut\b|\bor\b|\bso\b", s_lower):
            features.append("并列结构")
            analysis["complexity"] += 1
        
        if re.search(r"\b-ing\b", sentence):
            features.append("现在分词作修饰")
            analysis["complexity"] += 1
        
        if re.search(r"\bto \w+", s_lower):
            features.append("不定式结构")
            infinitive_match = re.search(r"\bto (\w+)", s_lower)
            if infinitive_match:
                parsing_parts.append(f"不定式: to + {infinitive_match.group(1)}")
        
        if re.search(r"\bthere be\b", s_lower):
            analysis["structure"] = "存在句型"
            features.append("there be结构")
            analysis["complexity"] += 1
        
        if re.search(r"\bIt is .+ that\b", s_lower):
            analysis["structure"] = "强调句型"
            features.append("It is ... that ... 强调结构")
            analysis["complexity"] += 2
        
        if analysis["structure"] == "简单句" and len(parsing_parts) == 0:
            if len(words) >= 3:
                pronouns = {"i", "you", "he", "she", "it", "we", "they", "this", "that", "these", "those"}
                verbs = {"is", "are", "was", "were", "have", "has", "had", "do", "does", "did", "will", "would", "could", "should", "may", "might", "must", "can", "need", "make", "take", "get", "go", "come", "know", "think", "see", "want", "give", "use", "find", "tell", "ask", "work", "seem", "feel", "look", "try", "say", "call", "help", "let", "keep", "put", "run", "set", "turn", "have", "are", "is", "am", "been", "being", "be", "did", "done", "does", "do", "was", "were", "will", "would", "could", "should", "may", "might", "must", "can", "need"}
                particles = {"alright", "so", "and", "but", "or", "then", "now", "well", "here", "there", "just", "only", "even", "still"}
                
                filtered_words = [w for w in words if w.lower() not in particles]
                
                if len(filtered_words) >= 2:
                    subject_idx = 0
                    if filtered_words[0].lower() in pronouns:
                        parsing_parts.append(f"主语: {filtered_words[0]}")
                        subject_idx = 1
                    elif len(filtered_words) > 1 and filtered_words[0].lower() not in verbs:
                        if filtered_words[1].lower() in verbs:
                            parsing_parts.append(f"主语: {filtered_words[0]}")
                            subject_idx = 1
                        else:
                            parsing_parts.append(f"主语: {filtered_words[0]} {filtered_words[1]}")
                            subject_idx = 2
                    
                    if subject_idx < len(filtered_words):
                        verb_idx = subject_idx
                        if filtered_words[verb_idx].lower() in verbs:
                            if verb_idx + 1 < len(filtered_words) and filtered_words[verb_idx + 1].lower() in verbs:
                                parsing_parts.append(f"谓语: {filtered_words[verb_idx]} {filtered_words[verb_idx + 1]}")
                                verb_idx += 2
                            else:
                                parsing_parts.append(f"谓语: {filtered_words[verb_idx]}")
                                verb_idx += 1
                            
                            if verb_idx < len(filtered_words):
                                parsing_parts.append(f"宾语/补语: {' '.join(filtered_words[verb_idx:])}")
                else:
                    parsing_parts.append(f"主语: {words[0]}")
                    if len(words) > 1:
                        parsing_parts.append(f"谓语: {' '.join(words[1:])}")
        
        analysis["features"] = features
        analysis["parsing"] = "\n".join(parsing_parts) if parsing_parts else "建议按意群拆分理解"
        
        return analysis
    
    def _generate_sentence_thinking(self, sentence: str, analysis: Dict[str, Any]) -> str:
        """生成针对具体句子的真实学习感悟"""
        thinkings = []
        
        if analysis["complexity"] >= 2:
            thinkings.append(f"🎯 这句话的结构比较复杂（{analysis['structure']}），建议先找出主干，再分析修饰成分。我刚开始分析时也觉得很难，但拆解后发现其实逻辑很清晰。")
        
        if "that引导表语从句" in analysis["features"]:
            thinkings.append("💡 表语从句是考试中的高频考点！记住结构：主语 + be动词 + that从句。这里的that虽然在从句中不充当成分，但不能省略。")
        
        if "定语从句" in analysis["structure"]:
            thinkings.append("🔍 定语从句的关键是找到先行词和关系词。建议先找到被修饰的名词，再看关系词在从句中充当什么成分（主语、宾语还是定语）。")
        
        if "让步状语从句" in analysis["structure"]:
            thinkings.append("🌐 让步状语从句中，although/though 不能和 but 连用！这是一个非常容易犯的错误，记住：'虽然...但是'在英语中只能用一个连词。")
        
        if "原因状语从句" in analysis["structure"]:
            thinkings.append("🔥 because 和 since 的区别：because 表示直接原因，语气最强；since 表示已知原因，语气较弱，常用于句首。")
        
        if "条件状语从句" in analysis["structure"]:
            thinkings.append("❓ 条件状语从句的时态规则：主将从现。主句用将来时，从句用现在时表示将来，比如'If it rains tomorrow, we will stay at home.'")
        
        if "时间状语从句" in analysis["structure"]:
            thinkings.append("⏰ when 和 while 的区别：when 可接短暂动作或持续动作；while 只能接持续动作，且通常用进行时。")
        
        if "并列结构" in analysis["features"] and analysis["structure"] != "简单句":
            thinkings.append("📝 并列结构要注意平行原则！and、but、or 连接的成分必须是同类的（名词对名词、动词对动词、从句对从句）。")
        
        if "现在分词" in analysis["features"]:
            thinkings.append("⚡ 现在分词作修饰时要注意逻辑主语！它修饰的是前面离它最近的名词，这个知识点考试经常考。")
        
        if "there be" in analysis["features"]:
            thinkings.append("🏠 there be句型看似简单，但考试中经常考主谓一致和否定形式。记住：be动词的数要和后面的主语保持一致。")
        
        if "强调句型" in analysis["features"]:
            thinkings.append("💪 强调句型的结构是：It is/was + 被强调部分 + that/who + 其他。注意：去掉It is/was...that后句子仍然完整。")
        
        if "不定式结构" in analysis["features"]:
            infinitive_thinkings = [
                "📌 不定式作后置定语修饰前面的名词，这是英语中非常常见的结构。记住：不定式表示将要发生的动作。",
                "🎯 不定式在这里作目的状语，表示动作的目的。注意区分不定式和动名词的用法：to do表示目的，doing表示方式或伴随。",
                "💡 动词不定式可以表达将来的动作或目的。这句话中的不定式用法很典型，建议记住这个结构并尝试仿写。",
                "📖 不定式短语在这里补充说明名词的内容。这种用法在英语写作中很常见，能让句子更简洁有力。",
            ]
            thinkings.append(infinitive_thinkings[hash(sentence) % len(infinitive_thinkings)])
        
        if re.search(r"\breally, really\b", sentence.lower()):
            really_count = sentence.lower().count("really")
            thinkings.append(f"🎤 这句话中'really'重复了{really_count}次！口语中通过重复副词来加强语气是非常地道的表达方式，但在书面语中一般只用一次。")
        
        if not thinkings:
            simple_thinking = [
                "📚 这句话虽然结构简单，但用词很地道。建议重点关注词汇搭配和表达方式，把它背下来作为口语素材。",
                "🎯 简单句的核心是主谓宾结构完整。这句话的主干非常清晰，可以作为基础句型来模仿，替换不同的名词和动词。",
                "💬 英语口语中很多句子都是简单句，但通过语调、重音和连读可以表达丰富的情感。建议跟读模仿发音。",
                "📖 建议把这句话中的核心动词和名词搭配记下来，这是构建句子的基础。地道的英语表达离不开好的搭配。",
                "✨ 别小看简单句！英语高手能用简单句表达复杂的意思。关键在于词汇的准确性和搭配的地道性。",
            ]
            thinkings.append(simple_thinking[hash(sentence) % len(simple_thinking)])
        
        return thinkings[0]
    
    def _find_expression_knowledge(self, subtitles: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """从知识库中发现有深度分析价值的表达"""
        expressions = []
        seen = set()
        all_text = " ".join([s.get("text", "").lower() for s in subtitles if s.get("text")])
        
        for expr in self._knowledge_base.get_expression_list():
            if expr in all_text and expr not in seen:
                seen.add(expr)
                info = self._knowledge_base.get_analysis(expr)
                if info:
                    for s in subtitles:
                        if expr in s.get("text", "").lower():
                            expressions.append({
                                "expression": expr,
                                "example": s.get("text", ""),
                                "translated": s.get("translated_text", ""),
                                **info,
                            })
                            break
        
        return expressions[:4]
    
    def _find_collocation_insights(self, subtitles: List[Dict[str, Any]], language: str = "en") -> List[Dict[str, Any]]:
        """发现有学习价值的词汇搭配
        
        Args:
            subtitles: 字幕片段列表
            language: 语言代码
            
        Returns:
            搭配洞察列表
        """
        insights = []
        seen = set()
        
        lang_data = self._lang_data.get(language, self._lang_data["en"])
        collocations = lang_data.get("collocations", {})
        
        all_text = " ".join([s.get("text", "").lower() for s in subtitles if s.get("text")])
        
        for word, collocation_list in collocations.items():
            if word in all_text and word not in seen:
                seen.add(word)
                for s in subtitles:
                    if word in s.get("text", "").lower():
                        insights.append({
                            "word": word,
                            "example": s.get("text", ""),
                            "translated": s.get("translated_text", ""),
                            "collocations": collocation_list[:4],
                        })
                        break
        
        return insights[:4]


class SocialMediaFormatter:
    """社交媒体文案格式化器 - AI增强版"""
    
    def __init__(self) -> None:
        self._analyzer = LanguageAnalyzer()
        self._ai_writer = get_ai_writer()
    
    def format(
        self,
        video_id: str,
        subtitles: List[Dict[str, Any]],
        analysis_mode: str,
        output_dir: Optional[str] = None,
        style: SocialStyle = SocialStyle.XIAOHONGSHU,
        use_ai_fallback: bool = True,
        language: str = "en"
    ) -> SocialContent:
        """
        格式化社交媒体文案
        
        Args:
            video_id: 视频ID
            subtitles: 字幕片段列表
            analysis_mode: 分析模式
            output_dir: 输出目录
            style: 社交媒体风格
            use_ai_fallback: 是否使用AI作为备选方案
            language: 视频语言代码（en/de/fr/es/zh/ja/ko/ru等）
            
        Returns:
            社交媒体内容
        """
        try:
            content = self._generate_content(subtitles, analysis_mode, style, language)

            # 社交媒体文案强制使用AI生成（硬编码模板质量不达标、不支持多语言），
            # 无条件调用LLM，只有LLM返回空时才回退到硬编码模板
            ai_content = self._generate_with_ai(subtitles, analysis_mode, style, language=language)
            if ai_content:
                content = ai_content
            
            if output_dir:
                file_path = self._save_content(video_id, style, content, output_dir)
            else:
                file_path = None
            
            return SocialContent(success=True, file_path=file_path, content=content)
        except Exception as e:
            return SocialContent(success=False, error_message=str(e))
    
    # AUDIT-0049: _should_use_ai 定义后未被调用，format() 无条件走 AI 分支。
    # 质量阈值逻辑当前为死代码，待恢复本地模板路径时启用。
    def _should_use_ai(self, content: str, subtitles: List[Dict[str, Any]]) -> bool:
        """判断是否应该使用AI生成"""
        if len(content) < 300:
            return True
        
        quality_indicators = ["搭配", "同义", "分析", "学习感悟", "记忆", "collocation", "synonym", "analysis"]
        indicator_count = sum(1 for indicator in quality_indicators if indicator in content.lower())
        
        return indicator_count < 3
    
    def _generate_with_ai(self, subtitles: List[Dict[str, Any]], analysis_mode: str, style: SocialStyle, language: str = "en") -> str:
        """使用AI生成文案"""
        content_type_map = {
            (SocialStyle.XIAOHONGSHU, "口语学习"): ContentType.XIAOHONGSHU_ORAL,
            (SocialStyle.XIAOHONGSHU, "应试学习"): ContentType.XIAOHONGSHU_EXAM,
            (SocialStyle.WEIBO, "口语学习"): ContentType.WEIBO_ORAL,
            (SocialStyle.WEIBO, "应试学习"): ContentType.WEIBO_EXAM,
            (SocialStyle.ZHIHU, "口语学习"): ContentType.ZHIHU_ORAL,
            (SocialStyle.ZHIHU, "应试学习"): ContentType.ZHIHU_EXAM,
        }
        
        content_type = content_type_map.get((style, analysis_mode), ContentType.XIAOHONGSHU_ORAL)
        
        return self._ai_writer.generate_content(subtitles, content_type, language=language)
    
    def _generate_content(
        self,
        subtitles: List[Dict[str, Any]],
        analysis_mode: str,
        style: SocialStyle,
        language: str = "en"
    ) -> str:
        """
        生成文案内容
        
        Args:
            subtitles: 字幕片段列表
            analysis_mode: 分析模式
            style: 社交媒体风格
            language: 视频语言代码
            
        Returns:
            文案内容
        """
        analysis = self._analyzer.analyze_content(subtitles, language)
        
        if style == SocialStyle.XIAOHONGSHU:
            return self._format_xiaohongshu(subtitles, analysis, analysis_mode, language)
        elif style == SocialStyle.WEIBO:
            return self._format_weibo(subtitles, analysis, analysis_mode, language)
        elif style == SocialStyle.ZHIHU:
            return self._format_zhihu(subtitles, analysis, analysis_mode, language)
        else:
            return self._format_xiaohongshu(subtitles, analysis, analysis_mode, language)
    
    def _format_xiaohongshu(
        self,
        subtitles: List[Dict[str, Any]],
        analysis: Dict[str, Any],
        analysis_mode: str,
        language: str = "en"
    ) -> str:
        """
        格式化小红书风格文案
        
        Args:
            subtitles: 字幕片段列表
            analysis: 分析结果
            analysis_mode: 分析模式
            language: 视频语言代码
            
        Returns:
            小红书风格文案
        """
        parts = []
        
        lang_names = {
            "en": "英语", "de": "德语", "fr": "法语", "es": "西班牙语",
            "zh": "中文", "ja": "日语", "ko": "韩语", "ru": "俄语"
        }
        lang_name = lang_names.get(language, "外语")
        
        if analysis_mode == "应试学习":
            parts.append(f"📚 {lang_name}考试提分干货！从视频中挖到的宝藏知识点")
            parts.append("")
            parts.append(f"今天从视频中提炼了几个超级实用的{lang_name}知识点，每个都配有详细解析和学习技巧！")
            parts.append("")
            
            if analysis["vocabulary_insights"]:
                parts.append("## 一、高级词汇深度解析")
                parts.append("")
                for gem in analysis["vocabulary_insights"]:
                    parts.append(f"🔤 **{gem['word']}**")
                    parts.append(f"   📖 例句：{gem['example']}")
                    parts.append(f"   💬 翻译：{gem['translated']}")
                    if "collocations" in gem:
                        parts.append(f"   🎯 常用搭配：{', '.join(gem['collocations'])}")
                    if "synonyms" in gem and gem["synonyms"]:
                        parts.append(f"   🔄 同义替换：{', '.join(gem['synonyms'][:3])}")
                    if "word_family" in gem and len(gem["word_family"]) > 1:
                        parts.append(f"   👨‍👩‍👧 单词家族：{', '.join(gem['word_family'])}")
                    if "memory_tip" in gem:
                        parts.append(f"   🧠 记忆技巧：{gem['memory_tip']}")
                    parts.append("")
                    parts.append("   ---")
                    parts.append("")
            
            if analysis["sentence_insights"]:
                parts.append("## 二、长难句精准拆解")
                parts.append("")
                for i, sent in enumerate(analysis["sentence_insights"], 1):
                    parts.append(f"📌 句子{i} ({sent['word_count']}词)")
                    parts.append(f"   原文：{sent['text']}")
                    parts.append(f"   翻译：{sent['translated']}")
                    parts.append(f"   📊 句型：{sent['structure']}")
                    parts.append(f"   🎯 语法特征：{', '.join(sent['features'])}")
                    if sent["parsing"]:
                        parts.append(f"   🔍 结构拆解：")
                        for line in sent["parsing"].split("\n"):
                            parts.append(f"      {line}")
                    parts.append(f"   💭 学习感悟：{sent['thinking']}")
                    parts.append("")
                    parts.append("   ---")
                    parts.append("")
            
            if analysis["collocation_insights"]:
                parts.append("## 三、高分搭配积累")
                parts.append("")
                for coll in analysis["collocation_insights"]:
                    parts.append(f"💡 **{coll['word']}**")
                    parts.append(f"   例句：{coll['example']}")
                    parts.append(f"   搭配：{', '.join(coll['collocations'])}")
                    parts.append("")
            
            parts.append("## 四、写作技巧总结")
            parts.append("")
            parts.append("1. **词汇升级**：用高级词汇替换简单词汇，比如用 significant 代替 important")
            parts.append("2. **句式多样**：适当使用复合句展示语言能力，但不要过度追求复杂")
            parts.append("3. **连接词**：使用 however、moreover、therefore 等连接词使逻辑更清晰")
            parts.append("4. **搭配积累**：记住常用搭配，避免中式英语")
            parts.append("")
            
            parts.append(f"💪 每天积累一点点，{lang_name}进步一大步！")
            parts.append("")
            
            lang_tags = {
                "en": "#英语考试 #雅思备考 #托福备考 #四六级 #英语写作",
                "de": "#德语学习 #德语考试 #德福 #歌德证书",
                "fr": "#法语学习 #法语考试 #TCF #DELF",
                "es": "#西班牙语学习 #西语考试 #DELE #SIELE",
                "zh": "#中文学习 #对外汉语 #汉语考试",
                "ja": "#日语学习 #日语考试 #JLPT #N1N2",
                "ko": "#韩语学习 #韩语考试 #TOPIK",
                "ru": "#俄语学习 #俄语考试",
            }
            parts.append(lang_tags.get(language, "#外语学习 #语言考试"))
        
        else:
            parts.append(f"🌍 挖到宝藏{lang_name}学习视频啦！")
            parts.append("")
            parts.append(f"今天从视频中提炼了几个超级实用的{lang_name}知识点，每个都配有详细解析和学习技巧！")
            parts.append("")
            
            if analysis["expression_knowledge"]:
                parts.append("## 一、高频口语表达深度解析")
                parts.append("")
                for expr in analysis["expression_knowledge"]:
                    parts.append(f"🎤 **{expr['expression']}**")
                    parts.append(f"   📖 含义：{expr['meaning']}")
                    parts.append(f"   📝 例句：{expr['example']}")
                    parts.append(f"   💬 翻译：{expr['translated']}")
                    parts.append(f"   🌐 中英差异：{expr['chinese_difference']}")
                    parts.append(f"   🎭 语气辨析：{expr['tone_analysis']}")
                    parts.append(f"   🚫 学习踩坑：{expr['learning_pitfall']}")
                    parts.append(f"   🎯 场景拓展：{expr['scene_expansion']}")
                    parts.append("")
                    parts.append("   ---")
                    parts.append("")
            
            if analysis["vocabulary_insights"]:
                parts.append("## 二、核心词汇深度解析")
                parts.append("")
                for gem in analysis["vocabulary_insights"]:
                    parts.append(f"🔤 **{gem['word']}**")
                    parts.append(f"   📖 例句：{gem['example']}")
                    parts.append(f"   💬 翻译：{gem['translated']}")
                    if "is_expression" in gem and gem.get("meaning"):
                        parts.append(f"   📚 含义：{gem['meaning']}")
                    if "memory_tip" in gem:
                        parts.append(f"   🧠 记忆技巧：{gem['memory_tip']}")
                    parts.append("")
                    parts.append("   ---")
                    parts.append("")
            
            if analysis["phrase_insights"]:
                parts.append("## 三、短语动词学习")
                parts.append("")
                for pv in analysis["phrase_insights"]:
                    parts.append(f"📚 **{pv['phrase']}**")
                    parts.append(f"   📝 例句：{pv['example']}")
                    parts.append(f"   💬 翻译：{pv['translated']}")
                    if "meaning" in pv:
                        parts.append(f"   📖 含义：{pv['meaning']}")
                    if "learning_pitfall" in pv:
                        parts.append(f"   🚫 学习踩坑：{pv['learning_pitfall']}")
                    parts.append("")
            
            if analysis["sentence_insights"]:
                parts.append("## 四、实用句型分析")
                parts.append("")
                for i, sent in enumerate(analysis["sentence_insights"], 1):
                    parts.append(f"📌 句子{i}")
                    parts.append(f"   原文：{sent['text']}")
                    parts.append(f"   翻译：{sent['translated']}")
                    parts.append(f"   📊 句型：{sent['structure']}")
                    parts.append(f"   💭 学习感悟：{sent['thinking']}")
                    parts.append("")
            
            parts.append("💪 每天积累一点点，英语进步一大步！")
            parts.append("")
            
            parts.append("#英语学习 #英语口语 #英语语法 #学习打卡")
        
        return "\n".join(parts)
    
    def _format_weibo(
        self,
        subtitles: List[Dict[str, Any]],
        analysis: Dict[str, Any],
        analysis_mode: str,
        language: str = "en"
    ) -> str:
        """
        格式化微博风格文案
        
        Args:
            subtitles: 字幕片段列表
            analysis: 分析结果
            analysis_mode: 分析模式
            language: 视频语言代码
            
        Returns:
            微博风格文案
        """
        parts = []
        
        lang_names = {
            "en": "英语", "de": "德语", "fr": "法语", "es": "西班牙语",
            "zh": "中文", "ja": "日语", "ko": "韩语", "ru": "俄语"
        }
        lang_name = lang_names.get(language, "外语")
        
        if analysis_mode == "应试学习":
            parts.append(f"📢 {lang_name}考试干货！这些知识点一定要记！")
            parts.append("")
            
            if analysis["vocabulary_insights"]:
                parts.append("🔤 高级词汇积累：")
                for gem in analysis["vocabulary_insights"][:6]:
                    parts.append(f"   • {gem['word']}")
                    parts.append(f"     → 例句：{gem['example'][:50]}")
                    if "collocations" in gem:
                        parts.append(f"     → 搭配：{', '.join(gem['collocations'][:2])}")
                    if "synonyms" in gem and gem["synonyms"]:
                        parts.append(f"     → 同义：{', '.join(gem['synonyms'][:2])}")
                    if "memory_tip" in gem:
                        parts.append(f"     → 记忆：{gem['memory_tip'][:40]}")
                    parts.append("")
            
            if analysis["sentence_insights"]:
                parts.append("📖 长难句拆解：")
                for sent in analysis["sentence_insights"][:3]:
                    parts.append(f"   • {sent['text'][:60]}")
                    parts.append(f"     → 句型：{sent['structure']}")
                    parts.append(f"     → 感悟：{sent['thinking'][:60]}")
                    parts.append("")
            
            if analysis["collocation_insights"]:
                parts.append("🎯 高分搭配：")
                for coll in analysis["collocation_insights"][:4]:
                    parts.append(f"   • {coll['word']} → {', '.join(coll['collocations'][:2])}")
                parts.append("")
            
            parts.append("💡 写作技巧：")
            parts.append("   1. 词汇升级：用高级词汇替换简单词汇")
            parts.append("   2. 句式多样：适当使用复合句")
            parts.append("   3. 连接词：使用逻辑连接词使文章更清晰")
            parts.append("   4. 搭配积累：记住常用搭配")
            parts.append("")
            
            lang_tags_weibo_exam = {
                "en": "#英语考试 #雅思 #托福 #四六级",
                "de": "#德语考试 #德福 #歌德证书",
                "fr": "#法语考试 #TCF #DELF",
                "es": "#西语考试 #DELE #SIELE",
                "zh": "#汉语考试",
                "ja": "#日语考试 #JLPT",
                "ko": "#韩语考试 #TOPIK",
                "ru": "#俄语考试",
            }
            parts.append(lang_tags_weibo_exam.get(language, "#语言考试"))
        
        else:
            parts.append(f"📢 {lang_name}学习干货！这些表达一定要记！")
            parts.append("")
            
            if analysis["expression_knowledge"]:
                for expr in analysis["expression_knowledge"]:
                    parts.append(f"🎤 {expr['expression']}")
                    parts.append(f"   → {expr['meaning']}")
                    if "chinese_difference" in expr:
                        parts.append(f"   → 中英差异：{expr['chinese_difference'][:40]}")
                    if "learning_pitfall" in expr:
                        parts.append(f"   → 学习踩坑：{expr['learning_pitfall'][:40]}")
                    parts.append(f"   → 例句：{expr['example'][:50]}")
                    parts.append("")
            
            if analysis["phrase_insights"]:
                parts.append("📚 实用短语：")
                for pv in analysis["phrase_insights"][:4]:
                    parts.append(f"   • {pv['phrase']}")
                    if "meaning" in pv:
                        parts.append(f"     → {pv['meaning']}")
                    parts.append(f"     → {pv['example'][:40]}")
                    parts.append("")
            
            if analysis["sentence_insights"]:
                parts.append("🧠 句型学习：")
                for sent in analysis["sentence_insights"][:2]:
                    parts.append(f"   • {sent['text'][:50]}")
                    parts.append(f"     → 句型：{sent['structure']}")
                    parts.append("")
            
            parts.append(f"💡 学习建议：每天记3个表达，坚持一个月！")
            parts.append("")
            
            lang_tags_oral = {
                "en": "#英语学习 #英语口语 #英语语法",
                "de": "#德语学习 #德语口语 #德语语法",
                "fr": "#法语学习 #法语口语 #法语语法",
                "es": "#西班牙语学习 #西语口语 #西语语法",
                "zh": "#中文学习 #汉语口语 #汉语语法",
                "ja": "#日语学习 #日语口语 #日语语法",
                "ko": "#韩语学习 #韩语口语 #韩语语法",
                "ru": "#俄语学习 #俄语口语 #俄语语法",
            }
            parts.append(lang_tags_oral.get(language, "#外语学习 #语言口语"))
        
        return "\n".join(parts)
    
    def _format_zhihu(
        self,
        subtitles: List[Dict[str, Any]],
        analysis: Dict[str, Any],
        analysis_mode: str,
        language: str = "en"
    ) -> str:
        """
        格式化知乎风格文案
        
        Args:
            subtitles: 字幕片段列表
            analysis: 分析结果
            analysis_mode: 分析模式
            language: 视频语言代码
            
        Returns:
            知乎风格文案
        """
        parts = []
        
        lang_names = {
            "en": "英语", "de": "德语", "fr": "法语", "es": "西班牙语",
            "zh": "中文", "ja": "日语", "ko": "韩语", "ru": "俄语"
        }
        lang_name = lang_names.get(language, "外语")
        
        if analysis_mode == "应试学习":
            parts.append(f"## 从视频中学到的应试{lang_name}表达技巧")
            parts.append("")
            parts.append(f"作为一个{lang_name}学习者，我发现从真实视频中提取考试有用的表达是一种非常有效的学习方法。")
            parts.append("")
            
            if analysis["vocabulary_insights"]:
                parts.append("### 一、高级词汇深度解析")
                parts.append("")
                for gem in analysis["vocabulary_insights"]:
                    parts.append(f"**{gem['word']}**")
                    parts.append(f"   - 例句：{gem['example']}")
                    parts.append(f"   - 翻译：{gem['translated']}")
                    if "collocations" in gem:
                        parts.append(f"   - 常用搭配：{', '.join(gem['collocations'])}")
                    if "synonyms" in gem and gem["synonyms"]:
                        parts.append(f"   - 同义替换：{', '.join(gem['synonyms'][:3])}")
                    if "memory_tip" in gem:
                        parts.append(f"   - 记忆技巧：{gem['memory_tip']}")
                    parts.append("")
            
            if analysis["sentence_insights"]:
                parts.append("### 二、长难句深度分析")
                parts.append("")
                for sent in analysis["sentence_insights"]:
                    parts.append(f"**原句**：{sent['text']}")
                    parts.append(f"**词数**：{sent['word_count']}")
                    parts.append(f"**翻译**：{sent['translated']}")
                    parts.append(f"**句子类型**：{sent['structure']}")
                    parts.append(f"**语法特征**：{', '.join(sent['features'])}")
                    if sent["parsing"]:
                        parts.append(f"**结构拆解**：")
                        for line in sent["parsing"].split("\n"):
                            parts.append(f"   - {line}")
                    parts.append(f"**学习感悟**：{sent['thinking']}")
                    parts.append("")
            
            parts.append("### 三、写作技巧总结")
            parts.append("")
            parts.append("1. **词汇升级**：在写作中用高级词汇替换简单词汇，可以显著提升文章质量")
            parts.append("")
            parts.append("2. **句式多样化**：适当使用复合句和复杂句式，展示语言能力，但不要过度追求复杂")
            parts.append("")
            parts.append("3. **连接词使用**：使用 however、moreover、therefore 等连接词使逻辑更清晰")
            parts.append("")
            parts.append("4. **搭配积累**：记住常用搭配，避免中式英语")
            parts.append("")
        
        else:
            parts.append("## 从视频中学到的实用英语表达")
            parts.append("")
            parts.append("作为一个英语学习者，我发现从真实视频中提取有用的表达是一种非常有效的学习方法。")
            parts.append("")
            
            if analysis["expression_knowledge"]:
                parts.append("### 一、高频口语表达深度解析")
                parts.append("")
                for expr in analysis["expression_knowledge"]:
                    parts.append(f"**{expr['expression']}**")
                    parts.append(f"   - 含义：{expr['meaning']}")
                    parts.append(f"   - 例句：{expr['example']}")
                    parts.append(f"   - 翻译：{expr['translated']}")
                    parts.append(f"   - 中英差异：{expr['chinese_difference']}")
                    parts.append(f"   - 语气辨析：{expr['tone_analysis']}")
                    parts.append(f"   - 学习踩坑：{expr['learning_pitfall']}")
                    parts.append(f"   - 场景拓展：{expr['scene_expansion']}")
                    parts.append("")
            
            if analysis["vocabulary_insights"]:
                parts.append("### 二、核心词汇解析")
                parts.append("")
                for gem in analysis["vocabulary_insights"]:
                    parts.append(f"**{gem['word']}**")
                    parts.append(f"   - 例句：{gem['example']}")
                    parts.append(f"   - 翻译：{gem['translated']}")
                    if "memory_tip" in gem:
                        parts.append(f"   - 记忆技巧：{gem['memory_tip']}")
                    parts.append("")
            
            if analysis["phrase_insights"]:
                parts.append("### 三、短语动词学习")
                parts.append("")
                for pv in analysis["phrase_insights"]:
                    parts.append(f"**{pv['phrase']}**")
                    parts.append(f"   - 例句：{pv['example']}")
                    parts.append(f"   - 翻译：{pv['translated']}")
                    if "meaning" in pv:
                        parts.append(f"   - 含义：{pv['meaning']}")
                    parts.append("")
            
            parts.append("### 总结")
            parts.append("")
            parts.append("通过分析真实视频中的语言表达，我们可以学到很多课本上没有的知识。")
            parts.append("")
            parts.append("关键在于将这些知识应用到实际交流中。希望这些分析对大家有所帮助！")
        
        return "\n".join(parts)
    
    def _save_content(
        self,
        video_id: str,
        style: SocialStyle,
        content: str,
        output_dir: str
    ) -> str:
        os.makedirs(output_dir, exist_ok=True)
        filename = f"{video_id}_social_{style.value}.txt"
        filepath = os.path.join(output_dir, filename)
        
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(content)
        
        return filepath