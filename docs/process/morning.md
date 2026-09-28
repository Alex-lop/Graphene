# morning.md — 2026-09-28 — the shaping directive

## The brief

**Do first**
1. The key in `~/.zshenv` (2 min): `export NEBIUS_API_KEY=…  NEBIUS_PROJECT_ID=…`, then a new shell.
2. Take out a fake key a reviewer's test wrote into your login keychain at about 02:00 (10 s; the
   classifier refused it to me): `security delete-generic-password -s graphene -a token-factory`
3. The ladder, in a terminal of your own, not inside Claude Code (about 10 min for rungs 1-3):
   `docs/test/practice.sh`, one rung at a time; `docs/test/PRACTICE.md` is the whole of it.

**New tonight** (all merged into `shaping`; this list changes at every merge)
- The board: the planner asks instead of guessing, you answer with a key: `graphene board`
- The plan as a tree and as a graph of what waits on what: `graphene plan --view dag`, Tab in `watch`
- Settings you state once: `graphene config`, `graphene key check`
- Talking on the tree: `?` on a node in `graphene watch` (why, split, merge, another way)
- Nemotron while you shape, three prototypes against a stand-in: `docs/process/ideas.md`

**Decide**
- (written at the end of the run)

**Broken or risky**
- **The board did not save attention.** Stand-ins shaping one Claude proposal per task spent about twice
  the modelled seconds with the board as with the outline, on 4 of 4 tasks, mostly reading; their plans
  were as faithful or more (`docs/test/results-2026-09-28-shaping.md`, study 2). Lane A's "done" is not met.
- The full study (with executors) never ran: the session's classifier refuses a sub-agent that starts
  Claude Code sessions. Its harness is ready for a session you allow.
- The keychain item above. Every test now runs with the keychain off (`GRAPHENE_KEYCHAIN=off`).

---

(Everything below the brief: decisions, evidence, screens, the state of every branch. The winning
run's morning is `morning-2026-09-26.md`.)

## Where the run stands (03:35)

| Lane | State |
| --- | --- |
| A | The board, the views, talking on the tree: merged. Two board screens were built and tried by three stand-ins (`docs/process/shaping/evaluation.md`); the rows board won a tie, and what the stand-ins stalled on is being fixed now. |
| B | Run through Graphene itself (`docs/process/shaping/as-the-person.md`), reviewed (42 findings, 30 fixed), measured (`sizing.md` on its branch): merged. |
| C | The ladder and its dry climb, the sealed paragraphs, the live pre-registration, arm A's harness: merged. The live directive's draft and the table script: in flight. |
| D | Pre-registered (`docs/test/results-2026-09-28-shaping.md`), deviations written before the first run, twelve runs in flight on build `668c7fd`. |
| E | Twenty ideas ranked (`docs/process/ideas.md`); three prototypes built, reviewed, fixed and merged behind `GRAPHENE_SHAPE`. |
| F | `HACKATHON.md` and the storyboard around shaping: in flight. |
| G | From 06:00. |

## Rollback

Before the first change, `main` on GitHub was `cb2ce54` (your merge of PR #30). This run is the
branch `shaping`, cut from there; nothing touches `main`.

```
git checkout main && git reset --hard cb2ce54
```
