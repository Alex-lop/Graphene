# Graphene: the process archive

This branch holds the working notes of the agent runs that built Graphene. It is not the product.

The files came from `docs/process/` on branch `cut` at `66125f0`. That commit is origin/main `4e5a2a9`
plus the cut directive. The cut moved them off `main` to keep the repo small. Each file keeps its path.

Three things stayed on `main`: `docs/process/directives/`, `docs/process/morning.md` and
`docs/process/cut/`.

What is here:

- `docs/process/morning-*.md`: the old morning briefs.
- `docs/process/fields/`: the Lean and bio spikes, about 11 MB.
- `docs/process/nemotron/`, `polish/`, `reports/`, `shaping/`, `winning/`: each run's notes, screens and reports.
- `docs/process/field.md`, `ideas.md`, `strategy-summary.md`.

This branch has no parent and shares no history with `main`. The files' history up to `4e5a2a9` is on
`main`: `git log 4e5a2a9 -- docs/process/ideas.md`.

To look at it:

```sh
git fetch origin process
git show origin/process:docs/process/ideas.md
git worktree add ../graphene-process origin/process   # the whole archive, beside your checkout
```

On GitHub: https://github.com/Alex-lop/Graphene/tree/process/docs/process
