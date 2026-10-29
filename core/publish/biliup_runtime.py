"""
biliup_runtime.py — B 站视频上传的 biliup CLI 集成

biliup (https://github.com/biliup/biliup) 是一个 Go 写的独立命令行工具，
它封装了 B 站完整的 HTTP 上传协议（分片上传、封面上传、提交发布）。
social-auto-upload 项目也用它来上传 B 站视频。

这里移植了 social-auto-upload 的 runtime.py，做了以下简化：
  - 去掉了 force_check 的复杂逻辑
  - 固定下载 Windows x86_64 版本
  - 增加了 cookie 导入方法（从我们的数据库 cookies → biliup account.json）
"""

from __future__ import annotations

import json
import platform
import shutil
import stat
import subprocess
import sys
import tarfile
import tempfile
import zipfile
from pathlib import Path

import requests
from loguru import logger


GITHUB_RELEASE_API = "https://api.github.com/repos/biliup/biliup/releases/latest"

# biliup 的 account 文件放在 ~/.videocrawler/tools/biliup/
def get_biliup_root() -> Path:
    return Path.home() / ".videocrawler" / "tools" / "biliup"

def get_biliup_exe() -> Path:
    return get_biliup_root() / "biliup.exe"

def get_biliup_version_file() -> Path:
    return get_biliup_root() / "version.txt"


def ensure_biliup() -> Path:
    """确保本地有 biliup.exe，没有就从 GitHub release 下载"""
    exe = get_biliup_exe()
    version_file = get_biliup_version_file()

    if exe.exists():
        return exe

    logger.info("[biliup] 本地未找到 biliup.exe，开始下载...")
    get_biliup_root().mkdir(parents=True, exist_ok=True)

    # 1. 获取最新 release
    resp = requests.get(
        GITHUB_RELEASE_API,
        headers={"Accept": "application/vnd.github+json", "User-Agent": "VideoCrawler"},
        timeout=30,
    )
    resp.raise_for_status()
    release = resp.json()
    tag = release["tag_name"]

    # 2. 找到 Windows x86_64 的 zip
    asset = None
    for a in release.get("assets", []):
        if "x86_64" in a["name"] and "windows" in a["name"].lower() and a["name"].endswith(".zip"):
            asset = a
            break
    if not asset:
        raise RuntimeError(f"biliup release {tag} 中未找到 Windows x86_64 版本")

    logger.info(f"[biliup] 下载 {asset['name']} ...")

    # 3. 下载并解压
    with tempfile.TemporaryDirectory(prefix="biliup-") as td:
        archive = Path(td) / asset["name"]
        with requests.get(asset["browser_download_url"], stream=True, timeout=120) as r:
            r.raise_for_status()
            with open(archive, "wb") as f:
                for chunk in r.iter_content(1024 * 1024):
                    if chunk:
                        f.write(chunk)

        extract_root = Path(td) / "extract"
        extract_root.mkdir()
        with zipfile.ZipFile(archive) as zf:
            zf.extractall(extract_root)

        # 找 exe（可能叫 biliup.exe 或 biliupR.exe）
        candidates = []
        for p in extract_root.rglob("*"):
            if p.is_file() and p.name.lower().endswith(".exe"):
                candidates.append(p)
        if not candidates:
            raise RuntimeError("解压后未找到 .exe 文件")
        # 优先选 biliup.exe，其次选 biliupR.exe
        candidates.sort(key=lambda p: (0 if "biliup.exe" == p.name.lower() else 1, len(str(p))))
        src = candidates[0]

        shutil.copy2(src, exe)
        if version_file.exists():
            version_file.unlink()
        version_file.write_text(tag, encoding="utf-8")

    logger.info(f"[biliup] 下载完成: {exe} ({tag})")
    return exe


def write_biliup_account(account_file: Path, cookies_raw: str, nickname: str = "") -> Path:
    """
    从我们数据库的 cookies（Netscape/header/JSON 格式都能解析）
    生成 biliup 需要的 account JSON 文件。

    biliup account.json 格式示例：
    {
      "bili_jct": "xxx",
      "DedeUserID": "xxx",
      "SESSDATA": "xxx",
      "buvid3": "xxx",
      "nickname": "xxx"
    }
    """
    # 解析 cookies
    cookies = {}
    # JSON 格式
    try:
        d = json.loads(cookies_raw)
        if isinstance(d, dict):
            cookies = {str(k): str(v) for k, v in d.items()}
    except Exception:
        pass

    if not cookies and "=" in cookies_raw:
        # Cookie header 格式
        for pair in cookies_raw.split(";"):
            pair = pair.strip()
            if "=" in pair:
                k, v = pair.split("=", 1)
                cookies[k.strip()] = v.strip()

    if not cookies:
        raise ValueError("无法解析 cookies 字符串")

    # biliup 要求的关键字段
    required = ["SESSDATA", "bili_jct", "DedeUserID"]
    missing = [k for k in required if k not in cookies]
    if missing:
        logger.warning(f"[biliup] cookies 缺少关键字段: {missing} — 可能上传会失败")

    account_data = dict(cookies)
    if nickname and "nickname" not in account_data:
        account_data["nickname"] = nickname

    account_file.parent.mkdir(parents=True, exist_ok=True)
    account_file.write_text(json.dumps(account_data, ensure_ascii=False, indent=2), encoding="utf-8")
    return account_file


def run_biliup(arguments: list[str], timeout: int = 600) -> subprocess.CompletedProcess[str]:
    """运行 biliup 命令"""
    exe = ensure_biliup()
    cmd = [str(exe), *arguments]
    logger.info(f"[biliup] 执行: {' '.join(cmd[:4])} ...")
    return subprocess.run(
        cmd,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
    )


def biliup_upload(
    account_file: Path,
    video_path: str,
    title: str,
    description: str = "",
    tid: int = 22,
    tags: list[str] | None = None,
    cover_path: str = "",
    schedule_ts: int | None = None,
) -> tuple[bool, str]:
    """
    用 biliup 上传一个视频到 B 站。

    返回 (success, message_or_bvid)
    """
    args = [
        "-u", str(account_file),
        "upload",
        video_path,
        "--title", title,
        "--desc", description,
        "--tid", str(tid),
    ]
    if tags:
        args.extend(["--tag", ",".join(tags[:10])])
    if cover_path and Path(cover_path).exists():
        args.extend(["--cover", cover_path])
    if schedule_ts:
        args.extend(["--dtime", str(schedule_ts)])

    result = run_biliup(args)

    output = (result.stdout or "") + "\n" + (result.stderr or "")
    output = output.strip()

    if result.returncode == 0:
        # 尝试从输出里找 BV 号
        import re
        bv_match = re.search(r'(BV[0-9A-Za-z]{10})', output)
        bvid = bv_match.group(1) if bv_match else ""
        return True, bvid or output.splitlines()[-1] if output else "上传成功"
    else:
        return False, output or f"biliup 返回码 {result.returncode}"
