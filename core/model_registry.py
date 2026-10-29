"""
ModelRegistry — 统一的大模型注册表 & 发现 & 连通性 & 能力打标

单一数据源：内置 3 个 provider + 用户自定义 provider 全部注册在这里。
GUI 从这里取按"功能"分组的可用模型列表；运行时从这里读用户勾选的模型链。

Provider 协议两种：
  1. gemini_generate_content — Google Gemini 原生 generateContent 端点
  2. openai_chat_completions  — OpenAI Chat Completions 兼容端点（Groq / GLM / 自定义）
"""

from __future__ import annotations

import threading
from utils.thread_spawn import spawn  # AUDIT-0033
import time
from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional, Any, Set, Tuple

import requests

# ---------------------------------------------------------------------------
# Qt lazy import — 让 core 模块在 headless（无 PySide6）环境也能 import
# ---------------------------------------------------------------------------
try:
    from PySide6.QtCore import QObject as _QObject, Signal as _QtSignal
    _HAS_QT = True
except ImportError:
    _HAS_QT = False

    class _QObject:
        """Qt 不存在时的空基类，支持 super().__init__()"""
        pass

    class _SignalStub:
        """Qt Signal 的空 stub —— emit/connect/disconnect 全是 no-op"""
        def __init__(self, *args, **kwargs):
            pass
        def emit(self, *a, **kw):
            pass
        def connect(self, *a, **kw):
            pass
        def disconnect(self, *a, **kw):
            pass

    def _QtSignal(*args, **kwargs):
        return _SignalStub(*args, **kwargs)

from utils.logger import get_crawler_logger
from utils.config_loader import load_config, DEFAULT_CONFIG

logger = get_crawler_logger()


# ---------------------------------------------------------------------------
# ProviderSpec — 统一 provider 定义（内置 + 自定义共用一个 schema）
# ---------------------------------------------------------------------------

@dataclass
class ProviderSpec:
    id: str                                    # 唯一 ID（如 "gemini" / "groq" / "custom_1"）
    name: str                                  # 显示名（如 "Gemini" / "Groq"）
    protocol: str                              # "gemini_generate_content" | "openai_chat_completions"
    icon: str = "🤖"                           # emoji 图标
    api_key: str = ""                          # API Key
    enabled: bool = False                      # 是否启用
    base_url: str = ""                         # 协议根地址（如 "https://api.groq.com/openai/v1"）
    user_agent: Optional[str] = None            # 可选 UA 覆盖（Groq Cloudflare 需要 curl UA）
    models_path_override: Optional[str] = None # 可选：覆盖默认的 /models 端点路径
    chat_path_override: Optional[str] = None   # 可选：覆盖默认的 chat 端点路径
    is_builtin: bool = False                   # 是否内置（内置的 URL/协议不可改）
    description: str = ""                      # 可选描述

    # --- 衍生 ---
    @property
    def chat_url(self) -> str:
        if self.protocol == "gemini_generate_content":
            # 例如 https://generativelanguage.googleapis.com/v1beta/models/{m}:generateContent
            base = self.base_url.rstrip("/")
            return f"{base}/v1beta/models/{{m}}:generateContent"
        if self.chat_path_override:
            return self.chat_path_override.format(base_url=self.base_url.rstrip("/"))
        # openai_chat_completions 默认
        base = self.base_url.rstrip("/")
        return f"{base}/chat/completions"

    @property
    def models_url(self) -> str:
        if self.protocol == "gemini_generate_content":
            base = self.base_url.rstrip("/")
            return f"{base}/v1beta/models"
        if self.models_path_override:
            return self.models_path_override.format(base_url=self.base_url.rstrip("/"))
        base = self.base_url.rstrip("/")
        return f"{base}/models"

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "ProviderSpec":
        return cls(
            id=str(d.get("id", "")),
            name=str(d.get("name", "")),
            protocol=str(d.get("protocol", "openai_chat_completions")),
            icon=str(d.get("icon", "🤖")),
            api_key=str(d.get("api_key", "")),
            enabled=bool(d.get("enabled", False)),
            base_url=str(d.get("base_url", "")),
            user_agent=d.get("user_agent"),
            models_path_override=d.get("models_path_override"),
            chat_path_override=d.get("chat_path_override"),
            is_builtin=bool(d.get("is_builtin", False)),
            description=str(d.get("description", "")),
        )

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# ---------------------------------------------------------------------------
# 内置 provider 定义（protocol / base_url 等不可改；api_key / enabled 可由用户填写）
# ---------------------------------------------------------------------------

BUILTIN_PROVIDERS: List[ProviderSpec] = [
    ProviderSpec(
        id="gemini",
        name="Gemini",
        protocol="gemini_generate_content",
        icon="🌀",
        base_url="https://generativelanguage.googleapis.com",
        is_builtin=True,
        description="Google Gemini 原生 API — 唯一支持 video 输入的模型提供商",
    ),
    ProviderSpec(
        id="groq",
        name="Groq",
        protocol="openai_chat_completions",
        icon="⚡",
        base_url="https://api.groq.com/openai/v1",
        user_agent="curl/8.7.1",   # Cloudflare WAF 强制
        is_builtin=True,
        description="Groq 免费层 LLM — 当前 Key 可用 qwen/gpt-oss 系列",
    ),
    ProviderSpec(
        id="glm",
        name="智谱 GLM",
        protocol="openai_chat_completions",
        icon="🧠",
        base_url="https://open.bigmodel.cn/api/paas/v4",
        is_builtin=True,
        description="智谱 AI — 当前 Key 可用 glm-5.x / glm-4.x 全系列",
    ),
    ProviderSpec(
        id="free.ai",
        name="free.ai",
        protocol="openai_chat_completions",
        icon="🖼️",
        base_url="https://api.free.ai/v1",
        is_builtin=True,
        description="free.ai — 免费 30k tokens/天 · 含图片编辑 / chat / vision / video 全品类",
    ),
]


# ---------------------------------------------------------------------------
# ModelInfo — 发现到的单个模型
# ---------------------------------------------------------------------------

@dataclass
class ModelInfo:
    provider_id: str                           # 所属 provider
    name: str                                  # 模型名（如 "gemini-3-flash-preview"）
    capabilities: Set[str] = field(default_factory=set)  # {"text", "multimodal", "video", "audio", ...}
    ok: Optional[bool] = None                  # 连通性：True/False/None(未测)
    ok_message: str = ""                        # 连通性详细消息
    last_checked: float = 0.0                   # 上次测试 unix time
    type_hint: str = ""                         # free.ai 等平台返回的原始 type 字段（chat/image/image_edit/vision/tts/stt/ocr/...）
    skip_probe: bool = False                    # True = 跳过连通性探测（用户手动勾选）
    was_paid_pool: bool = False                 # True = 来自付费池（free.ai self_hosted=false），默认 skip_probe=True

    @property
    def is_video_provider(self) -> bool:
        """视频处理（ASR + 翻译）需要原生支持 video input 的模型"""
        return "video" in self.capabilities

    @property
    def is_audio_provider(self) -> bool:
        """纯音频 ASR（不涉及视频输入）"""
        return "audio" in self.capabilities

    @property
    def is_multimodal(self) -> bool:
        """广义多模态（任何 audio/video/vision）"""
        return bool(self.capabilities & {"video", "audio", "multimodal", "vision"})

    @property
    def is_text_provider(self) -> bool:
        """文字处理（文本对话）"""
        return "text" in self.capabilities

    def status_emoji(self) -> str:
        if self.skip_probe:
            return "🚫"
        if self.ok is True:
            return "✅"
        if self.ok is False:
            return "❌"
        if self.ok is None:
            return "⏳"
        return ""


# ---------------------------------------------------------------------------
# ModelRegistry — 全局单例（QObject，带信号供 GUI 订阅）
# ---------------------------------------------------------------------------

class ModelRegistry(_QObject):
    """全局模型注册表 & 发现 & 连通性 & 能力打标

    继承 _QObject（有 Qt 时为 PySide6.QtCore.QObject，否则为空 stub），
    所有 Signal 在无 Qt 时自动退化为 no-op stub。
    """

    models_discovered = _QtSignal(str)                        # provider_id 完成发现
    connectivity_changed = _QtSignal(str, str, object, str)   # (provider_id, model_name, ok|None, message)
    scan_finished = _QtSignal()                               # 所有 enabled provider 扫完
    function_models_changed = _QtSignal()                     # 用户勾选变更
    skip_probe_changed = _QtSignal(str, str, bool)            # (provider_id, model_name, skip)

    _instance: Optional["ModelRegistry"] = None
    _lock = threading.Lock()

    @classmethod
    def instance(cls) -> "ModelRegistry":
        with cls._lock:
            if cls._instance is None:
                cls._instance = cls()
            return cls._instance

    def __init__(self) -> None:
        super().__init__()
        self._providers: Dict[str, ProviderSpec] = {}         # id → ProviderSpec
        self._models: Dict[str, Dict[str, ModelInfo]] = {}   # provider_id → {model_name: ModelInfo}
        self._function_models: Dict[str, List[Dict[str, str]]] = {
            "video": [],                                       # [{provider, model}]
            "text": [],
        }
        self._skip_probe: Dict[str, Set[str]] = {}             # provider_id → {model_name, ...}
        self._unskip_probe: Dict[str, Set[str]] = {}           # provider_id → {model_name, ...}  (用户显式取消跳过)
        self._rw_lock = threading.Lock()

    # -----------------------------------------------------------------------
    # Provider CRUD
    # -----------------------------------------------------------------------

    def load_from_config(self) -> None:
        """从 config.yaml 加载 providers 和 function_models（自动做旧格式迁移）

        逻辑：
          1. 先把 BUILTIN_PROVIDERS 全部注册进 self._providers（id 匹配就用 BUILTIN 的协议/URL/icon）
          2. 再用 config.yaml 的 providers[] 逐条覆盖 api_key / enabled / icon
          3. 自定义 provider（不在 BUILTIN 里）直接注册
          4. 旧格式 gemini/groq/ai_writer 字段做兜底 api_key 读取
        """
        cfg = load_config()

        # —— Step 1: 先把所有内置 provider 注册为骨架 ——
        builtin_map: Dict[str, ProviderSpec] = {b.id: b for b in BUILTIN_PROVIDERS}
        for b in BUILTIN_PROVIDERS:
            self._providers[b.id] = ProviderSpec(
                id=b.id, name=b.name, protocol=b.protocol, icon=b.icon,
                base_url=b.base_url, is_builtin=True, description=b.description,
                user_agent=b.user_agent,
            )

        # —— Step 2: 再用 config.yaml 的 providers[] 覆盖 ——
        cfg_providers = cfg.get("providers", [])
        # 如果 config 里完全没有 providers[] 新结构 → 从旧格式迁移
        if not cfg_providers:
            cfg_providers = self._migrate_legacy_to_providers(cfg)

        for spec_dict in cfg_providers:
            spec = ProviderSpec.from_dict(spec_dict)
            existing = self._providers.get(spec.id)
            if existing and existing.is_builtin:
                # 内置 provider → 只覆盖可变字段（api_key/enabled/icon），协议/URL 保留 BUILTIN
                existing.api_key = spec.api_key or existing.api_key
                existing.enabled = spec.enabled
                if spec.icon and spec.icon != "🤖":
                    existing.icon = spec.icon
            else:
                # 自定义 provider → 直接注册（覆盖内置以防冲突）
                spec.is_builtin = False
                self._providers[spec.id] = spec

        # —— Step 3: 兜底 —— 内置 provider 如果 api_key 还空，再从旧字段读 ——
        for bid in builtin_map:
            prov = self._providers.get(bid)
            if prov and prov.is_builtin and not prov.api_key:
                prov.api_key = self._read_legacy_key(cfg, bid)

        # —— Step 4: function_models 迁移 ——
        fm = cfg.get("function_models")
        if isinstance(fm, dict) and fm:
            self._function_models = {
                "video": fm.get("video", []),
                "text": fm.get("text", []),
            }
        else:
            self._function_models = self._migrate_legacy_to_function_models(cfg)

        # —— Step 5: skip_probe / unskip_probe ——
        sp = cfg.get("skip_probe", {})
        if isinstance(sp, dict):
            self._skip_probe = {
                pid: set(names) for pid, names in sp.items() if isinstance(names, list)
            }
        usp = cfg.get("unskip_probe", {})
        if isinstance(usp, dict):
            self._unskip_probe = {
                pid: set(names) for pid, names in usp.items() if isinstance(names, list)
            }

    def save_to_config(self, cfg: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """把 providers + function_models + skip_probe 写回 config（其他字段保持原样）"""
        if cfg is None:
            cfg = load_config()
        # 写 providers[]
        cfg["providers"] = [
            self._providers[pid].to_dict()
            for pid in sorted(self._providers.keys())
        ]
        # 写 function_models{}
        cfg["function_models"] = {
            "video": list(self._function_models["video"]),
            "text": list(self._function_models["text"]),
        }
        # 写 skip_probe —— 从当前 ModelInfo 状态反推
        skip_out: Dict[str, List[str]] = {}
        unskip_out: Dict[str, List[str]] = {}
        with self._rw_lock:
            for pid, mmap in self._models.items():
                for mname, mi in mmap.items():
                    if mi.skip_probe:
                        skip_out.setdefault(pid, []).append(mname)
                    elif mi.was_paid_pool:
                        # 付费池模型被用户取消跳过 → 显式记录
                        unskip_out.setdefault(pid, []).append(mname)
        cfg["skip_probe"] = skip_out
        cfg["unskip_probe"] = unskip_out
        # 同步回旧的 model_chain 字段（兼容运行时未完全迁移前的读取）
        self._sync_to_legacy_model_chains(cfg)
        return cfg

    def list_providers(self) -> List[ProviderSpec]:
        return list(self._providers.values())

    def get_provider(self, provider_id: str) -> Optional[ProviderSpec]:
        return self._providers.get(provider_id)

    def upsert_provider(self, spec: ProviderSpec) -> None:
        self._providers[spec.id] = spec

    def remove_provider(self, provider_id: str) -> None:
        if provider_id in self._providers:
            # 清理 function_models 里的引用
            for fn in ("video", "text"):
                self._function_models[fn] = [
                    entry for entry in self._function_models[fn]
                    if entry.get("provider") != provider_id
                ]
            del self._providers[provider_id]

    # -----------------------------------------------------------------------
    # 模型发现（/models 端点）
    # -----------------------------------------------------------------------

    def discover_models(self, provider_id: str) -> List[ModelInfo]:
        """动态扫描某个 provider 下用户 Key 可调用的所有模型"""
        spec = self._providers.get(provider_id)
        if not spec or not spec.enabled or not spec.api_key:
            return []

        url = spec.models_url
        # Gemini /models 端点需要 key= query param（不能只靠 Authorization header）
        if spec.protocol == "gemini_generate_content":
            url = f"{url}?key={spec.api_key}"

        headers: Dict[str, str] = {"Accept": "application/json"}
        if spec.protocol == "openai_chat_completions":
            headers["Authorization"] = f"Bearer {spec.api_key}"
        if spec.user_agent:
            headers["User-Agent"] = spec.user_agent

        try:
            resp = requests.get(url, headers=headers, timeout=15)
        except Exception as e:
            logger.warning(f"[Registry] discover {provider_id}: GET {url} failed: {e}")
            return []

        if resp.status_code != 200:
            logger.warning(f"[Registry] discover {provider_id}: HTTP {resp.status_code} {resp.text[:120]}")
            return []

        models: List[ModelInfo] = []
        try:
            data = resp.json()
        except Exception:
            return []

        # 两种 /models 响应格式
        raw_list = []
        if isinstance(data, dict):
            if "models" in data and isinstance(data["models"], list):
                # Gemini: {"models": [{"name": "models/gemini-xxx", ...}]}
                raw_list = data["models"]
            elif "data" in data and isinstance(data["data"], list):
                # OpenAI compat: {"data": [{"id": "model-name", ...}]}
                raw_list = data["data"]
            elif isinstance(data, list):
                raw_list = data
        elif isinstance(data, list):
            raw_list = data

        for item in raw_list:
            name = ""
            item_type = ""
            self_hosted = False
            if isinstance(item, dict):
                item_type = str(item.get("type", "") or item.get("model_type", ""))
                self_hosted = bool(item.get("self_hosted", False))
                if "name" in item:
                    name = item["name"].replace("models/", "")
                elif "id" in item:
                    name = str(item["id"])
                elif "model" in item:
                    name = str(item["model"])
                elif "model_name" in item:
                    name = str(item["model_name"])
            elif isinstance(item, str):
                name = item
            if not name:
                continue

            caps = self._tag_capabilities(provider_id, name, type_hint=item_type)
            # free.ai: self_hosted 为 True → 免费池；否则付费池默认跳过探测
            paid = provider_id in ("free.ai", "freeai") and not self_hosted
            mi = ModelInfo(
                provider_id=provider_id, name=name, capabilities=caps,
                type_hint=item_type, skip_probe=paid, was_paid_pool=paid,
            )
            models.append(mi)

        # 存起来
        with self._rw_lock:
            self._models[provider_id] = {m.name: m for m in models}
            # config 恢复：skip_set → True（用户显式跳过），unskip_set → False（用户显式取消）
            skip_set = self._skip_probe.get(provider_id, set())
            unskip_set = self._unskip_probe.get(provider_id, set())
            if skip_set or unskip_set:
                for mname, mi in self._models[provider_id].items():
                    if mname in skip_set:
                        mi.skip_probe = True
                    elif mname in unskip_set:
                        mi.skip_probe = False
                    # else: 保持 discover 时的默认值（free.ai 付费=True, 其他=False）

        self.models_discovered.emit(provider_id)
        return models

    def discover_all_enabled(self) -> None:
        """后台线程扫描所有 enabled provider"""
        def _run() -> None:
            providers = list(self._providers.values())
            for spec in providers:
                if spec.enabled and spec.api_key:
                    try:
                        self.discover_models(spec.id)
                    except Exception as e:
                        logger.warning(f"[Registry] discover {spec.id} error: {e}")
            # 扫完立刻对所有发现到的模型做一次连通性测试
            for spec in providers:
                if spec.enabled and spec.api_key:
                    try:
                        self.test_all(spec.id)
                    except Exception as e:
                        logger.warning(f"[Registry] test_all {spec.id} error: {e}")
            self.scan_finished.emit()

        spawn(target=_run, daemon=True).start()

    # -----------------------------------------------------------------------
    # 连通性测试
    # -----------------------------------------------------------------------

    def _ping_freeai(self, spec: ProviderSpec, model_name: str, mi: ModelInfo) -> Tuple[bool, str]:
        """free.ai 每种 type 对应不同端点，按 type 做真实最小请求

        端点地图（已实测）：
          chat/code/translation  → /v1/chat/completions       (pool 免费)
          vision/multimodal     → /v1/chat/completions + image_url
          image_edit            → /v1/image/edit/              (flux2-klein, qwen-image-edit, step1x-edit, deoldify, sam)
          image                 → /v1/image/edit/              (sdxl, controlnet-union)
          ocr                   → /v1/ocr                      (got-ocr2, paddleocr-vl)
          tts                   → /v1/tts                       (kokoro, qwen3-tts 等)
          embeddings            → /v1/embeddings               (bge-m3)
          stt                   → /v1/stt                       (whisper)
          video                 → /v1/video/generate            (免费 key 会 429 "free plan 不含视频生成")
        """
        import base64 as _b64
        import io as _io
        from PIL import Image as _PILImage, ImageDraw as _PILDraw

        h = {"Authorization": f"Bearer {spec.api_key}", "Content-Type": "application/json"}
        base = spec.base_url.rstrip("/")
        t = (mi.type_hint or "").lower()

        # 最小测试图 (64x64 黑底白字 PNG data URI)
        def _mini_png():
            if not hasattr(self, '_mini_png_cache'):
                img = _PILImage.new('RGB', (64, 64), 'black')
                _PILDraw.Draw(img).text((10, 20), 'OK', fill='white')
                buf = _io.BytesIO()
                img.save(buf, format='PNG')
                self._mini_png_cache = 'data:image/png;base64,' + _b64.b64encode(buf.getvalue()).decode()
            return self._mini_png_cache

        try:
            # —— chat / code / translation ——
            if t in ("chat", "code", "translation") or (not t and "text" in mi.capabilities and "vision" not in mi.capabilities):
                r = requests.post(f"{base}/chat/completions", headers=h, json={
                    "model": model_name, "messages": [{"role": "user", "content": "ping"}], "max_tokens": 1,
                }, timeout=15)
                if r.status_code == 200:
                    return True, "OK"
                try:
                    d = r.json()
                    msg = d.get("error", {}).get("message", r.text[:120])
                except Exception:
                    msg = r.text[:120]
                # 400 "is not a model this endpoint serves" 表示 premium 模型 → 算不可用
                if r.status_code == 400 and "not a model" in msg.lower():
                    if mi.was_paid_pool:
                        return False, "400 premium 模型不在免费池"
                    # 免费池模型收到 "not a model" → 端点/模型ID 变了，当作普通错误
                    return False, f"HTTP 400: {msg}"
                return False, f"HTTP {r.status_code}: {msg}"

            # —— vision / multimodal ——
            if t in ("vision", "multimodal") or "vision" in mi.capabilities:
                r = requests.post(f"{base}/chat/completions", headers=h, json={
                    "model": model_name,
                    "messages": [{"role": "user", "content": [
                        {"type": "text", "text": "describe briefly"},
                        {"type": "image_url", "image_url": {"url": _mini_png()}},
                    ]}],
                    "max_tokens": 1,
                }, timeout=15)
                if r.status_code == 200:
                    return True, "OK"
                return False, f"HTTP {r.status_code}: {(r.text or '')[:120]}"

            # —— image_edit / image ——
            if t in ("image_edit", "image") or "image" in mi.capabilities:
                r = requests.post(f"{base}/image/edit/", headers=h, json={
                    "model": model_name,
                    "prompt": "keep exactly as is",
                    "image_url": _mini_png(),
                }, timeout=60)
                if r.status_code == 200:
                    return True, "OK"
                return False, f"HTTP {r.status_code}: {(r.text or '')[:120]}"

            # —— ocr ——
            if t == "ocr" or any(k in model_name.lower() for k in ("ocr", "tesseract")):
                r = requests.post(f"{base}/ocr", headers=h, json={
                    "model": model_name, "image_url": _mini_png(),
                }, timeout=15)
                if r.status_code == 200:
                    return True, "OK"
                if r.status_code == 422:
                    # 422 "We could not read text from this image" → 端点通了但图里没字，算 OK
                    return True, "OK (端点通，图中无字)"
                return False, f"HTTP {r.status_code}: {(r.text or '')[:120]}"

            # —— tts ——
            if t == "tts" or "tts" in model_name.lower():
                r = requests.post(f"{base}/tts", headers=h, json={
                    "model": model_name, "input": "hello",
                }, timeout=15)
                if r.status_code in (200, 201):
                    return True, "OK"
                if r.status_code == 400:
                    # 参数错误=端点通
                    return True, "OK (端点通)"
                return False, f"HTTP {r.status_code}: {(r.text or '')[:120]}"

            # —— embeddings ——
            if t == "embeddings":
                r = requests.post(f"{base}/embeddings", headers=h, json={
                    "model": model_name, "input": "hello",
                }, timeout=15)
                if r.status_code == 200:
                    return True, "OK"
                return False, f"HTTP {r.status_code}: {(r.text or '')[:120]}"

            # —— stt ——
            if t == "stt" or "whisper" in model_name.lower() or "paraformer" in model_name.lower():
                r = requests.post(f"{base}/stt", headers=h, json={
                    "model": model_name,
                    "audio_url": "https://www.soundhelix.com/examples/mp3/SoundHelix-Song-1.mp3",
                }, timeout=60)
                if r.status_code == 200:
                    return True, "OK"
                return False, f"HTTP {r.status_code}: {(r.text or '')[:120]}"

            # —— video ——
            if t == "video" or "video" in model_name.lower() or "cogvideo" in model_name.lower() or "hunyuan-video" in model_name.lower() or "wan22" in model_name.lower():
                r = requests.post(f"{base}/video/generate", headers=h, json={
                    "model": model_name, "prompt": "a cat", "max_frames": 5,
                }, timeout=60)
                if r.status_code == 200:
                    return True, "OK"
                if r.status_code == 429:
                    # "Free API keys do not include video generation" → 端点通但免费 plan 不含
                    return False, "429 免费 plan 不含视频生成"
                return False, f"HTTP {r.status_code}: {(r.text or '')[:120]}"

            # —— 未知 type → 标记 OK（无法最小化 ping）——
            return True, "OK (端点未探测，假设可用)"

        except requests.exceptions.Timeout:
            return False, "超时"
        except requests.exceptions.ConnectionError as e:
            return False, f"网络错误: {str(e)[:60]}"
        except Exception as e:
            return False, f"异常: {str(e)[:60]}"

    def test_model(self, provider_id: str, model_name: str) -> Tuple[Optional[bool], str]:
        """ping 单个模型：HTTP 请求 → (ok, message)"""
        mi = self._models.get(provider_id, {}).get(model_name)
        if mi and mi.skip_probe:
            return (None, "🚫 跳过探测")

        spec = self._providers.get(provider_id)
        if not spec or not spec.api_key:
            return (None, "provider 未配置")

        ok: Optional[bool] = None
        msg = ""
        url = spec.chat_url.format(m=model_name) if spec.protocol == "gemini_generate_content" else spec.chat_url

        # —— free.ai 特殊：每个 type 对应不同端点 ——
        mi = self._models.get(provider_id, {}).get(model_name)
        if spec.id in ("free.ai", "freeai") and mi:
            ok, msg = self._ping_freeai(spec, model_name, mi)
            with self._rw_lock:
                mi.ok = ok
                mi.ok_message = msg
                mi.last_checked = time.time()
            self.connectivity_changed.emit(provider_id, model_name, ok, msg)
            return (ok, msg)

        # —— 其他 provider 走原来的逻辑 ——

        try:
            if spec.protocol == "gemini_generate_content":
                # POST /v1beta/models/{m}:generateContent?key={key}
                url_with_key = f"{url}?key={spec.api_key}"
                headers = {"Content-Type": "application/json"}
                if spec.user_agent:
                    headers["User-Agent"] = spec.user_agent
                payload = {
                    "contents": [{"parts": [{"text": "ping"}]}],
                    "generationConfig": {"maxOutputTokens": 1},
                }
                resp = requests.post(url_with_key, headers=headers, json=payload, timeout=15)
                if resp.status_code == 200:
                    ok, msg = True, "OK"
                elif resp.status_code == 400:
                    try:
                        msg = f"HTTP 400: {resp.json().get('error',{}).get('message', resp.text[:100])}"
                    except Exception:
                        msg = f"HTTP 400: {resp.text[:100]}"
                    ok = False
                elif resp.status_code == 403:
                    ok, msg = False, "403 无权限"
                elif resp.status_code == 404:
                    ok, msg = False, "404 模型不存在"
                elif resp.status_code == 429:
                    ok, msg = False, "429 配额耗尽"
                else:
                    ok, msg = False, f"HTTP {resp.status_code}: {resp.text[:100]}"
            else:
                # POST /chat/completions (OpenAI compat)
                headers = {
                    "Authorization": f"Bearer {spec.api_key}",
                    "Content-Type": "application/json",
                }
                if spec.user_agent:
                    headers["User-Agent"] = spec.user_agent
                payload = {
                    "model": model_name,
                    "messages": [{"role": "user", "content": "ping"}],
                    "max_tokens": 1,
                }
                resp = requests.post(url, headers=headers, json=payload, timeout=15)
                if resp.status_code == 200:
                    ok, msg = True, "OK"
                elif resp.status_code == 404:
                    try:
                        msg = resp.json().get("error",{}).get("message", "模型不存在")
                    except Exception:
                        msg = "404 模型不存在"
                    ok = False
                elif resp.status_code == 403:
                    ok, msg = False, f"403: Cloudflare/WAF 拦截"
                elif resp.status_code == 400:
                    try:
                        msg = resp.json().get("error",{}).get("message", resp.text[:100])
                    except Exception:
                        msg = resp.text[:100]
                    ok = False
                elif resp.status_code == 429:
                    ok, msg = False, "429 配额耗尽"
                elif resp.status_code == 503:
                    ok, msg = False, "503 服务暂时不可用"
                else:
                    ok, msg = False, f"HTTP {resp.status_code}: {resp.text[:100]}"
        except requests.exceptions.Timeout:
            ok, msg = False, "超时 (15s)"
        except requests.exceptions.ConnectionError as e:
            ok, msg = False, f"网络错误: {str(e)[:60]}"
        except Exception as e:
            ok, msg = False, f"异常: {str(e)[:60]}"

        # 写回 ModelInfo
        with self._rw_lock:
            mi = self._models.setdefault(provider_id, {}).get(model_name)
            if mi is None:
                caps = self._tag_capabilities(provider_id, model_name)
                mi = ModelInfo(provider_id=provider_id, name=model_name, capabilities=caps)
                self._models[provider_id][model_name] = mi
            mi.ok = ok
            mi.ok_message = msg
            mi.last_checked = time.time()

        self.connectivity_changed.emit(provider_id, model_name, ok, msg)
        return (ok, msg)

    def test_all(self, provider_id: Optional[str] = None) -> None:
        """批量测试：指定 provider 或全部（自动排除 skip_probe 模型）"""
        targets: List[Tuple[str, str]] = []
        with self._rw_lock:
            if provider_id:
                for mname, mi in self._models.get(provider_id, {}).items():
                    if not mi.skip_probe:
                        targets.append((provider_id, mname))
            else:
                for pid, mmap in self._models.items():
                    for mname, mi in mmap.items():
                        if not mi.skip_probe:
                            targets.append((pid, mname))

        def _run() -> None:
            for pid, mname in targets:
                self.test_model(pid, mname)

        spawn(target=_run, daemon=True).start()

    # -----------------------------------------------------------------------
    # 按 capability 过滤（供 UI & 运行时使用）
    # -----------------------------------------------------------------------

    def get_models_for_capability(self, capability: str, require_ok: bool = False) -> List[ModelInfo]:
        """获取所有已发现 + 带某能力标签的模型"""
        result: List[ModelInfo] = []
        with self._rw_lock:
            for pid, mmap in self._models.items():
                for mi in mmap.values():
                    if capability in mi.capabilities and (not require_ok or mi.ok is True):
                        result.append(mi)
        # 排序：skip_probe=False 优先 → provider_id → name
        result.sort(key=lambda m: (m.skip_probe, m.provider_id, m.name))
        return result

    def get_all_discovered(self) -> List[ModelInfo]:
        result: List[ModelInfo] = []
        with self._rw_lock:
            for mmap in self._models.values():
                result.extend(mmap.values())
        result.sort(key=lambda m: (m.skip_probe, m.provider_id, m.name))
        return result

    # -----------------------------------------------------------------------
    # 用户勾选 ↔ function_models
    # -----------------------------------------------------------------------

    def get_function_models(self, function: str) -> List[Dict[str, str]]:
        return list(self._function_models.get(function, []))

    def set_function_models(self, function: str, entries: List[Dict[str, str]]) -> None:
        self._function_models[function] = list(entries)
        self.function_models_changed.emit()

    def set_skip_probe(self, provider_id: str, model_name: str, skip: bool) -> None:
        """切换某个模型的 skip_probe 标志"""
        with self._rw_lock:
            mi = self._models.setdefault(provider_id, {}).get(model_name)
            if mi is None:
                caps = self._tag_capabilities(provider_id, model_name)
                mi = ModelInfo(provider_id=provider_id, name=model_name, capabilities=caps)
                self._models[provider_id][model_name] = mi
            mi.skip_probe = skip
        self.skip_probe_changed.emit(provider_id, model_name, skip)

    def get_enabled_chain(self, function: str) -> List[Tuple[ProviderSpec, ModelInfo]]:
        """运行时调用：按用户勾选顺序返回 (ProviderSpec, ModelInfo) 列表"""
        result: List[Tuple[ProviderSpec, ModelInfo]] = []
        for entry in self._function_models.get(function, []):
            pid = entry.get("provider", "")
            mname = entry.get("model", "")
            spec = self._providers.get(pid)
            mi = self._models.get(pid, {}).get(mname) if pid else None
            if spec and mi:
                result.append((spec, mi))
        return result

    # -----------------------------------------------------------------------
    # 内部：能力打标启发式
    # -----------------------------------------------------------------------

    def _tag_capabilities(self, provider_id: str, model_name: str,
                           type_hint: str = "") -> Set[str]:
        """根据模型名 + type 字段启发式打标签；provider 级硬约束也叠加进去"""
        caps: Set[str] = {"text"}   # 默认所有 chat 模型都是 text

        low = model_name.lower()

        # —— 先用 type_hint 精准打标（free.ai / 类似平台会返回这个字段）——
        if type_hint:
            t = type_hint.lower()
            if t == "chat":
                caps = {"text"}
            elif t == "code":
                caps = {"text"}
            elif t == "image":
                caps = {"text", "image"}
            elif t == "image_edit":
                caps = {"text", "image", "multimodal"}
            elif t == "video":
                caps = {"text", "video", "multimodal"}
            elif t == "tts":
                caps = {"text", "tts"}
            elif t == "stt":
                caps = {"audio"}
            elif t == "vision":
                caps = {"text", "multimodal", "vision"}
            elif t == "ocr":
                caps = {"text", "multimodal", "vision"}
            elif t == "translation":
                caps = {"text"}
            elif t == "embeddings":
                caps = {"text"}   # embedding 也算文本处理
            elif t == "multimodal":
                caps = {"text", "multimodal", "vision"}
            else:
                # 未知 type → 保留默认 {"text"}，让后面的名称启发式补充
                pass

        # —— provider 级硬约束 ——
        prov = self._providers.get(provider_id)
        if prov:
            if prov.protocol == "gemini_generate_content":
                if "flash" in low or "pro" in low or "omni" in low:
                    caps.add("video")
                    caps.add("audio")
                    caps.add("multimodal")
                if "transcribe" in low:
                    caps.add("audio")

        # —— 名称启发式补充（当 type_hint 为空时的兜底）——
        if not type_hint:
            video_keywords = ("video", "veo", "omni")
            audio_keywords = ("audio", "transcribe", "speech", "whisper", "asr", "stt")
            vision_keywords = ("vision", "vl")
            tts_keywords = ("tts", "speech-generation")
            image_keywords = ("image", "cogview")

            if any(k in low for k in video_keywords):
                caps |= {"video", "multimodal"}
            if any(k in low for k in audio_keywords):
                caps.add("audio")
            if any(k in low for k in vision_keywords):
                caps.add("multimodal")
            if any(k in low for k in tts_keywords):
                caps.add("tts")
            if any(k in low for k in image_keywords):
                caps.add("image")

            if any(k in low for k in ("whisper", "transcribe")) and "tts" not in caps and "image" not in caps:
                caps.discard("text")

        return caps

    # -----------------------------------------------------------------------
    # 旧格式迁移
    # -----------------------------------------------------------------------

    @staticmethod
    def _read_legacy_key(cfg: Dict[str, Any], provider_id: str) -> str:
        """从旧格式 gemini/groq/ai_writer 字段兜底读 api_key"""
        if provider_id == "gemini":
            return str(cfg.get("gemini", {}).get("api_key", "")).strip()
        if provider_id == "groq":
            return str(cfg.get("groq", {}).get("api_key", "")).strip()
        if provider_id == "glm":
            return str(cfg.get("ai_writer", {}).get("api_key", "")).strip()
        return ""

    @staticmethod
    def _migrate_legacy_to_providers(cfg: Dict[str, Any]) -> List[Dict[str, Any]]:
        """把旧格式 (gemini/groq/ai_writer section) 迁移成 providers[] 列表"""
        result: List[Dict[str, Any]] = []

        gem_cfg = cfg.get("gemini", {})
        if gem_cfg:
            result.append({
                "id": "gemini", "name": "Gemini", "protocol": "gemini_generate_content",
                "icon": "🌀", "base_url": "https://generativelanguage.googleapis.com",
                "is_builtin": True,
                "api_key": str(gem_cfg.get("api_key", "")).strip(),
                "enabled": bool(gem_cfg.get("enabled", False)),
            })

        groq_cfg = cfg.get("groq", {})
        if groq_cfg:
            result.append({
                "id": "groq", "name": "Groq", "protocol": "openai_chat_completions",
                "icon": "⚡",
                "base_url": ModelRegistry._strip_chat_path(
                    groq_cfg.get("api_url"), "https://api.groq.com/openai/v1"
                ),
                "user_agent": "curl/8.7.1", "is_builtin": True,
                "api_key": str(groq_cfg.get("api_key", "")).strip(),
                "enabled": bool(groq_cfg.get("enabled", False)),
            })

        glm_cfg = cfg.get("ai_writer", {})
        if glm_cfg:
            result.append({
                "id": "glm", "name": "智谱 GLM", "protocol": "openai_chat_completions",
                "icon": "🧠",
                "base_url": ModelRegistry._strip_chat_path(
                    glm_cfg.get("api_url"), "https://open.bigmodel.cn/api/paas/v4"
                ),
                "is_builtin": True,
                "api_key": str(glm_cfg.get("api_key", "")).strip(),
                "enabled": bool(glm_cfg.get("enabled", False)),
            })

        return result

    @staticmethod
    def _strip_chat_path(url: Optional[str], default: str) -> str:
        """旧 config 的 api_url 可能是完整 chat URL（如 /v1/chat/completions），剥成 base"""
        if not url:
            return default
        url = str(url).strip()
        import re
        # 只剥 chat/completions 这种 endpoint 路径尾，不动版本号（/v1 /v4 等）
        url = re.sub(r'/+chat/completions/?$', '', url, flags=re.IGNORECASE)
        url = re.sub(r'/+completions/?$', '', url, flags=re.IGNORECASE)
        return url.rstrip('/')

    @staticmethod
    def _migrate_legacy_to_function_models(cfg: Dict[str, Any]) -> Dict[str, List[Dict[str, str]]]:
        """从旧的 model_chain 字段推断 function_models"""
        video: List[Dict[str, str]] = []
        text: List[Dict[str, str]] = []

        # gemini → video + text（双用）
        for m in cfg.get("gemini", {}).get("model_chain", []):
            video.append({"provider": "gemini", "model": str(m)})
            text.append({"provider": "gemini", "model": str(m)})

        for m in cfg.get("groq", {}).get("model_chain", []):
            text.append({"provider": "groq", "model": str(m)})

        for m in cfg.get("ai_writer", {}).get("model_chain", []):
            text.append({"provider": "glm", "model": str(m)})

        return {"video": video, "text": text}

    def _sync_to_legacy_model_chains(self, cfg: Dict[str, Any]) -> None:
        """反向同步 function_models 到旧的 model_chain 字段（兼容旧运行时代码）"""
        video = self._function_models.get("video", [])
        text = self._function_models.get("text", [])

        gemini_video = [e["model"] for e in video if e.get("provider") == "gemini"]
        gemini_text = [e["model"] for e in text if e.get("provider") == "gemini"]
        gemini_chain = list(dict.fromkeys(gemini_video + gemini_text))
        if gemini_chain:
            cfg.setdefault("gemini", {})["model_chain"] = gemini_chain
            cfg["gemini"]["model"] = gemini_chain[0]

        groq_text = [e["model"] for e in text if e.get("provider") == "groq"]
        if groq_text:
            cfg.setdefault("groq", {})["model_chain"] = groq_text
            cfg["groq"]["model"] = groq_text[0]

        glm_text = [e["model"] for e in text if e.get("provider") == "glm"]
        if glm_text:
            cfg.setdefault("ai_writer", {})["model_chain"] = glm_text
            cfg["ai_writer"]["model"] = glm_text[0]
