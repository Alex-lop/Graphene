// A session as the snapshot the graph draws (src/sessions/snapshot.ts), on hand-made files
// (test/fixtures/sessions).
import assert from "node:assert/strict";
import { readFileSync, writeFileSync } from "node:fs";
import * as path from "node:path";
import { test } from "node:test";
import { empty, fold } from "../src/sessions/model.ts";
import { planSteps, QUIET, snapshot, status, titleOf } from "../src/sessions/snapshot.ts";
import { at, FIX, read, ROLLOUT } from "./sessions.ts";

test("Claude Code: the snapshot is a card a request, in order, with what each wrote and what the last is doing", async () => {
  const m = await read("requests.jsonl");
  const s = snapshot([m], at("2026-11-24T10:00:40.000Z"));
  assert.deepEqual(s.sessions!.map((x) => [x.agent, x.title, x.status, x.requests]), [["claude", "Fix the word counter", "working", 3]]);
  assert.deepEqual(s.tasks.map((t) => [t.title, t.state, t.card!.says, t.card!.kind]), [
    ["Fix the word counter: two spaces in a row count as a word.", "done", "done", "request"],
    ["/review the counter", "done", "interrupted", "request"],
    ["Now make it count hyphenated words as one.", "running", "working", "request"],
  ]);
  assert.deepEqual(s.tasks[0]!.changed, ["wordcount.py", "tests/test_wordcount.py"]); // from the session's folder
  assert.equal(s.tasks[0]!.note, "Fixed, and both tests pass."); // over: the agent's last words
  assert.equal(s.tasks[2]!.note, "$ python3 -m unittest"); // under way: the call that is out
  assert.deepEqual(s.tasks[0]!.tail.slice(-2), ["write tests/test_wordcount.py", "$ python3 -m unittest -v"]);
  assert.deepEqual(s.edges, [[s.tasks[0]!.id, s.tasks[1]!.id, "needs"], [s.tasks[1]!.id, s.tasks[2]!.id, "needs"]]);
  assert.equal(s.goal, ""); // no goal card: a session is not a plan
  assert.ok(s.tasks.every((t) => t.parent === null && t.agent === "Claude Code"));
  assert.deepEqual(s.scoreboard, { need_you: 0, running: 1, proven: 2, total: 3 });
});

test("working is said while something says it still runs, needs you only on proof, else idle", async () => {
  const m = await read("requests.jsonl"), last = at(m.last);
  assert.equal(status(m, last + 1000), "working");
  assert.equal(status(m, last + QUIET + 1000), "working"); // quiet, but its command is still out
  assert.equal(status(m, last + 31 * 60_000), "idle"); // nothing for half an hour: nothing says it runs
  assert.equal(status(m, last + 1000, { status: "idle" }), "idle"); // its own process says so
  assert.equal(status(m, last + 31 * 60_000, { status: "busy" }), "working");
  // a question put to the person and not answered is the proof, while something says it is still there to be answered
  fold(m, { k: "tool", at: "2026-11-24T10:00:50.000Z", id: "q1", name: "AskUserQuestion", input: { questions: [] }, side: "" });
  const asked = at("2026-11-24T10:00:50.000Z");
  assert.equal(status(m, asked + 20 * 60_000), "needs you");
  assert.equal(snapshot([m], asked + 20 * 60_000).tasks.at(-1)!.needs_you, true);
  assert.equal(status(m, asked + 23 * 86_400_000), "idle"); // three weeks on, no process: nobody is there to answer
  assert.equal(status(m, asked + 23 * 86_400_000, { status: "idle" }), "needs you"); // its process is: it still waits
  fold(m, { k: "result", at: "2026-11-24T10:00:55.000Z", id: "q1", error: false, out: "", err: "", interrupted: false, exit: 0, more: {} });
  assert.equal(status(m, at("2026-11-24T10:00:56.000Z")), "working");
  fold(m, { k: "end", at: "2026-11-24T10:01:00.000Z", side: "" });
  assert.equal(status(m, at("2026-11-24T10:01:01.000Z"), { status: "busy" }), "idle"); // its request is over
  assert.equal(status(empty("claude", "x"), 0), "idle");
});

test("its own task list is drawn after the request that wrote it: a card a task, in the list's order", async () => {
  const m = await read("tasks.jsonl");
  const s = snapshot([m], at(m.last) + 1000);
  assert.deepEqual(s.tasks.map((t) => [t.title, t.state, t.card!.says, t.card!.kind]), [
    ["Add CSV export, with a test, and update the README.", "running", "working", "request"],
    ["Write the CSV writer", "done", "done", "task"],
    ["Test an empty table", "running", "working", "task"],
    ["Say it in the README", "waiting", "not started", "task"],
  ]);
  assert.deepEqual(s.tasks[1]!.changed, ["export/csv.py"]); // written while it was the one in progress
  assert.equal(s.tasks[2]!.note, "$ pytest -q tests/test_csv.py");
  assert.deepEqual(s.edges.map(([a, b]) => [a.split("/")[1], b.split("/")[1]]), [["r1", "r1t1"], ["r1t1", "r1t2"], ["r1t2", "r1t3"]]);
  // the request ends with a task still in progress: its card says so, and is not called working
  fold(m, { k: "end", at: "2026-11-24T10:00:20.000Z", side: "" });
  assert.deepEqual(snapshot([m], at(m.last) + 1000).tasks.map((t) => t.card!.says), ["done", "done", "left in progress", "not started"]);
});

test("TodoWrite rewrites the list whole, a plan is drawn only without a list, and each belongs to its own request", () => {
  const m = empty("claude", "x", "s1");
  fold(m, { k: "ask", at: "2026-11-24T10:00:00.000Z", text: "do it", side: "" });
  fold(m, { k: "tool", at: "2026-11-24T10:00:01.000Z", id: "p", name: "ExitPlanMode", input: { plan: "# Plan\n\n1. Read the parser\n2. Fix the last token\n3. Run the tests\n" }, side: "" });
  let s = snapshot([m], at("2026-11-24T10:00:02.000Z"));
  assert.deepEqual(s.tasks.map((t) => [t.title, t.card!.says, t.card!.kind]), [["do it", "needs you", "request"], ["Read the parser", "planned", "step"], ["Fix the last token", "planned", "step"], ["Run the tests", "planned", "step"]]);
  assert.equal(s.sessions![0]!.status, "needs you"); // the plan is put to the person, and not answered
  fold(m, { k: "result", at: "2026-11-24T10:00:02.500Z", id: "p", error: false, out: "", err: "", interrupted: false, exit: 0, more: {} });
  const todos = (a: string, b: string) => fold(m, { k: "tool", at: "2026-11-24T10:00:03.000Z", id: `w${a}${b}`, name: "TodoWrite", side: "",
    input: { todos: [{ content: "Fix the last token", status: a, activeForm: "Fixing" }, { content: "Run the tests", status: b, activeForm: "Running" }] } });
  todos("in_progress", "pending");
  fold(m, { k: "tool", at: "2026-11-24T10:00:04.000Z", id: "e", name: "Edit", input: { file_path: "/w/parser.py" }, side: "" });
  fold(m, { k: "result", at: "2026-11-24T10:00:05.000Z", id: "e", error: false, out: "", err: "", interrupted: false, exit: 0, more: {} });
  todos("completed", "in_progress");
  s = snapshot([m], at("2026-11-24T10:00:06.000Z"));
  assert.deepEqual(s.tasks.map((t) => [t.title, t.card!.says]), [["do it", "working"], ["Fix the last token", "done"], ["Run the tests", "working"]]);
  assert.deepEqual(s.tasks[1]!.changed, ["/w/parser.py"]); // it keeps what it did through the rewrite
  // the next request has no list of its own: it is one card, after the last task of the one before
  fold(m, { k: "end", at: "2026-11-24T10:00:07.000Z", side: "" });
  fold(m, { k: "ask", at: "2026-11-24T10:00:08.000Z", text: "and the docs", side: "" });
  s = snapshot([m], at("2026-11-24T10:00:09.000Z"));
  assert.deepEqual(s.tasks.map((t) => [t.title, t.card!.kind]), [["do it", "request"], ["Fix the last token", "task"], ["Run the tests", "task"], ["and the docs", "request"]]);
  assert.deepEqual(s.edges.at(-1), [s.tasks[2]!.id, s.tasks[3]!.id, "needs"]);
  assert.deepEqual(planSteps("just words"), []);
  assert.deepEqual(planSteps("## Parse\ntext\n## Print\ntext"), ["Parse", "Print"]);
});

test("subagents and workflows are a card each, fanning out from the request that launched them", async () => {
  const m = await read("subagents.jsonl");
  const s = snapshot([m], at(m.last) + 1000);
  const by = new Map(s.tasks.map((t) => [t.title, t]));
  assert.deepEqual(s.tasks.map((t) => [t.title, t.card!.kind, t.card!.says]), [
    ["Review the parser and the printer, each on its own, then run the…", "request", "done"],
    ["Review the parser", "subagent", "done"], // back, by its own file's last line and its call's result
    ["Review the printer", "subagent", "working"], // launched behind the request, its thread not at its end
    ["release-check", "workflow", "done"], // every agent of its run ended
    ["Thanks. Fix what the parser review found.", "request", "working"],
  ]);
  const req = s.tasks[0]!.id, parser = by.get("Review the parser")!, printer = by.get("Review the printer")!, flow = by.get("release-check")!, next = s.tasks[4]!.id;
  assert.deepEqual(s.edges, [[req, parser.id, "needs"], [req, printer.id, "needs"], [req, flow.id, "needs"], [parser.id, next, "needs"], [flow.id, next, "needs"]]);
  assert.equal(parser.card!.side, "aaa111"); // its own transcript is its terminal view
  assert.equal(printer.card!.side, "bbb222");
  assert.equal(parser.agent, "general-purpose");
  assert.equal(parser.note, "The parser drops the last token."); // what its own thread said last
  assert.equal(printer.note, "$ grep -n print printer.py"); // and what the one at work is doing
  assert.deepEqual(flow.changed, ["setup.cfg"]); // what a workflow's agents wrote is the workflow's
  assert.equal(flow.card!.side, "");
});

test("a subagent with no note beside it is matched by its first line, which is its call's prompt", () => {
  const m = empty("claude", "x", "s1");
  fold(m, { k: "ask", at: "2026-11-24T10:00:00.000Z", text: "go", side: "" });
  fold(m, { k: "tool", at: "2026-11-24T10:00:01.000Z", id: "a", name: "Agent", input: { description: "Count the lines", prompt: "wc -l *.py" }, side: "" });
  fold(m, { k: "ask", at: "2026-11-24T10:00:02.000Z", text: "wc -l *.py", side: "zzz" });
  fold(m, { k: "tool", at: "2026-11-24T10:00:03.000Z", id: "z1", name: "Bash", input: { command: "wc -l *.py" }, side: "zzz" });
  const t = snapshot([m], at("2026-11-24T10:00:04.000Z")).tasks[1]!;
  assert.deepEqual([t.title, t.card!.side, t.note, t.card!.says], ["Count the lines", "zzz", "$ wc -l *.py", "working"]);
});

test("Codex: a rollout is drawn as the same cards", async () => {
  const m = await read(ROLLOUT, "codex");
  const s = snapshot([m], at(m.last) + 1000);
  assert.deepEqual(s.sessions!.map((x) => [x.agent, x.status, x.title]), [["codex", "idle", "slug() keeps punctuation. Strip it, add a test, and run the tests."]]);
  assert.deepEqual(s.tasks.map((t) => [t.card!.kind, t.card!.says, t.agent]), [["request", "done", "Codex"], ["subagent", "done", "subagent"]]);
  assert.equal(s.tasks[1]!.title, "check the docs");
  assert.deepEqual(s.tasks[0]!.changed, ["slug.py", "test_punctuation.py"]);
  assert.equal(s.tasks[0]!.note, "Punctuation is stripped, and the tests pass.");
});

test("two sessions on one page are a band each, under its title", async () => {
  const a = await read("requests.jsonl"), b = await read(ROLLOUT, "codex");
  const s = snapshot([a, b], at(a.last) + 1000);
  assert.deepEqual(s.goals.map((g) => g.title), ["Fix the word counter", "slug() keeps punctuation. Strip it, add a test, and run the tests."]);
  assert.deepEqual([...new Set(s.tasks.map((t) => t.parent))], s.goals.map((g) => g.id));
  assert.equal(new Set(s.tasks.map((t) => t.id)).size, s.tasks.length); // no two cards share an id
  assert.equal(s.sessions!.length, 2);
});

test("the preview's fixtures are these sessions' own snapshots (UPDATE=1 writes them again)", async () => {
  const when = at("2026-11-24T10:01:00.000Z");
  const drawn: [string, string[]][] = [["session", ["subagents.jsonl"]], ["sessions", ["requests.jsonl", "tasks.jsonl"]]];
  for (const [name, files] of drawn) {
    const s = snapshot(await Promise.all(files.map((f) => read(f))), when);
    for (const x of s.sessions!) x.file = x.file.slice(FIX.length); // where the repository is checked out is not the fixture's
    const file = path.join(FIX, "..", `${name}.json`), text = `${JSON.stringify(s, null, 1)}\n`;
    if (process.env.UPDATE) writeFileSync(file, text);
    assert.equal(readFileSync(file, "utf8"), text, `${name}.json is not what the reader draws now: UPDATE=1 node --test test/sessions.test.ts`);
  }
});

test("what an earlier request left out or in progress does not make this one working, or take its work", () => {
  const m = empty("claude", "x", "s1"), t = (s: number) => `2026-11-24T10:00:${String(s).padStart(2, "0")}.000Z`;
  fold(m, { k: "ask", at: t(0), text: "first", side: "" });
  fold(m, { k: "tool", at: t(1), id: "w", name: "TodoWrite", input: { todos: [{ content: "A", status: "in_progress", activeForm: "Doing A" }] }, side: "" });
  fold(m, { k: "tool", at: t(2), id: "orphan", name: "Bash", input: { command: "sleep 999" }, side: "" }); // its result never came: a crash
  fold(m, { k: "stop", at: t(3), side: "" });
  fold(m, { k: "ask", at: t(10), text: "rename foo.py", side: "" });
  fold(m, { k: "tool", at: t(11), id: "e", name: "Edit", input: { file_path: "/w/foo.py" }, side: "" });
  fold(m, { k: "result", at: t(12), id: "e", error: false, out: "", err: "", interrupted: false, exit: 0, more: {} });
  const s = snapshot([m], at(t(12)) + 5 * 60_000); // five minutes quiet, nothing of this request out
  assert.equal(s.sessions![0]!.status, "idle"); // the first request's orphan does not hold it at working
  assert.deepEqual(s.tasks.map((x) => [x.title, x.changed]), [["first", []], ["A", []], ["rename foo.py", ["/w/foo.py"]]]); // A did not edit foo.py
});

test("a request that left a subagent running behind it is working while that thread is, though the request is over", async () => {
  const m = await read("subagents.jsonl");
  fold(m, { k: "end", at: "2026-11-24T10:00:42.000Z", side: "" }); // the second request ends; the printer's review is still out
  assert.equal(status(m, at("2026-11-24T10:00:43.000Z")), "idle"); // nothing of the last request is behind it
  const n = await read("subagents.jsonl");
  n.turns.pop(); // as it stood before the second request: over, its background review at work
  assert.equal(status(n, at("2026-11-24T10:00:30.000Z")), "working");
  assert.equal(status(n, at("2026-11-24T11:30:00.000Z")), "idle"); // an hour and a half quiet: nothing says it runs
});

test("two sessions whose ids begin alike (Codex's begin with the time) keep cards apart", () => {
  const a = empty("codex", "a", "019a1b2c-0000-7000-8000-00000000000a"), b = empty("codex", "b", "019a1b2c-0000-7000-8000-00000000000b");
  for (const m of [a, b]) fold(m, { k: "ask", at: "2026-11-24T10:00:00.000Z", text: "go", side: "" });
  const ids = snapshot([a, b], 0).tasks.map((t) => t.id);
  assert.equal(new Set(ids).size, 2);
});

test("a long session folds its oldest requests into one card", () => {
  const m = empty("claude", "x", "s1");
  for (let i = 1; i <= 11; i++) {
    fold(m, { k: "ask", at: `2026-11-24T10:${String(i).padStart(2, "0")}:00.000Z`, text: `request ${i}`, side: "" });
    fold(m, { k: "end", at: `2026-11-24T10:${String(i).padStart(2, "0")}:30.000Z`, side: "" });
  }
  const s = snapshot([m], at("2026-11-24T11:00:00.000Z"));
  assert.deepEqual(s.tasks.map((t) => t.title), ["3 earlier requests", ...[4, 5, 6, 7, 8, 9, 10, 11].map((i) => `request ${i}`)]);
  assert.equal(s.tasks[0]!.card!.kind, "earlier");
  assert.equal(s.edges.length, 8);
});

test("a title is the first line that says something, without its markup, cut at a word", () => {
  assert.equal(titleOf("\n\n## Fix `the` bug\nmore"), "Fix `the` bug");
  assert.equal(titleOf("- [ ] one\n- two"), "[ ] one");
  assert.equal(titleOf("```python\n---\n"), ""); // a code fence's line is not words
  assert.equal(titleOf("`slug()` now collapses dashes."), "`slug()` now collapses dashes."); // code in a sentence keeps its marks
  assert.ok(titleOf("word ".repeat(40)).length <= 72);
});
