"""
test_open_api_clients.py — B站/抖音官方开放平台客户端 离线回归

只做**不联网**的验证：
  - 凭证 JSON 解析 / 序列化
  - 工厂按 auth_mode 正确路由（cookie 客户端 vs 官方客户端）
  - B站 HMAC-SHA256 签名串构造与签名值自洽
  - 抖音文案拼装、错误码解析、token 过期判断

运行：
  d:\\python\\python.exe scripts\\test_open_api_clients.py
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import sys
from types import SimpleNamespace

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import core.publish.open_api_clients as oac  # noqa: E402
from core.publish.clients import (  # noqa: E402
    BilibiliClient, PlatformClientFactory, VideoMeta,
)
from core.publish.open_api_clients import (  # noqa: E402
    BilibiliOpenApiClient, DouyinApiError, DouyinOpenApiClient,
    dump_open_api_credentials, parse_open_api_credentials,
)

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
# 1. 凭证解析 / 序列化
# ------------------------------------------------------------
def test_credentials() -> None:
    print("\n[凭证解析]")
    raw = dump_open_api_credentials({"client_id": "cid", "access_token": "tok"})
    creds = parse_open_api_credentials(raw)
    ok = creds is not None and creds.get("client_id") == "cid" and creds.get("auth_mode") == "open_api"
    record("TC-API01 序列化→解析 往返一致", ok, raw[:60])

    record("TC-API02 普通 cookie 不被误判",
           parse_open_api_credentials("SESSDATA=abc; bili_jct=def") is None)

    record("TC-API03 缺 auth_mode 的 JSON 不被误判",
           parse_open_api_credentials('{"client_id":"x"}') is None)

    record("TC-API04 非法 JSON 安全返回 None",
           parse_open_api_credentials("{not json") is None)

    record("TC-API05 空串安全返回 None", parse_open_api_credentials("") is None)


# ------------------------------------------------------------
# 2. 工厂路由
# ------------------------------------------------------------
def test_factory() -> None:
    print("\n[工厂路由]")
    bili_creds = dump_open_api_credentials({
        "client_id": "cid", "client_secret": "sec",
        "access_token": "tok", "refresh_token": "rt",
    })
    c1 = PlatformClientFactory.create("bilibili", cookies=bili_creds)
    record("TC-API06 带 open_api 凭证 → B站官方客户端",
           isinstance(c1, BilibiliOpenApiClient), type(c1).__name__)

    c2 = PlatformClientFactory.create("bilibili", cookies="SESSDATA=abc; bili_jct=def")
    record("TC-API07 普通 cookie → B站 cookie 客户端",
           isinstance(c2, BilibiliClient) and not isinstance(c2, BilibiliOpenApiClient),
           type(c2).__name__)

    dy_creds = dump_open_api_credentials({
        "client_key": "ck", "client_secret": "cs",
        "access_token": "tok", "refresh_token": "rt", "open_id": "oid",
    })
    c3 = PlatformClientFactory.create("douyin", cookies=dy_creds)
    record("TC-API08 带 open_api 凭证 → 抖音官方客户端",
           isinstance(c3, DouyinOpenApiClient), type(c3).__name__)

    try:
        PlatformClientFactory.create("xiaohongshu", cookies=bili_creds)
        record("TC-API09 小红书无官方 API → 明确报错", False, "未抛异常")
    except ValueError as e:
        record("TC-API09 小红书无官方 API → 明确报错", True, str(e))


# ------------------------------------------------------------
# 3. B站签名
# ------------------------------------------------------------
def test_bilibili_signature() -> None:
    print("\n[B站签名]")
    creds = {"client_id": "akid-123", "client_secret": "secret-xyz", "access_token": "at"}
    client = BilibiliOpenApiClient(creds)

    # 固定时间戳和 nonce，便于独立复算签名
    _orig_time, _orig_uuid = oac.time.time, oac.uuid.uuid4
    oac.time.time = lambda: 1700000000.0
    oac.uuid.uuid4 = lambda: SimpleNamespace(hex="fixednonce")
    try:
        body = json.dumps({"name": "a.mp4", "utype": "1"},
                          ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        h = client._signed_headers(body, "application/json")

        expect_md5 = hashlib.md5(body).hexdigest()
        sign_str = "\n".join([
            "x-bili-accesskeyid:akid-123",
            f"x-bili-content-md5:{expect_md5}",
            "x-bili-signature-method:HMAC-SHA256",
            "x-bili-signature-nonce:fixednonce",
            "x-bili-signature-version:2.0",
            "x-bili-timestamp:1700000000",
        ])
        expect_sign = hmac.new(b"secret-xyz", sign_str.encode(), hashlib.sha256).hexdigest()

        record("TC-API10 content-md5 与请求体一致", h["X-Bili-Content-Md5"] == expect_md5, expect_md5)
        record("TC-API11 签名串顺序/取值符合官方规范", h["Authorization"] == expect_sign,
               h["Authorization"][:16] + "...")
        ok = (h["X-Bili-Signature-Method"] == "HMAC-SHA256"
              and h["X-Bili-Signature-Version"] == "2.0"
              and h["X-Bili-Accesskeyid"] == "akid-123"
              and h["Access-Token"] == "at")
        record("TC-API12 必备签名头齐全", ok)

        # multipart 场景：官方要求 md5 取空串
        hp = client._signed_headers(b"", "multipart/form-data")
        record("TC-API13 multipart 用空串 md5",
               hp["X-Bili-Content-Md5"] == hashlib.md5(b"").hexdigest(),
               hp["X-Bili-Content-Md5"])
    finally:
        # 还原被替换的函数（不做 module reload，否则异常类对象会被换掉导致 except 失效）
        oac.time.time, oac.uuid.uuid4 = _orig_time, _orig_uuid


# ------------------------------------------------------------
# 4. 抖音
# ------------------------------------------------------------
def test_douyin() -> None:
    print("\n[抖音]")
    creds = {"client_key": "ck", "client_secret": "cs",
             "access_token": "tok", "refresh_token": "rt", "open_id": "oid"}
    client = DouyinOpenApiClient(creds)

    meta = VideoMeta(title="今天的翻译练习", tags=["英语", "#学习"])
    text = client._build_text(meta)
    record("TC-API14 文案拼装 标题+话题",
           text.startswith("今天的翻译练习") and "#英语" in text and "#学习" in text, text)
    record("TC-API15 去重 # 前缀不出现 ##", "##" not in text, text)

    record("TC-API16 空标题时只留话题",
           client._build_text(VideoMeta(tags=["a"])) == "#a")

    # 错误码解析
    class _Resp:
        def __init__(self, payload):
            self.status_code = 200
            self._p = payload
            self.text = json.dumps(payload)

        def json(self):
            return self._p

    try:
        DouyinOpenApiClient._check(
            _Resp({"data": {}, "extra": {"error_code": 10008, "description": "token过期"}}),
            "/x",
        )
        record("TC-API17 token 过期错误码透出", False, "未抛异常")
    except DouyinApiError as e:
        record("TC-API17 token 过期错误码透出", e.code in DouyinOpenApiClient.TOKEN_ERROR_CODES, f"code={e.code}")

    ok_data = DouyinOpenApiClient._check(
        _Resp({"data": {"video_id": "v1"}, "extra": {"error_code": 0}}), "/x")
    record("TC-API18 成功响应正确取 data", ok_data.get("video_id") == "v1")

    c2 = DouyinOpenApiClient(dict(creds, expires_at=1))
    record("TC-API19 过期时间已过 → 需要刷新", c2._token_expiring() is True)
    c3 = DouyinOpenApiClient(dict(creds, expires_at=9999999999))
    record("TC-API20 未过期 → 不刷新", c3._token_expiring() is False)


# ------------------------------------------------------------
# 5. 端到端流程（假 session，不联网）
# ------------------------------------------------------------
class _FakeResp:
    def __init__(self, payload):
        self.status_code = 200
        self._p = payload
        self.text = json.dumps(payload, ensure_ascii=False)

    def json(self):
        return self._p


class _FakeSession:
    """记录调用顺序，按 url 关键词返回预置响应"""

    def __init__(self, routes):
        self.routes = routes
        self.calls = []
        self.headers = {}
        self.cookies = SimpleNamespace(set=lambda *a, **k: None)

    def post(self, url, params=None, data=None, json=None, files=None, headers=None, timeout=None):
        self.calls.append({"url": url, "params": params or {}, "json": json,
                           "data": data, "files": files})
        for kw, payload in self.routes:
            if kw in url:
                return _FakeResp(payload)
        return _FakeResp({"code": -1, "message": "unexpected url"})


def _payload(call) -> dict:
    """取出请求体（B站用 data= 发 JSON 字节流，抖音用 json=）"""
    if call.get("json") is not None:
        return call["json"]
    data = call.get("data")
    if isinstance(data, (bytes, bytearray)):
        return json.loads(bytes(data).decode("utf-8"))
    if isinstance(data, str):
        return json.loads(data)
    return {}


def test_flow_bilibili() -> None:
    print("\n[B站投稿流程]")
    creds = {"client_id": "cid", "client_secret": "sec", "access_token": "at"}
    client = BilibiliOpenApiClient(creds)

    tmp = os.path.join(os.environ.get("TEMP", "."), "vc_api_test_video.mp4")
    with open(tmp, "wb") as f:
        f.write(b"\x00" * 2048)

    routes = [
        ("/arcopen/fn/archive/video/init", {"code": 0, "data": {"upload_token": "UT123"}}),
        ("/video/v2/upload", {"code": 0, "data": {"ok": 1}}),
        ("/arcopen/fn/archive/add-by-utoken",
         {"code": 0, "data": {"resource_id": "BV1xx411c7mD"}}),
    ]
    fake = _FakeSession(routes)
    client._session = fake

    meta = VideoMeta(title="测试投稿", tags=["英语学习", "翻译"], category="", description="desc")
    result = client.upload_video(tmp, meta)
    os.remove(tmp)

    urls = [c["url"].split("?")[0] for c in fake.calls]
    record("TC-API21 投稿成功并返回 BV 号",
           result.success and result.remote_id == "BV1xx411c7mD", f"remote={result.remote_id} err={result.error_msg}")
    record("TC-API22 调用顺序 init→upload→submit",
           urls[-3:] == ["https://member.bilibili.com/arcopen/fn/archive/video/init",
                         "https://member.bilibili.com/video/v2/upload",
                         "https://member.bilibili.com/arcopen/fn/archive/add-by-utoken"],
           " → ".join(u.replace("https://member.bilibili.com", "") for u in urls[-3:]))
    init_call = fake.calls[0]
    upload_call = fake.calls[1]
    submit_call = fake.calls[-1]
    record("TC-API23 init 传 utype=1（≤100MB 整片）",
           _payload(init_call).get("utype") == "1", str(_payload(init_call)))
    record("TC-API24 upload 带上 upload_token",
           upload_call["params"].get("upload_token") == "UT123", str(upload_call["params"]))
    record("TC-API25 提交体含标题/分区/标签/token",
           _payload(submit_call).get("title") == "测试投稿"
           and _payload(submit_call).get("tid") == 22
           and submit_call["params"].get("upload_token") == "UT123",
           str(_payload(submit_call)))


def test_flow_douyin() -> None:
    print("\n[抖音发布流程]")
    creds = {"client_key": "ck", "client_secret": "cs",
             "access_token": "at", "refresh_token": "rt", "open_id": "oid"}
    client = DouyinOpenApiClient(creds)

    tmp = os.path.join(os.environ.get("TEMP", "."), "vc_api_test_video2.mp4")
    with open(tmp, "wb") as f:
        f.write(b"\x00" * 2048)

    routes = [
        ("upload_video", {"data": {"video": {"video_id": "ENC123"}},
                          "extra": {"error_code": 0}}),
        ("create_video", {"data": {"video_id": "7111", "item_id": "7222"},
                          "extra": {"error_code": 0}}),
    ]
    fake = _FakeSession(routes)
    client._session = fake

    result = client.upload_video(tmp, VideoMeta(title="标题", tags=["a"]))
    os.remove(tmp)

    urls = [c["url"] for c in fake.calls]
    record("TC-API26 抖音发布成功并返回作品 id",
           result.success and result.remote_id == "7111", f"remote={result.remote_id} err={result.error_msg}")
    record("TC-API27 调用顺序 upload_video→create_video",
           "upload_video" in urls[0] and "create_video" in urls[1], " → ".join(urls))
    record("TC-API28 create 使用加密 video_id + 话题文案",
           fake.calls[1]["json"].get("video_id") == "ENC123"
           and "#a" in fake.calls[1]["json"].get("text", ""),
           str(fake.calls[1]["json"]))


def main() -> int:
    print("=" * 64)
    print("B站/抖音 官方开放平台客户端 — 离线回归")
    print("=" * 64)
    test_credentials()
    test_factory()
    test_bilibili_signature()
    test_douyin()
    test_flow_bilibili()
    test_flow_douyin()
    print("\n" + "=" * 64)
    print(f"结果: {_passed} 通过 / {_failed} 失败")
    print("=" * 64)
    return 0 if _failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
