"""
批量为已下载的视频补充下载封面

扫描 output 目录下所有 .mp4 文件，根据文件名提取 video_id，
通过 YouTube 固定封面 URL 格式直接下载（无需调 yt-dlp，速度快）。
"""

import os
import re
import sys
import time
import requests
from pathlib import Path

OUTPUT_DIR = Path(r"D:\Ideas\VideoCrawler\Vc\output")

YOUTUBE_THUMB_CANDIDATES = [
    "https://i.ytimg.com/vi/{vid}/maxresdefault.jpg",
    "https://i.ytimg.com/vi/{vid}/hqdefault.jpg",
    "https://i.ytimg.com/vi/{vid}/mqdefault.jpg",
    "https://i.ytimg.com/vi/{vid}/default.jpg",
]

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
}


def extract_video_id(filename: str) -> str | None:
    """从 mp4 文件名中提取 YouTube video_id

    文件名格式通常是: {video_id}_{title}.mp4
    或者: {video_id}.mp4
    video_id 是 11 位字母数字加下划线和连字符的组合
    """
    # 尝试提取第一个下划线前的部分作为 video_id
    stem = os.path.splitext(filename)[0]
    candidate = stem.split("_")[0] if "_" in stem else stem

    # 也可以尝试用正则在整个文件名里搜 11 字符的 video_id
    match = re.search(r"([a-zA-Z0-9_-]{11})", filename)
    if match:
        return match.group(1)

    # fallback: 如果 candidate 长度在 9-13 之间，就用它
    if 9 <= len(candidate) <= 13:
        return candidate
    return None


def download_one_thumb(video_id: str, video_path: Path) -> tuple[bool, str]:
    """下载单个视频封面，返回 (成功与否, 路径或错误信息)"""
    base = video_path.with_suffix("")
    thumb_path = Path(str(base) + ".jpg")

    if thumb_path.exists() and thumb_path.stat().st_size > 1024:
        return True, f"已存在 {thumb_path.name}"

    for tpl in YOUTUBE_THUMB_CANDIDATES:
        url = tpl.format(vid=video_id)
        try:
            resp = requests.get(url, timeout=15, headers=HEADERS)
            if resp.status_code == 200 and len(resp.content) > 512:
                with open(thumb_path, "wb") as f:
                    f.write(resp.content)
                return True, f"{thumb_path.name} [{len(resp.content)//1024}KB]"
        except Exception:
            continue

    return False, "所有分辨率候选均失败"


def main():
    print(f"扫描目录: {OUTPUT_DIR}")
    mp4_files = list(OUTPUT_DIR.rglob("*.mp4"))
    print(f"共发现 {len(mp4_files)} 个 mp4 文件\n")

    success = 0
    skipped = 0
    failed = 0

    for i, mp4 in enumerate(mp4_files, 1):
        video_id = extract_video_id(mp4.name)
        if not video_id:
            print(f"[{i}/{len(mp4_files)}] ✗ 无法从文件名提取 video_id: {mp4.name}")
            failed += 1
            continue

        thumb_path = Path(str(mp4.with_suffix("")) + ".jpg")
        if thumb_path.exists() and thumb_path.stat().st_size > 1024:
            skipped += 1
            continue

        ok, msg = download_one_thumb(video_id, mp4)
        if ok:
            success += 1
            print(f"[{i}/{len(mp4_files)}] ✓ {video_id} → {msg}")
        else:
            failed += 1
            print(f"[{i}/{len(mp4_files)}] ✗ {video_id}: {msg}")

        time.sleep(0.1)  # 轻微限流，避免被 YouTube 临时封 IP

    print(f"\n===== 完成 =====")
    print(f"新下载封面: {success}")
    print(f"已有封面跳过: {skipped}")
    print(f"失败: {failed}")


if __name__ == "__main__":
    main()
