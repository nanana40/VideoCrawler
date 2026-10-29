"""
任务队列模块

管理任务队列、重试次数控制、死信队列。

功能特性：
    1. 任务队列管理
    2. 重试次数控制
    3. 死信队列逻辑
    4. 失败任务自动迁移

AUDIT-0024: 基础设施已定义但未接入 Pipeline/TaskScheduler，
init_queue_manager() 仅在 app_initializer 里初始化单例，
无业务代码调用 QueueManager/TaskQueue 方法。留作未来接入入口。
"""

import time
from typing import Optional, Dict, Any, List, Callable

from utils.enums import TaskStatus, TaskPriority
from utils.logger import get_crawler_logger


logger = get_crawler_logger()


class TaskQueue:
    """
    任务队列
    
    管理任务的入队、出队和重试逻辑。
    """
    
    def __init__(self, max_retries: int = 3) -> None:
        """
        初始化任务队列
        
        Args:
            max_retries: 最大重试次数
        """
        self._max_retries = max_retries
        self._queue: List[Dict[str, Any]] = []
        self._dead_letter: List[Dict[str, Any]] = []
        self._processing: Dict[str, Dict[str, Any]] = {}
        self._lock = __import__("threading").Lock()
    
    def enqueue(
        self,
        task_id: str,
        task_type: str,
        data: Dict[str, Any],
        priority: TaskPriority = TaskPriority.NORMAL
    ) -> None:
        """
        入队任务
        
        Args:
            task_id: 任务 ID
            task_type: 任务类型
            data: 任务数据
            priority: 任务优先级
        """
        task = {
            "task_id": task_id,
            "task_type": task_type,
            "data": data,
            "priority": priority.value,
            "retry_count": 0,
            "status": TaskStatus.PENDING.value,
            "created_at": time.time(),
            "updated_at": time.time(),
        }
        
        with self._lock:
            self._queue.append(task)
            self._queue.sort(key=lambda x: (-x["priority"], x["created_at"]))
        
        logger.info(f"任务入队: {task_id} (类型: {task_type}, 优先级: {priority.display_name})")
    
    def dequeue(self) -> Optional[Dict[str, Any]]:
        """
        出队任务
        
        Returns:
            任务字典，如果队列为空返回 None
        """
        with self._lock:
            if not self._queue:
                return None
            
            task = self._queue.pop(0)
            task["status"] = TaskStatus.CRAWLING.value
            task["updated_at"] = time.time()
            self._processing[task["task_id"]] = task
        
        return task
    
    def complete(self, task_id: str) -> bool:
        """
        标记任务完成
        
        Args:
            task_id: 任务 ID
            
        Returns:
            True 表示成功标记
        """
        with self._lock:
            if task_id not in self._processing:
                return False
            
            task = self._processing.pop(task_id)
            task["status"] = TaskStatus.COMPLETED.value
            task["updated_at"] = time.time()
        
        logger.info(f"任务完成: {task_id}")
        return True
    
    def fail(self, task_id: str, error_message: str = "") -> bool:
        """
        标记任务失败，根据重试次数决定是否重新入队或进入死信队列
        
        Args:
            task_id: 任务 ID
            error_message: 错误信息
            
        Returns:
            True 表示已处理（重新入队或进入死信）
        """
        with self._lock:
            if task_id not in self._processing:
                return False
            
            task = self._processing.pop(task_id)
            task["retry_count"] += 1
            task["error_message"] = error_message
            task["updated_at"] = time.time()
            
            if task["retry_count"] < self._max_retries:
                task["status"] = TaskStatus.PENDING.value
                self._queue.append(task)
                self._queue.sort(key=lambda x: (-x["priority"], x["created_at"]))
                logger.warning(f"任务失败，已重新入队: {task_id} (重试次数: {task['retry_count']}/{self._max_retries})")
            else:
                task["status"] = TaskStatus.DEAD_LETTER.value
                self._dead_letter.append(task)
                logger.error(f"任务失败，已进入死信队列: {task_id} (重试次数: {task['retry_count']})")
        
        return True
    
    def get_dead_letter(self) -> List[Dict[str, Any]]:
        """获取死信队列"""
        return list(self._dead_letter)
    
    def clear_dead_letter(self) -> None:
        """清空死信队列"""
        self._dead_letter.clear()
        logger.info("死信队列已清空")
    
    def retry_dead_letter(self) -> int:
        """将死信队列中的任务重新入队"""
        count = 0
        with self._lock:
            for task in self._dead_letter:
                task["retry_count"] = 0
                task["status"] = TaskStatus.PENDING.value
                task["updated_at"] = time.time()
                self._queue.append(task)
                count += 1
            
            self._dead_letter.clear()
        
        logger.info(f"已将 {count} 个死信任务重新入队")
        return count
    
    def get_queue_status(self) -> Dict[str, Any]:
        """获取队列状态"""
        with self._lock:
            pending = [t for t in self._queue if t["status"] == TaskStatus.PENDING.value]
            return {
                "total_pending": len(self._queue),
                "processing": len(self._processing),
                "dead_letter": len(self._dead_letter),
                "high_priority": len([t for t in pending if t["priority"] == TaskPriority.HIGH.value]),
                "normal_priority": len([t for t in pending if t["priority"] == TaskPriority.NORMAL.value]),
            }
    
    def is_empty(self) -> bool:
        """检查队列是否为空"""
        return len(self._queue) == 0
    
    def get_size(self) -> int:
        """获取队列大小"""
        return len(self._queue)


class QueueManager:
    """
    队列管理器
    
    管理多个任务队列，提供统一的队列操作接口。
    """
    
    def __init__(self) -> None:
        """初始化队列管理器"""
        self._queues: Dict[str, TaskQueue] = {}
        logger.info("队列管理器初始化完成")
    
    def get_queue(self, queue_name: str, max_retries: int = 3) -> TaskQueue:
        """
        获取或创建队列
        
        Args:
            queue_name: 队列名称
            max_retries: 最大重试次数
            
        Returns:
            TaskQueue 实例
        """
        if queue_name not in self._queues:
            self._queues[queue_name] = TaskQueue(max_retries=max_retries)
        
        return self._queues[queue_name]
    
    def enqueue(
        self,
        queue_name: str,
        task_id: str,
        task_type: str,
        data: Dict[str, Any],
        priority: TaskPriority = TaskPriority.NORMAL
    ) -> None:
        """
        入队任务
        
        Args:
            queue_name: 队列名称
            task_id: 任务 ID
            task_type: 任务类型
            data: 任务数据
            priority: 任务优先级
        """
        queue = self.get_queue(queue_name)
        queue.enqueue(task_id, task_type, data, priority)
    
    def dequeue(self, queue_name: str) -> Optional[Dict[str, Any]]:
        """
        出队任务
        
        Args:
            queue_name: 队列名称
            
        Returns:
            任务字典，如果队列为空返回 None
        """
        queue = self.get_queue(queue_name)
        return queue.dequeue()
    
    def complete(self, queue_name: str, task_id: str) -> bool:
        """
        标记任务完成
        
        Args:
            queue_name: 队列名称
            task_id: 任务 ID
            
        Returns:
            True 表示成功标记
        """
        queue = self.get_queue(queue_name)
        return queue.complete(task_id)
    
    def fail(self, queue_name: str, task_id: str, error_message: str = "") -> bool:
        """
        标记任务失败
        
        Args:
            queue_name: 队列名称
            task_id: 任务 ID
            error_message: 错误信息
            
        Returns:
            True 表示已处理
        """
        queue = self.get_queue(queue_name)
        return queue.fail(task_id, error_message)
    
    def get_all_dead_letter(self) -> Dict[str, List[Dict[str, Any]]]:
        """获取所有队列的死信"""
        result = {}
        for name, queue in self._queues.items():
            dead = queue.get_dead_letter()
            if dead:
                result[name] = dead
        return result
    
    def retry_all_dead_letter(self) -> Dict[str, int]:
        """重试所有队列的死信"""
        result = {}
        for name, queue in self._queues.items():
            count = queue.retry_dead_letter()
            if count > 0:
                result[name] = count
        return result
    
    def get_all_status(self) -> Dict[str, Dict[str, Any]]:
        """获取所有队列的状态"""
        result = {}
        for name, queue in self._queues.items():
            result[name] = queue.get_queue_status()
        return result


# 便捷函数
_queue_manager: Optional[QueueManager] = None


def get_queue_manager() -> QueueManager:
    """获取队列管理器实例（单例）"""
    global _queue_manager
    if _queue_manager is None:
        _queue_manager = QueueManager()
    return _queue_manager


def get_queue(queue_name: str, max_retries: int = 3) -> TaskQueue:
    """
    便捷函数：获取或创建队列
    
    Args:
        queue_name: 队列名称
        max_retries: 最大重试次数
        
    Returns:
        TaskQueue 实例
    """
    return get_queue_manager().get_queue(queue_name, max_retries)


def enqueue_task(
    queue_name: str,
    task_id: str,
    task_type: str,
    data: Dict[str, Any],
    priority: TaskPriority = TaskPriority.NORMAL
) -> None:
    """
    便捷函数：入队任务
    
    Args:
        queue_name: 队列名称
        task_id: 任务 ID
        task_type: 任务类型
        data: 任务数据
        priority: 任务优先级
    """
    get_queue_manager().enqueue(queue_name, task_id, task_type, data, priority)


def init_queue_manager() -> None:
    """初始化队列管理器"""
    global _queue_manager
    _queue_manager = QueueManager()
