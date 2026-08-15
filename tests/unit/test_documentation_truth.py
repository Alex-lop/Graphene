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
    ROOT / "IMPLEMENTATION_STATUS.md",
    ROOT / "docs/demo_transcript.md",
)
HISTORICAL_MARKDOWN = (
    ROOT / "IDEA_EVALUATION.md",
    ROOT / "IMPLEMENTATION_PLAN.md",
    ROOT / "ULTRA_MVP_EXECUTION.md",
    ROOT / "POST_PHASE0_GRAPH_MVP_ULTRA_PLAN.md",
    ROOT / "GRAPHENE_CLI_LINEAGE_JUDGE_PROMPT.md",
    ROOT / "CLI_LINEAGE_JUDGE_DECISION.md",
    ROOT / "GRAPHENE_ULTRA_IMPLEMENTATION_LOOP.md",
    ROOT / "HACKATHON_TIMELINE.md",
)
LINK = re.compile(r"!?\[[^\]]*\]\(([^)]+)\)")


def test_every_relative_markdown_link_resolves() -> None:
    missing: list[str] = []
    for document in ROOT.rglob("*.md"):
        if any(part in {".git", ".venv"} for part in document.parts):
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
    assert "current head" not in lowered
    assert "base head" not in lowered
    assert "agent a" not in lowered
    assert "fresh agent" not in lowered
    assert "what the agent actually did" not in lowered
    assert "do not establish that memory caused or improved" in lowered
    assert "graph-derived context is not agent input" in lowered
    assert "no live agent, human attestation, or new test execution" in lowered
    assert "not gemini or independent-agent proof" in lowered


def test_historical_narratives_are_visibly_classified() -> None:
    history = (ROOT / "docs/HISTORY.md").read_text()
    for document in HISTORICAL_MARKDOWN:
        assert "not current product truth" in document.read_text().lower()
        assert document.name in history


def test_product_contract_is_canonical_and_legacy_contract_is_honest() -> None:
    product = json.loads((ROOT / "contracts/product_proof.json").read_text())
    golden_text = (ROOT / "contracts/golden_path.json").read_text()
    golden = json.loads(golden_text)
    decisions = (ROOT / "DECISIONS.md").read_text()
    package = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]

    assert product["status"] == "canonical"
    assert product["capture_boundary"]["operations"] == [
        "search_repo",
        "read_file",
        "open_evidence",
        "write_file",
        "run_fixed_test",
        "request_completion",
    ]
    assert set(product["drivers"]) == {"verified-replay", "scripted-local", "adk-fake"}
    assert product["capture_boundary"]["browser_authority"].startswith("Read-only")
    assert any("graph-to-agent" in item for item in product["deferred"])

    assert golden["model"]["model_id"] == "graphene-compatibility-fixture"
    assert "gemini" not in golden_text.lower()
    assert all(step["actor"] != "gemini" for step in golden["loop"])
    assert not any(step["proof_type"] == "candidate.committed" for step in golden["loop"])
    assert "promotion receipt" in golden["loop"][-1]["action"].lower()
    assert golden["tool_names"] == ["read_file", "write_file", "run_fixture_tests"]
    assert "golden_path.json" in decisions and "compatibility-only" in decisions

    assert package["description"] == "Evidence-backed review and handoff for bounded coding-agent work"
