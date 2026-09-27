"""LLM 通路自检：先确认模型能连通，再（可选）跑一遍完整的多智能体流水线。

用法（在 backend 目录下执行）：

    python scripts/smoke_llm.py                 # 只做连通性 + 流式检查，几秒钟
    python scripts/smoke_llm.py --full          # 跑完整流水线，产出 HTML 存到 scripts/out/
    python scripts/smoke_llm.py --full "做一个记账本"
"""

from __future__ import annotations

import asyncio
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from langchain_core.messages import HumanMessage, SystemMessage  # noqa: E402

from app.agents import MultiAgentOrchestrator, extract_html, looks_like_html  # noqa: E402
from app.config import get_settings  # noqa: E402
from app.llm import build_llm  # noqa: E402


async def check_connectivity() -> bool:
    settings = get_settings()
    print(f"provider={settings.llm_provider}  model={settings.llm_model_name}  agent_mode={settings.agent_mode}")
    try:
        llm = build_llm()
    except Exception as exc:  # noqa: BLE001
        print(f"[失败] 没法创建模型客户端：{exc}")
        return False

    print("\n--- 1. 非流式调用 ---")
    started = time.perf_counter()
    try:
        message = await llm.ainvoke(
            [SystemMessage(content="你是一个简洁的助手，只回答要求的字面内容。"), HumanMessage(content="只回复两个字：通了")]
        )
    except Exception as exc:  # noqa: BLE001
        print(f"[失败] 调用出错：{exc}")
        print("排查：Ollama 是否在运行？模型是否已 pull？BASE_URL 是否正确？")
        return False
    print(f"回复：{message.content!r}  耗时 {time.perf_counter() - started:.1f}s")

    print("\n--- 2. 流式调用（连接接力引擎用的就是这条通路）---")
    started = time.perf_counter()
    pieces = 0
    buffer = []
    async for chunk in llm.astream([HumanMessage(content="用一句话说明什么是待办清单")]):
        text = getattr(chunk, "content", "")
        if text:
            pieces += 1
            buffer.append(text)
    print(f"收到 {pieces} 个增量分片，合计 {len(''.join(buffer))} 字，耗时 {time.perf_counter() - started:.1f}s")
    print(f"内容：{''.join(buffer).strip()[:60]}…")
    return pieces > 0


async def run_pipeline(prompt: str) -> bool:
    print(f"\n--- 3. 完整流水线：{prompt} ---")
    orchestrator = MultiAgentOrchestrator()
    started = time.perf_counter()
    stage_started = time.perf_counter()
    tokens = 0

    async def on_event(event: dict) -> None:
        nonlocal stage_started, tokens
        if event["type"] == "stage_start":
            stage_started = time.perf_counter()
            print(f"\n▶ {event['message']}")
        elif event["type"] == "token":
            tokens += len(event.get("delta", ""))
            if tokens % 400 < 100:
                print(f"    …已收到 {tokens} 字", end="\r")
        elif event["type"] == "stage_complete":
            print(f"✓ {event['stage']:16} {time.perf_counter() - stage_started:6.1f}s")

    result = await orchestrator.generate(prompt, on_event)

    print(f"\n总耗时 {time.perf_counter() - started:.1f}s  模型 {result.model}")
    print(f"产物：{len(result.html_code)} 字符 / {len(result.html_code.splitlines())} 行")

    ok = looks_like_html(extract_html(result.html_code))
    print(f"产物校验（是不是完整 HTML）：{'通过' if ok else '不通过'}")

    out_dir = Path(__file__).resolve().parent / "out"
    out_dir.mkdir(exist_ok=True)
    target = out_dir / "generated.html"
    target.write_text(result.html_code, encoding="utf-8")
    print(f"已保存：{target}")
    return ok


async def main() -> int:
    if not await check_connectivity():
        return 1
    if "--full" not in sys.argv:
        print("\n连通性检查通过。（加 --full 可以顺带跑一遍完整流水线）")
        return 0
    args = [a for a in sys.argv[1:] if a != "--full"]
    prompt = args[0] if args else "做一个待办清单：可以新增、勾选完成、删除，数据存 localStorage"
    return 0 if await run_pipeline(prompt) else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
