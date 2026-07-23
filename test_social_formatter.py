"""
测试社交媒体文案生成器 - 高学习价值版
"""

import sys
import os

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, PROJECT_ROOT)

from core.social_media_formatter import SocialMediaFormatter, SocialStyle


def test_formatter():
    """测试文案生成器"""
    formatter = SocialMediaFormatter()
    
    test_subtitles = [
        {"text": "The significant impact of technology on modern society cannot be underestimated.", "translated_text": "技术对现代社会的重大影响不容忽视。"},
        {"text": "Education has the power to transform lives and create opportunities for all.", "translated_text": "教育有能力改变生活，为所有人创造机会。"},
        {"text": "Scientists continue to explore new possibilities for sustainable development.", "translated_text": "科学家继续探索可持续发展的新可能性。"},
        {"text": "We need to focus on finding solutions that benefit both individuals and communities.", "translated_text": "我们需要专注于寻找对个人和社区都有益的解决方案。"},
        {"text": "The project aims to promote healthy living through education and awareness.", "translated_text": "该项目旨在通过教育和意识提升促进健康生活。"},
        {"text": "It's important to analyze the data carefully before making any decisions.", "translated_text": "在做出任何决定之前，仔细分析数据很重要。"},
        {"text": "Climate change will significantly impact future generations if we don't act now.", "translated_text": "如果我们现在不采取行动，气候变化将对后代产生重大影响。"},
        {"text": "Every small action can contribute to building a better world for everyone.", "translated_text": "每一个小行动都可以为每个人建设一个更美好的世界做出贡献。"},
        {"text": "The company strives to maintain high standards of quality in all its products.", "translated_text": "公司努力在其所有产品中保持高标准的质量。"},
        {"text": "We should explore different approaches to solve this complex problem.", "translated_text": "我们应该探索不同的方法来解决这个复杂的问题。"},
        {"text": "After careful evaluation, we decided to implement the new strategy immediately.", "translated_text": "经过仔细评估，我们决定立即实施新战略。"},
        {"text": "The research reveals interesting insights into human behavior and decision-making.", "translated_text": "研究揭示了关于人类行为和决策的有趣见解。"},
        {"text": "Technology continues to evolve at a rapid pace, transforming every aspect of our lives.", "translated_text": "技术继续快速发展，改变我们生活的方方面面。"},
        {"text": "It is essential to establish strong relationships based on trust and mutual respect.", "translated_text": "基于信任和相互尊重建立牢固的关系至关重要。"},
        {"text": "The findings suggest that early intervention can significantly improve outcomes.", "translated_text": "研究结果表明，早期干预可以显著改善结果。"},
    ]
    
    print("=" * 60)
    print("测试小红书风格 - 口语学习模式")
    print("=" * 60)
    result = formatter.format("test_video_1", test_subtitles, "口语学习", style=SocialStyle.XIAOHONGSHU)
    if result.success:
        print(result.content)
        print()
    
    print("=" * 60)
    print("测试小红书风格 - 应试学习模式")
    print("=" * 60)
    result = formatter.format("test_video_1", test_subtitles, "应试学习", style=SocialStyle.XIAOHONGSHU)
    if result.success:
        print(result.content)
        print()
    
    print("=" * 60)
    print("测试知乎风格 - 应试学习模式")
    print("=" * 60)
    result = formatter.format("test_video_1", test_subtitles, "应试学习", style=SocialStyle.ZHIHU)
    if result.success:
        print(result.content)
        print()


if __name__ == "__main__":
    test_formatter()