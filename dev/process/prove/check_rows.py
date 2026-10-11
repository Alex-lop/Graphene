#!/usr/bin/env python3
"""Every check Graphene ran on a plan, with its output: check_rows.py REPO [NODE...]

Read through Graphene's own Store (run it with the build's interpreter, $TOOLPY), so the row that
`node show` sums up as "1 check failed" is printed whole: who ran it, when, the command, the tail."""
import sys
from pathlib import Path

from graphene_map.store import Store

repo = Path(sys.argv[1]).resolve()
only = set(sys.argv[2:])
with Store.open(repo) as store:
    for e in store.node_log():
        if e["kind"] not in ("check_passed", "check_failed", "precheck") or (only and e["node_id"] not in only):
            continue
        d = e["detail"]
        print(f"== {e['timestamp']} {e['node_id']} {e['kind']} by {e['actor']}")
        print(f"   command: {d.get('command') or d.get('check')}")
        if e["kind"] == "precheck":
            print(f"   verdict: {d.get('verdict')}: {d.get('why')}")
        tail = (d.get("output") or "").rstrip()
        if tail:
            print("   " + tail[-1200:].replace("\n", "\n   "))
