import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";
import { autoLine, parseState, summary, usd } from "../src/state.ts";

const fixture = (name: string) => readFileSync(new URL(`./fixtures/${name}.json`, import.meta.url), "utf8");

test("the empty plan parses to no tasks and a zero scoreboard", () => {
  const s = parseState(fixture("empty"));
  assert.equal(s.schema, 1);
  assert.deepEqual(s.tasks, []);
  assert.deepEqual(s.goals, []);
  assert.equal(s.auto, null);
  assert.equal(s.scoreboard.total, 0);
  assert.equal(summary(s), "no plan yet");
  assert.equal(autoLine(s), "");
});

test("proposals carry their question, their sub-goals and the edges between them", () => {
  const s = parseState(fixture("proposals"));
  assert.equal(s.tasks.length, 4);
  assert.ok(s.tasks.every((t) => t.state === "proposed" && t.needs_you));
  assert.equal(s.questions[0]?.about, "greet");
  assert.deepEqual(s.goals.map((g) => g.id), ["words", "api"]);
  assert.equal(s.edges.length, 4);
  assert.equal(summary(s), "4 need you");
});

test("a running plan with three forks keeps each fork's letter, model, state and the kept one", () => {
  const s = parseState(fixture("running"));
  const greet = s.tasks.find((t) => t.id === "greet")!;
  assert.equal(greet.state, "running");
  assert.equal(greet.model, "Nano");
  assert.deepEqual(greet.forks.map((f) => [f.letter, f.model, f.state]),
                   [["a", "Nano", "gave up"], ["b", "Nano", "passed"], ["c", "Super", "running"]]);
  assert.deepEqual(greet.kept, { letter: "b", why: "4 lines against 12", by: "rule" });
  assert.equal(s.run.pid, 4242);
  assert.equal(summary(s), "2 running · 2 need you · $0.42");
});

test("auto waiting reads as a header with the round, the stage and the spend of the budget", () => {
  const s = parseState(fixture("auto"));
  assert.equal(s.envelope.auto, "on");
  assert.equal(s.auto?.stage, "waits");
  assert.equal(autoLine(s), "auto · round 2 of 3 · waits · $1.37 of $2.00 · the goal's check is still red after 2 rounds");
  assert.equal(summary(s), "1 needs you · $1.37");
});

test("missing keys take defaults and unknown keys are ignored", () => {
  const s = parseState(JSON.stringify({
    schema: 2, goal: "x", colour: "mauve",
    tasks: [{ id: "a", title: "A", state: "running", shiny: true, forks: [{ letter: "a" }] }, { title: "no id" }],
    edges: [["a", "ghost", "needs"], ["a", "a"], "junk"],
  }));
  assert.equal(s.schema, 2);
  assert.equal(s.tasks.length, 1);
  const a = s.tasks[0]!;
  assert.equal(a.state, "running");
  assert.deepEqual(a.scope, []);
  assert.equal(a.kept, null);
  assert.deepEqual(a.forks[0], { letter: "a", state: "", why: "", lines: null, model: "", usd: null });
  assert.deepEqual(s.edges, [["a", "a", "needs"]]); // an edge to a task that is not there is dropped
  assert.equal(s.envelope.auto, "off");
  assert.equal(s.scoreboard.total, 1);
  assert.equal(s.run.going, false);
});

test("a state word the extension does not know reads as waiting, and an agent number may be a number", () => {
  const s = parseState(JSON.stringify({ tasks: [{ id: "a", state: "dancing", agent: 2 }] }));
  assert.equal(s.tasks[0]?.state, "waiting");
  assert.equal(s.tasks[0]?.agent, "2");
});

test("dollars read as the cockpit shows them", () => {
  assert.equal(usd(0.42), "$0.42");
  assert.equal(usd(0.004), "$0.004");
  assert.equal(usd(0), "");
  assert.equal(usd(null), "");
  assert.equal(usd(12), "$12.00");
});

test("bad JSON throws, so the caller shows a CLI error rather than an empty plan", () => {
  assert.throws(() => parseState("not json"));
});

test("a real snapshot, `graphene state --json` at the end of the --auto replay, parses whole", () => {
  // made by replaying src/graphene_map/demo-auto.jsonl to its last frame and running `graphene state --json` there
  const s = parseState(fixture("real-auto"));
  assert.equal(s.schema, 1);
  assert.deepEqual(s.tasks.map((t) => [t.id, t.state]), [["top", "done"], ["reading", "done"], ["hyphens", "done"], ["count-test", "done"]]);
  assert.ok(s.tasks.every((t) => t.model === "stand-in-Nano" && t.forks.length === 3));
  assert.deepEqual(s.tasks[0]!.forks.map((f) => f.state), ["passed", "passed", "gave up"]);
  assert.equal(autoLine(s), "auto · round 2 of 3 · done · $0.02 of $2.00");
});
