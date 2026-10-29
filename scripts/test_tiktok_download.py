"""
test_tiktok_download.py — TikTok / 抖音链接识别 离线回归

只验证**不联网**的纯函数：
  - detect_video_site 平台识别
  - extract_tiktok_video_id 数字 id 提取
  - fallback_tiktok_id 短链兜底 id 的稳定性
  - to_pipeline_video 元数据映射（pipeline candidate 结构）

运行：
  d:\\python\\python.exe scripts\\test_tiktok_download.py
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.video_url import (  # noqa: E402
    detect_video_site, extract_tiktok_video_id, fallback_tiktok_id,
    to_pipeline_video,
)

_passed = 0
_failed = 0


def record(name: str, ok: bool, detail: str = "") -> None:
    global _passed, _failed
    if ok:
        _passed += 1
        print(f"  [PASS] {name}" + (f" — {detail}" if detail else ""))
    else:
        _failed += 1
        print(f"  [FAIL] {name}" + (f" — {detail}" if detail else ""))


def test_detect() -> None:
    print("\n[平台识别]")
    cases = [
        ("https://www.youtube.com/watch?v=dQw4w9WgXcQ", "youtube"),
        ("https://youtu.be/dQw4w9WgXcQ", "youtube"),
        ("https://m.youtube.com/watch?v=abc12345678", "youtube"),
        ("https://www.tiktok.com/@user/video/7412345678901234567", "tiktok"),
        ("https://vm.tiktok.com/ZMabcDEF12/", "tiktok"),
        ("https://www.douyin.com/video/7300000000000000000", "tiktok"),
        ("https://v.douyin.com/iRabcDEF/", "tiktok"),
        ("https://example.com/video/123", ""),
        ("dQw4w9WgXcQ", ""),
        ("", ""),
    ]
    ok = True
    for url, expect in cases:
        got = detect_video_site(url)
        if got != expect:
            ok = False
            record(f"detect({url[:46]})", False, f"期望 {expect!r} 实际 {got!r}")
    record("TC-TT01 平台识别（YouTube/TikTok/抖音/未知）", ok, f"{len(cases)} 个用例")


def test_extract() -> None:
    print("\n[ID 提取]")
    url = "https://www.tiktok.com/@user/video/7412345678901234567?is_from_webapp=1"
    record("TC-TT02 TikTok 标准链接", extract_tiktok_video_id(url) == "7412345678901234567")

    record("TC-TT03 抖音标准链接",
           extract_tiktok_video_id("https://www.douyin.com/video/7300000000000000000")
           == "7300000000000000000")

    record("TC-TT04 note/photo 链接",
           extract_tiktok_video_id("https://www.tiktok.com/@u/photo/7412345678901234567")
           == "7412345678901234567")

    record("TC-TT05 TikTok 短链拿不到 id（需重定向）",
           extract_tiktok_video_id("https://vm.tiktok.com/ZMabcDEF12/") is None)

    record("TC-TT06 抖音短链拿不到 id（需重定向）",
           extract_tiktok_video_id("https://v.douyin.com/iRabcDEF/") is None)

    record("TC-TT07 非视频链接返回 None",
           extract_tiktok_video_id("https://www.tiktok.com/@user") is None)


def test_fallback() -> None:
    print("\n[短链兜底 id]")
    u = "https://vm.tiktok.com/ZMabcDEF12/"
    a, b = fallback_tiktok_id(u), fallback_tiktok_id(u)
    record("TC-TT08 同一链接兜底 id 稳定", a == b, a)
    record("TC-TT09 兜底 id 前缀 tt_", a.startswith("tt_") and len(a) == 19, a)
    record("TC-TT10 不同链接 id 不同",
           fallback_tiktok_id(u) != fallback_tiktok_id("https://vm.tiktok.com/other/"))


def test_mapping() -> None:
    print("\n[pipeline 结构映射]")
    info = {
        "source_url": "https://www.tiktok.com/@chef/video/7412345678901234567",
        "title": "5 分钟学会煎牛排",
        "channel_name": "chef",
        "duration": "00:58",
        "language": "en-US",
        "thumbnail": "https://p16-sign.tiktokcdn.com/x.jpg",
        "platform": "tiktok",
    }
    v = to_pipeline_video(info)
    record("TC-TT11 id/title/channel 正确",
           v["youtube_id"] == "7412345678901234567"
           and v["yt_video_id"] == v["youtube_id"]
           and v["title"] == "5 分钟学会煎牛排"
           and v["channel"] == "chef")
    record("TC-TT12 语言归一化 en-US → en", v["lang"] == "en", str(v["lang"]))
    record("TC-TT13 默认走 ASR（平台无字幕）", v["is_asr"] is True)
    record("TC-TT14 封面透传", v["thumbnail"].startswith("https://p16-sign"))

    short = to_pipeline_video({"title": "x"}, "https://v.douyin.com/iRabcDEF/")
    record("TC-TT15 短链信息缺失时用稳定兜底 id",
           short["youtube_id"].startswith("tt_") and short["source_url"].endswith("/"),
           short["youtube_id"])

    weird = to_pipeline_video({"duration": 58, "language": None})
    record("TC-TT16 非字符串 duration / 空语言安全处理",
           weird["duration"] == "" and weird["lang"] is None)


def main() -> int:
    print("=" * 60)
    print("TikTok 下载 · 离线回归")
    print("=" * 60)
    test_detect()
    test_extract()
    test_fallback()
    test_mapping()
    print("\n" + "=" * 60)
    print(f"结果: {_passed} 通过, {_failed} 失败")
    print("=" * 60)
    return 0 if _failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
