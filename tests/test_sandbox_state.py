"""The sandbox's list of files comes back whole, or nothing is taken as changed. A judge showed a
list read from capped output losing files: a file missing from a list cut short read as deleted, and
224 of 3,000 in-scope files were unlinked from the leaf's checkout. The list is now written to a file in
the sandbox, read back whole, and closed by an end line; without it, nothing is brought back."""

import shutil
import subprocess

import pytest

from graphene_map import sandbox

needs_docker = pytest.mark.skipif(
    shutil.which("docker") is None or subprocess.run(["docker", "info"], capture_output=True).returncode != 0,
    reason="needs a running Docker (the sandbox stand-in)",
)


class Capped(sandbox.Docker):
    """A box whose output is capped at its head, as a service's may be."""

    def run(self, image, script, files, timeout):
        new, code, out = super().run(image, script, files, timeout)
        return new, code, out[:2000]


@pytest.fixture
def repo(tmp_path):
    root = tmp_path / "repo"
    (root / "src" / "data").mkdir(parents=True)
    for k in range(500):
        (root / "src" / "data" / f"f{k:03}.txt").write_text(f"{k}\n")
    who = ["-c", "user.name=T", "-c", "user.email=t@e"]
    for args in (["init", "-q"], ["add", "-A"], [*who, "commit", "-qm", "s"]):
        subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True)
    return root


@needs_docker
def test_a_chatty_command_in_a_big_tree_loses_no_file(repo):
    place = sandbox.Sandbox(repo, ["src/**"], Capped())
    try:
        code, out = place.run("seq 1 100000")
        assert code == 0 and len(list((repo / "src" / "data").iterdir())) == 500
        code, out = place.run("echo changed > src/data/f001.txt")
        assert (repo / "src" / "data" / "f001.txt").read_text() == "changed\n"
        assert len(list((repo / "src" / "data").iterdir())) == 500
    finally:
        place.close()


@needs_docker
def test_a_list_that_does_not_come_back_whole_changes_nothing_here(repo, monkeypatch):
    place = sandbox.Sandbox(repo, ["src/**"], sandbox.Docker())
    try:
        monkeypatch.setattr(place.box, "read", lambda image, path: b"0\n./src/data/f000.txt\n")  # no end line
        code, out = place.run("rm src/data/f002.txt")
        assert "did not come back whole" in out
        assert (repo / "src" / "data" / "f002.txt").exists()
    finally:
        place.close()
