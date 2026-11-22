import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";
import * as C from "../src/commands.ts";
import { actsFor, asksYou, attemptsOf, badge, CHANGES, commandChip, commandWord, cornerWord, counts, draftedSteps, edgeKind, editable, fan, filesChip, fitWidth, fitWords, forkActs, forkWords, HEADER_ACTS, headerFor,
         checkWords, heldWords, linkHint, mayRun, OUTSIDE, OUTSIDE_OWN, paneKey, pipeline, planningLine, provesNothing, replayLine, scopeTree, stopAfterPlan, stopsOf, sub, tabOrder, tokenWords, topLine,
         whenEdit, who, worktrees, writtenOf, type StateX, type TaskX } from "../src/graph/words.ts";
import { SAY, WORDS } from "../src/state.ts";
import { ICONS } from "../src/graph/icons.ts";
import { layout } from "../src/layout.ts";
import { autoLine, parseState } from "../src/state.ts";

const race = JSON.parse(readFileSync(new URL("./fixtures/graph-race.json", import.meta.url), "utf8"));
const parsed = parseState(JSON.stringify(race));
// the fields the parser does not know yet, as the preview page carries them over
const tasks: TaskX[] = parsed.tasks.map((t) => {
  const r = race.tasks.find((x: { id: string }) => x.id === t.id);
  return { ...t, why: r.why, attempts: r.attempts,
           forks: t.forks.map((f) => ({ ...f, ...r.forks.find((x: { letter: string }) => x.letter === f.letter) })) };
});
const task = (id: string) => tasks.find((t) => t.id === id)!;
const state: StateX = { ...parsed, tasks };

test("narrow, the header is the goal alone: the counts and the auto line move to its hover and the footer", () => {
  const wide = headerFor(state, false);
  assert.equal(wide.goal, state.goal);
  assert.equal(wide.counts, counts(state));
  assert.equal(wide.auto, autoLine(state));
  assert.equal(wide.footer, "");
  const narrow = headerFor(state, true);
  assert.equal(narrow.goal, state.goal);
  assert.equal(narrow.counts, "");
  assert.equal(narrow.auto, "");
  assert.equal(narrow.hover, [state.goal, counts(state), autoLine(state)].filter(Boolean).join("\n"));
  assert.equal(narrow.footer, autoLine(state) || counts(state)); // the live line first, else the counts
  assert.equal(headerFor({ ...state, auto: null }, true).footer, counts(state));
});

test("words drop from the end until they fit, the first always stays", () => {
  assert.equal(fitWords(["a", "", "bb", "ccc"], 100), "a · bb · ccc");
  assert.equal(fitWords(["a", "bb", "ccc"], 6), "a · bb");
  assert.equal(fitWords(["a long first word"], 3), "a long first word");
});

test("a task that needs help says why on its box; a running one its agent, attempts and seconds quiet", () => {
  assert.equal(sub(task("logs"), 60), "needs help · app.py is outside its files · 2 tries · $0.02");
  assert.equal(sub(task("logs")), "needs help · app.py is o…"); // the reason is cut to the box, never dropped
  assert.equal(sub(task("greet"), 60), "agent 3 · 3 attempts · $0.31");
  const quiet = { ...task("greet"), forks: [], idle: 40 };
  assert.equal(sub(quiet, 60), "agent 3 · working · $0.31 · 40 s quiet");
  // an older CLI's snapshot, as parseState fills it: no reason and no tries, so the old words
  const old = { ...task("logs"), why: "", attempts: 0 };
  assert.equal(sub(old, 60), "needs help · 1 outside · $0.02");
});

test("the pane's key changes with the selected task, its question and its needs, not with the rest", () => {
  const key = paneKey(state, "farewell", false);
  assert.ok(key);
  const elsewhere = { ...state, tasks: state.tasks.map((t) => (t.id === "hello" ? { ...t, usd: 0.009 } : t)) };
  assert.equal(paneKey(elsewhere, "farewell", false), key); // a change elsewhere: the pane stands
  const own = { ...state, tasks: state.tasks.map((t) => (t.id === "farewell" ? { ...t, usd: 0.5 } : t)) };
  assert.notEqual(paneKey(own, "farewell", false), key);
  const asked = { ...state, questions: [{ id: "q9", text: "which?", options: ["a"], default: "a", about: "farewell", asked: "" } as never] };
  assert.notEqual(paneKey(asked, "farewell", false), key);
  assert.notEqual(paneKey(state, "farewell", true), key); // a replay offers other acts
  assert.equal(paneKey(state, null, false), "");
  assert.equal(paneKey(state, "nope", false), "");
});

test("the kept fork's chip says so in the cockpit's words; a running one its progress before its state word", () => {
  const g = task("greet");
  const chip = (letter: string, max?: number) => forkWords(g.forks.find((f) => f.letter === letter)!, g.kept, max);
  assert.equal(chip("b", 60), "b ✓ kept: 4 lines against 12 · 4 lines · $0.07");
  assert.equal(chip("b"), "b ✓ kept: 4 lines against 12");
  assert.equal(chip("a", 60), "a · Nano · gave up · 12 lines · 2 tries · $0.09"); // finished: the state is the news
  assert.equal(chip("a"), "a · Nano · gave up · 12 lines");
  assert.equal(chip("c", 60), "c · Super · 7 lines · 23 s quiet · $0.15 · running"); // running: the numbers are the news
  assert.equal(chip("c"), "c · Super · 7 lines · 23 s quiet"); // the chip's own width holds the progress
  assert.equal(forkWords({ ...g.forks[2]!, idle: 0 }, g.kept), "c · Super · 7 lines · $0.15");
});

test("a long kept reason is cut to the chip, never drawn past it", () => {
  const g = task("greet");
  const why = "left the check's own files as they were (a changed tests/test_app.py)"; // pick.py's untouched step
  const chip = forkWords(g.forks.find((f) => f.letter === "b")!, { ...g.kept!, why }, 28);
  assert.ok(chip.length <= 28, chip);
  assert.equal(chip, "b ✓ kept: left the check's…");
});

test("the replay line is the terminal replay's top line, and nothing when the store is the person's", () => {
  assert.equal(replayLine({ shown: "a scripted stand-in, no model ran", day: "2026-10-26", repository: "wordkit" }),
               "replay · a scripted stand-in, no model ran · 2026-10-26");
  assert.equal(replayLine(null), "");
  assert.equal(replayLine(undefined), "");
});

test("a live race against the stand-in says so first; a replay's line wins; a real run says nothing", () => {
  assert.equal(topLine({ replay: null, stand_in: true }), "practice run · a scripted stand-in, no real AI");
  assert.equal(topLine({ replay: null, stand_in: false }), "");
  // an older CLI sends no stand_in: parseState fills false, the line above
  assert.equal(topLine({ replay: { shown: "a scripted stand-in, no model ran", day: "", repository: "" }, stand_in: true }),
               "replay · a scripted stand-in, no model ran");
});

test("a replay offers none of the header's acts: the cockpit would open graphene watch in the person's folder", () => {
  for (const [id, act] of HEADER_ACTS) assert.ok(CHANGES.includes(act), `${id} (${act}) stays in a replay`);
});

test("a replay offers no diff either: openDiff and compareForks run in the person's folder, not the replay's", () => {
  for (const act of ["openDiff", "compareForks"]) assert.ok(CHANGES.includes(act as never), `${act} acts outside the replay`);
  for (const t of tasks) {
    assert.deepEqual(actsFor(t, true), [], `${t.id} (${t.state}) offers nothing in a replay`);
    for (const f of t.forks) assert.deepEqual(forkActs(t, f, true), [], `fork ${f.letter} of ${t.id} offers nothing in a replay`);
  }
});

test("the link hint names the task, says Cancel as well as Esc, and drop while a dot is dragged", () => {
  assert.equal(linkHint("hello", false), "link: click the task that waits on “hello” · Cancel or Esc stops it");
  assert.equal(linkHint("hello", true), "link: drop it on the task that waits on “hello” · Cancel or Esc stops it");
});

test("a task offers the acts its state takes; a replay offers only what reads", () => {
  const acts = (id: string, replay = false) => actsFor(task(id), replay).map((b) => b.act);
  assert.deepEqual(acts("farewell"), ["signOff", "openDiff", "compareForks", "add-after", "add-under", "link"]);
  assert.deepEqual(acts("logs"), ["handBack", "openDiff", "add-after", "add-under", "link", "tell"]);
  assert.deepEqual(acts("ship"), ["add-after", "add-under", "link", "drop", "tell"]); // no Edit: the pane is the form
  assert.deepEqual(acts("farewell", true), []);
  assert.deepEqual(acts("ship", true), []);
  assert.equal(actsFor(task("farewell"), false)[0]!.main, true);
});

test("a button's hover names the graphene command its click runs", () => {
  const named = (b: { title: string }, argv: string[]) => assert.ok(b.title.includes(`graphene ${argv.slice(0, 2).join(" ")}`), `"${b.title}" names ${argv.join(" ")}`);
  const r = actsFor(task("farewell"), false);
  named(r.find((b) => b.act === "signOff")!, C.signOff("farewell"));
  named(actsFor({ ...task("ship"), state: "proposed" }, false).find((b) => b.act === "accept")!, C.accept("ship"));
  const f = task("farewell");
  named(forkActs(f, f.forks[0]!, false).find((b) => b.act === "pickFork")!, C.pickFork("farewell", "a"));
});

test("a fork in review offers Keep beside its changes; elsewhere only its changes", () => {
  const f = task("farewell");
  assert.deepEqual(forkActs(f, f.forks[0]!, false).map((b) => [b.act, b.fork]), [["openDiff", "a"], ["pickFork", "a"]]);
  assert.deepEqual(forkActs(f, f.forks[0]!, true), []);
  const g = task("greet");
  assert.deepEqual(forkActs(g, g.forks[1]!, false).map((b) => b.act), ["openDiff"]);
});

test("text is cut to a measured width, with an ellipsis, in a few measures", () => {
  let measures = 0;
  const mono = (t: string) => { measures++; return t.length * 7; }; // 7 px a character
  assert.equal(fitWidth("short", 100, mono), "short");
  assert.equal(fitWidth("abcdefghijklmnop", 70, mono), "abcdefghi…"); // 10 characters at 7 px
  measures = 0;
  const wide = (t: string) => { measures++; return [...t].reduce((w, c) => w + (c === "W" ? 14 : 7), 0); }; // a wide W
  const out = fitWidth("WWWWWWWWWWWWWWWWWWWW", 70, wide);
  assert.ok(wide(out) <= 70, out);
  assert.ok(out.endsWith("…") && out.length >= 5, out);
  assert.ok(measures <= 8, `${measures} measures`);
  assert.equal(fitWidth("abc", 1, mono), "a…"); // never empty: one character and the ellipsis at least
});

test("the corner's word is the running task's model, cut to about six characters, or the mark that it needs you", () => {
  const greet = task("greet"); // running, Nano
  assert.equal(cornerWord(greet), "Nano");
  assert.equal(cornerWord({ ...greet, model: "claude-sonnet-4-5" }), "claude…");
  assert.equal(cornerWord({ ...greet, model: "qwen3-coder-480b" }), "qwen3-…");
  assert.equal(cornerWord(task("farewell")), "◆"); // in review: it needs you
  assert.equal(cornerWord(task("hello")), "");
});

test("a card's tile says who does the step: you, the executor by its letter, or a command by its first letters", () => {
  const greet = task("greet");
  assert.deepEqual(who(greet, "claude"), { kind: "claude", mark: "C", label: "Claude Code" });
  assert.deepEqual(who(greet, "codex --full-auto"), { kind: "codex", mark: "X", label: "Codex" });
  assert.equal(who(greet, "nemotron").mark, "N");
  assert.deepEqual(who(greet, "stand-in"), { kind: "agent", mark: "S", label: "stand-in" }, "the demo's scripted stand-in");
  assert.deepEqual(who(greet, "/usr/local/bin/aider --yes {prompt}"), { kind: "cmd", mark: "ai", label: "aider" });
  assert.equal(who(greet, "").mark, "?");
  assert.equal(who({ ...greet, owner: "alex" }, "claude").kind, "you", "a task you took is yours, whoever the executor is");
  assert.equal(who({ ...greet, state: "yours" }, "claude").kind, "you");
});

test("the files chip names the first path and counts the rest; a card with no files has none", () => {
  assert.equal(filesChip(["src/export/**"]), "src/export/**");
  assert.equal(filesChip(["app.py", "tests/test_app.py", "README.md"]), "app.py +2");
  assert.equal(filesChip([]), "");
});

test("an edge moves where an agent is working, is green where the work landed, and waits until then", () => {
  assert.equal(edgeKind(task("hello"), task("greet")), "run"); // done into running: the work is on its way
  assert.equal(edgeKind(task("hello"), task("bye")), "done");
  assert.equal(edgeKind(task("hello"), undefined), "done", "a landed task's edge into the goal");
  assert.equal(edgeKind(task("farewell"), undefined), "wait", "in review: nothing landed yet");
  assert.equal(edgeKind(task("logs"), task("docs")), "wait");
  // the edge that crosses the line starts at the goal, which is no task: green once the step past it has run
  assert.deepEqual([edgeKind(undefined, { state: "done" }), edgeKind(undefined, { state: "yours" })], ["done", "wait"]);
});

test("a card's mark: landed, working, needs you, came back; a suggested task has none, its dashed card says it", () => {
  assert.equal(badge(task("hello")), "done");
  assert.equal(badge({ ...task("greet"), needs_you: false }), "running");
  assert.equal(badge(task("greet")), "you", "a question on a working task: it needs you first");
  assert.equal(badge(task("farewell")), "you");
  assert.equal(badge(task("logs")), "back");
  assert.equal(badge({ ...task("farewell"), state: "proposed" }), "");
  assert.equal(badge({ ...task("hello"), state: "waiting", needs_you: false }), "");
});

test("this machine counts a worktree for each agent at work: each running attempt's, or the task's own", () => {
  const greet = task("greet");
  const running = { ...greet, forks: greet.forks.map((f, i) => ({ ...f, checkout: i < 2 ? `/tmp/w${i}` : null })) };
  assert.equal(worktrees([running]), 2);
  assert.equal(worktrees([{ ...greet, forks: [], checkout: "/tmp/w" }]), 1);
  assert.equal(worktrees([{ ...greet, forks: [], checkout: null }]), 0);
});

test("while a planner writes, its finished steps are drawn: tasks only, and none the plan already has", () => {
  const writing = parseState(readFileSync(new URL("./fixtures/drafting.json", import.meta.url), "utf8")) as StateX;
  assert.deepEqual(draftedSteps(writing).map((d) => d.id), ["failing", "rows", "button", "empty"], "the sub-goal is a band, not a box");
  assert.equal(planningLine(writing), "The planner (claude) is drawing: 4 steps so far");
  const one = { ...writing, drafting: { ...writing.drafting!, steps: writing.drafting!.steps.slice(0, 2) } };
  assert.equal(planningLine(one), "The planner (claude) is drawing: 1 step so far");
  // a line that names a task the plan has is an anchor: the task is drawn once, as itself
  const anchored = { ...state, drafting: { by: "claude", live: true, steps: [{ id: "greet", title: "greet route", parent: null, leaf: true, scope: [], check: null, needs: [] },
                                                                              { id: "new", title: "a new step", parent: null, leaf: true, scope: [], check: null, needs: ["greet"] }] } };
  assert.deepEqual(draftedSteps(anchored).map((d) => d.id), ["new"]);
  // a planner whose stream has no text: the boxes come with the plan, and the graph says so
  assert.equal(planningLine({ ...writing, drafting: { by: "codex", live: false, steps: [] } }), "The planner (codex) is writing: its steps appear when the plan arrives");
  assert.equal(planningLine(state), "", "no planner is writing");
});

test("a card whose check already passes says so under it until the work is done: it proves nothing yet", () => {
  const ship = { ...task("ship"), hollow: true }; // waiting
  assert.equal(sub(ship, 60), "waiting · check already passes");
  assert.equal(provesNothing(ship), true);
  assert.equal(provesNothing({ ...ship, state: "running" }), true);
  assert.equal(provesNothing({ ...ship, state: "done" }), false, "done or in review, the pane and Home say what it proved");
  assert.equal(provesNothing(task("ship")), false);
});

test("a command step: its tile is the command's word, and one past the line asks you before it runs", () => {
  const wf = parseState(readFileSync(new URL("./fixtures/workflow.json", import.meta.url), "utf8")) as StateX;
  const suite = wf.tasks.find((t) => t.id === "suite-48")!, pr = wf.tasks.find((t) => t.id === "pr-48")!;
  assert.deepEqual(who(suite, "claude"), { kind: "cmd", mark: "uv", label: "a command, with no agent" });
  assert.equal(who(pr, "claude").mark, "gh");
  assert.equal(commandWord("/usr/bin/python3 -m unittest"), "python3");
  assert.equal(commandWord('cd "$(git rev-parse --git-common-dir)/.." && git push -u origin HEAD'), "git", "the command that leaves, not the cd before it");
  assert.equal(commandWord("cd web && npm test"), "npm");
  // the chip shows the part the tile names, so a step past the line says what leaves and not the cd before it
  assert.equal(commandChip('cd "$GRAPHENE_CHECKOUT" && git push -u origin HEAD && gh pr create --draft --fill'), "gh pr create --draft --fill");
  assert.equal(commandChip("uv run pytest -q"), "uv run pytest -q");
  assert.deepEqual([asksYou(pr), asksYou(suite)], [true, false]);
  assert.equal(sub(pr, 36), "asks you: it leaves your machine");
  assert.equal(sub({ ...suite, state: "ready", checked: { before: null, after: "failed" } }, 60), "its command failed: a run tries it again");
  assert.deepEqual(actsFor(pr, false)[0], { label: "Approve and run", act: "markDone", icon: "check", main: true,
    title: "it leaves your machine: graphene node done runs git push -u origin HEAD && gh pr create --draft --fill" });
  assert.equal(actsFor(suite, false).some((b) => b.act === "markDone"), false, "a command step before the line runs by itself");
  assert.equal(badge(pr), "you");
  assert.deepEqual(pipeline(wf).map((x) => `${x.label} ${x.at}${x.note ? `: ${x.note}` : ""}`), ["Plan done: 4 steps", "Run now: 1 asks you", "Review next"]);
  // it is its command alone: the pane's form (files, attempts, your approval, whose it is) is closed, and the line says where it changes
  const ready = { ...suite, state: "ready" as const };
  assert.deepEqual([editable(ready, false), editable(pr, false)], [false, false]);
  for (const t of [ready, pr]) assert.equal(whenEdit(t), "A command step is its command alone: no files, no attempts, no agent. Change its run: line in the plan's text.");
  assert.match(whenEdit(suite), /^Done:/, "finished, it is not edited, as any task");
  assert.deepEqual(actsFor(ready, false).map((b) => b.act), ["add-after", "add-under", "link", "drop"], "no agent to message");
  // nothing is drawn after a step past the line: a task there would land in the first column, its edge running backwards
  assert.deepEqual(actsFor(pr, false).map((b) => b.act), ["markDone", "add-under"]);
  // the run executes a command itself, so the step never reads `running`: a run going with one ready is running it
  const going = { ...wf, run: { going: true, pid: 1 }, tasks: wf.tasks.map((t) => (t === suite ? ready : t === pr ? { ...pr, state: "waiting" as const } : t)) };
  assert.equal(pipeline(going)[1]!.note, "running a command");
});

test("one pipeline, the plan first: Plan, Run, Review, and where the work is in it", () => {
  const fx = (name: string) => parseState(readFileSync(new URL(`./fixtures/${name}.json`, import.meta.url), "utf8")) as StateX;
  const at = (s: StateX) => pipeline(s).map((x) => `${x.label} ${x.at}${x.note ? `: ${x.note}` : ""}`);
  assert.deepEqual(at(fx("empty")), ["Plan now", "Run next", "Review next"]);
  assert.deepEqual(at(fx("drafting")), ["Plan now: 4 steps so far", "Run next", "Review next"]);
  assert.deepEqual(at({ ...fx("drafting"), drafting: { by: "codex", live: false, steps: [] } }), ["Plan now: the planner is writing", "Run next", "Review next"]);
  assert.deepEqual(at(fx("proposals")), ["Plan now: 4 steps · 1 question", "Run next", "Review next"]); // suggested: it waits for Start
  assert.deepEqual(at(state), ["Plan done: 7 steps · 1 question", "Run now: 1 working", "Review next: 2 to review"]); // what waits for you is said while the rest runs
  const all = (word: TaskX["state"]) => ({ ...state, questions: [], run: { going: false, pid: null }, tasks: state.tasks.map((t) => ({ ...t, state: word })) });
  assert.deepEqual(at(all("ready")), ["Plan done: 7 steps", "Run now: 7 ready", "Review next"]);
  assert.deepEqual(at({ ...all("ready"), run: { going: true, pid: 1 } }), ["Plan done: 7 steps", "Run now: starting", "Review next"]);
  assert.deepEqual(at(all("review")), ["Plan done: 7 steps", "Run done", "Review now: 7 to review"]);
  assert.deepEqual(at(all("done")), ["Plan done: 7 steps", "Run done", "Review done: landed"]);
  // something suggested while agents work (an agent's proposal, a second ask): the work is still at Run, and the plan says what waits
  const more = { ...state, tasks: [...state.tasks, { ...task("ship"), id: "extra", state: "proposed" as const }] };
  assert.deepEqual(at(more), ["Plan done: 8 steps · 1 suggested · 1 question", "Run now: 1 working", "Review next: 2 to review"]);
  const back = { ...all("ready"), tasks: all("ready").tasks.map((t, i) => (i ? t : { ...t, state: "came back" as const })) };
  assert.equal(at(back)[1], "Run now: 1 needs help");
  assert.deepEqual(at({ ...all("done"), run: { going: true, pid: 1 } }), ["Plan done: 7 steps", "Run done", "Review done: landed"], "a run winding down has nothing left to start");
  // the switch is the envelope's auto setting, the other way round; an older CLI that says nothing leaves it on
  assert.equal(stopAfterPlan(fx("proposals")), true);
  assert.equal(stopAfterPlan({ envelope: { auto: "on" } }), false);
});

// ---- the pane's Scope tab ----
const scoped = parseState(JSON.stringify({
  tree: ["src/", "tests/", "web/", "README.md"], allows: ["graphene node *", "graphene plan *"], executor: "claude",
  tasks: [
    { id: "rows", title: "Export the visible rows", state: "running", scope: ["src/export/**"], check: "pytest -k export",
      files: ["src/export/__init__.py", "src/export/csv.py", "src/export/formats.py", "src/export/rows.py"], files_n: 4,
      touched: ["src/export/csv.py", "src/export/rows.py"], checked: { before: "red", after: null },
      tokens: { read: 41000, cached: 30000, written: 6000, turns: 14 }, held: { state: "refused", by: "claude" } },
    { id: "button", title: "Add the Export button", state: "running", scope: ["web/table/**"], files: ["web/table/button.tsx"], files_n: 1,
      stops: [{ path: "README.md", at: "2026-11-17T12:41:00", how: "Write" }], held: { state: "caught", by: "codex" } },
    { id: "test", title: "A test that fails today", state: "done", scope: ["tests/test_export.py"], files: ["tests/test_export.py"], files_n: 1,
      changed: ["tests/test_export.py"], check: "pytest -k export", checked: { before: "passes", after: "passed" } },
    { id: "docs", title: "Say it in the docs", state: "yours", scope: ["docs/EXPORT.md"], held: { state: "none", by: "you" } },
  ],
})) as StateX;
const step = (id: string) => scoped.tasks.find((t) => t.id === id)!;

test("May change is a tree: its folder opened to its files, the written ones marked, another step's named, the rest dim", () => {
  assert.deepEqual(scopeTree(step("rows"), scoped).map((r) => `${"  ".repeat(r.depth)}${r.name} [${r.kind}]${r.note ? ` ${r.note}` : ""}`), [
    "src/export/ [in]", "  __init__.py [in]", "  csv.py [in] written", "  formats.py [in]", "  rows.py [in] written",
    "tests/ [other] another step's", "web/ [other] another step's", "README.md [out]",
  ]);
  assert.equal(writtenOf(step("rows")), "2 of 4");
  const top = { id: "top", scope: ["wordkit/cli.py", "tests/test_top.py"], files: ["wordkit/cli.py"], filesN: 1, touched: [], changed: ["tests/test_top.py", "wordkit/cli.py"] };
  assert.equal(writtenOf(top), "2 of 2", "a file it created counts");
  assert.deepEqual(scopeTree(top, { tree: [], tasks: [] }).map((r) => `${r.name} ${r.note}`), ["tests/ ", "test_top.py written", "wordkit/ ", "cli.py written"], "and is drawn under its folder");
  // a write outside its files is not one of them: the finish refuses it, so the count and the tree leave it out
  const strayed = { ...top, files: ["wordkit/cli.py", "tests/test_top.py"], filesN: 2, touched: ["README.md", "wordkit/cli.py"], changed: [] };
  assert.equal(writtenOf(strayed), "1 of 2");
  assert.ok(!scopeTree(strayed, { tree: [], tasks: [] }).some((r) => r.name === "README.md"));
  // a replay's repository is empty, and an older CLI names no files: what is there is not known, so no path says "not there yet"
  assert.deepEqual(scopeTree({ ...top, files: [], filesN: 0, changed: [] }, { tree: [], tasks: [] }).map((r) => `${r.name} ${r.note}`), ["tests/test_top.py ", "wordkit/cli.py "]);
  // a scope past the 200 files a snapshot lists: its other folders are still its own, and the rest are counted
  const wide = { id: "all", scope: ["**"], files: ["a/x.py"], filesN: 300, touched: [], changed: [] };
  assert.deepEqual(scopeTree(wide, { tree: ["a/", "z/", "README.md"], tasks: [] }).map((r) => `${"  ".repeat(r.depth)}${r.name} [${r.kind}]`),
                   ["a/ [in]", "  x.py [in]", "z/ [in]", "README.md [in]", "… and 299 more files [in]"]);
  // a path the step will create is its own, and says it is not there yet; a finished step's changes are its written files
  assert.deepEqual(scopeTree(step("docs"), scoped).filter((r) => r.kind === "in"), [{ name: "docs/EXPORT.md", depth: 0, kind: "in", note: "not there yet" }]);
  assert.deepEqual(scopeTree(step("test"), scoped).filter((r) => r.kind === "in"), [{ name: "tests/", depth: 0, kind: "in", note: "" },
                                                                                   { name: "test_export.py", depth: 1, kind: "in", note: "written" }]);
  assert.equal(writtenOf(step("docs")), "");
  // a long folder is cut, and says how many more; an older CLI with no tree still shows the step's own files
  const many = { ...step("rows"), files: Array.from({ length: 15 }, (_, i) => `src/export/f${i}.py`), filesN: 15, touched: [] };
  assert.equal(scopeTree(many, scoped).filter((r) => r.kind === "in").at(-1)?.name, "… and 3 more");
  assert.deepEqual(scopeTree(step("rows"), { tree: [], tasks: [step("rows")] }).map((r) => r.name), ["src/export/", "__init__.py", "csv.py", "formats.py", "rows.py"]);
});

test("May run, Held by, Stopped, Done when and Tokens say what is known, and no more", () => {
  assert.deepEqual(mayRun(scoped, step("rows")), { commands: ["graphene node *", "graphene plan *"], words: "", outside: OUTSIDE });
  assert.match(mayRun({ allows: null, executor: "claude" }, step("rows")).words, /^any command: what a command writes is still held/);
  // the list is the repository's executor's: a step Codex holds, or one that is yours, is not under it
  assert.deepEqual(mayRun(scoped, step("button")), { commands: [], words: "any command: what a command writes is still held to its files", outside: OUTSIDE_OWN });
  assert.deepEqual(mayRun(scoped, step("docs")), { commands: [], words: "any command", outside: OUTSIDE_OWN });
  // the setting names the model (`claude:opus`), a run names the holder by family (`claude`): the same executor, the same list and name
  assert.deepEqual(mayRun({ ...scoped, executor: "claude:opus" }, step("rows")).commands, ["graphene node *", "graphene plan *"]);
  assert.match(heldWords({ held: { state: "refused", by: "claude:opus" } }).proof, /^Claude Code's hook/);
  // held: three states, each as the tests prove it; a Graphene that does not say is not held, never a shield
  assert.deepEqual([heldWords(step("rows")).shield, heldWords(step("rows")).line], [true, "A write outside its files is refused before it happens."]);
  assert.match(heldWords(step("rows")).proof, /^Claude Code's hook, proven by tests\/test_every_agent\.py$/);
  assert.match(heldWords(step("button")).line, /caught when it finishes/);
  assert.deepEqual([heldWords(step("docs")).shield, heldWords(step("docs")).line], [false, "Not held: nothing stops a write outside its files."]);
  assert.equal(heldWords({ held: { state: "", by: "" } }).shield, false);
  // stopped: here against the run; a step with none shows where the run's were
  const here = stopsOf(step("button"), scoped.tasks);
  assert.equal(here.count, "1 here · 1 in the run");
  assert.deepEqual(here.rows, [{ line: "tried README.md", note: "refused 12:41 · Write · it carried on in its own files" }]);
  assert.deepEqual(stopsOf(step("rows"), scoped.tasks), { count: "0 here · 1 in the run",
    rows: [{ line: "“Add the Export button” tried README.md", note: "refused 12:41 · Write · it carried on in its own files" }] });
  const back = { ...step("button"), state: "came back" as const };
  assert.equal(stopsOf(back, [back]).rows[0]!.note, "refused 12:41 · Write", "a step that came back did not carry on");
  // done when: before and after the work
  assert.deepEqual(checkWords(step("rows")), [{ tone: "red", line: "failed before the work, so it can tell" },
                                              { tone: "dim", line: "runs in a clean copy when the agent says done" }]);
  assert.deepEqual(checkWords(step("test")).map((x) => x.tone), ["warn", "ok"], "it passed before the work too: it proved nothing");
  assert.deepEqual(checkWords(step("docs")), [{ tone: "dim", line: "no check: your approval finishes it" }]);
  // tokens: reading and writing as shares; the check costs none
  assert.deepEqual(tokenWords(step("rows")), { total: "41k in · 6k out", read: 87, written: 13,
    line: "reading 87% (30k of it from cache) · writing 13% · its check 0%: Graphene runs it, no model" });
  assert.equal(tokenWords(step("button")), null, "no meter, or nothing spent yet");
});

test("an icon the graph's page asks for by name is one it has: the goal chip's arrow was a blank", () => {
  const src = (file: string) => readFileSync(new URL(`../src/graph/${file}`, import.meta.url), "utf8");
  // `icon("close")`, `icon(going ? "debug-stop" : "play")` on the page; `icon: "check"` on a button's words
  const asked = [...src("main.ts").matchAll(/\bicon\(([^()]*)\)/g)].flatMap((m) => [...m[1]!.matchAll(/(?:^|[?:]\s*)"([a-z-]+)"/g)].map((n) => n[1]!));
  asked.push(...[...src("words.ts").matchAll(/\bicon: "([a-z-]+)"/g)].map((m) => m[1]!));
  assert.ok(asked.includes("arrow-right") && asked.includes("play") && asked.includes("check"), "the page's source is read as it is written");
  assert.deepEqual([...new Set(asked)].filter((name) => !ICONS[name]), []);
});

test("every icon is a path; Tab walks the boxes wave by wave, then down each wave", () => {
  for (const [name, d] of Object.entries(ICONS)) assert.match(d, /^M/, `${name} has no path`);
  const edges = parsed.edges.filter(([, , kind]) => kind === "needs").map(([a, b]) => [a, b] as [string, string]);
  const lay = layout(tasks.map((t) => ({ id: t.id, band: t.parent ?? "" })), edges);
  const order = tabOrder(lay, tasks.map((t) => t.id));
  assert.equal(order.length, tasks.length);
  const rank = (id: string) => lay.boxes[id]!.rank, y = (id: string) => lay.boxes[id]!.y;
  for (let i = 1; i < order.length; i++) {
    const a = order[i - 1]!, b = order[i]!;
    assert.ok(rank(a) < rank(b) || (rank(a) === rank(b) && y(a) <= y(b)), `${a} before ${b}`);
  }
  assert.ok(order.indexOf("logs") < order.indexOf("greet")); // logs sits in wave 1, greet in wave 2, whatever the state's order
});

test("the fan is drawn before anything runs: one waiting chip for each attempt a task is set to", () => {
  const ship = { ...task("ship"), state: "ready" as const, forks: [], check: "pytest -q" };
  assert.deepEqual(fan({ ...ship, planned: 3 }, null).map((f) => f.letter), ["a", "b", "c"]);
  assert.equal(forkWords(fan({ ...ship, planned: 3 }, null)[0]!, null), "a · waiting");
  assert.equal(fan({ ...ship, planned: null }, 2).length, 2, "unset on the task: the limits' number");
  assert.equal(fan({ ...ship, planned: 1 }, 3).length, 0, "the task's own number comes first, and one attempt has no fan");
  assert.equal(fan({ ...ship, planned: 3, check: null }, null).length, 0, "no check: it runs as one agent");
  assert.equal(fan({ ...ship, planned: 3, state: "done" }, null).length, 0, "only before it starts");
  assert.equal(fan({ ...ship, planned: null, command: "pytest -q" }, 3).length, 0, "a command step runs once, with no agent, whatever the limits say");
  assert.equal(fan(task("farewell"), 8), task("farewell").forks, "attempts that ran are the fan");
  assert.equal(attemptsOf({ planned: null }, null), 1);
  assert.equal(attemptsOf({ planned: null }, 4), 4);
  assert.equal(attemptsOf({ planned: 2 }, 4), 2);
});

test("every state says what an edit does now, in the screen's words; only a finished task's form is closed", () => {
  const starts = { proposed: "Suggested:", ready: "Not started:", waiting: "Not started:", running: "Working now:", review: "To review:",
                   "came back": "Needs help:", yours: "Yours:", done: "Done:" };
  assert.equal(SAY.proposed, "suggested"); // the line opens with the state as the box says it
  for (const state of WORDS) {
    const line = whenEdit({ state });
    assert.ok(line.startsWith(starts[state]), `${state}: ${line}`);
    assert.doesNotMatch(line, /\b(fork|leaf|scope|node)s?\b/i, `${state} says attempt, task, files, check`);
    assert.equal(editable({ state }, false), state !== "done");
    assert.equal(editable({ state }, true), false, "a replay is watched");
  }
  assert.match(whenEdit({ state: "running" }), /next write/);
  assert.match(whenEdit({ state: "done" }), /not edited/);
});
