"""`graphene auto`: the goal, the envelope and the rounds (auto.py does the work)."""

from __future__ import annotations

import typer

from . import auto as AUTO
from . import plan as P
from . import settings as S


def register(cli: typer.Typer, root, open_store, fail) -> None:
    @cli.command("auto")
    def auto_(
        goal: str = typer.Argument(None, help="What you want, in a sentence; left out, the plan goes on."),
        budget: float = typer.Option(
            None, "--budget", min=0, help="Dollars the runs may spend while auto is on."
        ),
        tasks: int = typer.Option(
            None, "--tasks", min=1, help="Tasks the envelope may accept for you, all told."
        ),
        rounds: int = typer.Option(None, "--rounds", min=0, help="Fix rounds after the goal's check fails."),
        forks: int = typer.Option(
            None, "--forks", min=1, max=8, help="Agents at once on every task; its check keeps one."
        ),
        parallel: int = typer.Option(4, "--parallel", help="How many tasks run at once."),
        check: str = typer.Option(None, "--check", help="The goal's own check, run once every task landed."),
        planner: str = typer.Option(
            None, "--planner", help="This planner, not init's: claude, codex, nemotron or a command."
        ),
        withs: list[str] = typer.Option(
            None, "--with", help="This executor, not init's; --with again mixes forks."
        ),
        attempts: int = typer.Option(
            3, "--attempts", min=1, help="Attempts a task gets before it comes back."
        ),
    ) -> None:
        """Plan a goal, run it and fix it inside your envelope, hands off.

        The planner's tree is accepted when it fits the envelope; what passes lands, the goal's check
        runs, and a red one is planned again."""
        who = P.caller()
        if not who.person:
            fail(f"`graphene auto` is the person's: it turns auto on and accepts for them (this call comes "
                 f"from {who.name}). An agent proposes: graphene plan propose -", 1)  # fmt: skip
        r = root()
        withs = [w for w in withs or [] if w.strip()]
        if len(withs) > P.FORKS[-1]:
            fail(f"--with at most {P.FORKS[-1]} times: each is a fork", 2)
        files = P.tracked(r)  # before the plan's write lock, never under it
        given = {"auto": "on", "budget": "" if budget is None else f"{budget}", "tasks": "" if tasks is None
                 else str(tasks), "rounds": "" if rounds is None else str(rounds)}  # fmt: skip
        given = {k: v for k, v in given.items() if v or k == "auto"}  # a flag left out keeps the setting
        if forks is not None:
            given["forks"] = str(forks)
        try:
            with open_store(r) as store:
                S.set_some(store, who, files, **given)  # one `settings` row: the envelope, the person's
            code = AUTO.drive(open_store, r, goal, typer.echo, planner, withs, parallel, forks, check,
                              attempts)  # fmt: skip
        except P.Refused as no:
            fail(str(no), 1)
        if line := P.where_said(r):
            typer.echo(line, err=True)
        raise typer.Exit(code)
