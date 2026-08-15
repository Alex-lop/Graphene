# Graphene, simply

Graphene is an evidence-backed review and handoff layer for a developer supervising bounded coding-agent work. It shows captured edits, tests, corrections, approved context, and unknowns behind one candidate. The terminal decides; the browser explains committed evidence. Graphene passes only approved evidence into the next bounded runtime. It does not infer hidden causality or claim activity outside its six operations.

## Fastest path: verified replay

```bash
uv sync --frozen
uv run --frozen graphene demo --driver verified-replay
```

This works on common development operating systems and creates no authoritative lineage state. It materializes a checked-in event fixture through v2 verification; it is not a captured live run. It is always labeled **VERIFIED REPLAY — NO LIVE AGENT, HUMAN ATTESTATION, OR NEW TEST EXECUTION**.

## Interactive macOS proof

```bash
uv run --frozen graphene demo --driver scripted-local
```

This deterministic workflow fixture requires macOS and `/usr/bin/sandbox-exec`. It stays labeled **SCRIPTED LOCAL WORKFLOW FIXTURE — NOT INDEPENDENT-AGENT OR GOOGLE ADK PROOF**. It shows the evidence before each terminal branch: broad/narrow correction scope, memory approve/reject, and candidate commit/reject. Only a real TTY can attest a human choice. Approval creates a commit only inside the retained isolated fixture checkout; it never changes the user's checkout or creates a push, PR, or deployment.

For the Google ADK integration proof:

```bash
uv run --frozen graphene demo --driver adk-fake
```

This uses the real ADK Runner with a deterministic fake model and zero external model calls. It stays labeled **REAL ADK RUNNER + DETERMINISTIC FAKE MODEL — NOT GEMINI OR INDEPENDENT-AGENT PROOF** and never falls back to another driver.

## Know the boundary

- The six captured operations are `search_repo`, `read_file`, `open_evidence`, `write_file`, `run_fixed_test`, and `request_completion`.
- Live execution is limited to the sanitized Auth fixture on macOS. Billing is the zero-dispatch denial case.
- Authorized source/evidence bytes, diffs, approved context, and bounded test output may be captured only in owner-private local artifacts.
- Raw source, diffs, prompts/context text, test stdout, secrets, credentials, and private artifacts are not publicly projected into the viewer or replay.
- Arbitrary shell/editor work, whole-repository activity, hidden reasoning, push, PR, deployment, and cloud state are not observed by the six-operation boundary.
- Context inclusion, injection, opening, and later activity do not establish that memory caused or improved an edit.
- The viewer is read-only; graph-derived context is not agent input.

## Read the decision view

- **Review Brief:** attention, changed paths, bound tests, human intervention, handoff inclusion/exclusion, outcome, and unknowns.
- **Truth labels:** distinguish human attestation, simulated fixtures, policy, runtime observation, and server derivation in text and shape—not color alone.
- **Verified support path:** shows only explicit typed support; generic containment and unrelated branches are excluded.
- **Bubbles:** color means kind; capped size/line width mean observed **activity**, never importance, impact, or correctness.
- **Missing evidence:** says **not established by captured evidence**. Invalid evidence stops the view as `EVIDENCE_INVALID`.

## Truth matrix

| Driver | Proves | Does not prove |
|---|---|---|
| `verified-replay` | Checked-in event fixture materialized through v2 verification, explicit context opening/reference, and a hash-checked public decision view | Captured live work, human attestation, ADK, model, or new tests |
| `scripted-local` | Bounded protocol, real TTY branches, isolated retest, local-only approved result | Independent model behavior, ADK, Gemini, or memory efficacy |
| `adk-fake` | Real ADK Runner/session/tool routing with a fake model | Gemini, autonomous intelligence, or independent-agent quality |

## Troubleshooting

1. Run both commands from the repository root with Python 3.13 and `uv`.
2. Start with `verified-replay` if the host is not macOS.
3. On macOS, confirm `test -x /usr/bin/sandbox-exec` before a live driver.
4. Add `--no-open` to print the loopback URL without launching a browser.
5. Treat `EVIDENCE_INVALID` as terminal; do not continue from a partially trusted view.

Current truth: [`README.md`](README.md), [`IMPLEMENTATION_STATUS.md`](IMPLEMENTATION_STATUS.md), and [`contracts/product_proof.json`](contracts/product_proof.json). Historical plans are indexed in [`docs/HISTORY.md`](docs/HISTORY.md).
