# 项目进度与开发计划

> 本文档记录 MultiLangVideoCrawler 项目的当前完成状态、已交付物料、5 周开发计划与下一步任务。
> AI 助手接手时，**请先阅读本文档**了解进度，再开始开发。

---

## 一、项目总览

| 项目 | 内容 |
|:---|:---|
| 项目名称 | MultiLangVideoCrawler（多语言视频爬虫） |
| 技术栈 | Python 3.11+ / SQLite / curl_cffi / yt-dlp / Gradio / Nuitka |
| 运行平台 | Windows |
| 开发周期 | 5 周 |
| 当前阶段 | 第 0 周 — 项目初始化物料完成 |
| 下一阶段 | 第一周 — 爬虫基建（反爬 curl_cffi + 语种过滤） |

---

## 二、已完成物料清单（第 0 周）

### ✅ 2.1 目录结构

完整目录骨架已建立（共 14 个目录）：

```
MultiLangVideoCrawler/
├─ resources/        ✅ 静态资源目录
├─ core/             ✅ 核心业务层（待开发）
├─ utils/            ✅ 工具层（部分完成）
├─ webui/            ✅ WebUI 层（待开发）
├─ bin/              ✅ 外置二进制目录（需手动放入 exe）
├─ tests/            ✅ 单元测试目录（待开发）
├─ data/             ✅ 数据库目录
├─ tmp/              ✅ 临时缓存目录
├─ output/           ✅ 成品输出目录
├─ translate_queue/  ✅ 待翻译字幕中转目录
├─ finished_sub/     ✅ 翻译完成字幕缓存目录
├─ logs/             ✅ 日志目录
└─ .trae/rules/      ✅ AI 助手规则目录
```

### ✅ 2.2 utils/enums.py — 全局枚举

**状态**：已完成，可直接使用

**包含内容**：
- 6 个枚举类：
  - `TaskStatus(IntEnum)` — 任务状态机（7 个状态）
  - `LanguageType(StrEnum)` — 视频源语种（de/fr/es）
  - `VideoCategory(StrEnum)` — 视频题材分类（4 类）
  - `LogTag(StrEnum)` — 日志分类标签（4 类）
  - `SubtitleMode(StrEnum)` — 字幕对接模式（api/folder）
  - `TaskPriority(IntEnum)` — 任务优先级（normal/high）
- `BaseEnumMixin` 通用工具方法：
  - `is_valid(value)` — 合法性校验
  - `from_code(code, default)` — 安全转换
  - `from_int(value, default)` — 整数转换
  - `from_db(db_value, default)` — 数据库值转换
  - `.display_name` — 中文展示名
  - `.is_final` — 终态判断
- `TaskStatus.can_transition_to(target)` — 状态流转合法性校验
- 完整类型注解 + 中文 docstring

**验证**：语法验证通过，枚举值与 SQL 字段一一对应

### ✅ 2.3 utils/path_helper.py — 路径管理工具

**状态**：已完成，可直接使用

**包含内容**：
- 自动识别开发环境 / Nuitka 打包环境
- 16+ 个路径函数：
  - 核心目录：resources/bin/data/tmp/output/logs/...
  - 配置文件：config.yaml / api_secret.yaml.enc
  - 数据库：video_tasks.db / schema.sql
  - 二进制：ffmpeg.exe / yt-dlp.exe
  - 日志：按标签获取日志文件路径
- 临时文件工具：`make_tmp_file()` / `clear_tmp_dir()`
- 运行环境检测：`is_frozen()` / `get_runtime_info()`
- `_ensure_dir()` — 目录不存在自动创建

**验证**：功能验证通过，路径正确

### ✅ 2.4 resources/schema.sql — 数据库建表脚本

**状态**：已完成，可直接使用

**包含内容**：
- 2 张核心表：
  - `video_info` — 视频基础信息主表（含 is_downloaded 标记、自动时间戳）
  - `translate_task` — 翻译任务表（默认 status=3 DOWNLOADED）
- 死信通过 `status=7 (DEAD_LETTER)` 标识，不单独建表
- 新增字段：`subtitle_path` / `fail_reason` / `dead_letter_ts` / `timeout_ts`
- CHECK 约束：status / priority / lang / is_downloaded / retry_count
- 2 个触发器：自动更新 update_ts 时间戳
- 外键 `ON DELETE CASCADE` 级联删除
- 9 条索引（覆盖全场景查询）
- 详细字段注释

**验证**：sqlite3 executescript 执行通过

### ✅ 2.5 config.yaml — 全局业务配置

**状态**：已完成

**包含 7 大配置模块**：
- `crawler` — 爬虫配置（TLS 指纹、延时、页数、UA 池、代理）
- `download` — 下载配置（线程数、输出目录、外置二进制路径）
- `db_buffer` — 数据库缓冲配置（批量阈值、刷盘间隔）
- `subtitle` — 字幕翻译配置（模式、API、并发、超时、目录）
- `scheduler` — 调度器配置（内存告警、自动清理）
- `log` — 日志配置（根目录、级别）
- `classify` — AI 分类配置（API 地址、缓存时长）

### ✅ 2.6 requirements 依赖清单

**状态**：已完成，拆分两份

| 文件 | 说明 | 数量 |
|:---|:---|:---:|
| `requirements-runtime.txt` | 运行时最小依赖（不含打包/类型检查） | 10 个 |
| `requirements-dev.txt` | 开发全量依赖（runtime + types + mypy + nuitka） | 13 个 |

**runtime 依赖**：pyyaml / pydantic / loguru / cryptography / apsw / curl_cffi / yt-dlp / APScheduler / watchdog / gradio

**dev 额外**：types-PyYAML / mypy / nuitka

**注意**：包名使用下划线 `curl_cffi`（非横杠 curl-cffi）

### ✅ 2.7 env_init.bat — Windows 一键初始化脚本

**状态**：已完成

**功能清单**：
- UTF-8 编码（chcp 65001）
- 强制 Python ≥ 3.11 版本校验，低版本直接终止
- 不使用 activate.bat，全部通过 `venv\Scripts\` 绝对路径调用
- 两种安装模式选择（1=runtime / 2=dev）
- 内置清华镜像源加速下载
- bin 目录预检（ffmpeg.exe / yt-dlp.exe 缺失提前警告）
- 自动创建/复用虚拟环境
- 升级虚拟环境内部 pip
- 完整错误捕获，失败窗口 pause 停留

### ✅ 2.8 .gitignore — 版本控制忽略

**状态**：已完成

**忽略内容**：venv / *.pyc / __pycache__ / data/*.db / logs/*.log / tmp/ / bin/*.exe / api_secret.yaml.enc / .idea/ / .vscode/ / build/ / dist/ 等

### ✅ 2.9 项目交接文档

| 文档 | 状态 |
|:---|:---:|
| `README.md` — 项目主文档 | ✅ |
| `.trae/rules/project_rules.md` — AI 助手行为规范 | ✅ |
| `PROJECT_STATUS.md` — 本文档 | ✅ |

---

## 三、5 周开发计划

### 第一周：爬虫基建（反爬 curl_cffi + 语种过滤）

| 天 | 任务 | 产出 | 状态 |
|:---:|:---|:---|:---:|
| Day1 | utils/logger.py Loguru 分文件日志 + 日志滚动 | logger.py + 测试 | ⏳ |
| Day2 | utils/db_manager.py SQLite + apsw 内存缓冲写入池、初始化建表 | db_manager.py + 测试 | ⏳ |
| Day3 | utils/language_check.py 语种识别工具 | language_check.py + 测试 | ⏳ |
| Day4 | core/crawler.py curl_cffi 指纹爬虫封装（UA 轮换、延时、代理） | crawler.py + 测试 | ⏳ |
| Day5 | 爬虫分页采集、结果临时缓冲 | crawler.py 增强 | ⏳ |
| Day6 | 全量爬虫 demo 测试（德/法/西关键词检索过滤） | demo 脚本 + 测试报告 | ⏳ |
| Day7 | 代码整理、修复反爬拦截问题 | 优化后的 crawler.py | ⏳ |

### 第二周：AI 分类 + 内存缓冲数据库完整层

| 天 | 任务 | 产出 | 状态 |
|:---:|:---|:---|:---:|
| Day1 | core/classify.py 在线 API 文本分类、缓存机制 | classify.py + 测试 | ⏳ |
| Day2 | db_manager 内存写入缓冲池、批量事务、优雅退出刷盘 | db_manager.py 增强 | ⏳ |
| Day3 | 两张数据表完整 CRUD 封装、状态枚举绑定数据库字段 | db_manager.py 完整 CRUD | ⏳ |
| Day4 | 数据自动入库流程：爬虫采集→AI 分类→写入缓冲池入库 | 集成测试 | ⏳ |
| Day5 | 过期数据自动清理工具函数 | 清理工具函数 | ⏳ |
| Day6 | 全链路测试：抓取-分类-入库完整流程 | 全链路测试报告 | ⏳ |
| Day7 | 优化 SQLite 锁冲突、批量写入性能测试 | 性能优化 | ⏳ |

### 第三周：yt-dlp 下载 + 分层归档 + 自动生成翻译任务

| 天 | 任务 | 产出 | 状态 |
|:---:|:---|:---|:---:|
| Day1 | core/download.py yt-dlp 封装、外置 bin 路径适配、下载进度回调 | download.py + 测试 | ⏳ |
| Day2 | utils/file_sort.py 自动分层文件夹、标准化视频/字幕命名 | file_sort.py + 测试 | ⏳ |
| Day3 | 下载完成后自动创建 translate_task，状态置为 DOWNLOADED(3) | 集成逻辑 | ⏳ |
| Day4 | 多线程下载池限速、下载失败重试逻辑 | 下载池 | ⏳ |
| Day5 | 下载全流程测试，自动归档 output 分层目录 | 测试报告 | ⏳ |
| Day6 | utils/queue_manager.py 任务队列基础实现（重试次数控制） | queue_manager.py | ⏳ |
| Day7 | 压力测试批量下载，数据库状态同步校验 | 压力测试报告 | ⏳ |

### 第四周：核心调度、字幕对接、看门狗、文件监控、WebUI 字幕面板

| 天 | 任务 | 产出 | 状态 |
|:---:|:---|:---|:---:|
| Day1 | core/subtitle_trans.py 外部翻译 API 提交、任务 id 获取 | subtitle_trans.py | ⏳ |
| Day2 | core/task_scheduler.py 后台线程调度、ping 健康看门狗告警 | task_scheduler.py | ⏳ |
| Day3 | watchdog 文件监控、动态静默期防文件截断、字幕自动归档 | 文件监控逻辑 | ⏳ |
| Day4 | queue_manager 完善死信队列逻辑、失败任务自动迁移 | 死信逻辑 | ⏳ |
| Day5 | webui/subtitle_panel.py 字幕任务可视化、批量操作、死信管理 | subtitle_panel.py | ⏳ |
| Day6 | API 对接/文件夹中转双模式完整联调 | 联调测试 | ⏳ |
| Day7 | 全链路闭环测试：抓取→下载→自动入翻译队列→监控字幕入库 | 全链路测试报告 | ⏳ |

### 第五周：一体化 UI、容错、加密、Nuitka 打包、文档终测

| 天 | 任务 | 产出 | 状态 |
|:---:|:---|:---|:---:|
| Day1 | 全局异常捕获、内存监控告警、线程资源隔离 | 容错增强 | ⏳ |
| Day2 | webui/main_panel.py 整合所有功能一体化界面 | main_panel.py | ⏳ |
| Day3 | utils/crypto_util.py 密钥配置文件加密解密 | crypto_util.py | ⏳ |
| Day4 | build.py Nuitka 打包脚本、外置 bin 二进制分离瘦身 | build.py | ⏳ |
| Day5 | 完整使用手册、故障排查文档 | 文档 | ⏳ |
| Day6 | 全新目录完整终测，模拟各种异常场景（断网、假死、文件损坏） | 终测报告 | ⏳ |
| Day7 | 代码归档、成品打包输出、项目交付 | 交付产物 | ⏳ |

---

## 四、文件状态总览

### utils 层（工具层）

| 文件 | 状态 | 说明 |
|:---|:---:|:---|
| [enums.py](utils/enums.py) | ✅ 已完成 | 全局枚举 + 工具方法 |
| [path_helper.py](utils/path_helper.py) | ✅ 已完成 | 路径管理工具 |
| logger.py | ⏳ 待开发 | Loguru 分文件日志（第一周 Day1） |
| db_manager.py | ⏳ 待开发 | SQLite 内存缓冲池（第一周 Day2） |
| language_check.py | ⏳ 待开发 | 语种识别（第一周 Day3） |
| queue_manager.py | ⏳ 待开发 | 任务队列（第三周 Day6） |
| file_sort.py | ⏳ 待开发 | 文件归档（第三周 Day2） |
| crypto_util.py | ⏳ 待开发 | 加解密（第五周 Day3） |

### core 层（核心业务层）

| 文件 | 状态 | 说明 |
|:---|:---:|:---|
| crawler.py | ⏳ 待开发 | 反爬爬虫（第一周 Day4） |
| classify.py | ⏳ 待开发 | AI 分类（第二周 Day1） |
| download.py | ⏳ 待开发 | yt-dlp 下载（第三周 Day1） |
| subtitle_trans.py | ⏳ 待开发 | 字幕翻译（第四周 Day1） |
| task_scheduler.py | ⏳ 待开发 | 调度器（第四周 Day2） |

### webui 层

| 文件 | 状态 | 说明 |
|:---|:---:|:---|
| subtitle_panel.py | ⏳ 待开发 | 字幕任务面板（第四周 Day5） |
| main_panel.py | ⏳ 待开发 | 主面板（第五周 Day2） |

### 配置/脚本/文档

| 文件 | 状态 |
|:---|:---:|
| [config.yaml](config.yaml) | ✅ |
| [resources/schema.sql](resources/schema.sql) | ✅ |
| [requirements-runtime.txt](requirements-runtime.txt) | ✅ |
| [requirements-dev.txt](requirements-dev.txt) | ✅ |
| [env_init.bat](env_init.bat) | ✅ |
| [.gitignore](.gitignore) | ✅ |
| [README.md](README.md) | ✅ |
| [.trae/rules/project_rules.md](.trae/rules/project_rules.md) | ✅ |
| main.py | ⏳ 待开发 |
| build.py | ⏳ 待开发 |

---

## 五、给接手 AI 助手的操作指南

### 5.1 接手第一步（必做）

1. **读取规范**：打开 [.trae/rules/project_rules.md](.trae/rules/project_rules.md)，通读所有强制规范
2. **理解枚举**：打开 [utils/enums.py](utils/enums.py)，理解 6 个枚举类 + 工具方法 + 状态流转规则
3. **理解路径**：打开 [utils/path_helper.py](utils/path_helper.py)，熟悉所有路径函数
4. **理解数据**：打开 [resources/schema.sql](resources/schema.sql)，熟悉两张表结构 + 触发器 + 索引
5. **理解配置**：打开 [config.yaml](config.yaml)，熟悉 7 大配置模块
6. **确认进度**：阅读本文档，确认当前在哪一周、哪一天

### 5.2 开发顺序建议

严格按照 5 周计划推进，不要跳步。每完成一个模块，立即写对应的单元测试。

### 5.3 开发原则

- 每写一个文件，先确认依赖关系（core 只导入 utils）
- 每用一个状态/语种，必须用枚举，不许硬编码
- 每用一个路径，必须通过 path_helper，不许硬编码
- 每做一个 IO 操作，必须 try-except + 日志
- 每写一个公共函数，必须有类型注解 + docstring
- 完成后跑一遍自检清单（见 project_rules.md 第十一节）

### 5.4 下一步立即要做的事

> **第一周 Day1：开发 utils/logger.py**
>
> 目标：基于 Loguru 实现分文件日志，支持：
> - 按 LogTag 分文件输出（crawler.log / download.log / translate.log / error.log）
> - 日志滚动（按大小或按天）
> - 统一的日志格式（时间/级别/模块/消息）
> - 日志路径通过 path_helper 获取
> - 提供便捷的 logger 实例获取函数
> - 完整类型注解 + 中文 docstring

---

## 六、验收标准（每阶段完成后对照）

- [ ] 代码语法正确，无 import 错误
- [ ] 类型注解完整，mypy 检查通过（开发阶段）
- [ ] 单元测试通过
- [ ] 符合 .trae/rules/project_rules.md 所有规范
- [ ] 枚举使用正确，无硬编码数字/字符串
- [ ] 路径使用正确，无硬编码路径
- [ ] 异常处理完善，日志记录完整
- [ ] 数据库操作正确（写走缓冲、查直接读）
- [ ] 分层依赖正确，无循环导入
- [ ] 中文注释清晰，docstring 完整
