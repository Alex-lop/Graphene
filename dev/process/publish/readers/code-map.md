# code-map: the cockpit (`graphene watch`), its agent names, and what to fix before 0.6.0

I read every file in `src/graphene_map/cockpit/` (15 modules), all 16 `tests/test_cockpit_*.py`, plus `tests/cockpit_scene.py` and `tests/cockpit_repo.py`. I also read the entry points: `plan_cli.py` (`watch`, `demo`), what the cockpit takes from `tui.py`, and `views.inputs`. My clone is `<scratch>/agents/code-map`, with `origin` removed. Probe scripts and patches are in `<scratch>/agents/code-map-scratch/`. I also used a scratch test, `tests/test_zz_probe_codemap.py`, which exists only in my clone. Below, "observed" means I ran it. "From the code" means I did not.

**The tree changed while I was reading it.** The task gave night/publish = 921834de. After that, in order:
- 3e38cf24 (23:12): "agents go by numbers", one number per hold of a task.
- 1082b8b0: an amend of 3e38cf24 that numbers per task, by the order tasks were first taken. `dev/process/publish/plan.md` calls this "Done first".
- 04898059: the night's plan.
- 03bb5214: a docs/assets commit.

Line numbers below are at **1082b8b0** unless a line is marked 921834de. The cockpit files are the same at 03bb5214.

## 0. Runs

| tree | command | result (observed) |
|---|---|---|
| 921834de | `uv run pytest tests -q -k cockpit -n 6` | 156 passed in 21.81s |
| 3e38cf24 | same | 157 passed in 29.59s |
| 1082b8b0 | same | 157 passed in 41.71s |
| 1082b8b0 + `per-task-numbers.patch` (§3.3) | same | 156 passed. With an earlier territory fix on top as well: 4 runs, three of them 156 passed, one with 1 failure I did not capture. Likely a timing test under load (other agents share this machine); not identified. |
| 3e38cf24 + the per-task prototype | `uv run pytest tests -q -n 6` (whole suite) | 2 failed, 2028 passed, 18 skipped in 397s. Both failures come from the machine, not the cockpit (details below this table). |
| 1082b8b0 | `uv run ruff check` (cockpit + tests) | All checks passed |
| 1082b8b0 | `uv run ruff format --check` | would reformat `app.py` (one blank line before `def nearest`, :495) and `read.py` (the TOOLS dict :39, `read()`'s signature :62). CI runs only `ruff check` (`.github/workflows/ci.yml:27`), so CI does not fail on this. |

The two whole-suite failures:
- `test_cli.py::test_commands_refuse_to_run_outside_a_git_repo` fails because `~` is itself a git repository: `git -C $TMPDIR rev-parse --show-toplevel` prints `~`.
- `test_teardown.py::test_nothing_graphene_starts_outlives_its_terminal[it closes saying nothing]` passes when run alone (2 passed serially).

## 1. Architecture map

**Entry points**
- **`graphene watch`** (`plan_cli.py:618-663`):
  - `--once` or no TTY → `print_once`.
  - `--classic` or `--view` → `tui.run` (the classic `Watch`, `tui.py:737`, in a 2,840-line module).
  - Otherwise → `cockpit.run(root, open_store, every)` (`cockpit/__init__.py:13-18`), which runs `Cockpit(looker(root, open_store), every, root=, open_store=).run()`.
- **`graphene demo`** (`plan_cli.py:665-734`):
  - `D.load` builds the replay from the recording, and `D.repository` makes a temporary git repository for it.
  - With a TTY → `CockpitReplay(repo, head, lines).run()` (`replay.py:61`); `--classic` → `D.Replay`.
  - `--once` → prints the last frame.

**Modules** (line counts at 1082b8b0)

| module | lines | job | key functions |
|---|---|---|---|
| `read.py` | 309 | the store → `Model`, once a look; the only place the rows read the store or git | `looker:43` (catches only `sqlite3.Error`, `OSError`, `typer.Exit`), `read:62`, `numbers:127`, `fold_done:141`, `live:184`, `proofs:218`, `came_back:240`, `told:247`, `calls:270`, `touched_by_git:285` |
| `model.py` | 184 | the screens' data and the person's state (selection, lens, news) | `Task:30`, `Model.order:97` (questions, then what needs you, then running, ready, waiting, done), `scoreboard:107`, `allowed:115`, `pace:128`, `quiet:137`, `tail:145`, `color:162`, `agent_name:180` |
| `rows.py` | 221 | the cockpit frame as lines | `build_cockpit:21`, `question_line:79`, `right_of:101`, `task_lines:144`, `expansion:179` |
| `app.py` | 516 | the Textual app: canvas, timer, keys → verbs, tell box, the three screens | `Canvas:56`, `look:146`, `paint:154`, `follow:206`, `move:227`, `clicked:249`, `act:273`, `run_all:377`, `open_tell:418`, `on_key:455`, `nearest:495` |
| `verbs.py` | 252 | a key is a `graphene` command: quick ones in process (`tui._cli`), slow ones as processes with their logs in the store's `runs/` folder | `gist:33`, `Doer.run:55`, `background:62`, `_follow:79` (a thread), `stop:88`, then `take`, `pick`, `answer`, `tell`, `widen`, `offer`, `pull_back`, `paint`, `drop`, `reopen`, `command`, `split`, `plan_first`, `undo` |
| `territory.py` / `territory_view.py` | 162 / 101 | the map: folders, owners and bars (pure functions, using Graphene's own `in_scope`) | `group_files:42`, `compute:76`, `bar:143`; `build_territory:22`, `_waits:90` |
| `flow_view.py` / `flowlayout.py` | 64 / 455 | the graph: model → nodes and edges, then a layered layout in box-drawing cells | `flow_graph:18`, `build_flow:27`; `layout:78`, `_draw:220` |
| `details.py` | 144 | `i` / Enter: four panes built by the classic screen's builders, refreshed every second | `pane_text:34`, `Details:61` |
| `help.py` | 86 | `?` | `help_text:46` |
| `replay.py` | 151 | `graphene demo` in the cockpit: applies a recording to a temporary store, 10 times a second | `news:36`, `CockpitReplay.look_at:80`, `play:96`, `action_again:142` |
| `lines.py` | 91 | `Seg`/`Line` (a segment carries a click action), helpers measured in terminal cells | `fit:58`, `fit_end:65`, `fit_keys:81` |
| `look.py` | ~65 | palette, glyphs, short titles; `color_of` and `who` since 3e38cf24 | `short:44` |

**What the cockpit borrows from the classic screen.** `app.py` imports `Ask` and `ASK_HINT`, `verbs.py` imports `_cli` and `as_typed`, and `details.py` imports `detail`, `tail_pane`, `diff_pane`, `record_pane` and `direction_pane`, all from `tui.py`. So `--classic` cannot be deleted without moving these first.

**Data flow, from the store and the session logs to a row on screen**
1. `on_mount` (`app.py:132`) starts `set_interval(every, look)`. Each tick, `look()` (`:146`) calls `looker(previous)`, which calls `read(store, root, previous)`. This runs on the Textual thread.
2. `read` starts from `V.inputs(store)` (`views.py:169`): the nodes that are not dropped or archived, ordered by seq, each with the word a person reads it as (`P.reads`), plus the goal. It keeps the leaves, using `P.kids`, under which a proposed child does not turn its parent into a sub-goal. Each leaf becomes a `Task`: short title, state, scope, needs, and the path down from the goal. The selection, lens, news, file list and git cache carry over from the last model.
3. Each task is then filled in:
   - **Proofs** (`proofs`).
   - **Running, review or came back** (`live`):
     - `R.live` (`run.py:826`) gives the idle time from the meter's newest row, the hooks' last tool call, and the run log's modification time.
     - Then `recent(... did/said/denied, 200)`. The meter writes `did` and `said` from the executor's stream (`meter.py:157`, `:164`); the gate writes `denied` (`gate.py:539`).
     - With no stream (a person's own Claude Code session), it falls back to the hooks' `tool_events` (`calls` → `store.last_events`).
     - Then `touched_by_git` runs (`P.changed_since` and `P.outside_scope`, at most every 5 s per leaf).
   - **Running**: `told()` adds the board notes about the task or anything above it. A note counts as heard once the gate has logged a `told` row (`gate.py:634`).
   - **Came back**: `came_back()` gives the reason (`P.let_go`) and the offer keys (`P.offers`).
   - **Done**: `changed` comes from the last `finished` row. Past 8 done tasks, only the 4 latest stay; the rest become a count.
4. Questions come from `BR.read(store).open`. The selection is the first row of `order()` until the person moves.
5. `paint()` (`app.py:154`) calls `build_cockpit()` (`rows.py:21`), which draws:
   - the header, the scoreboard and the progress bar;
   - for each row: a lead (cursor, state glyph, number), the fitted title, and `right_of` (sparkline, ✎ touched of allowed, ✓ passed of checks, ! stopped, OUTSIDE, ⏸ quiet);
   - for the selected live row only, `expansion`: tail, last note and whether it was heard, verbs, the tell prompt.

   A click on a segment goes to `clicked` and then `act(seg.action)`.
6. Keys go through `on_key` → `act` → `Doer`. Quick commands run in process on the UI thread. Slow ones (`run`, `ask`, `node split|done|signoff`, `verbs.py:30`) run as processes; a thread waits for each and posts the news back with `call_from_thread`.

## 2. Every place an agent's name (now number) is assigned or shown

| what | 921834de (names) | 1082b8b0 (numbers) | reads now |
|---|---|---|---|
| the list of names | `look.py:8-11` NAMES (26) | removed | |
| choosing one | `look.py:35-43` `name_for` (sha1 of the session, the next free name) | `read.py:127-138` `numbers()` (first `started` row per task); `look.py:35-38` `who()` | "agent 1" |
| kept across looks | `model.py:83` `names`, `:180-184` `agent_name`, `read.py:73` | `read.py:80` rebuilt every look; `model.py:180-184` fallback `len+1` | |
| set on a task | `read.py:116` (done), `:174` (live), key from `agent_key` `:296-304` | `read.py:107` (every task), `:189` (live: the fallback) | |
| colour | `look.py:46-47`; `model.py:162-166` (agent's colour, else sha1 of the task id); `rows.py:103`, `:149` | `look.py:30-32`; `model.py:162-166`; `rows.py:103`, `:148` | |
| row lead | `rows.py:151-156` `{name:<6}`, `LEAD = 12` (`:97`; the real lead is 11 cells) | `rows.py:150-155` `{name:<2}`, `LEAD = 8` | `▶ ● 1  users return ids` |
| waiting column | `rows.py:120-123` | `rows.py:119-121` (the id when there is no number) | `← agent 1, agent 2` |
| tell prompt | `rows.py:220` | `rows.py:219` | `tell agent 1: …` |
| graph badge | `flow_view.py:20` (running boxes only) | `flow_view.py:19-20` | `1` on the border |
| graph's info line | `app.py:194` | `app.py:195` | `… running · agent 1 · proof 0/1 …` |
| details title | `app.py:289` | `app.py:290` | `users return ids · agent 1` |
| reopen prompt | `app.py:303` | `app.py:304` | |
| map owners | `territory_view.py:55`, `:62` | `:56`, `:63` (the id when there is no number) | `agent 1 (9)  docs (9)` |
| map's allow button | `territory_view.py:71-74` | `:72-75` | `a: allow agent 1` (the key is wrong, §4 H5) |
| map's "waits for" line | `territory_view.py:98` | `:99` | `tests waits for agent 1: …` |
| verbs | `verbs.py:128`, `:167` | `verbs.py:129`, `:168` | `agent 1 is running: nothing to take` |

**Never named:** `help.py`, the key bars (`app.py:42-46`), the status bar (`app.py:154-186`), and the replay's news (`replay.py:36-53`). The replay's news names node ids instead ("greet: editing app.py", "e2e-xml attempt"). No row shows an id: rows show short titles.

**Tests that pin a name or number (1082b8b0):**
- `cockpit_scene.py:11`, `:17`
- `test_cockpit_rows.py:35`, `:48`, `:71`, `:107` (a comment), `:124`
- `test_cockpit_app.py:174`, `:180`
- `test_cockpit_flow_view.py:14`, `:15`
- `test_cockpit_flowlayout.py:52` (a badge string only)
- `test_cockpit_territory_view.py:30`, `:44` (a comment), `:45`
- `test_cockpit_look.py:4`, `:22-28`
- `test_cockpit_model.py:59-62`
- `test_cockpit_read.py:85-87` (a news string), `:178`, `:204-208`, `:212-215`, `:379-391`, `:450-465`

## 3. Names → numbers

### 3.1 Three numberings on the real recordings (observed)

I replayed every recording in the repository (`src/graphene_map/demo.jsonl` and `tests/recordings/*.jsonl`) through `read()`; probe3 and probe4 are in the scratch folder.

| | per hold (3e38cf24) | **per task, first taken (1082b8b0, landed)** | per task, plan order (`#n`, my prototype) |
|---|---|---|---|
| `graphene demo` (the README GIF) | greet "1", then "3" after its retry; the last frame shows "3" and "2" and no "1" | greet 1, bye 2 | greet #1, bye #2 |
| README still (loop-claude-3, frame 120) | 5, 1, 4 | 1, 2, 3 | #1, #2, then #3 running |
| a retry by a new session | new number (2 → 3) | keeps its number | keeps its number |
| a person's own tasks (started and finished as "alex") | all share one number | one each | one each |
| a task nobody took yet (ready, waiting, proposed) | none | none: blank lead; sentences fall back to ids (`rows.py:121`, `territory_view.py:56`, `:63`, `:72`, `:99`) | every row has one |
| the next plan's first task after `graphene plan archive` of 2 tasks | — | **"agent 3"** (probe8) | #1 |
| a running task with no `started` row (a recording begun mid-run) | — | **shows 1, then 2** once another task is taken; the new task takes 1 (probe10) | its place |
| when numbers change | never; they grow with every hold ever made ("agent 120" after 120 holds: `▶ ● 120 one leaf` overflows the 2-cell slot) | never; they grow with every task ever taken in the store, archived ones included | when a task leaves the plan's tasks (dropped, split and accepted, reordered by `plan edit`), the ones after it renumber |
| cost per look | `numbers()` 3.8 ms on 50,000 log rows (best of 5) | the same scan | none |

### 3.2 If 1082b8b0 stays (the plan's choice), the fixes it still needs

1. **Count only tasks still in the plan**, so a new plan starts at 1. In the `numbers()` SQL (`read.py:132`), use `node_id IN (SELECT id FROM nodes WHERE state NOT IN ('dropped', 'archived'))`.
2. **Remove the fallback** in `live()` (`read.py:189`: `t.agent = m.agent_name(t.id)`) and remove `Model.agent_name` (`model.py:180-184`). The loop at `read.py:107` already sets `t.agent`; the fallback is what lets a number flip between looks (probe10).
3. **Size the lead from the widest number.** `rows.py:154` pads to 2 cells and `:157` subtracts a fixed `LEAD = 8`, so a 3-digit number pushes its own title one cell right. Instead, compute the slot width once per frame and use `room = width - span(lead) - cols - 1`.
4. **Never show ids in sentences** when a task has no number (`rows.py:121`, `territory_view.py:56`, `:63`, `:72`, `:99`): use the title. Lane M already says "owners are agents or titles, never ids".
5. **Fix `dev/ui/IDEAS.md:74`.** At 1082b8b0 it still says "a retry is a new number", which contradicts the code, the commit message and the plan's words ("A task keeps its number through a retry").
6. **Weigh the bare digit, a risk the plan's "1 in a column" accepts.**
   - A question row shows its options as bare digits (`⏎ keep both   1 drop old`).
   - Digits 1-9 pick an option of the *selected* question (`app.py:489`), and the selection starts on the first question (`read.py:118-120`). `tests/test_cockpit_keys.py:38-54` pins that pressing "1" picks.
   - So someone who presses `2` to reach the task numbered 2 picks option 2 of the question instead.
   - `#2` would set the two apart. Alternatively, make a digit on a task row select that task.

### 3.3 The numbering I would pick: one per task, in plan order, written `#n`

**What I recommend.** A task's number is its place among the plan's leaves in the store's order (`V.inputs` sorts by seq). It is assigned in `read()` before finished tasks fold, so a folded task keeps its place.

**Why:**
- Every row has a number from the moment it appears, including what waits and what is only proposed.
- `#1 #2 #3` follows the order `graphene plan` prints.
- A new plan after an archive starts at #1.
- A task's colour never changes. Today a map bar switches from a sha1 colour to the agent's colour when a task is taken (`model.py:162-166`).
- `read.numbers`, `Model.names` and `Model.agent_name` all go away.

**The limit.** A drop, an accepted split or a `plan edit` reorder renumbers the tasks after it. This is marked with a `ponytail:` comment in `read.py`. If it causes trouble, store the number on the node.

**How it reads (observed, from the prototype's frames):**
```
▶ ↩ #1 greet says hello                the word lives in words.py   ⏎ try again
      ┊ edit app.py
      t tell   w widen it   b a sibling   i everything
  ✓ #2 bye says goodbye                1 file
```

| where | text |
|---|---|
| row lead | `▶ ● #1 users return ids` |
| tell prompt | `tell #1: keep ids as strings▌` |
| waiting column | `← #1 #2` |
| map owners | `#1 (9)  #4 (9)  #3 (2)` |
| map's live lens | `!1 stopped  w allow #1` |
| map's "waits for" line | `#3 tests for ids waits for #1: it owns the same files` |
| graph | every box carries `#n` on its bottom border; the info line reads `#1 users return ids  ·  running · proof 0/1 · for API` |
| details title and reopen prompt | `#1 users return ids` |
| verbs | `#1 users return ids is running: nothing to take`, `#2 has no 'b' to offer: …` |
| help | no change needed; optionally `1-9  pick that option of the question under the cursor` |

**Widths:**
- **Lead:** 5 + len(`#n`) cells (7 up to #9, 8 up to #99), against 11 at 921834de and a fixed 8 at 1082b8b0. The title takes the rest (`room = max(12, width - span(lead) - cols - 1)`), so rows never misalign.
- **Waiting column:** 7 cells for `← #1 #2`, against 18 for `← agent 1, agent 2`.
- **Map owner:** 8 cells, against 13.
- **Graph box:** the inner width is at least len(badge) + 4, so `#12` widens only a box whose label is under 7 cells.

**Exact edits.** Verified: cockpit tests 156 passed. Patch: `code-map-scratch/per-task-numbers.patch`, 17 files against 1082b8b0; it applies on 03bb5214.

Code:
- `model.py`:
  - `Task.agent` becomes `n: int = 0`, plus a property `tag` (`"#n"`, else the id).
  - Delete `Model.names`, `agent_name` and the `color_of` import.
  - `color()` becomes `PALETTE[(n-1) % 16]` for a numbered task.
- `read.py`:
  - Delete `m.names = numbers(store)` (`:80`), `numbers()` (`:127-138`) and `t.agent = …` (`:107`, `:189`).
  - Number the leaves in the loop: `for number, n in enumerate(leaves, 1): … Task(…, n=number)`.
- `look.py`: delete `color_of` and `who` (`:30-38`).
- `rows.py`:
  - Delete `LEAD`. `build_cockpit` computes `tags = max(len(t.tag))` and passes it down.
  - The lead becomes `Seg(f"{t.tag:<{tags}} ", f"bold {m.color(t.id)}")`, with the room computed from the lead's real width.
  - Waiting column: `" ".join(o.tag …)`. Tell prompt: `tell {t.tag}: `. Colours (`:103`, `:148`): `m.color(t.id)`.
- `app.py`: `:195` becomes `f" {sel.tag} {sel.title}"` with no agent part; `:290` and `:304` become `f"{task.tag} {task.title}"`.
- `flow_view.py:19-20`: `F.GNode(t.id, t.title, t.state, t.tag)` for every task.
- `territory_view.py`:
  - `:56`, `:63`: `f"{m.tasks[tid].tag} ({n})  "`.
  - `:72`: `m.tasks[…].tag`.
  - `:75`: `"  w allow {whose}"`.
  - `:99`: `f"{t.tag} {t.title} waits for {o.tag}: …"`.
- `verbs.py`: `:129` becomes `f"{t.tag} {t.title} is {t.state}: nothing to take"`; `:168` becomes `t.tag if t else "this"`.

Tests:
- `cockpit_scene.py`: n = 1 to 5 for ids, migrate, tests, docs and schema.
- `test_cockpit_rows.py`: `:35` `"● #1 users return ids"`, `:48` `"← #1 #2"`, `:71` `"tell #1: …"`, `:124` n=6.
- `test_cockpit_app.py`: `:174` n=1; `:180` `"#1 users return ids  ·  running · proof 0/1 · for API"`.
- `test_cockpit_flow_view.py`: `:14` `"#1"`, `:15` docs `"#4"`. `test_cockpit_flowlayout.py:52`: `"#1"`.
- `test_cockpit_territory_view.py`: `:30` `"w allow #1"`, `:39` `"#5 (2)"`, `:45` `"waits for #1: …"`.
- `test_cockpit_look.py`: delete `:22-28` and the import.
- `test_cockpit_model.py:59-62`: becomes a test of `tag` and of the colour coming from the number.
- `test_cockpit_read.py`:
  - `:178` `t.n == 1`.
  - `:204-208`: a ready task has its number (`schema` n == 3).
  - `:212-215`: a task keeps its number across looks.
  - `:379-391`: the same number running, back, retried by a new session, and done.
  - `:450-465` is replaced by: numbers follow the plan's order (ids 1, docs 2, schema 3, notes 4); folded tasks leave the kept ones at their places (d6-d9 → 11-14); a fresh look gives the same numbers.

### 3.4 Decisions for Alex (each flips with one line)

1. `#2` or a bare `2`.
2. A number on every row, or only on tasks an agent took.
3. The number on every graph box, or only on running boxes.
4. Digits only pick a question's option, or a digit on a task row selects that task (so `2 t` would tell #2; this reaches only #1-#9).

### 3.5 Docs and pictures (not in any patch)

- `README.md:43`: "who is on it".
- `CHANGELOG.md:7`: "with its agent's number".
- `dev/ui/IDEAS.md:36-37` and `:73-74`.
- `docs/assets/cockpit.png` and `map.png` show "ant", "otter", "quail" and "ant 1". No committed script renders them: I searched `dev/` for `save_screenshot` and `.png` and found only `dev/screens/meter_shot.py`, for the meter.
- `docs/assets/watch.gif` is filmed with `vhs docs/assets/watch.tape` (about 2 minutes, $0).
- `README.md:74` says "`d` drops a leaf", but the cockpit's `d` drops only a proposal or a question (`verbs.py:195-204`).

## 4. Code smells, dead code, duplication, risky spots

The "lane" column names the night's plan lane whose files are involved; "plan?" says whether `plan.md` already covers the item.

### High

| # | where | what | evidence | lane / plan? |
|---|---|---|---|---|
| H1 | `read.py:54` | A look that raises anything other than `sqlite3.Error`, `OSError` or `typer.Exit` ends the screen mid-run, because Textual stops on an exception in a timer. The classic screen catches the same narrow set (`tui.py:925`, `:941`). `details.pane_text` already does it right: it catches `Exception` and says so (`details.py:57`). | Observed: a malformed told ledger made `json.loads` (`read.py:258`) raise, and the app stopped (`is_running` False). With `look-survives-on-1082b8b0.patch` it stays up and says why. | R / no |
| H2 | `verbs.py:186` | Painting the map's made-up rows writes meaningless globs. Painting "other" adds `other**`, which matches any root path that starts with "other" (`plan._pattern`: `**` → `.*`). Painting a "x/ (new)" row adds `x/ (new)**`. | Observed: the scope became `['api.py', 'other**']`. | S / no |
| H3 | `territory_view.py:43` | The map overflows 80 columns, and the canvas cuts the overflow (`app.py:60`). In the live lens the allow button shows as `a: allow a`, and the third owner's count is lost. The only width test is at 100 columns (`test_cockpit_territory_view.py:15`). | Observed: 84 and 82 cells at 921834de; 85, 94 and 86 at 1082b8b0. `territory-width-on-1082b8b0.patch` fits 80. | M / yes ("80 columns keeps them") |
| H4 | `verbs.py:79-86` | When `:ask` or `s` ends, the news repeats the whole typed paragraph and ends with the CLI's "next:" hint, not with what the planner proposed. The news line is one row high (`app.py:94`), so only the paragraph's first line shows. The classic screen builds "the planner proposed X, Y" (`tui.py:2148-2187`). | Observed on simulated ask output: `"graphene ask 'add a farewell command\nthat says goodbye' ended: next: y accepts, d drops"`, rendered as ` graphene ask 'add a farewell command`. | S / no |
| H5 | `territory_view.py:75` | The button reads `a: allow`, but `a` means answer (`app.py:49`). Clicking the button works. | Observed: `KEYS_TO_VERBS["a"] == "answer"`. | S / M / yes |
| H6 | `rows.py:83` | A question with 3 or more options shows only two. Keys 3-9 pick options nobody can see, and `i` on a question says "select a task to see everything about it" (`app.py:288`). | Observed: `? Which store?  ⏎ sqlite   1 postgres   2 duckdb`; "a json file" and "redis" appear nowhere. | S / no |

### Medium

| # | where | what | evidence |
|---|---|---|---|
| M1 | `app.py:133` → `read()` | Every look's I/O runs on the UI thread:<br>• `P.tracked` every 30 s (`read.py:79`)<br>• `P.changed_since` and `P.outside_scope` every 5 s per live task (`:297`, `:302`)<br>• `R.live` reads a task's *whole* log every look (`run.py:832`), so `ROWS = 200` (`read.py:36`) does not bound a look<br>• quick verbs run the CLI in process (`verbs.py:55-60` → `tui._cli`)<br>`test_cockpit_cost.py:45` takes the second-fastest of looks 2-5, so it never times the look that calls git. | From the code; not measured on a big repository. |
| M2 | `details.py:95` | The details screen refreshes every second and re-runs `git ls-files` (`details.py:56`) on the contract pane and the diff on the changes pane each time. | From the code; not measured. |
| M3 | `verbs.py:188` | Painting a task's only folder sends `node set ID` with no options. The command fails, and the news line repeats "graphene node set ids" twice. | Observed: `✗ graphene node set ids: graphene node set ids needs what to change: …`. `paint-on-1082b8b0.patch` covers this and H2 (test red on 1082b8b0, green with the patch). |
| M4 | `verbs.py:30` | `talk` (hidden, and it spends) is not in `SLOW`, so `:talk …` would run a planner in process and freeze the screen. | From the code; not run (it spends). |
| M5 | `replay.py:66` with `app.py:491` | In a replay, `r` restarts the replay and also reaches the cockpit's `run` verb. | Observed: "a replay: nothing runs here" appears in the news after `r`. |
| M6 | `verbs.py`, `app.py` ↔ `tui.py` | Eight copies of the classic screen's code, already drifting (H4):<br>• `gist` ↔ `tui.py:1657-1662`<br>• `background` ↔ `:2129-2146`<br>• `_follow` ↔ `:2148-2187`<br>• `stop` ↔ `:2196-2215`<br>• `ask_in_editor` ↔ `:1839-1861`<br>• `edit_with` ↔ `:1828-1837`<br>• `run_all` ↔ `:1925-1948`<br>• `terminal_gone` ↔ `:869-873`<br>"--parallel 4" is written twice (`verbs.py:29` list, `tui.py:58` string), and "at most 4" is hard-coded at `app.py:387`. | |
| M7 | `dev/ui/playground/` | A 2,295-line stale copy of the cockpit. Its `flowlayout.py` lacks the cell-width fixes, and `model.py:21-22` still has NAMES. | Observed with `diff`. |

### Low

- **Dead code:**
  - `territory_view.py:77`: `and False`.
  - `Model.extra_edges` (`model.py:73`, `flow_view.py:23`) is never filled in `src`.
  - `build_flow`'s `pan` (`flow_view.py:28`) is never passed.
  - `compute`'s `lens` (`territory.py:81`) is unused.
  - `LIVE_STATES` (`model.py:16`) is unused, while `territory.py:95` and `:118` repeat it inline.
  - `flow_view.py:58`: the conditional is redundant.
  - `read.py:174`: `import json` shadows the module import at `:10`.
  - `__init__.py:9-10`: needless `# noqa: E402`.
- **Labels:**
  - The key bar says `i all` (`app.py:44`); the row (`rows.py:213`) and the replay (`replay.py:78`) say `i everything`.
  - The map's footer (`territory_view.py:84-85`) repeats the key bar (`app.py:46`).
  - The replay keeps the live key bars for the graph and the map (`replay.py:77`), which offer verbs that refuse.
  - The tail's "stopped " is 8 cells wide; the other labels are 5 (`model.py:156`).
  - `verbs.plan_first`'s tuple (`verbs.py:247`) copies `P.FIRST`.
- **Silent cap:** `_waits` checks only `m.files[:400]` (`territory_view.py:98`).
- **Waste:**
  - The replay reads its whole log every look for one maximum timestamp (`replay.py:83`).
  - `r` on a task that is done, running, waiting or proposed still starts a background `graphene run --node X` (`app.py:312-318`).

## 5. Test coverage gaps in the cockpit

Each gap below would be closed by one small test.

- A look that raises an unexpected exception. Added in `look-survives-on-1082b8b0.patch`.
- Painting "other", a "(new)" row, or a task's last folder. Added in `paint-on-1082b8b0.patch`.
- Map width at 80 columns with three owners in the live lens; numbers ≥ 10 and ≥ 100 in the lead; the graph at 80 columns with more than a chain.
- That the key each screen advertises is the key that does it: the map's button against `KEYS_TO_VERBS`.
- What the news says after a background `ask` or `node split`. `test_cockpit_verbs.py:146` checks only that "plan" ends.
- A question with 3 or more options.
- Never tested at all:
  - `:stop` (`Doer.stop`);
  - `x` on a task in review or done (the reopen prompt, then `node reopen`);
  - the `e` and `E` keys themselves (only `:plan edit` is tested, with `edit_with` mocked);
  - `:watch` and `:init` refusing;
  - the `SLOW` routing in `Doer.command`;
  - clicks on `pick:N`, `allow` and `offer:` segments;
  - the tell box closing when its task leaves the rows;
  - the replay's `r` double-firing.
- Cost:
  - `test_cockpit_cost.py` never times the git look, and lets three of four looks be slow.
  - Nothing times the details screen's once-a-second refresh.

## 6. Scratch patches (in `code-map-scratch/`, each checked with `git apply --check` on 03bb5214)

| patch | lane | what | evidence |
|---|---|---|---|
| `look-survives-on-1082b8b0.patch` | R (`read.py`) | `looker` also catches `Exception` and says it on the news line, keeping the last model; adds a test | test red on 1082b8b0 (`ValueError`), green with the patch; the app probe stays running |
| `paint-on-1082b8b0.patch` | S (`verbs.py`) | `paint` refuses "other", "(new)" rows and a task's last folder, and says why; adds a test | red, then green; 13 passed in `test_cockpit_verbs.py` |
| `territory-width-on-1082b8b0.patch` | M (`territory_view.py`) | each folder's tail is built first, so the bar gives way to it; the button reads `w allow`; the dead `and False` goes | no line over 80 in either lens (probe6); 157 cockpit tests passed |
| `per-task-numbers.patch` | R, S, M | the `#n` numbering of §3.3, an alternative to 1082b8b0 | 156 cockpit tests passed; conflicts with the territory patch, which edits the same owner lines |
