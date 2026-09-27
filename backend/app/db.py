"""Supabase 数据访问层。

统一用 service_role_key 访问（绕过 RLS），并把同步的 supabase-py 调用
丢到线程池执行，避免阻塞 FastAPI 的事件循环。

⚠️ 连接保活（重要）
httpx 默认 `keepalive_expiry=5s`：请求间隔超过 5 秒就会关掉连接，下次要重新做
DNS + TLS 握手。实测跨国链路（本地 → Supabase 悉尼）新建连接要 **2~17 秒**，
而复用连接只要 **0.5 秒** —— 于是接口延迟会在 0.5s 和 14s 之间随机跳动。
所以这里注入一个自己调优过的 httpx.Client，把保活时间拉到分钟级。
"""

from __future__ import annotations

import logging
from functools import lru_cache
from typing import Any

import anyio
import httpx
from supabase import Client, create_client
from supabase.lib.client_options import SyncClientOptions

from .config import get_settings

logger = logging.getLogger("atoms.db")

# 可以安全重试的异常（连接类问题，请求本身没有产生副作用）
RETRYABLE = (httpx.TimeoutException, httpx.TransportError)


class DatabaseNotConfigured(RuntimeError):
    """未配置 Supabase 时抛出，由调用方转成 503。"""


def build_http_client() -> httpx.Client:
    """构造带长保活的 httpx 客户端。

    postgrest 用绝对 URL 发请求（`self.session.request(method, str(self.path))`），
    因此不需要给这个 client 设 base_url。
    """
    settings = get_settings()
    return httpx.Client(
        timeout=httpx.Timeout(settings.supabase_timeout, connect=15.0),
        follow_redirects=True,
        limits=httpx.Limits(
            max_connections=20,
            max_keepalive_connections=10,
            keepalive_expiry=settings.supabase_keepalive,
        ),
    )


@lru_cache
def get_supabase() -> Client:
    """返回全局唯一的 Supabase 客户端（复用同一个连接池）。"""
    settings = get_settings()
    if not settings.supabase_ready:
        raise DatabaseNotConfigured(
            "Supabase 未配置：请在 backend/.env 中填写 SUPABASE_URL 与 SUPABASE_SERVICE_KEY"
        )
    options = SyncClientOptions(
        httpx_client=build_http_client(),
        postgrest_client_timeout=settings.supabase_timeout,
    )
    return create_client(settings.supabase_url, settings.supabase_service_key, options=options)


def table(name: str):
    """`table("projects").select("*")` 风格查询的入口。"""
    return get_supabase().table(name)


async def execute(query, *, attempts: int = 1, retry_delay: float = 0.6) -> Any:
    """在后台线程执行 supabase 同步查询。

    `attempts > 1` 只给**读**操作使用：跨国链路偶发超时时重试是安全的。
    写操作一律单次执行 —— 超时不代表服务端没写成功，盲目重试会产生重复数据。
    """
    last_error: Exception | None = None
    for attempt in range(1, max(1, attempts) + 1):
        try:
            return await anyio.to_thread.run_sync(query.execute)
        except RETRYABLE as exc:
            last_error = exc
            if attempt >= attempts:
                break
            logger.warning(
                "Supabase 查询第 %d 次失败（%s），%.1fs 后重试",
                attempt,
                type(exc).__name__,
                retry_delay * attempt,
            )
            await anyio.sleep(retry_delay * attempt)
    assert last_error is not None
    raise last_error


async def fetch_one(query) -> dict | None:
    """执行查询并返回第一条记录（没有则 None）。"""
    response = await execute(query, attempts=3)
    rows = getattr(response, "data", None) or []
    return rows[0] if rows else None


async def fetch_all(query) -> list[dict]:
    """执行查询并返回全部记录。"""
    response = await execute(query, attempts=3)
    return getattr(response, "data", None) or []


async def ping() -> bool:
    """探测 Supabase 是否可用（启动时调用，失败不阻塞启动）。"""
    if not get_settings().supabase_ready:
        return False
    try:
        await execute(table("projects").select("id").limit(1))
        return True
    except Exception:  # noqa: BLE001 - 启动探测，任何异常都视为不可用
        return False
