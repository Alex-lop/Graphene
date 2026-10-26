"""The settings a person states once: the standing conditions (protected paths no scope may include,
read-only globs, what the planner must never propose), how big a plan is, and whether every task waits
for their sign-off once its check passes. They live in the store's plan_meta; `graphene config` shows
them as text and edits them the way `plan edit` edits the plan: a line that cannot be read is refused
by its number, and the rest is written all or none.

plan.py imports this module inside functions only: this one imports plan."""

from __future__ import annotations

import json
import re

from graphene_map import plan as P

SIZES = ("auto", "finer", "coarser")
BOARDS = ("auto", "on")  # auto (unset, study 4): the board shows only for a question; on: every open item
REVIEWS = ("off", "every")  # off (unset): the check decides; every: a proven task waits for the sign-off
NOTIFY = ("on", "off")  # on (unset): graphene watch rings and notifies when something new needs the person
FORKS = tuple(str(n) for n in P.FORKS)  # 1 (unset): one agent a leaf; more: that many at once, one kept
AUTOS = ("off", "on")  # off (unset): every proposal waits for the person; on: one in the envelope is theirs
# one of a few; unset: the first
SCALARS = {"size": SIZES, "board": BOARDS, "review": REVIEWS, "notify": NOTIFY, "forks": FORKS, "auto": AUTOS}
# a number, or unset (the reader says what unset means): the envelope's dollars, tasks and fix rounds
NUMBERS = {"budget": "dollars, such as 2 or 0.50", "tasks": "a count", "rounds": "a count"}
GLOBS = ("protected", "readonly")  # a line of either holds globs, comma-separated; lines add up
HEAD = """\
# Graphene's settings. A line is `key: value`; a line starting with '#' is not read.
# protected: globs no scope may include      readonly: globs no leaf may write
# never: one thing the planner must never propose, a line each
# size: auto, finer or coarser (how big a plan the planner proposes)
# board: auto (while a question, or an agent's note, is open) or on (every open item waits on you)
# review: off (the check decides) or every (a proven task waits for your sign-off before it lands)
# notify: on (graphene watch rings, and a terminal that shows them notifies, when something needs you) or off
# forks: 1 to 8 agents at once on every leaf, each in its own copy; the leaf's check keeps one
# auto: off (every proposal waits for you) or on (one that fits the envelope below is accepted at once)
# budget: dollars the runs Graphene starts on its own may spend while auto is on (unset: no cap)
# tasks: how many tasks the envelope may accept for you, all told, since auto went on (unset: 12)
# rounds: fix rounds `graphene auto` takes after the goal's check fails (unset: 2)
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
    """auto (unset): the screen and the plan show the board only while a question on it is open; what
    else is open takes its default at accept. on: they show every open item. Unset is auto by study 4
    (dev/test/results-2026-09-29-board.md): the board cost more than the outline on 3 of 4 tasks."""
    return store.meta("settings:board") or "auto"


def review(store) -> str:
    """off (unset): the check decides; a task whose check passes is done, and lands, unless it asks for a
    sign-off of its own (`signoff: yes`). every: each one waits in review instead, for the person's
    sign-off (⏎ in graphene watch, `graphene node signoff`), which lands it. `plan.finish` reads it as a
    task passes, so it holds the tasks proposed before it was said too."""
    return store.meta("settings:review") or "off"


def notify(store) -> str:
    """on (unset): when something new needs the person, graphene watch rings the terminal's bell and sends a
    desktop notification saying what; off: it stays quiet."""
    return store.meta("settings:notify") or "on"


def forks(store) -> int:
    """1 (unset): one agent takes a leaf. More: `graphene run` forks every leaf that says nothing itself
    (`forks:` in the plan) and that the run's own --forks does not say, that many agents at once, each
    in its own copy, and the leaf's check keeps one."""
    return int(store.meta("settings:forks") or FORKS[0])


# The envelope: what `graphene auto` and an agent's proposals may do without the person, set once by them.
# Readers only here; `graphene config` and `graphene auto` write them: settings:auto, :budget, :tasks,
# :rounds.


def auto(store) -> str:
    """off (unset): every proposal waits for the person. on: one inside the envelope is accepted at once."""
    return store.meta("settings:auto") or "off"


def budget(store) -> float | None:
    """Dollars the runs Graphene starts on its own may spend while the envelope is in force; None: unset."""
    said = store.meta("settings:budget")
    return float(said) if said else None


def tasks(store) -> int | None:
    """Leaves the envelope may accept on the person's behalf, all told; None: unset."""
    said = store.meta("settings:tasks")
    return int(said) if said else None


def rounds(store) -> int:
    """Fix rounds `graphene auto` may take after the goal's check fails (2 unset)."""
    return int(store.meta("settings:rounds") or 2)


def auto_since(store) -> str | None:
    """When auto went on: the timestamp of the settings row that turned it on (the latest one), so that
    what the envelope accepted and spent is counted from there. None while it is off; "" when it is on
    and no row says since when (every row counts)."""
    if auto(store) != "on":
        return None
    rows = [r for r in store.node_log("*", ("settings",))
            if ((r["detail"] or {}).get("changed") or {}).get("auto", [None, None])[1] == "on"]  # fmt: skip
    return rows[-1]["timestamp"] if rows else ""


def set_some(store, who: P.Caller, files: list[str] | None = None, **values: str) -> list[str]:
    """`graphene config set KEY VALUE`, and what `graphene auto` was told: the named settings changed and
    the rest kept, through ``apply`` (person-only, one `settings` row). An empty value clears its key; a
    key with several lines (protected, readonly, never) is replaced by the one line given."""
    lines = [line for line in render(store).splitlines() if line and not line.startswith("#")]
    kept = [line for line in lines if line.partition(":")[0].strip() not in values]
    new = [f"{key}: {value}" for key, value in values.items() if str(value).strip()]
    return apply(store, "\n".join([*kept, *new]) + "\n", who, None, files)


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
        f"# plan first: {P.plan_first(store)} (graphene plan first on|auto|off)",
        *([f"# answered: readonly {', '.join(chosen)} (plan undo takes it back)"]
          if chosen else []),  # fmt: skip
    ]


def lines_for_screen(store) -> list[str]:
    """What `?` in graphene watch shows under the keys: every setting, a line each, then how to change
    them; review once it is every (off is the check deciding, as before there was a setting). The key's
    whereabouts are left to `graphene config`: a screen never asks the keychain."""
    said = [line.removeprefix("# ") for line in elsewhere(store)]
    shown = ("#", "notify:")  # notify is the cockpit's bell: this screen has none
    lines = [line for line in render(store).splitlines() if line and not line.startswith(shown)]
    lines = [line for line in lines if line not in ("review: off", "forks: 1", "auto: off")]
    one = [line for line in lines if line.partition(":")[0] in SCALARS]  # one line for the one-value keys
    said += [line for line in lines if line not in one] + [" · ".join(one)]
    return [*said, "graphene config edit changes them"]


def render(store) -> str:
    out = [HEAD.rstrip("\n"), "# In force too, each changed by the command it names (not by this text):",
           *elsewhere(store), ""]  # fmt: skip
    out += [f"{key}: {', '.join(_list(store, key))}" for key in GLOBS if _list(store, key)]
    out += [f"never: {n}" for n in never(store)]
    out.append(f"auto: {auto(store)}")  # the envelope: its numbers only once said, as its readers default
    out += [f"{key}: {store.meta(f'settings:{key}')}" for key in NUMBERS if store.meta(f"settings:{key}")]
    out.append(f"notify: {notify(store)}")
    out.append(f"size: {size(store)}")
    out.append(f"board: {board(store)}")
    out.append(f"review: {review(store)}")
    out.append(f"forks: {forks(store)}")
    return "\n".join(out) + "\n"


def _number(no: int, key: str, value: str) -> str:
    """A number as the envelope stores it: dollars with their cents, a count whole, neither negative."""
    try:
        n = float(value) if key == "budget" else int(value)
    except ValueError:
        raise P.Refused(f"line {no}: {key} is {NUMBERS[key]}, not {value!r}") from None
    if n < 0 or n != n:  # nan is a number to float()
        raise P.Refused(f"line {no}: {key} is {NUMBERS[key]}, not {value!r}")
    return f"{n:.2f}" if key == "budget" else str(n)


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
        if not colon or key not in (*got, *SCALARS, *NUMBERS):
            raise P.Refused(
                f"line {no}: {body[:40]!r} is not a setting; the keys are protected, readonly, never, size, "
                "board, review, notify, forks, auto, budget, tasks, rounds"
            )
        if key in SCALARS or key in NUMBERS:
            if key in SCALARS and value not in SCALARS[key]:
                *rest, last = SCALARS[key]
                raise P.Refused(f"line {no}: {key} is {', '.join(rest)} or {last}, not {value!r}")
            if key in NUMBERS:
                value = _number(no, key, value)
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
        was = {k: _list(store, k) for k in got}
        was |= {"size": size(store), "board": board(store), "review": review(store), "notify": notify(store),
                "forks": str(forks(store)), "auto": auto(store)}  # fmt: skip
        was |= {k: store.meta(f"settings:{k}") for k in NUMBERS}
        for key, values in got.items():
            store.set_meta(f"settings:{key}", json.dumps(values) if values else None)
        for key, values in SCALARS.items():  # unset is the first value; stored only when it is another
            value = said.get(key, (0, values[0]))[1]
            store.set_meta(f"settings:{key}", value if value != values[0] else None)
        for key in NUMBERS:  # unset is None: the reader says what that means
            store.set_meta(f"settings:{key}", said[key][1] if key in said else None)
        now = {**got, **{k: said[k][1] if k in said else v[0] for k, v in SCALARS.items()}}
        now |= {k: said[k][1] if k in said else None for k in NUMBERS}
        changed = {k: [was[k], now[k]] for k in now if was[k] != now[k]}
        if changed:
            store.log_node("*", P._now(), "settings", who.label, None, None, {"changed": changed})
    return render(store).splitlines()
