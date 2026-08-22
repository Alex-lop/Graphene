"""The ingest pipeline over the synthetic ndjson fixture.

Counts, idempotence, capsule round-trip, claim insertion, private draft
fields, redaction before persistence, and source-file discipline.
"""

from __future__ import annotations

import importlib.util
import json
import sqlite3
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path
from types import ModuleType

import pytest

import graphene.shadow as shadow_package
from graphene.hashing import canonical_json_bytes, sha256_hex
from graphene.models import FrozenModel
from graphene.shadow import ingest as ingest_module
from graphene.shadow.adapters import ADAPTERS, AdapterError, Draft, ParsedSession
from graphene.shadow.events import EVENT_FIELDS, ShadowEvent
from graphene.shadow.ingest import IngestError, IngestResult, ingest_file
from graphene.shadow.lint import lint
from graphene.shadow.reconstruct import reconstruct
from graphene.shadow.redaction import REDACTED, collapse_home
from graphene.shadow.store import SHADOW_DB_FILENAME, ShadowStore

ROOT = Path(__file__).parents[3]
FIXTURE_DIR = ROOT / "tests" / "fixtures" / "shadow" / "ndjson"
FIXTURE = FIXTURE_DIR / "session_v1.ndjson"
GENERATOR = FIXTURE_DIR / "generate_session_v1.py"
SOURCE = {
    "adapter": "other-emitter",
    "adapter_version": "2.3.4",
    "record_ref": "line:1",
    "raw_type": "assistant_message",
}
CLAIM = {"matcher": "claims.v1", "category": "checks_pass", "pattern_id": "tests-pass"}
NOW = datetime(2026, 8, 22, 12, 30, tzinfo=UTC)


def _record(seq: int, **over: object) -> dict[str, object]:
    record: dict[str, object] = {
        "schema": "shadow.event.v1",
        "session_id": "sess-1",
        "seq": seq,
        "ts": None,
        "actor": "agent",
        "kind": "message",
        "paths": [],
        "outside_paths": [],
        "tool": None,
        "call_id": None,
        "argv_digest": None,
        "argv_excerpt": None,
        "exit_code": None,
        "check_family": None,
        "excerpt": f"message {seq}",
        "content_digest": f"{seq:02x}" * 32,
        "claim": None,
        "provenance": "observed",
        "derived_from": [],
        "source": {**SOURCE, "record_ref": f"line:{seq}"},
    }
    record.update(over)
    return record


def _write(path: Path, *records: dict[str, object]) -> Path:
    path.write_bytes(
        b"".join(json.dumps(record).encode("utf-8") + b"\n" for record in records)
    )
    return path


def _load_generator() -> ModuleType:
    spec = importlib.util.spec_from_file_location("generate_session_v1", GENERATOR)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _event_blobs(path: Path) -> list[bytes]:
    with closing(sqlite3.connect(path)) as connection:
        rows = connection.execute(
            "SELECT event_bytes FROM shadow_events ORDER BY shadow_id, seq"
        ).fetchall()
    return [bytes(row[0]) for row in rows]


@pytest.fixture
def store_path(tmp_path: Path) -> Path:
    return tmp_path / SHADOW_DB_FILENAME


@pytest.fixture
def store(store_path: Path) -> ShadowStore:
    return ShadowStore(store_path)


# -- the fixture itself ------------------------------------------------------


def test_fixture_is_reproducible_from_its_generator() -> None:
    generator = _load_generator()

    events = generator.build_events()
    assert generator.render(events) == FIXTURE.read_bytes()
    assert all(isinstance(event, ShadowEvent) for event in events)
    assert (FIXTURE_DIR / "README.md").read_text(encoding="utf-8").count("synthetic")


def test_fixture_contains_what_the_spec_demands() -> None:
    records = [json.loads(line) for line in FIXTURE.read_bytes().splitlines()]
    kinds = [record["kind"] for record in records]
    writes = {
        path
        for record in records
        if record["kind"] in {"file_edit", "file_create"}
        for path in record["paths"]
    }

    assert 25 <= len(records) <= 40
    assert "claim" not in kinds
    assert kinds.count("unknown") == 1
    assert "install_op" in kinds and "network_op" in kinds and "vcs_op" in kinds
    assert writes == {"app/greet.py", "app/config.py", "tests/test_greet.py", ".env"}
    assert records[0]["actor"] == "user" and records[0]["kind"] == "message"
    deletes = [record for record in records if record["kind"] == "file_delete"]
    assert [record["paths"] for record in deletes] == [["app/legacy.py"]]
    assert deletes[0]["provenance"] == "inferred"
    assert records[-1]["excerpt"].startswith("All tests pass.")
    assert {record["session_id"] for record in records} == {"fixture-session-v1"}
    assert {record["source"]["adapter"] for record in records} == {"fixture-emitter"}
    assert all("event_id" in record for record in records)


# -- ingesting the fixture ---------------------------------------------------


def test_fixture_ingests_with_expected_counts(store: ShadowStore) -> None:
    data = FIXTURE.read_bytes()

    result = ingest_file(store, FIXTURE, fmt="ndjson", repo=None, now=NOW)

    assert isinstance(result, IngestResult)
    assert isinstance(result, FrozenModel)
    assert result.created is True
    assert result.shadow_id.startswith("shadow_")
    assert (result.adapter, result.adapter_version) == ("ndjson", "1.0.0")
    assert result.session_id == "fixture-session-v1"
    assert (
        result.event_count,
        result.observed_count,
        result.inferred_count,
        result.claim_count,
        result.unknown_count,
    ) == (32, 29, 3, 2, 1)
    assert result.source_sha256 == sha256_hex(data)
    assert result.source_bytes == len(data)
    assert result.repo_label is None
    assert result.elapsed_ms >= 0
    record = store.session(result.shadow_id)
    assert (record.adapter, record.adapter_version) == ("ndjson", "1.0.0")
    assert record.source_adapter == "fixture-emitter"
    assert record.source_adapter_version == "0.1.0"
    assert record.session_id == "fixture-session-v1"
    assert record.event_count == 32
    assert record.ingested_at == "2026-08-22T12:30:00Z"
    assert record.summary == {
        "event_count": 32,
        "observed_count": 29,
        "inferred_count": 3,
        "claim_count": 2,
        "unknown_count": 1,
        "raw_record_count": 30,
        "source_adapter": "fixture-emitter",
        "source_adapter_version": "0.1.0",
        "has_source_claims": False,
        "heuristics": {"claims": "claims.v1"},
    }
    assert record.to_dict()["source_adapter"] == "fixture-emitter"
    assert len(store.events(result.shadow_id)) == 32


def test_reingest_is_idempotent(store: ShadowStore) -> None:
    first = ingest_file(store, FIXTURE, fmt="ndjson", repo=None, now=NOW)

    second = ingest_file(store, FIXTURE, fmt="ndjson", repo=None)

    assert second.created is False
    assert second.shadow_id == first.shadow_id
    assert second.model_dump(exclude={"created", "elapsed_ms"}) == first.model_dump(
        exclude={"created", "elapsed_ms"}
    )
    assert len(store.sessions()) == 1


def test_exported_stream_reingests_to_the_same_shadow_id(
    store: ShadowStore, tmp_path: Path
) -> None:
    first = ingest_file(store, FIXTURE, fmt="ndjson", repo=None)
    events = store.events(first.shadow_id)
    exported = tmp_path / "events.ndjson"
    exported.write_bytes(
        b"".join(canonical_json_bytes(event.to_record()) + b"\n" for event in events)
    )

    again = ingest_file(store, exported, fmt="ndjson", repo=None)
    fresh_store = ShadowStore(tmp_path / "fresh.sqlite3")
    fresh = ingest_file(fresh_store, exported, fmt="ndjson", repo=None)

    assert again.shadow_id == first.shadow_id
    assert again.created is False
    assert fresh.shadow_id == first.shadow_id
    assert fresh.created is True
    assert fresh.claim_count == 2
    assert fresh.event_count == 32
    assert fresh.source_sha256 != first.source_sha256
    assert fresh_store.session(fresh.shadow_id).summary["has_source_claims"] is True
    assert fresh_store.events(fresh.shadow_id) == events


def test_claims_are_inserted_directly_after_their_message(store: ShadowStore) -> None:
    result = ingest_file(store, FIXTURE, fmt="ndjson", repo=None)
    events = store.events(result.shadow_id)

    claims = [event for event in events if event.kind == "claim"]
    assert [claim.seq for claim in claims] == [12, 32]
    for claim in claims:
        message = events[claim.seq - 2]
        assert message.kind == "message" and message.actor == "agent"
        assert claim.provenance == "inferred"
        assert claim.actor == "agent"
        assert claim.derived_from == (message.event_id,)
        assert claim.content_digest == message.content_digest
        assert claim.ts == message.ts
        assert claim.paths == () and claim.outside_paths == ()
        assert claim.tool is None and claim.argv_excerpt is None
        assert claim.claim is not None
        assert claim.claim.matcher == "claims.v1"
        assert claim.claim.category == "checks_pass"
        assert claim.claim.pattern_id == "tests-pass"
        assert claim.source.adapter == message.source.adapter
        assert claim.source.adapter_version == message.source.adapter_version
        assert claim.source.record_ref == message.source.record_ref
        assert claim.source.raw_type == "claim"
    assert claims[0].excerpt == "Tests pass for app/greet.py and app/config.py"
    assert claims[1].excerpt == "All tests pass"
    assert events[30].excerpt is not None and events[30].excerpt.startswith("All tests")
    assert [event.seq for event in events] == list(range(1, 33))


def test_fixture_triggers_every_lint_rule(store: ShadowStore) -> None:
    result = ingest_file(store, FIXTURE, fmt="ndjson", repo=None)
    events = store.events(result.shadow_id)

    graph = reconstruct(events)
    report = lint(events, graph)

    assert report.rule_counts == {
        "claimed-without-evidence": 1,
        "edit-without-check": 3,
        "write-overlap": 2,
        "scope-drift": 1,
        "destructive-unverified": 1,
        "network-or-install": 2,
    }
    assert [(ratio.numerator, ratio.denominator) for ratio in report.ratios] == [
        (1, 4),
        (1, 2),
        (2, 3),
    ]
    assert [segment.boundary for segment in graph.segments] == [
        "session_start",
        "user_message",
        "plan_marker",
    ]
    assert len(graph.edges) == 1
    unbacked = [f for f in report.findings if f.rule == "claimed-without-evidence"]
    assert 'Claim "All tests pass"' in unbacked[0].message
    drift = [f for f in report.findings if f.rule == "scope-drift"]
    assert drift[0].paths == (".env",)


# -- claim extraction rules --------------------------------------------------


def test_matcher_runs_over_the_excerpt_for_ndjson(
    store: ShadowStore, tmp_path: Path
) -> None:
    path = _write(
        tmp_path / "s.ndjson",
        _record(1, actor="user", excerpt="All tests pass."),
        _record(2, excerpt="Working on it."),
        _record(3, excerpt="Done. All tests pass and lint is clean."),
    )

    result = ingest_file(store, path, fmt="ndjson", repo=None)
    events = store.events(result.shadow_id)

    assert result.claim_count == 1
    assert [event.kind for event in events] == [
        "message",
        "message",
        "message",
        "claim",
    ]
    assert events[3].derived_from == (events[2].event_id,)
    assert events[3].excerpt == "All tests pass and lint is clean"


def test_source_claims_make_the_emitter_the_authority(
    store: ShadowStore, tmp_path: Path
) -> None:
    message = _record(1, excerpt="All tests pass.")
    message_id = ShadowEvent.from_record(message).event_id
    path = _write(
        tmp_path / "s.ndjson",
        message,
        _record(
            2,
            kind="claim",
            claim={**CLAIM, "pattern_id": "emitter-said-so"},
            provenance="inferred",
            derived_from=[message_id],
            excerpt="All tests pass.",
        ),
        _record(3, excerpt="Build succeeds too."),
    )

    result = ingest_file(store, path, fmt="ndjson", repo=None)
    events = store.events(result.shadow_id)

    assert result.claim_count == 1
    assert result.event_count == 3
    assert events[1].claim is not None
    assert events[1].claim.pattern_id == "emitter-said-so"
    assert store.session(result.shadow_id).summary["has_source_claims"] is True


def test_private_draft_fields_feed_the_matcher_but_never_persist(
    store: ShadowStore, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    full_text = "Working on it.\n\nAll 12 tests pass now and the fix is complete."

    class FakeAdapter:
        name = "fake"
        version = "0.0.1"

        def parse(self, data: bytes, *, repo: Path | None) -> ParsedSession:
            base = _record(1)
            fields = {
                name: value
                for name, value in base.items()
                if name
                not in {
                    "schema",
                    "seq",
                    "event_id",
                    "provenance",
                    "derived_from",
                    "session_id",
                }
            }
            user = Draft(
                {**fields, "actor": "user", "excerpt": "Fix it."}, "observed", ()
            )
            agent = Draft(
                {
                    **fields,
                    "excerpt": "Working on it.",
                    "_full_text": full_text,
                    "_scratch": {"not": "persisted"},
                },
                "observed",
                (),
            )
            return ParsedSession(
                "sess-fake", (user, agent), False, 2, 0, "fake", "0.0.1"
            )

    monkeypatch.setitem(ADAPTERS, "fake", FakeAdapter())
    source = tmp_path / "anything.bin"
    source.write_bytes(b"opaque")

    result = ingest_file(store, source, fmt="fake", repo=None)
    events = store.events(result.shadow_id)

    assert (result.adapter, result.adapter_version) == ("fake", "0.0.1")
    # One match per sentence: the full text yields exactly one claim, and the
    # persisted excerpt of the message stays the adapter's bounded excerpt.
    assert [event.kind for event in events] == ["message", "message", "claim"]
    assert events[2].excerpt == "All 12 tests pass now and the fix is complete"
    assert events[2].claim is not None and events[2].claim.pattern_id == "tests-pass"
    assert events[2].derived_from == (events[1].event_id,)
    assert events[1].excerpt == "Working on it."
    assert result.claim_count == 1 and result.event_count == 3
    for event in events:
        assert set(event.to_record()) == set(EVENT_FIELDS) | {"event_id"}
    blobs = b"\n".join(_event_blobs(Path(store.path)))
    assert b"_full_text" not in blobs and b"_scratch" not in blobs
    assert b"not persisted" not in blobs and b"persisted" not in blobs


def test_no_claim_without_agent_success_text(
    store: ShadowStore, tmp_path: Path
) -> None:
    path = _write(
        tmp_path / "s.ndjson",
        _record(1, actor="user", excerpt="Tests pass on my machine."),
        _record(2, excerpt="Tests should pass once the fixture is regenerated."),
        _record(3, excerpt=None, content_digest=None),
        _record(4, kind="tool_call", tool="Bash", excerpt="All tests pass."),
    )

    result = ingest_file(store, path, fmt="ndjson", repo=None)

    assert result.claim_count == 0
    assert result.event_count == 4


# -- redaction before persistence --------------------------------------------


def test_secret_shaped_excerpts_are_redacted_before_persistence(
    store: ShadowStore, tmp_path: Path
) -> None:
    token = "abcd1234efgh5678ijkl"
    path = _write(
        tmp_path / "s.ndjson",
        # Two spaces, not a tab: control characters now fail closed at the
        # adapter, and the double space still exercises whitespace collapse.
        _record(1, excerpt=f"Set TOKEN={token} in the shell.  All tests pass."),
        _record(
            2,
            kind="command_exec",
            tool="Bash",
            argv_digest="cd" * 32,
            argv_excerpt=f"curl -H 'Authorization: Bearer {token}{token}' https://x",
        ),
    )

    result = ingest_file(store, path, fmt="ndjson", repo=None)
    events = store.events(result.shadow_id)

    assert [event.kind for event in events] == ["message", "claim", "command_exec"]
    assert events[0].excerpt == f"Set {REDACTED} in the shell. All tests pass."
    assert events[1].excerpt == "All tests pass"
    assert events[2].argv_excerpt == f"curl -H 'Authorization: {REDACTED}' https://x"
    blobs = b"\n".join(_event_blobs(Path(store.path)))
    assert token.encode() not in blobs
    assert REDACTED.encode() in blobs


def test_redaction_is_stable_on_reingest(store: ShadowStore, tmp_path: Path) -> None:
    path = _write(tmp_path / "s.ndjson", _record(1, excerpt="PASSWORD=hunter22 done"))
    first = ingest_file(store, path, fmt="ndjson", repo=None)
    events = store.events(first.shadow_id)
    exported = tmp_path / "events.ndjson"
    exported.write_bytes(
        b"".join(canonical_json_bytes(event.to_record()) + b"\n" for event in events)
    )

    again = ingest_file(store, exported, fmt="ndjson", repo=None)

    assert again.shadow_id == first.shadow_id
    assert events[0].excerpt == f"{REDACTED} done"


# -- source-file discipline --------------------------------------------------


def test_unsupported_format_fails_closed(store: ShadowStore) -> None:
    with pytest.raises(AdapterError, match="unsupported shadow format: claude-code"):
        ingest_file(store, FIXTURE, fmt="claude-code", repo=None)
    assert store.sessions() == []


def test_source_must_be_a_regular_file(store: ShadowStore, tmp_path: Path) -> None:
    with pytest.raises(IngestError, match="source file not found"):
        ingest_file(store, tmp_path / "missing.ndjson", fmt="ndjson", repo=None)
    with pytest.raises(IngestError, match="source must be a regular file"):
        ingest_file(store, tmp_path, fmt="ndjson", repo=None)
    link = tmp_path / "link.ndjson"
    link.symlink_to(FIXTURE)
    assert ingest_file(store, link, fmt="ndjson", repo=None).event_count == 32
    assert issubclass(IngestError, AdapterError)


def test_source_size_cap_is_enforced(
    store: ShadowStore, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(ingest_module, "SOURCE_SIZE_LIMIT", 1024)

    with pytest.raises(IngestError, match="exceeds the 256 MiB limit"):
        ingest_file(store, FIXTURE, fmt="ndjson", repo=None)
    assert store.sessions() == []


def test_adapter_errors_persist_nothing(store: ShadowStore, tmp_path: Path) -> None:
    path = _write(tmp_path / "s.ndjson", _record(1), _record(2, kind="dance"))

    with pytest.raises(AdapterError, match='line 2: unknown kind "dance"'):
        ingest_file(store, path, fmt="ndjson", repo=None)
    assert store.sessions() == []
    assert _event_blobs(Path(store.path)) == []


def test_repo_label_is_the_home_collapsed_repository_path(
    store: ShadowStore, tmp_path: Path
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()

    result = ingest_file(store, FIXTURE, fmt="ndjson", repo=repo)

    assert result.repo_label == collapse_home(repo.resolve().as_posix())
    assert store.session(result.shadow_id).repo_label == result.repo_label
    with pytest.raises(IngestError, match="repo must be an existing directory"):
        ingest_file(store, FIXTURE, fmt="ndjson", repo=tmp_path / "absent")


def test_argument_types_are_checked(store: ShadowStore) -> None:
    with pytest.raises(TypeError, match="requires a ShadowStore"):
        ingest_file(object(), FIXTURE, fmt="ndjson", repo=None)  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="requires a Path"):
        ingest_file(store, str(FIXTURE), fmt="ndjson", repo=None)  # type: ignore[arg-type]


def test_package_exports_the_pipeline() -> None:
    for name in (
        "ingest_file",
        "IngestResult",
        "AdapterError",
        "adapter_for",
        "reconstruct",
        "ShadowGraph",
        "graph_to_dot",
        "lint",
        "LintReport",
        "RULES",
        "report_value",
        "render_report",
        "ShadowStore",
        "extract_claims",
        "classify_command",
    ):
        assert name in shadow_package.__all__
        assert getattr(shadow_package, name) is not None
    assert shadow_package.ingest_file is ingest_file


# -- review findings: forged lines, split secrets, collapsed markdown ---------


def _fake_adapter_fields() -> dict[str, object]:
    base = _record(1)
    return {
        name: value
        for name, value in base.items()
        if name
        not in {"schema", "seq", "event_id", "provenance", "derived_from", "session_id"}
    }


def test_forged_report_lines_in_paths_are_rejected_before_anything_persists(
    store: ShadowStore, tmp_path: Path
) -> None:
    path = _write(
        tmp_path / "s.ndjson",
        _record(1, actor="user", excerpt="fix it"),
        _record(
            2,
            kind="file_edit",
            paths=["a\n  [claimed-without-evidence] FORGED LINE"],
            excerpt=None,
            content_digest=None,
        ),
        _record(
            3,
            kind="file_delete",
            outside_paths=["/tmp/x\nHIGH (1)\n  [forged] injected finding"],
            excerpt=None,
            content_digest=None,
        ),
    )

    with pytest.raises(
        AdapterError,
        match=r'line 2: field "paths\[0\]": must not contain control characters',
    ):
        ingest_file(store, path, fmt="ndjson", repo=None)
    assert store.sessions() == []


def test_control_and_zero_width_split_secrets_are_redacted_before_persistence(
    store: ShadowStore, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    bearer = "abcdefghijklmnopqrstuvwxyz012345"
    split_bearer = bearer[:8] + "\x7f" + bearer[8:]
    sk = "sk-" + "a" * 40
    split_sk = "sk-\u200d" + "a" * 40

    class FakeAdapter:
        name = "fake"
        version = "0.0.1"

        def parse(self, data: bytes, *, repo: Path | None) -> ParsedSession:
            fields = _fake_adapter_fields()
            message = Draft(
                {**fields, "excerpt": f"note: Bearer {split_bearer} end"},
                "observed",
                (),
            )
            command = Draft(
                {
                    **fields,
                    "kind": "command_exec",
                    "tool": "Bash",
                    "excerpt": None,
                    "content_digest": None,
                    "argv_digest": "cd" * 32,
                    "argv_excerpt": f"run {split_sk}",
                },
                "observed",
                (),
            )
            return ParsedSession(
                "sess-fake", (message, command), False, 2, 0, "fake", "0.0.1"
            )

    monkeypatch.setitem(ADAPTERS, "fake", FakeAdapter())
    source = tmp_path / "anything.bin"
    source.write_bytes(b"opaque")

    result = ingest_file(store, source, fmt="fake", repo=None)
    events = store.events(result.shadow_id)

    assert events[0].excerpt == f"note: {REDACTED} end"
    assert events[1].argv_excerpt == f"run {REDACTED}"
    blobs = b"\n".join(_event_blobs(Path(store.path)))
    assert bearer.encode() not in blobs
    assert sk.encode() not in blobs
    assert ("a" * 40).encode() not in blobs


def test_collapsed_checkbox_and_explanation_text_yields_no_claims(
    store: ShadowStore, tmp_path: Path
) -> None:
    # The review's end-to-end case, already whitespace-collapsed the way an
    # ndjson excerpt arrives: three false claims before the fix, none after.
    text = (
        "None of the tests pass. Here is how it works: the cache is keyed by "
        "path. - [ ] All tests pass The problem is fixed-point precision."
    )
    path = _write(
        tmp_path / "s.ndjson",
        _record(1, actor="user", excerpt="go"),
        _record(2, excerpt=text),
    )

    result = ingest_file(store, path, fmt="ndjson", repo=None)

    assert result.claim_count == 0
    assert result.event_count == 2
