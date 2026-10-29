"""
YouTube 视频爬虫

支持搜索、频道视频获取，集成语言过滤功能。
"""

import re
import json
import random
import time
from typing import Optional, Dict, List, Any

from core.spiders.base_spider import VideoSpider
from utils.enums import LanguageType
from utils.language_check import detect_video_language
from utils.youtube_url import build_watch_url  # AUDIT-0051
from utils.ytdlp_common import YTDLP_YOUTUBE_HEADERS


class YoutubeSpider(VideoSpider):
    """
    YouTube 视频爬虫
    
    功能：
        - 搜索视频
        - 获取单个视频详情
        - 获取频道视频列表
        - 语言过滤
        - 时长过滤
        - 题材分类（自动填充 category 字段）
    """

    def _enrich_categories(self, videos: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """在返回视频列表前，对每个视频调用分类器填充 category 字段

        这是修复「所有视频都被分到 daily」的核心步骤：
        此前 spider 返回的 video dict 没有 category 字段，
        pipeline.py 用 video.get('category', 'daily') 兜底，
        导致 100% 视频都落到 daily 目录。

        现在：调用 classify.classify_video(title, description) 生成
        真实分类（education/science/technology/entertainment/news/daily 其一）
        后填入 category 字段，下游按真实分类归档。

        Args:
            videos: 各 search_* 方法产生的视频字典列表

        Returns:
            相同列表，但每个元素都保证含有 category 字段（字符串）
        """
        if not videos:
            return videos

        # 延迟导入：避免在 import spider 阶段就初始化 classifier
        # （classifier 要加载 config，冷启动成本不低）
        try:
            from core.classify import classify_video
        except Exception as e:
            self._logger.warning(f"导入分类模块失败，全部使用默认 daily: {e}")
            for v in videos:
                v.setdefault("category", "daily")
            return videos

        n_ok = 0
        for v in videos:
            title = v.get("title", "") or ""
            description = v.get("description", "") or None
            try:
                cat_enum = classify_video(title, description)
                # .value 取枚举字符串（pipeline/db 存的是字符串）
                v["category"] = str(cat_enum.value)
                n_ok += 1
            except Exception as e:
                # 单个分类失败不阻塞，使用 daily 兜底
                v.setdefault("category", "daily")
                self._logger.debug(
                    f"分类失败，兜底daily: {title[:30]}... -> {type(e).__name__}: {e}"
                )

        self._logger.info(
            f"视频分类完成: 共 {len(videos)} 个，成功 {n_ok} 个，"
            f"兜底 {len(videos) - n_ok} 个"
        )
        return videos

    # =====================================================
    # yt-dlp 预探过滤（剔除已下架/私有/地区锁的死链）
    # =====================================================
    _probe_cache: Dict[str, bool] = {}
    _probe_cache_lock = __import__("threading").Lock()
    # AUDIT-0048: 预探缓存上限，超过即淘汰最早写入的一半，防止长期运行无界增长
    _probe_cache_max = 1024

    @classmethod
    def _probe_cache_store(cls, url: str, ok: bool) -> None:
        """写入预探缓存（持锁）；超过上限时按插入序淘汰最早的一半"""
        with cls._probe_cache_lock:
            cls._probe_cache[url] = ok
            if len(cls._probe_cache) > cls._probe_cache_max:
                for k in list(cls._probe_cache.keys())[: len(cls._probe_cache) // 2]:
                    cls._probe_cache.pop(k, None)

    @classmethod
    def probe_url(cls, url: str, timeout: int = 15) -> bool:
        """单 URL 可达性预探。True=视频可用，False=死链

        使用 yt-dlp 的 extract_info(download=False) 轻量探测，
        不走完整下载流程，仅拿元数据，速度极快。

        不强制要求浏览器登录态（因为大多数 YouTube 视频无需登录）。
        """
        with cls._probe_cache_lock:
            if url in cls._probe_cache:
                return cls._probe_cache[url]

        try:
            import yt_dlp
        except ImportError:
            cls._probe_cache_store(url, True)
            return True

        ydl_opts = {
            "quiet": True,
            "skip_download": True,
            "no_warnings": True,
            "geo_bypass": True,
            "geo_bypass_country": "US",
            "http_headers": {
                **YTDLP_YOUTUBE_HEADERS,
            },
        }
        # cookies_from_browser: 复用 VideoDownloader 的智能探测
        try:
            from core.download import VideoDownloader
            _browser = VideoDownloader._detect_browser_cookie()
            if _browser:
                ydl_opts["cookies_from_browser"] = _browser
        except Exception:
            pass
        # JS runtime (Node.js) — yt-dlp 2026+ 强依赖
        from utils.path_helper import get_node_path
        _node_path = get_node_path()
        _node_exe = str(_node_path) if _node_path.exists() else None
        if _node_exe:
            ydl_opts["js_runtimes"] = {"node": {"path": _node_exe}}
            ydl_opts["remote_components"] = ["ejs:github"]
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)
                ok = info is not None and info.get("id") is not None
        except Exception:
            ok = False

        cls._probe_cache_store(url, ok)
        return ok

    def filter_dead_urls(
        self,
        videos: List[Dict[str, Any]],
        max_probe: int = 15,
        use_db_cache: bool = True,
        enabled: bool = False,
    ) -> List[Dict[str, Any]]:
        """对候选视频做 yt-dlp 可达性预探，剔除死链。

        Args:
            videos: 爬虫返回的原始视频列表
            max_probe: 最多探测多少个（避免全量探测太慢；超过就抽样）
            use_db_cache: True = 对 DB 中已标记 check_status 的 URL 直接跳过探测
            enabled: **默认 False** — 预探默认关闭，避免连续高频 extract_info
                     被 YouTube 判定为 bot。单个下载不会触发检测（是孤立请求），
                     但预探一次发 15 个 metadata fetch 就会触发。
                     设为 True 时必须确保：① 浏览器已登录 YouTube ② 有代理/IP 池 ③ 探测间隔足够长

        Returns:
            通过预探的视频列表（原地可能被修改）
        """
        if not videos:
            return videos

        if not enabled:
            self._logger.info(
                f"预探过滤: 已跳过（enabled=False，避免触发 YouTube bot 检测）"
            )
            return videos

        try:
            from utils.db_manager import is_video_broken, mark_video_broken, mark_video_check_ok
        except Exception:
            is_video_broken = None
            mark_video_broken = None
            mark_video_check_ok = None

        total = len(videos)
        self._logger.info(f"预探过滤：输入 {total} 个候选，最多探测 {max_probe} 个")

        passed: List[Dict[str, Any]] = []
        dead_count = 0
        db_skipped = 0

        for i, v in enumerate(videos):
            url = v.get("source_url", "")
            if not url:
                dead_count += 1
                continue

            # DB 缓存：已标记 broken 的直接跳过
            if use_db_cache and is_video_broken and is_video_broken(url):
                db_skipped += 1
                dead_count += 1
                continue

            # 抽样：超过 max_probe 的候选直接保留（假设它们也可用）
            # 这样可以避免 100 个候选逐个探测花好几分钟
            if i >= max_probe:
                passed.append(v)
                continue

            # 探测间随机延迟（1~3.5s），避免 YouTube bot 检测
            if i > 0:
                time.sleep(random.uniform(1.0, 3.5))

            ok = self.probe_url(url)
            if ok:
                passed.append(v)
                if mark_video_check_ok:
                    try:
                        from utils.db_manager import get_video_by_url
                        rec = get_video_by_url(url)
                        if rec and rec.get("id"):
                            mark_video_check_ok(rec["id"])
                    except Exception:
                        pass
            else:
                dead_count += 1
                if mark_video_broken:
                    try:
                        from utils.db_manager import get_video_by_url
                        rec = get_video_by_url(url)
                        if rec and rec.get("id"):
                            mark_video_broken(rec["id"], "yt-dlp pre-probe failed")
                    except Exception:
                        pass
                self._logger.debug(
                    f"预探淘汰: {v.get('title', '')[:40]} ({url.split('?v=')[-1][:11]})"
                )

        self._logger.info(
            f"预探过滤完成：通过 {len(passed)}/{total}，淘汰 dead={dead_count}（其中DB命中={db_skipped}）"
        )
        return passed
    
    # 不同语言对应的搜索关键词映射（大幅扩展，增加多样性）
    LANGUAGE_KEYWORDS = {
        "en": [
            "learn English", "English language", "English conversation", "English culture",
            "English tutorial", "English grammar", "English pronunciation", "English vocabulary",
            "British English", "American English", "English speaking practice", "English listening",
            "English for beginners", "English idioms", "English storytelling", "English news",
            "English documentary", "English podcast", "daily English", "English slang",
            "English accent training", "English phrasal verbs", "English movies explained",
        ],
        "de": [
            "Deutsch lernen", "Deutsche Sprache", "auf Deutsch", "Deutsche Kultur",
            "Deutsch für Anfänger", "deutsche Grammatik", "Deutsch Konversation",
            "deutsche Geschichte", "Deutsch Alltag", "deutsche Doku", "Deutsch Podcast",
            "Deutsche Literatur", "Deutsch Sprechen", "deutsche Nachrichten", "Deutsch Unterricht",
            "Berliner Dialekt", "bayrisch lernen", "Deutsch Aussprache", "deutsche Redewendungen",
            "Deutsch Vokabeln", "deutsches Kino", "Deutsch Musik", "Deutsch Reise",
            "Mia isst", "deutsche Kochshow", "Deutsch Comedy", "Deutsch Vlog",
        ],
        "fr": [
            "apprendre le français", "en français", "culture française", "français pour débutants",
            "grammaire française", "conversation française", "français quotidien", "documentaire français",
            "podcast français", "littérature française", "français parlé", "actualités françaises",
            "cours de français", "prononciation française", "expressions françaises", "vocabulaire français",
            "cinéma français", "musique française", "cuisine française", "voyage en France",
        ],
        "es": [
            "aprender español", "en español", "cultura española", "español para principiantes",
            "gramática española", "conversación en español", "español diario", "documental español",
            "podcast español", "literatura española", "español hablado", "noticias en español",
            "curso de español", "pronunciación española", "expresiones españolas", "vocabulario español",
            "cine español", "música española", "cocina española", "viaje por España",
        ],
        "it": [
            "impara l'italiano", "in italiano", "cultura italiana", "italiano per principianti",
            "grammatica italiana", "conversazione italiana", "italiano quotidiano", "documentario italiano",
            "podcast italiano", "letteratura italiana", "italiano parlato", "notizie italiane",
            "corso di italiano", "pronuncia italiana", "espressioni italiane", "cinema italiano",
            "musica italiana", "cucina italiana", "viaggio in Italia",
        ],
        "pt": [
            "aprender português", "em português", "cultura portuguesa", "português para iniciantes",
            "gramática portuguesa", "conversação em português", "português do Brasil", "documentário português",
            "podcast português", "literatura portuguesa", "português falado", "notícias em português",
            "curso de português", "pronúncia portuguesa", "expressões portuguesas", "cinema português",
            "música portuguesa", "culinária portuguesa", "viagem a Portugal",
        ],
        "ru": [
            "русский язык", "на русском", "русская культура", "русский для начинающих",
            "русская грамматика", "разговорный русский", "русский повседневный", "документальный фильм",
            "русский подкаст", "русская литература", "новости на русском", "курс русского языка",
            "русскоe кино", "русская музыка", "русская кухня", "путешествие по России",
        ],
        "ja": [
            "日本語を勉強", "日本語で", "日本文化", "日本語初心者",
            "日本語文法", "日本語会話", "日常日本語", "日本語ドキュメンタリー",
            "日本語ポッドキャスト", "日本文学", "日本語ニュース", "日本語の授業",
            "日本の映画", "日本の音楽", "日本料理", "日本旅行",
        ],
        "ko": [
            "한국어 배우기", "한국어로", "한국 문화", "한국어 초보자",
            "한국어 문법", "한국어 회화", "일상 한국어", "한국어 다큐멘터리",
            "한국어 팟캐스트", "한국 문학", "한국어 뉴스", "한국 영화",
            "한국 음악", "한국 요리", "한국 여행",
        ],
        "ar": [
            "تعلم العربية", "بالعربية", "الثقافة العربية", "العربية للمبتدئين",
            "القواعد العربية", "محادثة عربية", "العربية اليومية", "وثائقي عربي",
            "بودكاست عربي", "الأدب العربي", "أخبار بالعربية", "السينما العربية",
            "الموسيقى العربية", "المطبخ العربي", "السفر في العالم العربي",
        ],
        "zh": [
            "学中文", "中文", "中国文化", "中文初学者",
            "中文语法", "中文对话", "日常中文", "中文纪录片",
            "中文播客", "中国文学", "中文新闻", "中文电影",
            "中国音乐", "中国美食", "中国旅行",
        ],
    }
    
    # YouTube 搜索排序参数（增加结果多样性）
    SEARCH_SORT_PARAMS = [
        "",  # 默认（相关性）
        "&sp=CAI%253D",  # 按上传时间排序
        "&sp=CAMSAhAB",  # 按播放量排序
        "&sp=CAE%253D",  # 按评分排序
    ]
    
    # 各语言对应的地区代码（gl 参数）和界面语言代码（hl 参数）
    # YouTube 通过这两个参数按地区和界面语言过滤内容
    LANGUAGE_REGION = {
        "en": ("US", "en"),
        "de": ("DE", "de"),
        "fr": ("FR", "fr"),
        "es": ("ES", "es"),
        "it": ("IT", "it"),
        "pt": ("BR", "pt"),
        "ru": ("RU", "ru"),
        "ja": ("JP", "ja"),
        "ko": ("KR", "ko"),
        "ar": ("EG", "ar"),
        "zh": ("CN", "zh"),
    }
    
    # 语言中性极简查询字符（用于无偏好搜索）
    # 这些是各语言中最常见的单字符/短词，不引入任何主题偏好
    # 配合 gl/hl 地区参数，YouTube 会自动返回该地区的热门内容
    NEUTRAL_QUERIES = ["a", "e", "i", "o", "u", "1", "2", "3"]

    # 音乐/歌曲类视频标记词黑名单（多语言，不区分大小写）
    # 用于过滤掉 ASR 难以识别的音乐类视频（歌词节奏快、有伴奏、非日常用语、纯器乐无对白）
    # 匹配标题或频道名中包含这些词的视频将被过滤
    MUSIC_KEYWORDS = [
        # 通用音乐标记词
        "feat.", "ft.", "featuring", "official video", "official audio",
        "music video", "lyrics", "lyric video", "official mv",
        "album", "single", "audio only", "full album",
        # 音乐可视化 / 音频可视化（典型音乐发布形式，如 bjw_PUWq9zE "una noche (visualizer)"）
        "visualizer", "visualiser", "audio visualizer", "visual video",
        # 纯器乐 / 伴奏类
        "instrumental", "karaoke", "karaokê", "karaoke version",
        "acapella", "a cappella", "remix", "cover song", "dj mix",
        "loop", "1 hour", "10 hour", "1hour", "10hour",
        # 法语音乐标记词（含单复数）
        "clip officiel", "chanson", "chansons", "musique", "album complet",
        # 德语音乐标记词（含单复数）
        "offizielles video", "offizielles musikvideo", "lied", "lieder", "musik",
        # 西班牙语音乐标记词（含单复数和带/不带重音形式）
        "video oficial", "canción", "canciónes", "cancion", "canciones",
        "música", "musica", "álbum", "album",
        # 意大利语音乐标记词
        "video ufficiale", "canzone", "canzoni", "musica",
        # 葡萄牙语音乐标记词
        "vídeo oficial", "video oficial", "canção", "canções", "musica", "álbum",

        # === 古典音乐作曲家名（高置信度：标题含作曲家名几乎必为古典音乐演奏） ===
        "beethoven", "mozart", "bach", "chopin", "liszt", "schubert",
        "schumann", "brahms", "tchaikovsky", "vivaldi", "handel", "haydn",
        "debussy", "ravel", "rachmaninov", "rachmaninoff", "mendelssohn",
        "grieg", "dvorak", "mahler", "stravinsky", "prokofiev", "satie",
        "scarlatti", "monteverdi", "rossini", "verdi", "puccini", "wagner",
        # 著名古典作品名（常作为标题主体出现）
        "für elise", "fur elise", "moonlight sonata", "symphony no.",
        "sonata no.", "concerto no.", "nocturne", "prélude", "prelude",
        "étude", "etude", "fantaisie", "fantasy", "impromptu",
        "the four seasons", "le cygne", "the swan",

        # === 器乐/演奏教学类（ASR 不可识别：以乐器演示为主，无对白） ===
        # 钢琴/吉他/小提琴等乐器名 + 演奏/教学语境
        "piano tutorial", "piano cover", "piano lesson", "piano sheet",
        "easy piano", "piano for beginners", "how to play piano",
        "guitar tutorial", "guitar cover", "guitar lesson", "how to play guitar",
        "violin tutorial", "violin cover", "violin lesson",
        "drum cover", "drum tutorial", "drum lesson",
        # 伴奏练习类（无对白，纯器乐伴奏）
        "play along", "play-along", "backing track",
        # 乐器独奏标记（标题主体即为乐器名时）
        "piano solo", "violin solo", "cello solo", "guitar solo",
        "solo piano", "solo violin",
        # 乐器名 + 演奏曲名（高置信度组合）
        "piano -", "violin -", "cello -", "guitar -",
        # 标题中包含 [Piano]/[Violin] 这类方括号乐器标注
        "[piano]", "[violin]", "[guitar]", "[cello]", "[drums]", "[ukulele]",
        # 钢琴/键盘/弦乐单独出现且无对白信号（标题主体即为乐器名时）
        # 注意：单独 "piano" 不加入，避免误伤 "piano mover" 等非音乐语境
        "[keyboard]", "sheet music", "music sheet", "tab sheet",

        # === 音乐演奏会/现场类（无字幕对白） ===
        "recital", "live concert", "classical music", "orchestra",
        "philharmonic", "symphony orchestra", "string quartet",
    ]

    # 音乐类频道名标识（用于识别 YouTube 自动生成的音乐频道和 VEVO 频道）
    MUSIC_CHANNEL_MARKERS = ["vevo", "- topic", "topic -"]

    # ASR 不友好标题关键词黑名单（除音乐外的其他 ASR 识别困难场景）
    # 匹配到则结合 categoryId 判断是否过滤
    ASR_HOSTILE_TITLE_KEYWORDS = [
        # 游戏类（大量BGM+音效，对白极少）
        "gameplay", "walkthrough", "let's play", "lets play", "playthrough",
        "speedrun", "speed run", "gaming", "esports", "twitch",
        # 影视类（剧本台词/配音，非真实日常口语）
        "official trailer", "trailer oficial", "teaser", "movie clip",
        "film clip", "movie scene", "full movie", "full episode",
        "opening scene", "ending scene", "best scenes",
        # 纯音效/ASMR类（无对白）
        "asmr", "white noise", "rain sounds", "nature sounds",
        "relaxing music", "sleep music", "study music", "ambient",
    ]

    def __init__(self, **kwargs) -> None:
        """初始化 YouTube 爬虫"""
        super().__init__(**kwargs)
        self._logger.info("YouTube 爬虫初始化完成")

    def _is_music_video(self, title: str, channel_name: str) -> bool:
        """检测视频是否为音乐/歌曲类

        通过检查标题和频道名中的音乐标记词，
        判断视频是否为音乐类内容（ASR 识别率低、翻译质量差）。

        音乐关键词同时检查标题和频道名，因为有些视频标题不含音乐标记，
        但频道名明确表明是音乐频道（如 "Comptines et chansons"）。

        Args:
            title: 视频标题
            channel_name: 频道名

        Returns:
            True 表示是音乐类视频（应过滤），False 表示非音乐类
        """
        if not title and not channel_name:
            return False

        # 统一转为小写进行匹配
        title_lower = (title or "").lower()
        channel_lower = (channel_name or "").lower()

        # 检查标题和频道名中的音乐标记词
        # 同时检查两个字段，因为音乐信号可能出现在任意一处
        combined_text = title_lower + " " + channel_lower
        for keyword in self.MUSIC_KEYWORDS:
            if keyword in combined_text:
                return True

        # 检查频道名中的音乐频道标识
        # VEVO 频道：如 "BigSeanVEVO"
        # Topic 频道：如 "Koffi Olomide - Topic"（YouTube 自动生成的音乐频道）
        for marker in self.MUSIC_CHANNEL_MARKERS:
            if marker in channel_lower:
                return True

        return False

    def _is_asr_hostile_video(
        self,
        title: str,
        channel_name: str,
        category_id: Optional[str] = None
    ) -> bool:
        """综合判断视频是否为 ASR 不友好内容（在入库/下载前过滤）

        多层级联合判断策略（置信度从高到低）：
            层级 1 [最高优先级]：YouTube categoryId 命中 HOSTILE 列表
                → 直接过滤（Music=10, Gaming=20, Movies系列等）
            层级 2：标题关键词命中 MUSIC_KEYWORDS 或 音乐频道标识
                → 直接过滤（_is_music_video 的关键词覆盖极广）
            层级 3：categoryId 命中 SUSPICIOUS 列表（Entertainment=24 / Film&Animation=1）
                且 标题命中 ASR_HOSTILE_TITLE_KEYWORDS
                → 二次匹配后过滤（避免误杀教育类 Vlog）
            其他情况：放行

        设计原则：宁可误杀少量也不把音乐/游戏类放进 ASR 流程，
        因为它们会生成空白字幕（如 bjw_PUWq9zE 案例），
        且会浪费大量翻译/分析算力。

        Args:
            title: 视频标题
            channel_name: 频道名
            category_id: YouTube categoryId（字符串，如 "10"=Music）；
                         为空或 API 不可用时，降级为仅关键词判断

        Returns:
            True 表示 ASR 不友好（应过滤），False 表示通过
        """
        # === 层级 1：categoryId 在 HOSTILE 集合 → 直接过滤 ===
        if category_id:
            try:
                from core.spiders.youtube_api_client import (
                    YOUTUBE_CATEGORY_ASR_HOSTILE,
                    YOUTUBE_CATEGORY_ASR_SUSPICIOUS,
                )
                cat_str = str(category_id)
                if cat_str in YOUTUBE_CATEGORY_ASR_HOSTILE:
                    self._logger.debug(
                        f"categoryId过滤（HOSTILE={cat_str}）: {title[:40]}"
                    )
                    return True
            except ImportError:
                # 导入失败，跳过categoryId判断（降级为仅关键词）
                pass

        # === 层级 2：标题/频道名命中音乐关键词 → 直接过滤 ===
        # 复用已验证的 _is_music_video（覆盖 visualizer/feat./lyrics/VEVO 等）
        if self._is_music_video(title, channel_name):
            return True

        # === 层级 3：categoryId 存疑 + 标题命中额外关键词 → 过滤 ===
        if category_id:
            try:
                from core.spiders.youtube_api_client import (
                    YOUTUBE_CATEGORY_ASR_SUSPICIOUS,
                )
                cat_str = str(category_id)
                if cat_str in YOUTUBE_CATEGORY_ASR_SUSPICIOUS:
                    # 二次判断：同时命中 ASR_HOSTILE_TITLE_KEYWORDS 才过滤
                    title_lower = (title or "").lower()
                    for kw in self.ASR_HOSTILE_TITLE_KEYWORDS:
                        if kw in title_lower:
                            self._logger.debug(
                                f"categoryId存疑+关键词过滤（SUSPICIOUS={cat_str}, kw={kw}）: {title[:40]}"
                            )
                            return True
            except ImportError:
                pass

        # === 附加兜底：无 categoryId 时，标题命中强信号也过滤 ===
        # （用户使用非 API 路径时，categoryId 为空，必须靠关键词）
        title_lower = (title or "").lower()
        for kw in self.ASR_HOSTILE_TITLE_KEYWORDS[:10]:  # 只取游戏+ASMR类强信号，前10条
            if kw in title_lower:
                self._logger.debug(
                    f"无categoryId时标题强信号过滤（kw={kw}）: {title[:40]}"
                )
                return True

        return False
    
    def search_trending(
        self,
        filter_languages: Optional[List[LanguageType]] = None,
        min_duration: int = 90,
        max_duration: int = 300,
        **kwargs
    ) -> List[Dict[str, Any]]:
        """
        通过 YouTube 热门页面抓取视频（无关键词偏好）
        
        利用 YouTube 的地区热门页（/feed/trending）和地区参数（gl/hl）
        按目标语言地区抓取当前热门视频，不依赖任何主题关键词。
        
        Args:
            filter_languages: 语言白名单（用于确定地区）
            min_duration: 最小时长（秒）
            max_duration: 最大时长（秒）
            **kwargs: 其他参数
        
        Returns:
            视频信息列表
        """
        language_code = "en"
        if filter_languages and len(filter_languages) > 0:
            language_code = filter_languages[0].value
        
        gl, hl = self.LANGUAGE_REGION.get(language_code, ("US", "en"))
        self._logger.info(f"无关键词抓取模式：地区={gl}, 语言={hl}")
        
        all_videos: List[Dict[str, Any]] = []
        seen_urls: set = set()
        
        # 1. 抓取 YouTube 热门页（Trending）
        trending_url = f"https://www.youtube.com/feed/trending?gl={gl}&hl={hl}"
        self._logger.info(f"抓取热门页: {trending_url}")
        try:
            html = self._engine.get(trending_url)
            if html:
                videos = self.parse(html, trending_url)
                for v in videos:
                    url = v.get("source_url", "")
                    if url and url not in seen_urls:
                        seen_urls.add(url)
                        all_videos.append(v)
                self._logger.info(f"热门页获取 {len(videos)} 个视频（累计 {len(all_videos)} 个）")
        except Exception as e:
            self._logger.warning(f"抓取热门页失败: {e}")
        
        # 2. 抓取 YouTube 音乐热门页（Trending Music）
        trending_music_url = f"https://www.youtube.com/feed/trending?bp=4gINGgt5dG1hX2NoYXJ0cw&gl={gl}&hl={hl}"
        self._logger.info(f"抓取音乐热门页: {trending_music_url}")
        try:
            html = self._engine.get(trending_music_url)
            if html:
                videos = self.parse(html, trending_music_url)
                for v in videos:
                    url = v.get("source_url", "")
                    if url and url not in seen_urls:
                        seen_urls.add(url)
                        all_videos.append(v)
                self._logger.info(f"音乐热门页获取 {len(videos)} 个视频（累计 {len(all_videos)} 个）")
        except Exception as e:
            self._logger.warning(f"抓取音乐热门页失败: {e}")
        
        # 3. 使用语言中性极简查询补充（不引入主题偏好）
        #    配合 gl/hl 地区参数，YouTube 会返回该地区的热门/相关内容
        neutral_queries = self.NEUTRAL_QUERIES[:]
        random.shuffle(neutral_queries)
        
        def neutral_pagination(base_url: str, page: int) -> str:
            if page == 1:
                return base_url
            return f"{base_url}&page={page}"
        
        for nq in neutral_queries[:5]:  # 最多用5个中性查询
            if len(all_videos) >= 60:  # 够多了就停
                break
            
            sort_param = random.choice(self.SEARCH_SORT_PARAMS)
            nq_url = self._build_search_url(nq, language=language_code) + sort_param
            self._logger.info(f"中性查询搜索: '{nq}' (排序: {sort_param or '默认'})")
            
            try:
                videos = self.crawl_with_pagination(
                    base_url=nq_url,
                    max_pages=3,
                    pagination_strategy=neutral_pagination,
                    filter_languages=filter_languages
                )
                for v in videos:
                    url = v.get("source_url", "")
                    if url and url not in seen_urls:
                        seen_urls.add(url)
                        all_videos.append(v)
            except Exception as e:
                self._logger.warning(f"中性查询 '{nq}' 搜索失败: {e}")
        
        self._logger.info(f"无关键词抓取完成，共获取 {len(all_videos)} 个视频")

        # 时长过滤
        duration_filtered = self._filter_by_duration(all_videos, min_duration, max_duration)

        # ASR 不友好过滤（无 categoryId，仅关键词兜底）
        # search_trending 走热门页面抓取，不走 API，无 categoryId，
        # 降级为仅通过 _is_asr_hostile_video 的关键词匹配
        asr_filtered_trending: List[Dict[str, Any]] = []
        trending_hostile = 0
        for v in duration_filtered:
            title = v.get("title", "")
            author = v.get("author", "")
            if self._is_asr_hostile_video(title, author, category_id=None):
                trending_hostile += 1
                self._logger.debug(
                    f"search_trending ASR过滤淘汰: {title[:40]} (频道: {author})"
                )
            else:
                asr_filtered_trending.append(v)

        self._logger.info(
            f"search_trending ASR过滤: 时长过滤后 {len(duration_filtered)} 个, "
            f"通过 {len(asr_filtered_trending)} 个 (淘汰 {trending_hostile} 个)"
        )
        # 自动分类填充 category 字段 → yt-dlp 预探过滤
        categorized = self._enrich_categories(asr_filtered_trending)
        # 语言硬过滤：hl=de&gl=DE 不保证视频实际是德语，标题/描述再验一次
        categorized = self._filter_videos_by_language(
            categorized, filter_languages, source="search_trending"
        )
        return self.filter_dead_urls(categorized)

    def search_with_api(
        self,
        filter_languages: Optional[List[LanguageType]] = None,
        min_duration: int = 90,
        max_duration: int = 600,
        target_count: int = 10,
        **kwargs
    ) -> List[Dict[str, Any]]:
        """通过 YouTube Data API v3 进行语言过滤 + 爬虫抓取详情（支持『不够继续找』）

        流程分层：
            1. 调用 API search.list 获取目标语言视频ID（支持分页/换关键词/exclude）
            2. language_check 严格语种特征过滤（淘汰 relevanceLanguage 带进来的杂语）
            3. ASR 不友好过滤（Music/Gaming/影视 + 关键词）
            4. 爬虫抓详情（时长/播放量）+ 时长过滤
            5. 若最终结果不足 target_count，会**自动再抓一轮**（带上已用过/淘汰的 ID 作为 exclude）
               直到凑够 target_count 或配额预算用完。

        Args:
            filter_languages: 语言白名单（取第一个作为目标语言）
            min_duration: 最小时长（秒）
            max_duration: 最大时长（秒）
            target_count: 目标产出数量（经过全部过滤后期望返回的条数，不是 API 返回条数）
            **kwargs: 支持两个扩展参数（由 PipelineRunner 传入，用来和数据库跨任务去重联动）：
                - exclude_source_urls: Set[str]  数据库中已存在的 source_url 集合（直接排除）
                - max_search_pages: int  覆盖 API 层默认 max_search_pages（默认 8）

        Returns:
            视频信息列表；API 不可用或调用失败时返回空列表（由调用方回退 trending 模式）
        """
        from core.spiders.youtube_api_client import YouTubeAPIClient

        language_code = "en"
        if filter_languages and len(filter_languages) > 0:
            language_code = filter_languages[0].value

        exclude_urls: set = set(kwargs.get("exclude_source_urls") or set())
        max_search_pages: int = int(kwargs.get("max_search_pages") or 12)

        self._logger.info(
            f"API 语言过滤模式：语言={language_code}, target={target_count}, "
            f"exclude_urls={len(exclude_urls)}, max_search_pages={max_search_pages}"
        )

        # source_url -> youtube video_id（API 层按 video_id 排除更干净）
        def _extract_id(url: str) -> str:
            url = url or ""
            if "v=" in url:
                tail = url.split("v=", 1)[1]
                return tail.split("&", 1)[0].strip()
            return ""

        try:
            client = YouTubeAPIClient()
            if not client.is_available():
                self._logger.warning("YouTube API 密钥未配置，API 搜索不可用")
                return []

            # ========== 继续查找循环 ==========
            # 考虑到语言过滤+ASR过滤+时长过滤会淘汰约 60%~80%，API 需要放大召回
            # v2: ×15 保底 80，配合 12 pages × 4 轮，一次下载轮次尽可能挖够
            target_api = max(target_count * 15, 80)
            max_rounds = 4
            round_i = 0
            excluded_video_ids: set = {_extract_id(u) for u in exclude_urls if u}
            excluded_video_ids.discard("")  # 去掉空值
            seen_attempt_video_ids: set = set(excluded_video_ids)  # 本地失败淘汰也记入，避免反复抓同一个页面
            result: List[Dict[str, Any]] = []
            # 每轮可用的 API 配额递减（上一轮用了多少，下一轮少给点，防止超额）
            remaining_pages = max_search_pages

            # v2 预热阶段：先用 trending 页抓一轮（不走 API，不耗 API 配额），
            # 把高质量的热门视频预填进 result，同时把它们的 video_id 加入排除集，
            # 后面 API 轮次就不会再重复搜到同一条，配额省下来挖更多候选。
            try:
                trending_preheat = self.search_trending(
                    filter_languages=filter_languages,
                    min_duration=min_duration,
                    max_duration=max_duration,
                    target_count=target_count,  # 预热阶段最多抓 target_count 条
                )
                # trending 预热结果也要过语言硬过滤，避免英语/杂语先占坑
                trending_preheat = self._filter_videos_by_language(
                    trending_preheat, filter_languages, source="preheat"
                )
                for tv in trending_preheat:
                    tv_id = _extract_id(tv.get("source_url", ""))
                    if tv_id:
                        seen_attempt_video_ids.add(tv_id)
                self._logger.info(
                    f"[preheat] trending 预热抓到 {len(trending_preheat)} 条候选，"
                    f"{len(seen_attempt_video_ids)} 个ID已加入排除集"
                )
                result.extend(trending_preheat)
            except Exception as preheat_err:
                self._logger.warning(f"[preheat] trending 预热失败（不致命，继续 API）: {preheat_err}")

            while round_i < max_rounds and len(result) < target_count and remaining_pages > 0:
                round_i += 1
                self._logger.info(
                    f"[search_with_api] 第 {round_i}/{max_rounds} 轮: "
                    f"已有结果 {len(result)}/{target_count}, "
                    f"剩余API配额 {remaining_pages} pages, 全局排除ID {len(seen_attempt_video_ids)}"
                )

                # 步骤1: API 仅做语言过滤，获取视频ID列表（自带分页/换词/exclude）
                try:
                    api_videos = client.search_video_ids_by_language(
                        language_code=language_code,
                        max_results=50,
                        target_count=target_api,
                        exclude_ids=set(seen_attempt_video_ids),
                        max_search_pages=remaining_pages,
                    )
                    # 粗略估算：本页平均每页 50 条 = 1 次 search.list，但实际 API 内部有分页
                    # 这里用 len(api_videos) 反推：假设一页能产出 15~25 新视频，取 20/页
                    consumed_pages = max(1, min(remaining_pages, (len(api_videos) + 19) // 20))
                    remaining_pages = max(0, remaining_pages - consumed_pages)
                except RuntimeError as api_err:
                    # 配额耗尽等致命错误：直接返回现有结果（可能 0），上层回退 trending 模式
                    self._logger.warning(f"API 调用报错: {api_err}。返回已有 {len(result)} 条")
                    break

                if not api_videos:
                    self._logger.info(
                        f"第 {round_i} 轮 API 返回 0 条新视频（池子已挖空/配额用完），结束续抓"
                    )
                    break

                self._logger.info(
                    f"第 {round_i} 轮 API 返回 {len(api_videos)} 个新视频ID "
                    f"(已被 exclude 的老视频不再重复返回)"
                )

                # 步骤2: 语言特征过滤
                from utils.language_check import detect_language

                target_lang = LanguageType.from_code(language_code)
                filtered_by_lang: List[Dict[str, Any]] = []
                for api_video in api_videos:
                    vid = api_video.get("video_id", "")
                    title = api_video.get("title", "")
                    seen_attempt_video_ids.add(vid)  # 本地尝试过，下轮排除
                    detected_lang, confidence = detect_language(title)
                    if detected_lang == target_lang:
                        filtered_by_lang.append(api_video)
                    else:
                        self._logger.debug(
                            f"语言过滤淘汰: {title[:40]} "
                            f"(识别为 {detected_lang}, 置信度 {confidence:.2f})"
                        )

                self._logger.info(
                    f"语言特征过滤: API返回 {len(api_videos)} 个, "
                    f"识别为 {target_lang.display_name} 的 {len(filtered_by_lang)} 个"
                )

                if not filtered_by_lang:
                    self._logger.warning(
                        f"语言特征过滤后 0 个视频（目标语言: {target_lang.display_name}）"
                    )
                    continue

                # 步骤2.5: ASR 不友好视频过滤（categoryId + 关键词 联合判断）
                from core.spiders.youtube_api_client import YouTubeAPIClient as _YTApi

                asr_filtered: List[Dict[str, Any]] = []
                category_map: Dict[str, str] = {}
                try:
                    client2 = _YTApi()
                    if client2.is_available():
                        ids_for_cat = [v.get("video_id", "") for v in filtered_by_lang if v.get("video_id")]
                        if ids_for_cat:
                            category_map = client2.get_video_category_ids(ids_for_cat)
                except Exception as e:
                    self._logger.warning(f"获取 categoryId 失败（降级为仅关键词）: {e}")

                hostile_by_category = 0
                hostile_by_keyword = 0
                for api_video in filtered_by_lang:
                    video_id = api_video.get("video_id", "")
                    title = api_video.get("title", "")
                    author = api_video.get("author", "")
                    cat_id = category_map.get(video_id, "")
                    if self._is_asr_hostile_video(title, author, category_id=cat_id):
                        if cat_id:
                            hostile_by_category += 1
                        else:
                            hostile_by_keyword += 1
                    else:
                        asr_filtered.append(api_video)

                self._logger.info(
                    f"ASR不友好过滤: 语言过滤后 {len(filtered_by_lang)} 个, "
                    f"通过 {len(asr_filtered)} 个 "
                    f"(categoryId命中 {hostile_by_category} 个, 关键词命中 {hostile_by_keyword} 个)"
                )

                if not asr_filtered:
                    self._logger.warning("ASR不友好过滤后 0 个，进入下一轮")
                    continue

                # 步骤3: 抓视频详情 + 时长过滤
                detail_need = max(target_count - len(result), 0)
                # 为节省网络：多抓 5 倍量（抵消详情抓取失败/时长不合）
                max_detail_count = min(len(asr_filtered), max(detail_need * 5, 30))
                detailed_videos: List[Dict[str, Any]] = []

                self._logger.info(f"开始抓取 {max_detail_count} 个视频的详情")

                for idx, api_video in enumerate(asr_filtered[:max_detail_count]):
                    video_id = api_video.get("video_id", "")
                    if not video_id:
                        continue

                    watch_url = build_watch_url(video_id)
                    try:
                        html = self._engine.get(watch_url)
                        if html is None:
                            self._logger.warning(f"抓取视频页面失败: {video_id}")
                            continue
                        page_info = self._parse_video_page(html, watch_url)
                        if not page_info:
                            self._logger.warning(f"解析视频页面失败: {video_id}")
                            continue

                        merged: Dict[str, Any] = {
                            "title": api_video.get("title") or page_info.get("title", ""),
                            "source_url": watch_url,
                            "description": api_video.get("description") or page_info.get("description", ""),
                            "thumbnail": api_video.get("thumbnail", ""),
                            "duration": page_info.get("duration", ""),
                            "author": api_video.get("author") or page_info.get("author", ""),
                            "views": page_info.get("views", ""),
                            "published_at": api_video.get("published_at", ""),
                        }
                        detailed_videos.append(merged)
                    except Exception as e:
                        self._logger.warning(f"抓取视频详情异常 {video_id}: {e}")
                        continue

                self._logger.info(f"详情抓取完成，共 {len(detailed_videos)} 个视频")
                duration_filtered = self._filter_by_duration(
                    detailed_videos, min_duration, max_duration
                )
                categorized = self._enrich_categories(duration_filtered)

                # 合并：去除与已有结果重复的 source_url
                existing_urls_in_result = {v.get("source_url", "") for v in result}
                for v in categorized:
                    if v.get("source_url", "") not in existing_urls_in_result:
                        result.append(v)
                        existing_urls_in_result.add(v.get("source_url", ""))

                self._logger.info(
                    f"第 {round_i} 轮结束: 本轮入库 {len(categorized)} 条 -> "
                    f"总结果 {len(result)}/{target_count}"
                )

            # ========== 循环结束 ==========
            if len(result) < target_count:
                self._logger.warning(
                    f"search_with_api 结束：最终 {len(result)}/{target_count} 条 "
                    f"({round_i} 轮, 剩余配额 pages={remaining_pages})"
                )
            else:
                self._logger.info(
                    f"search_with_api 达标：最终 {len(result)} 条 (target={target_count})"
                )
            return self.filter_dead_urls(result)

        except Exception as e:
            self._logger.error(f"API 语言过滤搜索失败: {e}")
            return []

    def _filter_videos_by_language(
        self,
        videos: List[Dict[str, Any]],
        filter_languages: Optional[List[LanguageType]],
        source: str = "trending",
    ) -> List[Dict[str, Any]]:
        """按视频标题+描述过滤语言

        爬虫的 YouTube 搜索 (hl=de&gl=DE) 只能保证地区，
        不保证返回的视频实际语言——热门/通用 query 常混入英语。
        这里用 detect_video_language 做硬过滤。
        """
        if not filter_languages:
            return videos

        target = filter_languages[0]
        target_code = target.value if isinstance(target, LanguageType) else str(target)

        kept: List[Dict[str, Any]] = []
        rejected = 0
        for v in videos:
            title = v.get("title", "") or ""
            desc = v.get("description") or ""
            det_lang, confidence = detect_video_language(title, desc)
            if det_lang == target:
                kept.append(v)
            else:
                rejected += 1
                if rejected <= 5:
                    self._logger.info(
                        f"[{source}] 语言淘汰: {title[:45]} "
                        f"(目标={target.display_name}, "
                        f"识别={getattr(det_lang, 'display_name', det_lang)}, "
                        f"置信={confidence:.2f})"
                    )

        self._logger.info(
            f"[{source}] 语言过滤完成: 输入 {len(videos)} → 保留 {len(kept)} "
            f"(淘汰 {rejected}, 目标={target.display_name})"
        )
        return kept

    def _filter_by_duration(
        self,
        videos: List[Dict[str, Any]],
        min_duration: int,
        max_duration: int
    ) -> List[Dict[str, Any]]:
        """按时长过滤视频列表"""
        if min_duration <= 0 and max_duration >= float('inf'):
            return videos
        
        filtered: List[Dict[str, Any]] = []
        filtered_count = 0
        no_duration_count = 0
        
        for video in videos:
            duration = self._parse_duration(video.get("duration"))
            if duration is None:
                no_duration_count += 1
                filtered_count += 1
            elif min_duration <= duration <= max_duration:
                filtered.append(video)
            else:
                filtered_count += 1
        
        # 回退：如果全部无时长，保留全部
        if not filtered and videos and no_duration_count == len(videos):
            self._logger.warning(
                f"时长过滤后0个（{no_duration_count}个无时长），回退保留全部 {len(videos)} 个"
            )
            return videos
        
        self._logger.info(
            f"时长过滤完成，保留 {len(filtered)} 个（过滤 {filtered_count} 个，其中无时长 {no_duration_count} 个）"
        )
        return filtered
    
    def _parse_duration(self, duration_str: Any) -> Optional[int]:
        """解析时长字符串或数字为秒数
        
        支持格式：
            - 整数秒数：123
            - 冒号格式："12:34", "1:23:45"
            - ISO 8601 格式："PT12M34S", "PT1H23M45S"
        
        Args:
            duration_str: 时长字符串或整数秒数
            
        Returns:
            秒数，解析失败返回 None
        """
        if duration_str is None:
            return None
            
        # 整数类型
        if isinstance(duration_str, (int, float)):
            return int(duration_str)
            
        if isinstance(duration_str, str):
            duration_str = duration_str.strip()
            if not duration_str:
                return None
            
            # ISO 8601 格式：PT1H23M45S
            iso_match = re.match(r'^PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?$', duration_str, re.IGNORECASE)
            if iso_match:
                hours = int(iso_match.group(1) or 0)
                minutes = int(iso_match.group(2) or 0)
                seconds = int(iso_match.group(3) or 0)
                return hours * 3600 + minutes * 60 + seconds
            
            # 冒号格式："12:34" 或 "1:23:45"
            parts = duration_str.split(":")
            try:
                if len(parts) == 2:
                    return int(parts[0]) * 60 + int(parts[1])
                elif len(parts) == 3:
                    return int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2])
                elif len(parts) == 1 and parts[0].isdigit():
                    return int(parts[0])
            except ValueError:
                return None
        
        return None
    
    def search(
        self,
        query: str,
        max_pages: int = 5,
        filter_languages: Optional[List[LanguageType]] = None,
        min_duration: int = 90,
        max_duration: int = 300,
        **kwargs
    ) -> List[Dict[str, Any]]:
        """
        搜索 YouTube 视频
        
        Args:
            query: 搜索关键词
            max_pages: 最大页数
            filter_languages: 语言白名单
            min_duration: 最小时长（秒），默认90秒（1分30秒）
            max_duration: 最大时长（秒），默认300秒（5分钟）
            **kwargs: 其他搜索参数
        
        Returns:
            视频信息列表
        """
        self._logger.info(f"YouTube 搜索: {query}")
        
        def pagination_strategy(base_url: str, page: int) -> str:
            if page == 1:
                return base_url
            return f"{base_url}&page={page}"
        
        language_code = "en"
        if filter_languages and len(filter_languages) > 0:
            language_code = filter_languages[0].value
        
        # 如果是通用词（如"Video"）且指定了语言，使用语言关键词替换
        search_queries = [query]
        if query.strip().lower() in ("video", "videos", "movie", "movies", "clip", "clips", "film"):
            lang_keywords = self.LANGUAGE_KEYWORDS.get(language_code, [])
            if lang_keywords:
                # 随机打乱关键词顺序，并随机选取一部分（最多选8个，避免请求过多）
                shuffled = lang_keywords[:]
                random.shuffle(shuffled)
                num_to_use = min(len(shuffled), max(5, max_pages))
                search_queries = shuffled[:num_to_use]
                self._logger.info(
                    f"检测到通用搜索词，从 {len(lang_keywords)} 个关键词中随机选取 {len(search_queries)} 个: "
                    f"{search_queries[:3]}..."
                )
        
        # 随机选取排序参数（增加结果多样性）
        sort_param = random.choice(self.SEARCH_SORT_PARAMS)
        
        # 随机起始页码偏移（从更大的页码范围中随机选择起始页）
        # 例如 max_pages=10 时，从 1-5 中随机选起始页，爬 5 页
        page_offset = random.randint(0, max(0, max_pages - 5))
        
        base_url = self._build_search_url(query, language=language_code) + sort_param
        
        # 如果有多个搜索词，则使用每个关键词分别搜索并合并结果
        if len(search_queries) > 1:
            all_videos = []
            seen_urls = set()
            for sq in search_queries:
                # 每个关键词使用不同的随机排序参数
                sq_sort = random.choice(self.SEARCH_SORT_PARAMS)
                sq_url = self._build_search_url(sq, language=language_code) + sq_sort
                self._logger.info(f"使用关键词搜索: {sq} (排序参数: {sq_sort or '默认'})")
                videos = self.crawl_with_pagination(
                    base_url=sq_url,
                    max_pages=max_pages,
                    pagination_strategy=pagination_strategy,
                    filter_languages=filter_languages
                )
                # 去重合并
                for v in videos:
                    url = v.get("source_url") or v.get("url", "")
                    if url and url not in seen_urls:
                        seen_urls.add(url)
                        all_videos.append(v)
                if len(all_videos) >= max_pages * 8:
                    break
            videos = all_videos
        else:
            videos = self.crawl_with_pagination(
                base_url=base_url,
                max_pages=max_pages,
                pagination_strategy=pagination_strategy,
                filter_languages=filter_languages
            )
        
        filtered_count = 0
        no_duration_count = 0
        if min_duration > 0 or max_duration < float('inf'):
            filtered_videos = []
            for video in videos:
                duration = self._parse_duration(video.get("duration"))
                if duration is None:
                    # 无法解析时长，不保留（避免下载阶段才发现时长不符）
                    no_duration_count += 1
                    filtered_count += 1
                    self._logger.debug(
                        f"过滤无时长视频: {video.get('title', 'N/A')[:30]} "
                        f"(duration字段={video.get('duration')!r})"
                    )
                elif min_duration <= duration <= max_duration:
                    filtered_videos.append(video)
                else:
                    filtered_count += 1
                    self._logger.debug(
                        f"过滤时长不符视频: {video.get('title', 'N/A')[:30]} "
                        f"(时长={duration}秒，要求{min_duration}-{max_duration}秒)"
                    )
            
            # 回退逻辑1：所有视频都无法解析时长，保留所有视频
            if not filtered_videos and videos and no_duration_count == len(videos):
                self._logger.warning(
                    f"时长过滤后0个视频（共{no_duration_count}个无时长），"
                    f"回退为不过滤，保留全部 {len(videos)} 个视频"
                )
                filtered_count = 0
                no_duration_count = 0
            # 回退逻辑2：所有视频都超过时长限制，保留时长最短的视频
            elif not filtered_videos and videos and no_duration_count == 0:
                self._logger.warning(
                    f"时长过滤后0个视频（所有视频都超过{max_duration}秒限制），"
                    f"保留时长最短的视频"
                )
                videos_with_duration = []
                for video in videos:
                    duration = self._parse_duration(video.get("duration"))
                    if duration:
                        videos_with_duration.append((duration, video))
                
                if videos_with_duration:
                    videos_with_duration.sort(key=lambda x: x[0])
                    videos = [v[1] for v in videos_with_duration]
                    filtered_count = 0
                else:
                    videos = []
            else:
                videos = filtered_videos
        
        self._logger.info(
            f"YouTube 搜索完成，获取 {len(videos)} 个视频"
            f"（过滤时长 {filtered_count} 个，其中无时长 {no_duration_count} 个）"
        )

        # ASR 不友好过滤（无 categoryId，仅关键词兜底）
        # search 关键词搜索模式无 API categoryId，降级为仅关键词判断
        asr_filtered_search: List[Dict[str, Any]] = []
        search_hostile = 0
        for v in videos:
            title = v.get("title", "")
            author = v.get("author", "")
            if self._is_asr_hostile_video(title, author, category_id=None):
                search_hostile += 1
                self._logger.debug(
                    f"search(关键词) ASR过滤淘汰: {title[:40]} (频道: {author})"
                )
            else:
                asr_filtered_search.append(v)

        self._logger.info(
            f"search ASR过滤: 时长过滤后 {len(videos)} 个, "
            f"通过 {len(asr_filtered_search)} 个 (淘汰 {search_hostile} 个)"
        )
        # 自动分类填充 category 字段 → yt-dlp 预探过滤
        categorized = self._enrich_categories(asr_filtered_search)
        # 语言硬过滤：关键词搜索结果可能混入杂语
        categorized = self._filter_videos_by_language(
            categorized, filter_languages, source="search"
        )
        return self.filter_dead_urls(categorized)
    
    def get_video_info(self, video_url: str) -> Optional[Dict[str, Any]]:
        """
        获取单个 YouTube 视频详情
        
        Args:
            video_url: 视频 URL
        
        Returns:
            视频详情字典
        """
        self._logger.info(f"获取 YouTube 视频详情: {video_url}")
        
        html = self._engine.get(video_url)
        if html is None:
            self._logger.error(f"获取视频页面失败: {video_url}")
            return None
        
        video_info = self._parse_video_page(html, video_url)
        if video_info:
            return self._normalize_video_info(video_info)
        
        return None
    
    def get_channel_videos(
        self,
        channel_url: str,
        max_pages: int = 5,
        filter_languages: Optional[List[LanguageType]] = None
    ) -> List[Dict[str, Any]]:
        """
        获取 YouTube 频道视频列表
        
        Args:
            channel_url: 频道 URL
            max_pages: 最大页数
            filter_languages: 语言白名单
        
        Returns:
            视频信息列表
        """
        self._logger.info(f"获取 YouTube 频道视频: {channel_url}")
        
        # YouTube 频道视频页面格式
        videos_url = channel_url.rstrip("/") + "/videos"
        
        def pagination_strategy(base_url: str, page: int) -> str:
            if page == 1:
                return base_url
            return f"{base_url}?page={page}"
        
        videos = self.crawl_with_pagination(
            base_url=videos_url,
            max_pages=max_pages,
            pagination_strategy=pagination_strategy,
            filter_languages=filter_languages
        )
        
        self._logger.info(f"频道视频获取完成，获取 {len(videos)} 个视频")
        return videos
    
    def parse(self, html: str, url: str) -> List[Dict[str, Any]]:
        """
        解析 YouTube 页面 HTML
        
        Args:
            html: 页面 HTML 内容
            url: 当前页面 URL
        
        Returns:
            视频信息列表
        """
        videos = []
        
        try:
            # 提取页面中的 JSON-LD 数据
            json_ld_match = re.search(r'<script type="application/ld\+json">(.*?)</script>', html, re.DOTALL)
            if json_ld_match:
                try:
                    data = json.loads(json_ld_match.group(1))
                    if isinstance(data, list):
                        data = data[0]
                    
                    if "@type" in data:
                        if data["@type"] == "ItemList":
                            for item in data.get("itemListElement", []):
                                video = self._parse_json_ld_item(item)
                                if video:
                                    videos.append(video)
                        elif data["@type"] == "VideoObject":
                            video = self._parse_video_object(data)
                            if video:
                                videos.append(video)
                except json.JSONDecodeError:
                    pass
            
            # 提取 YouTube 内部数据
            yt_data_match = re.search(r'var ytInitialData = ({.*?});', html, re.DOTALL)
            if yt_data_match:
                try:
                    yt_data = json.loads(yt_data_match.group(1))
                    videos.extend(self._parse_yt_initial_data(yt_data))
                except json.JSONDecodeError:
                    pass
            
            # 使用正则提取视频信息
            if not videos:
                videos = self._parse_with_regex(html)
        
        except Exception as e:
            self._logger.error(f"YouTube 页面解析失败: {e}")
        
        return videos
    
    def _parse_json_ld_item(self, item: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """解析 JSON-LD 列表项"""
        if item.get("@type") != "VideoObject":
            return None
        
        video = {
            "title": item.get("name"),
            "source_url": item.get("url"),
            "description": item.get("description"),
            "thumbnail": item.get("thumbnailUrl"),
            "duration": item.get("duration"),
            "author": item.get("author", {}).get("name"),
            "views": item.get("interactionCount"),
            "published_at": item.get("datePublished"),
        }
        
        return {k: v for k, v in video.items() if v}
    
    def _parse_video_object(self, data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """解析单个 VideoObject"""
        video = {
            "title": data.get("name"),
            "source_url": data.get("url"),
            "description": data.get("description"),
            "thumbnail": data.get("thumbnailUrl"),
            "duration": data.get("duration"),
            "author": data.get("author", {}).get("name"),
            "views": data.get("interactionCount"),
            "published_at": data.get("datePublished"),
        }
        
        return {k: v for k, v in video.items() if v}
    
    def _parse_yt_initial_data(self, data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """解析 YouTube 内部数据"""
        videos = []
        
        try:
            contents = data.get("contents", {})
            two_column_search_results = contents.get("twoColumnSearchResultsRenderer", {})
            primary_contents = two_column_search_results.get("primaryContents", {})
            section_list = primary_contents.get("sectionListRenderer", {})
            contents_list = section_list.get("contents", [])
            
            for section in contents_list:
                item_section = section.get("itemSectionRenderer", {})
                video_items = item_section.get("contents", [])
                
                for item in video_items:
                    video_renderer = item.get("videoRenderer")
                    if video_renderer:
                        video = self._parse_video_renderer(video_renderer)
                        if video:
                            videos.append(video)
        except Exception as e:
            self._logger.debug(f"解析 YouTube 内部数据失败: {e}")
        
        return videos
    
    def _parse_video_renderer(self, renderer: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """解析视频渲染器数据"""
        try:
            video = {
                "title": renderer.get("title", {}).get("runs", [{}])[0].get("text"),
                "source_url": build_watch_url(renderer.get("videoId", "")),
                "description": renderer.get("descriptionSnippet", {}).get("runs", [{}])[0].get("text"),
                "thumbnail": renderer.get("thumbnail", {}).get("thumbnails", [{}])[-1].get("url"),
                "duration": renderer.get("lengthText", {}).get("simpleText"),
                "author": renderer.get("ownerText", {}).get("runs", [{}])[0].get("text"),
                "views": renderer.get("viewCountText", {}).get("simpleText"),
                "published_at": renderer.get("publishedTimeText", {}).get("simpleText"),
            }
            
            return {k: v for k, v in video.items() if v}
        except Exception:
            return None
    
    def _parse_with_regex(self, html: str) -> List[Dict[str, Any]]:
        """使用正则表达式提取视频信息"""
        videos = []
        
        # 提取视频链接
        video_pattern = r'<a\s+href="(/watch\?v=[^"]+)"[^>]*>'
        title_pattern = r'<a\s+href="/watch\?v=[^"]+"[^>]*>([^<]+)</a>'
        
        links = re.findall(video_pattern, html)
        titles = re.findall(title_pattern, html)
        
        for i, link in enumerate(links):
            video = {
                "title": titles[i] if i < len(titles) else "",
                "source_url": "https://www.youtube.com" + link,
            }
            
            if video["title"] or video["source_url"]:
                videos.append(video)
        
        return videos
    
    def _parse_video_page(self, html: str, url: str) -> Optional[Dict[str, Any]]:
        """解析视频详情页面"""
        video_info = {}
        
        # 提取标题
        title_match = re.search(r'<title>(.*?)\s*-\s*YouTube</title>', html)
        if title_match:
            video_info["title"] = title_match.group(1)
        
        # 提取描述
        desc_match = re.search(r'<meta\s+name="description"\s+content="([^"]+)"', html)
        if desc_match:
            video_info["description"] = desc_match.group(1)
        
        # 提取时长
        duration_match = re.search(r'"lengthSeconds":"(\d+)"', html)
        if duration_match:
            video_info["duration"] = int(duration_match.group(1))
        
        # 提取播放量
        views_match = re.search(r'"viewCount":"([^"]+)"', html)
        if views_match:
            video_info["views"] = views_match.group(1)
        
        # 提取作者
        author_match = re.search(r'"author":"([^"]+)"', html)
        if author_match:
            video_info["author"] = author_match.group(1)
        
        video_info["source_url"] = url
        
        return video_info if video_info else None
    
    def _build_search_url(self, query: str, language: str = "en") -> str:
        """构建 YouTube 搜索 URL"""
        import urllib.parse
        encoded_query = urllib.parse.quote(query)
        return f"https://www.youtube.com/results?search_query={encoded_query}&hl={language}&gl={language.upper()}"
    
    def _extract_video_id(self, url: str) -> Optional[str]:
        """从 URL 中提取 YouTube 视频 ID"""
        match = re.match(r'.*youtube\.com/watch\?v=([^&]+)', url)
        if match:
            return match.group(1)
        
        match = re.match(r'.*youtube\.com/embed/([^/]+)', url)
        if match:
            return match.group(1)
        
        return None

    def search_by_keyword(
        self,
        keyword: str,
        filter_languages: Optional[List[LanguageType]] = None,
        min_duration: int = 60,
        max_duration: int = 900,
        target_count: int = 20,
        order: str = "relevance",
        **kwargs,
    ) -> List[Dict[str, Any]]:
        """按关键词搜索视频（WebUI 「搜索模式」Tab 入口）"""
        return self._enrich_api_videos(
            api_search_fn=lambda client, exc_ids: client.search_by_keyword(
                keyword=keyword,
                language_code=(
                    filter_languages[0].value if filter_languages else "en"
                ),
                target_count=max(target_count * 5, 30),
                exclude_ids=exc_ids,
                max_search_pages=int(kwargs.get("max_search_pages") or 8),
                order=order,
            ),
            filter_languages=filter_languages,
            min_duration=min_duration,
            max_duration=max_duration,
            target_count=target_count,
            search_label=f"keyword:'{keyword}'",
            exclude_source_urls=kwargs.get("exclude_source_urls") or set(),
        )

    def search_channel(
        self,
        channel_identifier: str,
        min_duration: int = 60,
        max_duration: int = 900,
        target_count: int = 20,
        order: str = "date",
        **kwargs,
    ) -> List[Dict[str, Any]]:
        """按频道名 / @handle / channelId 抓取视频（WebUI 入口）"""
        from core.spiders.youtube_api_client import YouTubeAPIClient

        exclude_urls: set = set(kwargs.get("exclude_source_urls") or set())

        def _extract_id(url: str) -> str:
            if "v=" in (url or ""):
                return url.split("v=", 1)[1].split("&", 1)[0]
            return ""

        try:
            client = YouTubeAPIClient()
            if not client.is_available():
                self._logger.warning("YouTube API 密钥未配置，频道搜索不可用")
                return []

            channel_id = client.resolve_channel_id(channel_identifier)
            if not channel_id:
                self._logger.warning(
                    f"无法解析频道标识 '{channel_identifier}' 为 channelId"
                )
                return []

            self._logger.info(
                f"频道解析: '{channel_identifier}' → channelId={channel_id}"
            )
        except Exception as e:
            self._logger.error(f"频道解析异常: {e}")
            return []

        return self._enrich_api_videos(
            api_search_fn=lambda c, exc_ids: c.search_channel_videos(
                channel_id=channel_id,
                target_count=max(target_count * 5, 30),
                exclude_ids=exc_ids,
                max_search_pages=int(kwargs.get("max_search_pages") or 6),
                order=order,
            ),
            filter_languages=None,
            min_duration=min_duration,
            max_duration=max_duration,
            target_count=target_count,
            search_label=f"channel:{channel_identifier}",
            exclude_source_urls=exclude_urls,
        )

    # --------------------------------------------------
    # 通用 API 视频 enrichment（供 search_by_keyword / search_channel 共用）
    # --------------------------------------------------
    def _enrich_api_videos(
        self,
        api_search_fn,
        filter_languages: Optional[List[LanguageType]],
        min_duration: int,
        max_duration: int,
        target_count: int,
        search_label: str,
        exclude_source_urls: set,
    ) -> List[Dict[str, Any]]:
        """调用 api_search_fn 拿轻量视频列表 → 过滤 → 抓详情 → 合并

        和 search_with_api 流程一致：
            1. API search.list → 拿到 video_id + title 等 snippet 信息
            2. 语言特征过滤（如果指定了 filter_languages）
            3. ASR 不友好过滤（categoryId + 关键词）
            4. 爬详情页 HTML → _parse_video_page 解析 → 合并成完整字典
            5. 时长过滤
        """
        from core.spiders.youtube_api_client import YouTubeAPIClient

        def _extract_id(url: str) -> str:
            url = url or ""
            if "v=" in url:
                return url.split("v=", 1)[1].split("&", 1)[0].strip()
            return ""

        try:
            client = YouTubeAPIClient()
            if not client.is_available():
                self._logger.warning("YouTube API 密钥未配置，搜索不可用")
                return []

            excluded_ids: set = {_extract_id(u) for u in exclude_source_urls if u}
            excluded_ids.discard("")

            # 1. 调 API
            try:
                api_videos = api_search_fn(client, excluded_ids)
            except RuntimeError as e:
                self._logger.warning(f"[{search_label}] API 调用失败: {e}")
                return []

            if not api_videos:
                self._logger.info(f"[{search_label}] API 返回 0 条")
                return []

            self._logger.info(
                f"[{search_label}] API 返回 {len(api_videos)} 条，开始过滤..."
            )

            # 2. 语言过滤（如果传了 filter_languages）
            if filter_languages:
                api_videos = self._filter_videos_by_language(
                    api_videos, filter_languages, source=search_label
                )
                self._logger.info(
                    f"[{search_label}] 语言过滤后 {len(api_videos)} 条"
                )

            if not api_videos:
                return []

            # 3. ASR 不友好过滤
            asr_passed: List[Dict[str, Any]] = []
            try:
                ids_for_cat = [
                    v.get("video_id", "")
                    for v in api_videos
                    if v.get("video_id")
                ]
                category_map = client.get_video_category_ids(ids_for_cat) if ids_for_cat else {}
            except Exception:
                category_map = {}

            for v in api_videos:
                vid = v.get("video_id", "")
                title = v.get("title", "")
                author = v.get("author", "")
                cat_id = category_map.get(vid, "")
                if self._is_asr_hostile_video(title, author, category_id=cat_id):
                    continue
                asr_passed.append(v)

            self._logger.info(
                f"[{search_label}] ASR 过滤后 {len(asr_passed)} 条"
            )
            if not asr_passed:
                return []

            # 4. 爬详情页 + 合并（和 search_with_api 步骤3 完全一致）
            need = max(target_count, len(asr_passed))
            max_detail = min(len(asr_passed), max(need * 3, 30))
            result: List[Dict[str, Any]] = []

            for api_v in asr_passed[:max_detail]:
                video_id = api_v.get("video_id", "")
                if not video_id:
                    continue
                watch_url = build_watch_url(video_id)
                try:
                    html = self._engine.get(watch_url)
                    if html is None:
                        continue
                    page_info = self._parse_video_page(html, watch_url)
                    if not page_info:
                        continue

                    duration_sec = 0
                    dur_str = page_info.get("duration", "")
                    if dur_str:
                        try:
                            parts = [int(p) for p in dur_str.split(":")]
                            if len(parts) == 3:
                                duration_sec = parts[0] * 3600 + parts[1] * 60 + parts[2]
                            elif len(parts) == 2:
                                duration_sec = parts[0] * 60 + parts[1]
                        except Exception:
                            duration_sec = 0

                    if duration_sec and (
                        duration_sec < min_duration or duration_sec > max_duration
                    ):
                        continue

                    merged: Dict[str, Any] = {
                        "title": api_v.get("title") or page_info.get("title", ""),
                        "source_url": watch_url,
                        "description": api_v.get("description") or page_info.get("description", ""),
                        "duration": dur_str or str(duration_sec),
                        "author": api_v.get("author") or page_info.get("author", ""),
                        "views": page_info.get("views", 0) or api_v.get("views", 0),
                        "thumbnail": api_v.get("thumbnail") or page_info.get("thumbnail", ""),
                        "yt_video_id": video_id,
                        "channel_id": api_v.get("channel_id", ""),
                        "channel_name": api_v.get("channel_name", "") or api_v.get("author", ""),
                        "published_at": api_v.get("published_at") or api_v.get("snippet", {}).get("publishedAt"),
                        "categoryId": api_v.get("categoryId"),
                    }
                    result.append(merged)
                    if len(result) >= target_count:
                        break
                except Exception as e:
                    self._logger.debug(f"[{search_label}] 抓 {video_id} 失败: {e}")
                    continue

            self._logger.info(
                f"[{search_label}] 最终 {len(result)} 条完整视频"
            )
            return result

        except Exception as e:
            self._logger.error(f"[{search_label}] 异常: {e}")
            return []
