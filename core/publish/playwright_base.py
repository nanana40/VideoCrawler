"""
playwright_base.py — Playwright 浏览器自动化上传基类

设计：
  - 所有平台共用一个 asyncio 事件循环（每个 upload 独立 run_until_complete）
  - cookies 从我们数据库的 cookie 字符串 → Playwright storage_state
  - 默认用系统 Edge（channel='msedge'），也支持 headless 模式

子类只需实现：
  PLATFORM_UPLOAD_URL  — 发布页 URL
  async def do_upload(page, video_path, meta) — 具体的表单填写 + 发布流程
"""

from __future__ import annotations

import asyncio
import json
import os
import tempfile
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Dict, List, Optional

from loguru import logger
from ._cookie_utils import parse_cookies_to_dict  # AUDIT-0025 去重


def _parse_cookies(raw: str, platform_domain: str = "") -> List[Dict[str, Any]]:
    """把 cookie 字符串解析成 Playwright 需要的 cookies 列表

    只保留属于目标 domain 的 cookie，其他平台的丢弃，
    避免 Playwright 因 domain 不匹配而报 "Invalid cookie fields"。
    """
    cookies_dict = parse_cookies_to_dict(raw)
    if not cookies_dict:
        return []

    # 平台 domain 到 cookie 名关键字的映射
    # （cookie 字符串里没 domain 信息，只能按 cookie 名猜测归属平台）
    # ★ 核心 cookie 名必须全列出来，否则会被错误过滤掉
    PLATFORM_KEYWORDS = {
        ".xiaohongshu.com": [
            # 核心鉴权（短名不能用 "in" 匹配，得精确匹配）
            "a1", "webid", "gid", "web_session",
            # 常规前缀/包含匹配
            "xiaohongshu", "xhs", "galaxy_creator", "creator.xiaohongshu",
            "customer-sso", "customerclient", "access-token",
            "unreadlikes", "unreadfollow", "unreadnotify",
            "sc_", "xhs_",
            # 创作者中心
            "creator",
        ],
        ".douyin.com": [
            "douyin", "ttwid", "odin_tt", "passport_csrf_token", "mstoken",
            "bd_ticket_guard", "a_bogus", "websectiga",
            "sessionid", "sid_guard", "uid_tt", "sid_tt",
        ],
        ".bilibili.com": [
            "bilibili", "sessdata", "dedeuserid", "bili_jct", "buvid",
            "ac_time_value", "buvid3", "buvid4",
        ],
        ".kuaishou.com": [
            "kuaishou", "kwscookie", "did", "kuaishouapi",
            "kuaishou_", "cookie3", "passport",
        ],
    }

    # 需要精确匹配的短 cookie 名（<4 字符，避免 "in" 误伤）
    EXACT_NAMES = {
        ".xiaohongshu.com": {"a1", "gid"},
    }

    # 如果没指定平台，直接全部放进去（行为退化）
    if not platform_domain:
        target_keywords = []
        target_exact = set()
    else:
        target_keywords = [k.lower() for k in PLATFORM_KEYWORDS.get(platform_domain, [])]
        target_exact = EXACT_NAMES.get(platform_domain, set())

    result = []
    skipped = 0
    for k, v in cookies_dict.items():
        kl = k.lower()
        # 精确匹配优先
        matched = kl in target_exact
        if not matched:
            matched = any(kw in kl for kw in target_keywords)
        if not matched:
            skipped += 1
            continue

        if isinstance(v, str) and v.startswith("{"):
            try:
                inner = json.loads(v)
                v = inner.get("value", str(v))
            except Exception:
                pass

        cookie = {
            "name": k,
            "value": str(v),
            "domain": platform_domain or ".douyin.com",
            "path": "/",
            "httpOnly": False,
            "secure": False,
            "sameSite": "Lax",
        }
        result.append(cookie)

    if skipped:
        logger.debug(f"[cookie] platform={platform_domain} kept={len(result)} skipped={skipped}")

    return result


def make_storage_state(cookies_raw: str, platform_domain: str) -> Path:
    """生成 Playwright storage_state JSON 文件（包含 cookies）

    Args:
        cookies_raw: 原始 cookie 字符串（浏览器 dump 的，可能混了多平台）
        platform_domain: 目标平台 domain（如 '.xiaohongshu.com'）
    """
    cookies_list = _parse_cookies(cookies_raw, platform_domain)

    # Playwright 严格校验：value 必须是字符串，sameSite 必须在三种值里
    VALID_SS = {"Strict", "Lax", "None"}
    for c in cookies_list:
        c["value"] = str(c.get("value", ""))
        if c.get("sameSite") not in VALID_SS:
            c["sameSite"] = "Lax"
        # secure / httpOnly 不能是 None
        c["secure"] = bool(c.get("secure", False))
        c["httpOnly"] = bool(c.get("httpOnly", False))

    storage = {
        "cookies": cookies_list,
        "origins": [],
    }
    f = tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False, encoding="utf-8")
    json.dump(storage, f, ensure_ascii=False, indent=2)
    f.close()
    return Path(f.name)


class PlaywrightUploader(ABC):
    """Playwright 浏览器自动化上传基类"""

    platform_id: str = ""
    platform_label: str = ""
    platform_domain: str = ""
    PLATFORM_UPLOAD_URL: str = ""

    def __init__(self, cookies: str, headless: bool = False):
        self._cookies_raw = cookies
        self._headless = headless
        self._progress_cb = None
        self._total_bytes = 0

    def upload_sync(self, video_path: str, meta, progress_cb=None) -> tuple[bool, str]:
        """同步入口 — 内部跑 asyncio

        :param progress_cb: (uploaded_bytes, total_bytes) -> None
        """
        import os
        self._progress_cb = progress_cb
        self._total_bytes = os.path.getsize(video_path) if os.path.exists(video_path) else 0

        # 立刻回调一次 0%
        if self._progress_cb:
            try:
                self._progress_cb(0, self._total_bytes)
            except Exception:
                pass

        try:
            result = asyncio.run(self._upload_async(video_path, meta))
            # 完成后回调 100%
            if self._progress_cb and self._total_bytes:
                try:
                    self._progress_cb(self._total_bytes, self._total_bytes)
                except Exception:
                    pass
            return result
        except Exception as e:
            import traceback
            logger.error(f"[{self.platform_label}] Playwright upload 异常: {e}\n{traceback.format_exc()}")
            return False, str(e)

    async def _upload_async(self, video_path: str, meta) -> tuple[bool, str]:
        import asyncio as _aio
        from playwright.async_api import async_playwright

        storage_file = make_storage_state(self._cookies_raw, self.platform_domain)
        browser = None
        context = None
        success = False
        msg = ""
        user_closed_browser = False
        try:
            async with async_playwright() as pw:
                # 用系统 Edge（不用下载浏览器）
                try:
                    browser = await pw.chromium.launch(channel="msedge", headless=self._headless)
                except Exception:
                    try:
                        browser = await pw.chromium.launch(channel="chrome", headless=self._headless)
                    except Exception:
                        browser = await pw.chromium.launch(headless=self._headless)

                context = await browser.new_context(storage_state=str(storage_file))
                page = await context.new_page()

                success, msg = await self.do_upload(page, video_path, meta)

                # ============================================================
                # 用户接管模式：
                #   发布失败 → 监听浏览器关闭事件，等用户手动关了才结束
                #   发布成功 → 正常关闭
                # 这样用户可以：手动点发布 / 处理扫码 / 检查表单 / 随便操作
                # ============================================================
                if not success and not self._headless:
                    closed_event = _aio.Event()

                    async def _on_context_close():
                        closed_event.set()

                    async def _on_page_close(p):
                        closed_event.set()

                    context.on("close", lambda: closed_event.set())
                    page.on("close", lambda: closed_event.set())
                    page.on("crash", lambda: closed_event.set())

                    logger.warning(
                        f"[{self.platform_label}] 自动化发布失败，"
                        f"浏览器窗口保留中 — 请手动操作后关闭浏览器窗口，"
                        f"程序将在您关闭后结束"
                    )
                    # ★ 同时也发一个 GUI 回调（如果有）让用户知道
                    self._emit_progress("等待用户手动接管浏览器", -1)

                    try:
                        await closed_event.wait()
                        user_closed_browser = True
                        logger.info(
                            f"[{self.platform_label}] 用户已关闭浏览器，流程结束"
                        )
                    except _aio.CancelledError:
                        pass

                return success, msg
        finally:
            # 无论成功失败还是异常，都确保关闭 browser/context
            # 如果是用户手动关的，close() 会抛 "TargetClosed" 异常，已被 try/except 吃掉
            if context is not None:
                try:
                    await context.close()
                except Exception:
                    pass
            if browser is not None:
                try:
                    await browser.close()
                except Exception:
                    pass
            try:
                storage_file.unlink(missing_ok=True)
            except Exception:
                pass

    @abstractmethod
    async def do_upload(self, page, video_path: str, meta) -> tuple[bool, str]:
        """子类实现具体的页面操作流程"""

    def _emit_progress(self, stage: str, pct: float) -> None:
        """子类在关键节点调用，GUI 进度条能看到阶段变化"""
        logger.info(f"[{self.platform_label}] 📊 进度 {pct:.0f}% — {stage}")
        if self._progress_cb and self._total_bytes:
            try:
                self._progress_cb(int(self._total_bytes * pct / 100), self._total_bytes)
            except Exception:
                pass

    async def _safe_fill(self, page, selector: str, value: str, clear_first: bool = True) -> bool:
        """安全地填写输入框"""
        try:
            loc = page.locator(selector).first
            await loc.wait_for(state="visible", timeout=5000)
            if clear_first:
                await loc.fill("")
            await loc.fill(value)
            return True
        except Exception as e:
            logger.warning(f"[{self.platform_label}] fill({selector}) 失败: {e}")
            return False

    async def _safe_click(self, page, selector: str, timeout: int = 8000) -> bool:
        """安全地点击"""
        try:
            loc = page.locator(selector).first
            await loc.wait_for(state="visible", timeout=timeout)
            await loc.click(timeout=timeout)
            return True
        except Exception as e:
            logger.warning(f"[{self.platform_label}] click({selector}) 失败: {e}")
            return False

    # ---------------------------------------------------------------
    # AUDIT-0027: 三平台共享的上传步骤，子类按需调用
    # ---------------------------------------------------------------

    async def _goto_upload_page(self, page) -> None:
        """打开上传页并等待 DOM 加载"""
        import asyncio
        await page.goto(self.PLATFORM_UPLOAD_URL, wait_until="domcontentloaded", timeout=90000)
        await asyncio.sleep(2)

    async def _check_login(self, page) -> str:
        """检测是否被踢到登录页，返回错误信息或空串"""
        url_lower = page.url.lower()
        if "login" in url_lower or "passport" in url_lower:
            return f"Cookie 已过期，请重新登录{self.platform_label}"
        return ""

    async def _wait_title_ready(self, page, title_selector: str, max_wait: int = 120) -> bool:
        """等待上传完成 → 标题输入框出现（轮询）"""
        import asyncio
        for _ in range(max_wait):
            await asyncio.sleep(0.5)
            loc = page.locator(title_selector).first
            try:
                if await loc.count() and await loc.is_visible():
                    return True
            except Exception:
                pass
        return False

    async def _fill_title_and_desc(
        self, page, meta,
        title_selector: str, desc_selector: str,
        title_max: int = 30, desc_max: int = 1000,
        tag_separator: str = " ",
    ) -> None:
        """填标题 + 描述（自动拼 tag）"""
        import asyncio

        title_loc = page.locator(title_selector).first
        if await title_loc.count():
            await title_loc.fill("")
            await title_loc.fill((meta.title or "")[:title_max])
            await asyncio.sleep(0.3)

        desc_loc = page.locator(desc_selector).first
        if await desc_loc.count():
            await desc_loc.fill("")
            full_desc = meta.description or ""
            if meta.tags:
                full_desc += tag_separator + " ".join(f"#{t}" for t in meta.tags[:5])
            await desc_loc.fill(full_desc[:desc_max])
            await asyncio.sleep(0.3)

    async def _do_original_declaration(self, page) -> None:
        """原创声明（点击第一个"原创"文本）"""
        import asyncio
        if not getattr(meta := None, "original_declaration", False):
            return
        # meta 从闭包拿不到就跳过，子类直接传参
        await self._click_text(page, "原创")

    async def _click_text(self, page, text: str, timeout: int = 5000) -> bool:
        """按文本点击（安全版）"""
        import asyncio
        try:
            loc = page.get_by_text(text, exact=False).first
            if await loc.count():
                await loc.click(timeout=timeout)
                await asyncio.sleep(0.3)
                return True
        except Exception:
            pass
        return False
