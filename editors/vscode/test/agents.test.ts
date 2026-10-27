import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";
import { agentRows, ago, description, quiet } from "../src/agents.ts";
import { parseState } from "../src/state.ts";

const fixture = (name: string) => readFileSync(new URL(`./fixtures/${name}.json`, import.meta.url), "utf8");

test("every running agent is a row: a forked task's running forks one each, numbered 3c, with their own model and dollars", () => {
  const rows = agentRows(parseState(fixture("running")));
  assert.deepEqual(rows.map((r) => [r.number, r.id, r.fork, r.model]), [["3", "greet", "c", "Super"], ["4", "farewell", null, "Super"]].map(([n, id, f, m]) => [f ? `${n}${f}` : n, id, f, m]));
  const c = rows[0]!;
  assert.equal(c.now, "read tests/test_app.py"); // the task's last move: a fork has no tail of its own yet
  assert.equal(c.usd, 0.15);
  assert.equal(c.idle, 2.5); // the task's, until the snapshot carries the fork's
  assert.equal(rows[1]!.idle, 14);
});

test("a fork's own idle and a task with no agent number still make a row", () => {
  const s = parseState(JSON.stringify({ schema: 1, tasks: [
    { id: "a", title: "A", state: "running", agent: 2, idle: 9, forks: [{ letter: "a", state: "running", idle: 1.2, usd: 0.01 }, { letter: "b", state: "passed" }] },
    { id: "b", title: "B", state: "running", tail: ["edit b.py"] },
    { id: "c", title: "C", state: "review" },
  ] }));
  const rows = agentRows(s);
  assert.deepEqual(rows.map((r) => [r.number, r.idle, r.now]), [["2a", 1.2, ""], ["?", null, "edit b.py"]]);
});

test("the seconds quiet tick from the snapshot's idle with no read, and read as the cockpit says them", () => {
  assert.equal(quiet(2.5, 1000, 1000), 2);
  assert.equal(quiet(2.5, 1000, 13500), 15);
  assert.equal(quiet(null, 0, 99999), null);
  assert.equal(ago(12), "12s");
  assert.equal(ago(185), "3m 05s");
  const row = agentRows(parseState(fixture("running")))[1]!;
  assert.equal(description(row, 20), "Super · edit app.py · quiet 20s · $0.08");
  assert.equal(description({ ...row, model: "", usd: null, now: "" }, null), "");
});
