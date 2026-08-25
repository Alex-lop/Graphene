# Session reports

One file per autonomous session, named for the date the session ran. These are
the detail behind the change ledger in
[`docs/IMPLEMENTATION_REPORT.md`](../IMPLEMENTATION_REPORT.md): what a session
was asked to do, what it proved, what it did not prove, what it spent, and what
it left for the next person.

They are a record, not a claim surface. A report states what was true on its own
date and is not updated afterwards, so where a report and
[`contracts/product_proof.json`](../../contracts/product_proof.json) disagree,
the contract wins. Current proof gaps live in
[`docs/KNOWN_LIMITATIONS.md`](../KNOWN_LIMITATIONS.md).

| Date | Report | What it covers | Final state |
|---|---|---|---|
| 2026-08-23 | [Night report](2026-08-23-night-report.md) | The first live North Star run on Vertex AI (`gemini-3.5-flash`, location `global`): two complete missions, two real workers each, provider receipts, the live failure laboratory, `graphene watch`, and the stretch Shadow v0 `claude-code` adapter | Both missions completed and their capsules cold-verify from a fresh clone. "Survives **and completes**" stayed a rehearsal claim — no laboratory mission completed after the injected kills. Spend ≈ $4.30 of $20; nothing pushed |
| 2026-08-23 | [Next steps](2026-08-23-next-steps.md) | Plain-language answers to three owner questions: what the first live two-worker run found (the Gemini API rejects any `response_schema` containing `anyOf`), where an API key belongs, and how to move onto Vertex AI to escape the 20-request daily free-tier cap | The schema fix is proven by the fake-model suite plus one live pass. Written for a reader, not a reviewer — the machine detail is in the night report |
| 2026-08-23 | [Convergence report](2026-08-23-convergence-report.md) | The two authority gates landed before any live spend — planning reads Git objects at the bound `base_sha` rather than worktree bytes, and the store recomputes the final result bundle itself instead of trusting the caller — plus locked `ruff` in CI, retry loops that carry a redacted diagnostic forward, and the narrowed two-task North Star | Gates landed and live missions plan in the new shape with zero lint issues. Nothing pushed, nothing deployed; the cloud command list it ends with has still not been run |
| 2026-08-24 | [Contract report](2026-08-24-contract-report.md) | Making `plan` a first-class verb: propose a commit-bound mission DAG, inspect a node contract, export and edit canonical YAML, compile revision N+1, lint, diff, approve a digest binding `mission_id + base_sha + revision + plan_sha256`, and prove the scheduler ran the operator's revision. Includes the three timed demo rehearsals | `MORNING VERIFY: ALL PASS` on the inherited tree. Three rehearsals found two defects that were fatal on camera, both fixed. The filmed sequence measures **1:17** against a ≤2:00 target. The preflight blocker closed 2026-08-25 and changed nothing |
| 2026-08-25 | _Night report — pending_ | Tonight's parallel-lane session. Placeholder row: the file lands at `docs/reports/2026-08-25-night-report.md` when the session's orchestrator writes it | Not yet written |

## Naming

`YYYY-MM-DD-<slug>.md`, dated for when the session ran rather than when a
sentence in it was last corrected. `scripts/check_doc_references.sh` fails if a
document anywhere in the tree still points at the root paths these files used to
occupy, and if any relative markdown link in the tree does not resolve.

Two files that look like they belong here and do not:

- [`simplreadme.md`](../../simplreadme.md) stays at the repository root. It is
  not a session report — it is a forwarding stub, and its whole function is that
  external judge links already resolve to that exact path. Moving it would break
  the one thing it exists to do, and no grep in this repository can see an
  inbound link break.
- `HANDOFF.md` is untracked by design and never enters a commit.
