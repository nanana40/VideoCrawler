"""
VideoCrawler MQTT Bridge
========================
远程控制主通道 —— 用公共 broker.emqx.io 做消息中继,
PC 主动出站连接 (TCP 1883), 手机 H5 网页走 WebSocket (8084),
纯 MQTT, 零反向隧道依赖。

设计原则:
  - 设备身份持久化 (device_id + token 存 Vc/data/mqtt_device.json, 重启不丢)
  - 双层鉴权: 独立 topic (user/{device_id}/*) + 消息内 token 校验
  - 指令白名单: 只允许预定义的 action, 不执行任意系统命令
  - 断线自动重连 (paho-mqtt reconnect_delay_set)
  - 不 import web.main (避免 FastAPI 循环), 通过回调注入依赖

Topic 约定:
  user/{device_id}/cmd   ← 手机下发指令 (JSON)
  user/{device_id}/resp  → 响应回传 (JSON)
  user/{device_id}/log   → 日志推送 (JSON)

消息格式 (统一 JSON, 便于扩展和前端解析):
  CMD:  {"token":"xxx", "action":"status", "params":{}, "request_id":"abc"}
  RESP: {"token":"xxx", "request_id":"abc", "ok":true, "data":{}, "error":""}
  LOG:  {"token":"xxx", "ts":1234567890, "msg":"[14:30:21] ..."}
"""

from __future__ import annotations

import json
import os
import random
import string
import threading
import time
from pathlib import Path
from typing import Any, Callable, Optional
from urllib.parse import quote

from loguru import logger

# ---------------------------------------------------------------------------
# Broker 配置 (公共免费 EMQX)
# ---------------------------------------------------------------------------
BROKER_HOST = os.environ.get("VC_MQTT_BROKER", "broker.emqx.io")
BROKER_PORT = int(os.environ.get("VC_MQTT_TCP_PORT", "1883"))
BROKER_WS_PORT = int(os.environ.get("VC_MQTT_WS_PORT", "8084"))
# 备选兜底: test.mosquitto.org
FALLBACK_BROKERS = [
    ("test.mosquitto.org", 1883),
]

BASE_TOPIC = os.environ.get("VC_MQTT_BASE_TOPIC", "user")
KEEPALIVE = int(os.environ.get("VC_MQTT_KEEPALIVE", "60"))
# Web 面板端口 (局域网兜底二维码用, 与 GuiWebHost 默认端口一致; 自定义端口时需同步设置)
WEB_PORT = int(os.environ.get("VC_WEB_PORT", "8000"))


# ---------------------------------------------------------------------------
# 设备身份持久化
# ---------------------------------------------------------------------------
def _data_dir() -> Path:
    """用户数据目录（打包后为 %LOCALAPPDATA%\\VideoCrawler\\data）"""
    # 局部 import：避免模块加载顺序问题（web/main.py 启动时才注入 sys.path）
    from utils.path_helper import get_data_dir

    return get_data_dir()


def _device_file() -> Path:
    return _data_dir() / "mqtt_device.json"


def _web_url_file() -> Path:
    """持久化公网 H5 地址的文件 (data/mqtt_web_url.txt, 快速隧道自动写入)"""
    return _data_dir() / "mqtt_web_url.txt"


def _load_web_ui_url() -> str:
    """读取公网 H5 地址: 环境变量 VC_MQTT_WEB_URL 优先, 其次持久化文件"""
    env = os.environ.get("VC_MQTT_WEB_URL", "").strip()
    if env:
        return env
    try:
        f = _web_url_file()
        if f.exists():
            url = f.read_text(encoding="utf-8").strip()
            if url:
                return url
    except Exception as e:
        logger.warning(f"[MQTT] 读取公网地址文件失败: {e}")
    return ""


def save_web_ui_url(url: str) -> None:
    """持久化公网 H5 地址 (公网模式二维码数据源; 传入空串视为清除)"""
    try:
        f = _web_url_file()
        if url.strip():
            f.write_text(url.strip(), encoding="utf-8")
        elif f.exists():
            f.unlink()
    except Exception as e:
        logger.warning(f"[MQTT] 保存公网地址失败: {e}")


def _lan_ip() -> str:
    """探测本机局域网 IP.

    多网卡机器 (WSL / VMware / VPN TUN) 会暴露多个地址, 二维码必须指向
    手机真正可达的那块网卡, 所以按优先级挑选:
      192.168.* > 10.* > UDP 路由源地址 > 172.16-31.* > 其余 > 127.0.0.1
    """
    import socket

    candidates: list[str] = []
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            ip = info[4][0]
            if ip and not ip.startswith("127.") and ip not in candidates:
                candidates.append(ip)
    except Exception:
        pass
    # UDP connect 不发包, 取默认路由源地址 (虚拟网卡/VPN 时可能不可用)
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            s.connect(("8.8.8.8", 80))
            src = s.getsockname()[0]
            if src and not src.startswith("127.") and src not in candidates:
                candidates.insert(0, src)
        finally:
            s.close()
    except Exception:
        pass

    for prefix in ("192.168.", "10."):
        for ip in candidates:
            if ip.startswith(prefix):
                return ip
    for ip in candidates:
        if ip.startswith("172."):
            return ip
    return candidates[0] if candidates else "127.0.0.1"


def _load_or_create_device() -> dict:
    """读取已有 device_id + token, 没有就生成并持久化"""
    f = _device_file()
    if f.exists():
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            if data.get("device_id") and data.get("token"):
                return data
        except Exception as e:
            logger.warning(f"[MQTT] 设备文件损坏, 重新生成: {e}")

    device_id = "".join(random.choices(string.ascii_lowercase + string.digits, k=16))
    token = "".join(random.choices(string.ascii_letters + string.digits, k=24))
    data = {
        "device_id": device_id,
        "token": token,
        "created_at": time.time(),
    }
    try:
        f.write_text(json.dumps(data, indent=2), encoding="utf-8")
    except Exception as e:
        logger.warning(f"[MQTT] 设备信息持久化失败: {e}")
    logger.info(f"[MQTT] 新设备: {device_id}")
    return data


# ---------------------------------------------------------------------------
# Bridge 类
# ---------------------------------------------------------------------------
class MqttBridge:
    """MQTT 控制桥 — 单例, 被 web_host / main.py 共用"""

    _instance: Optional["MqttBridge"] = None
    _lock = threading.Lock()

    def __init__(self, web_ui_url: str = "") -> None:
        self._device = _load_or_create_device()
        self.device_id = self._device["device_id"]
        self.token = self._device["token"]
        self.topic_cmd = f"{BASE_TOPIC}/{self.device_id}/cmd"
        self.topic_resp = f"{BASE_TOPIC}/{self.device_id}/resp"
        self.topic_log = f"{BASE_TOPIC}/{self.device_id}/log"

        # ── H5 面板 URL: 公网静态托管地址 ──
        # 优先级: 构造参数 > 环境变量 VC_MQTT_WEB_URL > 持久化文件 (快速隧道写入)
        self.web_ui_url = web_ui_url or _load_web_ui_url()

        # paho client
        import paho.mqtt.client as mqtt

        # client_id 加会话级随机后缀: 公共 broker (emqx) 对高频重连的固定 client_id
        # 会触发滥用防护直接封禁 (rc=5 Not authorized), 随机化后每次启动都是新 ID,
        # 即使被限流重启即自愈; 手机端 clientId 本就是随机的
        session_suffix = "".join(random.choices(string.ascii_lowercase + string.digits, k=8))
        self._mqtt = mqtt.Client(
            client_id=f"vc_{self.device_id[:8]}_{session_suffix}",
            callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
        )
        self._mqtt.on_connect = self._on_connect
        self._mqtt.on_message = self._on_message
        self._mqtt.on_disconnect = self._on_disconnect
        self._mqtt.on_subscribe = self._on_subscribe
        self._mqtt.on_socket_open = self._on_socket_open
        # 自动重连 (指数退避: 1s → 2s → 4s → ... → 60s)
        self._mqtt.reconnect_delay_set(min_delay=1, max_delay=60)

        # 状态
        self._connected = False
        self._connected_at: float = 0
        self._last_error = ""
        self._resp_lock = threading.Lock()

        # 日志节流: 所有 bridge_task_log 先入队, 后台定时器批量 publish (每 250ms)
        self._log_buffer: list[str] = []
        self._log_buffer_lock = threading.Lock()
        self._log_flush_thread: Optional[threading.Thread] = None
        self._log_flush_stop = threading.Event()

        # 依赖注入 (web.main lifespan 里 set_dependencies)
        self._task_store = None          # web.main.TASKS
        self._publish_queue_snapshot = None
        self._publish_enqueue = None
        self._pipeline_single = None
        self._pipeline_search = None
        self._stop_current = None
        self._log_push = None            # 外部日志回传 (TASKS.push_log)

        # 子任务互斥 (识别/成品制作/文案 等重活串行, 防并发抢 ffmpeg/GPU)
        self._subtask_lock = threading.Lock()
        self._copy_latest_path: str = ""  # 最近一次生成的文案文件路径

    # ------------------------------------------------------------------
    # 单例
    # ------------------------------------------------------------------
    @classmethod
    def instance(cls, web_ui_url: str = "") -> "MqttBridge":
        with cls._lock:
            if cls._instance is None:
                cls._instance = cls(web_ui_url=web_ui_url)
            return cls._instance

    # ------------------------------------------------------------------
    # 依赖注入 (避免循环 import web.main)
    # ------------------------------------------------------------------
    def set_dependencies(
        self,
        task_store=None,
        log_push: Optional[Callable[[str], None]] = None,
        pipeline_single: Optional[Callable[[dict], dict]] = None,
        pipeline_search: Optional[Callable[[dict], dict]] = None,
        stop_current: Optional[Callable[[], None]] = None,
        publish_enqueue: Optional[Callable[[list], Any]] = None,
    ) -> None:
        self._task_store = task_store
        self._log_push = log_push
        self._pipeline_single = pipeline_single
        self._pipeline_search = pipeline_search
        self._stop_current = stop_current
        self._publish_enqueue = publish_enqueue

    # ------------------------------------------------------------------
    # 生命周期
    # ------------------------------------------------------------------
    def start(self) -> bool:
        """启动 MQTT 连接 (非阻塞, 后台跑 loop)"""
        if self._connected:
            return True
        try:
            self._mqtt.connect(BROKER_HOST, BROKER_PORT, KEEPALIVE)
            self._mqtt.loop_start()
            # 启动日志节流 flush 线程
            self._log_flush_stop.clear()
            if self._log_flush_thread is None or not self._log_flush_thread.is_alive():
                self._log_flush_thread = threading.Thread(
                    target=self._log_flush_loop, name="mqtt-log-flush", daemon=True,
                )
                self._log_flush_thread.start()
            logger.info(f"[MQTT] 正在连接 {BROKER_HOST}:{BROKER_PORT}")
            return True
        except Exception as e:
            self._last_error = str(e)
            logger.error(f"[MQTT] 启动失败: {e}")
            return False

    def stop(self) -> None:
        """断开连接"""
        # 停 flush 线程
        self._log_flush_stop.set()
        # 最后 flush 一次
        self._flush_log_buffer()
        try:
            self._mqtt.loop_stop()
            self._mqtt.disconnect()
        except Exception:
            pass
        self._connected = False
        logger.info("[MQTT] 已断开")

    def restart(self) -> bool:
        self.stop()
        time.sleep(0.5)
        return self.start()

    # ------------------------------------------------------------------
    # paho 回调
    # ------------------------------------------------------------------
    def _on_connect(self, client, userdata, connect_flags, reason_code, properties):
        now = time.time()
        if reason_code == 0:
            was_reconnect = self._connected is False and self._connected_at > 0
            self._connected = True
            self._connected_at = now
            self._last_error = ""
            client.subscribe(self.topic_cmd)
            # 节流: 10s 内反复重连只打 INFO, 首次/稳定连接打 INFO
            if now - self._last_connect_log > 10 or not was_reconnect:
                logger.info(
                    f"[MQTT] ✅ 已连接{(' (重连成功)' if was_reconnect else '')}, "
                    f"订阅 {self.topic_cmd}"
                )
                self._publish_log("🟢 设备上线")
                self._publish_resp(request_id="", ok=True, data={"msg": "online"})
            self._last_connect_log = now
        else:
            self._last_error = f"connect rc={reason_code}"
            logger.warning(f"[MQTT] 连接被拒: rc={reason_code}")

    def _on_disconnect(self, client, userdata, disconnect_flags, reason_code, properties):
        self._connected = False
        self._last_error = f"disconnect rc={reason_code}"
        now = time.time()
        # 节流: 10 秒内多次断连只打一次 WARNING, 中间打 DEBUG
        if now - self._last_disconnect_log > 10:
            logger.warning(f"[MQTT] ⚠ 已断开 (rc={reason_code}), 自动重连中...")
            self._last_disconnect_log = now
        else:
            logger.debug(f"[MQTT] disconnect rc={reason_code} (throttled)")

    # 节流: 断连/重连日志不 spam (10 秒内最多打 1 次)
    _last_disconnect_log: float = 0
    _last_connect_log: float = 0

    def _on_socket_open(self, client, userdata, sock):
        """TCP socket 打开时设置 socket 选项, 提升 VPN/TUN 下的稳定性"""
        import socket as _sock
        # 开启 TCP keepalive —— OS 层面每 30s 发一次探测包
        # 比 MQTT 应用层 keepalive (60s) 更能穿透 VPN TUN 状态转换
        try:
            sock.setsockopt(_sock.SOL_SOCKET, _sock.SO_KEEPALIVE, 1)
            # TCP keepalive 参数 (Linux/macOS/Windows 通用写法)
            tcp_keepidle = 30   # 空闲 30s 后开始发探测
            tcp_keepintvl = 10  # 每次探测间隔 10s
            tcp_keepcnt = 3     # 探测 3 次无响应就判定断开
            for opt_name, opt_val in [
                ("TCP_KEEPIDLE", tcp_keepidle),
                ("TCP_KEEPINTVL", tcp_keepintvl),
                ("TCP_KEEPCNT", tcp_keepcnt),
            ]:
                if hasattr(_sock, opt_name):
                    sock.setsockopt(_sock.IPPROTO_TCP, getattr(_sock, opt_name), opt_val)
            # Windows 专用别名
            if hasattr(_sock, 'TCP_KEEPALIVE'):
                sock.setsockopt(_sock.IPPROTO_TCP, _sock.TCP_KEEPALIVE, tcp_keepidle)
        except Exception as e:
            logger.debug(f"[MQTT] TCP keepalive 设置跳过: {e}")
        # 关闭 Nagle 算法 —— MQTT 小包实时发送
        try:
            sock.setsockopt(_sock.IPPROTO_TCP, _sock.TCP_NODELAY, 1)
        except Exception:
            pass

    def _on_subscribe(self, client, userdata, mid, reason_code_list, properties):
        pass  # 静默

    def _on_message(self, client, userdata, msg) -> None:
        """收到指令 — 解析 → 鉴权 → 路由"""
        try:
            raw = msg.payload.decode("utf-8").strip()
            if not raw:
                return
            payload = json.loads(raw)
        except Exception as e:
            logger.warning(f"[MQTT] 消息解析失败: {e} payload={msg.payload[:80]}")
            return

        # --- token 校验 ---
        token = payload.get("token", "")
        if token != self.token:
            logger.warning(f"[MQTT] token 校验失败, 丢弃指令")
            return

        request_id = payload.get("request_id", "")
        action = payload.get("action", "")
        params = payload.get("params", {}) or {}

        # --- 路由 ---
        handler = ACTION_HANDLERS.get(action)
        if handler is None:
            self._publish_resp(request_id, False, error=f"未知 action: {action}")
            return

        try:
            result = handler(self, params)
            self._publish_resp(request_id, True, data=result)
        except Exception as e:
            logger.exception(f"[MQTT] action={action} 执行异常")
            self._publish_resp(request_id, False, error=str(e))

    # ------------------------------------------------------------------
    # 发布工具
    # ------------------------------------------------------------------
    def _publish_json(self, topic: str, obj: dict) -> None:
        if not self._connected:
            return
        try:
            payload = json.dumps(obj, ensure_ascii=False).encode("utf-8")
            self._mqtt.publish(topic, payload, qos=0)
        except Exception as e:
            logger.warning(f"[MQTT] publish 失败: {e}")

    def _publish_log(self, msg: str) -> None:
        self._publish_json(self.topic_log, {
            "token": self.token,
            "ts": int(time.time()),
            "msg": msg,
        })

    def _publish_resp(self, request_id: str, ok: bool,
                      data: Optional[dict] = None, error: str = "") -> None:
        self._publish_json(self.topic_resp, {
            "token": self.token,
            "request_id": request_id,
            "ok": ok,
            "data": data or {},
            "error": error,
        })

    # ------------------------------------------------------------------
    # 外部调用: 桥接 TASKS 日志 → MQTT
    # ------------------------------------------------------------------
    def bridge_task_log(self, msg: str) -> None:
        """供 web.main 把 TASKS.push_log 的内容桥到 MQTT log topic (入队, 节流)"""
        with self._log_buffer_lock:
            self._log_buffer.append(msg)

    def _log_flush_loop(self) -> None:
        """后台线程: 每 250ms 批量 publish 积压的日志"""
        while not self._log_flush_stop.wait(0.25):
            self._flush_log_buffer()

    def _flush_log_buffer(self) -> None:
        """把 buffer 里的日志一次性 publish (多条合并为一条 JSON)"""
        msgs: list[str] = []
        with self._log_buffer_lock:
            msgs = self._log_buffer
            self._log_buffer = []
        if not msgs:
            return
        for m in msgs[-50:]:  # 单批最多 50 条, 防止 broker 限流
            self._publish_log(m)

    # ------------------------------------------------------------------
    # 状态快照
    # ------------------------------------------------------------------
    def status(self) -> dict:
        return {
            "connected": self._connected,
            "connected_at": self._connected_at,
            "uptime_sec": round(time.time() - self._connected_at, 1) if self._connected else 0,
            "last_error": self._last_error,
            "device_id": self.device_id,
            "broker": BROKER_HOST,
            "tcp_port": BROKER_PORT,
            "ws_port": BROKER_WS_PORT,
            "topic_cmd": self.topic_cmd,
            "topic_resp": self.topic_resp,
            "topic_log": self.topic_log,
            "web_ui_url": self._full_web_url(),
        }

    def _full_web_url(self) -> str:
        """首选公网托管地址; 未配置 VC_MQTT_WEB_URL 时兜底局域网直连地址"""
        return self.get_qr_urls()["url"]

    def _lan_url(self) -> str:
        """局域网直连地址 (手机与 PC 同一 WiFi 时可直接打开 PC 上的 mobile.html)"""
        return (f"http://{_lan_ip()}:{WEB_PORT}/static/mobile.html"
                f"?device={self.device_id}&token={self.token}")

    def get_qr_urls(self) -> dict:
        """返回二维码用的连接地址集合 (双模式).

        Returns:
            {"mode": "public"|"lan", "url": 首选地址,
             "lan": 局域网地址, "public": 公网地址 (未配置则为空)}
        """
        # 每次现读: 兼容隧道启动后写入的持久化文件 (实例构造时可能还没有)
        if not self.web_ui_url:
            self.web_ui_url = _load_web_ui_url()
        public = ""
        if self.web_ui_url:
            sep = "&" if "?" in self.web_ui_url else "?"
            public = f"{self.web_ui_url}{sep}device={self.device_id}&token={self.token}"
        lan = self._lan_url()
        if public:
            return {"mode": "public", "url": public, "lan": lan, "public": public}
        return {"mode": "lan", "url": lan, "lan": lan, "public": ""}

    # ------------------------------------------------------------------
    # 二维码 URL 生成 (给 GUI 显示)
    # ------------------------------------------------------------------
    def get_qr_url(self) -> str:
        """返回带 device_id + token 的完整 H5 链接, 用于二维码"""
        return self._full_web_url()


# ===========================================================================
# 指令处理器 (白名单 + 参数校验)
# ===========================================================================

ActionHandler = Callable[[MqttBridge, dict], Any]


def _handler_ping(bridge: MqttBridge, params: dict) -> dict:
    return {"msg": "pong", "ts": int(time.time()), "device_id": bridge.device_id}


def _handler_status(bridge: MqttBridge, params: dict) -> dict:
    task_snap = {}
    if bridge._task_store:
        try:
            task_snap = bridge._task_store.snapshot()
        except Exception:
            pass
    return {
        "device": bridge.status(),
        "task": task_snap,
    }


def _handler_logs(bridge: MqttBridge, params: dict) -> dict:
    limit = int(params.get("limit", 50))
    if bridge._task_store and hasattr(bridge._task_store, "log_buffer"):
        logs = list(bridge._task_store.log_buffer)[-limit:]
        return {"logs": logs, "count": len(logs)}
    return {"logs": [], "count": 0}


def _handler_pipeline_single(bridge: MqttBridge, params: dict) -> dict:
    """触发单视频全自动流水线"""
    if not bridge._pipeline_single:
        raise RuntimeError("pipeline_single 未注入 (MQTT bridge 缺少依赖)")
    if not params.get("url"):
        raise ValueError("缺少 url 参数")
    bridge._publish_log(f"📥 MQTT 触发单视频: {params['url']}")
    return bridge._pipeline_single(params)


def _handler_pipeline_search(bridge: MqttBridge, params: dict) -> dict:
    if not bridge._pipeline_search:
        raise RuntimeError("pipeline_search 未注入")
    bridge._publish_log(f"📥 MQTT 触发搜索流水线: {params}")
    return bridge._pipeline_search(params)


def _handler_stop(bridge: MqttBridge, params: dict) -> dict:
    if bridge._stop_current:
        bridge._stop_current()
    bridge._publish_log("⏹ MQTT 停止指令已记录")
    return {"ok": True, "msg": "stop requested"}


def _handler_queue_snapshot(bridge: MqttBridge, params: dict) -> dict:
    from core.publish.publish_queue import get_publish_queue
    return get_publish_queue().snapshot()


def _handler_queue_enqueue(bridge: MqttBridge, params: dict) -> dict:
    """批量入队: params = {"items": [{"pool_id":1,"account_id":2}, ...]}"""
    from core.publish.publish_queue import get_publish_queue, PublishJob
    items = params.get("items", [])
    if not items:
        raise ValueError("items 为空")
    q = get_publish_queue()
    jobs = []
    for it in items:
        j = PublishJob(
            pool_id=it["pool_id"],
            account_id=it["account_id"],
            title=it.get("title"),
            description=it.get("description"),
            tags=it.get("tags"),
            scheduled_ts=it.get("scheduled_ts"),
            original=it.get("original", True),
        )
        jobs.append(j)
    ids = q.enqueue_batch(jobs)
    bridge._publish_log(f"📥 MQTT 入队 {len(ids)} 条")
    return {"ok": True, "enqueued": len(ids), "job_ids": ids}


def _handler_videos(bridge: MqttBridge, params: dict) -> dict:
    """列出 output 视频 (轻量版, 不 import web.main)"""
    this_dir = Path(__file__).resolve().parent
    vc_root = this_dir.parent
    out_root = vc_root / "output"
    limit = int(params.get("limit", 20))
    videos = []
    if out_root.is_dir():
        mp4s = sorted(out_root.rglob("*.mp4"), key=lambda p: p.stat().st_mtime, reverse=True)
        for p in mp4s[:limit]:
            videos.append({
                "name": p.name,
                "path": str(p.relative_to(out_root)),
                "size_mb": round(p.stat().st_size / 1024 / 1024, 1),
                "mtime": time.strftime("%Y-%m-%d %H:%M", time.localtime(p.stat().st_mtime)),
            })
    return {"videos": videos}


def _handler_accounts(bridge: MqttBridge, params: dict) -> dict:
    """列出已配置的发布账号"""
    from core.publish.accounts import AccountManager
    accs = AccountManager.list_accounts(only_active=False)
    for a in accs:
        a.pop("cookies", None)  # 脱敏
    return {"accounts": accs}


def _handler_dump_stacks(bridge: MqttBridge, params: dict) -> dict:
    """dump 所有 Python 线程的当前栈帧 — 用于诊断卡死位置"""
    import threading as _t
    import traceback
    lines = []
    for tid, frame in _t._active_frames().items():
        name = "?"
        for t in _t.enumerate():
            if t.ident == tid:
                name = t.name
                break
        lines.append(f"--- Thread {name} (tid={tid}) ---")
        lines.extend(traceback.format_stack(frame))
    return {"stacks": "\n".join(lines)[:8000]}


# ---------------------------------------------------------------------------
# 手机端功能扩展 (对齐 GUI 五页的一期远程操作)
# ---------------------------------------------------------------------------

# 字幕样式白名单 (与 GUI page_subtitle._save_style_config 保存的键一致)
_STYLE_KEYS = {
    "font_size", "primary_color", "outline_color", "bilingual", "bilingual_pos",
    "secondary_scale", "margin_v", "bar_enabled", "bar_height", "bar_opacity_pct",
    "out_mp4", "out_mkv", "pos_x", "pos_y",
}


def _handler_subtitle_style_get(bridge: MqttBridge, params: dict) -> dict:
    """读取字幕样式参数 (config.yaml 的 subtitle_style section)"""
    from utils.config_loader import load_config
    return {"style": load_config().get("subtitle_style", {})}


def _handler_subtitle_style_set(bridge: MqttBridge, params: dict) -> dict:
    """保存字幕样式参数 (仅白名单字段, 与 GUI 共用同一配置)"""
    from utils.config_loader import save_subsection
    style = params.get("style")
    if not isinstance(style, dict) or not style:
        raise ValueError("缺少 style 参数")
    filtered = {k: v for k, v in style.items() if k in _STYLE_KEYS}
    if not filtered:
        raise ValueError("style 中无可识别字段")
    save_subsection("subtitle_style", filtered)
    bridge._publish_log("⚙️ MQTT 已更新字幕样式")
    return {"ok": True, "saved": sorted(filtered.keys())}


def _resolve_media_path(name: str) -> Path:
    """把手机端传来的文件名解析为本机真实路径.

    规则: 绝对路径直接用; 相对名依次在 output/、成品字幕目录、Vc 根下查找;
    相对名禁止包含 ".." (防目录穿越)
    """
    from utils.path_helper import get_output_dir, get_finished_sub_dir
    if not name:
        raise ValueError("缺少文件名")
    p = Path(name)
    if p.is_absolute():
        if p.exists():
            return p
        raise ValueError(f"文件不存在: {name}")
    if ".." in p.parts:
        raise ValueError("非法路径 (不允许 ..)")
    for base in (get_output_dir(), get_finished_sub_dir(),
                 Path(__file__).resolve().parent.parent):
        cand = base / name
        if cand.exists():
            return cand
    raise ValueError(f"文件不存在: {name} (请在 output/ 或成品字幕目录下)")


def _handler_subtitle_render(bridge: MqttBridge, params: dict) -> dict:
    """异步制作成品字幕视频 (GUI ③ 页『开始制作成品』的远程版, 样式取自 config)"""
    video = _resolve_media_path(str(params.get("video", "")))
    srt = _resolve_media_path(str(params.get("srt", "")))
    from utils.config_loader import load_config
    style = load_config().get("subtitle_style", {})
    tag = video.stem[:24]

    if not bridge._subtask_lock.acquire(blocking=False):
        raise RuntimeError("已有子任务在执行 (识别/成品/文案), 请稍后再试")

    def _worker() -> None:
        try:
            from core.subtitle_render import burn_mp4

            def _cb(done: int, msg: str) -> None:
                bridge._publish_log(f"🎬 [{tag}] {msg} ({done}%)")

            out = burn_mp4(
                str(video), str(srt),
                font_size=int(style.get("font_size", 8)),
                margin_v=int(style.get("margin_v", 16)),
                primary_color=str(style.get("primary_color", "#FFFFFF")),
                outline_color=str(style.get("outline_color", "#000000")),
                progress_cb=_cb,
                bilingual=bool(style.get("bilingual", True)),
                bilingual_pos=str(style.get("bilingual_pos", "src_top")),
                secondary_scale=float(style.get("secondary_scale", 0.85)),
                bar_enabled=bool(style.get("bar_enabled", False)),
                bar_height=int(style.get("bar_height", 48)),
            )
            if out:
                bridge._publish_log(f"✅ [{tag}] 成品已生成: {out}")
            else:
                bridge._publish_log(f"❌ [{tag}] 成品制作失败 (详见 PC 日志)")
        except Exception as e:
            logger.exception("[MQTT] subtitle_render 异常")
            bridge._publish_log(f"❌ [{tag}] 成品制作异常: {e}")
        finally:
            bridge._subtask_lock.release()

    from utils.thread_spawn import spawn
    spawn(target=_worker, daemon=True).start()
    bridge._publish_log(f"🎬 MQTT 触发成品制作: {video.name}")
    return {"ok": True, "msg": "成品制作已启动", "video": video.name}


def _archive_params_from_path(video: Path) -> dict[str, Any]:
    """从成品视频路径反解归档参数.

    归档结构为 output/<语言>/<分类>/[<频道>/]<视频id>/xxx.mp4，
    反解出 language/category/channel/video_id，让手机端「识别」产出的 SRT
    与视频同目录（否则会落到 output/<视频id>/ 这类孤立目录）。

    解析失败（不在 output 下、层级不符、枚举非法）返回空 dict，调用方走默认值。
    """
    from utils.enums import LanguageType, VideoCategory
    from utils.path_helper import get_output_dir

    try:
        parts = video.resolve().relative_to(get_output_dir().resolve()).parts
    except (OSError, ValueError):
        return {}
    if len(parts) < 4:                      # 至少 <语言>/<分类>/<视频id>/<文件>
        return {}
    language = LanguageType.from_code(parts[0])
    category = VideoCategory.from_code(parts[1])
    if language is None or category is None:
        return {}
    if len(parts) == 4:
        return {"language": language, "category": category,
                "channel": None, "video_id": parts[2]}
    return {"language": language, "category": category,
            "channel": parts[2], "video_id": parts[3]}


def _handler_recognize_start(bridge: MqttBridge, params: dict) -> dict:
    """异步对本地视频做 识别+翻译 → 产出 SRT (GUI ② 页远程版)"""
    video = _resolve_media_path(str(params.get("video", "")))
    target = str(params.get("target_lang", "zh-CN"))
    # 按视频所在归档目录反解语言/分类/频道，保证 SRT 落在视频同目录
    arch = _archive_params_from_path(video)
    video_id = arch.get("video_id") or video.stem
    tag = video.stem[:24]

    if not bridge._subtask_lock.acquire(blocking=False):
        raise RuntimeError("已有子任务在执行 (识别/成品/文案), 请稍后再试")

    def _worker() -> None:
        try:
            from core.subtitles.processor import process_video_subtitle
            bridge._publish_log(f"🎙 [{tag}] 开始识别+翻译 (目标 {target})...")
            res = process_video_subtitle(
                video_id=video_id, video_path=str(video), target_lang=target,
                language=arch.get("language"), category=arch.get("category"),
                channel=arch.get("channel"),
            )
            if res.success:
                bridge._publish_log(f"✅ [{tag}] 完成: {res.subtitle_path}")
            else:
                bridge._publish_log(f"❌ [{tag}] 失败: {res.error_message}")
        except Exception as e:
            logger.exception("[MQTT] recognize_start 异常")
            bridge._publish_log(f"❌ [{tag}] 识别异常: {e}")
        finally:
            bridge._subtask_lock.release()

    from utils.thread_spawn import spawn
    spawn(target=_worker, daemon=True).start()
    bridge._publish_log(f"🎙 MQTT 触发识别+翻译: {video.name}")
    return {"ok": True, "msg": "识别+翻译已启动", "video": video.name}


def _handler_copy_generate(bridge: MqttBridge, params: dict) -> dict:
    """异步生成文案 (GUI ④ 页远程版): SRT → AIWriter → output/copy/*.txt"""
    srt = _resolve_media_path(str(params.get("srt", "")))
    ct_name = str(params.get("content_type", "XIAOHONGSHU_ORAL")).upper()
    language = str(params.get("language", "en"))

    from core.ai_writer import AIWriter, ContentType
    try:
        ct = ContentType[ct_name]
    except KeyError:
        valid = [m.name for m in ContentType]
        raise ValueError(f"未知文案类型: {ct_name} (可选: {', '.join(valid)})")

    from utils.srt_parser import parse_subtitle_file
    subs = parse_subtitle_file(str(srt))
    if not subs:
        raise ValueError(f"SRT 解析为空: {srt.name}")

    def _worker() -> None:
        try:
            bridge._publish_log(f"✍️ [{ct_name}] 开始生成文案 ({len(subs)} 句)...")
            text = AIWriter().generate_content(subs, ct, language=language)
            from utils.path_helper import get_output_dir
            out_dir = get_output_dir() / "copy"
            out_dir.mkdir(parents=True, exist_ok=True)
            out = out_dir / f"copy_{srt.stem[:40]}_{int(time.time())}.txt"
            out.write_text(text, encoding="utf-8")
            bridge._copy_latest_path = str(out)
            bridge._publish_log(f"✅ 文案已生成: {out.name}")
            bridge._publish_log(f"📄 {text[:400]}")
        except Exception as e:
            logger.exception("[MQTT] copy_generate 异常")
            bridge._publish_log(f"❌ 文案生成失败: {e}")

    from utils.thread_spawn import spawn
    spawn(target=_worker, daemon=True).start()
    return {"ok": True, "msg": "文案生成已启动 (完成后在日志通知, 用 copy_latest 拉取)"}


def _handler_copy_latest(bridge: MqttBridge, params: dict) -> dict:
    """拉取最近一次生成的文案全文"""
    p = bridge._copy_latest_path
    if p and Path(p).exists():
        return {"text": Path(p).read_text(encoding="utf-8"), "file": Path(p).name}
    from utils.path_helper import get_output_dir
    d = get_output_dir() / "copy"
    files = sorted(d.glob("*.txt"), key=lambda x: x.stat().st_mtime, reverse=True) if d.exists() else []
    if not files:
        return {"text": "", "file": ""}
    return {"text": files[0].read_text(encoding="utf-8"), "file": files[0].name}


def _handler_queue_clear(bridge: MqttBridge, params: dict) -> dict:
    """清空待发布队列 (GUI ⑤ 页远程版)"""
    from core.publish.publish_queue import get_publish_queue
    n = get_publish_queue().clear()
    bridge._publish_log(f"🗑 MQTT 清空待发布 {n} 条")
    return {"ok": True, "cleared": n}


def _handler_queue_cancel(bridge: MqttBridge, params: dict) -> dict:
    """取消单个待发布任务"""
    job_id = str(params.get("job_id", ""))
    if not job_id:
        raise ValueError("缺少 job_id")
    from core.publish.publish_queue import get_publish_queue
    ok = get_publish_queue().cancel_job(job_id)
    return {"ok": bool(ok), "job_id": job_id}


def _handler_publish_records(bridge: MqttBridge, params: dict) -> dict:
    """查看发布记录 (GUI ⑤ 页发布记录远程版)"""
    from core.publish import storage as pub_storage
    limit = min(int(params.get("limit", 20)), 100)
    records = pub_storage.list_publish_records(limit=limit)
    return {"records": records[:limit], "count": len(records[:limit])}


def _handler_pool_list(bridge: MqttBridge, params: dict) -> dict:
    """列出视频候选池 (手机发布页选取成品视频用)

    params:
      scope: "recent" (近 72h, 默认) | "all"
      hours: recent 模式的小时窗 (默认 72)
      limit: 最多返回条数 (默认 50, 上限 100)
    """
    from core.publish.pool import VideoPool
    scope = str(params.get("scope", "recent"))
    if scope == "all":
        items = VideoPool.list_all()
    else:
        items = VideoPool.list_recent(hours=int(params.get("hours", 72)))
    limit = min(int(params.get("limit", 50)), 100)
    out = []
    for it in items[:limit]:
        final_path = it.get("final_video_path", "") or ""
        out.append({
            "pool_id": it.get("id"),
            "title": it.get("title_translated") or it.get("title_original")
                     or os.path.basename(final_path),
            "video_name": os.path.basename(final_path),
            "has_cover": bool(it.get("cover_path") and os.path.exists(it["cover_path"])),
            "publish_status": it.get("publish_status", 0) or 0,
            "channel": it.get("channel_name", "") or "",
            "duration_sec": int(it.get("duration_sec", 0) or 0),
            "created": time.strftime("%m-%d %H:%M", time.localtime(it["create_ts"]))
                       if it.get("create_ts") else "",
        })
    return {"items": out, "total": len(items)}


def _handler_pool_file(bridge: MqttBridge, params: dict) -> dict:
    """把候选池里的成品视频 / 封面转成可直接下载的 HTTP 地址

    params:
      pool_id: video_pool.id
      kind:    "video"（默认）| "cover"

    返回的 url 是**局域网**地址（手机浏览器打开即下载），
    因此手机必须与电脑在同一 WiFi；走公网/流量时无法下载。
    """
    from core.publish.pool import VideoPool

    try:
        pool_id = int(params.get("pool_id") or 0)
    except Exception:
        return {"ok": False, "error": "pool_id 无效"}

    kind = str(params.get("kind") or "video")
    if kind not in ("video", "cover"):
        return {"ok": False, "error": f"kind 只能是 video / cover，收到: {kind}"}
    if not pool_id:
        return {"ok": False, "error": "缺少 pool_id"}

    item = VideoPool.get(pool_id)
    if not item:
        return {"ok": False, "error": f"候选池条目不存在: pool_id={pool_id}"}

    path = (item.get("cover_path") if kind == "cover" else item.get("final_video_path")) or ""
    if not path or not os.path.exists(path):
        return {"ok": False, "error": "文件不存在（可能已被移动或删除）"}

    try:
        size_mb = round(os.path.getsize(path) / 1024 / 1024, 1)
    except OSError:
        size_mb = 0

    key = os.environ.get("VC_WEB_API_KEY", "")
    url = f"http://{_lan_ip()}:{WEB_PORT}/api/pool/{pool_id}/file?kind={kind}"
    if key:
        url += f"&key={quote(key)}"

    return {
        "ok": True,
        "url": url,
        "name": os.path.basename(path),
        "size_mb": size_mb,
        "kind": kind,
        "lan_only": True,
        "hint": "手机需与电脑同一 WiFi；用流量/公网模式无法下载",
    }


# ---------------------------------------------------------------------------
# 指令注册表 (白名单 — 只有注册的 action 才允许执行)
# ---------------------------------------------------------------------------
# ★ 函数定义必须在字典之前 —— Python 模块从上到下顺序执行
ACTION_HANDLERS: dict[str, ActionHandler] = {
    "ping": _handler_ping,
    "status": _handler_status,
    "logs": _handler_logs,
    "pipeline_single": _handler_pipeline_single,
    "pipeline_search": _handler_pipeline_search,
    "stop": _handler_stop,
    "queue_snapshot": _handler_queue_snapshot,
    "queue_enqueue": _handler_queue_enqueue,
    "queue_clear": _handler_queue_clear,
    "queue_cancel": _handler_queue_cancel,
    "publish_records": _handler_publish_records,
    "pool_list": _handler_pool_list,
    "pool_file": _handler_pool_file,
    "videos": _handler_videos,
    "accounts": _handler_accounts,
    "subtitle_style_get": _handler_subtitle_style_get,
    "subtitle_style_set": _handler_subtitle_style_set,
    "subtitle_render": _handler_subtitle_render,
    "recognize_start": _handler_recognize_start,
    "copy_generate": _handler_copy_generate,
    "copy_latest": _handler_copy_latest,
    "dump_stacks": _handler_dump_stacks,
}


# ===========================================================================
# 便捷入口
# ===========================================================================

def start_mqtt(web_ui_url: str = "") -> MqttBridge:
    bridge = MqttBridge.instance(web_ui_url=web_ui_url)
    bridge.start()
    return bridge


def get_bridge() -> Optional[MqttBridge]:
    return MqttBridge._instance
