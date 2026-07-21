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
| 当前阶段 | 第一周完成 — 爬虫基建全部完成，进入第二周 AI 分类与数据库完善 |
| 下一阶段 | 第二周 — AI 分类 + 内存缓冲数据库完整层 + 核心模块骨架搭建完成 |

---

## 二、已完成物料清单

### ✅ 2.1 目录结构

完整目录骨架已建立：

```
MultiLangVideoCrawler/
├─ resources/        ✅ 静态资源目录（schema.sql）
├─ core/             ✅ 核心业务层（爬虫模块已完成）
│  └─ spiders/       ✅ 4个网站爬虫实现
├─ utils/            ✅ 工具层（全部完成）
├─ webui/            ⏳ WebUI 层（待开发）
├─ bin/              ⏳ 外置二进制目录（需手动放入 exe）
├─ tests/            ⏳ 单元测试目录（待开发）
├─ data/             ✅ 数据库目录
├─ tmp/              ✅ 临时缓存目录
├─ output/           ✅ 成品输出目录
├─ translate_queue/  ⏳ 待翻译字幕中转目录（待创建）
├─ finished_sub/     ⏳ 翻译完成字幕缓存目录（待创建）
├─ logs/             ✅ 日志目录
└─ .trae/rules/      ✅ AI 助手规则目录
```

### ✅ 2.2 utils 层（全部完成）

| 文件 | 状态 | 说明 |
|:---|:---:|:---|
| [enums.py](utils/enums.py) | ✅ | 6个全局枚举 + 工具方法 + 状态流转校验 |
| [path_helper.py](utils/path_helper.py) | ✅ | 16+路径函数 + 运行环境检测 + 临时文件管理 |
| [logger.py](utils/logger.py) | ✅ | Loguru 分文件日志 + 日志滚动 + 便捷函数 |
| [config_loader.py](utils/config_loader.py) | ✅ | 配置文件加载 + 7大配置模块便捷访问 |
| [db_manager.py](utils/db_manager.py) | ✅ | SQLite内存缓冲池 + apsw + WAL + 完整CRUD |
| [language_check.py](utils/language_check.py) | ✅ | Unicode字符特征语种识别 + 白名单过滤 |
| [queue_manager.py](utils/queue_manager.py) | ✅ | 任务队列管理 + 重试控制 + 死信队列 |
| [file_sort.py](utils/file_sort.py) | ✅ | 文件归档 + 自动分层文件夹 |
| [crypto_util.py](utils/crypto_util.py) | ✅ | 加解密工具 + 密钥配置文件加密 |

### ✅ 2.3 core 层（爬虫模块已完成）

| 文件 | 状态 | 说明 |
|:---|:---:|:---|
| [crawler.py](core/crawler.py) | ✅ | curl_cffi指纹爬虫 + 分页采集 + 结果缓冲 + 语言过滤 |
| [spiders/base_spider.py](core/spiders/base_spider.py) | ✅ | 视频爬虫抽象基类 |
| [spiders/youtube_spider.py](core/spiders/youtube_spider.py) | ✅ | YouTube爬虫（解析页面JSON数据） |
| [spiders/vimeo_spider.py](core/spiders/vimeo_spider.py) | ✅ | Vimeo爬虫（使用官方API） |
| [spiders/dailymotion_spider.py](core/spiders/dailymotion_spider.py) | ✅ | Dailymotion爬虫（使用官方API） |
| [spiders/bilibili_spider.py](core/spiders/bilibili_spider.py) | ✅ | Bilibili爬虫（解析页面数据） |
| [classify.py](core/classify.py) | ✅ | AI分类模块（在线API + 本地规则 + 缓存） |
| [download.py](core/download.py) | ✅ | 视频下载模块（yt-dlp封装 + 多线程下载池） |
| [subtitle_trans.py](core/subtitle_trans.py) | ✅ | 字幕翻译模块（API/文件夹双模式） |
| [task_scheduler.py](core/task_scheduler.py) | ✅ | 任务调度器（APScheduler + 健康检查） |

### ✅ 2.4 配置与脚本

| 文件 | 状态 | 说明 |
|:---|:---:|:---|
| [config.yaml](config.yaml) | ✅ | 7大配置模块（crawler/download/db_buffer/subtitle/scheduler/log/classify） |
| [resources/schema.sql](resources/schema.sql) | ✅ | 2张核心表 + 触发器 + 索引 |
| [requirements-runtime.txt](requirements-runtime.txt) | ✅ | 运行时最小依赖（10个） |
| [requirements-dev.txt](requirements-dev.txt) | ✅ | 开发全量依赖（13个） |
| [env_init.bat](env_init.bat) | ✅ | Windows一键初始化脚本 |
| [demo_crawler.py](demo_crawler.py) | ✅ | 全量爬虫测试Demo |
| [main.py](main.py) | ✅ | 统一入口文件 + 初始化流程 + 参数控制 |

### ✅ 2.5 在线测试验证

| 网站 | 视频数 | german | french | spanish |
|:---|:---:|:---:|:---:|:---:|
| YouTube | 210 | 48 | 91 | 71 |
| Vimeo | 10 | 10 | 0 | 0 |
| Dailymotion | 119 | 16 | 31 | 72 |
| Bilibili | 50 | 13 | 13 | 24 |
| **总计** | **389** | **87** | **135** | **167** |

---

## 三、5 周开发计划更新

### 第一周：爬虫基建（✅ 已完成）

| 天 | 任务 | 产出 | 状态 |
|:---:|:---|:---|:---:|
| Day1 | utils/logger.py Loguru 分文件日志 + 日志滚动 | logger.py + config_loader.py | ✅ |
| Day2 | utils/db_manager.py SQLite + apsw 内存缓冲写入池 | db_manager.py | ✅ |
| Day3 | utils/language_check.py 语种识别工具 | language_check.py | ✅ |
| Day4 | core/crawler.py curl_cffi 指纹爬虫封装 | crawler.py | ✅ |
| Day5 | 爬虫分页采集、结果临时缓冲 | crawler.py 增强 | ✅ |
| Day6 | 全量爬虫 demo 测试（德/法/西关键词检索过滤） | demo_crawler.py | ✅ |
| Day7 | 代码整理、修复反爬拦截问题 | Vimeo/Dailymotion/Bilibili修复 | ✅ |

### 第二周：AI 分类 + 内存缓冲数据库完整层

| 天 | 任务 | 产出 | 状态 |
|:---:|:---|:---|:---:|
| Day1 | core/classify.py 在线 API 文本分类、缓存机制 | classify.py + 测试 | ✅ |
| Day2 | db_manager 内存写入缓冲池、批量事务、优雅退出刷盘 | db_manager.py 增强 | ✅ |
| Day3 | 两张数据表完整 CRUD 封装、状态枚举绑定数据库字段 | db_manager.py 完整 CRUD | ✅ |
| Day4 | 数据自动入库流程：爬虫采集→AI 分类→写入缓冲池入库 | 集成测试 | ✅ |
| Day5 | 过期数据自动清理工具函数 | 清理工具函数 | ✅ |
| Day6 | 全链路测试：抓取-分类-入库完整流程 | 全链路测试报告 | ⏳ |
| Day7 | 优化 SQLite 锁冲突、批量写入性能测试 | 性能优化 | ⏳ |

### 第三周：yt-dlp 下载 + 分层归档 + 自动生成翻译任务

| 天 | 任务 | 产出 | 状态 |
|:---:|:---|:---|:---:|
| Day1 | core/download.py yt-dlp 封装、外置 bin 路径适配、下载进度回调 | download.py + 测试 | ✅ |
| Day2 | utils/file_sort.py 自动分层文件夹、标准化视频/字幕命名 | file_sort.py + 测试 | ✅ |
| Day3 | 下载完成后自动创建 translate_task，状态置为 DOWNLOADED(3) | 集成逻辑 | ⏳ |
| Day4 | 多线程下载池限速、下载失败重试逻辑 | 下载池 | ✅ |
| Day5 | 下载全流程测试，自动归档 output 分层目录 | 测试报告 | ⏳ |
| Day6 | utils/queue_manager.py 任务队列基础实现（重试次数控制） | queue_manager.py | ✅ |
| Day7 | 压力测试批量下载，数据库状态同步校验 | 压力测试报告 | ⏳ |

### 第四周：核心调度、字幕对接、看门狗、文件监控、WebUI 字幕面板

| 天 | 任务 | 产出 | 状态 |
|:---:|:---|:---|:---:|
| Day1 | core/subtitle_trans.py 外部翻译 API 提交、任务 id 获取 | subtitle_trans.py | ✅ |
| Day2 | core/task_scheduler.py 后台线程调度、ping 健康看门狗告警 | task_scheduler.py | ✅ |
| Day3 | watchdog 文件监控、动态静默期防文件截断、字幕自动归档 | 文件监控逻辑 | ⏳ |
| Day4 | queue_manager 完善死信队列逻辑、失败任务自动迁移 | 死信逻辑 | ✅ |
| Day5 | webui/subtitle_panel.py 字幕任务可视化、批量操作、死信管理 | subtitle_panel.py | ⏳ |
| Day6 | API 对接/文件夹中转双模式完整联调 | 联调测试 | ⏳ |
| Day7 | 全链路闭环测试：抓取→下载→自动入翻译队列→监控字幕入库 | 全链路测试报告 | ⏳ |

### 第五周：一体化 UI、容错、加密、Nuitka 打包、文档终测

| 天 | 任务 | 产出 | 状态 |
|:---:|:---|:---|:---:|
| Day1 | 全局异常捕获、内存监控告警、线程资源隔离 | 容错增强 | ⏳ |
| Day2 | webui/main_panel.py 整合所有功能一体化界面 | main_panel.py | ⏳ |
| Day3 | utils/crypto_util.py 密钥配置文件加密解密 | crypto_util.py | ✅ |
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
| [logger.py](utils/logger.py) | ✅ 已完成 | Loguru 分文件日志 |
| [config_loader.py](utils/config_loader.py) | ✅ 已完成 | 配置文件加载 |
| [db_manager.py](utils/db_manager.py) | ✅ 已完成 | SQLite内存缓冲池 + 完整CRUD |
| [language_check.py](utils/language_check.py) | ✅ 已完成 | 语种识别 |
| [queue_manager.py](utils/queue_manager.py) | ✅ 已完成 | 任务队列 + 重试控制 + 死信队列 |
| [file_sort.py](utils/file_sort.py) | ✅ 已完成 | 文件归档 + 自动分层文件夹 |
| [crypto_util.py](utils/crypto_util.py) | ✅ 已完成 | 加解密工具 |

### core 层（核心业务层）

| 文件 | 状态 | 说明 |
|:---|:---:|:---|
| [crawler.py](core/crawler.py) | ✅ 已完成 | 反爬爬虫 + 分页 + 缓冲 + 语言过滤 |
| [spiders/](core/spiders/) | ✅ 已完成 | 4个网站爬虫实现 |
| [classify.py](core/classify.py) | ✅ 已完成 | AI分类（在线API + 本地规则 + 缓存） |
| [download.py](core/download.py) | ✅ 已完成 | yt-dlp下载 + 多线程下载池 + 按语言/分类存储 |
| [subtitle_trans.py](core/subtitle_trans.py) | ✅ 已完成 | 字幕翻译（API/文件夹双模式） |
| [subtitle_processor.py](core/subtitle_processor.py) | ✅ 已完成 | 语音识别 + 字幕翻译 + 字幕嵌入 + 原字幕检测 |
| [task_scheduler.py](core/task_scheduler.py) | ✅ 已完成 | 调度器 + 健康检查 |

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
| [PROJECT_STATUS.md](PROJECT_STATUS.md) | ✅ |
| [main.py](main.py) | ✅ | 统一入口 |
| build.py | ⏳ 待开发 | 打包脚本（第五周 Day4） |

---

## 五、下一阶段开发规划

### 5.1 第二周重点任务

#### Day1: AI 分类模块
- 创建 `core/classify.py`
- 实现在线 API 文本分类
- 添加缓存机制（避免重复调用）
- 支持 VideoCategory 枚举

#### Day4: 数据自动入库流程
- 创建 `main.py` 统一入口
- 实现爬虫采集 → AI 分类 → 数据库入库完整流程
- 添加去重逻辑（URL 去重）

#### Day6: 全链路测试
- 测试抓取 → 分类 → 入库完整流程
- 验证数据库状态同步

### 5.2 第三周重点任务（视频下载 + 字幕生成）

#### Day1: 视频下载模块
- 创建 `core/download.py`
- 封装 yt-dlp 下载逻辑
- 支持多线程下载
- 下载进度回调

#### Day2: 文件归档模块
- 创建 `utils/file_sort.py`
- 按语言/分类自动创建目录结构
- 标准化视频/字幕命名

#### Day3: 翻译任务创建
- 下载完成后自动创建 translate_task
- 状态置为 DOWNLOADED(3)

### 5.3 第四周重点任务（字幕翻译 + 调度）

#### Day1: 字幕翻译模块
- 创建 `core/subtitle_trans.py`
- 对接外部翻译 API
- 支持文件夹中转模式

#### Day2: 任务调度器
- 创建 `core/task_scheduler.py`
- 后台线程调度
- 健康检查与告警

#### Day3: 文件监控
- watchdog 文件监控
- 字幕文件自动归档

### 5.4 第五周重点任务（UI + 打包）

- 一体化 WebUI
- 密钥加密
- Nuitka 打包

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

---

## 七、给接手 AI 助手的操作指南

### 7.1 接手第一步（必做）

1. **读取规范**：打开 [.trae/rules/project_rules.md](.trae/rules/project_rules.md)，通读所有强制规范
2. **理解枚举**：打开 [utils/enums.py](utils/enums.py)，理解 6 个枚举类 + 工具方法 + 状态流转规则
3. **理解路径**：打开 [utils/path_helper.py](utils/path_helper.py)，熟悉所有路径函数
4. **理解数据**：打开 [resources/schema.sql](resources/schema.sql)，熟悉两张表结构 + 触发器 + 索引
5. **理解配置**：打开 [config.yaml](config.yaml)，熟悉 7 大配置模块
6. **确认进度**：阅读本文档，确认当前在哪一周、哪一天

### 7.2 开发顺序建议

严格按照 5 周计划推进，不要跳步。每完成一个模块，立即写对应的单元测试。

### 7.3 开发原则

- 每写一个文件，先确认依赖关系（core 只导入 utils）
- 每用一个状态/语种，必须用枚举，不许硬编码
- 每用一个路径，必须通过 path_helper，不许硬编码
- 每做一个 IO 操作，必须 try-except + 日志
- 每写一个公共函数，必须有类型注解 + docstring
- 完成后跑一遍自检清单（见 project_rules.md 第十一节）

### 7.4 下一步立即要做的事

> **第二周 Day1：开发 core/classify.py**
>
> 目标：实现视频分类功能
> - 支持在线 API 分类（调用外部 AI 服务）
> - 支持本地规则分类（基于关键词匹配）
> - 缓存机制（避免重复调用）
> - 返回 VideoCategory 枚举
> - 完整类型注解 + 中文 docstring
