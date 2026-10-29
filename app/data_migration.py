"""
app/data_migration.py — 旧版本用户数据迁移到用户数据目录

背景：历史版本把 config/数据库/加密盐/设备身份全写在程序目录（APP_ROOT）。
打包安装到 Program Files 后该目录只读，必须把这些数据搬到
APP_DATA_ROOT（%LOCALAPPDATA%\\VideoCrawler）才能正常读写。

迁移规则（务必保守）：
  - 只复制、不删除；目标已存在一律跳过（幂等，可重复调用）
  - api_secret.yaml.enc 与 .crypto_salt 必须成对搬运，缺一不搬
    （盐与密文分离会导致已保存密钥永久不可解）
  - output/logs/tmp 等大体积目录不搬内容，只建空目录并提示旧路径
  - 任何异常仅告警，绝不阻断启动
"""

from __future__ import annotations

import shutil

from loguru import logger

from utils.path_helper import APP_ROOT, APP_DATA_ROOT, is_frozen

# 单项搬运清单（相对 APP_ROOT；仅当源存在且目标不存在时复制）
_FILES = [
    "config.yaml",
    "data/video_tasks.db",
    "data/video_tasks.db-wal",
    "data/video_tasks.db-shm",
    "data/browser_cookies.txt",
    "data/mqtt_device.json",
    "data/mqtt_web_url.txt",
]

# 加密配置与盐必须成对存在，单独搬运任一都会导致密文永久不可解
_CRYPTO_PAIR = ("api_secret.yaml.enc", ".crypto_salt")

# 大体积目录：只建空目录不搬内容（旧成品/日志留在原处并提示）
_BIG_DIRS = ("output", "logs", "tmp", "translate_queue", "finished_sub")


def migrate_legacy_data() -> None:
    """把旧版本散落在程序目录的用户数据复制到 APP_DATA_ROOT

    开发环境（非 frozen）数据本来就在项目根，直接跳过。
    """
    if not is_frozen() or APP_DATA_ROOT == APP_ROOT:
        return

    logger.info(f"[Migration] 程序根(只读)={APP_ROOT}")
    logger.info(f"[Migration] 用户数据根={APP_DATA_ROOT}")

    _migrate_plain_files()
    _migrate_crypto_pair()
    _prepare_big_dirs()

    logger.info("[Migration] 迁移检查完成")


def _migrate_plain_files() -> None:
    """逐项复制普通文件，单文件失败不影响其余"""
    for rel in _FILES:
        src = APP_ROOT / rel
        dst = APP_DATA_ROOT / rel
        if not src.is_file() or dst.exists():
            continue
        try:
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
            logger.info(f"[Migration] 已迁移 {rel}")
        except Exception as e:  # noqa: BLE001 — 迁移失败不阻断启动
            logger.warning(f"[Migration] 迁移 {rel} 失败: {e}")


def _migrate_crypto_pair() -> None:
    """加密配置与盐成对搬运；不成对时大声告警并跳过"""
    src_enc = APP_ROOT / _CRYPTO_PAIR[0]
    src_salt = APP_ROOT / _CRYPTO_PAIR[1]
    dst_enc = APP_DATA_ROOT / _CRYPTO_PAIR[0]
    dst_salt = APP_DATA_ROOT / _CRYPTO_PAIR[1]

    try:
        src_ready = src_enc.is_file() and src_salt.is_file()
        dst_ready = dst_enc.exists() or dst_salt.exists()

        if src_ready and not dst_ready:
            shutil.copy2(src_enc, dst_enc)
            shutil.copy2(src_salt, dst_salt)
            logger.info(
                f"[Migration] 已成对迁移 {_CRYPTO_PAIR[0]} + {_CRYPTO_PAIR[1]}"
            )
        elif src_ready and dst_ready:
            logger.info("[Migration] 数据目录已有密钥配置，跳过旧密文搬运")
        elif src_enc.is_file() or src_salt.is_file():
            logger.warning(
                "[Migration] 程序目录下 api_secret.yaml.enc 与 .crypto_salt "
                "只存在其一，为避免密钥不可解已跳过搬运；"
                "请在 GUI『API/模型管理』重新保存各密钥"
            )
    except Exception as e:  # noqa: BLE001 — 迁移失败不阻断启动
        logger.warning(f"[Migration] 密钥配置迁移失败: {e}")


def _prepare_big_dirs() -> None:
    """大体积目录只建空目录；旧目录非空时提示旧路径"""
    for name in _BIG_DIRS:
        try:
            (APP_DATA_ROOT / name).mkdir(parents=True, exist_ok=True)
        except Exception as e:  # noqa: BLE001
            logger.warning(f"[Migration] 创建 {name}/ 失败: {e}")
            continue

        old = APP_ROOT / name
        if old.is_dir() and any(old.iterdir()):
            logger.info(f"[Migration] 旧 {name}/ 内容未搬运，仍位于 {old}")
