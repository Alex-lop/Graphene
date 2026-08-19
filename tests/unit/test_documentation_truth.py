from __future__ import annotations

import json
import re
import tomllib
from pathlib import Path
from urllib.parse import unquote

ROOT = Path(__file__).parents[2]
CANONICAL_MARKDOWN = (
    ROOT / "README.md",
    ROOT / "simplreadme.md",
    ROOT / "docs/TASKMASTER_PRODUCT_CONTRACT.md",
    ROOT / "docs/demo_transcript.md",
)
HISTORICAL_NAMES = (
    "IDEA_EVALUATION.md",
    "IMPLEMENTATION_PLAN.md",
    "ULTRA_MVP_EXECUTION.md",
    "POST_PHASE0_GRAPH_MVP_ULTRA_PLAN.md",
    "GRAPHENE_CLI_LINEAGE_JUDGE_PROMPT.md",
    "CLI_LINEAGE_JUDGE_DECISION.md",
    "GRAPHENE_ULTRA_IMPLEMENTATION_LOOP.md",
    "HACKATHON_TIMELINE.md",
)
LINK = re.compile(r"!?\[[^\]]*\]\(([^)]+)\)")


def test_every_relative_markdown_link_resolves() -> None:
    missing: list[str] = []
    for document in ROOT.rglob("*.md"):
        if any(
            part.lower() in {".git", ".venv", "all_md_files"}
            for part in document.parts
        ):
            continue
        for match in LINK.finditer(document.read_text(errors="strict")):
            raw = match.group(1).strip().strip("<>")
            target = raw.split(maxsplit=1)[0]
            if target.startswith(("https://", "http://", "mailto:", "#")):
                continue
            relative = unquote(target.split("#", 1)[0])
            if relative and not (document.parent / relative).resolve().exists():
                missing.append(f"{document.relative_to(ROOT)} -> {target}")
    assert missing == []


def test_canonical_docs_have_current_claim_discipline() -> None:
    combined = "\n".join(path.read_text() for path in CANONICAL_MARKDOWN)
    lowered = combined.lower()

    assert not re.search(r"\b[0-9a-f]{40}\b", combined)
    assert not re.search(r"\b\d+ passed\b", lowered)
    assert "uncommitted working tree" not in lowered
    assert "what the agent actually did" not in lowered
    assert "does not claim that context caused or improved" in lowered
    assert (
        "verified mission replay — generated scripted fixture; no live agent, human "
        "attestation, new test execution, gemini, or cloud"
    ) in lowered
    assert "not proven" in lowered
    assert "not deployed" in lowered
    assert "no silent fallback" in lowered or "never substitutes replay" in lowered
    assert "worktree provides edit isolation" in lowered
    assert "it is not a security sandbox" in lowered
    assert "skills are not resource-isolation units" in lowered
    assert "stateless mcp is sessionless, not processless" in lowered
    assert "chain-of-thought" in lowered
    assert "default scripted start commits a validated proposal" in lowered
    assert "--auto-approve" in lowered and "simulated_fixture" in lowered
    assert "no linked replacement revision" in lowered
    assert "automatic expiry and purge" in lowered
    assert "current mission-plan validation rejects" in lowered
    assert "no shared listener or fan-out" in lowered


def test_historical_narratives_are_visibly_classified() -> None:
    history = (ROOT / "docs/HISTORY.md").read_text()
    assert "not current claims" in history.lower()
    assert "protocol tour" in history.lower()
    for name in HISTORICAL_NAMES:
        assert name in history


def test_product_contract_is_canonical_and_legacy_contract_is_honest() -> None:
    product = json.loads((ROOT / "contracts/product_proof.json").read_text())
    golden_text = (ROOT / "contracts/golden_path.json").read_text()
    golden = json.loads(golden_text)
    history = (ROOT / "docs/HISTORY.md").read_text()
    package = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]

    assert product["schema_version"] == 2
    assert product["status"] == "canonical"
    assert product["category"] == "The Taskmaster"
    assert product["legacy_protocol_tour"]["operations"] == [
        "search_repo",
        "read_file",
        "open_evidence",
        "write_file",
        "run_fixed_test",
        "request_completion",
    ]
    assert set(product["legacy_protocol_tour"]["drivers"]) == {
        "verified-replay",
        "scripted-local",
        "adk-fake",
    }
    assert (
        product["mission_capture_boundary"]["browser_authority"]
        == "Authenticated read-only public projection; operator changes use the idempotent CLI/store path."
    )
    assert any("replanning" in item for item in product["deferred"])
    assert any("retention" in item for item in product["deferred"])
    assert product["mission_control_limits"]["legacy_v2_adapter"].startswith(
        "reserved"
    )
    assert "no linked replacement revision" in product["mission_control_limits"][
        "replan"
    ]
    assert "NOT PROVEN" in product["mission_control_limits"]["cloud_streaming"]
    assert "backend/graphene/orchestration" in product["authority"]["mission"]
    assert "backend/graphene/viewer" in product["authority"]["legacy_protocol"]

    assert golden["model"]["model_id"] == "graphene-compatibility-fixture"
    assert "gemini" not in golden_text.lower()
    assert all(step["actor"] != "gemini" for step in golden["loop"])
    assert not any(
        step["proof_type"] == "candidate.committed" for step in golden["loop"]
    )
    assert "promotion receipt" in golden["loop"][-1]["action"].lower()
    assert golden["tool_names"] == ["read_file", "write_file", "run_fixture_tests"]
    assert "golden_path.json" in history and "protocol tour" in history.lower()

    assert package["description"] == (
        "Local-first mission control for bounded multi-agent coding work"
    )
