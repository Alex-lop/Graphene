import assert from "node:assert/strict";
import { test } from "node:test";
import * as C from "../src/commands.ts";

test("every mutation is the argv the cockpit's verbs use", () => {
  assert.deepEqual(C.addStep({ title: "greet route", parent: "api", needs: ["hello"], scope: ["app.py", "tests/**"], check: "pytest -q" }),
                   ["node", "add", "greet route", "--parent", "api", "--needs", "hello", "--scope", "app.py", "--scope", "tests/**", "--check", "pytest -q"]);
  assert.deepEqual(C.addStep({ title: "top" }), ["node", "add", "top"]);
  assert.deepEqual(C.link("a", "b"), ["node", "set", "b", "--add-needs", "a"]);
  assert.deepEqual(C.unlink("a", "b"), ["node", "set", "b", "--drop-needs", "a"]);
  assert.deepEqual(C.editStep("x", "title", "new words"), ["node", "set", "x", "--title", "new words"]);
  assert.deepEqual(C.editStep("x", "scope", ["a.py", "b/**"]), ["node", "set", "x", "--scope", "a.py", "--scope", "b/**"]);
  assert.deepEqual(C.editStep("x", "check", "pytest -q"), ["node", "set", "x", "--check", "pytest -q"]);
  assert.deepEqual(C.dropStep("x"), ["node", "drop", "x"]);
  assert.deepEqual(C.accept("x"), ["plan", "accept", "x"]);
  assert.deepEqual(C.accept(), ["plan", "accept"]);
  assert.deepEqual(C.acceptAll(), ["plan", "accept"]);
  assert.deepEqual(C.tell("x", "keep both routes"), ["board", "note", "keep both routes", "--about", "x"]);
  assert.deepEqual(C.stop(), ["run", "--stop"]);
  assert.deepEqual(C.runReady(), ["run", "--parallel", "4"]);
  assert.deepEqual(C.stateJson(), ["state", "--json"]);
  assert.deepEqual(C.auto("a CLI that greets", 2), ["auto", "a CLI that greets", "--budget", "2"]);
  assert.deepEqual(C.auto("a CLI that greets"), ["auto", "a CLI that greets"]);
  assert.deepEqual(C.auto("x", null), ["auto", "x"]);
  assert.deepEqual(C.auto("x", 2, true), ["auto", "x", "--budget", "2", "--plan"]);
  assert.deepEqual(C.setting("budget", "2"), ["config", "set", "budget", "2"]);
  assert.deepEqual(C.setting("auto", "on"), ["config", "set", "auto", "on"]);
});

test("the agent marks are taken out of the environment, nothing else is", () => {
  const env = { PATH: "/bin", CLAUDECODE: "1", CLAUDE_CODE_SESSION_ID: "s", CODEX_SESSION_ID: "c", CODEX_SANDBOX: "1",
                AI_AGENT: "x", GRAPHENE_NODE: "n", GRAPHENE_PLANNER: "p", GEMINI_CLI: "1", CURSOR_AGENT: "1", HOME: "/h" };
  assert.deepEqual(C.scrub(env), { PATH: "/bin", HOME: "/h" });
  assert.deepEqual(Object.values(C.unmarked()), Array(C.MARKS.length).fill(null));
  assert.ok("GRAPHENE_NODE" in C.unmarked());
});

test("globs typed in one box split on spaces and commas", () => {
  assert.deepEqual(C.globs("app.py, tests/**  docs/*.md"), ["app.py", "tests/**", "docs/*.md"]);
  assert.deepEqual(C.globs("  "), []);
});

test("a refusal is read from the first line of stderr, then stdout", () => {
  assert.equal(C.firstLine("\nonly the person accepts a plan\n  (the plan of ~/app)\n"), "only the person accepts a plan");
  assert.equal(C.firstLine("", "+ greet route  greet  proposed\nnext: accept it"), "+ greet route  greet  proposed");
  assert.equal(C.firstLine("", ""), "graphene said nothing");
});

test("a terminal line quotes what a shell would split", () => {
  assert.equal(C.shellLine("graphene", C.auto("a CLI that greets, in Rust's words", 2)),
               "graphene auto 'a CLI that greets, in Rust'\\''s words' --budget 2");
  assert.equal(C.shellLine("/opt/bin/graphene", ["watch"]), "/opt/bin/graphene watch");
});
