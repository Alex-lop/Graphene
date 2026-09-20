# morning.md — 2026-09-20 — the collaboration directive

(Moved: this file and every other agent artifact now live under `docs/process/`. The root is the
product's. Yesterday's is `docs/process/morning-2026-09-19.md`.)

## What I decided, and why

1. **The loop closes. In a terminal, on a real agent, in 45 seconds.** A person shapes two nodes; a
   real `claude -p` is told to work the plan *and*, in the same breath, to fix a typo no node
   covers; the person rewrites node 2 while node 1 runs. Result, asserted from Graphene's log and
   git: the typo write was refused and the file is byte-identical; node 1 is done by a check
   Graphene ran itself; node 2 was done as you left it, not as the agent first read it. Then the
   part I did not plan: refused, the agent **proposed a node for the typo** and asked you to accept
   it. Run it: `docs/proof/proof.sh` (also `stop.sh`, `run.sh`; recorded output beside them).
2. **How the graph binds: one core, both routes.** I spiked both routes and a third thing (no
   hooks at all, driven by Codex, Claude and by hand) before choosing. What held in every spike was
   a check made *out of process, after the agent was gone*: Graphene runs the node's check and asks
   git what changed since the node started. That is the core (`graphene node done`), and it needs
   no vendor. On it: the in-session hooks (your lean, and the route a person sits in) and
   `graphene run` (unattended; its loop has no vendor ceiling). Route 1 alone was not enough: the
   vendor ends a session after ~9 refused stops, and `--max-turns` never fires `Stop` at all.
   Because the core was there, the second route cost 125 lines. No MCP: every executor has a shell.
3. **A finished plan stays in force until you archive or pause it.** The first real agent run did
   both nodes properly, waited until no node was open, then made the forbidden edit and said so:
   "no node was open. Graphene accepted the write." That rule is why run two produced a proposal.
4. **You are in the graph.** A node can be yours; agents cannot take it; what waits on it waits;
   `graphene plan accept` tells you *before* the run what agents can reach alone and what will wait
   for whom; `graphene` says "waiting on a person: rate (yours to do)".
5. **THE TEST DOES NOT SHOW GRAPHENE HELPING. Read this one.** Twelve stand-in runs (3 tasks × 2
   arms × 2), audited by an agent told to assume I had rigged it: the paragraph arm was cheaper
   ($0.18 vs $0.26), faster (133 s vs 254 s) and typed less (896 vs 1342 chars) on every task.
   Files outside intent: zero in *both* arms. No write was ever refused, so enforcement was never
   exercised. One real "no, not that" in twelve runs. Both arms passed every hidden check. The one
   thing the plan arm demonstrably did: in both `report` runs the agent's own proposal contained two
   things you would have rejected on sight, and the person removed them by editing the plan before
   any code existed. Why it may mean little: the "people" were language models writing dense,
   precise paragraphs with the intent card in context; the repos were toys sonnet gets right from
   a paragraph; n = 2. Why it may mean a lot: on small tasks a good paragraph is enough, and
   Graphene costs twice the time. `docs/test/results-2026-09-20.md`. **Your ten minutes decide
   this, not mine:** `docs/test/PROTOCOL.md`, top section.

## What you can open right now

```
cd ~/Desktop/AllThingsAgenticHackathon
docs/proof/proof.sh            # the loop on a real agent, ~45 s, a few cents; prints ok/FALSE lines
graphene                       # this repo's plan: what I propose next, waiting for you to accept
graphene ui                    # the plan as the first screen; you can edit it there
```

Read first, in this order: `README.md`, `docs/DIRECTION.md` (yours to edit; your edits bind the next
run), `docs/test/results-2026-09-20.md`.

## Do these today (minutes in brackets)

1. [2] `docs/proof/proof.sh`. Watch a plan hold an agent.
2. [10] The test, yourself, one task, both arms, with a timer: `docs/test/PROTOCOL.md`.
3. [1] `graphene init` in any repo you set up before today: it adds the one new event, `PreToolUse`.
   I ran it in this repo (it edits `.claude/settings.json` here, never `~/.claude`).
4. [5] Edit `docs/DIRECTION.md`. Strike what you disagree with.
5. Still yours from before: PyPI publisher, the tag, `bashEditDiffEnabled` and `cleanupPeriodDays`
   in `~/.claude/settings.json`. Nothing was published, tagged or renamed.

(state of main, verification, not verified, disagreements, rollback and questions follow below;
filled in at the end of the night)
