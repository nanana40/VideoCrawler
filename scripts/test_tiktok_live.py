"""
test_tiktok_live.py — TikTok / 抖音 **真实网络** 下载测试

与 test_tiktok_download.py（纯离线）不同，本脚本会真的：
  1. 用 TiktokSpider 解析视频元数据
  2. 用 VideoDownloader 下载视频 + 封面
  3. 校验文件存在、体积、封面

所有产物写到临时数据目录（VC_DATA_ROOT），不会污染 output/。

用法：
  d:\\python\\python.exe scripts\\test_tiktok_live.py --url "https://www.douyin.com/video/xxx"

可选：
  --proxy http://127.0.0.1:7890   临时指定代理（优先于 config.yaml）
  --cookies path\\cookies.txt     临时指定 cookie 文件
  --keep                          保留下载产物，便于人工检查
"""

from __future__ import annotations

import argparse
import glob
import os
import shutil
import sys
import tempfile
import traceback
from pathlib import Path

VC_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, VC_ROOT)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", required=True, help="TikTok / 抖音视频链接")
    parser.add_argument("--proxy", default="", help="临时代理，如 http://127.0.0.1:7890")
    parser.add_argument("--cookies", default="", help="临时 cookie 文件（Netscape 格式）")
    parser.add_argument("--keep", action="store_true", help="保留下载产物")
    args = parser.parse_args()

    url = args.url.strip()

    # 隔离输出目录：所有产物落临时目录
    tmp_root = tempfile.mkdtemp(prefix="vc_tiktok_live_")
    os.environ["VC_DATA_ROOT"] = tmp_root
    print(f"数据目录（临时）: {tmp_root}")

    from utils.video_url import detect_video_site, extract_tiktok_video_id, resolve_tiktok_id

    site = detect_video_site(url)
    vid = extract_tiktok_video_id(url) or resolve_tiktok_id(url)
    print(f"\n[1/3] 链接识别：site={site or '未知'} id={vid or '（短链解析失败）'}")
    if site != "tiktok" or not vid:
        print("❌ 不是可识别的 TikTok/抖音视频链接")
        return 1

    # 临时覆盖代理 / cookie 配置
    import core.spiders.tiktok_spider as ts
    if args.proxy:
        ts._get_proxy_from_config = lambda: args.proxy
        print(f"    代理: {args.proxy}")

    if args.cookies:
        # 注入到隔离数据目录的 cookies 路径：
        # 解析（TiktokSpider）与下载（VideoDownloader）都会读这个文件
        from utils.path_helper import get_cookies_file_path
        src = Path(args.cookies).expanduser()
        if not src.is_file():
            print(f"❌ cookies 文件不存在: {src}")
            return 1
        dst = get_cookies_file_path()
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src, dst)
        _orig_build = ts.TiktokSpider._build_ydl_opts

        def _build_with_cookie(self_):  # type: ignore[no-untyped-def]
            opts = _orig_build(self_)
            opts.pop("cookies_from_browser", None)
            opts["cookies"] = str(dst)
            return opts

        ts.TiktokSpider._build_ydl_opts = _build_with_cookie  # type: ignore[method-assign]
        print(f"    cookies: {src} → {dst}")

    print("\n[2/3] 解析元数据（yt-dlp）...")
    info = None
    try:
        spider = ts.TiktokSpider()
        info = spider.get_video_info(url)
    except Exception as e:
        print(f"❌ 解析异常: {e}")
        traceback.print_exc()

    if not info:
        print("❌ 元数据解析失败")
        print("   常见原因：")
        print("   - 国内网络无法直连 TikTok → 在 config.yaml 配 crawler.proxy")
        print("   - 抖音要求新鲜 cookies → 用浏览器登录后导出 cookies，或关闭浏览器重试")
        print("   - yt-dlp 版本过旧 → D:\\python\\python.exe -m yt_dlp -U")
        return 2

    print(f"    ✓ 标题: {info.get('title', '')[:60]}")
    print(f"    ✓ 作者: {info.get('channel_name') or info.get('author') or '-'}")
    print(f"    ✓ 时长: {info.get('duration') or '-'}")
    print(f"    ✓ 封面: {'有' if info.get('thumbnail') else '无'}")
    print(f"    ✓ 规范地址: {info.get('source_url', '')}")

    print("\n[3/3] 下载视频 + 封面 ...")
    from core.download import VideoDownloader
    from utils.video_url import to_pipeline_video

    candidate = to_pipeline_video(info, url)
    dl = VideoDownloader()
    result = None
    try:
        result = dl.download_video(
            url=candidate["source_url"],
            video_id=candidate["youtube_id"],
            title=candidate.get("title", ""),
        )
    except Exception as e:
        print(f"❌ 下载异常: {e}")
        traceback.print_exc()

    if not result or not result.success:
        print(f"❌ 下载失败: {getattr(result, 'error_message', '') or '未知原因'}")
        return 3

    fp = result.file_path or result.local_path or ""
    size_mb = round(os.path.getsize(fp) / 1024 / 1024, 2) if fp and os.path.exists(fp) else 0
    print(f"    ✓ 视频: {fp}")
    print(f"    ✓ 体积: {size_mb} MB")

    # 封面归档后的文件名与视频主名不一定同 stem，直接在同目录找最大的 jpg
    cover = ""
    if fp:
        jpgs = [
            p for p in glob.glob(os.path.join(os.path.dirname(fp), "*.jpg"))
            if os.path.getsize(p) > 1024
        ]
        if jpgs:
            cover = max(jpgs, key=os.path.getsize)
    has_cover = bool(cover)
    print(f"    {'✓' if has_cover else '⚠'} 封面: {cover if has_cover else '未生成'}")

    ok = bool(fp) and os.path.exists(fp) and size_mb > 0.1
    print("\n" + "=" * 56)
    print(("✅ 真实下载成功" if ok else "❌ 未通过：视频文件缺失或过小"))
    print("=" * 56)

    if not args.keep:
        shutil.rmtree(tmp_root, ignore_errors=True)
        print("临时产物已清理")
    else:
        print(f"产物保留在: {tmp_root}")
    return 0 if ok else 4


if __name__ == "__main__":
    sys.exit(main())
