"""`graphene config` and `graphene config edit`: the settings a person states once, shown as text and
edited in their $EDITOR the way `plan edit` edits the plan (settings.py reads and writes them)."""

from __future__ import annotations

import sys

import typer

from . import plan as P
from . import plan_text as T
from . import settings as S


def register(cli: typer.Typer, root, open_store, fail):
    config_cli = typer.Typer(help="Graphene's settings: shown, and edited by the person.")
    cli.add_typer(config_cli, name="config")

    @config_cli.callback(invoke_without_command=True)
    def show(ctx: typer.Context) -> None:
        """Print the settings as `graphene config edit` opens them."""
        if ctx.invoked_subcommand is None:
            with open_store(root()) as store:
                typer.echo(S.render(store), nl=False)

    @config_cli.command()
    def edit() -> None:
        """Edit the settings in your editor (a person only); the save is applied all or none. A line
        that cannot be read is refused by its number: at a terminal the text goes back to the editor
        with the reason under that line; with none, it is kept and nothing is applied. A text with no
        setting in it is refused. `graphene plan undo` does not reach the settings: each change is
        logged with what was there before, and each line added or removed is printed."""
        who = P.caller()
        try:
            P._person_only(who, "changing Graphene's settings")
        except P.Refused as no:
            fail(str(no), 1)
        with open_store(root()) as store:
            shown = opened = S.render(store)
        path = T.edit_path(root(), "config")
        path.write_text(shown, encoding="utf-8")
        first = True
        while True:
            try:
                code = T.run_editor(path)
            except P.Refused as no:
                path.unlink(missing_ok=True)
                fail(str(no), 1)
            saved = path.read_text(encoding="utf-8") if path.exists() else None
            if saved is None:
                fail(f"{path} is gone; nothing was applied", 1)
            if code != 0:
                fail(f"the editor exited with {code}; nothing was applied (your text is in {path})", 1)
            if saved == shown:
                if first:
                    path.unlink(missing_ok=True)
                    typer.echo("nothing changed")
                    return
                fail(f"nothing was applied; your text is kept in {path}", 1)
            try:
                with open_store(root()) as store:
                    before = S.render(store)
                    after = S.apply(store, saved, who, opened)
            except P.Refused as no:
                if not sys.stdin.isatty():
                    fail(f"{no}. Nothing was applied; your text is kept in {path}", 1)
                if "changed by someone else" in str(no):  # the next save is judged against what they say now
                    with open_store(root()) as store:
                        opened = S.render(store)
                shown = T._annotated(saved, str(no))
                path.write_text(shown, encoding="utf-8")
                first = False
                continue
            path.unlink(missing_ok=True)
            was, now = before.splitlines(), after
            for line in [line for line in now if line not in was and not line.startswith("#")]:
                typer.echo(line)
            for line in [line for line in was if line not in now and not line.startswith("#")]:
                typer.echo(f"removed: {line}")
            if "\n".join(after) + "\n" == before:
                typer.echo("nothing changed")
            return
