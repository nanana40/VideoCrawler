"""
AI 分类模块

支持在线 API 文本分类和本地规则分类，用于视频题材分类。

功能特性：
    1. 在线 API 分类（调用外部 AI 服务）
    2. 本地规则分类（基于关键词匹配）
    3. 缓存机制（避免重复调用）
    4. 返回 VideoCategory 枚举
"""

import time
import hashlib
import re
from typing import Optional, Dict, Any, Tuple, List
from abc import ABC, abstractmethod

from utils.enums import VideoCategory
from utils.logger import get_crawler_logger
from utils.config_loader import get_classify_config, load_config


logger = get_crawler_logger()


# AUDIT-0029: 模块级单例，避免 APIClassifier 每次 fallback 都重建整个关键词规则表
_RULE_BASED_SINGLETON: Optional["RuleBasedClassifier"] = None


def _get_rule_based() -> "RuleBasedClassifier":
    global _RULE_BASED_SINGLETON
    if _RULE_BASED_SINGLETON is None:
        _RULE_BASED_SINGLETON = RuleBasedClassifier()
    return _RULE_BASED_SINGLETON


class VideoClassifier(ABC):
    """视频分类器抽象基类"""
    
    @abstractmethod
    def classify(self, title: str, description: Optional[str] = None) -> VideoCategory:
        """
        对视频进行分类
        
        Args:
            title: 视频标题
            description: 视频描述
            
        Returns:
            VideoCategory 枚举值
        """
        pass
    
    @abstractmethod
    def clear_cache(self) -> None:
        """清空分类缓存"""
        pass


class RuleBasedClassifier(VideoClassifier):
    """
    基于规则的本地分类器
    
    通过关键词匹配进行分类，不需要外部 API。
    """
    
    def __init__(self) -> None:
        """初始化规则分类器"""
        self._rules = self._build_rules()
        self._cache: Dict[str, Tuple[VideoCategory, float]] = {}
        logger.info("规则分类器初始化完成")
    
    def _build_rules(self) -> Dict[VideoCategory, list]:
        """构建分类规则

        设计原则：
            1. 关键词全小写，匹配时不区分大小写
            2. SCIENCE：科学/科普类（和TECHNOLOGY区分：更偏向理论/宇宙/生物/医学等自然科学）
            3. TECHNOLOGY：科技/数码/IT/编程/AI
            4. EDUCATION：教育/学习/语言教学
            5. ENTERTAINMENT：娱乐（综艺/影视剧/音乐/游戏等）
            6. NEWS：新闻
            7. DAILY：日常（生活/Vlog/旅行/美食/街访等真实口语素材）
        匹配优先级：取得分最高的分类；若所有分类得分为0，兜底为 DAILY
        """
        return {
            VideoCategory.SCIENCE: [
                # 通用自然科学
                "science", "scientist", "research", "study", "experiment", "laboratory",
                "space", "cosmos", "astronomy", "planet", "galaxy", "universe",
                "biology", "physics", "chemistry", "geology", "ecology", "evolution",
                "nature", "wildlife", "animal", "ocean", "earth", "climate",
                "medicine", "health", "doctor", "hospital", "virus", "bacteria",
                "documentary", "explained", "what if", "how does", "why do",
                # 多语言
                "wissenschaft", "ciencia", "science", "科学",
            ],
            VideoCategory.TECHNOLOGY: [
                "tech", "technology", "computer", "programming", "coding", "code",
                "software", "hardware", "gadget", "review", "unboxing",
                "innovation", "AI", "artificial intelligence", "machine learning",
                "data", "internet", "digital", "smartphone", "laptop", "CPU", "GPU",
                "cyber", "security", "hacker", "robot", "automation", "startup",
                "tech review", "apple", "google", "microsoft", "iphone", "android",
                "how to build", "tutorial code", "dev", "developer",
                # 多语言
                "technologie", "informatique", "tecnologia", "programmierung",
                "programación", "programação",
            ],
            VideoCategory.EDUCATION: [
                "lern", "learn", "edu", "tutorial", "course", "lesson",
                "school", "university", "college", "study", "teaching", "teacher",
                "educational", "academic", "training", "workshop", "seminar",
                "deutsch lernen", "français", "español", "apprendre", "aprender",
                "english learning", "learning english", "how to say", "pronunciation",
                "grammar", "vocabulary", "exam", "test", "quiz", "exercise",
                # 多语言
                "apprentissage", "unterricht", "lección", "lezione", "aula",
                "clase de", "curso de",
            ],
            VideoCategory.ENTERTAINMENT: [
                "movie", "film", "music", "song", "video", "game", "gaming",
                "play", "fun", "comedy", "drama", "series", "show", "tv",
                "entertainment", "video clip", "performance", "concert",
                "musik", "musique", "musica", "dance", "dance video",
                "trailer", "teaser", "clips", "highlights", "stand up", "prank",
                "challenge", "reaction", "compilation", "meme",
                # 多语言
                "película", "pelicula", "cinéma", "cinema", "divertissement",
                "unterhaltung", "divertimento", "diversão",
            ],
            VideoCategory.NEWS: [
                "news", "breaking", "update", "report", "journal", "politics",
                "world", "international", "local", "national", "headline",
                "news channel", "news report", "news update",
                "actualité", "noticias", "nachrichten", "notizie",
                "interview", "press", "media", "coverage", "broadcast",
                # 多语言
                "nouvelles", "aktualności", "haberler", "berita",
            ],
            VideoCategory.DAILY: [
                # 生活Vlog
                "vlog", "daily vlog", "my day", "a day in", "lifestyle",
                "routine", "morning routine", "night routine",
                # 旅行
                "travel", "trip", "tour", "visit", "city tour", "walk tour",
                "explore", "adventure", "travel vlog", "road trip", "vacation",
                # 美食/烹饪
                "food", "cooking", "recipe", "cook", "eat", "tasting",
                "restaurant", "street food", "cuisine", "chef", "bakery",
                "美食", "cocina", "küche", "cuisine",
                # 街访/真实口语素材
                "interview people", "street interview", "ask people",
                "what people think", "public interview", "man on the street",
                # 家庭/亲子/宠物
                "family", "home", "house", "apartment", "room tour", "pet",
                "cat", "dog", "kids", "baby", "parenting",
                # 生活技能/DIY/手工
                "DIY", "how to make", "craft", "handmade", "home decor",
                "life hack", "tips and tricks", "useful tips",
                # 运动/健身/户外（非娱乐竞技）
                "fitness", "workout", "gym", "running", "hiking", "camping",
                "yoga", "healthy lifestyle", "weight loss", "motivation",
                # 多语言日常词
                "vie quotidienne", "alltag", "vida cotidiana", "vida diária",
                "viaggio", "voyage", "reise", "viaje", "viagem",
                "cuisine maison", "hausgemacht", "casero", "comida callejera",
                # 真实场景对话
                "conversation", "real talk", "storytime", "story time",
                "q&a", "questions and answers", "asking strangers",
            ],
        }
    
    def classify(self, title: str, description: Optional[str] = None) -> VideoCategory:
        """
        对视频进行分类（基于规则匹配）

        特别处理：为解决语言关键词（如español/français）与日常Vlog标题的冲突，
        若标题含有强 DAILY 语义词（vlog/day/travel/food/street interview等），
        且 DAILY 得分>0 且与冠军类得分差值 <=1，则优先判为 DAILY。

        同理：TECHNOLOGY 中的"AI"极易误匹配（如 franç**ai**s），
        已在规则中改为边界匹配；并在打分后对 AI 单独做边界确认。
        
        Args:
            title: 视频标题
            description: 视频描述
            
        Returns:
            VideoCategory 枚举值
        """
        key = self._generate_cache_key(title, description)
        
        if key in self._cache:
            category, _ = self._cache[key]
            return category
        
        full_text = f"{title} {description or ''}".lower()
        scores: Dict[VideoCategory, int] = {}
        
        for category, keywords in self._rules.items():
            score = 0
            for keyword in keywords:
                kw = keyword.lower()
                # 边界敏感的短关键词：必须是"整词"而非子串
                # - AI：避免误匹配 franç**ai**s、curricul**ai**te 等
                # - play/game：避免误匹配 dis**play**、pro**game**n 等
                boundary_sensitive = {"ai", "play", "game", "fun", "tv", "cat", "dog"}
                if kw in boundary_sensitive:
                    # 使用 \b 整词正则匹配（为兼容空格/标点）
                    if re.search(rf"\b{re.escape(kw)}\b", full_text):
                        score += 1
                else:
                    if kw in full_text:
                        score += 1
            if score > 0:
                scores[category] = score
        
        if scores:
            category = max(scores, key=scores.get)
            top_score = scores[category]
            daily_score = scores.get(VideoCategory.DAILY, 0)

            # 冲突消解：当 DAILY 得分 >0 且与冠军得分相差<=1时，
            # 此时"日常Vlog"语义更贴近语言学习素材目标，优先选 DAILY
            if (
                category != VideoCategory.DAILY
                and daily_score > 0
                and top_score - daily_score <= 1
            ):
                category = VideoCategory.DAILY
        else:
            # 所有规则匹配不到 → 兜底为 DAILY
            category = VideoCategory.DAILY
        
        self._cache[key] = (category, time.time())
        return category
    
    def _generate_cache_key(self, title: str, description: Optional[str]) -> str:
        """生成缓存键"""
        content = f"{title}:{description or ''}"
        return hashlib.md5(content.encode("utf-8")).hexdigest()
    
    def clear_cache(self) -> None:
        """清空分类缓存"""
        self._cache.clear()
        logger.info("规则分类器缓存已清空")


class APIClassifier(VideoClassifier):
    """
    基于在线 API 的分类器
    
    调用外部 AI 服务进行智能分类。
    """
    
    def __init__(self) -> None:
        """初始化 API 分类器"""
        config = get_classify_config(load_config())
        self._api_url = config.get("api_url", "")
        self._cache_ttl = config.get("cache_ttl", 86400)
        self._cache: Dict[str, Tuple[VideoCategory, float]] = {}
        logger.info("API 分类器初始化完成")
    
    def classify(self, title: str, description: Optional[str] = None) -> VideoCategory:
        """
        对视频进行分类（调用在线 API）
        
        Args:
            title: 视频标题
            description: 视频描述
            
        Returns:
            VideoCategory 枚举值
        """
        key = self._generate_cache_key(title, description)
        
        if key in self._cache:
            category, timestamp = self._cache[key]
            if time.time() - timestamp < self._cache_ttl:
                return category
        
        if not self._api_url:
            fallback = _get_rule_based()
            return fallback.classify(title, description)
        
        try:
            import requests as std_requests
            
            data = {
                "title": title,
                "description": description or "",
            }
            
            response = std_requests.post(self._api_url, json=data, timeout=10)
            response.raise_for_status()
            
            result = response.json()
            category_code = result.get("category", "other")
            
            category = VideoCategory.from_code(category_code, VideoCategory.OTHER)
            
            self._cache[key] = (category, time.time())
            return category
            
        except Exception as e:
            logger.warning(f"API 分类失败，使用规则分类: {e}")
            fallback = _get_rule_based()
            return fallback.classify(title, description)
    
    def _generate_cache_key(self, title: str, description: Optional[str]) -> str:
        """生成缓存键"""
        content = f"{title}:{description or ''}"
        return hashlib.md5(content.encode("utf-8")).hexdigest()
    
    def clear_cache(self) -> None:
        """清空分类缓存"""
        self._cache.clear()
        logger.info("API 分类器缓存已清空")


class VideoClassifyService:
    """
    视频分类服务
    
    统一的分类入口，根据配置选择分类器类型。
    """
    
    def __init__(self, use_api: bool = False) -> None:
        """
        初始化视频分类服务
        
        Args:
            use_api: 是否使用在线 API 分类
        """
        if use_api:
            self._classifier: VideoClassifier = APIClassifier()
        else:
            self._classifier = RuleBasedClassifier()
        logger.info(f"视频分类服务初始化完成，分类器类型: {type(self._classifier).__name__}")
    
    def classify_video(self, title: str, description: Optional[str] = None) -> VideoCategory:
        """
        对视频进行分类
        
        Args:
            title: 视频标题
            description: 视频描述
            
        Returns:
            VideoCategory 枚举值
        """
        return self._classifier.classify(title, description)
    
    def classify_batch(self, videos: List[Dict[str, Any]]) -> List[Tuple[int, VideoCategory]]:
        """
        批量分类视频
        
        Args:
            videos: 视频列表，每个视频包含 title 和 description 字段
            
        Returns:
            (视频索引, 分类结果) 列表
        """
        results = []
        for i, video in enumerate(videos):
            category = self._classifier.classify(
                video.get("title", ""),
                video.get("description")
            )
            results.append((i, category))
        return results
    
    def clear_cache(self) -> None:
        """清空分类缓存"""
        self._classifier.clear_cache()


# 便捷函数
_video_classifier: Optional[VideoClassifyService] = None


def get_classifier() -> VideoClassifyService:
    """获取视频分类器实例（单例）"""
    global _video_classifier
    if _video_classifier is None:
        config = get_classify_config(load_config())
        use_api = bool(config.get("api_url"))
        _video_classifier = VideoClassifyService(use_api=use_api)
    return _video_classifier


def classify_video(title: str, description: Optional[str] = None) -> VideoCategory:
    """
    便捷函数：对视频进行分类
    
    Args:
        title: 视频标题
        description: 视频描述
        
    Returns:
        VideoCategory 枚举值
    """
    return get_classifier().classify_video(title, description)


def init_classifier(use_api: bool = False) -> None:
    """
    初始化视频分类器
    
    Args:
        use_api: 是否使用在线 API 分类
    """
    global _video_classifier
    _video_classifier = VideoClassifyService(use_api=use_api)
