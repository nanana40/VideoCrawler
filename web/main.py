"""
VideoCrawler 远程控制 Web 接口
==============================
FastAPI 后端 + 移动端单页前端。
部署：uvicorn web.main:app --host 0.0.0.0 --port 8000 --reload
"""

from __future__ import annotations

import asyncio
import json
import mimetypes
import os
import queue
import secrets
import sys
import threading
from utils.thread_spawn import spawn  # AUDIT-0033
import time
import uuid
from collections import deque
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.base import BaseHTTPMiddleware
from pydantic import BaseModel, Field

# ---------- 工作目录修正：让 `from core.xxx import` 生效 ----------
_THIS_DIR = Path(__file__).resolve().parent
_VC_ROOT = _THIS_DIR.parent
if str(_VC_ROOT) not in sys.path:
    sys.path.insert(0, str(_VC_ROOT))

from core.pipeline import PipelineConfig, PipelineResult, PipelineRunner, parse_video_id  # noqa: E402
from utils.logger import get_crawler_logger  # noqa: E402

logger = get_crawler_logger()

# =====================================================
# 安全：启动时生成一次性 API key（也可通过环境变量固定）
# =====================================================
API_KEY = os.environ.get("VC_WEB_API_KEY") or secrets.token_urlsafe(16)

# =====================================================
# 全局任务状态 & 日志流
# =====================================================

class TaskStore:
    """单任务槽：同一时刻只跑一个任务，新任务排队"""

    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.running: bool = False
        self.task_id: Optional[str] = None
        self.task_type: str = ""          # single / search / publish
        self.started_at: float = 0.0
        self.progress: str = "idle"       # idle / running / done / error
        self.result: Optional[Dict[str, Any]] = None
        self.errors: List[str] = []
        # SSE 广播用的队列集合
        self.subscribers: List["queue.Queue[str]"] = []
        # 环形日志缓冲（供新连接回放）
        self.log_buffer: deque[str] = deque(maxlen=500)

    # ---------- 日志 ----------
    def push_log(self, msg: str) -> None:
        line = f"[{time.strftime('%H:%M:%S')}] {msg}"
        self.log_buffer.append(line)
        # 广播给所有 SSE 订阅者
        dead = []
        for q in self.subscribers:
            try:
                q.put_nowait(line)
            except queue.Full:
                dead.append(q)
        for q in dead:
            self.subscribers.remove(q)

    def subscribe(self) -> "queue.Queue[str]":
        q: "queue.Queue[str]" = queue.Queue(maxsize=512)
        with self.lock:
            self.subscribers.append(q)
        return q

    def unsubscribe(self, q: "queue.Queue[str]") -> None:
        with self.lock:
            if q in self.subscribers:
                self.subscribers.remove(q)

    # ---------- 任务生命周期 ----------
    def try_acquire(self, task_type: str) -> Optional[str]:
        with self.lock:
            if self.running:
                return None
            self.running = True
            self.task_id = uuid.uuid4().hex[:10]
            self.task_type = task_type
            self.started_at = time.time()
            self.progress = "running"
            self.result = None
            self.errors = []
            return self.task_id

    def release(self, progress: str, result: Optional[Dict] = None, errors: Optional[List[str]] = None) -> None:
        with self.lock:
            self.running = False
            self.progress = progress
            self.result = result
            if errors:
                self.errors.extend(errors)

    def snapshot(self) -> Dict[str, Any]:
        with self.lock:
            return {
                "running": self.running,
                "task_id": self.task_id,
                "task_type": self.task_type,
                "started_at": self.started_at,
                "elapsed_sec": round(time.time() - self.started_at, 1) if self.running else 0,
                "progress": self.progress,
                "result": self.result,
                "errors": self.errors[-10:],
            }


TASKS = TaskStore()


# =====================================================
# Pydantic 请求体
# =====================================================

class SingleVideoRequest(BaseModel):
    url: str = Field(..., description="YouTube / TikTok / 抖音链接，或 11 位 YouTube video_id")
    language: str = Field("en", description="语言代码：en / de / ja 等")
    target_lang: str = Field("zh-CN", description="翻译目标语言")
    analyze: bool = Field(True, description="是否生成文案")


class SearchRequest(BaseModel):
    mode: str = Field("language", description="language / keyword / channel")
    language: str = Field("en")
    keyword: str = Field("")
    channel: str = Field("")
    count: int = Field(5, ge=1, le=50)
    target_lang: str = Field("zh-CN")
    analyze: bool = Field(True)
    min_duration: int = Field(90)
    max_duration: int = Field(600)


# =====================================================
# FastAPI 应用
# =====================================================

@asynccontextmanager
async def lifespan(app: FastAPI):
    # 把 nodejs / ffmpeg 注入 PATH（yt-dlp 解签名必须要 node）
    from utils.path_helper import ensure_tools_in_path
    ensure_tools_in_path()
    logger.info(f"PATH 已注入: {os.environ.get('PATH', '')[:200]}...")

    # 启动时刷新一次 CDP cookies（Edge 在跑，直接从 9222 拉）
    try:
        from core.cdp_cookies import auto_refresh_cookies
        ok = auto_refresh_cookies(port=9222)
        logger.info(f"CDP cookie 刷新: {ok}")
    except Exception as e:
        logger.warning(f"CDP cookie 刷新跳过: {e}")

    logger.info(f"🌐 Web 接口启动 — API key: {_mask_key(API_KEY)}")
    TASKS.push_log(f"🌐 远程接口已就绪 · API key: {_mask_key(API_KEY)}")

    # 把发布队列的日志桥接到 SSE
    try:
        from core.publish.publish_queue import get_publish_queue
        get_publish_queue().add_log_observer(TASKS.push_log)
        TASKS.push_log("📤 发布队列已就绪")
    except Exception as e:
        logger.warning(f"发布队列注册跳过: {e}")

    # ── MQTT Bridge (远程控制主通道) ────────────────────────────
    _mqtt = None
    try:
        from web.mqtt_bridge import MqttBridge

        _mqtt = MqttBridge.instance()

        # 注入依赖 (避免循环 import web.main)
        _mqtt.set_dependencies(
            task_store=TASKS,
            log_push=TASKS.push_log,
            pipeline_single=lambda params: _run_single_from_mqtt(params),
            pipeline_search=lambda params: _run_search_from_mqtt(params),
            stop_current=lambda: TASKS.push_log("⏹ MQTT stop 已记录 (当前任务会在当前视频结束后退出)"),
            publish_enqueue=None,  # mqtt_bridge 内部直接 import publish_queue
        )

        # 桥接: TASKS.push_log 同时推 MQTT log topic
        _orig_push = TASKS.push_log
        def _dual_push(msg: str) -> None:
            _orig_push(msg)
            _mqtt.bridge_task_log(msg)
        TASKS.push_log = _dual_push  # type: ignore[assignment]

        _mqtt.start()
        TASKS.push_log(f"📡 MQTT Bridge 已启动 · device={_mqtt.device_id} · broker=broker.emqx.io:1883")
    except Exception as e:
        logger.warning(f"[MQTT] bridge 启动跳过: {e}")
        _mqtt = None

    yield

    # 清理
    if _mqtt:
        try:
            _mqtt.stop()
        except Exception:
            pass


# ── MQTT bridge 需要的流水线包装 (复用 _run_single / _run_search) ──

def _run_single_from_mqtt(params: dict) -> dict:
    """MQTT pipeline_single 指令入口 — 等价于 SingleVideoRequest"""
    req = SingleVideoRequest(
        url=params["url"],
        language=params.get("language", "en"),
        target_lang=params.get("target_lang", "zh-CN"),
        analyze=params.get("analyze", True),
    )
    if TASKS.try_acquire("single") is None:
        return {"ok": False, "error": "已有任务在执行中"}

    def _worker():
        try:
            out = _run_single(req)
            TASKS.release("done" if out["ok"] else "error", result=out, errors=out.get("errors"))
            TASKS.push_log(f"✅ 单视频任务结束：{out}")
        except Exception as e:
            TASKS.push_log(f"💥 单视频任务异常: {e}")
            TASKS.release("error", errors=[str(e)])

    spawn(target=_worker, daemon=True).start()
    return {"ok": True, "msg": "单视频任务已启动"}


def _run_search_from_mqtt(params: dict) -> dict:
    req = SearchRequest(
        mode=params.get("mode", "language"),
        language=params.get("language", "en"),
        keyword=params.get("keyword", ""),
        channel=params.get("channel", ""),
        count=params.get("count", 5),
        target_lang=params.get("target_lang", "zh-CN"),
        analyze=params.get("analyze", True),
        min_duration=params.get("min_duration", 90),
        max_duration=params.get("max_duration", 600),
    )
    if TASKS.try_acquire("search") is None:
        return {"ok": False, "error": "已有任务在执行中"}

    def _worker():
        try:
            out = _run_search(req)
            TASKS.release("done" if out["ok"] else "error", result=out, errors=out.get("errors"))
            TASKS.push_log(f"✅ 搜索流水线结束：{out}")
        except Exception as e:
            TASKS.push_log(f"💥 搜索流水线异常: {e}")
            TASKS.release("error", errors=[str(e)])

    spawn(target=_worker, daemon=True).start()
    return {"ok": True, "msg": "搜索流水线已启动"}


app = FastAPI(title="VideoCrawler Remote", version="1.0", lifespan=lifespan)

# 挂载静态前端
_STATIC_DIR = _THIS_DIR / "static"
_STATIC_DIR.mkdir(exist_ok=True)
app.mount("/static", StaticFiles(directory=str(_STATIC_DIR)), name="static")


class _AuthMiddleware(BaseHTTPMiddleware):
    """统一鉴权中间件：所有 /api/* 请求都要校验 API key。

    支持两种传 key 方式（优先 Bearer 头，不进浏览器历史/Referer）：
      - Authorization: Bearer <key>
      - ?key=<key>（兼容旧前端）
    首页 / 和静态资源 /static/* 免鉴权。
    """

    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        if path == "/" or path.startswith("/static/"):
            return await call_next(request)

        q_key = request.query_params.get("key")
        auth_hdr = request.headers.get("authorization", "")
        h_key = None
        if auth_hdr and auth_hdr.lower().startswith("bearer "):
            h_key = auth_hdr[7:].strip()
        token = h_key or q_key

        if not token or token != API_KEY:
            return JSONResponse(status_code=401, content={"ok": False, "error": "无效的 API key"})

        return await call_next(request)


app.add_middleware(_AuthMiddleware)


# ---------- 认证 ----------
def _auth(key: Optional[str] = None, authorization: Optional[str] = None) -> None:
    """API Key 鉴权：支持 query 参数 ?key=xxx 和 Authorization: Bearer xxx 头两种方式。

    优先取 Bearer 头（不进浏览器历史/Referer），query 兼容旧前端。
    """
    token_from_header = None
    if authorization:
        # "Bearer xxx" → "xxx"
        token_from_header = authorization[7:] if authorization.startswith("Bearer ") else authorization
    candidate = token_from_header or key
    if not candidate or candidate != API_KEY:
        raise HTTPException(status_code=401, detail="无效的 API key")


def _mask_key(k: str) -> str:
    """日志脱敏：只打前 4 位"""
    return k[:4] + "****" + k[-4:] if len(k) > 8 else "****"


# ---------- 首页 ----------
@app.get("/", response_class=HTMLResponse)
async def index():
    html_path = _STATIC_DIR / "index.html"
    if html_path.exists():
        return HTMLResponse(content=html_path.read_text(encoding="utf-8"))
    return HTMLResponse(content="<h1>VideoCrawler Remote</h1><p>前端文件缺失</p>")


# ---------- API: 健康 & 状态 ----------
@app.get("/api/health")
async def health(key: Optional[str] = Query(None)):
    # middleware 已统一鉴权，无需二次校验
    return {"ok": True, "time": time.strftime("%Y-%m-%d %H:%M:%S")}


@app.get("/api/status")
async def get_status(key: Optional[str] = Query(None)):
    # middleware 已统一鉴权，无需二次校验
    return TASKS.snapshot()


@app.get("/api/logs")
async def stream_logs(key: Optional[str] = Query(None)):
    """SSE 日志流"""
    # middleware 已统一鉴权，无需二次校验
    q = TASKS.subscribe()

    async def gen():
        try:
            # 先回放历史
            for line in list(TASKS.log_buffer):
                yield f"data: {line}\n\n"
            # 持续推送
            loop = asyncio.get_event_loop()
            while True:
                try:
                    line = await loop.run_in_executor(None, q.get, True, 30)
                    yield f"data: {line}\n\n"
                except queue.Empty:
                    yield f": ping\n\n"  # 保持连接
        finally:
            TASKS.unsubscribe(q)

    return StreamingResponse(gen(), media_type="text/event-stream")


# ---------- API: 流水线（单视频/搜索）----------
def _find_cover_near(video_path: str) -> str:
    """在成品视频同目录找同名封面图（轻量版，找不到返回空串）"""
    base = os.path.splitext(os.path.basename(video_path))[0]
    d = os.path.dirname(video_path)
    try:
        for ext in (".jpg", ".jpeg", ".png", ".webp"):
            cand = os.path.join(d, base + ext)
            if os.path.exists(cand):
                return cand
    except Exception:
        pass
    return ""


def _pool_finished_videos(result) -> int:
    """流水线完成后把烧录成品登记进视频候选池（供发布页选取）。

    与 GUI 自动管线行为一致：仅字幕/烧录成功（sub_ok）且成品文件存在的
    视频入池。入池失败只记日志，不影响主流程。
    """
    from core.publish.pool import VideoPool

    added = 0
    for v in getattr(result, "downloaded_videos", []) or []:
        try:
            if not v.get("sub_ok"):
                continue
            final_path = v.get("local_video_path") or ""
            if not final_path or not os.path.exists(final_path):
                continue
            pool_id = VideoPool.add(
                final_video_path=final_path,
                source_url=v.get("source_url", ""),
                video_id=v.get("youtube_id", ""),
                cover_path=_find_cover_near(final_path),
                srt_path=v.get("srt_path", ""),
                title_original=v.get("title", ""),
                desc_original="",
                lang=v.get("lang", ""),
                category=v.get("category", ""),
                channel_name=v.get("channel", ""),
                pipeline_source="auto",
            )
            if pool_id:
                added += 1
                TASKS.push_log(f"📦 成品已入发布候选池: pool_id={pool_id} · {os.path.basename(final_path)}")
        except Exception as e:
            TASKS.push_log(f"⚠ 成品入池失败（不影响主流程）: {e}")
    return added


def _run_single(req: SingleVideoRequest) -> Dict[str, Any]:
    vid = parse_video_id(req.url)
    if not vid:
        return {"ok": False, "error": f"无法解析 video_id: {req.url}"}

    TASKS.push_log(f"🎯 开始单视频全自动：{vid}")
    cfg = PipelineConfig()
    cfg.search_mode = PipelineConfig.SEARCH_MODE_SINGLE
    cfg.single_video_url = req.url
    cfg.language = req.language
    cfg.target_lang = req.target_lang
    cfg.analyze_content = req.analyze
    cfg.video_count = 1
    cfg.min_duration = None   # 单视频跳过时长检查
    cfg.max_duration = None

    runner = PipelineRunner()
    runner.set_progress_callback(TASKS.push_log)
    result = runner.run(cfg)
    _pool_finished_videos(result)

    return {
        "ok": result.status == "completed",
        "downloaded": result.downloaded,
        "subtitled": result.subtitled,
        "analyzed": result.analyzed,
        "errors": result.errors,
    }


@app.post("/api/pipeline/single")
async def api_pipeline_single(req: SingleVideoRequest, key: Optional[str] = Query(None)):
    # middleware 已统一鉴权，无需二次校验
    if TASKS.try_acquire("single") is None:
        raise HTTPException(status_code=409, detail="已有任务在执行中")

    def _worker():
        try:
            out = _run_single(req)
            TASKS.release("done" if out["ok"] else "error", result=out, errors=out.get("errors"))
            TASKS.push_log(f"✅ 单视频任务结束：{out}")
        except Exception as e:
            TASKS.push_log(f"💥 单视频任务异常: {e}")
            TASKS.release("error", errors=[str(e)])

    spawn(target=_worker, daemon=True).start()
    return {"ok": True, "msg": "单视频任务已启动"}


# ---------- API: 搜索/批量流水线 ----------
def _run_search(req: SearchRequest) -> Dict[str, Any]:
    cfg = PipelineConfig()
    cfg.search_mode = req.mode
    cfg.language = req.language
    cfg.search_keyword = req.keyword
    cfg.channel_identifier = req.channel
    cfg.video_count = req.count
    cfg.target_lang = req.target_lang
    cfg.analyze_content = req.analyze
    cfg.min_duration = req.min_duration
    cfg.max_duration = req.max_duration

    runner = PipelineRunner()
    runner.set_progress_callback(TASKS.push_log)
    result = runner.run(cfg)
    _pool_finished_videos(result)

    return {
        "ok": result.status == "completed",
        "crawled": result.crawled,
        "downloaded": result.downloaded,
        "subtitled": result.subtitled,
        "analyzed": result.analyzed,
        "errors": result.errors,
    }


@app.post("/api/pipeline/search")
async def api_pipeline_search(req: SearchRequest, key: Optional[str] = Query(None)):
    # middleware 已统一鉴权，无需二次校验
    if TASKS.try_acquire("search") is None:
        raise HTTPException(status_code=409, detail="已有任务在执行中")

    def _worker():
        try:
            out = _run_search(req)
            TASKS.release("done" if out["ok"] else "error", result=out, errors=out.get("errors"))
            TASKS.push_log(f"✅ 搜索流水线结束：{out}")
        except Exception as e:
            TASKS.push_log(f"💥 搜索流水线异常: {e}")
            TASKS.release("error", errors=[str(e)])

    spawn(target=_worker, daemon=True).start()
    return {"ok": True, "msg": "搜索流水线已启动"}


# ---------- API: 列出 output 视频 ----------
@app.get("/api/videos")
async def list_videos(key: Optional[str] = Query(None), limit: int = Query(20, le=100)):
    # middleware 已统一鉴权，无需二次校验
    out_root = _VC_ROOT / "output"
    videos: List[Dict[str, Any]] = []
    if not out_root.is_dir():
        return {"videos": videos}

    # 扫 output 下的 mp4（跳过子目录里的中间文件如 .part / .temp）
    mp4s = sorted(out_root.rglob("*.mp4"), key=lambda p: p.stat().st_mtime, reverse=True)
    for p in mp4s[:limit]:
        videos.append({
            "name": p.name,
            "path": str(p.relative_to(out_root)),
            "size_mb": round(p.stat().st_size / 1024 / 1024, 1),
            "mtime": time.strftime("%Y-%m-%d %H:%M", time.localtime(p.stat().st_mtime)),
            "has_srt": any(p.with_suffix(".srt").parent.glob(p.stem + "*.srt")),
        })
    return {"videos": videos}


# ---------- API: 停止当前任务 ----------
@app.post("/api/stop")
async def stop_task(key: Optional[str] = Query(None)):
    # middleware 已统一鉴权，无需二次校验
    # 注意：PipelineRunner 内部没有 cancel 标志，这里只能标记状态；
    # 真正的中断需要线程自然退出。
    TASKS.push_log("⏹ 收到停止请求（当前任务会在当前视频结束后退出）")
    return {"ok": True, "msg": "停止请求已记录"}


# =====================================================
# API: 自动发布（新增）
# =====================================================

class PublishRequest(BaseModel):
    """手机端发布请求：选视频 + 选账号 + 可选覆盖标题/描述"""
    video_path: str = Field(..., description="output 下的相对路径，如 'de/xxx/xxx.mp4'")
    account_id: int = Field(..., description="publish_account.id")
    title: Optional[str] = Field(None, description="覆盖标题（留空用 AI 生成的）")
    description: Optional[str] = Field(None, description="覆盖描述")
    tags: Optional[List[str]] = Field(default_factory=list, description="话题标签")
    original: bool = Field(True, description="勾选原创声明")


@app.get("/api/platforms")
async def api_platforms(key: Optional[str] = Query(None)):
    """返回所有已配置的发布账号"""
    from core.publish.accounts import AccountManager
    try:
        accounts = AccountManager.list_accounts(only_active=False)
        # 脱敏：cookie 不返回
        for a in accounts:
            a.pop("cookies", None)
        return {"ok": True, "accounts": accounts}
    except Exception as e:
        return {"ok": False, "error": str(e)}


@app.post("/api/publish")
async def api_publish(req: PublishRequest, key: Optional[str] = Query(None)):
    """一键发布视频到指定平台"""
    if TASKS.try_acquire("publish") is None:
        raise HTTPException(status_code=409, detail="已有任务在执行中")

    def _worker():
        from core.publish.accounts import AccountManager
        from core.publish.clients import VideoMeta, PlatformClientFactory, normalize_tags

        try:
            # 1. 视频路径修正
            video_full = _VC_ROOT / "output" / req.video_path
            if not video_full.exists():
                TASKS.push_log(f"❌ 视频不存在: {video_full}")
                TASKS.release("error", errors=[f"视频不存在: {req.video_path}"])
                return

            # 2. 加载账号
            acc = AccountManager.get_account(req.account_id)
            if not acc:
                TASKS.push_log(f"❌ 账号不存在: account_id={req.account_id}")
                TASKS.release("error", errors=["账号不存在"])
                return

            platform = acc["platform"]
            TASKS.push_log(f"📤 开始发布 → {platform} · 账号 {acc.get('nickname','?')} · {video_full.name}")

            # 3. 构造 VideoMeta
            meta = VideoMeta()
            meta.title = req.title or ""
            meta.description = req.description or ""
            meta.tags = normalize_tags(req.tags)
            meta.original_declaration = req.original
            meta.video_path = str(video_full)

            # 4. 进度回调（bridge 到 SSE）
            def _progress(uploaded: int, total: int):
                pct = round(uploaded / total * 100, 1) if total else 0
                TASKS.push_log(f"📊 上传进度: {pct}% ({uploaded}/{total})")

            # 5. 直接调 client（不经过 pool，因为手机端没 pool 概念）
            client = PlatformClientFactory.create(platform, cookies=acc["cookies"])
            result = client.upload_video(str(video_full), meta, progress_cb=_progress)

            if result.success:
                TASKS.push_log(f"✅ 发布成功！remote_id={result.remote_id} remote_url={result.remote_url}")
                TASKS.release("done", result={
                    "platform": platform,
                    "remote_id": result.remote_id,
                    "remote_url": result.remote_url,
                    "duration_ms": result.duration_ms,
                })
            else:
                TASKS.push_log(f"❌ 发布失败: {result.error_msg}")
                TASKS.release("error", errors=[result.error_msg])

        except Exception as e:
            import traceback
            TASKS.push_log(f"💥 发布异常: {e}\n{traceback.format_exc()}")
            TASKS.release("error", errors=[str(e)])

    spawn(target=_worker, daemon=True).start()
    return {"ok": True, "msg": "发布任务已启动"}


# =====================================================
# API: 服务自身控制（手机端重启/健康检查）
# =====================================================

@app.get("/api/server/health")
async def api_server_health(key: Optional[str] = Query(None)):
    """详细健康检查（比 /api/health 多进程/版本信息）"""
    import platform
    try:
        # 检查 playwright + 账号
        from core.publish.accounts import AccountManager
        accs = AccountManager.list_accounts(only_active=False)
    except Exception:
        accs = []

    return {
        "ok": True,
        "time": time.strftime("%Y-%m-%d %H:%M:%S"),
        "platform": platform.platform(),
        "python": platform.python_version(),
        "pid": os.getpid(),
        "api_key_masked": _mask_key(API_KEY),
        "accounts_count": len(accs),
        "running_task": TASKS.task_type,
        "running": TASKS.running,
        # AUDIT-0012: 响应体不回显明文 key
        "local_url": f"http://localhost:8000/?key={_mask_key(API_KEY)}",
        "lan_url": f"http://<本机IP>:8000/?key={_mask_key(API_KEY)}",
    }


@app.post("/api/server/restart")
async def api_server_restart(key: Optional[str] = Query(None)):
    """内嵌模式下 web 服务随 GUI 进程存活, 不支持远程重启 (AUDIT-0064)"""
    return JSONResponse(
        status_code=503,
        content={"ok": False, "error": "内嵌模式不支持远程重启，请通过 GUI 退出"},
    )


# =====================================================
# API: MQTT Bridge 管理 (远程控制主通道)
# =====================================================

@app.get("/api/mqtt/info")
async def api_mqtt_info(key: Optional[str] = Query(None)):
    """返回 MQTT 设备信息 (device_id + token + 连接状态 + 二维码 URL)"""
    try:
        from web.mqtt_bridge import MqttBridge
        bridge = MqttBridge.instance()
        info = bridge.status()
        info["token"] = bridge.token  # API key 已校验, 这里给全量
        info["qr_url"] = bridge.get_qr_url()
        return {"ok": True, **info}
    except Exception as e:
        return {"ok": False, "error": str(e)}


@app.get("/api/mqtt/status")
async def api_mqtt_status(key: Optional[str] = Query(None)):
    """MQTT 连接状态快照"""
    try:
        from web.mqtt_bridge import get_bridge
        bridge = get_bridge()
        if bridge is None:
            return {"ok": True, "connected": False, "msg": "bridge 未启动"}
        return {"ok": True, **bridge.status()}
    except Exception as e:
        return {"ok": False, "error": str(e)}


@app.post("/api/mqtt/restart")
async def api_mqtt_restart(key: Optional[str] = Query(None)):
    """手动重连 MQTT"""
    try:
        from web.mqtt_bridge import get_bridge
        bridge = get_bridge()
        if bridge is None:
            return {"ok": False, "error": "bridge 未启动"}
        ok = bridge.restart()
        return {"ok": ok, "connected": bridge._connected}
    except Exception as e:
        return {"ok": False, "error": str(e)}


# =====================================================
# API: 自动发布队列（publish_queue.py）
# =====================================================

class QueuePublishItem(BaseModel):
    """队列里的单个发布项"""
    pool_id: int = Field(..., description="video_pool.id")
    account_id: int = Field(..., description="publish_account.id")
    title: Optional[str] = Field(None, description="覆盖标题（None 用池里的）")
    description: Optional[str] = Field(None, description="覆盖描述")
    tags: Optional[List[str]] = Field(default_factory=list, description="话题标签")
    scheduled_ts: Optional[int] = Field(None, description="定时发布时间戳（秒）")
    original: bool = Field(True, description="原创声明")


class QueueEnqueueRequest(BaseModel):
    """批量入队请求"""
    items: List[QueuePublishItem] = Field(..., min_length=1, description="要入队的发布项列表")


# ---------- 视频池 API ----------
@app.get("/api/pool")
async def api_pool(
    key: Optional[str] = Query(None),
    only_unpublished: bool = Query(False, description="只看未发布的"),
    limit: int = Query(50, le=200),
):
    """列出视频池（带发布状态）"""
    from core.publish.pool import VideoPool
    from core.publish import POOL_STATUS, PLATFORMS
    try:
        items = VideoPool.list_all()
        if only_unpublished:
            items = [i for i in items if i.get("publish_status", 0) in (0, 2, 3)]

        result = []
        for it in items[:limit]:
            fp = it.get("final_video_path", "")
            size_mb = round(os.path.getsize(fp) / 1024 / 1024, 1) if fp and os.path.exists(fp) else 0
            title = it.get("title_translated") or it.get("title_original") or os.path.basename(fp)
            status = it.get("publish_status", 0)
            platforms_done = it.get("published_platforms", "")
            try:
                platforms_done = json.loads(platforms_done) if platforms_done else []
            except Exception:
                platforms_done = []

            result.append({
                "pool_id": it["id"],
                "title": title[:60],
                "video_file": os.path.basename(fp),
                "size_mb": size_mb,
                "duration_sec": it.get("duration_sec", 0),
                "source": it.get("pipeline_source", "manual"),
                "status_code": status,
                "status_label": POOL_STATUS.get(status, "?"),
                "published_platforms": platforms_done,
                "has_copy": bool(it.get("copy_path")),
                "create_ts": it.get("create_ts", 0),
                "create_time": time.strftime("%m-%d %H:%M", time.localtime(it.get("create_ts", 0))) if it.get("create_ts") else "",
            })
        return {"ok": True, "total": len(items), "items": result}
    except Exception as e:
        import traceback
        return {"ok": False, "error": str(e), "trace": traceback.format_exc()[:300]}


@app.get("/api/pool/{pool_id}/file")
async def api_pool_file(pool_id: int, kind: str = Query("video")):
    """下载候选池里的成品视频 / 封面

    - kind=video（默认）| cover
    - middleware 已统一鉴权（?key= 或 Authorization: Bearer）
    - 手机端通过局域网地址访问，因此手机需与电脑在同一 WiFi
    """
    from core.publish.pool import VideoPool

    if kind not in ("video", "cover"):
        raise HTTPException(status_code=400, detail=f"kind 只能是 video / cover，收到: {kind}")

    try:
        item = VideoPool.get(pool_id)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"读取候选池失败: {e}") from e

    if not item:
        raise HTTPException(status_code=404, detail=f"候选池条目不存在: pool_id={pool_id}")

    path = (item.get("cover_path") if kind == "cover" else item.get("final_video_path")) or ""
    if not path or not os.path.exists(path):
        raise HTTPException(status_code=404, detail=f"{'封面' if kind == 'cover' else '视频'}文件不存在（可能已被移动或删除）")

    media_type = mimetypes.guess_type(path)[0] or "application/octet-stream"
    # filename 参数会让 Starlette 生成 Content-Disposition: attachment，浏览器直接下载
    return FileResponse(path, media_type=media_type, filename=os.path.basename(path))


# ---------- 发布队列状态 ----------
@app.get("/api/publish/queue")
async def api_publish_queue_status(key: Optional[str] = Query(None)):
    """查询发布队列状态（当前 + 排队 + 最近 30 条历史）"""
    from core.publish.publish_queue import get_publish_queue
    return get_publish_queue().snapshot()


# ---------- 批量入队 ----------
@app.post("/api/publish/queue")
async def api_publish_queue_enqueue(req: QueueEnqueueRequest, key: Optional[str] = Query(None)):
    """批量入队：把多个 pool_id + account_id 组合加入发布队列"""
    from core.publish.publish_queue import get_publish_queue, PublishJob

    q = get_publish_queue()
    jobs = []
    for item in req.items:
        job = PublishJob(
            pool_id=item.pool_id,
            account_id=item.account_id,
            title=item.title,
            description=item.description,
            tags=item.tags or None,
            scheduled_ts=item.scheduled_ts,
            original=item.original,
        )
        jobs.append(job)

    ids = q.enqueue_batch(jobs)
    return {
        "ok": True,
        "enqueued": len(ids),
        "job_ids": ids,
        "queue_size": q.queue_size(),
    }


# ---------- 定时发布（单条便捷入口） ----------
@app.post("/api/publish/schedule")
async def api_publish_schedule(req: QueuePublishItem, key: Optional[str] = Query(None)):
    """单条定时发布（其实就是 scheduled_ts 不为 None 的入队）"""
    from core.publish.publish_queue import get_publish_queue, PublishJob

    if not req.scheduled_ts or req.scheduled_ts <= int(time.time()):
        return {"ok": False, "error": "scheduled_ts 必须是未来的时间戳"}

    job = PublishJob(
        pool_id=req.pool_id,
        account_id=req.account_id,
        title=req.title,
        description=req.description,
        tags=req.tags or None,
        scheduled_ts=req.scheduled_ts,
        original=req.original,
    )
    job_id = get_publish_queue().enqueue(job)
    return {
        "ok": True,
        "job_id": job_id,
        "scheduled_for": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(req.scheduled_ts)),
    }


# ---------- 队列管理 ----------
@app.post("/api/publish/queue/clear")
async def api_publish_queue_clear(key: Optional[str] = Query(None)):
    """清空待发布队列（不影响正在上传的）"""
    from core.publish.publish_queue import get_publish_queue
    n = get_publish_queue().clear()
    return {"ok": True, "cleared": n}


@app.post("/api/publish/queue/cancel")
async def api_publish_queue_cancel(req: Dict[str, str], key: Optional[str] = Query(None)):
    """取消队列中的某个 job_id"""
    from core.publish.publish_queue import get_publish_queue
    job_id = req.get("job_id", "")
    if not job_id:
        return {"ok": False, "error": "缺少 job_id"}
    ok = get_publish_queue().cancel_job(job_id)
    return {"ok": ok, "job_id": job_id}


# ---------- 发布历史 ----------
@app.get("/api/publish-records")
async def api_publish_records(
    key: Optional[str] = Query(None),
    limit: int = Query(50, le=200),
    status: Optional[int] = Query(None, description="1=成功 2=失败"),
):
    """查看发布记录"""
    from core.publish import storage as pub_storage
    from core.publish import RECORD_STATUS, PLATFORMS
    try:
        records = pub_storage.list_publish_records(limit=limit * 3)
        if status is not None:
            records = [r for r in records if r.get("status") == status]

        # 取最近 limit 条
        records = records[:limit]
        result = []
        for r in records:
            platform = r.get("platform", "")
            pinfo = PLATFORMS.get(platform, {})
            ts = r.get("create_ts", 0)
            result.append({
                "record_id": r["id"],
                "pool_id": r.get("pool_id"),
                "account_id": r.get("account_id"),
                "platform": platform,
                "platform_label": pinfo.get("label", platform),
                "title": (r.get("title") or "")[:50],
                "status_code": r.get("status"),
                "status_label": RECORD_STATUS.get(r.get("status", 0), "?"),
                "remote_id": r.get("remote_id", ""),
                "error_msg": (r.get("error_msg") or "")[:200],
                "scheduled_ts": r.get("scheduled_ts"),
                "create_time": time.strftime("%m-%d %H:%M:%S", time.localtime(ts)) if ts else "",
            })
        return {"ok": True, "records": result}
    except Exception as e:
        return {"ok": False, "error": str(e)}


# ---------- 启动入口 ----------
if __name__ == "__main__":
    import uvicorn
    print(f"\n🚀 VideoCrawler Web 启动中...")
    print(f"   API key: {API_KEY}")
    print(f"   访问:  http://<本机IP>:8000/?key={API_KEY}\n")
    uvicorn.run("web.main:app", host="0.0.0.0", port=8000, reload=False)


