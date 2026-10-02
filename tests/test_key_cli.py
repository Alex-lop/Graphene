"""`graphene key set|check|remove` are the person's: an agent is refused before the keychain is
touched, the key is read from a hidden prompt, and its value never appears in any output."""

import importlib.util
import sys
import types
from types import SimpleNamespace

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
    assert "Sandboxes" not in done.output  # refused before ConTree's whoami is asked
    assert keychain == {"key": SECRET}


def test_check_that_does_not_reach_exits_1_and_names_key_set(keychain, monkeypatch):
    """Walk 2026-09-28: `key check` with no key exited 0 and never named `graphene key set`."""
    line = "Token Factory: not reached: NEBIUS_API_KEY is not set: Token Factory needs a key"
    monkeypatch.setattr(keys, "reached", lambda: line)
    done = key("check")
    assert done.exit_code == 1
    assert line in done.output and "graphene key set" in done.output
    assert "GRAPHENE_KEYCHAIN=off" in done.output  # the conftest turns it off, and the line says so


PROJECT = "proj-planted-0042"
ABOUT = "tokenfactory.nebius.com/sandboxes/about"
REFUSED = (
    "Sandboxes: refused the key and project together (403): check NEBIUS_PROJECT_ID is this "
    f"key's project (Project settings, Copy project ID), or access is not granted yet ({ABOUT})"
)


def whoami(monkeypatch, answer):
    """contree-sdk's ContreeSync, a stub whose whoami returns ``answer()`` (nothing is sent), with a key and
    a project in the environment that no line may show."""
    contree_sdk = pytest.importorskip("contree_sdk")
    monkeypatch.setattr(contree_sdk, "ContreeSync", lambda token=None: SimpleNamespace(
        get_token_info=lambda refresh=False: answer()))  # fmt: skip
    monkeypatch.setenv("NEBIUS_API_KEY", SECRET)
    monkeypatch.setenv("NEBIUS_PROJECT_ID", PROJECT)


def raises(name: str, **fields):
    def answer():
        from contree_sdk.sdk import exceptions

        raise getattr(exceptions, name)(**fields)

    return answer


def grants(**given):
    return lambda: SimpleNamespace(permissions={"import": True, "list": True, "spawn": True, **given})


@pytest.mark.parametrize("answer, line", [
    (grants(cancel=False), "Sandboxes: work (import, list and spawn granted)"),
    (grants(spawn=False, **{"import": False}),
     f"Sandboxes: this project lacks import, spawn (request access at {ABOUT})"),
    (raises("ForbiddenError"), REFUSED),
    (raises("ForbiddenError", error=f"project {PROJECT} has no\nSandboxes access; token {SECRET}"),
     REFUSED + "; ConTree said: project … has no Sandboxes access; token …"),
    (raises("ApiStatusCodeError", status=401, error=f"bad token {SECRET}"),
     "Sandboxes: the key was not accepted (401)"),
    (raises("ContreeTransportError", error="[Errno 8] nodename nor servname provided"),
     "Sandboxes: could not be reached (ContreeTransportError: [Errno 8] nodename nor servname provided)"),
    (raises("ApiStatusCodeError", status=502, error=f"Bad Gateway. Project: {PROJECT}"),
     "Sandboxes: could not be reached (ApiStatusCodeError 502: Bad Gateway. Project: …)"),
    (raises("ApiTimeoutError", timeout_type="connect"),
     "Sandboxes: could not be reached (ApiTimeoutError: connect)"),
])  # fmt: skip
def test_check_says_in_one_line_what_state_sandboxes_are_in(keychain, monkeypatch, answer, line):
    """Alex's whoami came back Forbidden (2026-09-29): `key check` says Sandboxes' state from ConTree's
    whoami, a read that spends nothing, under Token Factory's line, never with the key or the project id;
    Sandboxes are optional, so the exit status stays Token Factory's."""
    whoami(monkeypatch, answer)
    done = key("check")
    assert done.exit_code == 0, done.output
    assert done.output.splitlines() == ["Token Factory: reached, 3 NVIDIA models (0)", line]
    assert (done.output + done.stderr).count(SECRET) + (done.output + done.stderr).count(PROJECT) == 0


def test_check_says_when_sandboxes_are_not_set_up_here(keychain, monkeypatch, tmp_path):
    if importlib.util.find_spec("contree_sdk") is None:  # the `sandbox` extra is not installed here
        monkeypatch.setitem(sys.modules, "contree_sdk", types.ModuleType("contree_sdk"))
    monkeypatch.setenv("NEBIUS_API_KEY", SECRET)  # a key, and no project and no profile (the conftest's)
    done = key("check")
    assert done.exit_code == 0
    assert done.output.splitlines()[1:] == [
        "Sandboxes: not configured (no NEBIUS_PROJECT_ID and no contree auth profile)"]  # fmt: skip
    monkeypatch.setitem(sys.modules, "contree_sdk", None)  # import contree_sdk raises ImportError
    monkeypatch.setenv("NEBIUS_PROJECT_ID", PROJECT)
    done = key("check")
    assert done.output.splitlines()[1:] == ["Sandboxes: the SDK is not installed (uv sync --extra sandbox)"]


def test_a_profiles_project_and_token_are_not_said_either(keychain, monkeypatch, tmp_path):
    """Signed in with a `contree auth` profile alone, ConTree's reason is said without the profile's
    project id or token, as it is without the environment's."""
    token = "eyJhbGciOiJIUzI1NiJ9.profile-token"
    whoami(monkeypatch, raises("ForbiddenError", error=f"project {PROJECT} token {token}: no access"))
    for name in ("NEBIUS_API_KEY", "NEBIUS_PROJECT_ID"):
        monkeypatch.delenv(name)
    home = tmp_path / "contree"
    home.mkdir()
    (home / "auth.ini").write_text(f"[profile:default]\ntoken = {token}\nproject = {PROJECT}\n")
    monkeypatch.setenv("CONTREE_HOME", str(home))
    done = key("check")
    assert done.output.splitlines()[1] == REFUSED + "; ConTree said: project … token …: no access"
