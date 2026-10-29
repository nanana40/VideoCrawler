# MultiLangVideoCrawler 多语言视频爬虫项目

> 本文档为项目核心入口，包含业务说明、技术栈、目录结构、数据模型与快速开始指南。
> AI 助手接手时，请先阅读 [PROJECT\_STATUS.md](PROJECT_STATUS.md) 和 [.trae/rules/project\_rules.md](.trae/rules/project_rules.md)。

## 一、项目业务说明

Windows 平台 Python 工业级爬虫工具，功能链路：

```
网页采集视频信息 → 视频下载 → 字幕 AI 翻译 → 成品归档
```

附带 PySide6 桌面 GUI，使用 SQLite 本地数据库，PyInstaller 打包为独立 exe；采用虚拟环境部署，外置 ffmpeg、yt-dlp 二进制文件（不打进 exe，减小体积）。

## 二、技术栈

| 类别   | 技术                | 说明                         |
| :--- | :---------------- | :------------------------- |
| 语言   | Python 3.11+      | 强制版本 ≥ 3.11                |
| 数据库  | SQLite + apsw     | apsw 提供高级批量写入能力            |
| 爬虫   | curl\_cffi        | TLS 指纹反爬，绕过 Cloudflare 等防护 |
| 下载   | yt-dlp            | 外置二进制 bin/yt-dlp.exe       |
| 视频处理 | ffmpeg            | 外置二进制 bin/ffmpeg.exe       |
| 调度   | APScheduler       | 定时任务调度                     |
| 文件监控 | watchdog          | 监控翻译完成字幕目录                 |
| GUI  | PySide6           | 桌面可视化管理界面                  |
| 加密   | cryptography      | 配置文件加解密                    |
| 打包   | PyInstaller       | 编译为独立 exe，外置二进制分离          |
| 日志   | Loguru            | 分文件日志 + 日志滚动               |
| 配置   | PyYAML + pydantic | YAML 配置 + 数据校验             |

## 三、强制目录架构

```
MultiLangVideoCrawler/
├─ venv/                      # 虚拟环境（自动生成，git 忽略）
├─ resources/                 # 静态资源目录
│  └─ schema.sql              # SQLite 建表初始化脚本
├─ core/                      # 核心业务层，仅单向导入 utils，禁止反向导入
│  ├─ crawler.py              # curl_cffi 反爬爬虫
│  ├─ classify.py             # AI 视频题材分类 API
│  ├─ download.py             # yt-dlp 下载封装
│  ├─ subtitle_trans.py       # 字幕翻译 API 提交
│  └─ task_scheduler.py       # 线程调度、APScheduler、watchdog 文件监控
├─ utils/                     # 纯工具层，无业务逻辑
│  ├─ enums.py                # 全局统一枚举，禁止硬编码状态/语种
│  ├─ path_helper.py          # 全局统一路径工具，区分开发/打包环境
│  ├─ db_manager.py           # SQLite 内存缓冲写入池
│  ├─ queue_manager.py        # 任务队列、重试、死信存储工具
│  ├─ file_sort.py            # 文件归档、标准化重命名
│  ├─ language_check.py       # 语种识别工具
│  ├─ logger.py               # Loguru 分文件日志 + 日志滚动
│  └─ crypto_util.py          # yaml 配置加解密
├─ gui/                       # PySide6 桌面 GUI
│  └─ ...
├─ bin/                       # 外置二进制，打包不打进 exe
│  ├─ ffmpeg.exe
│  └─ yt-dlp.exe
├─ tests/                     # 单元测试目录，分模块测试脚本
├─ data/                      # 数据目录
│  └─ video_tasks.db          # SQLite 数据库文件
├─ tmp/                       # 运行临时缓存目录，启动自动清理
├─ output/                    # 成品视频存储
├─ translate_queue/           # 待翻译字幕中转文件夹
├─ finished_sub/              # 翻译完成字幕缓存
├─ logs/                      # 日志目录（分文件）
│  ├─ crawler.log
│  ├─ download.log
│  ├─ translate.log
│  └─ error.log
├─ .trae/                     # TRAE IDE 项目规则
│  └─ rules/
│     └─ project_rules.md     # AI 助手强制行为规范
├─ config.yaml                # 明文业务配置，根目录存放
├─ api_secret.yaml.enc        # 加密密钥配置文件（无明文密钥落地）
├─ main.py                    # 程序唯一统一入口
├─ build.py                   # Nuitka 打包脚本
├─ requirements-runtime.txt   # 运行最小依赖，无打包工具
├─ requirements-dev.txt       # 开发全量依赖，含 nuitka、类型检测库
├─ env_init.bat               # Windows 一键虚拟环境初始化脚本
├─ PROJECT_STATUS.md          # 项目进度与开发计划
├─ .gitignore                 # 版本控制忽略文件
└─ README.md                  # 本文档
```

### 分层依赖关系（禁止循环导入）

```
gui → core → utils
   ↘       ↘
    └───────→ main.py ←───────┘
```

- **core 层仅导入 utils**，禁止 utils 导入 core

- **gui 层可导入 core 和 utils**

- **main.py 作为统一入口**，可导入所有层

## 四、核心数据模型

### 4.1 TaskStatus 状态机

详见 [utils/enums.py](utils/enums.py)

```
PENDING(1) 待抓取
    ↓
CRAWLING(2) 采集中
    ↓
DOWNLOADED(3) 下载完成        ← translate_task 默认状态
    ↓
TRANSLATING(4) 翻译中
    ↓
COMPLETED(5) 已完成（终态）    ← 不可回退

任何阶段失败 → FAILED(6) 失败
重试超 max_retry → DEAD_LETTER(7) 死信（终态）
```

**终态**：COMPLETED(5)、DEAD\_LETTER(7) — 不可回退、不可再次流转

### 4.2 数据库表结构

详见 [resources/schema.sql](resources/schema.sql)

**表1：video\_info（视频基础信息主表）**

| 字段                 | 类型      | 说明             | 约束                                  |
| :----------------- | :------ | :------------- | :---------------------------------- |
| id                 | INTEGER | 主键自增ID         | PRIMARY KEY                         |
| source\_url        | TEXT    | 视频源URL         | NOT NULL UNIQUE                     |
| title              | TEXT    | 视频标题           | -                                   |
| lang               | TEXT    | 视频语种（de/fr/es） | NOT NULL, CHECK IN ('de','fr','es') |
| category           | TEXT    | 视频题材分类         | -                                   |
| local\_video\_path | TEXT    | 本地视频路径         | -                                   |
| is\_downloaded     | INTEGER | 下载标记（0/1）      | NOT NULL DEFAULT 0, CHECK IN (0,1)  |
| create\_ts         | INTEGER | 创建时间戳          | DEFAULT (strftime('%s', 'now'))     |
| update\_ts         | INTEGER | 更新时间戳          | 触发器自动更新                             |

**表2：translate\_task（翻译任务表）**

| 字段               | 类型      | 说明                | 约束                                       |
| :--------------- | :------ | :---------------- | :--------------------------------------- |
| id               | INTEGER | 主键自增ID            | PRIMARY KEY                              |
| video\_id        | INTEGER | 关联 video\_info.id | NOT NULL, FK ON DELETE CASCADE           |
| outer\_task\_id  | TEXT    | 外部翻译系统任务ID        | -                                        |
| subtitle\_path   | TEXT    | 字幕文件本地路径          | -                                        |
| status           | INTEGER | 任务状态（3-7）         | NOT NULL DEFAULT 3, CHECK IN (3,4,5,6,7) |
| retry\_count     | INTEGER | 当前重试次数            | DEFAULT 0, CHECK >= 0                    |
| max\_retry       | INTEGER | 最大重试次数            | DEFAULT 3, CHECK >= 0                    |
| priority         | INTEGER | 优先级（0/1）          | DEFAULT 0, CHECK IN (0,1)                |
| fail\_reason     | TEXT    | 最近一次失败原因          | -                                        |
| dead\_letter\_ts | INTEGER | 死信入队时间戳           | -                                        |
| timeout\_ts      | INTEGER | 任务超时时间戳           | -                                        |
| create\_ts       | INTEGER | 创建时间戳             | DEFAULT (strftime('%s', 'now'))          |
| update\_ts       | INTEGER | 更新时间戳             | 触发器自动更新                                  |

**核心设计**：

- 死信任务通过 `status=7 (DEAD_LETTER)` 标识，**不单独建表**

- `translate_task` 默认 `status=3 (DOWNLOADED)`（视频下载后才创建翻译任务）

- 外键 `ON DELETE CASCADE`：删视频自动级联删关联翻译任务

- 2 个触发器自动更新 `update_ts`，代码无需手动赋值

- 9 条索引覆盖全场景查询

## 五、全局枚举

详见 [utils/enums.py](utils/enums.py)

| 枚举类           | 类型      | 成员                                                                                                     | 说明       |
| :------------ | :------ | :----------------------------------------------------------------------------------------------------- | :------- |
| TaskStatus    | IntEnum | PENDING(1) / CRAWLING(2) / DOWNLOADED(3) / TRANSLATING(4) / COMPLETED(5) / FAILED(6) / DEAD\_LETTER(7) | 任务状态机    |
| LanguageType  | StrEnum | GERMAN("de") / FRENCH("fr") / SPANISH("es")                                                            | 视频源语种    |
| VideoCategory | StrEnum | SCIENCE("science") / DAILY("daily") / ENTERTAINMENT("entertainment") / NEWS("news")                    | 视频题材分类   |
| LogTag        | StrEnum | CRAWLER("crawler") / DOWNLOAD("download") / TRANSLATE("translate") / ERROR("error")                    | 日志分类标签   |
| SubtitleMode  | StrEnum | API("api") / FOLDER("folder")                                                                          | 字幕翻译对接模式 |
| TaskPriority  | IntEnum | NORMAL(0) / HIGH(1)                                                                                    | 任务优先级    |

**通用工具方法**（BaseEnumMixin）：

- `is_valid(value)` — 校验值是否合法

- `from_code(code, default)` — 从编码值安全转换

- `from_int(value, default)` — 从整数转换（IntEnum 专用）

- `from_db(db_value, default)` — 从数据库值转换

- `.display_name` — 中文展示名

- `.is_final` — 是否为终态

- `TaskStatus.can_transition_to(target)` — 状态流转合法性校验

## 六、路径管理

详见 [utils/path\_helper.py](utils/path_helper.py)

**所有路径必须通过 path\_helper 获取，禁止硬编码**。已自动适配开发环境与 Nuitka 打包环境。

核心函数：

- `get_app_root()` — 项目根目录（自动识别环境）

- `get_config_path()` / `get_secret_config_path()` — 配置文件路径

- `get_db_path()` / `get_schema_path()` — 数据库相关路径

- `get_ffmpeg_path()` / `get_ytdlp_path()` — 外置二进制路径

- `get_log_file(tag)` — 按标签获取日志文件路径

- `get_tmp_dir()` / `make_tmp_file()` / `clear_tmp_dir()` — 临时文件管理

- `is_frozen()` — 是否为打包环境

## 七、配置说明

详见 [config.yaml](config.yaml)

| 配置块        | 说明                        |
| :--------- | :------------------------ |
| crawler    | 爬虫配置（TLS指纹、延时、页数、UA池、代理）  |
| download   | 下载配置（线程数、输出目录、外置二进制路径）    |
| db\_buffer | 数据库缓冲配置（批量阈值、刷盘间隔）        |
| subtitle   | 字幕翻译配置（模式、API地址、并发、超时、目录） |
| scheduler  | 调度器配置（内存告警、自动清理）          |
| log        | 日志配置（根目录、级别）              |
| classify   | AI 分类配置（API地址、缓存时长）       |

**敏感密钥**：存放在 `api_secret.yaml.enc`（加密文件），通过 `utils/crypto_util.py` 加解密读取，**绝不落地明文**。

## 八、强制开发规范

详见 [.trae/rules/project\_rules.md](.trae/rules/project_rules.md)

1. 所有状态、语种、分类**必须使用枚举**，禁止硬编码数字/字符串
2. 所有文件路径**必须通过 path\_helper 获取**，禁止硬编码
3. **core 层仅导入 utils**，utils 严禁导入 core
4. 所有 IO 操作必须分层 try-except，写入对应 LogTag 日志
5. 数据库写入统一走内存缓冲池，查询直接访问库
6. 后台线程统一由 task\_scheduler 管理
7. 临时文件全部读写 tmp 目录，启动自动清理
8. 敏感密钥加密存储，无明文落地
9. 严格 PEP8，全类型注解，中文注释
10. 禁止编造不存在的库/函数/参数

## 九、快速开始

### 环境初始化（Windows）

双击 `env_init.bat`，按提示选择安装模式即可。

或手动执行：

```bat
cd MultiLangVideoCrawler
python -m venv venv
venv\Scripts\python.exe -m pip install -r requirements-runtime.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
```

### 运行程序

```bat
venv\Scripts\python.exe main.py
```

### 前置检查

确保 `bin/` 目录下存在：

- `ffmpeg.exe` — 视频处理工具

- `yt-dlp.exe` — 视频下载工具

## 十、AI 助手接手指南

如果你是 TRAE IDE / TRAE Work 的 AI 助手，接手项目时：

1. **先读规范**：[.trae/rules/project\_rules.md](.trae/rules/project_rules.md)
2. **再读进度**：[PROJECT\_STATUS.md](PROJECT_STATUS.md)
3. **理解枚举**：[utils/enums.py](utils/enums.py) — 状态流转核心
4. **理解路径**：[utils/path\_helper.py](utils/path_helper.py) — 路径统一入口
5. **理解数据**：[resources/schema.sql](resources/schema.sql) — 数据库设计
6. **按周推进**：按 PROJECT\_STATUS.md 中的 5 周计划逐步开发

