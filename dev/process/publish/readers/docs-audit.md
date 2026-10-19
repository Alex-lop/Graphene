# docs-audit: README and docs on night/publish (921834de)

Clone: <scratch>/agents/docs-audit (origin removed). `uv sync --all-extras` ok, `graphene --version` -> `graphene 0.5.1`.

## 0. Headline

**The README's first command does not install what the README shows.** PyPI has only `['0.2.0', '0.5.0']` (pypi.org JSON, observed), and 0.5.0 is the 7 Oct tag. Run against PyPI with my own tool dir:
- `uvx --from graphene-map graphene --version` -> `graphene 0.5.0`
- `uvx --from graphene-map graphene demo --cheat` -> `graphene demo: no such option: --cheat (Possible options: --help, --once)`
- `uvx --from graphene-map graphene init --remove` -> `graphene init: no such option: --remove`
- `uvx --from graphene-map graphene run --help | grep -c -- --stop` -> `0`

So README:27 shows the old screen, not the GIF at README:34, and README:32, :57, :59, :66, :74 (`--cheat`, `run --stop`, `init --remove`, `--classic`, the cockpit keys) all fail for anyone who follows the README today. Nothing else in this report matters as much. Fix: publish a release (the v0.5.1 Release workflow failed on a red suite, per website.md), or until then point the commands at git (`uvx --from git+https://github.com/Alex-lop/Graphene graphene demo`; I did not run this one).

## 1. PyPI build

- `uv build` -> `dist/graphene_map-0.5.1.tar.gz` (3.95 MB) and `graphene_map-0.5.1-py3-none-any.whl` (474 KB, 67 files).
- `uvx twine check dist/*` printed:
  `Checking dist/graphene_map-0.5.1-py3-none-any.whl: PASSED` and `Checking dist/graphene_map-0.5.1.tar.gz: PASSED`
- I rendered README.md with `readme_renderer[md]` (what PyPI uses). The `<img>`, `<picture>`, `<details>/<summary>`, `<sub>` and `<div align>` tags survive. `<source>` is stripped, so PyPI shows only the `-ink` variants, which is fine on PyPI's white page. All 6 images and all 8 links in README.md are absolute (raw.githubusercontent / github.com/blob/main), so nothing breaks on PyPI.
- Low: the images point at `main`, so the PyPI page of a release changes whenever main's assets change. Pinning to the release tag (`/v0.6.0/docs/assets/...`) freezes them.
- Low: the sdist carries 437 files under `dev/` and 126 under `tests/` (3.95 MB). A `[tool.hatch.build.targets.sdist] exclude = ["dev"]` would cut it. Optional.

## 2. False and stale claims (worst first)

| # | Sev | Where | Claim | Verdict | Evidence |
|---|---|---|---|---|---|
| 1 | critical | README.md:27, :32, :57, :59, :66, :74 | `uvx --from graphene-map graphene demo` / `uv tool install graphene-map` give what the page shows | **false today** | see section 0 |
| 2 | high | CHANGELOG.md:4 "0.5.1 holds the older screen", :23 "## 0.5.1 (14 October 2026)", :28 "Install from this version to have them" | 0.5.1 is a release you can install | **false**: no 0.5.1 on PyPI | pypi JSON releases `['0.2.0','0.5.0']`, tags have `v0.5.1` |
| 3 | high | docs/assets/watch.gif, cockpit.png, map.png; CHANGELOG.md:7 "with its agent's name" | agents are named | **stale once names become numbers** (Alex's request). Also confusing today: in the GIF the same leaf `greet` is `tern` at frame 300 and `wren` at frame 700, because `name_for` keys on the session (src/graphene_map/cockpit/look.py:8-43), so a retry gets a new animal | frames I pulled with ffmpeg; all three pictures need refilming after the change |
| 4 | medium | README.md:43 vs the screen | one word per thing | **inconsistent**: `g` is "boxes and arrows" (README:43), tab "g flow", footer "g graph", help "the graph" (cockpit/help.py:41). `m` is "the map" (README:47 alt), tab "m territory", map header "TERRITORY", help "the folder map". `x` is "hands back" (HOW_IT_WORKS:73), the row says "x pull back" (cockpit.png). `w` is "gives it what the gate stopped", the footer says "w allow", the row says "w widen it". README:43 says "proofs", README:51 says "check", the screen says "proven" and `✓` | cockpit.png, map.png, GIF frames, app.py:470 |
| 5 | medium | docs/COMPARE.md:19 | "`c` in `graphene watch` shows its diff" | **stale**: it is `i`, then `c` | cockpit/details.py:31 `KEYS = {"d": "contract", "l": "output", "c": "changes", "r": "record"}`; README:90 already says "`i` then `c`" |
| 6 | medium | docs/assets/cockpit.png (README:45) | shows a run | **weak**: its header reads "no goal yet" and "0 need you". map.png (README:47) reads "0 of 30 files may be touched (0%)" with every folder "nobody". The GIF's map frame shows "0 of 4 files" and a single row "(root) nobody". The pictures show emptiness exactly where the claim is "held to those files" | images read |
| 7 | medium | README.md:43 | "in numbers whether it is alive and on track" | true but **unreadable**: the row shows `✎1/1  ✓0/1  !2  ⏸12s` and a sparkline, and nothing on screen or in the README says what the glyphs mean | cockpit/rows.py:105-117 |
| 8 | low | README.md:43, :44 "it hears it with its next write" | `t` reaches the agent | **partial**: only a Claude Code session holding a leaf hears it (HOW_IT_WORKS.md:148). A Codex or command executor does not | verbs.py:143-149 runs `board note --about` |
| 9 | low | docs/HOW_IT_WORKS.md:55 | board table: `t` = `graphene board note WORDS` (a free note) | **stale**: the cockpit's `t` needs a selected task ("select a task to tell") and runs `board note … --about ID` | cockpit/app.py:417-421, verbs.py:149 |
| 10 | low | docs/HOW_IT_WORKS.md:35 | agents are told apart by `CLAUDECODE`, `CODEX_SESSION_ID`, `GRAPHENE_NODE` | **incomplete**: also `CLAUDE_CODE_SESSION_ID`, `CODEX_SANDBOX`, `AI_AGENT`, `GRAPHENE_PLANNER` | plan.py:150-160. Observed: `graphene init` with only CLAUDECODE unset still refused me as `claude-code_2-1-296_agent` (from AI_AGENT) |
| 11 | low | src/graphene_map/plan_cli.py:982 (`graphene plan first --help`) | "Off never proposes." | **false**: plan_cli.py:48 and HOW_IT_WORKS.md:97 say bigger work is still proposed first | help output |
| 12 | low | docs/HACKATHON.md:466 (linked from HOW_IT_WORKS:256) | "In the replay, Tab shows the same plan as a tree and then as a graph" | **stale**: Tab now cycles cockpit, flow, territory | cockpit/app.py:471-472 |
| 13 | low | README.md:91, A_RUN.md:38 | "in the three comparisons so far a plain paragraph … did just as well" | true (dev/test/results-2026-09-20/21/23.md) but **dated**: all three are from before the gate and the cockpit. Keep it, and add "(September)" | files listed |
| 14 | low | Alex's own diff, "Cost" bullet | "nothing caps the total yet" | **stale**: `graphene run --max-usd N` exists (run --help: "Start no attempt past these dollars; one going is not stopped"; CHANGELOG:71). True only by default | run --help |

### Claims I checked and found true

- README:32 / HOW_IT_WORKS:274 `demo --cheat`: ran it in an empty temp dir. 2.2 s. It printed 7 attempts and `6 refused, 1 flagged, 0 got through.` and left the dir empty.
- `graphene demo --once` (empty dir): prints the finished plan "a friendlier app", 2 leaves done, ends `the end · try it on your repo: graphene init, then graphene ask what you want`. Nothing written.
- HOW_IT_WORKS:271 "`graphene --help` lists nine commands": true (init ask watch run plan node board demo config).
- Every hidden command HOW_IT_WORKS:273-287 names exists and answers `--help` with exit 0: plan goal/propose/prompts/ack/record/cover/note/precheck, node diff/start/signoff/reopen/split, board park/unpark/lookup, talk why, direction, key.
- README:63 "You need a git folder": outside git, `graphene init` -> `run this inside a git repository (no .git found above the current directory)`.
- README:67 / :79: in a scratch repo, `graphene init --planner claude --executor claude` printed `hooks added to .claude/settings.local.json (8 Claude Code hooks)` and the recording sentence, and set `plan first: on` with no terminal (HOW_IT_WORKS:90 true).
- README:57 `:stop` (verbs.py:224), `run --stop` (run --help). README:58: `node show` prints `landed: <sha>` (plan_cli.py:1504) and `take it back: git revert -m 1 <sha>` (node_record.py:716). README:59 `init --remove` (init --help).
- README:74: `y` takes, `d` drops, and `R` asks first when more than one leaf could start (app.py:368-385). Note that the cockpit's R/r always run with `--parallel 4` (verbs.py:28), but README:71 shows `--parallel 2` for the CLI. Not wrong, just two different numbers.
- README:74 `graphene watch --classic`, `demo --classic` and `--view` exist (watch/demo --help).
- README:88 "shell redirects included": cheat #2 `echo RATE=2 > src/billing.py` -> "REFUSED before it ran".
- README:89 `done` flags a weakened test: cheat #7 "FLAGGED".
- README:90 `i` then `c` shows the diff: details.py:31.
- CHANGELOG Unreleased: `D` direction, `v` lens, `p` paint, Tab, `c` back, Enter opens details on a row that waits for nothing (app.py:475-481), four panes, replay keys space, `.`, `r` (replay.py:64-66): true. "53 ms at 22,000 log rows" and "a closed terminal ends it": not checked.
- CONTRIBUTING.md:16 "Python 3.12 or newer" matches pyproject `requires-python = ">=3.12"`. `uv run ruff check` -> `All checks passed!`. CONTRIBUTING:12 "about 18 minutes in one process": not checked. `uv run pytest -q -n auto -x` -> `2 failed, 992 passed, 10 skipped in 170.23s`. Both failures look environmental: ~ is itself a git repo (`git -C $TMPDIR rev-parse --show-toplevel` -> `~`), so `test_commands_refuse_to_run_outside_a_git_repo` cannot work under this TMPDIR, and `test_land_moved…not_held_against_the_next_leaf` passed when run alone.
- SECURITY.md: the "Security tab / Report a vulnerability" setting cannot be checked from the clone. Not checked.
- Not checked end to end: a real `node add` / `done` / `node show` cycle. This session's own Graphene hook refuses a shell write outside a held leaf, so I relied on reading the code.

## 3. Links

Every link resolves. I checked each relative target with `test -e`: docs/HACKATHON.md, dev/test/results-2026-09-23.md, dev/process/controller/designs.md, dev/README.md, dev/DIRECTION.md, README.md, the `#privacy` (HOW_IT_WORKS:253) and `#where-each-mechanism-ends` (:198) anchors, and .github/ISSUE_TEMPLATE/first-hour.yml. The README's blob/main paths (docs/COMPARE.md, docs/HOW_IT_WORKS.md, docs/A_RUN.md) and all 6 raw asset paths are in the tree. The external links (uv docs, two claude-code issues, Alex's site) were not fetched.

**Gaps rather than breaks:**
- The README links neither CONTRIBUTING.md, SECURITY.md, CHANGELOG.md, docs/HACKATHON.md, HOW_IT_WORKS's FAQ, nor Alex's YouTube video.
- CONTRIBUTING.md:4 `../../issues/new?…` works only on github.com's blob view. That is fine because it is not in the long description.

## 4. Alex's uncommitted README edit, exactly

The base is blob cb3ff455 = commit 7e5bad17 (16 Oct, "The README opens with why Alex built this"), so he made the edit in reaction to that commit. Hunk by hunk:

1. He dropped the centred `<div>` and the `<picture>` mark with its dark-mode source. In its place: a plain `![The Graphene mark](…graphene-mark-ink.svg)` above `# Graphene`. The ink-only mark will be dark on GitHub's dark theme.
2. He **cut the two-paragraph "## Why I built this" from the top.** The bold promise ("Your AI coding agent stays inside the files you agreed to…") becomes the first line under the title.
3. The `<sub>` uv note becomes a plain sentence.
4. The GIF's `<img width=720>` becomes a markdown image with no width. The loop `<picture>` becomes an ink-only markdown image.
5. He **added a "Cost" bullet** to "In your hands": "with Claude Code, $2 an attempt, three at most, and a run says its worst case first. Codex has no cap, and nothing caps the total yet. A real two-leaf run cost $0.30." The last clause is stale, see row 14.
6. He **unfolded both `<details>`** ("Does anything leave my computer?", "What does Graphene enforce?") into bold headings, always visible.
7. He **added "Why I built this" at the bottom**, as a bold heading, in the short one-paragraph version: "I believe the limit on building software won't be tokens or cost. It'll be the human direct"ion it takes. If you don't say which direction… Graphene tries to bridge that." It has a stray `"` typo in "direct"ion".
8. Cosmetic: extra blank lines, and no newline at end of file.

His base had no "What you see" section and no `--classic` sentence (both 17 Oct), so their absence in his file is not a removal.

Earlier history:
- On 15 Oct, c70302b7 shows Alex wrote the long "why" himself, inside a `<details>` fold at the bottom, then reverted it 4 min later (939e98af).
- On 7 Oct, 48ee55cb and a96fb48a show him hand-editing the why in the GitHub web UI.

**What it suggests he wants:**
- The promise first. The why short, personal, near the end.
- Plain markdown over HTML.
- Nothing hidden in folds.
- Cost stated next to Stop and Undo.
- The honesty lines kept.

There is a tension with his video and website, which lead with the why ("you, the human, drive innovation"). **This is a decision for Alex:**
- why-first, like the current main and his video, or
- promise-first with a short why at the end, like his own edit.

I'd follow his edit and link the video from the short why.

## 5. What a judge cannot find in five minutes

- **That the install gets a 7 Oct build** without any of this (section 0). The first command a judge copies shows a different screen.
- **What the hackathon entry is.** The README never says which hackathon, or what was built for it. Nemotron / Token Factory appear in pyproject keywords but not in the README. docs/HACKATHON.md (6,410 words) is not linked from the README.
- **What the row numbers mean** (`✎ ✓ ! ⏸`, the sparkline). The stills show "no goal yet" and an all-"nobody" map.
- **Cost.** Not in the current README at all; Alex's edit adds it.
- **A real run's output.** A_RUN.md is linked only in the footer line. Pasting the 7 lines of `demo --cheat` output, which is real text and observed above, would prove the locks in-page.
- **Who built it and why, in his voice.** The why is there. The video is not linked. The website appears only as the "Alex Lopez" footer link.
- **Supported platforms.** pyproject says macOS and Linux only. The README does not say so, and nothing says Windows is unsupported.
- **Uninstall.** `init --remove` takes the hooks out. Nothing says `uv tool uninstall graphene-map`, or what to do with the `.graphene/` store and the `graphene/<id>` branches.

## 6. What a published tool is missing

| Item | State |
|---|---|
| Badges | **none**. Add PyPI version, CI (ci.yml exists), Python 3.12+, license |
| Install | present (README:66), but it installs 0.5.0. No pipx/pip line |
| Requirements | git and Claude Code/Codex signed in (README:63), uv (README:30). Python 3.12 is implicit. **OS not stated** |
| Uninstall | partial: hooks only (README:59) |
| FAQ | two folds (README:76-93). HOW_IT_WORKS:258-267 has a FAQ that is not linked |
| Contributing | CONTRIBUTING.md exists, **not linked** from the README |
| Security | SECURITY.md exists, **not linked** |
| License | one word in the footer (README:97). LICENSE file present |
| Screenshots | GIF + 2 stills: present, but they show animal names, "no goal yet" and an empty map |
| 30-second demo | the GIF runs **50.9 s** (ffprobe; 1272 frames) and opens on a typed prompt (`> g`). The hosted demo command is broken on PyPI (section 0) |
| Changelog | exists, not linked from the README (it is in pyproject's URLs) |
| Video | the YouTube video (2:42, 17 Oct) is not linked |

## 7. Word count

- README.md raw: 1,021 words (`wc -w`).
- Visible text as PyPI renders it: **903 words**, of which 45 are in code blocks and 858 are prose (tags stripped from the readme_renderer HTML).
- For comparison, Alex's uncommitted README is 746 raw words.

## 8. Proposed outline for the published README (about 650 visible words)

1. **Header**: mark (`<picture>` with the dark variant, since PyPI falls back to ink), `# Graphene`, then the one-line promise and badges (PyPI, CI, Python 3.12+, Apache-2.0, macOS/Linux).
2. **The promise, two lines**: "Your coding agent stays inside the files you agreed to. Done means your tests passed, not that the agent said so." Then one line on what it is: local, no account, for Claude Code and Codex.
3. **Try it in 30 seconds**:
   - `uvx graphene-map demo` (works only once a release is on PyPI) with a GIF of 30 s or less, numbered agents, a real goal on top.
   - Then `graphene demo --cheat` with its real 7-line result pasted as text: "6 refused, 1 flagged, 0 got through".
4. **How it works**: three numbered steps (plan with files + check; held to the files; done is checked in a clean copy) plus the loop diagram.
5. **The cockpit**:
   - one still of a live-looking run;
   - a 6-row key table (Enter take, `t` tell, `w` widen, `x` hand back, `i` everything, `g`/`m` graph and map, `?` all keys);
   - a one-line legend for `✎ ✓ ! ⏸`;
   - one word per thing, matching the screen.
6. **On your project**:
   - Requirements line: git repo, Claude Code or Codex signed in, macOS or Linux, uv.
   - The 6 commands.
   - The Claude Code shortcut (no `ask`, plan first).
7. **In your hands**:
   - Stop.
   - Cost: Alex's line, corrected to "pass `--max-usd N` to cap a run".
   - Undo (`git revert -m 1`, which `node show` prints).
   - Leave: `graphene init --remove`, `uv tool uninstall graphene-map`.
8. **What it enforces, and where it ends**, open, not folded:
   - refused before the write (Claude Code only);
   - git at done (Codex, others);
   - a weakened test is flagged, not refused;
   - the honest comparison result (September), with links to COMPARE and "Every limit".
9. **Privacy**, one line: Graphene sends nothing; the hooks record on your machine; Nemotron is an opt-in extra.
10. **Why I built this**: Alex's short paragraph from his own edit (typo fixed), with a link to his video and site.
11. **Built at the hackathon**: two lines on what was built and the Nemotron extra, with a link to docs/HACKATHON.md for judges.
12. **Help it get better**: the first-hour form, issues, CONTRIBUTING.md, SECURITY.md, CHANGELOG.md.
13. **Footer**: How it works · A real run · Compare · Alex Lopez · Apache-2.0.

Decisions for Alex (flag, don't decide):
- why first or last (section 4);
- publish a release before the README goes out, or point the commands at git;
- whether the hackathon section belongs in the README or only in docs/HACKATHON.md.

## Files

- Report: <scratch>/reports/docs-audit.md
- Clone: <scratch>/agents/docs-audit (dist/ holds the built sdist and wheel)
- GIF frames I extracted: <scratch>/agents/docs-audit-tmp/strip.png
- PyPI-rendered README: <scratch>/agents/docs-audit-tmp/pypi.html
