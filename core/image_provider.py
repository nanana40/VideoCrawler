"""
免费图生图 / Inpaint 统一接口
=============================

封装多个免费图生图 API，提供「图进 → 图出」的图片编辑能力。
主要用途：YouTube 封面翻译（把外文封面上的文字替换成中文）。

Provider 降级链（免费优先，额度从大到小）：
  1. freeai       — free.ai 注册后 30k tokens/天，真·Mask Inpaint，效果最好
  2. rewind       — Rewind.ai 匿名 2500 tokens/天 / 注册 5000，FLUX.2 Klein
  3. pollinations — Pollinations /prompt GET，免费无 key，但只做 T2I
  4. pil_fallback — 本机 PIL 手工渲染（gemini_engine 里的现有方案）
"""

from __future__ import annotations

import io
import json
import os
import time
import base64
import threading
import urllib.request
import urllib.error
import urllib.parse
from typing import Optional, Tuple, List

from PIL import Image

from utils.logger import get_translate_logger

logger = get_translate_logger()


# ---------------------------------------------------------------------------
# free.ai provider id 统一常量（config 中可能写 'free.ai' 或 'freeai'）
# ---------------------------------------------------------------------------
FREEAI_PROVIDER_IDS = frozenset({"free.ai", "freeai"})


# ---------------------------------------------------------------------------
# 从 config.yaml 读 freeai api_key（lazy，避免循环 import）
# ---------------------------------------------------------------------------

def _get_freeai_key() -> str:
    """从 config.yaml 读取 free.ai provider 的 api_key；空串表示未配置"""
    try:
        from utils.config_loader import load_config
        cfg = load_config()
        for p in cfg.get("providers", []):
            if isinstance(p, dict) and p.get("id") in FREEAI_PROVIDER_IDS:
                key = str(p.get("api_key", "")).strip()
                return key
    except Exception as e:
        logger.warning(f'[ImageProvider] 读 config 获取 freeai key 失败: {e}')
    return ""


# ---------------------------------------------------------------------------
# 限流 / 状态追踪
# ---------------------------------------------------------------------------

class ProviderStatus:
    """记录每个 provider 的可用性 + 下次可重试时间"""
    def __init__(self):
        self._lock = threading.Lock()
        self._state: dict = {}

    def mark_429(self, provider: str, retry_after: float = 30.0):
        with self._lock:
            self._state.setdefault(provider, {})['cooldown_until'] = time.time() + retry_after

    def mark_broken(self, provider: str):
        with self._lock:
            self._state.setdefault(provider, {})['cooldown_until'] = time.time() + 300

    def is_cool(self, provider: str) -> bool:
        with self._lock:
            st = self._state.get(provider, {})
            return time.time() >= st.get('cooldown_until', 0)


_status = ProviderStatus()


# ---------------------------------------------------------------------------
# 通用工具
# ---------------------------------------------------------------------------

def _to_data_uri(image_path: str, max_side: int = 1024, quality: int = 85) -> Tuple[str, int, int]:
    """把本地图片读成 data URI，必要时缩小"""
    img = Image.open(image_path).convert('RGB')
    w, h = img.size
    scale = min(max_side / w, max_side / h, 1.0)
    if scale < 1.0:
        img = img.resize((int(w * scale), int(h * scale)), Image.LANCZOS)
        w, h = img.size
    buf = io.BytesIO()
    img.save(buf, format='JPEG', quality=quality, optimize=True)
    b64 = base64.b64encode(buf.getvalue()).decode()
    return f'data:image/jpeg;base64,{b64}', w, h


def _download_image(url: str, timeout: int = 60, depth: int = 0) -> Optional[Image.Image]:
    """从 URL 下载图片。

    depth: 递归下载深度（JSON 响应里嵌套 URL 时逐层跟进），
           超过 3 层停止递归，防止重定向环导致栈溢出。
    """
    if depth > 3:
        logger.warning(f'[ImageProvider] 下载图片递归深度超过 3 层，停止跟进 (url={url[:80]})')
        return None
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'curl/8.7.1'})
        resp = urllib.request.urlopen(req, timeout=timeout)
        data = resp.read()
        ct = resp.headers.get('Content-Type', '')
        if 'image' in ct:
            return Image.open(io.BytesIO(data))
        # 有些 API 返回 JSON 里带 base64
        try:
            j = json.loads(data)
            # 常见位置：data[0].b64_json / image / output
            b64 = None
            if isinstance(j, dict):
                if 'b64_json' in j:
                    b64 = j['b64_json']
                elif 'image' in j and isinstance(j['image'], str) and j['image'].startswith('data:'):
                    b64 = j['image'].split(',', 1)[1]
                elif 'output' in j and isinstance(j['output'], str) and j['output'].startswith('data:'):
                    b64 = j['output'].split(',', 1)[1]
                elif 'url' in j and isinstance(j['url'], str):
                    return _download_image(j['url'], timeout, depth + 1)
                elif 'data' in j and isinstance(j['data'], list):
                    for item in j['data']:
                        if isinstance(item, dict):
                            if 'b64_json' in item:
                                b64 = item['b64_json']
                            elif 'url' in item and isinstance(item['url'], str):
                                return _download_image(item['url'], timeout, depth + 1)
            if b64:
                return Image.open(io.BytesIO(base64.b64decode(b64)))
        except Exception:
            pass
        return None
    except Exception as e:
        logger.warning(f'[ImageProvider] 下载图片失败: {e}')
        return None


def _retry_delay(resp, default: float = 30.0) -> float:
    try:
        ra = resp.headers.get('Retry-After') or resp.headers.get('retry-after')
        if ra:
            return max(1.0, min(600.0, float(ra)))
    except Exception:
        pass
    return default


# ---------------------------------------------------------------------------
# Provider 1: free.ai （30k tokens/天免费，需注册）
# ---------------------------------------------------------------------------

FREEAI_IMAGE_EDIT = 'https://api.free.ai/v1/image/edit/'

FREEAI_PROMPT = """Image editing task: Translate ALL visible text in this image to Simplified Chinese.
CRITICAL RULES you must follow:
1. Keep 100% of non-text pixels EXACTLY unchanged (background, characters, objects, colors, layout, composition)
2. Erase original text by inpainting with matching surrounding texture — do NOT use a solid color block
3. Render Chinese text with matching font: weight, size, color, outline, shadow
4. Place translated text at the SAME position and roughly the SAME size as the original
5. Do NOT add, remove, distort, or alter anything that is not text
6. No watermarks, no new objects, no style changes"""


def call_freeai(image_path: str, timeout: int = 180) -> Optional[Image.Image]:
    """调 free.ai 图片编辑端点做封面翻译。需要在 config.yaml 里配置 providers[].id=freeai 的 api_key。"""
    api_key = _get_freeai_key()
    if not api_key:
        logger.info('[ImageProvider] freeai 未配置 api_key，跳过')
        return None

    data_uri, nw, nh = _to_data_uri(image_path, max_side=1024, quality=85)
    body = json.dumps({
        'model': 'flux2-klein',
        'prompt': FREEAI_PROMPT,
        'image_url': data_uri,   # free.ai 端点参数名是 image_url（不是 image）
    }).encode()

    req = urllib.request.Request(
        FREEAI_IMAGE_EDIT,
        data=body,
        headers={
            'Content-Type': 'application/json',
            'Authorization': f'Bearer {api_key}',
            'User-Agent': 'curl/8.7.1',
        },
        method='POST',
    )

    t0 = time.time()
    try:
        resp = urllib.request.urlopen(req, timeout=timeout)
    except urllib.error.HTTPError as e:
        err = (e.read() or b'').decode(errors='replace')[:300]
        if e.code == 429:
            delay = _retry_delay(e, default=60.0)
            _status.mark_429('freeai', retry_after=delay)
            logger.warning(f'[ImageProvider] free.ai 429 限流, 冷却 {delay:.0f}s ({err[:120]})')
        elif e.code in (401, 403):
            _status.mark_broken('freeai')
            logger.warning(f'[ImageProvider] free.ai {e.code}, 标记 broken ({err[:120]})')
        else:
            logger.warning(f'[ImageProvider] free.ai HTTP {e.code}: {err[:200]}')
        return None
    except Exception as e:
        logger.warning(f'[ImageProvider] free.ai 异常: {type(e).__name__}: {e}')
        return None

    logger.info(f'[ImageProvider] free.ai 生成完成 {time.time()-t0:.1f}s, 解析响应...')
    try:
        raw = resp.read()
        ct = resp.headers.get('Content-Type', '')
        # free.ai 可能直接返回图片，也可能返回 JSON
        if 'image' in ct:
            return Image.open(io.BytesIO(raw))
        # 尝试 JSON
        j = json.loads(raw)
        return _download_image(str(j.get('url', ''))) or _download_image_from_json(j)
    except Exception as e:
        logger.warning(f'[ImageProvider] free.ai 响应解析失败: {e}')
        return None


def _download_image_from_json(j: dict) -> Optional[Image.Image]:
    """从 JSON 响应里挖图片"""
    # free.ai 可能返回 {"output": "data:image/png;base64,XXX"} 或 {"data": [{"url": "..."}]}
    for key in ('output', 'image', 'result'):
        v = j.get(key)
        if isinstance(v, str) and v.startswith('data:'):
            b64 = v.split(',', 1)[1]
            try:
                return Image.open(io.BytesIO(base64.b64decode(b64)))
            except Exception:
                pass
    for item in j.get('data', []):
        if isinstance(item, dict):
            url = item.get('url', '')
            if url and url.startswith('http'):
                return _download_image(url)
    return None


# ---------------------------------------------------------------------------
# Provider 2: Rewind.ai （匿名免费，零 API key）
# ---------------------------------------------------------------------------

REWIND_API = 'https://api.rewind.ai/v1/images/generations/'

REWIND_PROMPT = """Image editing:
Goal: Translate ALL non-English text in this image to Simplified Chinese.
Rules you MUST follow:
1. Keep 100% of non-text pixels unchanged (background, characters, objects, colors, layout)
2. Erase original text by inpainting the surrounding texture (NOT a solid color block)
3. Render Chinese text with matching font style: weight, size, color, outline, shadow
4. Place translated text at the SAME position and roughly the SAME size as the original
5. Do NOT add, remove, or alter anything that is not text
6. No watermarks, no new objects, no style changes
"""


def call_rewind(image_path: str, timeout: int = 180) -> Optional[Image.Image]:
    data_uri, nw, nh = _to_data_uri(image_path, max_side=1024, quality=85)
    body = json.dumps({
        'prompt': REWIND_PROMPT,
        'image': data_uri,
        'model': 'flux-2-klein',
    }).encode()

    req = urllib.request.Request(
        REWIND_API,
        data=body,
        headers={'Content-Type': 'application/json', 'User-Agent': 'curl/8.7.1'},
        method='POST',
    )

    t0 = time.time()
    try:
        resp = urllib.request.urlopen(req, timeout=timeout)
    except urllib.error.HTTPError as e:
        err = (e.read() or b'').decode(errors='replace')[:300]
        if e.code == 429:
            delay = _retry_delay(e, default=60.0)
            _status.mark_429('rewind', retry_after=delay)
            logger.warning(f'[ImageProvider] Rewind.ai 429 限流, 冷却 {delay:.0f}s ({err[:120]})')
        elif e.code in (401, 403):
            _status.mark_broken('rewind')
            logger.warning(f'[ImageProvider] Rewind.ai {e.code}, 标记 broken ({err[:120]})')
        else:
            logger.warning(f'[ImageProvider] Rewind.ai HTTP {e.code}: {err[:200]}')
        return None
    except Exception as e:
        logger.warning(f'[ImageProvider] Rewind.ai 异常: {type(e).__name__}: {e}')
        return None

    try:
        j = json.loads(resp.read())
        url = j['data'][0]['url']
        gen_id = j.get('generationId', '')
        logger.info(f'[ImageProvider] Rewind.ai 生成成功: {gen_id}, 耗时 {time.time()-t0:.1f}s, 下载中...')
    except Exception as e:
        logger.warning(f'[ImageProvider] Rewind.ai 响应解析失败: {e}')
        return None

    return _download_image(url)


# ---------------------------------------------------------------------------
# Provider 3: Pollinations （/prompt GET，免费无 key，但只做 T2I）
# ---------------------------------------------------------------------------

POLL_PROMPT = """Exact copy of this Kurzgesagt YouTube video thumbnail.
Preserve EXACTLY: background dark space with stars, brain silhouette on left, all colors and layout.
Replace ONLY the German text 'Dein Hirn macht dich jeden Tag 2 Stunden blind' with Chinese translation '你的大脑每天让你盲视 2 小时'.
Use SAME visual style: bold sans-serif white text, dark outline/shadow.
Keep text at same position and size. Do NOT invent anything new."""


def call_pollinations(image_path: str, timeout: int = 180) -> Optional[Image.Image]:
    """T2I 专用、已移出图生图链、勿作为参考图翻译使用。

    Pollinations /prompt 端点是文生图（T2I），传入的 image 参数不被作为参考图，
    实际输出完全由硬编码 POLL_PROMPT 决定，与传入图片内容无关。
    该函数保留仅供未来接入 pollinations 图生图端点时复用参数构造逻辑。
    """
    img = Image.open(image_path).convert('RGB')
    w, h = img.size
    scale = min(384 / w, 384 / h, 1.0)  # 压到 384w 避免 URL 过长
    small = img.resize((int(w * scale), int(h * scale)), Image.LANCZOS)
    buf = io.BytesIO()
    small.save(buf, format='JPEG', quality=40, optimize=True)
    b64 = base64.b64encode(buf.getvalue()).decode()
    data_uri = f'data:image/jpeg;base64,{b64}'

    params = urllib.parse.urlencode({
        'image': data_uri,
        'width': w,
        'height': h,
        'model': 'turbo',
        'nologo': 'true',
        'seed': '42',
    })
    url = (
        'https://image.pollinations.ai/prompt/'
        + urllib.parse.quote(POLL_PROMPT)
        + '?' + params
    )
    logger.info(f'[ImageProvider] Pollinations URL 长度 {len(url)}')

    req = urllib.request.Request(url, headers={'User-Agent': 'curl/8.7.1'})
    t0 = time.time()
    try:
        resp = urllib.request.urlopen(req, timeout=timeout)
        data = resp.read()
        logger.info(f'[ImageProvider] Pollinations 完成 {time.time()-t0:.1f}s, {len(data)}B')
        return Image.open(io.BytesIO(data))
    except urllib.error.HTTPError as e:
        body = (e.read() or b'').decode(errors='replace')[:200]
        if e.code == 429:
            _status.mark_429('pollinations', 30.0)
        logger.warning(f'[ImageProvider] Pollinations HTTP {e.code}: {body}')
        return None
    except Exception as e:
        logger.warning(f'[ImageProvider] Pollinations 异常: {e}')
        return None


# ---------------------------------------------------------------------------
# 对外统一入口
# ---------------------------------------------------------------------------

# Provider 链：按优先级排序，逐个尝试直到成功
# freeai 需配置 api_key，未配置时 try_inpaint_translate 会跳过
# 注：pollinations 已移出（T2I 伪装图生图，见 call_pollinations docstring）
PROVIDER_CHAIN: List[Tuple[str, callable]] = [
    ('free.ai', call_freeai),
    ('rewind', call_rewind),
]


def try_inpaint_translate(image_path: str, out_path: Optional[str] = None) -> Tuple[str, Optional[str]]:
    """
    用图生图 API 把封面文字翻译成中文。

    Returns:
        (summary, out_image_path_or_None)
        out_image_path is None 表示所有图生图服务均不可用，调用方应降级到 PIL 方案。
    """
    if not image_path or not os.path.exists(image_path):
        return '封面图片不存在', None

    tried: List[str] = []
    for pid, fn in PROVIDER_CHAIN:
        # free.ai 特殊：无 api_key 直接跳过，不占冷却状态
        if pid in FREEAI_PROVIDER_IDS and not _get_freeai_key():
            tried.append('free.ai(未配置key)')
            continue
        if not _status.is_cool(pid):
            tried.append(f'{pid}(冷却)')
            continue
        logger.info(f'[ImageProvider] 尝试 provider={pid} ...')
        try:
            result = fn(image_path)
        except Exception as e:
            logger.warning(f'[ImageProvider] {pid} 抛异常: {e}')
            tried.append(f'{pid}(异常)')
            continue

        if result is not None:
            if out_path is None:
                base, _ = os.path.splitext(image_path)
                out_path = base + '_中文化.png'
            try:
                result.save(out_path, format='PNG')
                logger.info(f'[ImageProvider] ✅ {pid} 成功 → {out_path}')
                return f'图生图翻译成功 ({pid})', out_path
            except Exception as e:
                logger.warning(f'[ImageProvider] {pid} 保存失败: {e}')
                tried.append(f'{pid}(保存失败)')
                continue

        tried.append(f'{pid}(返回None)')

    logger.warning(f'[ImageProvider] 所有图生图 provider 均不可用: {", ".join(tried)}')
    return f'图生图不可用 ({", ".join(tried)})', None
