import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";
import { check } from "../src/graph/check.ts";
import { parseState } from "../src/state.ts";

const state = parseState(readFileSync(new URL("./fixtures/graph-race.json", import.meta.url), "utf8"));
const session = { state };
const ok = (m: unknown) => { const r = check(m, session); return r?.type === "act" ? r : r === null ? null : { type: "ready" as const, target: undefined, fork: undefined }; };

test("the host takes ready, and an act it knows on an id the plan has", () => {
  assert.equal(check({ type: "ready" }, session)?.type, "ready");
  assert.deepEqual(ok({ type: "act", act: "signOff", id: "farewell" }), { type: "act", act: "signOff", id: "farewell", target: undefined, fork: undefined });
  assert.deepEqual(ok({ type: "act", act: "link", id: "hello", target: "ship" })?.target, "ship");
  assert.equal(ok({ type: "act", act: "run", id: "" })?.type, "act");
  assert.equal(ok({ type: "act", act: "add-under", id: "" })?.type, "act");
});

test("an unknown act, a stranger's id, a target or a fork the plan lacks, or junk: nothing", () => {
  assert.equal(ok(null), null);
  assert.equal(ok("act"), null);
  assert.equal(ok({ type: "act", act: "rm -rf", id: "hello" }), null);
  assert.equal(ok({ type: "act", act: "signOff", id: "nobody" }), null);
  assert.equal(ok({ type: "act", act: "signOff", id: "" }), null); // an act on a task needs one
  assert.equal(ok({ type: "act", act: "link", id: "hello", target: "../x" }), null);
  assert.equal(ok({ type: "act", act: "pickFork", id: "farewell", fork: "z" }), null);
  assert.equal(ok({ type: "act", act: "pickFork", id: "hello", fork: "a" }), null); // no forks on hello
  assert.equal(ok({ type: "act", act: "signOff", id: ["farewell"] }), null);
});

test("a fork the task has passes; so does an answer with one of the question's options or its default", () => {
  assert.equal(ok({ type: "act", act: "pickFork", id: "farewell", fork: "b" })?.fork, "b");
  assert.equal(ok({ type: "act", act: "answer", id: "which-port", target: "pick a free one at start" })?.target, "pick a free one at start");
  assert.equal(ok({ type: "act", act: "answer", id: "which-port", target: "8000, as the README says" })?.type, "act");
  assert.equal(ok({ type: "act", act: "answer", id: "which-port" })?.type, "act");
  assert.equal(ok({ type: "act", act: "answer", id: "which-port", target: "--help" }), null);
  assert.equal(ok({ type: "act", act: "answer", id: "greet" }), null); // a task's id is not a question's
});

test("with no plan read yet, only ready and the acts that take no id pass", () => {
  const none = (m: unknown) => check(m, { state: null });
  assert.equal(none({ type: "ready" })?.type, "ready");
  assert.equal(none({ type: "act", act: "auto", id: "" })?.type, "act");
  assert.equal(none({ type: "act", act: "signOff", id: "farewell" }), null);
});
