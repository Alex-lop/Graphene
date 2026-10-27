import assert from "node:assert/strict";
import { test } from "node:test";
import * as C from "../src/commands.ts";

test("the proposal's id and title are read from the first line graphene ask --step prints", () => {
  assert.deepEqual(C.proposed("proposed greet-route: a greet route in app.py\nnext: accept it\n"), { id: "greet-route", title: "a greet route in app.py" });
  assert.equal(C.proposed("nothing proposed\n"), null);
  assert.equal(C.proposed(""), null);
});

test("a refused step is told by the refusal, not by the planner's progress line before it", () => {
  assert.equal(C.refusal("asking the planner (planner.py)…\nthe planner proposed no step; nothing was added\n"),
               "the planner proposed no step; nothing was added");
  assert.equal(C.refusal("asking the planner (planner.py)…\nGraphene could not read the proposal: line 1 [x]: x and y both write a.py\nasking the planner (planner.py) again…\nno proposal after 2 tries\n"),
               "Graphene could not read the proposal: line 1 [x]: x and y both write a.py");
  assert.equal(C.refusal("/usr/bin/graphene was not found"), "/usr/bin/graphene was not found");
  assert.equal(C.refusal("asking the planner…\n", "it said this on stdout"), "asking the planner…", "progress alone is still a line");
  assert.equal(C.refusal("", ""), "graphene said nothing");
});

test("a step by hand with no check asks for the person's sign-off, so the CLI takes the leaf as one it can finish", () => {
  assert.deepEqual(C.byHand("greet route", null, [], "app.py tests/**", ""),
                   ["node", "add", "--scope", "app.py", "--scope", "tests/**", "--signoff", "--", "greet route"]);
  assert.deepEqual(C.byHand(" greet route ", "api", ["hello"], "app.py", " pytest -q "),
                   ["node", "add", "--parent", "api", "--needs", "hello", "--scope", "app.py", "--check", "pytest -q", "--", "greet route"]);
  assert.ok(C.addStep({ title: "x", scope: ["a.py"], signoff: true }).includes("--signoff"));
  assert.ok(!C.addStep({ title: "x", scope: ["a.py"], check: "true" }).includes("--signoff"));
});

test("Add Step by Hand's places show a task's or a sub-goal's title as text, never as an icon", () => {
  const near = C.places({ title: "$(trash) the old route", parent: null });
  assert.ok(!near[0]!.label.includes("$("), near[0]!.label);
  assert.equal(near[0]!.v, "after");
  assert.equal(near[1]!.description, "at the top");
  const goals = C.goalPlaces([{ id: "api", title: "[x](command:graphene.stop) the API" }]);
  assert.equal(goals[0]!.id, null);
  assert.ok(!goals[1]!.label.includes("]("), goals[1]!.label);
  assert.equal(goals[1]!.id, "api");
});
