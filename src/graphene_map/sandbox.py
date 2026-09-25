"""A leaf's placement in a Token Factory Sandbox (ConTree): the Nemotron executor's commands run there,
as an unprivileged user who can write only what the leaf's scope covers.

The leaf's checkout here stays the truth that Graphene's boundary reads. The executor's edit and write
land here, after the scope check, and are pushed into the sandbox before its next command. What a
command changes in the sandbox comes back only when the scope covers it; a path outside the scope that
a command created there never reaches the checkout: the executor is told, it is logged on the leaf as a
breach (as the Claude Code hook logs one), and it is removed from the sandbox before the next command.

Layer 2, in the sandbox (``setup``): the repository at /work belongs to root and nobody else may write
it; the leaf's user owns the files the scope covers and every directory the scope covers whole; a
directory where the scope names a file (existing or not) is writable with the sticky bit, so that user
can create files there and replace its own, and cannot delete, rename or change anyone else's.

ConTree is spoken to in ``Contree`` alone: it is in beta, its docs describe an SDK no release matches
yet (checked 2026-09-25), and the version is pinned in the ``sandbox`` extra.
"""

from __future__ import annotations

import io
import os
import shlex
import subprocess
import tarfile
import tempfile
import time
from pathlib import Path

from . import gate
from . import plan as P

WORK = "/work"
USER = "leaf"
IMAGE = "python:3.12"  # Debian with git and setpriv; any OCI image with bash, git, useradd and setpriv
OUTPUT = 200_000  # characters of a command's output kept from the sandbox
MARK = "::graphene::"


def configured() -> bool:
    """Can a sandbox be made here? The SDK imports, and ConTree has credentials: a key and a project
    in the environment, or a profile saved by `contree auth`. Only whether the file exists is asked."""
    try:
        import contree_sdk  # noqa: F401
    except ImportError:
        return False
    return credentials()


def credentials() -> bool:
    """Has ConTree something to sign in with: a key and a project here, or a saved profile?"""
    env = os.environ
    home = Path(env.get("CONTREE_HOME") or Path.home() / ".config" / "contree")
    return bool(env.get("NEBIUS_API_KEY") and env.get("NEBIUS_PROJECT_ID")) or (home / "auth.ini").exists()


def _fixed(glob: str) -> str:
    """The directories a glob names before its first wildcard."""
    parts = glob.strip().removeprefix("./").rstrip("/").split("/")
    upto = next((k for k, part in enumerate(parts) if any(c in part for c in "*?[")), len(parts))
    return "/".join(parts[:upto])


def grants(scope: list[str], files: list[str], dirs: set[str]) -> tuple[list[str], list[str], list[str]]:
    """What the leaf's user may write, from the scope: (trees it owns whole, files it owns, directories
    it may create files in). A directory is owned whole only when the scope covers everything under it
    and takes nothing back (``!``) there."""
    takes_back = [g[1:] for g in scope if g.startswith("!")]
    trees, opened = [], set()
    for glob in scope:
        if glob.startswith("!"):
            continue
        head = _fixed(glob)
        whole = glob.rstrip("/") == head or glob.endswith("/**") and _fixed(glob[:-3]) == head
        if whole and head in dirs and not any(_fixed(t).startswith(head) for t in takes_back):
            trees.append(head)
            continue
        if any(c in glob for c in "*?["):  # new files may appear under the fixed part of a pattern
            opened.add(head or ".")
        else:
            opened.add(os.path.dirname(head) or ".")
    owned = [f for f in files if P.in_scope(f, scope) and not any(f.startswith(t + "/") for t in trees)]
    opened |= {os.path.dirname(f) or "." for f in owned}
    inside = [d for d in opened if not any(d == t or d.startswith(t + "/") for t in trees)]
    return sorted(trees), owned, sorted(inside)


def setup(scope: list[str], files: list[str], dirs: set[str]) -> str:
    """The script that makes the sandbox (run as root, once): the repository unpacked at /work, a git
    baseline for the executor's `git diff`, and layer 2."""
    trees, owned, opened = grants(scope, files, dirs)
    q = shlex.quote
    lines = [
        "set -e",
        f"mkdir -p {WORK} && tar -xf /tmp/graphene/repo.tar -C {WORK} && rm -f /tmp/graphene/repo.tar",
        f"id -u {USER} >/dev/null 2>&1 || useradd -m -u 1500 {USER}",
        f"git config --system --add safe.directory {WORK}",  # the leaf's user reads root's repository
        f"cd {WORK} && git init -q && git add -A && "
        "git -c user.name=graphene -c user.email=graphene@localhost commit -qm base --allow-empty",
        f"chown -R root:root {WORK} && chmod -R a+rX,go-w {WORK}",
    ]
    for d in opened:
        lines.append(f"mkdir -p {q(WORK + '/' + d)} && chmod 1777 {q(WORK + '/' + d)}")
    for t in trees:
        lines.append(f"mkdir -p {q(WORK + '/' + t)} && chown -R {USER}:{USER} {q(WORK + '/' + t)}")
    for f in owned:
        lines.append(f"chown {USER}:{USER} {q(WORK + '/' + f)}")
    lines.append(_manifest())
    return "\n".join(lines)


STATE = "/tmp/graphene.state"  # the exit code and the file list, read back whole (never from stdout)
END = MARK + "end"


def _manifest() -> str:
    """Every file under /work but .git, with its hash (links marked, never followed), written to a file
    in the sandbox after the command's exit code, and closed by an end line. It is read back whole:
    stdout is capped, and a list cut short would read as files deleted."""
    return (
        f"{{ cat /tmp/graphene.code 2>/dev/null || echo 0; cd {WORK} && "
        "find . -path ./.git -prune -o -type f -print0 | xargs -0 -r sha1sum; "
        f"find . -path ./.git -prune -o -type l -printf 'link %p\\n'; echo {END}; }} > {STATE}"
    )


def _state(text: str) -> tuple[int, dict[str, str]] | None:
    """The exit code and the file list, or None when the list did not arrive whole."""
    lines = text.rstrip("\n").split("\n")
    if len(lines) < 2 or lines[-1] != END or not lines[0].strip().lstrip("-").isdigit():
        return None
    return int(lines[0]), _parse_manifest("\n".join(lines[1:-1]))


def _parse_manifest(text: str) -> dict[str, str]:
    out = {}
    for line in text.splitlines():
        if line.startswith("link ./"):
            out[line[len("link ./") :]] = "link"
        elif "  ./" in line:
            digest, path = line.split("  ./", 1)
            out[path] = digest
    return out


def pack(root: Path, leave_out: list[str] | tuple = ()) -> Path:
    """The leaf's checkout as git sees it (tracked, and untracked but not ignored), in a tar."""
    fd, name = tempfile.mkstemp(suffix=".tar")
    os.close(fd)
    with tarfile.open(name, "w") as tar:
        for rel in P.in_tree(root):
            if rel in leave_out:
                continue
            path = root / rel
            if path.is_file() or path.is_symlink():
                tar.add(path, arcname=rel, recursive=False)
    return Path(name)


class Contree:
    """ConTree, through contree-sdk 0.3.6: an image per checkpoint, a run from any image, a file read
    from any image. The credentials are the SDK's own (NEBIUS_API_KEY and NEBIUS_PROJECT_ID, or the
    profile `contree auth` saved); nothing of the environment is passed into a command."""

    def __init__(self, image: str = IMAGE):
        from contree_sdk import ContreeSync

        if not credentials():  # else the SDK sends the variable's name as the token, and gets a 401
            raise RuntimeError("ConTree needs NEBIUS_API_KEY and NEBIUS_PROJECT_ID in the environment, or a "
                               "profile saved by `contree auth`")  # fmt: skip
        self.sdk = ContreeSync()
        self.base = self.sdk.images.oci(image)
        self.ops = 1

    def start(self, tar: Path, script: str, timeout: float) -> tuple[str, int, str]:
        return self._run(self.base, script, {"/tmp/graphene/repo.tar": str(tar)}, timeout)

    def run(self, image: str, script: str, files: dict[str, bytes], timeout: float) -> tuple[str, int, str]:
        return self._run(self.sdk.images.use(image), script, files, timeout)

    def _run(self, image, script: str, files: dict, timeout: float) -> tuple[str, int, str]:
        self.ops += 1
        done = image.run(shell=script, files=files or None, timeout=timeout, disposable=False,
                         truncate_output_at=OUTPUT).wait()  # fmt: skip
        return str(done.uuid), int(done.exit_code), (done.stdout or "") + (done.stderr or "")

    def read(self, image: str, path: str) -> bytes:
        self.ops += 1
        return self.sdk.images.use(image).read(path)


class Docker:
    """A sandbox on this machine: an image is a docker image, a run is a container from it committed
    afterwards, so checkpoints and forks behave as ConTree's do. The tests' and CI's stand-in for
    ConTree (`GRAPHENE_SANDBOX=docker`), with the same Linux users and permissions layer 2 rests on."""

    def __init__(self, image: str = IMAGE):
        self.base, self.ops, self.made = image, 0, []

    def forget(self, keep: set[str] = frozenset()) -> None:
        """Remove the checkpoint images this box made, but ``keep``: nothing else prunes them."""
        gone = [i for i in reversed(self.made) if i not in keep]
        if gone:
            self._docker("rmi", "-f", "--no-prune", *gone)  # a parent is another sandbox's checkpoint
        self.made = [i for i in self.made if i in keep]

    def _docker(self, *args: str, data: bytes | None = None) -> subprocess.CompletedProcess:
        return subprocess.run(["docker", *args], input=data, capture_output=True)

    def start(self, tar: Path, script: str, timeout: float) -> tuple[str, int, str]:
        return self.run(self.base, script, {"/tmp/graphene/repo.tar": tar.read_bytes()}, timeout)

    def run(self, image: str, script: str, files: dict[str, bytes], timeout: float) -> tuple[str, int, str]:
        self.ops += 1
        made = self._docker("create", "-i", image, "bash", "-c", script)
        if made.returncode != 0:
            return image, 125, made.stderr.decode("utf-8", "replace")
        box = made.stdout.decode().strip()
        try:
            if files:
                buf = io.BytesIO()
                with tarfile.open(fileobj=buf, mode="w") as tar:
                    for name, data in files.items():
                        info = tarfile.TarInfo(name.lstrip("/"))
                        info.size = len(data)
                        tar.addfile(info, io.BytesIO(data))
                self._docker("cp", "-", f"{box}:/", data=buf.getvalue())
            try:
                ran = subprocess.run(["docker", "start", "-a", box], capture_output=True, timeout=timeout)
                code = int(self._docker("inspect", "-f", "{{.State.ExitCode}}", box).stdout.decode().strip())
            except subprocess.TimeoutExpired:
                self._docker("kill", box)
                return image, 124, "(the sandbox command ran out of time)"
            new = self._docker("commit", box).stdout.decode().strip()
            self.made.append(new)
            return new, code, (ran.stdout + ran.stderr).decode("utf-8", "replace")
        finally:
            self._docker("rm", "-f", box)

    def read(self, image: str, path: str) -> bytes:
        self.ops += 1
        return self._docker("run", "--rm", image, "cat", path).stdout


def choose(name: str | None = None):
    """The sandbox Graphene uses: ConTree, unless GRAPHENE_SANDBOX says docker."""
    name = name or os.environ.get("GRAPHENE_SANDBOX") or "contree"
    return Docker() if name == "docker" else Contree()


def check_in_fork(name: str, image: str, root: Path, command: str, timeout: float = 1800,
                  leave_out: list[str] = ()) -> tuple[int, str]:  # fmt: skip
    """A leaf's check in a fresh fork of the image its sandbox started from, holding the leaf's checkout
    as Graphene reads it (what a command left there outside the scope is not in it), run as the leaf's
    user. Nothing it writes comes back: the fork is thrown away. ``leave_out``: new files outside the
    scope that the check runs without, as it does here."""
    tar = pack(root, leave_out)
    try:
        script = "\n".join([
            f"cd {WORK} && find . -mindepth 1 -maxdepth 1 ! -name .git -exec rm -rf {{}} +",
            f"tar -xf /tmp/graphene/repo.tar -C {WORK} && rm -f /tmp/graphene/repo.tar",
            f"chown -R {USER}:{USER} {WORK}",
            f"cd {WORK} && setpriv --reuid={USER} --regid={USER} --init-groups env -i HOME=/home/{USER} "
            f"PATH=/usr/local/bin:/usr/bin:/bin LANG=C.UTF-8 bash -c {shlex.quote(command)} 2>&1",
        ])  # fmt: skip
        inside = choose(name)
        _, code, out = inside.run(image, script, {"/tmp/graphene/repo.tar": tar.read_bytes()}, timeout)
        if hasattr(inside, "forget"):
            inside.forget()
        return code, out
    finally:
        tar.unlink(missing_ok=True)


class Sandbox:
    """The Nemotron executor's placement in a sandbox: the same four methods as ``executor.Local``,
    and the leaf's scope held at the write by the sandbox's own users and permissions."""

    name = "sandbox"

    def __init__(self, root: Path, scope: list[str], box=None, store=None, node_id: str | None = None):
        self.root, self.scope, self.store, self.node_id = root, scope, store, node_id
        self.box = box if box is not None else choose()
        self.pushed: set[str] = set()
        self.strays: set[str] = set()
        self.timings: list[float] = []
        files = P.in_tree(root)
        dirs = {str(p) for f in files for p in Path(f).parents if str(p) != "."}
        tar = pack(root)
        try:
            began = time.monotonic()
            self.image, code, out = self.box.start(tar, setup(scope, files, dirs), 600)
            self.timings.append(time.monotonic() - began)
        finally:
            tar.unlink(missing_ok=True)
        if code != 0:
            raise RuntimeError(f"the sandbox could not be made (exit {code}): {out[-500:]}")
        self.base = self.image
        state = _state(self.box.read(self.image, STATE).decode("utf-8", "replace"))
        if state is None:
            raise RuntimeError("the sandbox was made, and its list of files did not come back whole")
        self.seen = state[1]

    def read(self, rel: str) -> bytes:
        return (self.root / rel).read_bytes()

    def write(self, rel: str, data: bytes) -> None:
        path = self.root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        self.pushed.add(rel)

    def run(self, command: str, timeout: int = 300) -> tuple[int, str]:
        q = shlex.quote
        files, lines = {}, [f"rm -f {STATE} /tmp/graphene.code"]  # never the last command's list, read again
        for k, rel in enumerate(sorted(self.pushed)):  # the executor's own edits, as the leaf's user
            files[f"/tmp/graphene/push/{k}"] = (self.root / rel).read_bytes()
            target = q(f"{WORK}/{rel}")
            lines.append(f"mkdir -p $(dirname {target}) && cp /tmp/graphene/push/{k} {target} && "
                         f"chown {USER}:{USER} {target}")  # fmt: skip
        for rel in sorted(self.strays):  # what a command made outside the scope does not stay
            lines.append(f"rm -rf {q(WORK + '/' + rel)}")
        lines += [
            "rm -rf /tmp/graphene/push",
            f"cd {WORK} && setpriv --reuid={USER} --regid={USER} --init-groups env -i HOME=/home/{USER} "
            f"PATH=/usr/local/bin:/usr/bin:/bin LANG=C.UTF-8 bash -c {q(command)} > /tmp/graphene.out 2>&1; "
            "echo $? > /tmp/graphene.code",
            _manifest(),
            f"tail -c {OUTPUT} /tmp/graphene.out",  # what the model is shown: its tail, capped anyway
        ]
        began = time.monotonic()
        image, code, output = self.box.run(self.image, "\n".join(lines), files, timeout + 60)
        self.timings.append(time.monotonic() - began)
        try:
            state = _state(self.box.read(image, STATE).decode("utf-8", "replace"))
        except Exception as no:  # a box that cannot be read now: nothing is taken as changed
            state, output = None, f"{output}\n({type(no).__name__}: {no})"
        if state is None:  # fail closed: without the whole list, no file is taken as deleted or changed
            self.image = image
            return code or 1, (f"{output}\n(the sandbox's list of files did not come back whole; nothing "
                               "was brought back from this command)")  # fmt: skip
        self.image, self.pushed, self.strays = image, set(), set()
        exit_code, now = state
        return exit_code, output + self._bring_back(now)

    def _bring_back(self, now: dict[str, str]) -> str:
        """What the command changed in the sandbox: what the scope covers comes here, what it does not
        is refused after the fact and removed from the sandbox before the next command."""
        changed = sorted(p for p in now.keys() | self.seen.keys() if now.get(p) != self.seen.get(p))
        ignored = gate._ignored(self.root, changed)  # a check's __pycache__: nobody's change, as at done
        changed = [p for p in changed if p not in ignored]
        refused = []
        for rel in changed:
            if not P.in_scope(rel, self.scope) or now.get(rel) == "link":
                refused.append(rel)
                continue
            local = self.root / rel
            if rel not in now:
                local.unlink(missing_ok=True)
            else:
                local.parent.mkdir(parents=True, exist_ok=True)
                local.write_bytes(self.box.read(self.image, f"{WORK}/{rel}"))
        self.seen = {k: v for k, v in now.items() if k not in refused} | {
            k: self.seen[k] for k in refused if k in self.seen}  # fmt: skip
        if not refused:
            return ""
        self.strays = {r for r in refused if r not in self.seen}
        if self.store is not None and self.node_id:
            self.store.log_node(self.node_id, P._now(), "breach", "run:nemotron", None, None,
                                {"paths": refused, "how": "a command in the sandbox"})  # fmt: skip
        return ("\n(refused: this command changed " + ", ".join(refused[:8])
                + (" and more" if len(refused) > 8 else "") + " outside the leaf's scope; it is not brought "
                "back, and it is undone before your next command)")  # fmt: skip

    def close(self) -> None:
        """The checkpoints this sandbox made go, but the first: the leaf's check forks from it."""
        if hasattr(self.box, "forget"):
            self.box.forget({self.base})

