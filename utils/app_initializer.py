"""
AUDIT-0040: 兼容层，实际实现已迁移到 app/bootstrap.py。

utils 层不应反向依赖 core，所有装配逻辑统一从入口层 app/ 引入。
新代码请直接使用 `from app.bootstrap import initialize_app`。
"""

from app.bootstrap import initialize_app  # noqa: F401
