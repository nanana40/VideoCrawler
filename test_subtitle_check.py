"""
测试字幕检测逻辑

功能：检查视频文件是否真正包含字幕轨道
"""

import os
import sys
import re

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, PROJECT_ROOT)

FFMPEG_BIN_DIR = os.path.join(PROJECT_ROOT, "bin", "ffmpeg", "bin")
if FFMPEG_BIN_DIR not in os.environ["PATH"]:
    os.environ["PATH"] = f"{FFMPEG_BIN_DIR};{os.environ['PATH']}"
    print(f"已添加 ffmpeg 到 PATH: {FFMPEG_BIN_DIR}")

import subprocess


def check_subtitle_tracks(video_path: str) -> None:
    """检查视频文件的字幕轨道"""
    print(f"\n检查视频: {video_path}")
    print("-" * 60)
    
    cmd = ["ffmpeg", "-i", video_path]
    result = subprocess.run(cmd, stderr=subprocess.PIPE, stdout=subprocess.PIPE, text=True)
    
    print("ffmpeg 输出:")
    print("=" * 60)
    lines = result.stderr.split("\n")
    for line in lines:
        print(line)
    print("=" * 60)
    
    subtitle_pattern = re.compile(r"Stream #\d+:\d+.*Subtitle:", re.IGNORECASE)
    has_subtitle = bool(subtitle_pattern.search(result.stderr))
    
    print(f"\n检测结果: {'有字幕轨道' if has_subtitle else '无字幕轨道'}")
    
    print("\n详细分析:")
    for line in lines:
        if "Stream" in line:
            if "Subtitle" in line or "subtitle" in line:
                print(f"  ✅ {line.strip()}")
            elif "Video" in line:
                print(f"  📹 {line.strip()}")
            elif "Audio" in line:
                print(f"  🔊 {line.strip()}")


def main() -> None:
    """主测试函数"""
    print("=" * 60)
    print("字幕检测逻辑测试")
    print("=" * 60)
    
    video_dir = os.path.join(PROJECT_ROOT, "output", "en", "daily")
    
    video_files = [f for f in os.listdir(video_dir) if f.endswith(".mp4")]
    
    for video_file in video_files:
        video_path = os.path.join(video_dir, video_file)
        check_subtitle_tracks(video_path)
        print("\n" + "=" * 60)


if __name__ == "__main__":
    main()
