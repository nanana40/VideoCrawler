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

import os
import threading
from utils.thread_spawn import spawn  # AUDIT-0033
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
    
    # video_info 表操作（v2：新增 channel_id / series_id / sub_category / tags 等字段）
    INSERT_VIDEO = """
        INSERT OR IGNORE INTO video_info (
            source_url, yt_video_id, title, description, thumbnail, duration, published_at,
            author, channel_id, channel_name,
            lang, category, sub_category, tags, yt_category_id,
            series_id, related_cluster_id,
            views, local_video_path, is_downloaded
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
        SELECT * FROM video_info
        WHERE is_downloaded = 0 AND (check_status IS NULL OR check_status NOT IN (2, 3))
        ORDER BY create_ts DESC
    """

    GET_ALL_UNDOWNLOADED_VIDEOS = """
        SELECT * FROM video_info WHERE is_downloaded = 0 ORDER BY create_ts DESC
    """

    MARK_VIDEO_BROKEN = """
        UPDATE video_info
        SET check_status = 2, check_fail_reason = ?, check_ts = strftime('%s', 'now')
        WHERE id = ?
    """

    MARK_VIDEO_BROKEN_COPYRIGHT = """
        UPDATE video_info
        SET check_status = 3, check_fail_reason = ?, check_ts = strftime('%s', 'now')
        WHERE id = ?
    """

    MARK_VIDEO_CHECK_OK = """
        UPDATE video_info
        SET check_status = 1, check_fail_reason = NULL, check_ts = strftime('%s', 'now')
        WHERE id = ?
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
        UPDATE translate_task SET status = ?, fail_reason = ? WHERE id = ?
    """
    
    UPDATE_TASK_STATUS_WITH_RETRY = """
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
        self._lock = threading.RLock()
        self._running = True
        self._flush_thread = spawn(target=self._flush_loop, daemon=True)
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
    
    def flush_now(self) -> None:
        """立即刷盘（不停止后台线程）"""
        self._flush_immediate()
    
    def flush(self) -> None:
        """手动触发刷盘（优雅退出时调用，会停止后台线程）"""
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

                # 自动 checkpoint：约 1000 页（4MB）就回写主库，防止 WAL 无限膨胀
                _db_connection.execute("PRAGMA wal_autocheckpoint=1000")
                
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
        db_path = str(get_db_path())
        logger.info(f"开始批量写入数据库，路径={db_path}，待写入 {len(items)} 条")
        with conn:
            for sql, params in items:
                conn.execute(sql, params)
        
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM video_info")
        total = cursor.fetchone()[0]
        cursor.close()
        
        logger.info(f"批量写入完成，实际写入数据库记录数={total}")
    except Exception as e:
        logger.error(f"批量写入失败: {e}")
        raise


# =====================================================
# 数据库初始化
# =====================================================

def init_database() -> None:
    """初始化数据库
    
    执行 schema.sql 创建表结构、触发器和索引；
    同时检测老库 video_info 缺哪些新列，自动 ALTER TABLE 补上。
    """
    schema_path = str(get_schema_path())
    try:
        with open(schema_path, "r", encoding="utf-8") as f:
            schema_sql = f.read()
        
        conn = _get_connection()

        # ===== v2 迁移：老库自动补列（必须在 schema_sql 之前）=====
        # schema.sql 里的 CREATE INDEX 引用了 channel_id / series_id / related_cluster_id，
        # 如果老库还没有这些列，索引会直接报错。所以必须先补列再跑 schema.sql。
        _VIDEO_INFO_NEW_COLS = [
            ("yt_video_id",        "TEXT"),
            ("published_at",       "TEXT"),
            ("channel_id",         "TEXT"),
            ("channel_name",       "TEXT"),
            ("sub_category",       "TEXT"),
            ("tags",               "TEXT"),
            ("yt_category_id",     "INTEGER"),
            ("series_id",          "TEXT"),
            ("related_cluster_id", "TEXT"),
            ("check_status",       "INTEGER DEFAULT 0"),
            ("check_fail_reason",  "TEXT"),
            ("check_ts",           "INTEGER"),
        ]
        try:
            existing_tables = {
                row[0] for row in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                ).fetchall()
            }
            if "video_info" in existing_tables:
                existing_cols = {
                    row[1] for row in conn.execute("PRAGMA table_info(video_info)").fetchall()
                }
                added_cols = []
                for col_name, col_type in _VIDEO_INFO_NEW_COLS:
                    if col_name not in existing_cols:
                        conn.execute(
                            f"ALTER TABLE video_info ADD COLUMN {col_name} {col_type}"
                        )
                        added_cols.append(col_name)
                if added_cols:
                    logger.info(
                        f"数据库迁移：video_info 自动补列 {added_cols}"
                    )
        except Exception as migrate_err:
            logger.warning(f"数据库自动迁移失败（可忽略，如果是新库会由 schema.sql 处理）: {migrate_err}")

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
            # 关闭前强制 checkpoint，把 WAL 全部回写主库并截断
            _db_connection.execute("PRAGMA wal_checkpoint(TRUNCATE)")
            _db_connection.close()
            logger.info("数据库连接已关闭（WAL checkpoint 完成）")
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
        
        get_buffer_pool().flush_now()
        
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


# ---------------------------------------------------------------
# AUDIT-0039: video_info / translate_task 的 CRUD 已抽到 db/ 子模块
# 这里 re-export 保持外部调用方 import 路径不变
# ---------------------------------------------------------------
from utils.db.video_repo import *   # noqa: F401,F403
from utils.db.task_repo import *    # noqa: F401,F403
