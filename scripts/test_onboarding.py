"""
test_onboarding.py — 应用内新手引导 + YouTube Key 输入框 离线回归

不联网、不动生产数据：测试前把 VC_DATA_ROOT 指到临时目录，
所有 config.yaml / api_secret.yaml.enc / .crypto_salt 都写在那里面。

运行：
  d:\\python\\python.exe scripts\\test_onboarding.py
"""

from __future__ import annotations

import os
import shutil
import sys
import tempfile

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _PROJECT_ROOT)

# 必须在 import 项目模块之前设置，path_helper 在导入时读取
_TMP_ROOT = tempfile.mkdtemp(prefix="vc_onboard_")
os.environ["VC_DATA_ROOT"] = _TMP_ROOT
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import gui.onboarding as ob  # noqa: E402
from utils.config_loader import load_config  # noqa: E402
from utils.crypto_util import load_secret_config, save_secret_config  # noqa: E402

_passed = 0
_failed = 0


def record(name: str, ok: bool, detail: str = "") -> None:
    global _passed, _failed
    if ok:
        _passed += 1
        print(f"  [PASS] {name}" + (f" — {detail}" if detail else ""))
    else:
        _failed += 1
        print(f"  [FAIL] {name}" + (f" — {detail}" if detail else ""))


# ------------------------------------------------------------
# 1. 引导文案
# ------------------------------------------------------------
def test_guide_content() -> None:
    print("\n[引导文案]")
    expected = {"api_key", "mobile_remote", "publish", "tiktok_cookie"}
    record("TC-ON01 四个引导齐全", set(ob.GUIDES) == expected, str(sorted(ob.GUIDES)))

    for key, guide in ob.GUIDES.items():
        steps = guide.get("steps") or []
        ok = len(steps) >= 3 and all(s.get("h") and s.get("body") for s in steps)
        record(f"TC-ON02 {key} 至少 3 步且内容非空", bool(ok), f"{len(steps)} 步")

    api_text = " ".join(s["body"] for s in ob.GUIDES["api_key"]["steps"])
    record("TC-ON03 API 引导含 Gemini 获取步骤", "aistudio.google.com" in api_text)
    record("TC-ON04 API 引导含 YouTube Key 说明", "YouTube" in api_text)

    mob = " ".join(s["body"] for s in ob.GUIDES["mobile_remote"]["steps"])
    record("TC-ON05 手机引导含扫码与前提", "二维码" in mob and "睡眠" in mob)

    pub = " ".join(s["body"] for s in ob.GUIDES["publish"]["steps"])
    record("TC-ON06 发布引导含 Cookie 与风险提示", "Cookie" in pub and "封号" in pub)
    record("TC-ON07 发布引导写明节奏默认值", "10~30" in pub and "5 条" in pub)

    tt = " ".join(s["body"] for s in ob.GUIDES["tiktok_cookie"]["steps"])
    record("TC-ON07b Cookie 引导含导出与存放路径", "Export" in tt and "browser_cookies.txt" in tt)
    record("TC-ON07c Cookie 引导含维护与风险", "7~30 天" in tt and "账号登录凭证" in tt)


# ------------------------------------------------------------
# 2. 已看状态
# ------------------------------------------------------------
def test_seen_state() -> None:
    print("\n[已看状态]")
    ob.reset_onboarding()
    record("TC-ON08 初始未看过", ob.has_seen("publish") is False)

    ob.mark_seen("publish")
    record("TC-ON09 标记后为已看过", ob.has_seen("publish") is True)

    ob.mark_seen("publish")
    cfg = load_config()
    seen = (cfg.get("onboarding") or {}).get("seen") or []
    record("TC-ON10 重复标记不重复写入", seen.count("publish") == 1, str(seen))

    ob.reset_onboarding()
    record("TC-ON11 重置后重新可弹", ob.has_seen("publish") is False)

    # 写配置失败时应软失败（不抛异常）
    def _boom(*a, **k):
        raise OSError("disk full")

    _orig = ob.save_subsection
    ob.save_subsection = _boom
    try:
        ob.mark_seen("api_key")
        record("TC-ON12 写配置失败不影响主流程", True)
    except Exception as e:
        record("TC-ON12 写配置失败不影响主流程", False, str(e))
    finally:
        ob.save_subsection = _orig


# ------------------------------------------------------------
# 3. YouTube Key 保存 / 读取
# ------------------------------------------------------------
def test_youtube_key_io() -> None:
    print("\n[YouTube Key 存取]")
    save_secret_config({"youtube_api_key": "AIzaTESTKEY", "other": "keep-me"})
    secret = load_secret_config()
    record("TC-ON13 写入后可读回", secret.get("youtube_api_key") == "AIzaTESTKEY")

    save_secret_config(dict(secret, youtube_api_key="AIzaNEW"))
    secret2 = load_secret_config()
    record("TC-ON14 覆盖 Key 时保留其他字段", secret2.get("other") == "keep-me")
    record("TC-ON15 新 Key 已生效", secret2.get("youtube_api_key") == "AIzaNEW")


# ------------------------------------------------------------
# 4. UI 冒烟（offscreen，不需要真实屏幕）
# ------------------------------------------------------------
def test_ui() -> None:
    print("\n[UI 冒烟]")
    try:
        from PySide6.QtWidgets import QApplication
    except Exception as e:
        print(f"  [SKIP] PySide6 不可用: {e}")
        return

    app = QApplication.instance() or QApplication([])

    from gui.api_config_dialog import _YouTubeKeySection, _CookieTab
    from utils.path_helper import get_cookies_file_path
    sec = _YouTubeKeySection()
    sec.key_edit.setText("AIzaFromUI")
    sec._on_save()
    record("TC-ON16 YouTube 区域可保存",
           load_secret_config().get("youtube_api_key") == "AIzaFromUI")
    record("TC-ON17 YouTube 区域状态文本正确", "已配置" in sec.status.text())

    dlg = ob.GuideDialog(ob.GUIDES["mobile_remote"], actions=[("去试试", lambda: None)])
    total = len(ob.GUIDES["mobile_remote"]["steps"])
    record("TC-ON18 引导首屏渲染", dlg._counter.text().endswith(f"1 / {total} 步"))

    for _ in range(total - 1):
        dlg._next()
    record("TC-ON19 末页按钮变「开始使用」", dlg._btn_next.text() == "开始使用")

    dlg.accept()
    record("TC-ON20 勾选时关闭会记录已看", dlg.mark_seen is True and dlg.result() == 1)

    # ---- Cookie 标签 ----
    tab = _CookieTab()
    record("TC-ON21 Cookie 标签初始为未配置", "未配置" in tab.status.text())

    sample = (
        "# Netscape HTTP Cookie File\n"
        ".tiktok.com\tTRUE\t/\tTRUE\t1793334770\tttwid\tabc\n"
        ".douyin.com\tTRUE\t/\tFALSE\t1793334770\ts_v_web_id\tverify_x\n"
    )
    tab.editor.setPlainText(sample)
    tab.save(silent=True)
    cookie_path = get_cookies_file_path()
    record("TC-ON22 Cookie 保存后落盘",
           cookie_path.exists() and "ttwid" in cookie_path.read_text(encoding="utf-8"))
    record("TC-ON23 Cookie 状态显示已配置", "已配置 2 条" in tab.status.text())

    tab.editor.setPlainText('{"cookies": []}')
    rejected = tab.save(silent=True)
    record("TC-ON24 非法格式拒绝保存且不覆盖",
           rejected is False and "ttwid" in cookie_path.read_text(encoding="utf-8"))

    tab.editor.setPlainText("")
    tab.save(silent=True)
    record("TC-ON25 清空编辑框等于删除 Cookie 文件", not cookie_path.exists())

    del dlg, sec, tab
    app.processEvents()


# ------------------------------------------------------------
def main() -> int:
    try:
        test_guide_content()
        test_seen_state()
        test_youtube_key_io()
        test_ui()
    finally:
        shutil.rmtree(_TMP_ROOT, ignore_errors=True)

    print(f"\n{'='*46}\n通过 {_passed} / {_passed + _failed}")
    if _failed:
        print(f"❌ 失败 {_failed} 项")
        return 1
    print("✅ 全部通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())
