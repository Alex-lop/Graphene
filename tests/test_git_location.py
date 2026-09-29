"""A suite started where git has exported where the repository is (`git bisect run`, a hook, `rebase
--exec`: GIT_DIR and its kin) must not hand that to the git its tests start. With GIT_DIR set, a task
repo's `git -C DIR init/add/commit` re-initialises the repository running the suite and commits the task
into it: found on 29 September, when a bisect over test_bench left a `tiny: before` commit as a worktree's
HEAD."""

import os
import subprocess
import sys
from pathlib import Path

import keyguard
import pytest

INSIDE = "GRAPHENE_TEST_GIT_LOCATION_INSIDE"


@pytest.mark.skipif(not os.environ.get(INSIDE), reason="run by the test below, in a session of its own")
def test_the_session_holds_no_git_location():
    assert not [name for name in keyguard.GIT_LOCATION if name in os.environ]


def test_a_suite_started_with_git_location_set_hands_none_of_it_to_its_tests(tmp_path):
    here = Path(__file__).resolve()
    env = {**os.environ, INSIDE: "1", "GIT_DIR": str(tmp_path / "elsewhere.git"),
           "GIT_WORK_TREE": str(tmp_path), "GIT_INDEX_FILE": str(tmp_path / "index")}  # fmt: skip
    inner = f"{here}::test_the_session_holds_no_git_location"
    ran = subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", inner],
                         cwd=here.parents[1], env=env, capture_output=True, text=True, timeout=120)
    assert ran.returncode == 0 and "1 passed" in ran.stdout, ran.stdout[-2000:] + ran.stderr[-2000:]
