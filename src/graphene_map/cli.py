"""Command-line entry point.

``graphene ingest hook`` runs on every agent event, so it takes a fast path that imports only
the standard library and the store; Typer and Rich are imported for every other command.
"""

import os
import sys


def app() -> None:
    if sys.argv[1:3] == ["ingest", "hook"]:
        from .hooks import hook_main

        code = hook_main()
        # The store is closed and the answer is flushed here, so the hook skips the interpreter's
        # teardown of every module it loaded: about 4 ms of each call the agent waits for.
        try:
            sys.stdout.flush()
        except OSError:
            pass  # Claude Code stopped reading: the hook still never fails the agent
        os._exit(code)
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
    from .hooks import SETTINGS, hooks_file, install_hooks
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
        if path.startswith("graphene key"):  # what was typed may be a pasted key: never say it back
            return f"{path} takes no words; the key is read from a hidden prompt (`{path} --help`)"
        said = error.format_message().strip().rstrip(".")
        helped = f" (`{path} --help` says what it takes)" if error.ctx else ""  # the parser names none
        return f"{path}: {said[:1].lower()}{said[1:]}{helped}"

    def paragraphs(command, rich: bool) -> None:
        """Every command's help reads as paragraphs: Typer's list of commands shows a docstring's hard
        line breaks as they are. A "[" is a bracket, not Rich markup (the text form's `[id]` vanished)."""
        for sub in getattr(command, "commands", {}).values():
            if sub.help:
                said = inspect.cleandoc(sub.help).split("\n\n")
                sub.help = "\n\n".join(" ".join(p.split()) for p in said)
                sub.help = sub.help.replace("[", "\\[") if rich else sub.help
            paragraphs(sub, rich)

    class LockAware(TyperGroup):
        """One place where losing the race with a hook or another command is a line, not a traceback; and
        where a missing option or argument, anywhere, is a line and not Click's usage box."""

        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            paragraphs(self, self.rich_markup_mode == "rich")

        def list_commands(self, ctx):
            """The help lists the commands in the order a new user needs them."""
            first = ["init", "ask", "watch", "run", "plan", "node", "board", "demo", "config"]
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
            "Plan work with your coding agents, then hold them to the plan.\n\n"
            "`graphene` shows the plan. `graphene node show <id>` shows one node's record."
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

    @cli.callback(invoke_without_command=True)
    def main(
        ctx: typer.Context,
        version: bool = typer.Option(False, "--version", help="Print the version and exit."),
    ):
        """With no command, print the plan and where the work stands."""
        if version:
            console.print(f"graphene {__version__}")
            raise typer.Exit()
        if ctx.invoked_subcommand is None:
            if plan_or_nothing():
                return
            empty(NO_PLAN if initialised() else f"{NO_PLAN}. {NOT_INIT}")

    from .plan_cli import NO_PLAN, NOT_INIT, register

    def initialised() -> bool:
        db = root() / ".graphene" / "graphene.db"
        if not db.exists():
            return False
        with open_store(root()) as store:
            return store.meta("plan_first") is not None

    plan_or_nothing = register(cli, root, open_store, fail)  # first: talk adds two commands to `plan`
    from .board_cli import register as board

    board(cli, root, open_store, fail)
    from .direction_cli import register as direction

    direction(cli, root, open_store, fail)
    from .talk import register as talk

    talk(cli, root, open_store, fail)

    from . import config_cli, extra
    from . import settings as S

    config_cli.register(cli, root, open_store, fail)
    if key_cli := extra.load("key_cli"):  # `graphene key`: the Nemotron extra's, when it is installed
        key_cli.register(cli, fail)

    WHO = ("planner", "executor")
    # what init looks for, by name, so that none comes first: the `--with` word, its name, what it needs
    AGENTS = (("claude", "Claude Code", "claude on the PATH"), ("codex", "Codex", "codex on the PATH"),
              ("nemotron", "Nemotron on Token Factory", "NEBIUS_API_KEY"))  # fmt: skip

    def unreadable(command: str) -> str | None:
        """Why a planner or an executor cannot be started as written (`--with` splits it as a shell does)."""
        try:
            words = shlex.split(command)
        except ValueError as no:
            return f"{command!r} cannot be read as a command: {no}"
        return extra.MISSING if words[:1] == ["nemotron"] and not key_cli else None

    def asked_once(offer: dict[str, str], said: str, now: dict, found: list, agents) -> dict[str, str]:
        """At a terminal: each choice by name, with what it needs and whether it was found here. Enter
        keeps what is set; with nothing set it takes the one choice found, when exactly one is, and
        otherwise a number is typed (any of them: what is not found yet can still be chosen). A command
        of your own that cannot be read is said so, and asked again."""
        kept = any(now.values())
        if kept:
            say(" · ".join(f"{k} now: {now[k] or 'not chosen'}" for k in WHO))
        say("which planner and executor for this repo?")
        own = str(len(agents) + 1)
        picks = {own: {}}
        for n, (word, name, needs) in enumerate(agents, 1):
            picks[str(n)] = offer if word == "nemotron" else dict.fromkeys(WHO, word)
            # Nemotron is listed only with a key: not found, it did not answer, as the line above says
            state = "found" if word in found else "not reached" if word == "nemotron" else "not found"
            say(f"  {n}  {name:<27}needs {needs:<20}{state}")
            if word == "nemotron":  # what Nemotron would be, under its line
                where = "each in a Sandbox" if offer["executor"].endswith("sandbox") else "on this machine"
                say(f"     {said}, {where}")
        say(f"  {own}  {'a command of your own':<27}that takes the prompt last")
        one = [str(n) for n, (word, _, _) in enumerate(agents, 1) if word in found]
        default = one[0] if len(one) == 1 and not kept else ""
        if kept:
            picks[""] = {}
        ask = "choose (Enter keeps them)" if kept else "choose"
        while (picked := typer.prompt(ask, default=default, show_default=bool(default))) not in picks:
            say(f"choose {', '.join(map(str, range(1, len(agents) + 1)))} or {own}")
        if picked != own:
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
        offer, said, unreached, found, placed = {}, "", None, [], None
        keys = extra.load("keys")
        key = bool(keys) and keys.find() is not None  # the environment's, or the keychain's
        agents = AGENTS if key else AGENTS[:2]  # Nemotron is offered with the extra and a key, not before
        named = any(v.split()[:1] == ["nemotron"] for v in given.values())
        if asking or missing or named:
            if key or named:
                offer, said, unreached, placed = key_cli.offer()
            if unreached and key:  # a key that did not answer: before the choice
                say(unreached)
            found = [w for w, _, _ in agents if (not unreached if w == "nemotron" else shutil.which(w))]
        if asking:
            given = asked_once(offer, said, now, found, agents)
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
                    "then `run` and `ask` refuse")  # fmt: skip
            given = {**{k: one[k] for k in missing if one}, **given, **plain}
        if unreached and not key and named:  # chosen: what it needs, once
            say(unreached)
        if placed and offer and given.get("executor") == offer["executor"]:  # the offer, placed here: why
            say(placed)
        for k, v in given.items():
            store.set_meta(k, v)
        told = " · ".join(f"{k}: {store.meta(k) or 'not chosen'}" for k in WHO)
        return f"{told}  (`graphene init` changes them; --with changes one command)"

    @cli.command()
    def init(
        planner: str = typer.Option(None, help="The planner: claude, codex, nemotron or a command."),
        executor: str = typer.Option(None, help="The executor: claude, codex, nemotron or a command."),
    ) -> None:
        """Pick a planner and an executor, and install the Claude Code hooks.

        Run it once per repo. At a terminal it asks; --planner and --executor choose without asking."""
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
            specs = [store.meta(k) or "claude" for k in WHO]  # none chosen: the person's own Claude Code
            if store.meta("plan_first") is None:  # a repository set up for Graphene plans first
                store.set_meta("plan_first", "auto")
            for k in (*S.GLOBS, "never", "size"):  # each setting's default, so `graphene config` has it
                if store.meta(f"settings:{k}") is None:
                    store.set_meta(f"settings:{k}", "auto" if k == "size" else "[]")
        say(chosen)
        try:
            added = install_hooks(r)
        except ValueError as exc:
            fail(f"cannot update {SETTINGS}: {exc}", 1)
        settings = Path(os.path.relpath(hooks_file(r), Path.cwd()))
        say("plan first is auto: every ask is proposed first; one small leaf is yours at once, more waits")
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
        say("next: `graphene ask '<what you want>'` proposes a plan; `graphene watch` shows it")
        if shutil.which("graphene") is None:
            console.print(
                "[yellow]warning:[/yellow] `graphene` is not on PATH, so the hook will not run. "
                "Install it with `uv tool install graphene-map` (or `--editable .`)."
            )

    ingest = typer.Typer(help="Record what an agent did.\n\nThe installed hooks call this. Nobody types it.")
    cli.add_typer(ingest, name="ingest", hidden=True)

    @ingest.command("hook")
    def ingest_hook() -> None:
        """Read one hook event from stdin.

        The installed hooks call this."""
        from .hooks import hook_main

        raise typer.Exit(hook_main())

    return cli
