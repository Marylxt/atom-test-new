"""公开访问：不需要登录，任何人凭 public_id 都能打开已发布的应用。"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, status
from fastapi.responses import HTMLResponse

from .. import repository
from ..schemas import PublicAppOut

router = APIRouter(tags=["公开访问"])


async def _load(public_id: str) -> tuple[dict, dict]:
    publication = await repository.get_publication(public_id)
    if not publication:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "分享链接不存在或已下线")
    version = await repository.get_version(publication["version_id"])
    if not version:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "对应的版本已被删除")
    return publication, version


@router.get("/public/{public_id}", response_model=PublicAppOut, summary="读取已发布应用")
async def get_public_app(public_id: str):
    publication, version = await _load(public_id)
    await repository.increment_views(public_id)
    return {
        "public_id": publication["public_id"],
        "title": publication.get("title"),
        "html": version["html_code"],
        "version_no": version.get("version_no"),
        "published_at": publication.get("created_at"),
        "views": int(publication.get("views") or 0) + 1,
    }


@router.get("/public/{public_id}/raw", response_class=HTMLResponse, summary="直接渲染 HTML")
async def raw_public_app(public_id: str):
    """返回原始 HTML，便于 iframe src 直接引用或「在新窗口打开」。"""
    publication, version = await _load(public_id)
    await repository.increment_views(public_id)
    return HTMLResponse(content=version["html_code"])
