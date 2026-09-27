"""存储后端：Supabase（默认）或本地 SQLite。

选择逻辑见 `backend()`：`STORAGE_BACKEND=auto` 时，配了 Supabase 就用 Supabase，
没配就自动落到本地 SQLite —— 保证这个 Demo 拉到任何一台机器上都能立刻跑起来。
"""

from __future__ import annotations

from types import ModuleType

from ..config import get_settings

_backend: ModuleType | None = None


def backend() -> ModuleType:
    """返回当前生效的存储后端模块（进程内缓存）。"""
    global _backend
    if _backend is None:
        mode = get_settings().resolved_storage
        if mode == "sqlite":
            from . import sqlite_store

            _backend = sqlite_store
        else:
            from . import supabase_store

            _backend = supabase_store
    return _backend


def reset() -> None:
    """测试用：清掉缓存，让下次调用重新按配置选择。"""
    global _backend
    _backend = None


__all__ = ["backend", "reset"]
