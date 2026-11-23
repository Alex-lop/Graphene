import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";
import * as C from "../src/commands.ts";
import { banner, checkHome, countsLine, home, PROVES_NOTHING, type Card, type Home } from "../src/home/cards.ts";
import { headline, parseState, type State } from "../src/state.ts";

const fixture = (name: string): State => parseState(readFileSync(new URL(`./fixtures/${name}.json`, import.meta.url), "utf8"));
const section = (h: Home, key: string) => h.sections.find((s) => s.key === key);
const card = (h: Home, key: string): Card => h.sections.flatMap((s) => s.cards).find((c) => c.key === key)!;
const labels = (c: Card) => c.buttons.map((b) => b.label);

test("a suggested plan is read before it starts: each task says what for, what it may change, what proves it", () => {
  const h = home(fixture("proposals"));
  assert.deepEqual(h.sections.map((s) => s.key), ["needs", "suggested"]); // the question first: it changes the plan
  const s = section(h, "suggested")!;
  assert.equal(s.title, "Suggested plan · 4 tasks");
  assert.deepEqual(s.buttons.map((b) => [b.label, b.act, Boolean(b.main)]), [["Start", "startAll", true], ["Discard all", "discardAll", false]]);
  const hello = card(h, "p:hello");
  assert.equal(hello.tag, "suggested");
  assert.deepEqual(hello.lines, [
    { k: "What for", v: "hello says hello to the person by name" },
    { k: "May change", v: "words.py", mono: true, paths: ["words.py"] },
    { k: "Done when", v: "pytest -q tests/test_words.py passes", mono: true },
  ]);
  assert.deepEqual(card(h, "p:farewell").lines.find((l) => l.k === "After"), { k: "After", v: "bye says goodbye, greet route" });
  assert.deepEqual(labels(hello), ["Remove"]);
});

test("a question offers its default first, each option, and the person's own words; none looks chosen", () => {
  const q = card(home(fixture("proposals")), "q:which-port");
  assert.equal(q.title, "which port does the dev server take?");
  assert.deepEqual(q.lines, [{ k: "About", v: "greet route" }]); // the default's button says it is the default
  assert.deepEqual(q.buttons.map((b) => [b.label, b.arg, b.note, Boolean(b.main)]),
                   [["8000, as the README says", "8000, as the README says", "default", false],
                    ["pick a free one at start", "pick a free one at start", undefined, false], ["In your own words…", undefined, undefined, false]]);
});

test("a task's What for is left out when it only says the title again", () => {
  const s = fixture("proposals");
  const again = { ...s, tasks: s.tasks.map((t) => (t.id === "hello" ? { ...t, title: "export command writing json", full: "An export command writing JSON" } : t)) };
  assert.equal(card(home(again), "p:hello").lines.find((l) => l.k === "What for"), undefined);
});

test("a finished task to review shows its evidence; Open changes leads until the person has opened them", () => {
  const s = fixture("graph-race");
  const before = card(home(s), "review:docs");
  assert.equal(before.tag, "to review");
  assert.equal(before.lines.at(-1)?.v, "You have not opened these changes yet.");
  assert.equal(before.lines.at(-1)?.warn, true);
  assert.deepEqual(before.buttons.map((b) => [b.label, Boolean(b.main)]), [["Open changes", true], ["Approve", false], ["Send back…", false]]);
  const after = card(home(s, new Set(["docs"])), "review:docs");
  assert.equal(after.lines.at(-1)?.v, "You opened these changes.");
  assert.deepEqual(after.buttons.map((b) => [b.label, Boolean(b.main)]), [["Open changes", false], ["Approve", true], ["Send back…", false]]);
});

test("two attempts that both passed: the person compares them and keeps one before anything is approved", () => {
  const s = fixture("graph-race");
  const farewell = card(home(s), "review:farewell");
  assert.deepEqual(farewell.lines, [{ k: "Attempts", v: "a: passed, 9 lines · b: passed, 15 lines" }, // words and counts: no mono
                                    { v: "2 attempts passed the check. Compare them and keep one, then approve it.", warn: true }]);
  assert.deepEqual(farewell.buttons.map((b) => [b.label, b.act, b.arg, Boolean(b.main)]),
                   [["Compare attempts", "compare", undefined, true], ["Keep a", "keep", "a", false], ["Keep b", "keep", "b", false],
                    ["Send back…", "sendBack", undefined, false]]);
  const kept = { ...s, tasks: s.tasks.map((t) => (t.id === "farewell" ? { ...t, kept: { letter: "a", why: "fewer lines", by: "you" } } : t)) };
  assert.deepEqual(card(home(kept), "review:farewell").lines.find((l) => l.k === "Kept"), { k: "Kept", v: "attempt a of 2: fewer lines" });
  assert.ok(checkHome({ type: "act", act: "keep", id: "farewell", arg: "b" }, s));
  assert.equal(checkHome({ type: "act", act: "keep", id: "farewell", arg: "z" }, s), null);
  assert.equal(checkHome({ type: "act", act: "keep", id: "farewell" }, s), null);
});

test("a check that passed before the work is said on the card: it proves nothing about the change", () => {
  const s = fixture("graph-race");
  const docs = s.tasks.find((t) => t.id === "docs")!;
  const h = home({ ...s, tasks: s.tasks.map((t) => (t === docs ? { ...t, hollow: true } : t)) });
  assert.ok(card(h, "review:docs").lines.some((l) => l.warn && /passed before the work too/.test(l.v)));
});

test("a task that needs help says why, and offers its moves in plain words, trying again first", () => {
  const s = fixture("graph-race");
  const logs = s.tasks.find((t) => t.id === "logs")!;
  const offers = { w: ["node", "widen", "logs", "app.py"], b: ["node", "sibling", "logs", "app.py"], n: ["node", "set", "logs", "--needs", "greet"] };
  const h = home({ ...s, tasks: s.tasks.map((t) => (t === logs ? { ...t, offers } : t)) });
  const c = card(h, "help:logs");
  assert.equal(c.tag, "needs help");
  assert.deepEqual(c.lines[0], { k: "Why", v: "app.py is outside its scope", warn: true });
  assert.deepEqual(labels(c), ["Try again", "Allow it to change app.py", "Add a task for app.py", "Wait for greet route first", "Open changes", "Remove task"]);
  assert.deepEqual(c.buttons.slice(1, 4).map((b) => b.arg), ["w", "b", "n"]);
});

test("who is working, what is up next, and what is done, each in its own section; done starts folded", () => {
  const h = home(fixture("running"));
  assert.deepEqual(h.sections.map((s) => s.key), ["needs", "working", "next", "done"]);
  const greet = card(h, "w:greet");
  assert.deepEqual(greet.lines.find((l) => l.k === "Agent"), { k: "Agent", v: "3 · Nano" });
  assert.ok(greet.lines.some((l) => l.k === "Attempts"));
  assert.deepEqual(labels(greet), ["Open changes so far", "Message agent…", "Compare attempts"]);
  assert.deepEqual(section(h, "working")!.buttons.map((b) => b.act), ["stop"]);
  assert.equal(card(h, "n:ship").tag, "waiting");
  assert.equal(section(h, "done")!.folded, true);
  assert.deepEqual(labels(card(h, "d:hello")), ["Open changes", "Send back…"]);
  // Run is always there: while a run goes, `graphene run` hands the ready tasks to it (a run fixes its set at start)
  assert.deepEqual(section(h, "next")!.buttons.map((b) => [b.act, b.title]), [["run", "hand these to the run that is going"]]);
  const idle = section(home({ ...fixture("running"), run: { going: false, pid: null } }), "next")!;
  assert.deepEqual(idle.buttons.map((b) => [b.act, b.title]), [["run", "start an agent on every task that is ready"]]);
  assert.deepEqual([section(h, "next")!.buttons[0]!.main, idle.buttons[0]!.main], [false, true], "filled only when it is the next act");
});

test("the header: the goal, else what was last asked; the counts in plain words; a practice run says so", () => {
  const s = fixture("running");
  assert.equal(headline(s), "make the app friendlier");
  assert.equal(headline({ ...s, goal: "", news: ["you asked: a --json flag", "proposed: x"] }), "a --json flag");
  assert.equal(headline({ ...s, goal: "", news: [] }), "");
  assert.equal(countsLine(s), "2 of 7 done · $0.42 spent"); // who is working and what needs you: the stages and Needs you say it
  assert.equal(banner(s), "");
  assert.equal(banner({ ...s, stand_in: true }), "Practice run: a scripted stand-in answers for the AI, so nothing is spent");
  assert.equal(countsLine({ ...s, stand_in: true }), "2 of 7 done", "a practice run spends nothing, and says no cost");
  assert.equal(card(home({ ...s, stand_in: true }), "w:greet").lines.find((l) => l.k === "Cost"), undefined);
  assert.equal(banner({ ...s, replay: { shown: "a scripted stand-in, no model ran", day: "", repository: "" } }), "Demo replay: a scripted stand-in, no model ran");
  assert.equal(home(fixture("empty")).empty, true);
});

test("the page's messages are checked against the plan before anything runs", () => {
  const s = fixture("graph-race");
  const logs = s.tasks.find((t) => t.id === "logs")!;
  const plan = { ...s, tasks: s.tasks.map((t) => (t === logs ? { ...t, offers: { w: ["node", "widen", "logs", "app.py"] } } : t)) };
  const ok = (m: unknown) => assert.ok(checkHome(m, plan), JSON.stringify(m));
  const no = (m: unknown) => assert.equal(checkHome(m, plan), null, JSON.stringify(m));
  ok({ type: "ready" });
  no({ type: "act", act: "ask", arg: "a --json flag" }); // a plan comes from the person's coding agent: Home takes no ask
  no({ type: "act", act: "cancel" });
  ok({ type: "act", act: "setup", arg: "codex", flag: true });
  no({ type: "act", act: "setup", arg: "nemotron", flag: true }); // Home's picker offers Claude Code and Codex; the CLI still takes --executor nemotron
  no({ type: "act", act: "setup", arg: "rm -rf /" });
  ok({ type: "act", act: "setKey", arg: "nim" });
  no({ type: "act", act: "setKey", arg: "nim; rm" });
  ok({ type: "act", act: "approve", id: "docs" });
  no({ type: "act", act: "approve", id: "nope" });
  no({ type: "act", act: "approve" });
  ok({ type: "act", act: "offer", id: "logs", arg: "w" });
  no({ type: "act", act: "offer", id: "logs", arg: "b" }); // not an offer the task carries
  no({ type: "act", act: "offer", id: "logs", arg: "constructor" }); // an object's own keys only
  ok({ type: "act", act: "answer", id: "which-port", arg: "pick a free one at start" });
  ok({ type: "act", act: "answer", id: "which-port" });
  no({ type: "act", act: "answer", id: "which-port", arg: "port 22" });
  ok({ type: "act", act: "showGraph", id: "" });
  ok({ type: "act", act: "showGraph", id: "greet" });
  no({ type: "act", act: "showGraph", id: "nope" });
  no({ type: "act", act: "rm" });
  no({ type: "nonsense" });
  no(null);
  assert.equal(checkHome({ type: "act", act: "setup", arg: "claude" }, null)?.type, "act"); // set up: no plan yet
});

test("Home's commands: a send-back with its note, a set-up that asks nothing", () => {
  assert.deepEqual(C.reopen("top", "-- the test only checks one word"), ["node", "reopen", "top", "--note=-- the test only checks one word"]);
  assert.throws(() => C.reopen("-x", "why"));
  assert.deepEqual(C.initWith("codex"), ["init", "--planner", "codex", "--executor", "codex"]);
  // Discard all is one drop: one at a time, a task another of them waits on is refused
  assert.deepEqual(C.dropAll(["hello", "bye", "words"]), ["node", "drop", "hello", "bye", "words"]);
  assert.throws(() => C.dropAll(["hello", "--all"]));
});

test("the palette shows seven commands; the rest, and the advanced views, only with graphene.advanced", () => {
  const pkg = JSON.parse(readFileSync(new URL("../package.json", import.meta.url), "utf8"));
  const c = pkg.contributes;
  const hidden = new Set(c.menus.commandPalette.filter((m: { when: string }) => m.when === "config.graphene.advanced").map((m: { command: string }) => m.command));
  const shown = c.commands.map((x: { command: string }) => x.command).filter((x: string) => !hidden.has(x));
  assert.deepEqual(shown.sort(), ["graphene.home", "graphene.init", "graphene.install", "graphene.setKey", "graphene.showGraph",
                                  "graphene.stop", "graphene.watchDemo"]);
  for (const x of c.commands) assert.match(x.title, /^Graphene: /);
  const views = c.views.graphene;
  assert.equal(views[0].id, "graphene.home", "the side bar is Home: the graph is a tab of the editor, opened with it");
  for (const v of views.slice(1)) assert.equal(v.when, "config.graphene.advanced", v.id);
  assert.equal(c.configuration.properties["graphene.advanced"].default, false);
});

test("Home shows the pipeline's three stages and the one switch, on until `auto` is on", () => {
  const s = fixture("proposals");
  const h = home(s);
  assert.deepEqual(h.stages.map((x) => [x.label, x.at]), [["Plan", "now"], ["Run", "next"], ["Review", "next"]]);
  assert.equal(h.stopAfter, true, "the default: a plan waits for Start");
  assert.equal(home({ ...s, envelope: { ...s.envelope, auto: "on" } }).stopAfter, false, "off is auto");
  assert.deepEqual(home(fixture("graph-race")).stages.map((x) => x.at), ["done", "now", "next"]);
  assert.deepEqual(checkHome({ type: "act", act: "stopAfter", flag: false }, s), { type: "act", act: "stopAfter", id: "", flag: false });
  assert.equal(checkHome({ type: "act", act: "stopAfter" }, s), null, "the switch says which way");
  assert.deepEqual(C.stopAfter(true), ["config", "set", "auto", "off"]);
  assert.deepEqual(C.stopAfter(false), ["config", "set", "auto", "on"]);
});

test("before the run, a check that already passes is marked on its card: it proves nothing yet", () => {
  const s = fixture("graph-race");
  const mark = (id: string, key: string) => {
    const h = home({ ...s, tasks: s.tasks.map((t) => (t.id === id ? { ...t, hollow: true } : t)) });
    return card(h, key).lines.filter((l) => l.warn).map((l) => l.v);
  };
  assert.deepEqual(mark("ship", "n:ship"), [PROVES_NOTHING], "a task up next");
  assert.ok(mark("greet", "w:greet").includes(PROVES_NOTHING), "a task an agent is on");
  assert.deepEqual(card(home(s), "n:ship").lines.filter((l) => l.warn), [], "a check that fails now says nothing");
});

test("Home lists the repository's workflows, each with a Run; a file that is not a workflow says why and offers none", () => {
  const s = fixture("empty");
  const listed = [{ name: "fix-issue", goal: "fix issue {{issue}}", inputs: [{ name: "issue", default: null }, { name: "suite", default: "uv run pytest -q" }], error: null },
                  { name: "broken", goal: "", inputs: [], error: "line 3: {{branch}} is no input of this workflow" }];
  const sec = section(home(s, new Set(), false, listed), "workflows")!;
  assert.equal(sec.title, "Workflows · 2");
  assert.equal(sec.folded, false, "nothing planned: the workflows are a way to start");
  const fix = sec.cards[0]!;
  assert.deepEqual(fix.lines, [{ k: "Does", v: "fix issue {{issue}}" }, { k: "Asks for", v: "issue, suite (uv run pytest -q)" }]);
  assert.deepEqual(fix.buttons.map((b) => [b.label, b.act, b.arg]), [["Run", "runWorkflow", "fix-issue"]]);
  assert.deepEqual([sec.cards[1]!.lines, sec.cards[1]!.buttons], [[{ v: "line 3: {{branch}} is no input of this workflow", warn: true }], []]);
  assert.equal(section(home(s), "workflows"), undefined, "none in the repository: no section");
  assert.equal(section(home(fixture("graph-race"), new Set(), false, listed), "workflows")!.folded, true, "a plan is on: they wait folded");
  // Run is taken only for a workflow the repository has, and that reads
  assert.deepEqual(checkHome({ type: "act", act: "runWorkflow", arg: "fix-issue" }, s, listed), { type: "act", act: "runWorkflow", id: "", arg: "fix-issue" });
  assert.equal(checkHome({ type: "act", act: "runWorkflow", arg: "broken" }, s, listed), null);
  assert.equal(checkHome({ type: "act", act: "runWorkflow", arg: "fix-issue; rm -rf /" }, s, listed), null);
  assert.equal(checkHome({ type: "act", act: "runWorkflow", arg: "fix-issue" }, s), null, "none listed: none to run");
});

test("a step past the line asks you on Home: what leaves your machine, the command it runs, and Approve and run", () => {
  const s = fixture("workflow");
  const h = home(s);
  const c = card(h, "yours:pr-48");
  assert.equal(c.tag, "asks you");
  assert.match(c.lines[0]!.v, /^This task leaves your machine, so it asks you first\./);
  assert.deepEqual(c.lines[1], { k: "Runs", v: "git push -u origin HEAD && gh pr create --draft --fill", mono: true });
  assert.deepEqual(c.buttons.map((b) => [b.label, b.act, b.id]), [["Approve and run", "markDone", "pr-48"]]);
  // before Start, the suggested plan is where each step is read: a command step says what runs, with no agent,
  // and the one past the line says it will ask first. Neither says "no files named" or "... passes".
  const before = home({ ...s, tasks: s.tasks.map((t) => ({ ...t, state: "proposed" as const })) });
  const lines = (id: string) => before.sections.flatMap((x) => x.cards).find((x) => x.key.endsWith(`:${id}`))!.lines;
  assert.deepEqual(lines("suite-48").slice(0, 2), [{ k: "Runs", v: "uv run pytest -q", mono: true }, { v: "A command, with no agent: its exit code is its check." }]);
  assert.deepEqual(lines("pr-48")[1], { v: "It leaves your machine, so it asks you before it runs." });
  // a command that failed stays open and reads as before it ran: its card says it ran, once the terminal is gone
  const failed = (id: string, state: "ready" | "yours") => home({ ...s, tasks: s.tasks.map((t) => (t.id === id ? { ...t, state, checked: { before: null, after: "failed" } } : t)) });
  const warns = (x: Home, key: string) => card(x, key).lines.filter((l) => l.warn).map((l) => l.v);
  assert.deepEqual(warns(failed("suite-48", "ready"), "n:suite-48"), ["Its command failed the last time it ran: the terminal said why. Run tries it again."]);
  assert.deepEqual(warns(failed("pr-48", "yours"), "yours:pr-48"), ["Its command failed the last time it ran: the terminal said why. Approve and run tries it again."]);
  assert.deepEqual(warns(h, "yours:pr-48"), [], "nothing failed: no such line");
});

test("a question with no default stops the run either way: with the switch on, Start waits for its answer", () => {
  const s = fixture("proposals");
  const asks = { ...s, questions: [{ ...s.questions[0]!, default: null }] };
  const suggested = (h: ReturnType<typeof home>) => h.sections.find((x) => x.key === "suggested")!;
  const start = (h: ReturnType<typeof home>) => suggested(h).buttons.find((b) => b.act === "startAll")!;
  assert.equal(start(home(asks)).off, true);
  assert.match(suggested(home(asks)).note, /^Answer the 1 question with no default under Needs you first/);
  assert.equal(start(home(s)).off, false, "a question with a default takes it at Start");
  assert.equal(start(home({ ...s, questions: [] })).off, false);
});

test("Exact: Start waits while anything the plan asks is open, and says how many; off, or with nothing open, it starts", () => {
  const s = fixture("proposals");
  const suggested = (h: ReturnType<typeof home>) => h.sections.find((x) => x.key === "suggested")!;
  const start = (h: ReturnType<typeof home>) => suggested(h).buttons.find((b) => b.act === "startAll")!;
  assert.equal(s.questions.length, 1);
  assert.equal(start(home(s)).off, false, "off by default: what is left open takes its default at Start");
  const exact = home(s, new Set(), true);
  assert.equal(start(exact).off, true);
  assert.match(suggested(exact).note, /^Start waits for every answer: answer the 1 open question under Needs you first/);
  assert.equal(start(home({ ...s, questions: [] }, new Set(), true)).off, false, "nothing open: nothing to wait for");
  assert.deepEqual(checkHome({ type: "act", act: "exact", flag: true }, s), { type: "act", act: "exact", id: "", flag: true });
  assert.equal(checkHome({ type: "act", act: "exact" }, s), null, "the switch says which way");
  // approval, as Set Up asks it, is its own tick in Settings: Exact no longer hides it
  assert.deepEqual(checkHome({ type: "act", act: "review", flag: false }, s), { type: "act", act: "review", id: "", flag: false });
  assert.equal(checkHome({ type: "act", act: "review", arg: "every" }, s), null, "the tick says which way, and nothing else");
});
