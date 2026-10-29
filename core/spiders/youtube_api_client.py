"""
YouTube Data API v3 客户端（仅用于语言过滤）

为节省配额，本模块仅调用 search.list 接口获取符合目标语言的视频ID列表，
不调用 videos.list 获取视频详情。视频详情（时长、播放量等）由上层爬虫
抓取视频页面（watch URL）获取。

API 文档：
    - search.list: https://developers.google.com/youtube/v3/docs/search/list

配额消耗：
    - search.list: 100 单位/次
    - 默认配额 10000 单位/天，可支持 100 次搜索/天

设计原则：
    1. 仅做语言过滤（relevanceLanguage + regionCode），不获取视频详情
    2. 完整 try-except 包裹网络请求和 JSON 解析
    3. 配额耗尽（403）时抛出明确异常，供上层回退
    4. 只导入 utils 层，遵守分层依赖规范

注意：
    YouTube Data API v3 的 search.list 接口必须提供 q 参数才能返回结果，
    否则返回空。本模块使用语言中性的单字符（如 a/e/i）作为 q 参数，
    配合 regionCode 和 relevanceLanguage 实现按地区和语言过滤，
    不引入任何主题偏好。
"""

import random
from typing import Optional, Dict, List, Any, Tuple
from utils.youtube_url import build_watch_url  # AUDIT-0051

import requests as std_requests

from utils.crypto_util import load_secret_config
from utils.logger import get_crawler_logger, get_error_logger


logger = get_crawler_logger()
error_logger = get_error_logger()


# ============================================================
# YouTube 视频分类 ID → ASR 友好度映射
#
# ASR 不友好分类（直接过滤）：
#   - 10: Music（音乐，核心过滤目标，99% 是纯音乐/MV）
#   - 20: Gaming（游戏，大量背景音效+BGM，ASR 识别率极低）
#   - 30/31/32/.../44: Movies/Shows 等影视类（非日常教学语言）
# ASR 存疑分类（结合标题关键词二次判断）：
#   - 24: Entertainment（娱乐：可能混有演唱会、脱口秀、综艺片段）
#   - 1: Film & Animation（影视动画：非日常对话场景居多）
#
# 配额消耗：videos.list 1 单位/次，批量查询最多50个videoId仅消耗1单位
# ============================================================
YOUTUBE_CATEGORY_ASR_HOSTILE: set = {
    # Music - 音乐类（最高优先级，ASR 99% 无对白）
    "10",
    # Gaming - 游戏类（大量BGM+音效，对白少且被淹没）
    "20",
    # 影视类（非日常教学语言，多为剧本台词/配音，非真实口语）
    "30",  # Movies
    "31",  # Anime/Animation
    "32",  # Action/Adventure
    "33",  # Classics
    "34",  # Comedy (影视类喜剧，不同于 stand-up)
    "35",  # Documentary (影视纪录片，多旁白+配乐)
    "36",  # Drama
    "37",  # Family
    "38",  # Foreign
    "39",  # Horror
    "40",  # Sci-Fi/Fantasy
    "41",  # Thriller
    "42",  # Shorts
    "43",  # Shows
    "44",  # Trailers
}

# ASR 存疑分类：需结合标题关键词二次判断（非必过滤）
YOUTUBE_CATEGORY_ASR_SUSPICIOUS: set = {
    "24",  # Entertainment - 娱乐（演唱会/综艺/脱口秀混在一起）
    "1",   # Film & Animation - 影视动画
}


# 各语言对应的地区代码（regionCode）和界面语言代码（relevanceLanguage）
# YouTube Data API 通过这两个参数严格按地区和语言过滤内容
# 复用 YoutubeSpider.LANGUAGE_REGION 的映射关系
LANGUAGE_REGION_MAP: Dict[str, Tuple[str, str]] = {
    "en": ("US", "en"),
    "de": ("DE", "de"),
    "fr": ("FR", "fr"),
    "es": ("ES", "es"),
    "it": ("IT", "it"),
    "pt": ("BR", "pt"),
    "ru": ("RU", "ru"),
    "ja": ("JP", "ja"),
    "ko": ("KR", "ko"),
    "ar": ("EG", "ar"),
    "zh": ("CN", "zh"),
    # 其他语言默认走 US/en，由调用方决定是否接受
}

# YouTube Data API search.list 端点
_SEARCH_URL = "https://www.googleapis.com/youtube/v3/search"

# YouTube Data API videos.list 端点（获取视频详情，含 categoryId）
_VIDEOS_URL = "https://www.googleapis.com/youtube/v3/videos"

# API 单次请求最大返回数量（YouTube 限制上限 50）
_MAX_RESULTS_PER_REQUEST = 50

# 请求超时时间（秒）
_REQUEST_TIMEOUT = 15

# 各语言的高频功能词查询字符（不引入主题偏好）
# YouTube search.list 必须提供 q 参数才能返回结果，
# 使用目标语言的高频功能词（冠词、代词、介词）作为查询字符，
# 这些词是该语言的基本组成成分，不引入任何主题偏好，
# 但能显著提高目标语言视频的召回率。
# 对于未列出的语言，回退到通用元音字母。
_LANGUAGE_QUERIES: Dict[str, List[str]] = {
    "fr": ["le", "la", "les", "une", "des", "dans", "pour", "avec", "sur", "par", "vous", "nous"],
    "de": ["der", "die", "das", "ein", "eine", "und", "mit", "von", "für", "auf", "nicht", "ist"],
    "es": ["el", "la", "los", "las", "una", "unos", "con", "por", "para", "que", "esto", "eso"],
    "it": ["il", "la", "le", "uno", "una", "con", "per", "che", "questo", "quello", "sono", "sono"],
    "pt": ["o", "a", "os", "as", "uma", "com", "por", "para", "que", "este", "esse", "não"],
    "ru": ["и", "в", "не", "на", "я", "что", "это", "как", "для", "это"],
    "ja": ["の", "に", "は", "を", "が", "で", "と", "から"],
    "ko": ["의", "에", "는", "을", "가", "로", "와", "하고"],
    "ar": ["في", "من", "على", "إلى", "أن", "هذا", "التي", "الذي"],
    "zh": ["的", "是", "在", "了", "有", "和", "就", "不", "都", "而"],
    "en": ["the", "and", "for", "are", "but", "not", "you", "all", "can", "had", "her", "was"],
}

# 通用查询字符（元音字母），用于未列出语言
_FALLBACK_QUERIES = ["a", "e", "i", "o", "u"]

# 排序方式选项（按播放量排序获取热门视频，避免冷门内容）
_ORDER_OPTIONS = ["viewCount", "relevance"]


class YouTubeAPIClient:
    """
    YouTube Data API v3 客户端封装（仅语言过滤）

    功能：
        1. 从加密配置加载 API 密钥
        2. 调用 search.list 接口按语言过滤获取视频ID列表
        3. 不调用 videos.list，详情由上层爬虫抓取视频页面获取

    使用示例：
        client = YouTubeAPIClient()
        if client.is_available():
            videos = client.search_video_ids_by_language("fr", max_results=50)
    """

    def __init__(self) -> None:
        """初始化客户端，加载加密存储的 API 密钥

        从 api_secret.yaml.enc 读取 youtube_api_key 字段，
        若密钥不存在或加载失败，is_available() 返回 False。
        """
        self._api_key: Optional[str] = None
        self._session: std_requests.Session = std_requests.Session()

        try:
            secret = load_secret_config()
            self._api_key = secret.get("youtube_api_key")
            if self._api_key:
                logger.info("YouTube Data API v3 密钥已加载")
            else:
                logger.warning("api_secret.yaml.enc 中未找到 youtube_api_key")
        except Exception as e:
            error_logger.error(f"加载 YouTube API 密钥失败: {e}")
            self._api_key = None

    def is_available(self) -> bool:
        """API 客户端是否可用（密钥已配置）

        Returns:
            True 表示密钥已加载，可调用 API；False 表示密钥未配置
        """
        return self._api_key is not None

    def search_video_ids_by_language(
        self,
        language_code: str,
        max_results: int = 50,
        target_count: Optional[int] = None,
        exclude_ids: Optional[set] = None,
        max_search_pages: int = 8,
    ) -> List[Dict[str, Any]]:
        """按语言搜索视频ID列表（支持分页/换关键词/排除已知ID，保证召回率）

        调用 YouTube Data API v3 的 search.list 接口，
        通过 relevanceLanguage 和 regionCode 参数实现严格的语言过滤。

        由于 YouTube search.list 接口必须提供 q 参数才能返回结果，
        本方法使用语言中性的单字符（随机选择）作为 q 参数，
        不引入任何主题偏好，纯靠地区和语言参数过滤。
        同时支持自动翻页（nextPageToken）和多关键词轮询，在"第一页全是老视频"时
        会继续翻页/换词寻找新视频，直到凑够 target_count 或触达配额预算上限。

        Args:
            language_code: 语言代码（如 fr/de/es），需在 LANGUAGE_REGION_MAP 中
            max_results: 每页最大返回数量（YouTube 上限 50，保留此参数兼容旧调用）
            target_count: 期望召回的新视频数量（不含 exclude_ids）；默认=max_results。
                当语言过滤 + exclude_ids 淘汰较多时，会自动分页/换词继续找。
            exclude_ids: 本次搜索**直接跳过**的 YouTube video_id 集合（通常是数据库
                已有的历史记录），避免一页返回 50 条全是"已存在"的视频。
            max_search_pages: 最多调用 search.list 次数（每次约 100 单位配额）。
                默认 8 次 = 800 配额（每日配额约 1/12，安全）。

        Returns:
            轻量视频信息列表，每项包含：
            - video_id (str): YouTube 视频ID
            - source_url (str): 视频完整 URL
            - title (str): 视频标题
            - description (str): 视频描述
            - thumbnail (str): 缩略图 URL
            - author (str): 频道名
            - published_at (str): 发布时间（ISO 8601）
            不包含 duration（由爬虫抓取页面后补充）

        Raises:
            RuntimeError: API 密钥未配置
            RuntimeError: API 调用失败（配额耗尽、网络错误等）
        """
        if not self._api_key:
            raise RuntimeError("YouTube API 密钥未配置，无法调用 search.list")

        if target_count is None or target_count <= 0:
            target_count = max_results

        # 每页最大返回数量
        max_results = min(max_results, _MAX_RESULTS_PER_REQUEST)

        # 获取地区代码和语言代码
        region_code, relevance_language = LANGUAGE_REGION_MAP.get(
            language_code, ("US", "en")
        )

        # 准备查询关键词池（打乱顺序，增加多样性）
        query_pool = list(_LANGUAGE_QUERIES.get(language_code, _FALLBACK_QUERIES))
        random.shuffle(query_pool)

        # 两种 order 轮流尝试
        order_pool = list(_ORDER_OPTIONS)
        random.shuffle(order_pool)

        exclude_ids = exclude_ids or set()
        seen_ids: set = set(exclude_ids)  # 同时排除历史 + 本次分页内重复
        result: List[Dict[str, Any]] = []
        pages_done = 0
        query_idx = 0
        order_idx = 0
        # 对同一个 (query, order) 做分页；换词时重置 nextPageToken
        next_page_token: Optional[str] = None
        # 连续 N 页"没有任何新增 id"时，判定当前 (query, order) 池子已枯竭，换词
        _STALE_PAGES_PER_QUERY = 2
        stale_pages = 0

        logger.info(
            f"[API search] 语言={language_code} target_count={target_count} "
            f"exclude_ids={len(exclude_ids)} max_search_pages={max_search_pages}"
        )

        while (
            pages_done < max_search_pages
            and len(result) < target_count
            and query_idx < len(query_pool)
        ):
            query_char = query_pool[query_idx]
            order = order_pool[order_idx % len(order_pool)]

            params = {
                "key": self._api_key,
                "part": "snippet",
                "type": "video",
                "q": query_char,
                "relevanceLanguage": relevance_language,
                "regionCode": region_code,
                "order": order,
                "maxResults": max_results,
            }
            if next_page_token:
                params["pageToken"] = next_page_token

            try:
                logger.info(
                    f"[API search] page #{pages_done + 1}/{max_search_pages} "
                    f"q='{query_char}' order={order} pageToken={'yes' if next_page_token else 'no'}"
                )
                response = self._session.get(
                    _SEARCH_URL, params=params, timeout=_REQUEST_TIMEOUT
                )
                self._handle_api_error(response)
                data = response.json()
                pages_done += 1
            except std_requests.RequestException as e:
                error_logger.error(f"YouTube Data API 网络请求失败: {e}")
                raise RuntimeError(f"API 网络请求失败: {e}")
            except Exception as e:
                error_logger.error(f"YouTube Data API 调用失败: {e}")
                raise RuntimeError(f"API 调用失败: {e}")

            items = data.get("items", []) or []
            page_ids_before = len(seen_ids)
            for item in items:
                v = self._parse_search_item(item)
                if not v:
                    continue
                vid = v.get("video_id", "")
                if not vid or vid in seen_ids:
                    continue
                seen_ids.add(vid)
                result.append(v)

            page_new = len(seen_ids) - page_ids_before
            logger.info(
                f"[API search] 本页返回 {len(items)} 条 -> 新增 {page_new} "
                f"(排除 exclude/重复). 累计结果 {len(result)}/{target_count}"
            )

            if len(result) >= target_count:
                break

            # 取下一页：如果 YouTube 返回 nextPageToken 继续同词翻页
            next_token = data.get("nextPageToken") or None
            if page_new <= 0:
                stale_pages += 1
            else:
                stale_pages = 0

            if next_token and stale_pages < _STALE_PAGES_PER_QUERY:
                next_page_token = next_token
                continue

            # 没有下一页 / 连续两页都无新增 -> 换 query/order
            next_page_token = None
            stale_pages = 0
            query_idx += 1
            if query_idx % len(order_pool) == 0:
                order_idx += 1

        logger.info(
            f"[API search] 结束: {len(result)} 条 (target={target_count}), "
            f"调用 search.list {pages_done}/{max_search_pages} 次"
            f"（配额消耗约 {pages_done * 100} 单位）"
        )
        return result

    def _parse_search_item(self, item: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """解析 search.list 返回的单个视频项

        Args:
            item: API 返回的单个 item 字典

        Returns:
            标准化的视频信息字典，解析失败返回 None
        """
        try:
            video_id = item.get("id", {}).get("videoId", "")
            if not video_id:
                return None

            snippet = item.get("snippet", {})

            # 提取缩略图（优先取高分辨率）
            thumbnails = snippet.get("thumbnails", {})
            thumbnail = (
                thumbnails.get("high", {}).get("url")
                or thumbnails.get("medium", {}).get("url")
                or thumbnails.get("default", {}).get("url", "")
            )

            return {
                "video_id": video_id,
                "source_url": build_watch_url(video_id),
                "title": snippet.get("title", ""),
                "description": snippet.get("description", ""),
                "thumbnail": thumbnail,
                "author": snippet.get("channelTitle", ""),
                "published_at": snippet.get("publishedAt", ""),
            }
        except Exception as e:
            logger.warning(f"解析 search.list item 失败: {e}")
            return None

    def _handle_api_error(self, response: std_requests.Response) -> None:
        """统一处理 YouTube Data API 错误响应

        Args:
            response: requests.Response 对象

        Raises:
            RuntimeError: API 返回错误（含详细错误信息）
        """
        if response.status_code == 200:
            return

        # 解析错误响应体
        error_detail = "未知错误"
        try:
            data = response.json()
            error_obj = data.get("error", {})
            error_detail = error_obj.get("message", error_detail)
            error_reason = error_obj.get("errors", [{}])[0].get("reason", "")
        except Exception:
            error_detail = response.text[:200]

        # 根据状态码分类处理
        if response.status_code == 403:
            # 配额耗尽或密钥无效
            if "quota" in error_detail.lower() or "quotaExceeded" in error_reason:
                error_logger.error(
                    f"YouTube Data API 配额耗尽（403）: {error_detail}"
                )
                raise RuntimeError(f"API 配额耗尽: {error_detail}")
            else:
                error_logger.error(
                    f"YouTube Data API 密钥无效或权限不足（403）: {error_detail}"
                )
                raise RuntimeError(f"API 密钥无效或权限不足: {error_detail}")
        elif response.status_code == 400:
            error_logger.error(
                f"YouTube Data API 请求参数错误（400）: {error_detail}"
            )
            raise RuntimeError(f"API 请求参数错误: {error_detail}")
        else:
            error_logger.error(
                f"YouTube Data API 调用失败（HTTP {response.status_code}）: {error_detail}"
            )
            raise RuntimeError(
                f"API 调用失败（HTTP {response.status_code}）: {error_detail}"
            )

    def get_video_category_ids(
        self,
        video_ids: List[str]
    ) -> Dict[str, str]:
        """批量获取视频的 YouTube 分类 ID（categoryId）

        调用 videos.list 接口，part=snippet，批量获取 videoId → categoryId 映射。
        配额消耗极低：**每次调用仅 1 单位配额**，一次最多可查 50 个 videoId。
        （相比 search.list 的 100 单位配额，成本仅为 1%）

        使用场景：
            1. 在下载前按 categoryId 过滤 ASR 不友好分类（Music=10, Gaming=20 等）
            2. 对存疑分类（Entertainment=24 等）结合标题关键词做二次判断

        Args:
            video_ids: YouTube 视频 ID 列表（最多 50 个，超出会自动分批）

        Returns:
            Dict[video_id: str, category_id: str]
            - key: video_id（与入参一致）
            - value: categoryId（如 "10"=Music, "27"=Education）；
              API 返回空或无 categoryId 的视频，value 为空字符串 ""
            - 失败/异常时返回空 Dict（上层不阻塞，仅记录日志）

        Raises:
            不抛出异常，所有错误内部吞掉并返回空 Dict（降级到仅关键词过滤）
        """
        if not self._api_key:
            logger.warning("YouTube API 密钥未配置，跳过 videos.list categoryId 查询")
            return {}

        if not video_ids:
            return {}

        # 去重
        unique_ids: List[str] = list(dict.fromkeys(video_ids))
        result: Dict[str, str] = {}

        # videos.list 单次最多接受 50 个 id（用逗号分隔）
        batch_size = _MAX_RESULTS_PER_REQUEST
        total_batches = (len(unique_ids) + batch_size - 1) // batch_size

        logger.info(
            f"调用 YouTube Data API videos.list 获取 categoryId: "
            f"{len(unique_ids)} 个视频，分 {total_batches} 批（配额约 {total_batches} 单位）"
        )

        for batch_idx in range(total_batches):
            batch = unique_ids[batch_idx * batch_size : (batch_idx + 1) * batch_size]
            ids_csv = ",".join(batch)
            params = {
                "key": self._api_key,
                "part": "id,snippet",
                "id": ids_csv,
                "maxResults": batch_size,
                "fields": "items(id,snippet(categoryId))",  # 只取必要字段，省带宽
            }
            try:
                response = self._session.get(
                    _VIDEOS_URL, params=params, timeout=_REQUEST_TIMEOUT
                )
                self._handle_api_error(response)

                data = response.json()
                items = data.get("items", [])
                for item in items:
                    vid = item.get("id", "")
                    category_id = item.get("snippet", {}).get("categoryId", "")
                    if vid:
                        result[vid] = str(category_id) if category_id else ""

                logger.debug(
                    f"videos.list 批次 {batch_idx + 1}/{total_batches} 完成，"
                    f"本批 {len(batch)} 个返回 {len(items)} 条"
                )

            except std_requests.RequestException as e:
                error_logger.error(f"videos.list 网络请求失败（批次 {batch_idx + 1}）: {e}")
                # 某批失败不影响其他批，继续
            except RuntimeError:
                # _handle_api_error 已记日志，继续
                pass
            except Exception as e:
                error_logger.error(f"videos.list 解析失败（批次 {batch_idx + 1}）: {e}")

        logger.info(
            f"videos.list categoryId 获取完成：共查询 {len(unique_ids)} 个，"
            f"成功 {len([v for v in result.values() if v])} 个"
        )
        return result

    def get_video_snippets(
        self,
        video_ids: List[str]
    ) -> Dict[str, Dict[str, str]]:
        """批量获取视频的 snippet 信息（title, description, channelTitle）

        配额：每次 1 单位，一次最多 50 个 videoId。

        Args:
            video_ids: YouTube 视频 ID 列表

        Returns:
            Dict[video_id, {title: str, description: str, channel_title: str}]
            - 失败/异常时返回空 Dict（不抛异常）
        """
        if not self._api_key or not video_ids:
            return {}

        unique_ids: List[str] = list(dict.fromkeys(video_ids))
        result: Dict[str, Dict[str, str]] = {}

        batch_size = _MAX_RESULTS_PER_REQUEST
        total_batches = (len(unique_ids) + batch_size - 1) // batch_size

        for batch_idx in range(total_batches):
            batch = unique_ids[batch_idx * batch_size : (batch_idx + 1) * batch_size]
            ids_csv = ",".join(batch)
            params = {
                "key": self._api_key,
                "part": "id,snippet",
                "id": ids_csv,
                "maxResults": batch_size,
                "fields": "items(id,snippet(title,description,channelTitle))",
            }
            try:
                response = self._session.get(
                    _VIDEOS_URL, params=params, timeout=_REQUEST_TIMEOUT
                )
                self._handle_api_error(response)

                for item in response.json().get("items", []):
                    vid = item.get("id", "")
                    snippet = item.get("snippet", {})
                    if vid:
                        result[vid] = {
                            "title": snippet.get("title", ""),
                            "description": snippet.get("description", ""),
                            "channel_title": snippet.get("channelTitle", ""),
                        }
            except std_requests.RequestException as e:
                error_logger.error(f"videos.list snippet 网络请求失败: {e}")
            except RuntimeError:
                pass
            except Exception as e:
                error_logger.error(f"videos.list snippet 解析失败: {e}")

        return result

    # ============================================================
    # 关键词 / 频道 / 播放列表 搜索（新增：WebUI 「搜索模式」Tab 支撑）
    # ============================================================

    def search_by_keyword(
        self,
        keyword: str,
        language_code: str = "en",
        max_results: int = 50,
        target_count: Optional[int] = None,
        exclude_ids: Optional[set] = None,
        max_search_pages: int = 8,
        order: str = "relevance",
    ) -> List[Dict[str, Any]]:
        """按关键词搜索视频（与语言过滤版并行的新入口）

        Args:
            keyword: 搜索关键词（会作为 search.list 的 q 参数）
            language_code: 可选的语言/地区过滤
            max_results: 每页返回数（≤50）
            target_count: 期望召回的新视频数（不含 exclude_ids）
            exclude_ids: 要跳过的 video_id 集合
            max_search_pages: 最多翻页次数（每次 ≈100 配额）
            order: relevance / date / viewCount

        Returns:
            轻量视频信息列表（结构同 search_video_ids_by_language）
        """
        if not self._api_key:
            raise RuntimeError("YouTube API 密钥未配置")
        if not keyword or not keyword.strip():
            return []

        keyword = keyword.strip()
        if target_count is None or target_count <= 0:
            target_count = max_results
        max_results = min(max_results, _MAX_RESULTS_PER_REQUEST)

        region_code, relevance_language = LANGUAGE_REGION_MAP.get(
            language_code, ("US", "en")
        )

        exclude_ids = exclude_ids or set()
        seen_ids: set = set(exclude_ids)
        result: List[Dict[str, Any]] = []
        pages_done = 0
        next_page_token: Optional[str] = None

        logger.info(
            f"[API keyword] q='{keyword}' lang={language_code} "
            f"target={target_count} max_pages={max_search_pages} exclude={len(exclude_ids)}"
        )

        while pages_done < max_search_pages and len(result) < target_count:
            params = {
                "key": self._api_key,
                "part": "snippet",
                "type": "video",
                "q": keyword,
                "relevanceLanguage": relevance_language,
                "regionCode": region_code,
                "order": order,
                "maxResults": max_results,
            }
            if next_page_token:
                params["pageToken"] = next_page_token

            try:
                response = self._session.get(
                    _SEARCH_URL, params=params, timeout=_REQUEST_TIMEOUT
                )
                self._handle_api_error(response)
                data = response.json()
                pages_done += 1
            except std_requests.RequestException as e:
                error_logger.error(f"keyword search 网络失败: {e}")
                raise RuntimeError(f"API 网络请求失败: {e}")
            except RuntimeError:
                raise

            items = data.get("items", []) or []
            for item in items:
                v = self._parse_search_item(item)
                if not v:
                    continue
                vid = v.get("video_id", "")
                if not vid or vid in seen_ids:
                    continue
                seen_ids.add(vid)
                result.append(v)

            logger.info(
                f"[API keyword] page #{pages_done}: {len(items)} items → "
                f"{len(result)}/{target_count}"
            )

            if len(result) >= target_count:
                break

            next_page_token = data.get("nextPageToken") or None
            if not next_page_token:
                break

        logger.info(
            f"[API keyword] 结束: {len(result)} 条，search.list {pages_done}/{max_search_pages} 次"
        )
        return result

    def search_channel_videos(
        self,
        channel_id: str,
        target_count: int = 20,
        exclude_ids: Optional[set] = None,
        max_search_pages: int = 6,
        order: str = "date",
    ) -> List[Dict[str, Any]]:
        """按 channelId 抓取频道最新视频

        Args:
            channel_id: YouTube 频道 ID（如 UCxxx...）
            target_count: 期望视频数量
            exclude_ids: 要跳过的 video_id 集合
            max_search_pages: 最多翻页数
            order: date（最新）/ viewCount（最热门）

        Returns:
            轻量视频信息列表
        """
        if not self._api_key:
            raise RuntimeError("YouTube API 密钥未配置")
        if not channel_id:
            return []

        exclude_ids = exclude_ids or set()
        seen_ids: set = set(exclude_ids)
        result: List[Dict[str, Any]] = []
        pages_done = 0
        next_page_token: Optional[str] = None
        max_results = min(50, max(target_count, 20))

        logger.info(
            f"[API channel] id={channel_id} target={target_count} order={order}"
        )

        while pages_done < max_search_pages and len(result) < target_count:
            params = {
                "key": self._api_key,
                "part": "snippet",
                "type": "video",
                "channelId": channel_id,
                "order": order,
                "maxResults": max_results,
            }
            if next_page_token:
                params["pageToken"] = next_page_token

            try:
                response = self._session.get(
                    _SEARCH_URL, params=params, timeout=_REQUEST_TIMEOUT
                )
                self._handle_api_error(response)
                data = response.json()
                pages_done += 1
            except std_requests.RequestException as e:
                error_logger.error(f"channel search 网络失败: {e}")
                raise RuntimeError(f"API 网络请求失败: {e}")
            except RuntimeError:
                raise

            items = data.get("items", []) or []
            for item in items:
                v = self._parse_search_item(item)
                if not v:
                    continue
                vid = v.get("video_id", "")
                if not vid or vid in seen_ids:
                    continue
                seen_ids.add(vid)
                result.append(v)

            if len(result) >= target_count:
                break

            next_page_token = data.get("nextPageToken") or None
            if not next_page_token:
                break

        logger.info(
            f"[API channel] 结束: {len(result)} 条, search.list {pages_done} 次"
        )
        return result

    def resolve_channel_id(self, channel_name_or_handle: str) -> Optional[str]:
        """把频道名 / @handle 解析成 channelId

        YouTube API search.list type=channel 可根据频道名找到 channelId。
        若直接传 UCxxx... 格式，原样返回。

        Returns:
            channel_id 字符串或 None
        """
        if not self._api_key:
            return None

        name = (channel_name_or_handle or "").strip()
        if not name:
            return None

        # 已经是 channelId 格式（UC 开头）
        if name.startswith("UC") and len(name) >= 20:
            return name

        # 去掉 @ 前缀
        if name.startswith("@"):
            name = name[1:]

        params = {
            "key": self._api_key,
            "part": "snippet",
            "type": "channel",
            "q": name,
            "maxResults": 5,
        }
        try:
            response = self._session.get(
                _SEARCH_URL, params=params, timeout=_REQUEST_TIMEOUT
            )
            self._handle_api_error(response)
            data = response.json()
            items = data.get("items", []) or []
            if not items:
                logger.warning(f"resolve_channel_id: 未找到频道 '{channel_name_or_handle}'")
                return None
            # 取第一个匹配
            return items[0].get("id", {}).get("channelId")
        except Exception as e:
            logger.warning(f"resolve_channel_id 失败: {e}")
            return None
