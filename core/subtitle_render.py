"""
共享字幕硬烧录功能

将 SRT 字幕烧录进 MP4 画面（ffmpeg libass filter），供：
  - 字幕参数页（page_subtitle）手动制作
  - 全自动流水线（auto_pipeline）复用
两者使用完全一致的样式逻辑，保证烧录结果一致。

字符约束：
  - 字幕字号由调用方传入（GUI 恒为 8px）
  - 底部边距 margin_v 最小钳制为 8px
"""

import os
import re
import subprocess
from typing import Callable, Optional

from loguru import logger
from utils.path_helper import get_ffmpeg_path


"""
共享字幕硬烧录功能

将 SRT 字幕烧录进 MP4 画面（ffmpeg libass filter），供：
  - 字幕参数页（page_subtitle）手动制作
  - 全自动流水线（auto_pipeline）复用
两者使用完全一致的样式逻辑，保证烧录结果一致。

支持双语渲染：
  - SRT 条目多行 → ASS Dialogue 用 \\N 合并
  - 译文字号独立（secondary_scale）
  - 双语位置（src_top / src_bottom）
"""

import os
import re
import subprocess
import tempfile
from typing import Callable, List, Optional, Tuple

from loguru import logger
from utils.path_helper import get_ffmpeg_path


def _hex_to_ass_color(hex_str: str) -> str:
    """hex (#RRGGBB) → ASS (&HBBGGRR)。

    ASS v4+ 颜色格式：&HAABBGGRR（BGR 顺序！），alpha 反转：00=不透明, FF=透明。
    这里返回 6 位 &HBBGGRR，ASS 规范默认 alpha=00（不透明）。
    例：#FF6600（橙红） → &H0066FF → libass 渲染为橙红 ✓
    """
    h = (hex_str or "").lstrip('#') or "FFFFFF"
    h = h.ljust(6, '0')[:6]
    r, g, b = h[0:2], h[2:4], h[4:6]
    return f"&H{b}{g}{r}"


def _lighter_hex(hex_str: str, factor: float = 1.15) -> str:
    """hex 颜色变亮 factor 倍（模拟 Canvas 的 lighter(115)），输出 ASS 6 位 &HBBGGRR"""
    h = (hex_str or "").lstrip('#') or "FFFFFF"
    h = h.ljust(6, '0')[:6]
    r = min(255, int(int(h[0:2], 16) * factor))
    g = min(255, int(int(h[2:4], 16) * factor))
    b = min(255, int(int(h[4:6], 16) * factor))
    return f"&H{b:02X}{g:02X}{r:02X}"


def _ass_time(t: float) -> str:
    """秒 → ASS 时间戳 H:MM:SS.CS（厘秒精度）"""
    t = max(0.0, t)
    h = int(t // 3600)
    m = int((t % 3600) // 60)
    s = t - h * 3600 - m * 60
    return f"{h}:{m:02d}:{s:05.2f}"


def _parse_srt(srt_path: str) -> List[Tuple[float, float, List[str]]]:
    """
    解析 SRT 文件 → [(start, end, lines), ...]
    lines 是一个条目里的所有文本行（可能 1 行或 2 行双语）

    支持 LF、CRLF、CR 换行符。
    """
    with open(srt_path, "r", encoding="utf-8") as f:
        content = f.read()

    # ★ 统一换行符：CRLF → LF, CR → LF
    content = content.replace("\r\n", "\n").replace("\r", "\n")

    entries = []
    # 按空行分割条目
    raw_blocks = re.split(r"\n\s*\n", content.strip())
    for block in raw_blocks:
        lines = [l.strip() for l in block.strip().split("\n") if l.strip()]
        if len(lines) < 2:
            continue
        # 第一行是序号（跳过），第二行是时间戳
        time_line = lines[1]
        m = re.match(
            r"(\d{1,2}):(\d{2}):(\d{2})[,.](\d{1,3})\s*-->\s*"
            r"(\d{1,2}):(\d{2}):(\d{2})[,.](\d{1,3})",
            time_line,
        )
        if not m:
            continue
        sh, sm, ss, sms = m.group(1), m.group(2), m.group(3), m.group(4)
        eh, em, es, ems = m.group(5), m.group(6), m.group(7), m.group(8)
        start = int(sh) * 3600 + int(sm) * 60 + int(ss) + int(sms.ljust(3, '0')[:3]) / 1000
        end = int(eh) * 3600 + int(em) * 60 + int(es) + int(ems.ljust(3, '0')[:3]) / 1000
        text_lines = lines[2:]  # 文本部分
        entries.append((start, end, text_lines))

    return entries


def _srt_to_ass(
    srt_path: str,
    ass_path: str,
    font_size: int,
    primary_color: str,
    outline_color: str,
    margin_v: int,
    bilingual: bool = True,
    bilingual_pos: str = "src_top",   # "src_top" | "src_bottom"
    secondary_scale: float = 0.85,
    alignment: int = 2,              # libass 九宫格 1-9，默认 2=底部居中
    secondary_color_auto_lighter: bool = True,  # 译文颜色自动变淡（模拟 Canvas lighter(115)）
    video_res_x: int = 1920,          # ★ 视频原生宽度（ffprobe 探测）
    video_res_y: int = 1080,          # ★ 视频原生高度（ffprobe 探测）
    bar_enabled: bool = False,         # ★ 底部黑框（字幕条）
    bar_height: int = 48,              # ★ 黑框高度（视频像素）
    bar_opacity_pct: int = 70,         # ★ 黑框透明度 0-100%（100=不透明）
    pos_x: Optional[int] = None,       # ★ 字幕自由定位 X（视频像素，None=Alignment 2 默认居中）
    pos_y: Optional[int] = None,       # ★ 字幕自由定位 Y（视频像素，None=Alignment 2 默认贴底）
) -> str:
    """
    把 SRT 转成 ASS 文件（临时），复刻 Canvas 预览的所有字幕样式。

    Args:
        srt_path: 输入 SRT
        ass_path: 输出 ASS
        font_size: 主字号 (px，用户在 GUI 里设的像素值，相对于视频原生分辨率)
        primary_color: 主颜色 hex
        outline_color: 描边颜色 hex
        margin_v: 底部边距 (px，相对于视频原生分辨率)
        bilingual: 是否双语渲染
        bilingual_pos: src_top=原文在上, src_bottom=原文在下
        secondary_scale: 译文字号相对主字号比例（0.5-1.0）
        alignment: libass 九宫格 Alignment (1-9)，默认 2=底部居中
        secondary_color_auto_lighter: 译文自动变淡 15%（复刻 Canvas lighter(115)）
        video_res_x: 视频原生宽度（ffprobe 探测，用于 ASS PlayResX 对齐坐标空间）
        video_res_y: 视频原生高度（ffprobe 探测，用于 ASS PlayResY 对齐坐标空间）

    Returns:
        ass_path（成功）
    """
    primary = _hex_to_ass_color(primary_color)
    outline = _hex_to_ass_color(outline_color)
    margin_h = 32
    margin_v = max(8, int(margin_v))

    # ★ ASS 坐标系：视频部分固定 1080p 基准；启用底部黑条（扩边）时总高 = 1080 + 黑条高度
    # PlayResX 始终 = 1080 × 视频宽高比（pad 只向下扩展，宽度不变）
    video_w = max(1, int(video_res_x))
    video_h = max(1, int(video_res_y))
    bar_h_basis = max(20, min(200, int(bar_height))) if bar_enabled else 0
    play_res_y = 1080 + bar_h_basis
    play_res_x = max(1, round(1080 * video_w / video_h))

    # ★ libass 的 Fontsize 直接就是 ASS 脚本坐标系里的像素值（em size），不是印刷 pt！
    # PlayResY=1080 时 Fontsize=36 → 字高占视频高度 36/1080=3.33%，
    # 导出到任意分辨率（720p/1080p/4K）占比恒定，和 Canvas 预览（36×canvas_h/1080）完全一致。
    font_size_ass = max(4, round(float(font_size)))
    secondary_size_ass = max(4, round(float(font_size) * secondary_scale))
    # ★ 描边宽度同样直接用脚本像素：Canvas 主描边 2px，译文 1px
    outline_size_ass = 2
    secondary_outline_ass = max(1, outline_size_ass - 1)

    # ★ 译文颜色：自动变亮（复刻 Canvas lighter(115)）
    secondary_color_ass = _lighter_hex(primary_color, 1.15) if secondary_color_auto_lighter else primary

    lines = []
    lines.append("[Script Info]")
    lines.append("Title: Auto-generated by VideoCrawler")
    lines.append("ScriptType: v4.00+")
    lines.append(f"PlayResX: {play_res_x}")
    lines.append(f"PlayResY: {play_res_y}")
    lines.append("")
    lines.append("[V4+ Styles]")
    lines.append("Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, "
                 "Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, "
                 "Alignment, MarginL, MarginR, MarginV, Encoding")
    lines.append(
        f"Style: Default,Microsoft YaHei,{font_size_ass},{primary},&H00000000,{outline},&H00000000,"
        f"1,0,0,0,100,100,0.4,0,1,{outline_size_ass},1,{alignment},{margin_h},{margin_h},{margin_v},1"
    )
    lines.append("")
    lines.append("[Events]")
    lines.append("Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text")

    entries = _parse_srt(srt_path)

    for start, end, text_lines in entries:
        if not text_lines:
            continue

        # ★ ASS 里反斜杠是转义符
        _escape = lambda s: s.replace("\\", "\\\\").replace("\n", " ").strip()

        if bilingual and len(text_lines) >= 2:
            first = _escape(text_lines[0])
            second = _escape(text_lines[1])

            # ★ 译文行覆盖颜色 + 描边（复刻 Canvas 译文 lighter(115) + outline-1）
            tgt_override = f"{{\\c{secondary_color_ass}\\bord{secondary_outline_ass}}}"

            if bilingual_pos == "src_top":
                # 原文在上（主字号），译文在下（secondary + 变淡 + 细描边）
                text_field = f"{first}\\N{{\\fs{secondary_size_ass}}}{tgt_override}{second}"
            else:
                # 译文在上（secondary + 变淡 + 细描边），原文在下（主字号）
                text_field = f"{{\\fs{secondary_size_ass}}}{tgt_override}{second}\\N{first}"
        else:
            text_field = _escape(text_lines[0])

        # 时间戳
        t_start = _ass_time(start)
        t_end = _ass_time(end)

        # 注：底部黑条（字幕条）不在 ASS 里用 Draw Commands 画
        # （\p 缩放 + Alignment 原点坑多），统一由 ffmpeg pad 滤镜向下扩边实现。

        # ★ 自由定位：有 pos_x/pos_y 时用 \an2\pos 绝对定位
        if pos_x is not None and pos_y is not None:
            pos_override = f"{{\\an2\\pos({pos_x},{pos_y})}}"
        else:
            pos_override = ""

        dialogue = f"Dialogue: 0,{t_start},{t_end},Default,,0,0,0,,{pos_override}{text_field}"
        lines.append(dialogue)

    with open(ass_path, "w", encoding="utf-8-sig") as f:
        f.write("\n".join(lines))

    return ass_path


def _probe_video_resolution(video_path: str) -> Tuple[int, int]:
    """用 ffprobe 探测视频原生分辨率 (width, height)。失败返回 (1920, 1080)。"""
    try:
        # 用 ffprobe，从 path_helper 拿路径
        # ★ 只能替换文件名：路径目录本身也叫 bin\ffmpeg，全局 replace 会把目录改成不存在的 bin\ffprobe
        from utils.path_helper import get_ffmpeg_path
        if get_ffmpeg_path():
            _ff = str(get_ffmpeg_path())
            ffprobe = os.path.join(
                os.path.dirname(_ff),
                os.path.basename(_ff).replace("ffmpeg", "ffprobe"),
            )
        else:
            ffprobe = "ffprobe"

        result = subprocess.run(
            [ffprobe, "-v", "quiet", "-select_streams", "v:0",
             "-show_entries", "stream=width,height",
             "-of", "csv=p=0", video_path],
            capture_output=True, encoding="utf-8", errors="replace",
            timeout=30,
        )
        out = (result.stdout or "").strip()
        if out and "," in out:
            w, h = out.split(",")
            w_i, h_i = int(w), int(h)
            if w_i > 0 and h_i > 0:
                logger.info(f"[probe] 视频原生分辨率: {w_i}x{h_i} ({os.path.basename(video_path)})")
                return w_i, h_i
    except FileNotFoundError:
        logger.warning("[probe] ffprobe 未找到，尝试用 ffmpeg -i 解析...")
        try:
            ffmpeg = str(get_ffmpeg_path()) if get_ffmpeg_path() else "ffmpeg"
            probe = subprocess.run(
                [ffmpeg, "-i", video_path],
                capture_output=True, encoding="utf-8", errors="replace",
                timeout=30,
            )
            # 从 ffmpeg -i 输出里找 "Stream #0:0: Video: ... 1920x1080 ..."
            m = re.search(r"(\d{3,5})x(\d{3,5})", probe.stderr or "")
            if m:
                w_i, h_i = int(m.group(1)), int(m.group(2))
                logger.info(f"[probe] ffmpeg 解析视频分辨率: {w_i}x{h_i}")
                return w_i, h_i
        except Exception:
            pass
    except Exception as e:
        logger.warning(f"[probe] 视频分辨率探测失败: {e}")

    logger.warning("[probe] 无法探测视频分辨率，fallback 到 1920x1080")
    return 1920, 1080


def _probe_duration(ffmpeg: str, video_path: str) -> float:
    """用 ffmpeg -i 探测视频时长（秒），失败返回 0.0"""
    try:
        probe = subprocess.run(
            [ffmpeg, "-i", video_path],
            capture_output=True, encoding="utf-8", errors="replace",
            timeout=30,
        )
        m = re.search(r"Duration:\s*(\d+):(\d{2}):(\d{2}(?:\.\d+)?)", probe.stderr or "")
        if m:
            h, mi, s = m.group(1), m.group(2), m.group(3)
            return int(h) * 3600 + int(mi) * 60 + float(s)
    except Exception:
        pass
    return 0.0


def _has_video_stream(ffmpeg: str, video_path: str) -> bool:
    """检测文件是否含视频流（防止把纯音频文件当成视频烧录）。

    用 `ffmpeg -i` 的 stderr 解析 `Stream #...: Video:` 标记。
    纯音频文件（如 yt-dlp 兜底下载的 opus/webm）会缺失该标记。
    """
    try:
        probe = subprocess.run(
            [ffmpeg, "-i", video_path],
            capture_output=True, encoding="utf-8", errors="replace",
            timeout=30,
        )
        stderr = probe.stderr or ""
        return bool(re.search(r"Stream\s+#\d+:\d+.*:\s*Video:", stderr))
    except Exception:
        return False


def burn_mp4(
    video_path: str,
    srt_path: str,
    font_size: int = 8,
    margin_v: int = 16,
    primary_color: str = "#FFFFFF",
    outline_color: str = "#000000",
    progress_cb: Optional[Callable[[int, str], None]] = None,
    *,
    bilingual: bool = True,
    bilingual_pos: str = "src_top",       # "src_top" | "src_bottom"
    secondary_scale: float = 0.85,
    alignment: int = 2,                   # libass 九宫格 1-9，默认 2=底部居中
    bar_enabled: bool = False,             # ★ 底部黑框（字幕条）
    bar_height: int = 48,                  # ★ 黑框高度（视频像素）
    bar_opacity_pct: int = 70,             # ★ 黑框透明度 0-100%（100=不透明）
    pos_x: Optional[int] = None,           # ★ 字幕自由定位 X（视频像素）
    pos_y: Optional[int] = None,           # ★ 字幕自由定位 Y（视频像素）
) -> Optional[str]:
    """
    硬烧录 MP4 字幕。

    Args:
        video_path: 输入视频路径
        srt_path: SRT 字幕路径
        font_size: 主字号 (px，相对于视频原生分辨率)
        margin_v: 底部边距 (px，相对于视频原生分辨率)
        primary_color: 主文字颜色 (hex, #RRGGBB)
        outline_color: 描边颜色 (hex, #RRGGBB)
        progress_cb: 进度回调 (pct, desc)
        bilingual: 是否启用双语渲染（SRT 有两行时才生效）
        bilingual_pos: 双语位置 "src_top"(原文在上) / "src_bottom"(译文在上)
        secondary_scale: 译文字号相对主字号的比例（0.7-1.0 合理）
        bar_enabled: 是否启用底部黑框（字幕条）
        bar_height: 黑框高度（视频像素）
        bar_opacity_pct: 黑框透明度 0-100%（100=完全不透明）

    Returns:
        输出视频路径（<原名>_已完成.mp4），失败返回 None
    """
    if not video_path or not os.path.exists(video_path):
        logger.error(f"[burn_mp4] 视频不存在: {video_path}")
        return None
    if not srt_path or not os.path.exists(srt_path):
        logger.error(f"[burn_mp4] 字幕不存在: {srt_path}")
        return None

    ffmpeg = str(get_ffmpeg_path()) if get_ffmpeg_path() else "ffmpeg"
    dir_name = os.path.dirname(video_path)
    base, _ = os.path.splitext(os.path.basename(video_path))
    out_path = os.path.join(dir_name, f"{base}_已完成.mp4")

    # ★ 前置校验：输入必须含视频流
    if not _has_video_stream(ffmpeg, video_path):
        logger.error(
            f"[burn_mp4] 输入文件无视频流（疑似纯音频 webm/mp4），无法烧录字幕: {video_path}"
        )
        return None

    if progress_cb:
        progress_cb(0, "正在探测视频分辨率...")

    # ★ P0: 探测视频原生分辨率（ASS PlayResX/Y 必须对齐视频实际分辨率）
    video_res_x, video_res_y = _probe_video_resolution(video_path)

    if progress_cb:
        progress_cb(2, "正在探测视频时长...")
    total_duration = _probe_duration(ffmpeg, video_path)
    if total_duration <= 0:
        logger.warning("[burn_mp4] 无法获取视频时长，进度条不显示百分比")

    # ★ SRT → ASS 转换（支持双语双行不同字号/位置/颜色）
    # 临时 ASS 文件在 tempfile 里，ffmpeg 用完就删
    tmp_dir = tempfile.gettempdir()
    ass_path = os.path.join(tmp_dir, f"vc_burn_{os.getpid()}_{int(os.path.getmtime(srt_path) * 1000)}.ass")
    try:
        _srt_to_ass(
            srt_path, ass_path,
            font_size=font_size,
            primary_color=primary_color,
            outline_color=outline_color,
            margin_v=margin_v,
            bilingual=bilingual,
            bilingual_pos=bilingual_pos,
            secondary_scale=secondary_scale,
            alignment=alignment,
            video_res_x=video_res_x,
            video_res_y=video_res_y,
            bar_enabled=bar_enabled,
            bar_height=bar_height,
            bar_opacity_pct=bar_opacity_pct,
            pos_x=pos_x,
            pos_y=pos_y,
        )
        logger.info(
            f"[burn_mp4] SRT→ASS 完成: bilingual={bilingual} pos={bilingual_pos} "
            f"secondary_scale={secondary_scale} alignment={alignment} "
            f"video_res={video_res_x}x{video_res_y} ASS基准=1080p "
            f"| 主字号 Fontsize={round(font_size)} 译文 Fontsize={round(font_size * secondary_scale)} "
            f"| 黑条(扩边)={'开' if bar_enabled else '关'} +{bar_height}px "
            f"总PlayResY={1080 + (bar_height if bar_enabled else 0)} | pos=({pos_x},{pos_y})"
        )
    except Exception as e:
        logger.error(f"[burn_mp4] SRT→ASS 失败: {e}")
        # 清理
        try: os.remove(ass_path)
        except Exception: pass
        return None

    escaped_ass = ass_path.replace("\\", "/").replace(":", "\\:").replace("'", "\\'")

    # ★ 滤镜链：pad 向下扩展画布（视频原画面完整保留，底部接出黑色新区），再烧字幕
    # 黑条高度是 1080p 基准像素，实际扩展量 = 视频高 × H/1080，任意分辨率自适应
    filters = []
    if bar_enabled and bar_height > 0:
        bh = max(20, min(200, int(bar_height)))
        filters.append(
            f"pad=w=iw:h=ih+ih*{bh}/1080:x=0:y=0:color=black"
        )
    filters.append(f"subtitles='{escaped_ass}'")
    vf = ",".join(filters)

    cmd = [
        ffmpeg, "-y",
        "-i", video_path,
        "-vf", vf,
        "-c:a", "copy",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "23",
        "-movflags", "+faststart",
        out_path,
    ]

    result = None
    try:
        proc = subprocess.Popen(
            cmd,
            stderr=subprocess.PIPE,
            stdout=subprocess.DEVNULL,
            encoding="utf-8",
            errors="replace",
        )
        time_re = re.compile(r"time=(\d+):(\d{2}):(\d{2}(?:\.\d+)?)")
        last_pct = -1
        buf = ""
        # 最长运行：60 分钟保底，或视频时长 × 3（避免 ffmpeg 卡死永久挂起，AUDIT-0030）
        import queue
        import threading
        import time as _t
        max_run = max(3600, total_duration * 3 if total_duration > 0 else 3600)
        deadline = _t.time() + max_run

        # ★ AUDIT-0060: stderr 改由后台 daemon 线程读入队列，主循环带超时轮询。
        # 原 proc.stderr.read(256) 是阻塞读，ffmpeg 静默卡死时主循环永远等不到数据，
        # deadline 检查永不触发 → 烧录永久挂起。
        # stdout 为 DEVNULL 无需读取线程；Windows 下 selectors 不支持 pipe，故用线程+队列方案。
        stderr_q: "queue.Queue[Optional[str]]" = queue.Queue()

        def _pump_stderr(pipe) -> None:
            """后台线程：持续读 ffmpeg stderr 推入队列，EOF 后投递 None 哨兵。"""
            try:
                while True:
                    chunk = pipe.read(256)
                    if not chunk:
                        break
                    stderr_q.put(chunk)
            except Exception:
                pass
            finally:
                stderr_q.put(None)

        reader = threading.Thread(
            target=_pump_stderr, args=(proc.stderr,), name="ffmpeg-stderr-pump", daemon=True
        )
        reader.start()

        while True:
            if _t.time() > deadline:
                # ★ AUDIT-0030: deadline 到点强杀 ffmpeg 并抛 TimeoutExpired，
                # 交由下方既有 except subprocess.TimeoutExpired 分支清理并返回（不再永久挂起）
                proc.kill()
                logger.error("MP4 烧录超时（>60分钟或视频时长×3），已强制终止 ffmpeg")
                raise subprocess.TimeoutExpired(cmd, max_run)
            try:
                chunk = stderr_q.get(timeout=0.5)
            except queue.Empty:
                # 0.5s 无数据：进程已退出且读取线程已结束（管道 EOF）→ 正常收尾
                if proc.poll() is not None and not reader.is_alive():
                    break
                continue
            if chunk is None:
                # stderr EOF 哨兵（读取线程投递，所有数据已入队）
                break
            buf += chunk
            while "\r" in buf or "\n" in buf:
                sep = "\r" if "\r" in buf else "\n"
                line, buf = buf.split(sep, 1)
                m = time_re.search(line)
                if m and total_duration > 0 and progress_cb:
                    h, mi, s = m.group(1), m.group(2), m.group(3)
                    cur = int(h) * 3600 + int(mi) * 60 + float(s)
                    pct = int(cur / total_duration * 100)
                    pct = max(0, min(100, pct))
                    if pct != last_pct:
                        last_pct = pct
                        progress_cb(pct, f"烧录中 {pct}%  ({cur:.0f}s/{total_duration:.0f}s)")

        ret = proc.wait()
        if os.path.exists(out_path) and os.path.getsize(out_path) > 1024:
            # ★ 后置校验：成品必须含视频流，防止 ffmpeg 假成功（输入虽含视频流，
            # 但 subtitles filter 静默失败、输出只剩音频流的情况）。
            if not _has_video_stream(ffmpeg, out_path):
                err_tail = buf[-500:] if buf else ""
                logger.error(
                    f"[burn_mp4] 烧录成品无视频流（疑似 subtitles filter 失败），删除成品: {out_path}; "
                    f"stderr_tail={err_tail}"
                )
                try:
                    os.remove(out_path)
                except Exception:
                    pass
                return None
            if progress_cb:
                progress_cb(100, "MP4 烧录完成")
            logger.success(f"MP4 硬烧录完成: {out_path}")
            result = out_path
        else:
            err_tail = buf[-500:] if buf else ""
            logger.error(f"MP4 烧录失败 (code={ret}): {err_tail}")
    except subprocess.TimeoutExpired:
        try:
            proc.kill()
            proc.wait()
        except Exception:
            pass
        logger.error("MP4 烧录超时")
    except Exception as e:
        try:
            proc.kill()
            proc.wait()
        except Exception:
            pass
        logger.error(f"MP4 烧录异常: {e}")
    finally:
        # ★ 清理临时 ASS 文件
        try:
            os.remove(ass_path)
        except Exception:
            pass

    return result