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
    from .commits import refresh_commits
    from .debrief import (
        ACCENT,
        SHELL_LISTS_HINT,
        build_debrief,
        coverage_cell,
        offset,
        print_card,
        print_sessions,
        print_why,
        print_writes,
        render_card,
        select_sessions,
        shell_lists_enabled,
        stamp,
        stamp_tz,
        to_json,
        write_line,
    )
    from .sources.claude_code import (
        SETTINGS,
        backfill,
        hooks_file,
        hooks_installed,
        install_hooks,
        looked_in,
        now_iso,
        repo_root,
        transcripts_for,
    )
    from .store import StaleStore, Store
    from .why import (
        candidates,
        commits_of,
        last_commit,
        path_coverage,
        recorded_writes,
        why_line,
        why_path,
    )

    LOCKED = (
        "the store .graphene/graphene.db is locked by another graphene process (a backfill or a hook); "
        "try again in a moment"
    )

    class LockAware(TyperGroup):
        """One place where losing the race with a hook or a backfill is a line, not a traceback."""

        def list_commands(self, ctx):
            """The plan leads the help: what will be done comes before what was."""
            first = ["plan", "node", "run", "init", "ui"]
            names = super().list_commands(ctx)
            return [n for n in first if n in names] + [n for n in names if n not in first]

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
            "The shared plan between you and your coding agents: a graph of nodes, each with a goal, the "
            "paths it may touch and a check, which you shape and the agents are held to. `graphene` "
            "alone shows the plan and where the work stands; `graphene node show <id>` is what was done "
            "for one node."
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
        except StaleStore:  # only "newer" reaches here: an unreadable file was moved aside
            fail(
                f"{r / '.graphene' / 'graphene.db'} was written by a newer graphene; upgrade this one "
                "(`uv tool upgrade graphene-map`). The store was left as it is",
                1,
            )
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
        refresh_commits(store, r, report.added + report.refreshed)
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
    ) -> None:
        r = root()
        with loaded_store(r) as store:
            try:
                ids = select_sessions(store, session_id, since)
            except ValueError as exc:
                fail(str(exc))
            if not ids:
                empty(f"no session in that window; `graphene sessions` lists {len(store.sessions())}")
            result = build_debrief(store, ids, r)
            store.add_debrief_run(ids, now_iso())
            others = sum(1 for s in store.sessions() if s.id not in ids and store.event_count(s.id))
        if not as_json and not (result.files_changed or result.commits):
            n, p = len(result.sessions), result.prompt_count
            empty(
                f"{n} session{'s' if n != 1 else ''}, {p} prompt{'s' if p != 1 else ''}, "
                f"no file changes recorded; `graphene sessions` lists {'it' if n == 1 else 'them'}"
            )
        if as_json:
            sys.stdout.write(to_json(result) + "\n")
            return
        if console.is_terminal:
            print_card(console, result)
        else:  # piped or redirected: the markdown text itself, unrendered
            sys.stdout.write(render_card(result))
        if others:
            note(
                f"{others} other session{'s' if others != 1 else ''} recorded; `graphene sessions` lists them"
            )
        hooks_hint(r)

    @cli.callback(invoke_without_command=True)
    def main(
        ctx: typer.Context,
        session_id: str = typer.Option(None, "--session", help="A session id, or a unique prefix of one."),
        since: str = typer.Option(None, "--since", help="6h, 2d, or a date like 2026-09-16."),
        as_json: bool = typer.Option(False, "--json", help="Print the full structure as JSON."),
        version: bool = typer.Option(False, "--version", help="Print the version and exit."),
    ):
        """With no command, `graphene` prints the plan and where the work stands; in a repo with no
        plan (or with --session, --since or --json), the short card of the latest session."""
        if version:
            console.print(f"graphene {__version__}")
            raise typer.Exit()
        if ctx.invoked_subcommand is None:
            if not (session_id or since or as_json) and plan_or_nothing():
                return
            show(session_id, since, as_json=as_json)

    from .plan_cli import register

    plan_or_nothing = register(cli, root, open_store, fail)  # first: the plan leads `graphene --help`

    @cli.command()
    def why(
        target: str = typer.Argument(None, help="PATH for a file's history, or PATH:LINE for one line."),
    ) -> None:
        """Which prompts changed a file (newest first), or which one wrote a given line."""
        r = root()
        path, _, line = (target or "").rpartition(":")
        with loaded_store(r) as store:
            if target is None:
                write_line(console, Text("files with recorded edits, newest first:", "dim"))
                recent = store.recent_paths()
                pad = max((len(path) for path, _ in recent), default=0)
                for path, when in recent:
                    row = Text()
                    row.append(path.ljust(pad), ACCENT)
                    row.append("  " + stamp_tz(when), "dim")
                    write_line(console, row)
                more = store.recorded_path_count() - len(recent)
                if more > 0:
                    write_line(console, Text(f"… {more} more; `graphene` lists a session's files", "dim"))
                console.file.flush()  # the list before the usage line, whichever stream is captured
                fail("usage: graphene why <path> | <path>:<line>")
            if path and line.isdigit():
                answer = why_line(store, r, path, int(line))
                if answer.content is None:
                    fail(answer.reason, 1)
                where = (
                    f"committed in {answer.commit[:7]} ({stamp_tz(answer.committed_at)})"
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
                rel = entries[0].change.path if entries else candidates(r, target)[-1]
                covered = path_coverage(store, rel)
                if not entries:
                    writes = recorded_writes(store, rel)
                    held = commits_of(store, rel)
                    told = "; ".join(
                        f"{len(shas)} commit{'s' if len(shas) != 1 else ''} "
                        + (f"during session {sid[:8]}" if sid else "outside any recorded session")
                        for sid, shas in held.items()
                    )
                    if writes:  # recorded, but no payload carries its diff: show the writes themselves
                        n = len(writes)
                        head = (
                            f"{n} recorded write{'s' if n != 1 else ''}, newest first; no diff was recorded"
                        )
                        print_writes(console, rel, head + (f"\n{covered}" if covered else ""), writes)
                        return
                    if told:  # git knows the file changed, and that is the answer: no write was recorded
                        say(f"{rel}: changed in {told}; no recorded write. {covered}")
                        return
                    known = last_commit(r, rel)
                    if known:
                        say(
                            f"no recorded prompt changed {rel}; git last changed it in {known[0]} "
                            f"({stamp_tz(known[1])}), outside every recorded session"
                        )
                        return
                    if not (r / rel).exists():
                        empty(f"{target}: no such file in this repo, on disk or in git's history")
                    empty(f"no recorded prompt changed {rel}, and git has no commit of it yet")
                n = len(entries)
                subtitle = f"{n} prompt{'s' if n != 1 else ''}, newest first"
                print_why(console, rel, "", subtitle + (f"\n{covered}" if covered else ""), entries)

    @cli.command(hidden=True)
    def debrief(
        session_id: str = typer.Argument(None, help="A session id, or a unique prefix of one."),
        since: str = typer.Option(None, "--since", help="6h, 2d, or a date like 2026-09-16."),
        as_json: bool = typer.Option(False, "--json", help="Print the full structure as JSON."),
    ) -> None:
        """The short session card: an alias of plain `graphene`, kept for scripts that call it."""
        show(session_id, since, as_json=as_json)

    @cli.command()
    def init() -> None:
        """Install the Claude Code hooks: they hold agents to the plan and keep the record."""
        r = root()
        try:
            added = install_hooks(r)
        except ValueError as exc:
            fail(f"cannot update {SETTINGS}: {exc}", 1)
        settings = Path(os.path.relpath(hooks_file(r), Path.cwd()))
        if added:
            say(f"hooks added to {settings}: {', '.join(added)}")
        else:
            say("hooks already installed")
        if settings.name == Path(SETTINGS).name:
            say(
                f"{settings} is your personal settings file (if your team shares .claude/, add that "
                "file to .gitignore); nothing else is written until a session is recorded"
            )
        say(
            "the next Claude Code session in this repo is recorded live into .graphene/ (private to "
            "you, ignores itself in git); then run `graphene`"
        )
        if not shell_lists_enabled():
            say(SHELL_LISTS_HINT)
        if shutil.which("graphene") is None:
            console.print(
                "[yellow]warning:[/yellow] `graphene` is not on PATH, so the hook will not run. "
                "Install it with `uv tool install graphene-map` (or `--editable .`)."
            )

    ingest = typer.Typer(
        help="Record what the agent did (the hooks and --backfill do this for you).",
        invoke_without_command=True,
    )
    cli.add_typer(ingest, name="ingest", hidden=True)

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

    @cli.command()
    def ui(
        session: list[str] = typer.Option(
            None, "--session", help="A session id or unique prefix; repeat it to put several on one axis."
        ),
        export: Path = typer.Option(None, "--export", help="Write the map as one self-contained HTML file."),
        no_open: bool = typer.Option(False, "--no-open", help="Print the address without opening a browser."),
        as_json: bool = typer.Option(False, "--json", help="Print the graph the page draws, as JSON."),
    ) -> None:
        """The plan on screen, and behind it the map of a run, drawn from the records."""
        import webbrowser

        from .graph import build_graph, to_json
        from .plan import caller
        from .server import export_html, make_server

        r = root()
        with open_store(r) as store:
            planned = store.node_count() > 0
        # The plan is the page's first screen, so a repo that has one opens even when no session has
        # been recorded in it yet; `loaded_store` ends the command when there is nothing to look at.
        with open_store(r) if planned else loaded_store(r) as store:
            if planned:
                report = backfill(store, r)  # the record fills in beside the plan, quietly
                refresh_commits(store, r, report.added + report.refreshed)
            try:
                ids = [i for one in session or [None] for i in select_sessions(store, one, None)]
            except ValueError as exc:
                fail(str(exc))
            if as_json:
                sys.stdout.write(to_json(build_graph(store, ids)) + "\n")
                return
            if export:
                try:
                    export.parent.mkdir(parents=True, exist_ok=True)
                    export.write_text(export_html(store, ids), encoding="utf-8")
                except OSError as exc:
                    fail(f"cannot write {export}: {exc.strerror or exc}", 1)
                errors.print(f"wrote {export}")
                return
        # The plan is the person's to change, so the page may write only when a person opened it.
        person = caller().person
        server = make_server(r, ids, writable=person)
        url = f"http://127.0.0.1:{server.server_address[1]}/"
        say(f"{url}  (this machine only; Ctrl-C stops it)")
        if not person:
            say("the page is read-only: it was not opened from a person's terminal")
        console.file.flush()  # piped or redirected, the address must not sit in a buffer until the end
        if not no_open:
            webbrowser.open(url)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass
        finally:
            server.server_close()

    @cli.command()
    def sessions(
        everything: bool = typer.Option(False, "--all", help="Also list sessions that made no calls."),
    ) -> None:
        """List the recorded sessions, newest first."""
        from .graph import coverage_counts, run_records

        with loaded_store(root()) as store:
            listed = list(reversed(store.sessions()))
            listed = [(s, store.event_count(s.id)) for s in listed]
            rows = [
                (
                    s.id[:8],
                    s.source,
                    stamp(s.started_at),
                    stamp(s.ended_at) if s.ended_at else "running",
                    calls,
                    coverage_cell(coverage_counts(run_records(store, [s.id]).coverage)) if calls else "-",
                )
                for s, calls in listed
                if calls or everything
            ]
        quiet = [s for s, calls in listed if not calls]
        zone = next((offset(s.started_at) for s, _ in listed if s.started_at), "")
        print_sessions(console, rows, zone)
        if quiet and not everything:
            n = len(quiet)
            note(f"{n} session{'s' if n != 1 else ''} with no calls not listed; `graphene sessions --all`")

    return cli
