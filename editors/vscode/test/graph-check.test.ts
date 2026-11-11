import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";
import { check } from "../src/graph/check.ts";
import { CHANGES } from "../src/graph/words.ts";
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

test("a replay's host runs nothing that changes a plan or acts outside the replay; what reads still passes", () => {
  const replay = { state: { ...state, replay: { shown: "a scripted stand-in, no model ran", day: "", repository: "" } } };
  for (const act of CHANGES) {
    const id = ["run", "stop", "auto", "cockpit", "add-under"].includes(act) ? "" : act === "answer" ? "which-port" : "farewell";
    const fork = act === "pickFork" ? "b" : undefined;
    const target = act === "link" || act === "unlink" ? "hello" : undefined;
    assert.equal(check({ type: "act", act, id, fork, target }, replay), null, `${act} is refused in a replay`);
  }
  assert.equal(check({ type: "ready" }, replay)?.type, "ready");
});

test("with no plan read yet, only ready and the acts that take no id pass", () => {
  const none = (m: unknown) => check(m, { state: null });
  assert.equal(none({ type: "ready" })?.type, "ready");
  assert.equal(none({ type: "act", act: "auto", id: "" })?.type, "act");
  assert.equal(none({ type: "act", act: "signOff", id: "farewell" }), null);
});

const act = (m: unknown) => { const r = check(m, session); return r?.type === "act" ? r : null; };

test("a field of the form passes with a value its field takes, on a task the plan has", () => {
  const set = (field: unknown, value: unknown, id = "farewell") => act({ type: "act", act: "set", id, field, value });
  assert.deepEqual(set("title", "  a better title "), { type: "act", act: "set", id: "farewell", field: "title", value: "a better title" });
  assert.equal(set("scope", "app.py tests/**")?.value, "app.py tests/**");
  assert.equal(set("check", "")?.value, "", "an empty check is no check");
  assert.equal(set("forks", 3)?.value, 3);
  assert.equal(set("signoff", true)?.value, true);
  assert.equal(set("owner", false)?.value, false);
  for (const [field, value] of [["title", ""], ["title", "  "], ["scope", ""], ["forks", 0], ["forks", 9], ["forks", "3"], ["forks", 2.5], ["signoff", "yes"],
                                ["owner", 1], ["goal", "x"], ["title", "a\nb"], ["title", "x".repeat(2001)], [undefined, "x"]] as const) {
    assert.equal(set(field, value), null, `${String(field)}=${JSON.stringify(value).slice(0, 20)} is refused`);
  }
  assert.equal(set("title", "x", "nobody"), null);
});

test("a drawn task passes whole: a title, its files and check as typed, after a task and under a sub-goal the plan has", () => {
  const draft = { key: " d1", title: " a flag ", files: "cli.py tests/test_cli.py", check: " pytest -q ", approve: false, after: "hello", parent: null };
  const draw = (d: unknown) => act({ type: "act", act: "draw", id: "", draft: d });
  assert.deepEqual(draw(draft)?.draft, { ...draft, title: "a flag", check: "pytest -q" });
  assert.equal(draw({ ...draft, after: null, parent: state.goals[0]!.id })?.draft?.parent, state.goals[0]!.id);
  for (const bad of [{ ...draft, title: " " }, { ...draft, after: "nobody" }, { ...draft, parent: "nowhere" }, { ...draft, approve: "yes" }, { ...draft, files: 3 },
                     { ...draft, key: undefined }, null, "draft"]) assert.equal(draw(bad), null);
  assert.equal(check({ type: "act", act: "draw", id: "", draft }, { state: null }), null, "no plan read: nothing to draw on");
});

test("the planner fills a drawn task in: its title as the sentence, after a task or on its own", () => {
  assert.deepEqual(act({ type: "act", act: "add-after", id: "hello", sentence: " a flag ", key: " d1" }),
                   { type: "act", act: "add-after", id: "hello", sentence: "a flag", key: " d1" });
  assert.equal(act({ type: "act", act: "add-under", id: "", sentence: "a flag", key: " d1" })?.sentence, "a flag");
  assert.equal(act({ type: "act", act: "add-after", id: "hello", sentence: " ", key: " d1" }), null);
  assert.equal(act({ type: "act", act: "add-after", id: "nobody", sentence: "a flag", key: " d1" }), null);
});
