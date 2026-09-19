"""Seven words from the hackathon are kept out of every tracked file, as whole words, in any case."""

import re
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).parent.parent
# Each entry is spelled backwards so that this file passes its own check.
REVERSED = ("noissim", "retsamksat", "enalp lortnoc", "ytngierevos", "eldnub", "ecnef", "esael")
BANNED = re.compile(
    r"\b(?:" + "|".join(re.escape(w[::-1]).replace(r"\ ", r"\s+") for w in REVERSED) + r")\b", re.IGNORECASE
)


def tracked_files() -> list[Path]:
    try:
        out = subprocess.run(["git", "ls-files", "-z"], cwd=ROOT, capture_output=True, text=True, check=True)
    except (OSError, subprocess.CalledProcessError):
        pytest.skip("not a git checkout")
    return [ROOT / name for name in out.stdout.split("\0") if name and name != "LICENSE"]


def test_no_tracked_text_file_contains_a_banned_word():
    hits = []
    for path in tracked_files():
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue  # binary, or deleted in the working tree
        for number, line in enumerate(text.splitlines(), 1):
            if BANNED.search(line):
                hits.append(f"{path.relative_to(ROOT)}:{number}")
    assert hits == []


def test_the_check_sees_whole_words_only():
    assert BANNED.search("the " + REVERSED[4][::-1].upper() + " is here")
    assert BANNED.search(REVERSED[2][::-1].replace(" ", "   "))  # the two-word one, however it is spaced
    assert not BANNED.search("permission to release the ui_" + REVERSED[4][::-1] + "_file")
