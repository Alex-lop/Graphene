"""`graphene talk`: the person talks with the planner about a node of the tree, and sees what changed.

Each is `graphene ask --about` with its own words for the planner (`ask.talking`), so every planner
answers it (Claude Code, Codex, Nemotron), and each answer lands in the one store, never only printed:

    why ID            the planner's answer is a note on the board about ID, by the planner, to keep
                      (take) or dismiss (drop)
    split ID          `graphene node split`: leaves under ID, proposed
    merge ID ID…      one proposed leaf M for all of them, and a question on the board whose default
                      drops them (`then: drop`) and whose option, keep them apart, drops M
    another ID        another way, proposed beside ID, and a question on the board: its default keeps
                      ID and drops the other way, its option takes the other way and drops ID

The question is put up by Graphene in the planner's name, since it asks about the planner's proposal,
so its effects are always right whatever the planner wrote. Answering it is one `graphene board` act,
and one `graphene plan undo`.

What changed since the person last looked: `graphene plan seen` keeps a mark (plan_meta `seen:NAME`,
the last row of the plan's log they have seen); `graphene plan changes` lists what anyone else changed
after it, and the screen marks those rows. Only the person moves the mark, and only by asking to: a
planner's revision cannot slip past. The board's every act is a row of the log, so the mark covers it.
"""

from __future__ import annotations

import json

import typer

from . import ask as A
from . import board as B
from . import plan as P

# a row of the plan's log that changed the plan, and what it did, in plain words
DID = {
    "added": "added", "proposed": "proposed", "accepted": "accepted", "edited": "edited",
    "dropped": "dropped", "started": "started", "finished": "done", "overruled": "done, overruled",
    "released": "came back", "reopened": "reopened", "signed_off": "signed off",
    "rolled_up": "done, with its leaves", "archived": "archived", "undone": "undone", "landed": "landed",
    "goal": "the goal said", "goal_proposed": "a goal proposed", "reordered": "reordered",
    "board": "the board",
}  # fmt: skip
TODO = ("running", "review", "done")  # a merge or another way is for work still to do


def key(person: str) -> str:
    return f"seen:{person}"


def mine(actor: str | None, person: str) -> bool:
    """Is it the person's own act (`alex`, or `alex (no terminal)`)? They saw it as they made it."""
    return (actor or "").split(" (")[0] == person


def since(store, person: str) -> list[dict] | None:
    """What anyone but the person changed in the plan after their mark, oldest first; None: no mark."""
    mark = store.meta(key(person))
    if mark is None:
        return None
    kinds = ", ".join("?" * len(DID))  # from the mark on, not the whole log: the screen asks each second
    rows = store.conn.execute(
        f"SELECT * FROM node_log WHERE id > ? AND kind IN ({kinds}) ORDER BY id", (int(mark), *DID)
    ).fetchall()
    found = [{**dict(r), "detail": json.loads(r["detail"]) if r["detail"] else {}} for r in rows]
    return [e for e in found if not mine(e["actor"], person)]


def marks(store, person: str) -> tuple[dict[str, str], int]:
    """Each node changed since the mark, `+` when it was added since and `~` when it changed, and how
    many things changed (nodes, board items, the goal) for the bottom line."""
    out: dict[str, str] = {}
    things: set[str] = set()
    for e in since(store, person) or []:
        node = e["node_id"]
        if e["kind"] == "board":
            things.add(f"board:{e['detail'].get('item')}")
        elif node == "*":
            things.add(e["kind"])
        else:
            things.add(node)
            out[node] = "+" if e["kind"] in ("added", "proposed") or out.get(node) == "+" else "~"
    return out, len(things)


def seen(store, who: P.Caller) -> int:
    """Move the person's mark to where the plan's log is now; returns how many things it marks seen."""
    if not who.person:
        raise P.Refused(
            f"the mark is the person's, not {who.name}'s: moved by an agent, it would hide a change from them"
        )
    _, count = marks(store, who.name)
    last = store.conn.execute("SELECT COALESCE(MAX(id), 0) FROM node_log").fetchone()[0]
    store.set_meta(key(who.name), str(last))
    return count


def changes(store, person: str) -> list[str]:
    """`graphene plan changes`: every change after the mark, a line each, in plain words, by whom."""
    found = since(store, person)
    if found is None:
        return [
            "no mark yet: `graphene plan seen` (m on the screen) marks the plan as you have seen it; what "
            "anyone changes after it is listed here and marked on the screen"
        ]
    if not found:
        return ["nothing changed since you last looked"]
    _, count = marks(store, person)
    out = [f"{count} changed since you last looked (graphene plan seen marks them seen):"]
    for e in found:
        said = e["detail"]
        what = DID[e["kind"]]
        if e["kind"] == "edited":
            what += f" {', '.join(said.get('changed') or {})}"
        subject = "the plan" if e["node_id"] == "*" else e["node_id"]
        note = said.get("note") or (
            P.get(store, e["node_id"]).title if e["kind"] in ("added", "proposed") else ""
        )
        out.append(
            f"  {e['timestamp'][11:16]}  {subject}: {what} by {e['actor']}" + (f": {note}" if note else "")
        )
    return out


# -- talking --------------------------------------------------------------------------------------


def _todo(store, ids: list[str], what: str) -> list[P.Node]:
    everything = P.nodes(store)
    found = [P.get(store, i) for i in ids]
    for n in found:
        if n.state in P.GONE or P.reads(n, everything) in TODO:
            raise P.Refused(f"{n.id} is {P.reads(n, everything)}: {what} is for work still to do")
    return found


def _new(store, said) -> list[P.Node]:
    """The tops of what the planner proposed: a new node whose parent is not new too."""
    fresh = list(dict.fromkeys(getattr(said, "ids", [])))
    tops = [P.get(store, i) for i in fresh if P.get(store, i).parent not in fresh]
    if not tops:
        raise P.Refused("the planner proposed nothing new; nothing was put on the board")
    return tops


def _asker(template: str) -> P.Caller:
    return P.Caller(f"planner:{A.label(template)}", False)


def why(store, root, node_id: str, template: str, say=print) -> list[dict]:
    """The planner says why a node is there, as a note on the board about it."""
    P.get(store, node_id)
    said = A.ask(store, root, f"why is {node_id} in the plan?", template, node_id, say=say,
                 talk=A.talking(store, "why", [node_id]))  # fmt: skip
    put = [line.split(":", 1)[0].removeprefix("put up ") for line in said if line.startswith("put up ")]
    notes = [it for it in (B.get(store, i) for i in put) if it["kind"] == "note"]
    if not notes:
        raise P.Refused("the planner put no note on the board; what it said is above")
    return notes


def merge(store, root, ids: list[str], template: str, say=print) -> tuple[list[str], dict]:
    """One proposed leaf for several, and the question: merge them into it?"""
    if len(set(ids)) < 2:
        raise P.Refused("merge takes two leaves or more: graphene talk merge ID ID… (on the screen, V)")
    found = _todo(store, ids, "merge")
    under = P.kids(P.nodes(store), drawn=True)
    subgoals = [n.id for n in found if under.get(n.id)]
    if subgoals:
        raise P.Refused(f"{', '.join(subgoals)} has leaves under it: merge takes leaves")
    said = A.ask(store, root, f"merge {' and '.join(ids)} into one leaf", template, ids[0], say=say,
                 talk=A.talking(store, "merge", ids))  # fmt: skip
    made = _new(store, said)
    order, left = [], list(found)  # a leaf that needs another of them drops first, or that drop is refused
    while left:
        free = [n for n in left if not any(n.id in m.needs for m in left)]
        order.append((free or left)[0])
        left.remove(order[-1])
    names = ", ".join(n.id for n in made)
    return said, B.add(
        store, "question", f"merge {' and '.join(ids)} into {names}?", _asker(template),
        default=f"yes: {names} does all of it", then=[f"drop {n.id}" for n in order],
        options=[{"text": "keep them apart", "then": [f"drop {n.id}" for n in made]}], about=made[0].id,
    )  # fmt: skip


def another(store, root, node_id: str, template: str, say=print) -> tuple[list[str], dict]:
    """Another way, proposed beside the node, and the question: which way?"""
    _todo(store, [node_id], "another way")
    said = A.ask(store, root, f"another way for {node_id}", template, node_id, say=say,
                 talk=A.talking(store, "another", [node_id]))  # fmt: skip
    made = _new(store, said)
    names = ", ".join(n.id for n in made)
    return said, B.add(
        store, "question", f"which way for {node_id}: as planned, or {names}?", _asker(template),
        default=f"{node_id} as planned", then=[f"drop {n.id}" for n in made],
        options=[{"text": f"{names}: {made[0].title}", "then": [f"drop {node_id}"]}], about=made[0].id,
    )  # fmt: skip


# -- the commands ---------------------------------------------------------------------------------


def register(cli: typer.Typer, root, open_store, fail) -> None:
    out = typer.echo
    talk_cli = typer.Typer(
        help="Talk with the planner about a node: why it is there, split it, merge it with others, "
        "another way. Every answer lands in the plan or on the board, for you to keep or drop."
    )
    cli.add_typer(talk_cli, name="talk")
    WITH = typer.Option(
        None, "--with", help="The planner. Default: the one `graphene init` chose, else claude."
    )

    def asked(what):
        who = P.caller()
        if not who.person:
            fail("talking with the planner is the person's: it starts an agent, and spends", 1)
        with open_store(root()) as store:
            try:
                what(store)
            except P.Refused as no:
                fail(str(no), 1)
        typer.echo(f"  (the plan of {P.where(root())})", err=True)

    def planner(store, executor: str | None) -> str:
        return A.named(executor or store.meta("planner"))

    def question(said: list[str], item: dict) -> None:
        """What the planner proposed, then the question, its last line (the screen's bottom line)."""
        for line in said:
            out(line)
        out(f"  graphene board take {item['id']}: {item['default']}")
        for k, option in enumerate(item["options"], 1):
            out(f"  graphene board pick {item['id']} {k}: {option['text']}")
        out(f"the board asks ({item['id']}): {item['text']}")

    @talk_cli.command("why")
    def why_(node_id: str = typer.Argument(...), executor: str = WITH) -> None:
        """The planner says why the node is there: a note on the board about it (graphene board drop
        dismisses it)."""

        def go(store):
            for note in why(store, root(), node_id, planner(store, executor), out):
                out(f"put up {note['id']} on the board: graphene board drop {note['id']} dismisses it, take "
                    "tells it to the executor")  # fmt: skip
                out(f"the planner on {node_id}: {note['text']}")

        asked(go)

    @talk_cli.command("split")
    def split_(node_id: str = typer.Argument(...), executor: str = WITH) -> None:
        """The planner cuts it into smaller leaves under it, proposed (graphene node split)."""

        def go(store):
            said = A.ask(store, root(), f"split {node_id} into smaller leaves", planner(store, executor),
                         node_id, True, out)  # fmt: skip
            for line in said:
                out(line)

        asked(go)

    @talk_cli.command("merge")
    def merge_(
        ids: list[str] = typer.Argument(..., help="Two leaves or more."), executor: str = WITH
    ) -> None:
        """The planner proposes one leaf for all of them; the board asks you whether to merge."""
        asked(lambda store: question(*merge(store, root(), ids, planner(store, executor), out)))

    @talk_cli.command("another")
    def another_(node_id: str = typer.Argument(...), executor: str = WITH) -> None:
        """The planner proposes another way to reach what the node is for; the board asks you which."""
        asked(lambda store: question(*another(store, root(), node_id, planner(store, executor), out)))

    plan_cli = next(g.typer_instance for g in cli.registered_groups if g.name == "plan")

    @plan_cli.command("changes")
    def changes_() -> None:
        """What anyone else changed in the plan since you last marked it seen: added, dropped, edited,
        the board, by whom."""
        with open_store(root()) as store:
            for line in changes(store, P.caller().name):
                out(line)

    @plan_cli.command("seen")
    def seen_() -> None:
        """Mark the plan as you have seen it: what anyone changes after this is marked on the screen
        (+ added, ~ changed) and listed by `graphene plan changes`. Only you move the mark."""
        with open_store(root()) as store:
            try:
                count = seen(store, P.caller())
            except P.Refused as no:
                fail(str(no), 1)
        plural = "s" if count != 1 else ""
        out(f"{count} change{plural} marked as seen; what anyone else changes next is marked")
