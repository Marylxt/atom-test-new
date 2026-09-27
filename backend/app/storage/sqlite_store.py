"""本地 SQLite 存储后端。

用途：没接 Supabase 时也能完整跑通整个 Demo（生成 → 实时预览 → 多轮修改 → 版本回滚 → 发布分享）。
接口与 `supabase_store.py` 一一对应，由 `repository.py` 按 `STORAGE_BACKEND` 选择。

设计取舍：
- 单文件、零依赖，`data/atoms.db`（路径可用 `SQLITE_PATH` 覆盖）；
- 开启 WAL，读写不互相阻塞；
- 所有阻塞 IO 都丢到线程池，不占事件循环；
- 版本号自增用进程内锁串行化，避免并发生成撞号。
"""

from __future__ import annotations

import secrets
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

import anyio

from ..config import get_settings

# ---------------------------------------------------------------
# 建表
# ---------------------------------------------------------------
SCHEMA = """
create table if not exists projects (
    id                 text primary key,
    user_id            text not null,
    name               text not null,
    description        text,
    status             text not null default 'draft',
    current_version_id text,
    created_at         text not null,
    updated_at         text not null
);

create table if not exists versions (
    id                text primary key,
    project_id        text not null references projects (id) on delete cascade,
    version_no        integer not null,
    prompt            text not null default '',
    product_spec      text,
    architecture      text,
    html_code         text not null default '',
    review            text,
    change_type       text not null default 'create',
    parent_version_id text,
    model             text,
    duration_ms       integer,
    created_at        text not null,
    unique (project_id, version_no)
);

create table if not exists publications (
    id         text primary key,
    project_id text not null references projects (id) on delete cascade,
    version_id text not null references versions (id) on delete cascade,
    public_id  text not null unique,
    title      text,
    views      integer not null default 0,
    is_active  integer not null default 1,
    created_at text not null
);

create table if not exists generation_events (
    id         integer primary key autoincrement,
    project_id text not null references projects (id) on delete cascade,
    version_id text,
    stage      text not null,
    message    text not null,
    level      text not null default 'info',
    created_at text not null
);

create index if not exists idx_projects_user  on projects (user_id, updated_at desc);
create index if not exists idx_versions_proj  on versions (project_id, version_no desc);
create index if not exists idx_pub_project    on publications (project_id, created_at desc);
create index if not exists idx_events_project on generation_events (project_id, created_at desc);
"""

VERSION_LIST_COLUMNS = (
    "id, project_id, version_no, prompt, change_type, parent_version_id, model, duration_ms, created_at"
)

_init_lock = threading.Lock()
_write_lock = threading.Lock()
_initialized = False


# ---------------------------------------------------------------
# 连接与调度
# ---------------------------------------------------------------
def _db_path() -> Path:
    path = Path(get_settings().sqlite_path)
    if not path.is_absolute():
        path = Path.cwd() / path
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(_db_path(), timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("pragma journal_mode=wal")
    conn.execute("pragma foreign_keys=on")
    return conn


def _ensure_schema() -> None:
    global _initialized
    if _initialized:
        return
    with _init_lock:
        if _initialized:
            return
        with _connect() as conn:
            conn.executescript(SCHEMA)
        _initialized = True


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _uuid() -> str:
    return secrets.token_hex(16)


def _sync_call(fn: Callable[..., Any], *args: Any) -> Any:
    _ensure_schema()
    return fn(*args)


async def _run(fn: Callable[..., Any], *args: Any) -> Any:
    return await anyio.to_thread.run_sync(_sync_call, fn, *args)


def _row(row: sqlite3.Row | None) -> dict[str, Any] | None:
    return dict(row) if row is not None else None


def _rows(rows: list[sqlite3.Row]) -> list[dict[str, Any]]:
    return [dict(row) for row in rows]


# ---------------------------------------------------------------
# projects
# ---------------------------------------------------------------
def _list_projects_sync(user_id: str) -> list[dict[str, Any]]:
    with _connect() as conn:
        projects = _rows(
            conn.execute(
                "select * from projects where user_id = ? order by updated_at desc", (user_id,)
            ).fetchall()
        )
        stats = {
            row["project_id"]: (row["c"], row["m"])
            for row in conn.execute(
                "select project_id, count(*) as c, max(version_no) as m from versions group by project_id"
            ).fetchall()
        }
    for project in projects:
        count, latest = stats.get(project["id"], (0, None))
        project["version_count"] = count
        project["latest_version_no"] = latest
    return projects


async def list_projects(user_id: str) -> list[dict[str, Any]]:
    return await _run(_list_projects_sync, user_id)


def _get_project_sync(project_id: str) -> dict[str, Any] | None:
    with _connect() as conn:
        return _row(conn.execute("select * from projects where id = ?", (project_id,)).fetchone())


async def get_project(project_id: str) -> dict[str, Any] | None:
    return await _run(_get_project_sync, project_id)


def _get_owned_project_sync(project_id: str, user_id: str) -> dict[str, Any] | None:
    with _connect() as conn:
        return _row(
            conn.execute(
                "select * from projects where id = ? and user_id = ?", (project_id, user_id)
            ).fetchone()
        )


async def get_owned_project(project_id: str, user_id: str) -> dict[str, Any] | None:
    return await _run(_get_owned_project_sync, project_id, user_id)


def _create_project_sync(user_id: str, name: str, description: str | None) -> dict[str, Any]:
    now = _now()
    project_id = _uuid()
    payload = {
        "id": project_id,
        "user_id": user_id,
        "name": name.strip(),
        "description": (description or "").strip() or None,
        "status": "draft",
        "current_version_id": None,
        "created_at": now,
        "updated_at": now,
    }
    with _connect() as conn:
        conn.execute(
            "insert into projects (id, user_id, name, description, status, current_version_id,"
            " created_at, updated_at) values (:id, :user_id, :name, :description, :status,"
            " :current_version_id, :created_at, :updated_at)",
            payload,
        )
        created = conn.execute("select * from projects where id = ?", (project_id,)).fetchone()
    return dict(created)


async def create_project(user_id: str, name: str, description: str | None = None) -> dict[str, Any]:
    return await _run(_create_project_sync, user_id, name, description)


def _update_project_sync(project_id: str, fields: dict[str, Any]) -> dict[str, Any] | None:
    payload = {key: value for key, value in fields.items() if value is not None}
    with _connect() as conn:
        if payload:
            payload["updated_at"] = _now()
            assignments = ", ".join(f"{key} = :{key}" for key in payload)
            payload["project_id"] = project_id
            conn.execute(
                f"update projects set {assignments} where id = :project_id",  # noqa: S608 - 列名来自内部白名单
                payload,
            )
        return _row(conn.execute("select * from projects where id = ?", (project_id,)).fetchone())


async def update_project(project_id: str, fields: dict[str, Any]) -> dict[str, Any] | None:
    return await _run(_update_project_sync, project_id, fields)


def _delete_project_sync(project_id: str) -> None:
    with _connect() as conn:
        conn.execute("delete from projects where id = ?", (project_id,))


async def delete_project(project_id: str) -> None:
    await _run(_delete_project_sync, project_id)


# ---------------------------------------------------------------
# versions
# ---------------------------------------------------------------
def _list_versions_sync(project_id: str, limit: int) -> list[dict[str, Any]]:
    with _connect() as conn:
        return _rows(
            conn.execute(
                f"select {VERSION_LIST_COLUMNS} from versions where project_id = ?"
                " order by version_no desc limit ?",
                (project_id, limit),
            ).fetchall()
        )


async def list_versions(project_id: str, limit: int = 50) -> list[dict[str, Any]]:
    return await _run(_list_versions_sync, project_id, limit)


def _get_version_sync(version_id: str) -> dict[str, Any] | None:
    with _connect() as conn:
        return _row(conn.execute("select * from versions where id = ?", (version_id,)).fetchone())


async def get_version(version_id: str) -> dict[str, Any] | None:
    return await _run(_get_version_sync, version_id)


def _latest_version_sync(project_id: str) -> dict[str, Any] | None:
    with _connect() as conn:
        return _row(
            conn.execute(
                "select * from versions where project_id = ? order by version_no desc limit 1",
                (project_id,),
            ).fetchone()
        )


async def get_current_version(project: dict[str, Any]) -> dict[str, Any] | None:
    """优先按 projects.current_version_id 取，否则退回最新一条版本。"""
    version_id = project.get("current_version_id")
    if version_id:
        version = await get_version(version_id)
        if version:
            return version
    return await _run(_latest_version_sync, project["id"])


def _next_version_no_sync(conn: sqlite3.Connection, project_id: str) -> int:
    row = conn.execute(
        "select max(version_no) as m from versions where project_id = ?", (project_id,)
    ).fetchone()
    return int(row["m"] or 0) + 1


async def next_version_no(project_id: str) -> int:
    def _sync() -> int:
        with _connect() as conn:
            return _next_version_no_sync(conn, project_id)

    return await _run(_sync)


def _create_version_sync(project_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    # 取号 + 写入 + 回写 current_version_id 必须在同一个事务里，否则并发会撞版本号
    with _write_lock, _connect() as conn:
        version_no = _next_version_no_sync(conn, project_id)
        row = {
            "id": _uuid(),
            "project_id": project_id,
            "version_no": version_no,
            "prompt": payload.get("prompt") or "",
            "product_spec": payload.get("product_spec"),
            "architecture": payload.get("architecture"),
            "html_code": payload.get("html_code") or "",
            "review": payload.get("review"),
            "change_type": payload.get("change_type", "create"),
            "parent_version_id": payload.get("parent_version_id"),
            "model": payload.get("model"),
            "duration_ms": payload.get("duration_ms"),
            "created_at": _now(),
        }
        conn.execute(
            "insert into versions (id, project_id, version_no, prompt, product_spec, architecture,"
            " html_code, review, change_type, parent_version_id, model, duration_ms, created_at)"
            " values (:id, :project_id, :version_no, :prompt, :product_spec, :architecture,"
            " :html_code, :review, :change_type, :parent_version_id, :model, :duration_ms, :created_at)",
            row,
        )
        conn.execute(
            "update projects set current_version_id = ?, status = 'ready', updated_at = ? where id = ?",
            (row["id"], _now(), project_id),
        )
        return row


async def create_version(project_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    return await _run(_create_version_sync, project_id, payload)


# ---------------------------------------------------------------
# generation_events
# ---------------------------------------------------------------
def _log_event_sync(
    project_id: str, stage: str, message: str, level: str, version_id: str | None
) -> None:
    with _connect() as conn:
        conn.execute(
            "insert into generation_events (project_id, version_id, stage, message, level, created_at)"
            " values (?, ?, ?, ?, ?, ?)",
            (project_id, version_id, stage, message[:2000], level, _now()),
        )


async def log_event(
    project_id: str,
    stage: str,
    message: str,
    level: str = "info",
    version_id: str | None = None,
) -> None:
    """记录一条生成过程日志；失败不影响主流程。"""
    try:
        await _run(_log_event_sync, project_id, stage, message, level, version_id)
    except Exception:  # noqa: BLE001 - 日志属于旁路
        pass


def _list_events_sync(project_id: str, limit: int) -> list[dict[str, Any]]:
    with _connect() as conn:
        return _rows(
            conn.execute(
                "select * from generation_events where project_id = ?"
                " order by created_at desc limit ?",
                (project_id, limit),
            ).fetchall()
        )


async def list_events(project_id: str, limit: int = 100) -> list[dict[str, Any]]:
    return await _run(_list_events_sync, project_id, limit)


# ---------------------------------------------------------------
# publications
# ---------------------------------------------------------------
def new_public_id() -> str:
    """12 位短链 ID（URL 安全）。"""
    return secrets.token_urlsafe(9)[:12]


def _normalize_publication(row: sqlite3.Row | None) -> dict[str, Any] | None:
    if row is None:
        return None
    data = dict(row)
    data["is_active"] = bool(data.get("is_active"))
    return data


def _create_publication_sync(project_id: str, version_id: str, title: str | None) -> dict[str, Any]:
    row = {
        "id": _uuid(),
        "project_id": project_id,
        "version_id": version_id,
        "public_id": new_public_id(),
        "title": title,
        "views": 0,
        "is_active": 1,
        "created_at": _now(),
    }
    with _connect() as conn:
        conn.execute(
            "insert into publications (id, project_id, version_id, public_id, title, views,"
            " is_active, created_at) values (:id, :project_id, :version_id, :public_id, :title,"
            " :views, :is_active, :created_at)",
            row,
        )
    return {**row, "is_active": True}


async def create_publication(
    project_id: str, version_id: str, title: str | None = None
) -> dict[str, Any]:
    return await _run(_create_publication_sync, project_id, version_id, title)


def _list_publications_sync(user_id: str) -> list[dict[str, Any]]:
    with _connect() as conn:
        rows = conn.execute(
            "select p.* from publications p join projects j on j.id = p.project_id"
            " where j.user_id = ? order by p.created_at desc",
            (user_id,),
        ).fetchall()
    return [_normalize_publication(row) for row in rows]  # type: ignore[misc]


async def list_publications(user_id: str) -> list[dict[str, Any]]:
    return await _run(_list_publications_sync, user_id)


def _get_publication_sync(public_id: str) -> dict[str, Any] | None:
    with _connect() as conn:
        return _normalize_publication(
            conn.execute(
                "select * from publications where public_id = ? and is_active = 1", (public_id,)
            ).fetchone()
        )


async def get_publication(public_id: str) -> dict[str, Any] | None:
    return await _run(_get_publication_sync, public_id)


def _get_owned_publication_sync(publication_id: str, user_id: str) -> dict[str, Any] | None:
    with _connect() as conn:
        return _normalize_publication(
            conn.execute(
                "select p.* from publications p join projects j on j.id = p.project_id"
                " where p.id = ? and j.user_id = ?",
                (publication_id, user_id),
            ).fetchone()
        )


async def get_owned_publication(publication_id: str, user_id: str) -> dict[str, Any] | None:
    return await _run(_get_owned_publication_sync, publication_id, user_id)


def _deactivate_publication_sync(publication_id: str) -> None:
    with _connect() as conn:
        conn.execute("update publications set is_active = 0 where id = ?", (publication_id,))


async def deactivate_publication(publication_id: str) -> None:
    await _run(_deactivate_publication_sync, publication_id)


def _increment_views_sync(public_id: str) -> None:
    with _connect() as conn:
        conn.execute(
            "update publications set views = views + 1 where public_id = ? and is_active = 1",
            (public_id,),
        )


async def increment_views(public_id: str) -> None:
    try:
        await _run(_increment_views_sync, public_id)
    except Exception:  # noqa: BLE001 - 统计失败不影响渲染
        pass


# ---------------------------------------------------------------
# 健康检查
# ---------------------------------------------------------------
async def ping() -> bool:
    def _sync() -> bool:
        with _connect() as conn:
            conn.execute("select 1 from projects limit 1")
        return True

    try:
        return await _run(_sync)
    except Exception:  # noqa: BLE001
        return False


__all__ = [
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
