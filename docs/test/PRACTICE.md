# Practice: the first hour with the key
| | 1 access | 2 local leaf | 3 Sandbox | 4 escape | 5 recorded | 6 arms A+B | 7 demo |
|---|---|---|---|---|---|---|---|
| cap, min | $0.25, 1 | $0.50, 2-5 | $0.50, 3-8 | $0.05, 2-5 | $0.50, 2-5 | $3, 15-40 | $3, 10-30 |

The caps are Token Factory's only: Sandboxes (rungs 1, 3, 4, 6 and 7, live) are billed apart, under
no cap, at a price not read; rung 4 calls no model, so its cap bounds nothing.
Dry: `docs/test/practice.sh --dry`, all seven on stand-ins, same caps, about 3 minutes; rungs 3, 4,
6 and 7 need Docker running.
Live (minutes guessed): `export NEBIUS_API_KEY=… NEBIUS_PROJECT_ID=…` in `~/.zshenv`, then, in
your own terminal, not Claude Code (its `!` lines carry CLAUDECODE, which rungs 2-7 refuse),
`docs/test/practice.sh` per rung: rung 1 runs the access check itself (in Claude Code, it prints
a `!` line for it). `… N` reruns N with a fresh cap: $7.80 of Token Factory + calls in flight
is one pass each, plus the Sandboxes.
