"""`graphene key set|check|remove`: the Token Factory key in the system keychain, for a person only
(keys.py finds and keeps it). The key is read with a hidden prompt, never from argv, and never printed."""

from __future__ import annotations

import shlex

import typer

from .. import plan as P
from . import keys


def register(cli: typer.Typer, fail):
    key_cli = typer.Typer(help="The Token Factory key, kept in the system keychain (a person only).")
    cli.add_typer(key_cli, name="key")

    def person(what: str) -> None:
        try:
            P._person_only(P.caller(), what)
        except P.Refused as no:
            fail(str(no), 1)

    @key_cli.command("set")
    def set_(given: list[str] = typer.Argument(None, hidden=True)) -> None:
        """Keep the key in the keychain, read with a hidden prompt."""
        person("setting the Token Factory key")
        if given:  # refused here, not by click, which would echo it back
            fail("the key is read from a hidden prompt, never from the command line: run `graphene key set`")
        key = typer.prompt("Token Factory key", hide_input=True)
        try:
            keys.set(key)
        except RuntimeError as no:
            fail(str(no), 1)
        typer.echo("the key is kept in the keychain")

    @key_cli.command()
    def check() -> None:
        """Say whether the Token Factory is reached with the key found, and what state Sandboxes are in
        (ConTree's whoami, a read that spends nothing). Sandboxes are optional: the exit status is Token
        Factory's."""
        person("checking the Token Factory key")
        line = keys.reached()
        typer.echo(line)
        unreached = "not reached" in line
        if unreached and not keys.where():
            off = "" if keys._keychain() else "; the keychain was not read (GRAPHENE_KEYCHAIN=off)"
            typer.echo(f"  no key found: `graphene key set` keeps one in the keychain{off}")
        from . import sandbox  # asked here: no other command pays for its imports

        typer.echo(sandbox.says(*sandbox.whoami()))
        if unreached:
            raise typer.Exit(1)

    @key_cli.command()
    def remove() -> None:
        """Take the key out of the keychain."""
        person("removing the Token Factory key")
        try:
            keys.remove()
        except RuntimeError as no:
            fail(str(no), 1)
        typer.echo("the key is removed from the keychain")


def offer() -> tuple[dict[str, str], str, str | None, str | None]:
    """Nemotron on Token Factory as a new repo is offered it, what that is in words, what could not
    be reached, in one line, or None, and why the leaves are not in Sandboxes though ConTree is set
    up here, or None. The ids are the live list's, so a run is reproducible and nothing is guessed:
    the largest of Ultra and Super plans (as planner.py picks when it runs), and the two smallest
    listed do the leaves, the second on a second attempt; in a Sandbox when ConTree is set up here
    and does not refuse the project, on this machine otherwise. Out of reach it is plain `nemotron`,
    which finds its models when it runs. Asked once: offline, init must not wait."""
    from . import sandbox
    from . import tokenfactory as tf

    unreached = tf.reach(tries=1)
    found = {} if unreached else tf.roles(tf.models(tries=1))
    plans = [s for s in ("ultra", "super") if s in found][:1]
    leaves = [s for s in ("nano", "super", "ultra") if s in found][:2]

    def models(sizes: list[str]) -> str:
        return "".join(f" --model {shlex.quote(found[s])}" for s in sizes)

    refused = sandbox.refused() if sandbox.configured() else None  # whoami: a read, no operation
    place = "sandbox" if sandbox.configured() and not refused else "local"
    ladder = f"nemotron{models(leaves)} --placement {place}"
    planner = plans[0].title() if plans else "largest"
    does = " then ".join(s.title() for s in leaves) or "smallest"
    said = f"{planner} plans, {does} {'do' if leaves[1:] else 'does'} the leaves"
    if refused:
        refused += ("; the leaves run on this machine until `graphene key check` says Sandboxes work, "
                    "and `graphene init --executor nemotron` then places them there")  # fmt: skip
    return {"planner": f"nemotron{models(plans)}", "executor": ladder}, said, unreached, refused
