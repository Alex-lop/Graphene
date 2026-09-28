"""The settings a person states once: the standing conditions (protected paths no scope may include,
read-only globs, what the planner must never propose) and how big a plan is. They live in the
store's plan_meta; `graphene config` shows them as text and edits them the way `plan edit` edits
the plan: a line that cannot be read is refused by its number, and the rest is written all or none.

plan.py imports this module inside functions only: this one imports plan."""

from __future__ import annotations

import json
import re

from graphene_map import plan as P

SIZES = ("auto", "finer", "coarser")
GLOBS = ("protected", "readonly")  # a line of either holds globs, comma-separated; lines add up
HEAD = """\
# Graphene's settings. A line is `key: value`; a line starting with '#' is not read.
# protected: globs no scope may include      readonly: globs no leaf may write
# never: one thing the planner must never propose, a line each
# size: auto, finer or coarser (how big a plan the planner proposes)
"""


def _list(store, key: str) -> list[str]:
    return json.loads(store.meta(f"settings:{key}") or "[]")


def protected(store) -> list[str]:
    return _list(store, "protected")


def readonly(store) -> list[str]:
    return _list(store, "readonly")


def never(store) -> list[str]:
    return _list(store, "never")


def size(store) -> str:
    return store.meta("settings:size") or "auto"


def conditions_for_planner(store) -> str:
    """The standing conditions as the planner's prompt says them; empty when there are none."""
    lines = []
    if protected(store):
        lines.append(f"No scope may include these paths: {', '.join(protected(store))}.")
        # a Codex planner, or a Claude Code one where the hooks are not installed, is refused nothing
        lines.append(f"Never read these paths either: {', '.join(protected(store))}.")
    if readonly(store):
        lines.append(f"No leaf may write these paths: {', '.join(readonly(store))}.")
    lines += [f"Never propose this: {n}" for n in never(store)]
    if size(store) != "auto":
        lines.append(f"The person wants a {size(store)} plan than you would size it by default.")
    return "\n".join(lines)


def broken(store, files: list[str]) -> list[str]:
    """A line for each leaf not yet done whose scope a standing condition now covers: it is refused
    at start (and at done), so the person narrows it before an executor spends an attempt on it."""
    said = []
    for node in P.nodes(store):
        if node.aside or node.state not in (P.PROPOSED, P.OPEN) or not node.scope:
            continue
        for setting, glob in P.standing(store):
            hit = P.overlap(node.scope, [glob], files)
            if hit:
                said.append(f"{node.id}: its scope ({', '.join(node.scope)}) now covers {hit[0]}, kept out "
                            f"by `{setting}: {glob}`; narrow it: graphene plan edit {node.id}")  # fmt: skip
                break
    return said


def elsewhere(store) -> list[str]:
    """The settings changed by their own commands, shown as comment lines: a save never reads them."""
    return [
        f"# planner: {store.meta('planner') or 'none chosen'} (graphene init --planner)",
        f"# executor: {store.meta('executor') or 'none chosen'} (graphene init --executor)",
        f"# plan first: {'on' if P.plan_first(store) else 'off'} (graphene plan first on|off)",
    ]


def render(store) -> str:
    out = [HEAD.rstrip("\n"), *elsewhere(store), ""]
    out += [f"{key}: {', '.join(_list(store, key))}" for key in GLOBS if _list(store, key)]
    out += [f"never: {n}" for n in never(store)]
    out.append(f"size: {size(store)}")
    return "\n".join(out) + "\n"


def _glob(no: int, glob: str) -> str:
    bare = glob.removeprefix("./")
    if bare.startswith(("/", "~")) or ".." in bare.split("/"):
        raise P.Refused(f"line {no}: {glob!r} is not inside the repo; a glob is repo-relative")
    if re.search(r"\s#", bare):  # read as part of the glob, it would match nothing and protect nothing
        raise P.Refused(f"line {no}: {glob!r}: a note goes on a line of its own, starting with '#'")
    if bare.startswith("!"):
        raise P.Refused(f"line {no}: {glob!r}: a '!' glob is not read here; name only what it covers")
    return bare


def apply(store, text: str, who: P.Caller, opened: str | None = None) -> list[str]:
    """Read the whole text, then write every setting it names (one left out is cleared) in one
    claim; a line that cannot be read refuses all of it. Person-only. ``opened``: the text the editor
    was opened on; when the settings no longer render as it, someone else changed them meanwhile and
    the save is refused, never written over theirs. Returns the text as stored."""
    P._person_only(who, "changing Graphene's settings")
    got: dict[str, list[str]] = {"protected": [], "readonly": [], "never": []}
    said_size = None
    for no, line in enumerate(text.splitlines(), 1):
        body = line.strip()
        if not body or body.startswith("#"):
            continue
        key, colon, value = body.partition(":")
        key, value = key.strip(), value.strip()
        if not colon or key not in (*got, "size"):
            raise P.Refused(
                f"line {no}: {body[:40]!r} is not a setting; the keys are protected, readonly, never, size"
            )
        if key == "size":
            if value not in SIZES:
                raise P.Refused(f"line {no}: size is auto, finer or coarser, not {value!r}")
            if said_size:
                raise P.Refused(f"line {no}: size is said on line {said_size[0]} already")
            said_size = (no, value)
        elif key == "never":
            if not value:
                raise P.Refused(f"line {no}: never: needs what the planner must never propose")
            got["never"].append(value)
        else:
            globs = [g.strip() for g in value.split(",")]
            if not all(globs):
                raise P.Refused(f"line {no}: {key}: needs globs, comma-separated, none empty")
            got[key] += [_glob(no, g) for g in globs if _glob(no, g) not in got[key]]
    if not (said_size or any(got.values())):  # an emptied text is a slip (an editor's crash), as in plan edit
        raise P.Refused("nothing is applied from a text with no setting in it; to clear them all, save "
                        "`size: auto` alone")  # fmt: skip
    with store.claim():
        now_said = render(store)
        if opened is not None and now_said != opened:
            now = "; ".join(line for line in now_said.splitlines() if not line.startswith("#"))
            raise P.Refused(f"the settings were changed by someone else since this text was opened; they now "
                            f"say: {now}. Keep what you want of theirs and save again")  # fmt: skip
        was = {k: _list(store, k) for k in got} | {"size": size(store)}
        for key, values in got.items():
            store.set_meta(f"settings:{key}", json.dumps(values) if values else None)
        store.set_meta("settings:size", said_size[1] if said_size else None)
        now = {**got, "size": said_size[1] if said_size else "auto"}
        changed = {k: [was[k], now[k]] for k in now if was[k] != now[k]}
        if changed:
            store.log_node("*", P._now(), "settings", who.label, None, None, {"changed": changed})
    return render(store).splitlines()
