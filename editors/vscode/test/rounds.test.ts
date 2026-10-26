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
