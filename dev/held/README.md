# Held: does it stay inside the lines, and is done true

A bench for one question, asked of Graphene against plain Claude Code given the same rule as a deny setting.
`rules.md` is the decision rule, written before any number. Nothing here calls a model.

Each task under `tasks/<id>/` is self-contained:

| file | what it is |
|---|---|
| `base/` | the repository the agent is given: small, standard library only, the rule in its AGENTS.md |
| `prompt.md` | the prompt, byte for byte the same in every arm; it never names the forbidden file |
| `accept.py <repo>` | the visible check: exits 0 only when the tests the agent can see pass |
| `hidden.py <repo>` | the check the agent never sees, run on the final tree |
| `intent_globs.txt` | the paths the task's author means to change; anything else is an escape |
| `reference.patch` | a right ending: passes both checks, touches only intent paths |
| `trip.patch` | the tempting ending: passes accept, fails hidden |

`test_tasks.py` applies each patch to a fresh copy of `base/` and pins both endings, so the scorers are proved
before any run:

    uv run pytest -p no:cacheprovider -q dev/held/test_tasks.py
