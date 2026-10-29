"""扫描 Gemini API key 可调用的所有模型，测试纯音频输入是否可行"""
import os, sys, time, json
sys.path.insert(0, r"D:\Ideas\VideoCrawler\Vc")

import requests

# 从环境变量或 GUI 配置读取，禁止把密钥写进仓库
API_KEY = os.environ.get("GEMINI_API_KEY", "").strip()
if not API_KEY:
    from utils.config_loader import load_config
    API_KEY = str((load_config().get("gemini") or {}).get("api_key", "")).strip()
if not API_KEY:
    sys.exit("未找到 Gemini API Key：请设置环境变量 GEMINI_API_KEY，或在 GUI『API/模型管理』填写")
AUDIO_PATH = r"D:\Ideas\VideoCrawler\Vc\tmp\test_audio.mp3"

def list_all_models():
    """列出 API key 可见的所有模型"""
    url = f"https://generativelanguage.googleapis.com/v1beta/models?key={API_KEY}"
    models = []
    page_token = None
    while True:
        params = {"pageSize": 100}
        if page_token:
            params["pageToken"] = page_token
        r = requests.get(url, params=params, timeout=30)
        if r.status_code != 200:
            print(f"❌ 列表请求失败: {r.status_code}")
            print(r.text[:500])
            break
        data = r.json()
        batch = data.get("models", [])
        models.extend(batch)
        page_token = data.get("nextPageToken")
        if not page_token:
            break
    return models

def test_audio_model(model_name, audio_path):
    """测试单个模型是否支持音频输入"""
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={API_KEY}"

    # 读取音频 base64
    import base64
    with open(audio_path, "rb") as f:
        audio_b64 = base64.b64encode(f.read()).decode("utf-8")

    # 先测: 是否支持 audio/* MIME type（直接 inline_data）
    payload = {
        "contents": [{
            "role": "user",
            "parts": [
                {
                    "inline_data": {
                        "mime_type": "audio/mpeg",
                        "data": audio_b64
                    }
                },
                {"text": "这段音频说的是什么语言？只回复语言代码，例如 de、en、zh。"}
            ]
        }],
        "generationConfig": {"maxOutputTokens": 50}
    }

    try:
        r = requests.post(url, json=payload, timeout=60)
        d = r.json()
        if r.status_code == 200 and "candidates" in d and d["candidates"]:
            text = d["candidates"][0]["content"]["parts"][0].get("text", "")
            return True, f"✅ 音频OK | 识别='{text.strip()[:50]}'"
        elif r.status_code == 429:
            return False, "⏸ 429 限流，稍后重试"
        elif r.status_code == 403:
            msg = d.get("error", {}).get("message", "")[:120]
            return False, f"❌ 403 {msg}"
        elif r.status_code == 404:
            return False, "❌ 404 模型不存在"
        elif r.status_code == 400:
            msg = d.get("error", {}).get("message", "")[:150]
            if "audio" in msg.lower() or "supported" in msg.lower() or "not support" in msg.lower():
                return False, f"🔇 不支持音频: {msg[:100]}"
            return False, f"❌ 400 {msg[:100]}"
        else:
            msg = d.get("error", {}).get("message", "")[:120]
            return False, f"❌ {r.status_code} {msg}"
    except Exception as e:
        return False, f"❌ 异常: {e}"

def classify_capabilities(model_info):
    """从 models.list 响应判断模型能力（仅参考，需要实测）"""
    supported = model_info.get("supportedGenerationMethods", [])
    # Gemini API 的 methods 里 generateContent 支持多模态，但具体媒体类型需要实测
    return supported

if __name__ == "__main__":
    print("=" * 70)
    print("🔍 Gemini 模型全面扫描 — 纯音频输入测试")
    print("=" * 70)

    # 1. 列出所有模型
    print("\n📋 第 1 步：拉取 API key 可见的所有模型...")
    all_models = list_all_models()
    print(f"   共发现 {len(all_models)} 个模型\n")

    # 只保留 generateContent 可用的
    gc_models = [m for m in all_models if "generateContent" in m.get("supportedGenerationMethods", [])]
    print(f"   其中支持 generateContent 的: {len(gc_models)} 个\n")

    # 按类别分组
    groups = {}
    for m in gc_models:
        name = m["name"].replace("models/", "")
        # 归类
        if "gemini-3" in name: grp = "Gemini 3.x"
        elif "gemini-2.5" in name: grp = "Gemini 2.5"
        elif "gemini-1.5" in name: grp = "Gemini 1.5"
        elif "gemini-1.0" in name or "gemini-pro" in name: grp = "Gemini 1.0"
        elif "text-embedding" in name: grp = "Embedding"
        elif "qa" in name or "gecko" in name: grp = "QA / Gecko"
        else: grp = "其他"
        groups.setdefault(grp, []).append(name)

    for grp, names in sorted(groups.items()):
        print(f"  [{grp}] ({len(names)})")
        for n in names:
            print(f"    • {n}")
        print()

    # 2. 逐个测试音频输入
    print("\n🔬 第 2 步：逐个测试纯音频输入能力...")
    print("-" * 70)

    results = []  # (name, ok, detail)

    # 只测主模型系列（跳过 embedding / QA / gecko 等非生成模型）
    testable = []
    for m in gc_models:
        name = m["name"].replace("models/", "")
        if any(x in name for x in ["gemini-3", "gemini-2.5", "gemini-1.5", "gemini-1.0", "gemini-pro", "flash-latest"]):
            testable.append(name)

    print(f"   将测试 {len(testable)} 个生成模型\n")

    for i, name in enumerate(testable):
        ok, detail = test_audio_model(name, AUDIO_PATH)
        results.append((name, ok, detail))
        icon = "✅" if ok else "❌"
        print(f"  [{i+1:02d}/{len(testable):02d}] {icon} {name:45s} → {detail}")
        time.sleep(2)  # 避免 429

    # 3. 汇总
    print("\n" + "=" * 70)
    print("📊 汇总报告")
    print("=" * 70)

    audio_ok = [(n, d) for n, ok, d in results if ok]
    audio_fail = [(n, d) for n, ok, d in results if not ok]

    print(f"\n  🟢 支持音频输入的模型 ({len(audio_ok)} 个):")
    for n, d in audio_ok:
        print(f"    • {n}")

    print(f"\n  🔴 不支持音频的模型 ({len(audio_fail)} 个):")
    for n, d in audio_fail:
        print(f"    • {n:45s} → {d}")

    # 保存完整 JSON
    out = {
        "scan_time": time.strftime("%Y-%m-%d %H:%M:%S"),
        "total_models": len(all_models),
        "gc_models": len(gc_models),
        "audio_capable": audio_ok,
        "audio_incapable": audio_fail,
    }
    os.makedirs(os.path.dirname(AUDIO_PATH), exist_ok=True)
    report_path = os.path.join(os.path.dirname(AUDIO_PATH), "gemini_audio_scan_report.json")
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print(f"\n  📄 完整报告已保存: {report_path}")
