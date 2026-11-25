// The recorded session the extension carries (media/replay.jsonl), played back (src/sessions/replay.ts).
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";
import { Replay } from "../src/sessions/replay.ts";
import { snapshot } from "../src/sessions/snapshot.ts";

const text = readFileSync(new URL("../media/replay.jsonl", import.meta.url), "utf8");

test("the recording names no real folder or person: its paths were made generic when it was recorded", () => {
  assert.doesNotMatch(text, /\/Users\/|\/home\/(?!you\b)|\/private\/|\/tmp\//);
  assert.ok(text.split("\n").filter(Boolean).every((l) => { const o = JSON.parse(l) as { cwd?: string }; return o.cwd === undefined || o.cwd === "/work/textkit"; }));
  assert.ok(text.length < 60_000, "small enough to ship in the .vsix");
});

test("played an event at a time it draws as a real session does: a request, its two subagents fanning out, then a follow-up", () => {
  const r = new Replay(text), now = () => r.clock + 500;
  assert.equal(snapshot([r.model], now()).tasks.length, 0); // nothing played yet
  r.step();
  let s = snapshot([r.model], now());
  assert.deepEqual(s.tasks.map((t) => [t.card!.kind, t.card!.says]), [["request", "working"]]); // it is at work as soon as it is asked
  assert.equal(s.sessions![0]!.status, "working");
  const seen = new Set<string>();
  while (r.step()) for (const t of snapshot([r.model], now()).tasks) seen.add(`${t.card!.kind} ${t.card!.says}`);
  assert.ok(seen.has("subagent working") && seen.has("subagent done"), [...seen].join(", ")); // a subagent is seen at work, then back
  s = snapshot([r.model], now());
  assert.deepEqual(s.tasks.map((t) => [t.card!.kind, t.card!.says]), [["request", "done"], ["subagent", "done"], ["subagent", "done"], ["request", "done"]]);
  assert.deepEqual(s.tasks[0]!.changed, ["textkit.py", "test_textkit.py"]);
  assert.equal(s.sessions![0]!.status, "idle");
  assert.equal(s.edges.length, 4); // the request to each subagent, each to the follow-up
  assert.ok(r.over && !r.step()); // at its end it stays as it is
});
