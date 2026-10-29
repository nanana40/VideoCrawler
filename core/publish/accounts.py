"""
accounts.py — 平台账号管理

功能：
  - cookie 加密存储（复用 crypto_util Fernet）
  - CDP 浏览器 cookie 自动提取（复用 cdp_cookies 模块）
  - 有效性定时探测（verify_login 轮询）
"""

from __future__ import annotations

import threading
from typing import Any, Dict, List, Optional

from loguru import logger

from . import storage
from .clients import PlatformClientFactory


class AccountManager:
    """账号管理统一入口"""

    _lock = threading.Lock()

    @classmethod
    def list_accounts(
        cls, platform: Optional[str] = None, only_active: bool = True
    ) -> List[Dict[str, Any]]:
        return storage.list_accounts(platform=platform, only_active=only_active)

    @classmethod
    def get_account(cls, account_id: int) -> Optional[Dict[str, Any]]:
        return storage.get_account(account_id)

    @classmethod
    def add_account(
        cls,
        platform: str,
        cookies: str,
        nickname: str = "",
        uid: str = "",
        cookie_src: str = "manual",
        cdp_browser: str = "",
    ) -> int:
        with cls._lock:
            return storage.upsert_account(
                platform=platform,
                cookies=cookies,
                nickname=nickname,
                uid=uid,
                cookie_src=cookie_src,
                cdp_browser=cdp_browser,
            )

    @classmethod
    def delete_account(cls, account_id: int) -> None:
        storage.delete_account(account_id)

    @classmethod
    def set_active(cls, account_id: int, active: bool) -> None:
        storage.set_account_active(account_id, active)

    @classmethod
    def verify_account(cls, account_id: int) -> Dict[str, Any]:
        """探测账号有效性。返回 {'ok': bool, 'nickname': str, 'uid': str, 'error': str}"""
        acc = storage.get_account(account_id)
        if not acc:
            return {"ok": False, "error": "账号不存在"}

        try:
            client = PlatformClientFactory.create(acc["platform"], acc["cookies"])
            ok = client.verify_login()
            nickname = getattr(client, "_nickname_cache", "") if ok else acc.get("nickname", "")
            uid = getattr(client, "_uid_cache", "") if ok else acc.get("uid", "")

            storage.set_account_status(
                account_id,
                check_status=1 if ok else 2,
                nickname=nickname or None,
                uid=uid or None,
            )
            return {"ok": ok, "nickname": nickname, "uid": uid, "error": "" if ok else "登录已失效"}
        except Exception as e:
            storage.set_account_status(account_id, check_status=2)
            logger.warning(f"[AccountManager] verify_account 异常: {e}")
            return {"ok": False, "error": str(e)}

    @classmethod
    def cdp_extract_cookies(cls, platform: str, browser: str = "edge") -> str:
        """通过 CDP 从浏览器实时拉取 cookie"""
        try:
            from core.cdp_cookies import extract_cookies_for_domain
            domain_map = {
                "bilibili":    ".bilibili.com",
                "douyin":      ".douyin.com",
                "xiaohongshu": ".xiaohongshu.com",
                "kuaishou":    ".kuaishou.com",
            }
            domain = domain_map.get(platform, "")
            if not domain:
                return ""
            cookies = extract_cookies_for_domain(domain, browser=browser)
            return cookies or ""
        except Exception as e:
            logger.warning(f"[AccountManager] CDP cookie 提取失败: {e}")
            return ""
