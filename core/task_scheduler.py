"""
任务调度器模块

管理后台线程调度、定时任务、健康检查和文件监控。

功能特性：
    1. APScheduler 定时任务调度
    2. 健康检查（ping 翻译工具、内存监控）
    3. 文件系统监控（watchdog）
    4. 全局线程生命周期管理
    5. 优雅退出
    6. Pipeline 流程调度集成
"""

import os
import time
import threading
from utils.thread_spawn import spawn  # AUDIT-0033
import uuid
import psutil
from typing import Optional, Dict, Any, Callable

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.triggers.cron import CronTrigger

from utils.enums import TaskStatus, LogTag
from utils.logger import get_crawler_logger, get_error_logger
from utils.path_helper import get_logs_dir, get_translate_queue_dir
from utils.config_loader import get_scheduler_config, load_config


logger = get_crawler_logger()
error_logger = get_error_logger()


class HealthChecker:
    """
    健康检查器
    
    监控系统资源和外部服务状态。
    """
    
    def __init__(self) -> None:
        """初始化健康检查器"""
        config = get_scheduler_config(load_config())
        self._enable_memory_warn = config.get("enable_memory_warn", True)
        self._memory_threshold_mb = config.get("memory_threshold_mb", 2048)
        self._logger = logger
    
    def check_memory(self) -> Dict[str, Any]:
        """检查内存使用情况"""
        try:
            process = psutil.Process()
            memory_info = process.memory_info()
            memory_mb = memory_info.rss / (1024 * 1024)
            
            status = "ok"
            if self._enable_memory_warn and memory_mb > self._memory_threshold_mb:
                status = "warning"
                self._logger.warning(f"内存使用过高: {memory_mb:.2f} MB，超过阈值 {self._memory_threshold_mb} MB")
            
            return {
                "status": status,
                "used_mb": memory_mb,
                "threshold_mb": self._memory_threshold_mb,
            }
            
        except Exception as e:
            self._logger.error(f"内存检查失败: {e}")
            return {"status": "error", "error": str(e)}
    
    def check_disk(self) -> Dict[str, Any]:
        """检查磁盘使用情况"""
        try:
            disk = psutil.disk_usage("/")
            used_percent = disk.percent
            
            status = "ok"
            if used_percent > 90:
                status = "warning"
                self._logger.warning(f"磁盘使用过高: {used_percent}%")
            
            return {
                "status": status,
                "used_percent": used_percent,
                "total_gb": disk.total / (1024 ** 3),
                "used_gb": disk.used / (1024 ** 3),
            }
            
        except Exception as e:
            self._logger.error(f"磁盘检查失败: {e}")
            return {"status": "error", "error": str(e)}
    
    def check_all(self) -> Dict[str, Any]:
        """执行所有健康检查"""
        return {
            "memory": self.check_memory(),
            "disk": self.check_disk(),
            "timestamp": time.time(),
        }


class TaskScheduler:
    """
    任务调度器
    
    管理所有后台任务和定时任务，集成 Pipeline 流程调度。
    """
    
    def __init__(self) -> None:
        """初始化任务调度器"""
        self._scheduler = BackgroundScheduler(timezone="Asia/Shanghai")
        self._health_checker = HealthChecker()
        self._running = False
        self._lock = threading.Lock()
        self._scheduled_tasks: Dict[str, str] = {}
        self._pipeline_config: Optional[Dict[str, Any]] = None
        logger.info("任务调度器初始化完成")
    
    def start(self) -> None:
        """启动调度器"""
        with self._lock:
            if self._running:
                logger.warning("调度器已在运行中")
                return
            
            self._running = True
        
        self._scheduler.start()
        logger.info("任务调度器已启动")
    
    def stop(self) -> None:
        """停止调度器"""
        with self._lock:
            if not self._running:
                return
            
            self._running = False
        
        self._scheduler.shutdown(wait=True)
        logger.info("任务调度器已停止")
    
    def add_interval_task(
        self,
        func: Callable,
        seconds: Optional[int] = None,
        minutes: Optional[int] = None,
        hours: Optional[int] = None,
        id: Optional[str] = None,
        name: Optional[str] = None,
        replace_existing: bool = False,
        **kwargs
    ) -> str:
        """
        添加定时任务
        
        Args:
            func: 任务函数
            seconds: 间隔秒数
            minutes: 间隔分钟数
            hours: 间隔小时数
            id: 任务 ID
            name: 任务名称
            
        Returns:
            任务 ID
        """
        trigger_kwargs = {}
        if seconds is not None:
            trigger_kwargs["seconds"] = seconds
        if minutes is not None:
            trigger_kwargs["minutes"] = minutes
        if hours is not None:
            trigger_kwargs["hours"] = hours
        trigger = IntervalTrigger(**trigger_kwargs)
        
        if id is None:
            id = f"task_{uuid.uuid4().hex[:8]}"
        
        self._scheduler.add_job(
            func,
            trigger=trigger,
            id=id,
            name=name,
            kwargs=kwargs,
            replace_existing=replace_existing,
        )
        
        self._scheduled_tasks[id] = name or "unnamed"
        logger.info(f"定时任务已添加: {id} ({name or 'unnamed'})")
        
        return id
    
    def add_cron_task(
        self,
        func: Callable,
        year: Optional[int] = None,
        month: Optional[int] = None,
        day: Optional[int] = None,
        week: Optional[int] = None,
        day_of_week: Optional[int] = None,
        hour: Optional[int] = None,
        minute: Optional[int] = None,
        second: Optional[int] = None,
        id: Optional[str] = None,
        name: Optional[str] = None,
        replace_existing: bool = False,
        **kwargs
    ) -> str:
        """
        添加 Cron 定时任务
        
        Args:
            func: 任务函数
            year/month/day/week/day_of_week/hour/minute/second: Cron 参数
            id: 任务 ID
            name: 任务名称
            
        Returns:
            任务 ID
        """
        trigger = CronTrigger(
            year=year, month=month, day=day, week=week,
            day_of_week=day_of_week, hour=hour, minute=minute, second=second
        )
        
        if id is None:
            id = f"cron_task_{uuid.uuid4().hex[:8]}"
        
        self._scheduler.add_job(
            func,
            trigger=trigger,
            id=id,
            name=name,
            kwargs=kwargs,
            replace_existing=replace_existing,
        )
        
        self._scheduled_tasks[id] = name or "unnamed"
        logger.info(f"Cron 任务已添加: {id} ({name or 'unnamed'})")
        
        return id
    
    def remove_task(self, task_id: str) -> bool:
        """
        移除定时任务
        
        Args:
            task_id: 任务 ID
            
        Returns:
            True 表示成功移除
        """
        try:
            self._scheduler.remove_job(task_id)
            self._scheduled_tasks.pop(task_id, None)
            logger.info(f"定时任务已移除: {task_id}")
            return True
        except Exception as e:
            logger.error(f"移除定时任务失败: {task_id}, error={e}")
            return False
    
    def add_health_check(self, minutes: int = 30) -> str:
        """
        添加健康检查任务
        
        Args:
            minutes: 检查间隔（分钟）
            
        Returns:
            任务 ID
        """
        return self.add_interval_task(
            self._health_checker.check_all,
            minutes=minutes,
            id="health_check",
            name="健康检查"
        )
    
    def add_log_cleanup(self, hours: int = 24) -> str:
        """
        添加日志清理任务
        
        Args:
            hours: 清理间隔（小时）
            
        Returns:
            任务 ID
        """
        return self.add_interval_task(
            self._cleanup_logs,
            hours=hours,
            id="log_cleanup",
            name="日志清理"
        )
    
    def schedule_pipeline(
        self,
        config: Dict[str, Any],
        hours: Optional[int] = None,
        minutes: Optional[int] = None,
        day: Optional[int] = None,
        weekday: Optional[int] = None,
        id: str = "scheduled_pipeline"
    ) -> str:
        """
        调度 Pipeline 流程执行
        
        Args:
            config: Pipeline 配置字典
            hours: 执行小时（可选，用于定时）
            minutes: 执行分钟（可选，用于定时）
            day: 执行日期（可选）
            weekday: 执行星期（可选，0=周一，6=周日）
            id: 任务 ID
            
        Returns:
            任务 ID
        """
        self._pipeline_config = config
        
        def _run_scheduled_pipeline():
            logger.info(f"开始执行定时 Pipeline 任务: {id}")
            try:
                from core.pipeline import PipelineConfig, run_pipeline
                
                pipeline_config = PipelineConfig()
                for key, value in config.items():
                    if hasattr(pipeline_config, key):
                        setattr(pipeline_config, key, value)
                
                result = run_pipeline(pipeline_config)
                logger.info(f"定时 Pipeline 任务完成 - 爬取: {result.crawled}, 下载: {result.downloaded}, "
                           f"字幕: {result.subtitled}, 分析: {result.analyzed}")
                
            except Exception as e:
                error_logger.error(f"定时 Pipeline 任务执行失败: {e}")
        
        if hours is not None or minutes is not None:
            return self.add_cron_task(
                _run_scheduled_pipeline,
                day=day,
                day_of_week=weekday,
                hour=hours,
                minute=minutes,
                id=id,
                name="定时 Pipeline 流程",
                replace_existing=True  # AUDIT-0044: 固定 id 重复注册时覆盖而非报错
            )
        else:
            interval_hours = hours if hours is not None else 6
            interval_minutes = minutes if minutes is not None else 0
            return self.add_interval_task(
                _run_scheduled_pipeline,
                hours=interval_hours,
                minutes=interval_minutes,
                id=id,
                name="定时 Pipeline 流程",
                replace_existing=True  # AUDIT-0044: 固定 id 重复注册时覆盖而非报错
            )
    
    def run_pipeline_now(self, config: Dict[str, Any]) -> None:
        """
        立即执行 Pipeline 流程（异步）
        
        Args:
            config: Pipeline 配置字典
        """
        def _run():
            logger.info("开始执行即时 Pipeline 任务")
            try:
                from core.pipeline import PipelineConfig, run_pipeline
                
                pipeline_config = PipelineConfig()
                for key, value in config.items():
                    if hasattr(pipeline_config, key):
                        setattr(pipeline_config, key, value)
                
                result = run_pipeline(pipeline_config)
                logger.info(f"即时 Pipeline 任务完成 - 爬取: {result.crawled}, 下载: {result.downloaded}, "
                           f"字幕: {result.subtitled}, 分析: {result.analyzed}")
            except Exception as e:
                error_logger.error(f"即时 Pipeline 任务执行失败: {e}")
        
        thread = spawn(target=_run, daemon=True)
        thread.start()
    
    def _cleanup_logs(self) -> None:
        """清理过期日志文件"""
        try:
            logs_dir = get_logs_dir()
            now = time.time()
            max_age = 7 * 24 * 3600
            
            for filename in os.listdir(logs_dir):
                filepath = os.path.join(logs_dir, filename)
                if os.path.isfile(filepath):
                    mtime = os.path.getmtime(filepath)
                    if now - mtime > max_age:
                        os.remove(filepath)
                        logger.info(f"清理过期日志: {filename}")
            
        except Exception as e:
            logger.error(f"日志清理失败: {e}")
    
    def is_running(self) -> bool:
        """检查调度器是否在运行"""
        return self._running
    
    def get_scheduled_tasks(self) -> Dict[str, str]:
        """获取所有已调度的任务"""
        return dict(self._scheduled_tasks)
    
    def get_scheduler_info(self) -> Dict[str, Any]:
        """获取调度器信息"""
        jobs = self._scheduler.get_jobs()
        return {
            "running": self._running,
            "task_count": len(jobs),
            "tasks": [{"id": job.id, "name": job.name, "next_run": str(job.next_run_time)} for job in jobs],
        }


# 便捷函数
_task_scheduler: Optional[TaskScheduler] = None


def get_scheduler() -> TaskScheduler:
    """获取任务调度器实例（单例）"""
    global _task_scheduler
    if _task_scheduler is None:
        _task_scheduler = TaskScheduler()
    return _task_scheduler


def start_scheduler() -> None:
    """启动任务调度器"""
    get_scheduler().start()


def stop_scheduler() -> None:
    """停止任务调度器"""
    if _task_scheduler:
        _task_scheduler.stop()


def init_scheduler() -> None:
    """初始化任务调度器（添加默认任务）"""
    global _task_scheduler
    _task_scheduler = TaskScheduler()
    
    _task_scheduler.add_health_check(minutes=30)
    _task_scheduler.add_log_cleanup(hours=24)
    
    logger.info("任务调度器初始化完成，已添加默认任务")


def schedule_pipeline(
    config: Dict[str, Any],
    hours: Optional[int] = None,
    minutes: Optional[int] = None,
    day: Optional[int] = None,
    weekday: Optional[int] = None,
    id: str = "scheduled_pipeline"
) -> str:
    """
    便捷函数：调度 Pipeline 流程
    
    Args:
        config: Pipeline 配置字典
        hours: 执行小时
        minutes: 执行分钟
        day: 执行日期
        weekday: 执行星期
        id: 任务 ID
        
    Returns:
        任务 ID
    """
    return get_scheduler().schedule_pipeline(config, hours, minutes, day, weekday, id)


def run_pipeline_now(config: Dict[str, Any]) -> None:
    """
    便捷函数：立即执行 Pipeline 流程
    
    Args:
        config: Pipeline 配置字典
    """
    get_scheduler().run_pipeline_now(config)
