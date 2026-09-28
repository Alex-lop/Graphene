import re

import pytest

from graphene_map.sizing import layout, measure, named_dirs


def repo(tmp_path, files: dict[str, int]) -> list[str]:
    for p, n in files.items():
        f = tmp_path / p
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text("x\n" * n)
    return list(files)


def leaves(s: str) -> tuple[int, int]:
    m = re.search(r"about (\d+)(?: to (\d+))? lea", s)
    return int(m[1]), int(m[2] or m[1])


def test_layout():
    assert layout(["src/a.py", "tests/test_a.py"]) == "tests/"
    assert layout(["pkg/a.go", "pkg/a_test.go"]) == "beside"
    assert layout(["web/app.ts", "web/app.test.ts"]) == "beside"
    assert layout(["src/a.py", "README.md"]) == "none"


def test_named_dirs():
    files = ["src/graphene_map/plan.py", "src/graphene_map/ui/x.js", "docs/a.md", "tests/test_plan.py"]
    assert named_dirs("change ui and docs/ please.", files) == {"src/graphene_map/ui", "docs"}
    assert named_dirs("fix src/graphene_map/plan.py", files) == {"src/graphene_map"}
    assert named_dirs("make it faster", files) == set()


def test_measure_counts_and_sizes(tmp_path):
    files = repo(tmp_path, {"src/a.py": 30, "src/b.py": 20, "tests/test_a.py": 10})
    (tmp_path / "logo.png").write_bytes(b"\x89PNG\0\n\n\n")
    files.append("logo.png")
    s = measure(tmp_path, "touch src and tests", files)
    assert "4 files and 60 lines" in s
    assert "2 directories" in s and "tests/ directory" in s
    auto = leaves(s)
    assert auto[0] >= 2
    finer, coarser = leaves(measure(tmp_path, "touch src and tests", files, "finer")), leaves(
        measure(tmp_path, "touch src and tests", files, "coarser")
    )
    assert finer[0] > auto[0] and finer[1] > auto[1]
    assert coarser[0] <= auto[0] and coarser[1] < auto[1]


def test_bigger_repo_cuts_finer(tmp_path):
    small = measure(tmp_path / "s", "go", repo(tmp_path / "s", {"a.py": 100}))
    big_files = repo(tmp_path, {f"m{i}.py": 1000 for i in range(25)})
    big = measure(tmp_path, "go", big_files)
    assert leaves(big)[1] > leaves(small)[1]
    assert "no tests" in big


def test_bad_size(tmp_path):
    with pytest.raises(ValueError):
        measure(tmp_path, "x", [], "huge")


def test_a_word_naming_many_directories_does_not_set_the_floor(tmp_path):
    files = repo(tmp_path, {f"pkg{i}/sub/m.py": 1 for i in range(30)})
    assert named_dirs("fix a typo in sub", files) == set()  # 30 directories answer to it: none is meant
    assert named_dirs("fix a typo in pkg3/sub", files) == {"pkg3/sub"}
    lo, hi = leaves(measure(tmp_path, "fix a typo in pkg1 pkg2 pkg3 pkg4 pkg5 pkg6 pkg7", files))
    assert lo <= hi <= 7  # directories named by path count, and never past the repo's own bound twice


def test_a_small_ask_in_a_big_repo_can_be_one_leaf(tmp_path):
    files = repo(tmp_path, {f"m{i}.py": 1000 for i in range(25)})
    lo, hi = leaves(measure(tmp_path, "fix a typo in the README", files))
    assert lo == 1 and hi >= 6  # the repo's size bounds the tree from above, never from below
