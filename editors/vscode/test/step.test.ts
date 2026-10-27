import assert from "node:assert/strict";
import { test } from "node:test";
import * as C from "../src/commands.ts";

test("the proposal's id and title are read from the first line graphene ask --step prints", () => {
  assert.deepEqual(C.proposed("proposed greet-route: a greet route in app.py\nnext: accept it\n"), { id: "greet-route", title: "a greet route in app.py" });
  assert.equal(C.proposed("nothing proposed\n"), null);
  assert.equal(C.proposed(""), null);
});
