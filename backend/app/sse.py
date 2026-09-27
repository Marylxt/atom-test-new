"""SSE（Server-Sent Events）工具。

产物格式同时兼容两种解析方式：
- 标准 `event: xxx` + `data: {...}` 分帧；
- `data` 内部再带一个 `type` 字段（规格书里用的写法）。

这样无论前端用原生 EventSource 还是 fetch + ReadableStream 手写解析都能消费。
"""

from __future__ import annotations

import json
from typing import Any

SSE_HEADERS = {
    "Cache-Control": "no-cache, no-transform",
    "Connection": "keep-alive",
    # 关掉 Nginx 反向代理的缓冲，否则流会被攒成一坨再下发
    "X-Accel-Buffering": "no",
}


def sse(event: str, data: dict[str, Any]) -> str:
    """把一条事件编码成 SSE 帧。"""
    payload = {"type": event, **data}
    body = json.dumps(payload, ensure_ascii=False, default=str)
    return f"event: {event}\ndata: {body}\n\n"


def sse_comment(text: str = "keep-alive") -> str:
    """注释帧，用于保活（客户端会自动忽略）。"""
    return f": {text}\n\n"


def parse_sse_frame(frame: str) -> dict[str, Any] | None:
    """服务端自测用：把一帧 SSE 还原成字典。"""
    event = None
    data_lines: list[str] = []
    for line in frame.splitlines():
        if line.startswith("event:"):
            event = line[6:].strip()
        elif line.startswith("data:"):
            data_lines.append(line[5:].strip())
    if not data_lines:
        return None
    payload = json.loads("\n".join(data_lines))
    if event and "type" not in payload:
        payload["type"] = event
    return payload
