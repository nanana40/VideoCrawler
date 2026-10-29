"""极速诊断 v2 — 自动跑完、存结果、退出"""
import sys, os, asyncio, glob, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("PYTHONIOENCODING", "utf-8")

async def main():
    from playwright.async_api import async_playwright
    from core.publish.playwright_base import make_storage_state

    vc = os.path.dirname(os.path.abspath(__file__))
    out_file = os.path.join(vc, "_diag_result.json")
    
    cookies_raw = open(os.path.join(vc, "data", "browser_cookies.txt"), encoding="utf-8").read()
    storage = make_storage_state(cookies_raw, ".xiaohongshu.com")

    mp4s = glob.glob(os.path.join(vc, "output", "**", "*.mp4"), recursive=True)
    video = mp4s[0] if mp4s else None
    
    result = {
        "video": video,
        "cookies_len": len(cookies_raw),
        "page_url": "",
        "title_selector_found": None,
        "wait_log": [],
        "inputs": [],
        "textareas": [],
        "contenteditable_divs": [],
        "class_matches": {},
        "buttons": [],
        "screenshot": "",
    }

    async with async_playwright() as pw:
        try:
            br = await pw.chromium.launch(channel="msedge", headless=False)
        except Exception:
            br = await pw.chromium.launch(headless=False)

        ctx = await br.new_context(storage_state=str(storage))
        page = await ctx.new_page()

        print("打开发布页...")
        await page.goto("https://creator.xiaohongshu.com/publish/publish", wait_until="domcontentloaded", timeout=60000)
        await asyncio.sleep(3)
        result["page_url"] = page.url
        print(f"URL: {page.url}")

        if "login" in page.url.lower() or "passport" in page.url.lower():
            result["error"] = "COOKIE_EXPIRED"
            await br.close()
            json.dump(result, open(out_file, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
            print("❌ Cookie 过期！")
            return

        # 切视频 tab
        for t in ["上传视频", "上传"]:
            tab = page.get_by_text(t, exact=False).first
            try:
                if await tab.count() and await tab.is_visible():
                    await tab.click()
                    await asyncio.sleep(0.5)
                    print(f"点了 '{t}'")
                    break
            except Exception:
                continue

        # 上传视频
        if video and os.path.exists(video):
            print(f"上传: {os.path.basename(video)}")
            fc = page.locator("input[type='file']").first
            await fc.set_input_files(video)

        # 等标题框 — 最多 120 秒
        print("等标题框...")
        selectors = [
            "input[placeholder*='标题']",
            "textarea[placeholder*='标题']",
            "input[placeholder*='填写标题']",
            "textarea[placeholder*='填写标题']",
            "div[class*='title'] input",
            "div[class*='title'] textarea",
            "[class*='title'] input",
            "[class*='title'] textarea",
            "[class*='Title'] input",
            "[class*='Title'] textarea",
            ".title input",
            ".title textarea",
            "div[placeholder*='标题']",
        ]
        found = None
        for i in range(120):
            await asyncio.sleep(1)
            for s in selectors:
                try:
                    loc = page.locator(s).first
                    if await loc.count():
                        vis = await loc.is_visible()
                        entry = {"sec": i, "sel": s, "visible": vis}
                        result["wait_log"].append(entry)
                        print(f"  [{i}s] ✅ '{s}' visible={vis}")
                        if vis:
                            found = s
                            break
                except Exception:
                    pass
            if found:
                break
            if i % 15 == 0:
                print(f"  [{i}s] 还没找到...")

        result["title_selector_found"] = found
        print(f"\n🎯 标题框: {found}")

        # === DUMP DOM ===
        print("\n=== DUMP DOM ===")

        # inputs
        inputs = await page.locator("input").all()
        for inp in inputs:
            try:
                info = await inp.evaluate("el => ({type:el.type, placeholder:el.placeholder||'', cls:(el.className||'').toString(), aria:el.getAttribute('aria-label')||'', role:el.getAttribute('role')||'', id:el.id||''})")
                vis = await inp.is_visible()
                bb = await inp.bounding_box()
                result["inputs"].append({"visible": vis, "bbox": bb, **info})
            except Exception as e:
                result["inputs"].append({"error": str(e)})

        # textareas
        tas = await page.locator("textarea").all()
        for ta in tas:
            try:
                info = await ta.evaluate("el => ({placeholder:el.placeholder||'', cls:(el.className||'').toString(), aria:el.getAttribute('aria-label')||'', role:el.getAttribute('role')||'', id:el.id||''})")
                vis = await ta.is_visible()
                bb = await ta.bounding_box()
                result["textareas"].append({"visible": vis, "bbox": bb, **info})
            except Exception as e:
                result["textareas"].append({"error": str(e)})

        # contenteditable divs
        eds = await page.locator("div[contenteditable='true']").all()
        for ed in eds:
            try:
                info = await ed.evaluate("el => ({role:el.getAttribute('role')||'', cls:(el.className||'').toString(), placeholder:el.getAttribute('placeholder')||'', aria:el.getAttribute('aria-label')||'', tag:el.tagName})")
                vis = await ed.is_visible()
                bb = await ed.bounding_box()
                result["contenteditable_divs"].append({"visible": vis, "bbox": bb, **info})
            except Exception as e:
                result["contenteditable_divs"].append({"error": str(e)})

        # class 匹配
        for kw in ["title", "Title", "desc", "Desc", "content", "Content", "editor", "Editor", "publish", "Publish", "upload", "Upload", "original", "Original", "topic", "Topic", "tag", "Tag"]:
            try:
                c = await page.locator(f"[class*='{kw}']").count()
                if c:
                    result["class_matches"][kw] = c
            except Exception:
                pass

        # buttons — 找发布按钮相关
        btns = await page.locator("button").all()
        for b in btns:
            try:
                info = await b.evaluate("el => ({text:(el.innerText||el.textContent||'').substring(0,50), cls:(el.className||'').toString().substring(0,100), disabled:el.disabled, id:el.id||''})")
                vis = await b.is_visible()
                bb = await b.bounding_box()
                if vis and bb:
                    result["buttons"].append({"visible": vis, "bbox": bb, **info})
            except Exception:
                pass

        # 截图
        try:
            shot = os.path.join(vc, "_diag_screenshot.png")
            await page.screenshot(path=shot, full_page=False)
            result["screenshot"] = shot
            print(f"📸 截图: {shot}")
        except Exception as e:
            result["screenshot"] = f"ERR: {e}"

        await br.close()

    json.dump(result, open(out_file, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print(f"\n✅ 诊断完成: {out_file}")

if __name__ == "__main__":
    asyncio.run(main())
