"""A real Claude Code session as the recording the extension replays on an empty page.

    python3 dev/process/sessions/record.py ~/.claude/projects/<folder>/<session id>.jsonl /real/folder \
        > editors/vscode/media/replay.jsonl

It keeps the lines the reader reads (requests, what the agent said, tool calls and their results, a turn's
end, the title), the session's own and its subagents' in the order they were written; drops the thinking and
every field the reader does not use; cuts long results; and makes the paths and the ids generic. Run it only
on a session of a scratch repository made for the purpose: what it prints is committed."""

import json
import sys
from pathlib import Path

KEEP = 600  # characters of a result, or of a file's text in a call
LINE = ("type", "timestamp", "isSidechain", "agentId", "sessionId", "cwd", "gitBranch", "isMeta", "origin")
BLOCK = ("type", "text", "id", "name", "input", "tool_use_id", "content", "is_error")
RESULT = ("stdout", "stderr", "interrupted", "agentId", "status", "isAsync", "filePath", "type", "task",
          "runId", "workflowName")


def cut(v):
    if isinstance(v, str):
        return v if len(v) <= KEEP else v[:KEEP] + "…"
    if isinstance(v, list):
        return [cut(x) for x in v]
    if isinstance(v, dict):
        return {k: cut(x) for k, x in v.items()}
    return v


def slim(o):
    """One line, with only what the reader reads; None for a line it would skip anyway."""
    kind = o.get("type")
    if kind == "ai-title":
        return {"type": kind, "aiTitle": o.get("aiTitle")}
    if kind == "system":
        if o.get("subtype") != "turn_duration":
            return None
        return {"type": kind, "subtype": "turn_duration", "timestamp": o.get("timestamp"),
                "isSidechain": o.get("isSidechain", False)}
    if kind not in ("user", "assistant"):
        return None
    out = {k: o[k] for k in LINE if k in o}
    m = o.get("message") or {}
    content = m.get("content")
    if isinstance(content, list):
        kinds = ("text", "tool_use", "tool_result")
        shown = [b for b in content if isinstance(b, dict) and b.get("type") in kinds]
        content = [{k: cut(b[k]) for k in BLOCK if k in b} for b in shown]
        if not content and not m.get("stop_reason"):
            return None
    message = {"role": m.get("role"), "model": m.get("model"), "stop_reason": m.get("stop_reason"),
               "content": cut(content)}
    out["message"] = {k: v for k, v in message.items() if v is not None}
    r = o.get("toolUseResult")
    if isinstance(r, dict):
        out["toolUseResult"] = {k: cut(r[k]) for k in RESULT if k in r}
    elif isinstance(r, str):
        out["toolUseResult"] = cut(r)
    return out


def main(file, folder):
    session = Path(file)
    name = Path(folder).name
    # the longer path first: one holds the other. Made generic before anything is cut: no half of one is left
    real = sorted({str(Path(folder).resolve()), folder}, key=len, reverse=True)
    lines = []
    at = ""
    for f in [session, *sorted((session.parent / session.stem / "subagents").glob("**/agent-*.jsonl"))]:
        for line in f.read_text().splitlines():
            for path in real:
                line = line.replace(path, f"/work/{name}")
            line = line.replace(session.stem, "00000000-0000-4000-8000-000000000001")
            line = line.replace(str(Path.home()), "/home/you")
            try:
                o = slim(json.loads(line))
            except ValueError:
                continue
            if o:
                at = o.get("timestamp") or at  # a title has no time of its own: it stays where it was written
                lines.append((at, len(lines), o))
    for _, _, o in sorted(lines, key=lambda x: (x[0], x[1])):
        print(json.dumps(o, ensure_ascii=False, separators=(",", ":")))


if __name__ == "__main__":
    main(*sys.argv[1:3])
