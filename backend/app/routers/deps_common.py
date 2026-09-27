"""路由层共用的小工具。"""

from __future__ import annotations

from typing import Any

from fastapi import HTTPException, status

from .. import repository


async def require_project(project_id: str, user_id: str) -> dict[str, Any]:
    """取出项目并校验归属，不存在或不属于该用户统一返回 404。"""
    project = await repository.get_owned_project(project_id, user_id)
    if not project:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "项目不存在或无权访问")
    return project


async def require_version(project_id: str, version_id: str) -> dict[str, Any]:
    """取出属于该项目的版本。"""
    version = await repository.get_version(version_id)
    if not version or version.get("project_id") != project_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "版本不存在")
    return version
