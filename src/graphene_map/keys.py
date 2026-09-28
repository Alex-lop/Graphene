"""The Token Factory key: found in the environment (``NEBIUS_API_KEY``), then the system keychain, and
never in a file. On macOS the keychain is `security`; on Linux it is `secret-tool` (libsecret).

Setting a key never puts it in argv, which ps shows to everyone on the machine: `security -i` reads its
command on stdin, and `secret-tool store` reads the secret from stdin.

``GRAPHENE_KEYCHAIN=off`` turns the keychain off, so only the environment is read (the tests do this).
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys

KEY = "NEBIUS_API_KEY"
SERVICE = "graphene"
ACCOUNT = "token-factory"
PLATFORM = sys.platform


def _keychain() -> bool:
    return os.environ.get("GRAPHENE_KEYCHAIN", "").lower() != "off"


def _run(argv: list[str], stdin: str | None = None) -> subprocess.CompletedProcess | None:
    exe = shutil.which(argv[0]) if _keychain() else None
    if exe is None:
        return None
    try:  # the one found, never the next on the PATH when this one cannot start
        return subprocess.run([exe, *argv[1:]], input=stdin, capture_output=True, text=True, timeout=30)
    except OSError:
        return None


def find() -> str | None:
    """The key, from the environment first, then the keychain; None when neither has one."""
    key = os.environ.get(KEY)
    if key:
        return key
    if PLATFORM == "darwin":
        done = _run(["security", "find-generic-password", "-s", SERVICE, "-a", ACCOUNT, "-w"])
    elif PLATFORM.startswith("linux"):
        done = _run(["secret-tool", "lookup", "service", SERVICE, "account", ACCOUNT])
    else:
        return None
    if done is None or done.returncode != 0:
        return None
    return done.stdout.strip() or None


def set(key: str) -> None:  # noqa: A001 - keys.set reads as what it does
    """Keep ``key`` in the keychain, replacing any there. Raises RuntimeError, without the key, on failure."""
    key = key.strip()
    if not key or any(c.isspace() or c in "\"'\\" for c in key):
        raise RuntimeError("a Token Factory key is one word: no spaces or quotes")
    if PLATFORM == "darwin":
        done = _run(["security", "-i"], f'add-generic-password -U -s {SERVICE} -a {ACCOUNT} -w "{key}"\n')
    elif PLATFORM.startswith("linux"):
        done = _run(["secret-tool", "store", "--label=Graphene: Token Factory", "service", SERVICE,
                     "account", ACCOUNT], key)  # fmt: skip
    else:
        raise RuntimeError(f"no keychain on {PLATFORM}: set {KEY} in the environment")
    _said(done, "kept")


def remove() -> None:
    """Take the key out of the keychain. Raises RuntimeError on failure."""
    if PLATFORM == "darwin":
        done = _run(["security", "delete-generic-password", "-s", SERVICE, "-a", ACCOUNT])
    elif PLATFORM.startswith("linux"):
        done = _run(["secret-tool", "clear", "service", SERVICE, "account", ACCOUNT])
    else:
        raise RuntimeError(f"no keychain on {PLATFORM}")
    _said(done, "removed")


def _said(done: subprocess.CompletedProcess | None, what: str) -> None:
    tool = "security" if PLATFORM == "darwin" else "secret-tool"
    if not _keychain():
        raise RuntimeError(f"the key could not be {what}: the keychain is off (GRAPHENE_KEYCHAIN=off)")
    if done is None:
        raise RuntimeError(f"the key could not be {what}: `{tool}` is not on the PATH")
    # `security -i` exits 0 whatever its command did, and says so on stderr
    if done.returncode != 0 or "error" in done.stderr.lower():
        said = " ".join(done.stderr.split())[:200]
        raise RuntimeError(f"the key could not be {what}: {tool} said {said or f'exit {done.returncode}'}")


def reached() -> str:
    """One line: "Token Factory: reached, N NVIDIA models", or what stood in the way. Never the key."""
    from graphene_map import tokenfactory

    key = find()
    try:
        n = sum("nvidia" in m.id.lower() for m in tokenfactory.models(tries=1))
        line = f"Token Factory: reached, {n} NVIDIA models"
    except tokenfactory.Unreachable as no:
        line = "Token Factory: not reached: " + " ".join(str(no).split())
    return line.replace(key, "…") if key else line
