"""Print a `claude -p --output-format stream-json` transcript as one trimmed line per step."""

import json
import sys


def show(line):
    d = json.loads(line)
    kind = d.get("type")
    if kind == "assistant":
        for c in d["message"]["content"]:
            if c.get("type") == "tool_use":
                print("tool_use", c["name"], json.dumps(c["input"])[:160])
            elif c.get("type") == "text":
                print("text", c["text"][:200].replace("\n", " "))
    elif kind == "user":
        for c in d["message"]["content"]:
            if isinstance(c, dict) and c.get("type") == "tool_result":
                print("  result:", str(c.get("content"))[:240].replace("\n", " "))
    elif kind == "result":
        print("result", d.get("subtype"), "cost", d.get("total_cost_usd"))


for row in open(sys.argv[1]):
    show(row)
