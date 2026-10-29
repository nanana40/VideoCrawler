"""
爬虫模块：curl_cffi 指纹爬虫封装 + 可插拔适配器架构

架构设计：
    1. FingerprintCrawler - 底层请求引擎，封装 curl_cffi TLS 指纹
    2. CrawlerAdapter - 适配器接口，定义标准爬虫方法
    3. GenericCrawler - 通用爬虫实现，支持接入开源爬虫代码

Day5 增强功能：
    - 分页采集：支持多种分页策略（URL参数、路径、AJAX）
    - 结果临时缓冲：爬取结果写入临时文件，避免内存溢出
    - 去重机制：URL 去重、视频去重
    - 中断恢复：支持断点续爬
    - 进度跟踪：实时记录爬取进度
"""

import random
import time
import json
import os
import hashlib
import threading
from typing import Optional, Dict, List, Any, Tuple, Callable, Set
from abc import ABC, abstractmethod

from utils.enums import LogTag, LanguageType
from utils.logger import get_crawler_logger, get_error_logger
from utils.config_loader import load_config, get_crawler_config
from utils.path_helper import get_tmp_dir, make_tmp_file, clear_tmp_dir


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

        # TLS 指纹轮换池（curl_cffi 支持的浏览器指纹）
        # 注意：curl_cffi 0.15.0 不支持 safari17_4/safari17_5，
        # 只能用 safari17_0 / safari15_5 / safari15_3 / safari15_2 / safari15_1
        self._finger_pool: List[str] = [
            "chrome131", "chrome124", "chrome120", "chrome116", "chrome110",
            "safari17_0", "safari15_5", "safari15_3",
            "edge101", "edge99",
        ]
        # 上一次请求用的指纹 + 时间戳（确保同指纹间隔 >= 1.5s）
        self._last_finger: Optional[str] = None
        self._last_finger_ts: float = 0.0
        self._finger_min_gap: float = 1.5

        # 如果没有配置 UA 池，使用默认 UA 池
        if not self._ua_pool:
            self._ua_pool = self._get_default_ua_pool()

        logger.info(
            f"指纹爬虫引擎初始化完成，UA池={len(self._ua_pool)}, "
            f"指纹池={len(self._finger_pool)}, 最小同指纹间隔={self._finger_min_gap}s"
        )
    
    def _get_default_ua_pool(self) -> List[str]:
        """获取默认 UA 池
        
        Returns:
            User-Agent 列表
        """
        return [
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 Edg/120.0.0.0",
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
        
        self._add_delay()
        
        last_exception = None
        for attempt in range(retries):
            try:
                if headers is None:
                    headers = {}
                
                if "User-Agent" not in headers:
                    headers["User-Agent"] = self._rotate_ua()
                
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
                
                if self._enable_tls_finger:
                    response = self._curl_request(url, method, headers, data, params, timeout)
                else:
                    response = self._fallback_request(url, method, headers, data, params, timeout)
                
                if response:
                    logger.debug(f"请求成功: {url}")
                    return response
                
            except Exception as e:
                last_exception = e
                logger.warning(f"请求失败 (attempt {attempt + 1}/{retries}): {url}, error={e}")
                
                if attempt < retries - 1:
                    sleep_time = 2 ** attempt
                    logger.debug(f"等待 {sleep_time} 秒后重试...")
                    time.sleep(sleep_time)
        
        # curl_cffi 全部重试失败 → 自动降级到普通 requests 兜底一次
        # 注：last_exception 为 None 仅在"重试没抛异常但返回空响应"的罕见情况发生；
        # 真正失败时 last_exception 必非 None，所以去掉该条件，重试耗尽即降级
        if self._enable_tls_finger:
            logger.warning(f"curl_cffi 全部重试失败，自动 fallback 到普通 requests: {url}")
            try:
                fallback_resp = self._fallback_request(url, method, headers, data, params, timeout)
                if fallback_resp:
                    logger.info(f"普通 requests 兜底成功: {url}")
                    return fallback_resp
            except Exception as fe:
                logger.warning(f"普通 requests 兜底也失败: {fe}")

        error_logger.error(f"请求失败（已达最大重试次数）: {url}, last_error={last_exception}")
        return None

    def _pick_fingerprint(self) -> str:
        """从指纹池选一个指纹，确保同指纹两次调用间隔 >= 1.5s

        策略：
            1. 过滤掉上次用的指纹（避免连续重复）
            2. 如果所有指纹都刚用过（< 1.5s），等够 gap 再用
            3. 随机选一个
        """
        now = time.time()
        elapsed = now - self._last_finger_ts

        # 候选 = 池里去掉上次用的那个
        candidates = [f for f in self._finger_pool if f != self._last_finger]

        # 如果距离上次还没到 gap，且候选 > 0，从候选里挑
        if elapsed < self._finger_min_gap and candidates:
            chosen = random.choice(candidates)
        else:
            chosen = random.choice(self._finger_pool)

        self._last_finger = chosen
        self._last_finger_ts = time.time()
        return chosen

    def _ban_fingerprint(self, finger: str) -> None:
        """某个指纹报了硬错误（不支持），从池中移除避免反复踩坑"""
        if finger in self._finger_pool and len(self._finger_pool) > 2:
            self._finger_pool.remove(finger)
            logger.warning(
                f"指纹 {finger} 已从池中移除（剩余 {len(self._finger_pool)} 个）"
            )

    def _curl_request(
        self,
        url: str,
        method: str,
        headers: Dict[str, str],
        data: Optional[Dict[str, Any]],
        params: Optional[Dict[str, Any]],
        timeout: int
    ) -> Optional[str]:
        """使用 curl_cffi 发送请求（带轮换 TLS 指纹）"""
        try:
            from curl_cffi import requests

            finger = self._pick_fingerprint()

            kwargs: Dict[str, Any] = {
                "url": url,
                "method": method,
                "headers": headers,
                "timeout": timeout,
                "impersonate": finger,
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
            self._enable_tls_finger = False
            return self._fallback_request(url, method, headers, data, params, timeout)
        except Exception as e:
            err_msg = str(e)
            # 硬错误：指纹不支持 — 立刻从池中移除
            if "is not supported" in err_msg:
                self._ban_fingerprint(finger)
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
        """使用标准库 requests 发送请求（降级方案）"""
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
        """发送 GET 请求（便捷方法）"""
        return self.request(url, method="GET", **kwargs)
    
    def post(self, url: str, data: Dict[str, Any], **kwargs) -> Optional[str]:
        """发送 POST 请求（便捷方法）"""
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
# 结果临时缓冲器 - ResultBuffer
# =====================================================

class ResultBuffer:
    """
    爬取结果临时缓冲器
    
    功能：
        1. 将爬取结果写入临时文件，避免内存溢出
        2. 支持批量写入，提高 IO 效率
        3. 支持断点续爬，从中断点恢复
        4. 支持去重机制
    """
    
    def __init__(self, buffer_size: int = 100, temp_dir: Optional[str] = None) -> None:
        """初始化结果缓冲器
        
        Args:
            buffer_size: 缓冲区大小，达到后自动写入文件
            temp_dir: 临时文件目录
        """
        if temp_dir is None:
            temp_dir = get_tmp_dir()
        
        self._buffer_size = buffer_size
        self._temp_dir = temp_dir
        self._buffer: List[Dict[str, Any]] = []
        self._seen_urls: Set[str] = set()
        self._seen_titles: Set[str] = set()
        self._total_count = 0
        self._file_count = 0
        self._current_file: Optional[str] = None
        self._lock = threading.Lock()  # AUDIT-0020: 保护 _buffer/_seen_urls/_seen_titles/_file_count
        
        logger.info(f"结果缓冲器初始化完成，缓冲区大小={buffer_size}")
    
    def _generate_file_name(self) -> str:
        """生成临时文件名"""
        self._file_count += 1
        return os.path.join(self._temp_dir, f"crawl_result_{self._file_count:04d}.json")
    
    def _write_buffer(self) -> None:
        """将缓冲区写入临时文件"""
        with self._lock:
            if not self._buffer:
                return

            if self._current_file is None:
                self._current_file = self._generate_file_name()

            buf_snapshot = self._buffer[:]
            out_path = self._current_file
            self._buffer = []
            self._current_file = None

        try:
            with open(out_path, "a", encoding="utf-8") as f:
                for item in buf_snapshot:
                    f.write(json.dumps(item, ensure_ascii=False) + "\n")

            logger.debug(f"缓冲区写入文件: {out_path}, 数量={len(buf_snapshot)}")

        except Exception as e:
            error_logger.error(f"缓冲区写入失败: {e}")

    def add(self, item: Dict[str, Any]) -> bool:
        """添加一条爬取结果

        Args:
            item: 爬取结果字典

        Returns:
            True表示添加成功，False表示已去重
        """
        with self._lock:
            source_url = item.get("source_url", "")
            title = item.get("title", "")

            # URL 去重
            if source_url and source_url in self._seen_urls:
                logger.debug(f"URL 已存在，跳过: {source_url[:50]}...")
                return False

            # 标题去重（使用 MD5）
            if title:
                title_hash = hashlib.md5(title.encode("utf-8")).hexdigest()
                if title_hash in self._seen_titles:
                    logger.debug(f"标题已存在，跳过: {title[:30]}...")
                    return False
                self._seen_titles.add(title_hash)

            if source_url:
                self._seen_urls.add(source_url)

            self._buffer.append(item)
            self._total_count += 1

            need_flush = len(self._buffer) >= self._buffer_size

        # 达到缓冲区大小，写入文件（写 IO 放在锁外）
        if need_flush:
            self._write_buffer()

        return True
    
    def add_batch(self, items: List[Dict[str, Any]]) -> int:
        """批量添加爬取结果
        
        Args:
            items: 爬取结果列表
        
        Returns:
            实际添加的数量（去重后）
        """
        count = 0
        for item in items:
            if self.add(item):
                count += 1
        return count
    
    def flush(self) -> None:
        """强制刷新缓冲区，写入所有剩余数据"""
        self._write_buffer()
        logger.info(f"缓冲区刷新完成，总记录数={self._total_count}")
    
    def get_all_results(self) -> List[Dict[str, Any]]:
        """读取所有临时文件中的结果

        读完后删除所有临时文件（AUDIT-0020：之前文件只增不减，会持续累积到人工清理）。

        Returns:
            所有爬取结果列表
        """
        self.flush()

        results = []
        files_to_delete: List[str] = []

        with self._lock:
            max_file_num = self._file_count

        for file_num in range(1, max_file_num + 1):
            file_path = os.path.join(self._temp_dir, f"crawl_result_{file_num:04d}.json")
            if os.path.exists(file_path):
                try:
                    with open(file_path, "r", encoding="utf-8") as f:
                        for line in f:
                            line = line.strip()
                            if line:
                                results.append(json.loads(line))
                    files_to_delete.append(file_path)
                except Exception as e:
                    error_logger.error(f"读取临时文件失败: {file_path}, error={e}")

        # 统一删除已读完的临时文件
        for fp in files_to_delete:
            try:
                os.remove(fp)
            except Exception:
                pass

        # 重置文件计数
        with self._lock:
            self._file_count = 0

        return results
    
    def save_progress(self, url: str, page: int) -> None:
        """保存爬取进度（用于断点续爬）
        
        Args:
            url: 当前爬取的 URL
            page: 当前页码
        """
        progress = {
            "url": url,
            "page": page,
            "timestamp": time.time(),
            "total_count": self._total_count,
        }
        
        try:
            progress_file = os.path.join(self._temp_dir, "crawl_progress.json")
            with open(progress_file, "w", encoding="utf-8") as f:
                json.dump(progress, f, ensure_ascii=False, indent=2)
        except Exception as e:
            error_logger.error(f"保存进度失败: {e}")
    
    def load_progress(self) -> Optional[Dict[str, Any]]:
        """加载爬取进度（用于断点续爬）
        
        Returns:
            进度信息，无进度时返回 None
        """
        progress_file = os.path.join(self._temp_dir, "crawl_progress.json")
        if os.path.exists(progress_file):
            try:
                with open(progress_file, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                error_logger.error(f"加载进度失败: {e}")
        
        return None
    
    def clear_progress(self) -> None:
        """清除进度文件"""
        progress_file = os.path.join(self._temp_dir, "crawl_progress.json")
        if os.path.exists(progress_file):
            os.remove(progress_file)
    
    def clear(self) -> None:
        """清空所有缓冲区数据"""
        self._buffer = []
        self._seen_urls.clear()
        self._seen_titles.clear()
        self._total_count = 0
        
        file_count_to_delete = self._file_count
        self._file_count = 0
        self._current_file = None
        
        # 删除临时文件
        for file_num in range(1, file_count_to_delete + 1):
            file_path = os.path.join(self._temp_dir, f"crawl_result_{file_num:04d}.json")
            if os.path.exists(file_path):
                os.remove(file_path)
        
        self.clear_progress()
    
    @property
    def total_count(self) -> int:
        """获取总记录数"""
        return self._total_count
    
    @property
    def buffer_size(self) -> int:
        """获取缓冲区大小"""
        return self._buffer_size
    
    @property
    def seen_urls(self) -> Set[str]:
        """获取已访问的 URL 集合"""
        return self._seen_urls


# =====================================================
# 分页策略枚举 - PaginationStrategy
# =====================================================

class PaginationStrategy:
    """分页策略类"""
    
    @staticmethod
    def url_param(base_url: str, page: int, param_name: str = "page") -> str:
        """URL 参数分页（如 ?page=1）
        
        Args:
            base_url: 基础 URL
            page: 页码
            param_name: 参数名
        
        Returns:
            分页 URL
        """
        if "?" in base_url:
            return f"{base_url}&{param_name}={page}"
        else:
            return f"{base_url}?{param_name}={page}"
    
    @staticmethod
    def path_segment(base_url: str, page: int) -> str:
        """路径分段分页（如 /page/1）
        
        Args:
            base_url: 基础 URL
            page: 页码
        
        Returns:
            分页 URL
        """
        # 移除末尾的斜杠
        base_url = base_url.rstrip("/")
        return f"{base_url}/page/{page}"
    
    @staticmethod
    def offset_limit(base_url: str, page: int, limit: int = 20) -> str:
        """偏移量分页（如 ?offset=0&limit=20）
        
        Args:
            base_url: 基础 URL
            page: 页码
            limit: 每页条数
        
        Returns:
            分页 URL
        """
        offset = (page - 1) * limit
        if "?" in base_url:
            return f"{base_url}&offset={offset}&limit={limit}"
        else:
            return f"{base_url}?offset={offset}&limit={limit}"
    
    @staticmethod
    def custom_pattern(base_url: str, page: int, pattern: str = "page-{page}") -> str:
        """自定义模式分页
        
        Args:
            base_url: 基础 URL
            page: 页码
            pattern: 自定义模式，{page} 会被替换为页码
        
        Returns:
            分页 URL
        """
        return base_url + "/" + pattern.replace("{page}", str(page))


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
            def parse(self, html, url):
                # 复制开源爬虫的解析逻辑
                videos = []
                # ... 解析 html，提取视频信息 ...
                return videos
        
        crawler = MyOpenSourceCrawler()
        videos = crawler.crawl("https://example.com")
    """
    
    def __init__(
        self,
        engine: Optional[FingerprintCrawler] = None,
        buffer_size: int = 100,
        enable_buffer: bool = True
    ) -> None:
        """初始化适配器
        
        Args:
            engine: 指纹爬虫引擎，默认自动创建
            buffer_size: 结果缓冲区大小
            enable_buffer: 是否启用结果缓冲
        """
        if engine is None:
            engine = FingerprintCrawler()
        
        self._engine = engine
        self._logger = get_crawler_logger()
        self._enable_buffer = enable_buffer
        
        if enable_buffer:
            self._result_buffer = ResultBuffer(buffer_size)
        else:
            self._result_buffer = None
    
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
        filter_languages: Optional[List[LanguageType]] = None,
        use_buffer: bool = True
    ) -> List[Dict[str, Any]]:
        """
        爬取页面并解析视频信息
        
        Args:
            url: 目标 URL
            headers: 请求头
            params: URL 参数
            filter_languages: 语言白名单，过滤非目标语言视频
            use_buffer: 是否使用结果缓冲
        
        Returns:
            视频信息列表
        """
        try:
            self._logger.info(f"开始爬取: {url}")
            
            html = self._engine.get(url, headers=headers, params=params)
            
            if html is None:
                self._logger.error(f"获取页面失败: {url}")
                return []
            
            videos = self.parse(html, url)
            self._logger.info(f"解析完成，获取 {len(videos)} 个视频")
            
            if filter_languages:
                videos = self._filter_by_language(videos, filter_languages)
            
            # 写入缓冲区
            if use_buffer and self._result_buffer:
                added_count = self._result_buffer.add_batch(videos)
                self._logger.info(f"添加到缓冲区 {added_count} 条（去重后）")
                return videos
            
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
        pagination_strategy: Callable[[str, int], str] = PaginationStrategy.url_param,
        resume_from_progress: bool = False,
        use_buffer: bool = True
    ) -> List[Dict[str, Any]]:
        """
        分页爬取（增强版）
        
        功能：
            - 支持多种分页策略
            - 支持断点续爬
            - 支持结果缓冲
            - 支持去重
        
        Args:
            base_url: 基础 URL
            max_pages: 最大页数
            headers: 请求头
            params: URL 参数
            filter_languages: 语言白名单
            pagination_strategy: 分页策略函数
            resume_from_progress: 是否从断点恢复
            use_buffer: 是否使用结果缓冲
        
        Returns:
            所有页面的视频信息列表
        """
        all_videos = []
        start_page = 1
        current_url = base_url
        
        # 尝试从断点恢复
        if resume_from_progress and self._result_buffer:
            progress = self._result_buffer.load_progress()
            if progress:
                start_page = progress.get("page", 1) + 1
                current_url = progress.get("url", base_url)
                self._logger.info(f"从断点恢复，从第 {start_page} 页开始")
        
        try:
            for page in range(start_page, max_pages + 1):
                self._logger.info(f"爬取第 {page}/{max_pages} 页: {current_url}")
                
                videos = self.crawl(
                    current_url,
                    headers=headers,
                    params=params,
                    filter_languages=filter_languages,
                    use_buffer=use_buffer
                )
                all_videos.extend(videos)
                
                # 保存进度
                if self._result_buffer:
                    self._result_buffer.save_progress(current_url, page)
                
                # 检查是否需要停止
                if len(videos) == 0:
                    self._logger.info("当前页无视频，可能已到达最后一页")
                    break
                
                # 获取下一页 URL
                if page < max_pages:
                    try:
                        current_url = pagination_strategy(base_url, page + 1)
                    except Exception as e:
                        self._logger.warning(f"生成下一页 URL 失败: {e}")
                        break
                    
                    # 分页间隔
                    self._engine._add_delay()
                else:
                    break
            
            # 刷新缓冲区
            if self._result_buffer:
                self._result_buffer.flush()
                self._result_buffer.clear_progress()
            
            self._logger.info(f"分页爬取完成，共获取 {len(all_videos)} 个视频")
            return all_videos
        
        except Exception as e:
            error_logger.error(f"分页爬取失败: {e}")
            return all_videos
    
    def crawl_with_ajax(
        self,
        base_url: str,
        api_url: str,
        max_pages: int = 10,
        headers: Optional[Dict[str, str]] = None,
        params: Optional[Dict[str, Any]] = None,
        filter_languages: Optional[List[LanguageType]] = None,
        page_param_name: str = "page",
        use_buffer: bool = True
    ) -> List[Dict[str, Any]]:
        """
        AJAX 分页爬取（针对动态加载的页面）
        
        Args:
            base_url: 基础页面 URL
            api_url: AJAX API URL
            max_pages: 最大页数
            headers: 请求头
            params: 额外的 API 参数
            filter_languages: 语言白名单
            page_param_name: 页码参数名
            use_buffer: 是否使用结果缓冲
        
        Returns:
            所有页面的视频信息列表
        """
        all_videos = []
        
        try:
            for page in range(1, max_pages + 1):
                self._logger.info(f"爬取第 {page}/{max_pages} 页 (AJAX): {api_url}")
                
                # 构建 API 请求参数
                api_params = {page_param_name: page}
                if params:
                    api_params.update(params)
                
                # 获取 API 数据
                html = self._engine.get(api_url, headers=headers, params=api_params)
                
                if html is None:
                    self._logger.error(f"获取 AJAX 数据失败: {api_url}")
                    break
                
                videos = self.parse(html, api_url)
                self._logger.info(f"AJAX 解析完成，获取 {len(videos)} 个视频")
                
                if filter_languages:
                    videos = self._filter_by_language(videos, filter_languages)
                
                if use_buffer and self._result_buffer:
                    self._result_buffer.add_batch(videos)
                
                all_videos.extend(videos)
                
                if len(videos) == 0:
                    self._logger.info("AJAX 返回空数据，可能已到达最后一页")
                    break
                
                self._engine._add_delay()
            
            if self._result_buffer:
                self._result_buffer.flush()
            
            self._logger.info(f"AJAX 分页爬取完成，共获取 {len(all_videos)} 个视频")
            return all_videos
        
        except Exception as e:
            error_logger.error(f"AJAX 分页爬取失败: {e}")
            return all_videos
    
    def _filter_by_language(
        self,
        videos: List[Dict[str, Any]],
        allowed_languages: List[LanguageType],
        threshold: float = 0.3
    ) -> List[Dict[str, Any]]:
        """按语言过滤视频"""
        try:
            from utils.language_check import is_video_language_allowed
            
            filtered = []
            for video in videos:
                title = video.get("title", "")
                description = video.get("description", "")
                
                if is_video_language_allowed(title, description, allowed_languages, threshold):
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
    
    @property
    def engine(self) -> FingerprintCrawler:
        """获取底层爬虫引擎"""
        return self._engine
    
    @property
    def result_buffer(self) -> Optional[ResultBuffer]:
        """获取结果缓冲器"""
        return self._result_buffer


# =====================================================
# 通用爬虫实现 - GenericCrawler
# =====================================================

class GenericCrawler(CrawlerAdapter):
    """
    通用爬虫实现
    
    提供基础的页面解析能力，可作为接入开源爬虫的起点。
    用户可以继承此类并覆盖 parse 方法。
    """
    
    def __init__(
        self,
        engine: Optional[FingerprintCrawler] = None,
        buffer_size: int = 100,
        enable_buffer: bool = True
    ) -> None:
        """初始化通用爬虫"""
        super().__init__(engine, buffer_size, enable_buffer)
    
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
    """创建指纹爬虫引擎"""
    return FingerprintCrawler(config)


def create_crawler(
    adapter_class: type = GenericCrawler,
    engine: Optional[FingerprintCrawler] = None,
    buffer_size: int = 100,
    enable_buffer: bool = True,
    **kwargs
) -> CrawlerAdapter:
    """创建爬虫适配器"""
    if engine is None:
        engine = FingerprintCrawler()
    
    return adapter_class(engine, buffer_size, enable_buffer, **kwargs)


def create_result_buffer(buffer_size: int = 100) -> ResultBuffer:
    """创建结果缓冲器"""
    return ResultBuffer(buffer_size)


# =====================================================
# 模块初始化
# =====================================================

def init_crawler() -> None:
    """初始化爬虫模块"""
    logger.info("爬虫模块初始化完成")