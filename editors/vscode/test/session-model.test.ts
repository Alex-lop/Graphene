// A session as it stands (src/sessions/model.ts), found by its folder (find.ts) and followed as it grows
// (follow.ts), on hand-made files (test/fixtures/sessions).
import assert from "node:assert/strict";
import { appendFileSync, copyFileSync, cpSync, mkdirSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import * as path from "node:path";
import { test } from "node:test";
import { cwdOf, encoded, findAll, findCodex, glance, GLANCE, inside, NEWEST, procs, Scan } from "../src/sessions/find.ts";
import { Follow } from "../src/sessions/follow.ts";
import { empty, fold, sidesOf, subOver } from "../src/sessions/model.ts";
import { FIX, read, ROLLOUT, scratch } from "./sessions.ts";

test("Claude Code: a request is the person's own words, not what Claude Code wrote into their turn", async () => {
  const m = await read("requests.jsonl");
  assert.equal(m.id, "requests"); // the file's name is the session's id: it is what `claude --resume` takes
  assert.equal(m.cwd, "/work/app");
  assert.equal(m.branch, "main");
  assert.equal(m.title, "Fix the word counter"); // the ai-title line
  assert.equal(m.model, "claude-haiku-5-5");
  // three requests: the ask, the slash command as typed, the follow-up; no caveat, no command output, no task notice
  assert.deepEqual(m.turns.map((t) => t.text.split("\n")[0]), ["Fix the word counter: two spaces in a row count as a word.", "/review the counter", "Now make it count hyphenated words as one."]);
  const [first, second, third] = m.turns;
  assert.deepEqual(first!.calls.map((c) => [c.name, c.done, c.error]), [["Read", true, false], ["Edit", true, false], ["Write", true, false], ["Bash", true, false]]);
  assert.ok(first!.ended && !first!.stopped);
  assert.equal(first!.calls.at(-1)!.exit, 0);
  assert.deepEqual([second!.calls[0]!.error, second!.calls[0]!.exit], [true, 128]); // a failed command says its code
  assert.ok(second!.stopped, "[Request interrupted by user] ends the request it interrupts");
  // the last request: its command is out, and the truncated last line (its result, half written) is not read
  assert.deepEqual(third!.calls.map((c) => [c.name, c.done]), [["Bash", false]]);
  assert.ok(!third!.ended);
});

test("the agent's own task list belongs to the request it was written in, and a call to the task in progress", async () => {
  const m = await read("tasks.jsonl");
  assert.deepEqual(m.turns[0]!.todos.map((t) => [t.id, t.title, t.state, t.calls.map((c) => c.name)]), [
    ["1", "Write the CSV writer", "completed", ["Write", "TaskUpdate"]], // the call that ends it is its own
    ["2", "Test an empty table", "in_progress", ["Bash"]],
    ["3", "Say it in the README", "pending", []],
  ]);
  assert.equal(m.doing?.id, "2");
});

test("a subagent's thread is found by its call's result, by its own file's note, or by its first line", async () => {
  const m = await read("subagents.jsonl");
  assert.deepEqual(m.subs.map((s) => [s.kind, s.title, s.turn, sidesOf(m, s).map((x) => x.id), subOver(m, s)]), [
    ["subagent", "Review the parser", 1, ["aaa111"], true], // back: its call answered
    ["subagent", "Review the printer", 1, ["bbb222"], false], // launched behind the request, its thread not at its end
    ["workflow", "release-check", 1, ["ccc333"], true], // every agent of its run ended
  ]);
  assert.equal(m.sides.get("aaa111")!.call, "a1"); // its note beside it names the call
  // with no note and no result yet, its first line is its call's prompt word for word
  const n = empty("claude", "x", "s1");
  fold(n, { k: "ask", at: "2026-11-24T10:00:00.000Z", text: "go", side: "" });
  fold(n, { k: "tool", at: "2026-11-24T10:00:01.000Z", id: "a", name: "Agent", input: { description: "Count the lines", prompt: "wc -l *.py" }, side: "" });
  fold(n, { k: "ask", at: "2026-11-24T10:00:02.000Z", text: "wc -l *.py", side: "zzz" });
  fold(n, { k: "tool", at: "2026-11-24T10:00:03.000Z", id: "z1", name: "Bash", input: { command: "wc -l *.py" }, side: "zzz" });
  assert.deepEqual(sidesOf(n, n.subs[0]!).map((x) => [x.id, x.calls.length]), [["zzz", 1]]);
  assert.equal(n.turns[0]!.calls.length, 1); // a subagent's call is its thread's, not the request's
});

test("Codex: a rollout reads into the same model, its commands by their exit codes and a patch by its files", async () => {
  const m = await read(ROLLOUT, "codex");
  assert.equal(m.id, "01a20f92-0000-7000-8000-000000000001");
  assert.deepEqual([m.cwd, m.branch, m.head.slice(0, 7)], ["/work/app", "main", "25af821"]);
  assert.equal(m.turns.length, 1); // the environment Codex writes into the person's turn is not a request
  const calls = m.turns[0]!.calls;
  assert.deepEqual(calls.map((c) => [c.name, c.input.command ?? c.input.file_path, c.exit, c.error]), [
    ["Bash", "cat slug.py", 0, false], ["Edit", "/work/app/slug.py", null, false], ["Write", "/work/app/test_punctuation.py", null, false],
    ["Bash", "python3 -m unittest", 1, true], ["Agent", undefined, null, false], ["Bash", "python3 -m unittest", 0, false],
  ]);
});

test("a session is a folder's by the cwd its lines say, in the folder or inside it", async () => {
  assert.equal(encoded("/Users/me/My Repo.v2"), "-Users-me-My-Repo-v2");
  assert.equal(cwdOf('{"type":"x"}\n{"cwd":"/a/\\"b\\"/c","type":"user"}'), '/a/"b"/c');
  assert.ok(inside("/a/b", "/a/b") && inside("/a/b/c", "/a/b"));
  assert.ok(!inside("/a/bc", "/a/b") && !inside("/a", "/a/b") && !inside("", "/a/b"));
  const home = scratch(), folder = path.join(home, "work", "app");
  try {
    mkdirSync(folder, { recursive: true });
    const here = (file: string, cwd: string) => writeFileSync(file, readFileSync(path.join(FIX, "requests.jsonl"), "utf8").replaceAll('"/work/app', `"${cwd}`));
    const projects = path.join(home, "claude", "projects");
    mkdirSync(path.join(projects, encoded(folder)), { recursive: true });
    here(path.join(projects, encoded(folder), "aaaa.jsonl"), folder);
    here(path.join(projects, encoded(folder), "bbbb.jsonl"), `${folder}-other`); // another folder under the same name: its lines say so
    here(path.join(projects, encoded(folder), "agent-old1.jsonl"), folder); // an older version's subagent transcript: not a session
    mkdirSync(path.join(projects, `${encoded(folder)}-sub`), { recursive: true });
    here(path.join(projects, `${encoded(folder)}-sub`, "cccc.jsonl"), path.join(folder, "sub")); // started inside the folder
    const day = path.join(home, "codex", "sessions", "2026", "11", "24");
    mkdirSync(day, { recursive: true });
    writeFileSync(path.join(day, ROLLOUT), readFileSync(path.join(FIX, ROLLOUT), "utf8").replaceAll('"/work/app', `"${folder}`));
    copyFileSync(path.join(FIX, ROLLOUT), path.join(day, "rollout-2026-11-24T11-00-00-elsewhere.jsonl")); // another folder's
    const all = await findAll(folder, { claude: path.join(home, "claude"), codex: path.join(home, "codex") });
    // ponytail: findCodex looks back 30 days from now; the fixture's day is asked for by its own date below
    const codex = findCodex(folder, path.join(home, "codex"), 2, Date.parse("2026-11-25T00:00:00Z"));
    assert.deepEqual(all.filter((f) => f.agent === "claude").map((f) => f.id).sort(), ["aaaa", "cccc"]);
    assert.deepEqual((await codex).map((f) => [f.agent, f.id]), [["codex", "01a20f92-0000-7000-8000-000000000001"]]);
    assert.deepEqual(await findAll(path.join(home, "nowhere"), { claude: path.join(home, "claude"), codex: path.join(home, "codex") }), []);
    assert.deepEqual(await findAll(folder, { claude: path.join(home, "no-claude"), codex: path.join(home, "no-codex") }), []); // neither agent installed
    // a running Claude Code's record of itself: only while its process is there
    mkdirSync(path.join(home, "claude", "sessions"));
    writeFileSync(path.join(home, "claude", "sessions", "41.json"), JSON.stringify({ pid: 41, sessionId: "aaaa", cwd: folder, status: "busy" }));
    writeFileSync(path.join(home, "claude", "sessions", "42.json"), JSON.stringify({ pid: 42, sessionId: "gone", cwd: folder, status: "idle" }));
    writeFileSync(path.join(home, "claude", "sessions", "43.json"), "{ half");
    const live = await procs(path.join(home, "claude"), (pid) => pid === 41);
    assert.deepEqual([...live.values()], [{ pid: 41, session: "aaaa", cwd: folder, status: "busy" }]);
  } finally { rmSync(home, { recursive: true }); }
});

test("a session is followed as it grows, its subagents' files beside it, and a file that goes away says so in one line", async () => {
  const dir = scratch();
  try {
    cpSync(path.join(FIX, "subagents"), path.join(dir, "s"), { recursive: true });
    const file = path.join(dir, "s.jsonl"), whole = readFileSync(path.join(FIX, "subagents.jsonl"), "utf8").split("\n").filter(Boolean);
    writeFileSync(file, `${whole.slice(0, 3).join("\n")}\n`);
    const f = new Follow({ agent: "claude", file, id: "s", cwd: "/work/app", mtime: 0, size: 1 });
    assert.equal(await f.read(), true);
    assert.deepEqual(f.model.subs.map((s) => s.title), ["Review the parser", "Review the printer"]);
    assert.equal(await f.read(), false); // nothing new: the page is not drawn again
    appendFileSync(file, `${whole.slice(3).join("\n")}\n`);
    assert.equal(await f.read(), true);
    assert.equal(f.model.turns.length, 2);
    assert.equal(f.model.subs.length, 3);
    // rewritten shorter (a compaction, a restore): read from its start, and nothing is there twice
    writeFileSync(file, `${whole.slice(0, 5).join("\n")}\n`);
    assert.equal(await f.read(), true);
    assert.deepEqual([f.model.turns.length, f.model.subs.length, f.model.sides.size], [1, 2, 3]);
    appendFileSync(file, `${whole.slice(5).join("\n")}\n`);
    await f.read();
    assert.deepEqual([f.model.turns.length, f.model.subs.length, f.model.sides.get("aaa111")!.calls.length], [2, 3, 1]);
    rmSync(file);
    assert.equal(await f.read(), true);
    assert.match(f.model.error, /^cannot read .*s\.jsonl: ENOENT$/);
    assert.equal(f.model.turns.length, 2); // and what was read of it is still there
  } finally { rmSync(dir, { recursive: true }); }
});

test("the folder is looked at cheaply: a full listing now and then, a few stats between, and at once when a session is added", async () => {
  const home = scratch(), folder = path.join(home, "work", "app");
  try {
    const dir = path.join(home, "claude", "projects", encoded(folder));
    mkdirSync(dir, { recursive: true });
    mkdirSync(folder, { recursive: true });
    const line = (text: string) => `${JSON.stringify({ type: "user", cwd: folder, sessionId: "s", timestamp: "2026-11-24T10:00:00.000Z", message: { content: text } })}\n`;
    for (let i = 0; i < NEWEST + 5; i++) writeFileSync(path.join(dir, `s${String(i).padStart(2, "0")}.jsonl`), line("go"));
    const scan = new Scan(folder, { claude: path.join(home, "claude"), codex: path.join(home, "codex") });
    assert.equal((await scan.look(1_000_000)).length, NEWEST + 5);
    const newest = scan.found[0]!.file, oldest = scan.found.at(-1)!.file;
    appendFileSync(newest, line("more"));
    appendFileSync(oldest, line("more"));
    const quick = await scan.look(1_002_000); // two seconds on: only the newest few are asked their size
    assert.ok(quick.find((f) => f.file === newest)!.size > line("go").length);
    assert.equal(quick.find((f) => f.file === oldest)!.size, line("go").length); // not asked, until the next full listing
    writeFileSync(path.join(dir, "new.jsonl"), line("a new session")); // a session begins: its directory says something was added
    assert.ok((await scan.look(1_004_000)).some((f) => f.id === "new"));
    assert.ok((await scan.look(1_004_000 + 31_000)).find((f) => f.file === oldest)!.size > line("go").length); // the full listing catches up
    // a folder whose directory holds no session of its own yet (another folder's, under the same name) is watched all the same
    const bare = path.join(home, "work", "bare"), its = path.join(home, "claude", "projects", encoded(bare));
    mkdirSync(its, { recursive: true });
    mkdirSync(bare, { recursive: true });
    writeFileSync(path.join(its, "other.jsonl"), line("go")); // its lines say another folder
    const empty = new Scan(bare, { claude: path.join(home, "claude"), codex: path.join(home, "codex") });
    assert.deepEqual(await empty.look(2_000_000), []);
    writeFileSync(path.join(its, "first.jsonl"), line("go").replace(JSON.stringify(folder), JSON.stringify(bare)));
    assert.deepEqual((await empty.look(2_002_000)).map((f) => f.id), ["first"], "found at the next look, not at the next full listing");
  } finally { rmSync(home, { recursive: true }); }
});

test("a session at a glance: its start and its end, and never the megabytes between", async () => {
  const dir = scratch(), file = path.join(dir, "big.jsonl");
  try {
    const line = (n: number) => `${JSON.stringify({ n, pad: "x".repeat(2000) })}\n`;
    let text = "";
    for (let n = 0; text.length < 3 * (GLANCE.head + GLANCE.tail); n++) text += line(n);
    writeFileSync(file, text);
    const got = (await glance({ agent: "claude", file, id: "big", cwd: "/w", mtime: 0, size: text.length })).filter(Boolean).map((l) => JSON.parse(l).n as number);
    assert.equal(got[0], 0);
    assert.equal(got.at(-1), text.split("\n").length - 2); // the last whole line
    assert.ok(got.length < (GLANCE.head + GLANCE.tail) / 2000, "only the two ends are read"); // and every line read is whole: JSON.parse did not throw
    assert.deepEqual(await glance({ agent: "claude", file: path.join(dir, "none"), id: "x", cwd: "/w", mtime: 0, size: 9 }), []);
  } finally { rmSync(dir, { recursive: true }); }
});
