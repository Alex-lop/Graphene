# ux-critic: the cockpit `graphene watch` opens, looked at

Tree: clone of `night/publish` at 921834de (= origin/main), in `<scratch>/agents/ux-critic`.
Nothing in the repository was changed. All findings below were seen in a screenshot or reproduced with a script,
unless marked "not checked".

## How I looked

- `uv sync --all-extras` in my clone (textual 8.2.8), then headless runs the way `tests/test_cockpit_app.py` drives
  the app: `App.run_test(size=…)`, `pilot.press`, `app.save_screenshot` to SVG, `qlmanage -t -s 1600` to PNG, read.
- **Real plans in scratch git repos** (`scripts/shots.py`): a 33-file shop app, a 6-leaf plan built with the plan's
  own API (`plan.propose_goal/propose/accept/start/release`, `board.add/note`, `store.log_node` for did/said/denied
  rows, `put_node` for review/done). States: no plan (first run), proposed + a question + a risk, three leaves
  running (one with a stopped write and a note, one quiet), one came back with a reason, a sign-off waiting, all
  done. Keys: cockpit, `j`, `g`, `m`, `m v` (live), `m v v` (changed), `?`, `i`, `t` + typing, `a` + typing, `:`,
  `x` on a review row. Sizes 80x24 and 120x36.
- **The shipped demo** (`scripts/replay_shots.py`): `CockpitReplay` over `src/graphene_map/demo.jsonl`, paused,
  `.` sixteen times, every frame saved and dumped as text (`demo-100x24.txt`), then `g m c i r`.
- **The real 9 Oct Claude Code recording** the README stills come from (`tests/recordings/loop-claude-3.jsonl`,
  "plant-claude-3", 138 changes): every frame dumped (`loop-claude-3.txt`); steps 2, 93 and 120 rendered
  (`scripts/replay_at.py`).
- The README GIF: `ffmpeg` frames every 4 s (`gif/sheet.png`), against `docs/assets/watch.tape`.
- Probes: `scripts/outside_probe.py` + `outside_probe_prev.py` (the false OUTSIDE), `scripts/key_probe.py` (keys the
  screens advertise), `scripts/long_plan.py` (a plan longer than the screen).

## PNGs made

All under `<scratch>/agents/ux-critic-shots/`:

- `png/` (44): `{first-run,proposed,running,came-back,signoff,done}-cockpit-{80x24,120x36}.svg.png`,
  `running-cockpit-j-*` (stopped write selected), `*-flow-*`, `*-map-*`, `running-map-live-*`,
  `done-map-changed-*`, `running-help-*`, `running-details-*`, `came-back-details-120x36`, `running-tell-*`,
  `proposed-answer-*`, `proposed-command-80x24`, `signoff-reopen-x-80x24`, `long-plan-bottom-80x24`.
- `png-demo/`: `demo-100x24-step01` (first frame), `step02` (the board), `step07` (came back), `step13` (false
  OUTSIDE), `end-flow`, `end-map`, `end-details`, `end-record`.
- `png-loop/`: `loop-claude-3-100x28-step120` (= today's `docs/assets/cockpit.png` frame), `at093-rows` (the same
  run when the leaf really came back), `at002-m` (the same run's map at the proposal: the blast radius).
- `gif/sheet.png` and `gif/gif-01..13.png`: today's `docs/assets/watch.gif`, one frame every 4 s.

## Screen by screen

### First run (no plan) — `png/first-run-cockpit-80x24.svg.png`, `-120x36`
- Works: it does not crash, it says "Nothing is planned yet." in bold, and offers `:ask`.
- Does not: the headline is **"no goal yet your plan"** (bold "no goal yet" reads as the plan's title, "your plan"
  runs on). The scoreboard says `0 need you 0 running 0/0 proven` over an empty `▱▱▱` bar: four rows of zeros.
  The key line of the empty state is **cut at 80 columns**: "…here for you to acce…" (`rows.py:66-76`, the line is
  80 cells, `fit(t, width-2)` keeps 78). The bottom line shows the legend for marks that are not on screen
  (`✎ ✓ ! ⏸ ▁▃▅`, cut "activ…" at 80). The key bar offers `⏎ take · i all · t tell · w allow · x back`, none of
  which does anything here. Nothing says whether `graphene init` ran (`m.executor` is empty) or that `graphene demo`
  shows a run. At 120x36, 75% of the screen is black.
- `g` on it (`first-run-flow-80x24`): an empty screen with one line floating mid-screen, "amber lane = a retry loop
  (bounded) · ◀▶ two-way". `m` (`first-run-map-80x24`): "0 of 33 files may be touched (0%)" over seven "nobody".
- 3-second read: "nothing here, and zeros".

### Proposed plan with board questions — `png/proposed-cockpit-80x24.svg.png`, `-120x36`
- Works: questions come first, the default sits beside `⏎`, the options are numbered; `8 need you` in purple is
  the loudest number; `⏎ accept` on every proposal says what Enter does.
- Does not:
  - **You cannot see what you are agreeing to.** A proposal row shows a title and `⏎ accept`, nothing about its
    files or its check; selecting it does not expand it (`rows.py:164` expands only running/review/came back).
    The product's promise ("you see the agent's plan and fix it before any code is written") needs `i` per row.
  - **Accepting a 6-leaf plan is 6 Enters**: accepting a leaf takes its proposed parents, not its siblings
    (`plan.accept`), sub-goals are not rows, and there is no accept-all key (`app.py:47-51`; `:plan accept` only).
  - **Titles are cut to five words at read time**, even at 120 columns with 60 free cells: "Email the PDF when",
    "Store when each invoice was", "download button on the invoice" (lost "page"), "invoice template"
    (`read.py:90`, `look.short`). No ellipsis, so they pass for whole titles.
  - One glyph, three meanings: `?` is a question (purple), a proposal (cyan) and a **risk** ("Invoices from before
    2024 have no currency field ⏎ noted"). Question text starts at column 3, proposal titles at column 12 (the empty
    6-cell agent column), so the left edge zigzags.
  - Colour: proposals count in "need you" (purple) but their affordance is cyan.
- 3-second read: "8 things want me, a column of `?`, no idea what they touch".

### Three leaves running — `png/running-cockpit-*.svg.png`, `running-cockpit-j-*` (the stopped one selected)
- Works: this is the cockpit's best density: one row an agent, the last move under each in dim text, aligned
  numbers (`✎2/2 ✓0/1 !1 ⏸62s`), the selected row opens to its last three moves and its verbs. The note sent to an
  agent shows on its row with "sending…"/"heard 3s ago".
- Does not:
  - **"0 need you" while an agent is blocked on a write only you can allow** (`!1` on dove, small red at the far
    right; `NEEDS_YOU` in `model.py:17` leaves running leaves out, so the row does not float up either).
  - **Agent colours collide with status colours.** 12 of the 26 names get a status colour (`look.color_of`): oak,
    quail = proven green; bee, seal = running amber; hen, vole = need-you purple; ant, yak = came-back red; ivy,
    dove = accent cyan; crab, tern = stopped orange-red. Here quail's sparkline is "proven" green and dove's is
    "link" cyan; in the README's `cockpit.png` the healthy running agent `ant` and its sparkline are came-back red.
    26 names over 16 colours also gives pairs the same colour (crab/tern, ant/yak).
  - Waiting rows mix agent names and ids: "← pine", "← pine", "← button" (`button` is an id; the row says "download
    button on the invoice").
  - The told note appears **twice** in the open row: once in the tail ("you “use the existing Mailer.attach…”")
    and once as the told line ("you “…do not…” sending…") (`rows.py:185-203` + `read.py:250-251`).
  - The progress bar repeats `0/6 proven` and ignores running work.
- 3-second read: "three amber dots, alive" — and wrongly, "nothing for me".

### A leaf that came back — `png/came-back-cockpit-*.svg.png`, `came-back-details-120x36`
- Works: the best screen. `↩` red, the reason in red on the row, `⏎ try again` in purple, `w give it
  src/shop/mailer.py` / `b a sibling` in amber, `1 need you`, sorted first.
- Does not:
  - **The reason is chopped mid-path with no ellipsis**: "…which lives in src/shop/mailer.p" (`read.py:228`
    `[:80]`). Same for agent sayings (`read.py:193` `[:80]`): the README still reads "because the test can't pass
    while". In the replay's news, `[:60]` (`replay.py:46,48`): "…because the te".
  - The reason shows twice when selected (right column + wrapped lines).
  - On a leaf that came back *wanting* a path, the row says the generic `w widen it`; the details pane says "w widen
    its scope to src/shop/mailer.py". `b a sibling` and `r reopen` do not say for what / whom.
  - The details pane lists **`t ask the planner`** (`tui.py:2478`, the classic screen's offer list reused by
    `details.py:56`), but `t` in the cockpit opens the tell box (verified: `key_probe.py` → `tell_open=True`).
- 3-second read: "this one is mine, here is why, Enter retries" — exactly right.

### A sign-off waiting — `png/signoff-cockpit-*.svg.png`
- Works: `◆` purple, `✓1/2 ⏎ sign off`, counted in need you.
- Does not: nothing on the row says what you would be signing (files changed, `c` diff in details). `x` on it opens
  the reopen prompt (`signoff-reopen-x-80x24`): its title says "quail Store when each invoice was" and its
  placeholder "reopen migrate: …" — agent, title and id, three names for one task in one box.

### All done — `png/done-cockpit-*.svg.png`
- Works: `6/6 proven` and a full green bar are a real moment of closure; `3 files · OUTSIDE` in red is honest.
- Does not: nothing says what now (the plan is done: what landed, `:ask` the next thing). Agent names on finished
  rows are noise at full brightness.

### `g` flow — `png/*-flow-*.svg.png`, `png-demo/demo-100x24-end-flow`
- Works: a stable, readable layered graph; the selected box double-bordered; running boxes amber with the agent on
  the bottom border; proposed boxes cyan `?`; hot edges cyan.
- Does not: the legend "amber lane = a retry loop (bounded) · ◀▶ two-way" is drawn under **every** graph, with or
  without loops (`app.py:201`), and the cockpit legend is stacked under it (two legends, both irrelevant). Labels
  wrap at 18 cells even at 120 columns with half the screen empty (`flow_view.py:34`). With a question selected
  (`proposed-flow-80x24`) the info line is blank. The demo's graph is two unconnected boxes.

### `m` territory — `png/*-map-*`, `running-map-live-*`, `done-map-changed-*`, `png-loop/…at002-m`
- Works: **the most Graphene picture there is** when a plan is proposed: "12 of 33 files may be touched (36%) +
  new files in 4 places", a bar per folder shared by the tasks that may write it.
- Does not:
  - The headline is the plan-lens sentence in **every** lens: on a finished plan the "what changed" lens says "0 of
    33 files may be touched (0%)" (`territory_view.py:29-34`).
  - The lens always starts at "plan" (`model.py:78`), so a finished plan (and the README's `map.png`, and the
    GIF's end frame) is every folder "nobody".
  - **The live lens tells you to press `a`**: "a: allow dove" (`territory_view.py:74`); `a` is answer (verified:
    pressing it says "a answers a question in your own words: select one").
  - At 80 columns the live marks ("● 1 now", "!1 stopped") fall off the right edge behind the owner names
    (`running-map-live-80x24`): the lens loses the thing it exists for.
  - Owners are ids for tasks without a running agent ("button 1 email 1 migrate 1") and agent names for running
    ones ("dove 1 quail 1"), in one row; the rows elsewhere say titles.
  - `tests/` and `tests/ (new)` are two rows. The hint line "p paint the selected task here …" repeats the key bar.

### `?` help — `png/running-help-80x24.svg.png`, `-120x36`
- Works: grouped by intent (answer, agents, plan, screens, anything), fits 80x24, closes on Esc/q/?.
- Does not: no meaning for the marks (`● ◆ ↩ ○ ◌ ? ✓ ◇` are explained nowhere; `✎ ✓ ! ⏸` only in the bottom
  legend). Says "leaf" three times and "task" three times; "the graph, the folder map" while the tabs say "flow,
  territory"; "plan first", "the direction above your plans" are jargon.

### `i` details — `png/running-details-*`, `came-back-details-120x36`, `png-demo/…end-record`
- Works: dense, `key value`, each offer shows the command it runs (teaches the CLI); tabs on top, keys at the foot.
- Does not: pane keys `d l c r` (`details.py:31`) are `drop`, `cockpit`, `run` one screen down: habit carried back
  can drop a proposal or start a paid run. `t ask the planner` (above).

### `t` tell and the prompts — `png/running-tell-*`, `proposed-answer-*`, `proposed-command-80x24`
- Works: the inline row "tell pine: use Mailer▌" keeps the plan in view; prompts dim the plan and name what they
  are about.
- Does not: the tell text is drawn **twice**: inline, and in a 3-row Input at the bottom with Textual's default
  blue border (`app.py:95,128`), which pushes the rows up 3 lines. While the box or any prompt has the keys, the key
  bar still says `⏎ take · i all · t tell …` (wrong for that moment; no "Enter sends · Esc cancels").

### Long plans — `png/long-plan-bottom-80x24.svg.png`
- The goal, the counters and the bar are lines of the scrolling canvas (`rows.py:21-50` inside the
  `ScrollableContainer`, `app.py:125`), so `j` down a long plan scrolls "need you" off the screen. The scrollbar is
  Textual's default blue.

### The demo replay (the README GIF) — `demo-100x24.txt`, `png-demo/`, `gif/sheet.png`
Frame by frame, at 100x24, what a stranger sees for ~51 s:
1. step 1, ~3 s on screen: **"no goal yet … Nothing is planned yet. … Or type :ask"**, news "settings recorded".
2. step 2, 2 s: the best beat of the run, the agent asks three things before writing, including **"a --name flag;
   nobody asked for one"** (scope creep caught) — news "put up bye-word · put up hello-home · put up name-flag".
3. steps 3-6: "took bye-word · took hello-home", "friendly accepted · greet accepted · farewell accepted" (the rows
   say "greet says hello" and "bye says goodbye"; "farewell" and "friendly" never appear on a row), "greet precheck
   · farewell precheck".
4. steps 7-10: came back, "the word lives in words.py ⏎ try again"; news "greet usage · greet ended · farewell
   check passed".
5. step 11: the person widens the scope — the story's key move — narrated **"greet edited"**.
6. steps 13-14: **"● wren greet says hello … ✎2/2 ✓0/1 1 OUTSIDE"** in bold red, with the previous attempt's
   tail "run graphene node release greet" under a running row; news "greet started · greet attempt".
7. end: `g` = two unconnected boxes and the loop legend; `m` = "0 of 4 files may be touched (0%)", "(root)
   nobody"; `i` contract; `r` record.
The assumption's own text is a fragment: "greet reads its word from words.py, where HELLO is" (it is the script's
text, `tests/test_demo_script.py:43`, not a cut).

**Why "1 OUTSIDE" (reproduced):** `touched_by_git` caches git's answer per leaf id for `GIT_EVERY` = 5 s
(`read.py:279`). The came-back look (scope `['app.py']`) cached `outside=['words.py']`; after the widen the scope
is `['app.py','words.py']` and a new attempt has a new `base_sha`, but the recording's clock only moves 1.4 s
(…012.1 → …013.5), so the stale list is reused. `outside_probe.py` with a fresh model each step: `outside=[]`;
`outside_probe_prev.py` carrying the model as the app does: `outside=['words.py']` at steps 13 and 14. Live, the
same false flag shows for up to 5 s after any widen.

### The README stills — `docs/assets/cockpit.png`, `docs/assets/map.png`
- `cockpit.png` is step 120 of 138 of the 9 Oct run (`png-loop/loop-claude-3-100x28-step120` reproduces it). Its
  alt text says "an agent has just handed its leaf back and says why", but the row is `● ant … x pull back`
  (running): the second attempt has just started and its tail is the **first** attempt's release lines (same cause
  as the demo's step 13). Headline "no goal yet"; the running agent in came-back red; news "e2e-xml attempt" in
  bold amber, the loudest line on the picture; "…because the test can't pass while" cut with no ellipsis.
- `map.png` is the same frame in the plan lens: "0 of 30 files may be touched (0%)", twelve "nobody", one hatched
  "tests/ (new) ant 1". It shows nothing.
- The same run has the right frames already: step 93 (`png-loop/…at093-rows`, really came back: "1 need you",
  "↩ … ⏎ try again", the reason, `w widen it  b a sibling  r reopen`) and step 2 (`png-loop/…at002-m`: "6 of 27
  files may be touched (22%) + new files in 2 places", bars on six folders, six "nobody").

## Ranked changes (most felt first)

`[pic]` = makes the README's pictures better.

1. **Kill the false `OUTSIDE`** `[pic]` — high. `read.py:279-293`: key the cached git answer on
   `(node.base_sha, tuple(node.scope))` as well as the leaf (store them in the `m.seen` tuple; recompute when they
   differ). Why: the GIF shows the agent breaking the rule the README's first bold line promises, on the retry that
   was supposed to prove it; live, a widen flashes a false red flag. Felt: after "w", the row goes calm at once.
2. **The replay opens on the plan, and real headlines say a goal** `[pic]` — high. `replay.py:88-94` applies one
   change before the first paint; apply every leading change that has no nodes or board items (the "settings
   recorded" one) before the screen is drawn. In `rows.py:24-30`, a plan with no goal shows "No goal yet ·
   :plan goal '…' says what this is for" dim purple, not a bold "no goal yet" title, and drops "your plan". Why: the
   GIF's first 3 s and both stills lead with "no goal yet"; Alex's whole case is that direction is the scarce thing,
   so the empty goal should read as an invitation, not a title. Felt: the first frame is a plan with questions.
3. **The bottom line tells the story, quietly** `[pic]` — high. `replay.py:36-53`: drop bookkeeping kinds
   (precheck, usage, ended, attempt, model; "an executor's output", "settings recorded") instead of falling back to
   `D.what()` — leave the last news up; say board acts with the item's text ("asks: what does bye say?", "you took
   the default"), say "edited" as what changed ("greet may now write words.py"), name tasks by title (or `#n`), and
   cut with `fit()` not `[:60]`. `app.py:180`: news in a dim colour, bold only for `✗` (red) and landed/proven
   (green). Why: in the real run's replay 69 of 138 frames say "an executor's output" and 82 (59%) say only
   bookkeeping, all in bold amber; the stills' loudest line is "e2e-xml attempt". Felt: the line under the rows
   reads like a narrator, not a log.
4. **Agents are numbers, and colour means state only** `[pic]` — high (Alex asked). `look.py:8-47` (NAMES,
   name_for, color_of), `model.py:180-184`, `read.py:296-304` keep the key; the number is the order of the agent
   key's first `started` row in the plan's log (stable across looks, restarts and two watch windows; never reused),
   shown `#1`. Touch points: `rows.py:149-156` (lead column, then `LEAD` 12→9 gives 3 more title cells at 80),
   `rows.py:120-123`, `rows.py:220` ("tell #1:"), `flow_view.py:20`, `app.py:194,289,303`,
   `territory_view.py:55,62,71`, `verbs.py:128,167`, tests that import `NAMES`. Drop agent colours (the agent
   column grey, the sparkline the running amber). Why: 12 of 26 names wear a status colour; the README's healthy
   agent is drawn in alarm red. Felt: "#2 is stuck" is as sayable as "dove is stuck", and only trouble is red.
5. **See and take a whole proposal** — high. Expand the selected proposal like a running row (`rows.py:164`): its
   files (`t.scope`, and `m.allowed(t)` as "3 files"), its check, what it waits on; right column "3 files ⏎
   accept". Add `A` = accept every proposal (`plan accept`, with a one-line "accept 6? y" like `R`), on the bar
   when a proposal is selected (`app.py:47-51`). Give proposals their own mark (`+`, cyan) and risks theirs (`!`,
   amber) instead of `?` (`look.py:18-22`, `rows.py:86`), and start question text in the title column. Why: the
   moment the README sells takes six Enters and six `i`s today. Felt: read the plan in one glance, one key.
6. **A stopped write needs you** — high. Count a running leaf with unwidened `t.stopped` in `scoreboard()` and
   sort it with `NEEDS_YOU` (`model.py:17,97-113`); its right column says "w give it mailer.py" (amber) instead of a
   bare `!1` (`rows.py:112-113`). Why: the header says "0 need you" while an agent waits on a permission only you
   can give. Felt: the number on top is never a lie.
7. **Whole titles where they fit** — medium. `read.py:90`: keep `short()`'s cut at the colon and the dropped
   article but not its five-word cap for rows; `rows.py:160` already `fit()`s to the room with "…". Keep the cap for
   flow boxes. Why: "Store when each invoice was" and "download button on the invoice" at 120 columns. Felt: rows
   read as sentences, and a cut one shows its "…".
8. **Never cut an agent's words silently** `[pic]` — medium. `read.py:193,199,228` (`[:80]`) and
   `replay.py:46,48` (`[:60]`): keep the text (cap at a few hundred) and let `fit()`/`textwrap` cut at the screen.
   Why: "src/shop/mailer.p" looks like a real path; "because the test can't pass while" looks like a bug in a
   README still. Felt: a reason is always readable to its end, or ends in "…".
9. **A map that always says something true** `[pic]` — medium. Headline per lens (`territory_view.py:29-34`):
   plan "12 of 33 files may be touched (36%)", live "3 files being written · 1 write stopped", changed "10 files
   changed in 4 folders · 1 outside its scope". Open on "changed" when nothing is live (`model.py:78` / first
   paint). Live marks before owner names, so 80 columns keeps them (`territory_view.py:61-75`). Owners by `#n` or
   short title, never ids. One hint line (delete `territory_view.py:82-85`). An empty plan says one line, not seven
   "nobody". Re-render `map.png` from the proposal moment (below). Felt: `m` is worth pressing at every stage.
10. **A key bar that tells the truth now** — medium. `app.py:42-46,183-185`: build the bar from the selected
    row: proposal "⏎ accept · A all · d drop · e edit · i details", question "⏎ weasyprint · 1 2 pick · a answer ·
    d drop", running "t tell · w give it … · x hand back · i details", came back "⏎ try again · w … · b … · i
    details", done "i details · x reopen"; tell box open "Enter sends to #1 · Esc cancels"; any prompt "Enter ·
    Esc". (lazygit and gitui swap their options bar per panel.) Felt: Enter is never "take" in the abstract.
11. **One word for one thing** — medium. From the screens: `g` is "flow" (tab) and "graph" (bar, help); `m`
    "territory" (tab, header), "map" (bar), "folder map" (help); `i` "all", "everything", "details"; `x` "back",
    "pull back", "hand back"; `w` "allow", "give it", "widen it", "a: allow"; "leaf"/"task"; "proof"/"proven"/
    "check"; agent/id/title for one task in one prompt. Pick: tabs = bar words (`app.py:158`: cockpit, graph, map),
    one verb per key everywhere (rows `rows.py:204-216`, bar `app.py:42-46`, help `help.py:15-42`, map
    `territory_view.py:74,84`, README "What you see"), "task" on screen, titles where ids show (waiting rows, map,
    news, prompts). Also the top-right "plan first on" (`app.py:162`) is jargon: show it only when off ("plan
    first off: agents may write without a plan"). Felt: eight verbs, learned once.
12. **Keys the screens advertise must work** — medium (bugs). `territory_view.py:74` "a: allow" → "w give it"
    (`a` answers; verified). Details' `t ask the planner` (`tui.py:2478`, shown by `details.py:56`) → hide in the
    cockpit or show it as ":ask …". Felt: a hint you follow does what it says.
13. **Sticky header, one row shorter** — medium. Move goal + counters out of the canvas into Statics above the
    `ScrollableContainer` (`app.py:123-129`, `rows.py:21-50`); merge counters and bar into one line ("▰▰▱▱▱▱ 2/6
    proven · 3 running · 1 needs you"); style the scrollbar in the palette. Why: `j` in a long plan scrolls "need
    you" away (`long-plan-bottom-80x24`). Felt: the summary is always where k9s and lazygit keep theirs.
14. **First-run and empty states with a next step** — medium. `rows.py:66-76`: three lines that fit 78 cells ("In
    Claude Code, say what you want: it proposes a plan here." / ":ask what you want · see a run: graphene demo"),
    "graphene init has not run here" when `m.executor == ""`; hide counters, bar and legend while there are no
    tasks; the graph and the map say one line each when empty. Felt: the first 3 seconds say what to do, not 0/0.
15. **Legend into help; a calm bottom line** — low. `app.py:52,180`: no legend when there is no news (a blank dim
    line); `?` gains a "marks" group (`help.py`): `● running ◆ sign-off ↩ came back ○ ready ◌ waiting + proposed ✓
    done`, `✎ files written of allowed ✓ proofs ! writes stopped ⏸ quiet ▁▃▅ activity`. Felt: less noise, and "what
    is ◌" has an answer.
16. **The came-back row names its way out** `[pic]` — low. `rows.py:209-211`: "w give it words.py" (the wanted
    path, from `t.offers["w"]`), "b new task for words.py", "r reopen Add an XML reader"; drop the right-column
    reason when the row is open (`rows.py:127-129`). Felt: widen vs split vs reopen is a decision you can make from
    the row.
17. **A running row shows this attempt only** `[pic]` — low. `read.py:180-184`: when the node's `started_at` is
    newer than every row, show "starting…" instead of the old attempt's tail (today: "run graphene node release
    greet" under a running row, in the GIF and in `cockpit.png`); skip `you` events in the tail when the told line
    follows (`rows.py:185-203`); hide the agent's own `graphene node …` calls from the tail. Felt: a running row
    never says it is giving up.
18. **Tell in one place** — low. `app.py:95-96,128`: keep the inline "tell #1: …▌" as the visible editor; the
    Input 1 row (or off-screen), in the app's accent, no 3-row jump. Felt: you type where you look.
19. **The graph's own legend only when it applies** `[pic]` — low. `app.py:197-202`: the loop/two-way line only
    when such an edge is drawn; `flow_view.py:34` try labels up to ~28 cells when the width allows; a question
    selected shows the task it is about. Felt: the graph reads as the plan, not a key to a diagram.
20. **Details panes on 1-4** — low. `details.py:31`: `1 2 3 4` (and Tab) in tab order instead of `d l c r`, which
    mean drop, cockpit and run one screen down. Felt: no habit from the details can drop or start anything.

## README pictures, concretely

- **Re-pick the stills from the same real run, no code needed:** `cockpit.png` from step 93 of
  `tests/recordings/loop-claude-3.jsonl` (`png-loop/loop-claude-3-100x28-at093-rows.svg.png`: the leaf really came
  back, which is what the alt text says), `map.png` from step 2 (`png-loop/loop-claude-3-100x28-at002-m.svg.png`:
  "6 of 27 files may be touched (22%)" before anything ran, the blast radius only Graphene can draw). After 2, 3, 4
  and 8 land, re-render them so "no goal yet", "ant" in red and the bookkeeping news are gone.
- **Re-film the GIF after 1-4** (the false OUTSIDE, the empty first frame, the news words, numbers), and in
  `docs/assets/watch.tape`: hold the board frame (step 2, three questions incl. "a --name flag; nobody asked for
  one") ~4 s instead of 2; at the came-back frame press `i` (the reason and the three ways out with their commands)
  instead of at the end; skip `g` and `m` (the demo repo has 4 files in one folder and two unconnected leaves: both
  screens look empty) and let the map still carry that idea.
- Rendering note: `qlmanage` draws Textual SVGs with a fallback font, so the flow's heavy borders (`┏━┓`) come out
  dashed and squeeze the badge text (`png/running-flow-120x36`); a flow still should be filmed in vhs, not
  converted.

## Not checked

- A live agent behind the screens (all states are API-built plans or recordings); Codex executors; the classic
  screen; mouse clicks; terminals other than Textual's headless driver (colours in a 256-colour terminal, fonts).
- Whether `x` on a running row (acts at once, no prompt) loses work in progress.
- jcode's swarm view itself (only `dev/ui/IDEAS.md`'s and the memory notes' description of it).
- The details pane's "last nothing yet" on a running leaf whose did-rows exist: my scratch rows had no meter or
  hook events, so this may be my data, not the screen.
