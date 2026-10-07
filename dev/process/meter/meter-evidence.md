# Lane 2 evidence: the meter, live, on three executors

Run on 7 October between 01:04 and 01:32, on the feeds task, with `dev/test/meter_live.py`: Graphene from a
wheel of the branch, installed as a tool; the person a script with no agent's mark; `graphene run
--parallel 2` with each executor; `graphene watch` drawn headless every 10 to 20 seconds at 80 and 120
columns (`dev/screens/meter_shot.py`). Every live call is on the night's ledger, purpose `meter`.

- **Claude Code**: `claude -p … --output-format stream-json --verbose --model sonnet --max-budget-usd 2`.
  Its planner, read-only on Sonnet, planned runs 1 and 2 and the README's run.
- **Codex**: `codex exec --json --sandbox workspace-write` with a Token Factory provider and `-m
  nvidia/nemotron-3-super-120b-a12b`. The ChatGPT login on this machine is revoked, so Codex ran
  Nemotron Super; the stream is Codex's own. A `CODEX_HOME` of its own kept the person's plugins out.
- **Nemotron**: Graphene's executor, Nano then Super, on this machine.
- Codex and Nemotron got the tree Claude Code's planner proposed in run 1 (`tree.txt`, through a planner
  that prints it), so the three executors worked the same plan.

## The bill line against the ledger

| executor | run | bill line | bill $ | ledger $ | Claude's own $ | accept | held-out |
|---|---|---|---|---|---|---|---|
| Claude Code | 1 | `run: 3 done · agents 2 min, $0.4560 at list price · you 0 acts, 0 min` | 0.4560 | 0.4560 | 0.4560 | 18/20 | 12/12 |
| Claude Code | 2 | `run: 4 done · agents 2 min, $0.5812 at list price · you 0 acts, 0 min` | 0.5812 | 0.5812 | 0.5812 | 18/20 | 12/12 |
| Claude Code | README | `run: 2 done · agents <1 min, $0.3009 at list price · you 0 acts, 0 min` | 0.3009 | 0.3009 | 0.3009 | 18/20 | 12/12 |
| Codex | 1 | `run: 3 done · agents 6 min, $0.3669 at list price · you 0 acts, 0 min` | 0.3669 | 0.3669 | – | 17/20 | 12/12 |
| Codex | 2 | `run: 3 done · agents 5 min, $0.5011 at list price · you 0 acts, 0 min` | 0.5011 | 0.5011 | – | 17/20 | 12/12 |
| Nemotron | 1 | `run: 1 done, 1 came back (xml-read) · agents 7 min, $0.2258 at list price · you 0 acts, 0 min` | 0.2258 | 0.2258 | – | 11/20 | 0/12 |
| Nemotron | 2 | `run: 3 done · agents 10 min, $0.0998 at list price · you 0 acts, 0 min` | 0.0998 | 0.0998 | – | 18/20 | 12/12 |

- **Ledger $** is the settle rows of the run's own attempts (Claude Code and Codex reserve as `run: <leaf>
  attempt <n>`) or of its leaves' calls (Nemotron's carry the leaf's id). For Claude Code runs 1 and 2
  the harness first summed a time window, which caught the planner's worst case and the statements
  practice running beside them; recounted by leaf, as the harness now does, they match.
- **Claude's own $** is read from the attempts' logs, not from the meter: each session's
  `total_cost_usd`. It matches the meter to the cent each time.
- **Nemotron's ledger is independent of the meter**: Token Factory's calls reserve and settle themselves,
  so its match is the strongest of the three.
- **You 0 acts** is right for these runs: the person accepted before `run` and touched nothing during it.
  The status line counts the whole plan (`you 2 acts ~1m`).

## The screens

`screens/` holds one of each, as drawn: `claude-80.txt` and `claude-120.txt` (the README's run, mid-run),
`codex-80.txt` and `codex-120.txt`, `nemotron-80.txt` and `nemotron-120.txt`, and one leaf's `node show` for
each executor. The README's image is `docs/assets/meter.svg`, the Claude Code screen at 80 columns.

At 80 columns each running leaf takes two rows:

```
 ● xml-feed · claude sonnet-5-5 · attempt 1 · 16s · 3 turns · $0.10
   editing ingest/__init__.py · 0 s ago · 3 files · 89k in, 58 out
 0 on you · agents 1 · <1m · $0.23 · you 2 acts ~2m · none ready · 1/2 done
```

From 110 columns it is one row, the least wanted pieces dropped off the end.

## What the live runs changed

- **Output tokens.** Claude Code's stream counts a message's output before it is written: an Opus attempt
  of 40 turns read "527 out". The result's own usage now settles the tokens as well as the dollars.
- **`$0.00` while Codex works.** Codex reports its tokens only as its turn ends, so its row read `$0.00 · 0
  in, 0 out` for minutes. It now says "no usage yet" (the Codex screens here are from before the fix).
- **Nemotron said `no meter`.** The `ended` row named no meter for Graphene's own executor, whose rows it
  writes itself; it now says `nemotron`.
- **What stays rough.** A file written through a shell command (`cat > a.py`) is not counted as edited:
  only edit tools are. The live tokens count up as the stream says them and settle at the end.

## When the stream cannot be read

`tests/test_run_meter.py::test_a_stream_the_meter_cannot_read_leaves_the_run_as_it_was` runs an
executor that prints garbage and half a JSON line: the run finishes, lands the leaf, writes no usage rows,
counts what it could not read in the `ended` row, and the bill line says "no meter".
