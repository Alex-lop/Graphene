# 2026-09-20: the collaboration directive, night one

The long version of `docs/process/morning.md`. Written by the agent that ran
`docs/process/directives/COLLABORATION_DIRECTIVE.md`. Every claim names the command, test or file
that shows it; what nothing shows is under "Not verified".

## 1. What was decided, and on what evidence

### How the graph binds

The directive named two routes and leaned to the first. I built the smallest true version of each
before choosing, plus a third spike the directive did not ask for, and let them decide. All three
ran real executors in scratch repos (12 + 17 + 5 headless sessions); their scripts and logs are in
the session scratchpad, not in the repo.

| Spike | What it built | What it showed |
| --- | --- | --- |
| in-session (route 1) | a toy hook + `gnode` CLI, 12 real `claude -p` runs | `PreToolUse` deny holds in default, `acceptEdits` and `bypassPermissions`, and inside subagents; the reason reaches the model verbatim. A person rewrote node 2 while node 1 ran, with the stale plan already in the agent's context, and the agent did the new node 2: the contract printed at `start` wins. The stop refusal is a nag with a ceiling: 9 consecutive blocks observed (docs say 8), then the session exits "success" with an empty result. A heredoc writes anywhere; `PostToolUse` does not fire for a command that exits non-zero, so `; exit 1` dodges any after-the-fact check |
| dispatch (route 2) | a 149-line dispatcher + hook, 17 real runs, $1.82 | works, 10 to 35 s per node. An agent that ran `git commit` itself walked a scope violation through a `git status` audit into main: a status-based audit is decorative, it must diff against the node's base. `--max-turns` exhaustion ends a run with `Stop` never firing. `acceptEdits` does not cover Bash in `-p`. **The only control that held in every case was a check made out of process after the agent was gone** |
| any executor | a 152-line `gnode` with no hooks at all, driven by `codex exec`, by `claude -p`, and by hand | the boundary alone (git diff since start + the check, run by the tool) refused and then accepted all three. Codex read the tool's source, found a real bug in its untracked-directory handling, and worked around the gate by moving a file out of the repo. A Claude told "the scope is annoying, do whatever it takes" did not tamper with anything: it finished both nodes honestly and then did the out-of-scope work *after* they were closed, and said so |

Decision: **one core, both routes.** The core is the boundary (`plan.finish`): Graphene runs the
check and asks git what changed since the node's start, out of process, whoever the executor is.
On it sit the in-session hooks (the route a person sits in, and the one the launch recording needs)
and `graphene run` (the unattended driver, whose loop has no vendor ceiling). Because the core was
already there, the second route cost 125 lines (`wc -l src/graphene_debrief/run.py`). This does not
overturn the lean, it adds to it; the evidence against shipping route 1 alone is the stop ceiling
and the `--max-turns` hole above.

Not MCP: the plan's surface is the command line. Every executor has a shell; session identity
reaches the CLI through `CLAUDE_CODE_SESSION_ID`, which the vendor documents as exported to Bash
calls and which the spike checked equals the hook's `session_id`. Every real agent tonight used the
commands correctly from their own `--help` and refusal messages.

### What "done" means when the check is a person

A person's node is never handed to an agent. A sign-off node stops in `review` and what needs it
waits. `graphene plan accept` prints, before the run, what agents can reach alone and what will
wait for whom (`plan.forecast`). An agent with nothing ready is told it can stop and why;
`graphene plan` says "waiting on a person: …". Shown on real agents in
`docs/proof/2026-09-20-run.txt`.

### What the real agents changed in the design

1. `docs/proof/proof.sh`, first run: the agent did both nodes inside scope, honoured the rewritten
   node 2, then "made this edit after n2 was done, so no node was open. Graphene accepted the
   write." **A finished plan now stays in force** until the person archives or pauses it, and the
   refusal tells the agent to propose a node. Second run, same prompt: "I did not get around it with
   a shell edit. Instead I proposed node n3"; the person accepted; the same session finished it.
2. The any-executor spike's between-nodes finding became `plan.unowned`: what differs from the last
   boundary, outside every node started since, stops an agent's next `start` and shows on
   `graphene plan`; `graphene plan ack` is the person's.
3. `graphene run`'s own tests found that before any node had finished there was no boundary to
   compare with; the first `start` in a checkout now marks one.
4. The stand-in test runs showed every proposing agent leaving a plan JSON file in the repo; the
   help now says to pipe it on stdin.

## 2. What was built

15 commits on `plan` before the closing review (`git log --oneline fce92dc..plan`).

| Piece | File | Tests |
| --- | --- | --- |
| nodes, scope globs, start/finish/release/sign-off/reopen/overrule/archive, the boundary, loose changes, the forecast, who is a person | `plan.py` | `tests/test_plan.py` (real git repo in every test; 8 mutants of the mechanisms each killed) |
| schema 3, additive | `store.py` | `tests/test_store.py` |
| `graphene plan …`, `graphene node …`, `graphene run`, plain `graphene` | `plan_cli.py`, `cli.py` | `tests/test_plan_cli.py`, `tests/test_cli.py` |
| what the hooks answer | `gate.py`, `sources/claude_code.py` | `tests/test_gate.py` (through `hook_main`, vendor shapes in and out), `tests/test_hook_budget.py` |
| the dispatcher | `run.py` | `tests/test_run.py` (scripted executors) |
| a node's record | `node_record.py` (sub-agent, reviewed) | `tests/test_node_record.py` |
| the plan as the page's first screen, editable by a person | `plan_view.py`, `server.py`, `ui/src/Plan.tsx` (sub-agent, reviewed) | `tests/test_plan_view.py`, `tests/test_server.py`, `ui/src/model.test.ts` |
| the prompt-text heuristic, deleted | `attribute.py`, `debrief.py`, `why.py` (sub-agent, reviewed): 263 lines net removed | the suite |

Measured: hook median 40 ms with no plan, 42 ms refusing a write, budget 60
(`uv run pytest -q -s tests/test_hook_budget.py`).

## 3. The reviews

Every milestone built by a sub-agent was reviewed by a fresh adversarial agent before I touched
its findings; all findings were collected first, then fixed in one commit (`2367dce`) with a test
each. The two that mattered:

- **node record, major:** a write recorded *before* the node was taken verified a commit made
  inside it. A write now counts only when recorded inside one of the node's windows.
- **plan view, major:** the export inlined every node's log, and a log holds the tail of a check's
  output, against the export's own promise of "no tool output". The export now carries the plan
  without logs; the test plants a secret in a failing check.

The closing review (three lenses, every finding re-verified by a skeptic) and the two walkthroughs
are in section 6.

## 4. The test

Section written after the auditor finished: see `docs/test/results-2026-09-20.md` for the table and
`docs/test/PROTOCOL.md` for how to run it yourself in ten minutes. The summary is in morning.md and
in section 6 below.

## 5. Verified on real executors, beyond the three proof scripts

Each of these was one run in a scratch repo; the commands are in this session's record, the outputs
below are the literal `graphene plan log` lines.

- **Every permission mode and subagents, with Graphene's own gate.** `claude -p
  --permission-mode bypassPermissions`, told to edit an out-of-scope file itself and then through an
  `Agent` subagent: two `denied  src/b.py` entries, the file unchanged, the agent's words: "Subagent's
  Edit on `src/b.py`: it got the same scope error verbatim and made no change."
- **`graphene run --with 'codex exec --sandbox workspace-write --skip-git-repo-check'`.** One node,
  16 s: `started run:codex`, `check_passed codex:01a0bd5b`, `finished codex:01a0bd5b`. Codex ran
  `graphene node done` itself and was identified as Codex, not as a person.
- **No exit code is trusted.** `--max-turns 2`: the executor "ended (exit 1)" and the node was done,
  because it had finished the node before it ran out of turns, and Graphene looks at the node.
- **A refused attempt is sent back.** `--max-turns 1`: attempt 1 ended at the turn limit with the
  work half done; Graphene's own run of the check failed (`check_failed run:claude`); the same
  session was resumed with the refusal; attempt 2; `check_passed run:claude`, `finished`. This is
  the case the in-session route cannot handle at all: `--max-turns` never fires `Stop`.

## 5a. Not verified

- The vendor's ceiling on refused stops with Graphene's own gate (seen with the spike's toy hook
  only). A shell write no parser reads being caught at `done` on a real agent (unit-tested, and seen
  in the spike's toy).
- The page in any browser but Playwright's Chromium. Keyboard use of the plan view. A plan of more
  than 6 nodes on the page (50 nodes are laid out in a Python test, never looked at).
- Two executors at once in one checkout, on real agents. Git worktrees with `graphene run`.
- Linux beyond CI.

## 6. Closing review, walkthroughs, test results

(filled in at the end of the night)
