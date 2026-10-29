"""
publish_open_oauth.py — B站 / 抖音 开放平台 OAuth 授权helper

用途：
  在电脑上跑一次，浏览器点「同意授权」，脚本拿到 code 换 access_token，
  最后打印一段 JSON —— 复制粘贴到 GUI「发布」页的账号 Cookie 输入框即可。

用法：
  # B站（需先在开放平台控制台配置回调地址，且与 --redirect-uri 一致）
  d:\\python\\python.exe scripts\\publish_open_oauth.py --platform bilibili \\
      --client-id <客户端ID> --client-secret <客户端密钥>

  # 抖音
  d:\\python\\python.exe scripts\\publish_open_oauth.py --platform douyin \\
      --client-key <Client Key> --client-secret <Client Secret>

  # 只想看授权链接（比如浏览器在另一台机器/手机上打开）
  ... --print-url

注意：
  回调地址必须是开放平台控制台里登记过的。本地默认 http://127.0.0.1:8765/callback
  （抖音允许 localhost 回调；B站若不允许 http 本地回调，请登记后再跑）
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import threading
import time
import urllib.parse
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer

import requests

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.publish.open_api_clients import AUTH_MODE_OPEN_API  # noqa: E402

BILI_AUTHORIZE = "https://account.bilibili.com/account/oauth2/authorize"
BILI_TOKEN = "https://api.bilibili.com/x/account-oauth2/v1/token"
DOUYIN_AUTHORIZE = "https://open.douyin.com/platform/oauth/connect/"
DOUYIN_TOKEN = "https://open.douyin.com/oauth/access_token/"
DOUYIN_SCOPE = "video.create.bind"

_RESULT: dict = {"code": "", "error": ""}


class _CallbackHandler(BaseHTTPRequestHandler):
    def do_GET(self):  # noqa: N802
        parsed = urllib.parse.urlparse(self.path)
        qs = urllib.parse.parse_qs(parsed.query)
        _RESULT["code"] = (qs.get("code") or [""])[0]
        _RESULT["error"] = (qs.get("error") or qs.get("error_description") or [""])[0]
        body = "授权已完成，可以关闭本页面回到终端。".encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *_args):
        pass


def _build_authorize_url(platform: str, client_id: str, redirect_uri: str) -> str:
    state = str(int(time.time()))
    if platform == "bilibili":
        params = {
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "state": state,
        }
        return BILI_AUTHORIZE + "?" + urllib.parse.urlencode(params)
    params = {
        "client_key": client_id,
        "response_type": "code",
        "scope": DOUYIN_SCOPE,
        "redirect_uri": redirect_uri,
        "state": state,
    }
    return DOUYIN_AUTHORIZE + "?" + urllib.parse.urlencode(params)


def _exchange_bilibili(client_id: str, client_secret: str, code: str) -> dict:
    resp = requests.post(
        BILI_TOKEN,
        data={
            "client_id": client_id,
            "client_secret": client_secret,
            "grant_type": "authorization_code",
            "code": code,
        },
        timeout=30,
    )
    data = resp.json()
    if data.get("code") != 0:
        raise SystemExit(f"换取 token 失败: {data}")
    d = data.get("data") or {}
    return {
        AUTH_MODE_OPEN_API: AUTH_MODE_OPEN_API,
        "client_id": client_id,
        "client_secret": client_secret,
        "access_token": d.get("access_token", ""),
        "refresh_token": d.get("refresh_token", ""),
        "expires_at": int(time.time()) + int(d.get("expires_in", 0) or 0),
        "mid": d.get("mid", ""),
    }


def _exchange_douyin(client_key: str, client_secret: str, code: str) -> dict:
    resp = requests.post(
        DOUYIN_TOKEN,
        json={
            "client_key": client_key,
            "client_secret": client_secret,
            "code": code,
            "grant_type": "authorization_code",
        },
        timeout=30,
    )
    data = resp.json()
    d = data.get("data") or {}
    if not d.get("access_token"):
        raise SystemExit(f"换取 token 失败: {data}")
    return {
        AUTH_MODE_OPEN_API: AUTH_MODE_OPEN_API,
        "client_key": client_key,
        "client_secret": client_secret,
        "open_id": d.get("open_id", ""),
        "access_token": d.get("access_token", ""),
        "refresh_token": d.get("refresh_token", ""),
        "expires_at": int(time.time()) + int(d.get("expires_in", 0) or 0),
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="B站/抖音开放平台 OAuth 授权")
    ap.add_argument("--platform", required=True, choices=["bilibili", "douyin"])
    ap.add_argument("--client-id", default="", help="B站 Client ID / 抖音 Client Key")
    ap.add_argument("--client-key", default="", help="抖音 Client Key（同 --client-id）")
    ap.add_argument("--client-secret", required=True)
    ap.add_argument("--redirect-uri", default="http://127.0.0.1:8765/callback")
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--print-url", action="store_true", help="只打印授权链接，不启动本地回调")
    ap.add_argument("--code", default="", help="已知 code 时直接换取 token，跳过授权")
    args = ap.parse_args()

    client_id = args.client_id or args.client_key
    if not client_id:
        raise SystemExit("缺少 --client-id（抖音可用 --client-key）")

    if args.code:
        code = args.code
    else:
        url = _build_authorize_url(args.platform, client_id, args.redirect_uri)
        print("\n授权链接:\n" + url + "\n")
        if args.print_url:
            return 0

        server = HTTPServer(("127.0.0.1", args.port), _CallbackHandler)
        th = threading.Thread(target=server.serve_forever, daemon=True)
        th.start()
        try:
            webbrowser.open(url)
        except Exception:
            pass
        print(f"等待回调 {args.redirect_uri} ...（Ctrl+C 退出）")
        try:
            for _ in range(300):
                if _RESULT["code"] or _RESULT["error"]:
                    break
                time.sleep(0.2)
        except KeyboardInterrupt:
            server.shutdown()
            return 1
        server.shutdown()

        if _RESULT["error"]:
            raise SystemExit(f"授权被拒绝: {_RESULT['error']}")
        code = _RESULT["code"]
        if not code:
            raise SystemExit("超时未收到授权回调（检查 redirect_uri 是否与控制台登记一致）")

    if args.platform == "bilibili":
        creds = _exchange_bilibili(client_id, args.client_secret, code)
    else:
        creds = _exchange_douyin(client_id, args.client_secret, code)

    print("\n✅ 授权成功。把下面整段 JSON 粘贴到 GUI「发布」页 → 添加账号 → Cookie 输入框：\n")
    print(json.dumps(creds, ensure_ascii=False))
    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
