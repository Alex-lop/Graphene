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
BOARDS = ("on", "auto")  # on: every open item is shown; auto: the board shows only for a question
SCALARS = {"size": SIZES, "board": BOARDS}  # a key with one value of a few, the first when unset
GLOBS = ("protected", "readonly")  # a line of either holds globs, comma-separated; lines add up
HEAD = """\
# Graphene's settings. A line is `key: value`; a line starting with '#' is not read.
# protected: globs no scope may include      readonly: globs no leaf may write
# never: one thing the planner must never propose, a line each
# size: auto, finer or coarser (how big a plan the planner proposes)
# board: on (every open item waits on you) or auto (only while a question is open)
"""


def _list(store, key: str) -> list[str]:
    return json.loads(store.meta(f"settings:{key}") or "[]")


def protected(store) -> list[str]:
    return _list(store, "protected")


def readonly(store) -> list[str]:
    """The read-only globs: the person's in `graphene config`, then the ones they chose on the board
    (`then: condition GLOB`), which `plan undo` takes back with the answer."""
    from graphene_map import board as B

    return list(dict.fromkeys([*_list(store, "readonly"), *B.conditions(store)]))


def never(store) -> list[str]:
    return _list(store, "never")


def size(store) -> str:
    return store.meta("settings:size") or "auto"


def board(store) -> str:
    """on (unset): the screen and the plan show every open item on the board. auto: they show the
    board only while a question on it is open; what else is open takes its default at accept."""
    return store.meta("settings:board") or "on"


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
    from graphene_map import board as B

    chosen = B.conditions(store)
    return [
        f"# planner: {store.meta('planner') or 'none chosen'} (graphene init --planner)",
        f"# executor: {store.meta('executor') or 'none chosen'} (graphene init --executor)",
        f"# plan first: {'on' if P.plan_first(store) else 'off'} (graphene plan first on|off)",
        *([f"# board: readonly {', '.join(chosen)} (plan undo takes it back)"]
          if chosen else []),  # fmt: skip
    ]


def for_screen(store) -> dict:
    """The settings as the page's plan carries them, for the root row of the board and the graph."""
    return {"protected": protected(store), "readonly": readonly(store), "never": never(store),
            "size": size(store)}  # fmt: skip


def lines_for_screen(store) -> list[str]:
    """What `?` in graphene watch shows under the keys: every setting, a line each, then how to change
    them. The key's whereabouts are left to `graphene config`: a screen never asks the keychain."""
    said = [line.removeprefix("# ") for line in elsewhere(store)]
    lines = [line for line in render(store).splitlines() if line and not line.startswith("#")]
    one = [line for line in lines if line.partition(":")[0] in SCALARS]  # one line for the one-value keys
    said += [line for line in lines if line not in one] + [" · ".join(one)]
    return [*said, "graphene config edit changes them"]


def render(store) -> str:
    out = [HEAD.rstrip("\n"), "# In force too, each changed by the command it names (not by this text):",
           *elsewhere(store), ""]  # fmt: skip
    out += [f"{key}: {', '.join(_list(store, key))}" for key in GLOBS if _list(store, key)]
    out += [f"never: {n}" for n in never(store)]
    out.append(f"size: {size(store)}")
    out.append(f"board: {board(store)}")
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


def apply(
    store, text: str, who: P.Caller, opened: str | None = None, files: list[str] | None = None
) -> list[str]:
    """Read the whole text, then write every setting it names (one left out is cleared) in one
    claim; a line that cannot be read refuses all of it. Person-only. ``opened``: the text the editor
    was opened on; when the settings no longer render as it, someone else changed them meanwhile and
    the save is refused, never written over theirs. ``files``: what git tracks, so a glob that differs
    from a path only in case is refused, as a scope is. Returns the text as stored."""
    P._person_only(who, "changing Graphene's settings")
    got: dict[str, list[str]] = {"protected": [], "readonly": [], "never": []}
    said: dict[str, tuple[int, str]] = {}  # a one-value key: (its line, its value)
    for no, line in enumerate(text.splitlines(), 1):
        body = line.strip()
        if not body or body.startswith("#"):
            continue
        key, colon, value = body.partition(":")
        key, value = key.strip(), value.strip()
        if not colon or key not in (*got, *SCALARS):
            raise P.Refused(
                f"line {no}: {body[:40]!r} is not a setting; the keys are protected, readonly, never, size, "
                "board"
            )
        if key in SCALARS:
            if value not in SCALARS[key]:
                *rest, last = SCALARS[key]
                raise P.Refused(f"line {no}: {key} is {', '.join(rest)} or {last}, not {value!r}")
            if key in said:
                raise P.Refused(f"line {no}: {key} is said on line {said[key][0]} already")
            said[key] = (no, value)
        elif key == "never":
            if not value:
                raise P.Refused(f"line {no}: never: needs what the planner must never propose")
            got["never"].append(value)
        else:
            globs = [g.strip() for g in value.split(",")]
            if not all(globs):
                raise P.Refused(f"line {no}: {key}: needs globs, comma-separated, none empty")
            got[key] += [_glob(no, g) for g in globs if _glob(no, g) not in got[key]]
            wrong = P.miscased([_glob(no, g) for g in globs], files or [])
            if wrong:
                raise P.Refused(f"line {no}: {wrong}; spell it as git does")
    if not (said or any(got.values())):  # an emptied text is a slip (an editor's crash), as in plan edit
        raise P.Refused("nothing is applied from a text with no setting in it; to clear them all, save "
                        "`size: auto` alone")  # fmt: skip
    with store.claim():
        now_said = render(store)
        if opened is not None and now_said != opened:
            now = "; ".join(line for line in now_said.splitlines() if not line.startswith("#"))
            raise P.Refused(f"the settings were changed by someone else since this text was opened; they now "
                            f"say: {now}. Keep what you want of theirs and save again")  # fmt: skip
        was = {k: _list(store, k) for k in got} | {"size": size(store), "board": board(store)}
        for key, values in got.items():
            store.set_meta(f"settings:{key}", json.dumps(values) if values else None)
        for key, values in SCALARS.items():  # unset is the first value; stored only when it is another
            value = said.get(key, (0, values[0]))[1]
            store.set_meta(f"settings:{key}", value if value != values[0] else None)
        now = {**got, **{k: said[k][1] if k in said else v[0] for k, v in SCALARS.items()}}
        changed = {k: [was[k], now[k]] for k in now if was[k] != now[k]}
        if changed:
            store.log_node("*", P._now(), "settings", who.label, None, None, {"changed": changed})
    return render(store).splitlines()
