# The live take, rehearsed against the stand-in

The editor night, 27 October 2026, lane 7. Everything here ran against `dev/proof/standin.py`: a script
answered as Nemotron, no model ran, nothing was spent. No key was set and Token Factory was never reached.
The screenshots are from real VS Code 1.143.1 at 1920x1080, Dark Modern, in a profile of its own with the
night's `.vsix` installed. The terminal clips are `vhs` takes of the two replays a judge runs.

## The commands, in the order they ran

```
uv sync                                        # the branch's graphene, in .venv/bin
cd editors/vscode && npm ci && npm run package # graphene-0.8.0.vsix
cd e2e && npm ci                               # the harness (Playwright's Electron driver)
```

The take itself, as Alex runs it on Tuesday, with the stand-in in place of his key:

```
ENDPOINT=standin PAUSE=1 RECORD=take.jsonl dev/proof/auto.sh /tmp/gv-take-1/wordkit
```

The script puts the clone's `.venv/bin` first on PATH itself when `uv sync` made it, so the installed
`graphene` tool in `~/.local/bin` does not run the take or the stand-in. Its first lines are the install
lines for his own VS Code and Cursor, printed and never run. Then it starts the stand-in and says so, makes
wordkit, runs `graphene init`, and waits: "open DIR in VS Code and start recording, then press Enter". At
that pause the rehearsal opened the folder in the harness's VS Code, pressed Enter for him, and shot each
beat as `graphene state --json` first showed it:

```
E2E_TMP=/tmp/gv-take-1 node dev/process/editor/take/rehearse.mjs --clone . --dir /tmp/gv-take-1/wordkit --out shots
```

`rehearse.mjs` is that whole sequence in one script (it needs the harness's `npm ci`). The race took 42 s
from Enter to the bill. `beats.txt` is its log: the second each beat was seen, with the store's `auto`
line and every task's forks at that moment.

## The screenshots, by beat

| File | Beat | What it shows |
|---|---|---|
| `beat6-editor-paused-after-init.png` | 6 | the pause: the folder open, nothing planned yet |
| `beat2-aha-race-fans-out.png` | 2 | the race fanning out: three tasks, the first with its three forks running |
| `beat6-editor-explorer-owners.png` | 6 | the Explorer during the race: `cli.py` marked 1, `clean.py` marked 3 |
| `beat3-check-a-fork-kept.png` | 3 | two tasks done, each with its fork kept and why, one still racing |
| `beat3-check-goal-red.png` | 3 | the goal's check red: `FAIL: test_a_hyphen_splits_a_word`, round 2 fixing |
| `beat3-check-the-fix-races.png` | 3 | the fix as a fourth task, three forks racing it |
| `beat3-check-the-fix-lands.png` | 3 | the fix landed, 4 of 4 done |
| `beat4-real-the-end.png` | 4 | the end: auto done, the goal's check passed in round 2, $0.02 of $2.00 |
| `beat6-editor-1280-the-end.png` | 6 | the same end at 1280x800, a laptop's window |

Nothing on the editor's screen says the race was a stand-in's: the snapshot has no field for it, and the
replay line only shows for a `demo --into` store. The terminal's take says it in its third line, and the
record's bill says "a stand-in's usage". The dollars on screen are the stand-in's made-up prices.

## The terminal's b-roll

The tapes here film the two replays into `~/graphene-film/broll/`, never the repository. Each replay's
top line says what made it, a scripted stand-in, and stays in frame. Run them from `~/graphene-film` with
the branch's graphene first on PATH:

```
mkdir -p ~/graphene-film/broll && cd ~/graphene-film
export PATH=<clone>/.venv/bin:$PATH GRAPHENE_KEYCHAIN=off NEBIUS_API_KEY=fake-key   # the replays need no key
vhs <clone>/dev/process/editor/take/beat2-aha-demo-auto.tape
vhs <clone>/dev/process/editor/take/beat5-locks-demo-cheat.tape
```

- `beat2-aha-demo-auto.tape`: `graphene demo --auto --speed 4`, 65 changes at half a second each, 33 s;
  it makes `beat2-aha-demo-auto.mp4` and `.gif`, 1920x1080.
- `beat5-locks-demo-cheat.tape`: `graphene demo --cheat`, 25 lines, all in frame; `beat5-locks-demo-cheat.mp4`
  and `.gif`, 1920x1080.
