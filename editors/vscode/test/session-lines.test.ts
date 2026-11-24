// Claude Code's transcript and Codex's rollout, a line at a time, read into one vocabulary of events
// (src/sessions/claude.ts, codex.ts), on hand-made files (test/fixtures/sessions).
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";
import { claudeLine } from "../src/sessions/claude.ts";
import { codexLine } from "../src/sessions/codex.ts";
import type { Ev } from "../src/sessions/events.ts";

const lines = (name: string) => readFileSync(new URL(`./fixtures/sessions/${name}`, import.meta.url), "utf8").split("\n");
const kinds = (evs: Ev[]) => evs.map((e) => (e.k === "tool" ? `tool ${e.name}` : e.k === "ask" ? `ask ${e.text.split("\n")[0]}` : e.k));

test("a line that is not understood says nothing: another type, not JSON, cut short, not an object", () => {
  for (const line of ['{"type":"a-type-from-the-future","payload":[1]}', "not JSON {", '{"type":"user","message":{"content":[{"type":"tool_res', "[1,2]", "null", '"user"', "{}"]) {
    assert.deepEqual(claudeLine(line), [], line);
    assert.deepEqual(codexLine(line), [], line);
  }
});

test("Claude Code: a request is the person's own words; a tool call and its result; an end, and an interruption", () => {
  const evs = lines("requests.jsonl").flatMap(claudeLine).filter((e) => e.k !== "meta");
  assert.deepEqual(kinds(evs), [
    "ask Fix the word counter: two spaces in a row count as a word.",
    "tool Read", "result", "say", "tool Edit", "result", "tool Write", "result", "tool Bash", "result", "say", "end", "end",
    "ask /review the counter", // a slash command as typed; its caveat, its echo and a task's notice are no requests
    "tool Bash", "result", "stop",
    "ask Now make it count hyphenated words as one.", "tool Bash", // its result is the truncated last line: not read
  ]);
  const failed = evs.find((e) => e.k === "result" && e.error);
  assert.deepEqual(failed && failed.k === "result" && [failed.exit, failed.out.split("\n")[1]], [128, "fatal: not a git repository"]); // a failed command says its code
  const passed = evs.find((e) => e.k === "result" && e.out.includes("Ran 2 tests"));
  assert.equal(passed && passed.k === "result" && passed.exit, 0);
  assert.deepEqual(claudeLine(lines("requests.jsonl")[2]!)[0], { k: "meta", id: "11111111-2222-4333-8444-555555555555", cwd: "/work/app", branch: "main" });
  assert.deepEqual(claudeLine('{"type":"ai-title","aiTitle":"Fix the word counter"}'), [{ k: "meta", title: "Fix the word counter" }]);
  // a subagent's lines carry its id
  const side = lines("subagents/subagents/agent-aaa111.jsonl").flatMap(claudeLine).filter((e) => e.k !== "meta" && e.k !== "result");
  assert.ok(side.length === 4 && side.every((e) => "side" in e && e.side === "aaa111"));
});

test("Codex: the records of what ran, in Claude Code's names: a command by its exit code, a patch a write a file", () => {
  const evs = lines("rollout-2026-11-24T10-00-00-01a20f92-0000-7000-8000-000000000001.jsonl").flatMap(codexLine);
  assert.deepEqual(evs[0], { k: "meta", id: "01a20f92-0000-7000-8000-000000000001", cwd: "/work/app", branch: "main", head: "25af821668c07e663e06a4bba858439a3cb4fe7e" });
  assert.deepEqual(kinds(evs.slice(1)), [
    "ask slug() keeps punctuation. Strip it, add a test, and run the tests.", // the environment Codex writes into the person's turn is no request
    "say", "tool Bash", "result", "tool Edit", "result", "tool Write", "result", "tool Bash", "result", "tool Agent", "tool Bash", "result", "say", "end",
  ]);
  const results = evs.filter((e) => e.k === "result");
  assert.deepEqual(results.map((e) => e.k === "result" && [e.exit, e.error]), [[0, false], [null, false], [null, false], [1, true], [0, false]]);
  const tools = evs.filter((e) => e.k === "tool");
  assert.deepEqual(tools.map((e) => e.k === "tool" && (e.input.command ?? e.input.file_path ?? e.input.description)),
                   ["cat slug.py", "/work/app/slug.py", "/work/app/test_punctuation.py", "python3 -m unittest", "check the docs", "python3 -m unittest"]);
  assert.deepEqual(codexLine('{"type":"event_msg","payload":{"type":"turn_aborted"},"timestamp":"t"}'), [{ k: "stop", at: "t", side: "" }]);
});
