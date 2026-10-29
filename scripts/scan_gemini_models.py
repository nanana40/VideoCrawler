"""全量视频模型扫描 —— 用 API list 出来的所有 generateContent 模型"""
import sys, os, json, time, shutil, tempfile, requests
sys.path.insert(0, r"D:\Ideas\VideoCrawler\Vc")

# 从环境变量或 GUI 配置读取，禁止把密钥写进仓库
API_KEY = os.environ.get("GEMINI_API_KEY", "").strip()
if not API_KEY:
    from utils.config_loader import load_config
    API_KEY = str((load_config().get("gemini") or {}).get("api_key", "")).strip()
if not API_KEY:
    sys.exit("未找到 Gemini API Key：请设置环境变量 GEMINI_API_KEY，或在 GUI『API/模型管理』填写")
VIDEO_PATH = r"D:\Ideas\VideoCrawler\Vc\output\de\daily\PS3S0khaMEs\PS3S0khaMEs_MEINE_MEINUNG__Generalabrechnung_‒_Vorbach_kritisi.mp4"

# 从 API list 结果中提取的 generateContent 模型，排除 embedding/imagen/veo/audio/robotics/research
CANDIDATES = [
    # 3.x 系列
    "gemini-3-flash-preview",
    "gemini-3.5-flash",
    "gemini-3.5-flash-lite",
    "gemini-3.6-flash",
    "gemini-3.7-flash",
    "gemini-flash-latest",
    "gemini-flash-lite-latest",
    "gemini-pro-latest",
    "gemini-3.1-flash-lite-preview",
    "gemini-3.1-flash-lite",
    "gemini-3.1-pro-preview",
    # 2.5 系列
    "gemini-2.5-flash",
    "gemini-2.5-flash-lite",
    "gemini-2.5-pro",
]

def test_video(model_short, tmp_path):
    """单个模型视频测试"""
    from google import genai
    client = genai.Client(api_key=API_KEY)
    
    # 上传
    try:
        f = client.files.upload(file=tmp_path)
    except Exception as e:
        return None, f"上传失败: {str(e)[:80]}"
    
    # 等 ACTIVE
    for i in range(60):
        time.sleep(5)
        f = client.files.get(name=f.name)
        state_val = getattr(f.state, "name", str(f.state))
        if state_val == "ACTIVE":
            break
        elif state_val not in ("PROCESSING", "STATE_UNSPECIFIED"):
            return None, f"状态异常: {state_val}"
    else:
        return None, "ACTIVE 超时"
    
    # generate_content
    t0 = time.time()
    try:
        resp = client.models.generate_content(
            model=model_short,
            contents=[f, "What language is this video in? Reply with just the language code."]
        )
        elapsed = time.time() - t0
        text = resp.text.strip() if resp.text else "(empty)"
        return text, f"✅ OK ({elapsed:.1f}s) → {text[:50]}"
    except Exception as e:
        elapsed = time.time() - t0
        msg = str(e)
        if "403" in msg:
            return None, f"❌ 403 权限 ({elapsed:.1f}s)"
        elif "404" in msg:
            return None, f"❌ 404 下线/无权限 ({elapsed:.1f}s)"
        elif "503" in msg:
            return None, f"🟡 503 服务拥堵 ({elapsed:.1f}s)"
        elif "429" in msg:
            return None, f"🟡 429 限流 ({elapsed:.1f}s)"
        elif "400" in msg:
            return None, f"❌ 400 参数错误 ({elapsed:.1f}s)"
        else:
            return None, f"❌ {msg[:120]}"


def main():
    print("=" * 60)
    print(f"🔍 全量视频模型扫描 ({len(CANDIDATES)} 个候选)")
    print("=" * 60)
    
    # 准备临时视频
    tmp = os.path.join(tempfile.gettempdir(), "gemini_full_scan.mp4")
    if not os.path.exists(tmp):
        shutil.copy2(VIDEO_PATH, tmp)
    print(f"测试视频: {os.path.getsize(tmp)/1024/1024:.1f}MB")
    
    results = []
    for i, model in enumerate(CANDIDATES):
        print(f"\n[{i+1}/{len(CANDIDATES)}] {model}")
        text, status = test_video(model, tmp)
        print(f"  {status}")
        results.append((model, text is not None, text))
        time.sleep(4)
    
    # 汇总
    print(f"\n{'='*60}")
    print("📋 最终结果")
    print(f"{'='*60}")
    
    ok = [(n, t) for n, ok_, t in results if ok_]
    fail = [(n, t) for n, ok_, t in results if not ok_]
    
    print(f"\n🟢 视频可用 ({len(ok)}/{len(CANDIDATES)}):")
    for n, t in ok:
        print(f"  ✅ {n}")
    
    print(f"\n🔴 不可用 ({len(fail)}/{len(CANDIDATES)}):")
    for n, _ in fail:
        print(f"  ❌ {n}")
    
    if ok:
        print(f"\n💡 推荐 MODEL_CHAIN:")
        chain = [n for n, _ in ok]
        print(f"  MODEL_CHAIN = {json.dumps(chain)}")

if __name__ == "__main__":
    main()
