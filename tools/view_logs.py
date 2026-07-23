"""
日志查看工具
帮助用户快速查看和分析日志，定位下载失败等问题
"""

import sys
import os
import argparse
from typing import Optional

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

from utils.path_helper import get_logs_dir, get_log_file
from utils.enums import LogTag


def tail_file(file_path: str, lines: int = 50) -> None:
    """查看文件末尾指定行数"""
    try:
        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
            all_lines = f.readlines()
            start = max(0, len(all_lines) - lines)
            for line in all_lines[start:]:
                print(line.rstrip())
    except FileNotFoundError:
        print(f"文件不存在: {file_path}")
    except Exception as e:
        print(f"读取文件失败: {e}")


def search_file(file_path: str, keywords: list) -> None:
    """在文件中搜索关键字"""
    try:
        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
            for line_num, line in enumerate(f, 1):
                if any(keyword.lower() in line.lower() for keyword in keywords):
                    print(f"[{line_num}] {line.rstrip()}")
    except FileNotFoundError:
        print(f"文件不存在: {file_path}")
    except Exception as e:
        print(f"搜索失败: {e}")


def list_log_files() -> None:
    """列出所有日志文件"""
    logs_dir = get_logs_dir()
    print(f"日志目录: {logs_dir}")
    print("-" * 60)
    
    for tag in LogTag:
        log_file = get_log_file(tag.value)
        if os.path.exists(log_file):
            file_size = os.path.getsize(log_file)
            print(f"{tag.value}.log ({file_size:,} bytes) - {tag.display_name}")
        else:
            print(f"{tag.value}.log (不存在) - {tag.display_name}")


def view_download_errors() -> None:
    """查看下载相关的错误日志"""
    download_log = get_log_file("download")
    error_log = get_log_file("error")
    
    print("=" * 60)
    print("下载模块日志 (download.log) - 最近100行")
    print("=" * 60)
    tail_file(download_log, 100)
    
    print("\n" + "=" * 60)
    print("错误日志 (error.log) - 最近50行")
    print("=" * 60)
    tail_file(error_log, 50)


def search_download_errors(keywords: Optional[list] = None) -> None:
    """搜索下载错误相关日志"""
    if keywords is None:
        keywords = ["error", "fail", "失败", "exception", "traceback", "download"]
    
    download_log = get_log_file("download")
    error_log = get_log_file("error")
    
    print("=" * 60)
    print(f"在 download.log 中搜索: {', '.join(keywords)}")
    print("=" * 60)
    search_file(download_log, keywords)
    
    print("\n" + "=" * 60)
    print(f"在 error.log 中搜索: {', '.join(keywords)}")
    print("=" * 60)
    search_file(error_log, keywords)


def main() -> None:
    parser = argparse.ArgumentParser(description='日志查看工具 - 帮助定位下载失败等问题')
    parser.add_argument('command', choices=['list', 'download', 'search', 'tail'],
                        help='操作命令: list(列出日志文件), download(查看下载错误), search(搜索错误), tail(查看文件末尾)')
    parser.add_argument('--file', '-f', help='指定日志文件(如 download.log)')
    parser.add_argument('--lines', '-n', type=int, default=50, help='查看的行数')
    parser.add_argument('--keywords', '-k', nargs='+', help='搜索关键字')
    
    args = parser.parse_args()
    
    if args.command == 'list':
        list_log_files()
    
    elif args.command == 'download':
        view_download_errors()
    
    elif args.command == 'search':
        keywords = args.keywords if args.keywords else None
        search_download_errors(keywords)
    
    elif args.command == 'tail':
        if args.file:
            log_file = get_log_file(args.file.replace('.log', ''))
            tail_file(log_file, args.lines)
        else:
            print("请使用 --file 参数指定日志文件")


if __name__ == "__main__":
    main()
