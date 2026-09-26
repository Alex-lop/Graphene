# morning.md — 2026-09-25 (night) — the winning directive

**The blocker: this session had no Token Factory key, so access failed and nothing ran live.**
`NEBIUS_API_KEY`, `NEBIUS_PROJECT_ID` and `NEBIUS_AI_PROJECT` were unset in the shell this run works
in, and there is no `contree` CLI on the path. When I tried to run `uv run python docs/test/access.py`,
Claude Code's auto-mode classifier refused it as "credential exploration", and it refused my look at
where the key might be kept for the same reason. I did not try any way around that. So the directive's
"if access fails" branch is in force: only the work that needs no key, then stop.

To give the next run access (two minutes):

```
# in ~/.zshenv, which every shell Claude Code starts reads:
export NEBIUS_API_KEY=…   NEBIUS_PROJECT_ID=…
# then, in the session, so the classifier sees you run it:
! uv run python docs/test/access.py
```

(Current at every milestone of this run. The Nemotron run's morning is `morning-2026-09-25.md`.)

## Rollback

Before the first change, `main` on GitHub was `ebf7a95` (your merge of PR #29). This run is the
branch `submission`, cut from there; nothing touches `main`.

```
git checkout main && git reset --hard ebf7a95
```

## In progress

The no-key queue, in lanes: item 8 (faults against the fake), item 3 (forks and escalation on the
screen, against a recording that says it is a stand-in), item 7 (the front door, `graphene demo`),
item 9 (the Devpost skeleton), item 11 (the field), item 12 (0.5.0 readiness).
