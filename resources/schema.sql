-- =====================================================
-- MultiLangVideoCrawler 数据库初始化脚本（v2）
-- 核心变化：
--   video_info 新增 channel_id / channel_name / series_id / related_cluster_id
--   video_info 新增 sub_category / tags 细粒度标签（独立标签模块消费）
--   video_info 新增 published_at / yt_category_id / yt_video_id 元数据字段
-- 兼容性：新字段全部 nullable 或有 default，老库直接跑初始化会 ADD COLUMN；
--        本文件中的 CREATE TABLE 仍是幂等（IF NOT EXISTS）。
-- =====================================================

-- =====================================================
-- 表1：video_info 视频基础信息主表
-- =====================================================
CREATE TABLE IF NOT EXISTS video_info (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,

    -- 基础识别
    source_url          TEXT    NOT NULL UNIQUE,            -- 视频源URL（唯一约束）
    yt_video_id         TEXT,                               -- YouTube video_id（冗余存储，便于 JOIN/反查）
    title               TEXT,
    description         TEXT,
    thumbnail           TEXT,
    duration            TEXT,                               -- 视频时长（原始字符串）
    published_at        TEXT,                               -- 发布时间（YouTube ISO 格式 / 日期字符串）

    -- 作者 / 频道（用于强相关聚合）
    author              TEXT,                               -- 展示名（频道名）
    channel_id          TEXT,                               -- 频道/作者的 channel_id（原始平台 ID）
    channel_name        TEXT,                               -- 频道展示名（冗余）

    -- 内容分类（两层体系：大类 VideoCategory 枚举 + 细粒度标签）
    lang                TEXT    NOT NULL,                   -- 语种（LanguageType 枚举值）
    category            TEXT,                               -- 大类（VideoCategory 枚举，用于文件归档目录）
    sub_category        TEXT,                               -- 子类（可选，如 talk_show / street_interview / soap_opera）
    tags                TEXT,                               -- JSON 数组字符串，存 3-6 个细粒度标签
                                                          -- 示例: ["街头访谈","爱情故事","西班牙语综艺","真人秀"]
    yt_category_id      INTEGER,                           -- YouTube 官方 category_id（兜底可用）

    -- 强相关聚合字段（由 crawler 或标签模块填充）
    series_id           TEXT,                               -- 系列 ID（如系列名称 slug / playlist_id）
    related_cluster_id  TEXT,                               -- 语义相近的聚合桶（同话题/同关键词）

    -- 状态 / 路径
    views               INTEGER DEFAULT 0,
    local_video_path    TEXT,
    is_downloaded       INTEGER NOT NULL DEFAULT 0,

    -- 可达性探测（用于过滤已下架/私有的死链，避免下载阶段浪费时间）
    check_status        INTEGER DEFAULT 0,                   -- 0=未探测, 1=yt-dlp预探通过, 2=broken(下架/私有/地区锁), 3=broken版权锁
    check_fail_reason   TEXT,                                -- 探测失败原因（"This video is not available" / "Content not available in your area" ...）
    check_ts            INTEGER,                             -- 上次探测时间戳

    -- 时间戳（数据库触发器自动维护）
    create_ts           INTEGER NOT NULL DEFAULT (strftime('%s', 'now')),
    update_ts           INTEGER NOT NULL DEFAULT (strftime('%s', 'now')),

    CHECK (lang IN ('de','fr','es','en','zh','ja','ko','ru','it','pt','ar','hi','nl','sv','no','da','fi','pl','cs','hu','ro','el','tr','vi','th','id','ms','tl')),
    CHECK (is_downloaded IN (0, 1)),
    CHECK (check_status IN (0, 1, 2, 3))
);

-- =====================================================
-- 表2：translate_task 翻译任务表（结构不变）
-- =====================================================
CREATE TABLE IF NOT EXISTS translate_task (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    video_id        INTEGER NOT NULL,
    outer_task_id   TEXT,
    subtitle_path   TEXT,
    status          INTEGER NOT NULL DEFAULT 3,
    retry_count     INTEGER DEFAULT 0,
    max_retry       INTEGER DEFAULT 3,
    priority        INTEGER DEFAULT 0,
    fail_reason     TEXT,
    dead_letter_ts  INTEGER,
    timeout_ts      INTEGER,
    create_ts       INTEGER NOT NULL DEFAULT (strftime('%s', 'now')),
    update_ts       INTEGER NOT NULL DEFAULT (strftime('%s', 'now')),

    FOREIGN KEY(video_id) REFERENCES video_info(id) ON DELETE CASCADE,

    CHECK (status IN (3, 4, 5, 6, 7)),
    CHECK (priority IN (0, 1)),
    CHECK (retry_count >= 0),
    CHECK (max_retry >= 0)
);

-- =====================================================
-- 触发器：自动更新 update_ts（video_info）
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
-- 索引（新增 channel_id / series_id / related_cluster_id
--      以支持"同频道同系列优先批内聚下载"调度）
-- =====================================================
CREATE INDEX IF NOT EXISTS idx_video_lang                ON video_info(lang);
CREATE INDEX IF NOT EXISTS idx_video_category            ON video_info(category);
CREATE INDEX IF NOT EXISTS idx_video_is_downloaded       ON video_info(is_downloaded);
CREATE INDEX IF NOT EXISTS idx_video_create_ts           ON video_info(create_ts);
CREATE INDEX IF NOT EXISTS idx_video_channel_id          ON video_info(channel_id);
CREATE INDEX IF NOT EXISTS idx_video_series_id           ON video_info(series_id);
CREATE INDEX IF NOT EXISTS idx_video_related_cluster_id  ON video_info(related_cluster_id);
CREATE INDEX IF NOT EXISTS idx_video_yt_video_id         ON video_info(yt_video_id);
CREATE INDEX IF NOT EXISTS idx_video_check_status        ON video_info(check_status);

CREATE INDEX IF NOT EXISTS idx_task_status               ON translate_task(status);
CREATE INDEX IF NOT EXISTS idx_task_vid                  ON translate_task(video_id);
CREATE INDEX IF NOT EXISTS idx_task_priority             ON translate_task(priority);
CREATE INDEX IF NOT EXISTS idx_task_update_ts            ON translate_task(update_ts);
CREATE INDEX IF NOT EXISTS idx_task_status_prio          ON translate_task(status, priority DESC);

-- =====================================================
-- 表3：publish_account 平台账号表
-- 支持同一平台多账号并存，cookie 加密存储
-- =====================================================
CREATE TABLE IF NOT EXISTS publish_account (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    platform        TEXT    NOT NULL,            -- 'bilibili' | 'douyin' | 'xiaohongshu' | 'kuaishou'
    nickname        TEXT,                        -- 账号昵称（用户填 / 登录后拉取）
    uid             TEXT,                        -- 平台 uid（登录后自动拉取）
    cookies         TEXT,                        -- 加密后的 cookie 字符串
    cookie_src      TEXT,                        -- 'browser_cdp' | 'manual'
    cdp_browser     TEXT,                        -- cookie 来源浏览器名（edge/chrome/brave/firefox）
    is_active       INTEGER NOT NULL DEFAULT 1,  -- 是否激活（1/0）
    last_check_ts   INTEGER,                     -- 上次有效性探测时间
    check_status    INTEGER DEFAULT 0,           -- 0=未知 1=有效 2=失效
    create_ts       INTEGER NOT NULL DEFAULT (strftime('%s', 'now')),
    update_ts       INTEGER NOT NULL DEFAULT (strftime('%s', 'now')),

    CHECK (platform IN ('bilibili','douyin','xiaohongshu','kuaishou')),
    CHECK (is_active IN (0,1)),
    CHECK (check_status IN (0,1,2))
);

-- =====================================================
-- 表4：video_pool 完成视频候选池
-- 全自动 + 非全自动管线完成烧录后统一入池
-- 保留近 3 天，按 create_ts 清理
-- =====================================================
CREATE TABLE IF NOT EXISTS video_pool (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,

    -- 视频本体
    video_id            TEXT,                               -- YouTube video_id / 源平台 id
    source_url          TEXT,
    final_video_path    TEXT    NOT NULL,                  -- 烧录后的 mp4 绝对路径
    cover_path          TEXT,                               -- 封面 jpg 绝对路径
    srt_path            TEXT,                               -- SRT 字幕路径（可用于取原文）

    -- 元数据（从下载阶段带入，可被发布页覆盖）
    title_original      TEXT,                               -- 原始语言标题
    title_translated    TEXT,                               -- 翻译后标题（中文）
    desc_original       TEXT,
    desc_translated     TEXT,
    thumbnail_url       TEXT,
    lang                TEXT,
    category            TEXT,
    channel_name        TEXT,
    duration_sec        INTEGER DEFAULT 0,

    -- 来源标记
    pipeline_source     TEXT    NOT NULL,                  -- 'auto' | 'manual'
    copy_path           TEXT,                               -- 文案文件路径（可选）

    -- 发布状态
    publish_status      INTEGER NOT NULL DEFAULT 0,         -- 0=未发布 1=已发布 2=跳过 3=发布失败
    published_platforms TEXT,                               -- JSON 数组，已发布的平台 id 列表
                                                            -- 示例: ["bilibili:12345", "douyin:67890"]
    last_error          TEXT,

    create_ts           INTEGER NOT NULL DEFAULT (strftime('%s', 'now')),
    update_ts           INTEGER NOT NULL DEFAULT (strftime('%s', 'now')),

    CHECK (pipeline_source IN ('auto','manual')),
    CHECK (publish_status IN (0,1,2,3))
);

-- =====================================================
-- 表5：publish_record 发布历史
-- =====================================================
CREATE TABLE IF NOT EXISTS publish_record (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    pool_id         INTEGER NOT NULL,
    account_id      INTEGER NOT NULL,
    platform        TEXT    NOT NULL,
    remote_id       TEXT,                        -- 平台返回的作品 id
    title           TEXT,                        -- 发布时的标题快照
    status          INTEGER NOT NULL,            -- 1=成功 2=失败
    error_msg       TEXT,
    scheduled_ts    INTEGER,                     -- 定时发布时间（NULL=立即）
    create_ts       INTEGER NOT NULL DEFAULT (strftime('%s', 'now')),

    FOREIGN KEY(pool_id) REFERENCES video_pool(id) ON DELETE CASCADE,
    FOREIGN KEY(account_id) REFERENCES publish_account(id) ON DELETE CASCADE,
    CHECK (platform IN ('bilibili','douyin','xiaohongshu','kuaishou')),
    CHECK (status IN (1,2))
);

-- 触发器
CREATE TRIGGER IF NOT EXISTS trg_publish_account_update_ts
AFTER UPDATE ON publish_account
FOR EACH ROW
BEGIN
    UPDATE publish_account SET update_ts = strftime('%s', 'now') WHERE id = OLD.id;
END;

CREATE TRIGGER IF NOT EXISTS trg_video_pool_update_ts
AFTER UPDATE ON video_pool
FOR EACH ROW
BEGIN
    UPDATE video_pool SET update_ts = strftime('%s', 'now') WHERE id = OLD.id;
END;

-- 索引
CREATE INDEX IF NOT EXISTS idx_pool_create_ts     ON video_pool(create_ts);
CREATE INDEX IF NOT EXISTS idx_pool_publish_stat  ON video_pool(publish_status);
CREATE INDEX IF NOT EXISTS idx_pool_source        ON video_pool(pipeline_source);
CREATE INDEX IF NOT EXISTS idx_acc_platform       ON publish_account(platform);
CREATE INDEX IF NOT EXISTS idx_acc_active         ON publish_account(is_active);
CREATE INDEX IF NOT EXISTS idx_record_pool         ON publish_record(pool_id);
CREATE INDEX IF NOT EXISTS idx_record_account      ON publish_record(account_id);
