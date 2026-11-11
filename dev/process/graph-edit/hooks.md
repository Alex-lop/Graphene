# Do Graphene's hooks fire for every agent?

Run 2026-11-10/11 on Claude Code 2.1.322. Task: files `inside.txt`; the agent tries `outside.txt`.
Tests: `tests/test_every_agent.py` (hermetic, in CI). Probes: `dev/process/graph-edit/probes/` (live, Haiku).

| # | Agent | Answer | Proven by |
|---|-------|--------|-----------|
| 1 | Claude Code session (hooks from `graphene init`) | refused before the write | test rows 1-3; live probe p1: no file, `denied` row, `agent_id` null |
| 2 | its subagent (Agent tool) | refused before the write | test; live p2: `denied` row with `agent_id` a61c1a91..., same session_id as the parent |
| 3 | agent of a Workflow (`workflow-subagent`) | refused before the write | test; live p3: `denied` row with `agent_id` aa701fb8..., same session_id |
| 4 | Codex (`graphene run --with codex ...`) | caught at the finish | test with a stand-in `codex`; vendor docs below; no live Codex |
| 5 | any other command (`--with '...'`) | caught at the finish | test with a scripted stand-in |
| 6 | the editor's own agent (Cursor, Copilot), no Graphene launch | not held by Graphene's own code; vendors say their hooks may load ours (unverified) | test shows a plain write is not stopped; docs below |

## What the evidence says

- One session_id covers a session, its subagents and its workflow agents. The gate holds a task by session_id, so a
  child inherits the hold; `agent_id` only tells the log whose call it was. Rows 2 and 3 therefore needed no code.
- A Workflow cannot run headless without `--allowedTools Workflow` (without it: "Review dynamic workflow before
  running", no agent started). With it the agent ran and its Write was denied by the hook.
- Caught at the finish means the write lands: the stand-in's `outside.txt` is on disk after `graphene run` (serial,
  in the checkout); the task is handed back with the path named. In `--parallel` it lands in the leaf's worktree.
- A call under a session that holds nothing (what a workflow agent would be if it ever sent another session_id) is
  refused, not let through: fail closed (test `row_3_a_call_from_a_session_that_holds_nothing`).

## Holes

- Fixed (small): the plan-first and planner-read refusals logged a refusal with `agent_id` null, so a subagent's
  refused write on a session that held nothing did not say whose it was. Test first (failed), then 2 lines in `gate.py`.
- Not built (medium): hold Codex before the write. Codex has hooks (`<repo>/.codex/hooks.json`, PreToolUse fires for
  shell and `apply_patch`, can deny, project hooks load only when the `.codex/` layer is trusted and reviewed with
  `/hooks`; learn.chatgpt.com/docs/hooks). It would take: `init` writing that file, mapping Codex's payload
  (session id, `apply_patch` paths) to the gate, and `run` passing the hold a session id it can match. Unverified:
  Codex's real payload, never run here.
- Not built (needs a live test): Cursor and Copilot. Their docs say they load Claude Code hooks, including
  `.claude/settings.local.json` where `init` puts ours (cursor.com/docs/reference/third-party-hooks, on by default;
  code.visualstudio.com/docs/copilot/customization/hooks, preview). If so, a PreToolUse deny could stop their
  writes. Unverified: whether their payload carries `session_id` and `tool_input.file_path` as the gate reads them
  (the gate lets a Write with another field name through), and an editor session holds no task, so every write
  would be refused until a task is started for it. Holding it for real would also take a task-claim step in the
  editor. If the hook does not load: a watcher in the VS Code extension flagging a write outside every running
  task's files, or the finish check alone.

## Not proven

No live Codex, Cursor or Copilot call. Workflow agents with `isolation: 'worktree'` were tested only by payload.
The gate's known parser holes (HOW_IT_WORKS.md "Where each mechanism ends") are outside this question.
