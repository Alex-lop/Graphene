import hashlib
import json
import sys
from pathlib import Path

import pytest

from benchmarks.graph_economics import (
    METRICS,
    MODES,
    BenchmarkError,
    canonical_json_bytes,
    main,
)


def test_three_mode_run_is_equal_gate_raw_preserving_and_never_overwrites(tmp_path: Path):
    gate_definition = {
        "command": ["python", "-m", "pytest", "-q", "tests/fixture_gate.py"],
        "deterministic": True,
        "gate_id": "fixture-gate-v1",
    }
    gate = {
        **gate_definition,
        "definition_sha256": hashlib.sha256(canonical_json_bytes(gate_definition)).hexdigest(),
    }
    runner = tmp_path / "runner.py"
    runner.write_text(
        "import json, os\n"
        f"gate={gate!r}\n"
        f"names={METRICS!r}\n"
        "mode=os.environ['GRAPHENE_BENCHMARK_MODE']\n"
        "index=int(os.environ['GRAPHENE_BENCHMARK_RUN_INDEX'])\n"
        "metrics={name:index for name in names}\n"
        "metrics['cost_usd']='unavailable'\n"
        "success=not(mode=='linear_full_history' and index==2)\n"
        "print(json.dumps({'schema_version':1,'run_id':f'{mode}-{index}',"
        "'mode':mode,'fixture_id':os.environ['GRAPHENE_BENCHMARK_FIXTURE_ID'],"
        "'success':success,'quality_gate':gate,'quality_gate_passed':success,'metrics':metrics}))\n"
    )
    output = tmp_path / "result.json"
    raw = tmp_path / "raw"

    assert main(
        [
            "run",
            "--fixture-id",
            "fixture-v1",
            "--repetitions",
            "2",
            "--raw-directory",
            str(raw),
            "--output",
            str(output),
            "--",
            sys.executable,
            str(runner),
        ]
    ) == 0

    result = json.loads(output.read_text())
    assert result["mode_order"] == list(MODES)
    assert [section["section"] for section in result["comparison"]] == [
        "success_and_quality",
        "economics_for_successful_gate_passing_runs",
    ]
    assert len(result["raw_runs"]) == len(MODES) * 2
    assert len(tuple(raw.glob("*.json"))) == len(MODES) * 2
    economics = result["comparison"][1]["by_mode"]
    for mode in MODES:
        expected = (
            {"available_sample_count": 1, "median": 1, "p95_nearest_rank": 1}
            if mode == "linear_full_history"
            else {"available_sample_count": 2, "median": 1.5, "p95_nearest_rank": 2}
        )
        assert economics[mode]["statistics"]["total_tokens"] == expected
        assert economics[mode]["statistics"]["cost_usd"]["median"] == "unavailable"
        assert economics[mode]["unavailable_qualified_values"]["cost_usd"] == expected[
            "available_sample_count"
        ]
    assert economics["linear_full_history"]["excluded_failed_or_gate_failing_runs"] == 1

    with pytest.raises(BenchmarkError, match="overwrite"):
        main(["template", "--output", str(output)])

    unequal = [dict(run) for run in result["raw_runs"]]
    unequal[0] = {**unequal[0], "quality_gate": {**gate, "gate_id": "other"}}
    inputs = []
    for index, run in enumerate(unequal):
        path = tmp_path / f"run-{index}.json"
        path.write_text(json.dumps(run))
        inputs.extend(["--input", str(path)])
    with pytest.raises(BenchmarkError, match="quality_gate"):
        main(["aggregate", *inputs, "--output", str(tmp_path / "bad.json")])

    missing = dict(result["raw_runs"][0])
    missing.pop("quality_gate")
    missing_path = tmp_path / "missing.json"
    missing_path.write_text(json.dumps(missing))
    with pytest.raises(BenchmarkError, match="quality_gate"):
        main(
            [
                "aggregate",
                "--input",
                str(missing_path),
                "--output",
                str(tmp_path / "missing-result.json"),
            ]
        )
