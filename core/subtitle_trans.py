"""
字幕翻译模块

对接外部翻译 API 或文件夹中转模式，实现视频字幕的自动翻译。

功能特性：
    1. 外部翻译 API 提交
    2. 任务 ID 获取
    3. 任务状态查询
    4. 翻译结果下载
    5. 文件夹中转模式支持
"""

import os
import time
from typing import Optional, Dict, Any, Tuple

from utils.enums import SubtitleMode, TaskStatus
from utils.logger import get_translate_logger
from utils.path_helper import get_translate_queue_dir, get_finished_sub_dir
from utils.config_loader import get_subtitle_config, load_config


logger = get_translate_logger()


class SubtitleTranslator:
    """
    字幕翻译器
    
    支持 API 模式和文件夹中转模式。
    """
    
    def __init__(self) -> None:
        """初始化字幕翻译器"""
        config = get_subtitle_config(load_config())
        self._mode = SubtitleMode.from_code(config.get("mode", "api"), SubtitleMode.API)
        self._api_url = config.get("api_url", "")
        self._target_lang = config.get("target_lang", "zh-CN")
        self._sub_format = config.get("sub_format", "srt")
        self._max_concurrent = config.get("max_concurrent_task", 2)
        self._max_timeout = config.get("max_task_timeout", 600)
        self._translate_queue_dir = get_translate_queue_dir()
        self._finished_sub_dir = get_finished_sub_dir()
        
        os.makedirs(self._translate_queue_dir, exist_ok=True)
        os.makedirs(self._finished_sub_dir, exist_ok=True)
        
        logger.info(f"字幕翻译器初始化完成，模式: {self._mode.display_name}")
    
    def submit_translation(
        self,
        video_id: str,
        video_path: str,
        source_lang: str = "auto",
        target_lang: Optional[str] = None
    ) -> Optional[str]:
        """
        提交翻译任务
        
        Args:
            video_id: 视频 ID
            video_path: 视频文件路径
            source_lang: 源语言
            target_lang: 目标语言
            
        Returns:
            任务 ID，失败返回 None
        """
        if self._mode == SubtitleMode.API:
            return self._submit_via_api(video_id, video_path, source_lang, target_lang)
        else:
            return self._submit_via_folder(video_id, video_path, source_lang, target_lang)
    
    def _submit_via_api(
        self,
        video_id: str,
        video_path: str,
        source_lang: str,
        target_lang: Optional[str]
    ) -> Optional[str]:
        """通过 API 提交翻译任务"""
        if not self._api_url:
            logger.error("未配置翻译 API 地址")
            return None
        
        try:
            import requests as std_requests
            
            data = {
                "video_id": video_id,
                "video_path": video_path,
                "source_lang": source_lang,
                "target_lang": target_lang or self._target_lang,
                "sub_format": self._sub_format,
            }
            
            response = std_requests.post(f"{self._api_url}/submit", json=data, timeout=10)
            response.raise_for_status()
            
            result = response.json()
            task_id = result.get("task_id")
            
            if task_id:
                logger.info(f"翻译任务提交成功，任务 ID: {task_id}")
                return task_id
            
        except Exception as e:
            logger.error(f"通过 API 提交翻译任务失败: {e}")
        
        return None
    
    def _submit_via_folder(
        self,
        video_id: str,
        video_path: str,
        source_lang: str,
        target_lang: Optional[str]
    ) -> Optional[str]:
        """通过文件夹中转提交翻译任务"""
        try:
            task_info = {
                "video_id": video_id,
                "video_path": video_path,
                "source_lang": source_lang,
                "target_lang": target_lang or self._target_lang,
                "sub_format": self._sub_format,
                "status": "pending",
                "created_at": time.time(),
            }
            
            task_file = os.path.join(self._translate_queue_dir, f"{video_id}.json")
            with open(task_file, "w", encoding="utf-8") as f:
                import json
                json.dump(task_info, f, ensure_ascii=False, indent=2)
            
            logger.info(f"翻译任务已写入队列: {task_file}")
            return video_id
        
        except Exception as e:
            logger.error(f"通过文件夹提交翻译任务失败: {e}")
            return None
    
    def check_task_status(self, task_id: str) -> Tuple[TaskStatus, Optional[str]]:
        """
        检查翻译任务状态
        
        Args:
            task_id: 任务 ID
            
        Returns:
            (任务状态, 字幕文件路径)
        """
        if self._mode == SubtitleMode.API:
            return self._check_api_status(task_id)
        else:
            return self._check_folder_status(task_id)
    
    def _check_api_status(self, task_id: str) -> Tuple[TaskStatus, Optional[str]]:
        """检查 API 任务状态"""
        if not self._api_url:
            return TaskStatus.FAILED, None
        
        try:
            import requests as std_requests
            
            response = std_requests.get(f"{self._api_url}/status/{task_id}", timeout=10)
            response.raise_for_status()
            
            result = response.json()
            status_code = result.get("status", "pending")
            
            status_map = {
                "pending": TaskStatus.PENDING,
                "processing": TaskStatus.TRANSLATING,
                "completed": TaskStatus.COMPLETED,
                "failed": TaskStatus.FAILED,
            }
            
            status = status_map.get(status_code, TaskStatus.PENDING)
            subtitle_path = result.get("subtitle_path")
            
            return status, subtitle_path
            
        except Exception as e:
            logger.error(f"检查 API 任务状态失败: {e}")
            return TaskStatus.FAILED, None
    
    def _check_folder_status(self, task_id: str) -> Tuple[TaskStatus, Optional[str]]:
        """检查文件夹中转任务状态"""
        finished_file = os.path.join(self._finished_sub_dir, f"{task_id}.{self._sub_format}")
        
        if os.path.exists(finished_file):
            return TaskStatus.COMPLETED, finished_file
        
        queue_file = os.path.join(self._translate_queue_dir, f"{task_id}.json")
        if os.path.exists(queue_file):
            return TaskStatus.PENDING, None
        
        return TaskStatus.FAILED, None
    
    def download_subtitle(self, task_id: str) -> Optional[str]:
        """
        下载翻译完成的字幕文件
        
        Args:
            task_id: 任务 ID
            
        Returns:
            字幕文件路径，失败返回 None
        """
        if self._mode == SubtitleMode.API:
            return self._download_via_api(task_id)
        else:
            status, path = self._check_folder_status(task_id)
            return path if status == TaskStatus.COMPLETED else None
    
    def _download_via_api(self, task_id: str) -> Optional[str]:
        """通过 API 下载字幕"""
        if not self._api_url:
            return None
        
        try:
            import requests as std_requests
            
            response = std_requests.get(f"{self._api_url}/download/{task_id}", timeout=10)
            response.raise_for_status()
            
            subtitle_path = os.path.join(self._finished_sub_dir, f"{task_id}.{self._sub_format}")
            with open(subtitle_path, "wb") as f:
                f.write(response.content)
            
            logger.info(f"字幕文件已下载: {subtitle_path}")
            return subtitle_path
            
        except Exception as e:
            logger.error(f"下载字幕失败: {e}")
            return None


# 便捷函数
_subtitle_translator: Optional[SubtitleTranslator] = None


def get_subtitle_translator() -> SubtitleTranslator:
    """获取字幕翻译器实例（单例）"""
    global _subtitle_translator
    if _subtitle_translator is None:
        _subtitle_translator = SubtitleTranslator()
    return _subtitle_translator


def submit_translation(
    video_id: str,
    video_path: str,
    source_lang: str = "auto",
    target_lang: Optional[str] = None
) -> Optional[str]:
    """
    便捷函数：提交翻译任务
    
    Args:
        video_id: 视频 ID
        video_path: 视频文件路径
        source_lang: 源语言
        target_lang: 目标语言
        
    Returns:
        任务 ID，失败返回 None
    """
    return get_subtitle_translator().submit_translation(video_id, video_path, source_lang, target_lang)


def check_task_status(task_id: str) -> Tuple[TaskStatus, Optional[str]]:
    """
    便捷函数：检查翻译任务状态
    
    Args:
        task_id: 任务 ID
        
    Returns:
        (任务状态, 字幕文件路径)
    """
    return get_subtitle_translator().check_task_status(task_id)


def download_subtitle(task_id: str) -> Optional[str]:
    """
    便捷函数：下载翻译完成的字幕文件
    
    Args:
        task_id: 任务 ID
        
    Returns:
        字幕文件路径，失败返回 None
    """
    return get_subtitle_translator().download_subtitle(task_id)


def init_subtitle_translator() -> None:
    """初始化字幕翻译器"""
    global _subtitle_translator
    _subtitle_translator = SubtitleTranslator()
