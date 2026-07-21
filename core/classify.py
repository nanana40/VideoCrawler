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
from typing import Optional, Dict, Any, Tuple
from abc import ABC, abstractmethod

from utils.enums import VideoCategory
from utils.logger import get_crawler_logger
from utils.config_loader import get_classify_config, load_config


logger = get_crawler_logger()


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
        """构建分类规则"""
        return {
            VideoCategory.EDUCATION: [
                "lern", "learn", "edu", "tutorial", "course", "lesson", 
                "school", "university", "college", "study", "teaching",
                "educational", "academic", "training", "workshop", "seminar",
                "deutsch lernen", "français", "español", "apprendre", "aprender",
            ],
            VideoCategory.ENTERTAINMENT: [
                "movie", "film", "music", "song", "video", "game", "gaming",
                "play", "fun", "comedy", "drama", "series", "show", "tv",
                "entertainment", "video clip", "performance", "concert",
                "musik", "musique", "musica", "dance", "dance video",
            ],
            VideoCategory.NEWS: [
                "news", "breaking", "update", "report", "journal", "politics",
                "world", "international", "local", "national", "headline",
                "news channel", "news report", "news update",
                "actualité", "noticias", "nachrichten",
            ],
            VideoCategory.TECHNOLOGY: [
                "tech", "technology", "computer", "programming", "coding",
                "software", "hardware", "gadget", "review", "unboxing",
                "science", "innovation", "AI", "artificial intelligence",
                "machine learning", "data", "internet", "digital",
                "technologie", "informatique", "tecnologia",
            ],
        }
    
    def classify(self, title: str, description: Optional[str] = None) -> VideoCategory:
        """
        对视频进行分类（基于规则匹配）
        
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
                if keyword.lower() in full_text:
                    score += 1
            if score > 0:
                scores[category] = score
        
        if scores:
            category = max(scores, key=scores.get)
        else:
            category = VideoCategory.OTHER
        
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
            fallback = RuleBasedClassifier()
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
            fallback = RuleBasedClassifier()
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
