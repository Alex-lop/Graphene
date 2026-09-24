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
    import json
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
    from .sources.claude_code import (
        SETTINGS,
        backfill,
        hooks_file,
        hooks_installed,
        install_hooks,
        looked_in,
        repo_root,
        transcripts_for,
    )
    from .store import StaleStore, Store

    SHELL_LISTS_HINT = (
        'one line only you can add: "bashEditDiffEnabled": true in ~/.claude/settings.json makes Claude '
        "Code record which files every shell command changed (a repo's settings cannot turn it on). "
        "Without it those lists exist only when Claude Code itself routes edits through the shell, and a "
        "file an agent writes with a heredoc or a script traces to its commit at best"
    )

    def shell_lists_enabled() -> bool:
        """Is the vendor's shell change list on in the person's own settings? Read, never written."""
        config = Path(os.environ.get("CLAUDE_CONFIG_DIR", Path.home() / ".claude")) / "settings.json"
        try:
            return json.loads(config.read_text(encoding="utf-8")).get("bashEditDiffEnabled") is True
        except (OSError, ValueError, AttributeError):
            return False

    LOCKED = (
        "the store .graphene/graphene.db is locked by another graphene process (a backfill or a hook); "
        "try again in a moment"
    )

    class LockAware(TyperGroup):
        """One place where losing the race with a hook or a backfill is a line, not a traceback."""

        def list_commands(self, ctx):
            """The plan leads the help: what will be done comes before what was."""
            first = ["plan", "node", "watch", "ask", "run", "init", "ui"]
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
        """A plain line on stdout: wrapped at words on a terminal, one line (no escape codes) when
        piped or redirected, so a script can grep it."""
        text = Text(message)
        if not (console.is_terminal and not console.no_color):
            console.file.write(text.plain + "\n")
            return
        for line in text.wrap(console, max(20, console.width - 1)):
            line.rstrip()
            console.print(line, no_wrap=True, crop=False, overflow="ignore")

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

    @cli.callback(invoke_without_command=True)
    def main(
        ctx: typer.Context,
        version: bool = typer.Option(False, "--version", help="Print the version and exit."),
    ):
        """With no command, `graphene` prints the plan and where the work stands. What was done for
        one node is `graphene node show <id>`; the map of a recorded run is `graphene ui`."""
        if version:
            console.print(f"graphene {__version__}")
            raise typer.Exit()
        if ctx.invoked_subcommand is None:
            if plan_or_nothing():
                return
            empty(
                "no plan here yet. `graphene node add '<what>' --scope '<paths>' --check '<command>'` "
                "starts one, or ask your agent to propose one; `graphene plan --help` has the rest."
            )

    from .plan_cli import register

    plan_or_nothing = register(cli, root, open_store, fail)  # first: the plan leads `graphene --help`

    @cli.command()
    def init() -> None:
        """Install the Claude Code hooks: they hold agents to the plan and keep the record."""
        if os.environ.get("GRAPHENE_NODE") or os.environ.get("GRAPHENE_PLANNER"):
            fail("an executor or a planner does not install hooks; that is the person's", 1)
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
        with open_store(r) as store:  # a repository set up for Graphene plans first (`plan first off`)
            if store.meta("plan_first") is None:
                store.set_meta("plan_first", "on")
        say("plan first is on: what you ask for in a session becomes a tree before any code "
            "(`graphene plan first off` turns it off)")  # fmt: skip
        if settings.name == Path(SETTINGS).name:
            say(
                f"{settings} is your personal settings file (if your team shares .claude/, add that "
                "file to .gitignore)"
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

        from .graph import build_graph, select_sessions, to_json
        from .plan import accept_path, caller
        from .server import export_html, make_server

        r = root()
        planned = False
        if (r / ".graphene" / "graphene.db").exists():  # looking must not create a store
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
                if caller().person:  # theirs as it stands, or the next node would not start over it
                    accept_path(store, r, export)
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

    return cli
