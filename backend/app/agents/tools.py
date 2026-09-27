"""LangChain 工具层：把四位 Agent 包装成标准 Tool。

- `AGENT_MODE=tool`  → 编排器按顺序调用这些 Tool（接力式，不依赖具体 Agent 运行时）
- `AGENT_MODE=agent` → 交给 `langchain.agents.create_agent` 自主决策调用哪些 Tool

Tool 内部走同步 LLM 调用，只在工作线程中执行，不要直接在事件循环里 await。
"""

from __future__ import annotations

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.tools import tool

from ..llm import get_llm
from .prompts import (
    ARCHITECT_SYSTEM,
    ENGINEER_SYSTEM,
    PM_SYSTEM,
    QA_SYSTEM,
    content_to_text,
    extract_html,
)


def _ask(system_prompt: str, user_prompt: str) -> str:
    """一次性同步调用 LLM。"""
    llm = get_llm()
    message = llm.invoke(
        [SystemMessage(content=system_prompt), HumanMessage(content=user_prompt)]
    )
    return content_to_text(message).strip()


# ========== Agent 1: 产品经理 ==========
@tool
def analyze_requirement(user_input: str) -> str:
    """分析用户需求，输出产品功能清单和页面结构。"""
    prompt = f"""你是一个产品经理。根据用户需求，输出：
1. 应用名称和一句话描述
2. 核心功能列表（3-5个）
3. 页面结构（包含哪些页面/组件）
4. 数据交互说明

用户需求：{user_input}
"""
    return _ask(PM_SYSTEM, prompt)


# ========== Agent 2: 架构师 ==========
@tool
def design_architecture(product_spec: str) -> str:
    """根据产品规格，设计技术方案。"""
    prompt = f"""你是一个架构师。根据产品规格，输出：
1. 技术栈选择（纯前端 HTML/CSS/JS）
2. 数据模型设计（localStorage 或内嵌数据）
3. 组件拆分方案
4. 交互流程

产品规格：{product_spec}
"""
    return _ask(ARCHITECT_SYSTEM, prompt)


# ========== Agent 3: 工程师 ==========
@tool
def generate_code(architecture: str, user_input: str) -> str:
    """根据架构设计，生成完整可运行的 HTML 代码。"""
    prompt = f"""你是一个前端工程师。根据架构设计和用户需求，生成一个完整的、可运行的 HTML 文件。
要求：
- 包含完整的 HTML/CSS/JS
- 使用 Tailwind CSS CDN
- 具备真实交互功能
- 数据使用 localStorage 持久化
- 输入校验、空状态、溢出处理都要考虑到
- 代码整洁，有注释

用户需求：{user_input}
架构设计：{architecture}
"""
    return extract_html(_ask(ENGINEER_SYSTEM, prompt))


# ========== Agent 4: 测试工程师 ==========
@tool
def review_code(html_code: str) -> str:
    """以测试工程师视角评审生成的 HTML 代码，输出缺陷清单。"""
    prompt = f"""请评审下面这份 AI 生成的单页应用代码。

代码：
{html_code}
"""
    return _ask(QA_SYSTEM, prompt)


AGENT_TOOLS = [analyze_requirement, design_architecture, generate_code, review_code]

SUPERVISOR_SYSTEM = """你是一个研发团队的调度者，团队里有三位成员：
- analyze_requirement：产品经理，负责拆解需求；
- design_architecture：架构师，负责出技术方案；
- generate_code：工程师，负责产出完整 HTML。

用户会给你一个网页应用需求，你必须按「产品经理 → 架构师 → 工程师」的顺序依次调用工具：
先调用 analyze_requirement 拿到产品规格，把它的**原文**作为 design_architecture 的入参；
再调用 design_architecture 拿到架构方案，把它和用户原始需求一起作为 generate_code 的入参。
最后不要再调用任何工具，直接用一句话说明已完成即可（用户关心的是 generate_code 的产出）。"""


def build_tool_agent():
    """用 `langchain.agents.create_agent` 构建可自主编排的 Agent。

    不同 LangChain 版本里 `create_agent` 的位置不一致，这里做了兼容：
    找不到就抛 ImportError，由上层转成对用户友好的错误提示。
    """
    try:  # LangChain 1.x
        from langchain.agents import create_agent  # type: ignore
    except ImportError:  # pragma: no cover - 兼容旧版本
        try:
            from langgraph.prebuilt import create_react_agent as create_agent  # type: ignore
        except ImportError as exc:
            raise ImportError(
                "当前环境没有 create_agent，请升级 langchain（>=1.0）或改用 AGENT_MODE=tool"
            ) from exc

    return create_agent(
        model=get_llm(),
        tools=AGENT_TOOLS,
        system_prompt=SUPERVISOR_SYSTEM,
    )
