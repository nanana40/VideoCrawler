# VideoCrawler 开发与维护手册

> 最后更新：2026-08-13（生产环境初始化 + 资源锁/API 健壮性优化后）
> 代码规模：51 个 Python 文件，约 34,100 行
> 启动命令：`python main.py --full`（GUI 通过 `start_gui.bat` 启动）

---

## 一、项目定位与架构

### 1.1 一句话概述

多语种（英/德/法/西等）外语学习视频的自动化生产流水线：从 YouTube/B站/TikTok 爬取 → 下载 → 语音转写（ASR）→ 字幕翻译 → 字幕烧录 → 内容分析（口语学习+应试学习）→ 自动生成小红书/微博/知乎文案。

### 1.2 宏观流水线（pipeline.py）

```
Stage 1: 清理未下载旧记录（保留已下载用于跨任务去重）
         ↓
         YouTube Data API v3 语言过滤搜索 → 回退到热门页抓取
         → v2 LLM 标签打标（sub_category / tags / channel_id / series_id）
         → 写入 SQLite + 内存缓冲池批量刷盘
         ↓
Stage 2: 候选收集（不够则续搜 2 轮）
         → _cohesion_sort 按 channel_id / series_id / related_cluster_id 内聚排序
         ↓
Stage 3: ThreadPoolExecutor(max_workers=N) 跨视频并发
         ┌──────────────┬──────────────┬──────────────┐
         │ Video A      │ Video B      │ Video C      │
         │ download     │ subtitle     │ analyze+fmt  │
         │ → subtitle   │ → analyze+fmt│  ...          │
         │ → analyze+fmt│              │              │
         └──────────────┴──────────────┴──────────────┘
         每个视频内部严格顺序，但不同视频可以跨阶段并行。
```

### 1.3 关键设计决策

| 决策 | 理由 |
|------|------|
| **跨任务去重** | 保留已下载记录，只清理未下载的。下次启动同一视频 URL 直接跳过。 |
| **内聚排序** | 同频道/同系列视频聚在一起一次处理，产出的内容天然适合社交媒体连续发。 |
| **broken 标记** | 下载失败自动标记 broken，下游 `get_undownloaded_videos` 不再捞。 |
| **缓冲池 + 定时刷盘** | SQLite 单写者瓶颈，BufferPool 用 RLock + 后台线程批量写，吞吐提升 ~10x。 |
| **LLM 降级链** | 主模型 429/超时 → 指数退避重试 → 降级到备用模型链（glm-4.7-flash → glm-4-air → ...） |
| **Gemini 全托管 vs 本地管线** | subtitle_processor.py 内部根据 config.yaml 决定走哪条路径，透明处理。 |

---

## 二、目录结构

```
Vc/
├── main.py                       # 入口（--full / --reset-db / --query；GUI 通过 start_gui.bat 启动）
├── config.yaml                   # 全部配置（爬虫/下载/AI模型/输出目录）
├── requirements-runtime.txt      # 生产依赖
├── requirements-dev.txt          # 开发依赖
│
├── core/                         # 核心业务逻辑
│   ├── pipeline.py               # ⭐ 统一流程协调器（704 行，已重构）
│   ├── crawler.py                # 爬虫引擎（curl_cffi 指纹轮换 + 普通 requests 兜底）
│   ├── download.py               # yt-dlp 下载池（VideoDownloader）
│   ├── subtitle_processor.py     # ⚠ 6244 行巨型模块（ASR→翻译→烧录一站式）
│   ├── translation_engine.py     # 字幕翻译（本地/API 双通道）
│   ├── video_analyzer.py         # ⚠ 5683 行巨型模块（口语学习+应试学习分析）
│   ├── social_media_formatter.py # 3400 行（小红书/微博/知乎文案生成）
│   ├── content_tag.py            # v2 标签体系（Rule-based + LLM 混合打标）
│   ├── ai_writer.py              # AI 文案生成（提示词工程）
│   ├── classify.py               # RuleBasedClassifier（被 youtube_spider.py 调用）
│   ├── expression_knowledge.py    # 口语表达知识库（被 social_media_formatter 调用）
│   ├── gemini_engine.py          # Gemini ASR/校对/总结
│   ├── task_scheduler.py         # 定时健康检查 + 日志清理（被 main.py/app_initializer 调用）
│   ├── subtitle_trans.py         # 字幕翻译工具
│   └── spiders/
│       ├── __init__.py           # create_spider() 工厂
│       ├── base_spider.py
│       ├── youtube_spider.py     # 主爬虫（yt-dlp + API v3 双通道）
│       ├── youtube_api_client.py # YouTube Data API v3 封装
│       ├── bilibili_spider.py    # B站（代码就绪，未全面测试）
│       ├── tiktok_spider.py      # TikTok
│       ├── vimeo_spider.py       # Vimeo
│       └── dailymotion_spider.py # Dailymotion
│
├── utils/                        # 基础设施
│   ├── db_manager.py             # ⭐ SQLite 管理器 + BufferPool（1332 行）
│   ├── enums.py                  # LanguageType / VideoCategory / TaskStatus
│   ├── config_loader.py          # config.yaml 加载（无热重载）
│   ├── path_helper.py            # 统一路径管理（get_db_path / get_config_path ...）
│   ├── file_sort.py              # 按语言/类别归档视频文件
│   ├── srt_parser.py             # SRT 字幕解析
│   ├── logger.py                 # 日志配置
│   ├── queue_manager.py          # 任务队列
│   ├── crypto_util.py            # API Key 加密存储
│   ├── language_check.py         # BOM 已修复，语言检测
│   └── app_initializer.py        # 应用初始化（调 BufferPool + task_scheduler）
│
├── gui/                          # PySide6 桌面 GUI（main_window / pages / video_preview / subtitle_canvas）
│
├── models/
│   └── asr/models--Systran--faster-whisper-small/   # faster-whisper ASR 模型
│
├── bin/ffmpeg/                   # FFmpeg 可执行文件（视频处理必需）
├── data/video_tasks.db           # SQLite 查重数据库
├── output/                       # 视频输出目录（按语言/类别/ID 分层归档）
├── logs/                         # 运行日志
├── scripts/                      # 辅助脚本（下载 ASR 模型 / 保存 API Key）
├── tools/view_logs.py            # 日志查看器
└── resources/schema.sql         # 数据库建表脚本
```

---

## 三、启动方式

### 3.1 生产环境启动（推荐）

```bash
# 首次/重置数据库
python main.py --reset-db --full

# 日常运行（数据库保留已下载记录用于跨任务去重）
python main.py --full
```

### 3.2 GUI 桌面界面

双击项目根目录的 `start_gui.bat` 即可启动 PySide6 桌面 GUI。

### 3.3 带搜索关键词

```bash
python main.py --full --query "machine learning AI"
```

### 3.4 参数说明

| 参数 | 说明 |
|------|------|
| `--full` | 完整流水线：爬取→下载→字幕→分析 |
| `--query TEXT` | 搜索关键词（传入 config 但暂未注入 spider） |
| `--reset-db` | 启动前清空 video_info + translate_task |

### 3.5 环境准备清单

- [ ] Python 3.10+
- [ ] `pip install -r requirements-runtime.txt`
- [ ] FFmpeg 在 `bin/ffmpeg/` 或 PATH 中
- [ ] faster-whisper ASR 模型在 `models/asr/`
- [ ] YouTube Data API v3 Key（config.yaml 中配置）
- [ ] Gemini API Key（config.yaml 中配置，subtitle_processor 可选）
- [ ] 智谱 API Key（glm-4.7-flash，用于 LLM 标签和 AI 文案）

---

## 四、数据库 Schema（video_tasks.db）

### 4.1 video_info 表（核心查重表）

```sql
CREATE TABLE IF NOT EXISTS video_info (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_url TEXT UNIQUE NOT NULL,      -- 跨任务去重键
    youtube_id TEXT,                       -- 视频平台 ID
    title TEXT,
    description TEXT,
    thumbnail TEXT,
    duration TEXT,
    author TEXT,
    views INTEGER DEFAULT 0,
    lang TEXT DEFAULT 'en',                -- ISO 639-1
    category TEXT DEFAULT 'daily',         -- VideoCategory 枚举值
    sub_category TEXT,                     -- v2 细分类别（Rule-based + LLM）
    tags TEXT,                             -- v2 标签 JSON 数组
    yt_category_id TEXT,                   -- YouTube 官方 category ID
    channel_id TEXT,                       -- 频道 ID（用于内聚排序）
    channel_name TEXT,
    series_id TEXT,                        -- 系列 ID（同系列连续发布）
    related_cluster_id TEXT,               -- 相关话题聚类桶
    published_at TEXT,
    is_downloaded INTEGER DEFAULT 0,
    local_video_path TEXT,                 -- 烧录字幕后的成品 mp4 路径
    download_time TEXT,
    is_broken INTEGER DEFAULT 0,           -- 标记后不再被捞取
    broken_reason TEXT,
    create_ts INTEGER,
    update_ts INTEGER
);
CREATE INDEX IF NOT EXISTS idx_video_info_downloaded ON video_info(is_downloaded);
CREATE INDEX IF NOT EXISTS idx_video_info_broken ON video_info(is_broken);
CREATE INDEX IF NOT EXISTS idx_video_info_lang ON video_info(lang);
```

### 4.2 translate_task 表（字幕翻译任务）

```sql
CREATE TABLE IF NOT EXISTS translate_task (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    video_id INTEGER NOT NULL,
    source_lang TEXT,
    target_lang TEXT,
    status TEXT DEFAULT 'pending',         -- pending/done/failed
    source_srt_path TEXT,
    target_srt_path TEXT,
    error_message TEXT,
    create_ts INTEGER,
    update_ts INTEGER,
    FOREIGN KEY (video_id) REFERENCES video_info(id) ON DELETE CASCADE
);
```

### 4.3 关键 DB 操作（utils/db_manager.py）

| 函数 | 用途 |
|------|------|
| `insert_video()` | 写缓冲池，不落磁盘 |
| `get_undownloaded_videos()` | 捞未下载且未 broken 的视频 |
| `update_video_downloaded(id, path)` | 标记已下载 + 写路径 |
| `mark_video_broken(id, reason)` | 标记下载失败 |
| `is_video_broken(url)` | 检查 broken |
| `count_broken_videos()` | 统计 broken 数 |
| `get_buffer_pool().flush_now()` | 立即刷盘 |
| `_get_connection()` | 获取线程安全连接 |

**BufferPool 机制**：
- 线程安全：`threading.RLock()` 保护内部 list
- 自动刷盘：满 500 条或每 5 秒刷一次
- 调用方：程序退出前必须调 `flush_now()`，否则最后几条可能丢失

---

## 五、核心模块详解

### 5.1 PipelineRunner（core/pipeline.py）

**状态**：2025-08-13 重构完成，从 1162 → 704 行。

**删除的死代码**（从未被调用的旧串行路径）：
- `_clear_database()` — 被 `--reset-db` 参数替代
- `_download_videos()` — 旧串行下载，被 `run()` 内联 `_process_one` 替代
- `_get_video_folder_id()` — 辅助上述死代码
- `_process_subtitles()` — 旧串行字幕
- `_analyze_content()` — 旧串行分析
- `get_videos_with_downloaded_status()` — 从未导入

**保留的活跃方法**：
| 方法 | 被谁调用 |
|------|----------|
| `run()` | main.py / test |
| `run_async()` | GUI 调用 |
| `_crawl_videos()` | `run()` / `_collect_parallel_candidates()` |
| `_clear_undownloaded_records()` | `run()` |
| `_collect_parallel_candidates()` | `run()` |
| `_subtitle_single()` | `_process_one` |
| `_analyze_single()` | `_process_one` |
| `_cohesion_sort()` | `run()` |

### 5.2 Crawler（core/crawler.py）

**架构**：
```
YouTubeDataAPI v3  ──search_with_api()──▶ 语言过滤视频 ID
                                            ↓ 降级
热门页抓取         ──search_trending()──▶ 备用源
                                            ↓
curl_cffi 指纹池   ──10 个指纹轮换 ──▶ 视频详情页
                                            ↓
普通 requests 兜底 ──curl_cffi 全挂时自动启用
```

**curl_cffi 指纹池**（经 0.15.0 兼容性验证）：
```python
finger_pool = [
    "chrome131", "chrome124", "chrome120", "chrome116", "chrome110",
    "safari17_0", "safari15_5", "safari15_3",
    "edge101", "edge99",
]
# 轮换规则：同指纹两次调用间隔 ≥ 1.5s
# 自动剔除：请求失败 3 次后从池中移除
# 兜底：全部失败后回退普通 requests
```

**踩过的坑**：
- ❌ `safari17_4` / `safari17_5` — curl_cffi 0.15.0 不支持
- ❌ 直接用 requests 抓 YouTube 页面 — 被风控，需要 TLS 指纹
- ✅ 1.5s 间隔 + 指纹轮换 — 成功绕过风控

### 5.3 下载器（core/download.py）

**核心类**：`VideoDownloader`（单例）
- 底层用 `yt-dlp` 命令行或 Python API
- 下载完成后自动归档到 `output/{lang}/{category}/{video_id}/`
- `find_existing_video(youtube_id)` 检查文件是否已存在
- 并发通过 pipeline 的 ThreadPoolExecutor 控制，download.py 本身不做线程

### 5.4 字幕处理（core/subtitle_processor.py，⚠ 6244 行）

**两条路径**：

```
config.yaml:
  gemini.enabled: true
     ↓
     走 Gemini 全托管：
     extract_audio → Gemini ASR → Gemini 翻译 → Gemini 校对 → ffmpeg 烧录
     
  gemini.enabled: false
     ↓
     走本地管线：
     extract_audio → faster-whisper ASR → 本地/API 翻译 → ffmpeg 烧录
```

**关键函数**：`process_video_subtitle(video_id, video_path, language, category, source_lang, target_lang)`

**输出**：返回 `SubtitleResult(success, embedded_video_path, error_message)`，pipeline 用 `embedded_video_path` 更新数据库路径（从原 mp4 替换成烧录好的成品 mp4）。

### 5.5 内容标签（core/content_tag.py）

**v2 标签体系**（Rule-based 优先，LLM 增强）：

```python
tag_video(title, description, category, lang, yt_category_id, author, ...)
  ├── Rule-based classify → category（粗粒度 daily/tech/science/...）
  ├── Rule-based tag 匹配 → 关键词 + 频道 + 系列 ID
  └── if ai_writer.enabled:
      └── LLM tag_video() → sub_category + tags + series_id（降级链）

# LLM 降级链（智谱模型）：
_ZHIPU_DEGRADE_CHAIN = [
    "glm-4.7-flash", "glm-4-flash", "glm-4-air", "glm-4-plus", "glm-4.6-flash", "glm-4.5-flash"
]
# 每个模型内 3 次指数退避重试（1s → 2s → 4s）
# 全部失败则回退 rule-based 结果
```

### 5.6 video_analyzer.py（⚠ 5683 行巨型模块）

**功能**：对字幕内容进行深度分析，支持两种模式：

| 模式 | 输出 |
|------|------|
| ORAL_SPOKEN（口语学习） | 高频词、地道表达、常见搭配、场景拓展 |
| EXAM_PREP（应试学习） | 语法要点、长难句分析、考点归纳 |

**现状**：模块内混合了规则分析 + AI 增强 + 文件保存 + 多语言数据，5683 行确实过大，但当前跑通后暂不拆分，留给未来迭代。

### 5.7 social_media_formatter.py（3400 行）

**功能**：从分析结果 + 字幕 → 各平台风格文案。

**三种风格**：
- XIAOHONGSHU：标题党开头 + emoji + 口语表达深度解析（用 `expression_knowledge`）
- WEIBO：热点切入 + 核心观点
- ZHIHU：问题引入 + 结构化答案

### 5.8 utils/db_manager.py（1332 行）

**BufferPool 工作流**：
```
insert_video(source_url=..., title=..., ...)
  → get_buffer_pool().add("INSERT OR IGNORE INTO video_info ...", (url, title, ...))
  → BufferPool 内部 RLock.acquire()
  → self._buffer.append((sql, params))
  → if len(self._buffer) >= 500 or time since last flush > 5s:
        _flush_immediate()
        → yield_to_db()  # 批量 executemany + 单事务
```

**线程安全保证**：
- 所有对 `self._buffer` 的访问都在 `RLock` 内
- 后台刷盘线程（daemon）和主线程共享同一把锁
- `flush_now()` 在 finally 块中调用，保证程序退出前数据不丢

### 5.9 config.yaml 关键字段

```yaml
crawler:
  video_site: "youtube"         # 主爬虫源
  language: "en"                # 目标语言
  video_count: 10               # 每次爬取数量
  max_parallel: 4               # 流水线并发度
  enable_tls_finger: true       # curl_cffi 指纹轮换（生产必开）

download:
  yt_dlp_path: "bin/yt-dlp"
  ffmpeg_path: "bin/ffmpeg/ffmpeg.exe"
  output_dir: "output"

ai_writer:
  enabled: true                 # 开启后启用 LLM 标签和 AI 文案
  api_url: "https://open.bigmodel.cn/api/paas/v4/chat/completions"
  model: "glm-4.7-flash"

gemini:
  enabled: false                # 关闭时走本地 faster-whisper 管线
  model: "gemini-3.6-flash"
  api_key: "${GEMINI_API_KEY}"
```

---

### 5.10 utils/resource_locks.py（资源锁 + API 重试基础设施）

2026-08-13 新增，解决两类并发问题：

**FFmpeg 全局串行锁**：
```python
from utils.resource_locks import FFMPEG_LOCK

# 方式 A：with 语句（推荐）
with FFMPEG_LOCK:
    subprocess.run(["ffmpeg", "-i", video, ...])

# 方式 B：装饰器
@ffmpeg_guard
def burn_subtitle(...):
    subprocess.run(["ffmpeg", ...])
```
- 底层：`threading.Semaphore(1)`，同时只跑 1 个 ffmpeg subprocess
- 已加锁位置：`subtitle_processor.py` 中 **3 个重 CPU 调用**（字幕烧录 x264 编码 / 音频提取 / 内嵌字幕轨道提取）
- **不加锁**的轻量 ffprobe 只读调用不受影响
- 8 线程并发测试验证：最大并发 = 1 ✓

**API 统一重试**：
```python
from utils.resource_locks import api_retry, is_retryable_error

# 判断异常是否可重试
is_retryable_error(ConnectionError("reset"))  # → True
is_retryable_error(ValueError("bad json"))    # → False

# 装饰器自动重试
@api_retry(max_retries=3, name="content_tag")
def call_llm(...):
    requests.post(...)
```

**可重试错误关键词**（覆盖 HTTP + 连接级 + 系统级）：
```
HTTP 状态码: 503 500 429 502 UNAVAILABLE overloaded
连接级:     Server disconnected RemoteProtocolError ReadTimeout
            ConnectTimeout EOF occurred Connection reset Broken pipe
            RemoteDisconnected BadStatusLine
系统级:     ConnectionError TimeoutError OSError（异常类型本身）
```

**指数退避 + 抖动**：`backoff = min(2^(attempt-1), 16) + random(0, 1.5)`

**已应用到**：
| 模块 | 修复 |
|------|------|
| `gemini_engine.py` | transcribe + proofread 的可重试判断改用 `is_retryable_error()`；文件上传 `_prepare_input()` 新增 3 次重试 |
| `content_tag.py` | LLM 打标重试判断从硬编码关键词改为 `is_retryable_error()` |
| `subtitle_processor.py` | 3 个重 CPU ffmpeg 调用加 `with FFMPEG_LOCK:` |

---

## 六、已知问题与历史踩坑

### 6.1 curl_cffi 指纹兼容性（已修复）

| 指纹 | 状态 | 说明 |
|------|------|------|
| `safari17_4` | ❌ 不支持 | curl_cffi 0.15.0 报错 |
| `safari17_5` | ❌ 不支持 | 同上 |
| `safari17_0` | ✅ 可用 | 补充替换 |
| `safari15_3` | ✅ 可用 | 补充替换 |
| 全部 chrome* / edge* | ✅ 可用 | 无需改动 |

**修复**：更新指纹池 + 添加 `_ban_fingerprint()` 自动剔除 + 添加普通 requests 兜底。

### 6.2 LLM 429 Too Many Requests（已修复）

**根因**：glm-4-flash 的 RPM 限制被短时间连续请求打穿。

**修复**：
1. 模型降级链：`glm-4.7-flash → glm-4-flash → glm-4-air → glm-4-plus → glm-4.6-flash → glm-4.5-flash`
2. 每个模型内 3 次指数退避：1s → 2s → 4s
3. 全部失败回退 Rule-based 结果，不阻塞主流程

### 6.3 main.py `--all` 标志导致流水线执行 3 次（已修复）

**旧逻辑**：
```python
if args.all:
    args.crawl = True   # run_crawler() → run_pipeline()
    args.download = True # run_downloader() → run_pipeline()
    args.full = True    # run_full_pipeline() → run_pipeline()
    args.webui = True   # 旧版启动 WebUI（已移除）
```

**新逻辑**：移除 `--all / --crawl / --download / --webui`，只用 `--full`。新增 `--reset-db`。GUI 通过独立的 `start_gui.bat` 启动。

### 6.4 language_check.py BOM 编码问题（已修复）

Windows PowerShell 写入文件时自动加了 UTF-8 BOM，Python 3 解析时报 `invalid non-printable character U+FEFF`。已手动剥离 BOM。

**预防**：Windows 下用 `python -c` 写文件时用 `encoding='utf-8'`，不用 PowerShell Out-File。

### 6.5 字幕烧录后成品路径写回数据库（已修复）

**问题**：旧代码只更新了 download 阶段的本地路径，字幕烧录后（原 mp4 → 带字幕的 _已完成.mp4）数据库仍指向旧文件，用户在 GUI 看到的是无字幕版本。

**修复位置**：`pipeline.py` 的 `_subtitle_single()` → `update_video_downloaded(db_id, final_video)`。

---

### 6.6 Gemini `Server disconnected without sending a response` 连接级错误被跳过（已修复）

**现象（2026-08-13 生产日志）**：
```
[gemini-3.6-flash] API 失败 (retry 1/3): 503 UNAVAILABLE... — 2.5s 后重试
[gemini-3.6-flash] 全部重试失败 → 降级到下一个模型
transcribe_and_translate 失败: 文件上传失败: Server disconnected without sending a response.
transcribe_and_translate 失败: 文件上传失败: Server disconnected without sending a response.
```

**根因**：
1. **Bug A**：`gemini_engine.py` 的可重试判断只覆盖了 HTTP 状态码（503/500/429），但 `Server disconnected` 是 **连接级错误**（httpx.RemoteProtocolError），被跳过直接降级 → 下一个模型遇到同样的断连也直接死。
2. **Bug B**：文件上传 `_prepare_input()`（`client.files.upload`）**完全没有重试机制**，一次网络抖动就挂。
3. **并发放大器**：pipeline 并行度 4 时，多个视频同时上传大包给 Gemini，竞争代理/网络资源触发断连。

**修复**：
- 新增 `utils/resource_locks.py` 的 `is_retryable_error()` 统一判断（覆盖 HTTP + 连接级 + 系统级）
- `gemini_engine.py` 的 transcribe + proofread 改用 `is_retryable_error(e)`
- `_prepare_input()` 新增 3 次文件上传重试（指数退避 + 抖动）
- 同样修复 `content_tag.py` 的 LLM 打标重试判断

**修复位置**：
- `core/gemini_engine.py` → L27 import + L321/L435 retry 判断 + L525-547 `_prepare_input` 完整重写
- `core/content_tag.py` → L37 import + L488 retry 判断

### 6.7 多并发下多个 ffmpeg 同时跑导致 CPU 满载（已修复）

**问题**：pipeline 默认并发 4，每个视频的字幕烧录（x264 编码）是 CPU 杀手，4 个同时跑会把 CPU 打满到 100%×N 核，导致系统变慢甚至 ffmpeg 进程被 OOM kill。

**修复**：用 `threading.Semaphore(1)` 实现全局串行锁，3 个重 CPU ffmpeg 调用点全部加锁：
1. 字幕烧录 `subprocess.Popen(cmd, ...)` + `proc.communicate()` — **最关键**
2. 音频提取（ffmpeg → WAV）
3. 内嵌字幕轨道提取（ffmpeg → SRT）

轻量 ffprobe 只读调用（查询元数据、检测视频时长）不加锁，不受影响。

**修复位置**：`utils/resource_locks.py` 提供 `FFMPEG_LOCK`；`core/subtitle_processor.py` L1996 / L2923 / L5590 三处 `with FFMPEG_LOCK:`。

**验证**：8 线程并发测试 → 最大 ffmpeg 并发 = 1 ✓

---

## 七、维护时的高频操作速查

### 7.1 清理生产环境

```bash
# 清空视频文件 + 重置数据库
rm /data/downloads/* -rf
python -c "import sqlite3; c=sqlite3.connect('data/video_tasks.db'); c.executescript('DELETE FROM video_info; DELETE FROM translate_task;'); c.commit()"

# 或者用启动参数
python main.py --reset-db --full
```

### 7.2 查看运行日志

```bash
# 错误日志
Select-String logs/error.log -Pattern "ERROR|FAIL" | Select-Object -Last 50

# 爬虫日志统计
Select-String logs/crawler.log -Pattern "下载成功|下载失败|broken|字幕.*失败" | Group-Object | Select-Object Name, Count
```

### 7.3 数据库直接查询

```bash
python -c "
import sqlite3
c = sqlite3.connect('data/video_tasks.db')
c.row_factory = sqlite3.Row

# 查重测试
c.execute('SELECT COUNT(*) FROM video_info')
print('总记录:', c.fetchone()[0])

c.execute('SELECT COUNT(*) FROM video_info WHERE is_downloaded=1')
print('已下载:', c.fetchone()[0])

c.execute('SELECT COUNT(*) FROM video_info WHERE is_broken=1')
print('broken:', c.fetchone()[0])

# 语言分布
for row in c.execute('SELECT lang, COUNT(*) FROM video_info GROUP BY lang'):
    print(row)
"
```

### 7.4 验证单模块能导入

```bash
python -c "
import importlib
for m in ['main','core.pipeline','core.crawler','core.download','core.subtitle_processor',
          'core.video_analyzer','core.content_tag','core.classify','core.task_scheduler',
          'core.gemini_engine','utils.db_manager']:
    importlib.import_module(m)
    print(f'✓ {m}')
"
```

### 7.5 验证 DB BufferPool 正常

```bash
python -c "
from utils.db_manager import init_buffer_pool, get_buffer_pool, _get_connection
init_buffer_pool()
get_buffer_pool().flush_now()

# 简单写入测试
from utils.db_manager import insert_video
ok = insert_video(
    source_url='https://test.example.com/watch?v=test1234',
    title='test', description='test', lang='en', category='daily',
    duration='60', author='test', views=0,
)
get_buffer_pool().flush_now()

c = _get_connection()
row = c.execute('SELECT * FROM video_info WHERE source_url=?', ('https://test.example.com/watch?v=test1234',)).fetchone()
print('写入 OK:', row is not None)

# 清理测试数据
c.execute('DELETE FROM video_info WHERE source_url LIKE \"%test.example.com%\"')
c.commit()
print('清理完成')
"
```

---

## 八、代码质量审计结果（2025-08-13）

### 8.1 已修复项

| 文件 | 修复 |
|------|------|
| `core/pipeline.py` | 删除 4 个从未被调用的旧串行方法 + 1 个死函数 + 清理无用 import，1162→704 行 |
| `core/pipeline.py` | 提取 youtube_id 解析为模块级 helper `_extract_youtube_id`，消除 3 处重复 regex |
| `core/pipeline.py` | import 替换 `get_download_pool` → `VideoDownloader`（旧接口是死代码依赖） |
| `main.py` | 修复 `--all` 导致流水线执行 3 次的严重 bug，新增 `--reset-db` |
| `utils/language_check.py` | 剥离 UTF-8 BOM 防止 Python 解析报错 |

### 8.2 确认不是死代码的模块

| 模块 | 调用方 |
|------|--------|
| `core/classify.py` | `core/spiders/youtube_spider.py:55` |
| `core/expression_knowledge.py` | `core/social_media_formatter.py:25` |
| `core/task_scheduler.py` | `utils/app_initializer.py:21`, `main.py:71` |
| `core/crawler.py` | `core/pipeline.py`（create_spider 工厂返回实例） |

### 8.3 已知待优化项（暂不改动，留给未来迭代）

| 文件 | 问题 | 影响 |
|------|------|------|
| `core/subtitle_processor.py`（6244 行） | 承担了 ASR / 翻译 / 烧录三条管道的全部逻辑 | 维护困难，但当前跑通，拆分风险高 |
| `core/video_analyzer.py`（5683 行） | 混合了规则分析 + AI 增强 + 多语言数据 + 文件保存 | 同上 |
| `core/social_media_formatter.py`（3400 行） | 3 种风格 × 多种分析模式，内部有重复模板逻辑 | 同上 |
| `config_loader.py` | 无配置热重载能力，改 config.yaml 必须重启 | 低 |
| `download.py` | 当前由 pipeline 控制并发，自身无线程安全 | 合理设计 |
| 测试脚本 | 根目录有 8 个 test_*.py 和 demo_crawler.py，非 pytest 框架 | 可用但不规范 |

### 8.4 import 验证结果（23/24 通过）

```
✓ main
✓ core.pipeline       ← 重构后验证通过
✓ core.crawler
✓ core.download
✓ core.subtitle_processor
✓ core.video_analyzer
✓ core.social_media_formatter
✓ core.content_tag
✓ core.classify
✓ core.task_scheduler
✓ core.gemini_engine
✓ core.translation_engine
✓ core.ai_writer
✓ core.spiders.youtube_spider
✓ utils.db_manager
✓ utils.config_loader
✓ utils.path_helper
✓ utils.enums
✓ utils.logger
✓ utils.file_sort
✓ utils.srt_parser
✓ utils.app_initializer
✓ utils.language_check   ← BOM 修复后通过
```

> 注：GUI 层（gui/ 目录）依赖 PySide6，不在 main.py 的 import 链中，由 `start_gui.bat` 独立启动。

---

## 九、生产环境运维 SOP

### 9.1 首次部署

```bash
# 1. 拉代码
git clone ... && cd Vc

# 2. 安装依赖
pip install -r requirements-runtime.txt

# 3. 放好 FFmpeg
#    方法 A：bin/ffmpeg/ffmpeg.exe（推荐，已在仓库中）
#    方法 B：系统 PATH 中安装 ffmpeg

# 4. 放好 ASR 模型
python scripts/download_asr_model.py

# 5. 配置 API Key
python scripts/save_youtube_api_key.py

# 6. 改 config.yaml（language / max_parallel / output_dir 等）

# 7. 初始化 + 启动
python main.py --reset-db --full
# 桌面 GUI：双击 start_gui.bat
```

### 9.2 日常巡检 Checklist

- [ ] **磁盘空间**：output/ 目录下 mp4 文件增长速度，定期归档旧视频
- [ ] **broken 计数**：`SELECT COUNT(*) FROM video_info WHERE is_broken=1`，过多说明爬虫策略需调整
- [ ] **API 配额**：YouTube Data API v3 每日 10000 单位，监控用量
- [ ] **LLM 调用日志**：429 错误率是否过高
- [ ] **字幕烧录成功率**：`subtitled / downloaded` 比例，低于 50% 说明需要排查 audio 提取

### 9.3 常见故障排查

| 现象 | 可能原因 | 排查命令 |
|------|----------|----------|
| `AttributeError: module 'curl_cffi' has no attribute 'impersonate'` | curl_cffi 版本不匹配 | `pip show curl-cffi` → 应为 0.15.0 |
| 所有视频 download 阶段都失败 | yt-dlp 版本过旧 / 网络 | `yt-dlp --version`；单独命令行测试下载 |
| LLM 标签全部失败回退 rule-based | 智谱 API Key 失效 / 429 | 查 error.log 最后 50 行 |
| 字幕处理无报错但产出的 mp4 没字幕 | 烧录路径没写回 DB | `SELECT local_video_path FROM video_info WHERE is_downloaded=1 ORDER BY id DESC LIMIT 3` |
| BufferPool 刷盘失败 | SQLite 锁被占用（多进程） | 确保只有一个 pipeline 进程运行 |

---

## 十、未来迭代建议

1. **拆分巨型模块**：subtitle_processor / video_analyzer / social_media_formatter 各 3000-6000 行，可拆成子模块（ASR / translation / burning / rules / templates / data 分离），但当前稳定运行，建议先跑 2 周生产再动刀。

2. **config.yaml 热重载**：当前改配置必须重启。可加 `watchdog` 监听 + 各模块 config 读取时检查 hash 变化。

3. **测试框架升级**：根目录 8 个 test_*.py 是非标准脚本，建议迁移到 `tests/` + pytest + fixtures。

4. **断点续爬**：pipeline 中间崩溃后，当前依赖 `is_downloaded / is_broken` 状态恢复。可加一个 `pipeline_status.json` 标记当前阶段，重启后从断点继续。

5. **多源并行**：当前 spiders/ 已有 bilibili / tiktok / vimeo / dailymotion 骨架，可配置化启用多源并行爬取 + 统一去重。

6. **监控面板**：GUI 可加 broken 趋势图、API 配额用量、LLM 降级次数统计。

---

> **给新对话的开发者**：开启新对话时，把本文件路径和 `utils/db_manager.py` + `core/pipeline.py` 的内容粘贴给 AI，可以跳过上下文压缩直接进入开发状态。
