"""``mission.triggered`` is an annotation: committed, chained, verified, stateless."""

from __future__ import annotations

from datetime import timedelta

import pytest
from pydantic import ValidationError

from graphene.orchestration.causal_query import why
from graphene.orchestration.mission_models import (
    MissionEventInput,
    MissionEventType,
    MissionStatus,
    MissionTrigger,
)
from graphene.orchestration.sqlite_mission_store import MissionConflict, SQLiteMissionStore

from .test_store import NOW, _command, _create

DIGEST = "ab" * 32


def _trigger(**overrides: object) -> MissionTrigger:
    values: dict[str, object] = {
        "source_kind": "inbox_file",
        "source_ref": "mission.yaml",
        "source_url": None,
        "source_sha256": DIGEST,
        "observed_at": NOW,
        "watcher_id": "inbox-0123456789abcdef",
    }
    values.update(overrides)
    return MissionTrigger.model_validate(values)


def test_record_trigger_appends_a_stateless_verified_annotation(tmp_path) -> None:
    store = SQLiteMissionStore(tmp_path / "mission.sqlite")
    _create(store, approve=False)
    before = store.snapshot("mission-1")

    head = store.record_trigger(
        "mission-1", _trigger(), _command("trigger-1"), recorded_at=NOW
    )
    replayed = store.record_trigger(
        "mission-1", _trigger(), _command("trigger-1"), recorded_at=NOW + timedelta(1)
    )

    assert replayed == head == store.head("mission-1")
    assert head.seq == before.head.seq + 1
    after = store.snapshot("mission-1")
    assert store.verify("mission-1") == after.head
    assert after.mission.status == before.mission.status == MissionStatus.PROPOSED
    assert after.tasks == before.tasks
    event = store.tail("mission-1", before.head.seq, 1)[0]
    assert event.event_type == MissionEventType.MISSION_TRIGGERED
    assert event.payload == _trigger().model_dump(mode="json")
    assert event.previous_event_sha256 == before.head.event_sha256

    with pytest.raises(MissionConflict):
        store.record_trigger(
            "mission-1",
            _trigger(source_ref="other.yaml"),
            _command("trigger-1"),
            recorded_at=NOW,
        )


def test_why_lists_the_trigger_first_only_when_one_exists(tmp_path) -> None:
    store = SQLiteMissionStore(tmp_path / "mission.sqlite")
    _create(store, approve=False)
    snapshot = store.snapshot("mission-1")
    untriggered = why(
        snapshot,
        store.tail("mission-1", 0, snapshot.head.seq),
        "app/a.py",
        reference_exists=lambda _reference: True,
    )
    assert [link.stage for link in untriggered.links][0] == "target"

    store.record_trigger(
        "mission-1",
        _trigger(
            source_kind="github_issue",
            source_ref="octo/repo#7",
            source_url="https://github.com/octo/repo/issues/7",
        ),
        _command("trigger-why"),
        recorded_at=NOW,
    )
    snapshot = store.snapshot("mission-1")
    result = why(
        snapshot,
        store.tail("mission-1", 0, snapshot.head.seq),
        "app/a.py",
        reference_exists=lambda _reference: True,
    )

    first = result.links[0]
    assert first.stage == "trigger" and first.status == "established"
    assert first.nodes[0].kind == "github_issue"
    assert first.nodes[0].sha256 == DIGEST
    assert first.note == "Triggered by github_issue octo/repo#7."
    assert [link.stage for link in result.links[1:]] == [
        link.stage for link in untriggered.links
    ]


def test_trigger_payload_never_carries_a_home_path_or_content_key() -> None:
    with pytest.raises(ValidationError):
        MissionEventInput(
            event_type=MissionEventType.MISSION_TRIGGERED,
            truth_kind="runtime_observed",
            authority="mission_service",
            payload=_trigger(source_ref="/Users/someone/inbox/mission.yaml").model_dump(
                mode="json"
            ),
        )
    with pytest.raises(ValidationError):
        MissionEventInput(
            event_type=MissionEventType.MISSION_TRIGGERED,
            truth_kind="runtime_observed",
            authority="mission_service",
            payload={**_trigger().model_dump(mode="json"), "content_sha256": DIGEST},
        )
    with pytest.raises(ValidationError):
        _trigger(source_kind="slack_message")
