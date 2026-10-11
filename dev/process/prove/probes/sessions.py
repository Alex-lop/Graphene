#!/usr/bin/env python3
"""Did the hooks fire in a repo? Print every session the store holds and how many hook events each has.

    dev/process/prove/probes/sessions.py <repo>
"""
import sqlite3
import sys

db = sys.argv[1] + "/.graphene/graphene.db"
c = sqlite3.connect(db)
tables = [r[0] for r in c.execute("select name from sqlite_master where type='table'")]
print("tables:", tables)
for table in ("sessions", "prompts", "tool_events"):
    if table not in tables:
        continue
    cols = [r[1] for r in c.execute(f"pragma table_info({table})")]
    print(f"{table}: columns {cols}")
    if "session_id" in cols:
        for sid, n in c.execute(f"select session_id, count(*) from {table} group by session_id"):
            print(f"  {table} session {sid}: {n}")
    elif table == "sessions":
        for row in c.execute("select * from sessions"):
            print("  ", row)
