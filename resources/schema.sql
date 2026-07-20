-- =====================================================
-- MultiLangVideoCrawler 数据库初始化脚本
-- 仅两张核心表：video_info / translate_task
-- 死信任务通过 status = 7 (DEAD_LETTER) 标识，不单独建表
-- 状态枚举与 utils/enums.py 中 TaskStatus 严格对应
-- =====================================================

-- =====================================================
-- 表1：video_info 视频基础信息主表
-- 状态说明：
--   is_downloaded = 0  待下载/下载中
--   is_downloaded = 1  已下载完成（下载归档后自动置1）
-- =====================================================
CREATE TABLE IF NOT EXISTS video_info (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,  -- 主键自增ID
    source_url          TEXT    NOT NULL UNIQUE,            -- 视频源URL（唯一约束，防重复采集）
    title               TEXT,                               -- 视频标题
    lang                TEXT    NOT NULL,                   -- 视频语种（de/fr/es，对应 LanguageType 枚举）
    category            TEXT,                               -- 视频题材分类（对应 VideoCategory 枚举）
    local_video_path    TEXT,                               -- 本地视频文件存储路径
    is_downloaded       INTEGER NOT NULL DEFAULT 0,         -- 下载标记（0=未下载 1=已下载）
    create_ts           INTEGER NOT NULL DEFAULT (strftime('%s', 'now')),  -- 记录创建时间戳（Unix秒级）
    update_ts           INTEGER NOT NULL DEFAULT (strftime('%s', 'now')),  -- 记录更新时间戳（Unix秒级）

    -- CHECK约束拦截脏数据入库
    CHECK (lang IN ('de', 'fr', 'es')),
    CHECK (is_downloaded IN (0, 1))
);

-- =====================================================
-- 表2：translate_task 翻译任务表
-- 说明：视频下载完成后才创建翻译任务，因此默认状态=3(DOWNLOADED)
--      不存在 PENDING(1)/CRAWLING(2) 等抓取相关状态
-- status 字段取值与 TaskStatus 枚举一一对应：
--   3 = DOWNLOADED   下载完成，等待翻译（初始默认状态）
--   4 = TRANSLATING  字幕翻译中
--   5 = COMPLETED    全部流程完成（终态）
--   6 = FAILED       单次执行失败，可重试
--   7 = DEAD_LETTER  多次重试失败，死信任务（终态，等同原dead_letter表）
-- priority 字段取值与 TaskPriority 枚举对应：
--   0 = NORMAL   普通优先级
--   1 = HIGH     高优先级
-- =====================================================
CREATE TABLE IF NOT EXISTS translate_task (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,      -- 主键自增ID
    video_id        INTEGER NOT NULL,                       -- 关联video_info表ID
    outer_task_id   TEXT,                                   -- 外部翻译系统任务ID（API模式下使用）
    subtitle_path   TEXT,                                   -- 字幕文件本地路径（翻译完成后填充）
    status          INTEGER NOT NULL DEFAULT 3,             -- 任务状态（默认3=DOWNLOADED）
    retry_count     INTEGER DEFAULT 0,                      -- 当前重试次数
    max_retry       INTEGER DEFAULT 3,                      -- 最大重试次数
    priority        INTEGER DEFAULT 0,                      -- 优先级（0=普通 1=高）
    fail_reason     TEXT,                                   -- 最近一次失败原因描述
    dead_letter_ts  INTEGER,                                -- 死信入队时间戳（status=7时填充）
    timeout_ts      INTEGER,                                -- 任务超时时间戳（超时未完成触发失败）
    create_ts       INTEGER NOT NULL DEFAULT (strftime('%s', 'now')),  -- 任务创建时间戳
    update_ts       INTEGER NOT NULL DEFAULT (strftime('%s', 'now')),  -- 任务最后更新时间戳

    -- 外键约束，级联删除视频时自动删除关联翻译任务
    FOREIGN KEY(video_id) REFERENCES video_info(id) ON DELETE CASCADE,

    -- CHECK约束拦截脏数据入库
    CHECK (status IN (3, 4, 5, 6, 7)),
    CHECK (priority IN (0, 1)),
    CHECK (retry_count >= 0),
    CHECK (max_retry >= 0)
);

-- =====================================================
-- 触发器：自动更新 update_ts 时间戳
-- 代码层无需手动赋值，INSERT/UPDATE 时自动刷新
-- =====================================================
CREATE TRIGGER IF NOT EXISTS trg_video_info_update_ts
AFTER UPDATE ON video_info
FOR EACH ROW
BEGIN
    UPDATE video_info SET update_ts = strftime('%s', 'now') WHERE id = OLD.id;
END;

CREATE TRIGGER IF NOT EXISTS trg_translate_task_update_ts
AFTER UPDATE ON translate_task
FOR EACH ROW
BEGIN
    UPDATE translate_task SET update_ts = strftime('%s', 'now') WHERE id = OLD.id;
END;

-- =====================================================
-- 全场景索引优化查询速度
-- =====================================================

-- video_info 索引
CREATE INDEX IF NOT EXISTS idx_video_lang          ON video_info(lang);             -- 按语种筛选视频
CREATE INDEX IF NOT EXISTS idx_video_category      ON video_info(category);         -- 按分类筛选视频
CREATE INDEX IF NOT EXISTS idx_video_is_downloaded ON video_info(is_downloaded);    -- 按下载标记筛选
CREATE INDEX IF NOT EXISTS idx_video_create_ts     ON video_info(create_ts);        -- 按创建时间排序

-- translate_task 索引
CREATE INDEX IF NOT EXISTS idx_task_status         ON translate_task(status);       -- 按状态查询任务
CREATE INDEX IF NOT EXISTS idx_task_vid            ON translate_task(video_id);     -- 按视频ID查询任务
CREATE INDEX IF NOT EXISTS idx_task_priority       ON translate_task(priority);     -- 按优先级排序
CREATE INDEX IF NOT EXISTS idx_task_update_ts      ON translate_task(update_ts);    -- 按更新时间排序
CREATE INDEX IF NOT EXISTS idx_task_status_prio    ON translate_task(status, priority DESC);  -- 状态+优先级联合索引
