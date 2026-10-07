# The meter: what it reads, what it writes

Written at the start of the meter night (6 October), before the code. The builders work to it.

## What it reads

The executor's own stdout, which `graphene run` already sends to the attempt's log file
(`.graphene/runs/<id>-<stamp>-<session>-<attempt>.txt`). `run_node` reads the bytes the file gained since
the last poll (every `POLL`, 0.5 s), feeds each complete line to a `meter.Meter`, and logs the rows it
returns. Lines that are not JSON (stderr shares the file) are skipped and counted, never an error. A
stream that cannot be read leaves the run and the leaf as they are today: the meter degrades, the run
does not.

- **Claude Code** (`claude -p --output-format stream-json --verbose`, in `DEFAULT_WITH`). Shapes seen live
  on 2.1.292 (`tests/fixtures/meter/claude.jsonl`):
  - `{"type":"system","subtype":"init","model":"claude-sonnet-5-5","session_id":…}`
  - `{"type":"assistant","message":{"id":"msg_…","model":…,"usage":{"input_tokens","cache_creation_input_tokens",
    "cache_read_input_tokens","cache_creation":{"ephemeral_5m_input_tokens","ephemeral_1h_input_tokens"},
    "output_tokens"},"content":[{"type":"tool_use","id":"toolu_…","name":"Edit","input":{…}} | {"type":"text",…}]}}`.
    **One message can arrive as several events, one per content block, each repeating the same usage.**
    Usage is counted once per `message.id`.
  - `{"type":"user","message":{"content":[{"type":"tool_result","tool_use_id":…,"is_error":…}]}}`
  - `{"type":"result","total_cost_usd":…,"num_turns":…,"duration_ms":…,"usage":{…},"modelUsage":{…}}`, last.
    After `--resume` (attempt 2 and later) `total_cost_usd` is the session's running total, and `usage` is
    the call's own. Checked live at 03:20: two Sonnet calls, the second resumed, said $0.016725 and $0.0273024,
    and $0.0273024 is $0.016725 plus the second call's own usage priced (2,525 cache-write, 2,217 cache-read and
    3 output tokens). So the dollars net what the session paid before; the tokens are taken as they come.
- **Codex** (`codex exec --json`). Shapes seen live on 0.151.0 (`tests/fixtures/meter/codex.jsonl`):
  - `{"type":"thread.started","thread_id":…}`, `{"type":"turn.started"}`
  - `{"type":"item.started"|"item.completed","item":{"id","type":"command_execution","command":"/bin/zsh -lc '…'",
    "aggregated_output","exit_code","status"}}`; `"type":"agent_message","text"`; `"type":"error","message"`;
    `"type":"file_change","changes":[{"path","kind"}]` (from Codex's source; not yet seen live).
  - `{"type":"turn.completed","usage":{"input_tokens","cached_input_tokens","output_tokens","reasoning_output_tokens"}}`
  - `{"type":"turn.failed","error":{"message"}}`, `{"type":"error","message"}`
  - The stream never names the model. The meter takes it from `-m`/`--model` in the command, else "codex".
- **Nemotron**: Graphene's own executor. It writes its rows itself, per turn, in the same shapes.
- **Anything else**: no meter. Time and the log's tail, as today, and the live row says "no meter".

## What it writes (node_log rows on the leaf, actor `run:<executor>`, session = the run's session)

| kind | detail | when |
|---|---|---|
| `usage` | `{"model", "calls": 1, "prompt_tokens", "completion_tokens", "dollars", "endpoint", "attempt", "turn"}` | each turn: a Claude message, a Codex `turn.completed`, a Nemotron call |
| `usage` | `{"model", "calls": 0, "prompt_tokens": 0, "completion_tokens": 0, "dollars": reported − counted, "endpoint", "attempt", "turns", "reported"}` | Claude's `result`: settles the turns to what Claude Code reports. No `turn` key. |
| `did` | `{"attempt", "tool", "target", "verb"}` | each tool call: `verb` is reading, editing, running or searching |
| `said` | `{"attempt", "text"}` | each thing the agent says, cut to 400 characters |
| `ended` | `{"attempt", "exit", "seconds", "meter": "claude"\|"codex"\|"nemotron"\|null, "unread": n}` | when the executor's process ends |

- `prompt_tokens` counts every input token: Claude's `input_tokens + cache_creation_input_tokens +
  cache_read_input_tokens`, Codex's `input_tokens` (cached ones are inside it).
- `endpoint` is `"claude code"`, `"codex"`, `"token factory"` or `"a stand-in"`.
- `dollars` is at list price. Claude: the model's list price from `meter.PRICES` (cache writes at 1.25× input
  for 5 minutes, 2× for an hour; cache reads at the listed rate), so a turn's dollars climb as it runs; the
  `result` row settles the sum to `total_cost_usd`. Codex: its tokens at Token Factory's list price when the
  model is on Token Factory's live list; otherwise `"dollars": 0, "priced": false`, and the bill says the
  tokens have no list price. Nemotron: Token Factory's live list, as today.
- Rows with a `turn` key are turns; a `usage` row without one closes an attempt or is an older row. Every
  reader that summed `usage` rows still sums them (the status line's bill, `run`'s line, `node show`);
  `node_record.bill()` counts attempts from `ended` rows, or from the rows without a `turn` key in an older
  store, never from the number of rows.

## Which record wins where the hooks and the stream overlap

A Claude Code executor in a run worktree is also seen by the hooks: each tool call lands in `tool_events`
(the hook's record, keyed by `tool_use_id`). The stream's `did` rows are the meter's record. **For the
meter, the stream wins**: turns, tokens, dollars, tool calls and said text are counted from the stream
rows only, and the meter never counts `tool_events`. **For the gate, the hooks win**: what was refused
(`denied`, `refused`, `breach` rows) and what was written are the gate's, and the meter only reads them.
So each tool call is counted once. A session with no stream (a person's own Claude Code session) has
only the hooks' record, and the meter says nothing about it.

## The two clocks

- **Agents**: running executors now; minutes from each attempt's `attempt` row to its `ended` row (now,
  while it runs), summed; dollars from the `usage` rows.
- **You**: acts are the person's own rows in the log (`talk.mine(actor, person)`: accepted, dropped, edited,
  answered, a setting), counted once per timestamp; attended minutes are the distinct minutes holding at
  least one act. "By your keys": it counts what you did, not what you read.

`run` prints one line at the end, for every executor:
`run: 3 done · agents 41 min, $2.87 at list price · you 4 acts, 2 min`.

## The ledger

Under the opening (`GRAPHENE_AGENT_LIVE_USD`), a Claude Code or Codex attempt reserves its worst case on
the night's ledger before it starts (`--max-budget-usd` when the command has it, else $3). It settles at
the attempt's dollars only when the stream gave the whole figure: Claude Code's result was read, or every
Codex turn that started completed. A Codex model with no list price settles at $0, its tokens alone.
Anything else (no stream, a turn stopped or failed) keeps the worst case: it may have been spent. A run
killed outright leaves its holds on its attempt rows, and the next run's sweep settles them before the
night is asked. Nemotron's calls reserve and settle themselves, per call, as before. A run that would
spend does not start past 90% of the cap. The rows carry the purpose from `GRAPHENE_NIGHT_PURPOSE`.
(The review of 03:00 found the first version settled a stopped attempt at $0: `review.md`.)
