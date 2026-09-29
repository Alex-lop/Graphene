"""`graphene key set|check|remove`: the Token Factory key in the system keychain, for a person only
(keys.py finds and keeps it). The key is read with a hidden prompt, never from argv, and never printed."""

from __future__ import annotations

import typer

from . import keys
from . import plan as P


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
