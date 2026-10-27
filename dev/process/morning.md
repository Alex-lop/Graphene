# The editor night, 26 to 27 October 2026

*Written through the night; this is its last state. The record of every lane is in `dev/process/editor/`.*

## Your 15 minutes

A fresh terminal. Each block says what it shows. Run once as written from the pushed branch at 06:00, the harness's
hands in VS Code: 124 s of the machine's time, every step as it says (`dev/process/editor/after/fifteen/`).

```sh
# 1. The night's build in a clone of its own, and the CLI it needs (7 s here, with warm caches)
git clone -q -b night/editor https://github.com/Alex-lop/Graphene ~/graphene-night && cd ~/graphene-night
uv sync -q && (cd editors/vscode && npm ci --silent && npm run package)
uv tool install --force '.[nemotron]'   # your graphene becomes 0.9.0; undo: uv tool install --force 'graphene-map[nemotron]==0.8.0'
graphene --version                                           # graphene 0.9.0
```

```sh
# 2. Install the extension in VS Code and in Cursor (neither `code` nor `cursor` is on this Mac's PATH)
"/Applications/Visual Studio Code.app/Contents/Resources/app/bin/code" --install-extension editors/vscode/graphene-0.9.0.vsix
/Applications/Cursor.app/Contents/Resources/app/bin/cursor --install-extension editors/vscode/graphene-0.9.0.vsix
```

3. **Watch the Demo.** In VS Code, the palette: **Graphene: Watch the Demo**. A tab plays the auto replay. Its first
   line says `replay · a scripted stand-in, no model ran`, three tasks race with three forks each, the check
   keeps one fork a task, the goal's check goes red, and the fix lands. No key and no network.

```sh
# 4. A race of your own, free, against the stand-in, watched in VS Code
cd ~/graphene-night && ENDPOINT=standin PAUSE=1 dev/proof/auto.sh ~/graphene-try
#    at "open ... in VS Code and start recording, then press Enter": open ~/graphene-try in VS Code
#    (File > Open Folder…), then press Enter here
```

   The side bar leads with **Needs You**, then the graph as lanes, then **Agents**. The tab (**Graphene: Show
   Plan Graph**) shows the race, each fork's lines and seconds quiet, and the kept one with why. Its header
   says `against the scripted stand-in`.

```sh
# 5. Something that needs you: auto off, then an agent's proposal
cd ~/graphene-try && graphene config set auto off
CLAUDECODE=1 graphene node add "the README says how to use --top" --scope README.md --check "grep -q -- --top README.md"
```

   **Needs You** shows the proposal: click its ✓ (Accept), or the row itself. Then click a done task in the
   graph tab, and its **Open changes**: VS Code's own diff editor opens what it landed.

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

**The release, 0.9.0.** Merge PR #55 on GitHub, or the folded branch's PR (the brief's question 6). Date the
CHANGELOG's 0.9.0 heading (it says "unreleased") in a commit of its own on `main`. Then:

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

**The b-roll** is in `~/graphene-film/broll/`, each clip 1920x1080 and named for its beat in
`dev/launch/video-auto.md`. Every clip is the scripted stand-in and says so on screen.
- `beat2-aha-demo-auto.mp4` (40 s) and `beat5-locks-demo-cheat.mp4` (13 s): the terminal replays, filmed with vhs.
- `beat6-editor-race-fans-out.mp4` (12 s): three tasks, nine forks racing in the editor tab.
- `beat3-check-a-fork-kept.mp4` (12 s): the chips turn "✓ kept" with why; the goal's check goes red; the fix races.
- `beat6-editor-explorer-owners.mp4` (12 s): the Explorer marks the agents' files with their numbers.
- `beat6-editor-drag-links-two-tasks.mp4` (8 s): a task's dot dragged onto another, the edge drawn.
- `beat6-editor-open-changes-diff.mp4` (9 s): Open changes on a done task, in VS Code's own diff editor.
- `beat6-editor-needs-you-accepted.mp4` (13 s): two proposals in Needs You, accepted from the side bar.

## The brief

1. **Before and after** (`dev/process/editor/after/README.md`): the side bar's smallest text 4.6 → 11 px at every width;
   a write to the screen 123 → 31 ms at the median; idle 10.7 → 2.3 % of a core; the cockpit's moves 4 → 9 of 17 whole.
2. **Look at these first**: `after/code-panel-1280x800-dark.png` (the race), `after/code-sidebar-320-dark.png` beside
   `before/code-sidebar-320-dark.png`, and the clip `~/graphene-film/broll/beat6-editor-race-fans-out.mp4`.
3. **The review** (`dev/process/editor/review.md`): auto mode, the envelope and the gate, 9 faults, 5 high; the extension
   and the seams, 34, 3 high (the demo's panel ran your commands; a planner's title in a toast could run a link; Needs
   You's icons acted on no task). Each is fixed with a test that failed first (a few lines only VS Code runs have none),
   or was gone with another lane's work; a reader who did not find it confirmed each. Open: a crash leaves the demo's dir.
4. **Your notes**: `~/graphene-notes.md` did not exist.
5. **The browser spike** (`browser-spike.md`, $0.02 of Haiku): hooks fire for MCP tools, 18 calls of 18 on Claude Code
   2.1.311; a screenshot reaches the hook as base64 and the store keeps 9 KB of it, so a trail keeps the PNG beside it.
6. **Decide**, each with my default:
   - Auto…'s first choice is Plan first: Plan and run landed a stranger's race before they saw it. Default: keep it.
     To flip it, swap Auto…'s two picks in `extension.ts`.
   - Your `~/.zshenv` exports your Token Factory key into every shell, VS Code's too. Default: leave it, the harness no
     longer reads it. Or `graphene key set`, then drop the line.
   - 82 commits, over your 30 to 50: the branch was pushed early for CI, so it was not folded. Default: merge
     `night/editor-folded` instead, the same tree in 46 (a PR from it; close #55). Or merge #55 as it is.
7. **Broken or risky.** A usage limit stopped every agent 02:15 to 04:41, and lane 2a's builder stalled 00:34 to 02:00:
   no dogfood run. Maybe on your screen: VS Code's "Welcome — wordkit" (00:31) and a WezTerm prompt (Don't Allow).

## How the night ran

The work was in a fresh clone of GitHub's `main`, on `night/editor`, never in your checkout.
`dev/process/editor/CONTRACT.md` said which lane wrote which file and the CLI shapes the editor coded against.
Each lane built in its own clone; a skeptic who didn't write it reviewed it; a fixer paired each fault with the
test that failed before it, and a reader who did not find the fault confirmed the fix. Subagents ran on Fable 5.1, with
Opus 5.5 where Fable gave no answer.

| Lane | What it left |
|---|---|
| 0 | `editors/vscode/e2e/`: real VS Code and Cursor driven by Playwright, profiles of their own; `dev/proof/standin.py`; the before |
| 1 | the graph: lanes when narrow, nothing under 11 px, the race's numbers on each fork, the kept one and why |
| 2a | Needs You first, Agents, the stream with a fallback poll, first run without hunting, Set Key on a refused key |
| 2b | diffs in the diff editor, the plan as a text tab with refusals on their lines, a step in a sentence, Watch the Demo, files you open |
| 3 | `state --json --watch`, `node diff --json`, `plan edit --from -`, `ask --step`, `demo --into`, the snapshot's new keys |
| 4 | the listing README, the icon, `publish-vscode.yml`, RELEASING's first-time steps, CI's end-to-end job |
| 5 | two reviews, 43 faults, each fixed or gone and confirmed: `dev/process/editor/review.md` |
| 6 | the README's VS Code section on a real screenshot, the listing, HACKATHON, COMPARE, claims, the 0.9.0 notes |
| 7 | `ENDPOINT=standin` and `PAUSE=1` in `dev/proof/auto.sh`, the rehearsal, the b-roll |
| 8 | `dev/process/editor/browser-spike.md` |

Not done: dogfooding a lane through Graphene with Claude Code executors (no time after the limit), and a second seam
review round.

Verified at the end, at c05efea3: CI on GitHub, every leg (macOS 3.14: 2,907 passed, 22 skipped); the
extension's types, 110 unit tests, build and smoke; the harness's check in real VS Code and in Cursor; `vsce package`
clean (12 files); the judge's `demo --auto`, `--cheat` and `--live` from the built wheel alone; "Your 15 minutes".

Decisions taken tonight are in `dev/DIRECTION.md`, 196 on.

## Branches and rollback

- `main` on GitHub was `2da29a52a1b38031418506f5a7a6929c121f673b` when the night started. That is the rollback.
- `night/editor` is draft PR #55 (https://github.com/Alex-lop/Graphene/pull/55), 82 commits. Every SHA the record
  names (`dev/process/editor/`) is one of its commits, so keep it whichever you merge.
- `night/editor-folded` holds the same tree, byte for byte, in 46 commits: the morning's milestones, the ruff wraps
  and each lane's pieces folded into the commit they belong to. No PR; `gh pr create --head night/editor-folded` makes
  one. Nothing else was pushed.
- The lanes' own branches live only in the night's scratch clones; their work is on `night/editor`.
