# How Graphene works

Graphene reads what Claude Code already records about a session and turns it into an account
of what happened, grouped by what you asked for. Nothing here involves a model except the
optional explanation sentences, and those are written from a diff Graphene has already computed.

## 1. Where the data comes from

### Live hooks

`graphene init` adds one command hook, `graphene ingest hook`, to five Claude Code events in the
repo's `.claude/settings.json`: `SessionStart`, `UserPromptSubmit`, `PostToolUse`,
`PostToolUseFailure` and `Stop`. Existing settings and hooks are kept; the hook is added once.
Claude Code runs the command with the event JSON on stdin. The command writes one row to
`.graphene/graphene.db` and exits 0 whatever happens; internal errors go to
`.graphene/ingest.log`, never to stdout, so a broken Graphene can never block the agent. It takes
about 35 ms because it imports only the standard library on that path.

What each event contributes:

| Event | Recorded |
| --- | --- |
| `SessionStart` | the session, its repo, the time, and `git rev-parse HEAD` at that moment |
| `UserPromptSubmit` | the prompt text verbatim, with Claude Code's `prompt_id` |
| `PostToolUse` | the tool name, input, response, and for file tools the file's content before and after |
| `PostToolUseFailure` | the same call marked failed, with the error text |
| `Stop` | the session's end time (updated on every turn end) |

A tool call is grouped under the prompt whose `prompt_id` it carries. When that id is unknown
(hooks installed mid-session, older Claude Code), it falls back to the latest recorded prompt in
the session. Subagent calls carry `agent_id` and are grouped the same way.

### Transcript backfill

`graphene ingest --backfill` reads the JSONL transcripts Claude Code keeps under
`~/.claude/projects/<encoded repo path>/`, plus any directory whose name starts with that prefix
(sessions launched from a subdirectory of the repo). A transcript is used only if its recorded
`cwd` lies inside the repo. Facts the parser relies on, observed on Claude Code 2.1.27x:

- One JSON object per line. `type` is `user`, `assistant`, or bookkeeping (`attachment`,
  `system`, `file-history-snapshot`, `queue-operation`, `mode`, ...). Unknown types are skipped
  and counted; the count is printed after a backfill.
- A prompt is a `user` record whose content is a string (or text blocks) and that is not
  `isMeta`, not `isSidechain`, not a compaction summary, and not a slash-command echo wrapped in
  `<command-name>` or `<local-command-stdout>` tags.
- A tool call is a `tool_use` block in an `assistant` record. Its result is a `tool_result` block
  in a later `user` record; `is_error` marks failure, and that record's `toolUseResult` holds the
  structured result. That record also carries the `promptId` of the turn it ran in, which is how
  calls are grouped; a call without one is grouped under the last prompt before its timestamp.
- Subagent transcripts live in `<transcript dir>/<session id>/subagents/**/*.jsonl` and are
  merged into the session, keeping their `agentId`.
- The transcript never records the git HEAD at session start, so backfilled sessions store it as
  unknown and the git fallback below uses the current HEAD instead.

A backfilled session is reloaded when its transcript has grown. A session the hooks recorded is
left alone unless you pass `--replace`, which rebuilds its prompts and calls from the transcript
and keeps the HEAD the hook captured.

## 2. File content: what is known and what is not

For `Edit`, `MultiEdit` and `Write`, Claude Code's response carries `originalFile`, the content
before the call, and either the new content (`Write`) or the strings replaced (`Edit`), from which
Graphene derives the content after the call. Both are stored (up to 2 MB each) so a diff can be
computed later without touching the working tree. A `Write` whose response says `create` counts
as known with no prior content.

What is not known from the payload: anything a shell command does to a file, and notebook edits.
For `Bash`, Graphene recognises only the obvious write forms: `>` and `>>` redirections, `tee`,
`sed -i`, `mv`, `cp`, `rm` and `touch`. A script that rewrites files, a formatter, a `git
checkout`, or a `python -c` that writes are all invisible to it.

## 3. Attribution: prompt → file → hunks

Per session and file, Graphene lines up the file-touching calls in time order and splits them by
prompt.

**Payload strategy** (used when every call on the file carries content): for each prompt, the
diff is between the file before that prompt's first call and after its last call, computed with
Python's `difflib` in unified form with three lines of context. Line counts and the enclosing
definitions (`def`, `class`, `function`, `fn`, ...) of the changed lines come from that diff.
Failure modes: a change made outside the tools between two calls (you, a formatter, a shell
script) makes the next call's `originalFile` differ from the previous call's result; the diff for
that prompt then includes the outside change. Across 19 consecutive edits checked on real
transcripts, 17 chained exactly and 2 had such interference.

**Git strategy** (used when any call on the file lacks content): the diff is `git show
<HEAD at session start>:<path>` against the working tree now, credited in full to the last prompt
that touched the file; earlier prompts that touched it are listed with no hunks. Failure modes:
for backfilled sessions the base is the current HEAD, so commits made during the session hide
their changes from the diff; changes made after the session are blamed on it; if the file was
touched by several prompts, only the last one gets the diff.

**No strategy**: without git, the file is listed with its effect and no hunks.

The effect per prompt is `created` (no content before), `deleted` (no content after),
`reverted` (before and after identical), otherwise `modified`.

## 4. Unrequested changes

A file is flagged `unrequested` when the prompt text mentions none of the file's path, basename,
stem or parent directory name (case-insensitive substring). This over-flags on purpose: "fix the
login bug" says nothing about `auth.py`, and a prompt naming only a task flags every file the
agent touched. It never under-flags a file the prompt names. The flag is per prompt, so a file can
be requested under one prompt and unrequested under the next.

## 5. Tried and abandoned

- **Reverted files**: the file's content at the end of the session equals its content at the
  start (payload strategy), or the git diff against the session-start HEAD is empty (git
  strategy), and at least one call changed it in between.
- **Failed calls**: any tool call whose result was an error, with the first line of the error
  (and the first output line after an `Exit code N` line).
- **Checks that failed and were rerun**: a shell segment whose command word is a test or lint
  runner (`pytest`, `npm test`, `cargo test`, `go test`, `make`, `ruff`, `mypy`, `tsc`, `jest`,
  `vitest`, `eslint`, ...) that failed and was run again later with the same text, reporting the
  last rerun's outcome.

## 6. Explanations

Each file line in a debrief ends with one sentence. By default it is a template built from the
diff: "Edited 2 definitions in auth.py: login and refresh_token (+12/−4)." With `--explain claude`
(the default when `claude` is on PATH), Graphene makes one `claude -p` call per prompt with the
request text and the capped diffs of all its files, asks for a JSON object of one sentence per
path, and stores the sentences so `graphene why` and later debriefs never call the model again.
Any failure (no binary, timeout, non-JSON reply) falls back to the templates for the rest of the
run and says so at the bottom of the debrief. The call runs with no tools, no MCP servers, no
settings files and no session persistence.

## 7. `graphene why`

`graphene why PATH` runs the attribution for every session that touched the file and lists the
prompts newest first, each with its diff summary and the stored explanation if one exists.

`graphene why PATH:LINE` reads the line from disk, asks `git blame` which commit last touched it,
then looks for prompts whose recorded diff added a line with the same text. If the line is
committed, prompts that ran after the commit are excluded. One match is reported as the answer;
several are listed newest first; none is explained: committed before any recorded session, or
changed by something Graphene did not see.

## 8. What Graphene never does

It never runs an agent, never orchestrates, never pushes, and never sends anything anywhere. The
only network use is the optional `claude -p` call, made by your own Claude Code installation.
Transcripts can contain secrets; the store stays in `.graphene/` inside the repo and is
git-ignored by `graphene init`.
