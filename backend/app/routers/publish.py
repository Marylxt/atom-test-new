"""发布分享：生成公开访问链接。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Response, status

from .. import repository
from ..config import get_settings
from ..deps import get_current_user
from ..schemas import PublicationOut, PublishRequest
from .deps_common import require_project, require_version

router = APIRouter(tags=["发布"])


def _with_url(publication: dict) -> dict:
    settings = get_settings()
    return {
        **publication,
        "url": f"{settings.public_base_url.rstrip('/')}/app/{publication['public_id']}",
    }


@router.post("/publish", response_model=PublicationOut, summary="发布应用，生成公开链接")
async def publish(payload: PublishRequest, user_id: str = Depends(get_current_user)):
    project = await require_project(payload.project_id, user_id)

    version_id = payload.version_id or project.get("current_version_id")
    if not version_id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "项目还没有生成过版本，无法发布")
    version = await require_version(project["id"], version_id)

    publication = await repository.create_publication(
        project_id=project["id"],
        version_id=version["id"],
        title=payload.title or project["name"],
    )
    await repository.log_event(
        project["id"],
        "system",
        f"已发布 v{version['version_no']}，公开链接 {publication['public_id']}",
        version_id=version["id"],
    )
    return _with_url(publication)


@router.get("/publications", response_model=list[PublicationOut], summary="我的发布记录")
async def list_publications(user_id: str = Depends(get_current_user)):
    return [_with_url(row) for row in await repository.list_publications(user_id)]


@router.delete(
    "/publications/{publication_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="下线发布",
)
async def unpublish(publication_id: str, user_id: str = Depends(get_current_user)):
    publication = await repository.get_owned_publication(publication_id, user_id)
    if not publication:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "发布记录不存在或无权访问")
    await repository.deactivate_publication(publication_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
