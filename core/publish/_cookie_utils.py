"""
core.publish._cookie_utils — Cookie 解析公共函数

AUDIT-0025: clients.py._parse_cookies 和 playwright_base.py._parse_cookies 逻辑重复，
抽成统一的底层 raw→Dict[str, str] 函数，两边各自转自己需要的格式。
"""
from __future__ import annotations

import json
import re
from typing import Dict, List, Any


def parse_cookies_to_dict(raw: str) -> Dict[str, str]:
    """Netscape 文件 / Cookie header / JSON 三种格式 → Dict[str, str]

    底层统一解析函数，clients.py 和 playwright_base.py 都调用这一个。
    """
    if not raw:
        return {}

    # 1. JSON 格式
    try:
        d = json.loads(raw)
        if isinstance(d, dict):
            return {str(k): str(v) for k, v in d.items()}
        if isinstance(d, list) and d and isinstance(d[0], dict):
            # Edge/Chrome DevTools 导出: [{name, value}, ...]
            return {
                str(item["name"]): str(item["value"])
                for item in d
                if "name" in item and "value" in item
            }
    except Exception:
        pass

    # 2. Netscape 文件格式（每行 tab 分隔 7 列，最后两列 name=value）
    result: Dict[str, str] = {}
    for line in raw.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split("\t")
        if len(parts) >= 7:
            name = parts[-2].strip()
            value = parts[-1].strip()
            if name:
                result[name] = value
    if result:
        return result

    # 3. Cookie header 格式（分号分隔）
    for pair in raw.split(";"):
        pair = pair.strip()
        if not pair or "=" not in pair:
            continue
        k, v = pair.split("=", 1)
        k = k.strip()
        v = v.strip()
        if k:
            result[k] = v

    return result


def parse_cookies_for_playwright(raw: str) -> List[Dict[str, Any]]:
    """统一解析 + 转 Playwright cookies 列表"""
    d = parse_cookies_to_dict(raw)
    return [{"name": k, "value": v} for k, v in d.items()]
