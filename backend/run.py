"""本地开发启动脚本：python run.py（默认 8000 端口，带热重载）。

生产环境请直接用：uvicorn app.main:app --host 0.0.0.0 --port $PORT
"""

from __future__ import annotations

import os

import uvicorn

if __name__ == "__main__":
    uvicorn.run(
        "app.main:app",
        host=os.getenv("HOST", "127.0.0.1"),
        port=int(os.getenv("PORT", "8000")),
        reload=os.getenv("DEBUG", "true").lower() in {"1", "true", "yes"},
        reload_dirs=["app"],
    )
