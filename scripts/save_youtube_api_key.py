"""
YouTube Data API v3 密钥加密保存脚本

将用户提供的 YouTube Data API v3 密钥加密保存到 api_secret.yaml.enc，
密钥绝不落地明文，符合项目安全规范。

用法：
    # 命令行直接传入密钥
    python scripts/save_youtube_api_key.py AIzaSyXXXXXX

    # 交互式输入（密钥不可见，更安全）
    python scripts/save_youtube_api_key.py

    # 查看当前已保存的密钥（只显示前10位，避免泄露）
    python scripts/save_youtube_api_key.py --show

    # 删除已保存的密钥
    python scripts/save_youtube_api_key.py --delete
"""

import sys
import os
import getpass
from typing import Dict, Any

# 将项目根目录加入 sys.path
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

from utils.crypto_util import load_secret_config, save_secret_config


def save_api_key(api_key: str) -> None:
    """加密保存 YouTube API 密钥

    采用合并更新策略：若 api_secret.yaml.enc 中已存在其他密钥，
    只更新 youtube_api_key 字段，不覆盖其他字段。

    Args:
        api_key: YouTube Data API v3 密钥

    Raises:
        ValueError: 密钥为空
        Exception: 加密保存失败
    """
    api_key = api_key.strip()
    if not api_key:
        raise ValueError("API 密钥不能为空")

    # 加载已有配置（合并更新，不覆盖其他密钥）
    existing: Dict[str, Any] = load_secret_config()
    existing["youtube_api_key"] = api_key
    save_secret_config(existing)
    print(f"[成功] YouTube API 密钥已加密保存到 api_secret.yaml.enc")
    print(f"[提示] 密钥前10位: {api_key[:10]}...")


def show_api_key() -> None:
    """显示已保存的密钥（只显示前10位）"""
    secret = load_secret_config()
    key = secret.get("youtube_api_key")
    if key:
        print(f"[信息] 已保存的 YouTube API 密钥前10位: {key[:10]}...")
    else:
        print("[信息] 未保存任何 YouTube API 密钥")


def delete_api_key() -> None:
    """删除已保存的 YouTube API 密钥"""
    secret = load_secret_config()
    if "youtube_api_key" not in secret:
        print("[信息] 未保存任何 YouTube API 密钥，无需删除")
        return

    del secret["youtube_api_key"]
    if secret:
        # 还有其他密钥，保留文件
        save_secret_config(secret)
        print("[成功] 已删除 youtube_api_key，其他密钥保留")
    else:
        # 没有其他密钥了，删除整个加密文件
        from utils.path_helper import get_secret_config_path
        secret_path = get_secret_config_path()
        if os.path.exists(secret_path):
            os.remove(secret_path)
            print(f"[成功] 已删除空的密钥配置文件: {secret_path}")


def main() -> None:
    """主函数：解析命令行参数并执行对应操作"""
    if len(sys.argv) >= 2:
        arg = sys.argv[1]
        if arg == "--show":
            show_api_key()
            return
        if arg == "--delete":
            delete_api_key()
            return
        # 命令行直接传入密钥
        try:
            save_api_key(arg)
        except Exception as e:
            print(f"[错误] 保存密钥失败: {e}")
            sys.exit(1)
    else:
        # 交互式输入
        print("请输入 YouTube Data API v3 密钥（输入不可见）：")
        key = getpass.getpass("> ")
        try:
            save_api_key(key)
        except Exception as e:
            print(f"[错误] 保存密钥失败: {e}")
            sys.exit(1)


if __name__ == "__main__":
    main()
