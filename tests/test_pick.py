import subprocess

from graphene_map.pick import Entry, choose, is_test, overlay, size


def e(fork: str, **kw) -> Entry:
    return Entry(fork, kw.pop("passed", True), order=kw.pop("order", "abcdefgh".index(fork)), **kw)


def test_what_looks_like_a_test():
    for path in ["tests/test_a.py", "test/a.py", "src/a_test.go", "web/app.test.ts", "web/app.spec.js",
                 "pkg/__tests__/x.js", "src/FooTest.java", "spec/a_spec.rb", "conftest.py", "test_a.py"]:
        assert is_test(path), path
    for path in ["src/a.py", "src/attest.py", "contest.py", "src/latest/a.py", "Testimony.py", "README.md",
                 ""]:  # fmt: skip
        assert not is_test(path), path


def test_no_fork_passed_keeps_none():
    choice = choose([e("a", passed=False, why="the check failed"), e("b", passed=False, state="gave up")])
    assert choice.fork is None
    assert choice.reason == "no fork's check passed"
    assert [row["state"] for row in choice.table] == ["refused", "gave up"]
    assert choice.table[0]["why"] == "the check failed"


def test_the_only_one_that_passed_is_kept_and_nothing_is_run():
    asked = []
    choice = choose([e("a", passed=False), e("b"), e("c", passed=False)], lambda i, j: asked.append((i, j)))
    assert (choice.fork, choice.reason) == ("b", "the only fork whose check passed")
    assert asked == []


def test_agreement_decides_first_and_says_who_failed_whose_tests():
    # a's tests pass on b alone; b's, the stricter, pass on nobody; c, the smallest, wrote none
    passes = {("a", "b")}
    forks = [e("a", tests=["tests/test_x.py"], lines=5), e("b", tests=["tests/test_x.py"], lines=40),
             e("c", lines=3)]
    choice = choose(forks, lambda i, j: (i, j) in passes)
    assert choice.fork == "b"  # agreement outranks being smaller
    assert choice.agree == {"a": [], "b": ["a"], "c": []}
    assert choice.reason == "passes a's tests (a and c fail b's)"


def test_a_forks_own_tests_count_for_nobody_itself_included():
    # only a wrote tests, and they fail on b: its own pass is no agreement, so the smaller is kept
    choice = choose([e("a", tests=["tests/test_x.py"], lines=50), e("b", lines=5)], lambda i, j: False)
    assert (choice.fork, choice.reason) == ("b", "5 lines against 50")
    # they pass on b: b passes a's tests, and a passes nobody's
    choice = choose([e("a", tests=["tests/test_x.py"], lines=50), e("b", lines=5)], lambda i, j: True)
    assert (choice.fork, choice.reason) == ("b", "passes a's tests")


def test_each_pair_is_asked_once_and_only_referees_are_asked():
    asked = []
    choose([e("a", tests=["t/test_a.py"]), e("b"), e("c", tests=["t/test_c.py"])],
           lambda i, j: asked.append((i, j)) or True)
    assert asked == [("a", "b"), ("a", "c"), ("c", "a"), ("c", "b")]


def test_without_a_way_to_run_tests_agreement_is_a_tie():
    choice = choose([e("a", tests=["tests/test_x.py"], lines=9), e("b", lines=4)])
    assert (choice.fork, choice.reason) == ("b", "4 lines against 9")


def test_a_fork_that_left_the_check_alone_beats_one_that_changed_it():
    choice = choose([e("a", lines=2, touched_check=["tests/test_x.py"]), e("b", lines=30)])
    assert choice.fork == "b"
    assert choice.reason == "left the check's own files as they were (a changed tests/test_x.py)"


def test_smaller_then_cheaper_then_sooner():
    assert choose([e("a", lines=58), e("b", lines=31), e("c", lines=70)]).reason == "31 lines against 58"
    same = dict(lines=10)
    choice = choose([e("a", dollars=0.77, **same), e("b", dollars=0.41, **same)])
    assert (choice.fork, choice.reason) == ("b", "$0.41 against $0.77")
    choice = choose([e("a", dollars=0.411, order=1, **same), e("b", dollars=0.409, order=0, **same)])
    assert (choice.fork, choice.reason) == ("b", "finished first")  # the same to the cent
    choice = choose([e("a", dollars=None, order=1, **same), e("b", dollars=0.10, order=0, **same)])
    assert (choice.fork, choice.reason) == ("b", "finished first")  # no meter: cost is no step
    choice = choose([e("a", order=0, **same), e("b", order=0, **same)])
    assert (choice.fork, choice.reason) == ("a", "the same in every step: the first by letter")


def test_the_table_has_a_row_a_fork_in_letter_order():
    choice = choose([e("b", lines=1, dollars=0.2, seconds=12.0), e("a", passed=False, why="exit 1")])
    assert [row["fork"] for row in choice.table] == ["a", "b"]
    assert choice.table[1] == {"fork": "b", "state": "passed", "passed": True, "agrees": [], "lines": 1,
                               "test_lines": 0, "touched_check": False, "dollars": 0.2, "seconds": 12.0,
                               "order": 1}  # fmt: skip


def git(repo, *args) -> str:
    return subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True, text=True).stdout


def commit(repo, files: dict[str, str | None], message: str) -> str:
    for path, text in files.items():
        f = repo / path
        if text is None:
            f.unlink()
        else:
            f.parent.mkdir(parents=True, exist_ok=True)
            f.write_text(text)
    git(repo, "add", "-A")
    git(repo, "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", message)
    return git(repo, "rev-parse", "HEAD").strip()


def test_overlay_lays_one_forks_tests_over_anothers_code(tmp_path):
    git(tmp_path, "init", "-q")
    base = commit(tmp_path, {"src/a.py": "x = 1\n", "tests/test_a.py": "old\n", "tests/test_gone.py": "g\n"},
                  "base")  # fmt: skip
    a = commit(tmp_path, {"src/a.py": "x = 2\n", "tests/test_a.py": "a's test\n", "tests/test_gone.py": None},
               "a")  # fmt: skip
    git(tmp_path, "checkout", "-q", base)
    b = commit(tmp_path, {"src/a.py": "x = 3\n", "tests/test_a.py": "b's test\n"}, "b")
    before = git(tmp_path, "status", "--porcelain")
    made = overlay(tmp_path, b, a, ["tests/test_a.py", "tests/test_gone.py"])
    assert git(tmp_path, "show", f"{made}:src/a.py") == "x = 3\n"  # b's code
    assert git(tmp_path, "show", f"{made}:tests/test_a.py") == "a's test\n"  # a's test
    assert "tests/test_gone.py" not in git(tmp_path, "ls-tree", "-r", "--name-only", made)  # a deleted it
    assert git(tmp_path, "rev-parse", f"{made}^") == f"{b}\n"
    assert git(tmp_path, "status", "--porcelain") == before  # no checkout or index was touched


def test_size_counts_code_and_tests_apart(tmp_path):
    git(tmp_path, "init", "-q")
    base = commit(tmp_path, {"src/a.py": "1\n2\n3\n", "tests/test_a.py": "t\n"}, "base")
    after = commit(tmp_path, {"src/a.py": "1\nTWO\n3\n4\n", "tests/test_a.py": "t\nu\nv\n"}, "after")
    assert size(tmp_path, base, after) == (3, 2)  # -2 +TWO +4 in code; +u +v in tests
    assert size(tmp_path, base, after, ["src/a.py"]) == (3, 0)
