"""数据访问层门面。

按 `STORAGE_BACKEND` 把请求转发给具体的存储实现：

    auto（默认） 配了 Supabase 就用 Supabase，否则落到本地 SQLite
    supabase     强制用 Supabase（未配置时抛 DatabaseNotConfigured → 503）
    sqlite       强制用本地 SQLite，方便离线演示

路由层只 import 这个模块，不关心底下是谁。
"""

from __future__ import annotations

from typing import Any

from .storage import backend


# ---------------------------------------------------------------
# 元信息
# ---------------------------------------------------------------
def storage_name() -> str:
    """当前生效的存储后端名（给 /health 和前端展示用）。"""
    return backend().__name__.rsplit(".", 1)[-1]


async def ping() -> bool:
    """探测存储后端是否可用。"""
    return bool(await backend().ping())


def new_public_id() -> str:
    return backend().new_public_id()


# ---------------------------------------------------------------
# projects
# ---------------------------------------------------------------
async def list_projects(user_id: str) -> list[dict[str, Any]]:
    return await backend().list_projects(user_id)


async def get_project(project_id: str) -> dict[str, Any] | None:
    return await backend().get_project(project_id)


async def get_owned_project(project_id: str, user_id: str) -> dict[str, Any] | None:
    return await backend().get_owned_project(project_id, user_id)


async def create_project(
    user_id: str, name: str, description: str | None = None
) -> dict[str, Any]:
    return await backend().create_project(user_id, name, description)


async def update_project(project_id: str, fields: dict[str, Any]) -> dict[str, Any] | None:
    return await backend().update_project(project_id, fields)


async def delete_project(project_id: str) -> None:
    await backend().delete_project(project_id)


# ---------------------------------------------------------------
# versions
# ---------------------------------------------------------------
async def list_versions(project_id: str, limit: int = 50) -> list[dict[str, Any]]:
    return await backend().list_versions(project_id, limit)


async def get_version(version_id: str) -> dict[str, Any] | None:
    return await backend().get_version(version_id)


async def get_current_version(project: dict[str, Any]) -> dict[str, Any] | None:
    return await backend().get_current_version(project)


async def next_version_no(project_id: str) -> int:
    return await backend().next_version_no(project_id)


async def create_version(project_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    return await backend().create_version(project_id, payload)


# ---------------------------------------------------------------
# generation_events
# ---------------------------------------------------------------
async def log_event(
    project_id: str,
    stage: str,
    message: str,
    level: str = "info",
    version_id: str | None = None,
) -> None:
    await backend().log_event(project_id, stage, message, level, version_id)


async def list_events(project_id: str, limit: int = 100) -> list[dict[str, Any]]:
    return await backend().list_events(project_id, limit)


# ---------------------------------------------------------------
# publications
# ---------------------------------------------------------------
async def create_publication(
    project_id: str, version_id: str, title: str | None = None
) -> dict[str, Any]:
    return await backend().create_publication(project_id, version_id, title)


async def list_publications(user_id: str) -> list[dict[str, Any]]:
    return await backend().list_publications(user_id)


async def get_publication(public_id: str) -> dict[str, Any] | None:
    return await backend().get_publication(public_id)


async def get_owned_publication(publication_id: str, user_id: str) -> dict[str, Any] | None:
    return await backend().get_owned_publication(publication_id, user_id)


async def deactivate_publication(publication_id: str) -> None:
    await backend().deactivate_publication(publication_id)


async def increment_views(public_id: str) -> None:
    await backend().increment_views(public_id)
