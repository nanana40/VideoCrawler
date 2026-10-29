"""
pool.py — 视频候选池封装

Pipeline 完成烧录后 → 调 add() 入池
发布页 UI → 调 list_recent() / list_all() 取列表
"""

from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

from loguru import logger

from . import storage


class VideoPool:
    @staticmethod
    def add(
        final_video_path: str,
        source_url: str = "",
        video_id: str = "",
        cover_path: str = "",
        srt_path: str = "",
        title_original: str = "",
        title_translated: str = "",
        desc_original: str = "",
        desc_translated: str = "",
        thumbnail_url: str = "",
        lang: str = "",
        category: str = "",
        channel_name: str = "",
        duration_sec: int = 0,
        pipeline_source: str = "manual",
        copy_path: str = "",
    ) -> int:
        """烧录完成后入池。返回 pool_id。"""
        if not os.path.exists(final_video_path):
            logger.warning(f"[VideoPool] final_video_path 不存在，不入池: {final_video_path}")
            return 0

        pool_id = storage.add_to_pool(
            final_video_path=final_video_path,
            source_url=source_url,
            video_id=video_id,
            cover_path=cover_path,
            srt_path=srt_path,
            title_original=title_original,
            title_translated=title_translated,
            desc_original=desc_original,
            desc_translated=desc_translated,
            thumbnail_url=thumbnail_url,
            lang=lang,
            category=category,
            channel_name=channel_name,
            duration_sec=duration_sec,
            pipeline_source=pipeline_source,
            copy_path=copy_path,
        )
        logger.info(f"[VideoPool] 入池: id={pool_id} video={os.path.basename(final_video_path)} source={pipeline_source}")
        return pool_id

    @staticmethod
    def list_recent(hours: int = 72, pipeline_source: Optional[str] = None) -> List[Dict[str, Any]]:
        """近 N 小时内完成的视频"""
        return storage.list_pool(only_recent=True, hours=hours, pipeline_source=pipeline_source)

    @staticmethod
    def list_all(pipeline_source: Optional[str] = None) -> List[Dict[str, Any]]:
        """所有视频（仍然只返回文件存在的）"""
        return storage.list_pool(only_recent=False, pipeline_source=pipeline_source)

    @staticmethod
    def get(pool_id: int) -> Optional[Dict[str, Any]]:
        return storage.get_pool_item(pool_id)

    @staticmethod
    def mark_published(pool_id: int, platform_id: str, remote_id: str = "") -> None:
        storage.update_pool_publish_status(
            pool_id, status=1, platform_id=f"{platform_id}:{remote_id}" if remote_id else platform_id
        )

    @staticmethod
    def mark_failed(pool_id: int, error_msg: str) -> None:
        storage.update_pool_publish_status(pool_id, status=3, error_msg=error_msg)

    @staticmethod
    def cleanup_expired(hours: int = 72) -> int:
        return storage.delete_expired_pool(hours=hours)
