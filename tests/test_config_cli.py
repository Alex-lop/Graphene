# ruff: noqa: F811  (pytest fixtures imported from test_plan_cli are named again as arguments)
"""`graphene config` shows the settings and `graphene config edit` changes them through the person's
$EDITOR: every setting written and read back, a bad line refused by its number with nothing applied,
and an agent refused before any editor opens."""

import sys
from pathlib import Path

import pytest
import typer
from test_plan_cli import AGENT_ENV, repo, runner  # noqa: F401  (fixtures)

from graphene_map import config_cli
from graphene_map import plan as P
from graphene_map import settings as S
from graphene_map.store import Store

PERSON = {"GRAPHENE_AS": "person:alex"}


@pytest.fixture(autouse=True)
def no_agent_marks(monkeypatch):
    """These tests may themselves run under an agent (`graphene run` marks its executor's shell)."""
    for name in (*P.AGENT_MARKS, "CODEX_SESSION_ID", "CODEX_SANDBOX"):
        monkeypatch.delenv(name, raising=False)


def app() -> typer.Typer:
    cli = typer.Typer()

    @cli.callback()
    def main() -> None: ...

    def fail(message: str, code: int = 2) -> None:
        typer.echo(message, err=True)
        raise typer.Exit(code)

    config_cli.register(cli, Path.cwd, Store.open, fail)
    return cli


def config(*args, env=PERSON):
    return runner.invoke(app(), ["config", *args], env=env)


def editor(monkeypatch, tmp_path, python: str) -> None:
    """$EDITOR as a script that rewrites the file: `text` holds what the person sees."""
    script = tmp_path / "edit.py"
    script.write_text(
        f"import sys\np = sys.argv[1]\ntext = open(p).read()\n{python}\nopen(p, 'w').write(text)\n"
    )
    monkeypatch.setenv("EDITOR", f"{sys.executable} {script}")
    monkeypatch.delenv("VISUAL", raising=False)


def stored(repo):
    with Store.open(repo) as store:
        return S.protected(store), S.readonly(store), S.never(store), S.size(store)


def test_config_prints_the_settings_as_rendered(repo):
    shown = config()
    assert shown.exit_code == 0, shown.output
    with Store.open(repo) as store:
        assert shown.stdout == S.render(store) + "# the Token Factory key: none found (graphene key set)\n"
    assert "size: auto\n" in shown.stdout


def test_the_settings_made_elsewhere_are_shown_and_a_save_leaves_them_alone(repo):
    with Store.open(repo) as store:
        store.set_meta("planner", "codex")
        P.set_plan_first(store, "off", P.caller(env=PERSON))
        said = S.render(store)
        assert "# planner: codex (graphene init --planner)" in said
        assert "# executor: none chosen" in said
        assert "# plan first: off (graphene plan first on|auto|off)" in said
        S.apply(store, said.replace("size: auto", "size: finer"), P.caller(env=PERSON))
        assert (store.meta("planner"), P.plan_first(store), S.size(store)) == ("codex", "off", "finer")


def test_every_setting_is_written_by_edit_and_shown_back(repo, monkeypatch, tmp_path):
    editor(
        monkeypatch,
        tmp_path,
        "text = text.replace('size: auto\\n', 'protected: vendor/**, .env\\nreadonly: docs/**\\n"
        "never: add a dependency\\nsize: finer\\n')",
    )
    edited = config("edit")
    assert edited.exit_code == 0, edited.output
    assert "size: finer" in edited.stdout and "never: add a dependency" in edited.stdout
    # walk 2026-09-28: the added line was printed bare, so it read as echoed rather than added
    assert "added: protected: vendor/**, .env" in edited.stdout.splitlines()
    assert stored(repo) == (["vendor/**", ".env"], ["docs/**"], ["add a dependency"], "finer")
    shown = config().stdout
    for line in ("protected: vendor/**, .env", "readonly: docs/**", "never: add a dependency", "size: finer"):
        assert line in shown
    assert not list((repo / ".graphene" / "edits").iterdir())


def test_a_setting_left_out_is_cleared(repo, monkeypatch, tmp_path):
    with Store.open(repo) as store:
        S.apply(
            store, "protected: vendor/**\nreadonly: docs/**\nnever: x\nsize: coarser\n", P.caller(env=PERSON)
        )
    editor(monkeypatch, tmp_path, "text = '\\n'.join(l for l in text.splitlines() if l.startswith('#'))")
    assert config("edit").exit_code == 1  # no setting line at all: taken as a slip, nothing is applied
    assert stored(repo) == (["vendor/**"], ["docs/**"], ["x"], "coarser")
    editor(monkeypatch, tmp_path, "text = 'size: auto\\n'")
    edited = config("edit")
    assert edited.exit_code == 0
    assert stored(repo) == ([], [], [], "auto")
    for line in ("protected: vendor/**", "readonly: docs/**", "never: x", "size: coarser"):
        assert f"removed: {line}" in edited.stdout  # a removal is said, as an addition is


def test_a_bad_line_is_refused_by_its_number_and_nothing_is_applied(repo, monkeypatch, tmp_path):
    editor(monkeypatch, tmp_path, "text = text.replace('size: auto\\n', 'protected: a/**\\nsize: huge\\n')")
    before = config().stdout
    edited = config("edit")
    assert edited.exit_code == 1
    lines = before.replace("size: auto\n", "protected: a/**\nsize: huge\n").splitlines()
    no = lines.index("size: huge") + 1
    assert f"line {no}: size is auto, finer or coarser, not 'huge'" in edited.stderr
    assert "your text is kept in" in edited.stderr
    assert stored(repo) == ([], [], [], "auto")  # the good line before it was not written either
    assert config().stdout == before


def test_an_unchanged_save_changes_nothing(repo, monkeypatch, tmp_path):
    editor(monkeypatch, tmp_path, "")
    edited = config("edit")
    assert edited.exit_code == 0 and "nothing changed" in edited.stdout
    assert not list((repo / ".graphene" / "edits").iterdir())


def test_an_agent_cannot_edit_and_no_editor_opens(repo, monkeypatch, tmp_path):
    editor(monkeypatch, tmp_path, "open('opened', 'w').write('yes')")
    edited = config("edit", env=AGENT_ENV)
    assert edited.exit_code == 1
    assert "is the person's to do" in edited.stderr
    assert not (repo / "opened").exists()
    assert config(env=AGENT_ENV).exit_code == 0  # anyone may read them


def test_a_save_from_a_text_another_writer_has_since_changed_is_refused(repo, monkeypatch, tmp_path):
    other = (
        "from graphene_map import settings as S, plan as P\n"
        "from graphene_map.store import Store\n"
        f"with Store.open(__import__('pathlib').Path({str(repo)!r})) as st:\n"
        "    S.apply(st, 'protected: secrets/**\\n', P.Caller('alex', True))\n"
        "text = text.replace('size: auto\\n', 'never: add a dependency\\nsize: auto\\n')"
    )
    editor(monkeypatch, tmp_path, other)
    edited = config("edit")
    assert edited.exit_code == 1 and "changed by someone else" in edited.stderr
    assert "protected: secrets/**" in edited.stderr  # what they say now, so it can be kept
    assert stored(repo) == (["secrets/**"], [], [], "auto")


def test_a_new_protected_path_names_the_leaves_whose_scope_now_covers_it(repo, monkeypatch, tmp_path):
    with Store.open(repo) as store:
        leaf = {"id": "tv", "title": "t", "scope": ["*.py"], "check": "true"}
        P.propose(store, [leaf], P.caller(env=PERSON))
    python = "text = text.replace('\\nsize: auto\\n', '\\nprotected: api.py\\nsize: auto\\n')"
    editor(monkeypatch, tmp_path, python)
    edited = config("edit")
    assert edited.exit_code == 0, edited.output
    assert "tv: its scope (*.py) now covers api.py" in edited.stdout
    assert "graphene plan edit tv" in edited.stdout
