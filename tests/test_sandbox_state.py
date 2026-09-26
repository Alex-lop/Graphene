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


@needs_docker
def test_leaves_at_one_commit_fork_one_checkpoint_each_with_its_own_scope(repo, tmp_path):
    from graphene_map.store import Store

    (repo / ".gitignore").write_text(".graphene/\n")
    subprocess.run(["git", "-C", str(repo), "add", "-A"], check=True)
    who = ["-c", "user.name=T", "-c", "user.email=t@e"]
    subprocess.run(["git", "-C", str(repo), *who, "commit", "-qm", "ignore the store"], check=True)
    with Store.open(repo) as store:
        prep = "echo ok > /opt/p"
        a = sandbox.Sandbox(repo, ["src/data/f001.txt"], sandbox.Docker(), store, "a", prepare=prep)
        b = sandbox.Sandbox(repo, ["src/data/f002.txt"], sandbox.Docker(), store, "b", prepare=prep)
        try:
            assert not a.reused and b.reused and a.shared == b.shared
            assert b.box.ops == 2  # its grants, and its file list: no upload, no setup
            code, _ = b.run("echo mine > src/data/f002.txt && cat /opt/p")  # the prepared checkpoint
            assert code == 0 and (repo / "src" / "data" / "f002.txt").read_text() == "mine\n"
            code, _ = b.run("echo not-mine > src/data/f001.txt")  # a's scope, not b's
            assert code != 0 and (repo / "src" / "data" / "f001.txt").read_text() == "1\n"
            fork = b.fork(tmp_path / "copy")
            assert fork.image == b.base and fork.shared == b.shared
        finally:
            a.close()
            b.close()
