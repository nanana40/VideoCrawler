"""
爬虫模块：curl_cffi 指纹爬虫封装 + 可插拔适配器架构

架构设计：
    1. FingerprintCrawler - 底层请求引擎，封装 curl_cffi TLS 指纹
    2. CrawlerAdapter - 适配器接口，定义标准爬虫方法
    3. GenericCrawler - 通用爬虫实现，支持接入开源爬虫代码

使用方式：
    # 使用指纹引擎直接请求
    engine = FingerprintCrawler()
    html = engine.request("https://example.com")
    
    # 使用适配器接入开源爬虫
    class MyOpenSourceCrawler(CrawlerAdapter):
        def parse(self, html):
            # 复制开源爬虫的解析逻辑
            pass
    
    crawler = MyOpenSourceCrawler()
    videos = crawler.crawl("https://example.com")
"""

import random
import time
from typing import Optional, Dict, List, Any, Tuple, Callable
from abc import ABC, abstractmethod

from utils.enums import LogTag, LanguageType
from utils.logger import get_crawler_logger, get_error_logger
from utils.config_loader import load_config, get_crawler_config


logger = get_crawler_logger()
error_logger = get_error_logger()


# =====================================================
# 底层指纹引擎 - FingerprintCrawler
# =====================================================

class FingerprintCrawler:
    """
    curl_cffi TLS 指纹爬虫引擎
    
    功能：
        1. 模拟真实浏览器 TLS 指纹（绕过 Cloudflare 等反爬）
        2. UA 自动轮换
        3. 随机请求延时
        4. 代理支持
        5. 请求重试机制
    """
    
    def __init__(self, config: Optional[Dict[str, Any]] = None) -> None:
        """初始化指纹爬虫引擎
        
        Args:
            config: 爬虫配置，包含 UA 池、延时范围、代理等
        """
        if config is None:
            config = get_crawler_config(load_config())
        
        self._config = config
        self._ua_pool = config.get("ua_pool", [])
        self._request_delay = config.get("request_delay", 2.0)
        self._proxy = config.get("proxy", None)
        self._enable_tls_finger = config.get("enable_tls_finger", True)
        self._max_retries = config.get("max_retries", 3)
        self._timeout = config.get("timeout", 30)
        
        # 如果没有配置 UA 池，使用默认 UA 池
        if not self._ua_pool:
            self._ua_pool = self._get_default_ua_pool()
        
        logger.info(f"指纹爬虫引擎初始化完成，UA池大小={len(self._ua_pool)}")
    
    def _get_default_ua_pool(self) -> List[str]:
        """获取默认 UA 池
        
        Returns:
            User-Agent 列表
        """
        return [
            # Chrome Windows
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
            # Chrome macOS
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            # Firefox Windows
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0",
            # Edge Windows
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 Edg/120.0.0.0",
            # Safari macOS
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Safari/605.1.15",
        ]
    
    def _rotate_ua(self) -> str:
        """随机选择一个 User-Agent
        
        Returns:
            User-Agent 字符串
        """
        return random.choice(self._ua_pool)
    
    def _add_delay(self, min_delay: Optional[float] = None, max_delay: Optional[float] = None) -> None:
        """添加随机请求延时
        
        Args:
            min_delay: 最小延时（秒）
            max_delay: 最大延时（秒）
        """
        if min_delay is None:
            min_delay = self._request_delay * 0.5
        if max_delay is None:
            max_delay = self._request_delay * 1.5
        
        delay = random.uniform(min_delay, max_delay)
        logger.debug(f"请求延时: {delay:.2f}秒")
        time.sleep(delay)
    
    def request(
        self,
        url: str,
        method: str = "GET",
        headers: Optional[Dict[str, str]] = None,
        data: Optional[Dict[str, Any]] = None,
        params: Optional[Dict[str, Any]] = None,
        timeout: Optional[int] = None,
        retries: Optional[int] = None
    ) -> Optional[str]:
        """
        发送 HTTP 请求（核心方法）
        
        Args:
            url: 请求 URL
            method: HTTP 方法（GET/POST）
            headers: 请求头
            data: POST 数据
            params: URL 参数
            timeout: 超时时间（秒）
            retries: 重试次数
        
        Returns:
            响应 HTML 内容，失败返回 None
        """
        if timeout is None:
            timeout = self._timeout
        if retries is None:
            retries = self._max_retries
        
        # 添加请求延时（首次请求前也添加）
        self._add_delay()
        
        for attempt in range(retries):
            try:
                # 构建请求头
                if headers is None:
                    headers = {}
                
                # 添加 UA
                if "User-Agent" not in headers:
                    headers["User-Agent"] = self._rotate_ua()
                
                # 添加其他常见请求头
                default_headers = {
                    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
                    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
                    "Accept-Encoding": "gzip, deflate, br",
                    "Connection": "keep-alive",
                    "Sec-Ch-Ua": '"Not_A Brand";v="8", "Chromium";v="120", "Google Chrome";v="120"',
                    "Sec-Ch-Ua-Mobile": "?0",
                    "Sec-Ch-Ua-Platform": '"Windows"',
                    "Sec-Fetch-Dest": "document",
                    "Sec-Fetch-Mode": "navigate",
                    "Sec-Fetch-Site": "none",
                    "Sec-Fetch-User": "?1",
                    "Upgrade-Insecure-Requests": "1",
                }
                
                for key, value in default_headers.items():
                    if key not in headers:
                        headers[key] = value
                
                logger.debug(f"请求: {method} {url} (attempt {attempt + 1}/{retries})")
                
                # 使用 curl_cffi 发送请求
                if self._enable_tls_finger:
                    response = self._curl_request(url, method, headers, data, params, timeout)
                else:
                    response = self._fallback_request(url, method, headers, data, params, timeout)
                
                if response:
                    logger.debug(f"请求成功: {url}")
                    return response
                
            except Exception as e:
                logger.warning(f"请求失败 (attempt {attempt + 1}/{retries}): {url}, error={e}")
                
                if attempt < retries - 1:
                    sleep_time = 2 ** attempt
                    logger.debug(f"等待 {sleep_time} 秒后重试...")
                    time.sleep(sleep_time)
        
        error_logger.error(f"请求失败（已达最大重试次数）: {url}")
        return None
    
    def _curl_request(
        self,
        url: str,
        method: str,
        headers: Dict[str, str],
        data: Optional[Dict[str, Any]],
        params: Optional[Dict[str, Any]],
        timeout: int
    ) -> Optional[str]:
        """使用 curl_cffi 发送请求（带 TLS 指纹）
        
        Args:
            url: 请求 URL
            method: HTTP 方法
            headers: 请求头
            data: POST 数据
            params: URL 参数
            timeout: 超时时间
        
        Returns:
            响应内容
        """
        try:
            from curl_cffi import requests
            
            kwargs: Dict[str, Any] = {
                "url": url,
                "method": method,
                "headers": headers,
                "timeout": timeout,
                "impersonate": "chrome120",
            }
            
            if params:
                kwargs["params"] = params
            
            if data:
                kwargs["data"] = data
            
            if self._proxy:
                kwargs["proxies"] = {
                    "http": self._proxy,
                    "https": self._proxy,
                }
            
            response = requests.request(**kwargs)
            response.raise_for_status()
            
            return response.text
        
        except ImportError:
            logger.warning("curl_cffi 未安装，使用普通请求")
            return self._fallback_request(url, method, headers, data, params, timeout)
        except Exception as e:
            logger.error(f"curl_cffi 请求失败: {e}")
            return None
    
    def _fallback_request(
        self,
        url: str,
        method: str,
        headers: Dict[str, str],
        data: Optional[Dict[str, Any]],
        params: Optional[Dict[str, Any]],
        timeout: int
    ) -> Optional[str]:
        """使用标准库 requests 发送请求（降级方案）
        
        Args:
            url: 请求 URL
            method: HTTP 方法
            headers: 请求头
            data: POST 数据
            params: URL 参数
            timeout: 超时时间
        
        Returns:
            响应内容
        """
        try:
            import requests as std_requests
            
            kwargs: Dict[str, Any] = {
                "url": url,
                "method": method,
                "headers": headers,
                "timeout": timeout,
            }
            
            if params:
                kwargs["params"] = params
            
            if data:
                kwargs["data"] = data
            
            if self._proxy:
                kwargs["proxies"] = {
                    "http": self._proxy,
                    "https": self._proxy,
                }
            
            response = std_requests.request(**kwargs)
            response.raise_for_status()
            
            return response.text
        
        except ImportError:
            error_logger.error("requests 库未安装")
            return None
        except Exception as e:
            logger.error(f"请求失败: {e}")
            return None
    
    def get(self, url: str, **kwargs) -> Optional[str]:
        """发送 GET 请求（便捷方法）
        
        Args:
            url: 请求 URL
            **kwargs: 其他参数
        
        Returns:
            响应内容
        """
        return self.request(url, method="GET", **kwargs)
    
    def post(self, url: str, data: Dict[str, Any], **kwargs) -> Optional[str]:
        """发送 POST 请求（便捷方法）
        
        Args:
            url: 请求 URL
            data: POST 数据
            **kwargs: 其他参数
        
        Returns:
            响应内容
        """
        return self.request(url, method="POST", data=data, **kwargs)
    
    @property
    def config(self) -> Dict[str, Any]:
        """获取配置"""
        return self._config
    
    @property
    def ua_pool(self) -> List[str]:
        """获取 UA 池"""
        return self._ua_pool
    
    @ua_pool.setter
    def ua_pool(self, ua_list: List[str]) -> None:
        """设置 UA 池"""
        self._ua_pool = ua_list
    
    @property
    def proxy(self) -> Optional[str]:
        """获取代理设置"""
        return self._proxy
    
    @proxy.setter
    def proxy(self, proxy_url: Optional[str]) -> None:
        """设置代理"""
        self._proxy = proxy_url


# =====================================================
# 爬虫适配器接口 - CrawlerAdapter
# =====================================================

class CrawlerAdapter(ABC):
    """
    爬虫适配器接口
    
    定义标准爬虫方法，便于接入开源爬虫代码。
    用户只需继承此类并实现 parse 方法即可。
    
    使用方式：
        class MyOpenSourceCrawler(CrawlerAdapter):
            def parse(self, html):
                # 复制开源爬虫的解析逻辑
                videos = []
                # ... 解析 html，提取视频信息 ...
                return videos
        
        crawler = MyOpenSourceCrawler()
        videos = crawler.crawl("https://example.com")
    """
    
    def __init__(self, engine: Optional[FingerprintCrawler] = None) -> None:
        """初始化适配器
        
        Args:
            engine: 指纹爬虫引擎，默认自动创建
        """
        if engine is None:
            engine = FingerprintCrawler()
        
        self._engine = engine
        self._logger = get_crawler_logger()
    
    @abstractmethod
    def parse(self, html: str, url: str) -> List[Dict[str, Any]]:
        """
        解析 HTML，提取视频信息
        
        **用户需要实现此方法，复制开源爬虫的解析逻辑**
        
        Args:
            html: 页面 HTML 内容
            url: 当前页面 URL
        
        Returns:
            视频信息列表，每个视频包含：
                - title: 视频标题
                - source_url: 视频源 URL
                - description: 视频描述（可选）
                - thumbnail: 缩略图 URL（可选）
                - duration: 视频时长（可选）
                - author: 作者（可选）
                - views: 播放量（可选）
        """
        pass
    
    def crawl(
        self,
        url: str,
        headers: Optional[Dict[str, str]] = None,
        params: Optional[Dict[str, Any]] = None,
        filter_languages: Optional[List[LanguageType]] = None
    ) -> List[Dict[str, Any]]:
        """
        爬取页面并解析视频信息
        
        Args:
            url: 目标 URL
            headers: 请求头
            params: URL 参数
            filter_languages: 语言白名单，过滤非目标语言视频
        
        Returns:
            视频信息列表
        """
        try:
            self._logger.info(f"开始爬取: {url}")
            
            # 发送请求
            html = self._engine.get(url, headers=headers, params=params)
            
            if html is None:
                self._logger.error(f"获取页面失败: {url}")
                return []
            
            # 解析页面
            videos = self.parse(html, url)
            self._logger.info(f"解析完成，获取 {len(videos)} 个视频")
            
            # 语言过滤
            if filter_languages:
                videos = self._filter_by_language(videos, filter_languages)
            
            return videos
        
        except Exception as e:
            error_logger.error(f"爬取失败: {url}, error={e}")
            return []
    
    def crawl_with_pagination(
        self,
        base_url: str,
        max_pages: int = 10,
        headers: Optional[Dict[str, str]] = None,
        params: Optional[Dict[str, Any]] = None,
        filter_languages: Optional[List[LanguageType]] = None,
        get_next_page: Optional[Callable[[str, int], Optional[str]]] = None
    ) -> List[Dict[str, Any]]:
        """
        分页爬取
        
        Args:
            base_url: 基础 URL
            max_pages: 最大页数
            headers: 请求头
            params: URL 参数
            filter_languages: 语言白名单
            get_next_page: 获取下一页 URL 的函数
        
        Returns:
            所有页面的视频信息列表
        """
        all_videos = []
        
        try:
            current_url = base_url
            for page in range(1, max_pages + 1):
                self._logger.info(f"爬取第 {page}/{max_pages} 页: {current_url}")
                
                # 爬取当前页
                videos = self.crawl(current_url, headers=headers, params=params, filter_languages=filter_languages)
                all_videos.extend(videos)
                
                # 获取下一页 URL
                if get_next_page:
                    current_url = get_next_page(current_url, page)
                    if current_url is None:
                        self._logger.info("已到达最后一页")
                        break
                else:
                    if page < max_pages:
                        current_url = self._build_pagination_url(base_url, page + 1)
                    else:
                        break
                
                # 分页间隔
                self._engine._add_delay()
            
            self._logger.info(f"分页爬取完成，共获取 {len(all_videos)} 个视频")
            return all_videos
        
        except Exception as e:
            error_logger.error(f"分页爬取失败: {e}")
            return all_videos
    
    def _filter_by_language(
        self,
        videos: List[Dict[str, Any]],
        allowed_languages: List[LanguageType]
    ) -> List[Dict[str, Any]]:
        """按语言过滤视频
        
        Args:
            videos: 视频列表
            allowed_languages: 允许的语言列表
        
        Returns:
            过滤后的视频列表
        """
        try:
            from utils.language_check import is_video_language_allowed
            
            filtered = []
            for video in videos:
                title = video.get("title", "")
                description = video.get("description", "")
                
                if is_video_language_allowed(title, description, allowed_languages):
                    filtered.append(video)
                else:
                    self._logger.debug(f"过滤非目标语言视频: {title[:30]}...")
            
            self._logger.info(f"语言过滤完成，保留 {len(filtered)} 个视频")
            return filtered
        
        except ImportError:
            self._logger.warning("language_check 模块未导入，跳过语言过滤")
            return videos
        except Exception as e:
            self._logger.error(f"语言过滤失败: {e}")
            return videos
    
    def _build_pagination_url(self, base_url: str, page: int) -> str:
        """构建分页 URL（默认实现）
        
        Args:
            base_url: 基础 URL
            page: 页码
        
        Returns:
            分页 URL
        """
        if "?" in base_url:
            return f"{base_url}&page={page}"
        else:
            return f"{base_url}?page={page}"
    
    @property
    def engine(self) -> FingerprintCrawler:
        """获取底层爬虫引擎"""
        return self._engine


# =====================================================
# 通用爬虫实现 - GenericCrawler
# =====================================================

class GenericCrawler(CrawlerAdapter):
    """
    通用爬虫实现
    
    提供基础的页面解析能力，可作为接入开源爬虫的起点。
    用户可以继承此类并覆盖 parse 方法。
    """
    
    def __init__(self, engine: Optional[FingerprintCrawler] = None) -> None:
        """初始化通用爬虫"""
        super().__init__(engine)
        
    def parse(self, html: str, url: str) -> List[Dict[str, Any]]:
        """
        通用页面解析（模板方法）
        
        **用户需要覆盖此方法，复制开源爬虫的解析逻辑**
        
        默认实现返回空列表，需要用户根据目标网站实现。
        
        Args:
            html: 页面 HTML 内容
            url: 当前页面 URL
        
        Returns:
            视频信息列表
        """
        self._logger.warning("通用爬虫的 parse 方法未实现，请继承并覆盖此方法")
        return []


# =====================================================
# 便捷函数
# =====================================================

def create_fingerprint_crawler(config: Optional[Dict[str, Any]] = None) -> FingerprintCrawler:
    """创建指纹爬虫引擎
    
    Args:
        config: 爬虫配置
    
    Returns:
        FingerprintCrawler 实例
    """
    return FingerprintCrawler(config)


def create_crawler(
    adapter_class: type = GenericCrawler,
    engine: Optional[FingerprintCrawler] = None,
    **kwargs
) -> CrawlerAdapter:
    """创建爬虫适配器
    
    Args:
        adapter_class: 适配器类（默认为 GenericCrawler）
        engine: 指纹爬虫引擎
        **kwargs: 其他参数
    
    Returns:
        CrawlerAdapter 实例
    """
    if engine is None:
        engine = FingerprintCrawler()
    
    return adapter_class(engine, **kwargs)


# =====================================================
# 模块初始化
# =====================================================

def init_crawler() -> None:
    """初始化爬虫模块"""
    logger.info("爬虫模块初始化完成")