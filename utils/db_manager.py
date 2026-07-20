"""
数据库管理模块：基于 apsw 的 SQLite 内存缓冲写入池

功能特性：
    1. 使用 apsw 高级 SQLite 封装，支持批量写入
    2. 内存缓冲写入池：写入先缓存到内存，达到阈值或定时自动刷盘
    3. WAL 模式 + busy_timeout 解决并发写入锁问题
    4. 支持两张核心表（video_info / translate_task）的完整 CRUD
    5. 状态枚举绑定：写入前校验枚举合法性
    6. 优雅退出：程序退出时自动刷盘所有缓冲数据
    7. 日志输出到 error 标签
"""

import threading
import time
import logging
from typing import Optional, Dict, List, Any, Tuple

from .enums import TaskStatus, LanguageType, TaskPriority
from .path_helper import get_db_path, get_schema_path
from .logger import get_error_logger


logger = get_error_logger()


# =====================================================
# 数据库表操作 SQL 定义
# =====================================================

class SQLStatements:
    """SQL 语句常量定义"""
    
    # video_info 表操作
    INSERT_VIDEO = """
        INSERT OR IGNORE INTO video_info (source_url, title, lang, category, local_video_path, is_downloaded)
        VALUES (?, ?, ?, ?, ?, ?)
    """
    
    UPDATE_VIDEO_DOWNLOADED = """
        UPDATE video_info SET is_downloaded = ?, local_video_path = ? WHERE id = ?
    """
    
    UPDATE_VIDEO_CATEGORY = """
        UPDATE video_info SET category = ? WHERE id = ?
    """
    
    GET_VIDEO_BY_URL = """
        SELECT * FROM video_info WHERE source_url = ?
    """
    
    GET_VIDEO_BY_ID = """
        SELECT * FROM video_info WHERE id = ?
    """
    
    GET_UNDOWNLOADED_VIDEOS = """
        SELECT * FROM video_info WHERE is_downloaded = 0 ORDER BY create_ts DESC
    """
    
    GET_VIDEOS_BY_LANG = """
        SELECT * FROM video_info WHERE lang = ? ORDER BY create_ts DESC
    """
    
    GET_VIDEOS_BY_STATUS = """
        SELECT vi.*, tt.status as task_status 
        FROM video_info vi 
        LEFT JOIN translate_task tt ON vi.id = tt.video_id 
        ORDER BY vi.create_ts DESC
    """
    
    DELETE_VIDEO_BY_ID = """
        DELETE FROM video_info WHERE id = ?
    """
    
    COUNT_VIDEOS = """
        SELECT COUNT(*) FROM video_info
    """
    
    COUNT_VIDEOS_BY_LANG = """
        SELECT lang, COUNT(*) FROM video_info GROUP BY lang
    """
    
    COUNT_VIDEOS_BY_DOWNLOADED = """
        SELECT is_downloaded, COUNT(*) FROM video_info GROUP BY is_downloaded
    """
    
    DELETE_EXPIRED_VIDEOS = """
        DELETE FROM video_info WHERE create_ts < ?
    """
    
    # translate_task 表操作
    INSERT_TRANSLATE_TASK = """
        INSERT INTO translate_task (video_id, outer_task_id, subtitle_path, status, retry_count, max_retry, priority, fail_reason, dead_letter_ts, timeout_ts)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """
    
    UPDATE_TASK_STATUS = """
        UPDATE translate_task SET status = ?, fail_reason = ?, retry_count = retry_count + 1 WHERE id = ?
    """
    
    UPDATE_TASK_SUBTITLE = """
        UPDATE translate_task SET subtitle_path = ?, status = ? WHERE id = ?
    """
    
    UPDATE_TASK_TIMEOUT = """
        UPDATE translate_task SET timeout_ts = ? WHERE id = ?
    """
    
    UPDATE_TASK_DEAD_LETTER = """
        UPDATE translate_task SET status = ?, dead_letter_ts = ?, fail_reason = ? WHERE id = ?
    """
    
    GET_TASK_BY_VIDEO_ID = """
        SELECT * FROM translate_task WHERE video_id = ?
    """
    
    GET_TASK_BY_ID = """
        SELECT * FROM translate_task WHERE id = ?
    """
    
    GET_PENDING_TASKS = """
        SELECT * FROM translate_task WHERE status = ? ORDER BY priority DESC, update_ts ASC
    """
    
    GET_FAILED_TASKS = """
        SELECT * FROM translate_task WHERE status = ? ORDER BY retry_count DESC, update_ts DESC
    """
    
    GET_DEAD_LETTER_TASKS = """
        SELECT * FROM translate_task WHERE status = ? ORDER BY dead_letter_ts DESC
    """
    
    GET_TASKS_BY_STATUS = """
        SELECT * FROM translate_task WHERE status = ? ORDER BY priority DESC, update_ts ASC
    """
    
    COUNT_TASKS = """
        SELECT COUNT(*) FROM translate_task
    """
    
    COUNT_TASKS_BY_STATUS = """
        SELECT status, COUNT(*) FROM translate_task GROUP BY status
    """
    
    DELETE_TASK_BY_ID = """
        DELETE FROM translate_task WHERE id = ?
    """
    
    RESET_FAILED_TO_PENDING = """
        UPDATE translate_task SET status = ?, retry_count = 0, fail_reason = NULL WHERE status = ?
    """


# =====================================================
# 缓冲写入池类
# =====================================================

class BufferPool:
    """内存缓冲写入池
    
    写入操作先缓存到内存队列，达到阈值或定时触发时批量写入数据库，
    减少磁盘IO次数，提升写入性能。
    """
    
    def __init__(self, batch_size: int = 50, flush_interval: int = 3) -> None:
        """初始化缓冲池
        
        Args:
            batch_size: 批量写入阈值，达到此数量自动刷盘
            flush_interval: 定时刷盘间隔（秒）
        """
        self._batch_size = batch_size
        self._flush_interval = flush_interval
        self._buffer: List[Tuple[str, tuple]] = []
        self._lock = threading.Lock()
        self._running = True
        self._flush_thread = threading.Thread(target=self._flush_loop, daemon=True)
        self._flush_thread.start()
    
    def add(self, sql: str, params: tuple) -> None:
        """添加写入操作到缓冲池
        
        Args:
            sql: SQL 语句
            params: SQL 参数
        """
        with self._lock:
            self._buffer.append((sql, params))
            if len(self._buffer) >= self._batch_size:
                self._flush_immediate()
    
    def _flush_loop(self) -> None:
        """定时刷盘循环"""
        while self._running:
            time.sleep(self._flush_interval)
            self._flush_immediate()
    
    def _flush_immediate(self) -> None:
        """立即刷盘"""
        items = []
        with self._lock:
            if self._buffer:
                items = self._buffer[:]
                self._buffer.clear()
        
        if items:
            yield_to_db(items)
    
    def flush(self) -> None:
        """手动触发刷盘（优雅退出时调用）"""
        self._running = False
        self._flush_immediate()
        self._flush_thread.join(timeout=5)
    
    @property
    def buffer_size(self) -> int:
        """获取当前缓冲队列大小"""
        with self._lock:
            return len(self._buffer)


# =====================================================
# 全局缓冲池实例
# =====================================================

_buffer_pool: Optional[BufferPool] = None


def init_buffer_pool(batch_size: int = 50, flush_interval: int = 3) -> None:
    """初始化全局缓冲池
    
    Args:
        batch_size: 批量写入阈值
        flush_interval: 定时刷盘间隔（秒）
    """
    global _buffer_pool
    _buffer_pool = BufferPool(batch_size, flush_interval)
    logger.info(f"数据库缓冲池初始化完成，批量阈值={batch_size}，刷盘间隔={flush_interval}秒")


def get_buffer_pool() -> BufferPool:
    """获取全局缓冲池实例
    
    Returns:
        BufferPool 实例
    
    Raises:
        RuntimeError: 缓冲池未初始化
    """
    if _buffer_pool is None:
        raise RuntimeError("缓冲池未初始化，请先调用 init_buffer_pool()")
    return _buffer_pool


# =====================================================
# 数据库连接管理
# =====================================================

_db_connection: Any = None
_db_lock = threading.Lock()


def _get_connection() -> Any:
    """获取数据库连接（单例模式）
    
    Returns:
        apsw Connection 对象
    """
    global _db_connection
    with _db_lock:
        if _db_connection is None:
            db_path = str(get_db_path())
            try:
                import apsw
                _db_connection = apsw.Connection(db_path)
                
                # 配置 WAL 模式，提高并发写入性能
                _db_connection.execute("PRAGMA journal_mode=WAL")
                
                # 设置 busy_timeout，等待其他连接释放锁
                _db_connection.execute("PRAGMA busy_timeout=30000")
                
                # 设置 synchronous=NORMAL，平衡性能与可靠性
                _db_connection.execute("PRAGMA synchronous=NORMAL")
                
                # 启用外键约束
                _db_connection.execute("PRAGMA foreign_keys=ON")
                
                logger.info("数据库连接初始化成功")
            except ImportError:
                logger.error("apsw 未安装，请安装 apsw 库")
                raise
            except Exception as e:
                logger.error(f"数据库连接失败: {e}")
                raise
        return _db_connection


def _execute_with_retry(sql: str, params: tuple = (), retries: int = 3) -> Any:
    """带重试机制执行 SQL 语句
    
    Args:
        sql: SQL 语句
        params: SQL 参数
        retries: 重试次数
    
    Returns:
        apsw Cursor 对象
    
    Raises:
        Exception: 多次重试后仍失败
    """
    conn = _get_connection()
    for attempt in range(retries):
        try:
            return conn.execute(sql, params)
        except Exception as e:
            if "database is locked" in str(e).lower() and attempt < retries - 1:
                sleep_time = 0.5 * (2 ** attempt)
                logger.warning(f"数据库锁定，等待 {sleep_time:.1f} 秒后重试 (attempt {attempt + 1}/{retries})")
                time.sleep(sleep_time)
            else:
                logger.error(f"执行 SQL 失败: {sql[:50]}... params={params}, error={e}")
                raise


def yield_to_db(items: List[Tuple[str, tuple]]) -> None:
    """批量写入数据库
    
    Args:
        items: (sql, params) 元组列表
    """
    if not items:
        return
    
    conn = _get_connection()
    try:
        with conn:
            for sql, params in items:
                conn.execute(sql, params)
        logger.debug(f"批量写入完成，共 {len(items)} 条记录")
    except Exception as e:
        logger.error(f"批量写入失败: {e}")
        raise


# =====================================================
# 数据库初始化
# =====================================================

def init_database() -> None:
    """初始化数据库
    
    执行 schema.sql 创建表结构、触发器和索引。
    """
    schema_path = str(get_schema_path())
    try:
        with open(schema_path, "r", encoding="utf-8") as f:
            schema_sql = f.read()
        
        conn = _get_connection()
        conn.execute(schema_sql)
        logger.info("数据库初始化完成，表结构创建成功")
    except FileNotFoundError:
        logger.error(f"数据库初始化脚本不存在: {schema_path}")
        raise
    except Exception as e:
        logger.error(f"数据库初始化失败: {e}")
        raise


# =====================================================
# video_info 表 CRUD 操作
# =====================================================

def insert_video(
    source_url: str,
    title: str,
    lang: LanguageType,
    category: Optional[str] = None,
    local_video_path: Optional[str] = None,
    is_downloaded: int = 0
) -> bool:
    """插入视频信息（走缓冲池）
    
    Args:
        source_url: 视频源URL
        title: 视频标题
        lang: 视频语种枚举
        category: 视频分类
        local_video_path: 本地视频路径
        is_downloaded: 下载标记（0/1）
    
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
        
        sql = SQLStatements.INSERT_VIDEO
        params = (source_url, title, lang.value, category, local_video_path, is_downloaded)
        
        pool = get_buffer_pool()
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
        sql = SQLStatements.UPDATE_VIDEO_DOWNLOADED
        params = (1, local_video_path, video_id)
        
        pool = get_buffer_pool()
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
        sql = SQLStatements.UPDATE_VIDEO_CATEGORY
        params = (category, video_id)
        
        pool = get_buffer_pool()
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
        cursor = _execute_with_retry(SQLStatements.GET_VIDEO_BY_URL, (source_url,))
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
        cursor = _execute_with_retry(SQLStatements.GET_VIDEO_BY_ID, (video_id,))
        row = cursor.fetchone()
        if row:
            return dict(zip([desc[0] for desc in cursor.getdescription()], row))
        return None
    except Exception as e:
        logger.error(f"查询视频失败: id={video_id}, error={e}")
        return None


def get_undownloaded_videos() -> List[Dict[str, Any]]:
    """获取未下载视频列表（直接查询）
    
    Returns:
        视频信息字典列表
    """
    try:
        cursor = _execute_with_retry(SQLStatements.GET_UNDOWNLOADED_VIDEOS)
        return _cursor_to_list(cursor)
    except Exception as e:
        logger.error(f"查询未下载视频失败: {e}")
        return []


def get_videos_by_lang(lang: LanguageType) -> List[Dict[str, Any]]:
    """按语种查询视频（直接查询）
    
    Args:
        lang: 语种枚举
    
    Returns:
        视频信息字典列表
    """
    try:
        cursor = _execute_with_retry(SQLStatements.GET_VIDEOS_BY_LANG, (lang.value,))
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
        cursor = _execute_with_retry(SQLStatements.GET_VIDEOS_BY_STATUS)
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
        sql = SQLStatements.DELETE_VIDEO_BY_ID
        params = (video_id,)
        
        pool = get_buffer_pool()
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
        cursor = _execute_with_retry(SQLStatements.COUNT_VIDEOS)
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
        cursor = _execute_with_retry(SQLStatements.COUNT_VIDEOS_BY_LANG)
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
        cursor = _execute_with_retry(SQLStatements.COUNT_VIDEOS_BY_DOWNLOADED)
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
        cursor = _execute_with_retry(SQLStatements.DELETE_EXPIRED_VIDEOS, (expire_ts,))
        return cursor.getconnection().changes()
    except Exception as e:
        logger.error(f"删除过期视频失败: {e}")
        return 0


# =====================================================
# translate_task 表 CRUD 操作
# =====================================================

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
        
        sql = SQLStatements.INSERT_TRANSLATE_TASK
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
        
        pool = get_buffer_pool()
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
        
        sql = SQLStatements.UPDATE_TASK_STATUS
        params = (status.value, fail_reason, task_id)
        
        pool = get_buffer_pool()
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
        sql = SQLStatements.UPDATE_TASK_SUBTITLE
        params = (subtitle_path, TaskStatus.COMPLETED.value, task_id)
        
        pool = get_buffer_pool()
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
        sql = SQLStatements.UPDATE_TASK_TIMEOUT
        params = (timeout_ts, task_id)
        
        pool = get_buffer_pool()
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
        sql = SQLStatements.UPDATE_TASK_DEAD_LETTER
        params = (TaskStatus.DEAD_LETTER.value, dead_letter_ts, fail_reason, task_id)
        
        pool = get_buffer_pool()
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
        cursor = _execute_with_retry(SQLStatements.GET_TASK_BY_VIDEO_ID, (video_id,))
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
        cursor = _execute_with_retry(SQLStatements.GET_TASK_BY_ID, (task_id,))
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
        cursor = _execute_with_retry(SQLStatements.GET_PENDING_TASKS, (TaskStatus.DOWNLOADED.value,))
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
        cursor = _execute_with_retry(SQLStatements.GET_FAILED_TASKS, (TaskStatus.FAILED.value,))
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
        cursor = _execute_with_retry(SQLStatements.GET_DEAD_LETTER_TASKS, (TaskStatus.DEAD_LETTER.value,))
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
        cursor = _execute_with_retry(SQLStatements.GET_TASKS_BY_STATUS, (status.value,))
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
        cursor = _execute_with_retry(SQLStatements.COUNT_TASKS)
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
        cursor = _execute_with_retry(SQLStatements.COUNT_TASKS_BY_STATUS)
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
        sql = SQLStatements.DELETE_TASK_BY_ID
        params = (task_id,)
        
        pool = get_buffer_pool()
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
        cursor = _execute_with_retry(
            SQLStatements.RESET_FAILED_TO_PENDING,
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


def shutdown_db() -> None:
    """优雅关闭数据库
    
    刷盘所有缓冲数据，关闭连接。
    """
    global _buffer_pool, _db_connection
    
    logger.info("开始关闭数据库...")
    
    if _buffer_pool:
        _buffer_pool.flush()
        logger.info("缓冲池刷盘完成")
    
    if _db_connection:
        try:
            _db_connection.close()
            logger.info("数据库连接已关闭")
        except Exception as e:
            logger.error(f"关闭数据库连接失败: {e}")
        _db_connection = None
    
    _buffer_pool = None


def get_buffer_status() -> Dict[str, int]:
    """获取缓冲池状态（调试用）
    
    Returns:
        缓冲池状态字典
    """
    if _buffer_pool:
        return {"buffer_size": _buffer_pool.buffer_size}
    return {"buffer_size": 0}


# =====================================================
# 数据库操作便捷函数
# =====================================================

def create_video_and_task(
    source_url: str,
    title: str,
    lang: LanguageType,
    category: Optional[str] = None,
    priority: TaskPriority = TaskPriority.NORMAL
) -> Optional[int]:
    """创建视频和关联翻译任务（完整流程）
    
    Args:
        source_url: 视频源URL
        title: 视频标题
        lang: 语种
        category: 分类
        priority: 优先级
    
    Returns:
        创建的视频ID，失败返回 None
    """
    try:
        insert_video(source_url, title, lang, category)
        
        video = get_video_by_url(source_url)
        if video:
            video_id = video["id"]
            insert_translate_task(video_id=video_id, priority=priority)
            return video_id
        
        logger.error(f"创建视频后无法查询到: {source_url}")
        return None
    except Exception as e:
        logger.error(f"创建视频和任务失败: {e}")
        return None
