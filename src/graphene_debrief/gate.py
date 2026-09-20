"""What the Claude Code hooks answer while a plan is in force. Standard library only.

The plan binds at the boundary whoever executes a node (``plan.finish``: git and the check decide).
This is the part only a vendor's hooks can add: the write refused before it happens, with the reason;
the stop refused while a node is open; the person's word kept out of an agent's mouth. Each answer is
the vendor's documented JSON (code.claude.com/docs/en/hooks), printed by ``hook_main``.

The holes, which the README and the map print beside the controls:
- a hook that crashes or times out lets the call through (the vendor's rule); ``finish`` still holds;
- a shell command can write a file in a way no parser reads (a script that opens files itself);
  when the vendor reports what a command changed it is refused after the fact, and ``finish`` asks
  git, which sees every write however it was made;
- the vendor lets a session stop after 8 refused stops in a row; the node then stays open, visibly;
- the refusals that read a command's text (GRAPHENE_AS, .graphene/) stop the ordinary spellings and
  not a determined one. What holds against that is elsewhere: ``plan.caller`` ranks an agent's own
  environment above the variable, and the store is the one thing nothing here can defend against a
  script that opens it directly.
"""

from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path

from . import plan as P

WRITE_TOOLS = {"Edit", "Write", "MultiEdit", "NotebookEdit"}
OURS = (".graphene",)  # the plan's own store: never inside any scope
_AS_PERSON = re.compile(r"\bGRAPHENE_AS\b")
PARSED = 64_000  # characters of a shell command the hook will parse: the parser is superlinear, and the
# vendor lets a call through when a hook runs out of time (3 MB took 234 s in the closing review)


def _deny(reason: str) -> dict:
    return {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": reason,
        }
    }


def _held(store, session_id: str) -> list[P.Node]:
    return [n for n in P.nodes(store, (P.RUNNING,)) if n.session_id == session_id]


def _rel(path: str, root: Path, cwd: str | None) -> str | None:
    """Repo-relative for a path in the repo or a worktree of it; None for anywhere else."""
    from .sources.claude_code import _map_path  # here, not at the top: that module imports this one

    full = path if os.path.isabs(path) else os.path.join(cwd or str(root), path)
    rel = _map_path(full, root, cwd, None)
    return None if os.path.isabs(rel) or rel.startswith("..") else rel


def _leaves(path: str, root: Path, cwd: str | None) -> str | None:
    """The repo-relative spelling of a path inside the repo whose real file is not: a symbolic link
    (or a directory that is one) pointing out of the repo, or into the plan's own store. A write
    through it would land where no scope reaches, so it is refused whatever the scope says."""
    rel = _rel(path, root, cwd)
    if rel is None:
        return None
    full = path if os.path.isabs(path) else os.path.join(cwd or str(root), path)
    real, home = os.path.realpath(full), os.path.realpath(root)
    if os.path.realpath(os.path.dirname(full)) == os.path.dirname(
        os.path.abspath(full)
    ) and not os.path.islink(full):
        return None  # nothing on the way is a link: the common case, decided without touching git
    inside = _rel(real, Path(home), None)
    return rel if inside is None or inside.split("/", 1)[0] in OURS else None


def _ignored(root: Path, rel: str) -> bool:
    """Does git ignore this path? Asked only on the way to a refusal, never on the fast path."""
    try:
        out = subprocess.run(["git", "-C", str(root), "check-ignore", "-q", rel], timeout=2)
    except (OSError, subprocess.SubprocessError):
        return False
    return out.returncode == 0


def _link(rel: str) -> dict:
    return _deny(f"{rel} is a symbolic link that leaves the repo; no scope covers where it points")


def _how_out(held: list[P.Node]) -> str:
    n = held[0]
    return (
        f"If the work cannot be done inside that scope, do not work around it: "
        f"`graphene node release {n.id} --why '<what you need and why>'` hands it back, and the person "
        "decides whether the scope is wrong. Only they can widen it"
    )


def _claim_first(store) -> str:
    ready = P.ready(P.nodes(store), P.Caller("agent", False))
    if ready:
        return (
            f"This repo has a plan in force and this session holds no node, so nothing here may be "
            f"written yet. `graphene plan` shows the plan; `graphene node start {ready[0].id}` takes the "
            "first node that is ready and prints what you may touch and how it is checked"
        )
    running = [f"{n.id} is held by {n.executor}" for n in P.nodes(store, (P.RUNNING,))]
    return (
        "This repo has a plan in force and no node is ready for an agent to take"
        + (f" ({'; '.join(running)})" if running else "")
        + ", so nothing here may be written: work happens inside a node, and a plan stays in force "
        "after its last node is done. If this change is worth making, propose a node for it: "
        "`graphene node add '<what>' --scope '<paths it needs>' --check '<command that shows it is done>'`, "
        "then tell the person; they accept it, change it, or say no. `graphene plan` shows what each "
        "node waits for"
    )


def _check_write(store, held: list[P.Node], rel: str, event: dict, how: str) -> dict | None:
    if rel.split("/", 1)[0] in OURS:
        return _deny(f"{rel} is the plan's own store; no node's scope covers it")
    agent_id = event.get("agent_id") if isinstance(event.get("agent_id"), str) else None
    if not held:  # "*" is the plan's own log: what happened that belongs to no node
        store.log_node(
            "*", P._now(), "denied", None, event.get("session_id"), agent_id, {"path": rel, "how": how}
        )
        return _deny(_claim_first(store))
    if any(P.in_scope(rel, n.scope) for n in held):
        return None  # inside the scope: say nothing, so the person's own permission settings still apply
    n = held[0]
    store.log_node(
        n.id, P._now(), "denied", n.executor, event.get("session_id"), agent_id, {"path": rel, "how": how}
    )
    scopes = "; ".join(f"{h.id}: {', '.join(h.scope)}" for h in held)
    return _deny(f"{rel} is outside the scope of the node you hold ({scopes}). {_how_out(held)}")


def decide(store, event: dict, root: Path) -> dict | None:
    """The hook's answer for this event, or None to say nothing."""
    name = event.get("hook_event_name")
    sid = event.get("session_id")
    if not isinstance(sid, str) or name not in ("PreToolUse", "PostToolUse", "Stop", "SessionStart"):
        return None
    if not P.in_force(store):
        return None
    tool = event.get("tool_name")
    tool_input = event.get("tool_input") if isinstance(event.get("tool_input"), dict) else {}
    cwd = event.get("cwd") if isinstance(event.get("cwd"), str) else None

    if name == "SessionStart":
        return {
            "hookSpecificOutput": {
                "hookEventName": "SessionStart",
                "additionalContext": (
                    "This repository has a Graphene plan in force: a graph of nodes, each with a goal, "
                    "the paths it may touch, and a check. Work happens inside a node: `graphene plan` "
                    "shows the plan and what is ready; `graphene node start <id>` takes a node and "
                    "prints its contract. Writes outside the node you hold are refused."
                ),
            }
        }

    if name == "Stop":
        held = _held(store, sid)
        if not held:
            return None
        n = held[0]
        store.log_node(n.id, P._now(), "stop_refused", n.executor, sid, None, None)
        return {
            "decision": "block",
            "reason": (
                f"You hold {', '.join(h.id for h in held)} and {'it is' if len(held) == 1 else 'they are'} "
                f"not done. `graphene node done {n.id}` finishes it: Graphene runs the check "
                f"({P.done_means(n)}) and asks git what changed. If it cannot be finished as written, "
                f"`graphene node release {n.id} --why '<what is in the way>'` hands it back. "
                "Then you may stop."
            ),
        }

    if name == "PreToolUse" and tool in WRITE_TOOLS:
        path = tool_input.get("file_path") or tool_input.get("notebook_path")
        if not (isinstance(path, str) and path):
            return None
        if _leaves(path, root, cwd):
            return _link(_leaves(path, root, cwd))
        rel = _rel(path, root, cwd)
        return None if rel is None else _check_write(store, _held(store, sid), rel, event, tool)

    if name == "PreToolUse" and tool == "Bash":
        command = str(tool_input.get("command") or "")
        if _AS_PERSON.search(command):
            return _deny(
                "GRAPHENE_AS is how a script says it speaks for a person; an agent's command may not "
                "carry it. Say what you need, and the person decides"
            )
        if ".graphene" in command and not re.match(r"\s*graphene\s", command):
            return _deny(
                "the plan's own store (.graphene/) is not an agent's to read around or write: use "
                "`graphene plan`, `graphene node show <id>` and `graphene plan log`"
            )
        if len(command) > PARSED:
            return None  # ponytail: too long to parse inside the hook's time; `done` asks git anyway
        from .attribute import bash_written_paths

        held = _held(store, sid)
        for written, _kind in bash_written_paths(command, Path(cwd or root)):
            if _leaves(written, root, cwd):
                return _link(_leaves(written, root, cwd))
            rel = _rel(written, root, cwd)
            if (
                rel is not None and rel.split("/", 1)[0] in OURS
            ):  # before any scope is asked: `**` does not cover it
                return _check_write(store, held, rel, event, "shell")
            if rel is None or (held and any(P.in_scope(rel, n.scope) for n in held)):
                continue
            if rel.split("/", 1)[0] not in OURS and _ignored(root, rel):
                continue  # a build leftover git ignores is nobody's change
            return _check_write(store, held, rel, event, "shell")
        return None

    if name == "PostToolUse" and tool == "Bash":
        held = _held(store, sid)
        response = event.get("tool_response") if isinstance(event.get("tool_response"), dict) else {}
        diff = response.get("bashEditDiff") if isinstance(response.get("bashEditDiff"), dict) else {}
        if not held or diff.get("shared"):  # a list another command's changes leaked into proves nothing
            return None
        changed = [_rel(p, root, cwd) for p in diff.get("changedFiles") or [] if isinstance(p, str)]
        stray = [r for r in changed if r and not any(P.in_scope(r, n.scope) for n in held)]
        stray = [r for r in stray if not _ignored(root, r)]
        if not stray:
            return None
        n = held[0]
        store.log_node(n.id, P._now(), "breach", n.executor, sid, None, {"paths": stray, "how": "shell"})
        return {
            "decision": "block",
            "reason": (
                f"That command changed {', '.join(stray)}, outside the scope of the node you hold "
                f"({n.id}: {', '.join(n.scope)}). Put it back as it was now; `graphene node done` asks "
                f"git and will refuse while it differs. {_how_out(held)}"
            ),
        }
    return None
