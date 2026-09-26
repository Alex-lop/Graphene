#!/usr/bin/env python3
"""The directive's access check, in one command, for the moment a key exists:

    uv run python docs/test/access.py [--sandbox contree|docker|none] [--out FILE]

1. Token Factory: is NEBIUS_API_KEY set (never printed); what `GET /v1/models` lists for it (every NVIDIA
   id, and which is the Nemotron Ultra, Super and Nano, with their list prices); one real tool call per
   Nemotron model, as the docs' function-calling page makes it, and which of them misfire (no call, a
   call to the wrong tool, arguments that are not JSON).
2. Sandboxes: make a sandbox from a Python image, run a command, fork from the image it made, run two
   forks at once. Each step is timed; the times feed the placement decision.

It prints a block for morning.md and writes the same as JSON (default docs/test/access-<date>.json).
Every call's usage goes to the night's ledger when GRAPHENE_LEDGER is set, like every other.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from graphene_map import sandbox as S  # noqa: E402
from graphene_map import tokenfactory as tf  # noqa: E402

WEATHER = {
    "type": "function",
    "function": {
        "name": "get_current_weather",
        "description": "Get the current weather in a given location",
        "parameters": {
            "type": "object",
            "properties": {
                "city": {"type": "string", "description": "The city, e.g. 'San Francisco'"},
                "unit": {"type": "string", "enum": ["celsius", "fahrenheit"]},
            },
            "required": ["city", "unit"],
        },
    },
}
ASK = [{"role": "user", "content": "What is the temperature in Dallas, in Fahrenheit? Use the tool."}]


def tool_call(model: str) -> dict:
    """One call with one tool: did the model call it, by name, with JSON arguments that name the city?"""
    began = time.monotonic()
    try:
        said = tf.chat(model, ASK, [WEATHER], tag="access", temperature=0, max_tokens=512)
    except tf.Unreachable as no:
        took = time.monotonic() - began
        return {"model": model, "ok": False, "misfire": f"no answer: {no}", "seconds": took}
    calls = said["message"].get("tool_calls") or []
    out = {"model": model, "seconds": said["seconds"], "usage": said["usage"], "dollars": said["dollars"]}
    if not calls:
        text = " ".join(str(said["message"].get("content") or "").split())[:160]
        return out | {"ok": False, "misfire": f"no tool call; it said: {text}"}
    fn = calls[0].get("function") or {}
    if fn.get("name") != "get_current_weather":
        return out | {"ok": False, "misfire": f"called {fn.get('name')!r}"}
    try:
        args = json.loads(fn.get("arguments") or "")
    except ValueError:
        return out | {"ok": False, "misfire": f"arguments are not JSON: {str(fn.get('arguments'))[:120]}"}
    if "dallas" not in str(args.get("city", "")).lower():
        return out | {"ok": False, "misfire": f"arguments miss the city: {args}"}
    return out | {"ok": True, "arguments": args}


def sandbox_smoke(kind: str) -> dict:
    """Make, run, fork, two forks at once: each step timed, through Graphene's own sandbox module."""
    box = S.Docker() if kind == "docker" else S.Contree()
    steps: dict[str, float] = {}

    def timed(name: str, fn):
        began = time.monotonic()
        result = fn()
        steps[name] = round(time.monotonic() - began, 2)
        return result

    image, code, out = timed("make and run (import the image if needed)", lambda: box.run(
        S.IMAGE, "python3 -c 'print(6 * 7)' > /tmp/answer; cat /tmp/answer", {}, 300))  # fmt: skip
    if code != 0:
        return {"ok": False, "steps": steps, "said": out[-300:]}
    forked, fcode, fout = timed("fork from the image it made",
                                lambda: box.run(image, "cat /tmp/answer", {}, 300))  # fmt: skip
    with ThreadPoolExecutor(2) as pool:
        both = timed("two forks at once", lambda: list(pool.map(
            lambda k: box.run(image, f"echo fork{k} $(cat /tmp/answer)", {}, 300), (1, 2))))  # fmt: skip
    forks = [b[2].strip() for b in both]
    ok = out.strip() == "42" and fout.strip() == "42" and forks == ["fork1 42", "fork2 42"]
    if hasattr(box, "forget"):
        box.forget()
    return {"ok": ok, "steps": steps, "operations": box.ops}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--sandbox", choices=("contree", "docker", "none"), default="contree")
    ap.add_argument("--out", type=Path, default=Path(__file__).parent / f"access-{date.today()}.json")
    args = ap.parse_args(argv)
    report: dict = {"at": time.strftime("%Y-%m-%d %H:%M %Z"), "key": bool(os.environ.get(tf.KEY))}
    lines = [f"Access, checked {report['at']} (docs/test/access.py):"]
    if not report["key"]:
        lines.append("- Token Factory: NEBIUS_API_KEY is not set in this shell; nothing was sent.")
    else:
        try:
            listed = tf.models()
        except tf.Unreachable as no:
            listed, report["models_error"] = [], str(no)
            lines.append(f"- Token Factory: {no}")
        nvidia = [m for m in listed if "nvidia" in m.id.lower() or "nemotron" in m.id.lower()]
        report["nvidia"] = [{"id": m.id, "prompt": m.prompt, "completion": m.completion} for m in nvidia]
        report["roles"] = tf.roles(listed) if listed else {}
        if listed:
            lines.append(f"- Token Factory lists {len(listed)} models; the NVIDIA ones:")
            for m in nvidia:
                size = next((r for r, i in report["roles"].items() if i == m.id), "")
                per = f"${m.prompt * 1e6:.2f} in, ${m.completion * 1e6:.2f} out per million tokens"
                lines.append(f"  - `{m.id}`{f' ({size})' if size else ''}: {per}")
        report["tool_calls"] = [tool_call(i) for i in report["roles"].values()]
        for t in report["tool_calls"]:
            verdict = "a tool call, as asked" if t["ok"] else f"MISFIRE: {t['misfire']}"
            lines.append(f"  - one tool call to `{t['model']}`: {verdict} ({t['seconds']:.1f} s)")
    if args.sandbox != "none":
        if args.sandbox == "contree" and not S.configured():
            report["sandbox"] = {"ok": False, "said": "ConTree is not configured (SDK or credentials)"}
            lines.append("- Sandboxes: ConTree is not configured here (the `sandbox` extra, and "
                         "NEBIUS_API_KEY with NEBIUS_PROJECT_ID, or a `contree auth` profile).")  # fmt: skip
        else:
            try:
                report["sandbox"] = sandbox_smoke(args.sandbox)
            except Exception as no:  # an SDK or a network error is a result here
                report["sandbox"] = {"ok": False, "said": f"{type(no).__name__}: {no}"}
            sb = report["sandbox"]
            steps = "; ".join(f"{k}: {v} s" for k, v in sb.get("steps", {}).items())
            verdict = "works" if sb["ok"] else "FAILED: " + sb.get("said", "")
            lines.append(f"- Sandboxes ({args.sandbox}): {verdict}{'; ' + steps if steps else ''}")
    args.out.write_text(json.dumps(report, indent=1) + "\n", encoding="utf-8")
    print("\n".join(lines))
    return 0 if report["key"] and all(t["ok"] for t in report.get("tool_calls", [])) else 1


if __name__ == "__main__":
    raise SystemExit(main())
