"""校验两个存储后端的接口契约是否一致。

背景：`repository.py` 是个门面，把调用转发给 `sqlite_store` 或 `supabase_store`。
两边只要有一个函数缺失或签名不一致，就会出现"切了后端才报 AttributeError"
（真事：曾经 supabase_store 少了 ping，导致连上 Supabase 后启动直接失败）。

用法：python scripts/check_backends.py
"""

from __future__ import annotations

import inspect
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.storage import sqlite_store, supabase_store  # noqa: E402

# 门面会转发的方法（必须两边都有）
REQUIRED = [
    "create_project",
    "create_publication",
    "create_version",
    "deactivate_publication",
    "delete_project",
    "get_current_version",
    "get_owned_project",
    "get_owned_publication",
    "get_project",
    "get_publication",
    "get_version",
    "increment_views",
    "list_events",
    "list_projects",
    "list_publications",
    "list_versions",
    "log_event",
    "new_public_id",
    "next_version_no",
    "ping",
    "update_project",
]

# 必须同样是协程的（否则没法 await）
ASYNC = [name for name in REQUIRED if name != "new_public_id"]


def main() -> int:
    failures: list[str] = []
    modules = {"sqlite": sqlite_store, "supabase": supabase_store}

    print("=== 1. 必需方法是否齐全 ===")
    for name in REQUIRED:
        missing = [label for label, module in modules.items() if not hasattr(module, name)]
        mark = "✓" if not missing else "✗"
        print(f"  {mark} {name:24}" + (f"  缺失于 {missing}" if missing else ""))
        if missing:
            failures.append(f"{name} 缺失于 {missing}")

    print("\n=== 2. 必需方法是否都是协程 ===")
    for name in ASYNC:
        broken = [
            label
            for label, module in modules.items()
            if not inspect.iscoroutinefunction(getattr(module, name, None))
        ]
        mark = "✓" if not broken else "✗"
        print(f"  {mark} {name:24}" + (f"  不是协程于 {broken}" if broken else ""))
        if broken:
            failures.append(f"{name} 不是协程于 {broken}")

    print("\n=== 3. 两边公开接口的差异（仅供参考）===")
    def public(module):
        return {
            name
            for name, value in vars(module).items()
            if not name.startswith("_") and (inspect.isfunction(value) or inspect.iscoroutinefunction(value))
        }

    only_sqlite = sorted(public(sqlite_store) - public(supabase_store))
    only_supabase = sorted(public(supabase_store) - public(sqlite_store))
    print(f"  仅 sqlite 有：{only_sqlite or '无'}")
    print(f"  仅 supabase 有：{only_supabase or '无'}")

    # 门面里实际用到的方法必须齐全
    print("\n=== 4. 与 repository 门面的调用是否对齐 ===")
    facade = Path(__file__).resolve().parents[1] / "app" / "repository.py"
    called: set[str] = set()
    for line in facade.read_text(encoding="utf-8").splitlines():
        if "backend()." not in line:
            continue
        name = line.split("backend().", 1)[1].split("(")[0].strip()
        if name.isidentifier():  # 过滤掉 __name__.rsplit 这类非方法名
            called.add(name)
    for name in sorted(called):
        ok = all(hasattr(module, name) for module in modules.values())
        print(f"  {'✓' if ok else '✗'} repository -> {name}")
        if not ok:
            failures.append(f"repository 调用了 {name}，但后端没有实现")
    unused = sorted(set(REQUIRED) - called)
    if unused:
        print(f"  · 已实现但门面未转发：{unused}")

    print()
    if failures:
        print(f"✗ 发现 {len(failures)} 个问题：")
        for item in failures:
            print(f"    - {item}")
        return 1
    print("✓ 两个后端接口契约一致")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
