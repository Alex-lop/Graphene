#!/usr/bin/env python3
"""How wide a recorded run ran: `meter.width` over a `graphene demo` recording.

    uv run python dev/process/loop/width.py tests/recordings/meter-claude.jsonl …

A frame holds the log rows the store gained since the recorder's last look, not the whole store. So the
log is every frame's rows, in order. Now is the last row's moment, where `graphene demo --once` ends.
"""

import json
import sys
from datetime import datetime
from pathlib import Path

from graphene_map import demo
from graphene_map import meter as M

for path in sys.argv[1:]:
    _, frames = demo.load(Path(path))
    rows = [r | {"detail": json.loads(r["detail"] or "{}")} for f in frames for r in f.get("node_log") or []]
    w = M.width(rows, datetime.fromisoformat(max(r["timestamp"] for r in rows)))
    print(f"{Path(path).name}: width {w['most']} of {w['lanes']} · {w['alone']:.0%} of agent minutes alone")
