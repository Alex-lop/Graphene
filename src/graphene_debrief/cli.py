"""Command-line entry point.

``graphene ingest hook`` runs on every agent event, so it takes a fast path that imports only
the standard library and the store; Typer and Rich are imported for every other command.
"""

import sys


def app() -> None:
    if sys.argv[1:3] == ["ingest", "hook"]:
        from .sources.claude_code import hook_main

        raise SystemExit(hook_main())
    build()()


def build():
    from pathlib import Path

    import typer
    from rich.console import Console
    from rich.table import Table

    from . import __version__
    from .sources.claude_code import backfill, ignore_store_dir, install_hooks, repo_root
    from .store import Store

    cli = typer.Typer(
        help="What your coding agent did, and why, grouped by what you asked for.",
        no_args_is_help=True,
        add_completion=False,
    )
    console = Console()

    def root() -> Path:
        return repo_root(Path.cwd())

    @cli.callback(invoke_without_command=True)
    def main(
        ctx: typer.Context,
        version: bool = typer.Option(False, "--version", help="Print the version and exit."),
    ):
        if version:
            console.print(f"graphene {__version__}")
            raise typer.Exit()
        if ctx.invoked_subcommand is None:
            console.print(ctx.get_help())
            raise typer.Exit()

    @cli.command()
    def init() -> None:
        """Install Claude Code hooks for this repo and ignore .graphene/."""
        r = root()
        try:
            added = install_hooks(r)
        except ValueError as exc:
            console.print(f"[red]cannot update .claude/settings.json:[/red] {exc}")
            raise typer.Exit(1) from None
        if added:
            console.print(f"hooks added to {r / '.claude' / 'settings.json'}: {', '.join(added)}")
        else:
            console.print("hooks already installed")
        if ignore_store_dir(r):
            console.print("added .graphene/ to .gitignore")
        Store.open(r).close()
        import shutil

        if shutil.which("graphene") is None:
            console.print(
                "[yellow]warning:[/yellow] `graphene` is not on PATH, so the hook will not run. "
                "Install it with `uv tool install graphene-debrief` (or `--editable .`)."
            )

    ingest = typer.Typer(help="Record what the agent did.", invoke_without_command=True)
    cli.add_typer(ingest, name="ingest")

    @ingest.callback()
    def ingest_main(
        ctx: typer.Context,
        do_backfill: bool = typer.Option(
            False, "--backfill", help="Load this repo's Claude Code transcripts."
        ),
        transcript: list[Path] = typer.Option(
            None, "--transcript", help="Backfill these transcript files only."
        ),
    ) -> None:
        if ctx.invoked_subcommand is not None:
            return
        if not do_backfill:
            console.print("nothing to do: pass --backfill, or let the hooks call `graphene ingest hook`")
            raise typer.Exit(1)
        r = root()
        with Store.open(r) as store:
            report = backfill(store, r, transcripts=transcript or None)
        console.print(
            f"added {len(report.added)}, refreshed {len(report.refreshed)}, "
            f"already present {len(report.skipped)}, other repos {len(report.other_repo)}"
        )
        for sid in report.added + report.refreshed:
            console.print(f"  {sid}")
        if report.skipped_records:
            kinds = ", ".join(f"{k} {v}" for k, v in sorted(report.skipped_records.items()))
            console.print(f"skipped record types: {kinds}")

    @ingest.command("hook")
    def ingest_hook() -> None:
        """Read one hook event from stdin (used by the installed hooks)."""
        from .sources.claude_code import hook_main

        raise typer.Exit(hook_main())

    @cli.command()
    def sessions() -> None:
        """List recorded sessions."""
        with Store.open(root()) as store:
            rows = store.sessions()
            table = Table("session", "source", "started", "ended", "prompts", "tool calls")
            for s in rows:
                table.add_row(
                    s.id,
                    s.source,
                    s.started_at or "",
                    s.ended_at or "",
                    str(len(store.prompts(s.id))),
                    str(store.event_count(s.id)),
                )
        if not rows:
            console.print("no sessions recorded yet: run `graphene init`, or `graphene ingest --backfill`")
        else:
            console.print(table)

    return cli
