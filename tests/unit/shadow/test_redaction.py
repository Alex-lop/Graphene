"""Ingest-time redaction: secret patterns, bounded excerpts, path classes."""

from __future__ import annotations

from pathlib import Path

import pytest

from graphene.shadow.redaction import (
    COMMAND_EXCERPT_LIMIT,
    MESSAGE_EXCERPT_LIMIT,
    REDACTED,
    bounded_excerpt,
    classify_path,
    collapse_home,
    normalize_relative,
    redact_text,
)

JWT = (
    "eyJhbGciOiJIUzI1NiJ9."
    "eyJzdWIiOiIxMjM0NTY3ODkwIn0."
    "SflKxwRJSMeKKF2QT4fwpMeJf36POk6yJV_adQssw5c"
)
PEM = "-----BEGIN RSA PRIVATE KEY-----\nMIIEowIBAAKCAQEA\n-----END RSA PRIVATE KEY-----"

# One sample per secret pattern: (id, text, substring that must disappear).
SECRETS: tuple[tuple[str, str, str], ...] = (
    ("pem-block", f"key file:\n{PEM}\ndone", "MIIEowIBAAKCAQEA"),
    (
        "bearer",
        "Authorization: Bearer abcdefghijklmnopqrstuvwxyz012345",
        "abcdefghijklmnopqrstuvwxyz012345",
    ),
    (
        "api-key-assignment",
        "export OPENAI_API_KEY=abcd1234efgh5678",
        "abcd1234efgh5678",
    ),
    ("access-key-assignment", "aws_access_key_id = AKIAXXXXYYYY", "AKIAXXXXYYYY"),
    (
        "secret-assignment",
        "AWS_SECRET_ACCESS_KEY: 'wJalrXUtnFEMI/K7MDENG'",
        "wJalrXUtnFEMI/K7MDENG",
    ),
    ("token-assignment", 'GITHUB_TOKEN="ghx_abcdefgh"', "ghx_abcdefgh"),
    ("password-assignment", "password=hunter22", "hunter22"),
    ("passwd-assignment", "DB_PASSWD: s3cretvalue", "s3cretvalue"),
    ("credentials-assignment", "credentials=alice:wonderland", "wonderland"),
    ("private-key-assignment", "PRIVATE_KEY=deadbeefcafe", "deadbeefcafe"),
    ("aws-access-key", "key AKIAIOSFODNN7EXAMPLE here", "AKIAIOSFODNN7EXAMPLE"),
    ("google-api-key", "AIza" + "A" * 35, "AIza" + "A" * 35),
    ("github-token", "token ghp_" + "A" * 30 + " ok", "ghp_" + "A" * 30),
    ("github-pat", "github_pat_" + "A" * 30, "github_pat_" + "A" * 30),
    ("slack-token", "xoxb-123456789012-abcdefghijkl", "xoxb-123456789012-abcdefghijkl"),
    ("sk-key", "sk-" + "a" * 40, "sk-" + "a" * 40),
    ("jwt", f"header {JWT} trailer", JWT),
    (
        "url-credentials",
        "git clone https://alice:s3cretpass@github.com/org/repo.git",
        "s3cretpass",
    ),
)


@pytest.mark.parametrize(
    ("text", "secret"),
    [pytest.param(text, secret, id=name) for name, text, secret in SECRETS],
)
def test_every_secret_pattern_is_redacted(text: str, secret: str) -> None:
    scrubbed = redact_text(text)

    assert secret not in scrubbed
    assert REDACTED in scrubbed


def test_pem_block_is_redacted_whole() -> None:
    assert redact_text(PEM) == REDACTED
    assert "BEGIN" not in redact_text(f"before {PEM} after")


def test_url_credentials_keep_the_host() -> None:
    assert (
        redact_text("https://alice:s3cretpass@github.com/org/repo.git")
        == f"{REDACTED}github.com/org/repo.git"
    )


@pytest.mark.parametrize(
    "text",
    (
        "uv run --frozen pytest -q tests/unit",
        "the token bucket refills every second",
        "git commit -m 'tighten the secret scanning rules'",
        "All tests pass.",
    ),
)
def test_ordinary_text_is_untouched(text: str) -> None:
    assert redact_text(text) == text
    assert REDACTED not in text


def test_multiple_secrets_are_all_redacted() -> None:
    scrubbed = redact_text("API_KEY=abcd1234 and sk-" + "b" * 32 + " and " + JWT)

    assert scrubbed.count(REDACTED) == 3
    assert "abcd1234" not in scrubbed
    assert JWT not in scrubbed


# -- bounded excerpts --------------------------------------------------------


def test_excerpt_limits_are_the_documented_values() -> None:
    assert MESSAGE_EXCERPT_LIMIT == 280
    assert COMMAND_EXCERPT_LIMIT == 200
    assert REDACTED == "<redacted>"


def test_bounded_excerpt_truncates_with_a_single_ellipsis_character() -> None:
    text = "x" * 50

    excerpt = bounded_excerpt(text, 10)

    assert excerpt == "x" * 9 + "…"
    assert excerpt is not None and len(excerpt) == 10
    assert bounded_excerpt("x" * 10, 10) == "x" * 10
    assert bounded_excerpt("x" * 11, 10) == "x" * 9 + "…"
    long_excerpt = bounded_excerpt("y" * 1000, MESSAGE_EXCERPT_LIMIT)
    assert long_excerpt is not None and len(long_excerpt) == MESSAGE_EXCERPT_LIMIT
    assert long_excerpt.endswith("…")


def test_bounded_excerpt_collapses_whitespace_and_strips_control_characters() -> None:
    assert bounded_excerpt("  a \n\t b\r\n  c  ", 80) == "a b c"
    assert bounded_excerpt("a\x00b\x07c\x1fd\x7fe\x0bf\x0cg", 80) == "abcdefg"
    assert bounded_excerpt("\x1b[31mred\x1b[0m", 80) == "[31mred[0m"


@pytest.mark.parametrize("text", ("", "   ", "\n\t\r", "\x00\x07", " \x1f "))
def test_bounded_excerpt_returns_none_when_nothing_remains(text: str) -> None:
    assert bounded_excerpt(text, 80) is None


def test_bounded_excerpt_redacts_before_bounding() -> None:
    assert bounded_excerpt("run with token=abcd1234", 80) == f"run with {REDACTED}"
    excerpt = bounded_excerpt("sk-" + "a" * 40 + " " + "tail " * 40, 30)
    assert excerpt is not None
    assert excerpt.startswith(REDACTED)
    assert "aaaa" not in excerpt
    assert len(excerpt) == 30


@pytest.mark.parametrize("limit", (1, 0, -5))
def test_bounded_excerpt_rejects_limits_without_room_for_an_ellipsis(
    limit: int,
) -> None:
    with pytest.raises(ValueError, match="ellipsis"):
        bounded_excerpt("text", limit)


# -- home collapsing ---------------------------------------------------------


def test_collapse_home_replaces_only_the_exact_prefix() -> None:
    home = Path("/Users/alex")

    assert collapse_home("/Users/alex/project/file.py", home) == "~/project/file.py"
    assert collapse_home("/Users/alex", home) == "~"
    assert collapse_home("/Users/alexander/file.py", home) == "/Users/alexander/file.py"
    assert collapse_home("/tmp/file.py", home) == "/tmp/file.py"
    assert collapse_home("/Users/alex/", Path("/Users/alex/")) == "~/"


def test_collapse_home_with_root_home_is_a_no_op() -> None:
    assert collapse_home("/etc/passwd", Path("/")) == "/etc/passwd"


def test_collapse_home_defaults_to_the_current_home(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))

    assert collapse_home((tmp_path / "notes.txt").as_posix()) == "~/notes.txt"
    assert collapse_home("/opt/tool") == "/opt/tool"


# -- repository-relative normalization ---------------------------------------


@pytest.mark.parametrize(
    ("raw", "expected"),
    (
        ("src/app.py", "src/app.py"),
        ("./src/app.py", "src/app.py"),
        ("src//app.py", "src/app.py"),
        ("src/./app.py", "src/app.py"),
        ("src/", "src"),
        ("README.md", "README.md"),
        ("a" * 256, "a" * 256),
    ),
)
def test_normalize_relative_canonicalizes(raw: str, expected: str) -> None:
    assert normalize_relative(raw) == expected


@pytest.mark.parametrize(
    "raw",
    (
        "",
        ".",
        "./",
        "..",
        "../escape.py",
        "src/../escape.py",
        "src/..",
        "/etc/passwd",
        "src\\app.py",
        "src/app\0.py",
        "a" * 257,
    ),
)
def test_normalize_relative_rejects_escapes_absolutes_and_backslashes(
    raw: str,
) -> None:
    assert normalize_relative(raw) is None


# -- path classification -----------------------------------------------------

REPO = Path("/Users/alex/repo")
HOME = Path("/Users/alex")


@pytest.mark.parametrize(
    ("raw", "cwd", "expected"),
    (
        ("src/app.py", REPO, ("src/app.py", None)),
        ("./src/app.py", REPO, ("src/app.py", None)),
        ("/Users/alex/repo/src/app.py", REPO, ("src/app.py", None)),
        ("/Users/alex/repo/./src/../src/app.py", REPO, ("src/app.py", None)),
        ("app.py", REPO / "src", ("src/app.py", None)),
        ("../tests/test_app.py", REPO / "src", ("tests/test_app.py", None)),
        ("  src/app.py  ", REPO, ("src/app.py", None)),
        ("/Users/alex/repo", REPO, (None, None)),
        ("/Users/alex/repo/", REPO, (None, None)),
        (".", REPO, (None, None)),
        ("/etc/passwd", REPO, (None, "/etc/passwd")),
        ("../notes.txt", REPO, (None, "~/notes.txt")),
        ("/Users/alex/notes.txt", REPO, (None, "~/notes.txt")),
        ("/Users/alex/repo/../notes.txt", REPO, (None, "~/notes.txt")),
        ("/Users/alex/repo-other/x.py", REPO, (None, "~/repo-other/x.py")),
        ("/tmp/scratch.txt", REPO / "src", (None, "/tmp/scratch.txt")),
    ),
)
def test_classify_path_against_a_repository_root(
    raw: str, cwd: Path, expected: tuple[str | None, str | None]
) -> None:
    assert classify_path(raw, repo_root=REPO, cwd=cwd, home=HOME) == expected


@pytest.mark.parametrize(
    ("raw", "expected"),
    (
        ("src/app.py", ("src/app.py", None)),
        ("./src/app.py", ("src/app.py", None)),
        ("../escape.py", (None, None)),
        ("src\\app.py", (None, None)),
        ("/Users/alex/repo/src/app.py", (None, "~/repo/src/app.py")),
        ("/etc/passwd", (None, "/etc/passwd")),
        ("/a/./b/../c", (None, "/a/c")),
    ),
)
def test_classify_path_without_a_repository_root(
    raw: str, expected: tuple[str | None, str | None]
) -> None:
    assert classify_path(raw, repo_root=None, cwd=None, home=HOME) == expected
    assert classify_path(raw, repo_root=None, cwd=REPO, home=HOME) == expected


def test_classify_path_with_a_root_but_no_cwd_treats_relative_as_in_repo() -> None:
    assert classify_path("src/app.py", repo_root=REPO, cwd=None, home=HOME) == (
        "src/app.py",
        None,
    )
    assert classify_path("../x.py", repo_root=REPO, cwd=None, home=HOME) == (
        None,
        None,
    )
    assert classify_path("/etc/hosts", repo_root=REPO, cwd=None, home=HOME) == (
        None,
        "/etc/hosts",
    )


@pytest.mark.parametrize("raw", ("", "   ", "src/\0app.py", "a" * 4097))
def test_classify_path_rejects_unusable_input(raw: str) -> None:
    assert classify_path(raw, repo_root=REPO, cwd=REPO, home=HOME) == (None, None)
    assert classify_path(raw, repo_root=None, cwd=None, home=HOME) == (None, None)


def test_classify_path_never_touches_the_filesystem(tmp_path: Path) -> None:
    root = tmp_path / "absent-repo"
    link_target = tmp_path / "elsewhere"

    assert classify_path("link/file.py", repo_root=root, cwd=root, home=HOME) == (
        "link/file.py",
        None,
    )
    assert not root.exists()
    assert not link_target.exists()
