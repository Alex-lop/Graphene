"""`graphene config` and `graphene key` are on the command line; init writes each setting's default when
it is not set yet, and a key in the keychain counts as a key when init looks for Nemotron."""

import pytest
from test_init import NEMOTRON, chosen, fake, on_path  # noqa: F401  (fixtures)
from test_plan_cli import person, repo, runner  # noqa: F401  (fixtures)

from graphene_map.cli import build
from graphene_map.nemotron import keys
from graphene_map.nemotron import tokenfactory as tf
from graphene_map.store import Store

# ruff: noqa: F811  (pytest fixtures imported from test_init and test_plan_cli are named again as arguments)


def test_config_and_key_are_commands():
    for command in ("config", "key"):
        said = runner.invoke(build(), [command, "--help"])
        assert said.exit_code == 0, said.output


@pytest.mark.parametrize("argv", [["check"], ["remove"], [], ["set", "--"]])
def test_a_key_pasted_after_any_key_command_is_never_echoed(argv):
    said = runner.invoke(build(), ["key", *argv, "sk-SECRET-111"], env={"GRAPHENE_AS": "person:alex"})
    assert said.exit_code != 0 and "sk-SECRET" not in said.output, said.output


def test_init_writes_each_default_and_keeps_what_is_set(repo):
    assert person("init", "--planner", "claude", "--executor", "claude").exit_code == 0
    with Store.open(repo) as store:
        assert {k: store.meta(f"settings:{k}") for k in ("protected", "readonly", "never", "size")} == {
            "protected": "[]", "readonly": "[]", "never": "[]", "size": "auto",
        }  # fmt: skip
        store.set_meta("settings:size", "finer")
    assert person("init").exit_code == 0
    shown = person("config").output
    assert "size: finer" in shown


def test_a_key_in_the_keychain_is_found(repo, fake, on_path, monkeypatch):
    on_path()
    monkeypatch.delenv("NEBIUS_API_KEY")
    monkeypatch.setattr(keys, "find", lambda: "fake-key")  # the keychain's, not the environment's
    assert person("init").exit_code == 0
    assert chosen(repo) == NEMOTRON


def test_a_key_in_the_keychain_that_is_not_reached_is_said(repo, on_path, monkeypatch):
    on_path("claude")
    monkeypatch.setattr(keys, "find", lambda: "a-key")
    monkeypatch.setenv("GRAPHENE_TOKENFACTORY_URL", "http://127.0.0.1:9/v1/")  # nothing listens there
    monkeypatch.setattr(tf, "_sleep", lambda s: pytest.fail("init waited to try Token Factory again"))
    tf._listed.cache_clear()
    said = person("init")
    assert "Token Factory could not be reached at http://127.0.0.1:9/v1/" in said.output  # said: a key
    assert chosen(repo) == {"planner": "claude", "executor": "claude"}
