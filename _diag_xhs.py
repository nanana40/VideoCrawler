"""极速诊断：小红书发布页视频上传后 DOM 探测"""
import sys, os, asyncio, glob
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("PYTHONIOENCODING", "utf-8")

async def main():
    from playwright.async_api import async_playwright
    from core.publish.playwright_base import make_storage_state

    vc = os.path.dirname(os.path.abspath(__file__))
    cookies_raw = open(os.path.join(vc, "data", "browser_cookies.txt"), encoding="utf-8").read()
    storage = make_storage_state(cookies_raw, ".xiaohongshu.com")

    mp4s = glob.glob(os.path.join(vc, "output", "**", "*.mp4"), recursive=True)
    video = mp4s[0] if mp4s else None
    print(f"🎬 video = {video}")
    print(f"🍪 cookie len = {len(cookies_raw)}")

    async with async_playwright() as pw:
        try:
            br = await pw.chromium.launch(channel="msedge", headless=False)
        except Exception:
            br = await pw.chromium.launch(headless=False)

        ctx = await br.new_context(storage_state=str(storage))
        page = await ctx.new_page()

        print("\n🔗 打开 https://creator.xiaohongshu.com/publish/publish ...")
        await page.goto("https://creator.xiaohongshu.com/publish/publish", wait_until="domcontentloaded", timeout=60000)
        await asyncio.sleep(3)
        print(f"📍 URL: {page.url}")

        if "login" in page.url or "passport" in page.url:
            print("❌ Cookie 过期！需要重新登录")
            await br.close()
            return

        # 切到上传视频 tab
        for t in ["上传视频", "上传"]:
            tab = page.get_by_text(t, exact=False).first
            try:
                if await tab.count() and await tab.is_visible():
                    await tab.click()
                    await asyncio.sleep(0.5)
                    break
            except Exception:
                continue

        # 上传视频
        if video and os.path.exists(video):
            print(f"\n📤 上传视频... ({os.path.basename(video)})")
            fc = page.locator("input[type='file']").first
            await fc.set_input_files(video)
            print("✅ 文件已选，等上传...")

        # 等标题框出现（最多 60 秒）
        print("\n⏳ 等标题框（最多 60 秒）...")
        found = None
        selectors_to_try = [
            "input[placeholder*='标题']",
            "textarea[placeholder*='标题']",
            "input[placeholder*='填写标题']",
            "textarea[placeholder*='填写标题']",
            "div[class*='title'] input",
            "div[class*='title'] textarea",
            "[class*='title'] input",
            "[class*='title'] textarea",
            "[class*='Title'] input",
            ".title input",
            ".title textarea",
        ]
        for i in range(60):
            await asyncio.sleep(1)
            for s in selectors_to_try:
                loc = page.locator(s).first
                try:
                    c = await loc.count()
                    if c:
                        vis = await loc.is_visible()
                        print(f"  [{i}s] ✅ '{s}' count={c} visible={vis}")
                        if vis:
                            found = s
                            break
                except Exception:
                    pass
            if found:
                break
            if i % 10 == 0:
                print(f"  [{i}s] 还没找到...")

        print(f"\n🎯 标题框 selector: {found}")

        # ===== 现在 dump 所有可能相关的 DOM =====
        print("\n" + "="*60)
        print("🔍 完整 DOM 探测结果 (视频上传后)")
        print("="*60)

        inputs = await page.locator("input").all()
        print(f"\n📥 input ({len(inputs)}):")
        for i, inp in enumerate(inputs):
            try:
                info = await inp.evaluate("el => ({t:el.type, ph:el.placeholder||'', cls:(el.className||'').toString(), aria:el.getAttribute('aria-label')||''})")
                vis = await inp.is_visible()
                print(f"  [{i}] v={vis} type={info['t']} ph='{info['ph'][:50]}' aria='{info['aria'][:30]}' cls='{info['cls'][:70]}'")
            except Exception as e:
                print(f"  [{i}] ERR: {e}")

        tas = await page.locator("textarea").all()
        print(f"\n📝 textarea ({len(tas)}):")
        for i, ta in enumerate(tas):
            try:
                info = await ta.evaluate("el => ({ph:el.placeholder||'', cls:(el.className||'').toString(), aria:el.getAttribute('aria-label')||''})")
                vis = await ta.is_visible()
                print(f"  [{i}] v={vis} ph='{info['ph'][:50]}' aria='{info['aria'][:30]}' cls='{info['cls'][:70]}'")
            except Exception as e:
                print(f"  [{i}] ERR: {e}")

        eds = await page.locator("div[contenteditable='true']").all()
        print(f"\n✏️ contenteditable div ({len(eds)}):")
        for i, ed in enumerate(eds):
            try:
                info = await ed.evaluate("el => ({role:el.getAttribute('role')||'', cls:(el.className||'').toString(), placeholder:el.getAttribute('placeholder')||'', aria:el.getAttribute('aria-label')||''})")
                vis = await ed.is_visible()
                print(f"  [{i}] v={vis} role='{info['role']}' ph='{info['placeholder'][:30]}' aria='{info['aria'][:30]}' cls='{info['cls'][:70]}'")
            except Exception as e:
                print(f"  [{i}] ERR: {e}")

        # 所有带 title/desc/content/editor 关键词的 class
        print("\n🔑 class 包含 title/desc/content/editor 的元素:")
        for kw in ["title", "Title", "desc", "Desc", "content", "Content", "editor", "Editor", "publish", "Publish"]:
            els = page.locator(f"[class*='{kw}']").all()
            try:
                c = await els.count()
                if c:
                    print(f"  class*='{kw}' -> {c} 个")
            except Exception:
                pass

        print("\n" + "="*60)
        print("诊断完毕！请把上面的输出贴回来")
        print("浏览器保持打开，你可以手动观察页面")
        print("按 Ctrl+C 退出")
        print("="*60)
        try:
            while True:
                await asyncio.sleep(1)
        except KeyboardInterrupt:
            pass
        finally:
            await br.close()

if __name__ == "__main__":
    asyncio.run(main())
