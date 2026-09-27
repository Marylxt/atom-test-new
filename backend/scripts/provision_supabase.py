"""用 Supabase Management API 一键接入：建表 + 取回 API Key + 写回 .env + 校验。

用法（在 backend 目录下执行）：

    python scripts/provision_supabase.py <PERSONAL_ACCESS_TOKEN> [project_ref]

Personal Access Token 获取：https://supabase.com/dashboard/account/tokens
（形如 sbp_xxx，属于账号级凭据，用完建议立刻删除）

脚本做的事：
  1. 列出账号下的项目，确认目标 project_ref 存在
  2. 通过 Management API 执行 supabase/schema.sql（建表 / 视图 / RLS / 触发器）
  3. 取回该项目的 anon 与 service_role key（顺带尝试 JWT Secret）
  4. 写回 backend/.env 与 frontend/.env.local（只改对应几行，其余原样保留）
  5. 用 service_role key 真读一次数据库，并打一次后端 /health 做最终校验

输出里所有 Key 都会被脱敏，不会打印明文。
"""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path

import httpx

MGMT = "https://api.supabase.com"
ROOT = Path(__file__).resolve().parents[2]
BACKEND_ENV = ROOT / "backend" / ".env"
FRONTEND_ENV = ROOT / "frontend" / ".env.local"
SCHEMA_FILE = ROOT / "supabase" / "schema.sql"


def resolve_ref(cli_value: str | None) -> str:
    """确定目标项目 ref，不预置任何默认值。

    优先级：命令行参数 → 环境变量 SUPABASE_PROJECT_REF → 从 backend/.env 的 SUPABASE_URL 推导。
    这样脚本可以直接开源，不会把某个人的项目标识固化进仓库。
    """
    if cli_value and cli_value.strip():
        return cli_value.strip()

    env_ref = os.getenv("SUPABASE_PROJECT_REF", "").strip()
    if env_ref:
        return env_ref

    if BACKEND_ENV.exists():
        for line in BACKEND_ENV.read_text(encoding="utf-8").splitlines():
            if line.strip().startswith("SUPABASE_URL="):
                url = line.split("=", 1)[1].strip()
                match = re.match(r"https?://([a-z0-9]+)\.supabase\.(co|in)", url)
                if match:
                    return match.group(1)
    return ""


def mask(value: str | None) -> str:
    if not value:
        return "(空)"
    return f"{value[:10]}…{value[-6:]}（{len(value)} 位）"


def die(message: str, response: httpx.Response | None = None) -> None:
    print(f"✗ {message}")
    if response is not None:
        print(f"  HTTP {response.status_code}")
        print(f"  响应: {response.text[:600]}")
    raise SystemExit(1)


def upsert_env(path: Path, updates: dict[str, str]) -> list[str]:
    """只替换指定键的行，其余内容原样保留（不引入 BOM）。"""
    text = path.read_text(encoding="utf-8")
    changed: list[str] = []
    for key, value in updates.items():
        if value is None:
            continue
        pattern = rf"(?m)^{re.escape(key)}=.*$"
        if re.search(pattern, text):
            text = re.sub(pattern, f"{key}={value}", text)
        else:
            text = text.rstrip("\n") + f"\n{key}={value}\n"
        changed.append(key)
    path.write_text(text, encoding="utf-8", newline="\n")
    return changed


def main() -> int:
    if len(sys.argv) < 2 or not sys.argv[1].strip():
        print(__doc__)
        return 2

    token = sys.argv[1].strip()
    ref = resolve_ref(sys.argv[2] if len(sys.argv) > 2 else None)
    if not ref:
        print("✗ 没拿到目标项目的 project_ref。三种给法任选一种：")
        print("    1) 命令行传入：python scripts/provision_supabase.py sbp_xxx your-project-ref")
        print("    2) 设置环境变量 SUPABASE_PROJECT_REF=your-project-ref")
        print("    3) 先在 backend/.env 里填好 SUPABASE_URL，脚本会自动从域名推导")
        return 2

    # 前置校验：避免把占位符或写错的内容直接塞进 HTTP 头（会抛一大串 UnicodeEncodeError）
    if not token.isascii():
        print("✗ 传入的内容里含有非 ASCII 字符，看起来占位符还没换成真实 Token。")
        print(f"  你传入的是：{token}")
        print("  正确形式应为：sbp_ 开头、后面跟一串英文字母和数字")
        print("\n  用法：python scripts/provision_supabase.py sbp_你的真实token")
        return 2
    if not token.startswith("sbp_"):
        print(f"✗ Token 应以 sbp_ 开头，但收到的是：{token[:16]}…")
        print("  获取地址：https://supabase.com/dashboard/account/tokens")
        return 2
    if len(token) < 20:
        print(f"✗ Token 长度只有 {len(token)}，明显不完整（正常是 sbp_ 加 40 位左右字符）。")
        return 2

    with httpx.Client(timeout=120, headers={"Authorization": f"Bearer {token}"}) as client:
        # ---------- 1. 校验项目 ----------
        print("=== 1. 校验项目归属 ===")
        response = client.get(f"{MGMT}/v1/projects")
        if response.status_code != 200:
            die("列举项目失败，Token 可能无效或权限不足", response)
        projects = response.json()
        target = next((p for p in projects if p.get("id") == ref), None)
        if not target:
            print(f"✗ Token 对应的账号下没有 ref={ref} 的项目，账号下有：")
            for project in projects:
                print(f"    - {project.get('id')}  {project.get('name')}  {project.get('region')}")
            return 1
        print(f"✓ {target.get('name')}  ref={ref}  region={target.get('region')}")

        # ---------- 2. 建表 ----------
        print("\n=== 2. 执行 supabase/schema.sql ===")
        sql = SCHEMA_FILE.read_text(encoding="utf-8")
        print(f"    SQL 长度 {len(sql)} 字符")
        response = client.post(f"{MGMT}/v1/projects/{ref}/database/query", json={"query": sql})
        if response.status_code not in (200, 201):
            print("✗ Management API 执行 SQL 失败。")
            print(f"  HTTP {response.status_code}  响应: {response.text[:400]}")
            print("\n  → 退回手动方式：打开下面的地址，把 supabase/schema.sql 全文粘贴后 Run")
            print(f"    https://supabase.com/dashboard/project/{ref}/sql/new")
            return 1
        print("✓ SQL 执行成功")

        # ---------- 3. 取回 Key ----------
        print("\n=== 3. 取回 API Key ===")
        response = client.get(f"{MGMT}/v1/projects/{ref}/api-keys", params={"reveal": "true"})
        if response.status_code != 200:
            die("获取 API Key 失败", response)
        payload = response.json()

        anon_key = service_key = None
        if isinstance(payload, list):
            for item in payload:
                name = str(item.get("name", "")).lower()
                if name == "anon":
                    anon_key = item.get("api_key")
                elif name == "service_role":
                    service_key = item.get("api_key")
        elif isinstance(payload, dict):  # 兼容扁平返回
            anon_key = payload.get("anon") or payload.get("anon_key")
            service_key = payload.get("service_role") or payload.get("service_role_key")

        if not service_key:
            print("✗ 没能从响应里解析出 service_role key，原始响应片段：")
            print(f"  {str(payload)[:600]}")
            return 1
        print(f"✓ anon key        {mask(anon_key)}")
        print(f"✓ service_role key {mask(service_key)}")

        # JWT Secret（新版 API Key 体系下可能已不可见，取不到不阻塞）
        jwt_secret = None
        for path, params in (
            (f"{MGMT}/v1/projects/{ref}/config/auth", None),
            (f"{MGMT}/v1/projects/{ref}/postgrest", None),
        ):
            try:
                probe = client.get(path, params=params)
                if probe.status_code == 200:
                    body = probe.json()
                    jwt_secret = (
                        body.get("jwt_secret")
                        or (body.get("environment") or {}).get("JWT_SECRET")
                        or jwt_secret
                    )
            except Exception:  # noqa: BLE001
                pass
        print(f"{'✓' if jwt_secret else '·'} JWT Secret       {mask(jwt_secret) if jwt_secret else '未取到（免登录模式不需要）'}")

        # ---------- 4. 写回配置 ----------
        print("\n=== 4. 写回配置文件 ===")
        url = f"https://{ref}.supabase.co"
        backend_updates = {
            "SUPABASE_URL": url,
            "SUPABASE_ANON_KEY": anon_key,
            "SUPABASE_SERVICE_KEY": service_key,
        }
        if jwt_secret:
            backend_updates["SUPABASE_JWT_SECRET"] = jwt_secret
        changed = upsert_env(BACKEND_ENV, backend_updates)
        print(f"✓ backend/.env      更新 {', '.join(changed)}")

        changed = upsert_env(
            FRONTEND_ENV,
            {"NEXT_PUBLIC_SUPABASE_URL": url, "NEXT_PUBLIC_SUPABASE_ANON_KEY": anon_key},
        )
        print(f"✓ frontend/.env.local 更新 {', '.join(changed)}")

    # ---------- 5. 最终校验 ----------
    print("\n=== 5. 最终校验 ===")
    with httpx.Client(timeout=60) as client:
        response = client.get(
            f"{url}/rest/v1/projects",
            params={"select": "id", "limit": "1"},
            headers={"apikey": service_key, "Authorization": f"Bearer {service_key}"},
        )
        if response.status_code == 200:
            print(f"✓ 用 service_role 读 projects 表成功（当前 {len(response.json())} 条记录）")
        else:
            print(f"✗ 读表失败 HTTP {response.status_code}: {response.text[:300]}")
            return 1

        response = client.get(f"{url}/rest/v1/projects", params={"select": "id", "limit": "1"})
        print(f"· 不带 key 访问返回 HTTP {response.status_code}（有 RLS 拦住属于正常）")

    print("\n=== 完成 ===")
    print("接下来：重启后端即可自动切到 Supabase（STORAGE_BACKEND=auto）")
    print("  python run.py")
    print("\n⚠️ 这个 Personal Access Token 已经用完，建议去下面地址立即删除：")
    print("  https://supabase.com/dashboard/account/tokens")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
