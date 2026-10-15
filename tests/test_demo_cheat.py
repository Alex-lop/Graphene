"""`graphene demo --cheat`: a scripted stand-in tries seven ways round one leaf, and the real hook, git
and check answer each. The verdicts are what that code said: with the gate saying nothing, they change."""

from graphene_map import cheat


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
