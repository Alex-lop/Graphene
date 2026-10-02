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


def test_a_protected_file_is_never_uploaded_to_the_sandbox(repo):
    import tarfile

    from graphene_map import settings
    from graphene_map.plan import Caller
    from graphene_map.store import Store

    (repo / "secrets").mkdir()
    (repo / "secrets" / "prod.txt").write_text("KEY=do-not-send\n")
    subprocess.run(["git", "-C", str(repo), "add", "-A"], check=True)
    uploaded: list[str] = []

    class Box:
        ops = 0

        def start(self, tar, script, timeout):
            with tarfile.open(tar) as t:
                uploaded.extend(t.getnames())
            return "image", 1, "stopped here"

    with Store.open(repo) as store:
        settings.apply(store, "protected: secrets/**\n", Caller("alex", True))
        with pytest.raises(RuntimeError, match="could not be made"):
            sandbox.Sandbox(repo, ["src/**"], Box(), store, "a")
    assert "src/data/f001.txt" in uploaded and "secrets/prod.txt" not in uploaded


def test_the_list_takes_the_exit_code_through_a_substitution_never_a_cat_into_the_list():
    """Live on ConTree (rung 4, 2 Oct): after `cat` copied the exit code's file into the redirected list,
    every later write to the list failed with an I/O error, so no command's list came back and each read
    as exit 1. Through $(...) the code reaches the list as a pipe does, and the list is written whole."""
    script = sandbox._manifest()
    assert '{ echo "$(cat /tmp/graphene.code 2>/dev/null || echo 0)";' in script
    assert "{ cat " not in script


class Unlisted:
    """A box that makes the sandbox, then lets no command's list come back, as ConTree did on 2 Oct."""

    ops = 0

    def start(self, tar, script, timeout):
        return "img", 0, ""

    def run(self, image, script, files, timeout):
        return image + "+", 0, ""

    def read(self, image, path):  # the sandbox's own list arrives (img+); a command's does not (img++)
        return f"0\n{sandbox.END}\n".encode() if image.count("+") == 1 else b"0\n"


def test_a_command_whose_list_never_came_back_is_counted_on_the_leafs_record(tmp_path):
    from graphene_map import executor

    root = tmp_path / "leaf"
    root.mkdir()
    (root / "a.py").write_text("x = 1\n")
    who = ["-c", "user.name=T", "-c", "user.email=t@e"]
    for args in (["init", "-q"], ["add", "-A"], [*who, "commit", "-qm", "s"]):
        subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True)
    place = sandbox.Sandbox(root, ["a.py"], Unlisted())
    code, out = place.run("true")
    assert code == 1 and sandbox.LOST in out
    assert place.lost == 1 and executor._box(place)["lost"] == 1
    assert place.fork(tmp_path / "copy").lost == 0  # a fork starts its own count
