"""多智能体接力生成引擎。"""

from .agent_orchestrator import (  # noqa: F401
    AGENTS,
    AgentSpec,
    GenerationError,
    GenerationResult,
    MultiAgentOrchestrator,
    StageResult,
    orchestrate_generation,
)
from .prompts import content_to_text, extract_html, looks_like_html  # noqa: F401

__all__ = [
    "AGENTS",
    "AgentSpec",
    "GenerationError",
    "GenerationResult",
    "MultiAgentOrchestrator",
    "StageResult",
    "content_to_text",
    "extract_html",
    "looks_like_html",
    "orchestrate_generation",
]
