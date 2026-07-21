"""
测试原视频自带英文字幕场景 - 使用真正有字幕的视频

功能：下载一个已知有英文字幕的YouTube视频，验证脚本能否正确识别原字幕，
      并只嵌入中文字幕且不遮挡原字幕。
"""

import os
import sys

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, PROJECT_ROOT)

FFMPEG_BIN_DIR = os.path.join(PROJECT_ROOT, "bin", "ffmpeg", "bin")
if FFMPEG_BIN_DIR not in os.environ["PATH"]:
    os.environ["PATH"] = f"{FFMPEG_BIN_DIR};{os.environ['PATH']}"
    print(f"已添加 ffmpeg 到 PATH: {FFMPEG_BIN_DIR}")

from core.download import download_video, DownloadResult
from core.subtitle_processor import process_video_subtitle, SubtitleResult
from utils.enums import LanguageType, VideoCategory


def main() -> None:
    """主测试函数"""
    print("=" * 60)
    print("测试原视频自带英文字幕场景")
    print("=" * 60)
    
    youtube_url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
    video_id = "subtitle_test_real"
    language = LanguageType.ENGLISH
    category = VideoCategory.DAILY
    
    print(f"\n1. 开始下载视频: {youtube_url}")
    print(f"   语言: {language.display_name}")
    print(f"   分类: {category.display_name}")
    print("   (此视频通常有官方英文字幕)")
    
    download_result = download_video(
        url=youtube_url,
        video_id=video_id,
        title="Rick Astley - Never Gonna Give You Up",
        language=language,
        category=category
    )
    
    if not download_result.success:
        print(f"\n✗ 下载失败: {download_result.error_message}")
        sys.exit(1)
    
    video_path = download_result.file_path
    video_dir = os.path.dirname(video_path)
    
    print(f"\n✓ 下载成功")
    print(f"   文件路径: {video_path}")
    print(f"   时长: {download_result.duration} 秒")
    
    print(f"\n下载目录文件列表:")
    for file in os.listdir(video_dir):
        if file.startswith(video_id):
            file_path = os.path.join(video_dir, file)
            file_size = os.path.getsize(file_path) / (1024 * 1024)
            print(f"   {file} ({file_size:.2f} MB)")
    
    print(f"\n2. 开始处理字幕（检测原字幕+语音识别+翻译+嵌入）")
    
    subtitle_result = process_video_subtitle(
        video_id=video_id,
        video_path=video_path,
        language=language,
        category=category,
        source_lang="en",
        target_lang="zh-CN"
    )
    
    if not subtitle_result.success:
        print(f"\n✗ 字幕处理失败: {subtitle_result.error_message}")
        sys.exit(1)
    
    print(f"\n✓ 字幕处理成功")
    print(f"   字幕文件: {subtitle_result.subtitle_path}")
    print(f"   已完成视频: {subtitle_result.embedded_video_path}")
    print(f"   是否有原字幕: {subtitle_result.has_original_subtitle}")
    
    if subtitle_result.has_original_subtitle:
        print("\n✅ 已正确识别到原视频自带字幕！")
        print("   嵌入的中文字幕会放置在上方，避免遮挡原字幕。")
    else:
        print("\n⚠️ 未检测到原视频自带字幕")
        print("   嵌入的字幕会作为双语字幕显示。")
    
    print(f"\n3. 验证文件")
    print(f"\n下载目录文件列表: {video_dir}")
    print("-" * 60)
    
    original_found = False
    completed_found = False
    
    for file in os.listdir(video_dir):
        if file.startswith(video_id):
            file_path = os.path.join(video_dir, file)
            file_size = os.path.getsize(file_path) / (1024 * 1024)
            print(f"  {file} ({file_size:.2f} MB)")
            
            if "_已完成" not in file and file.endswith(".mp4"):
                original_found = True
            if "_已完成" in file and file.endswith(".mp4"):
                completed_found = True
    
    print("-" * 60)
    
    if original_found:
        print("✓ 原视频已找到")
    else:
        print("✗ 原视频未找到")
    
    if completed_found:
        print("✓ 已完成视频已找到")
    else:
        print("✗ 已完成视频未找到")
    
    print("\n" + "=" * 60)
    print("测试完成！")
    print("=" * 60)


if __name__ == "__main__":
    main()
