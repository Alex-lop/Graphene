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
    import sqlite3
    from pathlib import Path

    import typer
    from rich.console import Console
    from rich.markdown import Markdown
    from rich.markup import escape
    from rich.table import Table

    from . import __version__
    from .debrief import (
        build_debrief,
        preview,
        render_card,
        render_markdown,
        select_sessions,
        stamp,
        to_json,
    )
    from .explain import pick_explainer
    from .sources.claude_code import HOOK_COMMAND, backfill, install_hooks, now_iso, repo_root
    from .store import Store, ignore_store_dir
    from .why import why_line, why_path

    cli = typer.Typer(
        help=(
            "Why did my coding agent change this? `graphene why PATH` or `graphene why PATH:LINE` "
            "answers across Claude Code sessions; `graphene` alone shows a short card of the latest one."
        ),
        add_completion=False,
        no_args_is_help=False,
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

    def open_store(r: Path) -> Store:
        try:
            store = Store.open(r)
        except (sqlite3.DatabaseError, OSError) as exc:
            fail(f"cannot open {r / '.graphene' / 'graphene.db'}: {exc}", 1)
            raise AssertionError from None  # unreachable: fail() exits
        if store.rebuilt_from:
            errors.print(f"[dim]store rebuilt (old copy at {escape(store.rebuilt_from)})[/dim]")
        return store

    def loaded_store(r: Path) -> Store:
        """The repo's store; when it holds no sessions yet, Claude Code's transcripts are read first."""
        store = open_store(r)
        if store.sessions():
            return store
        report = backfill(store, r)
        n = len(report.added)
        if not n:
            store.close()
            fail(
                "no Claude Code sessions found for this repo: run Claude Code here first "
                "(`graphene init` records sessions live)",
                1,
            )
        errors.print(f"[dim]loaded {n} session{'s' if n != 1 else ''} from Claude Code's transcripts[/dim]")
        return store

    def hooks_hint(r: Path) -> None:
        settings = r / ".claude" / "settings.json"
        try:
            installed = HOOK_COMMAND in settings.read_text(encoding="utf-8")
        except OSError:
            installed = False
        if not installed:
            errors.print(
                "[dim]`graphene init` would record sessions live; "
                "until then Graphene reads Claude Code's transcripts[/dim]"
            )

    def show(
        session_id: str | None,
        since: str | None,
        as_json: bool = False,
        md: Path | None = None,
        full: bool = False,
        explain: str | None = None,
        model: str | None = None,
    ) -> None:
        r = root()
        try:
            explainer, notice = pick_explainer(explain, model)
        except ValueError as exc:
            fail(str(exc))
        with loaded_store(r) as store:
            try:
                ids = select_sessions(store, session_id, since)
            except ValueError as exc:
                fail(str(exc))
            if not ids:
                fail(f"no session in that window; `graphene sessions` lists {len(store.sessions())}", 1)
            if notice:
                errors.print(f"[dim]{escape(notice)}[/dim]")
            result = build_debrief(store, ids, r, explainer)
            store.add_debrief_run(ids, now_iso())
        markdown = render_markdown(result, full=True) if full else render_card(result)
        if md:
            try:
                md.parent.mkdir(parents=True, exist_ok=True)
                md.write_text(markdown, encoding="utf-8")
            except OSError as exc:
                fail(f"cannot write {md}: {exc.strerror or exc}", 1)
            errors.print(f"wrote {md}")
        if as_json:
            sys.stdout.write(to_json(result) + "\n")
        elif not md:
            console.print(Markdown(markdown))
            if not full:
                hooks_hint(r)

    @cli.callback(invoke_without_command=True)
    def main(
        ctx: typer.Context,
        version: bool = typer.Option(False, "--version", help="Print the version and exit."),
    ):
        """With no command: a short card of what changed since you last looked."""
        if version:
            console.print(f"graphene {__version__}")
            raise typer.Exit()
        if ctx.invoked_subcommand is None:
            show(None, None)

    @cli.command()
    def why(target: str = typer.Argument(..., help="PATH, or PATH:LINE for one line.")) -> None:
        """Which prompts changed a file (newest first), or which one wrote a given line."""
        r = root()
        path, _, line = target.rpartition(":")
        with loaded_store(r) as store:
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

    @cli.command(rich_help_panel="Advanced")
    def debrief(
        session_id: str = typer.Argument(None, help="A session id, or a unique prefix of one."),
        since: str = typer.Option(None, "--since", help="6h, 2d, or a date like 2026-09-16."),
        full: bool = typer.Option(
            False, "--full", help="The whole reconstruction: every prompt, file and failure."
        ),
        as_json: bool = typer.Option(False, "--json", help="Print the full structure as JSON."),
        md: Path = typer.Option(None, "--md", help="Write the output as markdown to this file."),
        explain: str = typer.Option(
            None, "--explain", help="claude (one call per prompt) or none (default)."
        ),
        model: str = typer.Option(None, "--model", help="Model for --explain claude (default haiku)."),
    ) -> None:
        """Verbose: with --full, the whole reconstruction (every prompt, file and failure).

        Not the come-back view; that is plain `graphene`. Without --full it prints the same card.
        """
        show(session_id, since, as_json=as_json, md=md, full=full, explain=explain, model=model)

    @cli.command(rich_help_panel="Advanced")
    def sessions() -> None:
        """List recorded sessions."""
        with loaded_store(root()) as store:
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
        console.print(table)

    @cli.command()
    def init() -> None:
        """Install Claude Code hooks so this repo's sessions are recorded live (optional)."""
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
        open_store(r).close()
        if shutil.which("graphene") is None:
            console.print(
                "[yellow]warning:[/yellow] `graphene` is not on PATH, so the hook will not run. "
                "Install it with `uv tool install graphene-debrief` (or `--editable .`)."
            )

    ingest = typer.Typer(
        help="Record what the agent did (the hooks and --backfill do this for you).",
        invoke_without_command=True,
    )
    cli.add_typer(ingest, name="ingest", rich_help_panel="Advanced")

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
        with open_store(r) as store:
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
            console.print(f"other record types (not prompts or tool calls): {kinds}")

    @ingest.command("hook")
    def ingest_hook() -> None:
        """Read one hook event from stdin (used by the installed hooks)."""
        from .sources.claude_code import hook_main

        raise typer.Exit(hook_main())

    return cli
