import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";
import * as C from "../src/commands.ts";
import { actsFor, ASK_AGENT, askLine, askNote, asksYou, attemptsOf, CHANGES, commandChip, commandWord, cornerWord, CURSOR_AGENT, draftedSteps, edgeKind, editable, filesChip, fitWidth, fitWords, forkActs, forkWords, HEADER_ACTS, headerFor,
         checkWords, heldWords, linkHint, mainAct, mayRun, newsLine, OUTSIDE, OUTSIDE_OWN, paneKey, pipeline, planningLine, provesNothing, replayLine, scopeTree, startAnswers, stopAfterPlan, stopsOf, sub, tabOrder, tokenWords, topLine,
         whenEdit, who, writtenOf, type StateX, type TaskX } from "../src/graph/words.ts";
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

test("the header says each number once: the stages, the cost in Run's note unless auto's line says it against its budget, and auto's line while it works", () => {
  const fx = (name: string) => parseState(readFileSync(new URL(`./fixtures/${name}.json`, import.meta.url), "utf8")) as StateX;
  const run = (s: StateX) => headerFor(s).stages.find((x) => x.key === "run")!.note;
  const h = headerFor(state);
  assert.equal(h.goal, state.goal);
  assert.equal(h.auto, autoLine(state));
  assert.match(h.auto, /\$0\.61 of \$2\.00/);
  assert.equal(run(state), "1 working", "the auto line says the cost: not again");
  assert.equal(run({ ...state, auto: null }), "1 working · $0.61");
  assert.equal(run({ ...state, auto: null, stand_in: true }), "1 working", "a stand-in's calls cost nothing");
  assert.equal(run({ ...state, auto: null, replay: { shown: "demo", day: "", repository: "" } }), "1 working", "nor does a replay spend");
  const done = { ...state, auto: { ...state.auto!, stage: "done" } };
  assert.deepEqual([headerFor(done).auto, run(done)], ["", "1 working · $0.61"], "auto done: the stages say where the plan is");
  assert.equal(run(fx("proposals")), "", "nothing has run: no cost under Run");
  assert.equal(headerFor(fx("drafting")).goal, "CSV export of the visible rows", "a planner drawing: what it draws");
  assert.equal(headerFor(fx("empty")).goal, "Graphene", "no plan: no placeholder for a goal");
  assert.match(ASK_AGENT, /Claude Code or Codex/, "the agents Graphene's hooks reach, by name");
  assert.equal(CURSOR_AGENT, "Cursor's own Agent does not plan with Graphene yet.");
  assert.deepEqual(headerFor(state).stages.map((x) => x.label), pipeline(state).map((x) => x.label));
});

test("the news a screen reader hears is in the screen's words, and not what a chip or auto's line says already", () => {
  const fx = (name: string) => parseState(readFileSync(new URL(`./fixtures/${name}.json`, import.meta.url), "utf8")) as StateX;
  const plan = fx("proposals"), auto = fx("auto");
  assert.equal(newsLine(plan, false), "the planner suggested 4 tasks under 2 sub-goals", "the CLI's proposed is suggested; its question is its chip's");
  assert.equal(newsLine({ ...plan, news: ["proposed: Input loop, quit and exit"] }, false), "suggested: Input loop, quit and exit");
  assert.equal(newsLine(fx("big"), false), "DELETE /orders/:id cancels needs help: it wrote outside its files");
  assert.equal(newsLine({ ...plan, news: ["proposed: List proposed changes"] }, false), "suggested: List proposed changes", "a title keeps its own words");
  assert.equal(newsLine({ ...plan, news: ["Retry when the API came back came back: it failed"] }, false), "Retry when the API came back needs help: it failed");
  assert.equal(newsLine(auto, true), "round 2 checked the goal: red", "auto's wait is its line's in the header, said once");
  assert.equal(newsLine(auto, false), "auto waits: the budget has $0.63 left and a question is open");
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
  assert.equal(chip("c", 60), "c · Super · 7 lines · 23 s quiet · $0.15 · working"); // working: the numbers are the news
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

test("the header's one act: Start a suggested plan (held by a question with no default), Run what is ready, Stop a run", () => {
  const fx = (name: string) => parseState(readFileSync(new URL(`./fixtures/${name}.json`, import.meta.url), "utf8")) as StateX;
  const say = (s: StateX) => { const a = mainAct(s); return a && `${a.label} ${a.act}${a.main ? " main" : ""}${a.off ? " off" : ""}`; };
  const plan = fx("proposals");
  assert.equal(say(plan), "Start start main", "a suggestion: Run would fail in a terminal, nobody accepted it");
  assert.equal(say({ ...plan, questions: plan.questions.map((q) => ({ ...q, default: null })) }), "Start start off");
  assert.match(mainAct({ ...plan, questions: [{ ...plan.questions[0]!, default: null }] })!.title, /question with no default/);
  assert.deepEqual([mainAct(plan, true)!.off, mainAct(plan, true)!.title], [true, "Exact is on: it waits for your answers"], "Exact: any question holds it, as Home's");
  assert.equal(mainAct({ ...plan, questions: [] }, true)!.main, true, "Exact with nothing asked: nothing to wait for");
  const accepted = { ...plan, tasks: plan.tasks.map((t, i) => (i ? t : { ...t, state: "ready" as const })) }; // one accepted in its pane
  assert.equal(say(accepted), "Start start main", "one task accepted alone: Start still takes the rest, not a Run that leaves them behind");
  assert.equal(say({ ...accepted, questions: [], tasks: accepted.tasks.map((t) => ({ ...t, state: "ready" as const })) }), "Run run main", "nothing suggested: Run");
  const stopped = { ...fx("running"), run: { going: false, pid: null } };
  const readied = { ...stopped, tasks: stopped.tasks.map((t) => (t.state === "running" ? { ...t, state: "ready" as const } : t)) };
  assert.equal(say(readied), "Run run main", "something ready, nothing working: Run");
  assert.equal(say({ ...readied, questions: [{ ...plan.questions[0]!, default: null }] }), "Run run main", "a question with no default leaves Run as it is: graphene run and Home's Run leave it open");
  assert.equal(mainAct({ ...readied, questions: [] })!.title, "start an agent on every task that is ready");
  assert.equal(mainAct({ ...readied, questions: [plan.questions[0]!, { ...plan.questions[0]!, default: null }] })!.title,
               "answer an open question with its default (“8000, as the README says”), then start an agent on every task that is ready",
               "Run takes the defaults there are, as graphene run does: its hover says so");
  assert.equal(say(fx("running")), "Stop stop", "a run going: Stop, never filled");
  assert.equal(say(stopped), "Run run off", "nothing ready: Run is there, held");
  assert.equal(say(fx("empty")), null, "no plan: nothing to start");
  assert.equal(say({ ...plan, tasks: plan.tasks.map((t) => ({ ...t, state: "done" as const })) }), null, "all done: nothing to start");
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
  // to review, as Home's card: two attempts passed and none kept, Compare first; else its changes until opened, then Approve
  assert.deepEqual(acts("farewell"), ["compareForks", "openDiff", "sendBack", "add-after", "add-under", "link"]);
  const docs = (opened: boolean) => actsFor(task("docs"), false, opened).map((b) => `${b.act}${b.main ? " (main)" : ""}`).slice(0, 3);
  assert.deepEqual(docs(false), ["openDiff (main)", "signOff", "sendBack"]);
  assert.deepEqual(docs(true), ["signOff (main)", "openDiff", "sendBack"]);
  assert.equal(acts("hello").includes("sendBack"), true, "a finished task is sent back, as Edit's line says");
  assert.deepEqual(acts("logs"), ["handBack", "openDiff", "add-after", "add-under", "link", "tell"]);
  assert.deepEqual(acts("ship"), ["add-after", "add-under", "link", "drop", "tell"]); // no Edit: the pane is the form
  assert.deepEqual(acts("farewell", true), []);
  assert.deepEqual(acts("ship", true), []);
  assert.equal(actsFor(task("farewell"), false)[0]!.main, true);
});

test("a button's hover names the graphene command its click runs", () => {
  const named = (b: { title: string }, argv: string[]) => assert.ok(b.title.includes(`graphene ${argv.slice(0, 2).join(" ")}`), `"${b.title}" names ${argv.join(" ")}`);
  const r = actsFor(task("farewell"), false);
  named(actsFor(task("docs"), false).find((b) => b.act === "signOff")!, C.signOff("docs"));
  named(r.find((b) => b.act === "sendBack")!, C.reopen("farewell", "x"));
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
  assert.equal(fitWidth("ship orders 1.0: a store", 100, mono), "ship orders 1…"); // no stop left before the ellipsis
});

test("a lane's corner word is the running task's model, cut to about six characters, and nothing else", () => {
  const greet = task("greet"); // running, Nano
  assert.equal(cornerWord(greet), "Nano");
  assert.equal(cornerWord({ ...greet, model: "claude-sonnet-4-5" }), "claude…");
  assert.equal(cornerWord({ ...greet, model: "qwen3-coder-480b" }), "qwen3…"); // no dash left before the ellipsis
  assert.equal(cornerWord(task("farewell")), ""); // in review: its mark says so, and that is marks.ts's (`cornerMark`)
  assert.equal(cornerWord(task("hello")), "");
});

test("a card's tile says who does the step: you, the executor by its letter, or a command by its first letters", () => {
  const greet = task("greet");
  assert.deepEqual(who(greet, "claude"), { kind: "claude", mark: "C", label: "Claude Code" });
  assert.deepEqual(who(greet, "codex --full-auto"), { kind: "codex", mark: "X", label: "Codex" });
  assert.equal(who(greet, "nemotron").mark, "N");
  assert.deepEqual(who(greet, "stand-in"), { kind: "agent", mark: "S", label: "Stand-in" }, "the demo's scripted stand-in");
  assert.equal(who(greet, "nemotron").label, "Nemotron", "a name as a person writes it, not the setting's word");
  assert.deepEqual(who(greet, "claude:opus"), { kind: "claude", mark: "C", label: "Claude Code" }, "the setting names the model too: the family is who");
  assert.equal(who(greet, "nemotron:super").label, "Nemotron");
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

test("while a planner writes, its finished steps are drawn: tasks only, and none the plan already has", () => {
  const writing = parseState(readFileSync(new URL("./fixtures/drafting.json", import.meta.url), "utf8")) as StateX;
  assert.deepEqual(draftedSteps(writing).map((d) => d.id), ["failing", "rows", "button", "empty"], "the sub-goal is a band, not a box");
  assert.equal(planningLine(writing), "The planner (claude) is drawing: 4 tasks so far");
  const one = { ...writing, drafting: { ...writing.drafting!, steps: writing.drafting!.steps.slice(0, 2) } };
  assert.equal(planningLine(one), "The planner (claude) is drawing: 1 task so far");
  // a line that names a task the plan has is an anchor: the task is drawn once, as itself
  const anchored = { ...state, drafting: { by: "claude", live: true, steps: [{ id: "greet", title: "greet route", parent: null, leaf: true, scope: [], check: null, needs: [] },
                                                                              { id: "new", title: "a new step", parent: null, leaf: true, scope: [], check: null, needs: ["greet"] }] } };
  assert.deepEqual(draftedSteps(anchored).map((d) => d.id), ["new"]);
  // a planner whose stream has no text: the boxes come with the plan, and the graph says so
  assert.equal(planningLine({ ...writing, drafting: { by: "codex", live: false, steps: [] } }), "The planner (codex) is writing: its tasks appear when the plan arrives");
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
  assert.deepEqual(pipeline(wf).map((x) => `${x.label} ${x.at}${x.note ? `: ${x.note}` : ""}`), ["Plan done: 4 tasks", "Run now: 1 asks you", "Review next"]);
  // it is its command alone: the pane's form (files, attempts, your approval, whose it is) is closed, and the line says where it changes
  const ready = { ...suite, state: "ready" as const };
  assert.deepEqual([editable(ready, false), editable(pr, false)], [false, false]);
  for (const t of [ready, pr]) assert.equal(whenEdit(t), "A command task is its command alone: no files, no attempts, no agent. Change its run: line in the plan's text.");
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
  assert.deepEqual(at(fx("drafting")), ["Plan now: 4 tasks so far", "Run next", "Review next"]);
  assert.deepEqual(at({ ...fx("drafting"), drafting: { by: "codex", live: false, steps: [] } }), ["Plan now: the planner is writing", "Run next", "Review next"]);
  assert.deepEqual(at(fx("proposals")), ["Plan now: 4 tasks", "Run next", "Review next"]); // suggested: it waits for Start; its question is said once, by its chip
  assert.equal(askLine(fx("proposals").questions.length), "1 question · answer");
  // Start takes the open questions' defaults (plan accept on the whole plan): said in its hover and under the chip
  const plan = fx("proposals");
  assert.match(mainAct(plan)!.title, /^accept the 4 suggested, answer the open question with its default \(“8000, as the README says”\), then start/);
  assert.equal(startAnswers({ questions: [plan.questions[0]!, plan.questions[0]!] }), "answer the 2 open questions with their defaults");
  assert.equal(startAnswers({ questions: [{ ...plan.questions[0]!, default: null }] }), "", "one with no default: nothing to take");
  assert.deepEqual([askNote(1, "Start"), askNote(2, "Run")], ["Start takes its default", "Run takes their defaults"], "no or: it reads without the chip's · answer");
  assert.deepEqual([askLine(2), askLine(0)], ["2 questions · answer", ""]);
  assert.deepEqual(at(state), ["Plan done: 7 tasks", "Run now: 1 working", "Review next: 2 to review"]); // what waits for you is said while the rest runs
  const all = (word: TaskX["state"]) => ({ ...state, questions: [], run: { going: false, pid: null }, tasks: state.tasks.map((t) => ({ ...t, state: word })) });
  assert.deepEqual(at(all("ready")), ["Plan done: 7 tasks", "Run now: 7 ready", "Review next"]);
  assert.deepEqual(at({ ...all("ready"), run: { going: true, pid: 1 } }), ["Plan done: 7 tasks", "Run now: starting", "Review next"]);
  assert.deepEqual(at(all("review")), ["Plan done: 7 tasks", "Run done", "Review now: 7 to review"]);
  assert.deepEqual(at(all("done")), ["Plan done: 7 tasks", "Run done", "Review done: done"]);
  // something suggested while agents work (an agent's proposal, a second ask): the work is still at Run, and the plan says what waits
  const more = { ...state, tasks: [...state.tasks, { ...task("ship"), id: "extra", state: "proposed" as const }] };
  assert.deepEqual(at(more), ["Plan done: 8 tasks · 1 suggested", "Run now: 1 working", "Review next: 2 to review"]);
  const back = { ...all("ready"), tasks: all("ready").tasks.map((t, i) => (i ? t : { ...t, state: "came back" as const })) };
  assert.equal(at(back)[1], "Run now: 1 needs help");
  assert.deepEqual(at({ ...all("done"), run: { going: true, pid: 1 } }), ["Plan done: 7 tasks", "Run done", "Review done: done"], "a run winding down has nothing left to start");
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
    "tests/ [other] another task's", "web/ [other] another task's", "README.md [out]",
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
  // a path the step will create is its own, and says it is new; a finished step's changes are its written files
  assert.deepEqual(scopeTree(step("docs"), scoped).filter((r) => r.kind === "in"), [{ name: "docs/EXPORT.md", depth: 0, kind: "in", note: "new" }]);
  assert.deepEqual(scopeTree(step("test"), scoped).filter((r) => r.kind === "in"), [{ name: "tests/", depth: 0, kind: "in", note: "" },
                                                                                   { name: "test_export.py", depth: 1, kind: "in", note: "written" }]);
  assert.equal(writtenOf(step("docs")), "");
  // a long folder is cut, and says how many more; an older CLI with no tree still shows the step's own files
  const many = { ...step("rows"), files: Array.from({ length: 15 }, (_, i) => `src/export/f${i}.py`), filesN: 15, touched: [] };
  assert.equal(scopeTree(many, scoped).filter((r) => r.kind === "in").at(-1)?.name, "… and 3 more");
  assert.deepEqual(scopeTree(step("rows"), { tree: [], tasks: [step("rows")] }).map((r) => r.name), ["src/export/", "__init__.py", "csv.py", "formats.py", "rows.py"]);
});

test("May run, Held by, Stopped, Done when and Tokens say what is known, and no more", () => {
  // Graphene's own two are not the repository's commands: left out, and the check the agent cannot run is named, with who runs it
  assert.deepEqual(mayRun(scoped, step("rows")), { commands: [], words: "no shell command", outside: OUTSIDE,
    note: "It cannot run pytest: it writes its files, and Graphene runs the check after, in a clean copy." });
  assert.equal(OUTSIDE, "none");
  const npm = { ...scoped, allows: ["graphene node *", "npm test *"] };
  assert.deepEqual(mayRun(npm, { ...step("rows"), check: "npm test table" }), { commands: ["npm test *"], words: "", note: "", outside: OUTSIDE }, "a check it may run: nothing to say");
  assert.equal(mayRun(npm, { ...step("rows"), check: null }).note, "", "no check: nothing it cannot run");
  assert.match(mayRun(npm, { ...step("rows"), check: "cd app && npm test table" }).note, /^$/, "the command a check runs, not the cd before it");
  assert.match(mayRun(scoped, { ...step("rows"), check: "cd app && ./gradlew test" }).note, /^It cannot run \.\/gradlew:/);
  assert.match(mayRun(scoped, { ...step("rows"), check: "PYTHONPATH=. pytest -q" }).note, /^It cannot run pytest:/, "the command, not the setting before it");
  assert.match(mayRun({ allows: null, executor: "claude" }, step("rows")).words, /^any command: what a command writes is still held/);
  // the list is the repository's executor's: a step Codex holds, or one that is yours, is not under it
  assert.deepEqual(mayRun(scoped, step("button")), { commands: [], words: "any command: what a command writes is still held to its files", note: "", outside: OUTSIDE_OWN });
  assert.deepEqual(mayRun(scoped, step("docs")), { commands: [], words: "any command", note: "", outside: OUTSIDE_OWN });
  // the setting names the model (`claude:opus`), a run names the holder by family (`claude`): the same executor, the same list and name
  assert.deepEqual(mayRun({ ...scoped, executor: "claude:opus" }, step("rows")).words, "no shell command");
  assert.match(heldWords({ held: { state: "refused", by: "claude:opus" } }).proof, /^Claude Code's hook/);
  // held: three states, each as the tests prove it; a Graphene that does not say is not held, never a shield
  assert.deepEqual([heldWords(step("rows")).shield, heldWords(step("rows")).line], [true, "A write outside its files is refused before it happens."]);
  assert.equal(heldWords(step("rows")).proof, "Claude Code's hook stops it, and its finish checks again.");
  // in plain words: the test that proves it is the README's to name, not the inspector's
  for (const state of ["refused", "caught", "none", ""] as const) assert.doesNotMatch(heldWords({ held: { state, by: "nemotron" } }).proof, /tests\/|\.py\b/);
  assert.match(heldWords({ held: { state: "refused", by: "nemotron" } }).proof, /^Nemotron's hook/);
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

test("an icon the graph's page asks for by name is one it has: the pane's close, the run's play, a button's check", () => {
  const src = (file: string) => readFileSync(new URL(`../src/graph/${file}`, import.meta.url), "utf8");
  // `icon("close")`, `icon(going ? "debug-stop" : "play")` on the page; `icon: "check"` on a button's words
  const asked = [...src("main.ts").matchAll(/\bicon\(([^()]*)\)/g)].flatMap((m) => [...m[1]!.matchAll(/(?:^|[?:]\s*)"([a-z-]+)"/g)].map((n) => n[1]!));
  asked.push(...[...src("words.ts").matchAll(/\bicon: "([a-z-]+)"/g)].map((m) => m[1]!));
  assert.ok(asked.includes("close") && asked.includes("play") && asked.includes("check"), "the page's source is read as it is written");
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

test("how many attempts a task runs as: its own number, else the limits', else one; one that has not started says waiting", () => {
  assert.equal(forkWords({ ...task("farewell").forks[0]!, letter: "a", state: "", model: "", lines: null, usd: null }, null), "a · waiting");
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
