"""FastAPI 公共依赖：校验 Supabase 签发的 JWT。"""

from __future__ import annotations

from typing import Any

import jwt
from fastapi import Header, HTTPException, status

from .config import get_settings

_jwks_client: jwt.PyJWKClient | None = None


def _get_jwks_client() -> jwt.PyJWKClient | None:
    """惰性初始化 JWKS 客户端（支持 ES256 / RS256 非对称签名的项目）。"""
    global _jwks_client
    settings = get_settings()
    if _jwks_client is None:
        url = settings.supabase_jwks_url or (
            f"{settings.supabase_url.rstrip('/')}/auth/v1/.well-known/jwks.json"
            if settings.supabase_url
            else ""
        )
        if not url:
            return None
        _jwks_client = jwt.PyJWKClient(url)
    return _jwks_client


def _decode_token(token: str) -> dict[str, Any]:
    """先尝试 JWKS（非对称），失败再退回共享密钥（HS256）。"""
    settings = get_settings()

    if token.count(".") == 2 and token.split(".")[0]:
        try:
            header = jwt.get_unverified_header(token)
        except jwt.PyJWTError:
            header = {}

        algorithm = header.get("alg", "")
        if algorithm.startswith(("ES", "RS", "PS")):
            client = _get_jwks_client()
            if client is not None:
                try:
                    signing_key = client.get_signing_key_from_jwt(token)
                    return jwt.decode(token, signing_key.key, algorithms=[algorithm], options={"verify_aud": False})
                except jwt.PyJWTError as exc:
                    raise HTTPException(status.HTTP_401_UNAUTHORIZED, f"Invalid token: {exc}") from exc

    if not settings.supabase_jwt_secret:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            "服务端未配置 SUPABASE_JWT_SECRET，无法校验 token",
        )
    try:
        return jwt.decode(
            token,
            settings.supabase_jwt_secret,
            algorithms=["HS256"],
            options={"verify_aud": False},
        )
    except jwt.PyJWTError as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, f"Invalid token: {exc}") from exc


async def get_current_user(authorization: str | None = Header(default=None)) -> str:
    """从 `Authorization: Bearer <jwt>` 解析出 user_id。

    本地联调时可以设 AUTH_DISABLED=true，此时允许匿名请求并统一映射到
    DEV_USER_ID（方便在没有 Supabase 的情况下跑通全流程）。
    """
    settings = get_settings()

    if authorization and authorization.lower().startswith("bearer "):
        token = authorization[7:].strip()
        if token and token not in {"dev", "anonymous"}:
            payload = _decode_token(token)
            subject = payload.get("sub")
            if not subject:
                raise HTTPException(status.HTTP_401_UNAUTHORIZED, "token 中缺少 sub")
            return str(subject)

    if settings.auth_disabled:
        return settings.dev_user_id

    raise HTTPException(
        status.HTTP_401_UNAUTHORIZED,
        "缺少或无效的 Authorization 头，格式应为 `Bearer <supabase-jwt>`",
    )


CurrentUser = str
