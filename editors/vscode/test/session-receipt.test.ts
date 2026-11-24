// A receipt: what a card says about the work after it happened (src/sessions/receipt.ts). Every flag has its test.
import assert from "node:assert/strict";
import { test } from "node:test";
import type { Call } from "../src/sessions/model.ts";
import { testsWords as testsLine } from "../src/graph/words.ts";
import { commands, isTest, receipt, shared } from "../src/sessions/receipt.ts";

const CWD = "/work/app";
let n = 0;
const call = (name: string, input: Record<string, unknown>, more: Partial<Call> = {}): Call =>
  ({ id: `c${++n}`, name, input, at: `2026-11-24T10:00:${String(n % 60).padStart(2, "0")}.000Z`, side: "", done: true, error: false, out: "", err: "", interrupted: false, exit: null, endAt: "", more: {}, ...more });
const sh = (command: string, exit: number | null = 0, out = "", more: Partial<Call> = {}) => call("Bash", { command }, { exit, error: exit !== 0, out, ...more });
const edit = (file: string, more: Record<string, unknown> = {}) => call("Edit", { file_path: file.startsWith("/") || file.startsWith("..") ? file : `${CWD}/${file}` }, { more });

test("a command line is read as its simple commands and what joins them, quotes and redirections left whole", () => {
  assert.deepEqual(commands("cd pkg && pytest -q 2>&1 | tail -5; echo done"), [
    { text: "cd pkg", then: "&&" }, { text: "pytest -q 2>&1", then: "|" }, { text: "tail -5", then: ";" }, { text: "echo done", then: "" }]);
  assert.deepEqual(commands(`git commit -m "fix; and && more | pipes" || true`), [{ text: `git commit -m "fix; and && more | pipes"`, then: "||" }, { text: "true", then: "" }]);
  assert.deepEqual(commands("npm test &> out.log &\nsleep 1"), [{ text: "npm test &> out.log", then: "&" }, { text: "sleep 1", then: "" }]);
  assert.deepEqual(commands("  "), []);
});

test("the files it changed: created, edited, deleted, each once, from the session's folder", () => {
  const r = receipt([call("Write", { file_path: `${CWD}/src/new.py` }, { more: { type: "create" } }), edit("src/new.py"), edit("src/old.py"), edit("src/old.py"),
                     edit("src/gone.py", { type: "delete" }), call("Edit", { file_path: `${CWD}/refused.py` }, { error: true }), call("Read", { file_path: `${CWD}/read.py` })], CWD);
  assert.deepEqual(r.changed, [{ file: "src/new.py", how: "created", outside: false }, { file: "src/old.py", how: "edited", outside: false }, { file: "src/gone.py", how: "deleted", outside: false }]);
  assert.equal(r.tests, "none");
  assert.equal(testsLine(r), "ran no tests");
});

test("three honest states for tests, and a fourth it does not hide; the last run of each tool decides", () => {
  // passed, by its own exit code: the tool is the line's last command and nothing is piped after it
  let r = receipt([sh("cd pkg && python3 -m unittest -v", 0)], CWD);
  assert.deepEqual(r.checks.map((c) => [c.tool, c.verdict, c.why]), [["unittest", "passed", "it exited 0"]]);
  assert.equal(testsLine(r), "unittest passed");
  // failed, by its output's own summary, whatever the pipe's exit code says
  r = receipt([sh("uv run pytest -q | tail -3", 0, "1 failed, 12 passed in 0.31s")], CWD);
  assert.deepEqual(r.checks.map((c) => [c.tool, c.verdict, c.why]), [["pytest", "failed", "its output says 1 failed"]]);
  assert.equal(r.tests, "failed");
  // ran, and the result was not seen: the exit code is tail's, and the output has no summary. No tick for that
  r = receipt([sh("pytest -q | tail -1", 0, "....")], CWD);
  assert.deepEqual([r.tests, r.checks[0]!.verdict, r.checks[0]!.why], ["unseen", "unseen", "its output has no summary, and the exit code is a later command's"]);
  assert.equal(testsLine(r), "pytest ran, result not seen");
  // a line that failed before the tests could run says nothing of them
  r = receipt([sh("npm ci && npx vitest run", 1, "npm ERR! code ENOTFOUND")], CWD);
  assert.deepEqual([r.checks[0]!.tool, r.checks[0]!.verdict], ["vitest", "unseen"]);
  // the last run of each decides: red, then green
  r = receipt([sh("pytest", 1, "2 failed, 3 passed"), edit("src/a.py"), sh("pytest", 0, "5 passed in 0.2s")], CWD);
  assert.deepEqual([r.tests, r.checks.length, r.checks[0]!.why], ["passed", 1, "its output says 5 passed"]);
  // green, then red: failed
  r = receipt([sh("go test ./...", 0, "ok  \tpkg\t0.01s"), sh("go test ./...", 1, "--- FAIL: TestX (0.00s)\nFAIL")], CWD);
  assert.equal(r.tests, "failed");
  // a command that was refused did not run: it is not a test that failed
  r = receipt([sh("pytest && git stash", null, "This command requires approval", { error: true })], CWD);
  assert.deepEqual([r.tests, r.checks.length], ["none", 0]);
  // an interrupted run was not seen
  r = receipt([sh("cargo test", null, "", { interrupted: true, error: false })], CWD);
  assert.equal(r.tests, "unseen");
});

test("every tool the receipt knows is found in the lines people type", () => {
  const lines: [string, string][] = [
    ["pytest tests/ -k top", "pytest"], ["python -m pytest", "pytest"], ["uv run pytest -q -n auto", "pytest"], ["python3 -m unittest tests.test_top", "unittest"],
    ["npm test", "npm test"], ["npm run test -- --watch=false", "npm test"], ["pnpm test", "pnpm test"], ["yarn test", "yarn test"], ["npx vitest run", "vitest"],
    ["npx jest src/", "jest"], ["go test ./...", "go test"], ["cargo test --all", "cargo test"], ["make test", "make test"], ["make -j4 test", "make test"],
    ["node --experimental-strip-types --test test/a.test.ts", "node --test"], ["FOO=1 time uv run ruff check", "ruff"], ["npx eslint .", "eslint"], ["npx tsc --noEmit -p .", "tsc"], ["uv run mypy src", "mypy"],
  ];
  for (const [line, tool] of lines) assert.deepEqual(receipt([sh(line, 0)], CWD).checks.map((c) => c.tool), [tool], line);
  for (const line of ["cat pytest.ini", "echo 'run npm test'", "git commit -m 'make test pass'", "npm run test:watch", "pip install pytest", "grep -r eslint ."]) {
    assert.deepEqual(receipt([sh(line, 0)], CWD).checks, [], line); // a tool named, not run
  }
  // checks are listed, and are not the tests' verdict
  const r = receipt([sh("uv run ruff check", 1, "Found 2 errors."), sh("npx tsc --noEmit", 0)], CWD);
  assert.deepEqual(r.checks.map((c) => [c.tool, c.kind, c.verdict]), [["ruff", "check", "failed"], ["tsc", "check", "passed"]]);
  assert.equal(r.tests, "none");
});

test("a push and a pull request are flagged, each with the line that shows it", () => {
  const r = receipt([sh("git add -A && git commit -m wip && git push -u origin fix/count"), sh("gh pr create --draft --fill"), sh("git log --oneline | head")], CWD);
  assert.deepEqual(r.flags.map((f) => [f.kind, f.line, f.guess]), [["push", "git push -u origin fix/count", false], ["pull request", "gh pr create --draft --fill", false]]);
  assert.deepEqual(receipt([sh("git push", null, "requires approval", { error: true })], CWD).flags, []); // refused: it did not push
  assert.deepEqual(receipt([sh("echo git push")], CWD).flags, []);
});

test("a delete is flagged: a command's, and a tool's", () => {
  const r = receipt([sh("rm -rf build/ dist/"), sh("git rm old.py"), sh("git clean -fd"), sh("find . -name '*.pyc' -delete"), edit("src/gone.py", { type: "delete" })], CWD);
  assert.deepEqual(r.flags.map((f) => [f.kind, f.line]), [["delete", "rm -rf build/ dist/"], ["delete", "git rm old.py"], ["delete", "git clean -fd"], ["delete", "find . -name '*.pyc' -delete"], ["delete", "src/gone.py"]]);
});

test("a force flag and a hard reset are flagged", () => {
  const r = receipt([sh("git push --force-with-lease origin main"), sh("git commit --no-verify -m x"), sh("git reset --hard HEAD~2"), sh("git checkout -f main"), sh("rm -f a.txt")], CWD);
  assert.deepEqual(r.flags.map((f) => [f.kind, f.line]), [
    ["push", "git push --force-with-lease origin main"], ["force", "git push --force-with-lease origin main"], ["force", "git commit --no-verify -m x"],
    ["hard reset", "git reset --hard HEAD~2"], ["force", "git checkout -f main"], ["delete", "rm -f a.txt"]]); // rm -f is a delete, not a forced git command
  assert.equal(r.flags.find((f) => f.line.includes("--no-verify"))!.note, "it skipped the repository's hooks");
});

test("a test file edited after its test failed is flagged as a fact; that it is the failing test's file is a guess unless the run names it", () => {
  let r = receipt([sh("pytest -q", 1, "FAILED tests/test_top.py::test_ten - assert 9 == 10\n1 failed"), edit("tests/test_top.py"), sh("pytest -q", 0, "1 passed")], CWD);
  assert.deepEqual(r.flags, [{ kind: "test edited after it failed", line: "tests/test_top.py", guess: false, note: "edited after pytest failed; the failing run's output names this file" }]);
  r = receipt([sh("npm test", 1, "1 failed"), edit("src/widget.spec.ts")], CWD);
  assert.deepEqual(r.flags.map((f) => [f.kind, f.guess, f.note]), [["test edited after it failed", true, "edited after npm test failed; the run's output does not name this file"]]);
  // the code edited after a failure, or a test edited with nothing red before it, is the work itself
  assert.deepEqual(receipt([sh("pytest", 1, "1 failed"), edit("src/top.py")], CWD).flags, []);
  assert.deepEqual(receipt([edit("tests/test_top.py"), sh("pytest", 0, "1 passed")], CWD).flags, []);
  assert.deepEqual(receipt([sh("pytest", 1, "1 failed"), sh("pytest", 0, "1 passed"), edit("tests/test_top.py")], CWD).flags, []); // green again before the edit
  assert.ok(isTest("pkg/widget_test.go") && isTest("src/__tests__/a.ts") && isTest("conftest.py") && !isTest("src/contest.py") && !isTest("latest/run.py"));
});

test("a write outside the folder is flagged, and a file two sessions wrote is said on each", () => {
  const r = receipt([edit("/work/other/config.yml"), edit("src/a.py"), call("Write", { file_path: "/home/you/.zshrc" }, { more: { type: "create" } })], CWD);
  assert.deepEqual(r.flags.map((f) => [f.kind, f.line]), [["outside the folder", "/work/other/config.yml"], ["outside the folder", "/home/you/.zshrc"]]);
  assert.deepEqual(r.changed.map((c) => [c.file, c.outside]), [["/work/other/config.yml", true], ["src/a.py", false], ["/home/you/.zshrc", true]]);
  assert.deepEqual(shared(r, [{ title: "the other session", files: ["src/a.py", "src/b.py"] }, { title: "a third", files: ["README.md"] }]),
                   [{ kind: "written by two sessions", line: "src/a.py", note: "also written by “the other session”", guess: false }]);
  assert.deepEqual(shared(r, []), []);
});
