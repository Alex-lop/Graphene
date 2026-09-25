# The demo page

`docs/demo/index.html` is a run's record as one read-only web page: the goal, the plan's tree,
each leaf's state, and each leaf's record. It is what `graphene ui` shows on the machine where the
run happened, with its data inlined, no token and no way to write. It is drawn from the
repository's `.graphene/` store alone, so a run whose executors keep no records of their own
(whatever `graphene run --with` starts, other than Claude Code) is drawn in full. Until the demo
run has been made, there is no `index.html` here, and the workflow below refuses to publish.

## Making it

In the repository the run happened in, once `graphene run --parallel N` has finished:

    graphene ui --export <this repository>/docs/demo/index.html

That is all. The page is one file (about 330 KB, most of it the page's own script): its script,
its style and the run's data are inlined, and it fetches nothing, so any static host serves it.
`tests/test_demo_export.py` makes one from a real `graphene run --parallel 2` with a scripted
executor and reads it back.

What a leaf's record on the page holds, from its log: who started it, each attempt, each refused
`done` with the paths it was refused over, each check Graphene ran by its command and result, what
had changed when it finished, that it landed and which paths it brought, and why it was handed back.

What stays on the machine: what a check printed (a check is named by its command and its result),
and anything after the first line of a reason (the reason `graphene run` hands a leaf back with
quotes the refusal, and a failed check's output is under it); the page's token; the log's absolute
paths (the leaf's worktree, the executor's output file, the checkout it was merged into).

Read the page before you publish it. It does carry the person's name as the actor of their own
acts (`GRAPHENE_PERSON`, else `USER`), the first word of `--with` as the executor's name (its
command name, never its path), and every check command as it was written: a check that names an
absolute path or a secret publishes it.

The page's second screen, the record of a run, is drawn from Claude Code's sessions only. When the
repository has none, that screen is shut and its button says why.

## Hosting it

`.github/workflows/pages.yml` publishes this directory to GitHub Pages. It runs only when someone
starts it (Actions, then Pages, then Run workflow), and stops before publishing unless
`docs/demo/index.html` is there and is a read-only export. Pages is not enabled for this
repository: enabling it (Settings, then Pages, then Source: GitHub Actions) and running the
workflow are the owner's. The page would then be at `https://alex-lop.github.io/Graphene/`.
