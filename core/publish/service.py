"""
service.py — 发布上层编排

把账号选择、客户端创建、视频上传、结果落库串起来。
GUI 和管线都只调这个模块的 publish()。
"""

from __future__ import annotations

import os
import threading
from typing import Any, Callable, Dict, List, Optional

from loguru import logger

from . import storage
from .accounts import AccountManager
from .clients import PlatformClientFactory, VideoMeta
from .pool import VideoPool


class PublishService:
    """单次发布编排器"""

    @staticmethod
    def publish(
        pool_id: int,
        account_id: int,
        meta: VideoMeta,
        on_progress: Optional[Callable[[int, int], None]] = None,
    ) -> Dict[str, Any]:
        """
        执行一次发布。返回 {'ok', 'remote_id', 'remote_url', 'error', 'duration_ms'}

        :param pool_id:      video_pool.id
        :param account_id:   publish_account.id
        :param meta:         已由 UI 编辑好的 VideoMeta
        :param on_progress:  上传进度回调 (uploaded_bytes, total_bytes)
        """
        pool_item = VideoPool.get(pool_id)
        if not pool_item:
            return {"ok": False, "error": f"候选池条目不存在: pool_id={pool_id}"}

        acc = AccountManager.get_account(account_id)
        if not acc:
            return {"ok": False, "error": f"账号不存在: account_id={account_id}"}

        platform = acc["platform"]
        cookies = acc["cookies"]

        # 用池里的封面兜底
        video_path = pool_item["final_video_path"]
        if not meta.cover_path and pool_item.get("cover_path"):
            if os.path.exists(pool_item["cover_path"]):
                meta.cover_path = pool_item["cover_path"]

        # 默认标题兜底
        if not meta.title:
            meta.title = pool_item.get("title_translated") or pool_item.get("title_original") or os.path.basename(video_path)

        # 描述兜底
        if not meta.description:
            meta.description = pool_item.get("desc_translated") or pool_item.get("desc_original") or ""

        try:
            client = PlatformClientFactory.create(platform, cookies=cookies)
            # 官方 OpenAPI 客户端：token 刷新后把新凭证回写 DB，避免下次还要重新授权
            if hasattr(client, "on_credentials_changed"):
                client.on_credentials_changed = lambda creds: PublishService._persist_credentials(
                    account_id, platform, creds, acc
                )
            result = client.upload_video(video_path, meta, progress_cb=on_progress)

            if result.success:
                VideoPool.mark_published(pool_id, platform, result.remote_id)
                storage.add_publish_record(
                    pool_id=pool_id,
                    account_id=account_id,
                    platform=platform,
                    remote_id=result.remote_id,
                    title=meta.title,
                    status=1,
                    error_msg="",
                    scheduled_ts=meta.scheduled_ts,
                )
                logger.info(f"[PublishService] ✅ 发布成功: platform={platform} pool={pool_id} remote={result.remote_id}")
                return {
                    "ok": True,
                    "remote_id": result.remote_id,
                    "remote_url": result.remote_url,
                    "error": "",
                    "duration_ms": result.duration_ms,
                }
            else:
                VideoPool.mark_failed(pool_id, result.error_msg)
                storage.add_publish_record(
                    pool_id=pool_id,
                    account_id=account_id,
                    platform=platform,
                    remote_id="",
                    title=meta.title,
                    status=2,
                    error_msg=result.error_msg,
                    scheduled_ts=meta.scheduled_ts,
                )
                logger.error(f"[PublishService] ❌ 发布失败: platform={platform} pool={pool_id} err={result.error_msg}")
                return {"ok": False, "error": result.error_msg, "duration_ms": result.duration_ms}

        except Exception as e:
            import traceback
            logger.error(f"[PublishService] 💥 发布异常: {e}\n{traceback.format_exc()}")
            VideoPool.mark_failed(pool_id, str(e))
            return {"ok": False, "error": str(e)}

    # ------------------------------------------------------------------
    @staticmethod
    def _persist_credentials(account_id: int, platform: str, creds: Dict[str, Any],
                             acc: Optional[Dict[str, Any]] = None) -> None:
        """官方 OpenAPI 刷新 token 后回写账号凭证（保持 nickname/uid 不变）"""
        try:
            from .open_api_clients import dump_open_api_credentials

            old = acc or AccountManager.get_account(account_id) or {}
            storage.upsert_account(
                platform=platform,
                cookies=dump_open_api_credentials(creds),
                nickname=old.get("nickname", "") or "",
                uid=old.get("uid", "") or "",
                cookie_src=old.get("cookie_src", "open_api") or "open_api",
                account_id=account_id,
            )
            logger.info(f"[PublishService] 开放平台凭证已回写: account_id={account_id} platform={platform}")
        except Exception as e:
            logger.warning(f"[PublishService] 凭证回写失败(不影响发布): {e}")
