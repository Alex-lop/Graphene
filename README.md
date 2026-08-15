<p align="center">
  <img src="Graphene_main_img.png" alt="Graphene" width="720">
</p>

# Graphene

**Graphene is an evidence-backed review and handoff layer for a developer supervising bounded coding-agent work. It shows the captured edits, tests, human corrections, approved context, and explicit unknowns behind a candidate, then passes only approved evidence into the next run.**

- **Primary user:** a developer supervising or taking over a coding-agent change.
- **Painful moment:** deciding whether a candidate is trustworthy after a long run, correction, or handoff without reconstructing a transcript.
- **Decision:** approve, reject, or hand off that exact candidate and its bounded evidence.
- **Result:** a faster, more legible review with fewer unsupported changes, missed tests, and lost corrections.

The graph is a read-only decision surface, not the authority. Verified v2 events, private artifacts, policy, and terminal decisions remain authoritative.

## See it quickly: verified replay

```bash
uv sync --frozen
uv run --frozen graphene demo --driver verified-replay
```

This cross-platform path opens a checked-in public event fixture materialized through the v2 verifier and protected by a checked-in SHA-256 digest. It requires no macOS isolation, credentials, model dispatch, authoritative writes, human attestation, or new test execution. Terminal and viewer stay labeled:

> **VERIFIED REPLAY — NO LIVE AGENT, HUMAN ATTESTATION, OR NEW TEST EXECUTION**

## Run the interactive protocol

On macOS with Python 3.13, Git, `uv`, and executable `/usr/bin/sandbox-exec`:

```bash
uv run --frozen graphene demo --driver scripted-local
```

`scripted-local` is a deterministic **workflow fixture**, not independent-agent or Google ADK proof. It creates a private runtime, starts the authenticated loopback viewer, and pauses at real terminal branches for correction scope, memory approval/rejection, and candidate commit/rejection. Only an interactive TTY can create `human_attested`; automation is labeled `simulated_fixture` or fails closed. An approved final branch creates a verifiable Git commit only inside the retained isolated fixture checkout—never in the user's checkout, and never pushed.

Terminal and viewer stay labeled:

> **SCRIPTED LOCAL WORKFLOW FIXTURE — NOT INDEPENDENT-AGENT OR GOOGLE ADK PROOF**

The Google ADK integration proof uses the same bounded protocol:

```bash
uv run --frozen graphene demo --driver adk-fake
```

It uses the real Google ADK Runner, session, and Graphene tool routing with a deterministic fake model and zero external model calls. It is always labeled:

> **REAL ADK RUNNER + DETERMINISTIC FAKE MODEL — NOT GEMINI OR INDEPENDENT-AGENT PROOF**

There is no silent driver fallback.

## Immediate boundaries

- **Captured operations:** exactly `search_repo`, `read_file`, `open_evidence`, `write_file`, `run_fixed_test`, and zero-argument `request_completion` through the scoped v2 service.
- **Live execution:** only the sanitized Auth fixture on macOS with `/usr/bin/sandbox-exec`; Linux and Docker cannot run the v2 fixed-test workflow.
- **Negative proof:** the Billing handoff is denied before consumer construction and records zero model dispatch.
- **Privately captured:** authorized source/evidence bytes, bounded diffs, approved context, and bounded test output may exist in owner-private local artifacts.
- **Not publicly projected:** raw source, diffs, prompts/context text, test stdout, secrets, credentials, and private artifact bytes never enter the viewer or replay fixture.
- **Not observed:** arbitrary shell/editor activity, whole-repository activity, hidden reasoning, pushes, pull requests, deployments, and cloud state remain outside the six-operation boundary.
- **Causality:** Graphene verifies context compilation, inclusion, injection, opening/reference, and later actions; it does not claim approved context caused or improved an edit.
- **Deferred:** the viewer remains read-only. Graph-derived context is not fed back into an agent.

The machine-readable version of this current truth is [`contracts/product_proof.json`](contracts/product_proof.json).

## Review story

1. A deterministic source workflow fixture reads the bounded Auth files, makes an allowlisted edit, records a fixed-test receipt, and reaches a review gate.
2. A developer anchors a correction to captured evidence and chooses the broad or narrow frozen scope.
3. The developer approves or rejects one immutable memory revision. Rejection remains inspectable and does not create an approved-context claim.
4. Billing is denied with zero dispatch. An allowed Auth handoff compiles included and excluded evidence for a fresh isolated consumer runtime.
5. The consumer runtime explicitly opens/references allowed evidence, rereads source, performs bounded operations, and records a bound retest. The checked-in replay includes the explicit `open_evidence` relationship while remaining a fixture rather than a captured live run.
6. The developer rejects the candidate or explicitly chooses **Approve and create isolated local commit**. The approved result is local-only: no push, PR, deployment, or user-checkout mutation.

Delivery and ordering do not prove that context caused the later edit. The viewer renders explicit support, authorization, inclusion, and handoff relationships; it does not infer relevance, importance, correctness, or hidden causality.

## Driver proof matrix

| Driver | What it proves | What it does not prove |
|---|---|---|
| `verified-replay` | Checked-in event fixture materialized through v2 verification, hash-checked public projection, explicit context opening/reference, and the decision-view experience | Captured live execution, human attestation, ADK, Gemini, or new tests |
| `scripted-local` | Bounded v2 protocol, policy, real TTY choices, isolated retest, and approved isolated local Git result | Independent model behavior, ADK, Gemini, context efficacy, push, PR, or deployment |
| `adk-fake` | Real Google ADK Runner/session/tool routing with a deterministic fake model | Gemini, autonomous intelligence, independent-agent quality, push, PR, or deployment |
| Future external-live mode | Only behavior observed in a separately authorized, credentialed run | Any silent substitution by replay, fake, or scripted execution |

No real Gemini driver, provider-credential workflow, or cloud deployment is shipped.

## Decision surface

The first viewport leads with a deterministic Review Brief: current attention, changed paths, bound tests, human intervention and truth level, included/excluded handoff context, final outcome, and explicit unknowns. Each fact focuses its committed support. Missing facts render as **not established by captured evidence**.

The bounded Cytoscape canvas remains available for inspection:

- color encodes semantic kind, never correctness;
- size and line width encode capped observed **activity**, never importance or impact;
- non-color badges distinguish `human_attested`, `simulated_fixture`, policy, runtime, and server-derived truth;
- **Verified support path** excludes generic membership and unrelated denial branches;
- invalid evidence replaces normal state with `EVIDENCE_INVALID`.

## Architecture and authority

```text
scripted fixture / Google ADK fake / MCP
                  |
                  v
        ScopedApplicationService
                  |
                  v
 committed + verified v2 SQLite events ---> private artifacts
                  |
                  v
 deterministic public projection ---> authenticated loopback viewer
```

The current path is `graphene` / `graphene-mcp`, the v2 lineage services, and the read-only viewer. `contracts/golden_path.json` and `contracts/graph_mvp.json` are shared operational fixture inputs; their legacy three-tool, API, loop, catalog-framework, and graph fields are not current product, driver, runtime, or outcome truth. `backend/graphene/app.py`, the root `frontend/`, and the root `Dockerfile` are compatibility-only legacy surfaces. The Docker image starts the mutable legacy HTTP demo with a persistent compatibility banner; it is not authoritative v2 and does not provide Linux fixed-test support.

See the [documentation history index](docs/HISTORY.md), [privacy boundary](docs/data_residency.md), and [executor threat model](docs/EXECUTOR_THREAT_MODEL.md).

## CLI reference

The demo owns its runtime. Advanced commands use an absolute owner-private `GRAPHENE_LINEAGE_DB`; `--json` emits canonical JSON/NDJSON.

| Command | Purpose |
|---|---|
| `graphene demo --driver verified-replay` | Open the cross-platform verified public replay |
| `graphene demo --driver scripted-local` | Run the macOS deterministic workflow fixture and interactive review branches |
| `graphene demo --driver adk-fake` | Run the real ADK Runner with a deterministic fake model |
| `graphene run TASK --profile PROFILE` | Bootstrap or exactly replay one frozen v2 run |
| `graphene watch RUN [--after-seq N] [--snapshot]` | Follow a verified committed suffix |
| `graphene inspect EVIDENCE --run RUN` | Resolve an item authorized by that verified run |
| `graphene why PATH --run RUN` | Show explicit evidence relationships and unknowns |
| `graphene replay RUN --speed N` | Pace committed events without executing work |
| `graphene review RUN` | Derive bounded changeset, hunk, and test evidence |
| `graphene feedback HUNK --event EVENT --run RUN --message TEXT` | Anchor a private correction |
| `graphene answer QUESTION --choice CHOICE` | Record the bounded scope branch |
| `graphene memory approve|reject MEMORY` | Decide one immutable memory revision |
| `graphene handoff RUN --to PROFILE --task TASK [--start]` | Compile a denial or included-only handoff |
| `graphene promote CONSUMER_RUN --decision commit\|reject` | Record the explicit bounded final decision; commit creates only the isolated local result |

`graphene-mcp` is the official STDIO integration for the same six scoped operations. The [MCP client template](docs/mcp_client_config.example.json) and [redacted demo transcript](docs/demo_transcript.md) are advanced references. The legacy HTTP compatibility API uses `Authorization: Bearer <GRAPHENE_DEMO_TOKEN>` and must not be treated as v2 authority.

## Local verification

The checked-in workflow defines the exact gates; this README does not claim a hosted run for the current commit.

```bash
uv lock --check
uv sync --frozen
uv run --frozen pytest -q tests/unit tests/integration tests/process tests/adversarial --ignore=tests/process/test_mcp_stdio.py
uv run --frozen pytest -q tests/process/test_mcp_stdio.py
node --test frontend/test/*.test.mjs
node --test tests/frontend/*.mjs
node --check frontend/src/app.mjs frontend/src/graph.mjs frontend/src/workflow.mjs
node --check backend/graphene/viewer/static/reducer.mjs backend/graphene/viewer/static/viewer.mjs
git diff --check
```

Automated local gates pass; hosted Ubuntu CI, real-browser visual QA, and the five-person graph-necessity study are not claimed until they are actually run.

## Roadmap

- **Now:** prove evidence-backed review, bounded handoff, and local-only approval outcomes.
- **Next:** run the graph-necessity comparison with real unfamiliar developers; demote the graph if it does not reduce errors or time.
- **Then:** separately authorize and prove an external live-model path without fallback.
- **Later:** design equivalent Linux isolation and durable artifact retention only after evidence warrants them.

Graph-to-agent retrieval, graph-generated prompts, and automatic context selection remain explicitly deferred.

## Experimental pixel graph inside the terminal

**Feasibility: yes, but it is terminal-emulator-specific and is not shipped yet.** This would be a real raster bubble map, not an ANSI, ASCII, or Unicode-block diagram. Modern emulators can draw images through escape protocols:

| Transport | What it renders | Graphene role |
|---|---|---|
| [Kitty graphics protocol](https://sw.kovidgoyal.net/kitty/graphics-protocol/) | Arbitrary raster pixels with reusable placements, updates, deletion, pixel offsets, and a capability query | First experimental target |
| [iTerm2 inline images](https://iterm2.com/3.5/documentation-images.html), also supported by [WezTerm](https://wezterm.org/imgcat.html) | PNG or other raster images sized in cells or pixels | Secondary full-frame redraw path |
| [Sixel](https://invisible-island.net/xterm/ctlseqs/ctlseqs.html) | Bitmap graphics encoded in six-pixel vertical groups | Later fallback only; support varies |

The image protocol supplies pixels, not clickable graph objects. Graphene still has to own terminal input, selection, hit-testing, redraws, resize handling, and cleanup. A small controller script is enough for a feasibility spike; a one-line image command is not enough for interaction.

### Smallest credible prototype

1. Start replay-only and read-only. Consume the same verified public [`GraphSnapshot` and deltas](backend/graphene/viewer/contract.py) that feed the browser; never read private artifacts or create a second authority.
2. Reuse the existing pure [reducer and deterministic positions](backend/graphene/viewer/static/reducer.mjs), including capped activity-based bubble size and verified-support paths. Do not build another graph model or force-layout engine.
3. Render only the current-decision neighborhood to a raster frame and transmit it through Kitty graphics. If the capability query fails, open or print the existing browser viewer URL—there is deliberately no character-art fallback.
4. Own a small alternate-screen interaction loop: `←/→` changes replay checkpoint, `↑/↓` selects a bubble, `Enter` opens the same sanitized detail, `p` highlights verified support, `f` fits, and `q` restores the terminal and exits.
5. Add mouse selection only after keyboard navigation works. [SGR mouse reporting](https://invisible-island.net/xterm/ctlseqs/ctlseqs.html) can report cells, and mode `1016` can report pixels where supported; Graphene must map those coordinates back to bubble circles.

For the fastest visual probe, [Graphviz 9+ can emit Kitty graphics directly](https://graphviz.org/docs/outputs/kitty/) with `dot -Tkitty`. That proves pixel rendering from a script, but it is a static spike—not the product path—because it adds a system dependency and would otherwise duplicate Graphene's existing layout and interaction semantics.

### Ship gate

- one named terminal target first: Kitty without `tmux`;
- replay truth label remains visible and the public/private boundary is unchanged;
- selection and verified-support highlighting match the browser for the same snapshot;
- resize, interruption, and normal exit leave no image placement or terminal mode behind;
- a short judge test shows the terminal view answers at least one review question more clearly or quickly than the Review Brief.

Until that gate passes, the authenticated browser viewer remains the supported interactive bubble map. Do not add a cross-emulator abstraction, graph database, TUI framework, or ASCII fallback for a speculative demo.
