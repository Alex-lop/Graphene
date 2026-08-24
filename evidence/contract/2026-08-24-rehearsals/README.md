# Three consecutive rehearsals of the filmed sequence — 2026-08-24

The §9 non-negotiable: three consecutive end-to-end runs of the exact sequence
Alex films, logged before he films it. All three are unedited transcripts of

    graphene demo --live --plan-edit "uv run --frozen python scripts/demo_plan_edit.py"

against live Gemini on the materialized North Star target. All three exited 0
and none printed a traceback.

| Run | Lines | Revision 2 digest | Spend (from receipts) |
|---|---|---|---|
| `run-1.txt` | 258 | `0550c08c4e86…` | $0.12 |
| `run-2.txt` | 283 | `caeaace3e8c5…` | $0.11 |
| `run-3.txt` | 256 | `655e46456b48…` | $0.09 |

Each transcript was checked for every beat, not just for exit 0: the plan
table, one node's full contract, the edit being applied, revision 2 being
compiled, `lint` reporting `VALID revision=2`, the diff, the
`** SCOPE EXPANSION **` marker, approval of revision 2, the dashboard showing
first `NEEDS APPROVAL` and then `approved`, the isolated result, the generated
feature running with a redacted note, and `why` naming the mission. All
thirteen are present in all three runs, and the three revision-2 digests are
different, because each run plans its own mission.

**What these prove.** The edit beat runs live, end to end, repeatably: a user
changes the proposed graph, the change becomes an immutable revision with a
new digest, the old approval stops covering it, and the workers execute the
revision the user approved.

**What they do not prove.** They are not the film. The edit is applied by
`scripts/demo_plan_edit.py` rather than typed by a person — the same
revise/lint/diff/approve code path either way, but a rehearsal of the
mechanism, not of the performance. Approval is operator-delegated
(`server_derived`) under the pre-authorized bounded policy, not TTY-attested.
The check failure is injected by `--inject-check-fault` and stamped
`simulated_fixture`; it is not a real infrastructure failure.

**Two earlier attempts failed and are not counted.** They found the two demo
defects fixed in `c758837` — the plan export dying on a symlinked temp
directory before the edit beat, and a `MissionProjectionError` reaching the
screen as a traceback. The three runs above are the first three after that fix,
consecutive, with nothing in between.
