# VideoCrawler 架构与代码审核历史档案

本档案由定时任务「每日架构代码审核」（每天 08:00）自动维护，累计记录每次审核已提出的全部优化点，用于**跨日去重**：后续审核只允许报告本档案中未出现过的新优化点。

## 编号规则

- 新优化点编号：`AUDIT-0001` 起，按提出顺序递增，不复用、不重排。
- 状态：`待处理` / `处理中` / `已修复` / `已确认不处理` / `转需求`。

## 已提出优化点总表

| 编号 | 提出日期 | 标题 | 涉及文件 | 严重程度 | 状态 |
|------|----------|------|----------|----------|------|
| AUDIT-0001 | 2026-10-08 | config.yaml 含明文 API Key 与云厂商凭据且被 git 跟踪 | config.yaml:21,64,101-102,110-111,127,141,153,165,177（10-23 已移出 git 跟踪、.gitignore:94 覆盖；磁盘明文仍在，云轮换+build_gui.bat:83 拷贝未做） | 高 | 处理中 |
| AUDIT-0002 | 2026-10-08 | crypto_util 密钥由机器名+硬编码 salt 派生，属混淆非加密 | utils/crypto_util.py:61-91（随机 salt `.crypto_salt`） | 高 | 已修复 |
| AUDIT-0003 | 2026-10-08 | SQLite 无 WAL checkpoint，内存缓冲池丢数据/读写不一致 | utils/db_manager.py:321,486（实测 WAL 已→0） | 高 | 已修复 |
| AUDIT-0004 | 2026-10-08 | git 跟踪错位：成品/第三方入库、第一方新代码未跟踪 | 989cb02 已移出 output/bin/tools/models/data/config.yaml（索引清零）；.gitignore:41,79-80,83,94 覆盖完整 | 高 | 已修复 |
| AUDIT-0005 | 2026-10-08 | 硬编码开发者本机 Node 路径，换机即失效 | path_helper.get_node_path；download.py:706-711；youtube_spider.py:129-134 | 高 | 已修复 |
| AUDIT-0006 | 2026-10-08 | curl_cffi→requests 兜底条件写反，异常路径不触发 | core/crawler.py:210-221 | 高 | 已修复 |
| AUDIT-0007 | 2026-10-08 | Pipeline ThreadPoolExecutor 异常路径不 shutdown | core/pipeline.py:649-657（finally shutdown） | 高 | 已修复 |
| AUDIT-0008 | 2026-10-08 | playwright 浏览器/上下文在 do_upload 异常路径不关闭 | core/publish/playwright_base.py:171-215 | 高 | 已修复 |
| AUDIT-0009 | 2026-10-08 | ai_writer 守卫误杀 Groq 梯队，文案静默返回空 | core/ai_writer.py:262 | 高 | 已修复 |
| AUDIT-0010 | 2026-10-08 | page_publish 工作线程直接操作 UI 并弹模态框 | gui/pages/page_publish.py:49-54 | 高 | 已修复 |
| AUDIT-0011 | 2026-10-08 | MainWindow 无 closeEvent，关窗时进程/线程不清理 | gui/main_window.py:486-516 | 高 | 已修复 |
| AUDIT-0012 | 2026-10-08 | Web API Key 走 URL query 且明文入日志，叠加隧道暴露 | web/main.py:44,173,286-313；health 已脱敏（_mask_key，10-23）；/api/stop cancel 未做（PipelineRunner 无取消入口） | 高 | 处理中 |
| AUDIT-0013 | 2026-10-08 | video_analyzer 5683 行：单方法硬编码约 3800 行语言数据 | core/video_analyzer.py（10-19 实测 5604 行，数据未外移） | 高 | 待处理 |
| AUDIT-0014 | 2026-10-08 | social_media_formatter 3400 行：语言数据重复且分叉 | core/social_media_formatter.py（10-19 实测 3376 行） | 高 | 待处理 |
| AUDIT-0015 | 2026-10-08 | gemini_engine 2166 行：单类承担 5 种无关职责 | core/gemini/；旧 gemini_engine.py 为 308 行门面 | 高 | 已修复 |
| AUDIT-0016 | 2026-10-08 | subtitle_processor 4096 行：8 类职责混装 | core/subtitles/；旧 subtitle_processor.py 为 29 行 shim | 高 | 已修复 |
| AUDIT-0017 | 2026-10-08 | PipelineRunner._running 检查置位无锁，并发双跑 | core/pipeline.py:142,489-495 | 中 | 已修复 |
| AUDIT-0018 | 2026-10-08 | 下载临时目录异常残留，重试复用陈旧文件 | download.py:833,963,977-980（finally 清理已落地，10-23） | 中 | 已修复 |
| AUDIT-0019 | 2026-10-08 | DownloadPool._threads 列表无锁读写 | download.py:1072-1085（闸门持锁原子化，start 出锁后，10-23） | 中 | 已修复 |
| AUDIT-0020 | 2026-10-08 | ResultBuffer 无锁，临时 JSON 读后不删 | core/crawler.py:415,508-548 | 中 | 已修复 |
| AUDIT-0021 | 2026-10-08 | CDP cookies 文件被多线程并发覆写 | core/cdp_cookies.py:22,223-250 | 中 | 已修复 |
| AUDIT-0022 | 2026-10-08 | Vimeo/Dailymotion 绕过指纹引擎且 search 互相复制 | vimeo_spider.py:79；dailymotion_spider.py:75 | 中 | 已修复 |
| AUDIT-0023 | 2026-10-08 | Pipeline 调用仅 YoutubeSpider 拥有的方法，跨平台 AttributeError | core/pipeline.py:195,217 | 中 | 已修复 |
| AUDIT-0024 | 2026-10-08 | TaskQueue 状态机完整但未被生产管线接线 | utils/queue_manager.py:12-15（已标注预留） | 中 | 已确认不处理 |
| AUDIT-0025 | 2026-10-08 | publish cookie 解析三处重复实现 | _cookie_utils 已收口；biliup_runtime.py:126-141 仍自带 | 中 | 处理中 |
| AUDIT-0026 | 2026-10-08 | 三平台 Client upload_video 包装逐行相同 | core/publish/clients.py:259-275,375-391 | 中 | 待处理 |
| AUDIT-0027 | 2026-10-08 | 三个 Playwright uploader 的 do_upload 流程同构 | core/publish/playwright_base.py:254-327 | 中 | 已修复 |
| AUDIT-0028 | 2026-10-08 | SpeechRecognizer._get_video_duration 同类内重复定义 | core/subtitles/asr.py:1211（仅 1 份） | 中 | 已修复 |
| AUDIT-0029 | 2026-10-08 | classify 缓存键重复且每次兜底新建 RuleBasedClassifier | core/classify.py:28-35（单例；缓存键/TTL 仍未收口） | 中 | 处理中 |
| AUDIT-0030 | 2026-10-08 | subtitle_render Popen 无超时、异常不 kill 子进程 | subtitle_render.py:489-519（daemon 线程+队列轮询、deadline 到点 kill 抛 TimeoutExpired，10-23） | 中 | 已修复 |
| AUDIT-0031 | 2026-10-08 | model_registry GUI 耦合，运行时与注册表双数据源 | core/model_registry.py:25-47（Qt lazy；运行时仍直读 config） | 中 | 处理中 |
| AUDIT-0032 | 2026-10-08 | page_download 封面管线在 worker 线程直接 setText | gui/pages/page_download.py:51-52 | 中 | 已修复 |
| AUDIT-0033 | 2026-10-08 | TaskManager.register_thread 形同虚设，force_stop 失效 | utils/thread_spawn.py；TaskManager.spawn 零调用 | 中 | 处理中 |
| AUDIT-0034 | 2026-10-08 | GUI 自动流水线与 Web 流水线两套编排并存 | gui/auto_pipeline.py:182-254；web/main.py:400,445 | 中 | 待处理 |
| AUDIT-0035 | 2026-10-08 | page_download 为 1246 行 God Class、11 项职责 | gui/pages/page_download.py（10-19 实测 1115 行，未拆类） | 中 | 待处理 |
| AUDIT-0036 | 2026-10-08 | log_bridge 同步 sink + 裸 except 吞日志 | gui/log_bridge.py:57（enqueue=True） | 中 | 已修复 |
| AUDIT-0037 | 2026-10-08 | config.yaml 职责臃肿，加载无校验、默认模板脱节 | config.yaml（仍 819 行）；config_loader.py:16-119 | 中 | 待处理 |
| AUDIT-0038 | 2026-10-08 | 依赖未锁版本，发行包打进约 927MB 模型与明文配置 | requirements-runtime.txt:9-34；build_gui.bat:78,83 | 中 | 待处理 |
| AUDIT-0039 | 2026-10-08 | db_manager 职责过载、同义重复 CRUD，3 表无访问层 | utils/db/video_repo.py、task_repo.py；db_manager 554 行 | 中 | 已修复 |
| AUDIT-0040 | 2026-10-08 | 分层倒置：utils 反向 import core，函数内延迟导入绕环 | app/bootstrap.py；app_initializer 为 9 行 shim | 中 | 已修复 |
| AUDIT-0041 | 2026-10-08 | tests/ 目录为空，实际零自动化测试 | tests/（仍为空） | 中 | 待处理 |
| AUDIT-0042 | 2026-10-08 | data/browser_cookies.txt 未被 .gitignore 覆盖 | .gitignore:69-70 | 中 | 已修复 |
| AUDIT-0043 | 2026-10-08 | CDP WebSocket 握手失败时 socket 句柄泄漏 | core/cdp_cookies.py:97-103 | 低 | 已修复 |
| AUDIT-0044 | 2026-10-08 | TaskScheduler 任务 ID 秒级时间戳冲突 | task_scheduler.py:349,360（replace_existing=True，10-23） | 低 | 已修复 |
| AUDIT-0045 | 2026-10-08 | yt-dlp http_headers 探针块复制 4 份 | utils/ytdlp_common.py（YTDLP_YOUTUBE_HEADERS 收口） | 低 | 已修复 |
| AUDIT-0046 | 2026-10-08 | except Exception: pass 聚集，异常被静默吞掉 | core/download.py:210 等约 9 处；youtube_spider 3 处 | 低 | 待处理 |
| AUDIT-0047 | 2026-10-08 | 超长函数清单 | download.py（_do_download 约 340 行）/youtube_spider.py/pipeline.py（未拆） | 低 | 待处理 |
| AUDIT-0048 | 2026-10-08 | 爬虫管线低风险观察（含待核实项） | pipeline.py:505（crawled 修复）；youtube_spider.py:91 _probe_cache_max=1024 已修（10-23）；去重仍仅 YouTube | 低 | 处理中 |
| AUDIT-0049 | 2026-10-08 | ai_writer/social_media_formatter 死代码 | core/ai_writer.py:928-946（保留待恢复） | 低 | 待处理 |
| AUDIT-0050 | 2026-10-08 | lang_names 重复 4 次；playwright domain 死代码 | ai_writer.py:36-41（LANG_NAMES）；playwright_base.py:84 | 低 | 处理中 |
| AUDIT-0051 | 2026-10-08 | YouTube URL 拼接与 _log 桥接重复 | utils/youtube_url.py（收口；_parse_video_id/_log 仍在） | 低 | 处理中 |
| AUDIT-0052 | 2026-10-08 | web/index.html innerHTML 拼接文件名存在 XSS 面 | index.html:653（esc 已加；作用域见 0065） | 低 | 已修复 |
| AUDIT-0053 | 2026-10-08 | web/ 目录隧道产物与二进制应清理 | cloudflared.exe 已删除（10-19）；lt.out/lt.err/tunnel.*/watchdog.log 已删（10-23） | 低 | 已修复 |
| AUDIT-0054 | 2026-10-08 | 根目录（Vc 上一级）卫生 | 父目录新增 _diag_gemini_api/_diag_proxy/_diag_vpn/_remote_diag 4 脚本；Vc 根新增 _test_mqtt.py | 低 | 处理中 |
| AUDIT-0055 | 2026-10-08 | .gitignore 编码与覆盖缺口及打包观察 | .gitignore（无 BOM）；build_gui.bat:22 | 低 | 处理中 |
| AUDIT-0056 | 2026-10-09 | subtitles/processor.py 缺 embedder/quality_gate import，NameError | core/subtitles/processor.py:33-35（import）、:55-56（实例化） | 高 | 已修复 |
| AUDIT-0057 | 2026-10-09 | 内嵌 Web 与独立 watchdog 生命周期冲突 | web/watchdog.py 已删除（10-19 确认）；遗留启动脚本见 0079 | 高 | 已确认不处理 |
| AUDIT-0058 | 2026-10-09 | 硬编码弱默认密钥 VideoCrawler2026 + 绑 0.0.0.0 | gui/web_host.py:37-46（token_urlsafe(24) 随机）、:172（默认 127.0.0.1+VC_WEB_HOST） | 高 | 已修复 |
| AUDIT-0059 | 2026-10-09 | video_repo/task_repo 缺 import os/time | video_repo.py:8-9（import）、:215,:458；task_repo.py:7、:178 | 高 | 已修复 |
| AUDIT-0060 | 2026-10-09 | 烧录 deadline 被 stderr 阻塞读架空 | subtitle_render.py:489-519（daemon 线程轮询，同 0030，10-23） | 中 | 已修复 |
| AUDIT-0061 | 2026-10-09 | 磁盘去重用 __file__ 拼 output 路径 | core/pipeline.py:163（get_output_dir，10-23） | 中 | 已修复 |
| AUDIT-0062 | 2026-10-09 | publish_queue 定时任务阻塞立即任务 | core/publish/publish_queue.py:173-203（跳过扫描，10-23） | 中 | 已修复 |
| AUDIT-0063 | 2026-10-09 | xhs_api_client 顶层硬依赖可选包 xhs_cli | core/publish/xhs_api_client.py:38-57（try/except 懒加载+_ensure_xhs_cli，10-23） | 中 | 已修复 |
| AUDIT-0064 | 2026-10-09 | /api/server/restart 内嵌模式 os._exit 杀 GUI、缺 import sys | web/main.py:15（import sys）、:636-642（restart 改 503，10-23） | 中 | 已修复 |
| AUDIT-0065 | 2026-10-09 | index.html esc 声明在 loadVideos 局部，发布 Tab ReferenceError | web/static/index.html:445-447（esc 提层）、:659-660,692-723,739,885-889 | 中 | 已修复 |
| AUDIT-0066 | 2026-10-09 | 诊断脚本散落 Vc 根目录未 gitignore | _diag_xhs*.py、_fix_cookies.py、_show_diag.py 等 7 个已随 989cb02 入库（见 0091，10-23 形态变化） | 中 | 处理中 |
| AUDIT-0067 | 2026-10-09 | publish storage 与 apsw 主库双轨、无 WAL/busy_timeout | core/publish/storage.py:28-29（WAL+busy_timeout=5000，10-23） | 中 | 已修复 |
| AUDIT-0068 | 2026-10-09 | CDP HTTPConnection 异常路径不 close | core/cdp_cookies.py:148-155（try/finally）、:207-211（WebSocket close） | 低 | 已修复 |
| AUDIT-0069 | 2026-10-09 | subtitles 各模块重复文件头/unused import | core/subtitles/models.py:1-13（文件头合并、删 10 个 unused import，10-23） | 低 | 已修复 |
| AUDIT-0070 | 2026-10-09 | @dataclass 装饰器悬空 | embedder.py:33、processor.py:40（悬空 @dataclass 已删，10-23） | 低 | 已修复 |
| AUDIT-0071 | 2026-10-09 | gemini mixin 依赖主类 _model_chain 无接口约束 | core/gemini/_asr_mixin.py:56,73,225,246 | 低 | 待处理 |
| AUDIT-0072 | 2026-10-09 | watchdog 通配 CORS | web/watchdog.py 已删除（10-19 确认） | 低 | 已确认不处理 |
| AUDIT-0073 | 2026-10-09 | MQTT token 随每条消息明文广播 | web/mqtt_bridge.py:343-357 | 低 | 待处理 |
| AUDIT-0074 | 2026-10-09 | tunnel reader 线程边界挂起 | web_host.py tunnel 代码已整段移除（10-19 确认） | 低 | 已确认不处理 |
| AUDIT-0075 | 2026-10-09 | SQLStatements 留在 db_manager 致循环依赖 | db_manager.py:33 类仍在；repos 已延迟 import（10-19 确认循环已解） | 低 | 处理中 |
| AUDIT-0076 | 2026-10-09 | build_gui.spec 未覆盖 app/ | build_gui.spec:20,49 | 低 | 待处理 |
| AUDIT-0077 | 2026-10-19 | PermanentDownloadError 定义后从未 raise，永久失败仍重试 | core/download.py:35（定义）、:890-892（raise）、:905/:923（permanent=True，10-23 重新应用） | 中 | 已修复 |
| AUDIT-0078 | 2026-10-19 | image_provider call_pollinations 文生图伪装图生图、输出错误封面 | core/image_provider.py:330-336,385-389 | 中 | 已修复 |
| AUDIT-0079 | 2026-10-19 | 启动脚本悬空引用已删 watchdog/cloudflared，独立部署路径坏 | start_all.bat；start_tunnel.bat；web/wake.html | 中 | 已修复 |
| AUDIT-0080 | 2026-10-19 | _test_mqtt.py 硬编码弱密钥 VideoCrawler2026 散落根目录 | scripts/test_mqtt.py（原 _test_mqtt.py 已移动）:5-12 | 中 | 已修复 |
| AUDIT-0081 | 2026-10-19 | image_provider _download_image 递归无深度限制 | core/image_provider.py:104-140 | 低 | 已修复 |
| AUDIT-0082 | 2026-10-19 | freeai provider id 字符串集合两处重复维护 | core/image_provider.py:38,51,406 | 低 | 已修复 |
| AUDIT-0083 | 2026-10-19 | subtitle_render 10-14 重写残留重复模块头/import | core/subtitle_render.py:1-26 | 低 | 已修复 |
| AUDIT-0084 | 2026-10-19 | download_video 跨类访问 FileSorter 私有 _output_dir | download.py:531（get_output_root，10-23 重新应用）；file_sort.py:48-53 | 低 | 已修复 |
| AUDIT-0085 | 2026-10-19 | _do_download 每轮重试双发 extract_info，放大限流 | download.py:583（prefetch_cache）、:661-662（命中复用）、:668-669（成功才写，10-23 重新应用） | 低 | 已修复 |
| AUDIT-0086 | 2026-10-19 | mobile.html 队列池/错误信息 innerHTML 未走 esc | web/static/mobile.html:401,406,475 | 低 | 已修复 |
| AUDIT-0087 | 2026-10-21 | 5 个第一方文件被写入双重 UTF-8 BOM（EF BB BF EF BB BF），py_compile 失败、无法导入 | web/main.py；core/spiders/youtube_spider.py；core/classify.py；core/cdp_cookies.py；core/publish/storage.py（10-23 BOM 剥离、py_compile 全过） | 高 | 已修复 |
| AUDIT-0088 | 2026-10-21 | 外部批量写入覆盖工作区，download.py 被整体还原到 10-19 修复前（0077/0085/0084 回退），需先定位覆盖源 | core/download.py（10-23 三处修复重新应用并验证；覆盖源未定位但未再复现） | 中 | 已修复 |
| AUDIT-0089 | 2026-10-23 | GitHub 远端 URL 内嵌明文 PAT（ghp_ 前缀）于 .git/config，随仓库泄露 | .git/config:12（origin URL 含 ghp_SP****（已脱敏，待轮换））；修改记录待办 1 | 高 | 待处理 |
| AUDIT-0090 | 2026-10-23 | Web API key 无持久化：随机生成不落盘，每次重启 GUI 即更换，手机端书签/二维码失效 | gui/web_host.py:41-46,206；web/main.py:45 | 中 | 待处理 |
| AUDIT-0091 | 2026-10-23 | 989cb02 将 7 个诊断脚本/产物提交入库（_diag_xhs*.py、_fix_cookies.py、_show_diag.py、_diag_result.json、_diag_screenshot.png） | Vc 根目录（git show 989cb02 确认）；0066 形态变化 | 中 | 待处理 |
| AUDIT-0092 | 2026-10-26 | build_gui.spec 未覆盖 web/，且 excludes 明确排除 uvicorn/fastapi/starlette——打包后内嵌 Web/MQTT 远程功能缺失 | build_gui.spec:20,49,92-95；gui/web_host.py:222,350；gui/main_window.py:323,355；web/static/ | 中 | 待处理 |
| AUDIT-0093 | 2026-10-26 | task_scheduler.py 顶层 import psutil 未声明，干净环境 import 即 ModuleNotFoundError | core/task_scheduler.py:20；requirements-runtime.txt（无 psutil） | 中 | 待处理 |
| AUDIT-0094 | 2026-10-26 | httpx 已用未声明：xhs_api_client.py:34 顶层 import（0063 懒加载未覆盖）、gemini_engine.py:326,392 惰性 import | core/publish/xhs_api_client.py:34；core/gemini_engine.py:326,392；requirements-runtime.txt | 低 | 待处理 |
| AUDIT-0095 | 2026-10-26 | README 与代码脱节：入口写 main.py 实为 main_gui.py、web 远程功能未文档化、目录树过时、PyInstaller/Nuitka 自相矛盾、Python 3.11+ vs 3.14 | README.md:20,29,35-85,271,78 | 低 | 待处理 |

## 明细记录

<!-- 每次审核在下方追加新条目，格式：
### AUDIT-XXXX（YYYY-MM-DD）标题
- 涉及文件：
- 严重程度：高/中/低
- 问题：
- 建议：
- 状态：待处理
- 来源报告：audit_YYYYMMDD.md
-->

---

## 2026-10-08 首次基线审核明细（来源：audit_20261008.md）

### AUDIT-0001（2026-10-08）config.yaml 含明文 API Key 与云厂商凭据且被 git 跟踪
- 涉及文件：config.yaml:21,64,101-102,110-111,127,141,153,165,177
- 严重程度：高
- 问题：git 跟踪的 config.yaml 中明文写入 Gemini/GLM/Groq/free.ai Key 及火山、腾讯云 AK/SK，并在 providers 段重复。
- 建议：立即作废并轮换全部 Key，迁入 api_secret.yaml.enc，config.yaml 改模板并移出 git，必要时清理历史。
- 状态：待处理
- 来源报告：audit_20261008.md

### AUDIT-0002（2026-10-08）crypto_util 密钥由机器名+硬编码 salt 派生
- 涉及文件：utils/crypto_util.py:54-68
- 严重程度：高
- 问题：主密钥由机器名+用户目录经 sha256 派生、salt 硬编码，异常分支随机生成新密钥；属混淆非加密。
- 建议：随机 salt 落本地受保护文件或改用用户口令派生；禁止异常分支静默生成密钥。
- 状态：待处理
- 来源报告：audit_20261008.md

### AUDIT-0003（2026-10-08）SQLite 无 WAL checkpoint、缓冲池丢数据/读写不一致
- 涉及文件：utils/db_manager.py:193-391
- 严重程度：高
- 问题：无 wal_checkpoint/autocheckpoint（WAL 已 2.17MB、主库 15 倍）；内存缓冲定时刷盘，崩溃丢数据、部分读路径不 flush。
- 建议：配置 autocheckpoint，shutdown 时 checkpoint(TRUNCATE)，强一致读先 flush。
- 状态：待处理
- 来源报告：audit_20261008.md

### AUDIT-0004（2026-10-08）git 跟踪错位
- 涉及文件：.gitignore; git index（output 37 文件、bin/ffmpeg* 84 文件）
- 严重程度：高
- 问题：成品与第三方 ffmpeg 入库，而 gui/web/core.publish/pipeline 等新代码未跟踪。
- 建议：git rm --cached 成品与陈旧 ffmpeg，补 .gitignore，正式提交第一方新代码。
- 状态：待处理
- 来源报告：audit_20261008.md

### AUDIT-0005（2026-10-08）硬编码开发者本机 Node 路径
- 涉及文件：core/download.py:726; core/spiders/youtube_spider.py:137
- 严重程度：高
- 问题：node 探测兜底写死 C:\Users\cjl\... 路径，换机即 None、YouTube 解析静默降级。
- 建议：改为配置项或由 path_helper/环境变量解析。
- 状态：待处理
- 来源报告：audit_20261008.md

### AUDIT-0006（2026-10-08）curl_cffi→requests 兜底条件写反
- 涉及文件：core/crawler.py:200-218
- 严重程度：高
- 问题：兜底条件 last_exception is None，而真正失败时该值非 None，降级永不触发。
- 建议：重试耗尽即降级，去掉 is None 条件。
- 状态：待处理
- 来源报告：audit_20261008.md

### AUDIT-0007（2026-10-08）ThreadPoolExecutor 异常路径不 shutdown
- 涉及文件：core/pipeline.py:512-635
- 严重程度：高
- 问题：shutdown 仅在正常路径，异常时非守护 worker 线程挂住进程退出。
- 建议：用 with 包裹或 finally 中 shutdown(cancel_futures=True)。
- 状态：待处理
- 来源报告：audit_20261008.md

### AUDIT-0008（2026-10-08）playwright 浏览器异常路径不关闭
- 涉及文件：core/publish/playwright_base.py:122-152
- 严重程度：高
- 问题：context/browser.close 在 do_upload 之后、finally 之外，异常即跳过、浏览器进程残留。
- 建议：用 try/finally 或 async with 管理 browser/context。
- 状态：待处理
- 来源报告：audit_20261008.md

### AUDIT-0009（2026-10-08）ai_writer 守卫误杀 Groq 梯队
- 涉及文件：core/ai_writer.py:255-257,872
- 严重程度：高
- 问题：守卫用 GLM 开关，只配 Groq 时函数提前返回空、无报错。
- 建议：守卫改为任一梯队可用即继续（groq_enabled or GLM）。
- 状态：待处理
- 来源报告：audit_20261008.md

### AUDIT-0010（2026-10-08）page_publish 工作线程直接操作 UI/弹模态
- 涉及文件：gui/pages/page_publish.py:641-666
- 严重程度：高
- 问题：worker 线程直接 setValue/setText 并弹 QMessageBox，不走信号槽。
- 建议：worker 只 emit 信号，UI 操作移到主线程槽。
- 状态：待处理
- 来源报告：audit_20261008.md

### AUDIT-0011（2026-10-08）MainWindow 无 closeEvent
- 涉及文件：gui/main_window.py; page_subtitle.py:402; auto_pipeline.py:155-162
- 严重程度：高
- 问题：关窗无清理钩子，子进程/daemon 线程残留、资源锁不释放。
- 建议：重写 closeEvent，stop 线程、terminate 子进程后 accept。
- 状态：待处理
- 来源报告：audit_20261008.md

### AUDIT-0012（2026-10-08）Web API Key 走 query 且明文入日志
- 涉及文件：web/main.py:41,170,367-369; web/static/index.html; web/lt.out
- 严重程度：高
- 问题：Key 在 URL/日志/历史/Referer 暴露，绑定 0.0.0.0 且残留 localtunnel 地址；/api/stop 无 cancel。
- 建议：改用 Bearer 头、日志打码、清理隧道产物、增加 cancel flag。
- 状态：待处理
- 来源报告：audit_20261008.md

### AUDIT-0013（2026-10-08）video_analyzer 5683 行
- 涉及文件：core/video_analyzer.py:111-3918
- 严重程度：高
- 问题：_init_language_data 单方法硬编码约 3800 行数据，文件 5683 行。
- 建议：数据抽到 language_data 独立模块，文件按职责拆为 video_analyzer 包。
- 状态：待处理
- 来源报告：audit_20261008.md

### AUDIT-0014（2026-10-08）social_media_formatter 3400 行、数据分叉
- 涉及文件：core/social_media_formatter.py:53-2392
- 严重程度：高
- 问题：LanguageAnalyzer 约 2800 行，语言数据与 video_analyzer 复制后分叉。
- 建议：合并共享数据，拆为 social_formatter 包。
- 状态：待处理
- 来源报告：audit_20261008.md

### AUDIT-0015（2026-10-08）gemini_engine 2166 行、5 职责
- 涉及文件：core/gemini_engine.py:287-2166
- 严重程度：高
- 问题：ASR/校对/翻译/封面 PIL 绘图/JSON 容错混装一类。
- 建议：拆为 core/gemini 包，image_localize 独立。
- 状态：待处理
- 来源报告：audit_20261008.md

### AUDIT-0016（2026-10-08）subtitle_processor 4096 行、8 职责
- 涉及文件：core/subtitle_processor.py 全文
- 严重程度：高
- 问题：数据模型/分句/ASR/翻译/SRT 写入/质量门/烧录/编排混在单文件。
- 建议：拆为 core/subtitles 包。
- 状态：待处理
- 来源报告：audit_20261008.md

### AUDIT-0017（2026-10-08）PipelineRunner._running 无锁
- 涉及文件：core/pipeline.py:479-485; core/task_scheduler.py:317-379
- 严重程度：中
- 问题：检查-置位无锁，手动与定时入口可并发双跑。
- 建议：加锁保护 _running 或用 Event。
- 状态：待处理
- 来源报告：audit_20261008.md

### AUDIT-0018（2026-10-08）下载临时目录残留
- 涉及文件：core/download.py:501-519,662-665,856-861
- 严重程度：中
- 问题：异常残留 .part，重试复用陈旧文件。
- 建议：下载前清理 workdir，清理移至 finally。
- 状态：待处理
- 来源报告：audit_20261008.md

### AUDIT-0019（2026-10-08）DownloadPool._threads 无锁
- 涉及文件：core/download.py:914-1052
- 严重程度：中
- 问题：线程列表轮询/append/重赋值无锁，可超并发或丢失线程。
- 建议：统一加锁或改用 ThreadPoolExecutor。
- 状态：待处理
- 来源报告：audit_20261008.md

### AUDIT-0020（2026-10-08）ResultBuffer 无锁、JSON 不删
- 涉及文件：core/crawler.py:383-517
- 严重程度：中
- 问题：add/write 无锁，crawl_result 文件读后不删。
- 建议：加锁、读后删除。
- 状态：待处理
- 来源报告：audit_20261008.md

### AUDIT-0021（2026-10-08）CDP cookies 并发覆写
- 涉及文件：core/download.py:557,699-707; core/cdp_cookies.py:203-234
- 严重程度：中
- 问题：多线程同写一 cookie 文件，截断写入无锁。
- 建议：临时文件+os.replace 原子替换并加模块锁。
- 状态：待处理
- 来源报告：audit_20261008.md

### AUDIT-0022（2026-10-08）Vimeo/Dailymotion 绕过指纹+复制
- 涉及文件：core/spiders/vimeo_spider.py; core/spiders/dailymotion_spider.py
- 严重程度：中
- 问题：直接 requests、无指纹/退避，search 互相复制。
- 建议：基类提供 _fetch_json_api 模板。
- 状态：待处理
- 来源报告：audit_20261008.md

### AUDIT-0023（2026-10-08）Pipeline 调用 YoutubeSpider-only 方法
- 涉及文件：core/pipeline.py:195,214,236; core/spiders/__init__.py
- 严重程度：中
- 问题：跨平台选关键词/频道模式会 AttributeError。
- 建议：基类抛 NotImplementedError 或分派前 getattr 判断。
- 状态：待处理
- 来源报告：audit_20261008.md

### AUDIT-0024（2026-10-08）TaskQueue 未接线
- 涉及文件：utils/queue_manager.py; core/pipeline.py
- 严重程度：中
- 问题：完整状态机无生产调用，真实管线仅用字符串状态。
- 建议：接入 future 或删除并标注。
- 状态：待处理
- 来源报告：audit_20261008.md

### AUDIT-0025（2026-10-08）cookie 解析三处重复
- 涉及文件：core/publish/clients.py,playwright_base.py,biliup_runtime.py
- 严重程度：中
- 问题：三类格式解析分支不一致。
- 建议：抽 cookie_utils 统一解析。
- 状态：待处理
- 来源报告：audit_20261008.md

### AUDIT-0026（2026-10-08）三平台 Client 包装重复
- 涉及文件：core/publish/clients.py:285-382
- 严重程度：中
- 问题：upload_video 包装逐行相同。
- 建议：基类加模板方法，子类传 uploader_cls。
- 状态：待处理
- 来源报告：audit_20261008.md

### AUDIT-0027（2026-10-08）uploader do_upload 同构
- 涉及文件：core/publish/playwright_uploaders.py:31-303
- 严重程度：中
- 问题：三平台流程同构、仅选择器不同。
- 建议：基类 _do_upload_common 模板 + selectors 配置。
- 状态：待处理
- 来源报告：audit_20261008.md

### AUDIT-0028（2026-10-08）_get_video_duration 重复
- 涉及文件：core/subtitle_processor.py:1483,2603
- 严重程度：中
- 问题：同类两个同名方法、前者死代码。
- 建议：删前者或抽模块级 probe。
- 状态：待处理
- 来源报告：audit_20261008.md

### AUDIT-0029（2026-10-08）classify 缓存重复/兜底重建
- 涉及文件：core/classify.py:229-309
- 严重程度：中
- 问题：缓存方法重复，每次兜底新建 RuleBased、缓存无 TTL。
- 建议：提到基类、单例复用、加 TTL/LRU。
- 状态：待处理
- 来源报告：audit_20261008.md

### AUDIT-0030（2026-10-08）subtitle_render Popen 无超时/不 kill
- 涉及文件：core/subtitle_render.py:142-200
- 严重程度：中
- 问题：Popen 无 timeout 却 catch TimeoutExpired，异常不 kill。
- 建议：communicate(timeout) 或加 deadline、异常 kill。
- 状态：待处理
- 来源报告：audit_20261008.md

### AUDIT-0031（2026-10-08）model_registry GUI 耦合/双数据源
- 涉及文件：core/model_registry.py:20,962; core/ai_writer.py; core/gemini_engine.py
- 严重程度：中
- 问题：依赖 Qt，运行时绕过 Registry 直读 config。
- 建议：拆不依赖 Qt 的核心，运行时统一从 Registry 取链。
- 状态：待处理
- 来源报告：audit_20261008.md

### AUDIT-0032（2026-10-08）封面管线 worker setText
- 涉及文件：gui/pages/page_download.py:1010-1090
- 严重程度：中
- 问题：worker 线程直接 setText，与信号混用。
- 建议：新增状态信号 emit。
- 状态：待处理
- 来源报告：audit_20261008.md

### AUDIT-0033（2026-10-08）register_thread 形同虚设
- 涉及文件：gui/task_manager.py:88-121
- 严重程度：中
- 问题：仅两处登记，18+ 裸线程未登记，force_stop 无法强杀。
- 建议：spawn 工厂自动登记或改用 Event stop flag。
- 状态：待处理
- 来源报告：audit_20261008.md

### AUDIT-0034（2026-10-08）GUI/Web 两套流水线编排
- 涉及文件：gui/auto_pipeline.py:172-488; web/main.py:253-300
- 严重程度：中
- 问题：GUI 手写阶段、Web 走 PipelineRunner，行为漂移。
- 建议：编排下沉 core，两端做薄壳。
- 状态：待处理
- 来源报告：audit_20261008.md

### AUDIT-0035（2026-10-08）page_download God Class
- 涉及文件：gui/pages/page_download.py:30-1250
- 严重程度：中
- 问题：1246 行、11 项职责。
- 建议：按单视频/批量/封面/服务拆分。
- 状态：待处理
- 来源报告：audit_20261008.md

### AUDIT-0036（2026-10-08）log_bridge 同步 sink/吞异常
- 涉及文件：gui/log_bridge.py:47-55
- 严重程度：中
- 问题：enqueue=False 同步执行，裸 except 丢日志。
- 建议：enqueue=True，except 上报。
- 状态：待处理
- 来源报告：audit_20261008.md

### AUDIT-0037（2026-10-08）config.yaml 臃肿/无校验
- 涉及文件：config.yaml; utils/config_loader.py:89-119
- 严重程度：中
- 问题：819 行含约 500 行模型清单，加载无校验、默认模板脱节。
- 建议：拆模型清单，加校验并对齐默认配置。
- 状态：待处理
- 来源报告：audit_20261008.md

### AUDIT-0038（2026-10-08）依赖未锁/打包近 1GB
- 涉及文件：requirements*.txt; build_gui.bat:66-84; build_gui.spec
- 严重程度：中
- 问题：依赖 >= 无锁，打包 927MB 模型与明文 config。
- 建议：锁版本、模型外置、发行包放模板。
- 状态：待处理
- 来源报告：audit_20261008.md

### AUDIT-0039（2026-10-08）db_manager 过载/重复/缺表
- 涉及文件：utils/db_manager.py; resources/schema.sql
- 严重程度：中
- 问题：1332 行、空壳函数、刷盘 COUNT 刷屏，3 张表无访问层。
- 建议：按表拆 repository、删空壳、补访问层。
- 状态：待处理
- 来源报告：audit_20261008.md

### AUDIT-0040（2026-10-08）分层倒置
- 涉及文件：utils/app_initializer.py:21; core 多处
- 严重程度：中
- 问题：utils 反向 import core，函数内延迟导入绕环。
- 建议：app_initializer 移入口层，解耦循环模块。
- 状态：待处理
- 来源报告：audit_20261008.md

### AUDIT-0041（2026-10-08）零自动化测试
- 涉及文件：tests/; 根目录 7 个 test_*.py
- 严重程度：中
- 问题：tests 为空，游离脚本未接入 pytest。
- 建议：收编进 tests、补配置，优先测基建模块。
- 状态：待处理
- 来源报告：audit_20261008.md

### AUDIT-0042（2026-10-08）browser_cookies 未忽略
- 涉及文件：data/browser_cookies.txt; .gitignore
- 严重程度：中
- 问题：明文 cookie 未跟踪但也未忽略，易误提交。
- 建议：.gitignore 增该文件并 check-ignore 复核。
- 状态：待处理
- 来源报告：audit_20261008.md

### AUDIT-0043（2026-10-08）CDP 握手 socket 泄漏
- 涉及文件：core/cdp_cookies.py:70-95
- 严重程度：低
- 问题：握手失败 raise 时未 close sock。
- 建议：内部 try/except 关闭后再抛。
- 状态：待处理
- 来源报告：audit_20261008.md

### AUDIT-0044（2026-10-08）任务 ID 冲突
- 涉及文件：core/task_scheduler.py:176,299
- 严重程度：低
- 问题：秒级时间戳/固定 id 易撞。
- 建议：用 uuid 或 replace_existing。
- 状态：待处理
- 来源报告：audit_20261008.md

### AUDIT-0045（2026-10-08）headers 复制 4 份
- 涉及文件：core/download.py; core/spiders/youtube_spider.py
- 严重程度：低
- 问题：探针 headers 逐字复制。
- 建议：抽常量+工厂。
- 状态：待处理
- 来源报告：audit_20261008.md

### AUDIT-0046（2026-10-08）except pass 聚集
- 涉及文件：core/download.py; core/spiders/youtube_spider.py
- 严重程度：低
- 问题：大量裸 except 静默吞异常。
- 建议：至少 debug/warning 日志。
- 状态：待处理
- 来源报告：audit_20261008.md

### AUDIT-0047（2026-10-08）超长函数清单
- 涉及文件：core/download.py; core/spiders/youtube_spider.py; core/pipeline.py
- 严重程度：低
- 问题：多个 160-344 行函数。
- 建议：按阶段拆方法。
- 状态：待处理
- 来源报告：audit_20261008.md

### AUDIT-0048（2026-10-08）爬虫管线低风险观察
- 涉及文件：core/pipeline.py; core/spiders/youtube_spider.py; core/download.py
- 严重程度：低
- 问题：result.crawled 恒 0、_probe_cache 无界、去重 URL 仅 YouTube、external_downloader 待核实。
- 建议：逐项核实修正。
- 状态：待处理
- 来源报告：audit_20261008.md

### AUDIT-0049（2026-10-08）死代码
- 涉及文件：core/ai_writer.py; core/social_media_formatter.py
- 严重程度：低
- 问题：Gemini 梯队已停用仍留方法，_should_use_ai 未被调用。
- 建议：删除或标注。
- 状态：待处理
- 来源报告：audit_20261008.md

### AUDIT-0050（2026-10-08）lang_names 重复/domain 死代码
- 涉及文件：core/ai_writer.py; core/publish/playwright_base.py
- 严重程度：低
- 问题：语言名映射 4 份、domain 恒 .douyin.com。
- 建议：提常量、删无效逻辑。
- 状态：待处理
- 来源报告：audit_20261008.md

### AUDIT-0051（2026-10-08）URL 拼接/_log 重复
- 涉及文件：gui/pages/page_download.py; gui/auto_pipeline.py; 各 page
- 严重程度：低
- 问题：YouTube URL 拼 4 处、每页复制 _log。
- 建议：抽 ui_log 与 URL 工具函数。
- 状态：待处理
- 来源报告：audit_20261008.md

### AUDIT-0052（2026-10-08）Web XSS
- 涉及文件：web/static/index.html:500-505
- 严重程度：低
- 问题：innerHTML 拼接未转义文件名。
- 建议：改用 textContent 或转义。
- 状态：待处理
- 来源报告：audit_20261008.md

### AUDIT-0053（2026-10-08）web 隧道产物清理
- 涉及文件：web/cloudflared.exe; tunnel/lt 日志
- 严重程度：低
- 问题：二进制/隧道日志/缓存同目录。
- 建议：gitignore 并移除。
- 状态：待处理
- 来源报告：audit_20261008.md

### AUDIT-0054（2026-10-08）根目录卫生
- 涉及文件：D:\Ideas\VideoCrawler\
- 严重程度：低
- 问题：散落调试脚本、临时输出、zip、temp_extract、_ref。
- 建议：删临时文件，有价值脚本移 Vc/scripts。
- 状态：待处理
- 来源报告：audit_20261008.md

### AUDIT-0055（2026-10-08）.gitignore 编码/缺口及打包观察
- 涉及文件：.gitignore; build_gui.bat; bin/
- 严重程度：低
- 问题：无 BOM 致中文注释显示乱码、忽略覆盖不全、build 硬编码 python 路径。
- 建议：另存 UTF-8 BOM、补全条目、路径可配置。
- 状态：待处理
- 来源报告：audit_20261008.md

---

## 2026-10-09 第二次审核明细（来源：audit_20261009.md）

> 说明：本次对 AUDIT-0001～0055 逐条回到代码复核，状态以本节与上方总表为准（取代 10-08 明细中的初始状态）。核查基于当前磁盘代码（git 未 commit，HEAD 3219857，故无 commit 号）。
> 统计：已修复 26（47.3%）、处理中 16、待处理 12、已确认不处理 1。

### 历史条目核查状态更新（55 条）

| 编号 | 新状态 | 核查证据 |
|---|---|---|
| 0001 | 待处理 | config.yaml 仍明文密钥（:21,64,101-102,110-111,127,141,153,165,177）；仍被 git 跟踪；build_gui.bat:83 仍拷 |
| 0002 | 已修复 | crypto_util.py:61-71 随机 salt `.crypto_salt`；PBKDF2；失败抛异常 |
| 0003 | 已修复 | db_manager.py:321 autocheckpoint=1000；:486 shutdown checkpoint(TRUNCATE)；实测 WAL 2.17MB→0 |
| 0004 | 处理中 | .gitignore 已补；但未 git rm --cached，output/bin/ffmpeg-8.1.2 仍在 index，新代码未 commit |
| 0005 | 已修复 | 改走 path_helper.get_node_path（download.py:706-711、youtube_spider.py:129-134）；无写死路径 |
| 0006 | 已修复 | crawler.py:210-221 删 last_exception is None，重试耗尽即降级 |
| 0007 | 已修复 | pipeline.py:649-657 finally shutdown(wait=False,cancel_futures)，含版本兜底 |
| 0008 | 已修复 | playwright_base.py:171-215 try/finally 关闭 context/browser、清理 storage |
| 0009 | 已修复 | ai_writer.py:262 守卫改为双梯队任一可用 |
| 0010 | 已修复 | page_publish.py:49-54 新增 4 信号；worker 仅 emit |
| 0011 | 已修复 | main_window.py:486-516 新增 closeEvent，停 web/auto/任务/DB |
| 0012 | 处理中 | 随机 key、日志脱敏、Bearer 中间件已做；key 仍走 query、绑 0.0.0.0、lt.out 残留、/api/stop 无 cancel |
| 0013 | 待处理 | video_analyzer.py 仍 5683 行，数据未外移 |
| 0014 | 待处理 | social_media_formatter.py 仍约 3400 行、数据分叉 |
| 0015 | 已修复 | 拆 core/gemini/；旧 gemini_engine.py 为 308 行门面 |
| 0016 | 已修复 | 拆 core/subtitles/；旧 subtitle_processor.py 为 29 行 shim |
| 0017 | 已修复 | pipeline.py:142 加锁、:489-495 检查置位原子化 |
| 0018 | 处理中 | download.py:651-655 入口 rmtree（消除错误续传）；清理未移 finally，最终失败仍残留 |
| 0019 | 处理中 | append/cleanup/results 加锁；闸门 len(_threads) 仍无锁、可超 max_threads |
| 0020 | 已修复 | crawler.py:415 加锁；get_all_results 读后 os.remove |
| 0021 | 已修复 | cdp_cookies.py:22 模块锁；:223-250 写 .tmp + os.replace |
| 0022 | 已修复 | vimeo_spider.py:79、dailymotion_spider.py:75 改走 engine.request；两 search 分化 |
| 0023 | 已修复 | pipeline.py:195,217 分派前 hasattr 守卫 |
| 0024 | 已确认不处理 | queue_manager.py:12-15 已标注预留，仅 bootstrap 初始化、无业务调用 |
| 0025 | 处理中 | clients/playwright_base 用 _cookie_utils；biliup_runtime.py:126-141 仍自带解析 |
| 0026 | 待处理 | clients.py:259-275,375-391 两 upload 包装仍逐行相同 |
| 0027 | 已修复 | playwright_base.py:254-327 抽取公共步骤 |
| 0028 | 已修复 | subtitles/asr.py:1211 仅 1 份，早期死代码已删 |
| 0029 | 处理中 | classify.py:28-35 RuleBased 单例；缓存键/clear_cache 仍重复、无 TTL |
| 0030 | 处理中 | subtitle_render.py:152-161 deadline + kill；TimeoutExpired 仍死代码、阻塞读见 0060 |
| 0031 | 处理中 | model_registry.py:25-47 Qt lazy import；运行时仍直读 config |
| 0032 | 已修复 | page_download.py:51-52 状态信号；worker 仅 emit |
| 0033 | 处理中 | thread_spawn 已建；TaskManager.spawn 零调用、多数线程未登记 |
| 0034 | 待处理 | auto_pipeline.py:182-254 与 web/main.py:400,445 两套编排仍并存 |
| 0035 | 待处理 | page_download.py 仍 1253 行 God Class |
| 0036 | 已修复 | log_bridge.py:57 enqueue=True；except 改 debug |
| 0037 | 待处理 | config.yaml 仍 819 行、加载无校验、DEFAULT_CONFIG 脱节 |
| 0038 | 待处理 | 依赖仍全 >=；build_gui.bat:78 拷 models、:83 拷 config |
| 0039 | 已修复 | utils/db/video_repo.py、task_repo.py；db_manager 1332→554；publish 三表有 storage.py |
| 0040 | 已修复 | app/bootstrap.py 承接装配；app_initializer 为 9 行 shim |
| 0041 | 待处理 | tests/ 仍为空（旧 test_*.py 已删≠建测试） |
| 0042 | 已修复 | .gitignore:69-70 增加 data/browser_cookies.txt、data/*.txt |
| 0043 | 已修复 | cdp_cookies.py:97-103 握手异常 close sock 后再抛 |
| 0044 | 处理中 | 自动 id 改 uuid；固定 id scheduled_pipeline 仍无 replace_existing |
| 0045 | 已修复 | ytdlp_common.YTDLP_YOUTUBE_HEADERS 收口 4 处 |
| 0046 | 待处理 | download.py 约 9 处、youtube_spider 3 处裸 except pass |
| 0047 | 待处理 | 超长函数未拆（_do_download~330、filter_dead_urls~285 等） |
| 0048 | 处理中 | result.crawled 已修复、external_downloader 已确认；_probe_cache 无界、去重仅 YouTube |
| 0049 | 待处理 | ai_writer.py:928-946 _call_gemini/_get_gemini_client 保留待恢复 |
| 0050 | 处理中 | ai_writer.py:36-41 LANG_NAMES；playwright_base.py:84 domain 仍回落 .douyin.com |
| 0051 | 处理中 | youtube_url 收口多处；_parse_video_id 仍自带正则、各页 _log 未收口 |
| 0052 | 已修复 | index.html:653 esc 已加（作用域见 0065） |
| 0053 | 处理中 | 隧道产物已 gitignore；物理文件仍在（cloudflared 55MB） |
| 0054 | 处理中 | 父目录仍散落脚本；Vc 内新增 _diag_* 诊断文件（见 0066） |
| 0055 | 处理中 | .gitignore 仍无 BOM；build_gui.bat:22 仍硬编码 python 路径 |

### 新增明细（AUDIT-0056～0076）

### AUDIT-0056（2026-10-09）subtitles/processor.py 缺关键 import，NameError
- 涉及文件：core/subtitles/processor.py:29-53
- 严重程度：高
- 问题：__init__ 第 52、53 行用 VideoSubtitleEmbedder、SubtitleQualityGate，但 import 列表（止于 :32）未导入。
- 建议：补 embedder 与 quality_gate 两行 import。
- 状态：待处理
- 来源报告：audit_20261009.md

### AUDIT-0057（2026-10-09）内嵌 Web 与独立 watchdog 生命周期冲突
- 涉及文件：gui/web_host.py:48-123；web/watchdog.py:296-450
- 严重程度：高
- 问题：关 GUI 后 watchdog 复活 uvicorn；或 watchdog/_ensure_port_free 的 taskkill 误杀占 8000 的 GUI。
- 建议：引入 VC_DEPLOY_MODE 互斥，watchdog 检测到 GUI 进程则退出。
- 状态：待处理
- 来源报告：audit_20261009.md

### AUDIT-0058（2026-10-09）硬编码弱默认密钥 + 绑 0.0.0.0
- 涉及文件：gui/web_host.py:27,52；web/watchdog.py:43；web/main.py:44
- 严重程度：高
- 问题：env 未设回落 VideoCrawler2026，setdefault 注入使 web/main 放弃随机 key；绑全部网卡。
- 建议：删硬编码回落，未设则强制随机或报错；默认绑 127.0.0.1。
- 状态：待处理
- 来源报告：audit_20261009.md

### AUDIT-0059（2026-10-09）video_repo/task_repo 缺 import os/time
- 涉及文件：utils/db/video_repo.py:213,456；task_repo.py:177
- 严重程度：高
- 问题：调用 os.path.exists、time.time 但两文件顶部无 import。
- 建议：补 import os、import time。
- 状态：待处理
- 来源报告：audit_20261009.md

### AUDIT-0060（2026-10-09）烧录 deadline 被阻塞读架空
- 涉及文件：core/subtitle_render.py:154-166
- 严重程度：中
- 问题：stderr.read(256) 阻塞，ffmpeg 静默卡死时 deadline 检查不再执行。
- 建议：reader 线程 + queue 读 stderr，或 -progress pipe:1 非阻塞。
- 状态：待处理
- 来源报告：audit_20261009.md

### AUDIT-0061（2026-10-09）磁盘去重用 __file__ 拼 output
- 涉及文件：core/pipeline.py:163
- 严重程度：中
- 问题：frozen 模式下 __file__ 与 APP_ROOT 不一致，去重扫不到真实 mp4 → 全量重下。
- 建议：改用 path_helper.get_output_dir()。
- 状态：待处理
- 来源报告：audit_20261009.md

### AUDIT-0062（2026-10-09）publish_queue 定时任务阻塞立即任务
- 涉及文件：core/publish/publish_queue.py:183-196
- 严重程度：中
- 问题：定时 job 放回队尾后 worker sleep 到点，期间不处理其他立即任务。
- 建议：用独立 scheduled 堆 + 短超时 wait。
- 状态：待处理
- 来源报告：audit_20261009.md

### AUDIT-0063（2026-10-09）xhs_api_client 顶层硬依赖 xhs_cli
- 涉及文件：core/publish/xhs_api_client.py:36-40
- 严重程度：中
- 问题：可选依赖为顶层 import，未安装即失败、无法优雅降级。
- 建议：移入 __init__ 或模块级 try/except 设可用性标志。
- 状态：待处理
- 来源报告：audit_20261009.md

### AUDIT-0064（2026-10-09）/api/server/restart 内嵌模式杀 GUI
- 涉及文件：web/main.py:803-835
- 严重程度：中
- 问题：os._exit(0) 内嵌模式会终止 GUI；且无 import sys，sys.executable 处 NameError 被吞。
- 建议：内嵌模式禁用该端点；补 import sys；仅 graceful restart。
- 状态：待处理
- 来源报告：audit_20261009.md

### AUDIT-0065（2026-10-09）index.html esc 作用域导致发布 Tab 失效
- 涉及文件：web/static/index.html:653,689-693
- 严重程度：中
- 问题：esc 声明在 loadVideos 局部，loadPool 等顶层函数引用即 ReferenceError。
- 建议：把 esc 提至 script 顶层。
- 状态：待处理
- 来源报告：audit_20261009.md

### AUDIT-0066（2026-10-09）诊断脚本散落 Vc 根目录
- 涉及文件：_diag_xhs.py、_diag_xhs2.py、_diag_xhs3.py、_fix_cookies.py、_show_diag.py、_diag_result.json、_diag_screenshot.png
- 严重程度：中
- 问题：7 个诊断文件未 gitignore，易误提交。
- 建议：移 scripts/diag/ 或 .gitignore 加对应规则。
- 状态：待处理
- 来源报告：audit_20261009.md

### AUDIT-0067（2026-10-09）publish storage 与 apsw 主库双轨
- 涉及文件：core/publish/storage.py:22-27
- 严重程度：中
- 问题：每次 sqlite3 新建连接、未设 WAL/busy_timeout，与主库双连接。
- 建议：统一 PRAGMA 或统一到 apsw。
- 状态：待处理
- 来源报告：audit_20261009.md

### AUDIT-0068（2026-10-09）CDP HTTPConnection 异常泄漏
- 涉及文件：core/cdp_cookies.py:147-154
- 严重程度：低
- 建议：with conn 或 try/finally 关闭。
- 状态：待处理
- 来源报告：audit_20261009.md

### AUDIT-0069（2026-10-09）subtitles 模块 unused import / 重复文件头
- 涉及文件：core/subtitles/ 8 模块
- 严重程度：低
- 建议：清理无用 import、重写各模块 docstring。
- 状态：待处理
- 来源报告：audit_20261009.md

### AUDIT-0070（2026-10-09）@dataclass 装饰器悬空
- 涉及文件：core/subtitles/embedder.py:34-37；processor.py:38-41
- 严重程度：低
- 建议：删空行或确认是否需要 dataclass。
- 状态：待处理
- 来源报告：audit_20261009.md

### AUDIT-0071（2026-10-09）gemini mixin 无接口约束
- 涉及文件：core/gemini/_asr_mixin.py:70,204 等
- 严重程度：低
- 建议：抽 GeminiBaseMixin 声明 _model_chain/_get_client 接口。
- 状态：待处理
- 来源报告：audit_20261009.md

### AUDIT-0072（2026-10-09）watchdog 通配 CORS
- 涉及文件：web/watchdog.py:470
- 严重程度：低
- 建议：CORS 收紧到具体来源。
- 状态：待处理
- 来源报告：audit_20261009.md

### AUDIT-0073（2026-10-09）MQTT token 明文广播
- 涉及文件：web/mqtt_bridge.py:277-292
- 严重程度：低
- 建议：payload 去掉 token，或换 TLS/私有 broker。
- 状态：待处理
- 来源报告：audit_20261009.md

### AUDIT-0074（2026-10-09）tunnel reader 线程边界挂起
- 涉及文件：gui/web_host.py:158-194
- 严重程度：低
- 建议：reader 加超时/stop 事件。
- 状态：待处理
- 来源报告：audit_20261009.md

### AUDIT-0075（2026-10-09）SQLStatements 致循环依赖
- 涉及文件：utils/db_manager.py:33-187
- 严重程度：低
- 建议：移 utils/db/constants.py，消除 _ensure_base()。
- 状态：待处理
- 来源报告：audit_20261009.md

### AUDIT-0076（2026-10-09）build_gui.spec 未覆盖 app
- 涉及文件：build_gui.spec:20,49
- 严重程度：低
- 建议：collect_submodules/datas 加 "app"。
- 状态：待处理
- 来源报告：audit_20261009.md

---

## 2026-10-19 第三次审核明细（来源：audit_20261019.md，手动补跑，距上次 10 天）

> 说明：本次对 AUDIT-0001～0076 逐条回到当前代码复核。git 仍未 commit（HEAD 3219857），证据为当前磁盘 `文件:行号/函数名`。
> 核心结论：**10 天内原始 55 条零新增修复，26 处已修复无回退**；唯一主动动作是删除 `web/watchdog.py`（连带关闭 0057/0072/0074，但遗留启动脚本悬空 0079）。
> 统计（76 条）：已修复 26（34.2%）、处理中 17、待处理 29、已确认不处理 4。原始 55 条口径修复率维持 47.3%。

### 历史条目核查状态表（76 条，10-19 现状）

| 编号 | 10-19 状态 | 核查证据/变化 |
|---|---|---|
| 0001 | 待处理 | config.yaml 9 处明文密钥（:21,64,101-102,110-111,127,141,153,165,177）值未变；git ls-files 仍命中；build_gui.bat:83 仍拷 |
| 0002 | 已修复 | crypto_util.py:61-79 随机 salt+PBKDF2（维持） |
| 0003 | 已修复 | db_manager.py:321,486；实测 db 159744B、无 -wal/-shm |
| 0004 | 处理中 | output(37)/bin(84) 仍在 index，新代码仍 `??`，未 git rm --cached、未 commit |
| 0005 | 已修复 | download.py:793-798、youtube_spider.py:129-134 走 get_node_path |
| 0006 | 已修复 | crawler.py:216 重试耗尽即降级 |
| 0007 | 已修复 | pipeline.py:649-657 finally shutdown |
| 0008 | 已修复 | playwright_base.py:171-215 try/finally |
| 0009 | 已修复 | ai_writer.py:262 双梯队守卫 |
| 0010 | 已修复 | page_publish 信号槽（维持） |
| 0011 | 已修复 | main_window.py:481 closeEvent；web_host 加 atexit/PID/stop |
| 0012 | 处理中 | 随机 key/mask/中间件已做；仍绑 0.0.0.0、key 走 query、health:629-630 与日志仍明文 key、lt.out 残留、stop 无 cancel |
| 0013 | 待处理 | video_analyzer 5683→5604，约 4000 行硬编码数据未外移 |
| 0014 | 待处理 | social_media_formatter 3400→3376，lang_names 仍 3 次重复 |
| 0015 | 已修复 | gemini_engine 308 行门面（维持） |
| 0016 | 已修复 | subtitle_processor 29 行 shim（维持） |
| 0017 | 已修复 | pipeline.py:489-495 加锁（维持） |
| 0018 | 处理中 | 入口 rmtree:736-739、新增 _abort_incomplete:865-870；extract_info:820 异常时 workdir 仍未在 finally 清理 |
| 0019 | 处理中 | 闸门 len(:1039) 仍无锁、start(:1048) 在持锁 append(:1049) 前 |
| 0020 | 已修复 | crawler.py:540 读后 os.remove（维持） |
| 0021 | 已修复 | download.py:769-770 走 auto_refresh_cookies（维持） |
| 0022 | 已修复 | vimeo/dailymotion 走 engine.request（维持） |
| 0023 | 已修复 | hasattr 守卫（维持） |
| 0024 | 已确认不处理 | queue_manager 标注预留（维持） |
| 0025 | 处理中 | biliup_runtime.py:126-141 仍自带 cookie 解析 |
| 0026 | 待处理 | clients.py:288-304 等 upload 仍逐行相同 |
| 0027 | 已修复 | playwright_base 公共步骤（维持） |
| 0028 | 已修复 | asr.py:1211 仅 1 份（维持） |
| 0029 | 处理中 | classify.py:240-243/312-315 缓存键重复；RuleBased:195-197 无 TTL |
| 0030 | 处理中 | subtitle_render 10-14 重写：Popen 仍无 timeout(:472)、TimeoutExpired:533 仍死代码 |
| 0031 | 处理中 | ai_writer 仍直读 config，model_registry 双数据源 |
| 0032 | 已修复 | page_download 封面信号（维持） |
| 0033 | 处理中 | spawn 被 15+ 文件采用；TaskManager.spawn 仍零调用，多数 worker 未登记 |
| 0034 | 待处理 | auto_pipeline 与 web/main PipelineRunner 两套编排并存 |
| 0035 | 待处理 | page_download 1253→1115，未拆类（有改善） |
| 0036 | 已修复 | log_bridge enqueue=True（维持） |
| 0037 | 待处理 | config 833 行；save_config/save_subsection 纯写盘无校验 |
| 0038 | 待处理 | 依赖仍全 >=；build:83 仍拷明文 config；models 927MB |
| 0039 | 已修复 | db_manager 554 行 + db/ 两 repo（维持） |
| 0040 | 已修复 | app/bootstrap 92 行（维持） |
| 0041 | 待处理 | tests/ 仍 0 文件 |
| 0042 | 已修复 | .gitignore:69-70（维持） |
| 0043 | 已修复 | cdp_cookies 握手异常 close（维持） |
| 0044 | 处理中 | 自动 id 仍 uuid；固定 id scheduled_pipeline:301 仍无 replace_existing |
| 0045 | 已修复 | download.py:451,643,764 与 youtube_spider:116 用 YTDLP_YOUTUBE_HEADERS |
| 0046 | 待处理 | download.py 仍约 9 处裸 except:pass（:95,277,403,423,459,652,784,840,934） |
| 0047 | 待处理 | _do_download 约 340 行（更長）；youtube_spider 三超长函数未拆 |
| 0048 | 处理中 | crawled/external_downloader 已闭环；_probe_cache 无界、去重仅 YouTube（pipeline:167-175） |
| 0049 | 待处理 | ai_writer.py:927-948 _call_gemini/_get_gemini_client 死代码 |
| 0050 | 处理中 | playwright_base.py:103 domain 仍回落 .douyin.com |
| 0051 | 处理中 | build_watch_url 收口；_parse_video_id 本地正则、各页 _log 仍在 |
| 0052 | 已修复 | index.html esc 已加（作用域问题见 0065） |
| 0053 | 处理中 | cloudflared.exe 已删（改善）；lt.out/lt.err/tunnel.*/watchdog.log 残留 |
| 0054 | 处理中 | 父目录新增 4 个 _diag/_remote 脚本；Vc 根新增 _test_mqtt.py（恶化） |
| 0055 | 处理中 | .gitignore 仍无 BOM；build_gui.bat:22 仍硬编码 D:\python\python.exe |
| 0056 | 待处理 | processor.py:52-53 实例化、import 仍止于 :32；pipeline:27→process_video_subtitle:632 必崩 |
| 0057 | 已确认不处理 | web/watchdog.py 已删除，冲突源消失；遗留 0079 |
| 0058 | 待处理 | web_host.py:35 仍硬编码弱 key、:159 绑 0.0.0.0、:194 setdefault 注入 |
| 0059 | 待处理 | video_repo:213,456 / task_repo:177 仍用 os/time，顶部无 import |
| 0060 | 待处理 | subtitle_render.py:492 read(256) 阻塞、:487 deadline 仅循环顶部；10-14 重写未改 |
| 0061 | 待处理 | pipeline.py:163 仍 __file__ 拼 output |
| 0062 | 待处理 | publish_queue.py:183-196 定时 job sleep 阻塞 |
| 0063 | 待处理 | xhs_api_client.py:36-40 顶层硬 import |
| 0064 | 待处理 | web/main.py:668 仍 os._exit(0)、:659 裸 sys 但顶部无 import sys |
| 0065 | 待处理 | index.html esc 仅 :653 局部；loadPool:672、loadAccounts:713 跨作用域 |
| 0066 | 待处理 | 8 个诊断/测试文件 git check-ignore 返回 False |
| 0067 | 待处理 | storage.py:22-27 sqlite3 直连，无 WAL/busy_timeout |
| 0068 | 待处理 | cdp_cookies.py:147-155 异常只 log 不 close |
| 0069 | 待处理 | models.py:4-28 重复文件头、无用 import |
| 0070 | 待处理 | embedder.py:34-37、processor.py:38-41 dataclass 悬空 |
| 0071 | 待处理 | mixin 直接调 _get_client/_model_chain，无基类约束 |
| 0072 | 已确认不处理 | watchdog.py 已删，CORS 随文件消失 |
| 0073 | 待处理 | mqtt_bridge.py:343-357 每条消息仍带 token（新增 keepalive/批量 flush 未改此） |
| 0074 | 已确认不处理 | web_host tunnel/reader 代码已整段移除 |
| 0075 | 处理中 | repos 已 _ensure_base 延迟 import（video_repo:17-23、task_repo:16-22），模块加载不成环；SQLStatements 类仍在 db_manager:33 |
| 0076 | 待处理 | build_gui.spec:20,49 列表仍无 app |

### 新增明细（AUDIT-0077～0086）

### AUDIT-0077（2026-10-19）PermanentDownloadError 定义后从未 raise，永久错误仍重试
- 涉及文件：core/download.py:35,584,865-883
- 严重程度：中
- 问题：永久错误类从未被 raise，流闸门失败抛 RuntimeError 被通用 except 捕获重试 3 次，放大限流。
- 建议：永久情形改抛 PermanentDownloadError，瞬时情形保留 RuntimeError。
- 状态：待处理
- 来源报告：audit_20261019.md

### AUDIT-0078（2026-10-19）image_provider call_pollinations 文生图伪装图生图
- 涉及文件：core/image_provider.py:307-357
- 严重程度：中
- 问题：图生图链第 3 位实际调 T2I 的 /prompt 端点，固定 POLL_PROMPT，输出与入参无关的大脑封面。
- 建议：删除该分支或改接真图生图端点。
- 状态：待处理
- 来源报告：audit_20261019.md

### AUDIT-0079（2026-10-19）启动脚本悬空引用已删 watchdog/cloudflared
- 涉及文件：start_all.bat；start_tunnel.bat；web/wake.html
- 严重程度：中
- 问题：start_all 仍 `python -m web.watchdog`（模块已删，双击即 No module named web.watchdog）；start_tunnel 调已删 cloudflared.exe；wake.html 仍 fetch :8001。
- 建议：删除或改写，统一走 start_gui.bat 内嵌模式。
- 状态：待处理
- 来源报告：audit_20261019.md

### AUDIT-0080（2026-10-19）_test_mqtt.py 硬编码弱密钥散落根目录
- 涉及文件：_test_mqtt.py:4
- 严重程度：中
- 问题：硬编码 VideoCrawler2026、内嵌 broker.emqx.io:8084，未 gitignore。
- 建议：移 scripts/，key 改环境变量，纳入 0066 清理。
- 状态：待处理
- 来源报告：audit_20261019.md

### AUDIT-0081（2026-10-19）image_provider _download_image 递归无深度限制
- 涉及文件：core/image_provider.py:98-135
- 严重程度：低
- 问题：重定向 URL 直接递归，无深度/循环检测，成环则栈溢出。
- 建议：加 depth 或 visited。
- 状态：待处理
- 来源报告：audit_20261019.md

### AUDIT-0082（2026-10-19）freeai provider id 字符串集合重复维护
- 涉及文件：core/image_provider.py:366-389（:45）
- 严重程度：低
- 问题：链/判断/取 key 三处 id 集合不一致。
- 建议：统一常量。
- 状态：待处理
- 来源报告：audit_20261019.md

### AUDIT-0083（2026-10-19）subtitle_render 重写残留重复模块头/import
- 涉及文件：core/subtitle_render.py:14-20 与 :23-45
- 严重程度：低
- 建议：删重复 docstring/import。
- 状态：待处理
- 来源报告：audit_20261019.md

### AUDIT-0084（2026-10-19）download_video 读 FileSorter 私有 _output_dir
- 涉及文件：core/download.py:531
- 严重程度：低
- 建议：FileSorter 暴露 get_output_root 或用 get_output_dir。
- 状态：待处理
- 来源报告：audit_20261019.md

### AUDIT-0085（2026-10-19）_do_download 每轮重试双发 extract_info
- 涉及文件：core/download.py:657-658,820
- 严重程度：低
- 问题：单轮 2 次信息请求，3 轮最多 6 次，放大 bot 检测面。
- 建议：预取结果在重试间缓存。
- 状态：待处理
- 来源报告：audit_20261019.md

### AUDIT-0086（2026-10-19）mobile.html 队列池/错误 innerHTML 未 esc
- 涉及文件：web/static/mobile.html:406,475
- 严重程度：低
- 问题：j.title 与 snap.errors 未转义直接入 innerHTML（文件 :501 已有全局 esc，此两处漏用）。
- 建议：统一 esc。
- 状态：待处理
- 来源报告：audit_20261019.md

### 当日修复记录（2026-10-19 手动修复，验证日期 2026-10-19）

> 用户授权仅修复本次新发现 0077～0086 共 10 条；未触碰任何旧条目。以下为修复方式、最终文件:行号证据与验证结果。

| 编号 | 最终状态 | 改动文件 | 修复方式（关键改动） | 最终文件:行号证据 | 验证结果 |
|---|---|---|---|---|---|
| 0077 | 已修复 | core/download.py | `_abort_incomplete` 增加 `permanent` 参：无视频流/缺音频致合并不完整两处改 `permanent=True`→抛 `PermanentDownloadError`；未产出文件保持默认 RuntimeError | download.py:875-886（:889 瞬时、:896-900/:915-918 永久）；:35 定义、:584 捕获 | py_compile 通过；异常语义逐条复核 |
| 0078 | 已修复 | core/image_provider.py | 从 PROVIDER_CHAIN 移除 pollinations 节点（链 3→2）；call_pollinations 保留并在 docstring 标注 T2I 专用/已移出图生图链 | image_provider.py:330-336（docstring）、:385-389（链） | py_compile 通过；链节点仅 free.ai/rewind |
| 0079 | 已修复 | start_all.bat、start_tunnel.bat、web/wake.html | start_all 改走 GUI 内嵌 main_gui.py（去掉 web.watchdog）；start_tunnel 改废弃说明（无 cloudflared 调用）；wake.html 死 fetch 改现行 :8000 /api/health 与 /api/server/health | start_all.bat:24；start_tunnel.bat:13-16；wake.html:150,162 | bat 无残留调用（仅注释）；wake.html 无 :8001 死调用 |
| 0080 | 已修复 | scripts/test_mqtt.py（由 _test_mqtt.py 移动） | 硬编码 key 改 `os.environ.get("VC_WEB_API_KEY","")`，缺失则提示退出；broker/端口走环境变量带默认值；脚本移入 scripts/ 去下划线 | scripts/test_mqtt.py:5-12、36-43、72 | py_compile 通过；旧路径已删、新路径存在；无其他文件引用 |
| 0081 | 已修复 | core/image_provider.py | `_download_image` 加 `depth` 参（默认 0，>3 记 warning 返回 None），两处递归传 depth+1 | image_provider.py:104（签名）、:110-112（截断）、:133/:140（递归） | py_compile 通过 |
| 0082 | 已修复 | core/image_provider.py | 新增模块常量 `FREEAI_PROVIDER_IDS=frozenset`，`_get_freeai_key` 与分支判断均引用同一常量 | image_provider.py:38（定义）、:51、:406 | py_compile 通过 |
| 0083 | 已修复 | core/subtitle_render.py | 合并重复的 docstring/import 为一份（保留两段独有注释，import 取超集），核对被删段无独有符号 | subtitle_render.py:1-26 | py_compile 通过；tempfile/List/Tuple 引用均被覆盖 |
| 0084 | 已修复 | utils/file_sort.py、core/download.py | FileSorter 增加公共只读方法 `get_output_root()`；download.py:531 不再访问私有 `_output_dir` | file_sort.py:48-53；download.py:531 | py_compile 通过 |
| 0085 | 已修复 | core/download.py | 重试循环前建 `prefetch_cache` 并透传；预取成功 info 缓存复用、跳过重复 download=False，预取失败不缓存仍重试 | download.py:582,585,625,661-662,670-671 | py_compile 通过；保留预取失败继续下载行为 |
| 0086 | 已修复 | web/static/mobile.html | 队列池标题（当前/待发布）与错误信息三处动态内容统一走全局 esc()，日志行用法不变 | mobile.html:401,406,475（.map(esc)） | esc 定义:501 与调用闭合、JS 括号/模板串核对通过 |

**集中验证结果（D:\Ideas\VideoCrawler\Vc，项目 python）**：
- `python -m py_compile core/download.py core/image_provider.py core/subtitle_render.py utils/file_sort.py scripts/test_mqtt.py` → **全部通过（PY_COMPILE_ALL_OK）**。
- import 冒烟 `import core.download / core.image_provider / core.subtitle_render`：本机系统 Python 缺第三方依赖 `loguru`（连带 yt_dlp），在 utils/logger.py:15 处中断——**属预先存在的环境缺依赖、非本次改动引入**；按约束不新增依赖。建议在装齐依赖的环境再跑一次 import 冒烟。
- 未新增依赖、未改 requirements、未动 config.yaml、未执行 git 提交；除移动 `_test_mqtt.py` 外未删除/重命名任何文件。
- 旧条目（0056/0059/0065/0001/0058 等）按要求**一律未动**，仍为原状态。

---

## 2026-10-20 每日审核补跑（09:05 定时任务失败，手动补跑）

### 当日确认修复（MainAgent 手动修复，组织者独立回代码复核）

#### AUDIT-0056（高）→ 已修复
- 证据：`core/subtitles/processor.py:33-35` 在 translator import（:32）之后补：
  - `from core.subtitles.embedder import VideoSubtitleEmbedder`（:34）
  - `from core.subtitles.quality_gate import SubtitleQualityGate`（:35）
- 实例化可解析：`__init__` 中 `self._embedder = VideoSubtitleEmbedder()`（:55）、`self._quality_gate = SubtitleQualityGate()`（:56）。
- import 链完整：subtitles 包内 grep 无任何模块 import processor，无循环依赖；embedder/quality_gate 自身导入链独立。
- 验证：`python -m py_compile core/subtitles/processor.py` 通过。

#### AUDIT-0059（高）→ 已修复
- 证据：`utils/db/video_repo.py:8-9` 补 `import os`、`import time`；`utils/db/task_repo.py:7` 补 `import time`（task_repo 无 os. 调用，无需 import os）。
- 调用点可解析：video_repo `:215 os.path.exists(local_path)`、`:458 int(time.time())`；task_repo `:178 int(time.time())`。
- 验证：`python -m py_compile utils/db/video_repo.py utils/db/task_repo.py` 通过；补 import 位于 stdlib 顶部、无重复无顺序问题。

#### AUDIT-0065（中）→ 已修复
- 证据：`web/static/index.html:445-447` 已将 `esc()` 提升为 `<script>` 顶层函数；loadVideos 内的局部定义已删除（全文件 `function esc` 仅 :445 一处）。
- 调用点作用域可达（共 12 处）：视频库 :659-660、loadPool :692-696、loadAccounts :723、onPubAccountChange :739、loadRecords :885-889。
- 无重复定义、无 TDZ；esc 内 `?? ''` 兜底。
- 验证：经组织者 grep 逐点核对；该文件已通过 node --check（用户侧）。

### 防回退抽查（0077～0086）—— 未回退
- download.py：永久分支 `raise PermanentDownloadError`（:884-886）、两处 permanent=True（:899/:917）、prefetch_cache（:582、:661-671）、:531 改调 get_output_root 均在。
- image_provider.py：链仅 free.ai/rewind、call_pollinations docstring、depth 参（:104/:110/:133/:140）、FREEAI_PROVIDER_IDS（:38/:51/:406）均在。
- mobile.html：:401/:406 esc、:475 .map(esc)、esc 定义 :501 均在。
- scripts/test_mqtt.py：:5-9 env key+缺失退出、:11-12 broker env；根目录无 _test_mqtt 残留。

### 新发现
- 自 2026-10-19 22:14 以来业务代码仅上述 4 个文件变更（即 3 处修复），逐一核查修复**未引入新问题**（无重复 import、无循环依赖、无作用域/TDZ、无遗漏符号）。**本轮无新增条目（无 AUDIT-0087）。**

### 最新完成率（口径：已修复 / 全部非「已确认不处理」）
- 已修复 39（原 36 + 本轮 0056/0059/0065）；处理中 17；待处理 26；已确认不处理 4。
- 分母 86−4 = 82；完成率 = 39/82 = **47.6%**（10-19 为 36/82 = 43.9%）。

---

## 2026-10-21 每日审核（定时任务正常触发）

### 当日重大发现：批量写入造成回退 + 编码损坏

#### AUDIT-0087（高）→ 5 个第一方文件被写入双重 UTF-8 BOM，py_compile 失败
- 涉及文件（首 6 字节均为 `EF BB BF EF BB BF`，即两个 BOM 叠加）：
  - `web/main.py`（Web 服务入口，first 12 bytes = 239,187,191,239,187,191,34,34,34,13,10,86）
  - `core/spiders/youtube_spider.py`（核心爬虫，78,742 B）
  - `core/classify.py`（分类器，被 download/pipeline 导入）
  - `core/cdp_cookies.py`（CDP cookies，被 download 导入）
  - `core/publish/storage.py`（发布存储）
- 证据：上述 5 文件 `python -m py_compile` 全部 `SyntaxError: invalid non-printable character U+FEFF`（exit 1）。第一个 BOM 被当作 UTF-8 签名消费，第二个 BOM 成为源码首字符 U+FEFF，Python 3.14 拒绝。
- 影响：web 服务、YouTube 爬虫、分类、CDP、发布存储在当前解释器下**无法导入/启动**。
- 修复建议：删除每个文件头部多余 BOM（保留 0 或 1 个；规范为无 BOM UTF-8）。
- 备注：根目录 `bom_test.py`（20B，内容为字面 `X = 1\nprint(X)\n`）是诊断用临时文件，非架构文件，未计入；其单 BOM 但内容本身非法。

#### AUDIT-0088（中）→ 外部批量写入覆盖工作区，download.py 被整体还原
- 证据：今日 08:54-08:56 全项目文件被批量触碰；`core/download.py`（08:56）被还原到 10-19 修复前版本：
  - `:531` 回到 `base = file_sorter._output_dir`（私有访问）；
  - `:865-870` `_abort_incomplete(reason)` 无 permanent 形参、仅 `raise RuntimeError`；
  - 全文件 grep `prefetch_cache`/`permanent`/`get_output_root` = 0 命中。
- 影响：0077/0085/0084 三条已修复条目回退（见总表状态改回）。
- 关键待办：**先定位覆盖源**（IDE 旧缓冲覆盖 / 同步工具 / 外部脚本），否则重新应用的修复会被再次覆盖。
- 注：`utils/file_sort.py` 的 `get_output_root()`（:48-53）仍在（该文件 mtime 停在 10-19 22:09，未被覆盖），但 download.py 已不调用，暂时成孤儿方法。

### 防回退抽查（其余已修复条目）—— 均未回退
- 0056（processor.py:33-35 import、:55-56 实例化）、0059（video_repo:8-9、task_repo:7）、0065（index.html:445 顶层 esc）、0078/0081/0082（image_provider）、0086（mobile.html）、0080（scripts/test_mqtt）均保持在位。

### 新状态分布与完成率
- 总条目 88（0001-0088）：**已修复 36、处理中 17、待处理 31、已确认不处理 4**。
- 校验：36+17+31+4 = 88 ✓。
- 完成率 = 已修复 /（88 − 4）= **36/84 = 42.9%**（10-20 为 47.6%，因 0077/0085/0084 回退 + 新增 0087/0088 而下降）。

---

## 2026-10-23 每日审核（定时任务正常触发）

### 背景
用户于 10-23 完成大批修复并提交还原点 `989cb02`（详见 `docs/修改记录.md`）：修复 10-21 外部覆盖损伤（0087/0088）+ 批量落地 16 项待修条目 + 仓库卫生（config.yaml 移出跟踪、output/bin/tools 清索引）。MainAgent 已独立核验 PAT/gitignore/随机 key 持久化；4 分片按"问题实质回代码复核"逐条抽查防伪，全部真实到位。

### 新发现（AUDIT-0089～0091）

#### AUDIT-0089【高·紧急】GitHub 远端 URL 内嵌明文 PAT
- 证据：`.git/config:12` = `url = https://ghp_SP****（已脱敏，待轮换）@github.com/nanana40/VideoCrawler.git`（fetch/push 同址，主线程独立读取确认）。
- 影响：PAT 以明文存于仓库配置，仓库目录若被同步/备份即泄露；修改记录确认其已出现在终端日志。
- 建议：GitHub → Settings → Developer settings → Personal access tokens 撤销重发；随后 `git remote set-url` 更新；再推送还原点完成异地备份（修改记录待办 1/3）。

#### AUDIT-0090【中】Web API key 无持久化，重启即更换
- 证据：`gui/web_host.py:41-46` `DEFAULT_API_KEY = _resolve_api_key()` 模块加载时 `token_urlsafe(24)` 随机生成、:206 `setdefault` 注入 env；`web/main.py:45` 独立 `token_urlsafe(16)` 兜底。单次运行内两处一致（setdefault 保证），但**不落盘**：每次启动 GUI 都重新随机；对比 mqtt_bridge 的 token 持久化在 `data/mqtt_device.json`，web key 无对应持久文件。
- 影响：旧的手机端 `?key=xxx` 书签、MQTT 二维码在 GUI 重启后全部失效，用户每次重启需从日志重新拷贝 key（可用性回退）。
- 建议：首次生成后持久化到 `data/web_api_key`（与 mqtt_device.json 同模式），或文档明确要求用户 `set VC_WEB_API_KEY` 固定。

#### AUDIT-0091【中】989cb02 将诊断脚本/产物提交入库
- 证据：`git show 989cb02 --stat` 确认 `_diag_xhs.py`（+153）、`_diag_xhs2/3.py`、`_fix_cookies.py`、`_show_diag.py`、`_diag_result.json`（+268，含本地视频绝对路径与 cookie 长度等运行信息）、`_diag_screenshot.png`（77KB 二进制）共 7 个诊断文件入库。
- 影响：调试产物污染仓库根目录（0066 形态从"散落未跟踪"变为"入库"）；后续诊断更新产生无意义 diff；`_diag_result.json` 含路径信息。
- 建议：`_diag_*.py`/`_fix_cookies.py`/`_show_diag.py` 移入 `scripts/diag/`；`_diag_result.json`/`_diag_screenshot.png` 补 .gitignore 并 `git rm --cached`。

### 修复核验（989cb02，全部真实到位）

**编码/回退损伤（2 项）：**
- 0087：5 文件（web/main.py、youtube_spider.py、classify.py、cdp_cookies.py、storage.py）首 3 字节均 `34,34,34`（`"""`）无 BOM，py_compile 全过；bom_test.py 已删。
- 0088：download.py 三处重新应用——0077 `:35` 定义、`:890-892` `if permanent: raise PermanentDownloadError`、`:905/:923` permanent=True、`:895` 未产出文件保留 RuntimeError（分类边界正确）；0084 `:531` = `get_output_root()`；0085 `:583` 初始化、`:661-662` 命中复用、`:668-669` 成功才写。

**烧录与下载稳定性（4 项）：**
- 0060+0030：subtitle_render.py:489-519 daemon 线程 + stderr_q 轮询（0.5s）、deadline 到点 `proc.kill()` + `raise TimeoutExpired`（不再死代码）。
- 0018：download.py:833 `download_success=False`（try 外预赋值，finally 无 NameError）、:963 成功置位、:977-980 finally 清理 tmp → **转已修复**。
- 0019：download.py:1072-1085 持锁清理+检查+登记、出锁后 :1085 start() → **转已修复**。
- 0048（子项）：youtube_spider.py:91 `_probe_cache_max=1024`、:94-100 持锁淘汰最早一半；去重仅 YouTube 子项仍开放。

**Web/远程安全（4 项）：**
- 0058：web_host.py:37-46 无 `VideoCrawler2026` 回落（token_urlsafe(24)）、:172 默认 127.0.0.1+VC_WEB_HOST；全仓 grep 弱 key 零残留 → **转已修复**。
- 0064：web/main.py:15 import sys、:636-642 restart 改 503 提示、grep `os._exit` 零命中 → **转已修复**。
- 0012（部分）：health 脱敏 `_mask_key`（:174-175,:626,:631-632）；**/api/stop cancel 未做**（:502-508 仍仅 push_log；pipeline 无取消入口）→ 保持处理中。
- 0053：web/ 5 个隧道日志已删 → **转已修复**。

**服务健壮性（7 项）：**
- 0062：publish_queue.py:173-203 跳过扫描，立即任务不再被队首定时任务阻塞 → **转已修复**。
- 0067：storage.py:28-29 WAL+busy_timeout=5000 → **转已修复**。
- 0044：task_scheduler.py:349,:360 `replace_existing=True` → **转已修复**。
- 0061：pipeline.py:163 `get_output_dir()` → **转已修复**。
- 0063：xhs_api_client.py:38-57 try/except 懒加载 + `_ensure_xhs_cli()` 中文报错 → **转已修复**。
- 0068：cdp_cookies.py:148-155 try/finally close、:207-211 WebSocket close → **转已修复**。
- 0069：models.py:1-13 文件头合并、删 10 个 unused import → **转已修复**。
- 0070：embedder.py:33、processor.py:40 悬空 @dataclass 已删 → **转已修复**。

**仓库卫生（2 项）：**
- 0001（git 层面）：config.yaml 移出跟踪（`git ls-files config.yaml` 空）、.gitignore:94 覆盖；磁盘明文仍在、云轮换+build_gui.bat:83 拷贝未做 → **转处理中**。
- 0004：output/bin/tools/models/data 索引清零 → **转已修复**。

**防回退（在位）：** 0056、0059、0065、0078/0081/0082、0086、0080 均未回退。

### 待办（修改记录第五节 → 路线图/条目映射）
1. GitHub PAT 轮换 → **AUDIT-0089**（紧急，用户操作）。
2. 云密钥轮换 → 0001 收口（用户操作 + 代码侧加密迁移）。
3. 推送还原点 → 依赖 0089 完成后执行（用户操作）。
4. /api/stop 补 cancel → 0012 剩余（需先设计 pipeline 取消机制）。
5. 结构性大拆（0013/0014/0035）→ 路线图阶段 4（先建测试网）。

### 新状态分布与完成率
- 总条目 91（0001-0091）：**已修复 57、处理中 13、待处理 17、已确认不处理 4**。
- 校验：57+13+17+4 = 91 ✓。
- 完成率 = 已修复 /（91 − 4）= **57/87 = 65.5%**（10-21 为 42.9%，本轮 +18 项转已修复、+3 项新增）。
- 本轮转已修复：0004、0018、0019、0030、0044、0053、0058、0060、0061、0062、0063、0064、0067、0068、0069、0070、0077、0084、0085、0087、0088（21 项）；0001、0066 转处理中。
- 仍待处理高/中危：0089（PAT，紧急）、0001（云轮换收口）、0012（/api/stop cancel）、0013/0014（大文件）、0034/0035（编排/God Class）、0037/0038/0041（配置/依赖/测试）、0066+0091（诊断入库）、0073（MQTT token 广播）、0090（key 持久化）。

---

## 2026-10-26 每日审核（定时任务正常触发）

### 基线
业务代码**零变动**（git HEAD 仍 `989cb02`，工作区仅 docs/audit 未提交 + `docs/修改记录.md` 未跟踪）。10-23 三条新发现全部待处理，本轮逐一确认。

### 新发现（AUDIT-0092～0095，代码零变动下从新维度切入）

#### AUDIT-0092【中】build_gui.spec 未覆盖 web/，且 excludes 明确排除其运行栈
- 证据：`build_gui.spec:20` hiddenimports 仅 core/utils/gui、`:49` datas 无 web；`:92-95` excludes 明确排除 `uvicorn/fastapi/starlette`；引用链全为函数内延迟导入（web_host.py:222,350、main_window.py:323,355）；web/static/ 不在 datas。
- 影响：GUI 打包后内嵌 Web 远程/MQTT 功能运行时缺失（web 模块、静态页、FastAPI 栈均无）。
- 建议：spec 加 `"web"`（含 web/static），excludes 移除 uvicorn/fastapi/starlette。

#### AUDIT-0093【中】task_scheduler.py 顶层 import psutil 未声明
- 证据：`core/task_scheduler.py:20` `import psutil`（模块顶层）；requirements-runtime.txt 无 psutil（grep 0 命中），非传递依赖。
- 影响：干净环境按 requirements-runtime.txt 安装后 import 调度器即 ModuleNotFoundError。
- 建议：requirements-runtime.txt 补 `psutil>=5.9.0`。

#### AUDIT-0094【低】httpx 已用未声明（顶层一处、惰性两处）
- 证据：`xhs_api_client.py:34` 顶层 `import httpx`（0063 懒加载 :38-47 仅保护 xhs_cli）；`gemini_engine.py:326,392` 惰性 import；requirements-runtime.txt 与 build_gui.spec hiddenimports 均无 httpx。
- 建议：requirements 补 `httpx>=0.27.0`，打包清单同步。

#### AUDIT-0095【低】README 与代码脱节
- 证据：README.md:271/:77 入口写 main.py（实为 main_gui.py，start_gui.bat 指向）、web 远程功能零文档、:35-85 目录树过时、:29 PyInstaller vs :78 Nuitka 矛盾、:20 Python 3.11+ vs 实际 3.14。
- 建议：补 main_gui.py 入口与 web 远程章节、修正目录树/打包工具描述。

### 核查确认（不编号，既有条目细化）
- config.yaml 明文密钥与 providers/section key 双源 → 0001/0031 既有内容。
- DEFAULT_CONFIG 缺 6 顶层字段（translation_engine/providers/function_models/skip_probe/unskip_probe/subtitle_style）+ 3 个 model_chain → 0037 既有内容。
- localStorage 缓存旧 key × 重启换 key 叠加 → 并入 0090 影响说明。
- schema.sql 5 表 vs db_manager/repos/storage 访问：**完全一致，无孤儿表**。
- .gitignore vs 实际跟踪：**一致无遗漏**（config.yaml/output/bin/tools/models/data 均 ignore 且未跟踪）。

### 10-23 三条新发现状态确认
- 0089：`.git/config:12` PAT 仍在 → 待处理（紧急，用户操作）。
- 0090：web_host.py:41-46/:206、web/main.py:45 随机 key 无持久化仍成立；index.html:455,471 localStorage 放大 401 → 待处理。
- 0091：7 个诊断文件仍在根目录且被跟踪 → 待处理。

### 防回退抽查（均在位）
0056/0059/0065、0078/0081/0082、0086、0080、0053、0058、0064、0043、0045。

### 新状态分布与完成率
- 总条目 95（0001-0095）：**已修复 57、处理中 13、待处理 21、已确认不处理 4**。
- 校验：57+13+21+4 = 95 ✓。
- 完成率 = 已修复 /（95 − 4）= **57/91 = 62.6%**（10-23 为 65.5%；状态零变化，分母因新增 4 条扩大）。
- 本轮无转已修复、无转处理中；新增 0092/0093/0094/0095 均待处理。
