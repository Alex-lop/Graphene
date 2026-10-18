"""Reading the plan's store into the cockpit's model: one look, once a second.

`read` is a pure function of the store and the last model shown: what the plan says (a task a leaf, its
state as a person reads it, what it waits on, what it is for), what the person still has selected, and the
news they were last told survive from one look to the next. The screens never see the store.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from pathlib import Path

from .. import board_rows as BR
from .. import plan as P
from .. import settings as S
from .. import views as V
from .look import short
from .model import Model, Question, Task

# what a person reads a leaf as (plan.reads), and the state the cockpit draws it in
STATE = {
    "done": "done", "running": "running", "review": "review", "came back": "came back",
    "proposed": "proposed", "ready": "ready", "waiting": "waiting", "yours": "yours",
    "to fill in": "waiting",
}  # fmt: skip
FOLD_AFTER = 8  # more finished tasks than this, and the rows keep the latest few: the rest are counted
KEEP_DONE = 4
FILES_EVERY = 30.0  # seconds between looks at what git tracks: a big repository's list is not free


def looker(root: Path, open_store: Callable) -> Callable[[Model | None], Model]:
    """The function `Cockpit` is given: the model now, from the store, keeping what the person has chosen.
    A store too busy to open leaves the last model as it was, with a word on the news."""
    import sqlite3

    def look(previous: Model | None) -> Model:
        try:
            with open_store() as store:
                return read(store, root, previous)
        except (sqlite3.Error, OSError) as no:
            model = previous or Model("the plan's store did not open")
            model.say(f"✗ the plan's store did not open ({no}); the screen is as it was")
            return model

    return look


def read(store, root: Path, previous: Model | None = None, now: float | None = None) -> Model:
    now = time.time() if now is None else now
    nodes, words, goal = V.inputs(store)
    by_id = {n.id: n for n in nodes}
    kids = P.kids(nodes, drawn=True)
    m = Model(goal, "plan")
    m.clock = now
    if previous is not None:  # what is the person's survives a look: the selection, the lens, the news
        m.selected, m.lens, m.feed, m.names = previous.selected, previous.lens, previous.feed, previous.names
        m.files, m.files_at = previous.files, previous.files_at
    if not m.files or now - m.files_at > FILES_EVERY:
        m.files, m.files_at = P.tracked(root), now
    m.protected = S.protected(store) + S.readonly(store)
    leaves = [n for n in nodes if not kids.get(n.id)]
    keep = {n.id for n in leaves}
    for n in leaves:
        above = P.above(n, by_id)
        m.tasks[n.id] = Task(
            n.id,
            short(n.title),
            STATE.get(words.get(n.id, ""), "waiting"),
            list(n.scope),
            [x for x in n.needs if x in keep],
            full=n.title,
            why=" › ".join(short(a.title) for a in reversed(above)),
        )
    fold_done(m, by_id)
    m.questions = [question_of(item) for item in BR.read(store).open]
    if m.selected not in {rid for _, rid in m.order()}:
        rows = m.order()
        m.selected = rows[0][1] if rows else ""
    return m


def fold_done(m: Model, by_id: dict[str, P.Node]) -> None:
    """The cockpit shows what is alive: when many tasks are finished, the latest few stay and the rest
    are a count."""
    done = [t for t in m.tasks.values() if t.state == "done"]
    if len(done) <= FOLD_AFTER:
        return
    latest = sorted(done, key=lambda t: by_id[t.id].finished_at or "")[-KEEP_DONE:]
    for t in done:
        if t not in latest:
            m.tasks.pop(t.id)
            m.folded_done += 1


def question_of(item: dict) -> Question:
    """A board item the person has not settled, as a row: its words, the default `y` takes (an assumption's
    is "confirm", a risk's "noted"), and the other options, numbered as `graphene board pick` numbers them."""
    default = item["default"] or BR.YES[item["kind"]].split(" ", 1)[1]
    return Question(
        item["id"], item["text"], default, [o["text"] for o in item["options"]], item.get("about") or "",
        item["kind"],
    )  # fmt: skip
