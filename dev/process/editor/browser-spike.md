# The browser spike: hooks and screenshots, measured

Lane 8 of the editor night, 27 October 2026, about 45 minutes. Alex asked whether Graphene could show what
agents do in the browser, with screenshots. Two questions decide that. Both are answered here from this
machine's Claude Code, with the raw hook events and the store measured. Nothing was built.

## The two answers

1. **Yes, both hooks fire for MCP tools.** On Claude Code 2.1.311, every MCP call in four runs (18 calls:
   `browser_navigate`, `browser_snapshot`, `browser_click`, `browser_take_screenshot`) produced one PreToolUse
   and one PostToolUse event, and Graphene's own hook recorded all 18 in the store. Issue #73586 (2.1.198)
   does not hold on 2.1.311. Each event also names the server: `"mcp_server": {"name": "playwright", "source":
   "dynamic"}`.
2. **The screenshot reaches the hook as base64, and the transcript holds it twice.** When the agent takes a
   screenshot without a filename, `tool_response` carries an `image` block, `source.type` `base64`,
   `media_type` `image/png`: 18,732 characters for a 14,048-byte PNG of the blank page, 299,736 characters
   (a 302 KB event) for a 225 KB PNG of a busy page. The transcript line holds that base64 two times, and
   Claude Code writes the PNG once more under `~/.claude/projects/<dashed cwd>/<session>/tool-results/`. The
   Playwright server writes the file too, in its output directory. Graphene's store keeps 9,004 bytes of it:
   the first and last 4 KB of the base64, which is no longer an image. When the agent passes a `filename`,
   or the server runs with `--image-responses omit`, the hook sees a path only, and the file lands where the
   server put it: with a filename, in the repository's root.

## Versions

- macOS Darwin 25.5.0, zsh. Node v26.7.0, npx. Python 3.13.9, uv 0.11.29.
- Claude Code 2.1.311, `--model haiku`.
- Graphene 0.8.0 from this clone at `0418ca97`, run from its own `.venv/bin` (`uv sync`; no `uv tool install`).
- `@playwright/mcp@0.0.83` (published 2026-09-28), which depends on `playwright 1.64.0-alpha-1790635538000`.
  Its browser: Chrome Headless Shell 155.0.8059.12 (`chromium-headless-shell v1247`), downloaded into the work
  directory with `PLAYWRIGHT_BROWSERS_PATH`, so Alex's Playwright cache and his Chrome were not touched.

## Setup, as run

Work directory `W`: `/private/tmp/claude-501/-Users-alexlopez-Desktop-AllThingsAgenticHackathon/00e4c85f-6c44-4aec-94fd-ce50137cc546/scratchpad/work/spike/`.
Clone `C`: `…/scratchpad/lanes/spike` (this file's checkout). `PATH=$C/.venv/bin:$PATH` for every command,
the `claude` runs included, because the hooks call `graphene` by name.

The scratch repository, with Graphene's hooks:

```
cd $W/scratch && git init -q -b main . && git commit -q --allow-empty -m scratch
graphene init --planner claude --executor claude
  -> choosing the planner and the executor is the person's to do: run it in a terminal outside Claude Code
     (this call comes from claude:00e4c85f)
graphene init
  -> plan first: on. …  hooks added to .claude/settings.local.json (8 Claude Code hooks)
graphene plan first off
  -> setting plan first is the person's to do: run it in a terminal outside Claude Code
```

The flags are refused from an agent's shell (`plan._person_only`); `graphene init` with no flags asks nothing,
leaves the planner and the executor unchosen, and installs the eight hooks. That is what the spike needs.
The hooks live in `.claude/settings.local.json` (hooks.py `SETTINGS`), not `settings.json`. Plan first stayed
on, since an agent cannot turn it off; it did not get in the way: MCP tools are not gated (hooks.py `gated`
answers PreToolUse only for file tools and Bash), and every run did its MCP calls and nothing else.

My own hook, beside Graphene's, on PreToolUse, PostToolUse and PostToolUseFailure, with no matcher (every
tool): `python3 $W/bin/log_event.py`, which writes stdin to `$W/events/<ns>-<event>-<tool>.json`.

Playwright MCP, `$W/mcp.json`:

```json
{"mcpServers": {"playwright": {"command": "npx",
  "args": ["-y", "@playwright/mcp@0.0.83", "--isolated", "--headless", "--output-dir", "$W/runs/out"],
  "env": {"PLAYWRIGHT_BROWSERS_PATH": "$W/browsers"}}}}
```

`$W/mcp-omit.json` is the same with `--image-responses omit`.

The page: `$W/site/index.html`, an `<h1>` and a button whose click rewrites the heading to `Clicked at <ISO
time>`; `busy.html`, the same under a gradient with 24 text cards. Served by
`python3 -m http.server --bind 127.0.0.1 8765` from `$W/site`.

The run (`$W/bin/run.sh`), from `$W/scratch`:

```
claude -p --model haiku --max-budget-usd 0.25 --mcp-config $W/mcp.json --strict-mcp-config \
  --allowedTools "mcp__playwright__browser_navigate,mcp__playwright__browser_click,\
mcp__playwright__browser_take_screenshot,mcp__playwright__browser_snapshot,mcp__playwright__browser_close" \
  --disallowedTools "Bash,Edit,Write,MultiEdit,NotebookEdit,Agent,WebFetch,WebSearch,Read,Glob,Grep" \
  --output-format json \
  "Use the playwright browser tools only. Open http://127.0.0.1:8765/ , click the button labelled 'Click me',
   then take a screenshot of the page. Finally say in one line what the page heading reads after the click."
```

The store was measured with Graphene's Python API (`$W/bin/measure_store.py`: `Store.open(root)`, a WAL
checkpoint, the file sizes, and `length(response)` per `tool_events` row).

## The runs

| run | page | images | screenshot input | PostToolUse event | store kept | cost |
|---|---|---|---|---|---|---|
| 1 | index | allow | `{"scale":"css","fullPage":true}` | 20,313 B (base64 18,732 chars; PNG 14,048 B) | 9,004 B | $0.0050 |
| 2 | busy | allow | `{"scale":"css","filename":"busy-after-click.png"}` | 1,117 B (path only) | 288 B | $0.0059 |
| 3 | busy | omit | `{"scale":"css","filename":"busy-after-click.png"}` | 1,117 B (path only) | 288 B | $0.0061 |
| 4 | busy | allow | `{"scale":"css"}` (told: no filename) | 302,368 B (base64 299,736 chars; PNG 225,618 B) | 8,984 B | $0.0054 |

Each run: 6 or 7 turns, 10 to 15 seconds, `is_error: false`, the heading read back right. Total $0.0225.
Haiku chose a filename on its own in runs 2 and 3; run 4 was told not to.

## Evidence for answer 1: the events

Run 1's event files, in order (bytes, name):

```
  838  PreToolUse-ToolSearch                                  1216  PostToolUse-ToolSearch
  773  PreToolUse-mcp__playwright__browser_navigate           1184  PostToolUse-mcp__playwright__browser_navigate
  743  PreToolUse-mcp__playwright__browser_snapshot           1059  PostToolUse-mcp__playwright__browser_snapshot
  781  PreToolUse-mcp__playwright__browser_click              1122  PostToolUse-mcp__playwright__browser_click
  779  PreToolUse-mcp__playwright__browser_take_screenshot   20313  PostToolUse-mcp__playwright__browser_take_screenshot
```

Runs 2, 3 and 4 the same: a pair for every MCP call (five calls in runs 2 and 3, Haiku took a second
snapshot). The pair for the click, trimmed:

```json
{"hook_event_name": "PreToolUse", "tool_name": "mcp__playwright__browser_click",
 "tool_input": {"target": "e3", "element": "Click me button"}, "tool_use_id": "toolu_01BiRk…",
 "session_id": "d041c488-…", "prompt_id": "5c6790d0-…", "permission_mode": "auto",
 "transcript_path": "/Users/alexlopez/.claude/projects/-private-tmp-…-spike-scratch/d041c488-….jsonl",
 "mcp_server": {"name": "playwright", "source": "dynamic"}}
{"hook_event_name": "PostToolUse", "tool_name": "mcp__playwright__browser_click", "tool_input": {…},
 "tool_response": [{"type": "text", "text": "### Ran Playwright code\n```js\nawait page.getByRole('button',
   { name: 'Click me' }).click();\n```\n### Page\n- Page URL: http://127.0.0.1:8765/ …"}],
 "tool_use_id": "toolu_01BiRk…", "duration_ms": 533, "mcp_server": {"name": "playwright", "source": "dynamic"}}
```

Graphene's hook, running beside mine, recorded every one: 22 `tool_events` rows after the four runs (4
`ToolSearch`, 18 MCP), `success=1` on all, and no `ingest.log` was written (no error). `ToolSearch` fires
hooks too: Haiku looked the MCP tools up before calling them.

## Evidence for answer 2: where the screenshot goes

Run 1's PostToolUse for the screenshot, trimmed:

```json
"tool_response": [
  {"type": "text", "text": "### Result\n- [Screenshot of full page](../runs/out/page-2026-10-27T04-24-08-328Z.png)
     \n### Ran Playwright code\n```js\n// Screenshot full page and save it as ../runs/out/page-….png\nawait
     page.screenshot({\n  fullPage: true,\n  path: '../runs/out/page-….png',\n  scale: 'css',\n  type: 'png'\n});\n```"},
  {"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": "<18732 chars: iVBORw0KGgo…>"}},
  {"type": "text", "text": "[Image: source: /Users/alexlopez/.claude/projects/-private-tmp-…-spike-scratch/
     d041c488-d508-4df8-915d-ebc974be7daa/tool-results/mcp-playwright-blob-1793075048333-lx7i2j.png]"}
]
```

The MCP server returns `{"type": "image", "data", "mimeType"}`; Claude Code hands the hook the API's shape
(`source.type` `base64`, `media_type`). The base64 decodes to 14,048 bytes, the same SHA-256 as the server's
file. The whole `tool_response` is 19,515 bytes as JSON.

So one screenshot without a filename is, on disk:

| copy | where | bytes (run 1 / run 4) |
|---|---|---|
| the server's file | `--output-dir`, `page-<time>.png`; a path relative to the cwd in the text block | 14,048 / 225,618 |
| Claude Code's blob | `~/.claude/projects/<dashed cwd>/<session>/tool-results/mcp-playwright-blob-<ms>-<id>.png` | 14,048 / 225,618 |
| the hook's event | `tool_response[1].source.data`, base64 | 18,732 / 299,736 chars |
| the transcript | one `user` line, the base64 in `message.content[0].content[1]` and again in `toolUseResult[1]` | line of 39,810 / 603,952 |
| Graphene's store | `tool_events.response`, the base64's first and last 4 KB | 9,004 / 8,984 |

Run 1's transcript is 315,403 bytes in 75 lines (the system prompt and `api-request-shape` lines are most of
it); run 4's is 893,789 bytes, the difference being the busy screenshot twice. The transcript is read-only
for Graphene and is pruned by `cleanupPeriodDays`.

With a filename (runs 2 and 3) the response is one text block, no image, in either mode:

```
"tool_input": {"scale": "css", "filename": "busy-after-click.png"}
"tool_response": [{"type": "text", "text": "### Result\n- [Screenshot of viewport](./busy-after-click.png)\n…
   await page.screenshot({\n  path: './busy-after-click.png',\n  scale: 'css',\n  type: 'png'\n});…"}]
```

The file went to the workspace root, which is the scratch repository: `busy-after-click.png`, 227,305 bytes,
untracked (`git status`: `?? busy-after-click.png`). Nothing under `tool-results/`. The server wrote it, not a
Claude tool, so no hook saw a write and the gate could not have refused it.

The server itself, asked directly over stdio (`$W/bin/probe_mcp.py`, no Claude, $0), on the busy page:

| call | images allowed | images omitted | file written |
|---|---|---|---|
| no arguments (viewport, png) | text 341 + base64 299,736 chars; 300,186 B | text 338; 391 B | 224,802 B |
| `fullPage: true` | base64 605,484 chars; 605,955 B | 412 B | 454,113 B |
| `filename: "shot.png"` | text 212; 265 B, no image | 265 B | 225,289 B, in the cwd |
| `type: "jpeg"` | base64 326,088 chars; 326,559 B | 411 B | 244,564 B (JPEG is not smaller here) |

`--image-responses omit` keeps the model from seeing the image at all (it still writes the file); it is a
token saving, not a trail.

## What Graphene keeps today

`hooks.py` `ingest_hook_event` passes `tool_response` whole into `ToolEvent.response` for every PostToolUse;
`store.add_event` drops a `Read`'s response and runs `capped_json` on the rest (store.py 257–271): every
string over `STRING_CAP` (8 KB) becomes its first and last `KEEP` (4 KB) around `… [N chars omitted] …`,
then a response over `RESPONSE_CAP` (256 KB) is replaced by `{"truncated": true, "bytes": N}`. A screenshot's
base64 is one string, so the row keeps 9,004 bytes of broken base64, whatever the image's size. The `ToolEvent`
comment says `capped at 256 KB`; for an image the effective cap is 8 KB.

Measured, `graphene.db` with a WAL checkpoint: 114,688 bytes with no events; 122,880 after run 1 (5 rows,
+8,192); 147,456 after run 2 (11 rows; two 8,352-byte snapshots of the busy page); 167,936 after run 3;
188,416 after run 4 (22 rows, +20,480). The store grows by the page snapshots, not by the screenshots.

If `graphene ingest hook` kept what it is given, unchanged, one screenshot row would be 19.5 KB for the blank
page and 300 KB for a real viewport, as base64 text in SQLite, four thirds of the PNG; a full-page one, 606
KB, is over `RESPONSE_CAP` and would be dropped whole. Keeping it is not a bigger cap: it is a file.

## What a per-task trail of browser work would take

What to keep, for each `browser_take_screenshot` PostToolUse:
- the PNG, decoded from `tool_response[*].source.data`, named by its SHA-256 (run 1's blob and the server's
  file were byte-identical; a page that did not change repeats);
- what the row already has: `session_id`, `prompt_id`, `agent_id`, `tool_use_id`, the timestamp, the input,
  the text blocks (the Playwright line, the page URL and title, the server's own path);
- the `mcp_server.name`, so the cockpit can tell browser work from the rest without parsing tool names.

Where: a files directory in the store, `blobs/<sha256>.png` beside `graphene.db` (the directory is already
0700 and git-ignored on every open), with the row's `image` block replaced by `{"type": "image", "blob":
"<sha>", "bytes": N, "media_type": "image/png"}`. Not in SQLite as text, and not the transcript: it is
read-only, holds the base64 twice, and is pruned.

How big: 14 KB for a blank page, 225 KB for a viewport of a real page, 455 KB full-page; JPEG does not help.
Twenty screenshots in a task are about 4.5 MB; ten such tasks a night, 45 MB, less what the SHA de-duplicates.

What Graphene would need to change:
1. `hooks.py` `ingest_hook_event`: when `tool_response` is a list (the MCP shape), lift each `image` block
   into a blob before `store.add_event` trims it. Decoding and writing 300 KB is milliseconds; the hook's 5 s
   timeout holds.
2. `store.py`: the blob directory, and `capped_json` leaving the replaced block alone. One column or none: the
   SHA sits in the response JSON.
3. The two path-only cases. With a `filename`, or under `--image-responses omit`, the hook gets a path
   relative to the workspace root (the cwd) or to the output directory; the file exists before the hook runs
   (the server writes, then answers), so the hook can copy it into the blobs by the same rule. A filename
   inside the repository is a file the gate never saw and git does not track; the trail should record that
   path, and the plan's cleanup is the agent's.
4. A viewer: `last_events` and the cockpit's agent view show the newest blob for an agent; the VS Code side
   gets it from the CLI like everything else. Nothing on the gate: MCP tools are not gated, which is right for
   a trail and a separate question for plan first.

Not needed: a dependency (base64 and hashlib are stdlib), a cap change, or reading the transcript.

## Side findings

- From inside a Claude Code session `graphene init --planner … --executor …` and `graphene plan first off`
  are refused as the person's; `graphene init` with no flags installs the hooks and chooses nothing.
- The Playwright server's 404 for `/favicon.ico` shows in every snapshot as `Console: 1 errors`; Haiku
  reported it each time. A real page would not.
- Haiku's own wording: it passed `filename` unasked in two of four runs. A trail cannot count on the inline
  image; it must handle the path case (point 3 above).

## Where the evidence is

Under `$W`: `events/run1..run4/` (the raw hook JSON), `runs/run1..run4.json` (`claude -p` output, with cost
and session id), `runs/store-before.txt` and `store-after1..4.txt`, `runs/out/` and `runs/out-omit/` (the
server's files), `runs/probe-allow/` and `runs/probe-omit/` (the direct probe), `bin/` (the scripts named
above), `scratch/` (the repository, with its `.claude/settings.local.json`). The transcripts are under
`~/.claude/projects/-private-tmp-claude-501--Users-alexlopez-Desktop-AllThingsAgenticHackathon-00e4c85f-6c44-4aec-94fd-ce50137cc546-scratchpad-work-spike-scratch/`,
sessions `d041c488`, `a244643f`, `39db426a`, `a965995a`.
