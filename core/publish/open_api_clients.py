"""
open_api_clients.py — B站 / 抖音 **官方开放平台** 发布客户端

与 clients.py 里基于 cookie/浏览器的客户端并列，但走的是平台官方 OpenAPI：
  - B站：开放平台「服务端视频稿件投递」（upload_token + HMAC-SHA256 签名）
  - 抖音：开放平台「代替用户发布内容到抖音」（OAuth access_token + 分片/整片上传）

为什么单独一个模块：
  官方 API 的鉴权模型是 client_id/client_secret + access_token，
  与 cookie 模型完全不同，混在 clients.py 里会让基类语义混乱。

凭证存储：
  复用 publish_account.cookies 字段，但内容改为 JSON，形如：
    {"auth_mode": "open_api", "client_id": "...", "client_secret": "...",
     "access_token": "...", "refresh_token": "...", "expires_at": 1730000000}
  这样 GUI / 手机端 / DB 结构都不用改，工厂按 auth_mode 自动路由。

⚠️ 前置条件（代码之外）：
  - B站开放平台：需企业资质（营业执照 + 授权公函）开通「视频稿件投递」能力
  - 抖音开放平台：需在能力实验室申请「代替用户发布内容到抖音」并通过
  凭据拿不到时，请继续用 cookie + cookie 客户端（clients.py）。
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import time
import uuid
from typing import Any, Callable, Dict, Optional

import requests
from loguru import logger

from .clients import BasePlatformClient, PublishResult, VideoMeta


# ============================================================
# 凭证解析 / 序列化
# ============================================================

AUTH_MODE_KEY = "auth_mode"
AUTH_MODE_OPEN_API = "open_api"


def parse_open_api_credentials(raw: str) -> Optional[Dict[str, Any]]:
    """从账号 cookies 字段识别官方开放平台凭证。

    不是 JSON / 没有 auth_mode=open_api 的，一律返回 None（交给 cookie 客户端）。
    """
    if not raw:
        return None
    text = raw.strip()
    if not text.startswith("{"):
        return None
    try:
        data = json.loads(text)
    except Exception:
        return None
    if not isinstance(data, dict):
        return None
    if data.get(AUTH_MODE_KEY) != AUTH_MODE_OPEN_API:
        return None
    return data


def dump_open_api_credentials(creds: Dict[str, Any]) -> str:
    """序列化凭证（写回 DB 用，保持 auth_mode）"""
    payload = dict(creds)
    payload[AUTH_MODE_KEY] = AUTH_MODE_OPEN_API
    return json.dumps(payload, ensure_ascii=False)


# ============================================================
# 公共基类
# ============================================================

class BaseOpenApiClient(BasePlatformClient):
    """官方 OpenAPI 客户端的公共部分（不走 cookie）"""

    platform_id = ""
    platform_label = ""

    def __init__(self, credentials: Dict[str, Any], user_agent: str = ""):
        # 注意：不调用 super().__init__（那会把 JSON 当 cookie 解析）
        self._creds: Dict[str, Any] = dict(credentials)
        self._cookies_raw = dump_open_api_credentials(self._creds)
        self._cookies: Dict[str, str] = {}
        self._nickname = str(self._creds.get("nickname") or "")
        self._access_token = str(self._creds.get("access_token") or "")
        # token 刷新后回写 DB 的回调，由调用方（service/GUI）注入
        self.on_credentials_changed: Optional[Callable[[Dict[str, Any]], None]] = None
        self._session = requests.Session()
        self._session.headers.update({
            "User-Agent": user_agent or (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/131.0.0.0 Safari/537.36"
            ),
            "Accept": "application/json",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        })

    def _cookie_domain(self) -> str:
        return ""

    # ---- 凭证维护 ----

    def _token_expiring(self, margin: int = 300) -> bool:
        exp = int(self._creds.get("expires_at") or 0)
        if not exp:
            return False        # 没记录过期时间，靠调用失败后重试刷新
        return time.time() + margin >= exp

    def _emit_credentials_changed(self) -> None:
        self._creds["access_token"] = self._access_token
        self._cookies_raw = dump_open_api_credentials(self._creds)
        cb = self.on_credentials_changed
        if cb:
            try:
                cb(dict(self._creds))
            except Exception as e:
                logger.warning(f"[{self.platform_label}] 凭证回写失败: {e}")

    # ---- 子类实现 ----

    def _refresh_token(self) -> bool:
        raise NotImplementedError

    def verify_login(self) -> bool:
        """默认实现：能用 refresh_token 换到新 token 就算有效"""
        if not self._access_token:
            return False
        if not self._creds.get("refresh_token"):
            return True
        return self._refresh_token()


# ============================================================
# B站开放平台客户端
# ============================================================

class BilibiliOpenApiClient(BaseOpenApiClient):
    """B站开放平台「服务端视频稿件投递」

    流程（官方规定）：
      文件 ≤100MB → init(utype=1) → /video/v2/upload → 稿件提交
      文件 >100MB → init(utype=0) → /video/v2/part/upload(8MB 分片) → /video/v2/complete → 稿件提交
    """

    platform_id = "bilibili"
    platform_label = "哔哩哔哩(开放平台)"

    MEMBER_BASE = "https://member.bilibili.com"
    OAUTH_BASE = "https://api.bilibili.com/x/account-oauth2/v1"
    SINGLE_LIMIT = 100 * 1024 * 1024
    PART_SIZE = 8 * 1024 * 1024
    DEFAULT_TID = 22          # 22 = 生活分区（后台可改）
    # 上传接口的文件字段名（官方文档未标注，社区实现均为 file / part）
    UPLOAD_FIELD = "file"
    PART_FIELD = "part"

    # ---- 签名（官方 HMAC-SHA256 2.0）----

    def _signed_headers(self, body: bytes = b"", content_type: str = "application/json") -> Dict[str, str]:
        client_id = str(self._creds.get("client_id") or "")
        secret = str(self._creds.get("client_secret") or self._creds.get("app_secret") or "")
        ts = str(int(time.time()))
        nonce = uuid.uuid4().hex
        content_md5 = hashlib.md5(body).hexdigest()

        # 待签名串：带 x-bili- 前缀的 header 按字典序，k:v 用 \n 连接
        sign_pairs = [
            f"x-bili-accesskeyid:{client_id}",
            f"x-bili-content-md5:{content_md5}",
            "x-bili-signature-method:HMAC-SHA256",
            f"x-bili-signature-nonce:{nonce}",
            "x-bili-signature-version:2.0",
            f"x-bili-timestamp:{ts}",
        ]
        signing_str = "\n".join(sign_pairs)
        signature = hmac.new(secret.encode("utf-8"), signing_str.encode("utf-8"), hashlib.sha256).hexdigest()

        return {
            "Accept": "application/json",
            "Content-Type": content_type,
            "X-Bili-Accesskeyid": client_id,
            "X-Bili-Content-Md5": content_md5,
            "X-Bili-Signature-Method": "HMAC-SHA256",
            "X-Bili-Signature-Nonce": nonce,
            "X-Bili-Signature-Version": "2.0",
            "X-Bili-Timestamp": ts,
            "Authorization": signature,
            "Access-Token": self._access_token,
        }

    def _post_json(self, path: str, payload: Dict[str, Any], params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        resp = self._session.post(
            self.MEMBER_BASE + path,
            params=params or {},
            data=body,
            headers=self._signed_headers(body, "application/json"),
            timeout=60,
        )
        return self._check(resp, path)

    def _post_multipart(self, path: str, field: str, file_path: str,
                        params: Optional[Dict[str, Any]] = None,
                        part_range: Optional[tuple] = None) -> Dict[str, Any]:
        # multipart 的 content-md5 按官方说明用空串的 md5
        headers = self._signed_headers(b"", "multipart/form-data")
        headers.pop("Content-Type", None)   # 让 requests 自己带 boundary
        fh = open(file_path, "rb")
        try:
            if part_range:
                start, end = part_range
                fh.seek(start)
                content = fh.read(end - start)
                files = {field: (os.path.basename(file_path), content, "application/octet-stream")}
            else:
                files = {field: (os.path.basename(file_path), fh, "application/octet-stream")}
            resp = self._session.post(
                self.MEMBER_BASE + path,
                params=params or {},
                files=files,
                headers=headers,
                timeout=600,
            )
        finally:
            fh.close()
        return self._check(resp, path)

    def _post_no_body(self, path: str, params: Dict[str, Any]) -> Dict[str, Any]:
        resp = self._session.post(
            self.MEMBER_BASE + path,
            params=params,
            headers=self._signed_headers(b"", "application/json"),
            timeout=120,
        )
        return self._check(resp, path)

    @staticmethod
    def _check(resp: requests.Response, path: str) -> Dict[str, Any]:
        try:
            data = resp.json()
        except Exception:
            raise RuntimeError(f"B站接口返回非 JSON ({resp.status_code}): {resp.text[:200]}")
        if data.get("code") not in (0, "0", None):
            raise RuntimeError(f"B站 {path} 失败: code={data.get('code')} message={data.get('message')}")
        return data.get("data") or {}

    # ---- OAuth ----

    def _refresh_token(self) -> bool:
        rt = self._creds.get("refresh_token")
        if not rt:
            return False
        try:
            resp = self._session.post(
                f"{self.OAUTH_BASE}/refresh_token",
                data={
                    "client_id": self._creds.get("client_id", ""),
                    "client_secret": self._creds.get("client_secret", ""),
                    "grant_type": "refresh_token",
                    "refresh_token": rt,
                },
                timeout=30,
            )
            data = resp.json()
            if data.get("code") != 0:
                logger.warning(f"[B站开放平台] 刷新 token 失败: {data.get('message')}")
                return False
            d = data.get("data") or {}
            self._access_token = d.get("access_token", self._access_token)
            self._creds["refresh_token"] = d.get("refresh_token", rt)
            self._creds["expires_at"] = int(time.time()) + int(d.get("expires_in", 0) or 0)
            self._emit_credentials_changed()
            logger.info("[B站开放平台] access_token 刷新成功")
            return True
        except Exception as e:
            logger.warning(f"[B站开放平台] 刷新 token 异常: {e}")
            return False

    # ---- 投稿 ----

    def upload_video(self, video_path: str, meta: VideoMeta, progress_cb=None) -> PublishResult:
        t0 = time.time()
        try:
            if not os.path.exists(video_path):
                return PublishResult(False, error_msg=f"视频文件不存在: {video_path}")
            if self._token_expiring():
                self._refresh_token()
            if not self._access_token:
                return PublishResult(False, error_msg="缺少 access_token，请重新授权 B站开放平台")

            size = os.path.getsize(video_path)
            utype = "1" if size <= self.SINGLE_LIMIT else "0"

            # 1) 上传预处理拿 upload_token
            init = self._post_json(
                "/arcopen/fn/archive/video/init",
                {"name": os.path.basename(video_path), "utype": utype},
            )
            upload_token = init.get("upload_token") or ""
            if not upload_token:
                return PublishResult(False, error_msg=f"未拿到 upload_token: {init}")

            # 2) 上传视频本体
            if utype == "1":
                self._post_multipart("/video/v2/upload", self.UPLOAD_FIELD, video_path,
                                     params={"upload_token": upload_token})
                if progress_cb:
                    progress_cb(size, size)
            else:
                total_parts = (size + self.PART_SIZE - 1) // self.PART_SIZE
                for idx in range(total_parts):
                    start = idx * self.PART_SIZE
                    end = min(start + self.PART_SIZE, size)
                    self._post_multipart(
                        "/video/v2/part/upload", self.PART_FIELD, video_path,
                        params={"part_number": idx + 1, "upload_token": upload_token},
                        part_range=(start, end),
                    )
                    if progress_cb:
                        progress_cb(end, size)
                self._post_no_body("/arcopen/fn/archive/video/complete", {"upload_token": upload_token})

            # 3) 封面（可选）
            cover_url = ""
            if meta.cover_path and os.path.exists(meta.cover_path):
                try:
                    cover = self._post_multipart(
                        "/arcopen/fn/archive/cover/upload", self.UPLOAD_FIELD, meta.cover_path,
                        params={"upload_token": upload_token},
                    )
                    cover_url = cover.get("url") or ""
                except Exception as e:
                    logger.warning(f"[B站开放平台] 封面上传失败，改用无封面投稿: {e}")

            # 4) 稿件提交
            tid = self._resolve_tid(meta.category)
            payload: Dict[str, Any] = {
                "title": (meta.title or os.path.basename(video_path))[:80],
                "tid": tid,
                "tag": ",".join(meta.tags[:10])[:200] if meta.tags else "生活",
                "desc": (meta.description or "")[:250],
                "copyright": 1 if meta.original_declaration else 2,
                "no_reprint": 0 if meta.allow_comment else 1,
            }
            if cover_url:
                payload["cover"] = cover_url
            if meta.scheduled_ts:
                logger.warning("[B站开放平台] 官方投稿接口不支持定时发布，已按立即发布处理")

            submitted = self._post_json(
                "/arcopen/fn/archive/add-by-utoken", payload,
                params={"upload_token": upload_token},
            )
            resource_id = str(submitted.get("resource_id") or "")
            return PublishResult(
                success=True,
                remote_id=resource_id,
                remote_url=f"https://www.bilibili.com/video/{resource_id}" if resource_id else "",
                uploaded_bytes=size,
                duration_ms=int((time.time() - t0) * 1000),
            )
        except Exception as e:
            import traceback
            logger.error(f"[B站开放平台] upload_video 异常: {e}\n{traceback.format_exc()}")
            return PublishResult(False, error_msg=str(e), duration_ms=int((time.time() - t0) * 1000))

    def _resolve_tid(self, category: str) -> int:
        """meta.category 可能是数字分区 id，也可能是项目内部类别枚举，兜底 22(生活)"""
        try:
            value = int(str(category).strip())
            return value if value > 0 else self.DEFAULT_TID
        except Exception:
            return self.DEFAULT_TID


# ============================================================
# 抖音开放平台客户端
# ============================================================

class DouyinOpenApiClient(BaseOpenApiClient):
    """抖音开放平台「代替用户发布内容到抖音」

    流程：upload_video（≤128MB 整片）→ create_video（标题/话题/可见范围）
    >128MB 必须分片上传，这里直接拒绝并提示（避免网关超时半途失败）。
    """

    platform_id = "douyin"
    platform_label = "抖音(开放平台)"

    OPEN_BASE = "https://open.douyin.com"
    SINGLE_LIMIT = 128 * 1024 * 1024
    # access_token 过期类错误码，命中后刷新一次重试
    TOKEN_ERROR_CODES = {10008, 2190002, 2190003}

    def _api(self, path: str, params: Dict[str, Any], json_body: Optional[Dict] = None,
             files: Optional[Dict] = None, timeout: int = 120) -> Dict[str, Any]:
        headers = {"access-token": self._access_token}
        if json_body is not None:
            headers["Content-Type"] = "application/json"
        resp = self._session.post(
            self.OPEN_BASE + path,
            params=params,
            json=json_body,
            files=files,
            headers=headers,
            timeout=timeout,
        )
        return self._check(resp, path)

    @staticmethod
    def _check(resp: requests.Response, path: str) -> Dict[str, Any]:
        try:
            data = resp.json()
        except Exception:
            raise RuntimeError(f"抖音接口返回非 JSON ({resp.status_code}): {resp.text[:200]}")
        extra = data.get("extra") or {}
        code = extra.get("error_code", data.get("data", {}).get("error_code", 0))
        if code not in (0, None):
            desc = extra.get("description") or data.get("data", {}).get("description") or ""
            raise DouyinApiError(int(code), f"抖音 {path} 失败: code={code} {desc}")
        return data.get("data") or {}

    def _refresh_token(self) -> bool:
        rt = self._creds.get("refresh_token")
        if not rt:
            return False
        try:
            resp = self._session.post(
                f"{self.OPEN_BASE}/oauth/refresh_token/",
                json={
                    "client_key": self._creds.get("client_key", ""),
                    "client_secret": self._creds.get("client_secret", ""),
                    "grant_type": "refresh_token",
                    "refresh_token": rt,
                },
                timeout=30,
            )
            data = resp.json()
            d = data.get("data") or {}
            if not d.get("access_token"):
                logger.warning(f"[抖音开放平台] 刷新 token 失败: {data}")
                return False
            self._access_token = d["access_token"]
            self._creds["refresh_token"] = d.get("refresh_token", rt)
            self._creds["expires_at"] = int(time.time()) + int(d.get("expires_in", 0) or 0)
            if d.get("open_id"):
                self._creds["open_id"] = d["open_id"]
            self._emit_credentials_changed()
            logger.info("[抖音开放平台] access_token 刷新成功")
            return True
        except Exception as e:
            logger.warning(f"[抖音开放平台] 刷新 token 异常: {e}")
            return False

    def upload_video(self, video_path: str, meta: VideoMeta, progress_cb=None) -> PublishResult:
        t0 = time.time()
        try:
            if not os.path.exists(video_path):
                return PublishResult(False, error_msg=f"视频文件不存在: {video_path}")
            open_id = str(self._creds.get("open_id") or "")
            if not open_id:
                return PublishResult(False, error_msg="凭证缺少 open_id，请重新授权抖音开放平台")

            size = os.path.getsize(video_path)
            if size > self.SINGLE_LIMIT:
                return PublishResult(
                    False,
                    error_msg=f"抖音整片上传上限 128MB，当前 {size / 1024 / 1024:.1f}MB，请先压缩或改用分片上传",
                    duration_ms=int((time.time() - t0) * 1000),
                )

            if self._token_expiring():
                self._refresh_token()

            # 1) 上传视频拿加密 video_id
            with open(video_path, "rb") as fh:
                uploaded = self._retry_on_token_error(
                    lambda: self._api(
                        "/api/douyin/v1/video/upload_video/",
                        {"open_id": open_id},
                        files={"video": (os.path.basename(video_path), fh, "video/mp4")},
                        timeout=1800,
                    )
                )
            if progress_cb:
                progress_cb(size, size)

            video_id = (uploaded.get("video") or {}).get("video_id") or uploaded.get("video_id") or ""
            if not video_id:
                return PublishResult(False, error_msg=f"上传成功但未拿到 video_id: {uploaded}")

            # 2) 创建视频
            text = self._build_text(meta)
            payload: Dict[str, Any] = {"video_id": video_id, "text": text}
            if meta.cover_path and os.path.exists(meta.cover_path):
                # 抖音自定义封面需要先走图片上传接口，这里按视频帧取封面更稳妥
                payload["cover_tsp"] = 1.0
            created = self._retry_on_token_error(
                lambda: self._api(
                    "/api/douyin/v1/video/create_video/",
                    {"open_id": open_id},
                    json_body=payload,
                )
            )
            plain_id = str(created.get("video_id") or "")
            item_id = str(created.get("item_id") or "")
            remote_id = plain_id or item_id
            return PublishResult(
                success=True,
                remote_id=remote_id,
                remote_url=f"https://www.douyin.com/video/{plain_id}" if plain_id else "",
                uploaded_bytes=size,
                duration_ms=int((time.time() - t0) * 1000),
            )
        except Exception as e:
            import traceback
            logger.error(f"[抖音开放平台] upload_video 异常: {e}\n{traceback.format_exc()}")
            return PublishResult(False, error_msg=str(e), duration_ms=int((time.time() - t0) * 1000))

    def _retry_on_token_error(self, fn: Callable[[], Dict[str, Any]]) -> Dict[str, Any]:
        try:
            return fn()
        except DouyinApiError as e:
            if e.code in self.TOKEN_ERROR_CODES and self._refresh_token():
                return fn()
            raise

    @staticmethod
    def _build_text(meta: VideoMeta) -> str:
        """标题 + 话题（抖音话题用 #xxx 拼接）"""
        title = (meta.title or "").strip()
        tags = [t for t in (meta.tags or []) if t][:10]
        topic = " ".join(f"#{t.lstrip('#')}" for t in tags)
        if title and topic:
            return f"{title} {topic}"[:1000]
        return (title or topic)[:1000]


class DouyinApiError(RuntimeError):
    """携带抖音业务错误码，便于判断是否为 token 过期"""

    def __init__(self, code: int, message: str):
        super().__init__(message)
        self.code = code


# ============================================================
# 构造入口
# ============================================================

_OPEN_REGISTRY: Dict[str, type] = {
    "bilibili": BilibiliOpenApiClient,
    "douyin": DouyinOpenApiClient,
}


def supports_open_api(platform_id: str) -> bool:
    return platform_id in _OPEN_REGISTRY


def build_open_api_client(platform_id: str, credentials: Dict[str, Any]) -> BaseOpenApiClient:
    klass = _OPEN_REGISTRY.get(platform_id)
    if not klass:
        raise ValueError(f"{platform_id} 暂不支持官方 OpenAPI 直发，请继续使用 cookie 方式")
    return klass(credentials)
