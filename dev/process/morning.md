# The editor night, 26 to 27 October 2026

*Written through the night; this is its last state. The record of every lane is in `dev/process/editor/`.*

## Your 15 minutes

A fresh terminal. Each block says what it shows. [TIMED]

```sh
# 1. The night's build in a clone of its own, and the CLI it needs (about 3 minutes)
git clone -q -b night/editor https://github.com/Alex-lop/Graphene ~/graphene-night && cd ~/graphene-night
uv sync -q && (cd editors/vscode && npm ci --silent && npm run package)
uv tool install --force --from . 'graphene-map[nemotron]'   # your graphene becomes 0.9.0; undo: --force graphene-map==0.8.0
graphene --version                                           # graphene 0.9.0
```

```sh
# 2. Install the extension in VS Code and in Cursor
code --install-extension editors/vscode/graphene-0.9.0.vsix
cursor --install-extension editors/vscode/graphene-0.9.0.vsix
```

3. **Watch the Demo.** In VS Code, the palette: **Graphene: Watch the Demo**. A tab plays the auto replay. Its first
   line says `replay · a scripted stand-in, no model ran`, three tasks race with three forks each, the check
   keeps one fork a task, the goal's check goes red, and the fix lands. No key and no network.

```sh
# 4. A race of your own, free, against the stand-in, watched in VS Code
cd ~/graphene-night && ENDPOINT=standin PAUSE=1 dev/proof/auto.sh ~/graphene-try
#    at "open ... in VS Code and start recording, then press Enter": `code ~/graphene-try`, then Enter here
```

   The side bar leads with **Needs You**, then the graph as lanes, then **Agents**. The tab (**Graphene: Show
   Plan Graph**) shows the race, each fork's lines and seconds quiet, and the kept one with why. Its header
   says `against the scripted stand-in`.

```sh
# 5. Something that needs you: auto off, then an agent's proposal
cd ~/graphene-try && graphene config set auto off
CLAUDECODE=1 graphene node add "the README says how to use --top" --scope README.md --check "grep -q -- --top README.md"
```

   **Needs You** shows the proposal: click its Accept. Then click a done task in the graph, and its **Open
   changes**: VS Code's own diff editor opens what it landed.

6. No live take ran tonight, so there is no live take to replay.

## Tuesday

**The two listings, once (about 20 minutes).** `docs/RELEASING.md`, "The VS Code extension", "First time only",
has every click. In short:
1. The Marketplace: sign in at <https://marketplace.visualstudio.com/manage> and create the publisher `alex-lop`
   (free on 27 October). At <https://dev.azure.com>, make a personal access token for **All accessible
   organizations** with the scope **Marketplace: Manage**. Check it: `cd editors/vscode && VSCE_PAT=<token> npx
   vsce verify-pat alex-lop`.
2. Open VSX: sign in at <https://open-vsx.org> with GitHub, link an Eclipse account, sign the publisher
   agreement, make an access token, then `npx --yes ovsx@1.3.0 create-namespace alex-lop -p <token>`.
3. The secrets: `gh secret set VSCE_PAT` and `gh secret set OVSX_PAT`.

**The release, 0.9.0.** Merge PR #55 on GitHub. Date the CHANGELOG's 0.9.0 heading (it says "unreleased") in a
commit of its own on `main`. Then:

```sh
git push origin main          # PyPI shows the README, which loads its pictures from main
git tag v0.9.0 && git push origin v0.9.0
gh run watch                  # the suite on the tag, the wheel, PyPI, then the published demo --cheat
(cd editors/vscode && npm ci && npm run package)
gh release create v0.9.0 --title "Graphene 0.9.0" --notes-file dev/launch/release-notes.md \
  editors/vscode/graphene-0.9.0.vsix
gh run watch                  # publish-vscode.yml: the same .vsix to the Marketplace and to Open VSX
```

**The live take, if you still need to film it.** From your checkout, after `uv sync`, with your key:
`PAUSE=1 RECORD=$PWD/take.jsonl dev/proof/auto.sh ~/graphene-take`. It prints the line that installs the night's
`.vsix`, makes the repo, runs `graphene init`, and waits: open `~/graphene-take` in VS Code, start recording, press
Enter. `ENDPOINT=standin` runs the same take free, to rehearse. `dev/process/editor/take/` has a screenshot of
each beat from the rehearsal.

**The b-roll** is in `~/graphene-film/broll/`, each clip named for its beat in `dev/launch/video-auto.md`. [BROLL]

## The brief

1. **Before and after**, the same scripts back to back (`dev/process/editor/after/README.md`). The smallest text
   in the side bar went from 4.6 px to 11 px at every width. A store write reaches the screen in 31 ms at the
   median, against 123. Idle, the app takes 2.3 % of a core, against 10.7. The editor covers 9 of the cockpit's
   17 moves whole, against 4. The first graph takes 2.5 s either way. A stranger reached the first graph in about
   7 minutes, against 11, and steered in about 14, against 18, with 11 guesses against 9 (`after/stranger.md`).
2. **Look at these first**: `dev/process/editor/after/code-panel-1280x800-dark.png` (the race),
   `after/code-sidebar-320-dark.png` beside `before/code-sidebar-320-dark.png` (the side bar). [BROLL-ONE]
3. **The review** (`dev/process/editor/review.md`). Auto mode, the envelope and the gate: nine faults, five high,
   all fixed with a failing test first, each confirmed by the other reviewer. The extension and the seams between
   the lanes: five readers found 29. [REVIEW-EXT]
4. **Your notes.** `~/graphene-notes.md` did not exist.
5. **The browser spike** (`dev/process/editor/browser-spike.md`, $0.02 of Haiku). PreToolUse and PostToolUse fire
   for MCP tools on Claude Code 2.1.311, 18 calls of 18. A screenshot reaches the hook as 19 to 300 KB of base64,
   and the store keeps 9 KB of it: a trail needs the PNG kept beside the store.
6. **Decide.**
   - Auto…'s first choice is now Plan first: with auto on, Plan and run landed a stranger's race before they saw
     it. Default: keep it. To flip it, swap the two items in Auto…'s pick (`extension.ts`).
   - Your `~/.zshenv` exports your Token Factory key into every shell, agents' and VS Code's terminals included.
     Default: leave it; the harness no longer reads it. Option: `graphene key set`, then remove the line.
   - The branch has [COMMITS] commits, over the 30 to 50 you want: it was pushed early for CI, so it could not be
     folded. Default: merge it as usual. Option: squash and merge.
7. **Broken or risky.** A usage limit stopped every agent from 02:15 to 04:41, and lane 2a's builder stalled from
   00:34 to 02:00 on a prompt nobody could answer: the night lost its second review round to them. The extension
   runs the first `graphene` it finds and does not say which; on a machine with two, it can run the older one.
   Two things may be on your screen: a VS Code window "Welcome — wordkit" from 00:31, and a WezTerm prompt (answer
   Don't Allow).

## How the night ran

The work was in a fresh clone of GitHub's `main`, on `night/editor`, never in your checkout.
`dev/process/editor/CONTRACT.md` said which lane wrote which file and the CLI shapes the editor coded against.
Each lane built in its own clone; a skeptic who didn't write it reviewed it; a fixer paired each fault with the
test that failed before it. Subagents ran on Fable 5.1 until the usage limit at 02:15, and on Opus 5.5 after.

| Lane | What it left |
|---|---|
| 0 | `editors/vscode/e2e/`: real VS Code and Cursor driven by Playwright, profiles of their own; `dev/proof/standin.py`; the before |
| 1 | the graph: lanes when narrow, nothing under 11 px, the race's numbers on each fork, the kept one and why |
| 2a | Needs You first, Agents, the stream with a fallback poll, first run without hunting, Set Key on a refused key |
| 2b | diffs in the diff editor, the plan as a text tab with refusals on their lines, a step in a sentence, Watch the Demo, files you open |
| 3 | `state --json --watch`, `node diff --json`, `plan edit --from -`, `ask --step`, `demo --into`, the snapshot's new keys |
| 4 | the listing README, the icon, `publish-vscode.yml`, RELEASING's first-time steps, CI's end-to-end job |
| 5 | two reviews: `dev/process/editor/review.md` |
| 6 | the README's VS Code section on a real screenshot, the listing, HACKATHON, COMPARE, claims, the 0.9.0 notes |
| 7 | `ENDPOINT=standin` and `PAUSE=1` in `dev/proof/auto.sh`, the rehearsal, the b-roll |
| 8 | `dev/process/editor/browser-spike.md` |

Not done: dogfooding a lane through Graphene with Claude Code executors (no time after the limit), Cursor's after
screenshots (its check passes), and a second seam review round.

Decisions taken tonight are in `dev/DIRECTION.md`, 196 on.

## Branches and rollback

- `main` on GitHub was `2da29a52a1b38031418506f5a7a6929c121f673b` when the night started. That is the rollback.
- `night/editor` is draft PR #55 (https://github.com/Alex-lop/Graphene/pull/55). Nothing else was pushed.
- The lanes' own branches live only in the night's scratch clones; their work is on `night/editor`.
