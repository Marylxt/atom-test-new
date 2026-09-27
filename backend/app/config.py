"""应用配置：全部来自环境变量 / .env 文件。"""

from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """集中式配置对象，字段名大小写不敏感地映射到环境变量。"""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ---------- 基础 ----------
    app_name: str = "Atoms Demo API"
    debug: bool = True
    api_prefix: str = "/api"
    cors_origins: str = "http://localhost:3000,http://127.0.0.1:3000"
    public_base_url: str = "http://localhost:3000"

    # ---------- Supabase ----------
    supabase_url: str = ""
    supabase_anon_key: str = ""
    supabase_service_key: str = ""
    supabase_jwt_secret: str = ""
    supabase_jwks_url: str = ""

    # Supabase HTTP 连接调优
    # httpx 默认 keepalive_expiry=5s，跨国链路下几乎每次请求都要重新做 TLS 握手
    # （实测新建连接 2~17s，复用连接 0.5s），所以把保活时间拉长
    supabase_keepalive: float = 300.0
    supabase_timeout: float = 60.0
    # 后台保活间隔（秒）。链路中间设备会在空闲数十秒后断连，
    # 主动周期性打一个轻量查询把 TCP 连接焐住；设为 0 关闭
    supabase_keepalive_interval: float = 20.0

    # ---------- 存储后端 ----------
    # auto（默认）：配了 Supabase 就用 Supabase，没配就落到本地 SQLite
    # supabase：强制 Supabase（未配置时报 503）
    # sqlite：强制本地 SQLite，方便离线演示
    storage_backend: str = "auto"
    sqlite_path: str = "data/atoms.db"

    # ---------- LLM ----------
    # auto（默认）：有 DeepSeek Key 就走云端，没有就回落本地 Ollama
    # 也可以显式写死 deepseek / ollama
    llm_provider: str = "auto"
    llm_temperature: float = 0.2
    llm_max_tokens: int = 8000
    deepseek_api_key: str = ""
    deepseek_base_url: str = "https://api.deepseek.com"
    deepseek_model: str = "deepseek-chat"
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "qwen2.5:7b"
    # 上下文窗口。CPU 推理时 KV cache 越小越快，默认给 16k（单页应用的 prompt + 产物足够放下）
    ollama_num_ctx: int = 16384

    # ---------- 生成流水线 ----------
    enable_qa_stage: bool = False
    stream_tokens: bool = True
    agent_mode: str = "chain"  # chain | tool

    # ---------- 认证 ----------
    auth_disabled: bool = False
    dev_user_id: str = "00000000-0000-0000-0000-000000000001"

    # ---------- 派生属性 ----------
    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def supabase_ready(self) -> bool:
        return bool(self.supabase_url and self.supabase_service_key)

    @property
    def resolved_storage(self) -> str:
        """把 auto 解析成确定的后端名。"""
        mode = (self.storage_backend or "auto").strip().lower()
        if mode in {"supabase", "sqlite"}:
            return mode
        return "supabase" if self.supabase_ready else "sqlite"

    @property
    def resolved_llm_provider(self) -> str:
        """把 auto 解析成确定的模型提供方。

        显式写了 deepseek 但没填 Key 时也回落到 ollama —— 宁可慢一点，
        也不要让整个服务起不来（启动日志里会给出明确提示）。
        """
        provider = (self.llm_provider or "auto").strip().lower()
        if provider == "ollama":
            return "ollama"
        if provider == "deepseek":
            return "deepseek" if self.deepseek_api_key else "ollama"
        return "deepseek" if self.deepseek_api_key else "ollama"

    @property
    def llm_model_name(self) -> str:
        return self.ollama_model if self.resolved_llm_provider == "ollama" else self.deepseek_model

    @property
    def llm_provider_mismatch(self) -> bool:
        """用户显式要求 deepseek 但没配 Key（用于启动告警）。"""
        return (self.llm_provider or "").strip().lower() == "deepseek" and not self.deepseek_api_key


@lru_cache
def get_settings() -> Settings:
    """配置单例（进程内缓存）。"""
    return Settings()
