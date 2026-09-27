"""FastAPI 应用入口。"""

from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager, suppress

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from . import __version__, repository
from .config import get_settings
from .db import DatabaseNotConfigured
from .deps import get_current_user
from .routers import generation, projects, public, publish
from .schemas import MeOut, RuntimeConfigOut

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
)
logger = logging.getLogger("atoms")

settings = get_settings()


async def _supabase_keepalive(interval: float) -> None:
    """周期性轻量查询，避免 TCP 连接被空闲回收。

    实测（本地 → Supabase 悉尼）：新建连接 2~17s，复用连接 0.5s。
    链路中间设备空闲数十秒就会断连，所以主动焐住连接，让接口延迟稳定。
    """
    while True:
        await asyncio.sleep(interval)
        try:
            await repository.ping()
        except Exception:  # noqa: BLE001 - 保活失败不能影响主服务
            logger.debug("Supabase 保活查询失败", exc_info=True)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """启动时做一次依赖自检，把问题尽早暴露在日志里。"""
    logger.info("启动 %s v%s", settings.app_name, __version__)
    logger.info(
        "LLM: provider=%s model=%s | AGENT_MODE=%s",
        settings.resolved_llm_provider,
        settings.llm_model_name,
        settings.agent_mode,
    )
    if settings.llm_provider_mismatch:
        logger.warning(
            "LLM_PROVIDER=deepseek 但没填 DEEPSEEK_API_KEY，已自动回落到本地 Ollama（%s）",
            settings.ollama_model,
        )
    if settings.resolved_llm_provider == "ollama":
        logger.warning(
            "正在用本地 Ollama 推理，CPU 上大约 6~10 分钟一次生成；"
            "填好 DEEPSEEK_API_KEY 后重启即可自动切到云端（约 30~90 秒）"
        )

    storage = settings.resolved_storage
    if storage == "sqlite":
        if settings.supabase_ready:
            logger.info("存储后端：本地 SQLite（STORAGE_BACKEND=sqlite 强制指定）")
        else:
            logger.warning(
                "存储后端：本地 SQLite（未配置 Supabase，已自动回落）。文件：%s",
                settings.sqlite_path,
            )
            logger.warning(
                "接好 Supabase 后把 .env 里的 STORAGE_BACKEND 设回 auto，即可无缝切回云端"
            )
    elif await repository.ping():
        logger.info("存储后端：Supabase，连接正常")
    else:
        logger.error(
            "存储后端：Supabase，但连接失败。请检查 SUPABASE_URL / SERVICE_KEY，"
            "以及是否已执行 supabase/schema.sql"
        )

    if settings.auth_disabled:
        logger.warning("AUTH_DISABLED=true，所有请求都会被当作本地开发账号 %s", settings.dev_user_id)

    keepalive: asyncio.Task[None] | None = None
    if storage == "supabase" and settings.supabase_keepalive_interval > 0:
        keepalive = asyncio.create_task(
            _supabase_keepalive(settings.supabase_keepalive_interval)
        )
        logger.info("已开启 Supabase 连接保活，间隔 %.0fs", settings.supabase_keepalive_interval)

    try:
        yield
    finally:
        if keepalive is not None:
            keepalive.cancel()
            with suppress(asyncio.CancelledError):
                await keepalive
        logger.info("服务已停止")


app = FastAPI(
    title=settings.app_name,
    version=__version__,
    description=(
        "多智能体接力生成 + Supabase 持久化 + iframe 实时预览。\n\n"
        "流水线：🧑‍💼 产品经理 → 🏗️ 架构师 → 👨‍💻 工程师 →（可选）🧪 测试工程师"
    ),
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list or ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["*"],
)


@app.exception_handler(DatabaseNotConfigured)
async def _database_not_configured(_request, exc: DatabaseNotConfigured):
    return JSONResponse(status_code=503, content={"detail": str(exc)})


# ---------------------------------------------------------------
# 基础接口
# ---------------------------------------------------------------
@app.get("/", tags=["基础"], summary="服务信息")
async def root():
    return {
        "name": settings.app_name,
        "version": __version__,
        "docs": "/docs",
        "health": "/health",
        "api_prefix": settings.api_prefix,
    }


@app.get("/health", tags=["基础"], summary="健康检查")
async def health():
    return {
        "status": "ok",
        "version": __version__,
        "storage_backend": settings.resolved_storage,
        "storage_reachable": await repository.ping(),
        "supabase_ready": settings.supabase_ready,
        "llm_provider": settings.resolved_llm_provider,
        "llm_model": settings.llm_model_name,
        "agent_mode": settings.agent_mode,
    }


@app.get(f"{settings.api_prefix}/config", response_model=RuntimeConfigOut, tags=["基础"], summary="运行时配置")
async def runtime_config():
    """前端启动时拉一次，用于展示模型信息与开关状态。"""
    return {
        "app_name": settings.app_name,
        "version": __version__,
        "llm_provider": settings.resolved_llm_provider,
        "llm_model": settings.llm_model_name,
        "qa_stage_enabled": settings.enable_qa_stage,
        "agent_mode": settings.agent_mode,
        "storage_backend": settings.resolved_storage,
        "supabase_ready": settings.supabase_ready,
        "auth_disabled": settings.auth_disabled,
        "public_base_url": settings.public_base_url,
    }


@app.get(f"{settings.api_prefix}/me", response_model=MeOut, tags=["基础"], summary="当前用户")
async def me(user_id: str = Depends(get_current_user)):
    return {"user_id": user_id, "email": None, "auth_disabled": settings.auth_disabled}


# ---------------------------------------------------------------
# 业务路由
# ---------------------------------------------------------------
app.include_router(projects.router, prefix=settings.api_prefix)
app.include_router(generation.router, prefix=settings.api_prefix)
app.include_router(publish.router, prefix=settings.api_prefix)
app.include_router(public.router, prefix=settings.api_prefix)
