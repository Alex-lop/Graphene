// A transcript's tail as a terminal would have shown it, and whose terminal a session runs in (src/sessions/term.ts).
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";
import { claudeLine } from "../src/sessions/claude.ts";
import { ancestors, commandsOf, OUTPUT_LINES, parents, resumeLine, runs, Term } from "../src/sessions/term.ts";

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
  // a file's name is an agent's words too: git allows control bytes in one, and a cloned repository can hold such a file
  const named = t.feed({ k: "tool", at: "", id: "f", name: "Read", input: { file_path: "/x/a\x1b]0;owned\x07\x1b[2J\x1b[H.py" }, side: "" });
  const inside = new Term("/work/app").feed({ k: "tool", at: "", id: "g", name: "Edit", input: { file_path: "/work/app/b\x1b]8;;https://evil\x07click\x1b]8;;\x07\u202e.py" }, side: "" });
  for (const l of [...named, ...inside]) assert.ok(!/[\x00-\x08\x0b-\x1a\x1c-\x1f\x7f-\x9f\u202e]/.test(l) && !/\x1b(?!\[(2|33|0)m)/.test(l), JSON.stringify(l));
  // a view of one thread prints only that thread's lines
  const mine = new Term("", "");
  assert.deepEqual(mine.feed({ k: "say", at: "", text: "a subagent's words", side: "sidechain", model: "" }), []);
  assert.equal(plain(mine.feed({ k: "say", at: "", text: "the session's own", side: "", model: "" }))[0], "the session's own");
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

test("a record of a process is believed only while that process is the agent's own program", () => {
  const ps = "  611   610 claude --resume abc\n  700     1 /usr/local/bin/node /opt/lib/node_modules/@scope/claude/cli.js -p hi\n  701     1 /bin/zsh -l\n  702     1 codex resume 01a2\n  703 1 vim claude.md\n";
  const command = commandsOf(ps);
  assert.equal(command.get(611), "claude --resume abc");
  assert.deepEqual([611, 700, 701, 702, 703].map((p) => runs(command.get(p) ?? "", "claude")), [true, true, false, false, false]); // a pid given to another program is not the agent
  assert.deepEqual([702, 611].map((p) => runs(command.get(p) ?? "", "codex")), [true, false]);
  assert.equal(runs("", "claude"), false);
  // started by its versioned binary, or from a path with a space in it: still the agent's, or a live session reads as one nobody has
  assert.equal(runs("/home/you/.local/share/claude/versions/2.1.331 -p hello", "claude"), true);
  assert.equal(runs("/Users/Ann Lee/.local/bin/claude --resume abc", "claude"), true);
  assert.equal(runs("vim /work/claude/notes.md", "claude"), false);
});
