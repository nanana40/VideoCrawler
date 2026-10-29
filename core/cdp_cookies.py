"""通过 Edge/Chrome DevTools Protocol (CDP) 实时获取浏览器 cookies。

绕过 v20 加密和 SQLite 文件锁——直接用浏览器自己的 HTTP-only 通道拿 cookies。

使用前提: 浏览器必须以 ``--remote-debugging-port=9222`` 参数启动。
"""
from __future__ import annotations

import base64
import http.client
import json
import os
import socket
import struct
import threading
from typing import List, Optional, Tuple
from urllib.parse import urlparse

from loguru import logger

# 串行化 CDP cookies 文件的写入：多线程并行下载时不允许并发覆写同一文件（AUDIT-0021）
_cookies_file_lock = threading.Lock()


def _websocket_key() -> str:
    import random, string, base64
    raw = "".join(random.choices(string.ascii_letters + string.digits, k=16)).encode()
    return base64.b64encode(raw).decode()


class _FrameReader:
    """最小化的 WebSocket frame reader（同步）。"""

    def __init__(self, sock: socket.socket):
        self._sock = sock
        self._buf = b""

    def _read_exact(self, n: int) -> bytes:
        while len(self._buf) < n:
            chunk = self._sock.recv(65536)
            if not chunk:
                raise ConnectionError("WebSocket closed")
            self._buf += chunk
        result = self._buf[:n]
        self._buf = self._buf[n:]
        return result

    def read_text_frame(self) -> str:
        # Header
        h = self._read_exact(2)
        opcode = h[0] & 0x0F
        masked = h[1] & 0x80
        payload_len = h[1] & 0x7F

        if opcode == 0x8:
            raise ConnectionError("WebSocket close frame received")

        if payload_len == 126:
            payload_len = struct.unpack(">H", self._read_exact(2))[0]
        elif payload_len == 127:
            payload_len = struct.unpack(">Q", self._read_exact(8))[0]

        if masked:
            mask = self._read_exact(4)
            data = self._read_exact(payload_len)
            data = bytes(b ^ mask[i % 4] for i, b in enumerate(data))
        else:
            data = self._read_exact(payload_len)

        return data.decode("utf-8", errors="replace")


def _connect_websocket(host: str, port: int, path: str) -> socket.socket:
    sock = socket.create_connection((host, port), timeout=5)
    try:
        key = _websocket_key()
        req = (
            f"GET {path} HTTP/1.1\r\n"
            f"Host: {host}:{port}\r\n"
            f"Upgrade: websocket\r\n"
            f"Connection: Upgrade\r\n"
            f"Sec-WebSocket-Key: {key}\r\n"
            f"Sec-WebSocket-Version: 13\r\n"
            f"\r\n"
        )
        sock.sendall(req.encode())

        resp = b""
        while b"\r\n\r\n" not in resp:
            chunk = sock.recv(4096)
            if not chunk:
                raise ConnectionError("Handshake failed")
            resp += chunk

        if b"101" not in resp.split(b"\r\n")[0]:
            raise ConnectionError(f"Bad WS response: {resp[:200]}")
    except Exception:
        # 握手失败时必须关闭刚创建的 socket，避免 TCP 句柄泄漏（AUDIT-0043）
        try:
            sock.close()
        except Exception:
            pass
        raise

    return sock


def _ws_send_text(sock: socket.socket, text: str) -> None:
    data = text.encode("utf-8")
    n = len(data)

    frame = bytearray()
    frame.append(0x81)  # FIN + text opcode

    if n < 126:
        frame.append(0x80 | n)
    elif n < 65536:
        frame.append(0x80 | 126)
        frame.extend(struct.pack(">H", n))
    else:
        frame.append(0x80 | 127)
        frame.extend(struct.pack(">Q", n))

    mask = os.urandom(4)
    frame.extend(mask)
    masked = bytes(b ^ mask[i % 4] for i, b in enumerate(data))
    frame.extend(masked)

    sock.sendall(frame)


def is_cdp_port_open(port: int = 9222) -> bool:
    """快速检查 CDP 端口是否可达。"""
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=1) as s:
            return True
    except OSError:
        return False


def _get_page_ws_url(port: int, prefer_domain: str = "") -> Optional[str]:
    """从 /json/list 拿 Page target 的 WebSocket URL。

    如果给了 prefer_domain (如 "xiaohongshu.com")，优先选 URL 包含该域名的 page。
    """
    try:
        conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
        try:
            conn.request("GET", "/json/list")
            resp = conn.getresponse()
            if resp.status != 200:
                return None
            targets = json.loads(resp.read())
        finally:
            conn.close()  # AUDIT-0068: 任何分支都确保关闭连接
    except Exception as e:
        logger.debug(f"CDP /json/list 失败: {e}")
        return None

    # 优先选符合 prefer_domain 的 page
    pages = [t for t in targets if t.get("type") == "page"]
    if prefer_domain:
        for p in pages:
            if prefer_domain in p.get("url", "") and p.get("webSocketDebuggerUrl"):
                return p["webSocketDebuggerUrl"]

    # fallback: 第一个 page target
    if pages and pages[0].get("webSocketDebuggerUrl"):
        return pages[0]["webSocketDebuggerUrl"]

    return None


def fetch_cdp_cookies(port: int = 9222, prefer_domain: str = "") -> Optional[List[dict]]:
    """通过 CDP ``Network.getAllCookies`` 获取浏览器 cookies。

    必须连 Page target（Browser target 没有 Network 域）。
    prefer_domain: 优先选 URL 包含此域名的 page target。
    返回 CDP cookie dict 列表；失败返回 None。
    """
    ws_url = _get_page_ws_url(port, prefer_domain)
    if not ws_url:
        logger.debug("CDP 没找到 Page target")
        return None

    try:
        parsed = urlparse(ws_url)
        sock = _connect_websocket(parsed.hostname, parsed.port or port, parsed.path)
    except Exception as e:
        logger.debug(f"CDP WebSocket 连接失败: {e}")
        return None

    reader = _FrameReader(sock)

    try:
        _ws_send_text(sock, json.dumps({"id": 1, "method": "Network.getAllCookies"}))
        raw = reader.read_text_frame()
        result = json.loads(raw)
        if result.get("id") != 1:
            return None
        cookies = result.get("result", {}).get("cookies", [])
        logger.info(f"CDP 获取到 {len(cookies)} 条 cookies")
        return cookies
    except Exception as e:
        logger.debug(f"CDP getAllCookies 失败: {e}")
        return None
    finally:
        try:
            sock.close()
        except Exception:
            pass


def save_cdp_cookies_to_netscape(cookies: List[dict], out_path: str) -> int:
    """把 CDP cookies 转成 Netscape (Mozilla) 格式文件，返回写入条数。

    yt-dlp ``cookies`` 参数直接支持这个格式。

    线程安全 + 原子替换：先写 ``.tmp`` 再 ``os.replace``，避免并发覆写时
    其他线程读到半截文件。（AUDIT-0021）
    """
    import tempfile

    with _cookies_file_lock:
        os.makedirs(os.path.dirname(out_path), exist_ok=True)
        tmp_path = out_path + ".tmp"

        with open(tmp_path, "w", encoding="utf-8") as f:
            f.write("# Netscape HTTP Cookie File\n")
            f.write("# This is a generated file!  Do not edit.\n")
            f.write("#\n")
            count = 0
            for c in cookies:
                domain = c.get("domain", "")
                if not domain:
                    continue
                include_subdomains = "TRUE" if domain.startswith(".") else "FALSE"
                path = c.get("path", "/")
                secure = "TRUE" if c.get("secure", False) else "FALSE"
                expires = int(c.get("expires", 0)) if c.get("expires") else 0
                name = c.get("name", "")
                value = c.get("value", "")
                if not name:
                    continue
                f.write(
                    f"{domain}\t{include_subdomains}\t{path}\t{secure}\t"
                    f"{expires}\t{name}\t{value}\n"
                )
                count += 1

        os.replace(tmp_path, out_path)

    logger.info(f"CDP cookies → Netscape 文件: {out_path} ({count} 条)")
    return count


def extract_cookies_for_domain(domain: str, port: int = 9222, browser: str = "edge") -> str:
    """从 CDP 拉 cookies，按域名过滤后拼成 Cookie header 字符串。
    返回形如 SESSDATA=xxx; bili_jct=yyy 的字符串，失败返回空串。
    """
    if not is_cdp_port_open(port):
        logger.warning("[CDP] port {0} not open — start browser with --remote-debugging-port".format(port))
        return ""
    all_cookies = fetch_cdp_cookies(port, prefer_domain=domain.lstrip("."))
    if not all_cookies:
        return ""
    # match domain: .bilibili.com matches .bilibili.com / api.bilibili.com etc.
    domain = domain.lstrip(".")
    matched = [c for c in all_cookies if domain in c.get("domain", "")]
    if not matched:
        logger.warning("[CDP] no cookies match {0}".format(domain))
        return ""
    parts = [c["name"] + "=" + c["value"] for c in matched if c.get("name") and c.get("value")]
    result = "; ".join(parts)
    logger.info(f"[CDP] extracted {len(parts)} cookies for {domain}")
    return result


def auto_refresh_cookies(port: int = 9222, out_path: Optional[str] = None) -> bool:
    """一步到位: CDP 拉 cookies → 存 Netscape 文件。

    ``out_path`` 默认用 :func:`utils.path_helper.get_cookies_file_path`.
    """
    if out_path is None:
        from utils.path_helper import get_cookies_file_path
        out_path = str(get_cookies_file_path())

    if not is_cdp_port_open(port):
        logger.debug(f"CDP 端口 {port} 未开放")
        return False

    cookies = fetch_cdp_cookies(port)
    if not cookies:
        return False

    n = save_cdp_cookies_to_netscape(cookies, out_path)
    return n > 0

