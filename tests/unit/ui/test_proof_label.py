"""`terminal_ui: verified_local` is a claim; this is the check that can fail it."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).parents[3]


def test_terminal_ui_label_is_backed_by_a_credential_free_render_and_its_evidence() -> None:
    contract = json.loads((ROOT / "contracts/product_proof.json").read_text(encoding="utf-8"))
    label = contract["terminal_ui"]
    assert label["status"] == "verified_local"
    assert "NOT A LIVE MODEL MISSION" in label["truth_label"] and "NOT FILMED" in label["truth_label"]
    assert (ROOT / label["evidence"]).is_file()
    assert (ROOT / label["screenshot"]).is_file()
    evidence = (ROOT / label["evidence"]).read_text(encoding="utf-8")
    assert "## Transitions observed" in evidence and "→ running" in evidence
    assert "Read-only" in evidence or "read-only" in evidence
    # The command the label names runs credential-free and prints the digest banner.
    completed = subprocess.run(
        [sys.executable, "-m", "graphene.cli.main", "ui", "--replay", "taskmaster", "--once"],
        cwd=ROOT,
        env={"PATH": "/usr/bin:/bin", "PYTHONPATH": str(ROOT / "backend"), "NO_COLOR": "1", "HOME": str(ROOT)},
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert completed.returncode == 0, completed.stderr
    first, second = completed.stdout.splitlines()[:2]
    assert first.startswith("GRAPHENE mission_status_reports")
    assert "PLAN v1" in second and "digest 9b9f15f52186" in second and "AUTHORIZED" in second
    assert "->" not in completed.stdout
    for path in ("README.md", "docs/PROOF.md"):
        assert "graphene ui" in (ROOT / path).read_text(encoding="utf-8")
