# Practice: the first hour with the key
| | 1 access | 2 local leaf | 3 Sandbox | 4 escape | 5 recorded | 6 A leaf + B′ | 7 demo |
|---|---|---|---|---|---|---|---|
| cap, min | $0.25, 1 | $0.50, 2-5 | $0.50, 3-8 | $0.05, 2-5 | $0.50, 2-5 | $3, 15-40 | $3, 10-30 |

The caps are Token Factory's only; rung 4 calls no model, so its cap bounds nothing. Sandboxes (rungs 1,
3, 4, 6 and 7, live) are free in the beta: "runs don't consume your credits", Nebius's Sandboxes page as
the search index quoted it on 2026-09-29 (tokenfactory.nebius.com/sandboxes draws in a browser only; no
Nebius page states a price). Each sandbox rung still counts its operations and seconds. A 403 from
Sandboxes is a project without access: ask at tokenfactory.nebius.com/sandboxes/about; 2 and 5 need none.
Dry: `docs/test/practice.sh --dry`, all seven on stand-ins, same caps, about 3 minutes; rungs 3, 4,
6 and 7 need Docker running.
Live (minutes guessed): `export NEBIUS_API_KEY=… NEBIUS_PROJECT_ID=…` in `~/.zshenv`, then, in
your own terminal, not Claude Code (its `!` lines carry CLAUDECODE, which rungs 2-7 refuse unless
opened, below), `docs/test/practice.sh` per rung: rung 1 runs the access check itself (in Claude
Code, it prints a `!` line for it). `… N` reruns N with a fresh cap: $7.80 of Token Factory + calls
in flight is one pass each.
An agent climbs only when you open it: start its session from a shell with the night's cap set
(`export GRAPHENE_AGENT_LIVE_USD=10`, then `claude`), and rungs 2-7 run there. While it is set, every
live call and Sandbox operation, the ladder's or any other, goes on one night's bill
(`~/.graphene/night/<date>.jsonl`, or `GRAPHENE_NIGHT_LEDGER`), capped at the lower of that figure and
$10: a call that would pass it is refused unsent, nothing new starts past 80% of it, and a rerun does
not reset it. Sandboxes are counted in operations and minutes, at $0 (free in the beta, above).
`practice.sh night` prints the bill. Everything made under it is practice: `evidence.py` refuses it, so
unset it before a registered run.
Prototypes (not a rung): `docs/test/practice.sh prototypes` runs cover, note and precheck on a fixed
plan in a fresh feeds, 4-5 Nano calls and one sandbox fork (skipped, and said, with no Sandboxes),
capped at $0.05; like rungs 2-7 it needs the opening in Claude Code. `--dry prototypes` on stand-ins.
