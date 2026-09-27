"""Supabase 存储后端：把 Supabase 的读写集中到一处，路由层只关心业务。

所有函数都是异步的（内部丢线程池执行同步的 supabase-py 调用）。
函数签名与 `sqlite_store.py` 完全一致，由 `repository.py` 按配置二选一。
"""

from __future__ import annotations

import secrets
from datetime import datetime, timezone
from typing import Any

from ..db import execute, fetch_all, fetch_one, table
from ..db import ping as _db_ping

VERSION_LIST_COLUMNS = (
    "id,project_id,version_no,prompt,change_type,parent_version_id,model,duration_ms,created_at"
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------
# projects
# ---------------------------------------------------------------
async def list_projects(user_id: str) -> list[dict[str, Any]]:
    """项目列表，附带版本数与最新版本号。"""
    projects = await fetch_all(
        table("projects").select("*").eq("user_id", user_id).order("updated_at", desc=True)
    )
    if not projects:
        return []

    ids = [p["id"] for p in projects]
    versions = await fetch_all(
        table("versions").select("project_id,version_no").in_("project_id", ids)
    )

    stats: dict[str, dict[str, int]] = {}
    for row in versions:
        bucket = stats.setdefault(row["project_id"], {"count": 0, "latest": 0})
        bucket["count"] += 1
        bucket["latest"] = max(bucket["latest"], row.get("version_no") or 0)

    for project in projects:
        bucket = stats.get(project["id"], {"count": 0, "latest": 0})
        project["version_count"] = bucket["count"]
        project["latest_version_no"] = bucket["latest"] or None
    return projects


async def ping() -> bool:
    """探测 Supabase 是否可用（供 /health 与启动自检使用）。

    注意：接口必须与 sqlite_store.ping 保持一致，否则切换后端时会直接 AttributeError。
    可用 scripts/check_backends.py 验证两个后端的接口契约。
    """
    return await _db_ping()


async def get_project(project_id: str) -> dict[str, Any] | None:
    return await fetch_one(table("projects").select("*").eq("id", project_id).limit(1))


async def get_owned_project(project_id: str, user_id: str) -> dict[str, Any] | None:
    return await fetch_one(
        table("projects")
        .select("*")
        .eq("id", project_id)
        .eq("user_id", user_id)
        .limit(1)
    )


async def create_project(user_id: str, name: str, description: str | None = None) -> dict[str, Any]:
    row = {
        "user_id": user_id,
        "name": name.strip(),
        "description": (description or "").strip() or None,
        "status": "draft",
    }
    response = await execute(table("projects").insert(row))
    return (response.data or [row])[0]


async def update_project(project_id: str, fields: dict[str, Any]) -> dict[str, Any] | None:
    payload = {k: v for k, v in fields.items() if v is not None}
    if not payload:
        return await get_project(project_id)
    payload["updated_at"] = _now()
    response = await execute(table("projects").update(payload).eq("id", project_id))
    rows = response.data or []
    return rows[0] if rows else await get_project(project_id)


async def delete_project(project_id: str) -> None:
    await execute(table("projects").delete().eq("id", project_id))


# ---------------------------------------------------------------
# versions
# ---------------------------------------------------------------
async def list_versions(project_id: str, limit: int = 50) -> list[dict[str, Any]]:
    return await fetch_all(
        table("versions")
        .select(VERSION_LIST_COLUMNS)
        .eq("project_id", project_id)
        .order("version_no", desc=True)
        .limit(limit)
    )


async def get_version(version_id: str) -> dict[str, Any] | None:
    return await fetch_one(table("versions").select("*").eq("id", version_id).limit(1))


async def get_current_version(project: dict[str, Any]) -> dict[str, Any] | None:
    """优先按 projects.current_version_id 取，否则退回最新一条版本。"""
    version_id = project.get("current_version_id")
    if version_id:
        version = await get_version(version_id)
        if version:
            return version
    rows = await fetch_all(
        table("versions")
        .select("*")
        .eq("project_id", project["id"])
        .order("version_no", desc=True)
        .limit(1)
    )
    return rows[0] if rows else None


async def next_version_no(project_id: str) -> int:
    rows = await fetch_all(
        table("versions")
        .select("version_no")
        .eq("project_id", project_id)
        .order("version_no", desc=True)
        .limit(1)
    )
    latest = rows[0]["version_no"] if rows else 0
    return int(latest) + 1


async def create_version(project_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    version_no = await next_version_no(project_id)
    row = {
        "project_id": project_id,
        "version_no": version_no,
        "prompt": payload.get("prompt") or "",
        "product_spec": payload.get("product_spec"),
        "architecture": payload.get("architecture"),
        "html_code": payload.get("html_code") or "",
        "review": payload.get("review"),
        "change_type": payload.get("change_type", "create"),
        "parent_version_id": payload.get("parent_version_id"),
        "model": payload.get("model"),
        "duration_ms": payload.get("duration_ms"),
    }
    response = await execute(table("versions").insert(row))
    created = (response.data or [row])[0]
    await update_project(project_id, {"current_version_id": created["id"], "status": "ready"})
    return created


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
    """记录一条生成过程日志；失败不影响主流程。"""
    try:
        await execute(
            table("generation_events").insert(
                {
                    "project_id": project_id,
                    "version_id": version_id,
                    "stage": stage,
                    "level": level,
                    "message": message[:2000],
                }
            )
        )
    except Exception:  # noqa: BLE001 - 日志属于旁路，绝不能让主流程挂掉
        pass


async def list_events(project_id: str, limit: int = 100) -> list[dict[str, Any]]:
    return await fetch_all(
        table("generation_events")
        .select("*")
        .eq("project_id", project_id)
        .order("created_at", desc=True)
        .limit(limit)
    )


# ---------------------------------------------------------------
# publications
# ---------------------------------------------------------------
def new_public_id() -> str:
    """12 位短链 ID（URL 安全）。"""
    return secrets.token_urlsafe(9)[:12]


async def create_publication(
    project_id: str, version_id: str, title: str | None = None
) -> dict[str, Any]:
    row = {
        "project_id": project_id,
        "version_id": version_id,
        "public_id": new_public_id(),
        "title": title,
        "is_active": True,
    }
    response = await execute(table("publications").insert(row))
    return (response.data or [row])[0]


async def list_publications(user_id: str) -> list[dict[str, Any]]:
    projects = await fetch_all(table("projects").select("id").eq("user_id", user_id))
    if not projects:
        return []
    return await fetch_all(
        table("publications")
        .select("*")
        .in_("project_id", [p["id"] for p in projects])
        .order("created_at", desc=True)
    )


async def get_publication(public_id: str) -> dict[str, Any] | None:
    return await fetch_one(
        table("publications").select("*").eq("public_id", public_id).eq("is_active", True).limit(1)
    )


async def get_owned_publication(publication_id: str, user_id: str) -> dict[str, Any] | None:
    row = await fetch_one(table("publications").select("*").eq("id", publication_id).limit(1))
    if not row:
        return None
    project = await get_owned_project(row["project_id"], user_id)
    return row if project else None


async def deactivate_publication(publication_id: str) -> None:
    await execute(table("publications").update({"is_active": False}).eq("id", publication_id))


async def increment_views(public_id: str) -> None:
    row = await get_publication(public_id)
    if not row:
        return
    try:
        await execute(
            table("publications").update({"views": int(row.get("views") or 0) + 1}).eq("id", row["id"])
        )
    except Exception:  # noqa: BLE001 - 统计失败不影响渲染
        pass
