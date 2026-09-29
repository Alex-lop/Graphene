"""`graphene key set|check|remove` are the person's: an agent is refused before the keychain is
touched, the key is read from a hidden prompt, and its value never appears in any output."""

import pytest
import typer
from typer.testing import CliRunner

from graphene_map import key_cli, keys
from graphene_map import plan as P

SECRET = "tf-SECRET-0123456789"
PERSON = {"GRAPHENE_AS": "person:alex"}
runner = CliRunner()


@pytest.fixture(autouse=True)
def keychain(monkeypatch):
    """A keychain in a dict, and no agent marks from whatever runs these tests."""
    for name in (
        *P.AGENT_MARKS,
        "CODEX_SESSION_ID",
        "CODEX_SANDBOX",
        "CLAUDECODE",
        "CLAUDE_CODE_SESSION_ID",
        "AI_AGENT",
    ):
        monkeypatch.delenv(name, raising=False)
    kept: dict[str, str] = {}
    monkeypatch.setattr(keys, "set", lambda k: kept.__setitem__("key", k.strip()))
    monkeypatch.setattr(keys, "remove", lambda: kept.pop("key"))
    monkeypatch.setattr(keys, "reached", lambda: f"Token Factory: reached, 3 NVIDIA models ({len(kept)})")
    return kept


def app() -> typer.Typer:
    cli = typer.Typer()

    @cli.callback()
    def main() -> None: ...

    def fail(message: str, code: int = 2) -> None:
        typer.echo(message, err=True)
        raise typer.Exit(code)

    key_cli.register(cli, fail)
    return cli


def key(*args, env=PERSON, input=None):
    done = runner.invoke(app(), ["key", *args], env=env, input=input)
    assert SECRET not in done.output + (done.stderr or "")
    return done


def test_set_check_remove(keychain):
    done = key("set", input=SECRET + "\n")
    assert done.exit_code == 0, done.output
    assert keychain == {"key": SECRET}
    assert "reached, 3 NVIDIA models (1)" in key("check").output
    assert key("remove").exit_code == 0
    assert keychain == {}


def test_set_never_takes_the_key_from_argv(keychain):
    assert key("set", SECRET).exit_code != 0
    assert keychain == {}


def test_a_failure_says_why_without_the_key(keychain, monkeypatch):
    def refuse(k):
        raise RuntimeError("the key could not be kept: the keychain is off")

    monkeypatch.setattr(keys, "set", refuse)
    done = key("set", input=SECRET + "\n")
    assert done.exit_code == 1 and "keychain is off" in done.output


@pytest.mark.parametrize("mark", ["GRAPHENE_NODE", "GRAPHENE_PLANNER", "CLAUDECODE", "CODEX_SESSION_ID"])
@pytest.mark.parametrize("cmd", ["set", "check", "remove"])
def test_an_agent_is_refused(keychain, mark, cmd):
    keychain["key"] = SECRET
    done = key(cmd, env={**PERSON, mark: "key-cli"}, input=SECRET + "\n")
    assert done.exit_code == 1 and "person's to do" in done.output
    assert keychain == {"key": SECRET}


def test_check_that_does_not_reach_exits_1_and_names_key_set(keychain, monkeypatch):
    """Walk 2026-09-28: `key check` with no key exited 0 and never named `graphene key set`."""
    line = "Token Factory: not reached: NEBIUS_API_KEY is not set: Token Factory needs a key"
    monkeypatch.setattr(keys, "reached", lambda: line)
    done = key("check")
    assert done.exit_code == 1
    assert line in done.output and "graphene key set" in done.output
    assert "GRAPHENE_KEYCHAIN=off" in done.output  # the conftest turns it off, and the line says so
