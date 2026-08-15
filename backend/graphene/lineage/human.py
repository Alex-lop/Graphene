from __future__ import annotations

import base64
import json
import re
from collections.abc import Mapping
from datetime import UTC, datetime
from difflib import unified_diff
from typing import Any

from pydantic import TypeAdapter, ValidationError

from ..hashing import (
    candidate_tree_sha256,
    canonical_json_bytes,
    canonical_json_sha256,
    sha256_hex,
)
from ..models import (
    MAX_PATCH_BYTES,
    BoundedText,
    ClarificationAnswer,
    ClarificationQuestion,
    Event,
    EventInput,
    EvidenceInvalidState,
    EvidenceKind,
    EvidenceReference,
    FeedbackRecord,
    FileVersion,
    HunkEvidence,
    HumanDecision,
    LineageAuthority,
    LineageEventType,
    LineageOperation,
    MemoryDecisionValue,
    MemoryRevision,
    MemorySpec,
    MemoryState,
    ScopeId,
    SourceKind,
    SourceReference,
    TruthKind,
    VerifiedHead,
)
from .artifacts import SQLiteArtifactStore
from .service import LineageStore

_TEXT = TypeAdapter(BoundedText)
_HUNK_HEADER = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@(?: .*)?$")


class HumanWorkflowError(RuntimeError):
    pass


class HumanEvidenceError(HumanWorkflowError):
    pass


class HumanConflict(HumanWorkflowError):
    pass


def _now() -> datetime:
    return datetime.now(UTC)


def _stable_id(prefix: str, *parts: str) -> str:
    return f"{prefix}:{sha256_hex(chr(0).join(parts).encode())[:32]}"


def _event_ref(event: Event) -> EvidenceReference:
    return EvidenceReference(
        kind=EvidenceKind.EVENT,
        id=event.event_id,
        sha256=event.event_sha256,
    )


def _decision_provenance(
    simulated_fixture: bool,
    human_attestation: bool,
) -> tuple[TruthKind, LineageAuthority, EvidenceKind, SourceKind, str]:
    if simulated_fixture and human_attestation:
        raise HumanConflict("a decision cannot be both human and simulated")
    if simulated_fixture:
        return (
            TruthKind.SIMULATED_FIXTURE,
            LineageAuthority.SIMULATED_FIXTURE,
            EvidenceKind.SIMULATED_FIXTURE,
            SourceKind.SIMULATED_FIXTURE,
            "simulated_fixture",
        )
    if not human_attestation:
        raise HumanConflict("human attestation requires a verified interactive TTY")
    return (
        TruthKind.HUMAN_ATTESTED,
        LineageAuthority.OPERATOR_REQUEST,
        EvidenceKind.OPERATOR_REQUEST,
        SourceKind.OPERATOR_REQUEST,
        "human",
    )


def _operator_details(label: str, rationale: str | None) -> tuple[str, str | None]:
    label = label.strip()
    rationale = None if rationale is None else rationale.strip() or None
    if not label or len(label.encode()) > 64:
        raise HumanConflict("operator label must contain 1 to 64 UTF-8 bytes")
    if rationale is not None and len(rationale.encode()) > 256:
        raise HumanConflict("operator rationale exceeds 256 UTF-8 bytes")
    return label, rationale


class HumanWorkflowService:
    """Exact evidence-to-human-record transitions for the frozen demo memory."""

    def __init__(
        self,
        store: LineageStore,
        artifacts: SQLiteArtifactStore,
        memory: MemorySpec,
    ) -> None:
        self.store = store
        self.artifacts = artifacts
        self.memory = memory

    def derive_changeset(
        self,
        run_id: str,
        expected_head: VerifiedHead,
        *,
        idempotency_key: str,
    ) -> Event:
        events = self._verified(run_id, expected_head)
        if any(
            event.event_type == LineageEventType.CHANGESET_PARSED for event in events
        ):
            raise HumanConflict("the run already has a parsed changeset")
        changes = self._write_changes(events)
        if not changes:
            raise HumanEvidenceError("the run has no observed file write")

        sections: list[str] = []
        file_changes: list[dict[str, Any]] = []
        after_files: dict[str, bytes] = {}
        for path in sorted(changes):
            change = changes[path]
            if len(change["events"]) != 1:
                raise HumanEvidenceError(
                    "exact feedback requires one observed write per changed path"
                )
            if "\n" in path or "\r" in path or "\t" in path:
                raise HumanEvidenceError(
                    "write path cannot enter a canonical patch header"
                )
            before = change["before"]
            after = change["after"]
            if (
                before is not None
                and before["content_sha256"] == after["content_sha256"]
            ):
                raise HumanEvidenceError(
                    "a reverted or no-op write has no exact changeset"
                )
            sections.append(
                self._file_patch(
                    path,
                    None if before is None else str(before["content"]),
                    str(after["content"]),
                )
            )
            after_files[path] = str(after["content"]).encode()
            file_changes.append(
                {
                    "path": path,
                    "before_file_version_id": (
                        None if before is None else before["file_version_id"]
                    ),
                    "before_sha256": None
                    if before is None
                    else before["content_sha256"],
                    "after_file_version_id": after["file_version_id"],
                    "after_sha256": after["content_sha256"],
                    "write_event_ids": [event.event_id for event in change["events"]],
                }
            )
        patch = "".join(sections).encode()
        if not patch or len(patch) > MAX_PATCH_BYTES:
            raise HumanEvidenceError(
                "the canonical patch is empty or exceeds its byte cap"
            )
        patch_sha256 = sha256_hex(patch)

        hunk_refs: list[EvidenceReference] = []
        ordinal = 0
        for item, section in zip(file_changes, sections, strict=True):
            hunks = self._hunks(
                run_id,
                str(item["path"]),
                section,
                before_sha256=item["before_sha256"],
                after_sha256=str(item["after_sha256"]),
                patch_sha256=patch_sha256,
                ordinal=ordinal,
            )
            ordinal += len(hunks)
            hunk_refs.extend(
                self._record(EvidenceKind.HUNK, hunk.model_dump(mode="json"))
                for hunk in hunks
            )
        if not hunk_refs:
            raise HumanEvidenceError("the canonical patch contains no textual hunk")

        changed_paths = tuple(sorted(changes))
        changeset_id = sha256_hex(f"{events[0].base_sha}{patch_sha256}".encode())
        write_refs = tuple(
            _event_ref(event)
            for event in events
            if event.event_type == LineageEventType.TOOL_COMPLETED
            and event.payload.get("operation") == LineageOperation.WRITE_FILE.value
        )
        if 1 + len(hunk_refs) + len(write_refs) > 16:
            raise HumanEvidenceError("the changeset exceeds the event reference cap")
        record = {
            "schema_version": 2,
            "changeset_id": changeset_id,
            "run_id": run_id,
            "repo_id": events[0].repo_id,
            "base_sha": events[0].base_sha,
            "candidate_patch_sha256": patch_sha256,
            "candidate_tree_sha256": candidate_tree_sha256(after_files),
            "canonical_patch_base64": base64.b64encode(patch).decode(),
            "changed_paths": list(changed_paths),
            "file_changes": file_changes,
            "hunk_references": [item.model_dump(mode="json") for item in hunk_refs],
            "source_write_events": [
                item.model_dump(mode="json") for item in write_refs
            ],
        }
        changeset_ref = self._record(EvidenceKind.CHANGESET, record)
        return self._append(
            events,
            expected_head,
            idempotency_key,
            LineageEventType.CHANGESET_PARSED,
            TruthKind.SERVER_DERIVED,
            LineageAuthority.ARTIFACT_PARSER,
            SourceReference(
                kind=SourceKind.REDUCER_RECEIPT,
                id=changeset_ref.id,
                sha256=changeset_ref.sha256,
            ),
            (changeset_ref, *hunk_refs, *write_refs),
            {
                "candidate_patch_sha256": patch_sha256,
                "changed_paths": list(changed_paths),
                "changeset_id": changeset_id,
                "hunk_count": len(hunk_refs),
                "status": "parsed",
            },
        )

    def record_test_receipt(
        self,
        run_id: str,
        expected_head: VerifiedHead,
        *,
        test_event_id: str,
        idempotency_key: str,
    ) -> Event:
        events = self._verified(run_id, expected_head)
        test_event = self._event(events, test_event_id)
        changeset_event, changeset_ref, changeset = self._only_changeset(events)
        if (
            test_event.event_type != LineageEventType.TOOL_COMPLETED
            or test_event.payload.get("operation")
            != LineageOperation.RUN_FIXED_TEST.value
            or test_event.payload.get("status") != "completed"
            or test_event.seq >= changeset_event.seq
        ):
            raise HumanEvidenceError(
                "test receipt source is not an observed fixed test"
            )
        if any(
            event.event_type == LineageEventType.TEST_RECEIPT_CREATED
            for event in events
        ):
            raise HumanConflict("the run already has fixed-test receipt metadata")

        receipt_refs = tuple(
            item
            for item in test_event.references
            if item.kind == EvidenceKind.TEST_RECEIPT
        )
        if len(receipt_refs) != 1:
            raise HumanEvidenceError(
                "fixed test does not reference one private receipt"
            )
        receipt_ref = receipt_refs[0]
        receipt = self._artifact(receipt_ref)
        expected_keys = {
            "schema_version",
            "required_test_profile",
            "command",
            "passed",
            "exit_code",
            "timed_out",
            "output_sha256",
            "output_byte_count",
            "output_truncated",
            "duration_bucket",
            "bound_paths",
            "candidate_written_versions_sha256",
            "output_ref",
        }
        if set(receipt) != expected_keys or receipt.get("schema_version") != 2:
            raise HumanEvidenceError("fixed-test receipt has an unexpected shape")
        for key in (
            "passed",
            "exit_code",
            "timed_out",
            "output_sha256",
            "output_byte_count",
            "output_truncated",
            "duration_bucket",
            "bound_paths",
            "candidate_written_versions_sha256",
        ):
            event_value = test_event.payload.get(key)
            record_value = receipt[key]
            if key == "bound_paths":
                event_value, record_value = (
                    tuple(event_value or ()),
                    tuple(record_value or ()),
                )
            if event_value != record_value:
                raise HumanEvidenceError(
                    "fixed-test public metadata does not match its receipt"
                )
        try:
            output_ref = EvidenceReference.model_validate(receipt["output_ref"])
        except ValidationError as error:
            raise HumanEvidenceError(
                "fixed-test output reference is malformed"
            ) from error
        if (
            output_ref.kind != EvidenceKind.EVIDENCE_BLOB
            or output_ref not in test_event.references
        ):
            raise HumanEvidenceError("fixed-test output reference is not event-bound")
        output = self._artifact(output_ref)
        content = output.get("content")
        if (
            set(output) != {"schema_version", "content", "content_sha256"}
            or output.get("schema_version") != 2
            or not isinstance(content, str)
            or sha256_hex(content.encode()) != receipt["output_sha256"]
            or output["content_sha256"] != receipt["output_sha256"]
            or len(content.encode()) != receipt["output_byte_count"]
        ):
            raise HumanEvidenceError("fixed-test output does not match its receipt")

        file_changes = changeset.get("file_changes")
        if not isinstance(file_changes, list):
            raise HumanEvidenceError("changeset file bindings are malformed")
        written_versions = {
            str(item["path"]): str(item["after_file_version_id"])
            for item in file_changes
            if isinstance(item, dict)
            and isinstance(item.get("path"), str)
            and isinstance(item.get("after_file_version_id"), str)
        }
        bound_paths = tuple(receipt["bound_paths"])
        if (
            len(written_versions) != len(file_changes)
            or bound_paths != tuple(sorted(set(bound_paths)))
            or bound_paths != tuple(changeset.get("changed_paths", ()))
            or canonical_json_sha256(dict(sorted(written_versions.items())))
            != receipt["candidate_written_versions_sha256"]
        ):
            raise HumanEvidenceError("fixed test does not bind the exact changeset")
        references = (
            receipt_ref,
            changeset_ref,
            _event_ref(test_event),
        )
        return self._append(
            events,
            expected_head,
            idempotency_key,
            LineageEventType.TEST_RECEIPT_CREATED,
            TruthKind.SERVER_DERIVED,
            LineageAuthority.ARTIFACT_PARSER,
            SourceReference(
                kind=SourceKind.REDUCER_RECEIPT,
                id=receipt_ref.id,
                sha256=receipt_ref.sha256,
            ),
            references,
            {
                "bound_paths": list(bound_paths),
                "passed": bool(receipt["passed"]),
                "receipt_id": receipt_ref.id,
                "receipt_sha256": receipt_ref.sha256,
                "status": "created",
            },
        )

    def ask_clarification(
        self,
        run_id: str,
        expected_head: VerifiedHead,
        *,
        write_event_id: str,
        hunk_id: str,
        correction: str,
        idempotency_key: str,
    ) -> Event:
        events = self._verified(run_id, expected_head)
        if any(
            event.event_type == LineageEventType.CLARIFICATION_ASKED for event in events
        ):
            raise HumanConflict("the run already has its bounded clarification")
        try:
            correction = _TEXT.validate_python(correction)
        except ValidationError as error:
            raise HumanConflict("feedback correction is not bounded text") from error
        if correction != self.memory.correction:
            raise HumanConflict(
                "feedback does not match the server-owned memory correction"
            )
        write_event = self._event(events, write_event_id)
        changeset_event, changeset_ref, changeset = self._only_changeset(events)
        hunk_ref, hunk = self._hunk(changeset_event, changeset, hunk_id)
        self._anchor(write_event, hunk)

        submitted_at = _now()
        feedback_id = _stable_id(
            "feedback",
            run_id,
            write_event.event_id,
            hunk.hunk_id,
            sha256_hex(correction.encode()),
        )
        pending_record = {
            "schema_version": 2,
            "action": "feedback.submitted",
            "run_id": run_id,
            "expected_head": expected_head.model_dump(mode="json"),
            "feedback_id": feedback_id,
            "evidence_event": _event_ref(write_event).model_dump(mode="json"),
            "hunk_reference": hunk_ref.model_dump(mode="json"),
            "changeset_reference": changeset_ref.model_dump(mode="json"),
            "exact_correction": correction,
            "correction_sha256": sha256_hex(correction.encode()),
            "submitted_at": submitted_at.isoformat(),
        }
        pending_ref = self._record(EvidenceKind.OPERATOR_REQUEST, pending_record)
        question_id = _stable_id("question", run_id, feedback_id)
        question_values = {
            "schema_version": 2,
            "question_id": question_id,
            "source_run_id": run_id,
            "feedback_id": feedback_id,
            "question_text": self.memory.clarification,
            "choices": tuple(item.scope_id for item in self.memory.scope_options),
            "policy_revision": events[0].policy_revision,
            "created_at": submitted_at,
        }
        question = ClarificationQuestion.model_validate(
            {
                **question_values,
                "question_sha256": canonical_json_sha256(
                    ClarificationQuestion.model_construct(
                        **question_values,
                        question_sha256="0" * 64,
                    ).model_dump(mode="json", exclude={"question_sha256"})
                ),
            }
        )
        policy_record = {
            "schema_version": 2,
            "action": "clarification.asked",
            "pending_feedback_reference": pending_ref.model_dump(mode="json"),
            "question": question.model_dump(mode="json"),
            "hunk_reference": hunk_ref.model_dump(mode="json"),
            "changeset_reference": changeset_ref.model_dump(mode="json"),
            "evidence_event": _event_ref(write_event).model_dump(mode="json"),
        }
        policy_ref = self._record(EvidenceKind.POLICY_RECEIPT, policy_record)
        return self._append(
            events,
            expected_head,
            idempotency_key,
            LineageEventType.CLARIFICATION_ASKED,
            TruthKind.POLICY_AUTHORITATIVE,
            LineageAuthority.POLICY_ENGINE,
            SourceReference(
                kind=SourceKind.POLICY_EVALUATION,
                id=policy_ref.id,
                sha256=policy_ref.sha256,
            ),
            (pending_ref, hunk_ref, changeset_ref, _event_ref(write_event)),
            {
                "choice_count": len(question.choices),
                "question_id": question.question_id,
                "question_sha256": question.question_sha256,
                "status": "asked",
            },
        )

    def answer_clarification(
        self,
        run_id: str,
        expected_head: VerifiedHead,
        *,
        question_id: str,
        choice: ScopeId | str,
        idempotency_key: str,
        simulated_fixture: bool = False,
        human_attestation: bool = False,
        operator_label: str = "local-operator",
        operator_rationale: str | None = None,
    ) -> Event:
        events = self._verified(run_id, expected_head)
        asked, question, pending_ref, _ = self._question(events, question_id)
        if any(
            event.event_type == LineageEventType.CLARIFICATION_ANSWERED
            and event.payload.get("question_id") == question_id
            for event in events
        ):
            raise HumanConflict("the clarification already has an answer")
        try:
            selected = ScopeId(choice)
        except ValueError as error:
            raise HumanConflict("clarification choice is unknown") from error
        if selected not in question.choices:
            raise HumanConflict("clarification choice was not offered")
        answered_at = _now()
        truth, authority, evidence_kind, source_kind, actor = _decision_provenance(
            simulated_fixture, human_attestation
        )
        operator_label, operator_rationale = _operator_details(
            operator_label, operator_rationale
        )
        answer_values = {
            "schema_version": 2,
            "answer_id": _stable_id("answer", run_id, question_id, selected.value),
            "question_id": question_id,
            "choice": selected,
            "actor": actor,
            "answered_at": answered_at,
        }
        answer = ClarificationAnswer.model_validate(
            {
                **answer_values,
                "answer_sha256": canonical_json_sha256(
                    ClarificationAnswer.model_construct(
                        **answer_values,
                        answer_sha256="0" * 64,
                    ).model_dump(mode="json", exclude={"answer_sha256"})
                ),
            }
        )
        question_ref = EvidenceReference(
            kind=EvidenceKind.POLICY_RECEIPT,
            id=asked.source_ref.id,
            sha256=asked.source_ref.sha256,
        )
        record = {
            "schema_version": 2,
            "action": "clarification.answered",
            "run_id": run_id,
            "expected_head": expected_head.model_dump(mode="json"),
            "answer": answer.model_dump(mode="json"),
            "question_reference": question_ref.model_dump(mode="json"),
            "pending_feedback_reference": pending_ref.model_dump(mode="json"),
            "operator_label": operator_label,
            "operator_rationale": operator_rationale,
        }
        source_ref = self._record(evidence_kind, record)
        return self._append(
            events,
            expected_head,
            idempotency_key,
            LineageEventType.CLARIFICATION_ANSWERED,
            truth,
            authority,
            SourceReference(
                kind=source_kind,
                id=source_ref.id,
                sha256=source_ref.sha256,
            ),
            (question_ref, pending_ref, _event_ref(asked)),
            {
                "answer_id": answer.answer_id,
                "answer_sha256": answer.answer_sha256,
                "choice": answer.choice.value,
                "operator_label": operator_label,
                "operator_rationale": operator_rationale,
                "question_id": question_id,
                "status": "answered",
            },
        )

    def record_feedback(
        self,
        run_id: str,
        expected_head: VerifiedHead,
        *,
        question_id: str,
        idempotency_key: str,
        simulated_fixture: bool = False,
        human_attestation: bool = False,
        operator_label: str = "local-operator",
        operator_rationale: str | None = None,
    ) -> Event:
        events = self._verified(run_id, expected_head)
        asked, question, pending_ref, pending = self._question(events, question_id)
        answered, answer = self._answer(events, question)
        truth, authority, evidence_kind, source_kind, actor = _decision_provenance(
            simulated_fixture, human_attestation
        )
        operator_label, operator_rationale = _operator_details(
            operator_label, operator_rationale
        )
        if answer.actor != actor:
            raise HumanConflict("feedback provenance does not match its answer")
        feedback_id = str(pending["feedback_id"])
        if any(
            event.event_type == LineageEventType.FEEDBACK_RECORDED
            and event.payload.get("feedback_id") == feedback_id
            for event in events
        ):
            raise HumanConflict("feedback was already recorded")
        write_ref = self._evidence_reference(
            pending["evidence_event"], EvidenceKind.EVENT
        )
        write_event = self._event(events, write_ref.id)
        if write_event.event_sha256 != write_ref.sha256:
            raise HumanEvidenceError("pending feedback write digest changed")
        hunk_ref = self._evidence_reference(
            pending["hunk_reference"], EvidenceKind.HUNK
        )
        changeset_ref = self._evidence_reference(
            pending["changeset_reference"], EvidenceKind.CHANGESET
        )
        hunk = HunkEvidence.model_validate(self._artifact(hunk_ref))
        self._anchor(write_event, hunk)
        correction = str(pending["exact_correction"])
        if (
            sha256_hex(correction.encode()) != pending["correction_sha256"]
            or answer.choice not in question.choices
        ):
            raise HumanEvidenceError(
                "pending feedback or clarification binding changed"
            )
        record = FeedbackRecord(
            feedback_id=feedback_id,
            run_id=run_id,
            evidence_event_id=write_event.event_id,
            exact_correction=correction,
            selected_hunk_id=hunk.hunk_id,
            selected_scope_id=answer.choice,
            occurred_at=str(pending["submitted_at"]),
        )
        feedback_ref = self._record(
            EvidenceKind.FEEDBACK, record.model_dump(mode="json")
        )
        source_record = {
            "schema_version": 2,
            "action": "feedback.recorded",
            "run_id": run_id,
            "expected_head": expected_head.model_dump(mode="json"),
            "feedback_reference": feedback_ref.model_dump(mode="json"),
            "answer_event": _event_ref(answered).model_dump(mode="json"),
            "operator_label": operator_label,
            "operator_rationale": operator_rationale,
        }
        source_ref = self._record(evidence_kind, source_record)
        return self._append(
            events,
            expected_head,
            idempotency_key,
            LineageEventType.FEEDBACK_RECORDED,
            truth,
            authority,
            SourceReference(
                kind=source_kind,
                id=source_ref.id,
                sha256=source_ref.sha256,
            ),
            (
                feedback_ref,
                hunk_ref,
                changeset_ref,
                write_ref,
                _event_ref(asked),
                _event_ref(answered),
            ),
            {
                "correction_sha256": sha256_hex(correction.encode()),
                "evidence_event_id": write_event.event_id,
                "feedback_id": feedback_id,
                "hunk_id": hunk.hunk_id,
                "operator_label": operator_label,
                "operator_rationale": operator_rationale,
                "scope_id": answer.choice.value,
                "status": "recorded",
            },
        )

    def propose_memory(
        self,
        run_id: str,
        expected_head: VerifiedHead,
        *,
        feedback_id: str,
        idempotency_key: str,
    ) -> Event:
        events = self._verified(run_id, expected_head)
        feedback_event = next(
            (
                event
                for event in events
                if event.event_type == LineageEventType.FEEDBACK_RECORDED
                and event.payload.get("feedback_id") == feedback_id
            ),
            None,
        )
        if feedback_event is None:
            raise HumanEvidenceError("memory feedback was not observed in this run")
        if any(
            event.event_type == LineageEventType.MEMORY_PROPOSED
            and event.payload.get("memory_id") == self.memory.memory_id
            and event.payload.get("revision") == self.memory.revision
            for event in events
        ):
            raise HumanConflict("memory revision was already proposed")
        feedback_refs = tuple(
            item
            for item in feedback_event.references
            if item.kind == EvidenceKind.FEEDBACK
        )
        if len(feedback_refs) != 1:
            raise HumanEvidenceError("feedback event does not bind one private record")
        feedback = FeedbackRecord.model_validate(self._artifact(feedback_refs[0]))
        scope = next(
            (
                item
                for item in self.memory.scope_options
                if item.scope_id == feedback.selected_scope_id
            ),
            None,
        )
        if (
            feedback.run_id != run_id
            or feedback.feedback_id != feedback_id
            or feedback.exact_correction != self.memory.correction
            or scope is None
            or self.memory.repo_id != events[0].repo_id
        ):
            raise HumanEvidenceError(
                "feedback cannot derive the frozen memory revision"
            )
        memory = MemoryRevision(
            memory_id=self.memory.memory_id,
            revision=self.memory.revision,
            state=MemoryState.PROPOSED,
            rule=self.memory.rule,
            repo_id=self.memory.repo_id,
            scope_id=scope.scope_id,
            path_globs=scope.path_globs,
            task_tags=scope.task_tags,
            required_test_path=self.memory.required_test_path,
            required_check=self.memory.required_check,
            evidence_run_id=run_id,
            feedback_id=feedback_id,
        )
        memory_ref = self._record(
            EvidenceKind.MEMORY_REVISION, memory.model_dump(mode="json")
        )
        bound_events = tuple(
            self._event(events, reference.id)
            for reference in feedback_event.references
            if reference.kind == EvidenceKind.EVENT
        )
        asked = tuple(
            event
            for event in bound_events
            if event.event_type == LineageEventType.CLARIFICATION_ASKED
        )
        answered = tuple(
            event
            for event in bound_events
            if event.event_type == LineageEventType.CLARIFICATION_ANSWERED
        )
        if len(asked) != 1 or len(answered) != 1:
            raise HumanEvidenceError(
                "feedback does not bind one clarification exchange"
            )
        source_record = {
            "schema_version": 2,
            "action": "memory.proposed",
            "run_id": run_id,
            "expected_head": expected_head.model_dump(mode="json"),
            "feedback_reference": feedback_refs[0].model_dump(mode="json"),
            "memory_reference": memory_ref.model_dump(mode="json"),
            "question_event": _event_ref(asked[0]).model_dump(mode="json"),
            "answer_event": _event_ref(answered[0]).model_dump(mode="json"),
        }
        source_ref = self._record(EvidenceKind.OPERATOR_REQUEST, source_record)
        return self._append(
            events,
            expected_head,
            idempotency_key,
            LineageEventType.MEMORY_PROPOSED,
            TruthKind.SERVER_DERIVED,
            LineageAuthority.LIFECYCLE_SERVICE,
            SourceReference(
                kind=SourceKind.LIFECYCLE_REQUEST,
                id=source_ref.id,
                sha256=source_ref.sha256,
            ),
            (
                memory_ref,
                feedback_refs[0],
                _event_ref(feedback_event),
                _event_ref(asked[0]),
                _event_ref(answered[0]),
            ),
            {
                "memory_id": memory.memory_id,
                "memory_sha256": memory_ref.sha256,
                "revision": memory.revision,
                "status": "proposed",
            },
        )

    def decide_memory(
        self,
        run_id: str,
        expected_head: VerifiedHead,
        *,
        memory_id: str,
        revision: int,
        decision: MemoryDecisionValue | str,
        idempotency_key: str,
        simulated_fixture: bool = False,
        human_attestation: bool = False,
        operator_label: str = "local-operator",
        operator_rationale: str | None = None,
    ) -> Event:
        events = self._verified(run_id, expected_head)
        proposed_event = next(
            (
                event
                for event in events
                if event.event_type == LineageEventType.MEMORY_PROPOSED
                and event.payload.get("memory_id") == memory_id
                and event.payload.get("revision") == revision
            ),
            None,
        )
        if proposed_event is None:
            raise HumanEvidenceError("memory revision was not proposed in this run")
        if any(
            event.event_type
            in {LineageEventType.MEMORY_APPROVED, LineageEventType.MEMORY_REJECTED}
            and event.payload.get("memory_id") == memory_id
            and event.payload.get("revision") == revision
            for event in events
        ):
            raise HumanConflict("memory revision already has a human decision")
        proposed_refs = tuple(
            item
            for item in proposed_event.references
            if item.kind == EvidenceKind.MEMORY_REVISION
        )
        if len(proposed_refs) != 1 or proposed_refs[
            0
        ].sha256 != proposed_event.payload.get("memory_sha256"):
            raise HumanEvidenceError("memory proposal reference is not exact")
        proposed = MemoryRevision.model_validate(self._artifact(proposed_refs[0]))
        try:
            value = MemoryDecisionValue(decision)
        except ValueError as error:
            raise HumanConflict("memory decision is unknown") from error
        if (
            proposed.state != MemoryState.PROPOSED
            or proposed.memory_id != memory_id
            or proposed.revision != revision
            or proposed.evidence_run_id != run_id
        ):
            raise HumanEvidenceError("memory proposal identity does not match")
        bound_digest = canonical_json_sha256(
            proposed.model_dump(mode="json", exclude={"state", "decision"})
        )
        truth, authority, evidence_kind, source_kind, actor = _decision_provenance(
            simulated_fixture, human_attestation
        )
        operator_label, operator_rationale = _operator_details(
            operator_label, operator_rationale
        )
        feedback_event = next(
            event
            for event in events
            if event.event_type == LineageEventType.FEEDBACK_RECORDED
        )
        if feedback_event.truth_kind != truth or feedback_event.authority != authority:
            raise HumanConflict(
                "memory decision provenance does not match its feedback"
            )
        human_decision = HumanDecision(
            decision_id=_stable_id(
                "decision", run_id, memory_id, str(revision), value.value, bound_digest
            ),
            value=value,
            purpose="memory",
            bound_digest=bound_digest,
            occurred_at=_now(),
            actor=actor,
        )
        state = (
            MemoryState.APPROVED
            if value == MemoryDecisionValue.APPROVE
            else MemoryState.REJECTED
        )
        decided = MemoryRevision.model_validate(
            {
                **proposed.model_dump(mode="json", exclude={"state", "decision"}),
                "state": state,
                "decision": human_decision.model_dump(mode="json"),
            }
        )
        decided_ref = self._record(
            EvidenceKind.MEMORY_REVISION, decided.model_dump(mode="json")
        )
        event_type = (
            LineageEventType.MEMORY_APPROVED
            if state == MemoryState.APPROVED
            else LineageEventType.MEMORY_REJECTED
        )
        source_record = {
            "schema_version": 2,
            "action": event_type.value,
            "run_id": run_id,
            "expected_head": expected_head.model_dump(mode="json"),
            "proposal_reference": proposed_refs[0].model_dump(mode="json"),
            "decided_reference": decided_ref.model_dump(mode="json"),
            "human_decision": human_decision.model_dump(mode="json"),
            "operator_label": operator_label,
            "operator_rationale": operator_rationale,
        }
        source_ref = self._record(evidence_kind, source_record)
        return self._append(
            events,
            expected_head,
            idempotency_key,
            event_type,
            truth,
            authority,
            SourceReference(
                kind=source_kind,
                id=source_ref.id,
                sha256=source_ref.sha256,
            ),
            (proposed_refs[0], decided_ref, _event_ref(proposed_event)),
            {
                "decision_id": human_decision.decision_id,
                "memory_id": memory_id,
                "memory_sha256": decided_ref.sha256,
                "operator_label": operator_label,
                "operator_rationale": operator_rationale,
                "revision": revision,
                "status": state.value,
            },
        )

    def _verified(self, run_id: str, expected_head: VerifiedHead) -> tuple[Event, ...]:
        if expected_head.run_id != run_id:
            raise HumanConflict("expected head belongs to another run")
        state = self.store.verify(run_id)
        if isinstance(state, EvidenceInvalidState):
            raise HumanEvidenceError("lineage evidence is invalid")
        if state != expected_head:
            raise HumanConflict("expected human-workflow head is stale")
        events: list[Event] = []
        after = 0
        while after < state.seq:
            batch = self.store.tail(run_id, after, min(256, state.seq - after))
            if not batch or batch[0].seq != after + 1:
                raise HumanEvidenceError("verified lineage tail is incomplete")
            events.extend(batch)
            after = batch[-1].seq
        if (
            not events
            or len(events) != state.event_count
            or events[-1].event_sha256 != state.event_sha256
        ):
            raise HumanEvidenceError("verified lineage tail does not match its head")
        return tuple(events)

    def _artifact(self, reference: EvidenceReference) -> dict[str, Any]:
        raw = self.artifacts.resolve(reference.kind.value, reference.id)
        if raw is None or sha256_hex(raw) != reference.sha256:
            raise HumanEvidenceError("referenced private artifact is unavailable")
        try:
            value = json.loads(raw)
        except (TypeError, ValueError, UnicodeError) as error:
            raise HumanEvidenceError(
                "referenced private artifact is malformed"
            ) from error
        if not isinstance(value, dict) or canonical_json_bytes(value) != raw:
            raise HumanEvidenceError("referenced private artifact is not canonical")
        return value

    def _record(
        self, kind: EvidenceKind, record: Mapping[str, Any]
    ) -> EvidenceReference:
        reference = self.artifacts(kind, record)
        if reference.kind != kind or reference.sha256 != canonical_json_sha256(record):
            raise HumanEvidenceError("artifact recorder returned a mismatched digest")
        return reference

    @staticmethod
    def _event(events: tuple[Event, ...], event_id: str) -> Event:
        event = next((item for item in events if item.event_id == event_id), None)
        if event is None:
            raise HumanEvidenceError("referenced event is not in the verified run")
        return event

    @staticmethod
    def _evidence_reference(value: Any, kind: EvidenceKind) -> EvidenceReference:
        try:
            reference = EvidenceReference.model_validate(value)
        except ValidationError as error:
            raise HumanEvidenceError(
                "private evidence reference is malformed"
            ) from error
        if reference.kind != kind:
            raise HumanEvidenceError("private evidence reference has the wrong kind")
        return reference

    def _file_version(self, reference: EvidenceReference) -> dict[str, Any]:
        record = self._artifact(reference)
        content = record.get("content")
        metadata = {
            name: record.get(name)
            for name in FileVersion.model_fields
            if name != "artifact_sha256"
        }
        expected_keys = set(metadata) | {"content"}
        try:
            version = FileVersion.model_validate(
                {**metadata, "artifact_sha256": reference.sha256}
            )
        except ValidationError as error:
            raise HumanEvidenceError("file-version metadata is malformed") from error
        if (
            set(record) != expected_keys
            or not isinstance(content, str)
            or sha256_hex(content.encode()) != version.content_sha256
            or len(content.encode()) != version.byte_count
            or len(content.splitlines()) != version.line_count
        ):
            raise HumanEvidenceError("file-version content does not match its metadata")
        return {**version.model_dump(mode="json"), "content": content}

    def _write_changes(self, events: tuple[Event, ...]) -> dict[str, dict[str, Any]]:
        changes: dict[str, dict[str, Any]] = {}
        for event in events:
            if not (
                event.event_type == LineageEventType.TOOL_COMPLETED
                and event.payload.get("operation") == LineageOperation.WRITE_FILE.value
            ):
                continue
            path = event.payload.get("path")
            before_id = event.payload.get("before_file_version_id")
            after_id = event.payload.get("after_file_version_id")
            versions = {
                item["file_version_id"]: item
                for item in (
                    self._file_version(reference)
                    for reference in event.references
                    if reference.kind == EvidenceKind.FILE_VERSION
                )
            }
            if (
                not isinstance(path, str)
                or not isinstance(after_id, str)
                or after_id not in versions
                or (before_id is not None and before_id not in versions)
                or set(versions)
                != {item for item in (before_id, after_id) if item is not None}
                or any(
                    version["path"] != path or version["repo_id"] != event.repo_id
                    for version in versions.values()
                )
            ):
                raise HumanEvidenceError(
                    "write event file-version references do not match"
                )
            before = None if before_id is None else versions[before_id]
            after = versions[after_id]
            existing = changes.get(path)
            if existing is None:
                changes[path] = {
                    "before": before,
                    "after": after,
                    "events": [event],
                }
            else:
                if before_id != existing["after"]["file_version_id"]:
                    raise HumanEvidenceError(
                        "write file-version lineage is not contiguous"
                    )
                existing["after"] = after
                existing["events"].append(event)
        return changes

    @staticmethod
    def _file_patch(path: str, before: str | None, after: str) -> str:
        old = [] if before is None else before.splitlines(keepends=True)
        new = after.splitlines(keepends=True)
        lines = unified_diff(
            old,
            new,
            fromfile="/dev/null" if before is None else f"a/{path}",
            tofile=f"b/{path}",
            n=3,
            lineterm="\n",
        )
        body: list[str] = []
        for line in lines:
            body.append(
                line
                if line.endswith("\n")
                else line + "\n\\ No newline at end of file\n"
            )
        metadata = "new file mode 100644\n" if before is None else ""
        return f"diff --git a/{path} b/{path}\n{metadata}{''.join(body)}"

    @staticmethod
    def _hunks(
        run_id: str,
        path: str,
        section: str,
        *,
        before_sha256: str | None,
        after_sha256: str,
        patch_sha256: str,
        ordinal: int,
    ) -> tuple[HunkEvidence, ...]:
        lines = section.splitlines(keepends=True)
        starts = [index for index, line in enumerate(lines) if line.startswith("@@ ")]
        starts.append(len(lines))
        values: list[HunkEvidence] = []
        for index in range(len(starts) - 1):
            start, end = starts[index], starts[index + 1]
            header = lines[start].rstrip("\n")
            match = _HUNK_HEADER.fullmatch(header)
            if match is None:
                raise HumanEvidenceError("canonical patch contains a malformed hunk")
            old_start = int(match.group(1))
            old_lines = int(match.group(2) or 1)
            new_start = int(match.group(3))
            new_lines = int(match.group(4) or 1)
            actual_old = actual_new = 0
            for line in lines[start + 1 : end]:
                if line.startswith("\\ No newline at end of file"):
                    continue
                if line.startswith(" "):
                    actual_old += 1
                    actual_new += 1
                elif line.startswith("-"):
                    actual_old += 1
                elif line.startswith("+"):
                    actual_new += 1
                else:
                    raise HumanEvidenceError(
                        "canonical patch contains a malformed hunk body"
                    )
            if (actual_old, actual_new) != (old_lines, new_lines):
                raise HumanEvidenceError(
                    "canonical hunk counts do not match its header"
                )
            raw = "".join(lines[start:end])
            exact_sha256 = sha256_hex(raw.encode())
            hunk_id = "hunk:" + canonical_json_sha256(
                {
                    "run_id": run_id,
                    "candidate_patch_sha256": patch_sha256,
                    "path": path,
                    "ordinal": ordinal + index + 1,
                    "exact_hunk_sha256": exact_sha256,
                }
            )
            values.append(
                HunkEvidence(
                    hunk_id=hunk_id,
                    path=path,
                    old_start=old_start,
                    old_lines=old_lines,
                    new_start=new_start,
                    new_lines=new_lines,
                    before_sha256=before_sha256,
                    after_sha256=after_sha256,
                    canonical_patch_sha256=patch_sha256,
                    exact_hunk_sha256=exact_sha256,
                    candidate_revision=1,
                    unified_diff=raw,
                )
            )
        return tuple(values)

    def _changeset(
        self, events: tuple[Event, ...], event_id: str
    ) -> tuple[Event, EvidenceReference, dict[str, Any]]:
        event = self._event(events, event_id)
        refs = tuple(
            item for item in event.references if item.kind == EvidenceKind.CHANGESET
        )
        if event.event_type != LineageEventType.CHANGESET_PARSED or len(refs) != 1:
            raise HumanEvidenceError("referenced event is not one parsed changeset")
        record = self._artifact(refs[0])
        if (
            record.get("schema_version") != 2
            or record.get("run_id") != event.run_id
            or record.get("repo_id") != event.repo_id
            or record.get("base_sha") != event.base_sha
            or record.get("changeset_id") != event.payload.get("changeset_id")
            or record.get("candidate_patch_sha256")
            != event.payload.get("candidate_patch_sha256")
            or record.get("changed_paths") != event.payload.get("changed_paths")
        ):
            raise HumanEvidenceError(
                "changeset event does not match its private artifact"
            )
        return event, refs[0], record

    def _only_changeset(
        self, events: tuple[Event, ...]
    ) -> tuple[Event, EvidenceReference, dict[str, Any]]:
        matches = tuple(
            event
            for event in events
            if event.event_type == LineageEventType.CHANGESET_PARSED
        )
        if len(matches) != 1:
            raise HumanEvidenceError(
                "the verified run does not contain one current changeset"
            )
        return self._changeset(events, matches[0].event_id)

    def _hunk(
        self,
        changeset_event: Event,
        changeset: Mapping[str, Any],
        hunk_id: str,
    ) -> tuple[EvidenceReference, HunkEvidence]:
        raw_refs = changeset.get("hunk_references")
        if not isinstance(raw_refs, list):
            raise HumanEvidenceError("changeset hunk references are malformed")
        refs = tuple(
            self._evidence_reference(item, EvidenceKind.HUNK) for item in raw_refs
        )
        if any(item not in changeset_event.references for item in refs):
            raise HumanEvidenceError("changeset hunk is not event-bound")
        matches = []
        for reference in refs:
            hunk = HunkEvidence.model_validate(self._artifact(reference))
            if hunk.hunk_id == hunk_id:
                matches.append((reference, hunk))
        if len(matches) != 1:
            raise HumanEvidenceError("selected hunk is not unique in the changeset")
        return matches[0]

    def _anchor(self, write_event: Event, hunk: HunkEvidence) -> None:
        if (
            write_event.event_type != LineageEventType.TOOL_COMPLETED
            or write_event.payload.get("operation") != LineageOperation.WRITE_FILE.value
            or write_event.payload.get("path") != hunk.path
        ):
            raise HumanEvidenceError("feedback evidence is not the matching write")
        versions = {
            item["file_version_id"]: item
            for item in (
                self._file_version(reference)
                for reference in write_event.references
                if reference.kind == EvidenceKind.FILE_VERSION
            )
        }
        before_id = write_event.payload.get("before_file_version_id")
        after_id = write_event.payload.get("after_file_version_id")
        before_sha256 = (
            None
            if before_id is None
            else versions.get(str(before_id), {}).get("content_sha256")
        )
        after_sha256 = versions.get(str(after_id), {}).get("content_sha256")
        if before_sha256 != hunk.before_sha256 or after_sha256 != hunk.after_sha256:
            raise HumanEvidenceError(
                "feedback write and exact hunk file versions differ"
            )

    def _question(
        self, events: tuple[Event, ...], question_id: str
    ) -> tuple[Event, ClarificationQuestion, EvidenceReference, dict[str, Any]]:
        matches = tuple(
            event
            for event in events
            if event.event_type == LineageEventType.CLARIFICATION_ASKED
            and event.payload.get("question_id") == question_id
        )
        if len(matches) != 1:
            raise HumanEvidenceError("clarification question is not unique in this run")
        asked = matches[0]
        policy_ref = EvidenceReference(
            kind=EvidenceKind.POLICY_RECEIPT,
            id=asked.source_ref.id,
            sha256=asked.source_ref.sha256,
        )
        policy = self._artifact(policy_ref)
        try:
            question = ClarificationQuestion.model_validate(policy["question"])
            pending_ref = self._evidence_reference(
                policy["pending_feedback_reference"], EvidenceKind.OPERATOR_REQUEST
            )
        except (KeyError, ValidationError) as error:
            raise HumanEvidenceError(
                "clarification policy receipt is malformed"
            ) from error
        pending = self._artifact(pending_ref)
        if (
            policy.get("action") != "clarification.asked"
            or question.question_id != question_id
            or question.source_run_id != asked.run_id
            or question.policy_revision != asked.policy_revision
            or question.question_sha256 != asked.payload.get("question_sha256")
            or question.question_text != self.memory.clarification
            or question.choices
            != tuple(item.scope_id for item in self.memory.scope_options)
            or pending.get("run_id") != asked.run_id
            or pending.get("feedback_id") != question.feedback_id
            or pending_ref not in asked.references
        ):
            raise HumanEvidenceError(
                "clarification binding does not match the frozen policy"
            )
        return asked, question, pending_ref, pending

    def _answer(
        self, events: tuple[Event, ...], question: ClarificationQuestion
    ) -> tuple[Event, ClarificationAnswer]:
        matches = tuple(
            event
            for event in events
            if event.event_type == LineageEventType.CLARIFICATION_ANSWERED
            and event.payload.get("question_id") == question.question_id
        )
        if len(matches) != 1:
            raise HumanEvidenceError("clarification answer is not unique in this run")
        event = matches[0]
        source = EvidenceReference(
            kind=(
                EvidenceKind.SIMULATED_FIXTURE
                if event.source_ref.kind == SourceKind.SIMULATED_FIXTURE
                else EvidenceKind.OPERATOR_REQUEST
            ),
            id=event.source_ref.id,
            sha256=event.source_ref.sha256,
        )
        record = self._artifact(source)
        try:
            answer = ClarificationAnswer.model_validate(record["answer"])
        except (KeyError, ValidationError) as error:
            raise HumanEvidenceError(
                "clarification answer receipt is malformed"
            ) from error
        if (
            record.get("action") != "clarification.answered"
            or record.get("run_id") != event.run_id
            or answer.question_id != question.question_id
            or answer.choice not in question.choices
            or answer.answer_id != event.payload.get("answer_id")
            or answer.answer_sha256 != event.payload.get("answer_sha256")
            or answer.choice.value != event.payload.get("choice")
            or (answer.actor == "simulated_fixture")
            != (event.truth_kind == TruthKind.SIMULATED_FIXTURE)
        ):
            raise HumanEvidenceError("clarification answer does not match its event")
        return event, answer

    def _append(
        self,
        events: tuple[Event, ...],
        expected_head: VerifiedHead,
        idempotency_key: str,
        event_type: LineageEventType,
        truth_kind: TruthKind,
        authority: LineageAuthority,
        source_ref: SourceReference,
        references: tuple[EvidenceReference, ...],
        payload: dict[str, Any],
    ) -> Event:
        first = events[0]
        event = self.store.append(
            first.run_id,
            expected_head,
            idempotency_key,
            EventInput(
                session_id=None,
                invocation_id=None,
                model_id=None,
                tool_call_id=None,
                repo_id=first.repo_id,
                base_sha=first.base_sha,
                agent_profile_id=first.agent_profile_id,
                policy_revision=first.policy_revision,
                event_type=event_type,
                truth_kind=truth_kind,
                authority=authority,
                references=references,
                source_ref=source_ref,
                payload=payload,
            ),
        )
        if (
            event.run_id != first.run_id
            or event.seq != expected_head.seq + 1
            or event.previous_event_sha256 != expected_head.event_sha256
            or event.event_type != event_type
        ):
            raise HumanEvidenceError("lineage store returned a non-successor event")
        return event


__all__ = [
    "HumanConflict",
    "HumanEvidenceError",
    "HumanWorkflowError",
    "HumanWorkflowService",
]
