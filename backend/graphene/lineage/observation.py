from __future__ import annotations

import fcntl
import os
import secrets
import stat
import time
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator

_WIDTH = 20


class ObservationError(RuntimeError):
    pass


def _directory(database: Path) -> Path:
    directory = database.parent / ".graphene-watch"
    try:
        directory.mkdir(mode=0o700, exist_ok=True)
        metadata = directory.stat(follow_symlinks=False)
    except OSError as error:
        raise ObservationError("watch coordination is unavailable") from error
    if (
        directory.is_symlink()
        or not stat.S_ISDIR(metadata.st_mode)
        or stat.S_IMODE(metadata.st_mode) != 0o700
        or (hasattr(os, "getuid") and metadata.st_uid != os.getuid())
    ):
        raise ObservationError("watch coordination is unsafe")
    return directory


@dataclass(frozen=True, slots=True)
class WatchCursor:
    descriptor: int

    def acknowledge(self, seq: int) -> None:
        raw = f"{seq:0{_WIDTH}d}\n".encode()
        if seq < 0 or len(raw) != _WIDTH + 1:
            raise ObservationError("watch cursor is invalid")
        try:
            os.pwrite(self.descriptor, raw, 0)
            os.ftruncate(self.descriptor, len(raw))
            os.fsync(self.descriptor)
        except OSError as error:
            raise ObservationError("watch cursor could not be acknowledged") from error


@contextmanager
def register_watch(database: Path, run_id: str, after_seq: int) -> Iterator[WatchCursor]:
    directory = _directory(database)
    path = directory / f"{run_id}.{os.getpid()}.{secrets.token_hex(8)}.cursor"
    flags = os.O_CREAT | os.O_EXCL | os.O_RDWR | getattr(os, "O_NOFOLLOW", 0)
    descriptor: int | None = None
    try:
        descriptor = os.open(path, flags, 0o600)
        os.fchmod(descriptor, 0o600)
        fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        cursor = WatchCursor(descriptor)
        cursor.acknowledge(after_seq)
    except OSError as error:
        if descriptor is not None:
            os.close(descriptor)
        try:
            path.unlink()
        except FileNotFoundError:
            pass
        raise ObservationError("watch could not register") from error
    try:
        yield cursor
    finally:
        os.close(descriptor)
        try:
            path.unlink()
        except FileNotFoundError:
            pass


def wait_until_observed(
    database: Path,
    run_id: str,
    seq: int,
    *,
    timeout: float = 2.0,
) -> None:
    directory = _directory(database)
    descriptors: list[int] = []
    prefix = f"{run_id}."
    try:
        for entry in os.scandir(directory):
            if (
                not entry.name.startswith(prefix)
                or not entry.name.endswith(".cursor")
                or not entry.is_file(follow_symlinks=False)
            ):
                continue
            try:
                descriptor = os.open(
                    entry.path,
                    os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0),
                )
                try:
                    fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
                except BlockingIOError:
                    descriptors.append(descriptor)
                else:
                    os.close(descriptor)
            except OSError:
                continue
        if not descriptors:
            return
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            for descriptor in descriptors:
                try:
                    raw = os.pread(descriptor, _WIDTH + 1, 0)
                    if len(raw) == _WIDTH + 1 and int(raw) >= seq:
                        return
                except (OSError, ValueError):
                    continue
            time.sleep(0.005)
        raise ObservationError("active watch did not acknowledge the committed event")
    finally:
        for descriptor in descriptors:
            os.close(descriptor)


__all__ = ["ObservationError", "WatchCursor", "register_watch", "wait_until_observed"]
