"""Red first in core (graphene_map.precheck): every accepted leaf's check run once at the base commit,
with no model. The verdict is passes, outside or red, read from the exit code and the output."""

import json
import shlex
import subprocess
import sys

import pytest

from graphene_map import plan as P
from graphene_map import precheck as K
from graphene_map.store import Store

ME = P.Caller("alex", True)
BOT = P.Caller("planner:claude", False, "s1")
FAILS = "python3 -c 'import sys; sys.exit(1)'"


def git(repo, *args):
    subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True)


@pytest.fixture
def repo(tmp_path, monkeypatch):
    for name in ("CLAUDECODE", "CLAUDE_CODE_SESSION_ID", "AI_AGENT", "GRAPHENE_AS"):
        monkeypatch.delenv(name, raising=False)
    for args in (["init", "-q"], ["config", "user.email", "t@e.com"], ["config", "user.name", "T"]):
        git(tmp_path, *args)
    (tmp_path / ".gitignore").write_text(".graphene/\n")
    (tmp_path / "tests").mkdir()
    (tmp_path / "app.py").write_text("x = 1\n")
    (tmp_path / "tests" / "test_other.py").write_text("assert False, 'other is broken'\n")
    git(tmp_path, "add", "-A")
    git(tmp_path, "commit", "-qm", "start")
    monkeypatch.chdir(tmp_path)
    return tmp_path


def leaves(store, *specs, who=ME):
    P.propose(store, [{"id": i, "title": i, "scope": s, "check": c} for i, s, c in specs], who)


def test_a_check_that_passes_at_base_is_a_passes_row_with_its_why(repo):
    with Store.open(repo) as store:
        leaves(store, ("a", ["new.py"], "true"))
        [(_, d)] = K.run(store, repo)
        [row] = store.node_log("a", ("precheck",))
    assert d["verdict"] == "passes" and d["why"] == "it exits 0 before any work is done"
    assert row["detail"] == d and d["exit"] == 0 and d["paths"] == [] and d["base"] and d["tree"]


def test_a_check_failing_for_the_file_its_leaf_writes_is_red_and_says_nothing(repo):
    with Store.open(repo) as store:
        leaves(store, ("a", ["new.py"], "python3 new.py"))
        rows = K.run(store, repo)
    [(_, d)] = rows
    assert d["verdict"] == "red" and d["paths"] == []
    assert [line for line in K.said(rows) if not line.startswith("red first")] == []


def test_a_failing_tracked_file_outside_the_scope_is_outside_with_that_path(repo):
    with Store.open(repo) as store:
        leaves(store, ("a", ["new.py"], "python3 tests/test_other.py"))
        rows = K.run(store, repo)
    [(_, d)] = rows
    assert d["verdict"] == "outside" and d["paths"] == ["tests/test_other.py"]
    assert K.said(rows)[0].startswith("a: its check names tests/test_other.py, outside its scope, at ")


def test_a_check_naming_another_leafs_new_test_file_is_outside(repo):
    with Store.open(repo) as store:
        leaves(store, ("a", ["new.py"], "python3 tests/test_new.py"), ("b", ["tests/test_new.py"], "true"))
        rows = {n.id: d for n, d in K.run(store, repo)}
    assert rows["a"]["verdict"] == "outside" and rows["a"]["paths"] == ["tests/test_new.py"]


def test_a_kept_verdict_is_not_run_again_but_a_commit_or_an_edited_check_runs_it(repo, monkeypatch):
    asked = []
    monkeypatch.setattr(K, "_here", lambda command, root, committed: asked.append(command) or (0, ""))
    with Store.open(repo) as store:
        leaves(store, ("a", ["new.py"], "true"))
        K.run(store, repo)
        [(_, kept)] = K.run(store, repo)
        assert asked == ["true"] and kept["kept"] and len(store.node_log("a", ("precheck",))) == 1
        (repo / "app.py").write_text("x = 2\n")
        git(repo, "commit", "-qam", "next")
        K.run(store, repo)
        assert asked == ["true", "true"]
        P.edit(store, "a", {"check": "true && true"}, ME)
        K.run(store, repo)
        assert asked == ["true", "true", "true && true"]
        K.run(store, repo, again=True)
        assert len(asked) == 4


def test_two_leaves_with_one_check_run_it_once_and_a_proposed_leaf_is_skipped(repo, monkeypatch):
    asked = []
    monkeypatch.setattr(K, "_here", lambda command, root, committed: asked.append(command) or (1, "nope"))
    with Store.open(repo) as store:
        leaves(store, ("a", ["a.py"], FAILS), ("b", ["b.py"], FAILS))
        leaves(store, ("p", ["p.py"], "false"), who=BOT)
        rows = K.run(store, repo)
        assert [n.id for n, _ in rows] == ["a", "b"] and asked == [FAILS]
        assert store.node_log("p", ("precheck",)) == []


def test_the_header_line_has_the_count_the_commit_and_the_wall_time(repo):
    with Store.open(repo) as store:
        leaves(store, ("a", ["a.py"], "true"), ("b", ["b.py"], "false"))
        rows = K.run(store, repo)
    lines = K.said(rows)
    assert lines[0].startswith("a: its check passes at the base commit ")
    assert "`graphene node set a --check" in lines[0]
    assert lines[-1].startswith("red first: 2 checks at ") and lines[-1].endswith(" s")
    assert f" in {rows.seconds:.0f} s" in lines[-1]


def test_a_check_that_runs_its_own_new_test_and_a_passing_outside_one_is_red_not_outside(repo):
    (repo / "tests" / "test_fine.py").write_text("print('fine')\n")
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", "a test that passes")
    with Store.open(repo) as store:
        both = "python3 tests/test_fine.py && python3 tests/test_new.py"
        leaves(store, ("a", ["new.py", "tests/test_new.py"], both))
        [(_, d)] = K.run(store, repo)
    assert d["verdict"] == "red" and d["paths"] == []  # its own test is what is missing


def test_a_check_whose_output_names_a_failing_outside_file_is_outside_by_the_output(repo):
    with Store.open(repo) as store:
        both = "python3 tests/test_other.py && python3 tests/test_new.py"
        leaves(store, ("a", ["new.py", "tests/test_new.py"], both))
        [(_, d)] = K.run(store, repo)
    assert d["verdict"] == "outside" and d["paths"] == ["tests/test_other.py"]


def test_the_whole_suite_is_outside_by_the_file_that_fails(repo, monkeypatch):
    (repo / "tests" / "__init__.py").write_text("")
    (repo / "tests" / "test_other.py").write_text("def test_other():\n    assert False, 'other is broken'\n")
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", "a suite with one failing test")
    monkeypatch.setenv("PATH", "/usr/bin:/bin")  # a python3 there may have no pytest: this one does
    with Store.open(repo) as store:
        leaves(store, ("a", ["new.py", "tests/test_new.py"], f"{shlex.quote(sys.executable)} -m pytest -q"))
        [(_, d)] = K.run(store, repo)
    assert d["verdict"] == "outside" and d["paths"] == ["tests/test_other.py"]


def test_a_check_whose_output_is_not_utf8_is_judged_here_and_at_done(repo):
    """Its bytes broke the reading: the check that passed was "could not be run", and `node done` raised."""
    with Store.open(repo) as store:
        leaves(store, ("a", ["new.py"], "printf 'caf\\351'"))
        [(_, d)] = K.run(store, repo)
    assert d["verdict"] == "passes"
    assert P.run_check("printf 'caf\\351'; exit 1", repo)[:2] == (False, "caf�")


@pytest.mark.parametrize("why, runs", [("timed out after 1800 s", 1), ("could not be run: no git", 2)])
def test_a_check_not_run_to_its_end_is_said_and_one_that_timed_out_is_kept(repo, monkeypatch, why, runs):
    """A check that hangs at the base made every run wait CHECK_TIMEOUT again, and said nothing of it."""
    asked = []
    monkeypatch.setattr(K, "_here", lambda command, root, committed: asked.append(command) or (None, why))
    with Store.open(repo) as store:
        leaves(store, ("hang", ["new.py"], "sleep 9999"))
        rows = K.run(store, repo)
        K.run(store, repo)
    assert len(asked) == runs and K.said(rows)[0] == f"hang: its check at {rows[0][1]['base'][:7]} {why}"


def test_a_failing_file_named_like_a_key_is_outside_all_the_same(repo, monkeypatch):
    """The output was hidden before it was judged: the hider took the file's name, and it read as red."""
    (repo / "tests" / "__init__.py").write_text("")
    (repo / "tests" / "test_other.py").unlink()
    (repo / "tests" / "test_OAuth2CallbackHandlerV2.py").write_text("def test_cb():\n    assert False\n")
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", "a suite whose failing file is named like a key")
    monkeypatch.setenv("PATH", "/usr/bin:/bin")
    with Store.open(repo) as store:
        leaves(store, ("a", ["new.py", "tests/test_new.py"], f"{shlex.quote(sys.executable)} -m pytest -q"))
        [(_, d)] = K.run(store, repo)
    assert d["verdict"] == "outside" and "OAuth2" not in str(d)


def test_leaves_with_one_check_that_passes_are_one_line_and_the_header_counts_the_commands(repo):
    with Store.open(repo) as store:
        leaves(store, ("a", ["a.py"], "true"), ("b", ["b.py"], "true"), ("c", ["c.py"], "true"))
        rows = K.run(store, repo)
    first, header = K.said(rows)
    assert first.startswith("a, b, c: their check passes at the base commit ") and "proves nothing" in first
    assert header.startswith("red first: 3 checks at ") and " (1 command) in " in header


@pytest.mark.parametrize("check", ["nosuchtool-zz --version", "python3 -m pytest -q tests"])
def test_a_check_this_environment_cannot_run_is_said_so_and_its_gist_kept(repo, check, monkeypatch):
    """Red first read `python3 -m pytest` with pytest missing as a red, or as outside: by its output."""
    monkeypatch.setenv("PATH", "/usr/bin:/bin")  # the system python3, which has no pytest; git is there
    with Store.open(repo) as store:
        leaves(store, ("a", ["new.py"], check))
        rows = K.run(store, repo)
    [(_, d)] = rows
    assert d["verdict"] == "environment" and d["gist"] and d["why"] in K.said(rows)[0]
    assert K.said(rows)[0].startswith("a: its check cannot run here: ")
    assert "nothing git ignores" in K.said(rows)[0]


def test_a_check_that_could_not_run_here_is_asked_again_once_the_person_installs_what_it_runs(
    repo, tmp_path_factory, monkeypatch
):
    """An "environment" verdict was kept until a commit or an edit: installed, the tool was still said to
    be missing, and the person was told the fix had not worked."""
    monkeypatch.setenv("PATH", "/usr/bin:/bin")
    with Store.open(repo) as store:
        leaves(store, ("a", ["new.py"], "zzprobe-tool --version"))
        [(_, first)] = K.run(store, repo)
        bin_ = tmp_path_factory.mktemp("bin")
        (bin_ / "zzprobe-tool").write_text("#!/bin/sh\nexit 1\n")
        (bin_ / "zzprobe-tool").chmod(0o755)
        monkeypatch.setenv("PATH", f"{bin_}:/usr/bin:/bin")  # the person installs it
        [(_, again)] = K.run(store, repo)
    assert first["verdict"] == "environment" and not again.get("kept") and again["verdict"] == "red"


def test_a_check_that_cannot_run_here_is_not_run_and_exits_as_the_shell_would(repo):
    """The Nemotron extra's precheck runs an accepted check through `_here` too: no exit code there is a
    not-run, run again at every precheck; 127, the shell's for what it cannot find, is its kept cannot-run."""
    assert K._here("nosuchtool-zz --version", repo) == (127, "cannot run here: nosuchtool-zz: not found")


def test_a_test_first_red_whose_module_the_leaf_writes_is_no_environment(repo):
    with Store.open(repo) as store:
        leaves(store, ("a", ["tests/test_nosuch_zz.py"], "python3 -m unittest tests.test_nosuch_zz"))
        rows = K.run(store, repo)
    [(_, d)] = rows
    assert d["verdict"] == "red" and d["gist"]  # every check that does not pass keeps its gist
    assert not [line for line in K.said(rows) if "cannot run here" in line]


def test_a_reopened_leaf_whose_check_passed_when_it_landed_is_landed_until_the_check_changes(repo):
    """A reopened leaf's check passes at the base by nature: it passed when the leaf landed."""
    from graphene_map import tui

    with Store.open(repo) as store:
        leaves(store, ("a", ["new.py"], "test -f new.py"))
        P.start(store, "a", ME, repo)
        (repo / "new.py").write_text("x = 1\n")
        P.finish(store, "a", ME)
        git(repo, "add", "-A")
        git(repo, "commit", "-qm", "a landed")
        P.reopen(store, "a", ME, "say why it is wrong")
        rows = K.run(store, repo)
        [(_, d)] = rows
        assert d["verdict"] == "landed" and tui.precheck(store, P.get(store, "a")) is None
        assert K.said(rows)[0].startswith("a: it passed this check when it landed; reopened, it passes until")
        assert not [line for line in K.said(rows) if "proves nothing" in line]
        P.edit(store, "a", {"check": "test -s new.py"}, ME)
        [(_, d)] = K.run(store, repo)
    assert d["verdict"] == "passes"


def test_a_check_that_passed_at_the_base_before_any_work_still_proves_nothing_once_reopened(repo):
    """'landed' was read from the leaf's history alone: `true`, which passed at the base before the leaf
    ever ran, read "it passed this check when it landed" once it finished and was reopened, and lost its ∅."""
    from graphene_map import tui

    with Store.open(repo) as store:
        leaves(store, ("a", ["new.py"], "true"))
        [(_, first)] = K.run(store, repo)
        P.start(store, "a", ME, repo)
        (repo / "new.py").write_text("x = 1\n")
        P.finish(store, "a", ME)
        git(repo, "add", "-A")
        git(repo, "commit", "-qm", "a landed")
        P.reopen(store, "a", ME, "wrong")
        rows = K.run(store, repo)
        [(_, d)] = rows
        assert first["verdict"] == d["verdict"] == "passes" and tui.precheck(store, P.get(store, "a"))
    assert "proves nothing" in K.said(rows)[0]


def test_a_reopened_leaf_done_again_on_its_landed_check_is_said_to_have_passed_at_the_base(repo):
    """Lane D's readers took only "passes": a reopened leaf done again on its unchanged check ("landed")
    lost its ∅, the merge's "passed at the base too" and the record's line, though nothing verified it."""
    from graphene_map import node_record as NR
    from graphene_map import run as R
    from graphene_map import tui

    with Store.open(repo) as store:
        leaves(store, ("a", ["new.py"], "test -f new.py"))
        P.start(store, "a", ME, repo)
        (repo / "new.py").write_text("x = 1\n")
        P.finish(store, "a", ME)
        git(repo, "add", "-A")
        git(repo, "commit", "-qm", "a landed")
        P.reopen(store, "a", ME, "it must also say y")
        [(_, d)] = K.run(store, repo)
        P.start(store, "a", ME, repo)
        (repo / "new.py").write_text("x = 2\n")
        P.finish(store, "a", ME)
        node = P.get(store, "a")
        assert d["verdict"] == "landed" and node.state == P.DONE
        assert tui.precheck(store, node) is not None
        assert "Check: `test -f new.py` passed, and it passed at the base too" in R._merged(store, node)
        assert NR._refusals(store.node_log("a")).at_base is not None


def test_a_review_leaf_keeps_its_mark_when_its_check_is_edited_since_nothing_ran_the_new_one(repo):
    """The mark was keyed on the check the leaf has now: `node set --check` on a leaf in review, which runs
    nothing, took the ∅ away, and signed off it was done with no mark, though nothing verified its work."""
    from graphene_map import tui

    bot = P.Caller("claude:aaaa1111", False, "aaaa1111-session")
    with Store.open(repo) as store:
        leaf = {"id": "a", "title": "a", "scope": ["new.py"], "check": "true", "signoff": "alex"}
        P.propose(store, [leaf], ME)
        K.run(store, repo)
        P.start(store, "a", bot, repo)
        (repo / "new.py").write_text("x = 1\n")
        P.finish(store, "a", bot)
        assert P.get(store, "a").state == P.REVIEW and tui.precheck(store, P.get(store, "a"))
        P.edit(store, "a", {"check": "test -s new.py"}, ME)
        assert tui.precheck(store, P.get(store, "a")) is not None
        P.signoff(store, "a", ME, checkout=repo)
        assert P.get(store, "a").state == P.DONE and tui.precheck(store, P.get(store, "a")) is not None


@pytest.mark.parametrize(
    "installed, check, named",
    [("editable", FAILS, True), ("elsewhere", FAILS, False), ("editable", "true", False),
     ("pth", FAILS, True)],  # fmt: skip
)
def test_a_python_with_this_repo_installed_editable_is_said(repo, tmp_path_factory, monkeypatch, installed,
                                                             check, named):  # fmt: skip
    """The person's venv had the project installed editable from their checkout: a check that imported it
    tested the checkout, whatever the leaf's worktree held, and passed at the base."""
    site = tmp_path_factory.mktemp("site")
    info = site / "fake_pkg-0.1.dist-info"
    info.mkdir()
    (info / "METADATA").write_text("Metadata-Version: 2.1\nName: fake_pkg\nVersion: 0.1\n")
    where = repo if installed != "elsewhere" else tmp_path_factory.mktemp("elsewhere")
    if installed == "pth":  # no direct_url.json: a path line, as an old `setup.py develop` leaves
        (site / "_fake_pkg.pth").write_text(f"{repo / 'src'}\n")
    else:
        said = {"url": where.as_uri(), "dir_info": {"editable": True}}  # PEP 610, as uv and pip write it
        (info / "direct_url.json").write_text(json.dumps(said))
    monkeypatch.setenv("PYTHONPATH", str(site))
    with Store.open(repo) as store:
        leaves(store, ("a", ["new.py"], check))
        rows = K.run(store, repo)
    said = [line for line in K.said(rows) if "installed editable from this repo" in line]
    assert len(said) == named and all("fake_pkg" in line and "`uv run pytest …`" in line for line in said)
