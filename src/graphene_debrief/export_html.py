"""One self-contained HTML file per debrief: the timeline, readable offline, safe to email.

Nothing is fetched at view time — no scripts, fonts or images from anywhere — and the data is
embedded as JSON that the page turns into DOM with ``textContent``, so a prompt or a diff can
never become markup. Sessions, prompts, files and directories are separate node types here
because later versions of Graphene attach things to them; tonight only the timeline reads them.
"""

from __future__ import annotations

import html
import json
from dataclasses import asdict
from importlib.resources import files as package_files

from .debrief import Debrief, _dt, file_rows

TEMPLATE = "templates/record.html"


def render(debrief: Debrief) -> str:
    """The HTML record for these sessions: the template with the data and the title filled in."""
    data = {"debrief": asdict(debrief), "nodes": nodes(debrief)}
    payload = (
        json.dumps(data, ensure_ascii=False)
        .replace("</", "<\\/")  # cannot close the script tag
        .replace("<!--", "\\u003c!--")  # nor open an HTML comment inside it
    )
    ids = ", ".join(s["id"][:8] for s in debrief.sessions) or "no sessions"
    out = (
        package_files("graphene_debrief")
        .joinpath(TEMPLATE)
        .read_text(encoding="utf-8")
        .replace("__GRAPHENE_TITLE__", html.escape(f"Graphene debrief — {ids}"))
        .replace("__GRAPHENE_DATA__", payload)
    )
    if "__GRAPHENE_" in out:
        raise AssertionError("a placeholder was left unfilled in templates/record.html")
    return out


def nodes(d: Debrief) -> list[dict]:
    """Sessions, prompts, files and directories, each tagged with its type.

    Prompts carry the two filter flags so the page does not recompute them, and files carry the
    net effect over the whole record (``file_rows``) so the panel can show it beside one diff.
    """
    reverted = {r["path"] for r in d.reverted}
    unrequested = {u["path"] for u in d.unrequested}
    reran = {(r["session_id"], o) for r in d.reruns for o in (r["failed_under"], r["rerun_under"])}
    touched: dict[str, set[str]] = {}
    out: list[dict] = []
    for block in d.prompts:
        paths = [f.path for f in block.files]
        touched.setdefault(block.session_id, set()).update(paths)
        out.append(
            {
                "id": f"prompt:{block.session_id}:{block.ordinal}",
                "type": "prompt",
                "session_id": block.session_id,
                "ordinal": block.ordinal,
                "timestamp": block.timestamp,
                "paths": paths,
                "unrequested": any(f.unrequested for f in block.files),
                "abandoned": any(p in reverted for p in paths) or (block.session_id, block.ordinal) in reran,
            }
        )
    sessions = [
        {
            "id": f"session:{s['id']}",
            "type": "session",
            "session_id": s["id"],
            "label": s["id"][:8],
            "started_at": s["started_at"],
            "ended_at": s["ended_at"],
            "source": s["source"],
            "prompts": s["prompts"],
            "files": len(touched.get(s["id"], ())),
            "wall_seconds": _seconds(s["started_at"], s["ended_at"] or d.generated_at),
        }
        for s in d.sessions
    ]
    dirs: dict[str, int] = {}
    for row in file_rows(d):
        head = row["path"].rpartition("/")[0]
        out.append(
            {
                "id": f"file:{row['path']}",
                "type": "file",
                "path": row["path"],
                "dir": head,
                "name": row["path"].rpartition("/")[2],
                "effect": row["effect"],
                "added": row["added"],
                "removed": row["removed"],
                "unrequested": row["path"] in unrequested,
                "abandoned": row["path"] in reverted,
            }
        )
        while head:
            dirs[head] = dirs.get(head, 0) + 1
            head = head.rpartition("/")[0]
    out += [
        {"id": f"dir:{p}", "type": "dir", "path": p, "parent": p.rpartition("/")[0], "files": n}
        for p, n in sorted(dirs.items())
    ]
    return sessions + out


def _seconds(start: str | None, end: str | None) -> int:
    if not start or not end:
        return 0
    return max(0, int((_dt(end) - _dt(start)).total_seconds()))
