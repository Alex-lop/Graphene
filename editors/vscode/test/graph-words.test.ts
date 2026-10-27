import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";
import { actsFor, fitWords, forkActs, forkWords, replayLine, sub, type TaskX } from "../src/graph/words.ts";
import { parseState } from "../src/state.ts";

const race = JSON.parse(readFileSync(new URL("./fixtures/graph-race.json", import.meta.url), "utf8"));
const parsed = parseState(JSON.stringify(race));
// the fields the parser does not know yet, as the preview page carries them over
const tasks: TaskX[] = parsed.tasks.map((t) => {
  const r = race.tasks.find((x: { id: string }) => x.id === t.id);
  return { ...t, why: r.why, attempts: r.attempts,
           forks: t.forks.map((f) => ({ ...f, ...r.forks.find((x: { letter: string }) => x.letter === f.letter) })) };
});
const task = (id: string) => tasks.find((t) => t.id === id)!;

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
  // without the new fields, the old words
  const old = { ...task("logs"), why: undefined, attempts: undefined };
  assert.equal(sub(old, 60), "came back · 1 outside · $0.02");
});

test("the kept fork's chip says so in the cockpit's words, the others their state, lines, tries, dollars, quiet", () => {
  const g = task("greet");
  const chip = (letter: string, max = 29) => forkWords(g.forks.find((f) => f.letter === letter)!, g.kept, max);
  assert.equal(chip("b", 60), "b ✓ kept: 4 lines against 12 · 4 lines · $0.07");
  assert.equal(chip("b"), "b ✓ kept: 4 lines against 12");
  assert.equal(chip("a", 60), "a · Nano · gave up · 12 lines · 2 tries · $0.09");
  assert.equal(chip("c", 60), "c · Super · running · 7 lines · $0.15 · 23 s quiet");
  assert.equal(chip("c"), "c · Super · running · 7 lines");
});

test("the replay line is the terminal replay's top line, and nothing when the store is the person's", () => {
  assert.equal(replayLine({ shown: "a scripted stand-in, no model ran", day: "2026-10-26", repository: "wordkit" }),
               "replay · a scripted stand-in, no model ran · 2026-10-26");
  assert.equal(replayLine(null), "");
  assert.equal(replayLine(undefined), "");
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
