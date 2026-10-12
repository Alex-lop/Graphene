#!/usr/bin/env python3
"""One field of a `claude -p` result: claude_json.py FILE KEY

FILE is `--output-format json`'s one object, or a stream-json file whose last `result` line is
read. Prints the value (JSON for a list or an object), nothing when it is absent."""

import json
import sys

path, key = sys.argv[1], sys.argv[2]
text = open(path, encoding="utf-8", errors="replace").read()
obj = None
try:
    obj = json.loads(text)
except ValueError:
    for line in reversed(text.splitlines()):
        try:
            event = json.loads(line)
        except ValueError:
            continue
        if isinstance(event, dict) and event.get("type") == "result":
            obj = event
            break
if isinstance(obj, dict) and obj.get(key) is not None:
    value = obj[key]
    print(value if isinstance(value, (str, int, float)) else json.dumps(value))
