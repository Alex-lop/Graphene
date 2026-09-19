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
    coverage: dict = field(default_factory=dict)  # of the window's committed files: the three counts


SHELL_LISTS_HINT = (
    'one line only you can add: "bashEditDiffEnabled": true in ~/.claude/settings.json makes Claude Code '
    "record which files every shell command changed (a repo's settings cannot turn it on). Without it "
    "those lists exist only when Claude Code itself routes edits through the shell, and a file an agent "
    "writes with a heredoc or a script traces to its commit at best"
)


def shell_lists_enabled() -> bool:
    """Is the vendor's shell change list on in the person's own settings? Read, never written."""
    config = Path(os.environ.get("CLAUDE_CONFIG_DIR", Path.home() / ".claude")) / "settings.json"
    try:
        return json.loads(config.read_text(encoding="utf-8")).get("bashEditDiffEnabled") is True
    except (OSError, ValueError, AttributeError):
        return False


def coverage_line(c: dict) -> str:
    """How much of what git committed the records account for. Never one number: a file an agent
    only committed is not a file it is recorded writing."""
    if not c:
        return ""
    n = c["committed_files"]
    if not n:
        return "no commits in the window, so no committed file to account for"
    nothing = f"{c['nothing']} to nothing"
    if c["window"]:
        nothing += f" ({c['window']} committed in the window by no identifiable agent)"
    return (
        f"{n} committed file{'s' if n != 1 else ''} · {c['write']} traced to a recorded write "
        f"({c['edit']} edit, {c['shell']} shell) · {c['commit']} only to an agent's commit · {nothing}"
    )


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
        fresh = [i for i in fresh if store.did_something(i)]
        if fresh:
            return fresh
    # the latest session that did something: a card about an empty session says nothing
    for wanted in (store.did_something, store.event_count):
        for s in reversed(sessions):
            if wanted(s.id):
                return [s.id]
    return [sessions[-1].id] if sessions else []


# -- building -----------------------------------------------------------------------------------


def template(change: FileChange) -> str:
    """The factual sentence under each file line: what the diff itself says, and nothing more."""
    name = change.path.rsplit("/", 1)[-1]
    counts = f"+{change.added}/−{change.removed}"
    if change.strategy == "deferred":
        return f"Touched {name}; its diff for this session is credited to a later prompt."
    if change.strategy == "later":
        return f"Touched {name}; its diff is credited to a later session, which is where it ends."
    if change.strategy == "none" and change.effect == "deleted":
        return f"Deleted {name} through a shell command (no content available)."
    if change.effect == "reverted" and change.strategy != "payload":
        return f"Touched {name}, but its content matches the session start."
    if change.effect == "created":
        defined = f", defining {_join(change.symbols)}" if change.symbols else ""
        return f"Created {name} with {change.added} lines{defined}."
    if change.effect == "deleted":
        return f"Deleted {name} ({change.removed} lines)."
    if change.effect == "reverted":
        return f"Edited {name} and then restored it; no net change."
    if change.strategy == "none":
        return f"Changed {name} through a shell command (no diff available)."
    if change.symbols:
        n = len(change.symbols)
        noun = "definition" if n == 1 else "definitions"
        return f"Edited {n} {noun} in {name}: {_join(change.symbols)} ({counts})."
    total = change.added + change.removed
    return f"Changed {total} line{'s' if total != 1 else ''} in {name} ({counts})."


def _join(names: list[str]) -> str:
    return ", ".join(names[:-1]) + f" and {names[-1]}" if len(names) > 1 else names[0]


def build_debrief(
    store: Store,
    session_ids: list[str],
    root: Path,
    now: datetime | None = None,
) -> Debrief:
    now = now or datetime.now(UTC)
    debrief = Debrief(generated_at=iso(now))
    results = attribute(store, session_ids, root)
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
                        [asdict(h) for h in change.hunks],
                    )
                )
                paths.add(change.path)
                debrief.added += change.added
                debrief.removed += change.removed
            debrief.prompts.append(block)
        for prompt in prompts:
            changes = by_prompt.get(prompt.id, [])
            block = PromptBlock(sid, prompt.id, prompt.ordinal, prompt.timestamp, prompt.text)
            for change in changes:
                block.files.append(
                    FileLine(
                        change.path,
                        change.effect,
                        change.added,
                        change.removed,
                        change.unrequested,
                        change.strategy,
                        template(change),
                        "none",
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
    from .graph import coverage_counts, run_records  # here: graph imports this module

    run = run_records(store, [s["id"] for s in debrief.sessions])
    debrief.coverage = coverage_counts(run.coverage)
    shell = [e for e in run.events if e.tool == "Bash"]
    listed = any(isinstance(e.response, dict) and "bashEditDiff" in e.response for e in shell)
    if shell and not listed and debrief.coverage["commit"] + debrief.coverage["nothing"]:
        debrief.notes.append(
            f"none of this window's {len(shell)} shell calls carries Claude Code's list of the files it "
            "changed, so a file written through the shell traces to a commit at best; `graphene init` "
            "says how to turn the lists on"
        )
    by_tool: dict[str, int] = {}
    for f in debrief.failed:
        by_tool[f["tool"]] = by_tool.get(f["tool"], 0) + 1
    debrief.failure_summary = {
        "total": len(debrief.failed),
        "by_tool": dict(sorted(by_tool.items(), key=lambda kv: (-kv[1], kv[0]))),
        "denials": sum(1 for f in debrief.failed if f["denied"]),
    }
    return debrief


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


def _local(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone()


def stamp(value: str | None) -> str:
    """A recorded moment in this machine's local time; `offset` says which time that is."""
    return _local(value).strftime("%Y-%m-%d %H:%M") if value else "?"


def offset(value: str | None) -> str:
    return _local(value).strftime("%z") if value else ""


def stamp_tz(value: str | None) -> str:
    return f"{stamp(value)} {offset(value)}".rstrip()


def duration(seconds: int) -> str:
    hours, rest = divmod(seconds, 3600)
    minutes = rest // 60
    return f"{hours}h {minutes:02d}m" if hours else f"{minutes}m"


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
    if f.strategy == "later":
        return "modified (diff credited to a later session)"
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


def _unrequested_lines(d: Debrief, where) -> list[str]:
    return [
        f'`{u["path"]}` under {where(u["prompt_ordinal"], u["session_id"])} "{u["prompt"]}"'
        for u in d.unrequested
    ]


def _failure_line(d: Debrief) -> str | None:
    """Every failed tool call as one line; `--json` carries them one by one."""
    total = d.failure_summary.get("total", 0)
    if not total:
        return None
    by_tool = ", ".join(f"{n} {tool}" for tool, n in d.failure_summary.get("by_tool", {}).items())
    denials = d.failure_summary.get("denials", 0)
    refused = f"; {denials} refused before running" if denials else ""
    return f"{total} tool failure{'s' if total != 1 else ''} ({by_tool}{refused})"


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
        span = _span(d)
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
    out += [f"- {c}" for c in d.commits[:CARD_COMMITS]]
    if len(d.commits) > CARD_COMMITS:
        out.append(f"- … {len(d.commits) - CARD_COMMITS} more; `git log` has them all")
    if d.coverage:
        out += ["", f"**Coverage:** {coverage_line(d.coverage)}"]
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
WHY_HINT_TTY = "graphene why <path> · graphene why <path>:<line>"


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
    zone = offset(d.sessions[0]["started_at"])
    return f"{start} → {end[11:] if end[:10] == start[:10] else end} {zone}".rstrip()


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
    if d.coverage:
        line = Text("coverage ", "dim")
        line.append(coverage_line(d.coverage))
        write_line(console, line, wrap=True)


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
        _abandoned_lines(d, where) + [line for line in [_failure_line(d)] if line],
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
    if f.effect == "reverted" or f.strategy in ("none", "deferred", "later"):
        out.append(_what(f), "dim")
        return out
    out.append(f"{f.effect} ", "dim")
    out.append(f"+{f.added}", "green")
    out.append("  ")
    out.append(f"−{f.removed}", "red")
    return out


GRADE_WORDS = {
    "edit": "recorded edit",
    "shell": "in the vendor's list of what a shell command changed",
    "command": "read from the recorded command",
}


def print_why(console, path: str, content: str, subtitle: str, entries: list) -> None:
    """`why PATH` and `why PATH:LINE`: the file, one line of provenance, then a block per prompt."""
    width = max(40, console.width)
    head = Text()
    head.append(clip_middle(path, width if not content else max(16, width // 2)), ACCENT)
    if content:
        head.append("  " + clip(content.strip(), max(8, width - len(head.plain) - 2)))
    write_line(console, head)
    for part in subtitle.split("\n"):  # the count, then the file's coverage
        write_line(console, Text(part, "dim"), wrap=True)
    for e in entries:
        write_line(console, Text(""))
        row = Text()
        row.append(f"{stamp_tz(e.timestamp)}  session {e.session_id[:8]}  prompt {e.ordinal}  ", "dim")
        row.append_text(_effect_text(e.change_line()))
        row.append(f"  {GRADE_WORDS.get(e.grade, e.grade)}", "dim")
        write_line(console, row)
        for agent, task in e.who:
            name = f"agent {agent[:8]}" if agent else "the main agent"
            write_indented(console, Text(f"by {name}" + (f": {task}" if task else ""), "dim"), 2, wrap=True)
        for line in preview(e.prompt_text).splitlines():
            write_indented(console, Text(f"> {line}", "dim"), 2, wrap=True)
        write_indented(console, Text(e.explanation), 2, wrap=True)


COVERAGE_KEY = (
    "coverage = committed files: traced to a recorded write / only to an agent's commit / to nothing"
)


def coverage_cell(c: dict) -> str:
    return (
        f"{c['committed_files']}: {c['write']}/{c['commit']}/{c['nothing']}"
        if c.get("committed_files")
        else "-"
    )


def print_sessions(console, rows: list[tuple[str, str, str, str, int, str]], zone: str = "") -> None:
    """`graphene sessions`: aligned columns, no box, newest first; ``zone`` is the times' UTC offset."""
    head = ("session", "source", f"started {zone}".rstrip(), "ended", "calls", "coverage")
    table = [head] + [tuple(str(cell) for cell in row) for row in rows]
    widths = [max(len(row[i]) for row in table) for i in range(len(head))]
    for n, row in enumerate(table):
        line = Text()
        for i, cell in enumerate(row):
            padded = cell.rjust(widths[i]) if i >= 4 else cell.ljust(widths[i])
            line.append(padded + ("  " if i < len(row) - 1 else ""), "dim" if n == 0 or i < 4 else None)
        write_line(console, line)
    if any(row[5] != "-" for row in rows):
        write_line(console, Text(COVERAGE_KEY, "dim"), wrap=True)


def to_json(d: Debrief) -> str:
    return json.dumps(asdict(d), ensure_ascii=False, indent=2)


def from_json(text: str) -> Debrief:
    data = json.loads(text)
    prompts = [
        PromptBlock(**{**p, "files": [FileLine(**f) for f in p["files"]]}) for p in data.pop("prompts")
    ]
    return Debrief(**data, prompts=prompts)
