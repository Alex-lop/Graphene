"""``graphene demo --live``: the one public product path as one continuous story.

This module is glue over existing verbs. It owns preflight, North Star target
materialization, the inbox trigger, the bounded-plan display, delegated
approval, mission execution in a subprocess, the live dashboard, result
isolation, an on-screen run of the generated feature, and ``why``. Every
printed line is a plain human sentence or a table row; raw JSON never appears.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tarfile
import tempfile
import time
from collections.abc import Callable, Sequence
from functools import partial
from pathlib import Path
from typing import IO, Any

from rich.console import Console

from .hashing import sha256_hex

_REPO_ROOT = Path(__file__).resolve().parents[2]
_MATERIALIZE_SCRIPT = _REPO_ROOT / "scripts" / "materialize_north_star.py"
_TRIGGER_TEMPLATE = _REPO_ROOT / "demo" / "north_star" / "mission.yaml"
_PLACEHOLDER = "/ABSOLUTE/PATH/TO/north-star-target"
_TRIGGER_NAME = "north-star.yaml"
_RATIONALE = "Pre-authorized bounded North Star demo policy."
# A tiny but real ledger: BOLT-M8 lands below its reorder level and one note
# carries an address the redaction policy must strip, so the generated report
# has something honest to show.
_SAMPLE_LEDGER: dict[str, list[dict[str, object]]] = {
    "items": [
        {"sku": "BOLT-M8", "name": "M8 bolt", "reorder_level": 70},
        {"sku": "NUT-M8", "name": "M8 nut"},
    ],
    "movements": [
        {"movement_id": "m1", "sku": "BOLT-M8", "kind": "receipt", "quantity": 100,
         "recorded_at": "2024-05-01T09:00:00+00:00"},
        {"movement_id": "m2", "sku": "BOLT-M8", "kind": "issue", "quantity": 40,
         "recorded_at": "2024-05-01T10:00:00+00:00", "note": "shipped; ask ops@example.com"},
        {"movement_id": "m3", "sku": "NUT-M8", "kind": "receipt", "quantity": 25,
         "recorded_at": "2024-05-01T11:00:00+00:00"},
    ],
}


class _DemoError(RuntimeError):
    """One plain sentence for the operator; never a traceback."""


def _say(console: Console, line: str) -> None:
    console.print(line, markup=False, highlight=False)


def _preflight() -> None:
    if shutil.which("git") is None:
        raise _DemoError("The live demo needs git on PATH and it is not there.")
    if not os.environ.get("GRAPHENE_CHECK_EXECUTOR"):
        if sys.platform != "darwin":
            raise _DemoError("The live demo needs GRAPHENE_CHECK_EXECUTOR set on this platform.")
        os.environ["GRAPHENE_CHECK_EXECUTOR"] = "host-sandbox"


def _materialize(dest: Path, stdout: IO[str]) -> Any:
    if not _MATERIALIZE_SCRIPT.is_file() or not _TRIGGER_TEMPLATE.is_file():
        raise _DemoError(
            "graphene demo --live needs a repository clone; the North Star "
            "target scripts are not installed with the wheel."
        )
    spec = importlib.util.spec_from_file_location("graphene_north_star", _MATERIALIZE_SCRIPT)
    if spec is None or spec.loader is None:
        raise _DemoError("The North Star materialization script could not load.")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    try:
        return module.materialize(dest, stdout)
    except module.MaterializeError as error:
        raise _DemoError(f"Materializing the target failed: {error}") from error


def _doctor_ready(repository: Path) -> None:
    from .cli.mission import doctor

    value = doctor(repository)
    if not value["gemini_preflight"]["configuration_ready"]:
        raise _DemoError(
            "Preflight failed: the live demo needs git, Google ADK, exactly one "
            "Gemini credential mode, and a usable project policy before it runs."
        )


def _write_trigger(inbox: Path, repository: Path) -> Path:
    text = _TRIGGER_TEMPLATE.read_text(encoding="utf-8").replace(_PLACEHOLDER, str(repository))
    path = inbox / _TRIGGER_NAME
    path.write_text(text, encoding="utf-8")
    return path


def _trigger_mission(inbox: Path, inject_check_fault: bool) -> tuple[str, str]:
    """Create the mission by running the inbox watcher's single-shot pass.

    ``inject_check_fault`` rides the watcher's injectable ``start`` seam into
    ``mission._start``, which records it in the same private start binding
    (``demo_injected_check_fault``) that ``graphene mission demo`` uses.
    """
    from .cli import mission as mission_cli
    from .cli import watch

    def start(args: argparse.Namespace) -> dict[str, object]:
        if inject_check_fault:
            args.demo_injected_check_fault = True
        return mission_cli._start(args)

    watcher_id = "inbox-" + sha256_hex(str(inbox.resolve()).encode())[:16]
    lines = watch.process_inbox_once(
        inbox, watcher_id=watcher_id, create=partial(watch.create_mission, start=start)
    )
    for line in lines:
        if line.get("name") != _TRIGGER_NAME:
            continue
        if line.get("status") != "created" or not line.get("mission_id"):
            raise _DemoError(f"The watcher did not accept the trigger: {line.get('reason')}.")
        return str(line["mission_id"]), str(line["digest"])
    raise _DemoError("The watcher never saw the trigger file it was given.")


def _plan(mission_id: str) -> dict[str, Any]:
    from .cli.mission import _plan_show_value

    return _plan_show_value(mission_id)["plan"]


def _print_plan(console: Console, goal: str, plan: dict[str, Any]) -> None:
    _say(console, f"Goal: {goal}")
    _say(console, f"Bounded plan, revision {plan['revision']}:")
    for task in plan["tasks"]:
        needs = ", ".join(task.get("dependencies", ())) or "nothing"
        writes = ", ".join(task.get("write_paths", ())) or "nothing"
        _say(console, f"  {task['task_id']}  {task['kind']}  needs {needs}  writes {writes}")
    _say(console, "Success criteria:")
    for criterion in plan.get("criteria", ()):
        _say(console, f"  - {criterion['description']}")


def _mission_argv(mission_id: str) -> list[str]:
    executable = shutil.which("graphene")
    base = (
        [executable]
        if executable
        else [
            sys.executable,
            "-c",
            "from graphene.cli.main import main; raise SystemExit(main())",
        ]
    )
    return base + [
        "--json",
        "mission",
        "approve-plan",
        mission_id,
        "--revision",
        "1",
        "--operator-label",
        "demo",
        "--rationale",
        _RATIONALE,
    ]


def _default_runner(argv: Sequence[str]) -> subprocess.Popen:
    # The dashboard owns the terminal; the subprocess's JSON stays off screen.
    return subprocess.Popen(
        list(argv),
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        env=dict(os.environ),
    )


def _follow(
    mission_id: str,
    console: Console,
    clock: Callable[[], float],
    sleeper: Callable[[float], None],
    process: Any,
) -> None:
    from .cli import mission as mission_cli
    from .cli.dashboard import follow

    store = mission_cli._store_for_mission(mission_id)
    evidence = mission_cli._mission_evidence(store, mission_id)
    follow(
        mission_cli._projection(mission_id),
        mission_id,
        console=console,
        spend=lambda _snapshot: mission_cli._mission_spend(store, evidence, mission_id),
        latest=lambda snapshot: mission_cli._latest_line(store, mission_id, snapshot.head.seq),
        clock=clock,
        sleeper=sleeper,
        # approve-plan runs the whole mission synchronously, so once its
        # process has exited nothing can append events: the projection is not
        # going to move again and a crashed mission cannot hang the demo.
        stop=lambda: process.poll() is not None,
    )


def _mission_status(mission_id: str) -> str:
    from .cli import mission as mission_cli

    return str(mission_cli._projection(mission_id).snapshot(mission_id).mission.status)


def _fault_fired(mission_id: str) -> bool:
    from .cli import mission as mission_cli
    from .orchestration.models import MissionEventType

    store = mission_cli._store_for_mission(mission_id)
    after = 0
    while True:
        events = store.tail(mission_id, after, 256)
        if not events:
            return False
        if any(event.event_type == MissionEventType.TASK_RETRIED for event in events):
            return True
        after = events[-1].seq


def _finalize(mission_id: str) -> dict[str, Any]:
    """Create the pending bundle, then approve the result bound to its exact id."""
    from .cli import mission as mission_cli

    with tempfile.TemporaryDirectory(prefix="graphene-demo-bundle-") as scratch:
        bundle = mission_cli._bundle_create_value(
            argparse.Namespace(mission_id=mission_id, output=Path(scratch) / "bundle.json")
        )
    return mission_cli._mutate(
        argparse.Namespace(
            mission_action="approve-result",
            mission_id=mission_id,
            bundle_id=bundle["bundle_id"],
            operator_label="demo",
            rationale=_RATIONALE,
            confirm_human=False,
            command_id=None,
        )
    )


def _run_generated_feature(mission_id: str, commit_sha: str, console: Console) -> None:
    """Run the target's own CLI from the isolated result commit, on screen."""
    from .cli import mission as mission_cli

    repository = mission_cli._mission_runtime(mission_id) / "repository"
    with tempfile.TemporaryDirectory(prefix="graphene-demo-result-") as scratch:
        checkout = Path(scratch) / "result"
        checkout.mkdir()
        archive = Path(scratch) / "result.tar"
        # `git archive` reads the commit without ever mutating the owned repo.
        with archive.open("wb") as stream:
            exported = subprocess.run(
                ["git", "archive", "--format=tar", commit_sha],
                cwd=repository, stdin=subprocess.DEVNULL, stdout=stream,
                stderr=subprocess.DEVNULL, timeout=60, check=False,
            )
        if exported.returncode:
            raise _DemoError("The isolated result commit could not be exported for the feature run.")
        with tarfile.open(archive) as tar:
            tar.extractall(checkout, filter="data")
        ledger = Path(scratch) / "ledger.json"
        ledger.write_text(json.dumps(_SAMPLE_LEDGER), encoding="utf-8")
        argv = [sys.executable, "-m", "ledger_service", "--ledger", str(ledger),
                "report", "--format", "markdown"]
        run = subprocess.run(
            argv, cwd=checkout, stdin=subprocess.DEVNULL, capture_output=True,
            text=True, timeout=120, check=False,
        )
    if run.returncode:
        raise _DemoError("The generated report command failed inside the isolated result.")
    _say(console, "The generated feature, run from the isolated result commit:")
    for line in run.stdout.splitlines():
        _say(console, "  " + line)


def _why_text(mission_id: str, path: str) -> str:
    from .cli import mission as mission_cli

    value = mission_cli._why_value(argparse.Namespace(mission_id=mission_id, path=path))
    return mission_cli._render_why(value)


def run_live_demo(
    *,
    target_root: Path,
    inbox: Path,
    console: Console,
    runner: Callable[[Sequence[str]], subprocess.Popen] | None = None,
    sleeper: Callable[[float], None] = time.sleep,
    clock: Callable[[], float] = time.monotonic,
    inject_check_fault: bool = True,
    stdout: IO[str] | None = None,
) -> int:
    out = stdout if stdout is not None else sys.stdout
    launch = runner if runner is not None else _default_runner
    try:
        _preflight()
        _say(console, "Materializing the North Star target repository...")
        target = _materialize(target_root, out)
        _doctor_ready(target.repository)
        _say(console, "Preflight is clean: git, the check executor, and the Gemini "
             "configuration are ready.")
        _write_trigger(inbox, target.repository)
        mission_id, digest = _trigger_mission(inbox, inject_check_fault)
        _say(console, f"A change arrived in the inbox (sha256 {digest[:12]}); "
             f"mission {mission_id} was proposed from it.")
        plan = _plan(mission_id)
        _print_plan(console, target.goal, plan)
        _say(console, "This demo runs under a pre-authorized bounded policy; approving "
             "the plan and starting the mission now.")
        process = launch(_mission_argv(mission_id))
        _follow(mission_id, console, clock, sleeper, process)
        exit_code = process.wait()
        status = _mission_status(mission_id)
        if inject_check_fault:
            if _fault_fired(mission_id):
                _say(console, "The injected check fault fired: one check failed on purpose "
                     "and a bounded retry was authorized with a diagnostic.")
            else:
                _say(console, "The injected check fault did not fire this run, so no retry "
                     "is being claimed.")
        if status != "awaiting_result":
            _say(console, f"The mission ended {status} (subprocess exit {exit_code}); "
                 "skipping the result and feature beats rather than faking them.")
            return 1
        decision = _finalize(mission_id)
        commit = str(decision["local_commit_sha"])
        _say(console, f"Result approved and isolated: commit {commit[:12]} on "
             f"{decision['result_ref']}; nothing was pushed anywhere.")
        _run_generated_feature(mission_id, commit, console)
        why_path = next(
            (path for task in plan["tasks"] for path in task.get("write_paths", ())),
            "ledger_service",
        )
        _say(console, f"And why did {why_path} change? The mission can answer:")
        console.print(_why_text(mission_id, why_path), markup=False, highlight=False, end="")
        _say(console, "The story is complete: trigger, bounded plan, approval, execution, "
             "isolated result, working feature, and provenance.")
        return 0
    except _DemoError as error:
        _say(console, str(error))
        return 1
    except Exception as error:
        from .cli.mission import MissionCliError
        from .cli.watch import WatchError

        if isinstance(error, (MissionCliError, WatchError)):
            _say(console, str(error))
            return 1
        raise


__all__ = ["run_live_demo"]
