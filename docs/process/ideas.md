# Nemotron while the person shapes: 32 ideas, 20 after merging, ranked

Three judges scored each idea from 1 to 5 on the five criteria in the shaping directive. The columns are Fit (with Graphene), Judge (what a judge would see), Uniq (uniqueness against `field.md`), Cost, and Oct20 (can it be built and measured by 20 October). Each score is the mean over the three judges, and Total is the sum of the five means (at most 25). Where ideas merged, the surviving version is the best-scoring member, and the other members are listed in brackets. Ties are broken by Oct20.

| # | Idea [members] | One line | Fit | Judge | Uniq | Cost | Oct20 | Total |
|--:|---|---|--:|--:|--:|--:|--:|--:|
| 1 | Your words, accounted for [1] | Nano maps each clause of the paragraph to a leaf and puts the clauses no leaf carries in front of the person | 5.0 | 4.0 | 4.7 | 5.0 | 4.3 | **23.0** |
| 2 | Notes find their leaf [15] | a loose sentence the person types becomes a checked `node set` on the one leaf it constrains | 5.0 | 4.0 | 4.7 | 5.0 | 4.0 | **22.7** |
| 3 | Red first [25, 2] | every proposed check is run at HEAD in a sandbox fork before R: passes already, cannot run, or red | 5.0 | 3.3 | 4.0 | 4.7 | 5.0 | **22.0** |
| 4 | The repo answers first [11, 21, 27] | Nano answers the planner's questions from the code, and a quote Graphene checks keeps each answer off the board | 4.3 | 4.0 | 4.7 | 4.0 | 4.0 | 21.0 |
| 5 | A critic that brings the fix [29] | Super flags the pruned plan, and only fixes that pass validate, overlap and unreachable are shown | 4.3 | 3.7 | 3.3 | 4.7 | 4.3 | 20.3 |
| 6 | Read less [3] | routine leaves fold into one row on a 4-of-5 Nano vote, and the cursor opens where the person is needed | 4.3 | 3.3 | 4.0 | 4.7 | 4.0 | 20.3 |
| 7 | Where the planner disagrees with itself [28, 20] | the planner's final tree is sampled n=6 times, and each row shows its stability (2/6, 6/6) | 4.3 | 4.3 | 5.0 | 3.3 | 3.3 | 20.3 |
| 8 | Where Nano disagrees on a leaf [12] | five Nano samples of "how would you do it" per leaf: rows where they agree dim, rows where they split light up | 4.0 | 4.0 | 4.7 | 4.7 | 3.0 | 20.3 |
| 9 | Checks that bite [19, 10] | a Nano saboteur writes a wrong stub in a fork, and a check that passes it is marked weak | 4.7 | 4.0 | 4.0 | 3.7 | 3.7 | 20.0 |
| 10 | Questions first, answered mid-plan [4] | Nano raises the paragraph's open questions while Ultra reads, and the person's answers reach Ultra's next step | 4.0 | 4.0 | 5.0 | 4.0 | 3.0 | 20.0 |
| 11 | Prunes become rules you confirm [32, 6, 13] | Nano proposes standing rules drawn from what the person cut, and each binds only after `y` | 4.7 | 2.7 | 4.0 | 5.0 | 2.7 | 19.0 |
| 12 | Start at y, land at R [26] | an accepted leaf starts in a sandbox fork on the flex tier, and R lands it if its contract did not change | 4.0 | 5.0 | 3.7 | 3.0 | 2.3 | 18.0 |
| 13 | Prune memory [24] | the last prunes made in this repo are added to the planner's prompt, with no model call | 3.7 | 2.0 | 3.0 | 5.0 | 4.0 | 17.7 |
| 14 | Rehearsal: hand-backs before R [9, 18] | a step-capped Nano try per leaf surfaces `w widen` offers while the leaf is still proposed | 4.0 | 4.0 | 4.3 | 2.7 | 2.7 | 17.7 |
| 15 | Options, tried [30, 8] | the two ways to do a branch are each spiked in a fork and shown side by side, and the person picks | 3.7 | 4.3 | 2.7 | 4.0 | 2.7 | 17.3 |
| 16 | Speculate before accept [5, 17] | Nano works on leaves in forks while they are still being pruned | 3.0 | 5.0 | 3.7 | 3.0 | 2.0 | 16.7 |
| 17 | Consensus tree [14, 23] | branches where n=3 planner samples split become options, each with a spike | 3.7 | 4.0 | 3.7 | 3.0 | 2.0 | 16.3 |
| 18 | Shaping budget [22] | a spending cap orders the background work: prechecks, then answers, then probes | 3.3 | 2.3 | 2.3 | 5.0 | 3.0 | 16.0 |
| 19 | The bill before R [16, 7] | the expected dollars, minutes and landing odds for each leaf, from this repo's ledger | 3.3 | 3.0 | 2.3 | 5.0 | 2.0 | 15.7 |
| 20 | Two lanes [31] | the person's calls go through `-fast`, and background calls use flex with rate-limit pacing | 2.7 | 1.7 | 2.0 | 4.0 | 3.0 | 13.3 |

**Prototype tonight: 1, 2 and 3.** All three are behind one flag, `GRAPHENE_SHAPE`, and each is also a command. They read the plan after it has landed, so they work with every planner (Claude Code, Codex and Nemotron). Nano is their only model, and the deterministic stage of #3 needs no model at all.

**How the ideas were merged.** Taking the full transitive union of the judges' merge groups collapses the 32 ideas into 10 groups. That joins folding (#3) to options (#8) through #12 and #14. I split groups apart wherever the mechanism or the point of consent differs, as follows:
- The base-run precheck (2, 25) and the saboteur (10, 19) are separate ideas.
- Asking mid-plan (4) and answering after (11, 21, 27) are separate.
- Speculation after `y` (26) and speculation before accept (5, 17) are separate.
- Per-leaf spread (12) and tree stability (20, 28) are separate.
- Options that come from sample splits (14, 23) and options that come from the planner (8, 30) are separate.
- Prompt memory with no model (24) and rules the person confirms (6, 13, 32) are separate.
- The budget (22) and the lanes (31) are separate from the bill (7, 16).

## The top three

**1. Your words, accounted for** (`src/graphene_map/cover.py`).

- **How it works.** When a proposal lands, Nano gets the person's paragraph (the `asked` row that `graphene ask` already logs, or `--paragraph FILE`) and the plan's text. It returns `{clauses: [{text, leaf|null, nearest|null}]}`. Graphene keeps a clause only when its whitespace-normalised text is a substring of the paragraph, so a clause the model invents is dropped. A mapping to a leaf id that does not exist is reported as uncovered, because no real leaf was shown to carry that clause. Each uncovered clause becomes an `uncovered` row and one printed line: "You said 'an empty feed means nothing is loaded and the command exits cleanly'; no leaf carries it. Take it: `graphene node set xml-wiring --goal '…; an empty feed means…'`". The text added to the leaf is the person's own clause, verbatim, so no model-drafted text ever lands on a leaf.
- **Models and Token Factory.** One Nano chat call using `response_format: json_schema` and `reasoning_effort: low`, through `tokenfactory.chat` exactly as it is today.
- **What it targets.** The one recorded case of this failure: `feeds-dense-tree-1`'s proposed tree dropped line 17 of its own paragraph, and the person had to type it back (`docs/test/results-2026-09-23.md`, line 673). The tree arm re-typed 2,172 and 3,162 characters of its own constraints.
- **Two corrections the judges made to the original pitch.** The zero-price rule was never in any paragraph, so this idea cannot claim to have caught it. And `docs/test/trees/` holds only its README, so no `proposed.plan` exists in the repo yet.
- **Testing against the fake.** Script Nano's JSON, then check that one orphan writes one row, that an invented clause is dropped, that a non-JSON reply writes nothing, and that a dismissed clause is not flagged again.
- **Measuring live.** Use the paragraph and the proposed plan that the trees procedure leaves for each of the four tasks. A blind judge labels the dropped clauses once, and that labelling is the ground truth for recall and precision. Also count the typed characters that `attention.py` records, with the command and without it. Pre-register what counts as a clause before the live planner runs.
- **Cost.** About 3.5k tokens in and 0.8k out, roughly $0.0003 a plan at the fake's placeholder Nano price ($0.05 in and $0.20 out per million tokens). The live list prices it.

**2. Notes find their leaf** (`src/graphene_map/note.py`).

- **How it works.** The person types `graphene plan note "prices in that feed are already cents"` (`:plan note …` in watch). One Nano call gets the note together with every open or proposed leaf's contract (`P.contract`). A plan of 30 leaves fits in about 3k tokens, so no embeddings are needed; the judges agreed to drop them. It returns `{target: leaf-id | "new" | "none", scope_add, scope_remove, check, goal_add, why}`.
- **What Graphene checks before offering anything.**
  - The target must exist and not be done.
  - Each glob in `scope_add` must match a tracked file or fall under the leaf's current scope.
  - `scope_remove` must already be in the scope.
  - A new check passes `P.unreachable`.
- **What the person sees.** Only then is the note offered, as the exact command that makes the change (`graphene node set <id> --scope … --check …`, or `graphene node add …` for "new"), and it is logged as a `suggested` row on that leaf. The person takes it by running that command. So it goes through `P.edit`, and `plan undo` and `plan edit` round-trip it with no new state.
- **Models and Token Factory.** Nano with `json_schema`.
- **Testing against the fake.** A note routes to the right leaf of three. An invented leaf id is refused. A scope glob that matches nothing is refused. A "new" target prints a `node add` command. The request carries `response_format` and the Nano id.
- **Measuring live.** Routing accuracy on the corrections typed in the 20 to 23 September runs. Those runlogs sit outside the repo, and the committed runs JSON has no correction rows, so the set has to be recovered or built fresh. Also count the characters and person-seconds for a note followed by running its command, against an `e` edit of the same change.
- **Cost.** About 3k tokens in and 0.3k out, roughly $0.0002 a note at the placeholder price.

**3. Red first** (`src/graphene_map/precheck.py`).

- **How it works.** `graphene plan precheck [ids]` runs each leaf's check against the untouched commit. Identical commands run only once. The checks of proposed leaves are written by the planner, so they run only in a sandbox fork (`sandbox.check_in_fork` from the commit's checkpoint, on ConTree or the Docker stand-in) and never on the person's machine before `y`. A proposed leaf with no sandbox configured is marked "not run: needs a sandbox". An accepted leaf may use `P.run_check`, as `done` will.
- **Verdicts, before any model.**
  - Exit 0 means "passes already".
  - Exit 126 or 127, pytest's exits 4 and 5, "command not found" and "No module named" mean "cannot run".
  - Any other non-zero tail goes to Nano with `json_schema {verdict: red-right-reason | environment | typo | other, why}`. Only `red-right-reason` leaves the row unmarked.
- **Where the verdict goes.** It is a `precheck` row carrying the node's `rev`. A later edit makes the row stale, and it is not shown.
- **What it replaces.** It turns `plan.unreachable`'s guess from the check's text into a run, and it puts into the product step 5 of the trees procedure, which people currently do by hand.
- **Testing against the fake.** A scripted runner stands in for `check_in_fork`. `true` must come back as passing already, with no model call. `pytest tests/nope.py` must come back as cannot run, with no model call. A failing assertion must make exactly one Nano call. A proposed leaf with no sandbox must never reach `P.run_check`. A Docker end-to-end run is skipped where Docker does not run.
- **Measuring live.** The share of flagged checks on Nemotron-planned trees for the four tasks, compared with `score_tree.py`'s base-run verdicts, which must agree exactly on "passes already". Nano's verdicts against hand labels on about 40 red tails. Seconds per fork.
- **Cost.** One sandbox fork per distinct check, well inside `sandbox.CAP`; ConTree's price is not published in the docs that were read. About $0.0002 of Nano for each ambiguous tail, so under $0.002 for a 10-leaf plan.
- **The judges' objection.** The model's part here is thin; Sandboxes do the work. The Nano repair from idea #2 (drafted only for a flagged leaf, re-run at base, and offered only if it is red for the right reason) is the next step, once the verdicts hold up.

## Why not higher

- **Forking candidates** (15 Options, 17 Consensus): forking N ways and letting a score or a person choose is the most common pattern in this track (PortVerdict, PQC Factory, Arborist). Uniqueness averaged 2.7 to 3.7. Options may also be fewer than one per plan.
- **Speculation** (12, 16, 14): it has the best demo moment (Judge 5.0), but it pays in wall-clock time, not attention. It needs `--hold` surgery in `executor.py` and `run.py`, and live Sandboxes. #16 would spend money before the person consents, which breaks the keep-list's "before anything is spent". It should come after #3 and #6 exist.
- **The repo answers first** (4): this is the directive's own seed and the strongest runner-up. It waits on lane A's board and on planners emitting structured questions, and nobody has measured how many questions a plan raises. It should be the fourth prototype once the board exists.
- **Stability** (7): it scored highest on Uniq (5.0). Whether Token Factory honours `n` together with `json_schema` for Nemotron, and whether it bills the prompt once, is unverified. And `Y`, which accepts every 6/6 row at once, invites accepting rows without reading them.
- **The critic** (5): LLM plan reviewers are the least novel category (SwarmForge). It ranks this high only because every fix it offers is validated before it is shown.
- **Learning prunes** (11, 13): the 23 September runs recorded no drops and 7 edits, so there is almost nothing to learn from. The payoff also appears only on a second plan. By the ideas' own reading of the docs, fine-tuning lists no Nemotron base; this is unverified here.
- **The bill** (19, 18, 20): `field.md` forbids selling per-call pricing as distinctive. With no history by 20 October, every row would say "no history". The one finding worth taking now is a one-line bug: `tokenfactory._size` cannot see a `Lightning` model.
- **Batch**: its completion window is measured in hours, and a person pruning waits seconds.
