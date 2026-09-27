These screens come from a scripted stand-in for Token Factory (`tests/fake_tokenfactory.py`), not Nemotron: no model ran, the models are named `-fake`, and each SVG's title says so.

# The forks and the step up, on screen (the winning directive, item 3)

`shoot.py` made every file here. It makes a repository with two leaves in a scratch directory (the screen's home, so the top line reads `the plan of ~/feeds`) and runs `graphene run --with "nemotron --model Nemotron-3-Nano-fake --model Nemotron-3-Super-fake --forks 3" --attempts 2` there, in the local placement, against the stand-in. The stand-in's replies hold each moment still while `graphene watch` is taken with Textual's headless pilot at 80x24 and 120x36 (`.svg`, and the screen's text in `.txt`):

| name | the moment | the cursor |
|---|---|---|
| `forks-running` | greet's three forks, each waiting on its first answer | on greet |
| `fork-lost` | fork 2's check passed; fork 1 was stopped, so it lost; fork 3 still waits on an answer | on greet |
| `stepped-up` | farewell's attempt 1 was refused on Nano; its three forks run again on Super | on the goal: nobody pointed at the leaf |
| `stepped-up-pane` | the same moment | on farewell |

`before/` is `ebf7a95` (the commit this work started from, a scratch worktree of it), `after/` is this branch. The script finds each moment in the stand-in's requests and the executor's own output, never in the store, so the same file took both.

What the difference shows, at 80x24:

- **Before**, the tree has one row for greet, `running`, and nothing under it. Nothing says there are three conversations, that one passed or that one lost; the pane's `last` line shows whichever line the executor printed last. farewell's pane names Super only inside the executor's last line of output, its bill names only Nano, and nothing says it stepped up or why.
- **After**, each fork is a row under its leaf in the one row grammar: its model where a title goes, `fork 1` where an id goes, its state in the word's column (`running` yellow, `passed` green, `lost` dim). With the cursor on the goal, the bottom line says `farewell stepped up to Nemotron-3-Super-fake: attempt 1 refused: farewell is…`; the leaf's pane says `model  Nemotron-3-Super-fake, stepped up from Nemotron-3-Nano-fake: attempt 1 refused: …`.

Take them again (a new scratch repository each time):

    uv run python docs/process/winning/screens/shoot.py --out docs/process/winning/screens/after

From a live run's store, as it is now (run it while the run goes, then read the files before committing them: a sandbox leaf's pane names the first twelve characters of its image):

    uv run python docs/process/winning/screens/shoot.py --repo <the repository> --label live --keys j --out <a directory>

Not shown here, and not verified: any of this against Token Factory or in a ConTree sandbox (this session has no key); a leaf's sandbox line (these forks ran in the local placement, so the panes have none; `tests/test_escape.py` checks the sandbox rows in the Docker stand-in, and `tests/test_tui.py` the pane that reads them).
