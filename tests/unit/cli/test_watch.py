"""``graphene watch inbox`` / ``graphene watch github``: fixture-driven, no network.

The inbox mission-creation test drives the real ``mission start`` path with the
scripted-local driver and is gated like the other scripted-local CLI tests. Every
rejection test and every GitHub poller test runs credential-free on any platform
with a fake ``fetch``/``create``; nothing here ever opens a socket.
"""

from __future__ import annotations

import ast
import json
import subprocess
from datetime import UTC, datetime
from pathlib import Path

import pytest

import graphene.cli.mission as mission_cli
import graphene.cli.watch as watch
from graphene.cli.main import build_parser, main
from graphene.hashing import canonical_json_sha256, sha256_hex
from graphene.orchestration.capsule import verify_mission_capsule
from graphene.orchestration.models import MissionEventType, MissionStatus
from graphene.orchestration.scripted import load_scenario, scripted_supported
from graphene.orchestration.store import SQLiteMissionStore

NOW = datetime(2026, 8, 23, 12, 0, tzinfo=UTC)
requires_scripted = pytest.mark.skipif(
    not scripted_supported(),
    reason="scripted-local mission start needs the macOS fixture sandbox",
)


def _git(repository: Path, *arguments: str) -> str:
    return subprocess.run(
        (
            "git",
            "-c",
            "user.name=Graphene Watch Fixture",
            "-c",
            "user.email=fixture@graphene.invalid",
            *arguments,
        ),
        cwd=repository,
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        timeout=20,
        check=True,
    ).stdout.strip()


@pytest.fixture
def repository(tmp_path: Path) -> Path:
    repo = tmp_path / "target-repository"
    repo.mkdir()
    _git(repo, "init", "-q", "-b", "main")
    (repo / "README.md").write_text("# Target fixture\n", encoding="utf-8")
    _git(repo, "add", "--all", "--")
    _git(repo, "commit", "-q", "-m", "base")
    mission_cli.initialize(repo)
    return repo


@pytest.fixture
def state(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    directory = tmp_path / "state"
    directory.mkdir(mode=0o700)
    monkeypatch.setenv("GRAPHENE_STATE_DIR", str(directory))
    return directory


@pytest.fixture
def inbox(tmp_path: Path) -> Path:
    directory = tmp_path / "inbox"
    directory.mkdir()
    return directory


def _lines(capsys: pytest.CaptureFixture[str]) -> list[dict[str, object]]:
    captured = capsys.readouterr()
    assert captured.err == ""
    return [json.loads(line) for line in captured.out.splitlines()]


def _sidecar(folder: Path, name: str) -> dict[str, object]:
    return json.loads((folder / f"{name}.result.json").read_text())


# --------------------------------------------------------------------------- inbox


@requires_scripted
def test_inbox_creates_one_proposed_mission_with_a_trigger_first_in_why(
    repository: Path,
    state: Path,
    inbox: Path,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    content = (
        f"goal: {json.dumps(load_scenario().goal)}\n"
        f"repo: {json.dumps(str(repository))}\n"
        "driver: scripted-local\n"
    ).encode()
    (inbox / "mission.yaml").write_bytes(content)
    digest = sha256_hex(content)

    assert main(["watch", "inbox", "--dir", str(inbox), "--once"]) == 0

    (line,) = _lines(capsys)
    assert line["name"] == "mission.yaml"
    assert line["status"] == "created"
    assert line["digest"] == digest
    mission_id = str(line["mission_id"])
    assert not (inbox / "mission.yaml").exists()
    sidecar = _sidecar(inbox / "processed", "mission.yaml")
    assert sidecar["status"] == "created"
    assert sidecar["mission_id"] == mission_id
    assert sidecar["content_sha256"] == digest
    assert json.loads((inbox / watch.INBOX_STATE_NAME).read_text())["seen"][digest][
        "mission_id"
    ] == mission_id

    store = SQLiteMissionStore(state / "missions.sqlite3")
    snapshot = store.snapshot(mission_id)
    assert snapshot.mission.status == MissionStatus.PROPOSED
    assert store.verify(mission_id) == snapshot.head
    events = store.tail(mission_id, 0, snapshot.head.seq)
    assert [event.event_type for event in events][-1] == (
        MissionEventType.MISSION_TRIGGERED
    )
    trigger = events[-1].payload
    assert trigger["source_kind"] == "inbox_file"
    assert trigger["source_ref"] == "mission.yaml"
    assert trigger["source_url"] is None
    assert trigger["source_sha256"] == digest
    assert "/" not in json.dumps(trigger)

    assert main(["why", "status_report/redact.py", "--mission", mission_id, "--json"]) == 0
    why = json.loads(capsys.readouterr().out)
    assert why["links"][0]["stage"] == "trigger"
    assert why["links"][0]["nodes"][0]["sha256"] == digest
    assert why["links"][0]["note"] == "Triggered by inbox_file mission.yaml."
    assert main(["why", "status_report/redact.py", "--mission", mission_id]) == 0
    rendered = capsys.readouterr().out.splitlines()
    assert rendered[1] == "STAGE trigger established"

    # The same content dropped again is a recorded duplicate, never a second mission.
    (inbox / "again.yaml").write_bytes(content)
    assert main(["watch", "inbox", "--dir", str(inbox), "--once"]) == 0
    (again,) = _lines(capsys)
    assert again["status"] == "duplicate" and again["mission_id"] == mission_id
    assert store.head(mission_id) == snapshot.head
    assert _sidecar(inbox / "processed", "again.yaml")["status"] == "duplicate"

    # Operator approval (never the watcher) executes the fixture; the capsule
    # verifier then recomputes the chain that now carries the trigger.
    assert (
        main(
            [
                "--json",
                "mission",
                "approve-plan",
                mission_id,
                "--revision",
                "1",
                "--operator-label",
                "watch-test",
                "--rationale",
                "Approve the triggered fixture plan.",
            ]
        )
        == 0
    )
    assert json.loads(capsys.readouterr().out)["status"] == "awaiting_result"
    output = tmp_path / "capsule-out"
    output.mkdir(mode=0o700)
    assert (
        main(["--json", "mission", "capsule", "export", mission_id, "--output", str(output)])
        == 0
    )
    exported = json.loads(capsys.readouterr().out)
    verified = verify_mission_capsule(Path(str(exported["capsule_dir"])))
    assert verified["verified"] is True, verified
    assert main(["why", "status_report/redact.py", "--mission", mission_id, "--json"]) == 0
    stages = [link["stage"] for link in json.loads(capsys.readouterr().out)["links"]]
    assert stages[:2] == ["trigger", "target"] and len(stages) == 7


@pytest.mark.parametrize(
    ("name", "content", "reason"),
    [
        ("broken.yaml", b"goal: [unterminated\n", "not valid UTF-8 YAML"),
        ("latin.yaml", b"goal: caf\xe9\n", "not valid UTF-8 YAML"),
        ("list.yml", b"- goal\n- repo\n", "must be a YAML mapping"),
        ("extra.yaml", b"goal: g\nrepo: /nope\ndriver: scripted-local\nwebhook: x\n", "unknown keys"),
        ("norepo.yaml", b"goal: g\nrepo: /definitely/not/here\ndriver: scripted-local\n", "existing directory"),
        ("relative.yaml", b"goal: g\nrepo: ../escape\ndriver: scripted-local\n", "absolute path"),
        ("big.yaml", b"goal: " + b"x" * (64 * 1024) + b"\n", "exceeds 64 KiB"),
        ("evil\\..\\..\\x.yaml", b"goal: g\n", "unsafe mission file name"),
    ],
)
def test_inbox_rejections_are_sidecars_never_missions(
    state: Path,
    inbox: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    name: str,
    content: bytes,
    reason: str,
) -> None:
    monkeypatch.setattr(mission_cli, "_start", lambda args: pytest.fail("_start was called"))
    (inbox / name).write_bytes(content)

    assert main(["watch", "inbox", "--dir", str(inbox), "--once"]) == 0

    (line,) = _lines(capsys)
    assert line["status"] == "rejected" and line["mission_id"] is None
    assert reason in str(line["reason"])
    assert not (inbox / name).exists()
    sidecars = list((inbox / "rejected").glob("*.result.json"))
    assert len(sidecars) == 1
    sidecar = json.loads(sidecars[0].read_text())
    assert sidecar["status"] == "rejected" and sidecar["mission_id"] is None
    assert not (state / "missions.sqlite3").exists()
    assert str(state) not in json.dumps(line)


def test_inbox_rejects_an_uninitialized_repo_and_a_foreign_policy_id(
    tmp_path: Path, state: Path, inbox: Path, repository: Path, monkeypatch
) -> None:
    bare = tmp_path / "bare"
    bare.mkdir()
    with pytest.raises(watch.WatchError, match="graphene init"):
        watch.parse_inbox_request(
            f"goal: g\nrepo: {json.dumps(str(bare))}\ndriver: gemini-adk\n".encode()
        )
    with pytest.raises(watch.WatchError, match="policy does not match"):
        watch.parse_inbox_request(
            f"goal: g\nrepo: {json.dumps(str(repository))}\ndriver: gemini-adk\n"
            "policy: some-other-policy\n".encode()
        )
    for bad in (b"max_workers: 9\n", b"max_workers: '2'\n", b"success_criteria: a\n"):
        with pytest.raises(watch.WatchError):
            watch.parse_inbox_request(
                f"goal: g\nrepo: {json.dumps(str(repository))}\ndriver: gemini-adk\n".encode()
                + bad
            )
    request = watch.parse_inbox_request(
        f"goal: ' g '\nrepo: {json.dumps(str(repository))}\ndriver: gemini-adk\n"
        "success_criteria: [' one ']\nmax_workers: 3\n".encode()
    )
    assert request == {
        "goal": "g",
        "repo": str(repository),
        "success_criteria": ["one"],
        "driver": "gemini-adk",
        "max_workers": 3,
    }


def test_inbox_skips_dotfiles_and_symlinks_and_requires_a_directory(
    state: Path, inbox: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    (inbox / ".editor-temp.yaml").write_bytes(b"goal: g\n")
    outside = tmp_path / "outside.yaml"
    outside.write_bytes(b"goal: g\n")
    (inbox / "link.yaml").symlink_to(outside)

    assert main(["watch", "inbox", "--dir", str(inbox), "--once"]) == 0
    assert _lines(capsys) == []
    assert (inbox / ".editor-temp.yaml").exists() and (inbox / "link.yaml").is_symlink()

    assert main(["watch", "inbox", "--dir", str(tmp_path / "missing"), "--once"]) == 1
    assert "WATCH_ERROR" in capsys.readouterr().err
    assert main(["watch", "inbox", "--once"]) == 1
    assert main(["watch", "inbox", "--dir", str(inbox), "--once", "--poll", "0"]) == 1


# -------------------------------------------------------------------------- github


def _issue(number: int, title: str | None = "Add a status export", body: str | None = None, **extra):
    item: dict[str, object] = {
        "id": 1000 + number,
        "number": number,
        "body": body,
        "html_url": f"https://github.com/octo/repo/issues/{number}",
        "updated_at": "2026-08-23T11:00:00Z",
    }
    if title is not None:
        item["title"] = title
    item.update(extra)
    return item


class _FakeGitHub:
    def __init__(self, responses: list[tuple[int, dict[str, str], object]]) -> None:
        self.responses = list(responses)
        self.requests: list[tuple[str, dict[str, str]]] = []

    def __call__(self, url: str, headers: dict[str, str]):
        self.requests.append((url, dict(headers)))
        status, response_headers, body = self.responses.pop(0)
        raw = body if isinstance(body, bytes) else json.dumps(body).encode()
        return status, response_headers, raw


class _FakeCreate:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def __call__(self, request, **fields):
        self.calls.append({"request": request, **fields})
        return {
            "mission_id": f"mission_fake_{len(self.calls)}",
            "status": "created",
            "reason": "fake",
        }


def _poll(fetch, state, create, **overrides):
    options = {
        "repo": "octo/repo",
        "label": "graphene-mission",
        "target_repo": Path("/target"),
        "driver": "gemini-adk",
        "poll_seconds": 60,
        "watcher_id": "github-test",
        "create": create,
        "now": lambda: NOW,
    }
    options.update(overrides)
    return watch.poll_once(fetch, state, **options)


def test_github_poll_creates_missions_skips_pull_requests_and_honors_etag() -> None:
    first = [
        _issue(1, body="- Tests pass\n- Docs updated\n"),
        _issue(2, body="Just one line of context.\nMore text."),
        _issue(3, pull_request={"url": "https://api.github.com/repos/octo/repo/pulls/3"}),
    ]
    fetch = _FakeGitHub(
        [
            (200, {"ETag": 'W/"abc"', "X-RateLimit-Remaining": "59"}, first),
            (304, {"ETag": 'W/"abc"'}, b""),
            (200, {"ETag": 'W/"def"'}, first),
        ]
    )
    create = _FakeCreate()
    state = watch._github_state()

    lines, delay = _poll(fetch, state, create, token="ghp_secret_value_0000000000")

    url, headers = fetch.requests[0]
    assert url == (
        "https://api.github.com/repos/octo/repo/issues"
        "?labels=graphene-mission&state=open&per_page=50"
    )
    assert headers["Authorization"] == "Bearer ghp_secret_value_0000000000"
    assert "If-None-Match" not in headers
    assert delay == 60
    assert [line["status"] for line in lines] == ["created", "created", "rejected"]
    assert lines[2]["reason"] == "pull requests are not mission triggers"
    assert len(create.calls) == 2
    assert create.calls[0]["request"] == {
        "goal": "Add a status export",
        "repo": "/target",
        "success_criteria": ["Docs updated", "Tests pass"],
        "driver": "gemini-adk",
        "max_workers": 2,
    }
    assert create.calls[0]["source_ref"] == "octo/repo#1"
    assert create.calls[0]["source_url"] == "https://github.com/octo/repo/issues/1"
    assert create.calls[0]["source_sha256"] == canonical_json_sha256(
        {"title": "Add a status export", "body": "- Tests pass\n- Docs updated\n"}
    )
    assert create.calls[1]["request"]["success_criteria"] == ["Just one line of context."]
    assert state["etag"] == 'W/"abc"'
    assert set(state["seen"]) == {"1001", "1002", "1003"}
    assert state["seen"]["1003"]["status"] == "rejected"
    assert state["seen"]["1001"]["updated_at"] == "2026-08-23T11:00:00Z"
    assert "ghp_secret" not in json.dumps(lines) + json.dumps(state)

    lines, delay = _poll(fetch, state, create)
    assert fetch.requests[1][1]["If-None-Match"] == 'W/"abc"'
    assert lines == [] and delay == 60 and len(create.calls) == 2

    # A fresh 200 carrying already-seen ids re-triggers nothing.
    lines, _ = _poll(fetch, state, create)
    assert lines == [] and len(create.calls) == 2
    assert state["etag"] == 'W/"def"'


def test_github_rate_limits_back_off_without_creating_missions() -> None:
    fetch = _FakeGitHub(
        [
            (403, {"Retry-After": "120"}, b"rate limited"),
            (429, {}, b""),
            (429, {}, b""),
            (
                200,
                {"X-RateLimit-Remaining": "0", "X-RateLimit-Reset": str(int(NOW.timestamp()) + 900)},
                [_issue(9)],
            ),
            (200, {"X-RateLimit-Remaining": "10"}, []),
        ]
    )
    create = _FakeCreate()
    state = watch._github_state()

    lines, delay = _poll(fetch, state, create)
    assert delay == 120 and lines == [{"status": "backoff", "reason": "github returned 403", "delay_seconds": 120}]
    _, delay = _poll(fetch, state, create)
    assert delay == 240
    _, delay = _poll(fetch, state, create)
    assert delay == 480
    assert create.calls == []

    lines, delay = _poll(fetch, state, create)
    assert delay == 960 and [line["status"] for line in lines] == ["created"]
    _, delay = _poll(fetch, state, create)
    assert delay == 60 and state["backoff_seconds"] == 0

    capped = watch._github_state()
    capped["backoff_seconds"] = 3600
    _, delay = _poll(_FakeGitHub([(429, {}, b"")]), capped, create)
    assert delay == 3600


def test_github_hostile_issues_are_recorded_rejections() -> None:
    items = [
        _issue(1, title=None),
        _issue(2, title="   "),
        _issue(3, body="x" * (16 * 1024 + 1)),
        _issue(4, html_url="https://evil.example/octo/repo/issues/4"),
        _issue(5, html_url="https://github.com/octo/repo/pull/5"),
        _issue(6, body=12345),
        _issue(7, body="\n".join(f"- c{index}" for index in range(33))),
        {"id": "not-an-int", "number": 8, "title": "t", "html_url": "https://github.com/o/r/issues/8"},
        "garbage",
    ]
    fetch = _FakeGitHub(
        [
            (200, {}, items),
            (200, {}, b"\xff\xfe not utf-8"),
            (200, {}, {"a": 1}),
            (500, {}, b""),
        ]
    )
    create = _FakeCreate()
    state = watch._github_state()

    lines, _ = _poll(fetch, state, create)
    assert create.calls == []
    assert [line["status"] for line in lines] == ["rejected"] * 7
    assert {line["reason"] for line in lines} == {
        "issue title is missing or longer than 1024 characters",
        "issue body is missing, not text, or longer than 16 KiB",
        "issue html_url is not a github.com issue URL",
        "issue body yields more than 32 criteria or one over 1024 characters",
    }
    assert len(state["seen"]) == 7
    assert all(entry["status"] == "rejected" for entry in state["seen"].values())
    assert "x" * 100 not in json.dumps(lines) + json.dumps(state)

    assert _poll(fetch, state, create)[0] == [{"status": "error", "reason": "github response is not JSON"}]
    assert _poll(fetch, state, create)[0] == [{"status": "error", "reason": "github response is not a list"}]
    assert _poll(fetch, state, create)[0] == [{"status": "error", "reason": "github returned 500"}]
    with pytest.raises(watch.WatchError):
        _poll(_FakeGitHub([]), state, create, repo="octo/repo/extra")


def test_github_cli_refuses_the_network_unless_explicitly_live(
    state: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch
) -> None:
    monkeypatch.delenv(watch.LIVE_ENV, raising=False)
    monkeypatch.setattr(watch, "_live_fetch", lambda url, headers: pytest.fail("network"))
    argv = ["watch", "github", "--repo", "octo/repo", "--target-repo", str(tmp_path), "--driver", "scripted-local", "--once"]

    assert main(argv) == 1
    assert watch.LIVE_ENV in capsys.readouterr().err
    assert main(["watch", "github", "--repo", "octo", "--once"]) == 1
    assert main(["watch", "github", "--repo", "octo/repo", "--once"]) == 1

    # With the flag set the loop runs once against the injected fetch and persists state.
    monkeypatch.setenv(watch.LIVE_ENV, "1")
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    monkeypatch.delenv("GRAPHENE_GITHUB_TOKEN", raising=False)
    fetch = _FakeGitHub([(200, {"ETag": '"e1"'}, [])])
    monkeypatch.setattr(watch, "_live_fetch", fetch)
    state_file = tmp_path / "gh-state.json"
    assert main([*argv, "--state", str(state_file), "--poll", "5"]) == 0
    assert capsys.readouterr().out == ""
    assert json.loads(state_file.read_text())["etag"] == '"e1"'
    assert "Authorization" not in fetch.requests[0][1]


def test_create_mission_records_rejections_duplicates_and_triggers(monkeypatch) -> None:
    calls: list[object] = []

    def rejecting(args):
        calls.append(args)
        raise mission_cli.MissionCliError("run graphene init --repo PATH")

    request = {"goal": "g", "repo": "/target", "success_criteria": [], "driver": "gemini-adk"}
    fields = {
        "source_kind": "inbox_file",
        "source_ref": "mission.yaml",
        "source_url": None,
        "source_sha256": "ab" * 32,
        "observed_at": NOW,
        "watcher_id": "inbox-test",
    }
    rejected = watch.create_mission(request, start=rejecting, **fields)
    assert rejected == {"mission_id": None, "status": "rejected", "reason": "run graphene init --repo PATH"}
    assert calls[0].auto_approve is False and calls[0].open_viewer is False
    assert calls[0].max_workers == 2 and calls[0].json_mode is True

    duplicate = watch.create_mission(
        request, start=lambda args: {"mission_id": "m1", "result_replayed": True}, **fields
    )
    assert duplicate["status"] == "duplicate" and duplicate["mission_id"] == "m1"

    def broken(args):
        raise RuntimeError("bug")

    with pytest.raises(RuntimeError):
        watch.create_mission(request, start=broken, **fields)


# ---------------------------------------------------------------------- boundaries


def test_watch_module_never_touches_an_approval_path() -> None:
    source = Path(watch.__file__).read_text()
    tree = ast.parse(source)
    identifiers = {
        node.id for node in ast.walk(tree) if isinstance(node, ast.Name)
    } | {node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute)}
    identifiers |= {
        alias.name for node in ast.walk(tree) if isinstance(node, ast.ImportFrom) for alias in node.names
    }
    assert not {name for name in identifiers if "approve" in name.lower()}
    assert "_mutate" not in identifiers and "approve_plan" not in source
    imported = {
        alias.name.split(".")[0]
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    } | {
        str(node.module).split(".")[0]
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.level == 0
    }
    assert imported.isdisjoint({"requests", "httpx"})


def test_watch_parser_keeps_the_positional_stream_form() -> None:
    parser = build_parser()
    streamed = parser.parse_args(["watch", "run_abc", "--after-seq", "4", "--snapshot"])
    assert (streamed.run_id, streamed.after_seq, streamed.snapshot) == ("run_abc", 4, True)
    assert streamed.inbox_dir is None and streamed.poll is None
    triggered = parser.parse_args(["watch", "inbox", "--dir", "drop", "--once", "--poll", "7"])
    assert (triggered.run_id, triggered.inbox_dir, triggered.once, triggered.poll) == (
        "inbox",
        Path("drop"),
        True,
        7,
    )
    github = parser.parse_args(["watch", "github", "--repo", "o/r", "--target-repo", ".", "--driver", "gemini-adk"])
    assert github.label == "graphene-mission" and github.driver == "gemini-adk"
