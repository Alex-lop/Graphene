# Three consecutive rehearsals through the INTERACTIVE edit pause — 2026-08-25

Every recorded run before tonight — the three rehearsals and the timed run of
2026-08-24 — applied the plan edit with `--plan-edit COMMAND`, which never
touches the prompt a person types into. On camera there is no `--plan-edit`:
`graphene demo --live` prints the export path, blocks on

    Edit it, then press Enter to compile the revision:

and continues only when the person has edited the file and pressed Enter.
That branch had never run under live Gemini. These three runs take exactly
that branch: a scripted operator (`scripts/rehearse_interactive_edit.py`)
watches the demo's output over a pipe, waits for the prompt, applies the same
edit a rehearsal uses (`scripts/demo_plan_edit.py`, so it transforms the plan
the live planner actually returned), and writes a newline to the demo's stdin.
Everything after that newline is the demo's own code.

    scripts/rehearse_interactive_edit.py TRANSCRIPT "uv run --frozen python scripts/demo_plan_edit.py"

against live Gemini (Vertex AI, location `global`, `gemini-3.5-flash`) on the
materialized North Star target, with the environment block
`docs/DEMO_SCRIPT.md` prescribes, from commit `ea52645`. Tree state at the
time: `main` at `9b120d4` pushed and green in Actions (run 32840452721), plus
the four product-gaps commits and one docs commit, all verified locally.

| Run | Lines | Prompt appeared | Mission phase (`ELAPSED`) | Total | Revision 2 digest | Spend (`SPEND`, from receipts) | Exit |
|---|---|---|---|---|---|---|---|
| `interactive-run-1.txt` | 274 | 37.5 s | 00:48 | 89.9 s | `6fc6326822a3…` | $0.14 | 0 |
| `interactive-run-2.txt` | 271 | 25.7 s | 00:45 | 74.4 s | `7ac9b7922e78…` | $0.13 | 0 |
| `interactive-run-3.txt` | 256 | 21.7 s | 00:43 | 68.7 s | `dd1912010978…` | $0.12 | 0 |

Each transcript was checked for every beat, not only for exit 0: the plan
table (`Needs approval: plan v1`), one node's full contract (`NODE`), the
prompt itself (`Edit it, then press Enter`), revision 2 compiled (`That is
revision 2`), `VALID revision=2`, `PLAN DIFF`, `** SCOPE EXPANSION **`,
`Approving revision 2`, the dashboard first at `NEEDS APPROVAL` and then
`approved`, `↻ retrying` after the injected check fault, `attempt 2  fence 2`
beside the untouched sibling, `Result approved and isolated`, the generated
feature with a `[REDACTED]` note, and `why` naming the mission. All present in
all three, zero tracebacks, and three different revision-2 digests because
each run plans its own mission.

The transcripts are the demo's byte stream as written to a pipe (so the
console is 80 columns wide and long paths fold, exactly as in the 2026-08-24
captures) with a few `#driver` lines appended at the end by the operator
script, clearly marked, carrying the timings above. The `Total` column is the
driver's wall clock from `Popen` to exit; `Prompt appeared` is when the demo
blocked for the edit, and the edit plus Enter took about 0.2 s of that.

**What these prove.** The interactive edit beat runs live, end to end,
repeatably: the prompt path a person uses — export, block on `input()`, edit
the file, Enter — compiles the person's change into revision 2 with a new
digest, the old approval stops covering it, and the workers execute the
revision that was approved. The mechanism the camera will see is now
rehearsed 3/3, under live Gemini, through the same branch of the code.

**What they do not prove.** They are still not the film, and they are not a
person. The edit was applied by a script in 0.2 s; on camera it is a human
reading a YAML file, finding one node, adding two paths and saving — the
~40 s of headroom `docs/SHOT_LIST.md` budgets for that is still an estimate
nobody has timed. Approval is operator-delegated (`truth_kind:
server_derived`) under the pre-authorized bounded policy, not TTY-attested.
The check failure is injected by `--inject-check-fault` and stamped
`simulated_fixture`; it is not a real infrastructure failure. Nothing has
been recorded; `product_media` stays `not_proven_capture_pending`.

**One earlier attempt aborted and is kept, not counted.**
`interactive-run-0-aborted-by-driver.txt` (58 lines) is the first attempt: the
demo reached the prompt correctly, but the operator script failed to read the
export path because the console folds the long absolute path across three
lines, and the script killed the demo at 31.5 s before any worker started.
That is a defect in the rehearsal harness, not in the demo, fixed by re-joining
the folded path; the run cost about one planner call. It is preserved because
an operator script that could not see the path is the same failure shape as
every other check that cannot observe what it certifies.

Spend across the four attempts, from the dashboard's receipt-derived counter:
about $0.40. No 429 or quota signal appeared in any transcript.
