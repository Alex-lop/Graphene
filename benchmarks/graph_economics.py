#!/usr/bin/env python3
"""Reproducible three-mode graph-economics benchmark collector."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import statistics
import subprocess
import tempfile
from pathlib import Path
from typing import Any


MODES = (
    "linear_full_history",
    "fixed_dag_scoped_context",
    "adaptive_versioned_dag",
)
METRICS = (
    "input_tokens",
    "cached_input_tokens",
    "output_tokens",
    "reasoning_tokens",
    "tool_tokens",
    "planner_tokens",
    "coordination_tokens",
    "verifier_tokens",
    "repeated_context_tokens",
    "total_tokens",
    "cost_usd",
    "wall_seconds",
    "critical_path_seconds",
    "interventions",
    "conflicts",
    "recoveries",
)
COUNT_METRICS = frozenset(METRICS) - {
    "cost_usd",
    "wall_seconds",
    "critical_path_seconds",
}
UNAVAILABLE = "unavailable"


class BenchmarkError(ValueError):
    pass


def canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        allow_nan=False,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode()


def _atomic_create(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(canonical_json_bytes(value) + b"\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.link(temporary, path)
        directory = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    except FileExistsError as error:
        raise BenchmarkError(f"refusing to overwrite {path}") from error
    finally:
        temporary.unlink(missing_ok=True)


def _validate_gate(gate: Any) -> dict[str, Any]:
    if not isinstance(gate, dict):
        raise BenchmarkError("every run requires a quality_gate object")
    definition = {
        "command": gate.get("command"),
        "deterministic": gate.get("deterministic"),
        "gate_id": gate.get("gate_id"),
    }
    if (
        not isinstance(definition["gate_id"], str)
        or not definition["gate_id"]
        or definition["deterministic"] is not True
        or not isinstance(definition["command"], list)
        or not definition["command"]
        or not all(isinstance(item, str) and item for item in definition["command"])
    ):
        raise BenchmarkError("quality_gate must name one deterministic command")
    expected = hashlib.sha256(canonical_json_bytes(definition)).hexdigest()
    if gate.get("definition_sha256") != expected or set(gate) != {
        "command",
        "definition_sha256",
        "deterministic",
        "gate_id",
    }:
        raise BenchmarkError("quality_gate definition digest or fields are invalid")
    return gate


def _validate_run(run: Any) -> dict[str, Any]:
    if not isinstance(run, dict) or run.get("schema_version") != 1:
        raise BenchmarkError("each raw run must be a schema_version 1 object")
    if run.get("mode") not in MODES:
        raise BenchmarkError("raw run has an unknown mode")
    if not isinstance(run.get("fixture_id"), str) or not run["fixture_id"]:
        raise BenchmarkError("raw run is missing fixture_id")
    if not isinstance(run.get("run_id"), str) or not run["run_id"]:
        raise BenchmarkError("raw run is missing run_id")
    if type(run.get("success")) is not bool or type(run.get("quality_gate_passed")) is not bool:
        raise BenchmarkError("success and quality_gate_passed must be booleans")
    _validate_gate(run.get("quality_gate"))
    metrics = run.get("metrics")
    if not isinstance(metrics, dict) or set(metrics) != set(METRICS):
        raise BenchmarkError("metrics must explicitly include every required value")
    for name, value in metrics.items():
        if value == UNAVAILABLE:
            continue
        valid_number = (
            type(value) is int
            if name in COUNT_METRICS
            else type(value) in {int, float}
        )
        if not valid_number or value < 0 or not math.isfinite(value):
            raise BenchmarkError(f"metric {name} must be nonnegative or unavailable")
    return run


def _nearest_rank_p95(values: list[int | float]) -> int | float:
    return sorted(values)[math.ceil(0.95 * len(values)) - 1]


def build_result(raw_runs: list[dict[str, Any]]) -> dict[str, Any]:
    runs = [_validate_run(run) for run in raw_runs]
    if not runs:
        raise BenchmarkError("at least one raw run is required")
    fixtures = {run["fixture_id"] for run in runs}
    gates = {canonical_json_bytes(run["quality_gate"]) for run in runs}
    run_ids = {run["run_id"] for run in runs}
    counts = {mode: sum(run["mode"] == mode for run in runs) for mode in MODES}
    if len(fixtures) != 1:
        raise BenchmarkError("all modes must use the same fixture")
    if len(gates) != 1:
        raise BenchmarkError("all modes must use the exact same quality gate")
    if len(run_ids) != len(runs):
        raise BenchmarkError("raw run_id values must be unique")
    if not counts[MODES[0]] or len(set(counts.values())) != 1:
        raise BenchmarkError("all three modes require the same nonzero run count")

    quality: dict[str, Any] = {}
    economics: dict[str, Any] = {}
    for mode in MODES:
        mode_runs = [run for run in runs if run["mode"] == mode]
        qualified = [
            run for run in mode_runs if run["success"] and run["quality_gate_passed"]
        ]
        known_conflicts = [
            run["metrics"]["conflicts"]
            for run in mode_runs
            if run["metrics"]["conflicts"] != UNAVAILABLE
        ]
        known_recoveries = [
            run["metrics"]["recoveries"]
            for run in mode_runs
            if run["metrics"]["recoveries"] != UNAVAILABLE
        ]
        quality[mode] = {
            "conflict_run_rate": (
                sum(value > 0 for value in known_conflicts) / len(known_conflicts)
                if known_conflicts
                else UNAVAILABLE
            ),
            "conflict_value_unavailable_runs": len(mode_runs) - len(known_conflicts),
            "gate_pass_rate": sum(run["quality_gate_passed"] for run in mode_runs)
            / len(mode_runs),
            "qualified_run_count": len(qualified),
            "recovery_run_rate": (
                sum(value > 0 for value in known_recoveries) / len(known_recoveries)
                if known_recoveries
                else UNAVAILABLE
            ),
            "recovery_value_unavailable_runs": len(mode_runs) - len(known_recoveries),
            "run_count": len(mode_runs),
            "success_rate": sum(run["success"] for run in mode_runs) / len(mode_runs),
        }
        statistics_by_metric: dict[str, Any] = {}
        unavailable_by_metric: dict[str, int] = {}
        for metric in METRICS:
            values = [run["metrics"][metric] for run in qualified]
            available = [value for value in values if value != UNAVAILABLE]
            unavailable_by_metric[metric] = len(values) - len(available)
            statistics_by_metric[metric] = (
                {
                    "available_sample_count": len(available),
                    "median": statistics.median(available),
                    "p95_nearest_rank": _nearest_rank_p95(available),
                }
                if available
                else {
                    "available_sample_count": 0,
                    "median": UNAVAILABLE,
                    "p95_nearest_rank": UNAVAILABLE,
                }
            )
        economics[mode] = {
            "excluded_failed_or_gate_failing_runs": len(mode_runs) - len(qualified),
            "statistics": statistics_by_metric,
            "unavailable_qualified_values": unavailable_by_metric,
        }

    return {
        "benchmark": "graphene.graph_economics.v1",
        "claim_boundary": (
            "Metrics and gate outcomes are runner-reported; preserve provider-unavailable "
            "values and verify raw receipts before making external claims."
        ),
        "comparison": [
            {"by_mode": quality, "section": "success_and_quality"},
            {
                "by_mode": economics,
                "section": "economics_for_successful_gate_passing_runs",
            },
        ],
        "fixture_id": next(iter(fixtures)),
        "mode_order": list(MODES),
        "quality_gate": runs[0]["quality_gate"],
        "raw_runs": runs,
        "schema_version": 1,
    }


def run_benchmark(
    command: list[str],
    *,
    fixture_id: str,
    repetitions: int,
    raw_directory: Path,
    timeout_seconds: float,
) -> list[dict[str, Any]]:
    if not command or repetitions < 1 or timeout_seconds <= 0:
        raise BenchmarkError("run requires a command, positive repetitions, and timeout")
    raw_directory.mkdir(parents=True, exist_ok=False)
    receipts = []
    for index in range(1, repetitions + 1):
        for mode in MODES:
            environment = {
                **os.environ,
                "GRAPHENE_BENCHMARK_FIXTURE_ID": fixture_id,
                "GRAPHENE_BENCHMARK_MODE": mode,
                "GRAPHENE_BENCHMARK_RUN_INDEX": str(index),
            }
            try:
                completed = subprocess.run(
                    command,
                    capture_output=True,
                    env=environment,
                    text=True,
                    timeout=timeout_seconds,
                    check=False,
                )
            except (OSError, subprocess.TimeoutExpired) as error:
                capture = {
                    "command": command,
                    "parse_error": type(error).__name__,
                    "receipt": None,
                    "returncode": UNAVAILABLE,
                    "stderr": str(getattr(error, "stderr", None) or error),
                    "stdout": str(getattr(error, "stdout", None) or ""),
                }
                _atomic_create(raw_directory / f"{index:04d}-{mode}.json", capture)
                raise BenchmarkError("runner failed before producing a receipt") from error
            try:
                receipt = json.loads(completed.stdout)
                parse_error = None
            except json.JSONDecodeError as error:
                receipt = None
                parse_error = str(error)
            capture = {
                "command": command,
                "parse_error": parse_error,
                "receipt": receipt,
                "returncode": completed.returncode,
                "stderr": completed.stderr,
                "stdout": completed.stdout,
            }
            _atomic_create(raw_directory / f"{index:04d}-{mode}.json", capture)
            if receipt is None:
                raise BenchmarkError("runner stdout was not one JSON receipt")
            _validate_run(receipt)
            if receipt["mode"] != mode or receipt["fixture_id"] != fixture_id:
                raise BenchmarkError("runner receipt does not match requested mode and fixture")
            if completed.returncode and receipt["success"]:
                raise BenchmarkError("nonzero runner exit cannot report success")
            receipts.append(receipt)
    return receipts


def _load(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise BenchmarkError(f"cannot read raw run {path}") from error


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="action", required=True)
    template = commands.add_parser("template", help="write an honest NOT PROVEN template")
    template.add_argument("--output", type=Path, required=True)
    aggregate = commands.add_parser("aggregate", help="validate and summarize raw receipts")
    aggregate.add_argument("--input", type=Path, action="append", required=True)
    aggregate.add_argument("--output", type=Path, required=True)
    run = commands.add_parser("run", help="execute one local runner in all three modes")
    run.add_argument("--fixture-id", required=True)
    run.add_argument("--output", type=Path, required=True)
    run.add_argument("--raw-directory", type=Path, required=True)
    run.add_argument("--repetitions", type=int, default=3)
    run.add_argument("--timeout-seconds", type=float, default=600)
    run.add_argument("command", nargs=argparse.REMAINDER)
    return parser


def main(argv: list[str] | None = None) -> int:
    arguments = _parser().parse_args(argv)
    if arguments.action == "template":
        result = {
            "benchmark": "graphene.graph_economics.v1",
            "comparison": [],
            "mode_order": list(MODES),
            "proof_status": "NOT PROVEN",
            "raw_runs": [],
            "reason": "No equal-gate benchmark runs have been recorded.",
            "schema_version": 1,
        }
    elif arguments.action == "aggregate":
        result = build_result([_load(path) for path in arguments.input])
    else:
        command = arguments.command[1:] if arguments.command[:1] == ["--"] else arguments.command
        result = build_result(
            run_benchmark(
                command,
                fixture_id=arguments.fixture_id,
                repetitions=arguments.repetitions,
                raw_directory=arguments.raw_directory,
                timeout_seconds=arguments.timeout_seconds,
            )
        )
    _atomic_create(arguments.output, result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
