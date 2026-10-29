import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";
import { banner, countsLine, home, type Card, type Home } from "../src/home/cards.ts";
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
    { k: "May change", v: "words.py", mono: true },
    { k: "Done when", v: "pytest -q tests/test_words.py passes", mono: true },
  ]);
  assert.deepEqual(card(h, "p:farewell").lines.find((l) => l.k === "After"), { k: "After", v: "bye says goodbye, greet route" });
  assert.deepEqual(labels(hello), ["Remove"]);
});

test("a question offers its default first, each option, and the person's own words", () => {
  const q = card(home(fixture("proposals")), "q:which-port");
  assert.equal(q.title, "which port does the dev server take?");
  assert.deepEqual(q.lines, [{ k: "About", v: "greet route" }, { k: "If unanswered", v: "8000, as the README says" }]);
  assert.deepEqual(q.buttons.map((b) => [b.label, b.arg, Boolean(b.main)]),
                   [["8000, as the README says", "8000, as the README says", true], ["pick a free one at start", "pick a free one at start", false],
                    ["In your own words…", undefined, false]]);
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
  assert.deepEqual(farewell.lines, [{ k: "Attempts", v: "a: passed, 9 lines · b: passed, 15 lines", mono: true },
                                    { v: "2 attempts passed the check. Compare them and keep one, then approve it.", warn: true }]);
  assert.deepEqual(farewell.buttons.map((b) => [b.label, b.act, b.arg, Boolean(b.main)]),
                   [["Compare attempts", "compare", undefined, true], ["Keep a", "keep", "a", false], ["Keep b", "keep", "b", false],
                    ["Send back…", "sendBack", undefined, false]]);
  const kept = { ...s, tasks: s.tasks.map((t) => (t.id === "farewell" ? { ...t, kept: { letter: "a", why: "fewer lines", by: "you" } } : t)) };
  assert.deepEqual(card(home(kept), "review:farewell").lines.find((l) => l.k === "Kept"), { k: "Kept", v: "attempt a of 2: fewer lines" });
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
});

test("the header: the goal, else what was last asked; the counts in plain words; a practice run says so", () => {
  const s = fixture("running");
  assert.equal(headline(s), "make the app friendlier");
  assert.equal(headline({ ...s, goal: "", news: ["you asked: a --json flag", "proposed: x"] }), "a --json flag");
  assert.equal(headline({ ...s, goal: "", news: [] }), "");
  assert.equal(countsLine(s), "2 working · 2 need you · 2 of 7 done · $0.42 spent");
  assert.equal(banner(s), "");
  assert.equal(banner({ ...s, stand_in: true }), "Practice run: a scripted stand-in answers for the AI, so nothing is spent");
  assert.equal(banner({ ...s, replay: { shown: "a scripted stand-in, no model ran", day: "", repository: "" } }), "Demo replay: a scripted stand-in, no model ran");
  assert.equal(home(fixture("empty")).empty, true);
});
