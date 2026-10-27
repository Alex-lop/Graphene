import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";
import { parseLog, roundLine, rounds } from "../src/rounds.ts";

// `graphene plan log --json` at the end of the --auto replay, its auto, accepted, picked and landed rows
const log = readFileSync(new URL("./fixtures/real-auto-log.jsonl", import.meta.url), "utf8");

test("the --auto replay's log reads as two rounds: three tasks raced and landed, then the fix", () => {
  const [one, two, ...rest] = rounds(parseLog(log));
  assert.equal(rest.length, 0);
  assert.deepEqual([one!.n, one!.accepted, one!.landed.length, one!.check], [1, ["top", "reading", "hyphens"], 3, "fail"]);
  assert.ok(one!.kept.includes("top kept b of 3: finished first"), one!.kept.join("; "));
  assert.deepEqual([two!.n, two!.stage, two!.accepted, two!.landed, two!.check], [2, "done", ["count-test"], ["count-test"], "pass"]);
  assert.equal(two!.failed, "FAIL: test_a_hyphen_splits_a_word");
  assert.equal(roundLine(two!), "Round 2 · done · 1 accepted · 1 landed · goal ✓ · $0.02");
  assert.equal(roundLine(one!), "Round 1 · checking · 3 accepted · 3 landed · goal ✗ · $0.0096");
});

test("a log with no auto rows has no rounds, and a line that is not JSON is no row", () => {
  assert.deepEqual(rounds(parseLog('{"id": 1, "node_id": "a", "kind": "added", "detail": {}}\nnot json\n')), []);
});

test("a second goal starts the rounds again: its round 1 is not merged into the first goal's", () => {
  const row = (id: number, kind: string, node_id: string, detail: Record<string, unknown>) => JSON.stringify({ id, kind, node_id, detail });
  const log = [
    row(1, "auto", "*", { round: 1, stage: "planning", root: "first-goal" }),
    row(2, "accepted", "a", { by: "auto", round: 1 }),
    row(3, "auto", "*", { round: 1, stage: "done", root: "first-goal", check: "pass" }),
    row(4, "auto", "*", { round: 1, stage: "planning", root: "second-goal" }),
    row(5, "accepted", "b", { by: "auto", round: 1 }),
  ].join("\n");
  const [only, ...rest] = rounds(parseLog(log));
  assert.equal(rest.length, 0);
  assert.deepEqual([only!.n, only!.stage, only!.accepted, only!.check], [1, "planning", ["b"], ""]);
});

test("a later ask the envelope accepts is not round 1's: an accepted row without a round, or after done, is no round's", () => {
  const row = (id: number, kind: string, node_id: string, detail: Record<string, unknown>) => JSON.stringify({ id, kind, node_id, detail });
  // the stranger's log: auto ran a goal to done, then a `graphene ask` with auto on; `take` logs its accepts
  // `by: auto` with no round, since auto's own round is over
  const log = [
    row(1, "auto", "*", { round: 1, stage: "planning", root: "goal" }),
    row(2, "accepted", "a", { by: "auto", round: 1 }),
    row(3, "picked", "a", { fork: "b", of: 3, reason: "finished first" }),
    row(4, "landed", "a", {}),
    row(5, "auto", "*", { round: 1, stage: "done", root: "goal", check: "pass" }),
    row(6, "accepted", "later", { by: "auto" }),
    row(7, "landed", "later", {}),
  ].join("\n");
  const [one, ...rest] = rounds(parseLog(log));
  assert.equal(rest.length, 0);
  assert.deepEqual([one!.accepted, one!.landed, one!.check], [["a"], ["a"], "pass"]);
});
