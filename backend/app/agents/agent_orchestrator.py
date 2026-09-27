"""多智能体接力生成引擎（Demo 核心）。

流水线：
    产品经理 → 架构师 → 工程师 →（可选）测试工程师

三种编排模式（环境变量 `AGENT_MODE`）：
    chain（默认）  直接用 LangChain ChatModel 流式串行接力，逐 token 回调进度
    tool          走 `@tool` 工具层接力，进度为阶段粒度
    agent         交给 `langchain.agents.create_agent` 自主编排工具调用
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Sequence

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage

from ..config import get_settings
from ..llm import build_llm
from .html_check import check_html
from .prompts import (
    ARCHITECT_SYSTEM,
    ENGINEER_SYSTEM,
    MODIFY_SYSTEM,
    PM_SYSTEM,
    QA_SYSTEM,
    REPAIR_SYSTEM,
    content_to_text,
    extract_html,
    looks_like_html,
)

# 单个阶段的 token 缓冲阈值：攒够这么多字符再推一次 SSE，减少帧数量
TOKEN_FLUSH_CHARS = 32
# 单份 HTML 允许进入修改流程的最大长度
MAX_HTML_CHARS = 200_000


class GenerationError(RuntimeError):
    """流水线执行失败，可直接转成 SSE 的 error 事件。"""


def _assert_complete_html(html: str, prefix: str = "工程师产出") -> None:
    """校验产物是不是一份完整 HTML，并给出可执行的修复建议。"""
    if looks_like_html(html):
        return
    lowered = html.lower()
    if "<html" in lowered and "</html>" not in lowered:
        raise GenerationError(
            f"{prefix}的 HTML 被截断了（撞到输出上限）。"
            "请把 LLM_MAX_TOKENS 调大，或把需求拆得更简单一些再试"
        )
    raise GenerationError(f"{prefix}的不是完整 HTML，请重试或更换模型")


@dataclass(frozen=True)
class AgentSpec:
    key: str
    name: str
    icon: str
    system_prompt: str
    idle_message: str
    # 单阶段输出上限（token）。CPU 本地推理很慢，必须给爱发挥的阶段戴紧箍咒。
    # None 表示用全局 LLM_MAX_TOKENS。
    max_tokens: int | None = None


AGENTS: dict[str, AgentSpec] = {
    "pm": AgentSpec(
        key="pm",
        name="产品经理",
        icon="🧑‍💼",
        system_prompt=PM_SYSTEM,
        idle_message="🧑‍💼 产品经理正在分析需求…",
        max_tokens=700,
    ),
    "architect": AgentSpec(
        key="architect",
        name="架构师",
        icon="🏗️",
        system_prompt=ARCHITECT_SYSTEM,
        idle_message="🏗️ 架构师正在设计方案…",
        max_tokens=900,
    ),
    "engineer": AgentSpec(
        key="engineer",
        name="工程师",
        icon="👨‍💻",
        system_prompt=ENGINEER_SYSTEM,
        idle_message="👨‍💻 工程师正在生成代码…",
    ),
    "engineer_modify": AgentSpec(
        key="engineer_modify",
        name="工程师",
        icon="🛠️",
        system_prompt=MODIFY_SYSTEM,
        idle_message="🛠️ 工程师正在按修改要求改代码…",
    ),
    "engineer_repair": AgentSpec(
        key="engineer_repair",
        name="工程师（自修）",
        icon="🩹",
        system_prompt=REPAIR_SYSTEM,
        idle_message="🩹 静态检查发现脚本语法错误，工程师正在自修…",
    ),
    "qa": AgentSpec(
        key="qa",
        name="测试工程师",
        icon="🧪",
        system_prompt=QA_SYSTEM,
        idle_message="🧪 测试工程师正在验收代码…",
        max_tokens=1500,
    ),
}

# SSE 事件回调：收到一个事件字典就往前端推一帧
EventEmitter = Callable[[dict[str, Any]], Awaitable[None]]


@dataclass
class StageResult:
    key: str
    name: str
    icon: str
    content: str
    duration_ms: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "stage": self.key,
            "name": self.name,
            "icon": self.icon,
            "duration_ms": self.duration_ms,
            "chars": len(self.content),
        }


@dataclass
class GenerationResult:
    product_spec: str | None
    architecture: str | None
    html_code: str
    review: str | None = None
    stages: list[StageResult] = field(default_factory=list)
    model: str = ""
    duration_ms: int = 0
    # 静态检查没能自动修好时，把问题带出去给前端提示（不阻断交付）
    validation_warning: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "product_spec": self.product_spec,
            "architecture": self.architecture,
            "html_code": self.html_code,
            "review": self.review,
            "stages": [s.to_dict() for s in self.stages],
            "model": self.model,
            "duration_ms": self.duration_ms,
            "validation_warning": self.validation_warning,
        }


class MultiAgentOrchestrator:
    """把「一个需求」变成「一份可运行 HTML」的接力编排器。"""

    def __init__(self, llm: BaseChatModel | None = None) -> None:
        self.settings = get_settings()
        self._custom_llm = llm is not None
        self.llm = llm or build_llm()
        self._stage_llms: dict[str, BaseChatModel] = {}
        self.model_name = (
            getattr(self.llm, "model_name", None) or getattr(self.llm, "model", None) or "unknown"
        )

    def _llm_for(self, agent: AgentSpec) -> BaseChatModel:
        """按阶段取模型。

        本地 CPU 推理时，产品经理 / 架构师这两个「爱写小作文」的阶段如果不加限制，
        能一路写到几千字，比工程师生成代码还慢。给它们单独压低输出上限。
        """
        cap = agent.max_tokens
        if self._custom_llm or not cap or cap >= self.settings.llm_max_tokens:
            return self.llm
        if agent.key not in self._stage_llms:
            self._stage_llms[agent.key] = build_llm(max_tokens=cap)
        return self._stage_llms[agent.key]

    # -----------------------------------------------------------
    # 内部工具
    # -----------------------------------------------------------
    @staticmethod
    async def _emit(emit: EventEmitter | None, event: dict[str, Any]) -> None:
        if emit is not None:
            await emit(event)

    async def _run_stage(
        self,
        agent: AgentSpec,
        human_text: str,
        emit: EventEmitter | None = None,
        *,
        stream: bool = True,
    ) -> StageResult:
        """跑一个 Agent 阶段，并把「开始 / 增量 token / 结束」推给回调。"""
        await self._emit(
            emit,
            {
                "type": "stage_start",
                "stage": agent.key,
                "name": agent.name,
                "agent": agent.icon,
                "message": agent.idle_message,
            },
        )

        messages = [
            SystemMessage(content=agent.system_prompt),
            HumanMessage(content=human_text),
        ]
        llm = self._llm_for(agent)
        started = time.perf_counter()
        collected: list[str] = []
        pending: list[str] = []
        pending_len = 0

        try:
            if stream:
                async for chunk in llm.astream(messages):
                    piece = content_to_text(chunk)
                    if not piece:
                        continue
                    collected.append(piece)
                    pending.append(piece)
                    pending_len += len(piece)
                    if pending_len >= TOKEN_FLUSH_CHARS:
                        await self._emit(
                            emit,
                            {
                                "type": "token",
                                "stage": agent.key,
                                "agent": agent.icon,
                                "delta": "".join(pending),
                            },
                        )
                        pending, pending_len = [], 0
            else:
                message = await llm.ainvoke(messages)
                piece = content_to_text(message)
                collected.append(piece)
                pending.append(piece)
        except GenerationError:
            raise
        except Exception as exc:  # noqa: BLE001 - 统一收敛成对用户友好的错误
            raise GenerationError(f"{agent.name}阶段执行失败：{exc}") from exc

        if pending:
            await self._emit(
                emit,
                {
                    "type": "token",
                    "stage": agent.key,
                    "agent": agent.icon,
                    "delta": "".join(pending),
                },
            )

        content = "".join(collected).strip()
        duration_ms = int((time.perf_counter() - started) * 1000)
        await self._emit(
            emit,
            {
                "type": "stage_complete",
                "stage": agent.key,
                "name": agent.name,
                "agent": agent.icon,
                "duration_ms": duration_ms,
                # 工程师的产出会通过 complete 事件下发，这里不再重复回传大段 HTML
                "content": "" if agent.key in {"engineer", "engineer_modify"} else content,
                "message": f"{agent.icon} {agent.name}完成（{duration_ms / 1000:.1f}s）",
            },
        )
        return StageResult(
            key=agent.key,
            name=agent.name,
            icon=agent.icon,
            content=content,
            duration_ms=duration_ms,
        )

    async def _ensure_valid_html(
        self, html: str, emit: EventEmitter | None = None
    ) -> tuple[str, str | None]:
        """静态校验产物；不合格就让工程师带着错误报告自修一轮。

        为什么单独立一步：AI 写前端最容易犯的是括号/引号不匹配，而浏览器遇到
        JS 语法错误会**丢弃整个 <script>** —— 页面看着完好，交互全死（实测踩过：
        多一个右括号，输入框改了什么反应都没有）。人肉看代码没发现，
        `node --check` 一跑就定位到行号。

        返回 (最终 HTML, 未修复的警告)。修不好也不阻断交付，只带一条警告出去。
        """
        passed, report = check_html(html)
        if passed:
            return html, None

        try:
            repaired = await self._run_stage(
                AGENTS["engineer_repair"],
                f"【静态检查报告】\n{report}\n\n【当前 HTML】\n{html}",
                emit,
            )
        except GenerationError as exc:
            return html, f"产物静态检查未通过，且自修失败（{exc}）。已交付原始产物，交互可能不可用。"

        fixed = extract_html(repaired.content)
        if not looks_like_html(fixed):
            return html, f"产物静态检查未通过（{report}），自修产出不完整。已交付原始产物。"

        passed_again, report_again = check_html(fixed)
        if not passed_again:
            return fixed, f"自修后仍存在静态问题：{report_again}。页面交互可能不可用。"
        return fixed, None

    # -----------------------------------------------------------
    # 主流程
    # -----------------------------------------------------------
    async def generate(
        self, user_input: str, emit: EventEmitter | None = None
    ) -> GenerationResult:
        """需求 → 产品规格 → 架构方案 → HTML。"""
        user_input = (user_input or "").strip()
        if len(user_input) < 2:
            raise GenerationError("需求描述太短了，请把想做的应用说清楚一点")

        mode = (self.settings.agent_mode or "chain").lower()
        if mode == "agent":
            return await self._generate_with_agent(user_input, emit)
        if mode == "tool":
            return await self._generate_with_tools(user_input, emit)
        return await self._generate_with_chain(user_input, emit)

    async def _generate_with_chain(
        self, user_input: str, emit: EventEmitter | None
    ) -> GenerationResult:
        started = time.perf_counter()
        stages: list[StageResult] = []
        await self._emit(emit, {"type": "pipeline_start", "agents": self.agent_roster()})

        pm = await self._run_stage(AGENTS["pm"], f"【用户需求】\n{user_input}", emit)
        stages.append(pm)

        architect = await self._run_stage(
            AGENTS["architect"],
            f"【用户原始需求】\n{user_input}\n\n【产品规格】\n{pm.content}",
            emit,
        )
        stages.append(architect)

        engineer = await self._run_stage(
            AGENTS["engineer"],
            (
                f"【用户原始需求】\n{user_input}\n\n"
                f"【产品规格】\n{pm.content}\n\n"
                f"【架构方案】\n{architect.content}"
            ),
            emit,
        )
        stages.append(engineer)

        html_code = extract_html(engineer.content)
        _assert_complete_html(html_code)
        html_code, validation_warning = await self._ensure_valid_html(html_code, emit)

        review: str | None = None
        if self.settings.enable_qa_stage:
            qa = await self._run_stage(
                AGENTS["qa"],
                f"【产品需求】\n{user_input}\n\n【待评审代码】\n{html_code}",
                emit,
            )
            stages.append(qa)
            review = qa.content

        return GenerationResult(
            product_spec=pm.content,
            architecture=architect.content,
            html_code=html_code,
            review=review,
            stages=stages,
            model=self.model_name,
            duration_ms=int((time.perf_counter() - started) * 1000),
            validation_warning=validation_warning,
        )

    async def _generate_with_tools(
        self, user_input: str, emit: EventEmitter | None
    ) -> GenerationResult:
        """走 LangChain 工具层接力（无 token 级流式，只有阶段进度）。"""
        from .tools import analyze_requirement, design_architecture, generate_code

        started = time.perf_counter()
        stages: list[StageResult] = []
        await self._emit(emit, {"type": "pipeline_start", "agents": self.agent_roster()})

        async def run(agent: AgentSpec, coro_factory) -> StageResult:
            await self._emit(
                emit,
                {
                    "type": "stage_start",
                    "stage": agent.key,
                    "name": agent.name,
                    "agent": agent.icon,
                    "message": agent.idle_message,
                },
            )
            tick = time.perf_counter()
            try:
                content = await asyncio.to_thread(coro_factory)
            except Exception as exc:  # noqa: BLE001
                raise GenerationError(f"{agent.name}阶段执行失败：{exc}") from exc
            duration_ms = int((time.perf_counter() - tick) * 1000)
            content = str(content).strip()
            await self._emit(
                emit,
                {
                    "type": "stage_complete",
                    "stage": agent.key,
                    "name": agent.name,
                    "agent": agent.icon,
                    "duration_ms": duration_ms,
                    "message": f"{agent.icon} {agent.name}完成（{duration_ms / 1000:.1f}s）",
                },
            )
            return StageResult(agent.key, agent.name, agent.icon, content, duration_ms)

        pm = await run(
            AGENTS["pm"], lambda: analyze_requirement.invoke({"user_input": user_input})
        )
        stages.append(pm)
        architect = await run(
            AGENTS["architect"],
            lambda: design_architecture.invoke({"product_spec": pm.content}),
        )
        stages.append(architect)
        engineer = await run(
            AGENTS["engineer"],
            lambda: generate_code.invoke(
                {"architecture": architect.content, "user_input": user_input}
            ),
        )
        stages.append(engineer)

        html_code = extract_html(str(engineer.content))
        _assert_complete_html(html_code)
        html_code, validation_warning = await self._ensure_valid_html(html_code, emit)

        return GenerationResult(
            product_spec=pm.content,
            architecture=architect.content,
            html_code=html_code,
            stages=stages,
            model=self.model_name,
            duration_ms=int((time.perf_counter() - started) * 1000),
            validation_warning=validation_warning,
        )

    async def _generate_with_agent(
        self, user_input: str, emit: EventEmitter | None
    ) -> GenerationResult:
        """由 create_agent 自主决定工具调用顺序（规格书里提到的 Agent 模式）。"""
        from .tools import build_tool_agent

        try:
            agent = build_tool_agent()
        except ImportError as exc:
            raise GenerationError(str(exc)) from exc

        started = time.perf_counter()
        roster = self.agent_roster()
        await self._emit(
            emit,
            {
                "type": "pipeline_start",
                "agents": roster,
                "message": "🤖 调度 Agent 正在自主编排工具调用…",
            },
        )
        for spec in (AGENTS["pm"], AGENTS["architect"], AGENTS["engineer"]):
            await self._emit(
                emit,
                {
                    "type": "stage_start",
                    "stage": spec.key,
                    "name": spec.name,
                    "agent": spec.icon,
                    "message": spec.idle_message,
                },
            )

        try:
            state = await agent.ainvoke(
                {"messages": [HumanMessage(content=f"【用户需求】\n{user_input}")]},
                config={"recursion_limit": 25},
            )
        except Exception as exc:  # noqa: BLE001
            raise GenerationError(f"Agent 模式执行失败：{exc}") from exc

        tool_outputs: dict[str, str] = {}
        for message in state.get("messages", []):
            name = getattr(message, "name", None)
            if name and name in {"analyze_requirement", "design_architecture", "generate_code"}:
                tool_outputs[name] = content_to_text(message).strip()

        product_spec = tool_outputs.get("analyze_requirement", "")
        architecture = tool_outputs.get("design_architecture", "")
        html_code = extract_html(tool_outputs.get("generate_code", ""))
        if not looks_like_html(html_code):
            raise GenerationError("Agent 模式没有产出完整 HTML，请改用 AGENT_MODE=chain 重试")
        html_code, validation_warning = await self._ensure_valid_html(html_code, emit)

        duration_ms = int((time.perf_counter() - started) * 1000)
        stages = [
            StageResult("pm", "产品经理", "🧑‍💼", product_spec, 0),
            StageResult("architect", "架构师", "🏗️", architecture, 0),
            StageResult("engineer", "工程师", "👨‍💻", html_code, 0),
        ]
        for stage in stages:
            await self._emit(
                emit,
                {
                    "type": "stage_complete",
                    "stage": stage.key,
                    "name": stage.name,
                    "agent": stage.icon,
                    "duration_ms": 0,
                    "message": f"{stage.icon} {stage.name}完成",
                },
            )

        return GenerationResult(
            product_spec=product_spec,
            architecture=architecture,
            html_code=html_code,
            stages=stages,
            model=self.model_name,
            duration_ms=duration_ms,
            validation_warning=validation_warning,
        )

    # -----------------------------------------------------------
    # 多轮修改 / 代码评审
    # -----------------------------------------------------------
    async def modify(
        self,
        current_html: str,
        modification: str,
        emit: EventEmitter | None = None,
    ) -> GenerationResult:
        """基于当前版本继续修改（不重新跑产品/架构两轮）。"""
        current_html = (current_html or "").strip()
        modification = (modification or "").strip()
        if not current_html:
            raise GenerationError("当前版本没有代码，无法修改")
        if len(current_html) > MAX_HTML_CHARS:
            raise GenerationError("当前版本代码过长，请新建项目重做")
        if len(modification) < 2:
            raise GenerationError("修改要求太短了")

        started = time.perf_counter()
        await self._emit(
            emit,
            {
                "type": "pipeline_start",
                "agents": [
                    {
                        "key": AGENTS["engineer_modify"].key,
                        "name": AGENTS["engineer_modify"].name,
                        "icon": AGENTS["engineer_modify"].icon,
                    }
                ],
            },
        )
        stage = await self._run_stage(
            AGENTS["engineer_modify"],
            f"【当前 HTML 代码】\n{current_html}\n\n【修改要求】\n{modification}",
            emit,
        )
        html_code = extract_html(stage.content)
        _assert_complete_html(html_code, prefix="修改后的产出")
        html_code, validation_warning = await self._ensure_valid_html(html_code, emit)

        return GenerationResult(
            product_spec=None,
            architecture=None,
            html_code=html_code,
            stages=[stage],
            model=self.model_name,
            duration_ms=int((time.perf_counter() - started) * 1000),
            validation_warning=validation_warning,
        )

    async def review(self, html_code: str, emit: EventEmitter | None = None) -> str:
        """测试工程师视角的代码评审。"""
        if not (html_code or "").strip():
            raise GenerationError("没有可评审的代码")
        stage = await self._run_stage(
            AGENTS["qa"], f"【待评审代码】\n{html_code[:MAX_HTML_CHARS]}", emit
        )
        return stage.content

    # -----------------------------------------------------------
    # 元信息
    # -----------------------------------------------------------
    def agent_roster(self) -> list[dict[str, str]]:
        keys = ["pm", "architect", "engineer"] + (["qa"] if self.settings.enable_qa_stage else [])
        return [{"key": AGENTS[k].key, "name": AGENTS[k].name, "icon": AGENTS[k].icon} for k in keys]

    @property
    def roster_names(self) -> Sequence[str]:
        return [item["name"] for item in self.agent_roster()]


# ---------------------------------------------------------------
# 兼容规格书中的调用方式
# ---------------------------------------------------------------
async def orchestrate_generation(user_input: str, on_progress=None) -> dict[str, Any]:
    """多智能体接力生成。

    与规格书保持一致的入参/出参：
        on_progress(message: str) 是一个「可 await」的回调；
        返回 {"product_spec": ..., "architecture": ..., "html_code": ...}
    """
    orchestrator = MultiAgentOrchestrator()

    async def emit(event: dict[str, Any]) -> None:
        if on_progress is None:
            return
        if event["type"] == "stage_start":
            await on_progress(event["message"])

    result = await orchestrator.generate(user_input, emit)
    return {
        "product_spec": result.product_spec,
        "architecture": result.architecture,
        "html_code": result.html_code,
        "review": result.review,
        "stages": [s.to_dict() for s in result.stages],
        "model": result.model,
        "duration_ms": result.duration_ms,
    }
