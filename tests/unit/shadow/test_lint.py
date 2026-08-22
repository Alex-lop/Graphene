from __future__ import annotations

import json

import pytest

from graphene.shadow.events import ShadowEvent
from graphene.shadow.lint import (
    COVERAGE_NOTE,
    GOVERNED_CLAIM,
    GOVERNED_SCOPE,
    LINT_VERSION,
    RULES,
    Finding,
    LintReport,
    lint,
    sensitive_reason,
)
from graphene.shadow.reconstruct import SEGMENTS_VERSION, reconstruct

_ACTORS = {
    "message": "user",
    "check_result": "tool",
    "command_result": "tool",
    "tool_result": "tool",
}
_CLAIM = {"matcher": "claims.v1", "category": "checks_pass", "pattern_id": "tests-pass"}


def _event(seq: int, kind: str, **over: object) -> ShadowEvent:
    fields: dict[str, object] = {
        "session_id": "sess-1",
        "seq": seq,
        "actor": _ACTORS.get(kind, "agent"),
        "kind": kind,
        "provenance": "observed",
        "source": {
            "adapter": "ndjson",
            "adapter_version": "1.0.0",
            "record_ref": f"line:{seq}",
            "raw_type": "test",
        },
    }
    fields.update(over)
    return ShadowEvent.create(**fields)


def _claim(seq: int, message: ShadowEvent, **over: object) -> ShadowEvent:
    fields: dict[str, object] = {
        "provenance": "inferred",
        "derived_from": (message.event_id,),
        "claim": _CLAIM,
        "excerpt": message.excerpt,
    }
    fields.update(over)
    return _event(seq, "claim", **fields)


def _passing(seq: int, **over: object) -> ShadowEvent:
    fields: dict[str, object] = {"check_family": "pytest", "exit_code": 0}
    fields.update(over)
    return _event(seq, "check_result", **fields)


def _run(events: list[ShadowEvent], **kwargs: object) -> LintReport:
    return lint(events, reconstruct(events), **kwargs)


def _rule(report: LintReport, rule: str) -> list[Finding]:
    return [finding for finding in report.findings if finding.rule == rule]


def _ratio(report: LintReport, key: str) -> tuple[int, int]:
    ratio = next(ratio for ratio in report.ratios if ratio.key == key)
    return ratio.numerator, ratio.denominator


# -- claimed-without-evidence -------------------------------------------------


def test_claim_without_a_check_after_the_last_edit_is_high_and_mixed():
    message = _event(3, "message", actor="agent", excerpt="All tests pass.")
    events = [
        _event(1, "message", excerpt="go"),
        _event(2, "file_edit", paths=("app/a.py",)),
        message,
        _claim(4, message),
    ]

    report = _run(events)
    findings = _rule(report, "claimed-without-evidence")

    assert len(findings) == 1
    finding = findings[0]
    assert finding.severity == "high"
    assert finding.basis == "mixed"
    assert finding.governed_diff == GOVERNED_CLAIM
    assert finding.message == (
        'Claim "All tests pass." (checks_pass) has no observed passing check '
        "after the last edit (seq 2)."
    )
    assert finding.event_ids == (events[3].event_id, message.event_id)
    assert finding.seqs == (3, 4)
    assert finding.segment_ids == ("seg_0001",)
    assert _ratio(report, "backed_claims") == (0, 1)


def test_claim_backed_by_observed_passing_check_after_the_edit():
    message = _event(5, "message", actor="agent", excerpt="All tests pass.")
    events = [
        _event(1, "message", excerpt="go"),
        _event(2, "file_edit", paths=("app/a.py",)),
        _event(3, "check_run", check_family="pytest"),
        _passing(4),
        message,
        _claim(6, message),
    ]

    report = _run(events)

    assert _rule(report, "claimed-without-evidence") == []
    assert _ratio(report, "backed_claims") == (1, 1)


def test_claim_with_no_preceding_edit_counts_checks_from_seq_zero():
    message = _event(2, "message", actor="agent", excerpt="Tests pass.")
    events = [_passing(1), message, _claim(3, message)]

    report = _run(events)

    assert _rule(report, "claimed-without-evidence") == []
    assert _ratio(report, "backed_claims") == (1, 1)


@pytest.mark.parametrize(
    "check",
    (
        _passing(1),  # before the edit, so it does not cover it
        _event(3, "check_result", check_family="pytest", exit_code=1),
        _event(3, "check_run", check_family="pytest"),
        _event(3, "command_result", exit_code=0),
    ),
)
def test_claim_is_unbacked_by_earlier_failing_or_other_checks(check: ShadowEvent):
    message = _event(4, "message", actor="agent", excerpt="Tests pass.")
    stream = {1: _event(1, "unknown"), 2: _event(2, "file_edit", paths=("a.py",))}
    stream[3] = _event(3, "unknown")
    stream[check.seq] = check
    events = [stream[1], stream[2], stream[3], message, _claim(5, message)]

    report = _run(events)

    assert len(_rule(report, "claimed-without-evidence")) == 1
    assert _ratio(report, "backed_claims") == (0, 1)


def test_inferred_passing_check_does_not_back_a_claim():
    command = _event(3, "command_exec", argv_excerpt="pytest -q")
    message = _event(5, "message", actor="agent", excerpt="Tests pass.")
    events = [
        _event(1, "message", excerpt="go"),
        _event(2, "file_edit", paths=("a.py",)),
        command,
        _passing(4, provenance="inferred", derived_from=(command.event_id,)),
        message,
        _claim(6, message),
    ]

    report = _run(events)

    assert len(_rule(report, "claimed-without-evidence")) == 1


def test_delete_counts_as_the_last_edit_for_claims():
    message = _event(4, "message", actor="agent", excerpt="Tests pass.")
    events = [
        _event(1, "file_edit", paths=("a.py",)),
        _passing(2),
        _event(3, "file_delete", paths=("b.py",)),
        message,
        _claim(5, message),
    ]

    report = _run(events)

    assert len(_rule(report, "claimed-without-evidence")) == 1
    assert "(seq 3)" in _rule(report, "claimed-without-evidence")[0].message


# -- edit-without-check -------------------------------------------------------


def test_edit_without_check_fires_per_path_with_last_write_provenance():
    command = _event(3, "command_exec", argv_excerpt="sed -i s/a/b/ c.py")
    events = [
        _event(1, "file_edit", paths=("a.py", "b.py")),
        _event(2, "file_create", paths=("b.py",)),
        command,
        _event(
            4,
            "file_edit",
            paths=("c.py",),
            provenance="inferred",
            derived_from=(command.event_id,),
        ),
    ]

    report = _run(events)
    findings = _rule(report, "edit-without-check")

    assert [(f.paths, f.seqs, f.basis) for f in findings] == [
        (("a.py",), (1,), "observed"),
        (("b.py",), (2,), "observed"),
        (("c.py",), (4,), "inferred"),
    ]
    assert findings[0].message == (
        "a.py was last edited at seq 1 and no observed check passed afterwards."
    )
    assert all(f.severity == "warn" and f.governed_diff is None for f in findings)
    assert findings[1].event_ids == (events[1].event_id,)
    assert _ratio(report, "covered_files") == (0, 3)


def test_edit_followed_by_passing_check_is_covered_until_edited_again():
    covered = [_event(1, "file_edit", paths=("a.py",)), _passing(2)]
    reedited = covered + [_event(3, "file_edit", paths=("a.py",))]

    assert _rule(_run(covered), "edit-without-check") == []
    assert _ratio(_run(covered), "covered_files") == (1, 1)
    findings = _rule(_run(reedited), "edit-without-check")
    assert [(f.paths, f.seqs) for f in findings] == [(("a.py",), (3,))]


def test_delete_and_read_do_not_count_as_edits_for_coverage():
    events = [
        _event(1, "file_delete", paths=("gone.py",)),
        _event(2, "file_read", paths=("seen.py",)),
    ]

    report = _run(events)

    assert _rule(report, "edit-without-check") == []
    assert _ratio(report, "covered_files") == (0, 0)


# -- write-overlap ------------------------------------------------------------


def test_write_overlap_fires_once_per_path_across_segments():
    events = [
        _event(1, "message", excerpt="first"),
        _event(2, "file_edit", paths=("a.py", "b.py")),
        _event(3, "message", excerpt="second"),
        _event(4, "file_edit", paths=("a.py",)),
        _event(5, "message", excerpt="third"),
        _event(6, "file_delete", paths=("a.py",)),
        _passing(7),
    ]

    report = _run(events)
    findings = _rule(report, "write-overlap")

    assert len(findings) == 1
    finding = findings[0]
    assert finding.paths == ("a.py",)
    assert finding.segment_ids == ("seg_0001", "seg_0002", "seg_0003")
    assert finding.seqs == (2, 4, 6)
    assert finding.event_ids == tuple(events[i].event_id for i in (1, 3, 5))
    assert finding.basis == "inferred"
    assert finding.severity == "warn"
    assert finding.governed_diff is None
    assert finding.message == (
        "a.py was written from 3 inferred segments (seg_0001, seg_0002, seg_0003); "
        "under a governed mission these would have been separate leased tasks and "
        "the second write would have been fenced."
    )
    assert _ratio(report, "overlap_segments") == (3, 3)


def test_repeated_writes_inside_one_segment_do_not_overlap():
    events = [
        _event(1, "file_edit", paths=("a.py",)),
        _event(2, "file_edit", paths=("a.py",)),
        _event(3, "message", excerpt="next"),
        _event(4, "file_edit", paths=("b.py",)),
    ]

    report = _run(events)

    assert _rule(report, "write-overlap") == []
    assert _ratio(report, "overlap_segments") == (0, 2)


# -- scope-drift --------------------------------------------------------------


def test_scope_drift_on_outside_path_is_high_with_governed_sentence():
    events = [
        _event(1, "file_edit", paths=("app/a.py",), outside_paths=("~/.zshrc",)),
        _passing(2),
    ]

    finding = _rule(_run(events), "scope-drift")[0]

    assert finding.severity == "high"
    assert finding.governed_diff == GOVERNED_SCOPE
    assert finding.basis == "observed"
    assert finding.paths == ("~/.zshrc",)
    assert finding.message == "file_edit at seq 1 wrote ~/.zshrc (outside repository)."


@pytest.mark.parametrize(
    ("path", "reason"),
    (
        (".env", "environment file"),
        ("config/.env.local", "environment file"),
        ("certs/server.pem", "key material"),
        ("keys/store.jks", "key material"),
        (".ssh/id_rsa", "ssh key"),
        ("home/id_ed25519.pub", "ssh key"),
        ("app/Secrets.py", "secret-like name"),
        ("infra/aws_credentials", "secret-like name"),
        (".github/workflows/ci.yml", "ci configuration"),
        (".circleci/config.yml", "ci configuration"),
        (".gitlab-ci.yml", "ci configuration"),
        ("ci/Jenkinsfile", "ci configuration"),
        (".travis.yml", "ci configuration"),
        ("uv.lock", "lockfile"),
        ("web/package-lock.json", "lockfile"),
        ("Cargo.lock", "lockfile"),
    ),
)
def test_sensitive_paths_trigger_scope_drift(path: str, reason: str):
    assert sensitive_reason(path) == reason
    events = [_event(1, "file_create", paths=(path,)), _passing(2)]

    findings = _rule(_run(events), "scope-drift")

    assert len(findings) == 1
    assert findings[0].message == (
        f"file_create at seq 1 wrote {path} (sensitive: {reason})."
    )
    assert findings[0].paths == (path,)


@pytest.mark.parametrize(
    "path", ("app/main.py", "docs/environment.md", "tests/test_lock.py", "keyboard.py")
)
def test_ordinary_paths_are_not_sensitive(path: str):
    assert sensitive_reason(path) is None
    events = [_event(1, "file_edit", paths=(path,)), _passing(2)]

    assert _rule(_run(events), "scope-drift") == []


def test_scope_drift_ignores_reads_and_lists_every_offending_path_once():
    events = [
        _event(1, "file_read", paths=(".env",), outside_paths=("~/x",)),
        _event(
            2,
            "file_delete",
            paths=(".env", "app/a.py", "uv.lock"),
            outside_paths=("~/y",),
        ),
        _passing(3),
    ]

    findings = _rule(_run(events), "scope-drift")

    assert len(findings) == 1
    assert findings[0].seqs == (2,)
    assert findings[0].paths == ("~/y", ".env", "uv.lock")
    assert findings[0].message == (
        "file_delete at seq 2 wrote ~/y (outside repository); "
        ".env (sensitive: environment file); uv.lock (sensitive: lockfile)."
    )


# -- destructive-unverified ---------------------------------------------------


def test_delete_without_a_later_passing_check_is_warned():
    events = [
        _event(1, "file_delete", paths=("old.py", "older.py")),
        _event(2, "check_result", check_family="pytest", exit_code=1),
    ]

    findings = _rule(_run(events), "destructive-unverified")

    assert len(findings) == 1
    assert findings[0].severity == "warn"
    assert findings[0].basis == "observed"
    assert findings[0].paths == ("old.py", "older.py")
    assert findings[0].message == (
        "old.py, older.py deleted at seq 1 with no observed check afterwards."
    )


def test_delete_followed_by_passing_check_is_not_warned():
    events = [_event(1, "file_delete", paths=("old.py",)), _passing(2)]

    assert _rule(_run(events), "destructive-unverified") == []


def test_delete_of_outside_path_names_that_path():
    events = [_event(1, "file_delete", outside_paths=("~/tmp/x",))]

    findings = _rule(_run(events), "destructive-unverified")

    assert findings[0].message == (
        "~/tmp/x deleted at seq 1 with no observed check afterwards."
    )


# -- network-or-install -------------------------------------------------------


def test_install_and_network_ops_are_surfaced_as_info():
    events = [
        _event(1, "install_op", argv_excerpt="uv sync"),
        _event(2, "network_op"),
        _event(3, "command_exec", argv_excerpt="curl-free"),
        _event(4, "vcs_op", argv_excerpt="git push"),
    ]

    findings = _rule(_run(events), "network-or-install")

    assert [f.message for f in findings] == [
        "install_op observed at seq 1: uv sync (surfaced, not judged).",
        "network_op observed at seq 2: no excerpt (surfaced, not judged).",
    ]
    assert all(f.severity == "info" and f.basis == "observed" for f in findings)
    assert all(f.governed_diff is None for f in findings)


# -- ratios, ordering, filtering, report shape -------------------------------


def _mixed_stream() -> list[ShadowEvent]:
    first_claim_message = _event(6, "message", actor="agent", excerpt="Tests pass.")
    second_claim_message = _event(11, "message", actor="agent", excerpt="All green.")
    return [
        _event(1, "message", excerpt="start"),
        _event(2, "file_edit", paths=("a.py", "b.py")),
        _event(3, "install_op", argv_excerpt="uv sync"),
        _event(4, "check_run", check_family="pytest"),
        _passing(5),
        first_claim_message,
        _claim(7, first_claim_message),
        _event(8, "message", excerpt="second task"),
        _event(9, "file_edit", paths=("a.py", "c.py")),
        _event(10, "file_delete", paths=("old.py",), outside_paths=("~/scratch",)),
        second_claim_message,
        _claim(12, second_claim_message),
        _event(13, "message", excerpt="third task"),
        _event(14, "file_read", paths=("c.py",)),
    ]


def test_ratio_arithmetic_over_a_mixed_stream():
    report = _run(_mixed_stream())

    assert _ratio(report, "covered_files") == (1, 3)
    assert _ratio(report, "backed_claims") == (1, 2)
    assert _ratio(report, "overlap_segments") == (2, 3)
    definitions = {ratio.key: ratio.definition for ratio in report.ratios}
    assert definitions == {
        "covered_files": (
            "changed files whose last edit was followed by an observed passing check"
        ),
        "backed_claims": (
            "success claims backed by an observed passing check after the last "
            "preceding edit"
        ),
        "overlap_segments": (
            "inferred segments that wrote a path another segment also wrote"
        ),
    }


def test_findings_are_ordered_by_severity_then_first_seq():
    report = _run(_mixed_stream())

    order = [(f.severity, f.rule, min(f.seqs)) for f in report.findings]
    assert order == [
        ("high", "scope-drift", 10),
        ("high", "claimed-without-evidence", 11),
        ("warn", "write-overlap", 2),
        ("warn", "edit-without-check", 9),
        ("warn", "edit-without-check", 9),
        ("warn", "destructive-unverified", 10),
        ("info", "network-or-install", 3),
    ]
    assert report.rule_counts == {
        "claimed-without-evidence": 1,
        "edit-without-check": 2,
        "write-overlap": 1,
        "scope-drift": 1,
        "destructive-unverified": 1,
        "network-or-install": 1,
    }


def test_governed_diff_is_present_exactly_on_high_findings():
    report = _run(_mixed_stream())

    assert report.findings
    for finding in report.findings:
        assert (finding.severity == "high") == (finding.governed_diff is not None)
    with pytest.raises(ValueError, match="exactly on high"):
        Finding(
            rule="edit-without-check",
            severity="warn",
            message="x",
            event_ids=(),
            seqs=(),
            paths=(),
            segment_ids=(),
            basis="observed",
            governed_diff=GOVERNED_CLAIM,
        )


def test_rules_filter_limits_findings_but_ratios_are_still_computed():
    report = _run(_mixed_stream(), rules=["network-or-install", "network-or-install"])

    assert report.rules_applied == ("network-or-install",)
    assert {f.rule for f in report.findings} == {"network-or-install"}
    assert report.rule_counts == {"network-or-install": 1}
    assert _ratio(report, "covered_files") == (1, 3)
    assert _ratio(report, "backed_claims") == (1, 2)
    assert _ratio(report, "overlap_segments") == (2, 3)


def test_rules_filter_keeps_canonical_order_and_rejects_unknown_or_empty():
    report = _run(_mixed_stream(), rules=("scope-drift", "claimed-without-evidence"))

    assert report.rules_applied == ("claimed-without-evidence", "scope-drift")
    with pytest.raises(ValueError, match="unknown lint rule: bogus"):
        _run(_mixed_stream(), rules=("bogus",))
    with pytest.raises(ValueError, match="at least one lint rule"):
        _run(_mixed_stream(), rules=())


def test_report_carries_versions_and_verbatim_coverage_note():
    report = _run(_mixed_stream())

    assert report.lint_version == LINT_VERSION == "lint.v1"
    assert report.segments_version == SEGMENTS_VERSION
    assert report.rules_applied == RULES
    assert report.coverage_note == COVERAGE_NOTE
    assert report.coverage_note == (
        "Coverage is coarse in v0: a file counts as covered when an observed passing "
        "check ran after the file's last edit. Graphene did not inspect which tests "
        "exercise which file."
    )


def test_clean_stream_has_no_findings_and_zero_counts():
    events = [_event(1, "file_edit", paths=("a.py",)), _passing(2)]

    report = _run(events)

    assert report.findings == ()
    assert report.rule_counts == {rule: 0 for rule in RULES}
    assert _ratio(report, "covered_files") == (1, 1)
    assert _ratio(report, "backed_claims") == (0, 0)
    assert _ratio(report, "overlap_segments") == (0, 1)


def test_lint_fails_closed_when_graph_does_not_describe_the_events():
    events = _mixed_stream()
    other = [_event(1, "unknown"), _event(2, "unknown")]

    with pytest.raises(ValueError, match="does not describe"):
        lint(events, reconstruct(other))
    with pytest.raises(ValueError, match="disagrees with the stream"):
        lint(other, reconstruct([_event(1, "unknown"), _event(2, "file_read")]))
    with pytest.raises(ValueError, match="empty"):
        lint([], reconstruct(other))


def test_lint_report_round_trips_through_json():
    report = _run(_mixed_stream())

    restored = LintReport.model_validate(json.loads(report.model_dump_json()))

    assert restored == report


def test_claim_with_no_edit_and_no_check_says_so_instead_of_citing_seq_zero():
    # Review finding: the message used to cite "the last edit (seq 0)", an
    # event that cannot exist because seqs are 1-based.
    message = _event(1, "message", actor="agent", excerpt="All tests pass.")
    events = [message, _claim(2, message)]

    report = _run(events)

    (finding,) = _rule(report, "claimed-without-evidence")
    assert finding.message == (
        'Claim "All tests pass." (checks_pass): no edit precedes this claim; '
        "no observed passing check precedes it either."
    )
    assert "seq 0" not in finding.message
    assert finding.severity == "high"
    assert _ratio(report, "backed_claims") == (0, 1)
