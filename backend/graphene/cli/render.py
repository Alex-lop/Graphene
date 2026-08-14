from __future__ import annotations

from ..hashing import canonical_json_bytes
from ..models import (
    Event,
    EvidenceInvalidState,
    LineageProjection,
    ProjectionEvent,
    ProjectionFile,
    ProjectionObligation,
    TruthKind,
)


def render_ndjson(events: tuple[Event, ...]) -> str:
    """Return canonical event envelopes only, one per line."""

    if not events:
        return ""
    return "".join(
        canonical_json_bytes(event.model_dump(mode="json")).decode() + "\n"
        for event in events
    )


def _fit(text: str, width: int) -> str:
    return text if len(text) <= width else text[: max(0, width - 1)] + "~"


def _row(prefix: str, label: str, suffix: str, width: int) -> str:
    fixed = len(prefix) + len(suffix)
    room = max(0, width - fixed)
    clipped = label if len(label) <= room else label[: max(0, room - 1)] + ("~" if room else "")
    return _fit(f"{prefix}{clipped}{suffix}", width)


def _file_row(item: ProjectionFile, width: int) -> str:
    if item.state == "NEW":
        footprint = "[NEW]"
    elif item.state == "DELETED":
        footprint = "[DEL]"
    elif item.size_bucket is None:
        footprint = "[....]"
    else:
        footprint = "[" + "#" * item.size_bucket + "." * (4 - item.size_bucket) + "]"
    marker = {"DISCOVERED": "D", "READ": "R", "EDITED": "E", "NEW": "E", "DELETED": "E"}[
        item.state
    ]
    changed = item.state in {"EDITED", "NEW", "DELETED"}
    suffix = (
        f" +{item.added_lines}/-{item.deleted_lines}"
        if changed
        else f" reads={item.read_count}"
    )
    if item.bound_test_pass:
        suffix += " T*"
    return _row(f"FILE {footprint} {marker} ", item.path, suffix, width)


def _event_row(item: ProjectionEvent, width: int) -> str:
    truth = {
        TruthKind.RUNTIME_OBSERVED: "O",
        TruthKind.SERVER_DERIVED: "D",
        TruthKind.HUMAN_ATTESTED: "H",
        TruthKind.SIMULATED_FIXTURE: "S",
        TruthKind.POLICY_AUTHORITATIVE: "P",
        TruthKind.MODEL_PROPOSED: "M",
    }[item.truth_kind]
    action = item.operation.value if item.operation is not None else item.event_type.value
    label = f"{action} {item.status}" + (f" {item.path}" if item.path else "")
    return _row(f"EVT {item.seq:03d} {truth} ", label, f" {item.event_id[:12]}", width)


def _obligation_row(item: ProjectionObligation, width: int) -> str:
    if item.obligation_id == "bound_fixed_test":
        label = {
            "SATISFIED": "BOUND TEST PASS",
            "MISSING": "NO BOUND TEST",
            "NOT_APPLICABLE": "BOUND TEST NOT APPLICABLE",
        }[item.status]
    elif item.obligation_id == "approved_memory_injected" and item.status == "MISSING":
        label = "MEMORY NOT INJECTED"
    else:
        label = f"{item.obligation_id} {item.status}"
    return _fit(f"CHECK {label}", width)


def render_human(
    projection: LineageProjection,
    *,
    no_color: bool = False,
    width: int = 80,
) -> str:
    """Render the same compact, explicit-state layout at every width."""

    del no_color  # The minimal renderer is readable without ANSI in every mode.
    width = max(1, min(width, 80))
    state = projection.state.value.replace("_", " ")
    lines = [
        _fit(
            f"RUN {projection.run_id[:12]} {state} seq={projection.head_seq} "
            f"head={projection.head_sha256[:12]}",
            width,
        )
    ]
    lines.extend(_file_row(item, width) for item in projection.files)
    lines.extend(_obligation_row(item, width) for item in projection.obligations)
    lines.extend(_event_row(item, width) for item in projection.event_rail)
    if projection.omitted_counts:
        counts = " ".join(
            f"{key}={value}" for key, value in sorted(projection.omitted_counts.items())
        )
        lines.append(_fit(f"OMITTED {counts}", width))
    lines.extend(_fit(f"UNKNOWN {unknown}", width) for unknown in projection.unknowns)
    return "\n".join(lines) + "\n"


def render_evidence_invalid(
    invalid: EvidenceInvalidState,
    *,
    no_color: bool = False,
    width: int = 80,
) -> str:
    del no_color
    width = max(1, min(width, 80))
    seq = "unknown" if invalid.first_invalid_seq is None else str(invalid.first_invalid_seq)
    return _fit(
        f"RUN {invalid.run_id[:12]} EVIDENCE INVALID seq={seq} {invalid.reason}",
        width,
    ) + "\n"
