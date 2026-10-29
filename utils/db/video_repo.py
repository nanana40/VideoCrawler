"""
utils/db/video_repo.py — video_info 表的 CRUD 实现

AUDIT-0039: 从 db_manager.py 抽出，让 db_manager 只保留连接管理/缓冲池。
调用方统一从 utils.db_manager 引入（db_manager.py 会 re-export）。
"""

import os
import time
from typing import Optional, Dict, List, Any
from utils.logger import get_error_logger
from utils.enums import LanguageType, TaskPriority


# AUDIT-0039: 延迟 import db_manager 避免循环依赖
# db_manager.py 在文件末尾才 import 本模块，所以本模块顶层不能反向 import db_manager
_base = None

def _cursor_to_list(cursor: Any) -> List[Dict[str, Any]]:
    """将游标结果转换为字典列表

    Args:
        cursor: apsw Cursor 对象

    Returns:
        字典列表
    """
    columns = [desc[0] for desc in cursor.getdescription()]
    return [dict(zip(columns, row)) for row in cursor.fetchall()]


def _ensure_base():
    """一次性延迟导入 db_manager 基础设施"""
    global _base
    if _base is None:
        from utils import db_manager as _m
        _base = _m
    return _base


logger = get_error_logger()

def insert_video(
    source_url: str,
    title: str,
    lang: LanguageType,
    category: Optional[str] = None,
    local_video_path: Optional[str] = None,
    is_downloaded: int = 0,
    description: Optional[str] = None,
    thumbnail: Optional[str] = None,
    duration: Optional[str] = None,
    author: Optional[str] = None,
    views: int = 0,
    # === v2 新增字段 ===
    yt_video_id: Optional[str] = None,
    published_at: Optional[str] = None,
    channel_id: Optional[str] = None,
    channel_name: Optional[str] = None,
    sub_category: Optional[str] = None,
    tags: Optional[str] = None,
    yt_category_id: Optional[int] = None,
    series_id: Optional[str] = None,
    related_cluster_id: Optional[str] = None,
) -> bool:
    """插入视频信息（走缓冲池）
    
    Args:
        source_url: 视频源URL
        title: 视频标题
        lang: 视频语种枚举
        category: 视频分类（VideoCategory 枚举值字符串，用于文件归档）
        local_video_path: 本地视频路径
        is_downloaded: 下载标记（0/1）
        description: 视频描述
        thumbnail: 缩略图URL
        duration: 视频时长
        author: 作者名称（频道展示名）
        views: 播放量
        yt_video_id: YouTube video_id
        published_at: 发布时间
        channel_id: 频道/作者平台 ID（用于强相关聚合）
        channel_name: 频道展示名
        sub_category: 细粒度子类（如 talk_show / street_interview）
        tags: JSON 数组字符串，3-6 个社交匹配标签
        yt_category_id: YouTube 官方 category_id
        series_id: 系列/playlist ID
        related_cluster_id: 语义话题聚合桶

    Returns:
        True 表示成功入队（不一定已写入数据库）
    """
    try:
        if not LanguageType.is_valid(lang.value):
            logger.error(f"非法语种: {lang}")
            return False
        
        if is_downloaded not in (0, 1):
            logger.error(f"非法下载标记: {is_downloaded}")
            return False
        
        sql = _ensure_base().SQLStatements.INSERT_VIDEO
        params = (
            source_url, yt_video_id, title, description, thumbnail, duration, published_at,
            author, channel_id, channel_name,
            lang.value, category, sub_category, tags, yt_category_id,
            series_id, related_cluster_id,
            views, local_video_path, is_downloaded,
        )
        
        pool = _ensure_base().get_buffer_pool()
        pool.add(sql, params)
        
        return True
    except Exception as e:
        logger.error(f"插入视频失败: url={source_url[:50]}, error={e}")
        return False


def update_video_downloaded(video_id: int, local_video_path: str) -> bool:
    """更新视频下载状态（走缓冲池）
    
    Args:
        video_id: 视频ID
        local_video_path: 本地视频路径
    
    Returns:
        True 表示成功
    """
    try:
        sql = _ensure_base().SQLStatements.UPDATE_VIDEO_DOWNLOADED
        params = (1, local_video_path, video_id)
        
        pool = _ensure_base().get_buffer_pool()
        pool.add(sql, params)
        
        return True
    except Exception as e:
        logger.error(f"更新视频下载状态失败: id={video_id}, error={e}")
        return False


def update_video_category(video_id: int, category: str) -> bool:
    """更新视频分类（走缓冲池）
    
    Args:
        video_id: 视频ID
        category: 视频分类
    
    Returns:
        True 表示成功
    """
    try:
        sql = _ensure_base().SQLStatements.UPDATE_VIDEO_CATEGORY
        params = (category, video_id)
        
        pool = _ensure_base().get_buffer_pool()
        pool.add(sql, params)
        
        return True
    except Exception as e:
        logger.error(f"更新视频分类失败: id={video_id}, error={e}")
        return False


def get_video_by_url(source_url: str) -> Optional[Dict[str, Any]]:
    """根据URL查询视频（直接查询）
    
    Args:
        source_url: 视频源URL
    
    Returns:
        视频信息字典，不存在返回 None
    """
    try:
        cursor = _ensure_base()._execute_with_retry(_ensure_base().SQLStatements.GET_VIDEO_BY_URL, (source_url,))
        row = cursor.fetchone()
        if row:
            return dict(zip([desc[0] for desc in cursor.getdescription()], row))
        return None
    except Exception as e:
        logger.error(f"查询视频失败: url={source_url[:50]}, error={e}")
        return None


def get_video_by_id(video_id: int) -> Optional[Dict[str, Any]]:
    """根据ID查询视频（直接查询）
    
    Args:
        video_id: 视频ID
    
    Returns:
        视频信息字典，不存在返回 None
    """
    try:
        cursor = _ensure_base()._execute_with_retry(_ensure_base().SQLStatements.GET_VIDEO_BY_ID, (video_id,))
        row = cursor.fetchone()
        if row:
            return dict(zip([desc[0] for desc in cursor.getdescription()], row))
        return None
    except Exception as e:
        logger.error(f"查询视频失败: id={video_id}, error={e}")
        return None


def is_video_downloaded(source_url: str) -> bool:
    """检查视频是否已下载（通过URL检查）
    
    先强制刷新缓冲池确保最新状态，再查询数据库。
    
    Args:
        source_url: 视频源URL
        
    Returns:
        True 表示已下载，False 表示未下载
    """
    try:
        # 先强制刷新缓冲池，确保查询到最新状态
        try:
            pool = _ensure_base().get_buffer_pool()
            pool.flush_now()
        except Exception:
            pass
        
        video = get_video_by_url(source_url)
        if video and video.get("is_downloaded", 0) == 1:
            local_path = video.get("local_video_path", "")
            if local_path and os.path.exists(local_path):
                logger.info(f"视频已下载，跳过: url={source_url[:50]}")
                return True
            elif local_path:
                logger.warning(f"视频已标记下载但文件不存在: url={source_url[:50]}, path={local_path}")
                # 文件不存在但数据库标记已下载，视为需要重新下载
                return False
        return False
    except Exception as e:
        logger.error(f"检查视频是否已下载失败: url={source_url[:50]}, error={e}")
        return False


def get_video_by_source_url(source_url: str) -> Optional[Dict[str, Any]]:
    """根据源URL查询视频完整信息（包含下载状态）
    
    Args:
        source_url: 视频源URL
    
    Returns:
        视频信息字典，不存在返回 None
    """
    try:
        video = get_video_by_url(source_url)
        if video:
            return video
        return None
    except Exception as e:
        logger.error(f"查询视频源URL失败: url={source_url[:50]}, error={e}")
        return None


def get_undownloaded_videos() -> List[Dict[str, Any]]:
    """获取未下载视频列表（直接查询）
    
    Returns:
        视频信息字典列表
    """
    try:
        conn = _ensure_base()._get_connection()
        cursor = conn.cursor()
        cursor.execute(_ensure_base().SQLStatements.GET_UNDOWNLOADED_VIDEOS)
        
        columns = [desc[0] for desc in cursor.getdescription()]
        result = [dict(zip(columns, row)) for row in cursor.fetchall()]
        
        cursor.close()
        logger.info(f"查询未下载视频成功，共 {len(result)} 条")
        return result
    except Exception as e:
        logger.error(f"查询未下载视频失败: {e}")
        return []


def mark_video_broken(video_id: int, reason: str) -> bool:
    """标记视频为 broken（下架/私有/地区锁/版权限制等不可恢复的死链）

    check_status:
        2 = broken 通用（下架、私有、地区锁）
        3 = broken 版权限制（age restricted、copyright takedown）
    """
    try:
        reason_lower = reason.lower() if reason else ""
        is_copyright = (
            "copyright" in reason_lower
            or "age restricted" in reason_lower
            or "content id" in reason_lower
        )
        sql = (
            _ensure_base().SQLStatements.MARK_VIDEO_BROKEN_COPYRIGHT
            if is_copyright
            else _ensure_base().SQLStatements.MARK_VIDEO_BROKEN
        )
        conn = _ensure_base()._get_connection()
        with conn:
            conn.execute(sql, ((reason or "")[:200], video_id))
        logger.info(
            f"标记 broken({'copyright' if is_copyright else 'dead'}): "
            f"video_id={video_id}, reason={(reason or '')[:80]}"
        )
        return True
    except Exception as e:
        logger.error(f"标记 broken 失败: video_id={video_id}, error={e}")
        return False


def mark_video_check_ok(video_id: int) -> bool:
    """标记视频可达性探测通过"""
    try:
        conn = _ensure_base()._get_connection()
        with conn:
            conn.execute(_ensure_base().SQLStatements.MARK_VIDEO_CHECK_OK, (video_id,))
        return True
    except Exception as e:
        logger.error(f"标记 check_ok 失败: video_id={video_id}, error={e}")
        return False


def is_video_broken(source_url: str) -> bool:
    """判断视频是否已被标记为 broken"""
    try:
        cursor = _ensure_base()._execute_with_retry(
            "SELECT check_status FROM video_info WHERE source_url = ?",
            (source_url,)
        )
        row = cursor.fetchone()
        if row is None:
            return False
        return row[0] in (2, 3)
    except Exception as e:
        logger.error(f"查询 broken 状态失败: {e}")
        return False


def get_all_undownloaded_videos() -> List[Dict[str, Any]]:
    """获取所有未下载视频（包括 broken，用于运维排查）"""
    try:
        cursor = _ensure_base()._execute_with_retry(_ensure_base().SQLStatements.GET_ALL_UNDOWNLOADED_VIDEOS)
        return _cursor_to_list(cursor)
    except Exception as e:
        logger.error(f"查询所有未下载视频失败: {e}")
        return []


def count_broken_videos() -> int:
    """统计 broken 视频数量"""
    try:
        cursor = _ensure_base()._execute_with_retry(
            "SELECT COUNT(*) FROM video_info WHERE check_status IN (2, 3)"
        )
        row = cursor.fetchone()
        return row[0] if row else 0
    except Exception as e:
        logger.error(f"统计 broken 视频失败: {e}")
        return 0


def get_videos_by_lang(lang: LanguageType) -> List[Dict[str, Any]]:
    """按语种查询视频（直接查询）
    
    Args:
        lang: 语种枚举
    
    Returns:
        视频信息字典列表
    """
    try:
        cursor = _ensure_base()._execute_with_retry(_ensure_base().SQLStatements.GET_VIDEOS_BY_LANG, (lang.value,))
        return _cursor_to_list(cursor)
    except Exception as e:
        logger.error(f"按语种查询视频失败: lang={lang}, error={e}")
        return []


def get_videos_with_task_status() -> List[Dict[str, Any]]:
    """获取视频及关联任务状态列表（直接查询）
    
    Returns:
        视频信息字典列表，包含任务状态
    """
    try:
        cursor = _ensure_base()._execute_with_retry(_ensure_base().SQLStatements.GET_VIDEOS_BY_STATUS)
        return _cursor_to_list(cursor)
    except Exception as e:
        logger.error(f"查询视频状态失败: {e}")
        return []


def delete_video(video_id: int) -> bool:
    """删除视频（走缓冲池，会触发级联删除）
    
    Args:
        video_id: 视频ID
    
    Returns:
        True 表示成功
    """
    try:
        sql = _ensure_base().SQLStatements.DELETE_VIDEO_BY_ID
        params = (video_id,)
        
        pool = _ensure_base().get_buffer_pool()
        pool.add(sql, params)
        
        return True
    except Exception as e:
        logger.error(f"删除视频失败: id={video_id}, error={e}")
        return False


def count_videos() -> int:
    """统计视频总数（直接查询）
    
    Returns:
        视频数量
    """
    try:
        cursor = _ensure_base()._execute_with_retry(_ensure_base().SQLStatements.COUNT_VIDEOS)
        row = cursor.fetchone()
        return row[0] if row else 0
    except Exception as e:
        logger.error(f"统计视频数量失败: {e}")
        return 0


def count_videos_by_lang() -> Dict[str, int]:
    """按语种统计视频数量（直接查询）
    
    Returns:
        语种->数量的字典
    """
    try:
        cursor = _ensure_base()._execute_with_retry(_ensure_base().SQLStatements.COUNT_VIDEOS_BY_LANG)
        return {row[0]: row[1] for row in cursor.fetchall()}
    except Exception as e:
        logger.error(f"按语种统计视频失败: {e}")
        return {}


def count_videos_by_downloaded() -> Dict[int, int]:
    """按下载状态统计视频数量（直接查询）
    
    Returns:
        下载状态->数量的字典
    """
    try:
        cursor = _ensure_base()._execute_with_retry(_ensure_base().SQLStatements.COUNT_VIDEOS_BY_DOWNLOADED)
        return {row[0]: row[1] for row in cursor.fetchall()}
    except Exception as e:
        logger.error(f"按下载状态统计视频失败: {e}")
        return {}


def delete_expired_videos(expire_days: int = 30) -> int:
    """删除过期视频（直接执行，不走缓冲池）
    
    Args:
        expire_days: 过期天数
    
    Returns:
        删除的记录数
    """
    try:
        expire_ts = int(time.time()) - expire_days * 24 * 3600
        cursor = _ensure_base()._execute_with_retry(_ensure_base().SQLStatements.DELETE_EXPIRED_VIDEOS, (expire_ts,))
        return cursor.getconnection().changes()
    except Exception as e:
        logger.error(f"删除过期视频失败: {e}")
        return 0


# =====================================================
# translate_task 表 CRUD 操作
# =====================================================

