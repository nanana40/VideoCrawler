"""
storage.py — 发布模块的底层 DB 操作

用 sqlite3 标准库直接查 publish_account / video_pool / publish_record 三张表。
所有方法都是幂等的，带异常兜底。

注：不用 apsw 了，因为 apsw.Cursor 在 fetchall() 后会清掉 description 引 ExecutionCompleteError，
    sqlite3 没有这个坑。
"""

from __future__ import annotations

import json
import os
import sqlite3
import time
from typing import Any, Dict, List, Optional

from utils.path_helper import get_db_path


def _get_conn():
    """获取 sqlite3 连接（每调用一次新建，不缓存，避免线程锁问题）"""
    db_path = str(get_db_path())
    conn = sqlite3.connect(db_path, timeout=5)
    conn.row_factory = sqlite3.Row
    # AUDIT-0067: WAL 降低读写互斥，busy_timeout 缓解并发锁定报错
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=5000")
    return conn


def _rows_to_dicts(rows: List[sqlite3.Row]) -> List[Dict[str, Any]]:
    return [dict(r) for r in rows]


# ============================================================
# publish_account 账号表
# ============================================================

def list_accounts(platform: Optional[str] = None, only_active: bool = True) -> List[Dict[str, Any]]:
    conn = _get_conn()
    try:
        sql = "SELECT * FROM publish_account WHERE 1=1"
        args: list = []
        if platform:
            sql += " AND platform = ?"
            args.append(platform)
        if only_active:
            sql += " AND is_active = 1"
        sql += " ORDER BY platform, id DESC"
        cur = conn.execute(sql, args)
        return _rows_to_dicts(cur.fetchall())
    finally:
        conn.close()


def get_account(account_id: int) -> Optional[Dict[str, Any]]:
    conn = _get_conn()
    try:
        cur = conn.execute("SELECT * FROM publish_account WHERE id = ?", (account_id,))
        row = cur.fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def upsert_account(
    platform: str,
    cookies: str,
    nickname: str = "",
    uid: str = "",
    cookie_src: str = "manual",
    cdp_browser: str = "",
    account_id: Optional[int] = None,
) -> int:
    conn = _get_conn()
    try:
        if account_id:
            conn.execute(
                """UPDATE publish_account
                   SET platform=?, nickname=?, uid=?, cookies=?, cookie_src=?,
                       cdp_browser=?, is_active=1, update_ts=strftime('%s','now')
                   WHERE id=?""",
                (platform, nickname, uid, cookies, cookie_src, cdp_browser, account_id),
            )
            conn.commit()
            return account_id
        cur = conn.execute(
            """INSERT INTO publish_account
               (platform, nickname, uid, cookies, cookie_src, cdp_browser, is_active)
               VALUES (?, ?, ?, ?, ?, ?, 1)""",
            (platform, nickname, uid, cookies, cookie_src, cdp_browser),
        )
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


def set_account_status(account_id: int, check_status: int, nickname: Optional[str] = None, uid: Optional[str] = None) -> None:
    conn = _get_conn()
    try:
        fields = ["check_status=?", "last_check_ts=strftime('%s','now')", "update_ts=strftime('%s','now')"]
        args: list = [check_status]
        if nickname is not None:
            fields.append("nickname=?")
            args.append(nickname)
        if uid is not None:
            fields.append("uid=?")
            args.append(uid)
        args.append(account_id)
        conn.execute(f"UPDATE publish_account SET {', '.join(fields)} WHERE id=?", args)
        conn.commit()
    finally:
        conn.close()


def delete_account(account_id: int) -> None:
    conn = _get_conn()
    try:
        conn.execute("DELETE FROM publish_account WHERE id=?", (account_id,))
        conn.commit()
    finally:
        conn.close()


def set_account_active(account_id: int, active: bool) -> None:
    conn = _get_conn()
    try:
        conn.execute(
            "UPDATE publish_account SET is_active=?, update_ts=strftime('%s','now') WHERE id=?",
            (1 if active else 0, account_id),
        )
        conn.commit()
    finally:
        conn.close()


# ============================================================
# video_pool 候选池
# ============================================================

def add_to_pool(
    final_video_path: str,
    source_url: str = "",
    video_id: str = "",
    cover_path: str = "",
    srt_path: str = "",
    title_original: str = "",
    title_translated: str = "",
    desc_original: str = "",
    desc_translated: str = "",
    thumbnail_url: str = "",
    lang: str = "",
    category: str = "",
    channel_name: str = "",
    duration_sec: int = 0,
    pipeline_source: str = "manual",
    copy_path: str = "",
) -> int:
    conn = _get_conn()
    try:
        cur = conn.execute(
            "SELECT id FROM video_pool WHERE final_video_path = ?",
            (final_video_path,),
        )
        existing = cur.fetchone()
        if existing:
            conn.execute(
                """UPDATE video_pool SET
                    source_url=?, video_id=?, cover_path=?, srt_path=?,
                    title_original=?, title_translated=?, desc_original=?, desc_translated=?,
                    thumbnail_url=?, lang=?, category=?, channel_name=?, duration_sec=?,
                    pipeline_source=?, copy_path=?, update_ts=strftime('%s','now')
                   WHERE id=?""",
                (source_url, video_id, cover_path, srt_path,
                 title_original, title_translated, desc_original, desc_translated,
                 thumbnail_url, lang, category, channel_name, duration_sec,
                 pipeline_source, copy_path, existing["id"]),
            )
            conn.commit()
            return existing["id"]

        cur = conn.execute(
            """INSERT INTO video_pool
               (final_video_path, source_url, video_id, cover_path, srt_path,
                title_original, title_translated, desc_original, desc_translated,
                thumbnail_url, lang, category, channel_name, duration_sec,
                pipeline_source, copy_path)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (final_video_path, source_url, video_id, cover_path, srt_path,
             title_original, title_translated, desc_original, desc_translated,
             thumbnail_url, lang, category, channel_name, duration_sec,
             pipeline_source, copy_path),
        )
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


def list_pool(
    only_recent: bool = True,
    hours: int = 72,
    pipeline_source: Optional[str] = None,
    include_path_missing: bool = False,
) -> List[Dict[str, Any]]:
    conn = _get_conn()
    try:
        sql = "SELECT * FROM video_pool WHERE 1=1"
        args: list = []
        if only_recent:
            cutoff = int(time.time()) - hours * 3600
            sql += " AND create_ts >= ?"
            args.append(cutoff)
        if pipeline_source:
            sql += " AND pipeline_source = ?"
            args.append(pipeline_source)
        sql += " ORDER BY create_ts DESC"
        cur = conn.execute(sql, args)
        rows = _rows_to_dicts(cur.fetchall())

        if not include_path_missing:
            rows = [r for r in rows if os.path.exists(r.get("final_video_path", ""))]
        return rows
    finally:
        conn.close()


def get_pool_item(pool_id: int) -> Optional[Dict[str, Any]]:
    conn = _get_conn()
    try:
        cur = conn.execute("SELECT * FROM video_pool WHERE id=?", (pool_id,))
        row = cur.fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def update_pool_publish_status(
    pool_id: int,
    status: int,
    platform_id: Optional[str] = None,
    error_msg: Optional[str] = None,
) -> None:
    conn = _get_conn()
    try:
        cur = conn.execute("SELECT published_platforms FROM video_pool WHERE id=?", (pool_id,))
        row = cur.fetchone()
        existing: List[str] = []
        if row and row["published_platforms"]:
            try:
                existing = json.loads(row["published_platforms"])
            except Exception:
                existing = []
        if platform_id and platform_id not in existing:
            existing.append(platform_id)

        conn.execute(
            """UPDATE video_pool
               SET publish_status=?,
                   published_platforms=?,
                   last_error=?,
                   update_ts=strftime('%s','now')
               WHERE id=?""",
            (status, json.dumps(existing, ensure_ascii=False), error_msg or "", pool_id),
        )
        conn.commit()
    finally:
        conn.close()


def delete_expired_pool(hours: int = 72) -> int:
    conn = _get_conn()
    try:
        cutoff = int(time.time()) - hours * 3600
        cur = conn.execute(
            "DELETE FROM video_pool WHERE create_ts < ? AND publish_status IN (0,2)",
            (cutoff,),
        )
        conn.commit()
        return cur.rowcount
    finally:
        conn.close()


# ============================================================
# publish_record 发布记录
# ============================================================

def add_publish_record(
    pool_id: int,
    account_id: int,
    platform: str,
    remote_id: str = "",
    title: str = "",
    status: int = 1,
    error_msg: str = "",
    scheduled_ts: Optional[int] = None,
) -> int:
    conn = _get_conn()
    try:
        cur = conn.execute(
            """INSERT INTO publish_record
               (pool_id, account_id, platform, remote_id, title, status, error_msg, scheduled_ts)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (pool_id, account_id, platform, remote_id, title, status, error_msg, scheduled_ts),
        )
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


def list_publish_records(limit: int = 100) -> List[Dict[str, Any]]:
    conn = _get_conn()
    try:
        cur = conn.execute(
            "SELECT * FROM publish_record ORDER BY create_ts DESC LIMIT ?",
            (limit,),
        )
        return _rows_to_dicts(cur.fetchall())
    finally:
        conn.close()
