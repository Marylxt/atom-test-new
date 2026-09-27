"""多智能体生成 / 多轮修改 / 代码评审。

`/api/generate` 与 `/api/modify/stream` 用 SSE 推送生成进度；
`/api/modify` 与 `/api/review` 用普通 JSON（一次性返回）。
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse

from .. import repository
from ..agents import GenerationError, MultiAgentOrchestrator
from ..deps import get_current_user
from ..schemas import GenerateRequest, ModifyRequest, ReviewRequest
from ..sse import SSE_HEADERS, sse

logger = logging.getLogger("atoms.generation")

router = APIRouter(tags=["生成"])


def _generation_error(exc: Exception) -> HTTPException:
    if isinstance(exc, GenerationError):
        return HTTPException(status.HTTP_502_BAD_GATEWAY, str(exc))
    logger.exception("生成流程异常")
    return HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, f"生成失败：{exc}")


async def _stream_pipeline(
    *,
    project: dict[str, Any],
    runner,
    start_payload: dict[str, Any],
    on_success,
) -> StreamingResponse:
    """把一个异步生成流程包装成 SSE 响应。

    runner(emit) -> GenerationResult
    on_success(result) -> complete 事件附加字段
    """
    queue: asyncio.Queue[dict[str, Any] | None] = asyncio.Queue()

    async def emit(event: dict[str, Any]) -> None:
        await queue.put(event)

    async def worker() -> None:
        try:
            await queue.put({"type": "start", **start_payload})
            result = await runner(emit)

            # 落库失败绝不能连产物一起丢掉：先保住结果，再单独报告保存问题。
            # （跨国链路偶发写超时是真实存在的，实测踩过一次。）
            # 静态检查留下的问题（例如脚本语法错误没能自修成功）
            warning: str | None = getattr(result, "validation_warning", None)
            try:
                extra = await on_success(result)
            except Exception as exc:  # noqa: BLE001
                logger.exception("生成结果落库失败")
                extra = {"version_id": None, "version_no": None}
                persistence = (
                    f"生成成功，但保存到数据库时出错：{exc}。"
                    "结果只显示在当前页面，刷新后会丢失，可以稍后重试一次生成。"
                )
                warning = f"{warning} {persistence}" if warning else persistence

            await queue.put(
                {
                    "type": "complete",
                    "html": result.html_code,
                    "product_spec": result.product_spec,
                    "architecture": result.architecture,
                    "review": result.review,
                    "model": result.model,
                    "duration_ms": result.duration_ms,
                    "stages": [s.to_dict() for s in result.stages],
                    "warning": warning,
                    **extra,
                }
            )
        except GenerationError as exc:
            await repository.update_project(project["id"], {"status": "failed"})
            await repository.log_event(project["id"], "system", str(exc), level="error")
            await queue.put({"type": "error", "message": str(exc)})
        except Exception as exc:  # noqa: BLE001
            logger.exception("生成流程异常")
            await repository.update_project(project["id"], {"status": "failed"})
            await queue.put({"type": "error", "message": f"生成失败：{exc}"})
        finally:
            await queue.put(None)

    async def event_stream():
        task = asyncio.create_task(worker())
        yield sse("open", {"message": "连接已建立，开始接力生成"})
        try:
            while True:
                event = await queue.get()
                if event is None:
                    break
                yield sse(event.pop("type"), event)
        except asyncio.CancelledError:  # 客户端断开
            task.cancel()
            raise
        finally:
            if not task.done():
                task.cancel()

    return StreamingResponse(event_stream(), media_type="text/event-stream", headers=SSE_HEADERS)


@router.post("/generate", summary="多智能体接力生成（SSE 流式）")
async def generate(request: GenerateRequest, user_id: str = Depends(get_current_user)):
    project = await repository.get_owned_project(request.project_id, user_id)
    if not project:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "项目不存在或无权访问")

    await repository.update_project(project["id"], {"status": "generating"})
    orchestrator = MultiAgentOrchestrator()
    await repository.log_event(
        project["id"], "system", f"开始生成：{request.prompt[:200]}"
    )

    async def runner(emit):
        async def bridge(event: dict[str, Any]) -> None:
            await emit(event)
            if event["type"] == "stage_complete":
                await repository.log_event(
                    project["id"],
                    event.get("stage", "system"),
                    event.get("message", ""),
                )

        return await orchestrator.generate(request.prompt, bridge)

    async def on_success(result):
        version = await repository.create_version(
            project["id"],
            {
                "prompt": request.prompt,
                "product_spec": result.product_spec,
                "architecture": result.architecture,
                "html_code": result.html_code,
                "review": result.review,
                "change_type": "create",
                "model": result.model,
                "duration_ms": result.duration_ms,
            },
        )
        await repository.log_event(
            project["id"],
            "system",
            f"v{version['version_no']} 生成完成，用时 {result.duration_ms / 1000:.1f}s",
            version_id=version["id"],
        )
        return {"version_id": version["id"], "version_no": version["version_no"]}

    return await _stream_pipeline(
        project=project,
        runner=runner,
        start_payload={
            "project_id": project["id"],
            "agents": orchestrator.agent_roster(),
            "model": orchestrator.model_name,
            "prompt": request.prompt,
        },
        on_success=on_success,
    )


# ---------------------------------------------------------------
# 多轮修改
# ---------------------------------------------------------------
async def _resolve_base(
    project: dict[str, Any], request: ModifyRequest | ReviewRequest
) -> dict[str, Any]:
    """确定「基于哪个版本改」。"""
    if request.current_html:
        return {"id": None, "html_code": request.current_html, "version_no": None}

    if request.version_id:
        version = await repository.get_version(request.version_id)
        if not version or version.get("project_id") != project["id"]:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "指定的版本不存在")
        return version

    version = await repository.get_current_version(project)
    if not version:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "项目还没有生成过版本，先跑一次生成")
    return version


async def _save_modification(
    project: dict[str, Any], request: ModifyRequest, base: dict[str, Any], result
) -> dict[str, Any]:
    version = await repository.create_version(
        project["id"],
        {
            "prompt": request.modification,
            "html_code": result.html_code,
            # 修改不改产品与架构，直接继承基线版本的产出，避免"Agent 产出"页变空
            "product_spec": base.get("product_spec"),
            "architecture": base.get("architecture"),
            "review": base.get("review"),
            "change_type": "modify",
            "parent_version_id": base.get("id"),
            "model": result.model,
            "duration_ms": result.duration_ms,
        },
    )
    await repository.log_event(
        project["id"],
        "engineer",
        f"v{version['version_no']} 修改完成：{request.modification[:160]}",
        version_id=version["id"],
    )
    return version


@router.post("/modify", summary="基于当前版本继续修改（一次性返回）")
async def modify(request: ModifyRequest, user_id: str = Depends(get_current_user)):
    project = await repository.get_owned_project(request.project_id, user_id)
    if not project:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "项目不存在或无权访问")

    base = await _resolve_base(project, request)
    orchestrator = MultiAgentOrchestrator()
    try:
        result = await orchestrator.modify(base["html_code"], request.modification)
    except Exception as exc:  # noqa: BLE001
        raise _generation_error(exc) from exc

    version = await _save_modification(project, request, base, result)
    return {
        "html": result.html_code,
        "version_id": version["id"],
        "version_no": version["version_no"],
        "model": result.model,
        "duration_ms": result.duration_ms,
    }


@router.post("/modify/stream", summary="基于当前版本继续修改（SSE 流式）")
async def modify_stream(request: ModifyRequest, user_id: str = Depends(get_current_user)):
    project = await repository.get_owned_project(request.project_id, user_id)
    if not project:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "项目不存在或无权访问")

    base = await _resolve_base(project, request)
    orchestrator = MultiAgentOrchestrator()
    await repository.update_project(project["id"], {"status": "generating"})

    async def runner(emit):
        async def bridge(event: dict[str, Any]) -> None:
            await emit(event)

        return await orchestrator.modify(base["html_code"], request.modification, bridge)

    async def on_success(result):
        version = await _save_modification(project, request, base, result)
        return {"version_id": version["id"], "version_no": version["version_no"]}

    return await _stream_pipeline(
        project=project,
        runner=runner,
        start_payload={
            "project_id": project["id"],
            "mode": "modify",
            "agents": orchestrator.agent_roster(),
            "model": orchestrator.model_name,
            "prompt": request.modification,
            "base_version_no": base.get("version_no"),
        },
        on_success=on_success,
    )


# ---------------------------------------------------------------
# 代码评审（测试工程师视角）
# ---------------------------------------------------------------
@router.post("/review", summary="测试工程师视角的代码评审")
async def review(request: ReviewRequest, user_id: str = Depends(get_current_user)):
    project = await repository.get_owned_project(request.project_id, user_id)
    if not project:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "项目不存在或无权访问")

    base = await _resolve_base(project, request)
    orchestrator = MultiAgentOrchestrator()
    try:
        report = await orchestrator.review(base["html_code"])
    except Exception as exc:  # noqa: BLE001
        raise _generation_error(exc) from exc

    await repository.log_event(
        project["id"],
        "qa",
        f"代码评审完成（{len(report)} 字）",
        version_id=base.get("id"),
    )
    return {
        "review": report,
        "version_id": base.get("id"),
        "version_no": base.get("version_no"),
    }
