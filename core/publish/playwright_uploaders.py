"""
playwright_uploaders.py — 抖音 / 小红书 / 快手 三平台 Playwright 上传实现

简化版移植自 dreammis/social-auto-upload，去掉了：
  - patchright 反检测（直接用标准 Playwright + 系统 Edge）
  - 短信验证码处理（cookie 过期直接失败）
  - 复杂的浮层清理 / 新手引导跳过

保留核心流程：打开上传页 → set_input_files → 等跳转 → 填表 → 发布
"""

from __future__ import annotations

import asyncio
import os
import re
from loguru import logger
from .playwright_base import PlaywrightUploader


# ============================================================
# 抖音 — creator.douyin.com
# ============================================================

class DouyinPlaywrightUploader(PlaywrightUploader):
    platform_id = "douyin"
    platform_label = "抖音"
    platform_domain = ".douyin.com"
    PLATFORM_UPLOAD_URL = "https://creator.douyin.com/creator-micro/content/upload"

    async def do_upload(self, page, video_path: str, meta) -> tuple[bool, str]:
        import asyncio as _aio

        # 1. 打开上传页（AUDIT-0027 基类公共步骤）
        await self._goto_upload_page(page)

        # 2. 上传视频 — 找 file input
        upload_input = page.locator("input.upload-btn-input, div[class^='container'] input[accept], div[class^='container'] input[type='file']").first
        if await upload_input.count() == 0:
            login_err = await self._check_login(page)
            if login_err:
                return False, login_err
            return False, f"找不到上传按钮，当前页面: {page.url}"

        await upload_input.set_input_files(video_path)
        logger.info(f"[抖音] 视频已选择，等待上传...")

        # 3. 等上传完成 → 跳到发布页（抖音特殊：URL 跳转）
        publish_url_patterns = [
            "https://creator.douyin.com/creator-micro/content/publish*",
            "https://creator.douyin.com/creator-micro/content/post/video*",
        ]
        jumped = False
        for _ in range(120):  # 最多等 60 秒
            await _aio.sleep(0.5)
            if any(page.url.startswith(p.replace("*", "")) for p in publish_url_patterns):
                jumped = True
                break
        if not jumped:
            return False, "视频上传超时或未跳转到发布页"

        await _aio.sleep(1)

        # 4+5. 填标题描述（AUDIT-0027 基类公共步骤）
        await self._fill_title_and_desc(
            page, meta,
            title_selector="div[class*='title'] input, input[placeholder*='标题']",
            desc_selector="div[class*='desc'] textarea, textarea[placeholder*='描述'], div[class*='content'] textarea",
            title_max=30, desc_max=1000,
        )

        # 6. 定时发布（可选）
        if meta.scheduled_ts:
            schedule_btn = page.get_by_text("定时发布", exact=False).first
            try:
                if await schedule_btn.count():
                    await schedule_btn.click()
                    await _aio.sleep(0.5)
            except Exception:
                pass

        # 7. 原创声明（AUDIT-0027 基类公共步骤）
        if meta.original_declaration:
            await self._click_text(page, "原创")

        # 8. 发布！
        publish_btn = page.locator("button:has-text('发布'), div[class*='publish'] button, button[class*='submit']").first
        if await publish_btn.count() == 0:
            return False, "找不到发布按钮"

        await publish_btn.click()
        await _aio.sleep(5)

        # 9. 判断结果
        if any(kw in page.url for kw in ["success", "complete", "result"]):
            return True, "抖音发布成功"
        if await page.get_by_text("发布成功", exact=False).count():
            return True, "抖音发布成功"
        if "verify" in page.url.lower() or "captcha" in page.url.lower():
            return False, "触发了抖音安全验证（滑块/验证码），需要手动处理"

        return True, "抖音发布请求已提交（请登录确认）"


# ============================================================
# 小红书 — creator.xiaohongshu.com
# ============================================================

class XiaohongshuPlaywrightUploader(PlaywrightUploader):
    platform_id = "xiaohongshu"
    platform_label = "小红书"
    platform_domain = ".xiaohongshu.com"
    PLATFORM_UPLOAD_URL = "https://creator.xiaohongshu.com/publish/publish"

    async def do_upload(self, page, video_path: str, meta) -> tuple[bool, str]:
        """小红书创作者中心视频发布 — 适配 2025/2026 DOM：Tiptap 正文、xhs-publish-btn 发布按钮"""
        import asyncio as _aio
        import os as _os

        # 1. 打开上传页
        await self._goto_upload_page(page)

        # 1z. ★ 扫码/安全验证检测 — 首次新环境时小红书会强制要求扫码确认身份
        #     不是未登录，是已登录但 IP/网络变了，小红书怕你是机器人
        try:
            await _aio.sleep(2)  # 给扫码弹窗加载时间

            def _looks_like_qrcode_or_verify(url: str, body_text: str) -> str:
                """返回 ''=正常, 'qrcode'=需要扫码, 'verify'=其他安全验证"""
                url_lower = url.lower()
                # URL 包含 passport / login / qrcode / verify
                if any(k in url_lower for k in ['passport', 'login', 'qrcode', 'verify', 'captcha']):
                    return 'qrcode' if ('qrcode' in url_lower or 'login' in url_lower) else 'verify'
                # 页面有扫码相关文字
                qrcode_kws = ['扫码登录', '扫码确认', '请扫描', '使用小红书APP扫码', '二维码']
                verify_kws = ['安全验证', '身份验证', '请验证', '人机验证', '滑动验证', '滑块']
                for kw in qrcode_kws:
                    if kw in body_text:
                        return 'qrcode'
                for kw in verify_kws:
                    if kw in body_text:
                        return 'verify'
                # 有二维码图片（canvas 或 img 带 qrcode 相关 alt）
                # 这个太复杂，先跳过
                return ''

            body_text_snippet = ""
            try:
                body_text_snippet = await page.locator("body").inner_text()
            except Exception:
                pass

            verify_state = _looks_like_qrcode_or_verify(page.url, body_text_snippet)

            if verify_state:
                msg = (
                    "🔐 小红书要求扫码确认身份（新网络环境安全检测）。\n"
                    "请用小红书 APP 扫描浏览器中显示的二维码，扫码成功后程序将自动继续。\n"
                    "如果 60 秒内没扫码，程序会再次检测，请先扫码再试。"
                )
                logger.warning(f"[小红书] {msg}")

                # 发 GUI 提示（progress_cb 是唯一从 base 传到 GUI 的通道）
                self._emit_progress(
                    f"🔐 需要{('扫码确认身份' if verify_state == 'qrcode' else '安全验证')}，"
                    f"请在浏览器中完成",
                    -1,
                )

                # 等用户扫码 — 最长等 120s，每 2s 检查一次页面是否恢复正常
                # 检查标准：URL 回到 creator.xiaohongshu.com/publish/publish 且没有扫码关键词
                for wait_round in range(60):  # 60 * 2s = 120s
                    await _aio.sleep(2)
                    cur_url = page.url
                    if 'creator.xiaohongshu.com' in cur_url and 'publish' in cur_url:
                        try:
                            cur_text = await page.locator("body").inner_text()
                            if not _looks_like_qrcode_or_verify(cur_url, cur_text):
                                logger.info(
                                    f"[小红书] ✅ 扫码确认已完成（等待了 {wait_round * 2 + 2} 秒）"
                                )
                                break
                        except Exception:
                            pass
                else:
                    # 120s 都没恢复
                    return (
                        False,
                        "小红书需要扫码确认身份，但 120 秒内未完成。"
                        "请扫码后重新发布，或检查浏览器是否正常显示二维码。",
                    )
        except Exception as e:
            logger.debug(f"[小红书] 扫码检测流程异常（可忽略）: {e}")

        # 2. 切到「上传视频」tab
        for tab_text in ["上传视频", "上传", "上传创作"]:
            tab = page.get_by_text(tab_text, exact=False).first
            try:
                if await tab.count() and await tab.is_visible():
                    await tab.click()
                    await _aio.sleep(0.5)
                    break
            except Exception:
                continue

        # 3. 上传视频
        upload_input = page.locator("input[type='file']").first
        if await upload_input.count() == 0:
            login_err = await self._check_login(page)
            if login_err:
                return False, login_err
            return False, f"找不到上传入口，当前页面: {page.url}"

        self._emit_progress("视频文件已选择", 5)
        await upload_input.set_input_files(video_path)
        logger.info("[小红书] 🎬 视频已选择，等待上传...")

        # 4. 等待上传完成 — 标题框出现
        #    并行等待（asyncio.wait），谁先出现用谁，总超时 90s
        #    小红书 2025/2026 DOM 可能是 <input> / <textarea> / <div contenteditable> 多种形态
        TITLE_SELECTORS = [
            "input[placeholder*='标题']",
            "textarea[placeholder*='标题']",
            "input[placeholder*='填写标题']",
            "textarea[placeholder*='填写标题']",
            "input[placeholder*='title' i]",
            "div[class*='title'] input",
            "div[class*='title'] textarea",
            "[data-testid*='title'] input",
            "[class*='TitleInput']",
            "[class*='title-input']",
            "input[maxlength]",  # 小红书标题通常有 maxlength 限制
            "textarea[maxlength]",
        ]

        async def _watch(sel, results):
            try:
                loc = page.locator(sel).first
                await loc.wait_for(state="visible", timeout=15000)
                results.append((sel, loc))
            except Exception:
                pass

        results: list = []
        watchers = [_watch(sel, results) for sel in TITLE_SELECTORS]
        try:
            await asyncio.wait_for(asyncio.gather(*watchers), timeout=90)
        except asyncio.TimeoutError:
            pass

        title_loc = results[0][1] if results else None
        if title_loc is None:
            # 超时：打印页面状态帮助调试
            logger.warning("[小红书] 标题框超时，页面当前 URL: %s", page.url)
            try:
                html_snippet = await page.evaluate(
                    """() => {
                    const inputs = document.querySelectorAll('input, textarea');
                    return Array.from(inputs).slice(0, 20).map(el => ({
                        tag: el.tagName,
                        type: el.type || '',
                        placeholder: el.placeholder || '',
                        class: el.className || '',
                        visible: !!(el.offsetWidth || el.offsetHeight)
                    }));
                }"""
                )
                logger.warning("[小红书] 页面 input/textarea 元素 (前20): %s", html_snippet)
            except Exception:
                pass
            return False, "视频上传超时（标题框未出现，已打印页面结构到日志）"
        logger.info("[小红书] 视频上传完成，标题框已就绪 (selector: %s)", results[0][0])
        self._emit_progress("视频上传完成", 30)

        # 5. 封面上传（如果有预设封面）
        if meta.cover_path and _os.path.exists(meta.cover_path):
            try:
                cover_uploaded = False
                # 5a. 找封面的 file input（通常在视频预览附近）
                for cover_sel in [
                    "input[accept*='image']",
                    "input[type='file'][accept*='image']",
                    "[class*='cover'] input[type='file']",
                    "[class*='Cover'] input[type='file']",
                    "[class*='封面'] input[type='file']",
                    "[class*='preview'] input[type='file']",
                ]:
                    cover_input = page.locator(cover_sel).first
                    try:
                        if await cover_input.count() and await cover_input.is_visible():
                            await cover_input.set_input_files(meta.cover_path)
                            await _aio.sleep(3)
                            cover_uploaded = True
                            logger.info(f"[小红书] 🖼️ 封面已上传: {_os.path.basename(meta.cover_path)}")
                            break
                    except Exception as e:
                        logger.debug(f"[小红书] 封面选择器 {cover_sel} 失败: {e}")

                # 5b. 兜底：找"上传封面"文本附近的文件输入
                if not cover_uploaded:
                    for kw in ["上传封面", "设置封面", "点击上传封面", "封面"]:
                        try:
                            btn = page.get_by_text(kw, exact=False).first
                            if await btn.count() and await btn.is_visible():
                                # 点击可能触发隐藏的 file input
                                async with page.expect_file_chooser(timeout=10000) as fc_info:
                                    await btn.click()
                                fc = await fc_info.value
                                await fc.set_files(meta.cover_path)
                                await _aio.sleep(3)
                                cover_uploaded = True
                                logger.info(f"[小红书] 🖼️ 封面已上传 (通过「{kw}」按钮)")
                                break
                        except Exception:
                            continue

                if not cover_uploaded:
                    logger.warning("[小红书] ⚠️ 封面未能上传（DOM 可能变化）")
            except Exception as e:
                logger.warning(f"[小红书] 封面上传异常: {e}")

        # 6. 填标题
        await title_loc.click()
        await title_loc.fill("")
        await _aio.sleep(0.2)
        await title_loc.fill((meta.title or "")[:20])
        await _aio.sleep(0.3)
        logger.info(f"[小红书] 📌 标题已填入: {(meta.title or '')[:20]}")
        self._emit_progress("标题已填入", 45)

        # 7. 填正文 — Tiptap/ProseMirror (div[contenteditable=true])
        desc_text = meta.description or ""
        desc_filled = False
        editor = page.locator("div[contenteditable='true']").first
        try:
            if await editor.count() and await editor.is_visible():
                await editor.click()
                await _aio.sleep(0.3)
                await page.evaluate(
                    "() => { const ed = document.querySelector('div[contenteditable=\"true\"]'); if (ed) { ed.innerHTML = ''; ed.focus(); } }"
                )
                await _aio.sleep(0.2)
                if desc_text:
                    await page.keyboard.type(desc_text, delay=12)
                await _aio.sleep(0.3)
                desc_filled = True
                logger.info("[小红书] 📝 正文已填入 (Tiptap 模式)")
                self._emit_progress("正文已填入", 60)
        except Exception as e:
            logger.warning(f"[小红书] Tiptap 正文填入失败: {e}")

        if not desc_filled:
            for sel in [
                "textarea[placeholder*='正文']",
                "textarea[placeholder*='内容']",
                "div[class*='content'] textarea",
            ]:
                loc = page.locator(sel).first
                try:
                    if await loc.count() and await loc.is_visible():
                        await loc.fill("")
                        await loc.fill(desc_text)
                        desc_filled = True
                        logger.info(f"[小红书] 📝 正文已填入 (textarea 兜底: {sel})")
                        break
                except Exception:
                    continue

        if not desc_filled:
            logger.warning("[小红书] ⚠️ 正文未填入")

        # ============================================================
        # 8. 添加话题标签 — 严格串行状态机（每个话题必须完成后才能开始下一个）
        #
        # 小红书 Tiptap 编辑器行为：
        #   - 在正文末尾输入 "#" → 弹出话题联想弹窗
        #   - 输入关键字 → 弹窗缩小到匹配列表
        #   - 点击第一个结果 → 弹窗关闭、编辑器插入蓝色 chip、光标移到 chip 后
        #   - 不关掉弹窗就去点别的 → 大概率点到弹窗元素上导致动作失败
        # ============================================================
        editor = page.locator("div[contenteditable='true']").first

        async def _anchor_cursor_to_editor_end():
            """把光标强制锚定到正文编辑器最后（用 Selection API，不依赖 End 键）"""
            try:
                await editor.click()
                await _aio.sleep(0.15)
                await page.evaluate("""() => {
                    const ed = document.querySelector('div[contenteditable="true"]');
                    if (!ed) return;
                    ed.focus();
                    const sel = window.getSelection();
                    const range = document.createRange();
                    range.selectNodeContents(ed);
                    range.collapse(false);  // false=结尾, true=开头
                    sel.removeAllRanges();
                    sel.addRange(range);
                }""")
                await _aio.sleep(0.1)
            except Exception:
                pass

        async def _dismiss_any_popup():
            """按 Escape 关掉可能存在的弹窗（话题联想 / 搜索 / 提示）"""
            try:
                await page.keyboard.press("Escape")
                await _aio.sleep(0.3)
            except Exception:
                pass

        tag_count = 0
        if meta.tags:
            try:
                for tag in meta.tags[:5]:
                    tag = tag.strip()
                    if not tag:
                        continue

                    # ① 先关掉任何残留弹窗 + 把光标锚到文末
                    await _dismiss_any_popup()
                    await _anchor_cursor_to_editor_end()

                    # ② 输入 "#" 触发话题模式
                    await page.keyboard.type("#", delay=20)
                    await _aio.sleep(0.4)

                    # ③ 等话题联想弹窗出现（最多等 2s）
                    popup_appeared = False
                    popup_selectors = [
                        "[class*='topic'] [class*='suggest']",
                        "[class*='topic'] [class*='list']",
                        "[class*='hashtag'] [class*='item']",
                        "[role='listbox']",
                        "[class*='mention-list']",
                        "[class*='suggestion']",
                    ]
                    for _ in range(10):  # 10 * 0.2s = 2s
                        await _aio.sleep(0.2)
                        for ps in popup_selectors:
                            try:
                                cnt = await page.locator(ps).count()
                                vis = await page.locator(ps).first.is_visible()
                                if cnt and vis:
                                    popup_appeared = True
                                    break
                            except Exception:
                                continue
                        if popup_appeared:
                            break

                    if not popup_appeared:
                        logger.debug(f"[小红书] 话题 #{tag}: # 后弹窗没出现，跳过")
                        continue

                    # ④ 输入话题关键字（弹窗会自动缩窄到匹配列表）
                    await page.keyboard.type(tag, delay=25)
                    await _aio.sleep(0.8)

                    # ⑤ 只在「弹窗作用域内」选第一个结果（全局 get_by_text 会误点正文）
                    clicked = False
                    for ps in popup_selectors:
                        try:
                            popup = page.locator(ps).first
                            if await popup.count() and await popup.is_visible():
                                # 弹窗内找第一个 list item
                                item = popup.locator(
                                    "[role='option'], li, [class*='item'], [class*='result']"
                                ).first
                                if await item.count():
                                    await item.click(force=True)
                                    clicked = True
                                    break
                        except Exception:
                            continue

                    if not clicked:
                        # 兜底：键盘回车选第一个
                        try:
                            await page.keyboard.press("Enter")
                            clicked = True
                        except Exception:
                            pass

                    if clicked:
                        tag_count += 1
                        logger.info(f"[小红书] 🏷️ 话题 #{tag} 已添加 ({tag_count}/5)")
                        # ⑥ 等弹窗消失（光标已被自动移到新 chip 后）
                        await _aio.sleep(0.6)

                if tag_count > 0:
                    self._emit_progress(f"话题标签已添加 ({tag_count} 个)", 70)
                else:
                    logger.warning("[小红书] ⚠️ 话题标签一个都没加上")

            except Exception as e:
                logger.warning(f"[小红书] 添加话题异常: {e}")

        # 8z. 话题结束后强制关弹窗（无论加没加成功）
        await _dismiss_any_popup()
        await _anchor_cursor_to_editor_end()

        # ============================================================
        # 9. 原创声明 — 严格 debug + 点击后必须验证 checked
        #
        # 核心原则：点了不算，is_checked() 变 True 才算
        # ============================================================
        if meta.original_declaration:
            await _dismiss_any_popup()

            # ★ DEBUG DUMP：打印页面上所有 checkbox / switch / 含"原创"的元素
            if not hasattr(self, '_dump_done'):
                try:
                    dump = await page.evaluate("""() => {
                        const results = [];
                        // 所有 checkbox
                        document.querySelectorAll('input[type="checkbox"]').forEach((el, i) => {
                            const r = el.getBoundingClientRect();
                            results.push({
                                type: 'checkbox',
                                idx: i,
                                checked: el.checked,
                                aria_label: el.getAttribute('aria-label') || '',
                                parent_text: (el.parentElement?.innerText || '').trim().slice(0, 50),
                                parent_class: el.parentElement?.className || '',
                                visible: !!(r.width || r.height),
                                rect: {x: r.x, y: r.y, w: r.width, h: r.height}
                            });
                        });
                        // 所有 switch / toggle / 含"原创"文字的
                        document.querySelectorAll('[role="switch"], [class*="switch"], [class*="toggle"]').forEach((el, i) => {
                            const r = el.getBoundingClientRect();
                            results.push({
                                type: 'switch',
                                idx: i,
                                aria_label: el.getAttribute('aria-label') || '',
                                aria_checked: el.getAttribute('aria-checked') || '',
                                text: (el.innerText || '').trim().slice(0, 50),
                                class: (el.className || '').toString().slice(0, 60),
                                visible: !!(r.width || r.height),
                                rect: {x: r.x, y: r.y, w: r.width, h: r.height}
                            });
                        });
                        // 全文搜索"原创"文字
                        const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
                        let node; let kw_results = [];
                        while (node = walker.nextNode()) {
                            if (node.nodeValue && node.nodeValue.includes('原创')) {
                                const r = node.parentElement?.getBoundingClientRect();
                                kw_results.push({
                                    text: node.nodeValue.trim().slice(0, 40),
                                    tag: node.parentElement?.tagName,
                                    class: node.parentElement?.className || '',
                                    rect: r ? {x: r.x, y: r.y} : null
                                });
                            }
                            if (kw_results.length >= 10) break;
                        }
                        return {checkboxes: results, original_texts: kw_results};
                    }""")
                    logger.info(f"[小红书] 📋 原创声明 DOM dump:\n{dump}")
                    self._dump_done = True
                except Exception as e:
                    logger.debug(f"[小红书] DOM dump 失败: {e}")

            declared = False

            # 9a. 尝试 3 次：每次用不同方法
            for attempt in range(1, 4):
                if declared:
                    break
                logger.info(f"[小红书] 原创声明尝试 #{attempt}")

                # 方法 1: 直接通过 JS 找 + 点（最可靠，不依赖 Playwright selector 解析）
                try:
                    js_result = await page.evaluate("""() => {
                        // 找原创 checkbox
                        const cbs = document.querySelectorAll('input[type="checkbox"]');
                        for (const cb of cbs) {
                            const txt = (cb.parentElement?.innerText || '') + ' ' + (cb.getAttribute('aria-label') || '');
                            if (txt.includes('原创') || txt.toLowerCase().includes('original')) {
                                if (!cb.checked) {
                                    cb.click();
                                    return {clicked: true, method: 'js_checkbox_click', checked_after: cb.checked};
                                } else {
                                    return {clicked: true, method: 'already_checked', checked_after: true};
                                }
                            }
                        }
                        // 找 switch
                        const switches = document.querySelectorAll('[role="switch"], [class*="switch"], [class*="toggle"]');
                        for (const sw of switches) {
                            const txt = (sw.innerText || '') + ' ' + (sw.getAttribute('aria-label') || '');
                            if (txt.includes('原创') || txt.toLowerCase().includes('original')) {
                                sw.click();
                                return {clicked: true, method: 'js_switch_click', checked_after: sw.getAttribute('aria-checked')};
                            }
                        }
                        return {clicked: false, reason: 'not_found'};
                    }""")
                    logger.info(f"[小红书] 🔧 JS 点原创结果: {js_result}")

                    if js_result.get("clicked"):
                        await _aio.sleep(2)  # 等二次确认弹窗

                        # 9b. 处理二次确认弹窗
                        if not js_result.get("checked_after"):
                            confirm_handled = False
                            # 先用 JS 扫弹窗
                            try:
                                confirm_js = await page.evaluate("""() => {
                                    const kws = ['确认声明', '确认原创', '声明原创', '确定声明', '确定原创', '确认', '同意', '继续'];
                                    // 找可能的弹窗容器
                                    const containers = document.querySelectorAll(
                                        '[class*="modal"], [class*="Modal"], [class*="dialog"], [class*="Dialog"], [class*="confirm"], [role="dialog"]'
                                    );
                                    for (const c of containers) {
                                        if (!c.offsetWidth) continue;  // 隐藏的跳过
                                        for (const kw of kws) {
                                            const btn = c.querySelector(`button:scope, [role="button"]:scope, a:scope`);
                                            // 简化：容器内所有 button
                                            const btns = c.querySelectorAll('button, [role="button"]');
                                            for (const b of btns) {
                                                const t = (b.innerText || '').trim();
                                                if (t.includes(kw)) {
                                                    b.click();
                                                    return {clicked: true, kw, container_class: c.className};
                                                }
                                            }
                                        }
                                    }
                                    // 兜底：全页面找"确认"按钮
                                    const all_btns = document.querySelectorAll('button, [role="button"]');
                                    for (const b of all_btns) {
                                        if ((b.innerText || '').trim() === '确认' || (b.innerText || '').includes('声明')) {
                                            const r = b.getBoundingClientRect();
                                            if (r.width > 40 && r.height > 20) {  // 大概率是弹窗内的按钮
                                                b.click();
                                                return {clicked: true, kw: (b.innerText || '').trim(), container_class: 'global'};
                                            }
                                        }
                                    }
                                    return {clicked: false};
                                }""")
                                logger.info(f"[小红书] 🔧 JS 处理二次确认: {confirm_js}")
                                confirm_handled = confirm_js.get("clicked", False)
                            except Exception as e:
                                logger.debug(f"[小红书] JS 弹窗处理失败: {e}")

                            if not confirm_handled:
                                # 兜底用 Playwright get_by_role
                                for kw in ["确认声明", "确认原创", "声明原创", "确认", "同意"]:
                                    try:
                                        btn = page.get_by_role("button", name=kw).first
                                        if await btn.count() and await btn.is_visible():
                                            await btn.click(force=True)
                                            confirm_handled = True
                                            logger.info(f"[小红书] ✅ Playwright 点弹窗确认: {kw}")
                                            break
                                    except Exception:
                                        continue

                            await _aio.sleep(1)

                        # 9c. 最终验证 — 再用 JS 查一遍 checkbox 是否真的 checked
                        verify = await page.evaluate("""() => {
                            const cbs = document.querySelectorAll('input[type="checkbox"]');
                            for (const cb of cbs) {
                                const txt = (cb.parentElement?.innerText || '') + ' ' + (cb.getAttribute('aria-label') || '');
                                if (txt.includes('原创') || txt.toLowerCase().includes('original')) {
                                    return {found: true, checked: cb.checked};
                                }
                            }
                            // switch 也查一下
                            const switches = document.querySelectorAll('[role="switch"], [class*="switch"], [class*="toggle"]');
                            for (const sw of switches) {
                                const txt = (sw.innerText || '') + ' ' + (sw.getAttribute('aria-label') || '');
                                if (txt.includes('原创') || txt.toLowerCase().includes('original')) {
                                    return {found: true, checked: sw.getAttribute('aria-checked') === 'true'};
                                }
                            }
                            return {found: false};
                        }""")
                        logger.info(f"[小红书] 🔍 原创声明验证: {verify}")

                        if verify.get("checked"):
                            declared = True
                            logger.info("[小红书] ✅ 原创声明已勾选（JS 验证通过）")
                            self._emit_progress("原创声明已勾选", 80)
                            break
                        else:
                            logger.warning(
                                f"[小红书] ⚠️ 第 {attempt} 次点击原创后仍未 checked，"
                                f"{'再试一次' if attempt < 3 else '放弃'}"
                            )

                except Exception as e:
                    logger.warning(f"[小红书] 原创声明 attempt {attempt} 异常: {e}")

            if not declared:
                logger.warning("[小红书] ⚠️ 原创声明未能勾选 — 请手动确认")

        # 9z. 原创后关弹窗
        await _dismiss_any_popup()

        # ============================================================
        # 10. 发布前校验 — 没填完不能点发布
        # ============================================================
        # 小红书必填：标题、正文（或至少一个话题）
        # 先等一下页面可能的自动校验
        await _aio.sleep(1)

        pre_errors = []

        # 10a. 标题非空校验
        try:
            title_inputs = await page.locator(
                "input[placeholder*='标题'], input[placeholder*='填写标题']"
            ).all()
            for t in title_inputs:
                val = await t.input_value()
                if not val or not val.strip():
                    pre_errors.append("标题为空，可能无法发布")
                    break
        except Exception:
            pass

        if pre_errors:
            # 尝试自动补填标题（兜底）
            try:
                for t in title_inputs:
                    val = await t.input_value()
                    if not val.strip():
                        await t.fill((meta.title or "")[:20])
                        await _aio.sleep(0.3)
            except Exception:
                pass

        # 10b. 定时发布（可选，不校验）
        if meta.scheduled_ts:
            try:
                schedule_btn = page.get_by_text("定时发布", exact=False).first
                if await schedule_btn.count():
                    await schedule_btn.click()
                    await _aio.sleep(0.5)
            except Exception:
                pass

        # ============================================================
        # 11. 发布按钮 — 用 JS 直接找 + 点，避免 shadow DOM 问题
        #
        # 核心改动：
        #   - 不用 Playwright selector 找（shadow DOM 里经常抓不到）
        #   - 用 JS document.querySelectorAll 直接扫
        #   - 点之前必须查 disabled / aria-disabled — 被禁用就不报 click 成功
        #   - 坐标兜底返回 False（之前 page.mouse.click 从不抛异常 = 假阳性）
        # ============================================================

        async def _click_publish_via_js(strategy_label: str) -> dict:
            """
            返回 dict:
              {ok: True/False, 按钮状态: disabled/not_found/clicked, method: 策略名}
            """
            await _dismiss_any_popup()
            await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            await _aio.sleep(0.4)

            # ★ 第一次先 dump 所有按钮状态
            if not hasattr(self, '_publish_dump_done'):
                try:
                    btn_dump = await page.evaluate("""() => {
                        const results = [];
                        const selectors = 'button, [role="button"], xhs-publish-btn, [submit-text]';
                        document.querySelectorAll(selectors).forEach((el, i) => {
                            const r = el.getBoundingClientRect();
                            const disabled = el.disabled !== undefined ? el.disabled :
                                           el.getAttribute('aria-disabled') === 'true' ||
                                           (el.className && String(el.className).includes('disable'));
                            const text = (el.innerText || '').trim().slice(0, 30);
                            const submitText = el.getAttribute('submit-text') || '';
                            const tag = el.tagName;
                            const visible = !!(r.width || r.height);
                            results.push({
                                i, tag, text, submitText,
                                disabled, visible,
                                class: String(el.className || '').slice(0, 60),
                                rect: {x: Math.round(r.x), y: Math.round(r.y), w: Math.round(r.width), h: Math.round(r.height)}
                            });
                        });
                        return results;
                    }""")
                    logger.info(f"[小红书] � 发布按钮 DOM dump:\n{btn_dump}")
                    self._publish_dump_done = True
                except Exception as e:
                    logger.debug(f"[小红书] 发布按钮 dump 失败: {e}")

            # 用 JS 找 + 点 — 最可靠
            try:
                js_result = await page.evaluate("""() => {
                    const candidates = [];
                    // 收集所有可能的发布按钮
                    document.querySelectorAll('button, [role="button"], xhs-publish-btn, [submit-text]').forEach(el => {
                        const r = el.getBoundingClientRect();
                        if (!r.width || !r.height) return;  // 隐藏的跳过
                        const text = (el.innerText || '').trim();
                        const submitText = el.getAttribute('submit-text') || '';
                        // 严格匹配：submit-text="发布" 或 text 刚好是 "发布"（不是"发布笔记"/"草稿发布"等）
                        if (submitText === '发布' || text === '发布') {
                            candidates.push({el, r, text, submitText, tag: el.tagName});
                        }
                    });

                    if (candidates.length === 0) {
                        return {ok: false, reason: 'not_found'};
                    }

                    // 选最靠下、最靠右的那个（发布按钮通常在右下角）
                    candidates.sort((a, b) => (b.r.bottom + b.r.right) - (a.r.bottom + a.r.right));
                    const target = candidates[0];
                    const el = target.el;

                    // 检查是否 disabled
                    const disabled = el.disabled !== undefined ? el.disabled :
                                    el.getAttribute('aria-disabled') === 'true' ||
                                    (el.className && String(el.className).includes('disable'));
                    if (disabled) {
                        return {ok: false, reason: 'disabled', button_text: target.text};
                    }

                    // 点！优先 click()，不行再 dispatchEvent
                    try {
                        el.click();
                        // 自定义元素需要触发 custom event
                        el.dispatchEvent(new CustomEvent('click', {bubbles: true, cancelable: true}));
                        return {ok: true, method: 'js_click', button_text: target.text, tag: target.tag};
                    } catch(e) {
                        return {ok: false, reason: 'js_error', error: String(e)};
                    }
                }""")
                logger.info(f"[小红书] 🚀 JS 点发布 ({strategy_label}): {js_result}")

                if js_result.get("ok"):
                    return {"ok": True, "method": js_result.get("method", "js"), "button": js_result.get("button_text", "")}

                if js_result.get("reason") == "disabled":
                    logger.warning(
                        f"[小红书] 🚫 发布按钮处于 disabled 状态！"
                        f"（这通常意味着表单校验没过：标题空/话题少/视频还没处理完）"
                    )
                    return {"ok": False, "reason": "disabled"}

                if js_result.get("reason") == "not_found":
                    return {"ok": False, "reason": "not_found"}

            except Exception as e:
                logger.debug(f"[小红书] JS 点发布异常: {e}")

            return {"ok": False, "reason": "error"}

        # 发布主循环：最多 5 轮
        MAX_PUBLISH_ATTEMPTS = 5

        publish_result_url = page.url
        for attempt in range(1, MAX_PUBLISH_ATTEMPTS + 1):
            logger.info(f"[小红书] === 发布尝试 #{attempt}/{MAX_PUBLISH_ATTEMPTS} ===")

            click_result = await _click_publish_via_js(f"attempt {attempt}")

            if not click_result.get("ok"):
                reason = click_result.get("reason", "unknown")
                if reason == "disabled":
                    # disabled 再点也没用，跳出去让上层判定失败
                    logger.error("[小红书] ❌ 发布按钮 disabled，表单校验未通过，放弃重试")
                    break
                if reason == "not_found":
                    logger.error(f"[小红书] ❌ 第 {attempt} 轮：找不到发布按钮")
                    break
                logger.error(f"[小红书] ❌ 第 {attempt} 轮：点击失败 ({reason})")
                continue

            # 点成功了 → 等 2s 让"确认发布"弹窗出来
            await _aio.sleep(2)

            # 处理"二次确认发布"弹窗
            confirm_handled = False
            try:
                confirm_js = await page.evaluate("""() => {
                    const kws = ['确认发布', '确定发布', '确认', '继续'];
                    const containers = document.querySelectorAll(
                        '[class*="modal"], [class*="Modal"], [class*="dialog"], [class*="Dialog"], [class*="confirm"], [role="dialog"]'
                    );
                    for (const c of containers) {
                        if (!c.offsetWidth) continue;
                        const btns = c.querySelectorAll('button, [role="button"]');
                        for (const b of btns) {
                            const t = (b.innerText || '').trim();
                            if (kws.some(kw => t.includes(kw)) && t.length < 20) {
                                b.click();
                                return {clicked: true, kw: t};
                            }
                        }
                    }
                    return {clicked: false};
                }""")
                confirm_handled = confirm_js.get("clicked", False)
                if confirm_handled:
                    logger.info(f"[小红书] ✅ 已点击二次确认弹窗: {confirm_js.get('kw')}")
                    await _aio.sleep(1)
            except Exception:
                pass

            # 轮询 3s 看效果
            SUCCESS_KEYWORDS = ["发布成功", "发布完成", "已发布", "发布笔记成功"]
            FAIL_KEYWORDS = [
                "内容不能为空", "请填写标题", "标题不能为空",
                "至少添加", "添加话题", "话题不能为空",
                "请选择", "请填写", "请检查",
                "违规", "被禁用", "审核中",
            ]

            cur_url_before_wait = page.url
            found_fail = False
            for _ in range(6):  # 6 * 0.5s = 3s
                await _aio.sleep(0.5)
                cur_url = page.url

                if "success" in cur_url.lower():
                    logger.info(f"[小红书] ✅ 发布成功 (URL 跳转 success)")
                    self._emit_progress("发布成功", 100)
                    return True, "小红书发布成功"

                if "verify" in cur_url.lower() or "captcha" in cur_url.lower():
                    logger.warning("[小红书] 🔐 触发安全验证（滑块/验证码）")
                    return False, "触发安全验证，请手动处理"

                try:
                    body_text = await page.locator("body").inner_text()
                    for kw in SUCCESS_KEYWORDS:
                        if kw in body_text:
                            logger.info(f"[小红书] ✅ 发布成功 (检测到「{kw}」)")
                            self._emit_progress("发布成功", 100)
                            return True, "小红书发布成功"
                except Exception:
                    pass

                # 表单校验失败（第 2 轮之后才查）
                if attempt >= 2:
                    try:
                        body_text = await page.locator("body").inner_text()
                        for kw in FAIL_KEYWORDS:
                            if kw in body_text:
                                found_fail = True
                                logger.warning(f"[小红书] ❌ 发布被拦截: 页面出现「{kw}」")
                                break
                    except Exception:
                        pass
                    if found_fail:
                        break

            if found_fail:
                break

            # URL 已跳走 = 疑似成功
            if "publish/publish" not in page.url and page.url != cur_url_before_wait:
                await _aio.sleep(3)
                try:
                    body_text = await page.locator("body").inner_text()
                    for kw in SUCCESS_KEYWORDS:
                        if kw in body_text:
                            logger.info(f"[小红书] ✅ 发布成功 (URL 跳转后检测到「{kw}」)")
                            self._emit_progress("发布成功", 100)
                            return True, "小红书发布成功"
                except Exception:
                    pass
                logger.info(
                    f"[小红书] ⚠️ URL 已跳转但未检测到明确成功文案，"
                    f"疑似已发布 (当前: {page.url})"
                )
                self._emit_progress("发布疑似成功", 100)
                return True, "发布疑似成功，请手动确认"

            # 还在编辑页 → 继续下一轮
            logger.info(
                f"[小红书] 第 {attempt} 轮点击后仍在编辑页，"
                f"{'继续' if attempt < MAX_PUBLISH_ATTEMPTS else '放弃'}"
            )

        # ============================================================
        # 发布失败 / 没找到按钮 — 保留浏览器给用户手动接管（由 _upload_async 监听 close）
        # ============================================================
        publish_result_url = page.url
        logger.error(
            f"[小红书] ❌ 自动发布失败（已尝试 {attempt} 轮）。"
            f"浏览器页面保留，请手动检查/操作。"
        )

        # 把当前页面状态打印到日志，方便用户排查
        try:
            body_text = await page.locator("body").inner_text()
            for kw in FAIL_KEYWORDS + ["话题", "验证", "安全", "发布"]:
                if kw in body_text[:2000]:
                    logger.info(f"[小红书] 页面含关键字「{kw}」")
        except Exception:
            pass

        # ★ 不关闭 context / browser！让 _upload_async 的 finally 块跳过关闭
        # 但 PlaywrightUploader.upload_sync 的 finally 会执行，所以我们需要一种方式
        # 让用户看到页面。简单做法：返回 False + 错误消息，调用方会提示用户手动检查
        # 浏览器 context 会在 upload_sync 的 finally 里被关，但我们用 "留页面" 提示
        return (
            False,
            f"自动发布失败（已尝试多轮点击），请手动检查页面: {publish_result_url}",
        )


# ============================================================
# 快手 — media.kuaishou.com
# ============================================================

class KuaishouPlaywrightUploader(PlaywrightUploader):
    platform_id = "kuaishou"
    platform_label = "快手"
    platform_domain = ".kuaishou.com"
    PLATFORM_UPLOAD_URL = "https://media.kuaishou.com/content/new"

    async def do_upload(self, page, video_path: str, meta) -> tuple[bool, str]:
        import asyncio as _aio

        # 1. 打开上传页（AUDIT-0027 基类公共步骤）
        await self._goto_upload_page(page)

        # 找上传按钮（快手是点击 → 选文件）
        upload_click = page.locator("div[class*='upload']:has-text('上传'), button:has-text('上传'), input[type='file']").first
        if await upload_click.count() == 0:
            login_err = await self._check_login(page)
            if login_err:
                return False, login_err
            return False, f"找不到上传入口，当前页面: {page.url}"

        # 如果是 file input 直接 set_files；如果是 div/button 先点再选
        tag = await upload_click.evaluate("el => el.tagName")
        if tag == "INPUT":
            await upload_click.set_input_files(video_path)
        else:
            async with page.expect_file_chooser(timeout=60000) as fc_info:
                await upload_click.click()
            file_chooser = await fc_info.value
            await file_chooser.set_files(video_path)

        logger.info(f"[快手] 视频已选择，等待上传...")

        # 3. 等标题输入框出现（AUDIT-0027 基类公共步骤）
        title_selector = "input[placeholder*='标题'], div[class*='title'] input"
        if not await self._wait_title_ready(page, title_selector):
            return False, "视频上传超时"

        # 4+5. 填标题描述（AUDIT-0027 基类公共步骤）
        await self._fill_title_and_desc(
            page, meta,
            title_selector=title_selector,
            desc_selector="textarea[placeholder*='描述'], textarea[placeholder*='简介'], div[class*='desc'] textarea",
            title_max=30, desc_max=1000,
        )

        # 原创（AUDIT-0027 基类公共步骤）
        if meta.original_declaration:
            await self._click_text(page, "原创")

        # 发布
        publish_btn = page.locator("button:has-text('发布'), button:has-text('提交')").first
        if await publish_btn.count() == 0:
            return False, "找不到发布按钮"

        await publish_btn.click()
        await _aio.sleep(5)

        if await page.get_by_text("发布成功", exact=False).count() or "success" in page.url.lower():
            return True, "快手发布成功"

        return True, "快手发布请求已提交"
