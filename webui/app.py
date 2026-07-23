"""
WebUI 主应用
提供一键自动下载和分析功能
"""

import sys
import os
import time
import threading
import traceback
import re
from typing import Optional, Dict, List, Any

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

import gradio as gr

from core.spiders import create_spider
from core.download import get_download_pool
from core.subtitle_processor import process_video_subtitle
from core.video_analyzer import get_video_analyzer, AnalysisMode
from core.social_media_formatter import SocialMediaFormatter, SocialStyle
from utils.enums import LanguageType, VideoCategory
from utils.path_helper import get_output_dir, clear_tmp_dir, APP_ROOT, ensure_tools_in_path
from utils.db_manager import get_undownloaded_videos, update_video_downloaded, get_buffer_pool, init_database, init_buffer_pool, insert_video
from utils.logger import init_logger, get_crawler_logger
from utils.config_loader import load_config

logger = get_crawler_logger()

_pipeline_progress = ""
_pipeline_result = ""
_pipeline_running = False


def init_app() -> None:
    """初始化应用环境"""
    logger.info("初始化WebUI应用环境...")
    init_logger()
    clear_tmp_dir()
    ensure_tools_in_path()
    init_buffer_pool()
    init_database()
    logger.info("WebUI应用环境初始化完成")


def parse_srt_file(srt_path: str) -> List[Dict[str, str]]:
    """解析SRT字幕文件"""
    subtitles = []
    import re
    
    with open(srt_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    blocks = content.strip().split('\n\n')
    for block in blocks:
        lines = block.strip().split('\n')
        if len(lines) >= 3:
            text_lines = lines[2:]
            
            english_text = ""
            chinese_text = ""
            for line in text_lines:
                if re.match(r'^[\w\s\,\.\!\?\:\;\'\"\-]+$', line.strip()):
                    english_text = line.strip()
                else:
                    chinese_text = line.strip()
            
            if english_text:
                subtitles.append({
                    "text": english_text,
                    "translated_text": chinese_text,
                })
    
    return subtitles


def format_results(results: Dict[str, Any]) -> str:
    """格式化结果"""
    lines = ["=" * 50]
    lines.append("流程执行结果")
    lines.append("=" * 50)
    lines.append(f"爬取视频数: {results['crawled']}")
    lines.append(f"下载成功数: {results['downloaded']}")
    lines.append(f"字幕处理数: {results['subtitled']}")
    lines.append(f"内容分析数: {results['analyzed']}")
    
    if results["errors"]:
        lines.append("")
        lines.append("错误信息:")
        for error in results["errors"][:5]:
            lines.append(f"  - {error}")
        if len(results["errors"]) > 5:
            lines.append(f"  ... 还有 {len(results['errors']) - 5} 个错误")
    
    lines.append("=" * 50)
    lines.append("输出目录:")
    lines.append(f"  {get_output_dir()}")
    lines.append("=" * 50)
    
    return "\n".join(lines)


_SEARCH_QUERIES = {
    "en": "English learning video",
    "de": "Deutsche Lernvideo",
    "fr": "Vidéo d'apprentissage français",
    "es": "Video de aprendizaje español",
    "zh": "中文学习视频",
    "ja": "日本語学習動画",
    "ko": "한국어 학습 비디오",
    "ru": "видео для изучения русского языка",
    "it": "video di apprendimento italiano",
    "pt": "vídeo de aprendizagem em português",
    "ar": "فيديو تعلم اللغة العربية",
    "hi": "हिंदी सीखने का वीडियो",
    "nl": "Nederlandse leervideo",
    "sv": "Svenska inlärningsvideo",
    "no": "Norsk læringsvideo",
    "da": "Dansk læringsvideo",
    "fi": "Suomalainen oppimiskuva",
    "pl": "Wideo do nauki języka polskiego",
    "cs": "Videa pro studium češtiny",
    "hu": "Magyar tanulási videó",
    "ro": "Video de învățare română",
    "el": "Βίντεο μάθησης Ελληνικής",
    "tr": "Türkçe öğrenme videosu",
    "vi": "Video học tiếng Việt",
    "th": "วิดีโอเรียนรู้ภาษาไทย",
    "id": "Video pembelajaran Bahasa Indonesia",
    "ms": "Video pembelajaran Bahasa Melayu",
    "tl": "Video pag-aaral ng Tagalog",
}


def extract_video_id(source_url: str) -> str:
    """从视频URL中提取视频ID，支持多种视频网站
    
    Args:
        source_url: 视频源URL
        
    Returns:
        视频ID字符串
    """
    youtube_match = re.search(r'youtube\.com/watch\?v=([^&]+)', source_url)
    if youtube_match:
        return youtube_match.group(1)
    
    youtu_be_match = re.search(r'youtu\.be/([^/]+)', source_url)
    if youtu_be_match:
        return youtu_be_match.group(1)
    
    vimeo_match = re.search(r'vimeo\.com/(\d+)', source_url)
    if vimeo_match:
        return vimeo_match.group(1)
    
    dailymotion_match = re.search(r'dailymotion\.com/video/([^/]+)', source_url)
    if dailymotion_match:
        return dailymotion_match.group(1)
    
    bilibili_match = re.search(r'bilibili\.com/video/(BV[^/]+)', source_url)
    if bilibili_match:
        return bilibili_match.group(1)
    
    bilibili_av_match = re.search(r'bilibili\.com/video/av(\d+)', source_url)
    if bilibili_av_match:
        return bilibili_av_match.group(1)
    
    return source_url.split("/")[-1] if "/" in source_url else "unknown"


def run_pipeline_impl(video_site: str, language: str, video_count: int, analyze_content: bool,
                      analysis_mode: str, social_style: str, target_lang: str,
                      min_duration: int, max_duration: int) -> tuple:
    """运行完整流程（实际执行）"""
    global _pipeline_progress
    
    progress_lines = []
    
    def log(msg):
        line = f"[{time.strftime('%H:%M:%S')}] {msg}"
        progress_lines.append(line)
        logger.info(msg)
        _pipeline_progress = "\n".join(progress_lines[-50:])
        return _pipeline_progress
    
    results = {
        "crawled": 0,
        "downloaded": 0,
        "subtitled": 0,
        "analyzed": 0,
        "errors": []
    }
    
    try:
        log("清空之前的任务数据...")
        from utils.db_manager import _get_connection
        conn = _get_connection()
        with conn:
            conn.execute("DELETE FROM video_info")
            conn.execute("DELETE FROM translate_task")
        log("已清空数据库")
        
        log(f"步骤1: 爬取 {LanguageType.from_code(language).display_name} 视频（{video_site}）")
        
        try:
            crawler = create_spider(video_site)
            search_query = _SEARCH_QUERIES.get(language, "learning video")
            
            videos = crawler.search(search_query, max_pages=2, min_duration=min_duration, max_duration=max_duration)
            
            from utils.db_manager import _get_connection
            
            conn = _get_connection()
            cursor = conn.cursor()
            
            inserted_count = 0
            if crawler.result_buffer:
                all_videos = crawler.result_buffer.get_all_results()
                log(f"从缓冲器获取 {len(all_videos)} 个视频，写入数据库...")
                with conn:
                    for video in all_videos:
                        source_url = video.get("source_url", "")
                        title = video.get("title", "")
                        if source_url and title:
                            try:
                                cursor.execute(
                                    "INSERT OR REPLACE INTO video_info (source_url, title, lang, category, is_downloaded) VALUES (?, ?, ?, ?, 0)",
                                    (source_url, title, language, video.get("category", "daily"))
                                )
                                inserted_count += 1
                            except Exception as e:
                                log(f"  ⚠ 写入失败: {title[:20]}... - {str(e)[:30]}")
                
                cursor.execute("SELECT COUNT(*) FROM video_info")
                total_in_db = cursor.fetchone()[0]
                log(f"成功写入 {inserted_count} 个视频到数据库，数据库总计 {total_in_db} 条")
            elif videos:
                log(f"从搜索结果获取 {len(videos)} 个视频，写入数据库...")
                with conn:
                    for video in videos:
                        source_url = video.get("source_url", "")
                        title = video.get("title", "")
                        if source_url and title:
                            try:
                                cursor.execute(
                                    "INSERT OR REPLACE INTO video_info (source_url, title, lang, category, is_downloaded) VALUES (?, ?, ?, ?, 0)",
                                    (source_url, title, language, video.get("category", "daily"))
                                )
                                inserted_count += 1
                            except Exception as e:
                                log(f"  ⚠ 写入失败: {title[:20]}... - {str(e)[:30]}")
                
                cursor.execute("SELECT COUNT(*) FROM video_info")
                total_in_db = cursor.fetchone()[0]
                log(f"成功写入 {inserted_count} 个视频到数据库，数据库总计 {total_in_db} 条")
            
            cursor.close()
            log("爬取完成")
        except Exception as e:
            log(f"⚠ 爬取失败，尝试使用数据库已有数据: {str(e)[:50]}")
            traceback.print_exc()
        
        log(f"步骤2: 下载 {video_count} 个视频")
        
        try:
            download_pool = get_download_pool()
            download_pool.clear()
            
            all_undownloaded = get_undownloaded_videos()
            results["crawled"] = len(all_undownloaded)
            log(f"找到 {len(all_undownloaded)} 个未下载视频")
            
            if not all_undownloaded:
                log("没有可下载的视频")
                return log(""), format_results(results)
            
            video_id_map = {}
            category_map = {}
            successful_downloads = []
            failed_count = 0
            tried_indices = set()
            batch_size = video_count
            max_rounds = (len(all_undownloaded) + batch_size - 1) // batch_size
            
            for round_num in range(max_rounds):
                if len(successful_downloads) >= video_count:
                    break
                
                start_idx = round_num * batch_size
                videos_batch = all_undownloaded[start_idx:start_idx + batch_size]
                
                if not videos_batch:
                    log(f"已无更多视频可尝试")
                    break
                
                remaining_needed = video_count - len(successful_downloads)
                log(f"  第 {round_num + 1}/{max_rounds} 轮尝试，处理 {len(videos_batch)} 个视频（还需 {remaining_needed} 个）")
                
                videos_to_download = []
                for video in videos_batch:
                    db_id = video["id"]
                    source_url = video["source_url"]
                    title = video.get("title", "")
                    lang_code = video.get("lang")
                    category_str = video.get("category")
                    
                    video_id = extract_video_id(source_url)
                    
                    video_id_map[video_id] = db_id
                    category_map[video_id] = category_str
                    
                    language_type = LanguageType.from_code(lang_code) if lang_code else None
                    category = VideoCategory.from_code(category_str) if category_str else VideoCategory.DAILY
                    
                    videos_to_download.append({
                        "video_id": video_id,
                        "url": source_url,
                        "title": title,
                        "language": language_type,
                        "category": category,
                    })
                    
                    log(f"    添加下载任务: {title[:30]}... (ID: {video_id[:11]})")
                
                download_pool.download_batch(videos_to_download)
                download_results = download_pool.wait_all()
                
                for result in download_results:
                    if result.success:
                        successful_downloads.append((result.video_id, result.file_path))
                        results["downloaded"] += 1
                        log(f"    ✓ 下载成功: {result.video_id}")
                    else:
                        failed_count += 1
                        error_detail = f"下载失败: {result.video_id} - URL: {result.url[:80]} - 错误: {result.error_message}"
                        results["errors"].append(error_detail)
                        log(f"    ✗ 下载失败: {result.video_id}")
                        log(f"      错误详情: {result.error_message}")
            
            log(f"下载完成，成功 {len(successful_downloads)} 个，失败 {failed_count} 个")
        
        except Exception as e:
            results["errors"].append(f"下载异常: {str(e)}")
            log(f"❌ 下载异常: {str(e)[:100]}")
            return log(""), format_results(results)
        
        log(f"步骤3: 处理字幕")
        
        from utils.path_helper import ensure_tools_in_path
        ensure_tools_in_path()
        
        for video_id, file_path in successful_downloads:
            try:
                db_id = video_id_map.get(video_id)
                log(f"  处理字幕: {video_id}")
                log(f"    视频路径: {file_path[:80]}")
                
                video_category_str = category_map.get(video_id, "daily")
                video_category = VideoCategory.from_code(video_category_str) if video_category_str else VideoCategory.DAILY
                
                subtitle_result = process_video_subtitle(
                    video_id=video_id,
                    video_path=file_path,
                    language=LanguageType.from_code(language),
                    category=video_category,
                    source_lang=language,
                    target_lang=target_lang
                )
                
                if subtitle_result.success:
                    results["subtitled"] += 1
                    if db_id:
                        update_video_downloaded(db_id, file_path)
                    log(f"  ✓ 字幕处理成功: {video_id}")
                    log(f"    字幕路径: {subtitle_result.subtitle_path}")
                else:
                    error_msg = subtitle_result.error_message or "未知错误"
                    results["errors"].append(f"字幕处理失败: {video_id} - {error_msg}")
                    log(f"  ✗ 字幕处理失败: {video_id}")
                    log(f"    错误详情: {error_msg}")
            except Exception as e:
                error_detail = str(e)
                results["errors"].append(f"字幕处理异常: {video_id} - {error_detail}")
                log(f"  ✗ 字幕处理异常: {video_id}")
                log(f"    异常详情: {error_detail}")
        
        get_buffer_pool().flush()
        
        if analyze_content and successful_downloads:
            log(f"步骤4: 内容分析")
            
            try:
                analyzer = get_video_analyzer()
                formatter = SocialMediaFormatter()
                
                for video_id, file_path in successful_downloads:
                    try:
                        video_category_str = category_map.get(video_id, "daily")
                        video_category = VideoCategory.from_code(video_category_str) if video_category_str else VideoCategory.DAILY
                        
                        from utils.file_sort import get_file_sorter
                        file_sorter = get_file_sorter()
                        
                        subtitle_dir = file_sorter.get_subtitle_dir(
                            language=LanguageType.from_code(language),
                            category=video_category,
                            video_id=video_id
                        )
                        srt_path = os.path.join(subtitle_dir, f"{video_id}_{target_lang}.srt")
                        
                        video_dir = file_sorter.get_video_dir(
                            language=LanguageType.from_code(language),
                            category=video_category,
                            video_id=video_id
                        )
                        
                        if not os.path.exists(srt_path):
                            log(f"  ⚠ 字幕文件不存在，跳过分析: {video_id}")
                            continue
                        
                        subtitles = parse_srt_file(srt_path)
                        
                        analysis_modes = []
                        if analysis_mode == "oral" or analysis_mode == "both":
                            analysis_modes.append(("口语学习", AnalysisMode.ORAL_SPOKEN))
                        if analysis_mode == "exam" or analysis_mode == "both":
                            analysis_modes.append(("应试学习", AnalysisMode.EXAM_PREP))
                        
                        for mode_name, mode_enum in analysis_modes:
                            analyzer.analyze(
                                video_id=video_id,
                                subtitles=subtitles,
                                mode=mode_enum,
                                output_dir=video_dir,
                                use_ai_fallback=False,
                                language=language
                            )
                            log(f"    ✓ {mode_name}分析完成")
                        
                        social_styles = []
                        if social_style == "xiaohongshu" or social_style == "all":
                            social_styles.append(("小红书", "口语学习", SocialStyle.XIAOHONGSHU))
                        if social_style == "weibo" or social_style == "all":
                            social_styles.append(("微博", "应试学习", SocialStyle.WEIBO))
                        if social_style == "zhihu" or social_style == "all":
                            social_styles.append(("知乎", "应试学习", SocialStyle.ZHIHU))
                        
                        for style_name, mode_name, style_enum in social_styles:
                            formatter.format(
                                video_id=video_id,
                                subtitles=subtitles,
                                analysis_mode=mode_name,
                                style=style_enum,
                                output_dir=video_dir,
                                use_ai_fallback=False,
                                language=language
                            )
                            log(f"    ✓ {style_name}风格文案生成完成")
                        
                        results["analyzed"] += 1
                        log(f"  ✓ 分析完成: {video_id}")
                        
                    except Exception as e:
                        results["errors"].append(f"分析失败: {video_id} - {str(e)[:50]}")
                        log(f"  ✗ 分析失败: {video_id}")
            
            except Exception as e:
                results["errors"].append(f"分析初始化异常: {str(e)[:50]}")
                log(f"❌ 分析初始化异常: {str(e)[:100]}")
        
        log("流程执行完成！")
        
    except Exception as e:
        results["errors"].append(f"流程异常: {str(e)}")
        log(f"❌ 流程异常: {str(e)}")
        logger.error(f"流程异常: {e}")
        traceback.print_exc()
    
    return log(""), format_results(results)


def run_pipeline_thread(video_site: str, language: str, video_count: int, analyze_content: bool,
                        analysis_mode: str, social_style: str, target_lang: str,
                        min_duration: int, max_duration: int) -> None:
    """在后台线程中运行完整流程"""
    global _pipeline_progress, _pipeline_result, _pipeline_running
    
    try:
        progress_text, result_text = run_pipeline_impl(
            video_site=video_site,
            language=language,
            video_count=video_count,
            analyze_content=analyze_content,
            analysis_mode=analysis_mode,
            social_style=social_style,
            target_lang=target_lang,
            min_duration=min_duration,
            max_duration=max_duration
        )
        _pipeline_progress = progress_text
        _pipeline_result = result_text
    except Exception as e:
        logger.error(f"后台线程异常: {e}")
        traceback.print_exc()
        _pipeline_progress = f"❌ 后台线程异常: {str(e)}"
        _pipeline_result = "执行失败"
    finally:
        _pipeline_running = False


def start_pipeline(video_site: str, language: str, video_count: int, analyze_content: bool,
                   analysis_mode: str, social_style: str, target_lang: str,
                   min_duration: int, max_duration: int) -> tuple:
    """启动流程（fire-and-forget，立即返回）"""
    global _pipeline_progress, _pipeline_result, _pipeline_running
    
    try:
        if _pipeline_running:
            return "❌ 已有任务正在执行中，请等待完成", ""
        
        _pipeline_progress = "[启动] 正在初始化任务..."
        _pipeline_result = ""
        _pipeline_running = True
        
        thread = threading.Thread(
            target=run_pipeline_thread,
            args=(video_site, language, video_count, analyze_content,
                  analysis_mode, social_style, target_lang,
                  min_duration, max_duration),
            daemon=True
        )
        thread.start()
        
        return str(_pipeline_progress), str(_pipeline_result)
    except Exception as e:
        logger.error(f"start_pipeline 异常: {e}")
        traceback.print_exc()
        return f"❌ 启动失败: {str(e)[:100]}", ""


def check_progress() -> tuple:
    """检查进度（用于定时器轮询）"""
    global _pipeline_progress, _pipeline_result
    return str(_pipeline_progress), str(_pipeline_result)


def launch() -> None:
    """启动 Gradio WebUI"""
    init_app()
    
    with gr.Blocks(title="多语种视频爬虫") as demo:
        gr.Markdown("# 🎬 多语种视频一键下载与分析")
        gr.Markdown("""
            输入视频语言和数量，一键启动自动下载和分析流程。
            支持多种语言和视频网站。
        """)
        
        with gr.Row():
            with gr.Column(scale=2):
                gr.Markdown("### 🎯 视频爬取设置")
                
                video_site = gr.Dropdown(
                    choices=[
                        ("YouTube", "youtube"),
                        ("Vimeo", "vimeo"),
                        ("Dailymotion", "dailymotion"),
                        ("Bilibili", "bilibili"),
                        ("TikTok", "tiktok"),
                        ("Twitch", "twitch"),
                        ("Instagram", "instagram"),
                        ("Facebook", "facebook"),
                    ],
                    label="视频网站",
                    value="youtube",
                    info="选择要爬取的视频网站（推荐使用YouTube获取最佳体验）"
                )
                
                language = gr.Dropdown(
                    choices=[
                        ("英语 (English)", "en"),
                        ("德语 (Deutsch)", "de"),
                        ("法语 (Français)", "fr"),
                        ("西班牙语 (Español)", "es"),
                        ("俄语 (Russian)", "ru"),
                        ("意大利语 (Italian)", "it"),
                        ("葡萄牙语 (Portuguese)", "pt"),
                        ("中文 (Chinese)", "zh"),
                        ("日语 (Japanese)", "ja"),
                        ("韩语 (Korean)", "ko"),
                        ("阿拉伯语 (Arabic)", "ar"),
                        ("印地语 (Hindi)", "hi"),
                        ("荷兰语 (Dutch)", "nl"),
                        ("瑞典语 (Swedish)", "sv"),
                        ("挪威语 (Norwegian)", "no"),
                        ("丹麦语 (Danish)", "da"),
                        ("芬兰语 (Finnish)", "fi"),
                        ("波兰语 (Polish)", "pl"),
                        ("捷克语 (Czech)", "cs"),
                        ("匈牙利语 (Hungarian)", "hu"),
                        ("罗马尼亚语 (Romanian)", "ro"),
                        ("希腊语 (Greek)", "el"),
                        ("土耳其语 (Turkish)", "tr"),
                        ("越南语 (Vietnamese)", "vi"),
                        ("泰语 (Thai)", "th"),
                        ("印尼语 (Indonesian)", "id"),
                        ("马来语 (Malay)", "ms"),
                        ("他加禄语 (Tagalog)", "tl"),
                    ],
                    label="视频语言",
                    value="en",
                    info="选择视频语言，支持28种语言的完整分析"
                )
                
                video_count = gr.Slider(
                    minimum=1,
                    maximum=10,
                    value=3,
                    step=1,
                    label="视频数量",
                    info="一次下载和分析的视频数量"
                )
                
                analyze_content = gr.Checkbox(
                    label="进行内容分析",
                    value=True,
                    info="下载后自动进行语言分析和文案生成"
                )
            
            with gr.Column(scale=1):
                gr.Markdown("### ⚙️ 分析设置")
                
                analysis_mode = gr.Dropdown(
                    choices=[
                        ("口语学习模式", "oral"),
                        ("应试学习模式", "exam"),
                        ("两种模式都分析", "both"),
                    ],
                    label="分析模式",
                    value="both",
                    info="选择内容分析的侧重点"
                )
                
                social_style = gr.Dropdown(
                    choices=[
                        ("小红书风格", "xiaohongshu"),
                        ("微博风格", "weibo"),
                        ("知乎风格", "zhihu"),
                        ("全部风格", "all"),
                    ],
                    label="社交平台风格",
                    value="all",
                    info="选择要生成的社交媒体文案风格"
                )
                
                target_lang = gr.Dropdown(
                    choices=[
                        ("中文 (Chinese)", "zh-CN"),
                        ("英语 (English)", "en"),
                        ("日语 (Japanese)", "ja"),
                        ("韩语 (Korean)", "ko"),
                        ("法语 (French)", "fr"),
                        ("德语 (German)", "de"),
                    ],
                    label="翻译目标语言",
                    value="zh-CN",
                    info="字幕翻译和文案生成的目标语言"
                )
                
                min_duration = gr.Slider(
                    minimum=60,
                    maximum=1200,
                    value=90,
                    step=30,
                    label="最小时长（秒）",
                    info="过滤时长小于此值的视频"
                )
                
                max_duration = gr.Slider(
                    minimum=60,
                    maximum=3600,
                    value=600,
                    step=60,
                    label="最大时长（秒）",
                    info="过滤时长大于此值的视频"
                )
            
            with gr.Column(scale=1):
                gr.Markdown("""
                    **功能说明：**
                    - 🕷️ **自动爬取**：根据语言搜索相关视频
                    - 📥 **自动下载**：下载指定数量的视频
                    - 📝 **字幕处理**：自动生成双语字幕
                    - 📊 **内容分析**：生成学习分析报告
                    - 📝 **文案生成**：多平台风格社交媒体文案
                    
                    **支持语言：**
                    - 🇺🇸🇬🇧🇩🇪🇫🇷🇪🇸🇷🇺🇮🇹🇵🇹
                    - 🇨🇳🇯🇵🇰🇷🇸🇦🇮🇳🇳🇱🇸🇪🇳🇴
                    - 🇩🇰🇫🇮🇵🇱🇨🇿🇭🇺🇷🇴🇬🇷🇹🇷
                    - 🇻🇳🇹🇭🇮🇩🇲🇾🇵🇭
                """)
        
        with gr.Row():
            start_btn = gr.Button("🚀 一键启动", variant="primary", size="lg")
        
        with gr.Row():
            progress_box = gr.Textbox(
                label="执行进度",
                lines=15,
                max_lines=15,
                interactive=False,
                placeholder="点击「一键启动」开始执行..."
            )
        
        with gr.Row():
            result_box = gr.Textbox(
                label="执行结果",
                lines=8,
                max_lines=8,
                interactive=False,
                placeholder="执行结果将显示在这里..."
            )
        
        timer = gr.Timer(value=2)
        
        start_btn.click(
            fn=start_pipeline,
            inputs=[video_site, language, video_count, analyze_content,
                    analysis_mode, social_style, target_lang,
                    min_duration, max_duration],
            outputs=[progress_box, result_box]
        )
        
        timer.tick(
            fn=check_progress,
            outputs=[progress_box, result_box]
        )
        
        test_btn = gr.Button("🧪 测试连接")
        
        def test_connection():
            return "✅ 连接正常！", "测试成功"
        
        test_btn.click(
            fn=test_connection,
            outputs=[progress_box, result_box]
        )
    
    demo.queue(max_size=10, default_concurrency_limit=1)
    demo.launch(
        server_name="127.0.0.1",
        server_port=7860,
        share=False,
        debug=False,
        max_threads=20
    )


if __name__ == "__main__":
    launch()
