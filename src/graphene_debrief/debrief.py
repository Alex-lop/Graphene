"""Build the debrief structure from the store and render it as markdown, terminal text or JSON."""

from __future__ import annotations

import json
import os
import re
import subprocess
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path

from rich.text import Text

from .attribute import attribute
from .explain import Explainer, ExplainError, NullExplainer, template
from .model import FileChange, ToolEvent
from .store import Store

PROMPT_PREVIEW_LINES = 3
PROMPT_PREVIEW_CHARS = 300


@dataclass
class FileLine:
    path: str
    effect: str
    added: int
    removed: int
    unrequested: bool
    strategy: str
    explanation: str
    explained_by: str
    model: str | None = None  # the model that wrote the sentence, when one did
    hunks: list[dict] = field(default_factory=list)  # the change's unified-diff hunks, as dicts


@dataclass
class PromptBlock:
    session_id: str
    prompt_id: str
    ordinal: int
    timestamp: str
    text: str
    files: list[FileLine] = field(default_factory=list)


@dataclass
class Debrief:
    generated_at: str
    sessions: list[dict] = field(default_factory=list)
    wall_seconds: int = 0
    prompt_count: int = 0
    files_changed: int = 0
    added: int = 0
    removed: int = 0
    commits: list[str] = field(default_factory=list)
    prompts: list[PromptBlock] = field(default_factory=list)
    unrequested: list[dict] = field(default_factory=list)
    reverted: list[dict] = field(default_factory=list)
    failed: list[dict] = field(default_factory=list)
    failure_summary: dict = field(default_factory=dict)  # total, by_tool, denials
    reruns: list[dict] = field(default_factory=list)
    outside_repo: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


# -- selecting sessions -------------------------------------------------------------------------


def parse_since(value: str, now: datetime) -> str:
    """``6h`` / ``2d`` / ``30m`` / ``2026-09-16`` -> ISO timestamp cutoff."""
    match = re.fullmatch(r"(\d+)([mhdw])", value.strip())
    if match:
        amount, unit = int(match.group(1)), match.group(2)
        delta = {
            "m": timedelta(minutes=amount),
            "h": timedelta(hours=amount),
            "d": timedelta(days=amount),
            "w": timedelta(weeks=amount),
        }[unit]
        return iso(now - delta)
    try:
        parsed = datetime.fromisoformat(value.strip())
    except ValueError:
        raise ValueError(f"cannot read --since {value!r}: use 6h, 2d, or a date like 2026-09-16") from None
    if parsed.tzinfo is None:
        parsed = parsed.astimezone()
    return iso(parsed.astimezone(UTC))


def iso(moment: datetime) -> str:
    return moment.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def select_sessions(
    store: Store, session_id: str | None = None, since: str | None = None, now: datetime | None = None
) -> list[str]:
    """Which sessions a debrief covers: one by id (prefix ok), all since a cutoff, or since the last run."""
    now = now or datetime.now(UTC)
    sessions = store.sessions()
    if session_id:
        matches = [s.id for s in sessions if s.id.startswith(session_id)]
        if len(matches) != 1:
            raise ValueError(f"{len(matches)} sessions match {session_id!r}")
        return matches
    if since:
        cutoff = parse_since(since, now)
        return [s.id for s in sessions if (s.ended_at or s.started_at or "") >= cutoff]
    last = store.last_debrief_run()
    if last:
        fresh = [s.id for s in sessions if (s.ended_at or iso(now)) > last.timestamp]
        if fresh:
            return fresh
    return [sessions[-1].id] if sessions else []


# -- building -----------------------------------------------------------------------------------


def build_debrief(
    store: Store,
    session_ids: list[str],
    root: Path,
    explainer: Explainer | None = None,
    now: datetime | None = None,
) -> Debrief:
    now = now or datetime.now(UTC)
    explainer = explainer or NullExplainer()
    debrief = Debrief(generated_at=iso(now))
    results = attribute(store, session_ids, root)
    fallback: Explainer | None = None
    paths: set[str] = set()
    for sid in session_ids:
        session = store.session(sid)
        if session is None or sid not in results:
            continue
        prompts = store.prompts(sid)
        result = results[sid]
        end = session.ended_at or iso(now)
        debrief.sessions.append(
            {
                "id": sid,
                "started_at": session.started_at,
                "ended_at": session.ended_at,
                "source": session.source,
                "prompts": len(prompts),
            }
        )
        if session.started_at:
            debrief.wall_seconds += max(0, int((_dt(end) - _dt(session.started_at)).total_seconds()))
        debrief.prompt_count += len(prompts)
        by_prompt: dict[str, list[FileChange]] = {}
        for change in result.changes:
            by_prompt.setdefault(change.prompt_id or "", []).append(change)
        orphans = by_prompt.get("", [])
        if orphans:  # recorded before any prompt (hooks installed mid-session, or a slash-command turn)
            block = PromptBlock(
                sid, "", 0, session.started_at or "", "(changes recorded before the first prompt)"
            )
            for change in orphans:
                block.files.append(
                    FileLine(
                        change.path,
                        change.effect,
                        change.added,
                        change.removed,
                        False,
                        change.strategy,
                        template(change),
                        "none",
                        None,
                        [asdict(h) for h in change.hunks],
                    )
                )
                paths.add(change.path)
                debrief.added += change.added
                debrief.removed += change.removed
            debrief.prompts.append(block)
        for prompt in prompts:
            changes = by_prompt.get(prompt.id, [])
            explanations, explainer, fallback = _explain(
                store, explainer, fallback, prompt.text, prompt.id, changes, debrief.notes, now
            )
            block = PromptBlock(sid, prompt.id, prompt.ordinal, prompt.timestamp, prompt.text)
            for change in changes:
                text, by, model = explanations.get(change.path, (template(change), "none", None))
                block.files.append(
                    FileLine(
                        change.path,
                        change.effect,
                        change.added,
                        change.removed,
                        change.unrequested,
                        change.strategy,
                        text,
                        by,
                        model,
                        [asdict(h) for h in change.hunks],
                    )
                )
                paths.add(change.path)
                debrief.added += change.added
                debrief.removed += change.removed
                if change.unrequested:
                    debrief.unrequested.append(
                        {
                            "path": change.path,
                            "session_id": sid,
                            "prompt_ordinal": prompt.ordinal,
                            "prompt": preview(prompt.text, 1, 80),
                        }
                    )
            debrief.prompts.append(block)
        ordinal = {p.id: p.ordinal for p in prompts}
        debrief.reverted += [
            {"path": c.path, "session_id": sid, "prompt_ordinal": ordinal.get(c.prompt_id, 0)}
            for c in result.reverted
        ]
        debrief.failed += [_failed(e, ordinal, sid) for e in result.failed]
        debrief.reruns += [
            {
                "command": check[:120],
                "session_id": sid,
                "failed_under": ordinal.get(a.prompt_id, 0),
                "rerun_under": ordinal.get(b.prompt_id, 0),
                "rerun_passed": bool(b.success),
            }
            for a, b, check in result.reruns
        ]
        debrief.outside_repo += [p for p in result.outside_repo if p not in debrief.outside_repo]
        debrief.commits += commits_between(root, session.started_at, end)
    debrief.files_changed = len(paths)
    by_tool: dict[str, int] = {}
    for f in debrief.failed:
        by_tool[f["tool"]] = by_tool.get(f["tool"], 0) + 1
    debrief.failure_summary = {
        "total": len(debrief.failed),
        "by_tool": dict(sorted(by_tool.items(), key=lambda kv: (-kv[1], kv[0]))),
        "denials": sum(1 for f in debrief.failed if f["denied"]),
    }
    return debrief


def _explain(store, explainer, fallback, text, prompt_id, changes, notes, now):
    """Explanations for one prompt: stored model output first, else the explainer, else templates."""
    out: dict[str, tuple[str, str, str | None]] = {}
    missing: list[FileChange] = []
    for change in changes:
        stored = store.explanation(prompt_id, change.path)
        if stored and stored[1] != "none":
            out[change.path] = stored
        else:
            missing.append(change)
    if missing:
        active = fallback or explainer
        try:
            produced = active.explain_prompt(text, missing)
        except ExplainError as exc:
            notes.append(f"explanations by {active.name} failed ({exc}); showing templates instead")
            fallback = NullExplainer()
            produced = fallback.explain_prompt(text, missing)
            active = fallback
        model = getattr(active, "model", None)
        for change in missing:
            sentence = produced.get(change.path) or template(change)
            by = active.name if change.path in produced else "none"
            out[change.path] = (sentence, by, model if by != "none" else None)
            if by != "none":
                store.set_explanation(prompt_id, change.path, sentence, by, iso(now), model)
    return out, explainer, fallback


def _failed(e: ToolEvent, ordinal: dict[str, int], sid: str) -> dict:
    if e.tool == "Bash":
        what = " ".join((e.input.get("command") or "").split())[:120]
    elif e.file_path:
        what = e.file_path
    else:
        strings = [v for v in e.input.values() if isinstance(v, str)]
        what = " ".join((strings[0] if strings else json.dumps(e.input, ensure_ascii=False)).split())[:120]
    error = e.response.get("error") if isinstance(e.response, dict) else e.response
    lines = [line.strip() for line in (str(error) if error else "").splitlines() if line.strip()]
    summary = lines[0] if lines else ""
    if "Exit code" in summary and len(lines) > 1:
        summary += " · " + lines[1]
    denied, reason = _denial(str(error) if error else "")
    return {
        "tool": e.tool,
        "what": what,
        "error": summary[:160],
        "denied": denied,
        "reason": reason,
        "session_id": sid,
        "prompt_ordinal": ordinal.get(e.prompt_id, 0),
    }


_CLASSIFIER_REASON = re.compile(r"Reason: \[?([^\]\n.]+)")


def _denial(error: str) -> tuple[bool, str]:
    """Was this call refused before it ran (permission system, classifier, the user), and why?"""
    if "denied by the Claude Code auto mode classifier" in error:
        match = _CLASSIFIER_REASON.search(error)
        return True, f"auto mode classifier: {match.group(1).strip() if match else 'unknown reason'}"
    if "doesn't want to proceed" in error or "user declined" in error.lower():
        return True, "rejected by the user"
    if "permission" in error.lower() and "denied" in error.lower():
        return True, "permission denied"
    return False, ""


def _dt(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def commits_between(root: Path, start: str | None, end: str) -> list[str]:
    if not start or not (root / ".git").exists():
        return []
    try:
        proc = subprocess.run(
            ["git", "log", "--format=%h %s", f"--since={start}", f"--until={end}"],
            cwd=root,
            capture_output=True,
            text=True,
            timeout=20,
        )
    except (OSError, subprocess.SubprocessError):
        return []
    return proc.stdout.strip().splitlines() if proc.returncode == 0 else []


# -- rendering ----------------------------------------------------------------------------------


def preview(text: str, lines: int = PROMPT_PREVIEW_LINES, chars: int = PROMPT_PREVIEW_CHARS) -> str:
    rows = [r for r in text.strip().splitlines() if r.strip()]
    clipped = "\n".join(rows[:lines])
    truncated = len(rows) > lines or len(clipped) > chars
    if len(clipped) > chars:
        clipped = clipped[:chars].rstrip()
    if sum(1 for r in clipped.splitlines() if r.strip().startswith("```")) % 2:
        clipped += "\n```"  # close a code block the clip left open
    return clipped + ("…" if truncated else "")


def stamp(value: str | None) -> str:
    return value[:16].replace("T", " ") if value else "?"


def duration(seconds: int) -> str:
    hours, rest = divmod(seconds, 3600)
    minutes = rest // 60
    return f"{hours}h {minutes:02d}m" if hours else f"{minutes}m"


def render_markdown(d: Debrief, full: bool = False) -> str:
    many = len(d.sessions) > 1

    def where(ordinal: int, session_id: str) -> str:
        return f"prompt {ordinal}" + (f" of {session_id[:8]}" if many else "")

    out: list[str] = ["# Graphene debrief", ""]
    ids = ", ".join(s["id"][:8] for s in d.sessions) or "none"
    span = f"{stamp(d.sessions[0]['started_at'])} → {stamp(d.sessions[-1]['ended_at'])}" if d.sessions else ""
    out.append(f"**Sessions:** {len(d.sessions)} ({ids}) {span}  ")
    out.append(
        f"**Wall time:** {duration(d.wall_seconds)} · **Prompts:** {d.prompt_count} · "
        f"**Files changed:** {d.files_changed} (+{d.added}/−{d.removed})  "
    )
    out.append(f"**Commits during the sessions:** {len(d.commits)}")
    out += [f"- {c}" for c in d.commits]
    out += ["", "## What you asked, and what happened", ""]
    current_session = None
    for block in d.prompts:
        if many and block.session_id != current_session:
            current_session = block.session_id
            info = next(s for s in d.sessions if s["id"] == block.session_id)
            out += [
                f"**Session {block.session_id[:8]}** ({info['source']}, {stamp(info['started_at'])} → "
                f"{stamp(info['ended_at'])})",
                "",
            ]
        text = block.text.strip() if full else preview(block.text)
        if block.ordinal == 0:
            out.append(f"### Before the first recorded prompt (session started {stamp(block.timestamp)})")
        else:
            out.append(f"### {block.ordinal}. {stamp(block.timestamp)}")
        out += [f"> {line}" for line in text.splitlines()]
        out.append("")
        if not block.files:
            out.append("_No file changes._")
        for f in block.files:
            flag = " **[unrequested]**" if f.unrequested else ""
            out.append(f"- `{f.path}` {_what(f)}{flag} — {f.explanation}")
        out.append("")
    if d.unrequested:
        out += ["## Not what you asked for", ""]
        groups: dict[tuple[str, int, str], list[str]] = {}
        for u in d.unrequested:
            groups.setdefault((u["session_id"], u["prompt_ordinal"], u["prompt"]), []).append(u["path"])
        for (sid, ordinal, text), paths in groups.items():
            out.append(f'- under {where(ordinal, sid)} "{text}": ' + ", ".join(f"`{p}`" for p in paths))
        out.append("")
    if d.reverted or d.failed or d.reruns:
        out += ["## Tried and abandoned", ""]
        out += [f"- {line}" for line in _abandoned_lines(d, where) + _failure_lines(d, where)]
        out.append("")
    if d.outside_repo:
        if out[-1] != "":
            out.append("")
        paths = ", ".join(f"`{p}`" for p in outside_summary(d.outside_repo))
        out.append(f"**Files written outside the repo:** {paths}")
    if d.notes:
        out += ["", *[f"_Note: {n}_" for n in d.notes]]
    out += ["", WHY_HINT, ""]
    return "\n".join(out)


WHY_HINT = (
    "Ask `graphene why <path>` for who changed a file and why, or `graphene why <path>:<line>` for one line."
)


def _what(f: FileLine) -> str:
    if f.effect == "reverted":
        return "reverted"
    if f.strategy == "none":
        return f"{f.effect} (no diff available)"
    if f.strategy == "deferred":
        return "modified (diff credited to a later prompt)"
    return f"{f.effect} +{f.added}/−{f.removed}"


def _abandoned_lines(d: Debrief, where) -> list[str]:
    """Real abandoned work: files put back to their session-start content, checks that failed then reran."""
    out = [f"reverted: `{r['path']}` ({where(r['prompt_ordinal'], r['session_id'])})" for r in d.reverted]
    for r in d.reruns:
        outcome = "passed" if r["rerun_passed"] else "failed again"
        first, again = where(r["failed_under"], r["session_id"]), where(r["rerun_under"], r["session_id"])
        if first == again:
            when = f"failed and was rerun under {first}"
        else:
            when = f"failed under {first}, rerun under {again}"
        out.append(f"check `{r['command']}` {when}: {outcome}")
    return out


def _failure_lines(d: Debrief, where) -> list[str]:
    """The full view only: refusals grouped by reason, then every real failure on its own line."""
    groups: dict[tuple[str, str], int] = {}
    for f in d.failed:
        if f["denied"]:
            groups[(f["tool"], f["reason"])] = groups.get((f["tool"], f["reason"]), 0) + 1
    out = [
        f"{count} {tool} call{'s' if count != 1 else ''} refused before running ({reason})"
        for (tool, reason), count in sorted(groups.items(), key=lambda kv: (-kv[1], kv[0]))
    ]
    for f in d.failed:
        if not f["denied"]:
            place = where(f["prompt_ordinal"], f["session_id"])
            out.append(f"failed {f['tool']}: `{f['what']}` ({place}) — {f['error']}")
    return out


def _unrequested_lines(d: Debrief, where) -> list[str]:
    return [
        f'`{u["path"]}` under {where(u["prompt_ordinal"], u["session_id"])} "{u["prompt"]}"'
        for u in d.unrequested
    ]


def _failure_line(d: Debrief, hint: bool = True) -> str | None:
    """Every failed tool call as one line; the full reconstruction lists them one by one.

    The terminal card drops the ``hint`` because its closing line already points at ``--full``.
    """
    total = d.failure_summary.get("total", 0)
    if not total:
        return None
    by_tool = ", ".join(f"{n} {tool}" for tool, n in d.failure_summary.get("by_tool", {}).items())
    denials = d.failure_summary.get("denials", 0)
    refused = f"; {denials} refused before running" if denials else ""
    tail = "; `graphene debrief --full` lists them" if hint else ""
    return f"{total} tool failure{'s' if total != 1 else ''} ({by_tool}{refused}){tail}"


def file_rows(d: Debrief) -> list[dict]:
    """One row per file with its net effect and summed counts over the covered sessions."""
    rows: dict[str, dict] = {}
    for block in d.prompts:
        for f in block.files:
            row = rows.setdefault(f.path, {"path": f.path, "effects": [], "added": 0, "removed": 0})
            row["effects"].append(f.effect)
            row["added"] += f.added
            row["removed"] += f.removed
    reverted = {r["path"] for r in d.reverted}
    out = []
    for row in rows.values():
        effects = row["effects"]
        if row["path"] in reverted or all(e == "reverted" for e in effects):
            effect = "reverted"
        elif effects[-1] == "deleted":
            effect = "deleted"
        elif "created" in effects:
            effect = "created"
        else:
            effect = "modified"
        out.append({"path": row["path"], "effect": effect, "added": row["added"], "removed": row["removed"]})
    return sorted(out, key=lambda r: (-(r["added"] + r["removed"]), r["path"]))


def _counted(row: dict) -> bool:
    """A reverted file has no net counts; a deletion with none known (a shell `rm`) shows none either."""
    if row["effect"] == "reverted":
        return False
    return not (row["effect"] == "deleted" and row["added"] + row["removed"] == 0)


def render_card(d: Debrief, limit: int = 30) -> str:
    """The short come-back view: numbers, commits, a capped net file list, and only the sections
    that have something real in them."""
    many = len(d.sessions) > 1

    def where(ordinal: int, session_id: str) -> str:
        return f"prompt {ordinal}" + (f" of {session_id[:8]}" if many else "")

    out: list[str] = ["# Graphene", ""]
    if d.sessions:
        span = f"{stamp(d.sessions[0]['started_at'])} → {stamp(d.sessions[-1]['ended_at'])}"
        head = (
            f"**Sessions {len(d.sessions)}** ({', '.join(s['id'][:8] for s in d.sessions)})"
            if many
            else f"**Session {d.sessions[0]['id'][:8]}**"
        )
        prompts = f"{d.prompt_count} prompt{'s' if d.prompt_count != 1 else ''}"
        files = f"{d.files_changed} file{'s' if d.files_changed != 1 else ''} (+{d.added}/−{d.removed})"
        out.append(f"{head} · {span} · {duration(d.wall_seconds)} · {prompts} · {files}  ")
    noun = "sessions" if many else "session"
    out.append(f"**Commits during the {noun}:** {len(d.commits) or 'none'}")
    out += [f"- {c}" for c in d.commits]
    rows = file_rows(d)
    if rows:
        out += ["", "**Files changed**"]
        for row in rows[:limit]:
            counts = f" +{row['added']}/−{row['removed']}" if _counted(row) else ""
            out.append(f"- `{row['path']}` {row['effect']}{counts}")
        if len(rows) > limit:
            out.append(f"- … {len(rows) - limit} more; `graphene why <path>` for any of them")
    if d.unrequested:
        out += ["", "**Not what you asked for**"]
        out += [f"- {line}" for line in _unrequested_lines(d, where)]
    abandoned = _abandoned_lines(d, where) + [line for line in [_failure_line(d)] if line]
    if abandoned:
        out += ["", "**Abandoned**", *[f"- {line}" for line in abandoned]]
    if d.outside_repo:
        out += [
            "",
            "**Written outside the repo:** " + ", ".join(f"`{p}`" for p in outside_summary(d.outside_repo)),
        ]
    if d.notes:
        out += ["", *[f"_Note: {n}_" for n in d.notes]]
    out += ["", WHY_HINT, ""]
    return "\n".join(out)


def outside_summary(paths: list[str], limit: int = 6) -> list[str]:
    """Paths outside the repo, collapsed to directories with counts once there are many of them."""
    if len(paths) <= limit:
        return sorted(paths)
    buckets: dict[str, list[str]] = {}
    for path in paths:
        parts = path.split("/")
        buckets.setdefault("/".join(parts[:3]), []).append(path)
    out: list[str] = []
    for group in buckets.values():
        if len(group) == 1:
            out.append(group[0])
        else:
            common = os.path.commonpath(group)
            if len(group) > 1 and common in group:  # commonpath is one of the files: use its directory
                common = os.path.dirname(common)
            out.append(f"{common}/ ({len(group)} files)")
    return sorted(out)


# -- terminal rendering -------------------------------------------------------------------------

ACCENT = "cyan"  # the one colour: the paths and commands you could act on
CARD_FILES = 20  # file rows before the card says "… N more"
CARD_COMMITS = 5
SECTION_ROWS = 6
WHY_HINT_TTY = "graphene why <path> · graphene why <path>:<line> · graphene debrief --full"


def write_line(console, text: Text, wrap: bool = False) -> None:
    """One line: styled for a colour terminal, plain text (no escape codes) anywhere else. With
    ``wrap``, a terminal gets it word-wrapped one column short of its width, no trailing spaces."""
    text.rstrip()
    if not (console.is_terminal and not console.no_color):
        console.file.write(text.plain + "\n")
        return
    lines = text.wrap(console, max(20, console.width - 1)) if wrap else [text]
    for line in lines:
        line.rstrip()
        console.print(line, no_wrap=True, crop=False, overflow="ignore")


def write_indented(console, text: Text, indent: int, wrap: bool = False) -> None:
    """A row under ``indent`` spaces; on a terminal, wrapped at words with a hanging indent: a
    continuation line sits two columns deeper than its row, so it cannot be read as a new row."""
    if not (wrap and console.is_terminal):
        write_line(console, Text(" " * indent).append_text(text))
        return
    for i, line in enumerate(text.wrap(console, max(20, console.width - 3 - indent))):
        line.rstrip()
        write_line(console, Text(" " * (indent + (2 if i else 0))).append_text(line))


def clip(text: str, width: int) -> str:
    """Truncate at the end, so a row never wraps."""
    return text if len(text) <= width else text[: max(1, width - 1)].rstrip() + "…"


def clip_middle(text: str, width: int) -> str:
    """Truncate a path in the middle: its name matters as much as its directory."""
    if len(text) <= width or width < 5:
        return clip(text, width)
    head = (width - 1) // 2
    return text[:head] + "…" + text[len(text) - (width - 1 - head) :]


def code_text(line: str, width: int | None) -> Text:
    """A markdown-ish line as Text: what `backticks` marked takes the accent, the rest is plain.
    Truncated to ``width`` when one is given; the full view passes None and wraps instead."""
    out = Text()
    for i, part in enumerate(line.split("`")):
        out.append(part, ACCENT if i % 2 else None)
    if width is not None:
        out.truncate(width, overflow="ellipsis")
    return out


def _span(d: Debrief) -> str:
    start, end = stamp(d.sessions[0]["started_at"]), stamp(d.sessions[-1]["ended_at"])
    return f"{start} → {end[11:] if end[:10] == start[:10] else end}"


def _section(console, label: str, rows: list[str], width: int, limit: int | None = SECTION_ROWS) -> None:
    """A labelled block of rows; capped and clipped on the card, complete and wrapped in the full view."""
    if not rows:
        return
    write_line(console, Text(""))
    write_line(console, Text(label))
    for row in rows[: limit or len(rows)]:
        write_indented(console, code_text(row, width - 2 if limit else None), 2, wrap=not limit)
    if limit and len(rows) > limit:
        write_line(console, Text(f"  … {len(rows) - limit} more", "dim"))


def _print_header(console, d: Debrief, width: int, commits: int | None) -> None:
    """The two header lines and the commit list (capped on the card, complete in the full view)."""
    many = len(d.sessions) > 1
    ids = ", ".join(s["id"][:8] for s in d.sessions)
    head = f"Sessions {len(d.sessions)} ({ids})" if many else f"Session {ids or 'none'}"
    if d.sessions:
        head += f" · {_span(d)} · {duration(d.wall_seconds)}"
    write_line(console, Text(clip(head, width), "bold"))

    counts = Text()
    counts.append(f"{d.prompt_count} prompt{'s' if d.prompt_count != 1 else ''} · ", "dim")
    counts.append(f"{d.files_changed} file{'s' if d.files_changed != 1 else ''} ", "dim")
    counts.append(f"+{d.added}", "green")
    counts.append("/", "dim")
    counts.append(f"−{d.removed}", "red")
    counts.append(f" · {len(d.commits) or 'no'} commit{'s' if len(d.commits) != 1 else ''}", "dim")
    write_line(console, counts)
    shown = d.commits[:commits] if commits else d.commits
    for entry in shown:
        sha, _, subject = entry.partition(" ")
        row = Text("  ")
        row.append(sha, "dim")
        row.append(" " + clip(subject, width - len(sha) - 3))
        write_line(console, row)
    if len(d.commits) > len(shown):
        write_line(console, Text(f"  … {len(d.commits) - len(shown)} more", "dim"))


def print_card(console, d: Debrief, files: int = CARD_FILES, commits: int = CARD_COMMITS) -> None:
    """The card for a terminal: the facts `render_card` writes, aligned into columns and coloured."""
    width = max(40, console.width)
    many = len(d.sessions) > 1
    _print_header(console, d, width, commits)

    rows = file_rows(d)
    if rows:
        shown = rows[:files]
        effect = max(len(r["effect"]) for r in shown)
        added = max(len(f"+{r['added']}") for r in shown)
        removed = max(len(f"−{r['removed']}") for r in shown)
        room = max(12, width - 8 - effect - added - removed)
        paths = min(room, max(len(r["path"]) for r in shown))
        write_line(console, Text(""))
        write_line(console, Text("Files changed"))
        for r in shown:
            row = Text("  ")
            row.append(clip_middle(r["path"], paths).ljust(paths), ACCENT)
            row.append("  " + r["effect"].ljust(effect), "dim")
            if _counted(r):
                row.append("  " + f"+{r['added']}".rjust(added), "green")
                row.append("  " + f"−{r['removed']}".rjust(removed), "red")
            write_line(console, row)
        if len(rows) > files:
            write_line(
                console,
                Text(f"  … {len(rows) - files} more; graphene why <path> for any", "dim"),
            )

    def where(ordinal: int, session_id: str) -> str:
        return f"prompt {ordinal}" + (f" of {session_id[:8]}" if many else "")

    _section(console, "Not what you asked for", _unrequested_lines(d, where), width)
    _section(
        console,
        "Abandoned",
        _abandoned_lines(d, where) + [line for line in [_failure_line(d, hint=False)] if line],
        width,
    )
    _section(console, "Written outside the repo", outside_summary(d.outside_repo), width)
    for note in d.notes:
        write_line(console, Text(""))
        write_line(console, Text(f"Note: {note}", "dim"), wrap=True)
    write_line(console, Text(""))
    write_line(console, Text(clip(WHY_HINT_TTY, width), "dim"))


def _effect_text(f: FileLine) -> Text:
    """The effect and counts of one file line: dim words, green `+N`, red `−N`."""
    out = Text()
    if f.effect == "reverted" or f.strategy in ("none", "deferred"):
        out.append(_what(f), "dim")
        return out
    out.append(f"{f.effect} ", "dim")
    out.append(f"+{f.added}", "green")
    out.append("  ")
    out.append(f"−{f.removed}", "red")
    return out


def print_full(console, d: Debrief) -> None:
    """`debrief --full` for a terminal: every prompt, file and failure, in the card's style, complete
    (nothing capped) and wrapped rather than clipped."""
    width = max(40, console.width)
    many = len(d.sessions) > 1

    def where(ordinal: int, session_id: str) -> str:
        return f"prompt {ordinal}" + (f" of {session_id[:8]}" if many else "")

    _print_header(console, d, width, None)
    current = None
    for block in d.prompts:
        write_line(console, Text(""))
        if many and block.session_id != current:
            current = block.session_id
            info = next(s for s in d.sessions if s["id"] == block.session_id)
            session = f"Session {block.session_id[:8]} ({info['source']}, {_span_of(info)})"
            write_line(console, Text(clip(session, width), "bold"))
            write_line(console, Text(""))
        if block.ordinal == 0:
            title = f"Before the first recorded prompt (session started {stamp(block.timestamp)})"
        else:
            title = f"{block.ordinal}. {stamp(block.timestamp)}"
        write_line(console, Text(clip(title, width), "bold"))
        for line in block.text.strip().splitlines():
            write_indented(console, Text(f"> {line}", "dim"), 2, wrap=True)
        if not block.files:
            write_line(console, Text("  no file changes", "dim"))
        for f in block.files:
            row = Text()
            row.append(f.path, ACCENT)
            row.append("  ")
            row.append_text(_effect_text(f))
            if f.unrequested:
                row.append("  [unrequested]")
            write_indented(console, row, 2, wrap=True)
            write_indented(console, Text(f.explanation), 4, wrap=True)
    _section(console, "Not what you asked for", _unrequested_lines(d, where), width, limit=None)
    abandoned = _abandoned_lines(d, where) + _failure_lines(d, where)
    _section(console, "Tried and abandoned", abandoned, width, limit=None)
    _section(console, "Written outside the repo", outside_summary(d.outside_repo), width, limit=None)
    for note in d.notes:
        write_line(console, Text(""))
        write_line(console, Text(f"Note: {note}", "dim"), wrap=True)
    write_line(console, Text(""))
    write_line(console, Text(clip(WHY_HINT_TTY, width), "dim"))


def _span_of(info: dict) -> str:
    return f"{stamp(info['started_at'])} → {stamp(info['ended_at'])}"


def print_why(console, path: str, content: str, subtitle: str, entries: list) -> None:
    """`why PATH` and `why PATH:LINE`: the file, one line of provenance, then a block per prompt."""
    width = max(40, console.width)
    head = Text()
    head.append(clip_middle(path, width if not content else max(16, width // 2)), ACCENT)
    if content:
        head.append("  " + clip(content.strip(), max(8, width - len(head.plain) - 2)))
    write_line(console, head)
    write_line(console, Text(clip(subtitle, width), "dim"))
    for e in entries:
        write_line(console, Text(""))
        row = Text()
        row.append(f"{stamp(e.timestamp)}  session {e.session_id[:8]}  prompt {e.ordinal}  ", "dim")
        row.append_text(_effect_text(e.change_line()))
        write_line(console, row)
        for line in preview(e.prompt_text).splitlines():
            write_indented(console, Text(f"> {line}", "dim"), 2, wrap=True)
        write_indented(console, Text(e.explanation), 2, wrap=True)


def print_sessions(console, rows: list[tuple[str, str, str, str, int, int]]) -> None:
    """`graphene sessions`: aligned columns, no box, newest first."""
    head = ("session", "source", "started", "ended", "prompts", "calls")
    table = [head] + [tuple(str(cell) for cell in row) for row in rows]
    widths = [max(len(row[i]) for row in table) for i in range(len(head))]
    for n, row in enumerate(table):
        line = Text()
        for i, cell in enumerate(row):
            padded = cell.rjust(widths[i]) if i >= 4 else cell.ljust(widths[i])
            line.append(padded + ("  " if i < len(row) - 1 else ""), "dim" if n == 0 or i < 4 else None)
        write_line(console, line)


def to_json(d: Debrief) -> str:
    return json.dumps(asdict(d), ensure_ascii=False, indent=2)


def from_json(text: str) -> Debrief:
    data = json.loads(text)
    prompts = [
        PromptBlock(**{**p, "files": [FileLine(**f) for f in p["files"]]}) for p in data.pop("prompts")
    ]
    return Debrief(**data, prompts=prompts)
