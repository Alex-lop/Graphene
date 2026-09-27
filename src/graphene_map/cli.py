"""Command-line entry point.

``graphene ingest hook`` runs on every agent event, so it takes a fast path that imports only
the standard library and the store; Typer and Rich are imported for every other command.
"""

import sys


def app() -> None:
    if sys.argv[1:3] == ["ingest", "hook"]:
        from .hooks import hook_main

        raise SystemExit(hook_main())
    build()()


def build():
    import inspect
    import json
    import os
    import shlex
    import shutil
    import sqlite3
    from pathlib import Path

    import typer
    from rich.console import Console
    from rich.text import Text
    from typer.core import TyperGroup

    try:  # typer carries its own click in recent releases, and used click's before
        from typer._click.exceptions import MissingParameter, UsageError
    except ImportError:  # pragma: no cover
        from click.exceptions import MissingParameter, UsageError

    from . import __version__
    from .commits import refresh_commits
    from .hooks import SETTINGS, hooks_file, hooks_installed, install_hooks
    from .store import StaleStore, Store, repo_root

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
        "the store .graphene/graphene.db is locked by another graphene process (a hook or a command); "
        "try again in a moment"
    )

    def usage(error) -> str:
        """What Click would put in its usage box, as one plain line: what to add, or what was wrong."""
        path = " ".join(["graphene", *(error.ctx.command_path.split()[1:] if error.ctx else [])])
        if isinstance(error, MissingParameter) and error.param is not None:
            param = error.param
            name = param.opts[0] if param.param_type_name == "option" else f"<{param.name}>"
            what = (getattr(param, "help", None) or "").strip().rstrip(".")
            return f"{path} needs {name}" + (f": {what[:1].lower()}{what[1:]}" if what else "")
        said = error.format_message().strip().rstrip(".")
        helped = f" (`{path} --help` says what it takes)" if error.ctx else ""  # the parser names none
        return f"{path}: {said[:1].lower()}{said[1:]}{helped}"

    def paragraphs(command, rich: bool) -> None:
        """Every command's help reads as paragraphs: Typer's list of commands shows a docstring's hard
        line breaks as they are. A "[" is a bracket, not Rich markup (the text form's `[id]` vanished).
        A paragraph that starts with a \\b is printed as it is written."""
        for sub in getattr(command, "commands", {}).values():
            if sub.help:
                said = inspect.cleandoc(sub.help).split("\n\n")
                sub.help = "\n\n".join(p if p.startswith("\b") else " ".join(p.split()) for p in said)
                sub.help = sub.help.replace("[", "\\[") if rich else sub.help
            paragraphs(sub, rich)

    class LockAware(TyperGroup):
        """One place where losing the race with a hook or another command is a line, not a traceback; and
        where a missing option or argument, anywhere, is a line and not Click's usage box."""

        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            paragraphs(self, self.rich_markup_mode == "rich")

        def list_commands(self, ctx):
            """The plan leads the help: what will be done comes before what was."""
            first = ["plan", "node", "watch", "ask", "run", "init", "ui"]
            names = super().list_commands(ctx)
            return [n for n in first if n in names] + [n for n in names if n not in first]

        def parse_args(self, ctx, args):
            try:
                return super().parse_args(ctx, args)
            except UsageError as no:  # `graphene --bogus`: the only one raised before `invoke`
                fail(usage(no))

        def invoke(self, ctx):
            try:
                return super().invoke(ctx)
            except sqlite3.OperationalError as exc:
                if "locked" not in str(exc):
                    raise
                fail(LOCKED, 1)
            except UsageError as no:
                fail(usage(no))

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

    def nothing_to_draw(r: Path) -> None:
        if hooks_installed(r):
            then = "the hooks are installed, so the next session here is recorded live"
        else:
            then = "`graphene init` records sessions live"
        empty(f"nothing to draw here yet: no plan, and no Claude Code session recorded; {then}")

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
            empty(NO_PLAN)

    from .plan_cli import NO_PLAN, register

    plan_or_nothing = register(cli, root, open_store, fail)  # first: the plan leads `graphene --help`

    WHO = ("planner", "executor")
    # what init looks for, by name, so that none comes first: the `--with` word, its name, what it needs
    AGENTS = (("claude", "Claude Code", "claude on the PATH"), ("codex", "Codex", "codex on the PATH"),
              ("nemotron", "Nemotron on Token Factory", "NEBIUS_API_KEY"))  # fmt: skip

    def unreadable(command: str) -> str | None:
        """Why a planner or an executor cannot be started as written (`--with` splits it as a shell does)."""
        try:
            shlex.split(command)
        except ValueError as no:
            return f"{command!r} cannot be read as a command: {no}"
        return None

    def nemotron() -> tuple[dict[str, str], str, str | None]:
        """Nemotron on Token Factory as a new repo is offered it, what that is in words, and what could
        not be reached, in one line, or None. The ids are the live list's, so a run is reproducible and
        nothing is guessed: the largest of Ultra and Super plans (as planner.py picks when it runs), and
        the two smallest listed do the leaves, the second on a second attempt; in a Sandbox when ConTree
        is set up here, on this machine otherwise. Out of reach it is plain `nemotron`, which finds its
        models when it runs. Asked once: offline, init must not wait."""
        from . import sandbox
        from . import tokenfactory as tf

        unreached = tf.reach(tries=1)
        found = {} if unreached else tf.roles(tf.models(tries=1))
        plans = [s for s in ("ultra", "super") if s in found][:1]
        leaves = [s for s in ("nano", "super", "ultra") if s in found][:2]

        def models(sizes: list[str]) -> str:
            return "".join(f" --model {shlex.quote(found[s])}" for s in sizes)

        place = "sandbox" if sandbox.configured() else "local"
        ladder = f"nemotron{models(leaves)} --placement {place}"
        planner = plans[0].title() if plans else "largest"
        does = " then ".join(s.title() for s in leaves) or "smallest"
        said = f"{planner} plans, {does} {'do' if leaves[1:] else 'does'} the leaves"
        return {"planner": f"nemotron{models(plans)}", "executor": ladder}, said, unreached

    def asked_once(offer: dict[str, str], said: str, now: dict, found: list[str]) -> dict[str, str]:
        """At a terminal: each choice by name, with what it needs and whether it was found here. Enter
        keeps what is set; with nothing set it takes the one choice found, when exactly one is, and
        otherwise a number is typed (any of them: what is not found yet can still be chosen). A command
        of your own that cannot be read is said so, and asked again."""
        kept = any(now.values())
        if kept:
            say(" · ".join(f"{k} now: {now[k] or 'not chosen'}" for k in WHO))
        where = "each in a Sandbox" if offer["executor"].endswith("sandbox") else "on this machine"
        say("which planner and executor for this repo?")
        picks = {"4": {}}
        for n, (word, name, needs) in enumerate(AGENTS, 1):
            picks[str(n)] = offer if word == "nemotron" else dict.fromkeys(WHO, word)
            state = "found" if word in found else "not found"
            if word == "nemotron" and word not in found and os.environ.get("NEBIUS_API_KEY"):
                state = "not reached"  # the key is here; the line above says what did not answer
            say(f"  {n}  {name:<27}needs {needs:<20}{state}")
        say(f"     {said}, {where}")  # what Nemotron would be, under its line
        say(f"  4  {'a command of your own':<27}that takes the prompt last")
        one = [str(n) for n, (word, _, _) in enumerate(AGENTS, 1) if word in found]
        default = one[0] if len(one) == 1 and not kept else ""
        if kept:
            picks[""] = {}
        ask = "choose (Enter keeps them)" if kept else "choose"
        while (picked := typer.prompt(ask, default=default, show_default=bool(default))) not in picks:
            say("choose 1, 2, 3 or 4")
        if picked != "4":
            return picks[picked]

        def readable(command: str) -> str:
            if why := unreadable(command):
                raise typer.BadParameter(why)  # the prompt says it and asks again
            return command

        what = "a command that takes the prompt last"
        return {k: typer.prompt(f"the {k}, {what}", value_proc=readable) for k in WHO}

    def choose(store, given: dict[str, str], asking: bool) -> str:
        """The planner and the executor, kept in the store's meta as `--with` reads them. Found here:
        `claude` or `codex` on the PATH, and Nemotron when Token Factory answers the key. Asking, the
        person chooses at the terminal; else what is set is kept, and what is not gets what is found
        when exactly one thing is, and stays unset, said in one line, when none or several are. The
        flags change only what they name, and plain `nemotron` among them is the offer, ids and all.
        Returns what is set, in one line."""
        now = {k: store.meta(k) for k in WHO}
        missing = [k for k in WHO if k not in given and not now[k]]
        offer, said, unreached, found = {}, "", None, []
        if asking or missing or any(v.split()[:1] == ["nemotron"] for v in given.values()):
            offer, said, unreached = nemotron()
            if unreached and os.environ.get("NEBIUS_API_KEY"):  # a key that did not answer: before the choice
                say(unreached)
            found = [w for w, _, _ in AGENTS if (not unreached if w == "nemotron" else shutil.which(w))]
        if asking:
            given = asked_once(offer, said, now, found)
        else:
            plain = {k: offer[k] for k, v in given.items() if v.split() == ["nemotron"]}  # ids and all
            one = {} if len(found) != 1 else offer if found[0] == "nemotron" else dict.fromkeys(WHO, found[0])
            if missing and not one:  # nothing to pick from, or more than one: a script picks none
                names = " and ".join(name for w, name, _ in AGENTS if w in found)
                none = "no claude or codex is on the PATH, and no key that Token Factory answers"
                why = f"{names} are found here" if names else none
                who = " and ".join(f"the {k}" for k in missing)
                say(f"{who} {'are' if missing[1:] else 'is'} not chosen: {why}; "
                    "`graphene init` at a terminal asks, or --planner and --executor name one, and until "
                    "then `run` and `ask` start Claude Code")  # fmt: skip
            given = {**{k: one[k] for k in missing if one}, **given, **plain}
        if unreached and not os.environ.get("NEBIUS_API_KEY"):
            if any(v.split()[:1] == ["nemotron"] for v in given.values()):  # chosen: what it needs, once
                say(unreached)
        for k, v in given.items():
            store.set_meta(k, v)
        told = " · ".join(f"{k}: {store.meta(k) or 'not chosen'}" for k in WHO)
        return f"{told}  (`graphene init` changes them; --with changes one command)"

    @cli.command()
    def init(
        planner: str = typer.Option(None, help="The planner: claude, codex, nemotron or a command."),
        executor: str = typer.Option(None, help="The executor: claude, codex, nemotron or a command."),
    ) -> None:
        """Choose this repo's planner and executor from what is found here: `claude` or `codex` on the
        PATH, or NEBIUS_API_KEY for NVIDIA Nemotron on Token Factory. None is offered first. At a
        terminal it asks once, each choice with what it needs, and Enter takes one only when exactly
        one is found; without a terminal the flags choose, and a choice not made gets what is found
        when exactly one thing is. `graphene run`, `ask` and `node split` start them, and `--with`
        overrides one command. Then install the Claude Code hooks, which hold a Claude Code session to
        the plan and keep its record."""
        from . import plan as P

        if os.environ.get("GRAPHENE_NODE") or os.environ.get("GRAPHENE_PLANNER"):
            fail("an executor or a planner does not install hooks; that is the person's", 1)
        who = P.caller()
        given = {k: v for k, v in (("planner", planner), ("executor", executor)) if v is not None}
        if given:  # they are started as you, with your permissions, and they spend
            try:
                P._person_only(who, "choosing the planner and the executor")
            except P.Refused as no:
                fail(str(no), 1)
        for k, v in given.items():
            if why := unreadable(v):
                fail(f"--{k} {why}")
        # an agent is never asked, at a terminal or not: it would be choosing what the person runs
        asking = not given and who.person and sys.stdin.isatty() and sys.stdout.isatty()
        r = root()
        with open_store(r) as store:  # the choice first: a question left unanswered installs nothing
            chosen = choose(store, given, asking)
            specs = [store.meta(k) or "claude" for k in WHO]  # what `run` and `ask` start when none is set
            if store.meta("plan_first") is None:  # a repository set up for Graphene plans first
                store.set_meta("plan_first", "on")
        say(chosen)
        try:
            added = install_hooks(r)
        except ValueError as exc:
            fail(f"cannot update {SETTINGS}: {exc}", 1)
        settings = Path(os.path.relpath(hooks_file(r), Path.cwd()))
        say("plan first is on: what you ask for becomes a tree before any code "
            "(`graphene plan first off` turns it off)")  # fmt: skip
        if not any(s.split()[:1] == ["claude"] for s in specs):  # Claude Code is not how this repo works
            say(f"the Claude Code hooks are in {settings} too, for a Claude Code session you may run here"
                + ("" if added else " (already there)"))  # fmt: skip
        else:
            say(f"hooks added to {settings}: {', '.join(added)}" if added else "hooks already installed")
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

    ingest = typer.Typer(help="Record what the agent did (the hooks call this).")
    cli.add_typer(ingest, name="ingest", hidden=True)

    @ingest.command("hook")
    def ingest_hook() -> None:
        """Read one hook event from stdin (used by the installed hooks)."""
        from .hooks import hook_main

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
        if not (r / ".graphene" / "graphene.db").exists():  # looking must not create a store
            nothing_to_draw(r)
        # The plan is the page's first screen, so a repo that has one opens even when no session has
        # been recorded in it yet. The sessions are the ones the hooks recorded; their commits, git's.
        with open_store(r) as store:
            if not store.node_count() and not store.sessions():
                nothing_to_draw(r)
            refresh_commits(store, r, [])
            try:
                ids = [i for one in session or [None] for i in select_sessions(store, one)]
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
