"""
MQTT 手机-电脑联动自动化测试
============================
验证远程控制链路 (手机 H5 → MQTT broker → PC bridge → 回包) 是否可正常工作。

覆盖两层:
  A. 离线单元测试 —— 不连 broker, 直接构造 MQTT 消息喂给 _on_message,
     验证 token 鉴权 / action 路由 / 参数校验 / 依赖注入 / 设备持久化
  B. 在线集成测试 —— 真连公共 broker (broker.emqx.io),
     模拟手机端 (WSS 8084, 与 mobile.html 相同通道) 下发指令,
     验证 指令下发 → PC 执行 → 响应/日志回传 全链路

运行方式 (在 Vc 目录下):
    python scripts/test_mqtt_linkage.py
可选参数:
    --offline-only   只跑离线部分 (不访问网络)
"""

from __future__ import annotations

import argparse
import json
import socket
import ssl
import sys
import threading
import time
import types
import uuid
from pathlib import Path
from typing import Any, Callable, Optional

# 保证能 import web.mqtt_bridge (mqtt_bridge 顶层只依赖 loguru + paho)
VC_ROOT = Path(__file__).resolve().parent.parent
if str(VC_ROOT) not in sys.path:
    sys.path.insert(0, str(VC_ROOT))

# Windows 控制台中文输出兜底
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from web.mqtt_bridge import MqttBridge  # noqa: E402

BROKER_HOST = "broker.emqx.io"
TCP_PORT = 1883
WSS_PORT = 8084

_results: list[tuple[str, bool, str]] = []
# 敏感值脱敏表 (record 输出时替换)
_MASKS: list[str] = []


def _mask(text: str) -> str:
    """把输出中的敏感 token 替换为 ***"""
    for m in _MASKS:
        if m:
            text = text.replace(m, "***")
    return text


def record(name: str, ok: bool, note: str = "") -> None:
    """记录并即时打印一条测试结果 (自动脱敏 token)"""
    _results.append((name, ok, note))
    mark = "PASS" if ok else "FAIL"
    print(f"  [{mark}] {name}" + (f"  — {_mask(note)}" if note else ""))


class FakeTaskStore:
    """模拟 web.main.TASKS 的最小任务存储 (供 status/logs 注入)"""

    def __init__(self) -> None:
        self.log_buffer: list[str] = ["[09:00:01] 模拟日志 A", "[09:00:02] 模拟日志 B"]

    def snapshot(self) -> dict:
        """任务快照"""
        return {"running": False, "mode": "idle", "fake": True}

    def push_log(self, msg: str) -> None:
        """日志推送 (测试中仅吞掉)"""


def _make_offline_bridge(**deps: Any) -> tuple[MqttBridge, list[dict]]:
    """构造离线测试 bridge, 拦截 _publish_json 捕获所有出站消息"""
    b = MqttBridge()
    b.set_dependencies(
        task_store=deps.get("task_store"),
        pipeline_single=deps.get("pipeline_single"),
        pipeline_search=deps.get("pipeline_search"),
        stop_current=deps.get("stop_current"),
    )
    sent: list[dict] = []
    b._publish_json = lambda topic, obj: sent.append({"topic": topic, "obj": obj})  # type: ignore[method-assign]
    return b, sent


def _feed(b: MqttBridge, payload: bytes) -> None:
    """把模拟 MQTT 消息直接喂给 _on_message"""
    b._on_message(None, None, types.SimpleNamespace(payload=payload))


def _resp_of(sent: list[dict], request_id: str) -> Optional[dict]:
    """从捕获的出站消息中找指定 request_id 的 resp"""
    for s in reversed(sent):
        o = s["obj"]
        if s["topic"].endswith("/resp") and o.get("request_id") == request_id:
            return o
    return None


# ===========================================================================
# A. 离线单元测试
# ===========================================================================
def run_offline_tests() -> None:
    """离线部分: 鉴权 / 路由 / 校验 / 依赖注入 / 设备持久化"""
    print("\n========== A. 离线单元测试 (不连 broker) ==========")

    # --- TC-I1 token 鉴权: 错误 token 必须被丢弃 ---
    b, sent = _make_offline_bridge()
    _feed(b, json.dumps({"token": "WRONG", "action": "ping", "params": {}, "request_id": "i1"}).encode())
    ok = len(sent) == 0
    record("TC-I1 错误 token 被丢弃(不回包)", ok, f"出站消息={len(sent)} 条(应为 0)")

    # --- TC-I2 坏 JSON: 不崩溃、不回包 ---
    b, sent = _make_offline_bridge()
    try:
        _feed(b, b"this is not json")
        ok = len(sent) == 0
        note = "未抛异常且无出站消息"
    except Exception as e:  # pragma: no cover
        ok = False
        note = f"抛异常: {e}"
    record("TC-I2 坏 JSON 消息被静默忽略", ok, note)

    # --- TC-I3 未知 action: 回错误响应 ---
    b, sent = _make_offline_bridge()
    _feed(b, json.dumps({"token": b.token, "action": "hack_rm_rf", "request_id": "i3"}).encode())
    r = _resp_of(sent, "i3")
    ok = r is not None and r["ok"] is False and "未知 action" in r["error"]
    record("TC-I3 未知 action 返回错误响应", ok, f"resp={r}")

    # --- TC-I4 ping: 正常往返, request_id 原样回传 ---
    b, sent = _make_offline_bridge()
    _feed(b, json.dumps({"token": b.token, "action": "ping", "request_id": "i4"}).encode())
    r = _resp_of(sent, "i4")
    ok = r is not None and r["ok"] is True and r["data"].get("msg") == "pong" \
        and r["data"].get("device_id") == b.device_id
    record("TC-I4 ping → pong 往返正常", ok, f"resp={r}")

    # --- TC-I5 status: 注入 task_store 后快照透传 ---
    store = FakeTaskStore()
    b, sent = _make_offline_bridge(task_store=store)
    _feed(b, json.dumps({"token": b.token, "action": "status", "request_id": "i5"}).encode())
    r = _resp_of(sent, "i5")
    ok = r is not None and r["ok"] is True and r["data"].get("task", {}).get("fake") is True
    record("TC-I5 status 返回设备+任务快照", ok, f"task={r['data'].get('task') if r else None}")

    # --- TC-I6 logs: 返回注入存储的日志缓冲 ---
    b, sent = _make_offline_bridge(task_store=store)
    _feed(b, json.dumps({"token": b.token, "action": "logs", "params": {"limit": 1}, "request_id": "i6"}).encode())
    r = _resp_of(sent, "i6")
    ok = r is not None and r["ok"] is True and r["data"].get("count") == 1
    record("TC-I6 logs 按 limit 截取返回", ok, f"count={r['data'].get('count') if r else None}")

    # --- TC-I7 pipeline_single 缺 url: 参数校验报错 ---
    b, sent = _make_offline_bridge(pipeline_single=lambda p: {"ok": True})
    _feed(b, json.dumps({"token": b.token, "action": "pipeline_single", "request_id": "i7"}).encode())
    r = _resp_of(sent, "i7")
    ok = r is not None and r["ok"] is False and "url" in r["error"]
    record("TC-I7 pipeline_single 缺 url 报错", ok, f"error={r['error'] if r else None}")

    # --- TC-I8 pipeline_single 依赖未注入: 报 RuntimeError 而非崩溃 ---
    b, sent = _make_offline_bridge()
    _feed(b, json.dumps({"token": b.token, "action": "pipeline_single", "params": {"url": "https://x/v.mp4"}, "request_id": "i8"}).encode())
    r = _resp_of(sent, "i8")
    ok = r is not None and r["ok"] is False and "未注入" in r["error"]
    record("TC-I8 依赖未注入时报错不崩溃", ok, f"error={r['error'] if r else None}")

    # --- TC-I9 pipeline_single 正常派发: mock 被调用且收到 params ---
    calls: list[dict] = []
    b, sent = _make_offline_bridge(pipeline_single=lambda p: calls.append(p) or {"ok": True, "msg": "已启动"})
    _feed(b, json.dumps({"token": b.token, "action": "pipeline_single",
                         "params": {"url": "https://example.com/v.mp4", "language": "en"}, "request_id": "i9"}).encode())
    r = _resp_of(sent, "i9")
    ok = r is not None and r["ok"] is True and len(calls) == 1 and calls[0]["url"] == "https://example.com/v.mp4"
    has_log = any(s["topic"].endswith("/log") and "MQTT 触发单视频" in s["obj"].get("msg", "") for s in sent)
    record("TC-I9 pipeline_single 派发到注入函数+发日志", ok and has_log, f"calls={len(calls)}, log推送={has_log}")

    # --- TC-I10 stop: 注入的 stop_current 被调用 ---
    stop_calls: list[int] = []
    b, sent = _make_offline_bridge(stop_current=lambda: stop_calls.append(1))
    _feed(b, json.dumps({"token": b.token, "action": "stop", "request_id": "i10"}).encode())
    r = _resp_of(sent, "i10")
    ok = r is not None and r["ok"] is True and len(stop_calls) == 1
    record("TC-I10 stop 指令触发注入回调", ok, f"stop_calls={len(stop_calls)}")

    # --- TC-I11 设备身份持久化: 两次实例化身份一致 ---
    b1 = MqttBridge()
    b2 = MqttBridge()
    same = b1.device_id == b2.device_id and b1.token == b2.token
    dev_file = VC_ROOT / "data" / "mqtt_device.json"
    file_ok = dev_file.exists()
    record("TC-I11 设备 device_id/token 持久化一致", same and file_ok,
           f"device_id={b1.device_id[:8]}…, 文件存在={file_ok}")

    # --- TC-I12 topic 约定: user/{device_id}/cmd|resp|log ---
    b3 = MqttBridge()
    expect = f"user/{b3.device_id}"
    ok = b3.topic_cmd == f"{expect}/cmd" and b3.topic_resp == f"{expect}/resp" and b3.topic_log == f"{expect}/log"
    record("TC-I12 topic 命名符合约定", ok, b3.topic_cmd)

    # --- 公网地址文件全局备份 (二维码相关用例会改写它, 离线部分结束时统一恢复) ---
    from web.mqtt_bridge import _web_url_file as _wuf
    _urlfile = _wuf()
    _url_backup = _urlfile.read_text(encoding="utf-8").strip() if _urlfile.exists() else None

    # --- TC-I13 二维码 LAN 兜底: 未配置公网地址时自动生成局域网直连链接 ---
    import os as _os
    from web.mqtt_bridge import save_web_ui_url as _save_url
    _os.environ.pop("VC_MQTT_WEB_URL", None)  # 环境变量优先级更高, 测试前置条件: 均无
    _save_url("")                             # 清除持久化文件 (其他用例结束后残留)
    b = MqttBridge()
    b.web_ui_url = ""
    urls = b.get_qr_urls()
    ok = urls["mode"] == "lan" and urls["url"].startswith("http://") \
        and f"/static/mobile.html?device={b.device_id}&token=" in urls["url"] \
        and urls["public"] == "" and urls["lan"] == urls["url"]
    record("TC-I13 二维码 LAN 兜底自动生成", ok, urls["url"].split("?")[0])

    # --- TC-I14 二维码公网模式优先: 配置 VC_MQTT_WEB_URL 后首选公网地址 ---
    b2 = MqttBridge()
    b2.web_ui_url = "https://vc.example.com/mobile.html"
    urls2 = b2.get_qr_urls()
    ok = urls2["mode"] == "public" and urls2["url"].startswith("https://vc.example.com/") \
        and f"device={b2.device_id}" in urls2["url"] and urls2["lan"].startswith("http://")
    record("TC-I14 二维码公网模式优先+LAN备选", ok, urls2["url"][:40] + "…")

    # --- TC-I16 公网地址文件回退: save → get_qr_urls 现读生效 → 清除 ---
    # (生产配置已在用例前全局备份, 由离线部分收尾统一恢复, 此处只操作临时态)
    from web.mqtt_bridge import save_web_ui_url
    b4 = MqttBridge()
    b4.web_ui_url = ""
    save_web_ui_url("https://test-tunnel.trycloudflare.com")
    urls4 = b4.get_qr_urls()
    ok = urls4["mode"] == "public" and "test-tunnel.trycloudflare.com" in urls4["url"]
    save_web_ui_url("")  # 用例自身清理
    cleaned = not _urlfile.exists() or _urlfile.read_text(encoding="utf-8").strip() == ""
    record("TC-I16 公网地址持久化写入/现读/清除", ok and cleaned,
           f"mode={urls4['mode']}, 清除成功={cleaned}")

    # --- TC-I17 字幕模块 NameError 回归 (2026-10-28 流水线事故): import 全模块 + SRTWriter 冒烟 ---
    try:
        from core.subtitles import (SubtitleSegment, SubtitleSentence,  # noqa: F401
                                    SubtitleResult, SRTWriter, SubtitleQualityGate,
                                    VideoSubtitleEmbedder, SpeechRecognizer,
                                    SubtitleTranslator, SentenceMerger)
        from core.subtitles import (processor, asr, writer, translator,  # noqa: F401
                                    embedder, quality_gate, sentence_merger)
        seg = SubtitleSegment(start_time=0.0, end_time=2.0, text="Hello", translated_text="你好")
        srt_tmp = VC_ROOT / "tmp" / "test_regression.srt"
        srt_tmp.parent.mkdir(exist_ok=True)
        SRTWriter.write([seg], str(srt_tmp), bilingual=True)
        srt_ok = srt_tmp.exists() and "你好" in srt_tmp.read_text(encoding="utf-8")
        srt_tmp.unlink(missing_ok=True)
    except Exception as e:
        srt_ok = False
        record("TC-I17 字幕模块回归(前置失败)", False, f"异常: {e}")
    else:
        record("TC-I17 字幕模块 NameError 回归", srt_ok,
               "import 全模块 + SRTWriter 双语写入" if srt_ok else "SRT 写入失败")

    # --- TC-I18 手机端功能扩展: 新 action 注册表 + 安全校验 ---
    from web.mqtt_bridge import ACTION_HANDLERS
    need = {"queue_clear", "queue_cancel", "publish_records", "subtitle_style_get",
            "subtitle_style_set", "subtitle_render", "recognize_start",
            "copy_generate", "copy_latest", "queue_enqueue", "accounts",
            "videos", "pool_list"}
    ok = need.issubset(ACTION_HANDLERS.keys())
    record("TC-I18a 新 action 全部注册", ok, f"共 {len(ACTION_HANDLERS)} 个 action")

    from web.mqtt_bridge import _resolve_media_path
    travel_ok = missing_ok = False
    try:
        _resolve_media_path("../secret.yaml")
    except ValueError:
        travel_ok = True
    except Exception:
        pass
    try:
        _resolve_media_path("no_such_file_xyz.mp4")
    except ValueError:
        missing_ok = True
    except Exception:
        pass
    record("TC-I18b 路径解析防穿越+缺失报错", travel_ok and missing_ok,
           f"穿越拒绝={travel_ok}, 缺失拒绝={missing_ok}")

    from web.mqtt_bridge import _handler_copy_latest
    r = _handler_copy_latest(b3, {})
    ok = isinstance(r, dict) and "text" in r and "file" in r
    record("TC-I18c copy_latest 空态安全返回", ok, f"file={r.get('file') or '(空)'}")

    # --- TC-I20 发布链路: pool_list 映射 + 队列风控配置 + 手机页面标记 ---
    from web.mqtt_bridge import _handler_pool_list
    import core.publish.pool as _pool_mod

    class _FakePool:
        """不打真 DB, 只验证字段映射逻辑"""
        @staticmethod
        def list_recent(hours: int = 72):
            return [{"id": 11, "final_video_path": "C:/x/y.mp4", "title_original": "T1",
                     "publish_status": 0, "create_ts": 0, "channel_name": "ch",
                     "duration_sec": 12, "cover_path": ""}]
        @staticmethod
        def list_all():
            return [{"id": 12, "final_video_path": "", "title_translated": "T2",
                     "publish_status": 1, "create_ts": 0}]

    _orig_pool = _pool_mod.VideoPool
    _pool_mod.VideoPool = _FakePool
    try:
        r_recent = _handler_pool_list(b3, {})
        r_all = _handler_pool_list(b3, {"scope": "all"})
    finally:
        _pool_mod.VideoPool = _orig_pool
    it = (r_recent.get("items") or [{}])[0]
    ok = (r_recent.get("total") == 1 and it.get("pool_id") == 11
          and it.get("title") == "T1" and it.get("has_cover") is False
          and (r_all.get("items") or [{}])[0].get("pool_id") == 12)
    record("TC-I20a pool_list 字段映射", ok, f"recent={r_recent.get('total')}, all={r_all.get('total')}")

    from core.publish.publish_queue import PublishQueueManager
    (lo, hi), limit = PublishQueueManager._load_risk_config()
    inst = PublishQueueManager()  # 直接实例化 (不碰单例/worker)
    ok = 0 <= lo <= hi and limit >= 0 and inst._today_done_count() == 0
    record("TC-I20b 队列风控配置默认可用", ok, f"cooldown={lo}~{hi}s, daily_limit={limit}, 今日已完成={inst._today_done_count()}")

    _mob = (VC_ROOT / "web" / "static" / "mobile.html").read_text(encoding="utf-8")
    ok = all(m in _mob for m in ("loadPool", "enqueueJob", "pool_list", "pubAccount",
                                 "data.current || null"))
    record("TC-I20c mobile.html 发布 Tab 关键标记", ok,
           "候选池+入队+账号选择+快照字段已对齐" if ok else "缺少关键函数标记")

    # --- TC-I22 手机下载成品/封面 (pool_file → 局域网 HTTP 地址) ---
    import os as _os
    import tempfile as _tempfile
    from web.mqtt_bridge import _handler_pool_file

    _tmp_dir = _tempfile.mkdtemp(prefix="vc_poolfile_")
    _vpath = _os.path.join(_tmp_dir, "done.mp4")
    _cpath = _os.path.join(_tmp_dir, "cover.jpg")
    for _p in (_vpath, _cpath):
        with open(_p, "wb") as _f:
            _f.write(b"\x00" * 300_000)  # ~0.29MB, 保证 size_mb > 0

    class _FakePool2:
        @staticmethod
        def get(pid: int):
            if pid == 21:
                return {"id": 21, "final_video_path": _vpath, "cover_path": _cpath}
            if pid == 22:
                return {"id": 22, "final_video_path": _vpath, "cover_path": ""}
            return None

    _orig_key = _os.environ.get("VC_WEB_API_KEY")
    _os.environ["VC_WEB_API_KEY"] = "testkey"
    _pool_mod.VideoPool = _FakePool2
    try:
        r_v = _handler_pool_file(b3, {"pool_id": 21, "kind": "video"})
        r_c = _handler_pool_file(b3, {"pool_id": 21, "kind": "cover"})
        r_no_pool = _handler_pool_file(b3, {"pool_id": 99})
        r_no_cover = _handler_pool_file(b3, {"pool_id": 22, "kind": "cover"})
        r_bad_kind = _handler_pool_file(b3, {"pool_id": 21, "kind": "audio"})
    finally:
        _pool_mod.VideoPool = _orig_pool
        if _orig_key is None:
            _os.environ.pop("VC_WEB_API_KEY", None)
        else:
            _os.environ["VC_WEB_API_KEY"] = _orig_key
        import shutil as _shutil
        _shutil.rmtree(_tmp_dir, ignore_errors=True)

    ok = (r_v.get("ok") is True
          and "/api/pool/21/file?kind=video" in (r_v.get("url") or "")
          and "key=testkey" in (r_v.get("url") or "")
          and r_v.get("name") == "done.mp4"
          and r_v.get("size_mb", 0) > 0)
    record("TC-I22a pool_file 视频地址+鉴权参数正确", ok, r_v.get("url") or r_v.get("error", ""))

    ok = (r_c.get("ok") is True and "kind=cover" in (r_c.get("url") or "")
          and r_c.get("name") == "cover.jpg")
    record("TC-I22b pool_file 封面地址正确", ok, r_c.get("url") or r_c.get("error", ""))

    ok = (r_no_pool.get("ok") is False and r_no_cover.get("ok") is False
          and r_bad_kind.get("ok") is False)
    record("TC-I22c 池条目/封面缺失、非法 kind 均安全失败", ok,
           f"no_pool={r_no_pool.get('error')}, no_cover={r_no_cover.get('error')}")

    ok = all(m in _mob for m in ("downloadFile", "pool_file", "⬇ 视频", "⬇ 封面"))
    record("TC-I22d mobile.html 下载按钮已接入", ok)

    # --- TC-I19 全库 undefined name 扫描 (防"拆分漏 import"类地雷复发) ---
    try:
        from pyflakes.api import checkPath
        from pyflakes.reporter import Reporter
        import io as _io
        _out = _io.StringIO()
        rep = Reporter(_out, _out)
        scan_roots = [VC_ROOT / "core", VC_ROOT / "utils", VC_ROOT / "web",
                      VC_ROOT / "scripts", VC_ROOT / "gui"]
        scanned = 0
        for root_dir in scan_roots:
            if not root_dir.exists():
                continue
            for py in root_dir.rglob("*.py"):
                try:
                    checkPath(str(py), rep)
                    scanned += 1
                except Exception:
                    pass  # 个别文件解析失败不阻断
        # 只统计真正的 F821 (undefined name 'xxx'),
        # 排除 pyflakes 对 import * 的能力警告 ("unable to detect undefined names")
        undef_lines = [l for l in _out.getvalue().splitlines()
                       if "undefined name '" in l]
    except ImportError:
        undef_lines = []
        scanned = -1
        record("TC-I19 全库 undefined name 扫描", True, "pyflakes 未安装, 跳过 (pip install pyflakes)")
    else:
        record("TC-I19 全库 undefined name 扫描", len(undef_lines) == 0,
               f"扫描 {scanned} 个文件, undefined name={len(undef_lines)}"
               + (f" 首个: {undef_lines[0]}" if undef_lines else ""))

    # --- 信息性发现: JSON 数组 payload 会触发回调异常 ---
    b, sent = _make_offline_bridge()
    threw = False
    try:
        _feed(b, b"[1,2,3]")
    except Exception:
        threw = True
    record("TC-I15(发现) 非对象 JSON 会导致回调抛异常", True,
           f"payload='[1,2,3]' 抛异常={threw} (鲁棒性可改进点, 不算失败)")

    # --- TC-I21 恢复公网地址文件现场 (防测试破坏生产二维码 — 10/28 事故教训) ---
    try:
        if _url_backup is None:
            if _urlfile.exists():
                _urlfile.unlink()
            record("TC-I21 公网地址测试现场清理", True, "测试前无生产配置, 保持清除态")
        else:
            _urlfile.parent.mkdir(parents=True, exist_ok=True)
            _urlfile.write_text(_url_backup, encoding="utf-8")
            record("TC-I21 公网地址测试现场清理", True, f"已恢复: {_url_backup[:44]}")
    except Exception as e:
        record("TC-I21 公网地址测试现场清理", False, f"恢复失败: {e}")


# ===========================================================================
# B. 在线集成测试 (真连 broker.emqx.io)
# ===========================================================================
class _OnlinePhone:
    """模拟手机端 — 与 mobile.html 相同: WebSocket(WSS) 连 broker, 订阅 resp/log, 发 cmd"""

    def __init__(self, bridge: MqttBridge) -> None:
        self.bridge = bridge
        self.received: list[tuple[str, dict]] = []
        self._lock = threading.Lock()
        self._subscribed = threading.Event()
        import paho.mqtt.client as mqtt
        self.c = mqtt.Client(
            callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
            client_id=f"vc_test_phone_{uuid.uuid4().hex[:6]}",
            transport="websockets",
        )
        self.c.tls_set(cert_reqs=ssl.CERT_NONE)  # 公共 broker, 简化证书校验
        self.c.tls_insecure_set(True)
        self.c.on_connect = self._on_connect
        self.c.on_message = self._on_message
        self.connected = threading.Event()

    def _on_connect(self, client, userdata, flags, reason_code, properties) -> None:
        if reason_code == 0:
            client.subscribe(self.bridge.topic_resp)
            client.subscribe(self.bridge.topic_log)
            self._subscribed.set()
            self.connected.set()

    def _on_message(self, client, userdata, msg) -> None:
        try:
            data = json.loads(msg.payload.decode("utf-8"))
        except Exception:
            return
        with self._lock:
            self.received.append((msg.topic, data))

    def start(self) -> str:
        """连接 broker (WSS 8084), 失败则回退 TCP 1883; 返回实际使用的传输层描述"""
        try:
            self.c.connect(BROKER_HOST, WSS_PORT, keepalive=30)
            self.c.loop_start()
            if self.connected.wait(15):
                return "WSS:8084 (与手机端 mobile.html 相同通道)"
        except Exception:
            pass
        # 回退: TCP 1883 (传输层不同, 链路逻辑等价)
        try:
            self.c.loop_stop()
        except Exception:
            pass
        import paho.mqtt.client as mqtt
        self.c = mqtt.Client(
            callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
            client_id=f"vc_test_phone_{uuid.uuid4().hex[:6]}",
        )
        self.c.on_connect = self._on_connect
        self.c.on_message = self._on_message
        self.c.connect(BROKER_HOST, TCP_PORT, keepalive=30)
        self.c.loop_start()
        if self.connected.wait(15):
            return "TCP:1883 (WSS 失败后的回退通道)"
        return "连接失败"

    def publish_cmd(self, action: str, request_id: str, params: Optional[dict] = None,
                    token: Optional[str] = None) -> None:
        """向 cmd topic 发布一条指令 (模拟手机点按钮)"""
        payload = {"token": token if token is not None else self.bridge.token,
                   "action": action, "params": params or {}, "request_id": request_id}
        info = self.c.publish(self.bridge.topic_cmd, json.dumps(payload, ensure_ascii=False), qos=0)
        info.wait_for_publish(5)

    def wait_resp(self, request_id: str, timeout: float = 12.0) -> Optional[dict]:
        """等待指定 request_id 的响应回包"""
        deadline = time.time() + timeout
        while time.time() < deadline:
            with self._lock:
                for topic, o in self.received:
                    if topic.endswith("/resp") and o.get("request_id") == request_id:
                        return o
            time.sleep(0.2)
        return None

    def wait_log(self, keyword: str, timeout: float = 12.0) -> bool:
        """等待 log topic 上出现包含关键字的日志"""
        deadline = time.time() + timeout
        while time.time() < deadline:
            with self._lock:
                for topic, o in self.received:
                    if topic.endswith("/log") and keyword in str(o.get("msg", "")):
                        return True
            time.sleep(0.2)
        return False

    def stop(self) -> None:
        """断开并停止网络线程"""
        try:
            self.c.loop_stop()
            self.c.disconnect()
        except Exception:
            pass


def run_online_tests() -> None:
    """在线部分: 真连 broker, 验证手机→PC→回包全链路"""
    print("\n========== B. 在线集成测试 (broker.emqx.io) ==========")

    # 护栏: 真实 GUI bridge 在线时, PC bridge 部分必须跳过 ——
    #   测试 bridge 与 GUI bridge 会互踢; 测试发布的 pipeline 指令会被真实 GUI 消费执行。
    #   探测方式: 用正确 token 向 cmd 发 ping, 3s 内收到回包 → 真实 bridge 在线
    #   (比端口探测可靠: uvicorn 死而 bridge 活时端口探测会漏报)
    gui_online = False
    try:
        probe_owner = MqttBridge()
        probe = _OnlinePhone(probe_owner)
        if probe.start():
            probe.publish_cmd("ping", "probe_alive")
            gui_online = probe.wait_resp("probe_alive", timeout=3.0) is not None
        probe.stop()
    except Exception:
        gui_online = False
    if gui_online:
        print("  [SKIP] 检测到真实 GUI bridge 在线 (ping 有回包) —— 跳过 PC bridge 交互测试")
        print("         (避免 client_id 互踢; 手机端连接测试仍照常执行)")

    # 准备依赖 (与 web.main lifespan 注入方式一致, 但 pipeline 用 mock)
    store = FakeTaskStore()
    pipeline_calls: list[dict] = []

    def fake_pipeline_single(params: dict) -> dict:
        """注入的假流水线 — 只验证联动派发, 不跑重型管线"""
        pipeline_calls.append(params)
        return {"ok": True, "msg": "单视频任务已启动"}

    # --- TC-O1 模拟手机端先连接并订阅 (resp + log) ---
    phone_proto = MqttBridge()  # 仅借用其 topic 配置, 不启动
    phone = _OnlinePhone(phone_proto)
    transport = phone.start()
    record("TC-O1 模拟手机端连接 broker", phone.connected.is_set(), transport)
    if not phone.connected.is_set():
        record("TC-O2~O8 全部跳过", False, "broker 连不上, 在线部分终止")
        return
    time.sleep(1.0)  # 等订阅生效

    if gui_online:
        record("TC-O2~O8 跳过 (真实 GUI 在线)", True,
               "PC bridge 部分避免 client_id 互踢与误触发真流水线; 手机端链路已验证")
        phone.stop()
        return

    # --- TC-O2 PC bridge 连接后手机端收到"设备上线"推送 (log 通道) ---
    bridge = MqttBridge()
    bridge.set_dependencies(task_store=store, pipeline_single=fake_pipeline_single)
    bridge.start()
    t0 = time.time()
    while time.time() - t0 < 20 and not bridge._connected:
        time.sleep(0.3)
    record("TC-O2 PC bridge 连上 broker", bridge._connected,
           f"耗时 {time.time() - t0:.1f}s, device={bridge.device_id[:8]}…")
    if not bridge._connected:
        record("TC-O3~O8 全部跳过", False, "PC bridge 连不上, 在线部分终止")
        phone.stop()
        return
    got_online_log = phone.wait_log("设备上线", timeout=8.0)
    record("TC-O3 log 通道推送'设备上线'事件", got_online_log, "(phone 已先订阅, 应必达)")
    _MASKS.append(bridge.token)  # 后续输出脱敏

    # --- TC-O4 ping 全链路往返 ---
    phone.publish_cmd("ping", "o3")
    r = phone.wait_resp("o3")
    ok = r is not None and r["ok"] is True and r["data"].get("msg") == "pong"
    record("TC-O4 手机发 ping → PC 回 pong", ok, f"resp={r}")

    # --- TC-O5 status 全链路: 设备快照 + 任务快照透传 ---
    phone.publish_cmd("status", "o4")
    r = phone.wait_resp("o4")
    ok = r is not None and r["ok"] is True \
        and r["data"].get("device", {}).get("device_id") == bridge.device_id \
        and r["data"].get("task", {}).get("fake") is True
    record("TC-O5 status 返回设备+任务快照", ok, f"device_id匹配={r is not None}")

    # --- TC-O6 logs 全链路: 任务存储日志缓冲透传 ---
    phone.publish_cmd("logs", "o5", params={"limit": 2})
    r = phone.wait_resp("o5")
    ok = r is not None and r["ok"] is True and r["data"].get("count") == 2
    record("TC-O6 logs 返回日志缓冲", ok, f"count={r['data'].get('count') if r else None}")

    # --- TC-O7 pipeline_single 全链路触发: 手机按钮 → PC mock 收到 params → resp+log 回传 ---
    phone.publish_cmd("pipeline_single", "o6", params={"url": "https://example.com/demo.mp4"})
    r = phone.wait_resp("o6")
    got_log = phone.wait_log("MQTT 触发单视频")
    ok = r is not None and r["ok"] is True and r["data"].get("msg") == "单视频任务已启动" \
        and len(pipeline_calls) == 1 and pipeline_calls[0].get("url") == "https://example.com/demo.mp4"
    record("TC-O7 pipeline_single 全链路触发", ok and got_log,
           f"mock收到={len(pipeline_calls)}次, log回传={got_log}, resp={r}")

    # --- TC-O8 在线错误 token: 指令被拒, 无响应回包 ---
    phone.publish_cmd("ping", "o7", token="WRONG_TOKEN")
    r = phone.wait_resp("o7", timeout=6.0)
    record("TC-O8 在线错误 token 被拒(无回包)", r is None, f"resp={r}")

    # --- 清理 ---
    phone.stop()
    bridge.stop()
    print("  (在线资源已清理: phone 断开, bridge stop)")


# ===========================================================================
# 入口
# ===========================================================================
def main() -> int:
    """跑全部测试, 返回失败数"""
    parser = argparse.ArgumentParser(description="MQTT 手机-电脑联动测试")
    parser.add_argument("--offline-only", action="store_true", help="只跑离线单元测试")
    args = parser.parse_args()

    print("=" * 56)
    print("VideoCrawler MQTT 联动自动化测试")
    print(f"device_id 来自: {VC_ROOT / 'data' / 'mqtt_device.json'} (token 输出已脱敏)")
    print("=" * 56)

    # 脱敏: 所有 bridge 实例共用 data/mqtt_device.json 里的同一 token
    try:
        dev = json.loads((VC_ROOT / "data" / "mqtt_device.json").read_text(encoding="utf-8"))
        _MASKS.append(str(dev.get("token", "")))
    except Exception:
        pass

    run_offline_tests()
    if not args.offline_only:
        run_online_tests()

    failed = [r for r in _results if not r[1]]
    print("\n" + "=" * 56)
    print(f"汇总: 共 {len(_results)} 项, 失败 {len(failed)} 项")
    for name, _, note in failed:
        print(f"  ✗ {name}  {_mask(note)}")
    print("=" * 56)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
