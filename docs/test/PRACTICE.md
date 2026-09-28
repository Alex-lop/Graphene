# Practice: the first hour with the key

Once: `export NEBIUS_API_KEY=… NEBIUS_PROJECT_ID=…` in `~/.zshenv`, and open a terminal of its own (rungs 6 and 7 run for up to 40 minutes). Then type `docs/test/practice.sh` once per rung: it runs the next rung not yet passed and prints PASS or FAIL, the bill so far, how long it took and the next command; a FAIL says what it most likely means and what to try. Each rung has its own spend cap, at Token Factory's list price (live times are estimates until the first climb):

1. **Access** (1 min, $0.25). Inside a Claude Code session the rung runs nothing and prints the line to type yourself with `!`, since the session's classifier refuses it to an agent.
2. **One leaf local** on Nemotron (2-5 min, $0.50). 3. **One leaf in a Sandbox** (3-8 min, $0.50).
4. **The escape test in ConTree** (2-5 min, $0.05: no model calls; Sandboxes are billed apart, not in the bill).
5. **A recorded leaf**, replayed with `graphene demo` (2-5 min, $0.50).
6. **Arms A and B on feeds**, one run each (15-40 min, $3). It needs the sealed `docs/test/tasks/feeds/paragraph.md`, which it never prints.
7. **The demo run**, recorded (10-30 min, $3): `.graphene/practice/demo.jsonl`, for `graphene demo` and CI.

All seven: at most $7.80, plus the calls already in flight when a cap is reached. `practice.sh status` lists every rung and the bill; `practice.sh N` runs rung N again; `practice.sh --dry` climbs the whole ladder against the scripted fake and Docker, with no key, in about two minutes.
