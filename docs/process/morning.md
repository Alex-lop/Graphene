# morning.md — 2026-10-02 — first light, the live half (practice)

## The brief

**Watch first**
- Nothing live yet. The best live take of rung 7 will be replayable here with no key once one has run.

**What ran live** — $0 of $10
- Nothing yet. The key in `~/.zshenv` expired at 23:27:06 on 1 Oct (ConTree's whoami), and the planning
  session had no `GRAPHENE_AGENT_LIVE_USD`. Sandboxes were granted to the project (import, list, spawn).

**New tonight**
- Your six 29 Sep commits that missed PR #34 are on `practice` (spend-cap guard, `key check`'s
  Sandboxes line, prereg rule 6's $10 cap, DIRECTION 132): `git log --oneline origin/main..practice`
- CI's flake, fixed at its root (main 1 failed in 30 under full load, the fix 30 of 30):
  `uv run pytest tests/test_tokenfactory.py -k "slow_child or 429"`

**Decide**
- None yet.

**Broken or risky**
- The live half waits on a new key in `~/.zshenv` and a session started with
  `GRAPHENE_AGENT_LIVE_USD=10 claude --continue`.

---

(Everything below the brief: what was decided, the evidence, and the state of the branch.
The first-light morning is `morning-2026-09-29.md`; tonight's plan is
`docs/process/directives/PRACTICE_PLAN.md`.)

## Rollback

Nothing on `main` changes tonight. The branch starts at origin/main `4e1660c`. To drop the night's work:
close its PR and `git push origin --delete practice`.

## What was done, in order

- **00:00** Worktree `~/graphene-practice-night` on `practice`, cut from origin/main `4e1660c`.
- **00:01** Cherry-picked `fee8b6b..5166edb` with `-x`: the six commits pushed to `first-light` after PR #34
  merged. One conflict: d45abf6's README hunk edits a paragraph the PR #37 README no longer has. The
  hunk was dropped, and that commit's message says so.
- **00:10** The carried commits' tests: 206 passed (test_key_cli, test_sandbox_contract, test_tokenfactory,
  test_init, docs/test/test_bench, test_arm_a, test_arm_bprime, test_doc_claims, test_tui), with the
  key, the project and the opening unset and the keychain off.
- **00:30** CI's flake (9c07c29). With the global `time.sleep` patched as the eleven tests did, a 0.2 s
  child's `subprocess.run(timeout=30)` recorded `[0.001, 0.002, 0.004, 0.008, 0.016, …]`, CI's list. With
  all 11 cores busy, main's two tests failed 1 run of 30 and the fix's passed 30 of 30. Both new tests fail
  on main (a throwaway worktree at 4e1660c). The seven touched files: 135 passed, 2 skipped.

## What I read before starting (23:22, 1 Oct; $0, nothing written)

- ConTree's whoami, from a first-light worktree's venv: `Sandboxes: work (import, list and spawn
  granted)`, and the key's `token_expiration` at 23:27:06 local, five minutes later.
- Sandboxes' price: none published. docs.tokenfactory.nebius.com/sandboxes/overview (read 2026-10-01)
  states only the beta's limits (50 concurrent operations). The night ledger counts Sandbox operations
  and minutes at $0, `price: unknown`. Tonight caps them at 150 minutes.
- CI on `main`: `test_precheck.py::test_a_failing_endpoint_is_tried_once_with_no_backoff_and_then_not_again`
  and `test_cover.py::test_a_failing_nano_is_asked_once_and_waits_for_nothing` failed 4 CI runs since 30 Sep
  (36944380283, 36944036307, 36729751766, 36682769735; 3 of the last 17 completed), each time one
  of the six test jobs, on branches that changed no product code. Eleven tests patch the global `time.sleep` through
  `tf.time`, and CPython's `Popen.wait(timeout=…)` polls with sleeps of 0.001, 0.002, 0.004 … 0.05, which is
  the list those failures recorded.

## Not on the machine's record

Your checkout's hooks (`graphene ingest hook`, your editable install at 041b93f) record every tool event
of this session in your git-ignored `.graphene/graphene.db`, as they do for every session there. Nothing
else of yours was written: no file in your checkout, and no git command there beyond `fetch` and
`worktree add`, which write only the shared `.git`.
