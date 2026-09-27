"""LLM 工厂：统一 DeepSeek（OpenAI 兼容协议）与 Ollama 的 ChatModel 创建。"""

from __future__ import annotations

from functools import lru_cache

from langchain_core.language_models.chat_models import BaseChatModel

from .config import get_settings


class LLMNotConfigured(RuntimeError):
    """缺少 API Key 等必要配置。"""


def build_llm(temperature: float | None = None, max_tokens: int | None = None) -> BaseChatModel:
    """按配置创建 LangChain ChatModel。"""
    settings = get_settings()
    temperature = settings.llm_temperature if temperature is None else temperature
    max_tokens = settings.llm_max_tokens if max_tokens is None else max_tokens
    provider = settings.resolved_llm_provider

    if provider == "ollama":
        from langchain_ollama import ChatOllama

        return ChatOllama(
            model=settings.ollama_model,
            base_url=settings.ollama_base_url,
            temperature=temperature,
            num_predict=max_tokens,
            num_ctx=settings.ollama_num_ctx,
        )

    if not settings.deepseek_api_key:
        raise LLMNotConfigured(
            "DEEPSEEK_API_KEY 未配置：请在 backend/.env 中填写，或把 LLM_PROVIDER 切换为 ollama"
        )

    from langchain_openai import ChatOpenAI

    return ChatOpenAI(
        model=settings.deepseek_model,
        api_key=settings.deepseek_api_key,
        base_url=settings.deepseek_base_url,
        temperature=temperature,
        max_tokens=max_tokens,
        streaming=True,
        timeout=300,
        max_retries=2,
    )


@lru_cache
def get_llm() -> BaseChatModel:
    """进程内共享的 ChatModel 实例（给 @tool 等同步调用场景使用）。"""
    return build_llm()
