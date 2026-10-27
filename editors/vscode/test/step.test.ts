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
