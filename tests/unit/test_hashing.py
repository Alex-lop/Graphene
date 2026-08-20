import hashlib

import pytest

from graphene.hashing import (
    EXECUTABLE_FILE_MODE,
    REGULAR_FILE_MODE,
    SYMLINK_MODE,
    TREE_HASH_VERSION,
    TreeEntry,
    candidate_tree_sha256,
)


def _reference_hash(files: dict[str, bytes | TreeEntry]) -> str:
    encoded = TREE_HASH_VERSION.encode("ascii") + b"\0"
    encoded += len(files).to_bytes(8, "big")
    entries = []
    for path, value in files.items():
        entry = value if isinstance(value, TreeEntry) else TreeEntry(value)
        entries.append((path.encode("utf-8"), entry))
    for path, entry in sorted(entries):
        encoded += len(path).to_bytes(8, "big") + path
        encoded += entry.mode.to_bytes(4, "big")
        encoded += len(entry.content).to_bytes(8, "big") + entry.content
    return hashlib.sha256(encoded).hexdigest()


def test_tree_hash_v2_eliminates_the_exact_v1_nul_collision():
    one_file = {"a": b"X\0b\0Y"}
    two_files = {"a": b"X", "b": b"Y"}

    assert candidate_tree_sha256(one_file) != candidate_tree_sha256(two_files)


def test_tree_hash_v2_covers_binary_empty_and_prefix_like_entries():
    cases = (
        {"binary": bytes(range(256)) + b"\0tail"},
        {"empty": b""},
        {"a": b"bc"},
        {"ab": b"c"},
        {"a/b": b"c"},
        {},
    )

    assert len({candidate_tree_sha256(case) for case in cases}) == len(cases)
    assert all(candidate_tree_sha256(case) == _reference_hash(case) for case in cases)


def test_tree_hash_v2_distinguishes_mode_and_symlink_type():
    content = b"bin/tool"
    regular = {"entry": TreeEntry(content, REGULAR_FILE_MODE)}
    executable = {"entry": TreeEntry(content, EXECUTABLE_FILE_MODE)}
    symlink = {"entry": TreeEntry(content, SYMLINK_MODE)}

    assert len(
        {
            candidate_tree_sha256(regular),
            candidate_tree_sha256(executable),
            candidate_tree_sha256(symlink),
        }
    ) == 3
    assert candidate_tree_sha256(symlink) == _reference_hash(symlink)


def test_tree_hash_v2_order_is_stable_and_matches_reference_encoder():
    first = {"z": b"last", "é": b"unicode", "a/b": b"nested"}
    second = dict(reversed(tuple(first.items())))

    assert candidate_tree_sha256(first) == candidate_tree_sha256(second)
    assert candidate_tree_sha256(first) == _reference_hash(first)


@pytest.mark.parametrize(
    "path",
    ("", ".", "./a", "/a", "a/../b", "a//b", "a/", "a\\b", "a\0b"),
)
def test_tree_hash_v2_rejects_noncanonical_paths(path: str):
    with pytest.raises(ValueError, match="canonical relative POSIX"):
        candidate_tree_sha256({path: b"content"})


def test_tree_hash_v2_rejects_unknown_modes_and_non_bytes():
    with pytest.raises(ValueError, match="mode"):
        candidate_tree_sha256({"file": TreeEntry(b"content", 0o100600)})
    with pytest.raises(TypeError, match="bytes"):
        candidate_tree_sha256({"file": "content"})  # type: ignore[dict-item]
