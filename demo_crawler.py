"""
全量爬虫 Demo 测试脚本

Day6 任务：测试德/法/西关键词检索过滤功能

支持两种模式：
    1. 在线模式：真实访问视频网站
    2. 模拟模式：使用 mock 数据进行本地测试（默认）
"""

import sys
import os
import json
import time
import argparse
from typing import Dict, List, Any, Optional

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from utils.logger import init_logger
from utils.enums import LanguageType
from utils.path_helper import get_output_dir, get_tmp_dir
from core.spiders import (
    YoutubeSpider,
    VimeoSpider,
    DailymotionSpider,
    BilibiliSpider,
    VideoSpider,
)


class MockSpider(VideoSpider):
    """模拟爬虫（用于本地测试）"""
    
    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._mock_data = self._generate_mock_data()
    
    def _generate_mock_data(self) -> Dict[str, List[Dict[str, Any]]]:
        """生成模拟数据"""
        return {
            "german": [
                {"title": "Deutsch Lernen für Anfänger", "source_url": "https://youtube.com/watch?v=g1", "description": "Lernen Sie Deutsch einfach und schnell"},
                {"title": "Kochrezepte deutsch", "source_url": "https://youtube.com/watch?v=g2", "description": "Leckere deutsche Gerichte"},
                {"title": "Reise durch Deutschland", "source_url": "https://youtube.com/watch?v=g3", "description": "Schöne Städte und Landschaften"},
                {"title": "German Tech Tutorial", "source_url": "https://youtube.com/watch?v=g4", "description": "Technologie auf Deutsch"},
                {"title": "Klassik Musik", "source_url": "https://youtube.com/watch?v=g5", "description": "Deutsche Klassik"},
            ],
            "french": [
                {"title": "Apprendre le français", "source_url": "https://youtube.com/watch?v=f1", "description": "Apprendre le français facilement"},
                {"title": "Recettes françaises", "source_url": "https://youtube.com/watch?v=f2", "description": "Délicieuses recettes françaises"},
                {"title": "Voyage en France", "source_url": "https://youtube.com/watch?v=f3", "description": "Belles villes et paysages"},
                {"title": "Tutoriel informatique français", "source_url": "https://youtube.com/watch?v=f4", "description": "Technologie en français"},
                {"title": "Musique classique française", "source_url": "https://youtube.com/watch?v=f5", "description": "Classique français"},
            ],
            "spanish": [
                {"title": "Aprender español", "source_url": "https://youtube.com/watch?v=s1", "description": "Aprender español fácilmente"},
                {"title": "Recetas españolas", "source_url": "https://youtube.com/watch?v=s2", "description": "Deliciosas recetas españolas"},
                {"title": "Viaje por España", "source_url": "https://youtube.com/watch?v=s3", "description": "Ciudades y paisajes hermosos"},
                {"title": "Tutorial de tecnología", "source_url": "https://youtube.com/watch?v=s4", "description": "Tecnología en español"},
                {"title": "Música clásica española", "source_url": "https://youtube.com/watch?v=s5", "description": "Clásico español"},
            ],
        }
    
    def search(
        self,
        query: str,
        max_pages: int = 5,
        filter_languages: Optional[List[LanguageType]] = None,
        **kwargs
    ) -> List[Dict[str, Any]]:
        """模拟搜索"""
        print(f"  [模拟] 搜索: '{query}'")
        
        # 根据关键词判断语言
        language_key = "german"
        if "français" in query.lower() or "france" in query.lower():
            language_key = "french"
        elif "español" in query.lower() or "españa" in query.lower():
            language_key = "spanish"
        
        videos = self._mock_data.get(language_key, [])
        
        # 模拟分页
        videos = videos[:max_pages * 2]
        
        # 模拟语言过滤
        if filter_languages:
            filtered = []
            for video in videos:
                title_lang, _ = self._detect_video_language(video)
                if title_lang in [lang.value for lang in filter_languages]:
                    filtered.append(video)
            videos = filtered
        
        print(f"    获取 {len(videos)} 个视频")
        return videos
    
    def _detect_video_language(self, video: Dict[str, Any]) -> Tuple[str, float]:
        """简单的语言检测"""
        title = video.get("title", "")
        
        if any(word in title.lower() for word in ["deutsch", "german"]):
            return ("de", 0.9)
        elif any(word in title.lower() for word in ["français", "france", "french"]):
            return ("fr", 0.9)
        elif any(word in title.lower() for word in ["español", "españa", "spanish"]):
            return ("es", 0.9)
        return ("en", 0.5)
    
    def get_video_info(self, video_url: str) -> Optional[Dict[str, Any]]:
        """模拟获取视频详情"""
        return {"title": "Mock Video", "source_url": video_url}
    
    def get_channel_videos(
        self,
        channel_url: str,
        max_pages: int = 5,
        filter_languages: Optional[List[LanguageType]] = None
    ) -> List[Dict[str, Any]]:
        """模拟获取频道视频"""
        return []
    
    def parse(self, html: str, url: str) -> List[Dict[str, Any]]:
        """模拟解析"""
        return []
    
    def _build_search_url(self, query: str, page: int = 1) -> str:
        """模拟构建搜索 URL"""
        return f"https://mock.com/search?q={query}&page={page}"
    
    def _extract_video_id(self, url: str) -> Optional[str]:
        """模拟提取视频 ID"""
        return "mock_id"


class CrawlerDemo:
    """全量爬虫 Demo 测试类"""
    
    def __init__(self, online_mode: bool = False) -> None:
        """初始化 Demo
        
        Args:
            online_mode: 是否在线模式（真实访问网站）
        """
        init_logger("DEBUG")
        
        self._online_mode = online_mode
        self._output_dir = get_output_dir()
        self._tmp_dir = get_tmp_dir()
        
        self._keywords = {
            "german": [
                "Deutsch Lernen",
                "Kochrezepte",
                "Reise Deutschland",
                "Technologie Tutorial",
                "Musik Klassik",
            ],
            "french": [
                "Apprendre Français",
                "Recettes de cuisine",
                "Voyage France",
                "Tutoriel Informatique",
                "Musique Classique",
            ],
            "spanish": [
                "Aprender Español",
                "Recetas de cocina",
                "Viaje España",
                "Tutorial Tecnologia",
                "Musica Clasica",
            ],
        }
        
        self._language_filter = {
            "german": [LanguageType.GERMAN],
            "french": [LanguageType.FRENCH],
            "spanish": [LanguageType.SPANISH],
        }
        
        self._spiders: Dict[str, VideoSpider] = {}
        
        self._results: Dict[str, Any] = {
            "total_videos": 0,
            "by_site": {},
            "by_language": {},
            "errors": [],
            "mode": "online" if online_mode else "mock",
            "test_time": time.strftime("%Y-%m-%d %H:%M:%S"),
        }
    
    def _init_spiders(self) -> None:
        """初始化爬虫实例"""
        print("\n" + "=" * 60)
        print("初始化爬虫实例")
        print(f"模式: {'在线模式' if self._online_mode else '模拟模式'}")
        print("=" * 60)
        
        if self._online_mode:
            spider_classes = [
                ("youtube", YoutubeSpider),
                ("vimeo", VimeoSpider),
                ("dailymotion", DailymotionSpider),
                ("bilibili", BilibiliSpider),
            ]
        else:
            spider_classes = [
                ("mock_youtube", MockSpider),
                ("mock_vimeo", MockSpider),
                ("mock_dailymotion", MockSpider),
                ("mock_bilibili", MockSpider),
            ]
        
        for site_name, spider_class in spider_classes:
            try:
                self._spiders[site_name] = spider_class()
                display_name = site_name.replace("mock_", "").capitalize()
                print(f"✓ {display_name} 爬虫初始化成功")
            except Exception as e:
                display_name = site_name.replace("mock_", "").capitalize()
                print(f"✗ {display_name} 爬虫初始化失败: {e}")
                self._results["errors"].append({
                    "site": site_name,
                    "error": str(e),
                    "type": "init",
                })
    
    def _run_search_test(
        self,
        spider: VideoSpider,
        site_name: str,
        language_key: str,
        keywords: List[str],
        max_pages: int = 2
    ) -> List[Dict[str, Any]]:
        """运行搜索测试"""
        all_videos: List[Dict[str, Any]] = []
        
        for keyword in keywords:
            print(f"  搜索: '{keyword}'")
            
            try:
                videos = spider.search(
                    query=keyword,
                    max_pages=max_pages,
                    filter_languages=self._language_filter.get(language_key)
                )
                
                all_videos.extend(videos)
                
            except Exception as e:
                print(f"    ✗ 搜索失败: {e}")
                self._results["errors"].append({
                    "site": site_name,
                    "language": language_key,
                    "keyword": keyword,
                    "error": str(e),
                    "type": "search",
                })
        
        return all_videos
    
    def run(self) -> Dict[str, Any]:
        """运行全量测试"""
        print("\n" + "=" * 60)
        print("Day6 全量爬虫 Demo 测试")
        print("=" * 60)
        print(f"测试时间: {time.strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"输出目录: {self._output_dir}")
        print(f"临时目录: {self._tmp_dir}")
        
        self._init_spiders()
        
        for site_name, spider in self._spiders.items():
            display_name = site_name.replace("mock_", "").capitalize()
            print(f"\n{'=' * 60}")
            print(f"测试 {display_name}")
            print(f"{'=' * 60}")
            
            site_results: Dict[str, List[Dict[str, Any]]] = {}
            
            for language_key, keywords in self._keywords.items():
                print(f"\n  [{language_key.upper()}]")
                
                videos = self._run_search_test(
                    spider=spider,
                    site_name=site_name,
                    language_key=language_key,
                    keywords=keywords,
                    max_pages=2
                )
                
                site_results[language_key] = videos
                
                if language_key not in self._results["by_language"]:
                    self._results["by_language"][language_key] = 0
                self._results["by_language"][language_key] += len(videos)
            
            self._results["by_site"][site_name] = site_results
            self._results["total_videos"] += sum(
                len(videos) for videos in site_results.values()
            )
        
        self._save_results()
        self._print_report()
        
        return self._results
    
    def _save_results(self) -> None:
        """保存测试结果到文件"""
        print(f"\n{'=' * 60}")
        print("保存测试结果")
        print(f"{'=' * 60}")
        
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        mode_suffix = "_online" if self._online_mode else "_mock"
        result_file = os.path.join(self._output_dir, f"crawler_demo_{timestamp}{mode_suffix}.json")
        
        try:
            with open(result_file, "w", encoding="utf-8") as f:
                json.dump(self._results, f, ensure_ascii=False, indent=2)
            
            print(f"✓ 测试结果已保存: {result_file}")
        except Exception as e:
            print(f"✗ 保存失败: {e}")
    
    def _print_report(self) -> None:
        """输出测试报告"""
        print(f"\n{'=' * 60}")
        print("测试报告")
        print(f"{'=' * 60}")
        
        print(f"\n测试模式: {'在线模式' if self._online_mode else '模拟模式'}")
        print(f"总视频数: {self._results['total_videos']}")
        
        print("\n按网站统计:")
        for site_name, site_results in self._results["by_site"].items():
            display_name = site_name.replace("mock_", "").capitalize()
            total = sum(len(videos) for videos in site_results.values())
            print(f"  {display_name}: {total} 个视频")
            for lang, videos in site_results.items():
                print(f"    {lang}: {len(videos)}")
        
        print("\n按语言统计:")
        for lang, count in self._results["by_language"].items():
            print(f"  {lang}: {count} 个视频")
        
        if self._results["errors"]:
            print(f"\n错误统计 ({len(self._results['errors'])}):")
            for error in self._results["errors"][:5]:
                print(f"  - [{error['site']}] {error['type']}: {error.get('keyword', '')} - {error['error']}")
            if len(self._results["errors"]) > 5:
                print(f"  ... 还有 {len(self._results['errors']) - 5} 个错误")
        else:
            print("\n错误统计: 无")


def main():
    """主函数"""
    parser = argparse.ArgumentParser(description="全量爬虫 Demo 测试")
    parser.add_argument("--online", action="store_true", help="在线模式（真实访问网站）")
    args = parser.parse_args()
    
    try:
        demo = CrawlerDemo(online_mode=args.online)
        results = demo.run()
        
        if results["total_videos"] > 0:
            print("\n✓ 全量爬虫 Demo 测试完成！")
            return 0
        else:
            if args.online:
                print("\n✗ 在线测试未获取到视频，请检查网络连接")
            else:
                print("\n✗ 模拟测试未获取到视频，可能存在问题")
            return 1
            
    except Exception as e:
        print(f"\n✗ 测试运行失败: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())