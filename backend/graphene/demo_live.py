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
import io
import json
import os
import shlex
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
    # dataclasses(slots=True) resolves its own module through sys.modules, so a
    # file loaded outside sys.modules blows up on the first slotted dataclass.
    sys.modules[spec.name] = module
    try:
        spec.loader.exec_module(module)
    except Exception as error:
        del sys.modules[spec.name]
        raise _DemoError(
            f"The North Star materialization script could not load: {error}"
        ) from error
    try:
        return module.materialize(dest, stdout)
    except module.MaterializeError as error:
        raise _DemoError(f"Materializing the target failed: {error}") from error
    except Exception as error:
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


def _plan_view(mission_id: str) -> dict[str, Any]:
    from .cli.mission import _plan_show_value

    return _plan_show_value(mission_id)


def _plan(mission_id: str) -> dict[str, Any]:
    return _plan_view(mission_id)["plan"]


def _print_plan(console: Console, goal: str, mission_id: str) -> None:
    """The product's own plan table — the thing the user is about to change."""
    from .cli.mission import _render_plan_table

    _say(console, f"Goal: {goal}")
    console.print(
        _render_plan_table(_plan_view(mission_id)), markup=False, highlight=False, end=""
    )


def _print_node(console: Console, mission_id: str, task_id: str) -> None:
    """One node's full contract: outcome, scopes, checks, budget, binding."""
    from .cli.mission import _render_node_contract

    view = _plan_view(mission_id)
    task = next(
        item for item in view["plan"]["tasks"] if item["task_id"] == task_id
    )
    _say(console, f"What exactly is {task_id} allowed to do?")
    console.print(
        _render_node_contract(task, view) + "\n", markup=False, highlight=False, end=""
    )


def _edit_plan(
    console: Console,
    mission_id: str,
    *,
    edit_command: str | None,
    prompt: Callable[[str], str],
) -> int:
    """Pause for the user's edit, then compile, lint, and diff the revision.

    This is the beat the product exists for, so it is the only place the demo
    stops. `--plan-edit COMMAND` runs `COMMAND <exported-plan>` instead of
    waiting on a person — the plan a live planner returns is not known until
    the run is underway, so a rehearsal has to *transform* the real export
    rather than substitute a file written in advance. Everything after the
    edit is the same code either way.
    """
    from .cli.mission import (
        _plan_diff_value,
        _plan_export_value,
        _plan_lint_value,
        _plan_revise_value,
        _render_plan_diff,
        _render_plan_lint,
    )

    view = _plan_view(mission_id)
    revision = int(view["plan_revision"])
    export = Path(tempfile.gettempdir()) / f"{mission_id}-plan-v{revision}.yaml"
    export.unlink(missing_ok=True)
    _plan_export_value(mission_id, export)
    _say(console, f"The plan is yours to change. It is exported to {export}.")
    before = export.read_text()
    if edit_command is not None:
        _say(console, f"Applying the prepared edit: {edit_command}")
        edited = subprocess.run(
            [*shlex.split(edit_command), str(export)],
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )
        if edited.returncode:
            raise _DemoError(
                "The prepared edit failed; nothing was revised or approved."
            )
        for line in edited.stdout.splitlines():
            _say(console, "  " + line)
    else:
        prompt("Edit it, then press Enter to compile the revision: ")
    if export.read_text() == before:
        raise _DemoError(
            "The plan was not changed, so there is no revision to approve."
        )
    result = _plan_revise_value(export)
    next_revision = int(result["plan_revision"])
    _say(
        console,
        f"That is revision {next_revision}, digest "
        f"{str(result['plan_sha256'])[:12]}… — a different graph, so the old "
        "approval no longer covers it.",
    )
    lint = _plan_lint_value(mission_id)
    console.print(_render_plan_lint(lint), markup=False, highlight=False, end="")
    if not lint["valid"]:
        raise _DemoError("The revision did not pass lint; nothing was approved.")
    console.print(
        _render_plan_diff(_plan_diff_value(mission_id, revision, next_revision)),
        markup=False,
        highlight=False,
        end="",
    )
    return next_revision


def _mission_argv(mission_id: str, revision: int = 1) -> list[str]:
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
        str(revision),
        "--operator-label",
        "demo",
        "--rationale",
        _RATIONALE,
    ]


def _frontier_node(mission_id: str) -> str:
    """The node that would run first — the one worth inspecting on camera."""
    view = _plan_view(mission_id)
    frontier = view.get("ready_frontier") or []
    if frontier:
        return str(frontier[0])
    return str(view["plan"]["tasks"][0]["task_id"])


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
        # `bundle create` requires an already-resolved parent, and on macOS a
        # temp dir arrives as /var/... which is a symlink to /private/var.
        output = Path(scratch).resolve(strict=True) / "bundle.json"
        bundle = mission_cli._bundle_create_value(
            argparse.Namespace(mission_id=mission_id, output=output)
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
    edit_command: str | None = None,
    prompt: Callable[[str], str] = input,
) -> int:
    # The materializer's own chatter is captured, not printed: a one-take demo
    # shows the story, not the setup script's "next commands" block.
    captured_setup = stdout if stdout is not None else io.StringIO()
    launch = runner if runner is not None else _default_runner
    try:
        _preflight()
        _say(console, "Materializing the North Star target repository...")
        target = _materialize(target_root, captured_setup)
        _say(
            console,
            f"Target ready at {target.repository} on base commit "
            f"{target.base_sha[:12]}; its own suite is green before we start.",
        )
        _doctor_ready(target.repository)
        _say(console, "Preflight is clean: git, the check executor, and the Gemini "
             "configuration are ready.")
        _write_trigger(inbox, target.repository)
        mission_id, digest = _trigger_mission(inbox, inject_check_fault)
        _say(console, f"A change arrived in the inbox (sha256 {digest[:12]}); "
             f"mission {mission_id} was proposed from it.")
        _print_plan(console, target.goal, mission_id)
        _print_node(console, mission_id, _frontier_node(mission_id))
        revision = _edit_plan(
            console, mission_id, edit_command=edit_command, prompt=prompt
        )
        _say(
            console,
            f"Approving revision {revision} — this demo runs under a "
            "pre-authorized bounded policy — and starting the mission now.",
        )
        plan = _plan(mission_id)
        process = launch(_mission_argv(mission_id, revision))
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
