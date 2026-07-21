"""
字幕处理测试脚本

测试语音识别、翻译和字幕嵌入功能。
"""

import os
import sys

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, PROJECT_ROOT)

FFMPEG_BIN_DIR = os.path.join(PROJECT_ROOT, "bin", "ffmpeg", "bin")
if FFMPEG_BIN_DIR not in os.environ["PATH"]:
    os.environ["PATH"] = f"{FFMPEG_BIN_DIR};{os.environ['PATH']}"
    print(f"已添加 ffmpeg 到 PATH: {FFMPEG_BIN_DIR}")

from core.subtitle_processor import process_video_subtitle, SubtitleResult
from utils.enums import LanguageType, VideoCategory


def main() -> None:
    """主测试函数"""
    print("=" * 60)
    print("字幕处理测试")
    print("=" * 60)
    
    test_videos = [
        {
            "video_id": "test_3",
            "video_path": r"D:\Ideas\VideoCrawler\Vc\output\en\daily\test_3_Me_at_the_zoo.mp4",
            "language": LanguageType.ENGLISH,
            "category": VideoCategory.DAILY,
            "source_lang": "en",
            "target_lang": "zh-CN",
        },
    ]
    
    success_count = 0
    fail_count = 0
    
    for video in test_videos:
        print(f"\n正在处理: {video['video_id']}")
        print(f"视频路径: {video['video_path']}")
        
        if not os.path.exists(video["video_path"]):
            print(f"✗ 视频文件不存在")
            fail_count += 1
            continue
        
        try:
            result = process_video_subtitle(
                video_id=video["video_id"],
                video_path=video["video_path"],
                language=video["language"],
                category=video["category"],
                source_lang=video["source_lang"],
                target_lang=video["target_lang"]
            )
            
            if result.success:
                success_count += 1
                print(f"✓ 处理成功")
                print(f"  字幕文件: {result.subtitle_path}")
                print(f"  嵌入字幕视频: {result.embedded_video_path}")
                print(f"  是否有原字幕: {result.has_original_subtitle}")
            else:
                fail_count += 1
                print(f"✗ 处理失败: {result.error_message}")
                
        except Exception as e:
            fail_count += 1
            print(f"✗ 处理异常: {e}")
            import traceback
            traceback.print_exc()
    
    print("\n" + "=" * 60)
    print(f"测试完成，成功: {success_count}，失败: {fail_count}")
    print("=" * 60)
    
    if fail_count > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
