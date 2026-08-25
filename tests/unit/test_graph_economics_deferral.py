"""Guards for the deliberate `graph_economics` deferral.

`benchmarks/DEFERRAL.md` records why no credential-free benchmark can discharge
the economics claim. These checks fail if the deferral is quietly undone: if the
checked-in template stops saying `NOT PROVEN`, if the proof label is flipped
without evidence, or if a public surface starts advertising a measured economic
advantage.

The scan in `test_no_public_surface_claims_a_measured_economic_advantage` covers
the product-claim surfaces listed in `PUBLIC_SURFACES` only, and matches
*quantified comparative* phrasing. It is deliberately not a general-purpose
economics detector, and `test_comparative_claim_matcher_can_observe_a_violation`
exists so that this scan cannot silently degrade into a check that passes
because it can no longer see anything.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).parents[2]

PUBLIC_SURFACES = (
    ROOT / "README.md",
    ROOT / "simplreadme.md",
    ROOT / "benchmarks/README.md",
    ROOT / "benchmarks/DEFERRAL.md",
    ROOT / "docs/PRODUCT.md",
    ROOT / "docs/DEMO_GUIDE.md",
    ROOT / "docs/KNOWN_LIMITATIONS.md",
    ROOT / "docs/README.md",
)

# Quantified comparative economics: a number attached to a claim of doing
# better than some alternative. Absolute spend ("$2.30 across 14 missions") and
# aspirational thresholds in the eval protocol are intentionally not matched.
COMPARATIVE_CLAIM = re.compile(
    r"\d+(?:\.\d+)?\s*%\s*(?:fewer|less|lower|cheaper|faster|reduction)"
    r"|\d+(?:\.\d+)?\s*[x×]\s*(?:fewer|less|cheaper|faster)"
    r"|(?:saves|saved|reduces|reduced|cuts|cut)\s+(?:cost|costs|tokens|spend|rework)\s+by"
    r"|(?:cheaper|faster|fewer\s+tokens|less\s+rework)\s+than\s+"
    r"(?:a\s+|the\s+)?(?:flat|linear|single|monolithic|uncoordinated|ungoverned)",
    re.IGNORECASE,
)


def test_checked_in_template_still_says_not_proven() -> None:
    template = json.loads(
        (ROOT / "benchmarks/templates/graph_economics.not_proven.json").read_text(
            encoding="utf-8"
        )
    )
    assert template["proof_status"] == "NOT PROVEN"
    assert template["reason"] == "No equal-gate benchmark runs have been recorded."
    assert template["comparison"] == []
    assert template["raw_runs"] == []


def test_proof_label_is_still_deferred_and_names_the_deferral() -> None:
    contract = json.loads(
        (ROOT / "contracts/product_proof.json").read_text(encoding="utf-8")
    )
    economics = contract["graph_economics"]
    assert economics["status"] == "not_proven"
    truth = economics["truth"]
    assert "benchmarks/DEFERRAL.md" in truth
    assert "median, or P95 is claimed" in truth
    assert (ROOT / "benchmarks/DEFERRAL.md").is_file()


def test_readme_still_disclaims_the_benchmark() -> None:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    assert "no token-efficiency claim, and no speed or cost comparison" in readme


def test_comparative_claim_matcher_can_observe_a_violation() -> None:
    """The scan below is only worth trusting if it fires on a real violation."""
    for planted in (
        "The graph uses 40% fewer tokens.",
        "Coordinated runs are 2.5x cheaper.",
        "Graphene reduces cost by a third.",
        "The DAG is faster than a linear transcript.",
    ):
        assert COMPARATIVE_CLAIM.search(planted), planted
    for honest in (
        "$2.30 of receipt-derived spend across 14 missions",
        "no token-efficiency claim, and no speed or cost comparison",
        "results are NOT PROVEN until real equal-gate receipts exist",
    ):
        assert not COMPARATIVE_CLAIM.search(honest), honest


def test_no_public_surface_claims_a_measured_economic_advantage() -> None:
    offences: list[str] = []
    for surface in PUBLIC_SURFACES:
        assert surface.is_file(), f"public surface is missing: {surface}"
        for number, line in enumerate(
            surface.read_text(encoding="utf-8").splitlines(), start=1
        ):
            if COMPARATIVE_CLAIM.search(line):
                offences.append(f"{surface.relative_to(ROOT)}:{number}: {line.strip()}")
    assert not offences, "measured economic advantage claimed on:\n" + "\n".join(
        offences
    )
