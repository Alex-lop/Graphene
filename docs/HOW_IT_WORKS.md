# How Graphene works

Graphene reads what Claude Code already records about a session and turns it into an account
of what happened, grouped by what you asked for. No model is involved at any point: every
sentence here is computed from a diff Graphene already has.

## 1. Where the data comes from

### Live hooks

`graphene init` adds one command hook, `graphene ingest hook`, to five Claude Code events in the
repo's `.claude/settings.local.json` (the personal file; the team's `settings.json` is never
written, though hooks found there are recognised): `SessionStart`, `UserPromptSubmit`, `PostToolUse`,
`PostToolUseFailure` and `Stop`. Existing settings and hooks are kept; the hook is added once, and
the file is rewritten atomically (through a symlink to its target) so a crash cannot truncate it.
Claude Code runs the command with the event JSON on stdin. The command writes one row to
`.graphene/graphene.db` and exits 0 whatever happens; internal errors go to
`.graphene/ingest.log`, never to stdout, so a broken Graphene can never block the agent. It takes
about 40 ms (a median of twenty runs on the author's machine, measured by `tests/test_hook_budget.py`
and held under 60 ms there) because it imports only the standard library on that path, and if another process
holds the database lock (a backfill, a second session) it gives up after 250 ms and logs the
missed event rather than stalling the agent.

What each event contributes:

| Event | Recorded |
| --- | --- |
| `SessionStart` | the session, its repo, the time, and `git rev-parse HEAD` at that moment |
| `UserPromptSubmit` | the prompt text verbatim, with Claude Code's `prompt_id`; a slash command (`/model`, a skill) is skipped, as in the transcripts |
| `PostToolUse` | the tool name, input, response, and for file tools the file's content before and after |
| `PostToolUseFailure` | the same call marked failed, with the error text |
| `Stop` | the session's end time (updated on every turn end) |

Not all of a response is worth keeping. A `Read` is recorded as the call, the path and whether it
worked: its response is the file itself, and nothing here reads it back. Any other recorded string
longer than 8 KB keeps its first and last 4 KB with a count of the characters between them, so a
command is remembered by how its output started and how it ended — a `git commit … && git log
--oneline -1` prints the new SHA on the very last line. Paths, names, the list of files a command
changed and the error of a failed call are never cut, and a file edit's before and after content
keeps its own 2 MB budget in its own columns.

A tool call is grouped under the prompt whose `prompt_id` it carries. When that id is unknown
(hooks installed mid-session, older Claude Code), it falls back to the latest recorded prompt in
the session; calls made before any recorded prompt appear in the debrief under their own heading,
"Before the first recorded prompt". Subagent calls carry `agent_id` and are grouped the same way.

### Transcript backfill

`graphene ingest --backfill` reads the JSONL transcripts Claude Code keeps under
`~/.claude/projects/<encoded repo path>/`, plus any directory whose name starts with that prefix
(sessions launched from a subdirectory of the repo), under the repo's path as given and as
resolved through symlinks. A transcript is used only if its recorded `cwd` lies inside the repo. Facts the parser relies on, observed on Claude Code 2.1.27x:

- One JSON object per line. `type` is `user`, `assistant`, or bookkeeping (`attachment`,
  `system`, `file-history-snapshot`, `queue-operation`, `mode`, ...). Only `user` and `assistant`
  records carry prompts and tool calls; every other type is counted and listed after a backfill
  as "other record types", so a new type Claude Code starts writing is at least visible.
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
  unknown; the git fallback below then uses the last commit made before the session started
  (or git's empty tree when there is none), so commits made during or after the session do not
  hide its changes.

A transcript is only parsed when it might have changed: the store keeps the file's size and
modification time from the last time it was read, and a transcript matching both is skipped
without being opened. One that grew is parsed and its session reloaded. A transcript that cannot
be read is reported and skipped; the others still load. Injected context blocks
(`<system-reminder>…</system-reminder>`) are stripped from prompt text, and a message that
consists only of them is not a prompt.

A session the hooks recorded is left alone, because the hooks saw more than the transcript does
(the content before and after each call, and the git HEAD at the start). There is one exception:
if the hooks are installed in this repo and the transcript holds more tool calls than the store
has events for that session — which means they were installed part-way through it — the session
is rebuilt from the transcript automatically, keeping the HEAD the hook captured and the earlier
of the two start times, and is reported as refreshed. `--replace` forces that rebuild for every
session the hooks recorded, installed or not.

### The store

`.graphene/graphene.db` carries a schema version in SQLite's `user_version`. Everything in it is
derived from transcripts and hook events, so a store written by another version of Graphene is
not migrated: it is moved to `.graphene/graphene.db.v<old>.bak` (with its `-wal`/`-shm` sidecars,
and a numeric suffix rather than overwriting an existing backup), and the command that found it
creates an empty store, prints one line to stderr saying so, and backfills from the transcripts.
A file SQLite refuses to read at all goes to `.graphene/graphene.db.corrupt.bak` the same way. A
locked database is not that case and is never moved aside. The hook path never rebuilds: on a
store it cannot use it skips the event, writes one line to `.graphene/ingest.log` saying a rebuild
is needed, and exits 0, so the next `graphene` command is what does the work.

## 2. File content: what is known and what is not

For `Edit`, `MultiEdit` and `Write`, Claude Code's response carries `originalFile`, the content
before the call, and either the new content (`Write`) or the strings replaced (`Edit`), from which
Graphene derives the content after the call. Both are stored (up to 2 MB each) so a diff can be
computed later without touching the working tree. A `Write` whose response says `create` counts
as known with no prior content. For a file outside the repo (a dotfile in your home directory,
say) only the path is kept, never the contents, not even inside the raw tool payload the store
keeps for every call: the debrief lists such files by name and nothing else. A file inside another git checkout below the repo root (a worktree under
`.claude/worktrees/`, a vendored clone) counts as outside too: it belongs to that checkout.

What is not known from the payload: anything a shell command does to a file, and notebook edits.
For `Bash`, Graphene recognises only the obvious write forms: `>` and `>>` redirections, `tee`,
`sed -i`, `mv`, `cp`, `rm` and `touch`. Relative paths follow `cd` segments earlier in the same
command; heredoc bodies are ignored so a `>` inside a script fed to `python` is not a
redirection. A script that rewrites files, a formatter, a `git checkout`, or a `python -c` that
writes are all invisible to it.

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

**Bridged strategy** (a shell write between two payload calls): whatever a shell command left
in the file is exactly what the next `Edit` or `Write` reports as `originalFile`, so the
shell-writing prompt gets the diff between the previous payload's result and that `originalFile`.
No git involved, and the payload diffs of the other prompts are untouched.

**Git strategy** (a shell write at the start or the end of the file's history in the session):
the missing boundary comes from `git show <HEAD at session start>:<path>` at the start, or from
the working tree now at the end. Several consecutive prompts writing a file through shell
commands with no payload in between form one span credited to the last of them; the earlier ones
are listed with no hunks. A deleted or moved directory is expanded to the files it held at the
base revision, one change each. A file that is absent from the base revision reads as created;
an untracked file that already existed and was then changed by a shell command therefore shows
its whole content as added, while one whose modification time predates the session is dropped as
untouched. Failure modes: changes made after the session by anything else are blamed on its last
prompt; for backfilled sessions the base is the commit before the session's first record, which
misses work committed within the same second.

**Deferred**: a prompt inside such a span, other than the last, is listed as touching the file
with no hunks and the sentence "its diff for this session is credited to a later prompt", never as
having changed zero lines.

**No strategy**: without git (or with git unavailable), a file a shell command wrote is listed as
modified with no hunks, since created cannot be told from modified, and a file a shell command
removed is listed as deleted with no content. In a repository with no commits yet, git's empty
tree is the base, so files the agent wrote read as created.

The effect per prompt is `created` (no content before), `deleted` (no content after),
`reverted` (before and after identical), otherwise `modified`.

## 4. Unrequested changes

A file is flagged `unrequested` only when the prompt named a file scope and the file lies outside
it. Silence is preferred to a flag people learn to ignore, so every one of these must hold:

1. The prompt names a **file scope**: a path-like token (`auth.py`, `src/app/`, `.env`,
   `docs/HOW_IT_WORKS.md`), or a bare word right after *in*, *under*, *inside*, *within*, *into* or
   *at* that is a directory of a file the prompt changed ("look in app"). A prompt with no such
   token ("fix the login bug") flags nothing: a goal is not a file list.
2. Names that point at a goal rather than a place define no scope: `.md`, `.txt`, `.rst` or `.adoc`
   files at the repo root, and anywhere when their name contains words like directive, spec, goal,
   plan, readme, todo, prompt or notes. "Implement REBUILD_DIRECTIVE.md" flags nothing.
3. A changed file is **in scope** when a named directory contains it, a named file is it, or it is
   a conventional companion of an in-scope file: a test twin by stem (`tests/test_hello.py` for
   `app/hello.py`, `x_test.go` for `x.go`, `a.spec.ts` for `a.ts`), or any file in the same
   directory as a named file, `__init__.py` included.
4. Every other changed file is flagged, with the prompt it happened under.

Failure modes: a domain or version-like token that looks like a file name (`node.js`) can name a
scope by accident and flag real work; a prompt that names one small file while asking for broad
work ("start in cli.py and wire everything up") flags the everything; naming a directory brings
its whole subtree into scope even if the prompt meant one file; and nothing outside the repo is
ever considered here, those paths are listed separately. The flag is per prompt, so a file can be
in scope under one prompt and flagged under the next.

## 5. Tried and abandoned

- **Reverted files**: the file's content at the end of the session equals its content at the
  start (payload strategy), or the git diff against the session-start HEAD is empty (git
  strategy), and at least one call changed it in between.
- **Failed calls**: every tool call whose result was an error is recorded, but a failed call is
  not abandoned work, so the default view shows only one line with their count by tool and how
  many were refused before running (the permission system, the auto mode classifier, or the
  user). `--json` carries every one.
- **Checks that failed and were rerun**: a shell segment whose command word is a test or lint
  runner (`pytest`, `npm test`, `cargo test`, `go test`, `make`, `ruff`, `mypy`, `tsc`, `jest`,
  `vitest`, `eslint`, ...) that failed and whose check segment (`uv run pytest -q`, say) was run
  again later, whatever surrounded it in the command, reporting the last rerun's outcome.

## 5a. What you see

Every command first tops the store up from the repo's transcripts (a transcript that has not
changed since it was last read costs one `stat`), so a session run without the hooks still
shows up the next time you look. `graphene` prints a short card: the sessions covered,
their span, wall time and prompt count; files changed with added and removed lines; the commits
made during the sessions; a net list of files (created, modified, deleted or reverted over the
whole span, biggest change first, capped at 30 rows); and then only the sections that have
something in them: files outside a named scope (§4), abandoned work (§5), a one-line failure
count, files written outside the repo. `--session ID` picks one session and `--since 6h` a
window; `--json` is the whole structure behind the card, prompt by prompt.

In a terminal that card is drawn in columns: one bold header line, dim metadata, one accent
colour for paths and commands, green for `+N`, red for `−N`, no boxes and no emoji. Rows never
wrap — paths are shortened in the middle, commit subjects at the end — and the terminal card
shows at most 5 commits and 20 files before "… N more", so a session fits in 40 rows at 80
columns. `NO_COLOR` turns the colour off and keeps the layout. When stdout is not a terminal
(`graphene > out.txt`, a pipe, CI) the markdown text is written as it is, with no rendering at
all; `--json` is always plain. `graphene why` and `graphene sessions` follow the same rules.

Graphene writes nothing until it has something to record: in a repo with neither a store nor a
transcript the empty state is printed and `.graphene/` and `.gitignore` are left alone (`graphene
init` creates them, and says so). Every dead end is one line on stderr and a non-zero exit (plain text when it is merely empty,
red when it is an error; word-wrapped on a terminal, one line when piped): outside a git repository, inside your
home directory, no transcripts for this repo (naming the directory it searched), a session that
changed nothing, a store another Graphene process has locked, `why` on a path nothing touched,
and `why` with no path at all, which first lists the five files that changed most recently.

## 6. `graphene why`

`graphene why PATH` runs the attribution for every session that touched the file and lists the
prompts newest first, each with its diff summary and a sentence built from that diff: "Edited 2
definitions in auth.py: login and refresh_token (+12/−4)."

`graphene why PATH:LINE` reads the line from disk, asks `git blame` which commit last touched it,
then looks for prompts whose recorded diff added a line with the same text, preferring an edit at
the same line number and falling back to the same text elsewhere. If the line is committed, prompts
that ran after the commit are excluded even when they added identical text. One match is reported
as the answer; several are listed newest first; none is explained: committed before any recorded
session, committed before any matching edit, or changed by something Graphene did not see.

All commands except the hook refuse to run outside a git repository, and never treat your home
directory as one, so `~/.claude/settings.json` (Claude Code's user-level settings) is never
written.

## 7. What Graphene never does

It never runs an agent, never orchestrates, never pushes, never calls a model, and never sends
anything anywhere. Transcripts can contain secrets; the store stays in `.graphene/` inside the repo, a directory
that is made private to your user (`0700`, the database `0600`) and that ignores itself in git
through a `.gitignore` of its own, so the repo's `.gitignore` is never edited.

## 8. The HTML record

`graphene debrief --html record.html` writes one file: the same structure `--json` prints, embedded
as JSON in a `<script type="application/json">` tag, plus a stylesheet and a script that build the
page from it. Nothing is fetched when you open it — no fonts, scripts, images or trackers — so it
works offline and can be emailed to someone who has neither the repo nor Graphene. Every piece of
text from your prompts, diffs and file paths reaches the page through `textContent`, and `</` is
escaped inside the JSON, so nothing recorded can turn into markup.

The page is a timeline: session bands at the top, then one row per prompt in time order with its
text (three lines, click to expand) and the files it touched with `+N/−N` and an `unrequested`
marker. Clicking a file opens a panel with that prompt's diff, its sentence, and the file's
history inside the record — every prompt that touched the same path, newest first, each one a
link back to its row. Two checkboxes filter the rows down to the
unrequested or the abandoned ones. Alongside the debrief the file carries a `nodes` list in which
sessions, prompts, files and directories are distinct node types, and the markup tags them the same
way (`data-node="file"`, `data-node="dir"`, …); today only the timeline reads them.
