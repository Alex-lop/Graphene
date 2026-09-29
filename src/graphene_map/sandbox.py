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

import fcntl
import hashlib
import io
import os
import shlex
import subprocess
import tarfile
import tempfile
import time
from contextlib import contextmanager
from pathlib import Path

from . import gate, night
from . import plan as P
from . import tokenfactory as tf

WORK = "/work"
USER = "leaf"
IMAGE = "python:3.12"  # Debian with git and setpriv; any OCI image with bash, git, useradd and setpriv
OUTPUT = 200_000  # characters of a command's output kept from the sandbox
MARK = "::graphene::"

# ConTree's 403, as rung 1 met it live on 2026-09-29 (docs/test/first-light.md): what it means, and the way in
# Nebius's own pages give (contree.dev and the Sandboxes docs, read 2026-09-29). ConTree answers a made-up key
# and project with a 403 too, not a 401, so without whoami's grants the project id is the other suspect.
FORBIDDEN = ("Sandboxes refused this project (403): {why}; request access at "
             "tokenfactory.nebius.com/sandboxes/about")  # fmt: skip
NO_GRANT = "its key may not use them there, or NEBIUS_PROJECT_ID is not its project"
USED = ("import", "list", "spawn")  # the grants a leaf's sandbox uses, as Nebius's docs name them
TIMED_OUT = "(the sandbox command ran out of time)"  # Docker's words for the same stop


class Refused(tf.Unreachable):
    """Sandboxes said no to this project: the message says what that means and what to do, whole, and
    every caller that says Token Factory's refusals says it as it is (a leaf's reason, a precheck's)."""


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
    from . import keys  # the environment's key, else the keychain's

    return bool(keys.find() and env.get("NEBIUS_PROJECT_ID")) or (home / "auth.ini").exists()


def _client():
    """contree-sdk's client, signed in as ConTree reads its credentials, with a keychain key it cannot
    see handed to it."""
    from contree_sdk import ContreeSync

    from . import keys

    token = None if os.environ.get(keys.KEY) else keys.find()
    return ContreeSync(token=token) if token else ContreeSync()


def _sdk_error(name: str) -> type[Exception]:
    """contree-sdk's own exception class ``name``, asked for only once something was raised (an except
    clause is evaluated then), or a class nothing raises when the SDK in this process has none by that
    name (a stand-in module with ContreeSync alone)."""
    try:
        from contree_sdk.sdk import exceptions

        return getattr(exceptions, name)
    except (ImportError, AttributeError):
        return type(name, (Exception,), {})


def _unkeyed(said) -> str:
    """ConTree's words with the key and the project id taken out, as set and as sent, then anything shaped
    like a key, then cut: a gateway's page may echo the request's headers, and the cut must not halve a key
    first (tokenfactory._request does the same for Token Factory's)."""
    from . import keys

    text = " ".join(str(said).split())
    raw = [os.environ.get(n) or "" for n in (keys.KEY, "NEBIUS_PROJECT_ID")]
    for secret in sorted({*raw, *(v.strip() for v in raw), keys.find() or ""}, key=len, reverse=True):
        if len(secret) >= 6:
            text = text.replace(secret, "…")
    return tf.unkeyed(text)[:300]


def refused() -> str | None:
    """The refusal a leaf would meet, asked before any is placed (`graphene init`): ConTree's whoami, a
    read and no operation, answering 403, or saying the key lacks one of the grants a leaf uses. None when
    it may, or when that cannot be told (no SDK, no network, grants named otherwise): a leaf's own
    refusal then says it."""
    try:
        from contree_sdk.sdk.exceptions import ForbiddenError

        grants = _client().get_token_info().permissions
    except ImportError:
        return None
    except ForbiddenError:
        return FORBIDDEN.format(why=NO_GRANT)
    except Exception:  # noqa: BLE001 (offline, or an SDK that answers otherwise: not a refusal)
        return None
    lacks = sorted(g for g in USED if grants.get(g) is False)
    return FORBIDDEN.format(why=f"its key lacks {', '.join(lacks)} there") if lacks else None


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


def base(prepare: str | None = None) -> str:
    """The script that makes the checkpoint every leaf at one commit forks from (run as root, once): the
    repository unpacked at /work, a git baseline for the executor's `git diff`, the leaf's user, and
    ``prepare`` (what the repository needs installed to run its checks, e.g. `pip install -e .`)."""
    lines = [
        "set -e",
        f"mkdir -p {WORK} && tar -xf /tmp/graphene/repo.tar -C {WORK} && rm -f /tmp/graphene/repo.tar",
        f"id -u {USER} >/dev/null 2>&1 || useradd -m -u 1500 {USER}",
        f"git config --system --add safe.directory {WORK}",  # the leaf's user reads root's repository
        f"cd {WORK} && git init -q && git add -A && "
        "git -c user.name=graphene -c user.email=graphene@localhost commit -qm base --allow-empty",
    ]
    if prepare:
        lines.append(f"cd {WORK} && {prepare}")
    return "\n".join(lines)


def layer2(scope: list[str], files: list[str], dirs: set[str]) -> str:
    """One leaf's permissions on the checkpoint (run as root): layer 2, then the file list."""
    trees, owned, opened = grants(scope, files, dirs)
    q = shlex.quote
    lines = ["set -e", f"chown -R root:root {WORK} && chmod -R a+rX,go-w {WORK}"]
    for d in opened:
        lines.append(f"mkdir -p {q(WORK + '/' + d)} && chmod 1777 {q(WORK + '/' + d)}")
    for t in trees:
        lines.append(f"mkdir -p {q(WORK + '/' + t)} && chown -R {USER}:{USER} {q(WORK + '/' + t)}")
    for f in owned:
        lines.append(f"chown {USER}:{USER} {q(WORK + '/' + f)}")
    lines.append(_manifest())
    return "\n".join(lines)


def setup(scope: list[str], files: list[str], dirs: set[str], prepare: str | None = None) -> str:
    """The checkpoint and one leaf's permissions in one script: what a leaf whose checkout is not a
    clean commit gets (its state is its own, so nothing is shared)."""
    return base(prepare) + "\n" + layer2(scope, files, dirs).removeprefix("set -e\n")


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
    profile `contree auth` saved); nothing of the environment is passed into a command. Under the
    person's opening, each operation and its seconds go to the night's ledger (``night.sandbox``)."""

    def __init__(self, image: str = IMAGE):
        self.image = image
        if not credentials():  # else the SDK sends the variable's name as the token, and gets a 401
            raise RuntimeError("ConTree needs a key (NEBIUS_API_KEY or `graphene key set`) and "
                               "NEBIUS_PROJECT_ID, or a profile saved by `contree auth`")
        night.person_only("a ConTree sandbox")  # ConTree is always the real service
        night.first("a ConTree sandbox")  # past 80% of the night's cap, no sandbox is made
        self.sdk = _client()
        with self._counted("image"):
            self.base = self._asked(lambda: self.sdk.images.oci(image))
        self.ops = 1

    @contextmanager
    def _counted(self, op: str):
        began = time.monotonic()
        try:
            yield
        finally:  # an operation that failed or was stopped ran all the same
            night.sandbox(op, time.monotonic() - began)

    def _asked(self, call):
        """One call to the SDK, its 403 said as ``Refused``, with what the key lacks when ConTree's whoami
        says, and any other error of its own said without the key or the project (``_unkeyed``); its time
        limit reaches ``_run`` as it is."""
        try:
            return call()
        except _sdk_error("OperationTimedOutError"):
            raise
        except _sdk_error("ForbiddenError"):
            try:  # a read of the key's grants, no operation: which of them this project does not give
                lacks = sorted(k for k, v in self.sdk.get_token_info().permissions.items() if not v)
            except Exception:  # noqa: BLE001 (the refusal is said either way)
                lacks = []
            why = f"its key lacks {', '.join(lacks)} there" if lacks else NO_GRANT
            raise Refused(FORBIDDEN.format(why=why)) from None
        except _sdk_error("ContreeError") as no:  # its message is the response's body: it may echo a header
            said = f"ConTree answered with an error ({type(no).__name__}): {_unkeyed(no)}"
            raise RuntimeError(said) from None

    def start(self, tar: Path, script: str, timeout: float) -> tuple[str, int, str]:
        return self._run(self.base, script, {"/tmp/graphene/repo.tar": str(tar)}, timeout, "")

    def run(self, image: str, script: str, files: dict[str, bytes], timeout: float) -> tuple[str, int, str]:
        return self._run(self._asked(lambda: self.sdk.images.use(image)), script, files, timeout, image)

    def _run(self, image, script: str, files: dict, timeout: float, ref: str) -> tuple[str, int, str]:
        self.ops += 1
        with self._counted("run"):
            try:
                done = self._asked(lambda: image.run(shell=script, files=files or None, timeout=timeout,
                                                     disposable=False, truncate_output_at=OUTPUT).wait())
            except _sdk_error("OperationTimedOutError"):
                return ref, 124, TIMED_OUT
        return str(done.uuid), int(done.exit_code), (done.stdout or "") + (done.stderr or "")

    def read(self, image: str, path: str) -> bytes:
        self.ops += 1
        with self._counted("read"):
            return self._asked(lambda: self.sdk.images.use(image).read(path))


class Docker:
    """A sandbox on this machine: an image is a docker image, a run is a container from it committed
    afterwards, so checkpoints and forks behave as ConTree's do. The tests' and CI's stand-in for
    ConTree (`GRAPHENE_SANDBOX=docker`), with the same Linux users and permissions layer 2 rests on."""

    def __init__(self, image: str = IMAGE):
        self.base, self.image, self.ops, self.made = image, image, 0, []
        self.running: set[str] = set()  # the containers running a command now

    def forget(self, keep: set[str] = frozenset()) -> None:
        """Remove the checkpoint images this box made, but ``keep``: nothing else prunes them."""
        gone = [i for i in reversed(self.made) if i not in keep]
        if gone:
            self._docker("rmi", "-f", "--no-prune", *gone)  # a parent is another sandbox's checkpoint
        self.made = [i for i in self.made if i in keep]

    def _docker(self, *args: str, data: bytes | None = None) -> subprocess.CompletedProcess:
        """docker's CLI, in a session of its own: a terminal's Ctrl-C reaches Graphene, not it. A call a
        stop lands in is let end first (its input cut short), so what it made is known to the cleanup:
        a container by its name, a committed image in ``made``."""
        given = subprocess.DEVNULL if data is None else subprocess.PIPE
        with subprocess.Popen(["docker", *args], stdin=given, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                              start_new_session=True) as call:  # fmt: skip
            try:
                out, err = call.communicate(data)
            except BaseException:
                if call.stdin:
                    call.stdin.close()
                out, _ = call.communicate()
                if args[0] == "commit" and call.returncode == 0:
                    self.made.append(out.decode().strip())
                raise
        return subprocess.CompletedProcess(call.args, call.returncode, out, err)

    def start(self, tar: Path, script: str, timeout: float) -> tuple[str, int, str]:
        return self.run(self.base, script, {"/tmp/graphene/repo.tar": tar.read_bytes()}, timeout)

    def run(self, image: str, script: str, files: dict[str, bytes], timeout: float) -> tuple[str, int, str]:
        self.ops += 1
        box = f"graphene-{os.getpid()}-{os.urandom(6).hex()}"  # named before it is made: a stop finds it
        self.running.add(box)
        try:
            made = self._docker("create", "-i", "--name", box, image, "bash", "-c", script)
            if made.returncode != 0:
                return image, 125, made.stderr.decode("utf-8", "replace")
            if files:
                buf = io.BytesIO()
                with tarfile.open(fileobj=buf, mode="w") as tar:
                    for name, data in files.items():
                        info = tarfile.TarInfo(name.lstrip("/"))
                        info.size = len(data)
                        tar.addfile(info, io.BytesIO(data))
                self._docker("cp", "-", f"{box}:/", data=buf.getvalue())
            try:
                ran = subprocess.run(["docker", "start", "-a", box], capture_output=True, timeout=timeout,
                                     start_new_session=True)  # fmt: skip
                if box not in self.running:  # halted: removed with all it ran, and nothing of it is kept
                    return image, 137, ""
                code = int(self._docker("inspect", "-f", "{{.State.ExitCode}}", box).stdout.decode().strip())
            except subprocess.TimeoutExpired:
                self._docker("kill", box)
                return image, 124, TIMED_OUT
            new = self._docker("commit", box).stdout.decode().strip()
            self.made.append(new)
            return new, code, (ran.stdout + ran.stderr).decode("utf-8", "replace")
        finally:
            self.running.discard(box)
            self._docker("rm", "-f", box)

    def halt(self) -> None:
        """The run was stopped while a fork's thread waits on a container: remove it here, with all it runs
        (its command ignores the TERM docker passes on, as the first process in the container). Left to
        the fork's thread, it went only after a commit of the killed container, and a slow commit
        outlasted the executor's grace (CI caught one)."""
        # ponytail: a container still being created when this runs is made after it, and starts
        for box in list(self.running):
            self.running.discard(box)
            self._docker("rm", "-f", box)

    def read(self, image: str, path: str) -> bytes:
        self.ops += 1
        return self._docker("run", "--rm", image, "cat", path).stdout


def choose(name: str | None = None, image: str | None = None):
    """The sandbox Graphene uses: ConTree, unless GRAPHENE_SANDBOX says docker; from ``image``."""
    name = name or os.environ.get("GRAPHENE_SANDBOX") or "contree"
    return Docker(image or IMAGE) if name == "docker" else Contree(image or IMAGE)


CAP = 50  # sandbox operations at once: the Sandboxes beta's own cap
POOL = Path(tempfile.gettempdir()) / f"graphene-sandbox-ops-{os.getuid()}"  # a lock file a slot


@contextmanager
def _slot():
    """One of CAP slots for a sandbox operation, shared by every Graphene process of this user on this
    machine: a lock file a slot, held with flock while the operation runs, and let go by the kernel
    however its process ends. A lock inside one process would not bound a run: under `graphene run
    --parallel` each leaf's executor is a process of its own, its forks are threads, and each `graphene
    node done` forks the check from a process of its own too."""
    # ponytail: one machine's bound; two machines on one account can still pass fifty between them
    POOL.mkdir(parents=True, exist_ok=True)
    while True:
        for k in range(CAP):
            held = open(POOL / str(k), "a")  # noqa: SIM115 (closed below, which lets the lock go)
            try:
                fcntl.flock(held, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError:
                held.close()
                continue
            try:
                yield
            finally:
                held.close()
            return
        time.sleep(0.05)


class Capped:
    """A box whose every operation holds one of the CAP slots while it runs (``_slot``)."""

    def __init__(self, box):
        self.box = box

    def __getattr__(self, name: str):  # the box's image, its count of operations, its forget
        return getattr(self.box, name)

    def start(self, *args):
        with _slot():
            return self.box.start(*args)

    def run(self, *args):
        with _slot():
            return self.box.run(*args)

    def read(self, *args):
        with _slot():
            return self.box.read(*args)


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
        inside = Capped(choose(name))
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

    def __init__(self, root: Path, scope: list[str], box=None, store=None, node_id: str | None = None,
                 prepare: str | None = None, checkout: Path | None = None):  # fmt: skip
        """``root``: where the executor's edits land here; ``checkout``: the git checkout its files come
        from, when that is not ``root`` (a fork's copy has no .git of its own)."""
        self.root, self.scope, self.store, self.node_id = root, scope, store, node_id
        source = self.checkout = checkout or root  # where git is asked what it shows and ignores
        self.box = Capped(box if box is not None else choose())
        self.pushed: set[str] = set()
        self.strays: set[str] = set()
        self.timings: list[float] = []
        self.shared: str | None = None  # the checkpoint of the commit, which other leaves fork too
        from . import settings

        hidden = settings.protected(store) if store is not None else []  # never uploaded, so never read
        files = P.in_tree(source)
        kept_back = [f for f in files if P.covers(hidden, f)]
        files = [f for f in files if f not in kept_back]
        dirs = {str(p) for f in files for p in Path(f).parents if str(p) != "."}
        began = time.monotonic()
        key = self._key(source, prepare, hidden)
        shared = store.meta(key) if store is not None and key else None
        if shared:  # a leaf at this commit made the checkpoint already: fork it, with this leaf's grants
            self.image, code, out = self.box.run(shared, layer2(scope, files, dirs), {}, 600)
            self.shared = shared if code == 0 else None  # gone (a pruned box): made again below
        self.reused = bool(self.shared)
        if not self.shared:
            tar = pack(source, kept_back)
            try:
                if key:  # a clean commit: its checkpoint is kept for the other leaves at it
                    shared, code, out = self.box.start(tar, base(prepare), 1800)
                    if code == 0:
                        self.shared = shared
                        if store is not None:
                            store.set_meta(key, shared)
                        self.image, code, out = self.box.run(shared, layer2(scope, files, dirs), {}, 600)
                else:
                    self.image, code, out = self.box.start(tar, setup(scope, files, dirs, prepare), 1800)
            finally:
                tar.unlink(missing_ok=True)
        self.timings.append(time.monotonic() - began)
        if code != 0:
            raise RuntimeError(f"the sandbox could not be made (exit {code}): {out[-500:]}")
        self.base = self.image
        state = _state(self.box.read(self.image, STATE).decode("utf-8", "replace"))
        if state is None:
            raise RuntimeError("the sandbox was made, and its list of files did not come back whole")
        self.seen = state[1]
        self.ops = self.box.ops  # what making it took: the box is its own until it forks

    def _key(self, checkout: Path, prepare: str | None, hidden: list[str] = ()) -> str | None:
        """Where the checkpoint of this checkout's commit is kept, or None when the checkout is not
        exactly a commit (anything uncommitted is this leaf's own)."""
        try:
            if P._git(checkout, "status", "--porcelain").strip():
                return None
            head = P._git(checkout, "rev-parse", "HEAD").strip()
        except (P.Refused, OSError):
            return None
        box = getattr(self.box, "box", self.box)  # a wrapper's box is the box
        made = f"{type(box).__name__}|{getattr(box, 'image', IMAGE)}|{prepare or ''}|{','.join(hidden)}"
        return f"sandbox:{head}:{hashlib.sha1(made.encode()).hexdigest()[:12]}"

    def fork(self, root: Path) -> Sandbox:
        """Another sandbox from this one's first image, for a copy of the same checkout: a fork of the
        leaf (``--forks``), which uploads and sets up nothing."""
        other = object.__new__(Sandbox)
        other.__dict__.update(self.__dict__)
        other.root, other.pushed, other.strays, other.timings = root, set(), set(), []
        other.image, other.seen, other.ops, other.reused = self.base, dict(self.seen), 0, True
        return other

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
        try:
            image, code, output = self.box.run(self.image, "\n".join(lines), files, timeout + 60)
        except Refused:  # said whole: running the leaf again would meet it again
            raise
        except Exception as no:  # the service's own error, or a box gone mid-leaf: the leaf comes back
            raise RuntimeError(f"the sandbox stopped answering mid-leaf ({type(no).__name__}: {no}); nothing "
                               "of this command was brought back: run the leaf again") from no  # fmt: skip
        self.timings.append(time.monotonic() - began)
        self.ops += 2  # the command, and its list of files read back
        stale = image == self.image  # no new image (the box's own time limit): its list is the last command's
        try:
            state = None if stale else _state(self.box.read(image, STATE).decode("utf-8", "replace"))
        except Exception as no:  # a box that cannot be read now: nothing is taken as changed
            state, output = None, f"{output}\n({type(no).__name__}: {no})"
        if state is None and code > 128:  # a signal ended the sandbox's own script, not only the command
            raise RuntimeError(f"the sandbox's operation was killed mid-leaf (exit {code}: out of memory, or "
                               "stopped); nothing of this command was brought back: run the leaf again")
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
        ignored = gate._ignored(self.checkout, changed)  # a check's __pycache__: nobody's change, as at done
        changed = [p for p in changed if p not in ignored]
        refused, self.brought = [], []
        for rel in changed:
            if not P.in_scope(rel, self.scope) or now.get(rel) == "link":
                refused.append(rel)
                continue
            local = self.root / rel
            self.brought.append(rel)
            if rel not in now:
                local.unlink(missing_ok=True)
            else:
                local.parent.mkdir(parents=True, exist_ok=True)
                local.write_bytes(self.box.read(self.image, f"{WORK}/{rel}"))
                self.ops += 1
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

    def halt(self) -> None:
        """The run was stopped while a fork's thread waits on this sandbox: the box ends what it runs."""
        # ponytail: ConTree's operation is not cancelled; it ends at its own time limit
        if hasattr(self.box, "halt"):
            self.box.halt()

    def close(self) -> None:
        """The checkpoints this sandbox made go, but its first (the leaf's check forks from it) and the
        commit's (other leaves fork from it)."""
        if hasattr(self.box, "forget"):
            self.box.forget({self.base, *([self.shared] if self.shared else [])})

