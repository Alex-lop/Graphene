import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import PurePosixPath
from struct import pack
from typing import Any


TREE_HASH_VERSION = "graphene.tree.v2"
REGULAR_FILE_MODE = 0o100644
EXECUTABLE_FILE_MODE = 0o100755
SYMLINK_MODE = 0o120000
_TREE_MODES = {REGULAR_FILE_MODE, EXECUTABLE_FILE_MODE, SYMLINK_MODE}


@dataclass(frozen=True, slots=True)
class TreeEntry:
    content: bytes
    mode: int = REGULAR_FILE_MODE


def sha256_hex(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
        allow_nan=False,
    ).encode()


def canonical_json_sha256(value: Any) -> str:
    return sha256_hex(canonical_json_bytes(value))


def _tree_path_bytes(path: str) -> bytes:
    if not isinstance(path, str):
        raise TypeError("tree paths must be strings")
    parsed = PurePosixPath(path)
    if (
        not path
        or path == "."
        or "\\" in path
        or "\0" in path
        or parsed.is_absolute()
        or ".." in parsed.parts
        or parsed.as_posix() != path
    ):
        raise ValueError("tree paths must be canonical relative POSIX paths")
    return path.encode("utf-8")


def candidate_tree_sha256(files: Mapping[str, bytes | TreeEntry]) -> str:
    entries = []
    for path, value in files.items():
        path_bytes = _tree_path_bytes(path)
        entry = value if isinstance(value, TreeEntry) else TreeEntry(value)
        if not isinstance(entry.content, bytes):
            raise TypeError("tree entry content must be bytes")
        if entry.mode not in _TREE_MODES:
            raise ValueError("tree entry mode must be 100644, 100755, or 120000")
        entries.append((path_bytes, entry))

    digest = hashlib.sha256()
    digest.update(TREE_HASH_VERSION.encode("ascii") + b"\0")
    digest.update(pack(">Q", len(entries)))
    for path, entry in sorted(entries):
        digest.update(pack(">Q", len(path)))
        digest.update(path)
        digest.update(pack(">I", entry.mode))
        digest.update(pack(">Q", len(entry.content)))
        digest.update(entry.content)
    return digest.hexdigest()
