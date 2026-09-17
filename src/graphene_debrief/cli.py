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
    import os
    import shutil
    from pathlib import Path

    import typer
    from rich.console import Console
    from rich.markdown import Markdown
    from rich.markup import escape
    from rich.table import Table

    from . import __version__
    from .debrief import build_debrief, preview, render_markdown, select_sessions, stamp, to_json
    from .explain import pick_explainer
    from .sources.claude_code import backfill, ignore_store_dir, install_hooks, now_iso, repo_root
    from .store import Store
    from .why import why_line, why_path

    cli = typer.Typer(
        help="What your coding agent did, and why, grouped by what you asked for.",
        no_args_is_help=True,
        add_completion=False,
    )
    console = Console()
    errors = Console(stderr=True)

    def root() -> Path:
        r = repo_root(Path.cwd())
        if not (r / ".git").exists():
            fail("run this inside a git repository (no .git found above the current directory)")
        if r == Path.home():
            fail("refusing to treat your home directory as a repo")
        return r

    def fail(message: str, code: int = 2) -> None:
        errors.print(f"[red]{escape(message)}[/red]")
        raise typer.Exit(code)

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
            fail(f"cannot update .claude/settings.json: {exc}", 1)
        if added:
            settings = Path(os.path.relpath(r / ".claude" / "settings.json", Path.cwd()))
            console.print(f"hooks added to {settings}: {', '.join(added)}")
        else:
            console.print("hooks already installed")
        if ignore_store_dir(r):
            console.print("added .graphene/ to .gitignore")
        Store.open(r).close()
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
        replace: bool = typer.Option(False, "--replace", help="Rebuild sessions the hooks recorded, too."),
    ) -> None:
        if ctx.invoked_subcommand is not None:
            return
        if not do_backfill:
            fail("nothing to do: pass --backfill, or let the hooks call `graphene ingest hook`", 1)
        r = root()
        with Store.open(r) as store:
            report = backfill(store, r, transcripts=transcript or None, replace=replace)
        console.print(
            f"added {len(report.added)}, refreshed {len(report.refreshed)}, "
            f"already present {len(report.skipped)}, other repos {len(report.other_repo)}"
        )
        for sid in report.added + report.refreshed:
            console.print(f"  {sid}")
        for path, error in report.failed:
            console.print(f"[yellow]could not read {path}: {error}[/yellow]")
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
            table = Table("session (prefix)", "source", "started", "ended", "prompts", "tool calls")
            for s in rows:
                table.add_row(
                    s.id[:8],
                    s.source,
                    stamp(s.started_at),
                    stamp(s.ended_at),
                    str(len(store.prompts(s.id))),
                    str(store.event_count(s.id)),
                )
        if not rows:
            console.print("no sessions recorded yet: run `graphene init`, or `graphene ingest --backfill`")
        else:
            console.print(table)

    @cli.command()
    def debrief(
        session_id: str = typer.Argument(None, help="A session id, or a unique prefix of one."),
        since: str = typer.Option(None, "--since", help="6h, 2d, or a date like 2026-09-16."),
        as_json: bool = typer.Option(False, "--json", help="Print the debrief structure as JSON."),
        md: Path = typer.Option(None, "--md", help="Write the debrief as markdown to this file."),
        full: bool = typer.Option(False, "--full", help="Show whole prompts instead of their first lines."),
        explain: str = typer.Option(None, "--explain", help="claude or none (default: claude when on PATH)."),
    ) -> None:
        """What the agent did since the last debrief, grouped by what you asked for."""
        r = root()
        try:
            explainer, notice = pick_explainer(explain)
        except ValueError as exc:
            fail(str(exc))
        with Store.open(r) as store:
            try:
                ids = select_sessions(store, session_id, since)
            except ValueError as exc:
                fail(str(exc))
            if not ids:
                fail("no sessions recorded yet: run `graphene init`, or `graphene ingest --backfill`", 1)
            if notice:
                errors.print(f"[dim]{escape(notice)}[/dim]")
            result = build_debrief(store, ids, r, explainer)
            store.add_debrief_run(ids, now_iso())
        if as_json:
            sys.stdout.write(to_json(result) + "\n")
            return
        markdown = render_markdown(result, full=full)
        if md:
            md.write_text(markdown, encoding="utf-8")
            console.print(f"wrote {md}")
        else:
            console.print(Markdown(markdown))

    @cli.command()
    def why(target: str = typer.Argument(..., help="PATH, or PATH:LINE for one line.")) -> None:
        """Which prompts changed a file, newest first; or which one wrote a given line."""
        r = root()
        path, _, line = target.rpartition(":")
        with Store.open(r) as store:
            if path and line.isdigit():
                answer = why_line(store, r, path, int(line))
                if answer.content is None:
                    fail(answer.reason, 1)
                where = (
                    f"committed in {answer.commit[:7]} ({stamp(answer.committed_at)})"
                    if answer.commit
                    else "not committed"
                )
                console.print(
                    f"[bold]{escape(answer.path)}:{answer.line}[/bold]  {escape(answer.content.strip())}"
                )
                console.print(f"{where} · {escape(answer.reason)}")
                entries = answer.matches
            else:
                entries = why_path(store, r, target)
                if not entries:
                    fail(f"no recorded prompt changed {target}", 1)
                console.print(
                    f"[bold]{escape(entries[0].change.path)}[/bold]  {len(entries)} prompt(s), newest first"
                )
        for e in entries:
            console.print(
                f"\n{stamp(e.timestamp)}  session {e.session_id[:8]}  prompt {e.ordinal}  "
                f"{e.effect} +{e.added}/−{e.removed}"
            )
            for row in preview(e.prompt_text).splitlines():
                console.print(f"  [dim]> {escape(row)}[/dim]")
            console.print(f"  {escape(e.explanation)}")

    return cli
