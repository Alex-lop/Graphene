# morning.md — 2026-09-21 — the tree directive

(Kept current at every milestone of the run; this is the state as of the last commit on `tree`.
Yesterday's is `docs/process/morning-2026-09-20.md`.)

## 1. What you can run in five minutes

```
cd ~/Desktop/AllThingsAgenticHackathon && git checkout tree
docs/proof/parallel.sh     # two real agents at once, a worktree each, on a tree; ~30 s, some cents; prints ok/FALSE
docs/proof/tuesday.sh      # a plan in force, and you type an ordinary request: no refusal, no command; then "yes" accepts
graphene watch             # in any repo with a plan: the tree, live (Ctrl-C leaves)
```

Recorded output of both scripts from tonight: `docs/proof/2026-09-21-parallel.txt`, `-tuesday.txt`.

## 2. What is waiting on you

Nothing blocks. Decisions 13 to 24 in `docs/DIRECTION.md` are tonight's; strike what you disagree with.
The three I would look at first: 18 (a typed request is a leaf that may touch anything unless you
write `scope:`), 20 (no terminal is still you), 21 (`run --parallel` commits and merges on its own
branches).

## Rollback

`main` before tonight: `6cece1c`. Nothing has touched `main` yet; the work is on `tree` (pushed, CI green).
```
git checkout main && git reset --hard 6cece1c      # only if tree is ever merged and you want it out
```
A store this version has opened is version 4 (no table changed; a node's JSON gained `parent` and
`aside`). 0.3 refuses it in words. To go back in a repo whose store 0.4 has touched:
```
sqlite3 .graphene/graphene.db "UPDATE nodes SET data = json_remove(data, '$.parent', '$.aside'); PRAGMA user_version = 3"
```
(Run tonight against 0.3's code from `6cece1c` in a scratch repo: before it, 0.3 says "written by a newer
graphene"; after it, 0.3 prints the plan. A sub-goal shows there as a node with no scope.)

(Sections 3 and 4, the map of the code and what was verified, are written when the run closes.)
