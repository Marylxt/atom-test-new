"""项目管理 / 版本 / 过程日志。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Response, status

from .. import repository
from ..deps import get_current_user
from ..schemas import (
    ProjectCreate,
    ProjectOut,
    ProjectUpdate,
    RollbackRequest,
    VersionOut,
)
from .deps_common import require_project, require_version

router = APIRouter(prefix="/projects", tags=["项目"])


# ---------------------------------------------------------------
# 项目
# ---------------------------------------------------------------
@router.get("", response_model=list[ProjectOut], summary="项目列表")
async def list_projects(user_id: str = Depends(get_current_user)):
    return await repository.list_projects(user_id)


@router.post("", response_model=ProjectOut, status_code=status.HTTP_201_CREATED, summary="新建项目")
async def create_project(payload: ProjectCreate, user_id: str = Depends(get_current_user)):
    project = await repository.create_project(user_id, payload.name, payload.description)
    project.setdefault("version_count", 0)
    project.setdefault("latest_version_no", None)
    return project


@router.get("/{project_id}", response_model=ProjectOut, summary="项目详情（含当前版本代码）")
async def get_project(project_id: str, user_id: str = Depends(get_current_user)):
    project = await require_project(project_id, user_id)
    version = await repository.get_current_version(project)
    project["current_html"] = version.get("html_code") if version else None
    project["version_count"] = len(await repository.list_versions(project_id, limit=200))
    project["latest_version_no"] = version.get("version_no") if version else None
    return project


@router.patch("/{project_id}", response_model=ProjectOut, summary="更新项目")
async def update_project(
    project_id: str, payload: ProjectUpdate, user_id: str = Depends(get_current_user)
):
    await require_project(project_id, user_id)
    updated = await repository.update_project(project_id, payload.model_dump(exclude_none=True))
    if not updated:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "项目不存在")
    return updated


@router.delete("/{project_id}", status_code=status.HTTP_204_NO_CONTENT, summary="删除项目")
async def delete_project(project_id: str, user_id: str = Depends(get_current_user)):
    await require_project(project_id, user_id)
    await repository.delete_project(project_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ---------------------------------------------------------------
# 版本
# ---------------------------------------------------------------
@router.get("/{project_id}/versions", response_model=list[VersionOut], summary="版本列表")
async def list_versions(project_id: str, user_id: str = Depends(get_current_user)):
    await require_project(project_id, user_id)
    return await repository.list_versions(project_id)


@router.get("/{project_id}/versions/{version_id}", response_model=VersionOut, summary="版本详情")
async def get_version(project_id: str, version_id: str, user_id: str = Depends(get_current_user)):
    await require_project(project_id, user_id)
    return await require_version(project_id, version_id)


@router.post("/{project_id}/rollback", response_model=VersionOut, summary="回滚到指定版本")
async def rollback(
    project_id: str, payload: RollbackRequest, user_id: str = Depends(get_current_user)
):
    project = await require_project(project_id, user_id)
    version = await require_version(project_id, payload.version_id)

    # 回滚 = 把历史版本的代码复制成一个新版本，保证历史不可变、操作可追溯
    created = await repository.create_version(
        project_id,
        {
            "prompt": f"回滚到 v{version['version_no']}",
            "product_spec": version.get("product_spec"),
            "architecture": version.get("architecture"),
            "html_code": version["html_code"],
            "review": version.get("review"),
            "change_type": "rollback",
            "parent_version_id": version["id"],
            "model": version.get("model"),
            "duration_ms": 0,
        },
    )
    await repository.log_event(
        project_id,
        "system",
        f"已回滚到 v{version['version_no']}，生成 v{created['version_no']}",
        version_id=created["id"],
    )
    return created


# ---------------------------------------------------------------
# 过程日志
# ---------------------------------------------------------------
@router.get("/{project_id}/events", summary="生成过程日志")
async def list_events(project_id: str, limit: int = 50, user_id: str = Depends(get_current_user)):
    await require_project(project_id, user_id)
    return await repository.list_events(project_id, limit=min(limit, 200))


@router.get("/{project_id}/raw", summary="直接查看当前版本 HTML（便于新窗口调试）")
async def raw_html(project_id: str, user_id: str = Depends(get_current_user)):
    project = await require_project(project_id, user_id)
    version = await repository.get_current_version(project)
    if not version:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "项目还没有生成过版本")
    from fastapi.responses import HTMLResponse

    return HTMLResponse(content=version["html_code"])
