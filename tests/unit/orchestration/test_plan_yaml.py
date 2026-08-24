from __future__ import annotations

import pytest

from graphene.orchestration.plan_yaml import (
    MAX_DOCUMENT_BYTES,
    PlanDocumentError,
    plan_from_yaml,
    plan_to_yaml,
)
from tests.unit.orchestration.test_store import _plan


def test_the_canonical_export_round_trips_exactly() -> None:
    """The document a person edits is the plan, byte for byte and back."""
    plan = _plan()
    document = plan_to_yaml(plan)

    assert plan_from_yaml(document) == plan
    assert plan_to_yaml(plan_from_yaml(document)) == document
    # Same plan, same bytes, every time — so two revisions diff line by line.
    assert plan_to_yaml(plan) == document


def test_the_body_is_deterministic_and_ordered() -> None:
    body = plan_to_yaml(_plan(), header=False)
    keys = [line.split(":")[0] for line in body.splitlines() if line and line[0].isalpha()]
    assert keys == sorted(keys)
    assert plan_to_yaml(_plan(), header=False) == body


def test_a_document_with_an_unknown_field_is_refused_by_name() -> None:
    document = plan_to_yaml(_plan()) + "\nsurprise: 1\n"
    with pytest.raises(PlanDocumentError, match="unknown field surprise"):
        plan_from_yaml(document)


def test_a_duplicate_key_is_refused_rather_than_silently_dropped() -> None:
    """PyYAML's default is last-key-wins, which would eat half of an edit."""
    with pytest.raises(PlanDocumentError, match="duplicate key 'revision'"):
        plan_from_yaml("mission_id: mission-1\nrevision: 1\nrevision: 2\n")


def test_a_broken_or_oversized_document_is_refused_with_one_reason() -> None:
    with pytest.raises(PlanDocumentError, match="must be a mapping"):
        plan_from_yaml("- 1\n")
    with pytest.raises(PlanDocumentError, match="not valid YAML"):
        plan_from_yaml("tasks: [\n")
    with pytest.raises(PlanDocumentError, match="too large"):
        plan_from_yaml("a" * (MAX_DOCUMENT_BYTES + 1))


def test_an_edit_that_breaks_the_model_names_the_field_that_broke() -> None:
    document = plan_to_yaml(_plan()).replace("max_concurrency: 2", "max_concurrency: 0")
    with pytest.raises(PlanDocumentError, match="max_concurrency"):
        plan_from_yaml(document)
