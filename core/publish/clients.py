"""
clients.py — 四大平台发布客户端

架构：
  BasePlatformClient — 抽象基类，定义统一接口 + cookie 管理
  BilibiliClient     — B站上传（API 相对开放）
  DouyinClient       — 抖音（cookie 逆向）
  XiaohongshuClient  — 小红书（cookie 逆向）
  KuaishouClient     — 快手（cookie 逆向）

所有客户端都是 **同步 + requests**，GUI 层负责在后台线程调用。
cookie 解密 / 加密由 accounts.py 负责，这里只拿到明文 cookie 字符串。

⚠️ 平台私有 API 随时可能变更。这里提供的是稳定骨架：
   - upload_video / update_video_meta 等方法有真实 HTTP 实现
   - 部分参数可能需要根据最新逆向结果微调
"""

from __future__ import annotations

import json
import os
import re
import time
import threading
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import requests
from ._cookie_utils import parse_cookies_to_dict  # AUDIT-0025
from loguru import logger


# ============================================================
# 统一数据结构
# ============================================================

@dataclass
class PublishResult:
    """单次发布结果"""
    success: bool
    remote_id: str = ""          # 平台返回的作品 id
    remote_url: str = ""         # 作品访问链接
    error_msg: str = ""
    uploaded_bytes: int = 0
    duration_ms: int = 0         # 上传耗时


@dataclass
class VideoMeta:
    """上传前需要组装的元数据"""
    title: str = ""
    description: str = ""
    tags: List[str] = field(default_factory=list)
    category: str = ""           # 平台分区 id（B站有，其他平台可能不用）
    cover_path: str = ""          # 封面绝对路径
    scheduled_ts: Optional[int] = None  # 定时发布时间戳（None=立即）
    original_declaration: bool = True   # 原创声明
    allow_comment: bool = True
    allow_duet: bool = True       # 抖音合拍权限
    location: str = ""            # 地理位置（可选）


def normalize_tags(raw) -> list[str]:
    """
    把各种可能的 tags 输入统一成干净的 list[str]。

    输入类型:
      - None / [] → []
      - str  "AI,科技,自媒体" → ["AI", "科技", "自媒体"]  ← 关键！
      - list ["AI", "科技"] → 原样（strip + 去空）
      - list 里混 str/其他 → 只保留 str
    """
    if raw is None:
        return []
    if isinstance(raw, str):
        # 逗号 / 中文逗号 / 空格 / 分号 都能分隔
        import re
        parts = re.split(r"[,\，\s;；]+", raw.strip())
        return [p.lstrip("#").strip() for p in parts if p.strip()]
    if isinstance(raw, (list, tuple)):
        result = []
        for item in raw:
            if item is None:
                continue
            s = str(item).lstrip("#").strip()
            if s:
                result.append(s)
        return result
    return []


# ============================================================
# 抽象基类
# ============================================================

class BasePlatformClient(ABC):
    """所有平台客户端的公共基底"""

    platform_id: str = ""          # 子类覆写，如 "bilibili"
    platform_label: str = ""       # "哔哩哔哩"
    base_url: str = ""

    def __init__(self, cookies: str, user_agent: str = ""):
        self._cookies_raw = cookies
        self._cookies = self._parse_cookies(cookies)
        self._session = requests.Session()
        self._session.headers.update({
            "User-Agent": user_agent or (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/131.0.0.0 Safari/537.36"
            ),
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        })
        # 把 cookies 注入 session
        for k, v in self._cookies.items():
            self._session.cookies.set(k, v, domain=self._cookie_domain())

    # ---- 工具方法 ----

    @staticmethod
    def _parse_cookies(raw: str) -> Dict[str, str]:
        """委托 _cookie_utils.parse_cookies_to_dict — AUDIT-0025 去重"""
        return parse_cookies_to_dict(raw)

    def _cookie_header(self) -> str:
        return "; ".join(f"{k}={v}" for k, v in self._cookies.items())

    @abstractmethod
    def _cookie_domain(self) -> str:
        """cookie 所属域名"""

    # ---- 必须由子类实现 ----

    @abstractmethod
    def verify_login(self) -> bool:
        """校验 cookie 是否有效（请求个人信息接口，不抛异常且返回成功则有效）"""

    @abstractmethod
    def upload_video(self, video_path: str, meta: VideoMeta, progress_cb=None) -> PublishResult:
        """
        上传视频 + 设置元数据 + 发布
        progress_cb(uploaded_bytes, total_bytes) — 可选回调
        """

    # ---- 通用工具 ----

    def _post_json(self, url: str, data: Any, extra_headers: Optional[Dict] = None) -> requests.Response:
        headers = {"Content-Type": "application/json"}
        if extra_headers:
            headers.update(extra_headers)
        return self._session.post(url, json=data, headers=headers, timeout=30)

    def _get(self, url: str, params: Optional[Dict] = None) -> requests.Response:
        return self._session.get(url, params=params, timeout=30)


# ============================================================
# Bilibili — API 相对开放，走官方投稿接口
# ============================================================

class BilibiliClient(BasePlatformClient):
    """
    B 站客户端 — 视频上传走 biliup CLI（Go 写的独立工具），
    cookie 探活走 HTTP API。

    biliup GitHub: https://github.com/biliup/biliup
    social-auto-upload 也用它来上传 B 站视频。
    """
    platform_id = "bilibili"
    platform_label = "哔哩哔哩"
    base_url = "https://api.bilibili.com"

    def __init__(self, cookies: str, user_agent: str = "", nickname: str = ""):
        super().__init__(cookies, user_agent)
        self._nickname = nickname
        # biliup account 文件缓存路径
        from pathlib import Path as _P
        import tempfile
        self._account_file = _P(tempfile.gettempdir()) / f"videocrawler_biliup_{id(self)}.json"

    def _cookie_domain(self) -> str:
        return ".bilibili.com"

    def verify_login(self) -> bool:
        """用 B 站官方 nav 接口探活 cookie"""
        try:
            resp = self._get("https://api.bilibili.com/x/web-interface/nav")
            data = resp.json()
            ok = data.get("code") == 0 and data.get("data", {}).get("mid")
            if ok:
                self._nickname = data["data"].get("uname", self._nickname)
            return ok
        except Exception as e:
            logger.warning(f"[Bilibili] verify_login 失败: {e}")
            return False

    def upload_video(
        self, video_path: str, meta: VideoMeta, progress_cb=None
    ) -> PublishResult:
        from .biliup_runtime import biliup_upload, write_biliup_account

        t0 = time.time()
        try:
            if not os.path.exists(video_path):
                return PublishResult(False, error_msg=f"视频文件不存在: {video_path}")

            # 1. 生成 biliup account 文件
            write_biliup_account(self._account_file, self._cookies_raw, self._nickname)

            # 2. 调用 biliup 上传
            tid = int(meta.category) if meta.category else 22  # 默认"生活"
            success, result = biliup_upload(
                account_file=self._account_file,
                video_path=video_path,
                title=(meta.title or os.path.basename(video_path))[:80],
                description=(meta.description or "")[:250],
                tid=tid,
                tags=meta.tags[:10] if meta.tags else None,
                cover_path=meta.cover_path or "",
                schedule_ts=meta.scheduled_ts,
            )

            duration_ms = int((time.time() - t0) * 1000)

            if success:
                # result 可能是 BV 号或成功消息
                remote_id = result if result.startswith("BV") else ""
                remote_url = f"https://www.bilibili.com/video/{remote_id}" if remote_id else ""
                return PublishResult(
                    success=True,
                    remote_id=remote_id,
                    remote_url=remote_url,
                    error_msg="",
                    duration_ms=duration_ms,
                )
            else:
                return PublishResult(
                    success=False,
                    error_msg=result,
                    duration_ms=duration_ms,
                )

        except Exception as e:
            import traceback
            logger.error(f"[Bilibili] upload_video 异常: {e}\n{traceback.format_exc()}")
            return PublishResult(
                success=False,
                error_msg=str(e),
                duration_ms=int((time.time() - t0) * 1000),
            )


# ============================================================
# 抖音 / 小红书 / 快手 — Playwright 浏览器自动化上传
# 这三个平台没有稳定的公开 API，全行业（包括 social-auto-upload）
# 都走 Playwright/Patchright 驱动浏览器自动填表单。
#
# 这里用我们自己的 playwright_base.py + playwright_uploaders.py，
# 底层用系统 Edge，避免下载 Playwright 自带浏览器。
# ============================================================

class DouyinClient(BasePlatformClient):
    platform_id = "douyin"
    platform_label = "抖音"
    base_url = "https://www.douyin.com"

    def __init__(self, cookies: str, user_agent: str = "", headless: bool = False):
        super().__init__(cookies, user_agent)
        self._headless = headless

    def _cookie_domain(self) -> str:
        return ".douyin.com"

    def verify_login(self) -> bool:
        try:
            resp = self._get("https://www.douyin.com/webcast/room/web/enter/", params={"aid": "6383"})
            if resp.status_code == 200 and "passport" not in resp.text[:2000].lower():
                return True
            return False
        except Exception as e:
            logger.warning(f"[抖音] verify_login 失败: {e}")
            return False

    def upload_video(
        self, video_path: str, meta: VideoMeta, progress_cb=None
    ) -> PublishResult:
        from .playwright_uploaders import DouyinPlaywrightUploader
        t0 = time.time()
        try:
            uploader = DouyinPlaywrightUploader(self._cookies_raw, headless=self._headless)
            ok, msg = uploader.upload_sync(video_path, meta, progress_cb=progress_cb)
            return PublishResult(
                success=ok,
                error_msg="" if ok else msg,
                duration_ms=int((time.time() - t0) * 1000),
            )
        except Exception as e:
            import traceback
            logger.error(f"[抖音] upload_video 异常: {e}\n{traceback.format_exc()}")
            return PublishResult(False, error_msg=str(e), duration_ms=int((time.time() - t0) * 1000))


class XiaohongshuClient(BasePlatformClient):
    platform_id = "xiaohongshu"
    platform_label = "小红书"
    base_url = "https://www.xiaohongshu.com"

    def __init__(self, cookies: str, user_agent: str = "", headless: bool = False):
        super().__init__(cookies, user_agent)
        self._headless = headless

    def _cookie_domain(self) -> str:
        return ".xiaohongshu.com"

    def verify_login(self) -> bool:
        try:
            resp = self._get("https://www.xiaohongshu.com/api/sns/web/v1/user/me")
            if resp.status_code == 200:
                j = resp.json()
                return j.get("code") == 0
            return False
        except Exception as e:
            logger.warning(f"[小红书] verify_login 失败: {e}")
            return False

    def upload_video(
        self, video_path: str, meta: VideoMeta, progress_cb=None
    ) -> PublishResult:
        t0 = time.time()

        # ── 优先走逆向 HTTP API（最快最稳，不启浏览器）──
        try:
            from .xhs_api_client import XhsApiClient
            api_cookies = self._cookies.copy()
            if "a1" in api_cookies:
                logger.info("[小红书] 尝试 API 发布 (逆向 creator API)...")
                api_client = XhsApiClient(cookies=api_cookies)
                result = api_client.upload_video(
                    video_path=video_path,
                    title=(meta.title or os.path.basename(video_path))[:20],
                    desc=(meta.description or "")[:1000],
                    cover_path=meta.cover_path or None,
                    topics=meta.tags[:10] if meta.tags else None,
                )
                duration_ms = int((time.time() - t0) * 1000)
                if result.get("success"):
                    note_id = result.get("note_id") or ""
                    note_url = f"https://www.xiaohongshu.com/explore/{note_id}" if note_id else ""
                    logger.success(f"[小红书] API 发布成功 note_id={note_id}")
                    return PublishResult(
                        success=True,
                        remote_id=note_id,
                        remote_url=note_url,
                        duration_ms=duration_ms,
                    )
                else:
                    logger.warning(f"[小红书] API 返回失败, 降级到 Playwright: {result}")
            else:
                logger.info("[小红书] cookies 缺 a1, 跳过 API, 直接 Playwright")
        except Exception as api_err:
            logger.warning(f"[小红书] API 发布异常, 降级 Playwright: {api_err}")

        # ── fallback: Playwright 浏览器自动化 ──
        try:
            from .playwright_uploaders import XiaohongshuPlaywrightUploader
            logger.info("[小红书] 启动 Playwright fallback 上传...")
            uploader = XiaohongshuPlaywrightUploader(self._cookies_raw, headless=self._headless)
            ok, msg = uploader.upload_sync(video_path, meta, progress_cb=progress_cb)
            return PublishResult(
                success=ok,
                error_msg="" if ok else msg,
                duration_ms=int((time.time() - t0) * 1000),
            )
        except Exception as e:
            import traceback
            logger.error(f"[小红书] Playwright fallback 也崩了: {e}\n{traceback.format_exc()}")
            return PublishResult(False, error_msg=str(e), duration_ms=int((time.time() - t0) * 1000))


class KuaishouClient(BasePlatformClient):
    platform_id = "kuaishou"
    platform_label = "快手"
    base_url = "https://www.kuaishou.com"

    def __init__(self, cookies: str, user_agent: str = "", headless: bool = False):
        super().__init__(cookies, user_agent)
        self._headless = headless

    def _cookie_domain(self) -> str:
        return ".kuaishou.com"

    def verify_login(self) -> bool:
        try:
            resp = self._get("https://www.kuaishou.com/graphql", params={"op": "profile"})
            return resp.status_code == 200
        except Exception as e:
            logger.warning(f"[快手] verify_login 失败: {e}")
            return False

    def upload_video(
        self, video_path: str, meta: VideoMeta, progress_cb=None
    ) -> PublishResult:
        from .playwright_uploaders import KuaishouPlaywrightUploader
        t0 = time.time()
        try:
            uploader = KuaishouPlaywrightUploader(self._cookies_raw, headless=self._headless)
            ok, msg = uploader.upload_sync(video_path, meta, progress_cb=progress_cb)
            return PublishResult(
                success=ok,
                error_msg="" if ok else msg,
                duration_ms=int((time.time() - t0) * 1000),
            )
        except Exception as e:
            import traceback
            logger.error(f"[快手] upload_video 异常: {e}\n{traceback.format_exc()}")
            return PublishResult(False, error_msg=str(e), duration_ms=int((time.time() - t0) * 1000))


# ============================================================
# 工厂
# ============================================================

class PlatformClientFactory:
    _registry = {
        "bilibili": BilibiliClient,
        "douyin": DouyinClient,
        "xiaohongshu": XiaohongshuClient,
        "kuaishou": KuaishouClient,
    }

    @classmethod
    def create(cls, platform_id: str, cookies: str, **kwargs) -> BasePlatformClient:
        # 账号里存的是官方开放平台凭证（JSON, auth_mode=open_api）→ 走官方 API 客户端
        # 延迟 import：open_api_clients 依赖本模块，顶层互引会循环
        from .open_api_clients import parse_open_api_credentials, build_open_api_client

        creds = parse_open_api_credentials(cookies)
        if creds is not None:
            return build_open_api_client(platform_id, creds)

        klass = cls._registry.get(platform_id)
        if not klass:
            raise ValueError(f"未知平台: {platform_id}")
        return klass(cookies=cookies, **kwargs)

    @classmethod
    def available(cls) -> List[str]:
        return list(cls._registry.keys())
