"""一键建表：把 supabase/schema.sql 执行到你的 Supabase 数据库上。

用法（在 backend 目录下执行）：

    # 方式一：先用 Supabase 的数据库连接串（推荐，无需手工粘贴 SQL）
    python scripts/init_db.py "postgresql://postgres.xxxx:密码@aws-0-xx.pooler.supabase.com:5432/postgres"

    # 方式二：把连接串写进 backend/.env 的 SUPABASE_DB_URL，然后直接跑
    python scripts/init_db.py

    # 执行完会打印实际建出来的表 / 视图 / 策略数量，便于核对
连接串位置：Supabase 控制台 → Project Settings → Database → Connection string → URI
（记得把 [YOUR-PASSWORD] 替换成数据库密码；密码里的特殊字符要做 URL 编码）
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCHEMA_FILE = ROOT / "supabase" / "schema.sql"

EXPECTED_TABLES = ["profiles", "projects", "versions", "publications", "generation_events"]


def load_connection_string() -> str:
    if len(sys.argv) > 1 and sys.argv[1].strip():
        return sys.argv[1].strip()

    # 允许从 backend/.env 读取
    env_file = ROOT / "backend" / ".env"
    if env_file.exists():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            if line.strip().startswith("SUPABASE_DB_URL="):
                value = line.split("=", 1)[1].strip().strip('"').strip("'")
                if value:
                    return value
    return ""


def main() -> int:
    if not SCHEMA_FILE.exists():
        print(f"找不到建表脚本：{SCHEMA_FILE}")
        return 1

    connection_string = load_connection_string()
    if not connection_string:
        print(
            "缺少数据库连接串。请任选一种方式：\n"
            '  1) python scripts/init_db.py "postgresql://postgres.xxx:密码@xxx.pooler.supabase.com:5432/postgres"\n'
            "  2) 在 backend/.env 里填好 SUPABASE_DB_URL 后重跑本脚本\n"
            "  3) 也可以直接把 supabase/schema.sql 全文粘到 Supabase 的 SQL Editor 里执行\n"
            "连接串位置：Supabase 控制台 → Project Settings → Database → Connection string → URI"
        )
        return 2

    try:
        import psycopg
    except ImportError:
        print('缺少 psycopg 驱动，请先执行：pip install "psycopg[binary]"')
        return 3

    sql = SCHEMA_FILE.read_text(encoding="utf-8")
    print(f"准备执行 {SCHEMA_FILE.name}（{len(sql)} 字符）…")

    with psycopg.connect(connection_string, autocommit=True) as conn:
        conn.execute(sql)
        print("SQL 执行完成，开始核对对象…\n")

        with conn.cursor() as cur:
            cur.execute(
                "select table_name from information_schema.tables "
                "where table_schema = 'public' order by table_name"
            )
            tables = [row[0] for row in cur.fetchall()]

            cur.execute(
                "select table_name from information_schema.views "
                "where table_schema = 'public' order by table_name"
            )
            views = [row[0] for row in cur.fetchall()]

            cur.execute(
                "select count(*) from pg_policies where schemaname = 'public'"
            )
            policy_count = cur.fetchone()[0]

            cur.execute("select count(*) from pg_trigger where not tgisinternal")
            trigger_count = cur.fetchone()[0]

    print("表：")
    for name in EXPECTED_TABLES:
        mark = "OK " if name in tables else "缺失"
        print(f"  [{mark}] {name}")
    print(f"\n视图：{', '.join(views) or '无'}")
    print(f"RLS 策略：{policy_count} 条")
    print(f"触发器：{trigger_count} 个")

    missing = [name for name in EXPECTED_TABLES if name not in tables]
    if missing:
        print(f"\n有 {len(missing)} 张表没建成功：{missing}")
        return 4

    print("\n全部就绪：把 Supabase 的 URL / anon key / service key / JWT secret 填进 backend/.env 即可。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
