# How Graphene works

Graphene reads what Claude Code already records about a session and turns it into an account
of what happened, grouped by what you asked for. Nothing here involves a model except the
optional explanation sentences, and those are written from a diff Graphene has already computed.

## 1. Where the data comes from

### Live hooks

`graphene init` adds one command hook, `graphene ingest hook`, to five Claude Code events in the
repo's `.claude/settings.json`: `SessionStart`, `UserPromptSubmit`, `PostToolUse`,
`PostToolUseFailure` and `Stop`. Existing settings and hooks are kept; the hook is added once, and
the file is rewritten atomically (through a symlink to its target) so a crash cannot truncate it.
Claude Code runs the command with the event JSON on stdin. The command writes one row to
`.graphene/graphene.db` and exits 0 whatever happens; internal errors go to
`.graphene/ingest.log`, never to stdout, so a broken Graphene can never block the agent. It takes
about 35 ms because it imports only the standard library on that path, and if another process
holds the database lock (a backfill, a second session) it gives up after 250 ms and logs the
missed event rather than stalling the agent.

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

A backfilled session is reloaded when its transcript has grown. A session the hooks recorded is
left alone unless you pass `--replace`, which rebuilds its prompts and calls from the transcript
and keeps the HEAD the hook captured. A transcript that cannot be read is reported and skipped;
the others still load. Injected context blocks (`<system-reminder>…</system-reminder>`) are
stripped from prompt text, and a message that consists only of them is not a prompt.

## 2. File content: what is known and what is not

For `Edit`, `MultiEdit` and `Write`, Claude Code's response carries `originalFile`, the content
before the call, and either the new content (`Write`) or the strings replaced (`Edit`), from which
Graphene derives the content after the call. Both are stored (up to 2 MB each) so a diff can be
computed later without touching the working tree. A `Write` whose response says `create` counts
as known with no prior content. For a file outside the repo (a dotfile in your home directory,
say) only the path is kept, never the contents: the debrief lists such files by name and nothing
else.

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
  user). `graphene debrief --full` lists real failures one by one and groups refusals by reason;
  `--json` carries every one.
- **Checks that failed and were rerun**: a shell segment whose command word is a test or lint
  runner (`pytest`, `npm test`, `cargo test`, `go test`, `make`, `ruff`, `mypy`, `tsc`, `jest`,
  `vitest`, `eslint`, ...) that failed and whose check segment (`uv run pytest -q`, say) was run
  again later, whatever surrounded it in the command, reporting the last rerun's outcome.

## 5a. What you see

`graphene` with no command, and `graphene debrief`, print a short card: the sessions covered,
their span, wall time and prompt count; files changed with added and removed lines; the commits
made during the sessions; a net list of files (created, modified, deleted or reverted over the
whole span, biggest change first, capped at 30 rows); and then only the sections that have
something in them: files outside a named scope (§4), abandoned work (§5), a one-line failure
count, files written outside the repo. `graphene debrief --full` is the whole reconstruction,
prompt by prompt, with a sentence per file. `--json` is the structure behind both.

## 6. Explanations

Each file line in the full reconstruction and in `graphene why` ends with one sentence. By default
it is a template built from the diff: "Edited 2 definitions in auth.py: login and refresh_token
(+12/−4)." With `--explain claude` (never by default), Graphene makes one `claude -p` call per prompt with the
request text and the diffs of all its files (each capped at 4,000 characters, 80,000 in total;
files past the budget are sent with line counts and an "omitted" marker), asks for a JSON object
of one sentence per path validated by a JSON schema, in batches of at most 120 files, and stores the sentences so `graphene why`
and later debriefs never call the model again. Any failure (no binary, timeout, an unusable
reply) falls back to the templates for the rest of the run and says so at the bottom of the
debrief. The call runs with no tools, no MCP servers, no settings files, no session persistence
and a temporary working directory, so it leaves no transcript behind and fires no hooks. Before
anything is sent, the diff of any file whose name looks like a secrets file (`.env*`, `*.pem`,
`*.key`, `id_rsa*`, anything with credential, secret, token or password in the name) is replaced
by a note, and token-shaped strings or private-key blocks in any diff are masked. It uses
whatever model your Claude Code defaults to; a 23-file prompt cost about half a dollar on the
default model during the rebuild.

## 7. `graphene why`

`graphene why PATH` runs the attribution for every session that touched the file and lists the
prompts newest first, each with its diff summary and the stored explanation if one exists.

`graphene why PATH:LINE` reads the line from disk, asks `git blame` which commit last touched it,
then looks for prompts whose recorded diff added a line with the same text, preferring an edit at
the same line number and falling back to the same text elsewhere. If the line is committed, prompts
that ran after the commit are excluded even when they added identical text. One match is reported
as the answer; several are listed newest first; none is explained: committed before any recorded
session, committed before any matching edit, or changed by something Graphene did not see.

All commands except the hook refuse to run outside a git repository, and never treat your home
directory as one, so `~/.claude/settings.json` (Claude Code's user-level settings) is never
written.

## 8. What Graphene never does

It never runs an agent, never orchestrates, never pushes, and never sends anything anywhere. The
only network use is the optional `claude -p` call, made by your own Claude Code installation.
Transcripts can contain secrets; the store stays in `.graphene/` inside the repo, a directory
that is made private to your user and git-ignored the first time any command creates it.
