// A transcript's tail as a terminal would have shown it, and whose terminal a session runs in (src/sessions/term.ts).
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";
import { claudeLine } from "../src/sessions/claude.ts";
import { ancestors, OUTPUT_LINES, parents, resumeLine, Term } from "../src/sessions/term.ts";

const plain = (lines: string[]) => lines.map((l) => l.replace(/\x1b\[[0-9;]*m/g, ""));
const lines = (name: string) => readFileSync(new URL(`./fixtures/sessions/${name}`, import.meta.url), "utf8").split("\n");

test("a session's lines read like its terminal: the ask, what it said, each command, the end of its output", () => {
  const t = new Term("/work/app");
  const out = plain(lines("requests.jsonl").flatMap(claudeLine).flatMap((ev) => t.feed(ev)));
  assert.deepEqual(out.slice(0, 13), [
    "", "❯ Fix the word counter: two spaces in a row count as a word.", "  Add a test for it.", "",
    "· read wordcount.py",
    "The split on a single space is the bug.", "",
    "✎ edit wordcount.py",
    "✎ write tests/test_wordcount.py",
    "$ python3 -m unittest -v",
    "  Ran 2 tests in 0.001s",
    "  ",
    "  OK",
  ]);
  assert.ok(out.includes("— interrupted —"));
  assert.equal(out.filter((l) => l === "— its turn ended —").length, 1); // said once, though the transcript says it on two lines
  const at = out.indexOf("$ git diff --stat");
  assert.deepEqual(out.slice(at, at + 4), ["$ git diff --stat", "  Exit code 128", "  fatal: not a git repository", "  ✗ exit 128"]); // a failed command says so
  assert.equal(out.at(-1), "$ python3 -m unittest"); // still out: its output is not there yet
});

test("only the end of a long output is shown, and nothing an agent wrote can drive the terminal", () => {
  const t = new Term();
  t.feed({ k: "tool", at: "", id: "c", name: "Bash", input: { command: "seq 100" }, side: "" });
  const long = plain(t.feed({ k: "result", at: "", id: "c", error: false, out: Array.from({ length: 100 }, (_, i) => String(i + 1)).join("\n"), err: "", interrupted: false, exit: 0, more: {} }));
  assert.equal(long[0], `  … ${100 - OUTPUT_LINES} lines above`);
  assert.deepEqual(long.slice(1, 3), ["  87", "  88"]);
  assert.equal(long.at(-2), "  100");
  // an escape sequence in a transcript (a title change, a cursor move, a bell) is printed as nothing
  const evil = t.feed({ k: "say", at: "", text: "ok\x1b]0;owned\x07 \x1b[2J\x1b[H done\x9b31m", side: "", model: "" });
  assert.ok(evil.every((l) => !/[\x00-\x08\x0b-\x1f\x7f-\x9f]/.test(l)), JSON.stringify(evil));
  assert.equal(t.feed({ k: "tool", at: "", id: "d", name: "Bash", input: { command: "echo \x1b[31mred" }, side: "" })[0]!.replace(/\x1b\[36m|\x1b\[0m/g, ""), "$ echo [31mred");
  // a command that was refused did not run: it is not printed as a failure of the command
  t.feed({ k: "tool", at: "", id: "e", name: "Bash", input: { command: "rm -rf build" }, side: "" });
  assert.deepEqual(plain(t.feed({ k: "result", at: "", id: "e", error: true, out: "This command requires approval", err: "", interrupted: false, exit: null, more: {} })), ["  This command requires approval", "  ✗ did not run", ""]);
});

test("the editor's terminal a session runs in is the one above its process", () => {
  const table = parents("  501   1\n  610 501\n  611 610\n  700   1\n  701 700\n garbage\n");
  assert.deepEqual(ancestors(611, table), [611, 610, 501, 1]); // the agent, its shell, the terminal's host
  assert.deepEqual(ancestors(701, table), [701, 700, 1]);
  assert.deepEqual(ancestors(999, table), [999]); // a process that is gone: only itself
  assert.deepEqual(ancestors(5, new Map([[5, 6], [6, 5]])), [5, 6]); // a table that loops ends the walk
});

test("a session is taken up again by its id, and an id that is not one puts nothing on a shell's line", () => {
  assert.equal(resumeLine("claude", "4a26adbb-6712-4d1f-9289-17fc4becbb73"), "claude --resume 4a26adbb-6712-4d1f-9289-17fc4becbb73");
  assert.equal(resumeLine("codex", "01a20f92-f7bd-7743-aec6-1d9cea565dcf"), "codex resume 01a20f92-f7bd-7743-aec6-1d9cea565dcf");
  for (const bad of ["", "x", "a; rm -rf ~", "$(id)", "--help", "id with space", "a/../b"]) assert.equal(resumeLine("claude", bad), "", bad);
});
