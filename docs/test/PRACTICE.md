# Practice: the first hour with the key
| | 1 access | 2 local leaf | 3 Sandbox | 4 escape | 5 recorded | 6 A leaf + B′ | 7 demo |
|---|---|---|---|---|---|---|---|
| cap, min | $0.25, 1 | $0.50, 2-5 | $0.50, 3-8 | $0.05, 2-5 | $0.50, 2-5 | $3, 15-40 | $3, 10-30 |

Dry, anywhere: `docs/test/practice.sh --dry`, all seven on stand-ins, same caps, about 3 minutes.
Live (minutes guessed): `export NEBIUS_API_KEY=… NEBIUS_PROJECT_ID=…` in `~/.zshenv`, then, in
your own terminal, not Claude Code (its `!` lines carry CLAUDECODE, which rungs 2-7 refuse),
`docs/test/practice.sh` per rung: rung 1 runs the access check itself (in Claude Code, it prints
a `!` line for it). `… N` reruns N with a fresh cap: $7.80 + calls in flight is one pass each.
