import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";
import { actsFor, CHANGES, cornerWord, counts, fitWidth, fitWords, forkActs, forkWords, HEADER_ACTS, headerFor, linkHint, paneKey, replayLine, sub, tabOrder, zoomK,
         topLine, type StateX, type TaskX } from "../src/graph/words.ts";
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

test("a task that came back says why on its box; a running one its agent, forks and seconds quiet", () => {
  assert.equal(sub(task("logs"), 60), "came back · app.py is outside its scope · 2 tries · $0.02");
  assert.equal(sub(task("logs")), "came back · app.py is ou…"); // the reason is cut to the box, never dropped
  assert.equal(sub(task("greet"), 60), "agent 3 · 3 forks · $0.31");
  const quiet = { ...task("greet"), forks: [], idle: 40 };
  assert.equal(sub(quiet, 60), "agent 3 · running · $0.31 · 40 s quiet");
  // an older CLI's snapshot, as parseState fills it: no reason and no tries, so the old words
  const old = { ...task("logs"), why: "", attempts: 0 };
  assert.equal(sub(old, 60), "came back · 1 outside · $0.02");
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
  assert.equal(topLine({ replay: null, stand_in: true }), "against the scripted stand-in");
  assert.equal(topLine({ replay: null, stand_in: false }), "");
  // an older CLI sends no stand_in: parseState fills false, the line above
  assert.equal(topLine({ replay: { shown: "a scripted stand-in, no model ran", day: "", repository: "" }, stand_in: true }),
               "replay · a scripted stand-in, no model ran");
});

test("a replay offers none of the header's acts: the cockpit would open graphene watch in the person's folder", () => {
  for (const [id, act] of HEADER_ACTS) assert.ok(CHANGES.includes(act), `${id} (${act}) stays in a replay`);
});

test("the link hint names the task, says Cancel as well as Esc, and drop while a dot is dragged", () => {
  assert.equal(linkHint("hello", false), "link: click the task that waits on “hello” · Cancel or Esc stops it");
  assert.equal(linkHint("hello", true), "link: drop it on the task that waits on “hello” · Cancel or Esc stops it");
});

test("a task offers the acts its state takes; a replay offers only what reads", () => {
  const acts = (id: string, replay = false) => actsFor(task(id), replay).map((b) => b.act);
  assert.deepEqual(acts("farewell"), ["signOff", "openDiff", "compareForks", "add-after", "add-under", "link", "edit", "tell"].filter((a) => a !== "tell"));
  assert.deepEqual(acts("logs"), ["handBack", "openDiff", "add-after", "add-under", "link", "edit", "tell"]);
  assert.deepEqual(acts("ship"), ["add-after", "add-under", "link", "edit", "drop", "tell"]);
  assert.deepEqual(acts("farewell", true), ["openDiff", "compareForks"]);
  assert.deepEqual(acts("ship", true), []);
  assert.equal(actsFor(task("farewell"), false)[0]!.main, true);
});

test("a fork in review offers Keep beside its changes; elsewhere only its changes", () => {
  const f = task("farewell");
  assert.deepEqual(forkActs(f, f.forks[0]!, false).map((b) => [b.act, b.fork]), [["openDiff", "a"], ["pickFork", "a"]]);
  assert.deepEqual(forkActs(f, f.forks[0]!, true).map((b) => b.act), ["openDiff"]);
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

test("the zoom never goes under 1, where the smallest text is 11 px, nor over 3; a remembered zoom is clamped too", () => {
  assert.equal(zoomK(0.5), 1);
  assert.equal(zoomK(1), 1);
  assert.equal(zoomK(1.5), 1.5);
  assert.equal(zoomK(5), 3);
  assert.equal(zoomK(Number.NaN), 1); // a saved state from an older page
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
