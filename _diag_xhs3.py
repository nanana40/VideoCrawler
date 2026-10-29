"""补诊断：发布按钮到底是什么元素"""
import sys, os, asyncio, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

async def main():
    from playwright.async_api import async_playwright
    from core.publish.playwright_base import make_storage_state

    vc = os.path.dirname(os.path.abspath(__file__))
    cookies_raw = open(os.path.join(vc, "data", "browser_cookies.txt"), encoding="utf-8").read()
    storage = make_storage_state(cookies_raw, ".xiaohongshu.com")

    async with async_playwright() as pw:
        br = await pw.chromium.launch(channel="msedge", headless=False)
        ctx = await br.new_context(storage_state=str(storage))
        page = await ctx.new_page()

        await page.goto("https://creator.xiaohongshu.com/publish/publish", wait_until="domcontentloaded", timeout=60000)
        await asyncio.sleep(3)

        # 先上传视频（复用之前的）
        import glob
        mp4s = glob.glob(os.path.join(vc, "output", "**", "*.mp4"), recursive=True)
        if mp4s:
            fc = page.locator("input[type='file']").first
            await fc.set_input_files(mp4s[0])
            print(f"上传: {os.path.basename(mp4s[0])}")

        # 等标题框
        for i in range(60):
            await asyncio.sleep(1)
            loc = page.locator("input[placeholder*='填写标题']").first
            if await loc.count() and await loc.is_visible():
                print(f"[{i}s] 标题框就绪")
                break

        # 滚动到底部，让发布按钮出现
        await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        await asyncio.sleep(1)

        W = await page.viewport_size
        print(f"\nviewport: {W}")

        # 抓所有包含"发布"/"暂存"文本的元素（任何 tag）
        print("\n=== 包含 '发布' 文本的元素 ===")
        publish_all = await page.locator("text=发布").all()
        for i, el in enumerate(publish_all):
            try:
                info = await el.evaluate("el => ({tag:el.tagName, text:(el.innerText||el.textContent||'').trim().substring(0,30), cls:(el.className||'').toString().substring(0,80), role:el.getAttribute('role')||'', disabled:el.disabled, clickable:!!el.onclick || el.tagName==='BUTTON' || el.getAttribute('role')==='button'})")
                vis = await el.is_visible()
                bb = await el.bounding_box()
                print(f"  [{i}] vis={vis} tag={info['tag']} role={info['role']} disabled={info['disabled']} clickable={info['clickable']}")
                print(f"       text='{info['text']}'")
                print(f"       bbox={bb}")
                print(f"       cls={info['cls']}")
            except Exception as e:
                print(f"  [{i}] ERR: {e}")

        # 抓 role=button 的
        print("\n=== role='button' 元素 ===")
        rbs = await page.locator("[role='button']").all()
        for i, el in enumerate(rbs):
            try:
                info = await el.evaluate("el => ({tag:el.tagName, text:(el.innerText||el.textContent||'').trim().substring(0,30), cls:(el.className||'').toString().substring(0,80)})")
                vis = await el.is_visible()
                bb = await el.bounding_box()
                print(f"  [{i}] vis={vis} tag={info['tag']} text='{info['text']}' bbox={bb} cls={info['cls']}")
            except Exception as e:
                print(f"  [{i}] ERR: {e}")

        # 抓底部所有元素（y > viewport.height - 200）
        print(f"\n=== 底部元素 (y > {W['height']-200}) ===")
        all_els = await page.locator("*").all()
        bottom_els = []
        for el in all_els:
            try:
                bb = await el.bounding_box()
                if bb and bb['y'] > W['height'] - 200 and bb['height'] > 5:
                    tag = await el.evaluate("el => el.tagName")
                    vis = await el.is_visible()
                    if vis:
                        bottom_els.append((bb['y'], tag, bb['width'], bb['height']))
            except Exception:
                pass
        bottom_els.sort()
        for y, tag, w, h in bottom_els[-20:]:
            print(f"  y={y:.0f} tag={tag} w={w:.0f} h={h:.0f}")

        # 原创声明开关
        print("\n=== 原创声明 ===")
        orig = await page.locator("[class*='original']").all()
        for i, el in enumerate(orig):
            try:
                info = await el.evaluate("el => ({tag:el.tagName, cls:(el.className||'').toString(), aria:el.getAttribute('aria-label')||'', role:el.getAttribute('role')||'', checked:el.getAttribute('aria-checked')||el.checked})")
                vis = await el.is_visible()
                bb = await el.bounding_box()
                print(f"  [{i}] vis={vis} tag={info['tag']} aria={info['aria']} role={info['role']} checked={info['checked']}")
                print(f"       bbox={bb}")
                print(f"       cls={info['cls'][:150]}")
            except Exception as e:
                print(f"  [{i}] ERR: {e}")

        await br.close()

if __name__ == "__main__":
    asyncio.run(main())
