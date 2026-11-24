// What the graph's page says of a page of sessions (src/graph/words.ts, marks.ts): the one renderer, a second source.
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";
import { cardAct, cardLine, filesLine, receiptFoot, receiptMark, stateMark } from "../src/graph/marks.ts";
import { actsFor, headerFor, receiptLine, sessionsLine, sub, testsWords } from "../src/graph/words.ts";
import { parseState } from "../src/state.ts";

const fixture = (name: string) => parseState(readFileSync(new URL(`./fixtures/${name}.json`, import.meta.url), "utf8"));

test("a page of one session: its title, who and what it is doing, and no stages to be at", () => {
  const s = fixture("session"), h = headerFor(s);
  assert.equal(h.goal, "Review the parser and the printer, each on its own, then run the…");
  assert.equal(h.auto, "Claude Code · working · main · 1 file changed · ran no tests"); // and its receipt as a whole
  assert.deepEqual(h.stages, []); // a session is not a plan to start
});

test("a page of two sessions says how many, and what they are doing between them", () => {
  const s = fixture("sessions");
  assert.equal(headerFor(s).goal, "2 sessions");
  assert.equal(headerFor(s).auto, "2 working");
  const [a, b] = s.sessions!;
  assert.equal(sessionsLine([{ ...a!, status: "needs you" }, { ...b!, status: "idle" }]), "1 need you · 1 idle");
  assert.equal(sessionsLine([{ ...a!, error: "cannot read /x/s.jsonl: EACCES" }, b!]), "cannot read /x/s.jsonl: EACCES"); // a file it cannot read: one line
});

test("a session's card says its state in a session's words, then what it is doing; its files are what it wrote", () => {
  const s = fixture("sessions"), by = (title: string) => s.tasks.find((t) => t.title.startsWith(title))!;
  assert.equal(cardLine(by("Fix the word counter"), 60), "done · Fixed, and both tests pass.");
  assert.equal(cardLine(by("/review"), 60), "interrupted · $ git diff --stat");
  assert.equal(cardLine(by("Now make it count"), 60), "working · 29 s quiet · $ python3 -m unittest");
  assert.equal(cardLine(by("Say it in the README"), 60), "not started");
  assert.equal(sub(by("Now make it count"), 60), "working · 29 s quiet · $ python3 -m unittest"); // and as a lane, in a narrow tab
  assert.deepEqual(filesLine(by("Fix the word counter")), { tone: "plain", mark: "edit", text: "wordcount.py +1", refused: "" });
  assert.deepEqual(filesLine(by("/review")), { tone: "plain", mark: "", text: "", refused: "" }); // it wrote nothing: no chip
  assert.equal(stateMark(by("Now make it count")), "working");
  // watched: no card of a session asks anything of a plan
  assert.ok(s.tasks.every((t) => cardAct(t, true) === null && actsFor(t, true).length === 0));
});

test("a card's foot is its receipt: a tick only for a pass that was seen, and the three states said as they are", () => {
  const s = fixture("sessions"), by = (title: string) => s.tasks.find((t) => t.title.startsWith(title))!.card!.receipt!;
  const passed = by("Fix the word counter");
  assert.deepEqual([receiptMark(passed).box, receiptMark(passed).tone, receiptFoot(passed, 60)], ["passed", "ok", "unittest passed"]);
  assert.equal(receiptMark(passed).words, "unittest passed: its output says OK"); // the hover says what decided it
  assert.equal(receiptLine(passed), "2 files changed · unittest passed");
  const none = by("/review"); // it ran git diff, and no test
  assert.deepEqual([receiptMark(none).box, receiptMark(none).tone, receiptFoot(none, 60)], ["unrun", "dim", "ran no tests"]);
  const out = by("Now make it count"); // its test run is still out: no result yet, no tick
  assert.deepEqual([receiptMark(out).box, testsWords(out)], ["unrun", "ran no tests"]);
  const failed = { ...passed, tests: "failed" as const, checks: [{ ...passed.checks[0]!, verdict: "failed" as const, why: "its output says FAILED (" }], flags: [{ kind: "push" as const, line: "git push", note: "", guess: false }] };
  assert.deepEqual([receiptMark(failed).box, receiptMark(failed).tone, receiptFoot(failed, 60)], ["failed", "red", "unittest failed · 1 to look at"]);
  const unseen = { ...passed, tests: "unseen" as const, checks: [{ ...passed.checks[0]!, verdict: "unseen" as const }] };
  assert.deepEqual([receiptMark(unseen).box, receiptMark(unseen).tone, receiptFoot(unseen, 60)], ["hollow", "warn", "unittest ran, result not seen"]);
  assert.deepEqual([receiptMark(null).box, receiptFoot(null, 60)], ["unrun", ""]); // a plan's step: no receipt, no foot
});

test("a plan's snapshot says nothing of sessions, and reads as it did", () => {
  const s = fixture("running");
  assert.equal(s.sessions, undefined);
  assert.ok(s.tasks.every((t) => t.card === undefined));
  assert.ok(headerFor(s).stages.length > 0);
});
