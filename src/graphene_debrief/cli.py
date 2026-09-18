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
    from rich.text import Text
    from typer.core import TyperGroup

    from . import __version__
    from .debrief import (
        ACCENT,
        build_debrief,
        print_card,
        print_full,
        print_sessions,
        print_why,
        render_card,
        render_markdown,
        select_sessions,
        stamp,
        to_json,
        write_line,
    )
    from .explain import pick_explainer
    from .sources.claude_code import (
        SETTINGS,
        backfill,
        hooks_installed,
        install_hooks,
        looked_in,
        now_iso,
        repo_root,
        transcripts_for,
    )
    from .store import Store
    from .why import why_line, why_path

    ADVANCED = "Advanced"
    LOCKED = (
        "the store .graphene/graphene.db is locked by another graphene process (a backfill or a hook); "
        "try again in a moment"
    )

    class LockAware(TyperGroup):
        """One place where losing the race with a hook or a backfill is a line, not a traceback."""

        def invoke(self, ctx):
            try:
                return super().invoke(ctx)
            except sqlite3.OperationalError as exc:
                if "locked" not in str(exc):
                    raise
                fail(LOCKED, 1)

    cli = typer.Typer(
        cls=LockAware,
        help=(
            "Why did your coding agent change this? `graphene why <path>` and `graphene why <path>:<line>` "
            "answer that from Claude Code's own records; `graphene` alone prints the short card of the "
            "latest session."
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
        if r.resolve() == Path.home().resolve():
            fail("refusing to treat your home directory as a repo; cd into the repo you ran Claude Code in")
        return r

    def note(message: str, style: str | None = "dim") -> None:
        """One message on stderr: one line when piped (greppable), word-wrapped on a terminal."""
        if errors.is_terminal:
            for line in Text(message).wrap(errors, max(20, errors.width - 1)):
                line.rstrip()
                errors.print(line, style=style, no_wrap=True, crop=False, overflow="ignore")
        else:
            errors.print(Text(message), style=style, no_wrap=True, crop=False, overflow="ignore")

    def fail(message: str, code: int = 2) -> None:
        note(message, "red")
        raise typer.Exit(code)

    def say(message: str) -> None:
        """A plain line on stdout: wrapped at words on a terminal, one line when piped."""
        write_line(console, Text(message), wrap=True)

    def empty(message: str) -> None:
        """Nothing to show yet is not an error: plain text, exit 1 so scripts can tell."""
        note(message, None)
        raise typer.Exit(1)

    def open_store(r: Path) -> Store:
        try:
            store = Store.open(r)
        except (sqlite3.DatabaseError, OSError) as exc:
            if "locked" in str(exc):
                fail(LOCKED, 1)
            fail(f"cannot open {r / '.graphene' / 'graphene.db'}: {exc}", 1)
            raise AssertionError from None  # unreachable: fail() exits
        if store.rebuilt_from:
            note(f"store rebuilt (old copy at {store.rebuilt_from})")
        return store

    def no_sessions(r: Path) -> None:
        if hooks_installed(r):
            then = "the hooks are installed, so the next session here is recorded live"
        else:
            then = "`graphene init` records sessions live"
        empty(
            f"no Claude Code sessions for this repo yet (looked in {looked_in(r)}): "
            f"run Claude Code here, then `graphene` again; {then}"
        )

    def loaded_store(r: Path) -> Store:
        """The repo's store, topped up from Claude Code's transcripts first (a transcript that has not
        changed since it was last read costs one stat, so this is cheap on every run). A repo with
        neither a store nor a transcript gets the empty state and nothing written."""
        if not (r / ".graphene" / "graphene.db").exists() and not transcripts_for(r):
            no_sessions(r)
        store = open_store(r)
        report = backfill(store, r)
        if not store.sessions():
            store.close()
            no_sessions(r)
        n = len(report.added)
        if n:
            note(f"loaded {n} session{'s' if n != 1 else ''} from Claude Code's transcripts")
        return store

    def hooks_hint(r: Path) -> None:
        if not hooks_installed(r):
            note("`graphene init` records sessions live; until then Graphene reads transcripts")

    def show(
        session_id: str | None,
        since: str | None,
        as_json: bool = False,
        md: Path | None = None,
        full: bool = False,
        explain: str | None = None,
        model: str | None = None,
        html: Path | None = None,
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
                empty(f"no session in that window; `graphene sessions` lists {len(store.sessions())}")
            if notice:
                note(notice)
            result = build_debrief(store, ids, r, explainer)
            store.add_debrief_run(ids, now_iso())
        if md is None and html is None and not as_json and not (result.files_changed or result.commits):
            n, p = len(result.sessions), result.prompt_count
            empty(
                f"{n} session{'s' if n != 1 else ''}, {p} prompt{'s' if p != 1 else ''}, "
                f"no file changes recorded; `graphene sessions` lists {'it' if n == 1 else 'them'}"
            )
        markdown = render_markdown(result, full=True) if full else render_card(result)
        if md:
            try:
                md.parent.mkdir(parents=True, exist_ok=True)
                md.write_text(markdown, encoding="utf-8")
            except OSError as exc:
                fail(f"cannot write {md}: {exc.strerror or exc}", 1)
            errors.print(f"wrote {md}")
        if html:
            from .export_html import render as render_html

            try:
                html.parent.mkdir(parents=True, exist_ok=True)
                html.write_text(render_html(result), encoding="utf-8")
            except OSError as exc:
                fail(f"cannot write {html}: {exc.strerror or exc}", 1)
            errors.print(f"wrote {html}")
        if as_json:
            sys.stdout.write(to_json(result) + "\n")
        elif not md and not html:
            if console.is_terminal:
                (print_full if full else print_card)(console, result)
            else:  # piped or redirected: the markdown text itself, unrendered
                sys.stdout.write(markdown)
            if not full:
                hooks_hint(r)

    @cli.callback(invoke_without_command=True)
    def main(
        ctx: typer.Context,
        version: bool = typer.Option(False, "--version", help="Print the version and exit."),
    ):
        """With no command, `graphene` prints the short card of the latest session."""
        if version:
            console.print(f"graphene {__version__}")
            raise typer.Exit()
        if ctx.invoked_subcommand is None:
            show(None, None)

    @cli.command()
    def why(
        target: str = typer.Argument(None, help="PATH for a file's history, or PATH:LINE for one line."),
    ) -> None:
        """Which prompts changed a file (newest first), or which one wrote a given line."""
        r = root()
        path, _, line = (target or "").rpartition(":")
        with loaded_store(r) as store:
            if target is None:
                write_line(console, Text("files with recorded changes, newest first:", "dim"))
                recent = store.recent_paths()
                pad = max((len(path) for path, _ in recent), default=0)
                for path, when in recent:
                    row = Text()
                    row.append(path.ljust(pad), ACCENT)
                    row.append("  " + stamp(when), "dim")
                    write_line(console, row)
                console.file.flush()  # the list before the usage line, whichever stream is captured
                fail("usage: graphene why <path> | <path>:<line>")
            if path and line.isdigit():
                answer = why_line(store, r, path, int(line))
                if answer.content is None:
                    fail(answer.reason, 1)
                where = (
                    f"committed in {answer.commit[:7]} ({stamp(answer.committed_at)})"
                    if answer.commit
                    else "not committed"
                )
                print_why(
                    console,
                    f"{answer.path}:{answer.line}",
                    answer.content,
                    f"{where} · {answer.reason}",
                    answer.matches,
                )
            else:
                entries = why_path(store, r, target)
                if not entries:
                    empty(f"no recorded prompt changed {target}")
                n = len(entries)
                subtitle = f"{n} prompt{'s' if n != 1 else ''}, newest first"
                print_why(console, entries[0].change.path, "", subtitle, entries)

    @cli.command()
    def debrief(
        session_id: str = typer.Argument(None, help="A session id, or a unique prefix of one."),
        since: str = typer.Option(None, "--since", help="6h, 2d, or a date like 2026-09-16."),
        full: bool = typer.Option(
            False, "--full", help="The whole reconstruction: every prompt, file and failure."
        ),
        as_json: bool = typer.Option(False, "--json", help="Print the full structure as JSON."),
        md: Path = typer.Option(None, "--md", help="Write the output as markdown to this file."),
        html: Path = typer.Option(
            None,
            "--html",
            help="Write a self-contained HTML record of the selected sessions to this file.",
        ),
        explain: str = typer.Option(
            None, "--explain", help="claude (one call per prompt) or none (default)."
        ),
        model: str = typer.Option(None, "--model", help="Model for --explain claude (default haiku)."),
    ) -> None:
        """The short session card, the same as plain `graphene`; --full is the whole reconstruction."""
        show(session_id, since, as_json=as_json, md=md, full=full, explain=explain, model=model, html=html)

    @cli.command(rich_help_panel=ADVANCED)
    def init() -> None:
        """Install Claude Code hooks so this repo's sessions are recorded live (optional)."""
        r = root()
        try:
            added = install_hooks(r)
        except ValueError as exc:
            fail(f"cannot update {SETTINGS}: {exc}", 1)
        settings = Path(os.path.relpath(r / SETTINGS, Path.cwd()))
        if added:
            say(f"hooks added to {settings}: {', '.join(added)}")
        else:
            say("hooks already installed")
        say(
            f"{settings} is your personal settings file (if your team shares .claude/, add that file "
            "to .gitignore); nothing else is written until a session is recorded"
        )
        say(
            "the next Claude Code session in this repo is recorded live into .graphene/ (private to "
            "you, ignores itself in git); then run `graphene`"
        )
        if shutil.which("graphene") is None:
            console.print(
                "[yellow]warning:[/yellow] `graphene` is not on PATH, so the hook will not run. "
                "Install it with `uv tool install graphene-debrief` (or `--editable .`)."
            )

    ingest = typer.Typer(
        help="Record what the agent did (the hooks and --backfill do this for you).",
        invoke_without_command=True,
    )
    cli.add_typer(ingest, name="ingest", rich_help_panel=ADVANCED)

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

    @cli.command(rich_help_panel=ADVANCED)
    def sessions() -> None:
        """List the recorded sessions, newest first."""
        with loaded_store(root()) as store:
            rows = [
                (
                    s.id[:8],
                    s.source,
                    stamp(s.started_at),
                    stamp(s.ended_at) if s.ended_at else "running",
                    len(store.prompts(s.id)),
                    store.event_count(s.id),
                )
                for s in reversed(store.sessions())
            ]
        print_sessions(console, rows)

    return cli
