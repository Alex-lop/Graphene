"""The `graphene ui` command: pick a source, then show it or dump frames."""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

from ..orchestration.mission_replay import DEFAULT_REPLAY_PATH, load_verified_mission_replay
from .frames import compose_frame
from .read_only_store import ReadOnlyMissionStore
from .sources import LiveSource, ReplaySource, UiSource

_STOP_STATES = {"completed", "failed", "cancelled", "rejected", "awaiting_result"}


class UiError(Exception):
    """A usage or lookup problem the command reports on stderr with exit 2."""


def register(commands: argparse._SubParsersAction) -> None:  # type: ignore[type-arg]
    ui = commands.add_parser(
        "ui",
        allow_abbrev=False,
        help="draw the signed map in the terminal and follow the mission, read-only",
    )
    ui.add_argument("--replay", metavar="SOURCE", help="render the verified replay: 'taskmaster' or a replay file")
    ui.add_argument("--mission", dest="mission_id", help="attach to this mission instead of the most recent active one")
    ui.add_argument("--speed", type=float, default=1.0, help="seconds per replay checkpoint; 0 steps only on n/p")
    ui.add_argument("--poll", type=float, default=0.25, help="live poll interval in seconds")
    ui.add_argument("--once", action="store_true", help="print one plain-text frame and exit")
    ui.add_argument("--frames", metavar="DIR", help="write a plain-text frame to DIR whenever the view changes, then exit")
    ui.add_argument("--max-seconds", type=float, default=600.0, help="stop a --frames dump after this long")
    ui.add_argument("--state-dir", help=argparse.SUPPRESS)


def build_source(args: argparse.Namespace) -> UiSource:
    if args.replay:
        path = DEFAULT_REPLAY_PATH if args.replay == "taskmaster" else Path(args.replay)
        if not path.is_file():
            raise UiError(f"no replay at {path}")
        return ReplaySource(load_verified_mission_replay(path))
    from ..cli.mission import _state_root  # the CLI owns the state-root rules
    from ..hashing import sha256_hex

    root = Path(args.state_dir) if getattr(args, "state_dir", None) else _state_root()
    store = ReadOnlyMissionStore(root / "missions.sqlite3")
    mission_id = args.mission_id or store.most_recent_active_mission()
    if mission_id is None:
        raise UiError("no active mission; pass --mission MISSION_ID or --replay taskmaster")
    if mission_id not in store.mission_ids():
        raise UiError(f"unknown mission {mission_id}")
    # Same layout the CLI derives for the mission's private runtime; the
    # evidence store is what lets the projection validate publications.
    evidence = root / "missions" / sha256_hex(mission_id.encode())[:32] / "attempt-evidence.sqlite3"
    return LiveSource(store, mission_id, evidence_path=evidence)


def dump_frames(source: UiSource, directory: Path, *, poll_seconds: float, max_seconds: float) -> int:
    """Write every distinct frame until the mission stops or time runs out."""

    directory.mkdir(parents=True, exist_ok=True)
    deadline = time.monotonic() + max_seconds
    last = None
    count = 0
    while True:
        snapshot = source.snapshot()  # one read per poll; the frame and the stop test share it
        frame = compose_frame(source, snapshot=snapshot)
        if frame != last:
            count += 1
            (directory / f"frame-{count:04d}.txt").write_text(frame + "\n", encoding="utf-8")
            last = frame
        if source.label == "replay":
            finished = not source.step(1)  # a replay ends at its last checkpoint
        else:
            finished = snapshot is not None and str(snapshot.mission.status) in _STOP_STATES
        if finished:
            # The store may still be settling; a closing summary over a refused
            # read would be a stale picture, so re-read until the read is clean.
            for _ in range(50):
                closing = source.snapshot()
                if source.notice() is None:
                    break
                time.sleep(0.05)
            (directory / f"frame-{count + 1:04d}.txt").write_text(
                compose_frame(source, pane="summary", snapshot=closing) + "\n", encoding="utf-8"
            )
            return count + 1
        if time.monotonic() >= deadline:
            return count
        time.sleep(poll_seconds)


def handle(args: argparse.Namespace) -> int:
    try:
        source = build_source(args)
        if args.once:
            sys.stdout.write(compose_frame(source) + "\n")
            return 0
        if args.frames:
            written = dump_frames(source, Path(args.frames), poll_seconds=args.poll, max_seconds=args.max_seconds)
            sys.stdout.write(f"wrote {written} frame(s) to {args.frames}\n")
            return 0
    except UiError as error:
        sys.stderr.write(f"graphene ui: {error}\n")
        return 2
    from .tui import GrapheneUI

    autoplay = args.speed if (args.replay and args.speed > 0) else None
    GrapheneUI(source, poll_seconds=args.poll, autoplay_seconds=autoplay).run()
    return 0
