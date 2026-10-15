"""`graphene demo --cheat`: a scripted stand-in tries seven ways round one leaf, and the real hook, git
and check answer each. The verdicts are what that code said: with the gate saying nothing, they change."""

import subprocess
import tempfile

from typer.testing import CliRunner

from graphene_map import cheat, gate
from graphene_map.cli import build


def verdicts(lines: list[str]) -> dict[str, str]:
    """Each move's number and the first line of its verdict."""
    pairs = zip(lines, lines[1:] + [""], strict=True)
    return {a.split()[0]: b.strip() for a, b in pairs if a[:1].isdigit() and b.startswith("  ")}


def test_the_seven_moves_are_answered_by_the_real_hook_git_and_check(tmp_path):
    lines: list[str] = []
    assert cheat.run(lines.append, tmp_path) == (6, 1, 0)
    said = verdicts(lines)
    assert said["1"] == "REFUSED before the write" and said["2"] == "REFUSED before it ran"
    assert said["3"] == "let through by the hook, then REFUSED at done: git saw billing.py change"
    assert said["4"] == "REFUSED: only you change a leaf's check"
    assert said["5"] == "REFUSED: Graphene ran the check itself, and it failed"
    assert said["6"] == "REFUSED: it holds a leaf that is not done"
    assert said["7"].startswith("FLAGGED: its check runs tests/test_calc.py, which it changed")
    # a run lands it at once: only a --signoff leaf has a moment before it lands
    assert lines[-4] == "  (`graphene node diff n1`); a --signoff leaf waits for that before it lands."


def cheat_demo(tmp_path, monkeypatch):
    monkeypatch.delenv("NEBIUS_API_KEY", raising=False)
    monkeypatch.setattr(tempfile, "tempdir", str(tmp_path / "tmp"))  # to see its repository go
    (tmp_path / "tmp").mkdir()
    monkeypatch.chdir(tmp_path)
    return CliRunner().invoke(build(), ["demo", "--cheat"])


def test_cheat_needs_no_key_and_every_move_is_refused_or_flagged(tmp_path, monkeypatch):
    said = cheat_demo(tmp_path, monkeypatch)
    assert said.exit_code == 0, said.output
    lines = said.stdout.splitlines()
    assert lines[0] == "graphene demo --cheat · a scripted stand-in, no model ran · $0"
    assert "6 refused, 1 flagged, 0 got through." in lines
    assert said.stdout.count("REFUSED") == 6 and said.stdout.count("FLAGGED") == 1
    assert (
        "A script played the agent: the locks held against these moves. It does not show what a real model "
        "will try. Next: graphene init" in " ".join(lines)
    )
    assert len(lines) <= 25 and max(map(len, lines)) <= 80


def test_cheat_uses_the_real_gate(tmp_path, monkeypatch):
    monkeypatch.setattr(gate, "decide", lambda *_: None)
    said = cheat_demo(tmp_path, monkeypatch)
    assert said.exit_code == 1, said.output
    got = [n for n, verdict in verdicts(said.stdout.splitlines()).items() if "GOT THROUGH" in verdict]
    assert got == ["1", "2", "6"]
    assert "3 got through." in said.stdout and "the locks held" not in said.stdout


def test_cheat_leaves_nothing_behind(tmp_path, monkeypatch):
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    said = cheat_demo(tmp_path, monkeypatch)
    assert said.exit_code == 0, said.output
    status = ["git", "status", "--porcelain", "--ignored"]
    porcelain = subprocess.run(status, cwd=tmp_path, capture_output=True, text=True)
    assert porcelain.stdout == ""  # no plan's store either: it would show as ignored
    assert sorted(p.name for p in tmp_path.iterdir()) == [".git", "tmp"] and not any(
        (tmp_path / "tmp").iterdir()
    )


def test_done_says_when_the_leaf_changed_a_file_its_check_runs(tmp_path, monkeypatch):
    root = cheat.repo(tmp_path)
    test = root / "tests/test_calc.py"
    test.write_text(test.read_text().replace("== 4", "== 0"))  # move 7: the test made to agree
    monkeypatch.setenv("CLAUDE_CODE_SESSION_ID", cheat.SID)  # the stand-in's session says done
    monkeypatch.chdir(root)
    said = CliRunner().invoke(build(), ["node", "done", "n1"])
    assert said.exit_code == 0, said.output
    flag = "its check runs tests/test_calc.py, which this leaf changed: read that diff"
    assert said.stdout.splitlines()[1] == f"{flag} (`graphene node diff n1`)"
