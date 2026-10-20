#!/usr/bin/env python3
"""Import a consistent V0.2 SQLite state backup or JSON export into PostgreSQL."""
import argparse, json, sqlite3, sys
from pathlib import Path
from psycopg.types.json import Jsonb
from app import init_db, connect, sync_projection


def load_sqlite(path: Path):
    uri = f"file:{path.resolve()}?mode=ro"
    con = sqlite3.connect(uri, uri=True)
    try:
        integrity = con.execute("PRAGMA integrity_check").fetchone()[0]
        if integrity != "ok": raise RuntimeError(f"SQLite integrity_check failed: {integrity}")
        names = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if "state" not in names: raise RuntimeError("SQLite 文件中没有 state 表；请确认使用的是 V0.2 activity.sqlite3 备份")
        row = con.execute("SELECT revision,data,updated_at,updated_by FROM state WHERE id=1").fetchone()
        if not row: raise RuntimeError("SQLite state 表中没有 id=1 的共享台账")
        state = json.loads(row[1])
        return state, int(row[0]), {"integrity": integrity, "updated_at": row[2], "updated_by": row[3]}
    finally:
        con.close()


def load_json(path: Path):
    state = json.loads(path.read_text(encoding="utf-8"))
    return state, 1, {"source": "JSON export"}


def validate(state):
    for key in ("events", "tasks", "assets", "changes", "suppliers", "workPackages", "venues"):
        state.setdefault(key, [])
        if not isinstance(state.get(key), list): raise RuntimeError(f"导入文件缺少有效数组：{key}")
    ids = [x.get("id") for x in state["events"] if isinstance(x, dict)]
    if len(ids) != len(set(ids)): raise RuntimeError("活动 ID 存在重复")
    return {k: len(state[k]) for k in ("events", "tasks", "assets", "changes", "suppliers", "workPackages", "venues")}


def main():
    p = argparse.ArgumentParser()
    source = p.add_mutually_exclusive_group(required=True)
    source.add_argument("--sqlite", type=Path, help="SQLite 一致性备份路径")
    source.add_argument("--json", type=Path, help="从工作台导出的 JSON 台账")
    p.add_argument("--replace", action="store_true", help="明确覆盖目标 PostgreSQL 当前台账；默认拒绝覆盖")
    args = p.parse_args()
    source_path = args.sqlite if args.sqlite else args.json
    if not source_path.exists():
        raise SystemExit("导入源文件不存在")
    init_db(seed=False)
    state, source_revision, meta = load_sqlite(args.sqlite) if args.sqlite else load_json(args.json)
    counts = validate(state)
    with connect() as conn:
        conn.execute("BEGIN")
        current = conn.execute("SELECT revision FROM state_documents WHERE id=1 FOR UPDATE").fetchone()
        if current and not args.replace:
            conn.rollback()
            raise SystemExit("目标数据库已有台账，默认拒绝覆盖。需要覆盖时必须显式传 --replace，并先完成备份。")
        if current:
            revision = int(current["revision"]) + 1
            conn.execute("UPDATE state_documents SET revision=%s,data=%s,updated_at=now(),updated_by='sqlite-migration' WHERE id=1", (revision, Jsonb(state)))
        else:
            revision = max(1, source_revision)
            conn.execute("INSERT INTO state_documents(id,revision,data,updated_by) VALUES(1,%s,%s,'sqlite-migration')", (revision, Jsonb(state)))
        sync_projection(conn, state)
        conn.execute("INSERT INTO audit_log(actor,revision,action,details) VALUES(%s,%s,%s,%s)",
                     ("migration", revision, "SQLite/JSON 台账迁移", Jsonb({"source": str(args.sqlite or args.json), "source_meta": meta, "counts": counts})))
    print(json.dumps({"status": "PASS", "revision": revision, "counts": counts, "source_meta": meta}, ensure_ascii=False, indent=2, default=str))

if __name__ == "__main__":
    main()
