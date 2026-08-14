# Redacted one-command demo transcript

The values below are redacted examples. The executable process proof is `tests/process/test_demo_cli.py`; the MCP-specific proof remains `tests/process/test_mcp_stdio.py`.

```text
$ uv run --frozen graphene demo --driver scripted-local

SCRIPTED LOCAL
Google ADK Runner: not used
Gemini calls: 0
Evidence source: committed and verified v2 SQLite lineage
Viewer: http://127.0.0.1:<free-port>/viewer/<run-id>
Private runtime: <owner-private-runtime>

DECISION PACKET — SCOPE
Correction: <bounded exact correction>
Proposed Scope: all_auth (app/auth/**)
Hunk: app/auth/limiter.py:<line> +<count> lines
Why: The exact correction must be explicitly scoped before memory is proposed.
SCOPE GATE: apply this correction to every app/auth/** change?
Type 'all_auth' or press Enter for this safe default: <Enter>

DECISION PACKET — MEMORY
Rule: <bounded proposed rule>
Scope: all_auth (app/auth/**)
Revision: 1
Digest: <sha256>
Why: Only this immutable scoped revision may enter an authorized handoff.
MEMORY GATE: approve the displayed scoped memory revision?
Type 'approve' or press Enter for this safe default: <Enter>

DECISION PACKET — PROMOTION
Changed Paths: app/auth/limiter.py, tests/test_security_policy.py
Test Receipt: <receipt-id> sha256=<sha256> passed=true
Candidate Digest: <sha256>
Why: Promotion binds these exact paths and candidate digest to the passing fixed-test receipt.
PROMOTION GATE: promote the verified bounded candidate?
Type 'promote' or press Enter for this safe default: <Enter>

DEMO COMPLETE — committed lineage verified
Origin run: <run-id>
Consumer run: <different-run-id>
Promotion state: PROMOTED
Viewer: http://127.0.0.1:<free-port>/viewer/<run-id>
Runtime retained: <owner-private-runtime>
Press Ctrl-C to stop the viewer. Evidence remains on disk.
^C
Viewer stopped. Runtime retained: <owner-private-runtime>
```

The browser observes sanitized projections derived from verified committed v2 events. It cannot submit a database path, mutate lineage, or expose private source/diff/prompt/test-output bytes. Billing denial records zero model dispatch; the fresh Auth consumer opens authorized evidence, rereads source, edits only allowed files, runs the fixed test, and reaches a human promotion checkpoint.

For manual MCP integration, export the printed database path after the demo and use `graphene watch`, `graphene inspect`, `graphene why`, or `graphene replay`. The primary demo itself requires no export, copied IDs, or extra terminals.

Process tests use a hidden `--automated-fixture --exit-after-demo` seam instead of sending fake keystrokes. Its terminal and viewer repeatedly say `SIMULATED OPERATOR — NOT HUMAN ATTESTATION`; its clarification answer, feedback, memory decision, and promotion approval are stored with `truth_kind=simulated_fixture`, `authority=simulated_fixture`, and a `simulated_fixture` source—not `human_attested`. It exercises the fixed downstream transitions but cannot support any claim that a person reviewed or decided them. Normal demo runs never select this seam, still wait for operator input at all three packets, and retain human-attested provenance.
