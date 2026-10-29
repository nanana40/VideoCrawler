"""Fix storage_state cookies — find and strip invalid fields"""
import sys, os, json, tempfile
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from core.publish.playwright_base import _parse_cookies

raw = open("data/browser_cookies.txt", encoding="utf-8").read()
lst = _parse_cookies(raw)
print(f"Total cookies: {len(lst)}")

VALID_KEYS = {"name", "value", "domain", "path", "httpOnly", "secure", "sameSite", "expires"}
VALID_SS = {"Strict", "Lax", "None"}
BAD = []

for c in lst:
    name = c.get("name", "?")
    # 1. 移除非法 key
    for k in list(c.keys()):
        if k not in VALID_KEYS:
            BAD.append(f"[BAD KEY] {name}.{k} = {c[k]}")
            del c[k]
    # 2. sameSite 修正
    ss = c.get("sameSite")
    if ss and ss not in VALID_SS:
        BAD.append(f"[BAD sameSite] {name} = {ss!r}")
        c["sameSite"] = "Lax"
    # 3. expires 修正（必须是时间戳，不能是负的或过期太久）
    if "expires" in c:
        try:
            val = float(c["expires"])
            if val <= 0:
                BAD.append(f"[BAD expires] {name} = {c['expires']} (negative/zero)")
                del c["expires"]
        except Exception:
            BAD.append(f"[BAD expires] {name} = {c['expires']!r} (non-numeric)")
            del c["expires"]

print(f"\nBad entries fixed: {len(BAD)}")
for b in BAD[:20]:
    print(f"  {b}")

tmp = os.path.join(tempfile.gettempdir(), "test_storage.json")
json.dump({"cookies": lst, "origins": []}, open(tmp, "w", encoding="utf-8"), ensure_ascii=False)
print(f"\nSaved: {tmp}")

# 测试能不能 new_context
from playwright.sync_api import sync_playwright
with sync_playwright() as pw:
    br = pw.chromium.launch(headless=True)
    ctx = br.new_context(storage_state=tmp)
    page = ctx.new_page()
    page.goto("https://creator.xiaohongshu.com/publish/publish", wait_until="domcontentloaded", timeout=15000)
    import time
    time.sleep(2)
    print(f"URL: {page.url}")
    br.close()
print("\n✅ COOKIE FIXED!")
