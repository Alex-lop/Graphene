from __future__ import annotations

import argparse
import json
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from graphene.hashing import canonical_json_bytes, canonical_json_sha256, sha256_hex
from graphene.lineage.artifacts import SQLiteArtifactStore
from graphene.lineage.promotion import SQLiteCheckpointRecorder
from graphene.lineage.reducer import reduce_events
from graphene.lineage.store import SQLiteLineageStore
from graphene.models import (
    Event,
    EventInput,
    EvidenceKind,
    EvidenceReference,
    HeadCheckpoint,
    LineageAuthority,
    LineageEventType,
    SourceReference,
    TruthKind,
    VerifiedHead,
)
from graphene.viewer.contract import ViewHead
from graphene.viewer.projection import _encode_cursor, build_snapshot, snapshot_at_cursor


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SOURCE = ROOT / "tests/fixtures/viewer_replay_source.json"
DEFAULT_OUTPUT = ROOT / "backend/graphene/viewer/static/replay.json"
BASE_SHA = "49692b04fb28e2f9697d20f6dc4eaa08e3e27e4d"
_SOURCE_ARTIFACT = {
    "lifecycle_request": "operator_request",
    "policy_evaluation": "policy_receipt",
    "reducer_receipt": "evidence_blob",
    "context_compiler_receipt": "handoff_decision",
}


def _resolve(value, *, source, evidence, events, head):
    if isinstance(value, dict):
        return {
            key: _resolve(item, source=source, evidence=evidence, events=events, head=head)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [
            _resolve(item, source=source, evidence=evidence, events=events, head=head)
            for item in value
        ]
    if not isinstance(value, str) or not value.startswith("$"):
        return value
    if value == "$source.id":
        return source.id
    if value == "$source.sha256":
        return source.sha256
    if value == "$head.sha256":
        return head.event_sha256
    if value.startswith("$digest:"):
        return sha256_hex(value.removeprefix("$digest:").encode())
    if value.startswith("$evidence:"):
        index, field = value.removeprefix("$evidence:").split(".")
        return getattr(evidence[int(index)], field)
    if value.startswith("$event:"):
        run, seq, field = value.removeprefix("$event:").split(".")
        return getattr(events[(run, int(seq))], field)
    raise ValueError(f"unknown fixture placeholder: {value}")


def materialize(source_path: Path, database: Path) -> tuple[dict, dict[tuple[str, int], Event]]:
    fixture = json.loads(source_path.read_text())
    artifacts = SQLiteArtifactStore(database)
    checkpoints = SQLiteCheckpointRecorder(database)
    store = SQLiteLineageStore(
        database,
        artifact_resolver=artifacts.resolve,
        checkpoint_reader=checkpoints.read,
    )
    events: dict[tuple[str, int], Event] = {}
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    counter = 0

    def event_id() -> str:
        nonlocal counter
        counter += 1
        return f"event_fixture_{counter:04d}"

    def recorded_at() -> datetime:
        return start + timedelta(seconds=counter)

    with patch("graphene.lineage.store._new_event_id", side_effect=event_id), patch(
        "graphene.lineage.store._now", side_effect=recorded_at
    ):
        for run_alias, run in fixture["runs"].items():
            run_id = run["run_id"]
            for seq, spec in enumerate(run["events"], 1):
                source_kind = spec["source_kind"]
                artifact_kind = EvidenceKind(_SOURCE_ARTIFACT.get(source_kind, source_kind))
                stored_source = artifacts(
                    artifact_kind,
                    {"fixture": f"{run_alias}:{seq}:source:{source_kind}"},
                )
                source = SourceReference(
                    kind=source_kind,
                    id=stored_source.id,
                    sha256=stored_source.sha256,
                )
                evidence = tuple(
                    artifacts(kind, {"fixture": f"{run_alias}:{seq}:evidence:{kind}"})
                    for kind in map(EvidenceKind, spec.get("evidence_kinds", ()))
                )
                head = store.verify(run_id)
                assert isinstance(head, VerifiedHead)
                references = [*evidence]
                for target in spec.get("event_references", ()):
                    target_run, target_seq = target.split(":")
                    event = events[(target_run, int(target_seq))]
                    references.append(
                        EvidenceReference(
                            kind=EvidenceKind.EVENT,
                            id=event.event_id,
                            sha256=event.event_sha256,
                        )
                    )
                payload = _resolve(
                    spec.get("payload", {}),
                    source=source,
                    evidence=evidence,
                    events=events,
                    head=head,
                )
                event = store.append(
                    run_id,
                    head,
                    f"fixture_{run_alias}_{seq:04d}",
                    EventInput(
                        session_id=spec.get("session_id"),
                        invocation_id=spec.get("invocation_id"),
                        model_id=spec.get("model_id"),
                        tool_call_id=spec.get("tool_call_id"),
                        repo_id="graphene-demo",
                        base_sha=BASE_SHA,
                        agent_profile_id=run["agent_profile_id"],
                        policy_revision=1,
                        event_type=LineageEventType(spec["event_type"]),
                        truth_kind=TruthKind(spec["truth_kind"]),
                        authority=LineageAuthority(spec["authority"]),
                        references=tuple(references),
                        source_ref=source,
                        payload=payload,
                    ),
                )
                events[(run_alias, seq)] = event
                if spec.get("checkpoint"):
                    values = {
                        "schema_version": 2,
                        "checkpoint_id": "checkpoint_fixture_promotion",
                        "run_id": run_id,
                        "expected_seq": event.seq - 1,
                        "event_head_sha256": events[(run_alias, seq - 1)].event_sha256,
                        "purpose": "promotion_precommit",
                        "bound_artifact_kind": EvidenceKind.PROMOTION_RECEIPT,
                        "bound_artifact_id": stored_source.id,
                        "bound_artifact_sha256": stored_source.sha256,
                        "server_recorded_at": start + timedelta(seconds=counter + 1),
                    }
                    checkpoints(
                        HeadCheckpoint(
                            **values,
                            checkpoint_sha256=canonical_json_sha256(
                                {
                                    **values,
                                    "bound_artifact_kind": "promotion_receipt",
                                    "server_recorded_at": values[
                                        "server_recorded_at"
                                    ].isoformat().replace("+00:00", "Z"),
                                }
                            ),
                        )
                    )

    for run in fixture["runs"].values():
        assert isinstance(store.verify(run["run_id"]), VerifiedHead)
    return fixture, events


def render(source_path: Path = DEFAULT_SOURCE) -> bytes:
    with tempfile.TemporaryDirectory(prefix="graphene-replay-") as directory:
        database = Path(directory) / "lineage.sqlite3"
        fixture, events = materialize(source_path, database)
        root_run_id = fixture["runs"][fixture["root_run"]]["run_id"]
        snapshots = []
        current_ids = []
        for stage in fixture["stages"]:
            heads = []
            for run_alias, seq in stage.items():
                run_id = fixture["runs"][run_alias]["run_id"]
                prefix = tuple(events[(run_alias, index)] for index in range(1, seq + 1))
                projection = reduce_events(prefix)
                heads.append(
                    ViewHead(
                        run_id=run_id,
                        seq=seq,
                        event_sha256=projection.head_sha256,
                        projection_sha256=projection.projection_sha256,
                    )
                )
            cursor = _encode_cursor(root_run_id, sorted(heads, key=lambda item: item.run_id))
            snapshots.append(snapshot_at_cursor(database, root_run_id, cursor))
            run_alias, seq = next(reversed(stage.items()))
            current_ids.append(
                f"event:{fixture['runs'][run_alias]['run_id']}:{events[(run_alias, seq)].event_id}"
            )
        final = build_snapshot(database, root_run_id)
        if snapshots[-1] != final:
            raise ValueError("the final replay stage is not the verified family head")
        heads = final.model_dump(mode="json")["heads"]
        payload = {
            "snapshot": snapshots[0].model_dump(mode="json"),
            "deltas": [
                {
                    "type": "reset",
                    "cursor": snapshot.cursor,
                    "current_id": current_id,
                    "snapshot": snapshot.model_dump(mode="json"),
                }
                for snapshot, current_id in zip(snapshots[1:], current_ids[1:], strict=True)
            ],
            "meta": {
                **fixture["meta"],
                "final_graph_sha256": final.graph_sha256,
                "source_heads": heads,
            },
        }
        return canonical_json_bytes(payload) + b"\n"


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Generate replay.json from the checked-in verified v2 fixture."
    )
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    replay = render(args.source)
    if args.check:
        if not args.output.exists() or args.output.read_bytes() != replay:
            raise SystemExit(f"replay differs: generated sha256={sha256_hex(replay)}")
        return 0
    args.output.write_bytes(replay)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
