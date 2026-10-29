"""
小红书视频/图文发布 — 基于逆向 Creator API 的纯 HTTP 客户端。

签名 / 上传 permit / 文件上传 全部来自 xhs_cli (xiaohongshu-cli 0.6.4) 的
逆向成果；本文件补齐 **create_video_note**（xhs_cli 只支持图文）。

前置依赖:
    pip install xiaohongshu-cli httpx
    xhs login   # 从浏览器自动提取 cookie, 或手动放 cookies.json

使用:
    from Vc.core.publish.xhs_api_client import XhsApiClient

    client = XhsApiClient.from_browser_cookies()
    result = client.upload_video(
        video_path="/path/to/video.mp4",
        title="标题",
        desc="正文描述",
        cover_path="/path/to/cover.jpg",   # 可选, 不传则从视频抽首帧
        topics=[{"name": "标签名"}],
    )
    print(result["note_id"])
"""

from __future__ import annotations

import json
import logging
import os
import time
from pathlib import Path
from typing import Any

import httpx

# AUDIT-0063: xhs_cli 是可选依赖，未安装时保证本模块仍可导入；
# XhsClient 是基类无法延迟导入，故在真正用到功能的使用点抛清晰中文异常。
try:
    from xhs_cli.client import XhsClient
    from xhs_cli.constants import CREATOR_HOST, UPLOAD_HOST
    from xhs_cli.exceptions import XhsApiError
    _XHS_CLI_IMPORT_ERROR: BaseException | None = None
except ImportError as _exc:
    XhsClient = object  # type: ignore[assignment, misc]
    CREATOR_HOST = UPLOAD_HOST = ""
    XhsApiError = RuntimeError  # type: ignore[assignment, misc]
    _XHS_CLI_IMPORT_ERROR = _exc


def _ensure_xhs_cli() -> None:
    """用到 xhs_cli 功能前检查可选依赖，缺失时抛清晰中文提示。"""
    if _XHS_CLI_IMPORT_ERROR is not None:
        raise RuntimeError(
            "缺少可选依赖 xiaohongshu-cli（xhs_cli），无法使用小红书 API 发布。\n"
            "请先安装依赖后重试: pip install xiaohongshu-cli\n"
            f"（原始导入错误: {_XHS_CLI_IMPORT_ERROR}）"
        )

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 扩展: create_video_note — 把 Spider_XHS 的 video_info 结构抄进来
# ---------------------------------------------------------------------------

def _build_video_note_data(
    title: str,
    desc: str,
    video_file_id: str,           # "spectrum/xxx"
    cover_file_id: str,           # "spectrum/xxx"
    topics: list[dict] | None = None,
    is_private: bool = False,
    post_loc: dict | None = None,
) -> dict[str, Any]:
    """构造 /web_api/sns/v2/note 的 POST body (视频笔记)."""
    business_binds = (
        '{"version":1,"noteId":0,"bizType":0,"noteOrderBind":{},'
        '"notePostTiming":{},"noteCollectionBind":{"id":""},'
        '"noteSketchCollectionBind":{"id":""},"coProduceBind":{"enable":true},'
        '"noteCopyBind":{"copyable":true},'
        '"interactionPermissionBind":{"commentPermission":0},'
        '"optionRelationList":[]}'
    )
    return {
        "common": {
            "type": "video",
            "title": title,
            "note_id": "",
            "desc": desc,
            "source": (
                '{"type":"web","ids":"",'
                '"extraInfo":"{\\"subType\\":\\"official\\",'
                '\\"systemId\\":\\"web\\"}"}'
            ),
            "business_binds": business_binds,
            "ats": [],
            "hash_tag": topics or [],
            "post_loc": post_loc or {},
            "privacy_info": {
                "op_type": 1,
                "type": 1 if is_private else 0,
                "user_ids": [],
            },
            "goods_info": {},
            "biz_relations": [],
            "capa_trace_info": {
                "contextJson": (
                    '{"recommend_title":{"recommend_title_id":"","is_use":3,'
                    '"used_index":-1},"recommendTitle":[],'
                    '"recommend_topics":{"used":[]}}'
                )
            },
        },
        "image_info": None,
        "video_info": {
            "fileid": video_file_id,
            "file_id": video_file_id,
            "format_width": 0,
            "format_height": 0,
            "video_preview_type": "",
            "composite_metadata": {
                "video": {
                    "bitrate": None,
                    "colour_primaries": "BT.709",
                    "duration": 0,
                    "format": "AVC",
                    "frame_rate": 0,
                    "height": 0,
                    "matrix_coefficients": "BT.709",
                    "rotation": 0,
                    "transfer_characteristics": "BT.709",
                    "width": 0,
                },
                "audio": {"bitrate": None},
            },
            "timelines": [],
            "cover": {
                "fileid": cover_file_id,
                "file_id": cover_file_id,
                "height": 0,
                "width": 0,
                "frame": {
                    "ts": 0,
                    "is_user_select": False,
                    "is_upload": False,
                },
                "stickers": {"version": 2, "neptune": []},
                "fonts": [],
                "extra_info_json": "{}",
            },
            "chapters": [],
            "chapter_sync_text": False,
            "segments": {
                "count": 1,
                "need_slice": False,
                "items": [
                    {"bizType": 0, "fileIds": video_file_id},
                ],
            },
        },
    }


# ---------------------------------------------------------------------------
# 封装 Client
# ---------------------------------------------------------------------------

class XhsApiClient(XhsClient):
    """
    在 xhs_cli.XhsClient 之上补 create_video_note.

    用法:
        from Vc.core.publish.xhs_api_client import XhsApiClient
        client = XhsApiClient.from_browser_cookies()
        client.upload_video(...)
        client.upload_image(...)
    """

    # ---------- factory ----------

    # 从 __file__ 定位到项目根:
    #   xhs_api_client.py → publish → core → Vc → VideoCrawler (项目根)
    _HERE = Path(__file__).resolve()                   # .../Vc/core/publish/xhs_api_client.py
    _PROJECT_ROOT = _HERE.parent.parent.parent.parent  # VideoCrawler/

    # 默认 cookie 文件搜索路径 (按优先级, 全部绝对路径)
    _DEFAULT_COOKIE_FILES = [
        _PROJECT_ROOT / "xhs_cookies.json",
        _PROJECT_ROOT / "xhs_cookies.txt",
        _PROJECT_ROOT / "Vc" / "xhs_cookies.json",
        _PROJECT_ROOT / "Vc" / "xhs_cookies.txt",
        Path.home() / "xhs_cookies.json",
        Path.home() / "xhs_cookies.txt",
    ]

    @classmethod
    def from_file(cls, path: str | None = None) -> "XhsApiClient":
        """从文件读 cookie (支持 JSON / Cookie header 两种格式)."""
        _ensure_xhs_cli()
        from ._cookie_utils import parse_cookies_to_dict

        if path is None:
            for p in cls._DEFAULT_COOKIE_FILES:
                if os.path.isfile(p):
                    path = p
                    break
            if path is None:
                raise FileNotFoundError(
                    "没找到 cookie 文件. 请在 Edge 登录 creator.xiaohongshu.com 后, "
                    "F12→Console 执行 copy(document.cookie) 把输出粘贴到 "
                    "xhs_cookies.txt (项目根目录)."
                )

        with open(path, "r", encoding="utf-8") as f:
            raw = f.read()
        cookies = parse_cookies_to_dict(raw)
        if "a1" not in cookies:
            raise RuntimeError(
                f"{path} 里没 a1 cookie. 请确认 cookie 是从 xiaohongshu.com 登录后导出的."
            )
        logger.info("从 %s 加载 %d 个 cookie (a1=%s...)", path, len(cookies), cookies["a1"][:8])
        return cls(cookies=cookies)

    @classmethod
    def from_browser_cookies(cls) -> "XhsApiClient":
        """多级 fallback: browser_cookie3 → 默认文件 → 抛友好错误."""
        _ensure_xhs_cli()
        cookies: dict[str, str] = {}

        # 先试 browser_cookie3 (需要管理员权限)
        try:
            from browser_cookie3 import chrome, chromium, edge
            for fn in (edge, chromium, chrome):
                try:
                    jar = fn(domain_name="xiaohongshu.com")
                    cookies.update({c.name: c.value for c in jar})
                except Exception as e:
                    logger.debug("browser_cookie3.%s 失败: %s", fn.__name__, e)
        except ImportError:
            pass

        if "a1" in cookies:
            logger.info("从浏览器提取到 %d 个 cookie (a1=%s...)", len(cookies), cookies["a1"][:8])
            return cls(cookies=cookies)

        # 降级: 从默认文件读
        for p in cls._DEFAULT_COOKIE_FILES:
            if os.path.isfile(p):
                try:
                    return cls.from_file(p)
                except Exception as e:
                    logger.debug("文件 %s 也不行: %s", p, e)

        raise RuntimeError(
            "❌ 没拿到有效 cookie (缺 a1).\n"
            "   原因: Windows Edge 用 DPAPI 加密 cookie, 普通进程解不开.\n"
            "\n"
            "   解法 A (最快): 以管理员身份运行 VSCode, 然后重新跑.\n"
            "   解法 B (永久): 在 Edge 登录 creator.xiaohongshu.com 后,\n"
            "                   F12 → Console 执行 copy(document.cookie)\n"
            "                   把输出粘贴到 d:\\Ideas\\VideoCrawler\\xhs_cookies.txt\n"
            "                   然后就永远不用再管了."
        )

    # ---------- video upload ----------

    def _get_permit(self, scene: str) -> tuple[str, str]:
        """
        拿 upload permit.

        xhs_cli 原实现:
            GET /api/media/v1/upload/web/permit?biz_name=spectrum&scene=<scene>
                &source=web&file_count=1&version=1
        返回 (file_id_without_prefix, token).
        """
        data = self._creator_get(
            "/api/media/v1/upload/web/permit",
            {
                "biz_name": "spectrum",
                "scene": scene,       # "image" 或 "video"
                "file_count": 1,
                "version": 1,
                "source": "web",
            },
        )
        permits = data.get("uploadTempPermits") or []
        if not permits:
            raise XhsApiError(f"permit 响应里没有 uploadTempPermits: {json.dumps(data)[:300]}")
        file_ids = permits[0].get("fileIds") or []
        token = permits[0].get("token")
        if not file_ids or not token:
            raise XhsApiError(f"permit 缺少 fileIds 或 token: {json.dumps(data)[:300]}")
        return file_ids[0], token

    def _put_file(self, file_id: str, token: str, file_path: str) -> None:
        """PUT 到 ros-upload.xiaohongshu.com/{file_id} (xhs_cli 原实现)."""
        import mimetypes
        with open(file_path, "rb") as f:
            file_data = f.read()
        url = f"{UPLOAD_HOST}/{file_id}"
        content_type = mimetypes.guess_type(file_path)[0] or "application/octet-stream"
        logger.info("PUT %s (%d bytes)", url, len(file_data))
        resp = self._request_with_retry(
            "PUT",
            url,
            headers={
                "X-Cos-Security-Token": token,
                "Content-Type": content_type,
            },
            content=file_data,
        )
        if resp.status_code >= 400:
            raise XhsApiError(f"PUT 上传失败: {resp.status_code} {resp.text[:200]}")
        logger.info("上传成功 HTTP %d", resp.status_code)

    def upload_video(
        self,
        video_path: str | Path,
        title: str,
        desc: str = "",
        cover_path: str | Path | None = None,
        topics: list[str] | None = None,
        is_private: bool = False,
    ) -> dict[str, Any]:
        """
        完整的视频发布流程:
            permit(video) → PUT video → permit(image) → PUT cover → POST /web_api/sns/v2/note

        返回: {"note_id": "...", "success": True, ...}

        ⚠️ 小红书 ros-upload Nginx 有请求体大小限制 (~50-100MB)，
           大视频会 413 → 调用方应捕获异常后降级 Playwright。
        """
        _ensure_xhs_cli()
        video_path = str(video_path)
        if not os.path.isfile(video_path):
            raise FileNotFoundError(video_path)

        # ★ 预检查：视频太大直接跳过 API 路径，不浪费时间
        # 小红书 ros-upload Nginx client_max_body_size 估计 ~100MB
        MAX_API_UPLOAD_MB = 80
        size_mb = os.path.getsize(video_path) / 1024 / 1024
        if size_mb > MAX_API_UPLOAD_MB:
            raise RuntimeError(
                f"视频体积 {size_mb:.1f}MB 超过小红书 API 上传限制 ({MAX_API_UPLOAD_MB}MB)，"
                f"请降级 Playwright 或手动压缩视频"
            )

        # 1. permit + 上传视频
        logger.info("=== 1/4 获取视频 upload permit ===")
        raw_video_id, video_token = self._get_permit("video")
        video_file_id = f"spectrum/{raw_video_id}"  # Spider_XHS 的格式
        logger.info("video file_id = %s", video_file_id)

        logger.info("=== 2/4 PUT 上传视频文件 ===")
        self._put_file(raw_video_id, video_token, video_path)

        # 2. permit + 上传封面 (必须)
        logger.info("=== 3/4 获取封面 upload permit ===")
        raw_cover_id, cover_token = self._get_permit("image")
        cover_file_id = f"spectrum/{raw_cover_id}"

        if cover_path is None:
            cover_path = self._extract_first_frame(video_path)
        if not os.path.isfile(str(cover_path)):
            raise FileNotFoundError(f"封面文件不存在: {cover_path}")

        logger.info("=== 4/4 PUT 上传封面 %s ===", cover_path)
        self._put_file(raw_cover_id, cover_token, str(cover_path))

        # 3. 组装 note 数据 + POST
        logger.info("=== POST /web_api/sns/v2/note ===")
        topic_dicts = [{"name": t} for t in (topics or [])]
        data = _build_video_note_data(
            title=title,
            desc=desc,
            video_file_id=video_file_id,
            cover_file_id=cover_file_id,
            topics=topic_dicts,
            is_private=is_private,
        )
        result = self._main_api_post(
            "/web_api/sns/v2/note",
            data,
            {"origin": CREATOR_HOST, "referer": f"{CREATOR_HOST}/"},
        )
        note_id = None
        if isinstance(result, dict):
            note_id = result.get("note_id") or result.get("noteId")
        logger.info("发布成功 note_id=%s", note_id)
        return {"success": True, "note_id": note_id, "raw": result}

    # ---------- 封面抽帧 ----------

    @staticmethod
    def _extract_first_frame(video_path: str) -> str:
        """从视频抽第一帧当封面, 返回临时 jpg 路径."""
        import cv2
        import tempfile
        tmp = tempfile.NamedTemporaryFile(suffix=".jpg", delete=False)
        tmp.close()
        cap = cv2.VideoCapture(video_path)
        ret, frame = cap.read()
        cap.release()
        if not ret:
            raise RuntimeError(f"无法从视频抽帧: {video_path}")
        cv2.imwrite(tmp.name, frame)
        logger.info("抽首帧封面 -> %s", tmp.name)
        return tmp.name


# ---------------------------------------------------------------------------
# 快捷函数: 一步到位
# ---------------------------------------------------------------------------

def quick_publish_video(
    video_path: str,
    title: str,
    desc: str = "",
    cover_path: str | None = None,
    topics: list[str] | None = None,
) -> dict[str, Any]:
    """一行代码发布视频 (从浏览器自动提取 cookie)."""
    client = XhsApiClient.from_browser_cookies()
    return client.upload_video(
        video_path=video_path,
        title=title,
        desc=desc,
        cover_path=cover_path,
        topics=topics,
    )
