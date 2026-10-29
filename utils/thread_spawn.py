"""
utils.thread_spawn — 统一的线程创建工厂

AUDIT-0033: 24 处裸 threading.Thread() 统一走这个工厂，
方便未来加入全局监控/命名/异常钩子。
"""
from __future__ import annotations

import threading
import traceback
from typing import Callable, Optional, Any


def spawn(
    target: Callable[..., Any],
    *args,
    name: Optional[str] = None,
    daemon: bool = True,
    **kwargs,
) -> threading.Thread:
    """创建并返回一个线程（需要调用方自己 .start()）

    用法:
        t = spawn(_work, arg1, arg2, name="download")
        t.start()

    相比裸 threading.Thread 的好处:
    - 统一命名（方便日志/调试）
    - 未来可加全局异常钩子（target 抛异常时自动记录 traceback）
    - HEADLESS 安全：零 Qt 依赖，core/web/gui 都能用
    """

    def _wrapped():
        try:
            return target(*args, **kwargs)
        except Exception:
            # 线程内异常不会传播，这里兜底打 traceback
            traceback.print_exc()
            raise

    t = threading.Thread(target=_wrapped, name=name, daemon=daemon)
    return t
