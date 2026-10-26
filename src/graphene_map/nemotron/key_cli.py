"""`graphene key set|check|remove [--endpoint nim|openai|ollama]`: an endpoint's key in the system keychain,
Token Factory's by default, for a person only (keys.py finds and keeps it). The key is read with a hidden
prompt, never from argv, and never printed."""

from __future__ import annotations

import shlex

import typer

from .. import plan as P
from . import keys

ENDPOINT = typer.Option("tokenfactory", "--endpoint", help="Whose key: tokenfactory, nim, ollama or openai.")


def register(cli: typer.Typer, fail):
    key_cli = typer.Typer(
        help="Keep the Token Factory key in the system keychain.\n\n"
        "Only a person can set, check or remove the key. --endpoint nim|openai keeps another host's."
    )
    cli.add_typer(key_cli, name="key", hidden=True)

    def person(what: str) -> None:
        try:
            P._person_only(P.caller(), what)
        except P.Refused as no:
            fail(str(no), 1)

    def which(endpoint: str):
        from . import tokenfactory as tf  # here: the CLI registers `key` without the client's imports

        if endpoint not in tf.ENDPOINTS:
            fail(f"no endpoint named {endpoint!r}: the endpoints are {', '.join(tf.ENDPOINTS)}")
        return tf.ENDPOINTS[endpoint]

    @key_cli.command("set")
    def set_(given: list[str] = typer.Argument(None, hidden=True), endpoint: str = ENDPOINT) -> None:
        """Keep the key in the keychain, read with a hidden prompt."""
        e = which(endpoint)
        person(f"setting the {e.host} key")
        if given:  # refused here, not by click, which would echo it back
            fail("the key is read from a hidden prompt, never from the command line: run `graphene key set`")
        key = typer.prompt(f"{e.host} key", hide_input=True)
        try:
            keys.set(key, e.account, e.host)
        except RuntimeError as no:
            fail(str(no), 1)
        typer.echo("the key is kept in the keychain")

    @key_cli.command()
    def check(endpoint: str = ENDPOINT) -> None:
        """Say whether Token Factory answers the key found.

        A Sandboxes check follows and spends nothing. The exit status is Token Factory's."""
        e = which(endpoint)
        person(f"checking the {e.host} key")
        from . import tokenfactory as tf

        with tf.using(endpoint):
            line = keys.reached()
            typer.echo(line)
            unreached = "not reached" in line
            if unreached and not keys.where(e.key_envs, e.account):
                off = "" if keys._keychain() else "; the keychain was not read (GRAPHENE_KEYCHAIN=off)"
                flag = "" if e.name == "tokenfactory" else f" --endpoint {e.name}"
                typer.echo(f"  no key found: `graphene key set{flag}` keeps one in the keychain{off}")
            if e.name == "tokenfactory":  # Sandboxes are Nebius's: no other host has them
                from . import sandbox  # asked here: no other command pays for its imports

                typer.echo(sandbox.says(*sandbox.whoami()))
        if unreached:
            raise typer.Exit(1)

    @key_cli.command()
    def remove(endpoint: str = ENDPOINT) -> None:
        """Take the key out of the keychain."""
        e = which(endpoint)
        person(f"removing the {e.host} key")
        try:
            keys.remove(e.account)
        except RuntimeError as no:
            fail(str(no), 1)
        typer.echo("the key is removed from the keychain")


def offer(endpoint: str | None = None) -> tuple[dict[str, str], str, str | None, str | None]:
    """Nemotron on Token Factory as a new repo is offered it (``endpoint``: another host, named in the
    specs), what that is in words, what could not be reached, in one line, or None, and why the leaves
    are not in Sandboxes though ConTree is set up here, or None. The ids are the live list's, so a run is
    reproducible and nothing is guessed: the largest of Ultra and Super plans (as planner.py picks when it
    runs), and the two smallest listed do the leaves, the second on a second attempt; in a Sandbox when
    ConTree is set up here and does not refuse the project, on this machine otherwise. A host with no
    Nemotron gets plain specs: the first model it lists does both, found when it runs. Out of reach it is
    plain `nemotron`, which finds its models when it runs. Asked once: offline, init must not wait."""
    from . import sandbox
    from . import tokenfactory as tf

    with tf.using(endpoint) as e:
        unreached = tf.reach(tries=1)
        listed = [] if unreached else tf.models(tries=1)
        found = tf.roles(listed)
    at = f" --endpoint {e.name}" if e.name != "tokenfactory" else ""
    plans = [s for s in ("ultra", "super") if s in found][:1]
    leaves = [s for s in ("nano", "super", "ultra") if s in found][:2]

    def models(sizes: list[str]) -> str:
        return "".join(f" --model {shlex.quote(found[s])}" for s in sizes)

    nebius = e.name == "tokenfactory"  # Sandboxes are Nebius's: another host's leaves run on this machine
    refused = sandbox.refused() if nebius and sandbox.configured() else None  # whoami: a read, no operation
    place = "sandbox" if nebius and sandbox.configured() and not refused else "local"
    ladder = f"nemotron{at}{models(leaves)} --placement {place}"
    if listed and not found:  # no Nemotron here: resolve() takes the first chat model listed, and says so
        first = tf.resolve([], "planner", listed)[0][0].rsplit("/", 1)[-1]
        said = f"{first} does both (no Nemotron listed)"
    else:
        planner = plans[0].title() if plans else "largest"
        does = " then ".join(s.title() for s in leaves) or "smallest"
        said = f"{planner} plans, {does} {'do' if leaves[1:] else 'does'} the leaves"
    if refused:
        refused += ("; the leaves run on this machine until `graphene key check` says Sandboxes work, "
                    "and `graphene init --executor nemotron` then places them there")  # fmt: skip
    return {"planner": f"nemotron{at}{models(plans)}", "executor": ladder}, said, unreached, refused
