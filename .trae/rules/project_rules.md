# MultiLangVideoCrawler AI 助手行为规范

> 本文件为 TRAE IDE / TRAE Work AI 助手的项目级强制规范。
> 所有代码生成、修改、重构、建议必须严格遵守，违反即重新生成。

---

## 一、分层依赖规范（最高优先级）

### 1. 层级划分

```
webui 层   →  可导入 core + utils
core  层   →  仅导入 utils（禁止导入 webui、禁止互导 core）
utils 层   →  纯工具，无业务逻辑，禁止导入 core / webui
main.py    →  统一入口，可导入所有层
```

### 2. 强制约束

- ❌ **禁止 utils 导入 core**（绝对禁止，杜绝循环导入）
- ❌ **禁止 core 模块互相导入**（如 crawler.py 导入 download.py）— 必须通过 task_scheduler 协调
- ❌ **禁止 core 导入 webui**
- ✅ core 只导入 utils 下的模块
- ✅ webui 导入 core + utils
- ✅ main.py 导入所有层

---

## 二、枚举使用规范

### 1. 强制使用枚举的场景

以下场景**必须使用 `utils/enums.py` 中的枚举**，禁止硬编码数字/字符串：

- 任务状态 → `TaskStatus`（IntEnum，1-7）
- 语种 → `LanguageType`（StrEnum，de/fr/es）
- 视频分类 → `VideoCategory`（StrEnum）
- 日志标签 → `LogTag`（StrEnum）
- 字幕模式 → `SubtitleMode`（StrEnum，api/folder）
- 任务优先级 → `TaskPriority`（IntEnum，0/1）

### 2. 枚举转换方法

| 场景 | 方法 | 示例 |
|:---|:---|:---|
| 从数据库读状态 | `TaskStatus.from_db(db_val)` | `status = TaskStatus.from_db(row["status"])` |
| 从整数转 | `TaskStatus.from_int(val)` | `status = TaskStatus.from_int(3)` |
| 从字符串转 | `LanguageType.from_code("de")` | `lang = LanguageType.from_code(lang_str)` |
| 校验合法性 | `TaskStatus.is_valid(val)` | `if not TaskStatus.is_valid(s): raise` |
| 中文展示 | `.display_name` | `print(status.display_name)` |
| 判断终态 | `.is_final` | `if task_status.is_final: return` |

### 3. 状态流转校验

所有状态变更**必须通过 `TaskStatus.can_transition_to()` 校验**：

```python
from utils.enums import TaskStatus

# 正确：先校验再变更
if not current_status.can_transition_to(new_status):
    logger.error(f"非法状态流转: {current_status} -> {new_status}")
    raise ValueError(f"Illegal transition: {current_status} -> {new_status}")
```

### 4. TaskStatus 状态流转规则（严格遵守）

```
PENDING(1) ──→ CRAWLING(2) ──→ DOWNLOADED(3) ──→ TRANSLATING(4) ──→ COMPLETED(5)
     │              │               │                │
     └─→ FAILED(6) ←┘               └─→ FAILED(6) ←─┘
                     │
                     └─→ DEAD_LETTER(7) （retry_count >= max_retry）
```

**终态（不可回退）**：COMPLETED(5)、DEAD_LETTER(7)
**翻译任务表默认状态**：DOWNLOADED(3)（视频下载后才创建翻译任务，不存在 PENDING/CRAWLING）

---

## 三、路径使用规范

### 1. 强制统一入口

**所有文件路径必须通过 `utils/path_helper.py` 获取**，禁止任何形式的硬编码：

- ❌ 禁止 `"./data/video_tasks.db"` 相对路径
- ❌ 禁止 `Path("./output")` 字面量路径
- ✅ 必须 `path_helper.get_db_path()`
- ✅ 必须 `path_helper.get_output_dir()`

### 2. 常用路径函数

| 路径 | 函数 |
|:---|:---|
| 项目根目录 | `APP_ROOT`（全局单例） |
| 配置文件 | `get_config_path()` / `get_secret_config_path()` |
| 数据库 | `get_db_path()` / `get_schema_path()` |
| 外置二进制 | `get_ffmpeg_path()` / `get_ytdlp_path()` |
| 日志文件 | `get_log_file(tag: str)` |
| 临时目录/文件 | `get_tmp_dir()` / `make_tmp_file()` / `clear_tmp_dir()` |
| 输出目录 | `get_output_dir()` / `get_translate_queue_dir()` / `get_finished_sub_dir()` |

### 3. 路径自动适配

path_helper 已自动处理：
- 开发环境 → 基于 `__file__` 推导项目根
- Nuitka 打包环境 → 基于 `sys.executable` 取 exe 所在目录
- 目录不存在 → 自动创建（`_ensure_dir` 已封装）

---

## 四、IO 与异常处理规范

### 1. 必须加 try-except 的场景

以下操作**必须分层 try-except 捕获异常**：

- 网络请求（爬虫、API调用）
- 文件读写（含数据库文件）
- 数据库操作
- 外部进程调用（yt-dlp、ffmpeg）
- 任何可能抛出异常的 IO 操作

### 2. 异常捕获规则

- **分层捕获**：底层捕获后记录日志，向上抛出或返回错误标识
- **不吞异常**：至少记录 error 级别日志，不得裸 except 后什么都不做
- **日志必带**：异常类型 + 错误信息 + 关键上下文（任务ID、URL等）
- **使用 LogTag**：按模块写入对应日志文件

### 3. 日志使用规范

- 日志模块：`utils/logger.py`（Loguru 封装）
- 日志标签：使用 `LogTag` 枚举，不写字符串
- 日志级别：
  - `DEBUG` — 调试细节，开发用
  - `INFO` — 正常流程节点
  - `WARNING` — 异常但可继续（如重试中）
  - `ERROR` — 错误但不崩（如单任务失败）
  - `CRITICAL` — 致命错误，程序可能退出

---

## 五、数据库操作规范

### 1. 读写分离

- **写入操作** → 统一走 `utils/db_manager.py` 内存缓冲池（批量写入、定时刷盘）
- **查询操作** → 可直接访问数据库（走 db_manager 的查询接口）

### 2. 时间戳

- `create_ts` / `update_ts` 由**数据库触发器自动维护**
- 代码层**禁止手动赋值** update_ts
- 代码层可读取，但不主动写入

### 3. 表结构约束

- 仅两张核心表：`video_info`、`translate_task`
- 死信通过 `status=7 (DEAD_LETTER)` 标识，**不单独建表**
- `translate_task` 默认 `status=3 (DOWNLOADED)`
- 外键 `ON DELETE CASCADE` 级联删除
- CHECK 约束已在库层拦截脏数据，代码层仍需预校验

### 4. 状态写入前校验

写入数据库前，必须校验枚举合法性：
```python
if not TaskStatus.is_valid(status_val):
    raise ValueError(f"Invalid status: {status_val}")
```

---

## 六、线程与调度规范

### 1. 线程管理

- **所有后台线程统一由 `core/task_scheduler.py` 管理**
- 禁止在业务代码中直接 `threading.Thread()`
- 使用 APScheduler 做定时任务调度
- 使用 watchdog 做文件监控
- 线程优雅退出：程序退出时 scheduler 负责 stop + join

### 2. 调度器职责

task_scheduler 负责：
- 爬虫定时任务
- 下载任务调度
- 翻译任务轮询
- 健康检查（ping 翻译工具、内存监控）
- 文件系统监控（watchdog）
- 全局线程生命周期管理

---

## 七、临时文件规范

- 临时文件**必须**放在 `tmp/` 目录下（通过 `path_helper.get_tmp_dir()` 获取）
- 程序启动时调用 `path_helper.clear_tmp_dir()` 清理遗留临时文件
- 临时文件使用 `path_helper.make_tmp_file()` 生成唯一文件名
- 任务完成后主动清理临时文件（如有异常，依赖启动清理兜底）

---

## 八、密钥与安全规范

- 敏感密钥**绝不落地明文**，统一存入 `api_secret.yaml.enc`
- 通过 `utils/crypto_util.py` 加解密读取
- `config.yaml` 仅存业务参数，不存密钥
- 日志中不得输出密钥、token、密码等敏感信息
- 加密文件路径：`path_helper.get_secret_config_path()`

---

## 九、编码风格规范

### 1. PEP8

- 严格遵守 PEP8
- 缩进 4 空格，不用 tab
- 行宽建议 100 字符以内
- 函数/类之间空 2 行，方法之间空 1 行

### 2. 类型注解

- **所有函数必须有完整的参数和返回值类型注解**
- 变量类型标注（复杂变量、容器等）
- 适配 mypy 类型检测
- 使用 `typing` 模块：Optional、list、dict、tuple 等

### 3. 注释

- 模块头部必须有模块说明 docstring
- 类必须有类 docstring（功能、职责）
- 公共函数必须有 docstring（Args、Returns、Raises）
- 关键逻辑行内注释
- **全部中文注释**

### 4. 命名

- 模块/函数/变量：snake_case（下划线命名）
- 类名：PascalCase（大驼峰）
- 常量：UPPER_SNAKE_CASE
- 私有方法/变量：单下划线前缀 `_xxx`

---

## 十、第三方库使用规范

### 1. 禁止事项

- ❌ 禁止编造不存在的库、类、函数、参数
- ❌ 禁止使用项目未声明的依赖
- ❌ 禁止随意添加新依赖（需确认后更新 requirements）

### 2. 已确认的关键库（必须按官方 API 使用）

| 库 | 正确包名 | 用途 |
|:---|:---|:---|
| curl_cffi | `curl_cffi`（下划线） | TLS 指纹反爬爬虫 |
| yt-dlp | `yt_dlp`（Python 模块） | 视频下载 |
| apsw | `apsw` | SQLite 高级封装 |
| watchdog | `watchdog` | 文件系统监控 |
| APScheduler | `apscheduler` | 定时任务调度 |
| Loguru | `loguru` | 日志 |
| cryptography | `cryptography` | 加解密 |
| Gradio | `gradio` | WebUI |
| pydantic | `pydantic` | 数据校验 |

### 3. 包名注意

- 爬虫库：`curl_cffi`（**下划线**，非 `curl-cffi`）
- 下载库：`yt_dlp`（Python 模块内用下划线）

---

## 十一、代码生成自检清单

每次生成/修改代码后，AI 助手必须逐项自检：

- [ ] 所有状态/语种/分类是否使用了枚举？
- [ ] 所有路径是否通过 path_helper 获取？
- [ ] core 层是否只导入 utils？
- [ ] utils 层是否没有导入 core/webui？
- [ ] IO 操作是否有 try-except + 日志记录？
- [ ] 数据库写入是否走缓冲池？
- [ ] 是否有完整类型注解？
- [ ] 是否有中文 docstring 和关键注释？
- [ ] 日志是否使用 LogTag 枚举？
- [ ] 临时文件是否在 tmp 目录？
- [ ] 是否编造了不存在的库/函数/字段？
- [ ] 是否违反了状态流转规则？
- [ ] 时间戳是否没有手动赋值 update_ts？

---

## 十二、绝对禁止清单

1. ❌ 编造不存在的库、类、字段、状态值
2. ❌ 硬编码状态数字、语种字符串、分类字符串
3. ❌ 硬编码文件路径（相对或绝对）
4. ❌ utils 层导入 core / webui
5. ❌ core 模块互相导入（必须通过 scheduler 协调）
6. ❌ 吞掉异常不记录日志
7. ❌ 业务代码中直接 new Thread
8. ❌ 明文存储密钥
9. ❌ 直接写入数据库（不走缓冲池）
10. ❌ 无类型注解的公共函数
11. ❌ 终态状态回退
12. ❌ 手动赋值 update_ts
13. ❌ 翻译任务表使用 PENDING(1)/CRAWLING(2) 状态
