import assert from "node:assert/strict";
import { test } from "node:test";
import * as C from "../src/commands.ts";

test("every mutation is the argv the cockpit's verbs use", () => {
  assert.deepEqual(C.addStep({ title: "greet route", parent: "api", needs: ["hello"], scope: ["app.py", "tests/**"], check: "pytest -q" }),
                   ["node", "add", "--parent", "api", "--needs", "hello", "--scope", "app.py", "--scope", "tests/**", "--check", "pytest -q", "--", "greet route"]);
  assert.deepEqual(C.addStep({ title: "top" }), ["node", "add", "--", "top"]);
  assert.deepEqual(C.link("a", "b"), ["node", "set", "b", "--add-needs", "a"]);
  assert.deepEqual(C.logJson(), ["plan", "log", "--json"]);
  assert.deepEqual(C.keySet(), ["key", "set"]);
  assert.deepEqual(C.keySet("nim"), ["key", "set", "--endpoint", "nim"]);
  assert.deepEqual(C.logJson(230), ["plan", "log", "--json", "--since", "230"]);
  assert.deepEqual(C.unlink("a", "b"), ["node", "set", "b", "--drop-needs", "a"]);
  assert.deepEqual(C.editStep("x", "title", "new words"), ["node", "set", "x", "--title", "new words"]);
  assert.deepEqual(C.editStep("x", "scope", ["a.py", "b/**"]), ["node", "set", "x", "--scope", "a.py", "--scope", "b/**"]);
  assert.deepEqual(C.editStep("x", "check", "pytest -q"), ["node", "set", "x", "--check", "pytest -q"]);
  assert.deepEqual(C.dropStep("x"), ["node", "drop", "x"]);
  assert.deepEqual(C.accept("x"), ["plan", "accept", "x"]);
  assert.deepEqual(C.accept(), ["plan", "accept"]);
  assert.deepEqual(C.acceptAll(), ["plan", "accept"]);
  assert.deepEqual(C.tell("x", "keep both routes"), ["board", "note", "--about", "x", "--", "keep both routes"]);
  assert.deepEqual(C.stop(), ["run", "--stop"]);
  assert.deepEqual(C.runReady(), ["run", "--parallel", "4"]);
  assert.deepEqual(C.stateJson(), ["state", "--json"]);
  assert.deepEqual(C.auto("a CLI that greets", 2), ["auto", "--budget", "2", "--", "a CLI that greets"]);
  assert.deepEqual(C.auto("a CLI that greets"), ["auto", "--", "a CLI that greets"]);
  assert.deepEqual(C.auto("x", null), ["auto", "--", "x"]);
  assert.deepEqual(C.auto("x", 2, true), ["auto", "--budget", "2", "--plan", "--", "x"]);
  assert.deepEqual(C.setting("budget", "2"), ["config", "set", "budget", "2"]);
  assert.deepEqual(C.setting("auto", "on"), ["config", "set", "auto", "on"]);
});

test("the editor night's argv: diffs, forks, the plan's text, a step in a sentence, the demo", () => {
  assert.deepEqual(C.nodeDiff("ids"), ["node", "diff", "ids", "--json"]);
  assert.deepEqual(C.nodeDiff("ids", "b"), ["node", "diff", "ids", "--fork", "b", "--json"]);
  assert.deepEqual(C.pickFork("ids", "b"), ["node", "pick", "ids", "b"]);
  assert.deepEqual(C.signOff("ids"), ["node", "signoff", "ids"]);
  assert.deepEqual(C.planText(), ["plan", "--text"]);
  assert.deepEqual(C.planApply(230), ["plan", "edit", "--from", "-", "--json", "--since", "230"]);
  assert.deepEqual(C.askStep("add a --json flag"), ["ask", "--step", "--", "add a --json flag"]);
  assert.deepEqual(C.askStep("x", { after: "ids" }), ["ask", "--step", "--after", "ids", "--", "x"]);
  assert.deepEqual(C.askStep("x", { under: "api" }), ["ask", "--step", "--under", "api", "--", "x"]);
  assert.deepEqual(C.demoInto("/tmp/d"), ["demo", "--auto", "--into", "/tmp/d"]);
});

test("an id that starts with a dash never reaches argv", () => {
  for (const bad of ["--json", "-", ""]) {
    assert.throws(() => C.nodeDiff(bad), /not an id/);
    assert.throws(() => C.nodeDiff("ids", bad || "-x"), /not an id/);
    assert.throws(() => C.pickFork("ids", bad || "-"), /not an id/);
    assert.throws(() => C.signOff(bad), /not an id/);
    assert.throws(() => C.askStep("x", { after: bad || "-" }), /not an id/);
  }
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
               "graphene auto --budget 2 -- 'a CLI that greets, in Rust'\\''s words'");
  assert.equal(C.shellLine("/opt/bin/graphene", ["watch"]), "/opt/bin/graphene watch");
});

test("a planner's words reach a toast as text: no link, no command, no icon", () => {
  const hostile = "[open a terminal](command:workbench.action.terminal.new) $(check) safe to accept";
  const shown = C.plain(hostile);
  assert.doesNotMatch(shown, /\]\(/, "a Markdown link's bracket pair");
  assert.doesNotMatch(shown, /\$\(/, "a codicon");
  assert.match(shown, /open a terminal/);
  assert.match(shown, /safe to accept/);
  assert.equal(C.plain("plain words, (parens) and $5"), "plain words, (parens) and $5");
  assert.equal(C.plain("two\nlines"), "two lines");
});

test("free text comes after `--`, so a title, a note, an answer or a goal that starts with a dash is words, not an option", () => {
  assert.deepEqual(C.addStep({ title: "- add tests for the counter", scope: ["a.py"], check: "true" }),
                   ["node", "add", "--scope", "a.py", "--check", "true", "--", "- add tests for the counter"]);
  assert.deepEqual(C.tell("n1", "-1 for this route"), ["board", "note", "--about", "n1", "--", "-1 for this route"]);
  assert.deepEqual(C.tell("n1", "-v keep both routes"), ["board", "note", "--about", "n1", "--", "-v keep both routes"]);
  assert.deepEqual(C.auto("--plan a goal", 2, true), ["auto", "--budget", "2", "--plan", "--", "--plan a goal"]);
  for (const argv of [C.addStep({ title: "-x" }), C.tell("n1", "-x"), C.auto("-x")]) {
    assert.equal(argv.indexOf("--"), argv.length - 2, `${argv.join(" ")}: the words are last, after --`);
  }
});

test("a refusal's toast names the command once: the CLI's line already does when it is a usage error", () => {
  assert.equal(C.refused(["board", "note", "--about", "n1", "--", "x"], "graphene board note: no such option: -v (`graphene board note --help` says what it takes)"),
               "graphene board note: no such option: -v (`graphene board note --help` says what it takes)");
  assert.equal(C.refused(["node", "add", "--", "x"], "n2: a leaf needs a scope"), "graphene node add: n2: a leaf needs a scope");
  assert.equal(C.refused(["run", "--stop"], "nothing runs"), "graphene run --stop: nothing runs");
});

test("an older CLI's refusal of a new shape is the one 'older Graphene' line, not a Typer usage line", () => {
  const says = /older than the extension.*0\.8/;
  assert.equal(C.firstLine("graphene node diff: no such option: --json (`graphene node diff --help` says what it takes)\n"), C.OLDER);
  assert.equal(C.firstLine("graphene plan edit: no such option: --from (`graphene plan edit --help` says what it takes)\n"), C.OLDER);
  assert.equal(C.firstLine("graphene demo: no such option: --into (`graphene demo --help` says what it takes)\n"), C.OLDER);
  assert.equal(C.firstLine("graphene plan: no such command: edit\n"), C.OLDER);
  assert.equal(C.refusal("asking the planner…\ngraphene ask: no such option: --step\n"), C.OLDER);
  assert.match(C.OLDER, says);
  assert.equal(C.firstLine("n2: a leaf needs a scope\n"), "n2: a leaf needs a scope", "a refusal of the plan's own is said as it is");
});
