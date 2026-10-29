"""
utils/db/task_repo.py — translate_task 表的 CRUD 实现

AUDIT-0039: 从 db_manager.py 抽出，让 db_manager 只保留连接管理/缓冲池。
"""

import time
from typing import Optional, Dict, List, Any
from utils.logger import get_error_logger
from utils.enums import TaskStatus, TaskPriority


# AUDIT-0039: 延迟 import db_manager 避免循环依赖
# db_manager.py 在文件末尾才 import 本模块，所以本模块顶层不能反向 import db_manager
_base = None

def _ensure_base():
    """一次性延迟导入 db_manager 基础设施"""
    global _base
    if _base is None:
        from utils import db_manager as _m
        _base = _m
    return _base


logger = get_error_logger()

def insert_translate_task(
    video_id: int,
    outer_task_id: Optional[str] = None,
    subtitle_path: Optional[str] = None,
    status: TaskStatus = TaskStatus.DOWNLOADED,
    retry_count: int = 0,
    max_retry: int = 3,
    priority: TaskPriority = TaskPriority.NORMAL,
    fail_reason: Optional[str] = None,
    dead_letter_ts: Optional[int] = None,
    timeout_ts: Optional[int] = None
) -> bool:
    """插入翻译任务（走缓冲池）
    
    Args:
        video_id: 关联视频ID
        outer_task_id: 外部任务ID
        subtitle_path: 字幕文件路径
        status: 任务状态（默认 DOWNLOADED）
        retry_count: 当前重试次数
        max_retry: 最大重试次数
        priority: 优先级
        fail_reason: 失败原因
        dead_letter_ts: 死信时间戳
        timeout_ts: 超时时间戳
    
    Returns:
        True 表示成功
    """
    try:
        if not TaskStatus.is_valid(status.value):
            logger.error(f"非法任务状态: {status}")
            return False
        
        if not TaskPriority.is_valid(priority.value):
            logger.error(f"非法优先级: {priority}")
            return False
        
        sql = _ensure_base().SQLStatements.INSERT_TRANSLATE_TASK
        params = (
            video_id,
            outer_task_id,
            subtitle_path,
            status.value,
            retry_count,
            max_retry,
            priority.value,
            fail_reason,
            dead_letter_ts,
            timeout_ts
        )
        
        pool = _ensure_base().get_buffer_pool()
        pool.add(sql, params)
        
        return True
    except Exception as e:
        logger.error(f"插入翻译任务失败: video_id={video_id}, error={e}")
        return False


def update_task_status(task_id: int, status: TaskStatus, fail_reason: Optional[str] = None) -> bool:
    """更新任务状态（走缓冲池）
    
    Args:
        task_id: 任务ID
        status: 目标状态
        fail_reason: 失败原因
    
    Returns:
        True 表示成功
    """
    try:
        if not TaskStatus.is_valid(status.value):
            logger.error(f"非法任务状态: {status}")
            return False
        
        if status in (TaskStatus.FAILED, TaskStatus.DEAD_LETTER):
            sql = _ensure_base().SQLStatements.UPDATE_TASK_STATUS_WITH_RETRY
        else:
            sql = _ensure_base().SQLStatements.UPDATE_TASK_STATUS
        
        params = (status.value, fail_reason, task_id)
        
        pool = _ensure_base().get_buffer_pool()
        pool.add(sql, params)
        
        return True
    except Exception as e:
        logger.error(f"更新任务状态失败: task_id={task_id}, status={status}, error={e}")
        return False


def update_task_subtitle(task_id: int, subtitle_path: str) -> bool:
    """更新任务字幕路径并标记完成（走缓冲池）
    
    Args:
        task_id: 任务ID
        subtitle_path: 字幕文件路径
    
    Returns:
        True 表示成功
    """
    try:
        sql = _ensure_base().SQLStatements.UPDATE_TASK_SUBTITLE
        params = (subtitle_path, TaskStatus.COMPLETED.value, task_id)
        
        pool = _ensure_base().get_buffer_pool()
        pool.add(sql, params)
        
        return True
    except Exception as e:
        logger.error(f"更新任务字幕失败: task_id={task_id}, error={e}")
        return False


def update_task_timeout(task_id: int, timeout_ts: int) -> bool:
    """更新任务超时时间戳（走缓冲池）
    
    Args:
        task_id: 任务ID
        timeout_ts: 超时时间戳
    
    Returns:
        True 表示成功
    """
    try:
        sql = _ensure_base().SQLStatements.UPDATE_TASK_TIMEOUT
        params = (timeout_ts, task_id)
        
        pool = _ensure_base().get_buffer_pool()
        pool.add(sql, params)
        
        return True
    except Exception as e:
        logger.error(f"更新任务超时时间失败: task_id={task_id}, error={e}")
        return False


def update_task_dead_letter(task_id: int, fail_reason: str) -> bool:
    """将任务标记为死信（走缓冲池）
    
    Args:
        task_id: 任务ID
        fail_reason: 失败原因
    
    Returns:
        True 表示成功
    """
    try:
        dead_letter_ts = int(time.time())
        sql = _ensure_base().SQLStatements.UPDATE_TASK_DEAD_LETTER
        params = (TaskStatus.DEAD_LETTER.value, dead_letter_ts, fail_reason, task_id)
        
        pool = _ensure_base().get_buffer_pool()
        pool.add(sql, params)
        
        return True
    except Exception as e:
        logger.error(f"标记任务为死信失败: task_id={task_id}, error={e}")
        return False


def get_task_by_video_id(video_id: int) -> Optional[Dict[str, Any]]:
    """根据视频ID查询翻译任务（直接查询）
    
    Args:
        video_id: 视频ID
    
    Returns:
        翻译任务字典，不存在返回 None
    """
    try:
        cursor = _ensure_base()._execute_with_retry(_ensure_base().SQLStatements.GET_TASK_BY_VIDEO_ID, (video_id,))
        row = cursor.fetchone()
        if row:
            return dict(zip([desc[0] for desc in cursor.getdescription()], row))
        return None
    except Exception as e:
        logger.error(f"查询翻译任务失败: video_id={video_id}, error={e}")
        return None


def get_task_by_id(task_id: int) -> Optional[Dict[str, Any]]:
    """根据任务ID查询翻译任务（直接查询）
    
    Args:
        task_id: 任务ID
    
    Returns:
        翻译任务字典，不存在返回 None
    """
    try:
        cursor = _ensure_base()._execute_with_retry(_ensure_base().SQLStatements.GET_TASK_BY_ID, (task_id,))
        row = cursor.fetchone()
        if row:
            return dict(zip([desc[0] for desc in cursor.getdescription()], row))
        return None
    except Exception as e:
        logger.error(f"查询翻译任务失败: task_id={task_id}, error={e}")
        return None


def get_pending_tasks(limit: Optional[int] = None) -> List[Dict[str, Any]]:
    """获取待翻译任务列表（直接查询）
    
    Args:
        limit: 返回数量限制
    
    Returns:
        翻译任务字典列表
    """
    try:
        cursor = _ensure_base()._execute_with_retry(_ensure_base().SQLStatements.GET_PENDING_TASKS, (TaskStatus.DOWNLOADED.value,))
        results = _cursor_to_list(cursor)
        if limit:
            return results[:limit]
        return results
    except Exception as e:
        logger.error(f"查询待翻译任务失败: {e}")
        return []


def get_failed_tasks() -> List[Dict[str, Any]]:
    """获取失败任务列表（直接查询）
    
    Returns:
        翻译任务字典列表
    """
    try:
        cursor = _ensure_base()._execute_with_retry(_ensure_base().SQLStatements.GET_FAILED_TASKS, (TaskStatus.FAILED.value,))
        return _cursor_to_list(cursor)
    except Exception as e:
        logger.error(f"查询失败任务失败: {e}")
        return []


def get_dead_letter_tasks() -> List[Dict[str, Any]]:
    """获取死信任务列表（直接查询）
    
    Returns:
        翻译任务字典列表
    """
    try:
        cursor = _ensure_base()._execute_with_retry(_ensure_base().SQLStatements.GET_DEAD_LETTER_TASKS, (TaskStatus.DEAD_LETTER.value,))
        return _cursor_to_list(cursor)
    except Exception as e:
        logger.error(f"查询死信任务失败: {e}")
        return []


def get_tasks_by_status(status: TaskStatus) -> List[Dict[str, Any]]:
    """按状态查询任务（直接查询）
    
    Args:
        status: 任务状态
    
    Returns:
        翻译任务字典列表
    """
    try:
        cursor = _ensure_base()._execute_with_retry(_ensure_base().SQLStatements.GET_TASKS_BY_STATUS, (status.value,))
        return _cursor_to_list(cursor)
    except Exception as e:
        logger.error(f"按状态查询任务失败: status={status}, error={e}")
        return []


def count_tasks() -> int:
    """统计翻译任务总数（直接查询）
    
    Returns:
        任务数量
    """
    try:
        cursor = _ensure_base()._execute_with_retry(_ensure_base().SQLStatements.COUNT_TASKS)
        row = cursor.fetchone()
        return row[0] if row else 0
    except Exception as e:
        logger.error(f"统计任务数量失败: {e}")
        return 0


def count_tasks_by_status() -> Dict[int, int]:
    """按状态统计任务数量（直接查询）
    
    Returns:
        状态->数量的字典
    """
    try:
        cursor = _ensure_base()._execute_with_retry(_ensure_base().SQLStatements.COUNT_TASKS_BY_STATUS)
        return {row[0]: row[1] for row in cursor.fetchall()}
    except Exception as e:
        logger.error(f"按状态统计任务失败: {e}")
        return {}


def delete_task(task_id: int) -> bool:
    """删除翻译任务（走缓冲池）
    
    Args:
        task_id: 任务ID
    
    Returns:
        True 表示成功
    """
    try:
        sql = _ensure_base().SQLStatements.DELETE_TASK_BY_ID
        params = (task_id,)
        
        pool = _ensure_base().get_buffer_pool()
        pool.add(sql, params)
        
        return True
    except Exception as e:
        logger.error(f"删除翻译任务失败: task_id={task_id}, error={e}")
        return False


def reset_failed_tasks() -> int:
    """重置失败任务为待翻译状态（直接执行）
    
    Returns:
        重置的记录数
    """
    try:
        cursor = _ensure_base()._execute_with_retry(
            _ensure_base().SQLStatements.RESET_FAILED_TO_PENDING,
            (TaskStatus.DOWNLOADED.value, TaskStatus.FAILED.value)
        )
        return cursor.getconnection().changes()
    except Exception as e:
        logger.error(f"重置失败任务失败: {e}")
        return 0


# =====================================================
# 工具函数
# =====================================================

def _cursor_to_list(cursor: Any) -> List[Dict[str, Any]]:
    """将游标结果转换为字典列表
    
    Args:
        cursor: apsw Cursor 对象
    
    Returns:
        字典列表
    """
    columns = [desc[0] for desc in cursor.getdescription()]
    return [dict(zip(columns, row)) for row in cursor.fetchall()]


