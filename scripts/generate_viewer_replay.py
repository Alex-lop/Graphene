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
from graphene.lineage.lineage_reducer import reduce_events
from graphene.lineage.sqlite_lineage_store import SQLiteLineageStore
from graphene.core_models import (
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
from graphene.viewer.contract import GraphSnapshot, ViewHead
from graphene.viewer.viewer_projection import (
    _encode_cursor,
    apply_deltas,
    build_snapshot,
    current_node_id,
    diff_snapshots,
    snapshot_at_cursor,
)
from graphene.viewer.viewer_replay import apply_replay_envelope


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SOURCE = ROOT / "tests/fixtures/viewer_replay_source.json"
DEFAULT_OUTPUT = ROOT / "backend/graphene/viewer/static/replay.json"
DEFAULT_DIGEST = ROOT / "backend/graphene/viewer/static/replay.sha256"
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
            key: _resolve(
                item, source=source, evidence=evidence, events=events, head=head
            )
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


def materialize(
    source_path: Path, database: Path
) -> tuple[dict, dict[tuple[str, int], Event]]:
    fixture = json.loads(source_path.read_text())
    artifacts = SQLiteArtifactStore(database)
    checkpoints = SQLiteCheckpointRecorder(database)
    store = SQLiteLineageStore(
        database,
        artifact_resolver=artifacts.resolve,
        checkpoint_reader=checkpoints.read,
    )
    events: dict[tuple[str, int], Event] = {}
    evidence_by_event: dict[tuple[str, int], tuple[EvidenceReference, ...]] = {}
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    counter = 0

    def event_id() -> str:
        nonlocal counter
        counter += 1
        return f"event_fixture_{counter:04d}"

    def recorded_at() -> datetime:
        return start + timedelta(seconds=counter)

    with (
        patch("graphene.lineage.sqlite_lineage_store._new_event_id", side_effect=event_id),
        patch("graphene.lineage.sqlite_lineage_store._now", side_effect=recorded_at),
    ):
        for run_alias, run in fixture["runs"].items():
            run_id = run["run_id"]
            for seq, spec in enumerate(run["events"], 1):
                source_kind = spec["source_kind"]
                artifact_kind = EvidenceKind(
                    _SOURCE_ARTIFACT.get(source_kind, source_kind)
                )
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
                for target in spec.get("evidence_references", ()):
                    target_run, target_seq, target_index = target.split(":")
                    references.append(
                        evidence_by_event[(target_run, int(target_seq))][int(target_index)]
                    )
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
                    evidence=tuple(references),
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
                evidence_by_event[(run_alias, seq)] = evidence
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
                                    "server_recorded_at": values["server_recorded_at"]
                                    .isoformat()
                                    .replace("+00:00", "Z"),
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
                prefix = tuple(
                    events[(run_alias, index)] for index in range(1, seq + 1)
                )
                projection = reduce_events(prefix)
                heads.append(
                    ViewHead(
                        run_id=run_id,
                        seq=seq,
                        event_sha256=projection.head_sha256,
                        projection_sha256=projection.projection_sha256,
                    )
                )
            cursor = _encode_cursor(
                root_run_id, sorted(heads, key=lambda item: item.run_id)
            )
            snapshots.append(snapshot_at_cursor(database, root_run_id, cursor))
            current_ids.append(current_node_id(snapshots[-1]))
        final = build_snapshot(database, root_run_id)
        if snapshots[-1] != final:
            raise ValueError("the final replay stage is not the verified family head")
        heads = final.model_dump(mode="json")["heads"]
        envelopes = []
        for before, after, current_id in zip(
            snapshots[:-1], snapshots[1:], current_ids[1:], strict=True
        ):
            deltas = diff_snapshots(before, after)
            if len(deltas) == 1 and deltas[0].op == "reset":
                raise ValueError("replay stages unexpectedly require a reset")
            envelope = {
                "type": "delta",
                "cursor": after.cursor,
                "current_id": current_id,
                "deltas": [item.model_dump(mode="json") for item in deltas],
                "heads": [item.model_dump(mode="json") for item in after.heads],
                "graph_sha256": after.graph_sha256,
                "omitted_counts": after.omitted_counts,
                "unknowns": after.unknowns,
                "review_brief": after.review_brief.model_dump(mode="json"),
                "support_paths": [
                    item.model_dump(mode="json") for item in after.support_paths or ()
                ],
            }
            if (
                apply_deltas(
                    before,
                    deltas,
                    cursor=after.cursor,
                    heads=after.heads,
                    graph_sha256=after.graph_sha256,
                    omitted_counts=after.omitted_counts,
                    unknowns=after.unknowns,
                    review_brief=after.review_brief,
                    support_paths=after.support_paths or (),
                )
                != after
            ):
                raise ValueError("replay delta does not reconstruct its verified stage")
            envelopes.append(envelope)
        payload = {
            "snapshot": snapshots[0].model_dump(mode="json"),
            "deltas": envelopes,
            "meta": {
                **fixture["meta"],
                "final_graph_sha256": final.graph_sha256,
                "source_heads": heads,
            },
        }
        return canonical_json_bytes(payload) + b"\n"


def flat_transcript(replay: bytes) -> str:
    payload = json.loads(replay)
    lines = [
        str(payload["meta"]["mode"]),
        "META " + canonical_json_bytes(payload["meta"]).decode(),
    ]
    stages = [GraphSnapshot.model_validate(payload["snapshot"])]
    for item in payload["deltas"]:
        stages.append(apply_replay_envelope(stages[-1], item))
    current_ids = [None, *(item.get("current_id") for item in payload["deltas"])]
    for index, (stage, current_id) in enumerate(
        zip(stages, current_ids, strict=True), 1
    ):
        brief = stage.review_brief
        lines.append(
            "CHECKPOINT "
            + canonical_json_bytes(
                {
                    "index": index,
                    "current_id": current_id,
                    "heads": [head.model_dump(mode="json") for head in stage.heads],
                    "graph_sha256": stage.graph_sha256,
                    "attention": (
                        brief.attention.model_dump(mode="json") if brief else None
                    ),
                    "stage": brief.stage if brief else None,
                    "outcome_kind": brief.outcome_kind if brief else None,
                }
            ).decode()
        )

    final = stages[-1]
    lines.append(
        "FINAL "
        + canonical_json_bytes(
            {
                "view_version": final.view_version,
                "root_run_id": final.root_run_id,
                "cursor": final.cursor,
                "graph_sha256": final.graph_sha256,
                "omitted_counts": final.omitted_counts,
                "changed_paths": final.review_brief.changed_paths,
                "bound_paths": final.review_brief.bound_paths,
                "counts": final.review_brief.counts.model_dump(mode="json"),
            }
        ).decode()
    )
    for node in sorted(
        final.nodes,
        key=lambda item: (
            item.recorded_at.isoformat() if item.recorded_at else "9999",
            item.run_id or "",
            item.seq or 0,
            item.id,
        ),
    ):
        lines.append("ITEM " + canonical_json_bytes(node.model_dump(mode="json")).decode())
    for edge in final.edges:
        lines.append(
            "RELATIONSHIP "
            + canonical_json_bytes(edge.model_dump(mode="json")).decode()
        )
    for section in final.review_brief.sections:
        for fact in section.facts:
            lines.append("FACT " + canonical_json_bytes(fact.model_dump(mode="json")).decode())
    for path in final.support_paths or ():
        lines.append(
            "SUPPORT_PATH "
            + canonical_json_bytes(path.model_dump(mode="json")).decode()
        )
    for unknown in final.unknowns:
        lines.append("UNKNOWN " + canonical_json_bytes(unknown).decode())
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Generate replay.json from the checked-in verified v2 fixture."
    )
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--digest-output", type=Path, default=DEFAULT_DIGEST)
    parser.add_argument("--flat-output", type=Path)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    replay = render(args.source)
    digest = sha256_hex(replay)
    if args.flat_output:
        args.flat_output.write_text(flat_transcript(replay))
        return 0
    if args.check:
        if (
            not args.output.exists()
            or args.output.read_bytes() != replay
            or not args.digest_output.exists()
            or args.digest_output.read_text() != f"{digest}\n"
        ):
            raise SystemExit(f"replay differs: generated sha256={digest}")
        return 0
    args.output.write_bytes(replay)
    args.digest_output.write_text(f"{digest}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
