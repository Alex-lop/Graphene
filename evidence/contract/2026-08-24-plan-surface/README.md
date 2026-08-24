# The plan surface, exactly as it prints — 2026-08-24

`plan-surface.txt` is a verbatim capture of the terminal for the whole
pre-execution loop: propose, orient, inspect one node in full, export, edit,
revise, lint, diff, and the table again on the new revision.

It was produced credential-free with `--driver scripted-local` against a
disposable fixture repository, so it contacts no provider and spends nothing.
Nothing in it is re-wrapped, re-ordered or tidied. The only edit is path
substitution: the scratch target directory is written as `TARGET` and the
scratch state directory as `SCRATCH`, because both are temporary paths that
would not exist for a reader.

The edit shown is the one `scripts/demo_plan_edit.py` makes — it gives one
worker read access to a file another worker owns. That is a scope expansion,
which is why `plan diff` marks it `** SCOPE EXPANSION **`.

**What this capture is:** the shape and wording of the surface, and proof that
the loop runs end to end without a provider.

**What it is not:** a live run. The plan here comes from the scripted fixture,
not from a model. The filmed sequence uses `--driver gemini-adk`, and no live
capture of the edit beat exists yet.
