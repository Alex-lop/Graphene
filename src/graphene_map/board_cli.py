"""`graphene board`: the board at the command line, one command for each act, so every key a screen
gives it is a command a person could type."""

from __future__ import annotations

import json

import typer
from rich.cells import cell_len, chop_cells

from . import board as B
from . import cover
from . import plan as P
from . import plan_text as T
from . import settings as S

EMPTY = (
    "the board is empty. The planner puts up what it would ask you (`graphene ask '…'`); "
    "you put up notes (`graphene board note '…'`)"
)
WIDE = 80  # the print is laid out to 80 columns, as `graphene plan`'s is
ACTS = "graphene board take|drop|park|unpark ID · pick ID N · answer ID TEXT · note TEXT"
LEFT = "left open, an item takes its default when you accept the plan"
FOLDED = ("settled", "dropped")  # what the short print counts and `--all` lists


def rows(store, everything: bool = False) -> list[str]:
    """The board as `graphene board` prints it: each group under its name, an item in the row
    grammar (glyph, words, id, the word its state reads as); what is open with its default and its
    options; last, the commands that answer. Only what answering needs: what is settled or dropped
    is counted in the first line, not listed, and no `then:` line is printed (``everything``, `--all`,
    lists them all, each settled item in one line)."""
    shown = B.groups(store)  # dropped too, last: gone from what executors are told, not from sight
    if all(name == "dropped" for name, _ in shown):  # nothing but what was dropped reads as empty
        return [EMPTY]
    count = {name: len(group) for name, group in shown}
    opened = sum(n for name, n in count.items() if name not in ("parked", *FOLDED))
    said = {k: f"{count[k]} {k}" for k in ("parked", *FOLDED) if k in count}
    head = ([f"{opened} open"] if opened else []) + list(said.values())  # never "0 open"
    out = [f"the board: {', '.join(head)}"]
    if not everything:
        shown = [(name, group) for name, group in shown if name not in FOLDED]
        if not shown:  # nothing waits on the person: the one line, and where the rest is
            return [f"{out[0]}; nothing waits on you (`graphene board --all` lists them)"]
    listed = [it for _, group in shown for it in group]
    # one row grammar, as `graphene plan` prints a node: glyph and words, id, state word. The id and the
    # state are whole (an id is what a command takes); the words take what is left of 80 columns, and
    # wrap under the row rather than being cut
    wid, ww = max(len(it["id"]) for it in listed), max(len(B.reads(it)) for it in listed)
    wt = min(48, max(cell_len(_words(it)) for it in listed) + 4, WIDE - 4 - wid - ww)
    for name, group in shown:
        out.append(name)
        for item in group:
            first, *rest = _wrap(_words(item), wt - 4)
            title = f"  {B.look(item)[0]} {first}"
            out.append(f"{T.pad(title, wt)}  {item['id'].ljust(wid)}  {B.reads(item)}".rstrip())
            out += [f"    {line}" for line in rest]
            if name == "dropped":
                continue
            if name == "settled":
                out += _hang("      → ", item["answer"]) if item.get("answer") else []
                out += [ln for line in item["became"] for ln in _hang("      ", _became(line))]
                continue
            effects = _then if everything else lambda _: []
            if item["default"] or (item["then"] and everything):
                out += [*_hang("      default: ", item["default"] or ""), *effects(item["then"])]
            for k, option in enumerate(item["options"], 1):
                out += [*_hang(f"      {k}: ", option["text"]), *effects(option["then"])]
            out += [f"      about {item['about']}"] if item.get("about") else []
    left = not everything and any(B.has_default(it) for it in listed)
    return [*out, ACTS, *([LEFT] if left else [])]


def _words(item: dict) -> str:
    """An item's words as its row shows them: an agent's note says whose it is."""
    return item["text"] + (f" · {item['by']}'s" if item["agent"] and item["kind"] == "note" else "")


def _wrap(text: str, wide: int) -> list[str]:
    """``text`` in lines of at most ``wide`` terminal cells, broken between words (a word longer than
    a line is cut where it must)."""
    lines, line = [], ""
    for word in text.split():
        for piece in chop_cells(word, wide):
            if line and cell_len(line) + 1 + cell_len(piece) > wide:
                lines.append(line)
                line = piece
            else:
                line = f"{line} {piece}" if line else piece
    return [*lines, line]


def _hang(head: str, text: str) -> list[str]:
    """``head`` and ``text`` wrapped to 80 columns, each line after the first under the text's start."""
    first, *rest = _wrap(text, WIDE - len(head))
    return [f"{head}{first}".rstrip(), *(" " * len(head) + line for line in rest)]


def _became(line: str) -> str:
    """What an answer did to the plan, or to what a leaf may write."""
    return f"changed: {line}"


def _then(effects: list[str]) -> list[str]:
    return [ln for line in effects for ln in _hang("         then: ", line)]


def register(cli: typer.Typer, root, open_store, fail) -> None:
    out = typer.echo
    board_cli = typer.Typer(
        help="The board: the planner's questions, assumptions, risks and leave-outs, and your notes.",
        invoke_without_command=True,
    )
    cli.add_typer(board_cli, name="board")

    def act(what: str, operation) -> None:
        """One act on the board, kept for `graphene plan undo` with everything its answer changed."""
        who = P.caller()
        files = P.tracked(root())  # asked before the plan's write lock is taken, never under it
        with open_store(root()) as store:
            try:
                with P.undoable(store, who, what):
                    item = operation(store, who, files)
            except P.Refused as no:
                fail(str(no), 1)
            # a condition is a read-only glob as a setting is: name the leaves it now covers, as config does
            covered = S.broken(store, files) if item["state"] in B.DECIDED and item.get("conditions") else []
        # one short line: the person just read the item, and chose the answer
        said = f": option {item['option']}" if item["state"] == "picked" else ""
        out(f"{B.reads(item)} {item['id']}{said}")
        for line in item["became"] if item["state"] in B.DECIDED else []:
            out(f"  {_became(line)}")
        if item["state"] == "answered" and item.get("then"):  # words carry no `then:`, a default does
            out(f"  your words go to executors as written and change no leaf; `graphene plan undo`, then "
                f"`graphene board take {item['id']}`, applies the default's change")  # fmt: skip
        for line in covered:
            out(line)
        for line in B.lifted(item):
            out(f"  {line}")
        typer.echo(f"  (the plan of {P.where(root())})", err=True)

    @board_cli.callback()
    def show(
        ctx: typer.Context,
        as_json: bool = typer.Option(False, "--json", help="Every item, in the order shown, as JSON."),
        everything: bool = typer.Option(
            False, "--all", help="List what is settled and dropped too, and every option's `then:` lines."
        ),
    ) -> None:
        """The board: open questions first with their defaults and options, then assumptions, risks,
        what would be left out and notes, then what is parked; what is settled is counted."""
        if ctx.invoked_subcommand:
            return
        with open_store(root()) as store:
            if as_json:
                items = [{**it, "reads": B.reads(it)} for _, group in B.groups(store) for it in group]
                out(json.dumps({"items": items, "conditions": B.conditions(store)}, indent=2))
                return
            for line in rows(store, everything):
                out(line)

    @board_cli.command()
    def take(item_id: str = typer.Argument(None, help="None: every open item that has a default.")) -> None:
        """Take the default: yes to a question's default, confirm an assumption, agree to a leave-out.
        With no id, every open item that has a default takes it, in one act."""
        if item_id:
            return act(f"board take {item_id}", lambda s, who, files: B.take(s, item_id, who, files))
        who, files = P.caller(), P.tracked(root())
        with open_store(root()) as store:
            try:
                if not who.person:
                    raise P.Refused(f"answering the board is the person's, not {who.name}'s")
                with P.undoable(store, who, "board take"):
                    taken = B.defaults(store, who, files)
            except P.Refused as no:
                fail(str(no), 1)
        out(B.took(taken) or "nothing open on the board has a default to take")
        typer.echo(f"  (the plan of {P.where(root())})", err=True)

    @board_cli.command()
    def pick(item_id: str = typer.Argument(...), option: int = typer.Argument(..., help="From 1.")) -> None:
        """Pick one of a question's options."""
        act(f"board pick {item_id} {option}", lambda s, who, files: B.pick(s, item_id, option, who, files))

    @board_cli.command()
    def drop(item_id: str = typer.Argument(...)) -> None:
        """Drop it: it is not told to anyone. An answer's read-only globs are lifted; what it changed in
        the tree stays (`graphene plan undo` takes an answer back with all of it)."""
        act(f"board drop {item_id}", lambda s, who, files: B.drop(s, item_id, who))

    @board_cli.command()
    def park(item_id: str = typer.Argument(...)) -> None:
        """Park it: not now; it stays on the board, told to nobody."""
        act(f"board park {item_id}", lambda s, who, files: B.park(s, item_id, who))

    @board_cli.command()
    def unpark(item_id: str = typer.Argument(...)) -> None:
        """Unpark it: it is open again, waiting on you."""
        act(f"board unpark {item_id}", lambda s, who, files: B.unpark(s, item_id, who))

    @board_cli.command()
    def answer(item_id: str = typer.Argument(...), words: list[str] = typer.Argument(...)) -> None:
        """Answer it in your own words."""
        act(f"board answer {item_id}", lambda s, who, files: B.answer(s, item_id, " ".join(words), who))

    @board_cli.command()
    def note(
        words: list[str] = typer.Argument(...),
        about: str = typer.Option(None, "--about", help="The node it is about; none is the whole plan."),
    ) -> None:
        """Put up a note. Yours is told to the executors as written; an agent's waits for you. With
        GRAPHENE_SHAPE=note, a model then finds the leaf it constrains, and the change is put up as an
        item whose default, taken, makes it."""
        act("board note", lambda s, who, files: B.note(s, " ".join(words), who, about))
        if "note" in cover.shaping() and P.caller().person:
            from . import note as N  # here, not above: it loads the model's client only when asked

            with open_store(root()) as store:  # routed outside the plan's write lock, as note.route asks
                item = N.to_board(store, root(), " ".join(words), say=out)
            if item is not None:
                out(f"put up {item['id']}: {item['text']}")
                out(f"  default: {item['default']}")
