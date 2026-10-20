#!/usr/bin/env python3
"""Create a consistent SQLite backup using SQLite's backup API (WAL-safe)."""
import argparse, hashlib, sqlite3
from pathlib import Path
from datetime import datetime
p=argparse.ArgumentParser(); p.add_argument("source",type=Path); p.add_argument("destination",type=Path); a=p.parse_args()
if not a.source.exists(): raise SystemExit(f"Source not found: {a.source}")
a.destination.parent.mkdir(parents=True,exist_ok=True)
src=sqlite3.connect(f"file:{a.source.resolve()}?mode=ro",uri=True)
dst=sqlite3.connect(a.destination)
try:
    src.backup(dst)
    integrity=dst.execute("PRAGMA integrity_check").fetchone()[0]
    if integrity!="ok": raise SystemExit(f"Backup integrity failed: {integrity}")
    try:
        row=dst.execute("SELECT data FROM state WHERE id=1").fetchone()
        import json
        state=json.loads(row[0]) if row else {}
        counts={k:len(state.get(k,[])) for k in ("events","tasks","assets","changes")}
    except Exception: counts={}
finally:
    dst.close(); src.close()
digest=hashlib.sha256(a.destination.read_bytes()).hexdigest()
print(f"PASS backup={a.destination} bytes={a.destination.stat().st_size} sha256={digest} integrity=ok counts={counts}")
