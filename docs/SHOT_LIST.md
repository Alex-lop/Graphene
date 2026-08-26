# Shot list — the one-take run

Beat by beat: what you type, what the camera sees, how long it took when it was
measured, and what each beat is and is not proof of. The narration is in
[`docs/DEMO_SCRIPT.md`](DEMO_SCRIPT.md); this file is the timing and the frames.

Everything quoted below is from one run:
[`evidence/contract/2026-08-24-rehearsals/timed-run.txt`](../evidence/contract/2026-08-24-rehearsals/timed-run.txt),
266 lines, `graphene demo --live` against live Gemini on 2026-08-24, exit 0.

## Read this before you trust a number on this page

**Only the mission phase was machine-timed.** The transcript carries eleven
dashboard frames stamped `ELAPSED 00:00` through `ELAPSED 00:47`, and those
cover approval through `awaiting_result` and nothing else. Every beat before the
dashboard opens (materialize, trigger, plan table, node contract, export, edit,
lint, diff, approve) and every beat after it closes (result, feature, `why`) has
**no counter in the capture**. The 77-second total and the ~30 seconds around
the mission are an operator's stopwatch, recorded at
[`evidence/contract/2026-08-24-rehearsals/README.md`](../evidence/contract/2026-08-24-rehearsals/README.md)
lines 32–35. They are honest, they are just not machine-recorded, and a shot
list that presented them as transcript timings would be inventing precision.

So: **1:17 total, of which 0:47 is measured by the tool and ~0:30 is measured by
a person.** Against the ≤2:00 target that leaves about **40 seconds of
headroom**, and §"Where the headroom goes" below is the only place it can be
spent.

**Quoting convention.** The transcript is hard-wrapped at 80 columns, so table
rows and long lines are split across physical lines in the file. Frames below are
re-joined to how they look on a wide terminal. Nothing else is changed. Digests
print truncated to 12 hex characters followed by a real ellipsis character (`…`,
U+2026), not three periods — match that if you retype anything.

**The one thing that must stay on screen.** The twelve characters
`b43792bf3f72` appear in eight places between the edit and `why`. That repetition
*is* the film's argument — the workers obeyed the graph you approved, and you can
see the same digest on the plan you signed and on the provenance at the end. A
cut that loses those frames loses the claim.

---

## Three new shots — added 2026-08-26, after `graphene ui` and the MCP loop landed

The sequence below is unchanged; these three sit around it. Every timing on
this page that is not a transcript counter is labelled; these are no different.

### 0 — Cold start · separate shot, ~30 s real time, speed-up must be labelled · **VERIFIED IN A CONTAINER, NOT FILMED**

A fresh terminal, nothing installed but `git` and `uv`. Type the three
README lines and nothing else:

```bash
git clone https://github.com/Alex-lop/Graphene.git && cd Graphene
uv sync --frozen
uv run --frozen graphene mission replay taskmaster
```

Measured on 2026-08-26 in a fresh `python:3.13-slim` container: `uv sync
--frozen` took **2 s** after the clone; the replay printed its truth label and
served Mission Control until a 60 s timeout stopped it (a container has no
browser to close it). On a laptop the clone dominates; if you speed the shot
up, say so on screen. This shot is proof of the door, not of the product — cut
to it, do not narrate over it.

### 16 — The `/graphene` loop with the map in a split pane · the centerpiece · **MECHANISM LIVE ON THE FIXTURE 1/1 (2026-08-26); NOT YET UNDER LIVE GEMINI; NOT FILMED**

Left pane, Claude Code with this clone open (it offers the `graphene` server
from `.mcp.json`; approve it once). Right pane, before you type anything:

```bash
uv run --frozen graphene ui
```

It says `no active mission` until the plan exists — that is correct, not a
bug; start it after step 1 if you want a clean first frame. Then, left pane:

```
/mcp__graphene__goal Add redacted JSON and Markdown status reports to the fixture CLI.
```

What the camera must catch, in order — every one of these is in
[`evidence/integration/2026-08-26/transcript.md`](../evidence/integration/2026-08-26/transcript.md),
where the client was the official MCP client and the signer was a script:

1. The agent calls `plan_goal` and prints the map: mission id, `base_sha`,
   **the digest**, six nodes with dependencies. Right pane: the DAG appears,
   banner `UNSIGNED — nothing runs until you sign`.
2. The agent **stops and asks you to sign.** This is the beat. Nothing is
   running; the right pane is still and unsigned.
3. You type the digest. The agent calls `approve_plan` with what you typed.
   (If you mistype one character the store refuses — `plan approval digest
   does not match the committed revision` — and the agent asks again. On the
   fixture that refusal was rehearsed deliberately; it is a good frame if you
   want one.)
4. Right pane: banner flips to `SIGNED — revision 1 approved`, nodes go
   `queued → ready → running → done`, `render_markdown` shows `↻ retrying`
   once — the injected check fault — then `done`; `verify_candidate` shows
   `? verifying` then `done`; the status line reaches `awaiting_result`.
   Sixteen distinct frames on the fixture, about seven seconds.
5. The agent relays `mission_summary`: goal, every node's outcome, artifacts
   touched, result state, one receipts line. Press `s` in the right pane and
   the same summary is on screen, from the same store.

Not proven and say so if asked: a person has not yet signed inside Claude
Code on this machine (the E2E signer is a script, `claude mcp list` proves
discovery of the server and nothing more); this loop has not run under live
Gemini with the map attached — the credentials were not present in the
session that built it. Live it would be the same beats with a 47 s mission
phase instead of seven.

### 17 — Summary and `why`, the closer · untimed · **MECHANISM LIVE ON THE FIXTURE 1/1**

Right pane: press `enter` on `render_markdown` (`j`/`k` to move). The why
pane shows attempt #1 `failed · check_failed`, attempt #2
`committed · passed_after_retry`, the checks, the receipts, and — when the
store is attached, as it is here — the lineage stages. Left pane, ask the
agent *why* one of the touched files looks the way it does; it calls `why`
and relays `matched_by=path` with the stages, `prior_attempts` naming the
failed attempt and its fence. Then `q`: the terminal comes back clean.

The digest that appears on the plan you signed, in the banner the whole time,
and in `why` at the end is the film's argument, exactly as beat 15 says below.

---

## Beats

### 1 — A change arrives · untimed · **LIVE**

You type, once, and then do not touch the keyboard again until beat 4:

```bash
uv run --frozen graphene demo --live
```

Camera:

```
Materializing the North Star target repository...
Target ready at /private/var/folders/.../target on base commit 1e9ad2c5f55a; its own suite is green before we start.
Preflight is clean: git, the check executor, and the Gemini configuration are ready.
A change arrived in the inbox (sha256 af369202407c); mission mission_start_f6c93854be1471e294aa7aab was proposed from it.
```

The real temp path is long and absolute. `docs/DEMO_GUIDE.md` line 62 says
captures should exclude absolute paths; this sequence prints one. Either frame it
out or accept it, but decide before you record rather than in the edit.

### 2 — The bounded plan, v1 · untimed · **LIVE**

Camera — the plan table, four nodes, the whole graph on one screen:

```
Mission: mission_start_f6c93854be1471e294aa7aab      Base: 1e9ad2c5f55a      Plan: v1 / sha256:d0087ae02328…

ID                         STATE   DEPS                                             ROLE       READ/WRITE  CHECKS
assemble                   queued  implement_report_json,implement_report_markdown  assembler  7 / 0       1
implement_report_json      queued  -                                                worker     3 / 2       1
implement_report_markdown  queued  -                                                worker     3 / 2       1
verify                     queued  assemble                                         verifier   7 / 0       1

Critical path: implement_report_markdown → assemble → verify
Frontier on approval: implement_report_json, implement_report_markdown
Needs approval: plan v1
```

`Needs approval: plan v1` is the beat's point: a proposal, stopped.

### 3 — One node, in full · untimed · **LIVE**

Camera — 22 lines print; these are the ones to hold on:

```
NODE implement_report_json  work  state=queued
  read scope       ledger_service/report_base.py, tests/conftest.py, tests/test_report_contract.py
  write scope      ledger_service/report_json.py, tests/test_report_json.py
  allowed commands fixture-tests
  acceptance       fixture-tests
  attempts         0 of 3
  bound to         mission mission_start_f6c93854be1471e294aa7aab base 1e9ad2c5f55a plan v1 sha256:d0087ae02328…
  mission budget   900s worker time, 16 attempts, 10485760 artifact bytes
```

### 4 — You change the route · untimed · **MECHANISM LIVE 7/7, THE PERSON NOT TIMED — see below**

Camera, in the measured run:

```
The plan is yours to change. It is exported to /private/var/folders/.../mission_start_f6c93854be1471e294aa7aab-plan-v1.yaml.
Applying the prepared edit: uv run --frozen python scripts/demo_plan_edit.py
  edited implement_report_json: read scope gained ledger_service/report_markdown.py, tests/test_report_markdown.py
That is revision 2, digest b43792bf3f72… — a different graph, so the old approval no longer covers it.
```

**This is the beat no rehearsal can fully cover.** The four recorded runs of
2026-08-24 — three rehearsals and the timed run — passed
`--plan-edit "uv run --frozen python scripts/demo_plan_edit.py"`, so the line on
screen there is `Applying the prepared edit: …`. On camera there is no such
line. `demo --live` instead prints a prompt and waits:

```
Edit it, then press Enter to compile the revision:
```

On 2026-08-25 three consecutive runs took exactly that branch
([`evidence/contract/2026-08-25-rehearsals/`](../evidence/contract/2026-08-25-rehearsals/README.md)):
the demo printed the prompt, a scripted operator (`scripts/rehearse_interactive_edit.py`)
edited the export and pressed Enter, and everything after ran the same revise →
lint → diff → approve code — exit 0, 3/3, every beat present. So the *mechanism*
is rehearsed 7/7 and the interactive *branch* 3/3. The *performance* — a person
reading the YAML, finding the node, typing two paths, saving — is rehearsed 0/7
and its duration is unmeasured. Two ways this beat kills a take, both worth
practising against:

- **Save without changing anything** and the demo stops:
  `The plan was not changed, so there is no revision to approve.`
- **Make an edit that does not lint** and it stops:
  `The revision did not pass lint; nothing was approved.`

The edit itself is one change: give `implement_report_json` read access to the
two files `implement_report_markdown` owns. Know the two filenames cold before
you sit down, because the exported YAML is the plan the live planner returned on
the day and you cannot memorise its layout in advance.

### 5 — Lint · untimed · **LIVE**

Camera — the verdict line, then four criteria:

```
PLAN mission_start_f6c93854be1471e294aa7aab VALID revision=2
CRITERION criterion-403b869bdad7900051b49261 producers=implement_report_markdown verifier=verify:fixture-tests
CRITERION criterion-d8c6095a1fcefd4e9bafab64 producers=implement_report_json verifier=verify:fixture-tests
```

### 6 — Diff, and the scope expansion · untimed · **LIVE**

Camera — the money frame:

```
PLAN DIFF mission_start_f6c93854be1471e294aa7aab v1 -> v2
  from sha256:d0087ae02328… to sha256:b43792bf3f72…
  ~ NODE implement_report_json changed
    field read_paths: +ledger_service/report_markdown.py, +tests/test_report_markdown.py  ** SCOPE EXPANSION **
```

`** SCOPE EXPANSION **` is the marker the whole plan surface exists to print. In
the file it lands on a wrapped continuation line, two spaces after the second
`+path` — on a narrow terminal it will not share a line with `field read_paths`.
Check your terminal width before recording if you want it on one line.

### 7 — Approval of an exact revision · untimed · **LIVE, but delegated**

Camera:

```
  approve this revision: graphene plan approve mission_start_f6c93854be1471e294aa7aab --revision 2
Approving revision 2 — this demo runs under a pre-authorized bounded policy — and starting the mission now.
```

**Say the label out loud.** This approval is operator-delegated
(`truth_kind: server_derived`) under a pre-authorized bounded policy — that is
what keeps the take continuous. It is **not** TTY human attestation, and
human-attested approval on a live mission is still an open blocker in
[`contracts/product_proof.json`](../contracts/product_proof.json) (`north_star.blockers`).

### 8 — The dashboard opens · `ELAPSED 00:00` → `00:02` · **LIVE**

Three frames, about 2 seconds. `NEEDS APPROVAL` flips to `approved`, then both
workers start:

```
GOAL Add a redacted JSON status rep~ | STATUS proposed | ELAPSED 00:00 | SPEND —
PLAN v2 sha256:b43792bf3f72… NEEDS APPROVAL | FRONTIER —
Latest: trigger received
```

```
PLAN v2 sha256:b43792bf3f72… approved | FRONTIER —
Latest: plan approved
```

```
GOAL Add a redacted JSON status repo~ | STATUS running | ELAPSED 00:02 | SPEND —
implement_report_json      ● running   attempt 1  fence 1
implement_report_markdown  ● running   attempt 1  fence 1
Latest: worker started
```

The `GOAL` string is truncated with `~`, and **the truncation point moves between
frames** as the `SPEND` column widens from `—` to `$0.03` to `$0.11`. That is
normal. Do not try to cut frames on a matching goal line.

### 9 — The failure · `ELAPSED 00:17` · 15 s after the workers start · **LIVE run, INJECTED fault**

Camera:

```
GOAL Add a redacted JSON status ~ | STATUS running | ELAPSED 00:17 | SPEND $0.03
implement_report_json      ↻ retrying  attempt 1  fence 1
implement_report_markdown  ● running   attempt 1  fence 1
Latest: check failed → retry authorized with diagnostic
```

First frame where `SPEND` is non-zero — real provider receipts, `$0.03`.

**Never say "the Gemini worker died."** The failure is injected by
`--inject-check-fault`, fails the first trusted check exactly once, and is
stamped `simulated_fixture` in evidence. It is not an infrastructure failure. The
real-process variant is the night's SIGKILL laboratory, which is a separate and
narrower claim.

### 10 — The retry learns · `ELAPSED 00:28` → `00:29` · 11 s later · **LIVE**

The single most quotable frame in the run — a fence escalation beside an
untouched sibling:

```
GOAL Add a redacted JSON status ~ | STATUS running | ELAPSED 00:29 | SPEND $0.08
implement_report_json      ● running   attempt 2  fence 2
implement_report_markdown  ✓ accepted  attempt 1  fence 1
Latest: worker started
```

`attempt 2  fence 2` next to `✓ accepted  attempt 1  fence 1`: the failure was
bounded to one node and the retry ran under a strictly higher fence. Hold this
frame.

### 11 — Assemble, then verify · `ELAPSED 00:44` → `00:46` · 15 s · **LIVE**

```
GOAL Add a redacted JSON status ~ | STATUS running | ELAPSED 00:44 | SPEND $0.11
assemble                   ● running   attempt 1  fence 1  needs implement_report_json,implement_report_markdown
implement_report_json      ✓ accepted  attempt 2  fence 2
implement_report_markdown  ✓ accepted  attempt 1  fence 1
verify                     ○ queued    attempt —  fence —  needs assemble
```

`SPEND` reaches `$0.11` at 00:44 and never moves again: assembly and verification
are deterministic and cost nothing.

### 12 — `awaiting_result` · `ELAPSED 00:47` · **LIVE — last counter in the capture**

```
GOAL Add a redacted JSON~ | STATUS awaiting_result | ELAPSED 00:47 | SPEND $0.11
verify                     ✓ accepted  attempt 1  fence 1  needs assemble
Result: The final candidate and verification evidence are being bound into an exact review bundle.
```

### 13 — The fault is named, the result is isolated · untimed · **LIVE**

```
The injected check fault fired: one check failed on purpose and a bounded retry was authorized with a diagnostic.
Result approved and isolated: commit 687cab89f639 on refs/graphene/results/0022227589fd8d8739ae58e4; nothing was pushed anywhere.
```

The tool says "on purpose" itself. Let it.

### 14 — The feature runs · untimed · **LIVE**

```
The generated feature, run from the isolated result commit:
  | sku | name | unit | quantity | reorder_level | below_reorder | notes |
  | --- | --- | --- | --- | --- | --- | --- |
  | BOLT-M8 | M8 bolt | each | 60 | 70 | True | shipped; ask [REDACTED] |
  | NUT-M8 | M8 nut | each | 25 | 0 | False |  |
```

Two of the three details `docs/DEMO_SCRIPT.md` promises are visible: `[REDACTED]`
in the BOLT-M8 note, and `below_reorder = True` on the item under its reorder
level. **The third is not.** The script's 2:15 beat promises "a pipe escaped
inside a cell"; no escaped pipe appears in this run's output. Do not say that
line over this frame.

### 15 — `why` · untimed, and the longest beat at 68 lines · **LIVE**

```
And why did ledger_service/report_json.py change? The mission can answer:
WHY mission_start_f6c93854be1471e294aa7aab ledger_service/report_json.py matched_by=path
PLAN v2 sha256:b43792bf3f72… approved
```

`b43792bf3f72…` one last time, in the provenance, which is the shot the whole
film has been building. Then eight stages. Two carry the argument:

```
STAGE prior_attempts established
  node attempt attempt_fa7b5af4b94c0289aec944d009d7b6ea kind=none task=implement_report_json
    worker=gemini-worker-1 attempt_number=1 fence=1 state=failed result_code=acceptance_check_failed
  note Earlier attempts of the producing task ended without an accepted publication; the producer above ran under a strictly higher fence.
```

```
STAGE accepted_inputs not_present
  events none
  note Producer attempts declare no accepted inputs.
```

The second one is the more valuable frame of the two, and it is the one an editor
will want to cut: it is a stage that reports **absence**. `not_present`, `events
none`. That is what "where Graphene doesn't know, it says so" looks like, and it
is worth more than any green checkmark on screen.

Closing:

```
TRUST: every line above is derived from hash-chained mission events and resolvable evidence references; unknowns are listed, never guessed.
The story is complete: trigger, bounded plan, approval, execution, isolated result, working feature, and provenance.
```

---

## Where the headroom goes

| | Measured how | Time |
|---|---|---|
| Mission phase, approval → `awaiting_result` | Dashboard counters in the transcript | **0:47** |
| Everything else, with a **scripted** edit | Operator stopwatch, rehearsals README lines 32–35 | **~0:30** |
| Total, scripted | Operator stopwatch | **1:17** |
| §9 target | — | **≤ 2:00** |
| **Headroom** | | **~0:40** |

That 40 seconds has exactly one claimant: **beat 4, you typing the edit instead
of a script applying it.** Nothing else in the sequence is under your control —
the mission phase is the model's pace, and every other beat is print speed.

Which means the 1:17 does not transfer to the take. It is the floor. The take is
1:17 plus however long you take to open a YAML file, find one node, add two
paths, save, and press Enter. Forty seconds is enough for that and is not enough
for reading the file to work out what to change.

**Rehearse the edit, not the command.** The command has been rehearsed seven
times, three of them through the interactive prompt. A person's edit has been
rehearsed zero.

The headroom line above is **arithmetic, not measured**: no person typed the
edit in any recorded run, including the ones of 2026-08-26.

## Truth labels, one line each

| Beat | Label |
|---|---|
| 1, 2, 3, 5, 6, 8, 11, 12, 13, 14, 15 | **LIVE** — ran under live Gemini, 4/4 recorded runs, exit 0 |
| 4 (the edit) | **MECHANISM LIVE 7/7 (interactive prompt 3/3 on 2026-08-25), THE PERSON NOT TIMED 0/7** — the interactive pause has run live with a scripted operator; a human's typing time has never been measured |
| 7 (approval) | **LIVE, DELEGATED** — `truth_kind: server_derived` under a pre-authorized bounded policy; not TTY human attestation |
| 9 (the failure) | **LIVE RUN, INJECTED FAULT** — `--inject-check-fault`, stamped `simulated_fixture`; not an infrastructure failure |
| 0 (cold start) | **VERIFIED IN A CONTAINER** — `python:3.13-slim`, 2026-08-26; sync 2 s; not filmed |
| 16, 17 (the loop with the map, summary, why) | **MECHANISM LIVE ON THE FIXTURE 1/1** — official MCP client, scripted signer, `graphene ui` attached from a second process (`evidence/integration/2026-08-26/`); **NOT RUN under live Gemini with the map attached** — no credentials in the session that built it; **NOT FILMED** |
| The film | **NOT PROVEN** — `product_media` is `not_proven_capture_pending`; nothing has been recorded |

Cost, from evidence-bound receipts across four runs on 2026-08-24: **$0.09–$0.12
per run**. Three rehearsals plus a take is under $0.50.

## If you reuse a different transcript

The three rehearsal runs (`run-1.txt`, `run-2.txt`, `run-3.txt`) hit all thirteen
checked beats and are the same 80-column format, so this shot list transfers to
them with only the identifiers changing. It does **not** transfer with the
digests: each run plans its own mission against its own base commit, so all four
revision-2 digests differ (`0550c08c4e86…`, `caeaace3e8c5…`, `655e46456b48…`, and
this run's `b43792bf3f72…`). Only `timed-run.txt` is the measured one, and only
its digests belong in a frame labelled with 1:17.
