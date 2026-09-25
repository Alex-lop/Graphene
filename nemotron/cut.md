# Item 9: the session-era modules, cut

Queue item 9, its first paragraph and the first step of its second. Every line below was checked
by a grep of `src/`, `tests/`, `docs/test/`, `docs/assets/`, `docs/proof/` and `docs/demo/` for
the name, and by asking which command a person or an agent types reaches it. Six commits on the
item's branch, each green on its own (the hook-budget exception is in its commit message), and a
seventh after review: the first version of this note said a subagent's task, closing words and
worktree come only from transcripts, and that was wrong (below).

## What was decided about the transcripts

Nothing reads Claude Code's transcripts any more (`~/.claude/projects/`).

- `graphene ui`, and the page it serves on every poll, called `backfill` on each open. Now they draw
  what the store holds: the plan, and the sessions the hooks recorded. They still ask git for those
  sessions' commits (`refresh_commits`). That is git, not transcripts, and the map and a node's
  coverage need it.
- `graphene ingest --backfill` (hidden) is deleted. `graphene ingest hook` stays: it is the live
  hooks, which hold Claude Code sessions to the plan.
- The page's record of a session, and a node's coverage grading, read the rows the hooks write while
  the session runs. No command still needed the transcripts. Every Claude Code session in a repo
  where `graphene init` ran is recorded live, and `graphene node show` and the record pane never
  topped up anyway.
- A subagent's task, prompt and spawn anchor are in the `Agent` call that spawned it, which names
  it in its response (`agentId`); its closing words are in its `SubagentHandback` call. The hooks
  record both calls, and the map reads them off (`graph._told_by_calls`), as the backfill's
  `_finish_agent` did. Its worktree is asked of git's own files when `SubagentStart` and
  `SubagentStop` arrive (`hooks.worktree_root`), so a command's list of changed files in a
  `.claude/worktrees/` worktree maps to the repo's file, drawn as a copy (`record.changes`).
  `tests/test_ingest_run.py` proves both from hook events alone.
- What is lost: a session run before `init`, or without the hooks, is not on the map. A subagent's
  Workflow group comes only from transcripts, so it is not added now. A store an earlier version
  filled keeps it, and the map still draws it.

## The map

| Piece | Where it is now | Why |
| --- | --- | --- |
| `attribute.py`: `bash_written_paths`, `shell_segments`, `check_segments`, `nested_checkout` and their helpers | moved, whole, to `shell.py` | the gate refuses writes with the first, `commits.py` reads `git commit` with the second, the map names checks with the third, the hooks' path mapping uses the fourth. The name was the attribution era's |
| `sources/claude_code.py`: the live hooks (`hook_main`, `ingest_hook_event`, `attach_file_content`, `_map_path`, `worktree_root`, `relative_path`, `git_head`, `install_hooks`, `hooks_file`, `hooks_installed`, `HOOK_EVENTS`, `_SLASH_COMMAND`, …) | moved to `hooks.py`; `sources/` is gone | `init` installs them, every Claude Code event runs them, the gate answers through them |
| `repo_root`, `_worktree_main` | moved to `store.py` (`repo_root`, `worktree_main`) | "which repository's store does this directory write to": the CLI, the hooks, and the Nemotron executor and planner ask it. The executor imported it from the Claude Code module |
| `_NOT_A_PROMPT` | moved to `gate.py` | only the gate reads it now (what the vendor sends as a prompt nobody typed) |
| the transcript backfill: `backfill`, `_backfill_one`, `parse_transcript`, `ParsedSession`, `BackfillReport`, `project_dirs`, `project_dir_name`, `default_projects_dir`, `transcripts_for`, `looked_in`, `worktree_transcripts`, `orphan_subagents`, `iter_records`, `subagent_files`, `transcript_cwd`, `is_prompt`, `_human_text`, `_text_of`, `_result_text`, `_prompt_before`, `_fold`, `_message`, `_meta_of`, `_journal_labels`, `_parse_agent`, `_finish_agent`, `_stat`, `JOURNAL`, `PROMPT_CAP` | deleted | only the transcript world |
| `Worktrees`, `_worktree_of`, `_in_history`, `is_within` | deleted | only the backfill (remembering worktrees that are gone). The hook never passed them |
| `cli.py`: `loaded_store`, `no_sessions`, `ingest --backfill/--transcript/--replace` | deleted; `nothing_to_draw` says the empty state in one line | the top-up and its command |
| `server.py`: the `backfill` call in `/api/graph` | deleted | the top-up |
| `store.py`: `transcript_stat`, `set_transcript_stat`, `delete_session_data` | deleted | only the backfill |
| `store.py`: `set_explanation`, `explanation`, `add_debrief_run`, `last_debrief_run`, `recent_paths`, `recorded_path_count`; `model.DebriefRun` | deleted | only the session card and `graphene why`, cut in 0.4 (decision 25 left them "for a follow-up") |
| `graph.py`: `parse_since`, `iso`, `select_sessions(since, now)` | deleted | only the `--since` option, removed in 0.4 |
| the tables `explanations`, `debrief_runs` and the sessions' `transcript_*` columns | kept in the schema | migrations only add. A store must still open, and `tests/test_store.py` pins them |
| `commits.py`: all of it (`window`, `sync_commits`, `credit`, `refresh_commits`, …) | kept | `node_record` asks git for a window's commits, and `ui` and the page credit commits to recorded calls. The map and the coverage grading read them |
| `record.py`: `changes`, `coverage`, `seconds`, `RANK`, `window_commits`, … | kept | `graph.py` and `node_record.py` grade paths with them. `seconds` is used across the package |
| `graph.py`: the rest (`build_graph`, `run_records`, `coverage_counts`, `select_sessions`, `to_json`) | kept | the page's map (`ui`, the demo export) and a node's coverage grading |
| `node_record.py`: all of it | kept | `graphene node show`, `plan record`, the record pane, the bill |
| `server.py`: the rest | kept | the page and `ui --export` |
| `store.py`: sessions, prompts, tool events, agents, commits | kept | the hooks write them; the map, the coverage and the executor's tail (`last_events`, `run` and `watch`) read them |

Tests deleted with what they tested: `test_backfill.py`, `test_scale.py`, `test_round_trip.py`; the
transcript sections of `test_ingest_run.py`, `test_run_fixture.py`, `test_cli.py` (the top-up) and
`test_store.py` (re-reading after a migration, `delete_session_data`, explanations and debrief
runs); `tests/fixtures/transcripts/`, `tests/fixtures/run/`, `make_transcript_fixture.py` and the
rendering half of `make_run_fixture.py`. The CLI tests of the map now record their session through
`hook_main`.

## Who imports whom, after

| Module | Imports (Graphene's own) |
| --- | --- |
| `cli` | `commits` `graph` `hooks` `plan` `plan_cli` `sandbox` `server` `store` `tokenfactory` |
| `hooks` | `gate` (only when there is something to decide) `model` `shell` `store` |
| `gate` | `hooks` (lazily) `plan` `shell` (lazily) |
| `store` | `model` |
| `commits` | `model` `record` `shell` `store` |
| `graph` | `model` `record` `shell` `store` |
| `record` | `model` |
| `node_record` | `commits` `graph` (lazily) `plan` `record` |
| `server` | `commits` `graph` `plan` `plan_view` `store` |
| `executor` | `gate` `plan` `sandbox` `store` `tokenfactory` |
| `planner` | `plan` `store` `tokenfactory` |
| `plan` | `sandbox` (lazily) |
| `plan_cli` | `ask` `gate` `node_record` `plan` `plan_text` `run` `tui` |
| `plan_text`, `plan_view` | `plan` |
| `ask` | `plan` `plan_text` `planner` `run` |
| `run` | `executor` `plan` |
| `sandbox` | `gate` `plan` |
| `tui` | `cli` `node_record` `plan` `plan_text` `run` |

## Lines, `src/graphene_map` (`wc -l`)

| Module | Before | After | |
| --- | --- | --- | --- |
| `sources/claude_code.py` → `hooks.py` | 1007 | 415 | −592 |
| `cli.py` | 485 | 421 | −64 |
| `store.py` | 701 | 659 | −42 |
| `graph.py` | 715 | 703 | −12 |
| `model.py` | 88 | 81 | −7 |
| `server.py` | 231 | 229 | −2 |
| `executor.py`, `planner.py` | 566, 197 | 565, 196 | −1 each |
| `gate.py` | 575 | 589 | +14 (`_NOT_A_PROMPT`, moved in) |
| `attribute.py` → `shell.py` | 251 | 251 | 0 |
| every other module | | | 0 |
| total | 14017 | 13310 | −707 |

Before is `f3cc6aa`, where the item's branch was cut; after is that branch with the review's fix
(`hooks.py` +4, `graph.py` +20), before `nemotron`'s later commits were merged in. On the merged
tree the same modules differ from `nemotron`'s tip (`bd17cd0`) by the same amount: 14243 lines
there, 13536 here.

## Also moved

The screen harness (`docs/process/polish/harness/`) is `docs/screens/`, with a README. Every
reference to the old path is fixed (`docs/process/polish/screens.md`, `messages.md`,
`docs/process/nemotron/folding/plan30.py`).

## Not done

- `docs/process/` onto `process-archive` with `git subtree split`, and the one command that removes
  it from `main`: the second paragraph's later steps, the lead's at the end of the run.
- The schema is untouched (see the table): dropping the dead tables would break the additive
  migration rule and the stores already out there.
- The map's Workflow groups read a field only a transcript ever filled (`workflow_run`). They are
  kept, because a store an earlier version filled still holds it and the page draws it. They are
  dead for any store made from now on. Cut them when old stores no longer matter.
  (`record.py`'s worktree mapping is not: the hooks fill `agents.worktree`.)
- `docs/PRODUCT_THESIS.md` still describes the backfill as it was. It is a dated thesis, left as
  written.
