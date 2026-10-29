"""
gui.web_host — 把 FastAPI 后端嵌到 PySide6 GUI 进程里跑.

启动时机:  MainWindow 构造完成后 start_all()
停止时机:  MainWindow.closeEvent → stop_all() + atexit 兜底

保证:
  ✅ 每次关闭 GUI, uvicorn + MQTT bridge 一定被杀干净 (端口释放)
  ✅ 每次打开 GUI, 自动清残留 → 自动启动, 端口不再撞
  ✅ 非管理员权限也能杀 (不用 PowerShell Get-NetTCPConnection)
  ✅ 崩溃/任务管理器结束也能下次自动恢复

后台线程:
  ① uvicorn  (daemon, 默认监听 127.0.0.1:8000)
  ② MQTT bridge 由 FastAPI lifespan 管理 (start/shutdown)
"""
from __future__ import annotations

import atexit
import json
import os
import re
import secrets
import signal
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Any, Optional

from loguru import logger

# 默认 key — 可以被环境变量覆盖, 和 web/main.py 保持一致
# AUDIT-0058: 未配置时不再回落弱默认 key, 改为随机生成 (本地用户从日志获取)
def _resolve_api_key() -> str:
    key = os.environ.get("VC_WEB_API_KEY")
    if key:
        return key
    key = secrets.token_urlsafe(24)
    logger.info(f"🌐 [WebHost] 未配置 VC_WEB_API_KEY, 已生成随机 API key: {key}")
    return key


DEFAULT_API_KEY = _resolve_api_key()

# PID 文件路径 (用户数据目录 data/web_host.pid)
def _pid_file() -> Path:
    from utils.path_helper import get_data_dir

    return get_data_dir() / "web_host.pid"


# ---------------------------------------------------------------------------
# 底层工具: 进程 & 端口
# ---------------------------------------------------------------------------

def _is_pid_alive(pid: int) -> bool:
    """跨平台: 检测 PID 是否还活着."""
    try:
        if sys.platform == "win32":
            # Windows: 用 tasklist 查
            out = subprocess.run(
                ["tasklist", "/FI", f"PID eq {pid}"],
                capture_output=True, text=True, timeout=3,
            ).stdout
            return str(pid) in out
        else:
            os.kill(pid, 0)
            return True
    except Exception:
        return False


def _kill_pid_tree(pid: int, timeout: float = 3.0) -> bool:
    """强制杀掉某个 PID 及其子进程 (进程树). 返回 True 表示成功."""
    try:
        if sys.platform == "win32":
            # /F 强制 /T 进程树
            subprocess.run(
                ["taskkill", "/F", "/T", "/PID", str(pid)],
                capture_output=True, timeout=5,
            )
        else:
            try:
                os.killpg(os.getpgid(pid), signal.SIGKILL)
            except Exception:
                os.kill(pid, signal.SIGKILL)
        # 等端口释放
        deadline = time.time() + timeout
        while time.time() < deadline and _is_pid_alive(pid):
            time.sleep(0.1)
        return not _is_pid_alive(pid)
    except Exception as e:
        logger.warning(f"杀 PID {pid} 失败: {e}")
        return False


def _port_pid(port: int) -> Optional[int]:
    """查哪个 PID 占了端口 (纯 netstat, 不用 PowerShell, 任何权限都能跑)."""
    try:
        out = subprocess.run(
            ["netstat", "-ano"],
            capture_output=True, text=True, timeout=5,
        ).stdout
        # Windows netstat 输出示例:
        #   TCP    0.0.0.0:8000       0.0.0.0:0       LISTENING       12345
        for line in out.splitlines():
            # 匹配 LISTENING 状态且端口等于目标的行
            m = re.search(rf":{port}\s+\S+\s+LISTENING\s+(\d+)", line)
            if m:
                return int(m.group(1))
    except Exception:
        pass
    return None


def _kill_all_residual_uvicorn(port: int) -> None:
    """激进清理: 先查 PID 文件 → 再查 netstat → 全杀."""
    killed = set()

    # 1. PID 文件
    pf = _pid_file()
    if pf.exists():
        try:
            data = json.loads(pf.read_text(encoding="utf-8"))
            pid = int(data.get("pid", 0))
            if pid and pid != os.getpid() and _is_pid_alive(pid):
                logger.warning(f"🌐 [WebHost] 发现残留 PID 文件, 清理 PID {pid}")
                _kill_pid_tree(pid)
                killed.add(pid)
        except Exception:
            pass
        try:
            pf.unlink()
        except Exception:
            pass

    # 2. netstat 查端口 (兜底: 不管是谁占的, 都杀)
    pid = _port_pid(port)
    if pid and pid != os.getpid() and pid not in killed:
        logger.warning(f"🌐 [WebHost] 端口 {port} 被 PID {pid} 占用, 强制清理")
        _kill_pid_tree(pid)
        killed.add(pid)

    # 3. 等端口真的空了
    deadline = time.time() + 5.0
    while time.time() < deadline:
        pid = _port_pid(port)
        if pid is None:
            break
        if pid != os.getpid():
            _kill_pid_tree(pid)
        time.sleep(0.3)


# ---------------------------------------------------------------------------
# GuiWebHost
# ---------------------------------------------------------------------------

class GuiWebHost:
    """在 GUI 进程里托管 uvicorn + MQTT bridge (后者由 FastAPI lifespan 管理)."""

    _instance: Optional["GuiWebHost"] = None
    _instance_lock = threading.Lock()

    def __init__(self, host: Optional[str] = None, port: int = 8000):
        # AUDIT-0058: 默认只绑回环地址; 显式传入 host 或设置 VC_WEB_HOST 才对外监听
        self.host = host or os.environ.get("VC_WEB_HOST") or "127.0.0.1"
        self.port = port
        self.api_key = DEFAULT_API_KEY

        self._uvicorn_thread: Optional[threading.Thread] = None
        self._uvicorn_server = None  # uvicorn.Server 实例
        self._started = False
        self._my_pid = os.getpid()

        # ── 自愈 watchdog 状态 (进程层保活: 程序开着服务就不断) ──
        self._watchdog_thread: Optional[threading.Thread] = None
        self._watchdog_stop = threading.Event()
        self._last_uvicorn_ok = 0.0   # 上次 uvicorn 健康时刻
        self._last_bridge_ok = 0.0    # 上次 MQTT 在线时刻

        # 注册 atexit 兜底 (只有第一个实例注册一次)
        with GuiWebHost._instance_lock:
            if GuiWebHost._instance is None:
                GuiWebHost._instance = self
                atexit.register(self.stop_all)
                self._register_signal_handlers()

    def _register_signal_handlers(self) -> None:
        """注册信号处理器 (Unix). Windows 下 signal 不太可靠, atexit 是主力."""
        if sys.platform == "win32":
            return
        try:
            for sig in (signal.SIGTERM, signal.SIGINT):
                signal.signal(sig, lambda *_: self.stop_all())
        except Exception:
            pass

    # ------------------------------------------------------------------
    # 生命周期
    # ------------------------------------------------------------------

    def start_uvicorn(self) -> None:
        """启动 uvicorn (非阻塞, 后台线程). 失败会 raise."""
        if self._started:
            return
        os.environ.setdefault("VC_WEB_API_KEY", self.api_key)

        # ── 步骤 1: 激进清理任何残留 ──
        _kill_all_residual_uvicorn(self.port)

        # ── 步骤 2: 写 PID 文件 (供下次启动/崩溃时清理) ──
        try:
            pf = _pid_file()
            pf.write_text(json.dumps({"pid": self._my_pid, "port": self.port,
                                      "started_at": time.time()}), encoding="utf-8")
        except Exception as e:
            logger.warning(f"🌐 [WebHost] 写 PID 文件失败 (不影响启动): {e}")

        # ── 步骤 3: 后台线程启动 uvicorn ──
        def _run():
            import uvicorn
            from web.main import app

            logger.info(f"🌐 [WebHost] 启动 uvicorn 监听 {self.host}:{self.port}")
            config = uvicorn.Config(
                app,
                host=self.host,
                port=self.port,
                log_level="warning",
                access_log=False,
            )
            self._uvicorn_server = uvicorn.Server(config)
            try:
                self._uvicorn_server.run()
            except Exception as e:
                logger.error(f"🌐 [WebHost] uvicorn 启动异常: {e}")
            finally:
                self._started = False

        self._uvicorn_thread = threading.Thread(target=_run, name="uvicorn-gui", daemon=True)
        self._uvicorn_thread.start()
        self._started = True

        # ── 步骤 4: 健康检查 (严格, 超时 raise) ──
        ready = False
        for _ in range(50):  # 最多 ~10s
            time.sleep(0.2)
            # 先确认线程还活着 (防止刚启动就崩)
            if not self._uvicorn_thread.is_alive():
                self._started = False
                raise RuntimeError("uvicorn 线程启动后立即退出 (端口可能仍被占用)")
            try:
                import urllib.request
                urllib.request.urlopen(
                    f"http://127.0.0.1:{self.port}/api/health?key={self.api_key}",
                    timeout=0.8,
                )
                ready = True
                break
            except Exception:
                continue

        if not ready:
            self._started = False
            # 超了也不等了, 检查一下是不是自己线程已经挂了
            if not self._uvicorn_thread.is_alive():
                raise RuntimeError("uvicorn 启动超时且线程已退出 (可能端口冲突)")
            # 还活着但 health 不通, 多半是 FastAPI lifespan 里有东西卡住了
            raise RuntimeError("uvicorn 启动超时: 端口已监听但 /api/health 不响应")

        logger.info(f"🌐 [WebHost] uvicorn 就绪 → http://localhost:{self.port}/?key={self.api_key}")

    def stop_uvicorn(self) -> None:
        """优雅停止 uvicorn + MQTT bridge, 确保端口释放."""
        # 本实例从未启动过 uvicorn: 直接返回, 绝不清理端口
        # (否则 atexit 兜底会把别人占用的同端口进程误当残留杀掉)
        if not self._started and self._uvicorn_thread is None and self._uvicorn_server is None:
            return

        # ── 步骤 1: 触发 FastAPI lifespan shutdown (bridge.stop() 在这里面) ──
        if self._uvicorn_server is not None:
            try:
                self._uvicorn_server.should_exit = True
            except Exception:
                pass

        # ── 步骤 2: 等线程结束 (最多 5s) ──
        if self._uvicorn_thread is not None and self._uvicorn_thread.is_alive():
            self._uvicorn_thread.join(timeout=5.0)

        # ── 步骤 3: 超时强制清理 (不管了, 直接杀) ──
        if self._uvicorn_thread is not None and self._uvicorn_thread.is_alive():
            logger.warning("🌐 [WebHost] uvicorn 优雅退出超时, 强制杀进程树")
            _kill_all_residual_uvicorn(self.port)

        self._uvicorn_server = None
        self._uvicorn_thread = None
        self._started = False

        # ── 步骤 4: 删 PID 文件 ──
        try:
            pf = _pid_file()
            if pf.exists():
                pf.unlink()
        except Exception:
            pass

        # ── 步骤 5: 最终确认端口释放 ──
        for _ in range(10):  # ~2s
            if _port_pid(self.port) is None:
                break
            time.sleep(0.2)
        else:
            pid = _port_pid(self.port)
            if pid:
                logger.warning(f"🌐 [WebHost] 端口 {self.port} 最终仍被 PID {pid} 占用, 强制清理")
                _kill_pid_tree(pid)

        logger.info("🌐 [WebHost] uvicorn + MQTT bridge 已全部停止, 端口已释放")

    # ------------------------------------------------------------------
    # 总控
    # ------------------------------------------------------------------

    def start_all(self, **kwargs) -> dict:
        try:
            self.start_uvicorn()
        except Exception as e:
            logger.error(f"🌐 [WebHost] 启动失败: {e}")
            return {
                "lan": f"http://localhost:{self.port}/?key={self.api_key}",
                "api_key": self.api_key,
                "mqtt": {"ok": False, "msg": str(e)},
                "error": str(e),
            }
        # 启动成功 → 重置健康计时并拉起自愈 watchdog (30s 一次体检)
        self._last_uvicorn_ok = time.time()
        self._last_bridge_ok = time.time()
        self._start_watchdog()
        mqtt_info = self._peek_mqtt_info()
        return {
            "lan": f"http://localhost:{self.port}/?key={self.api_key}",
            "api_key": self.api_key,
            "mqtt": mqtt_info,
        }

    def stop_all(self) -> None:
        """总停止入口 — 会被 closeEvent 和 atexit 共同调用, 幂等."""
        # 先停 watchdog, 避免关闭过程中被自愈逻辑再次拉起
        self._watchdog_stop.set()
        try:
            self.stop_uvicorn()
        except Exception as e:
            logger.warning(f"🌐 [WebHost] stop_all 异常 (不影响退出): {e}")

    # ------------------------------------------------------------------
    # 远程联动就绪保障 (一键启动按钮调用)
    # ------------------------------------------------------------------
    def ensure_remote_service(self) -> dict:
        """确保远程联动就绪: 手机可达 (LAN 监听) + MQTT bridge 在线.

        Returns:
            {"lan_ok": bool, "bridge_ok": bool, "actions": [实际执行的调整动作...]}
        """
        actions: list[str] = []

        # ① LAN 可达: 未显式配置监听地址时切到 0.0.0.0 (默认 127.0.0.1 手机打不开)
        if not os.environ.get("VC_WEB_HOST") and self.host not in ("0.0.0.0", "::"):
            self.host = "0.0.0.0"
            actions.append(f"监听切换为 0.0.0.0:{self.port} (手机局域网可达)")
            try:
                self.stop_uvicorn()
                self.start_uvicorn()
                self._last_uvicorn_ok = time.time()
            except Exception as e:
                logger.warning(f"🌐 [WebHost] 切换 0.0.0.0 重启失败: {e}")
                actions.append(f"切换监听失败: {e}")

        # ② MQTT bridge 在线 (未启动则重启 uvicorn 重新走 lifespan 注入依赖)
        bridge_ok = False
        try:
            from web.mqtt_bridge import get_bridge
            bridge = get_bridge()
            if bridge is None:
                try:
                    self.stop_uvicorn()
                    self.start_uvicorn()
                    self._last_uvicorn_ok = time.time()
                    actions.append("重启 uvicorn 以拉起 MQTT bridge")
                    bridge = get_bridge()
                except Exception as e:
                    actions.append(f"拉起 bridge 失败: {e}")
            if bridge is not None:
                if not bridge._connected:
                    # lifespan 已在后台异步发起连接, 先等几秒就绪;
                    # 立刻 restart 会和进行中的连接撞车 (同 client_id 双连,
                    # EMQX 稍后踢掉旧连接, 表现为一次多余的"已断开/重连")
                    if self._wait_bridge_connected(bridge, 5.0):
                        actions.append("MQTT bridge 已连接 (等待后就绪)")
                    else:
                        bridge.restart()
                        actions.append("MQTT bridge 执行了一次强制重连")
                        self._wait_bridge_connected(bridge, 10.0)
                bridge_ok = bool(bridge._connected)
        except Exception as e:
            actions.append(f"bridge 状态检查失败: {e}")

        # 说明: 公网控制链路由 MQTT (broker.emqx.io 出站连接) 承担, 无需隧道;
        #       公网模式只差 mobile.html 的固定静态托管地址 ——
        #       部署后设置环境变量 VC_MQTT_WEB_URL (或写入 data/mqtt_web_url.txt) 即生效

        return {"lan_ok": bool(self._started), "bridge_ok": bridge_ok, "actions": actions}

    @staticmethod
    def _wait_bridge_connected(bridge: Any, timeout: float) -> bool:
        """轮询等待 MQTT bridge 建立连接 (连接是异步回调, 必须等待后再判断)"""
        deadline = time.time() + timeout
        while time.time() < deadline:
            if bridge._connected:
                return True
            time.sleep(0.3)
        return bool(bridge._connected)

    # ------------------------------------------------------------------
    # 进程层保活 watchdog (30s 体检, 异常自愈)
    # ------------------------------------------------------------------
    _WATCHDOG_INTERVAL = 30       # 体检间隔 (秒)
    _UVICORN_DEAD_AFTER = 60      # uvicorn 失联超过该秒数才重启
    _BRIDGE_DEAD_AFTER = 90       # MQTT 断连超过该秒数才强制重连 (平时交给 paho 自动重连)

    def _start_watchdog(self) -> None:
        """启动 watchdog 守护线程 (幂等)"""
        if self._watchdog_thread is not None and self._watchdog_thread.is_alive():
            return
        self._watchdog_stop.clear()
        self._last_uvicorn_ok = time.time()
        self._last_bridge_ok = time.time()
        self._watchdog_thread = threading.Thread(
            target=self._watchdog_loop, name="web-watchdog", daemon=True,
        )
        self._watchdog_thread.start()
        logger.info(f"🌐 [WebHost] 保活 watchdog 已启动 (每 {self._WATCHDOG_INTERVAL}s 体检)")

    def _watchdog_loop(self) -> None:
        """循环体检直到 stop_all"""
        while not self._watchdog_stop.wait(self._WATCHDOG_INTERVAL):
            try:
                self._watchdog_tick()
            except Exception as e:
                logger.warning(f"🌐 [WebHost] watchdog 体检异常 (下轮继续): {e}")

    def _watchdog_tick(self) -> None:
        """单次体检: uvicorn 健康 + MQTT 在线, 失联超时自动自愈"""
        now = time.time()

        # ① uvicorn: 线程存活 + health 接口可达
        uvicorn_ok = bool(self._started and self._uvicorn_thread
                          and self._uvicorn_thread.is_alive())
        if uvicorn_ok:
            try:
                import urllib.request
                urllib.request.urlopen(
                    f"http://127.0.0.1:{self.port}/api/health?key={self.api_key}",
                    timeout=3,
                )
            except Exception:
                uvicorn_ok = False
        if uvicorn_ok:
            self._last_uvicorn_ok = now
        elif now - self._last_uvicorn_ok > self._UVICORN_DEAD_AFTER:
            logger.warning("🌐 [WebHost] watchdog: uvicorn 失联超时, 自动重启")
            try:
                self.stop_uvicorn()
                self.start_uvicorn()
                self._last_uvicorn_ok = time.time()
                logger.info("🌐 [WebHost] watchdog: uvicorn 重启成功")
            except Exception as e:
                logger.error(f"🌐 [WebHost] watchdog: uvicorn 重启失败: {e}")

        # ② MQTT bridge: 在线记录健康; 断连超时才强制重连
        try:
            from web.mqtt_bridge import get_bridge
            bridge = get_bridge()
        except Exception:
            bridge = None
        if bridge is None:
            return
        if bridge._connected:
            self._last_bridge_ok = now
        elif now - self._last_bridge_ok > self._BRIDGE_DEAD_AFTER:
            logger.warning("🌐 [WebHost] watchdog: MQTT 断连超时, 强制重连")
            try:
                bridge.restart()
                if bridge._connected:
                    self._last_bridge_ok = time.time()
                    logger.info("🌐 [WebHost] watchdog: MQTT 重连成功")
            except Exception as e:
                logger.error(f"🌐 [WebHost] watchdog: MQTT 重连失败: {e}")

    # ------------------------------------------------------------------
    # 读 MQTT bridge 状态 (只读)
    # ------------------------------------------------------------------
    def _peek_mqtt_info(self, timeout: float = 3.0) -> dict:
        try:
            from web.mqtt_bridge import MqttBridge
        except Exception as e:
            return {"ok": False, "msg": f"mqtt_bridge 不可用: {e}"}
        bridge = MqttBridge._instance
        start = time.time()
        while bridge is None and time.time() - start < timeout:
            time.sleep(0.2)
            bridge = MqttBridge._instance
        if bridge is None:
            return {"ok": False, "msg": "bridge 未启动"}
        return {
            "ok": True,
            "connected": bridge._connected,
            "device_id": bridge.device_id,
            "token": bridge.token,
            "broker": "broker.emqx.io",
            "tcp_port": 1883,
            "ws_port": 8084,
            "topic_cmd": bridge.topic_cmd,
            "topic_log": bridge.topic_log,
            "web_ui_url": bridge.web_ui_url,
            "qr_url": bridge.get_qr_url(),
        }


# 单例 — MainWindow 拿这同一个实例
_host_instance: Optional[GuiWebHost] = None


def get_host() -> GuiWebHost:
    global _host_instance
    if _host_instance is None:
        _host_instance = GuiWebHost()
    return _host_instance
