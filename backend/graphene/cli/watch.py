"""``graphene watch inbox`` and ``graphene watch github``: mission triggers.

A watcher turns an external signal (a ``mission.yaml`` dropped in a folder, a
labeled open GitHub issue) into exactly one proposed mission through the same
``mission start`` path an operator uses, then commits a ``mission.triggered``
annotation naming the source. It can create missions only; plan approval stays
with the operator and deny-by-default stands.

Rejections are recorded artifacts (an inbox sidecar, a state-file entry, one
printed JSON line), never missions. Output carries names, digests, and fixed
reasons; never file contents, issue bodies, or paths under ``$HOME``.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import quote

import yaml

from ..hashing import canonical_json_bytes, canonical_json_sha256, sha256_hex
from ..orchestration.mission_models import MissionTrigger
from . import mission as mission_cli

INBOX_STATE_NAME = ".graphene-watch-state.json"
MAX_INBOX_BYTES = 64 * 1024
MAX_ISSUE_BODY_BYTES = 16 * 1024
MAX_RESPONSE_BYTES = 4 * 1024 * 1024
LIVE_ENV = "GRAPHENE_WATCH_GITHUB_LIVE"
GITHUB_API = "https://api.github.com"
BACKOFF_BASE_SECONDS = 60
BACKOFF_CAP_SECONDS = 3600
DRIVERS = ("gemini-adk", "scripted-local")
_YAML_KEYS = frozenset(
    {"goal", "repo", "success_criteria", "driver", "max_workers", "policy"}
)
_SAFE_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}\.ya?ml$")
_REPO = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,99}/[A-Za-z0-9][A-Za-z0-9_.-]{0,99}$")
_ISSUE_URL = re.compile(
    r"^https://github\.com/[A-Za-z0-9][A-Za-z0-9_.-]{0,99}/"
    r"[A-Za-z0-9][A-Za-z0-9_.-]{0,99}/issues/[0-9]{1,12}$"
)

#: ``fetch(url, headers) -> (status, headers, body)``; tests inject a fake.
Fetch = Callable[[str, dict[str, str]], tuple[int, dict[str, str], bytes]]
#: ``create(request, trigger fields) -> result line``; tests inject a fake.
Create = Callable[..., dict[str, object]]


class WatchError(ValueError):
    pass


def _now() -> datetime:
    return datetime.now(UTC)


def _reason(error: BaseException) -> str:
    """A fixed public reason for a rejected request; never the raw exception text."""

    if isinstance(error, (mission_cli.MissionCliError, WatchError)):
        return str(error)[:256]
    return f"mission start rejected the request ({type(error).__name__})"


def _rejectable(error: BaseException) -> bool:
    return isinstance(
        error, (WatchError, ValueError, OSError)
    ) or error.__class__.__module__.startswith("graphene.")


def create_mission(
    request: dict[str, object],
    *,
    source_kind: str,
    source_ref: str,
    source_url: str | None,
    source_sha256: str,
    observed_at: datetime,
    watcher_id: str,
    start: Callable[[argparse.Namespace], dict[str, object]] = mission_cli._start,
) -> dict[str, object]:
    """Run ``mission start`` for a validated request, then commit the trigger."""

    args = argparse.Namespace(
        repo=Path(str(request["repo"])),
        goal=str(request["goal"]),
        success_criteria=list(request.get("success_criteria") or ()),
        driver=str(request["driver"]),
        max_workers=int(request.get("max_workers") or 2),
        auto_approve=False,
        # The trigger is the event: two different files (or issues) with the
        # same goal are two missions; the same bytes twice are caught by the
        # content-digest dedupe before this point.
        command_id=f"watch_{source_kind}_{source_sha256[:48]}",
        open_viewer=False,
        json_mode=True,
    )
    try:
        result = start(args)
    except Exception as error:
        # A watcher records a rejection and keeps polling; only bugs propagate.
        if not _rejectable(error):
            raise
        return {"mission_id": None, "status": "rejected", "reason": _reason(error)}
    mission_id = str(result["mission_id"])
    if result.get("result_replayed"):
        return {
            "mission_id": mission_id,
            "status": "duplicate",
            "reason": "an identical mission request is already committed",
        }
    trigger = MissionTrigger(
        source_kind=source_kind,
        source_ref=source_ref,
        source_url=source_url,
        source_sha256=source_sha256,
        observed_at=observed_at,
        watcher_id=watcher_id,
    )
    store = mission_cli._store_for_mission(mission_id)
    store.record_trigger(
        mission_id,
        trigger,
        mission_cli._command_id("trigger", mission_id, source_sha256),
        recorded_at=observed_at,
    )
    return {
        "mission_id": mission_id,
        "status": "created",
        "reason": f"mission {result.get('status')}; plan approval stays with the operator",
    }


# --------------------------------------------------------------------------- inbox


def _load_state(path: Path, default: dict[str, object]) -> dict[str, object]:
    if path.is_symlink():
        raise WatchError("watch state file cannot be a symlink")
    if not path.exists():
        return dict(default)
    try:
        value = json.loads(path.read_bytes())
    except (OSError, ValueError) as error:
        raise WatchError("watch state file is unreadable") from error
    if (
        not isinstance(value, dict)
        or value.get("schema_version") != 1
        or not isinstance(value.get("seen"), dict)
    ):
        raise WatchError("watch state file has an unknown schema")
    return value


def _save_state(path: Path, state: dict[str, object]) -> None:
    staging = path.with_name(path.name + ".tmp")
    staging.write_bytes(canonical_json_bytes(state) + b"\n")
    os.chmod(staging, 0o600)
    os.replace(staging, path)


def _inbox_state() -> dict[str, object]:
    return {"schema_version": 1, "seen": {}}


def parse_inbox_request(raw: bytes) -> dict[str, object]:
    """Fail closed: ``yaml.safe_load`` only, a mapping, known keys, bounded values."""

    if len(raw) > MAX_INBOX_BYTES:
        raise WatchError("mission file exceeds 64 KiB")
    try:
        loaded = yaml.safe_load(raw.decode("utf-8"))
    except (UnicodeDecodeError, yaml.YAMLError) as error:
        raise WatchError("mission file is not valid UTF-8 YAML") from error
    if not isinstance(loaded, dict):
        raise WatchError("mission file must be a YAML mapping")
    unknown = set(loaded) - _YAML_KEYS
    if unknown or not all(isinstance(key, str) for key in loaded):
        raise WatchError("mission file has unknown keys")
    goal = loaded.get("goal")
    if not isinstance(goal, str) or not 1 <= len(goal.strip()) <= 1024:
        raise WatchError("goal must be a non-empty string of at most 1024 characters")
    repo = loaded.get("repo")
    if not isinstance(repo, str) or not Path(repo).is_absolute():
        raise WatchError("repo must be an absolute path")
    repository = Path(repo)
    if repository.is_symlink() or not repository.is_dir():
        raise WatchError("repo must be an existing directory")
    if not (repository / ".graphene/project.json").is_file():
        raise WatchError("repo has no .graphene/project.json; run graphene init")
    driver = loaded.get("driver")
    if driver not in DRIVERS:
        raise WatchError("driver must be gemini-adk or scripted-local")
    criteria = loaded.get("success_criteria", [])
    if criteria is None:
        criteria = []
    if (
        not isinstance(criteria, list)
        or len(criteria) > 32
        or not all(
            isinstance(item, str) and 1 <= len(item.strip()) <= 1024
            for item in criteria
        )
    ):
        raise WatchError(
            "success_criteria must be a list of at most 32 bounded strings"
        )
    max_workers = loaded.get("max_workers", 2)
    if type(max_workers) is not int or not 1 <= max_workers <= 5:
        raise WatchError("max_workers must be an integer from 1 to 5")
    policy = loaded.get("policy")
    if policy is not None:
        if not isinstance(policy, str) or not policy:
            raise WatchError("policy must be a policy id string")
        _, _, project_policy = mission_cli._load_project_policy(repository)
        if project_policy.policy_id != policy:
            raise WatchError("policy does not match the repository's project policy")
    return {
        "goal": goal.strip(),
        "repo": repo,
        "success_criteria": [item.strip() for item in criteria],
        "driver": driver,
        "max_workers": max_workers,
    }


def _move(source: Path, folder: Path, digest: str, content: dict[str, object]) -> None:
    folder.mkdir(mode=0o700, exist_ok=True)
    name = source.name if _SAFE_NAME.match(source.name) else f"{digest[:12]}.yaml"
    target = folder / name
    if target.exists() or target.is_symlink():
        target = folder / f"{digest[:12]}-{name}"
    os.replace(source, target)
    sidecar = target.with_name(target.name + ".result.json")
    sidecar.write_bytes(canonical_json_bytes(content) + b"\n")


def _inbox_candidates(directory: Path) -> list[Path]:
    names = []
    for entry in os.scandir(directory):
        if entry.name.startswith(".") or entry.is_symlink() or not entry.is_file():
            continue
        if entry.name.endswith((".yaml", ".yml")):
            names.append(entry.name)
    return [directory / name for name in sorted(names)]


def process_inbox_once(
    directory: Path,
    *,
    watcher_id: str,
    create: Create = create_mission,
    now: Callable[[], datetime] = _now,
) -> list[dict[str, object]]:
    """Process every ``*.yaml``/``*.yml`` in ``directory`` exactly once by content."""

    state_path = directory / INBOX_STATE_NAME
    state = _load_state(state_path, _inbox_state())
    seen: dict[str, object] = state["seen"]  # type: ignore[assignment]
    lines: list[dict[str, object]] = []
    for path in _inbox_candidates(directory):
        observed_at = now()
        try:
            with path.open("rb") as stream:
                raw = stream.read(MAX_INBOX_BYTES + 1)
        except OSError:
            continue
        digest = sha256_hex(raw)
        line: dict[str, object]
        remember = False
        if len(raw) > MAX_INBOX_BYTES:
            line = {
                "mission_id": None,
                "status": "rejected",
                "reason": "mission file exceeds 64 KiB",
            }
        elif not _SAFE_NAME.match(path.name):
            line = {
                "mission_id": None,
                "status": "rejected",
                "reason": "unsafe mission file name",
            }
        elif digest in seen:
            previous = seen[digest]
            line = {
                "mission_id": previous.get("mission_id")
                if isinstance(previous, dict)
                else None,
                "status": "duplicate",
                "reason": "identical content was already processed",
            }
        else:
            remember = True
            try:
                request = parse_inbox_request(raw)
            except WatchError as error:
                line = {"mission_id": None, "status": "rejected", "reason": str(error)}
            else:
                line = create(
                    request,
                    source_kind="inbox_file",
                    source_ref=path.name,
                    source_url=None,
                    source_sha256=digest,
                    observed_at=observed_at,
                    watcher_id=watcher_id,
                )
        record = {
            **line,
            "content_sha256": digest,
            "observed_at": observed_at.isoformat(),
        }
        if remember:
            seen[digest] = {"name": path.name, **record}
            _save_state(state_path, state)
        _move(
            path,
            directory / ("rejected" if line["status"] == "rejected" else "processed"),
            digest,
            record,
        )
        lines.append({"name": path.name, **line, "digest": digest})
    return lines


# -------------------------------------------------------------------------- github


def _github_state() -> dict[str, object]:
    return {"schema_version": 1, "etag": None, "seen": {}, "backoff_seconds": 0}


def _live_fetch(url: str, headers: dict[str, str]) -> tuple[int, dict[str, str], bytes]:
    request = urllib.request.Request(url, headers=headers, method="GET")
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return (
                response.status,
                dict(response.headers.items()),
                response.read(MAX_RESPONSE_BYTES + 1),
            )
    except urllib.error.HTTPError as error:
        return (
            error.code,
            dict(error.headers.items()),
            error.read(MAX_RESPONSE_BYTES + 1),
        )


def _criteria(body: str | None) -> list[str]:
    if not body:
        return []
    bullets = [
        line.strip()[2:].strip()
        for line in body.splitlines()
        if line.strip().startswith(("- ", "* "))
    ]
    bullets = [item for item in bullets if item]
    if bullets:
        return sorted(set(bullets))
    first = next((line.strip() for line in body.splitlines() if line.strip()), "")
    return [first] if first else []


def issue_request(
    item: object, *, target_repo: Path, driver: str
) -> tuple[dict[str, object], dict[str, object]]:
    """Validate one issues-endpoint item; returns ``(request, trigger fields)``."""

    if not isinstance(item, dict):
        raise WatchError("issue item is not an object")
    if "pull_request" in item:
        raise WatchError("pull requests are not mission triggers")
    number = item.get("number")
    title = item.get("title")
    body = item.get("body")
    url = item.get("html_url")
    if type(number) is not int or number < 1:
        raise WatchError("issue has no number")
    if not isinstance(title, str) or not 1 <= len(title.strip()) <= 1024:
        raise WatchError("issue title is missing or longer than 1024 characters")
    if body is not None and (
        not isinstance(body, str) or len(body.encode("utf-8")) > MAX_ISSUE_BODY_BYTES
    ):
        raise WatchError("issue body is missing, not text, or longer than 16 KiB")
    if not isinstance(url, str) or not _ISSUE_URL.match(url):
        raise WatchError("issue html_url is not a github.com issue URL")
    criteria = _criteria(body)
    if len(criteria) > 32 or any(len(line) > 1024 for line in criteria):
        raise WatchError(
            "issue body yields more than 32 criteria or one over 1024 characters"
        )
    owner_name = "/".join(url.split("/")[3:5])
    request = {
        "goal": title.strip(),
        "repo": str(target_repo),
        "success_criteria": criteria,
        "driver": driver,
        "max_workers": 2,
    }
    fields = {
        "source_kind": "github_issue",
        "source_ref": f"{owner_name}#{number}",
        "source_url": url,
        "source_sha256": canonical_json_sha256({"title": title, "body": body}),
    }
    return request, fields


def _retry_delay(
    headers: dict[str, str], state: dict[str, object], now: datetime
) -> int:
    """Exponential backoff (60s base, 3600s cap) honoring Retry-After / X-RateLimit-Reset."""

    previous = state.get("backoff_seconds")
    backoff = min(
        BACKOFF_CAP_SECONDS,
        max(BACKOFF_BASE_SECONDS, 2 * (previous if type(previous) is int else 0)),
    )
    retry_after = headers.get("retry-after")
    reset = headers.get("x-ratelimit-reset")
    if retry_after and retry_after.isdigit():
        backoff = max(backoff, int(retry_after))
    elif reset and reset.isdigit():
        backoff = max(backoff, int(reset) - int(now.timestamp()))
    backoff = min(BACKOFF_CAP_SECONDS, max(BACKOFF_BASE_SECONDS, backoff))
    state["backoff_seconds"] = backoff
    return backoff


def poll_once(
    fetch: Fetch,
    state: dict[str, object],
    *,
    repo: str,
    label: str,
    target_repo: Path,
    driver: str,
    poll_seconds: int,
    watcher_id: str,
    create: Create = create_mission,
    now: Callable[[], datetime] = _now,
    token: str | None = None,
) -> tuple[list[dict[str, object]], int]:
    """One conditional GET; returns ``(result lines, seconds until the next poll)``."""

    if not _REPO.match(repo):
        raise WatchError("repo must be OWNER/NAME")
    url = (
        f"{GITHUB_API}/repos/{repo}/issues?labels={quote(label, safe='')}"
        "&state=open&per_page=50"
    )
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "graphene-watch",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if isinstance(state.get("etag"), str):
        headers["If-None-Match"] = str(state["etag"])
    if token:
        headers["Authorization"] = f"Bearer {token}"
    status, raw_headers, body = fetch(url, headers)
    response_headers = {
        str(key).lower(): str(value) for key, value in raw_headers.items()
    }
    observed_at = now()
    remaining = response_headers.get("x-ratelimit-remaining")
    if status in {403, 429} or remaining == "0":
        delay = _retry_delay(response_headers, state, observed_at)
        if status in {403, 429}:
            return (
                [
                    {
                        "status": "backoff",
                        "reason": f"github returned {status}",
                        "delay_seconds": delay,
                    }
                ],
                delay,
            )
    else:
        delay = poll_seconds
        state["backoff_seconds"] = 0
    if status == 304:
        return [], delay
    if status != 200:
        return [{"status": "error", "reason": f"github returned {status}"}], max(
            delay, poll_seconds
        )
    if len(body) > MAX_RESPONSE_BYTES:
        return [{"status": "error", "reason": "github response exceeds 4 MiB"}], delay
    try:
        items = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        return [{"status": "error", "reason": "github response is not JSON"}], delay
    if not isinstance(items, list):
        return [{"status": "error", "reason": "github response is not a list"}], delay
    if isinstance(response_headers.get("etag"), str):
        state["etag"] = response_headers["etag"]
    seen: dict[str, object] = state["seen"]  # type: ignore[assignment]
    lines: list[dict[str, object]] = []
    for item in items:
        issue_id = item.get("id") if isinstance(item, dict) else None
        if type(issue_id) is not int or str(issue_id) in seen:
            continue
        try:
            request, fields = issue_request(
                item, target_repo=target_repo, driver=driver
            )
        except WatchError as error:
            line: dict[str, object] = {
                "mission_id": None,
                "status": "rejected",
                "reason": str(error),
            }
        else:
            line = create(
                request, observed_at=observed_at, watcher_id=watcher_id, **fields
            )
        number = item.get("number")
        seen[str(issue_id)] = {
            **line,
            "number": number if type(number) is int else None,
            "updated_at": item.get("updated_at")
            if isinstance(item.get("updated_at"), str)
            else None,
            "observed_at": observed_at.isoformat(),
        }
        lines.append(
            {"issue_id": issue_id, "number": seen[str(issue_id)]["number"], **line}
        )
    return lines, delay


# ----------------------------------------------------------------------------- CLI


def _poll_seconds(value: int | None, *, default: int, minimum: int = 1) -> int:
    seconds = default if value is None else value
    if type(seconds) is not int or not 1 <= seconds <= 3600:
        raise WatchError("--poll must be an integer number of seconds from 1 to 3600")
    return max(seconds, minimum)


def _emit(lines: list[dict[str, object]]) -> None:
    for line in lines:
        sys.stdout.write(canonical_json_bytes(line).decode() + "\n")
    sys.stdout.flush()


def _run_inbox(args: argparse.Namespace) -> int:
    directory = args.inbox_dir
    if directory is None:
        raise WatchError("watch inbox requires --dir PATH")
    if directory.is_symlink() or not directory.is_dir():
        raise WatchError("--dir must be an existing directory")
    poll = _poll_seconds(args.poll, default=5)
    watcher_id = "inbox-" + sha256_hex(str(directory.resolve()).encode())[:16]
    while True:
        _emit(process_inbox_once(directory, watcher_id=watcher_id))
        if args.once:
            return 0
        time.sleep(poll)


def _run_github(args: argparse.Namespace) -> int:
    if not args.repo or not _REPO.match(args.repo):
        raise WatchError("watch github requires --repo OWNER/NAME")
    if args.target_repo is None or args.driver is None:
        raise WatchError("watch github requires --target-repo PATH and --driver DRIVER")
    if os.environ.get(LIVE_ENV) != "1":
        raise WatchError(
            f"live GitHub polling is off; set {LIVE_ENV}=1 to contact api.github.com"
        )
    token = (
        os.environ.get("GRAPHENE_GITHUB_TOKEN")
        or os.environ.get("GITHUB_TOKEN")
        or None
    )
    poll = _poll_seconds(args.poll, default=60, minimum=1 if token else 60)
    key = sha256_hex(f"{args.repo}\0{args.label}".encode())[:16]
    state_path = args.state or (mission_cli._state_root() / f"watch-github-{key}.json")
    watcher_id = f"github-{key}"
    state = _load_state(state_path, _github_state())
    while True:
        lines, delay = poll_once(
            _live_fetch,
            state,
            repo=args.repo,
            label=args.label,
            target_repo=args.target_repo,
            driver=args.driver,
            poll_seconds=poll,
            watcher_id=watcher_id,
            token=token,
        )
        _save_state(state_path, state)
        _emit(lines)
        if args.once:
            return 0
        time.sleep(delay)


def handle(args: argparse.Namespace) -> int:
    try:
        if args.run_id == "inbox":
            return _run_inbox(args)
        return _run_github(args)
    except KeyboardInterrupt:
        return 130
    except (WatchError, mission_cli.MissionCliError) as error:
        sys.stderr.write(f"WATCH_ERROR: {error}\n")
        return 1
    except OSError:
        sys.stderr.write("WATCH_ERROR: watcher filesystem operation failed\n")
        return 1


__all__ = [
    "LIVE_ENV",
    "WatchError",
    "create_mission",
    "handle",
    "issue_request",
    "parse_inbox_request",
    "poll_once",
    "process_inbox_once",
]
