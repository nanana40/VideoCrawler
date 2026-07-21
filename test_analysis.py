"""
视频分析扩展功能测试脚本

功能：在下载视频前询问用户分析提炼方向，下载并翻译后根据用户要求
对内容进行分析并输出，将原视频、翻译视频、分析文案保存在同一文件夹内。
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
from core.video_analyzer import analyze_video, AnalysisMode, get_video_analyzer
from core.social_media_formatter import SocialMediaFormatter, SocialStyle
from utils.enums import LanguageType, VideoCategory
from utils.file_sort import get_file_sorter


def ask_analysis_mode() -> AnalysisMode:
    """询问用户分析方向"""
    print("\n请选择视频分析方向：")
    modes = list(AnalysisMode)
    
    for i, mode in enumerate(modes, 1):
        print(f"  {i}. {mode.display_name}")
    
    while True:
        try:
            choice = int(input("\n请输入序号: "))
            if 1 <= choice <= len(modes):
                return modes[choice - 1]
            print("无效输入，请重新选择")
        except ValueError:
            print("无效输入，请输入数字")


def main() -> None:
    """主测试函数"""
    print("=" * 60)
    print("视频分析扩展功能测试")
    print("=" * 60)
    
    youtube_url = "https://www.youtube.com/watch?v=jNQXAC9IVRw"
    video_id = "analysis_test_1"
    title = "YouTube Introduction"
    language = LanguageType.ENGLISH
    category = VideoCategory.DAILY
    
    print(f"\n1. 视频信息")
    print(f"   URL: {youtube_url}")
    print(f"   语言: {language.display_name}")
    print(f"   分类: {category.display_name}")
    
    analysis_mode = AnalysisMode.EXAM_PREP
    print(f"\n已选择分析方向: {analysis_mode.display_name}")
    
    print(f"\n2. 开始下载视频")
    download_result = download_video(
        url=youtube_url,
        video_id=video_id,
        title=title,
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
    
    print(f"\n3. 开始处理字幕（语音识别+翻译+嵌入）")
    
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
    
    print(f"\n4. 开始视频内容分析")
    
    analyzer = get_video_analyzer()
    
    segments_dict = []
    if subtitle_result.subtitle_path and os.path.exists(subtitle_result.subtitle_path):
        with open(subtitle_result.subtitle_path, "r", encoding="utf-8") as f:
            content = f.read()
        
        import re
        pattern = re.compile(r'(\d+)\n(\d{2}:\d{2}:\d{2},\d{3}) --> (\d{2}:\d{2}:\d{2},\d{3})\n(.+?)(?=\n\n|\Z)', re.DOTALL)
        
        for match in pattern.finditer(content):
            text = match.group(4).strip()
            lines = text.split("\n")
            
            if len(lines) >= 2:
                original_text = lines[0]
                translated_text = lines[1]
            else:
                original_text = text
                translated_text = ""
            
            start_time_str = match.group(2)
            parts = start_time_str.split(":")
            seconds = int(parts[0]) * 3600 + int(parts[1]) * 60 + float(parts[2].replace(",", "."))
            
            segments_dict.append({
                "start_time": seconds,
                "end_time": 0,
                "text": original_text,
                "translated_text": translated_text
            })
    
    analysis_result = analyze_video(
        video_id=video_id,
        subtitles=segments_dict,
        mode=analysis_mode,
        output_dir=video_dir
    )
    
    if analysis_result.success:
        print(f"\n✓ 分析完成")
        print(f"   分析报告: {analysis_result.report_path}")
    else:
        print(f"\n✗ 分析失败: {analysis_result.error_message}")
    
    print(f"\n5. 生成社交媒体文案")
    
    formatter = SocialMediaFormatter()
    
    for style in [SocialStyle.XIAOHONGSHU, SocialStyle.WEIBO, SocialStyle.ZHIHU]:
        social_result = formatter.format(
            video_id=video_id,
            subtitles=segments_dict,
            analysis_mode=analysis_mode.display_name,
            output_dir=video_dir,
            style=style
        )
        
        if social_result.success:
            print(f"\n✓ {style.display_name}文案生成成功")
            print(f"   文案文件: {social_result.file_path}")
        else:
            print(f"\n✗ {style.display_name}文案生成失败")
    
    print(f"\n6. 文件验证")
    print(f"\n视频文件夹内容: {video_dir}")
    print("-" * 60)
    
    original_found = False
    completed_found = False
    report_found = False
    social_found = False
    
    for file in os.listdir(video_dir):
        file_path = os.path.join(video_dir, file)
        if os.path.isfile(file_path):
            file_size = os.path.getsize(file_path) / (1024 * 1024)
            print(f"  {file} ({file_size:.2f} MB)")
            
            if "_已完成" not in file and file.endswith(".mp4"):
                original_found = True
            if "_已完成" in file and file.endswith(".mp4"):
                completed_found = True
            if file.endswith(".md") and "analysis" in file:
                report_found = True
            if file.endswith(".txt") and "social" in file:
                social_found = True
    
    if os.path.exists(os.path.join(video_dir, "subtitles")):
        subtitle_dir = os.path.join(video_dir, "subtitles")
        print(f"\n  subtitles/")
        for sub_file in os.listdir(subtitle_dir):
            sub_path = os.path.join(subtitle_dir, sub_file)
            sub_size = os.path.getsize(sub_path) / 1024
            print(f"    {sub_file} ({sub_size:.2f} KB)")
    
    print("-" * 60)
    
    if original_found:
        print("✓ 原视频已找到")
    else:
        print("✗ 原视频未找到")
    
    if completed_found:
        print("✓ 已完成视频已找到")
    else:
        print("✗ 已完成视频未找到")
    
    if report_found:
        print("✓ 分析报告已找到")
    else:
        print("✗ 分析报告未找到")
    
    if social_found:
        print("✓ 社交媒体文案已找到")
    else:
        print("✗ 社交媒体文案未找到")
    
    print("\n" + "=" * 60)
    print("测试完成！")
    print("=" * 60)
    
    print(f"\n文件结构:")
    print(f"  {video_dir}/")
    print(f"    ├── {os.path.basename(video_path)}          ← 原视频")
    print(f"    ├── {os.path.basename(subtitle_result.embedded_video_path)}  ← 已完成视频")
    print(f"    ├── {os.path.basename(analysis_result.report_path)}        ← 分析报告")
    print(f"    └── subtitles/")
    print(f"        └── {os.path.basename(subtitle_result.subtitle_path)}  ← 字幕文件")


if __name__ == "__main__":
    main()