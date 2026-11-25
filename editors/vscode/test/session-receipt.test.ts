// A receipt: what a card says about the work after it happened (src/sessions/receipt.ts). Every flag has its test.
import assert from "node:assert/strict";
import { test } from "node:test";
import type { Call } from "../src/sessions/model.ts";
import { testsWords as testsLine } from "../src/graph/words.ts";
import { commands, isTest, receipt, shared } from "../src/sessions/receipt.ts";

const CWD = "/work/app";
let n = 0;
const call = (name: string, input: Record<string, unknown>, more: Partial<Call> = {}): Call =>
  ({ id: `c${++n}`, name, input, at: new Date(Date.UTC(2026, 10, 24, 10) + n * 1000).toISOString(), side: "", done: true, error: false, out: "", err: "", interrupted: false, exit: null, endAt: "", more: {}, ...more });
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
  assert.deepEqual(r.checks.map((c) => [c.tool, c.verdict, c.why]), [["pytest", "failed", "its output says 1 failed, 12 passed in 0.31s"]]);
  assert.equal(r.tests, "failed");
  // ran, and the result was not seen: the exit code is tail's, and the output has no summary. No tick for that
  r = receipt([sh("pytest -q | tail -1", 0, "....")], CWD);
  assert.deepEqual([r.tests, r.checks[0]!.verdict, r.checks[0]!.why], ["unseen", "unseen", "its output has no summary, and the exit code is another command's"]);
  assert.equal(testsLine(r), "pytest ran, result not seen");
  // a line that failed before the tests could run says nothing of them
  r = receipt([sh("npm ci && npx vitest run", 1, "npm ERR! code ENOTFOUND")], CWD);
  assert.deepEqual([r.checks[0]!.tool, r.checks[0]!.verdict], ["vitest", "unseen"]);
  // the last run of each decides: red, then green
  r = receipt([sh("pytest", 1, "2 failed, 3 passed"), edit("src/a.py"), sh("pytest", 0, "5 passed in 0.2s")], CWD);
  assert.deepEqual([r.tests, r.checks.length, r.checks[0]!.why], ["passed", 1, "its output says 5 passed in 0.2s"]);
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
  for (const line of ["cat pytest.ini", "echo 'run npm test'", "git commit -m 'make test pass'", "pip install pytest", "grep -r eslint .",
                      "make test-fixtures", "node seed.js --test-db", "npx jest --clearCache", "npm test -- --listTests", "cargo nextest list"]) {
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
  assert.equal(r.flags.find((f) => f.line.includes("--no-verify"))!.note, "it ran git with --no-verify (it skips the repository's hooks)");
  assert.equal(r.flags.find((f) => f.kind === "hard reset")!.note, "it ran git reset --hard"); // what was run, never what it did: on a clean tree it discards nothing
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
  assert.deepEqual(shared(r, CWD, [{ title: "the other session", cwd: CWD, files: ["src/a.py", "src/b.py"] }, { title: "a third", cwd: CWD, files: ["README.md"] }]),
                   [{ kind: "written by two sessions", line: "src/a.py", note: "also written by “the other session”", guess: false }]);
  assert.deepEqual(shared(r, CWD, []), []);
  // the same file is the same place on disk: another folder's src/a.py is another file, and a session one folder up names this one its own way
  assert.deepEqual(shared(r, CWD, [{ title: "another project", cwd: "/work/other-project", files: ["src/a.py"] }]), []);
  assert.deepEqual(shared(r, CWD, [{ title: "from the folder above", cwd: "/work", files: ["app/src/a.py"] }]).map((f) => f.line), ["src/a.py"]);
  // a name that begins with two dots is a name, not a way out of the folder
  assert.deepEqual(receipt([edit("..env"), edit("../sibling/x.py")], CWD).changed.map((c) => [c.file, c.outside]), [["..env", false], ["../sibling/x.py", true]]);
});

// What a reader of the receipts found (the review of piece 4): each a tick, a failure or a flag that was not earned.
const one = (c: Call) => { const r = receipt([c], CWD); return [r.tests, r.checks[0]?.verdict ?? "", r.checks[0]?.why ?? ""]; };

test("a tick is never given against the tool's own exit code, whatever its output says", () => {
  // a long output with its failures in the middle, which the reader cut out: the end says ok, the exit code says not
  assert.deepEqual(one(sh("go test -v ./...", 1, "=== RUN TestA\n…\nok  \tpkg/b\t0.01s")), ["failed", "failed", "it exited 1, though its output says ok pkg/b 0.01s"]);
  assert.deepEqual(one(sh("python -m unittest", 1, "Ran 3 tests in 0.001s\n\nOK\nFatal Python error: Segmentation fault")), ["failed", "failed", "it exited 1, though its output says Ran 3 tests in 0.001s, OK"]);
  assert.deepEqual(one(sh("pytest -q", 1, "INFO 3 passed checks\nINTERNALERROR> boom")), ["failed", "failed", "it exited 1"]); // "3 passed" in a log line is not pytest's summary
  // the same long output through a pipe: the exit code is not go's, and no last line sums a go run up, so it was not seen
  assert.deepEqual(one(sh("go test -v ./... | tail -40", 0, "=== RUN TestA\n…\nok  \tpkg/b\t0.01s"))[1], "unseen");
  // words that look like a verdict and are not the tool's summary decide nothing
  assert.deepEqual(one(sh("pytest", 0, "plugin: 0 failed lookups\n5 passed in 0.10s")), ["passed", "passed", "its output says 5 passed in 0.10s"]);
  assert.deepEqual(one(sh("npm test", 0, " ✓ shows 2 failed jobs\n Tests  12 passed (12)"))[0], "passed");
  assert.deepEqual(one(sh("npx jest", 1, "Tests:       1 failed, 2 passed, 3 total")), ["failed", "failed", "its output says Tests:       1 failed, 2 passed, 3 total"]);
});

test("a run in the background was not seen: its result is not in the call", () => {
  const why = "it ran in the background: its result is not in this call";
  assert.deepEqual(one(call("Bash", { command: "uv run pytest -q", run_in_background: true }, { exit: 0, out: "Command running in background with ID: b7x2" })), ["unseen", "unseen", why]);
  assert.deepEqual(one(sh("pytest -q > /tmp/out.log 2>&1 &", 0)), ["unseen", "unseen", why]);
  assert.deepEqual(one(sh("nohup pytest > log 2>&1 &", 0)), ["unseen", "unseen", why]);
});

test("a run that ran no test is not a test that passed, nor one that failed", () => {
  // by its arguments it lists, compiles or prints help: nothing is recorded, and the receipt says ran no tests
  for (const line of ["pytest --collect-only -q", "pytest --co", "pytest --help", "pytest --version", "cargo test --no-run", "go test -c ./pkg", "make -n test", "npx jest --listTests"]) {
    assert.deepEqual([receipt([sh(line, 0, "1 test collected")], CWD).tests, receipt([sh(line, 0)], CWD).checks.length], ["none", 0], line);
  }
  // by its output it found none: said in the pane as a run that ran no test, and the card says ran no tests
  const none: [string, number, string][] = [
    ['node --test "nomatch/*.test.ts"', 0, "ℹ tests 0\nℹ pass 0\nℹ fail 0"], ["go test ./...", 0, "?   \tpkg\t[no test files]"], ["pytest", 0, "3 skipped in 0.01s"],
    ["python -m unittest", 0, "Ran 0 tests in 0.000s\n\nOK"], ["python -m unittest", 5, "Ran 0 tests in 0.000s\n\nNO TESTS RAN"], ["npm test", 0, "Tests:       0 total"],
    ["pytest -k nothing", 5, "no tests ran in 0.00s"], ["cargo test", 0, "test result: ok. 0 passed; 0 failed; 0 ignored"],
  ];
  for (const [line, exit, out] of none) {
    const r = receipt([sh(line, exit, out)], CWD);
    assert.deepEqual([r.tests, r.checks.map((c) => c.verdict), testsLine(r)], ["none", ["none"], "ran no tests"], line);
  }
  // a line that failed before the tool could run says nothing of the tool
  assert.deepEqual(one(sh("cd nope && pytest", 1, "cd: no such file or directory: nope")), ["unseen", "unseen", "the line exited 1, and its output does not say this ran"]);
});

test("the last run of each command decides, in the order the runs were made: one command's pass does not clear another's failure", () => {
  // the whole suite failed, then a narrower run passed: the suite was never seen to pass
  let r = receipt([sh("pytest", 1, "3 failed, 7 passed in 0.4s"), sh("pytest -k test_one", 0, "1 passed, 9 deselected in 0.1s")], CWD);
  assert.deepEqual([r.tests, r.checks.map((c) => [c.command, c.verdict]), testsLine(r)], ["failed", [["pytest", "failed"], ["pytest -k test_one", "passed"]], "pytest failed"]);
  // the same command, said more quietly or sent to a file, is the same command: its last run decides
  r = receipt([sh("pytest", 1, "3 failed, 7 passed in 0.4s"), sh("uv run pytest -q 2>&1 | tail -3", 0, "10 passed in 0.4s")], CWD);
  assert.deepEqual([r.tests, r.checks.length], ["passed", 1]);
  // two runs on one line, each to its own file: the first was not seen, and the second's exit code does not speak for it
  r = receipt([sh("pytest tests/a > a.log; pytest tests/b > b.log", 0)], CWD);
  assert.deepEqual([r.tests, r.checks.map((c) => c.verdict)], ["unseen", ["unseen", "passed"]]);
  // a subagent's calls are read after its session's: by their time, its pass at 10:05 does not follow the failure at 10:06
  const late = sh("pytest", 1, "1 failed in 0.1s", { at: "2026-11-24T10:06:00.000Z" }), early = sh("pytest", 0, "1 passed in 0.1s", { at: "2026-11-24T10:05:00.000Z" });
  assert.equal(receipt([late, early], CWD).tests, "failed");
});

test("a flag says what was run, and is a guess where the line does not show that it ran, or worked", () => {
  const flags = (c: Call) => receipt([c], CWD).flags.map((f) => [f.kind, f.guess, f.note]);
  assert.deepEqual(flags(sh("git push")), [["push", false, "it ran git push"]]);
  assert.deepEqual(flags(sh("git push", 1, "! [rejected] main -> main")), [["push", false, "it ran git push, which exited 1"]]);
  // the tests failed, so the push after `&&` never ran: the receipt does not say it did
  assert.deepEqual(flags(sh("pytest && git push", 1, "1 failed in 0.1s")), [["push", true, "git push is on a line that exited 1: whether it ran, or worked, is not seen"]]);
  assert.deepEqual(flags(sh("make build || git push", 0)), [["push", true, "git push is on a line that exited 0: whether it ran, or worked, is not seen"]]);
  assert.deepEqual(flags(sh("rm build/x", 1, "rm: build/x: No such file or directory")), [["delete", false, "it ran rm, which exited 1"]]);
  // a rehearsal changes nothing, and a flag named inside a message is not a flag given
  for (const line of ["git push --dry-run", "git clean -n", "git clean --dry-run -d", "git commit -m 'support the -f flag'", `git commit -m "document --no-verify"`]) assert.deepEqual(flags(sh(line)), [], line);
  // found however it is carried
  const kinds = (line: string) => receipt([sh(line)], CWD).flags.map((f) => f.kind);
  for (const line of ["git -C ../other push", "git -c user.name=x push origin main", "sh -c 'git push'", "/usr/bin/git push"]) assert.deepEqual(kinds(line), ["push"], line);
  assert.deepEqual(kinds('bash -lc "git push --force"'), ["push", "force"]);
  assert.deepEqual(kinds("gh api repos/o/r/pulls -f title=x -f head=y"), ["pull request"]);
  assert.deepEqual(kinds("gh api repos/o/r/pulls"), []); // read, not written
  assert.deepEqual(kinds("git -C sub reset --hard"), ["hard reset"]);
  for (const line of ["/bin/rm -rf dist", "find . -name '*.orig' -exec rm {} +", "ls | xargs rm", "bash -c 'rm -rf dist'", "git branch -D old", "git stash drop"]) assert.deepEqual(kinds(line), ["delete"], line);
});

test("tests are found however they are carried, and a carried run's exit code is believed only where it is its own", () => {
  const found = (line: string, exit = 0, out = "") => receipt([sh(line, exit, out)], CWD).checks.map((c) => [c.tool, c.verdict]);
  assert.deepEqual(found("timeout 60 pytest"), [["pytest", "passed"]]); // timeout hands on its command's exit code, or its own, which is not 0
  assert.deepEqual(found('bash -c "pytest"', 0, "2 passed in 0.1s"), [["pytest", "passed"]]);
  assert.deepEqual(found('bash -c "pytest"'), [["pytest", "unseen"]]); // the exit code is the shell's
  assert.deepEqual(found("! pytest"), [["pytest", "unseen"]]);
  assert.deepEqual(found("if pytest; then echo ok; fi"), [["pytest", "unseen"]]);
  assert.deepEqual(found("for d in a b; do pytest $d; done", 0, "2 passed in 0.1s"), [["pytest", "passed"]]);
  assert.deepEqual(found("ls tests | xargs pytest", 1, "1 failed in 0.1s"), [["pytest", "failed"]]);
});

test("a test file edited after a failure is the failing test's own only where the run names it by its path, and only that tool's pass clears it", () => {
  const out = "FAILED tests/test_data.py::test_load - KeyError\n1 failed in 0.1s";
  const flags = (...cs: Call[]) => receipt(cs, CWD).flags.map((f) => [f.line, f.guess]);
  assert.deepEqual(flags(sh("pytest", 1, out), edit("tests/test_data.py")), [["tests/test_data.py", false]]);
  assert.deepEqual(flags(sh("pytest", 1, out), edit("tests/data.py")), [["tests/data.py", true]]); // a name inside the failing file's name
  assert.deepEqual(flags(sh("pytest", 1, out), edit("pkg2/tests/test_data.py")), [["pkg2/tests/test_data.py", true]]); // the same name in another folder
  assert.deepEqual(flags(sh("pytest", 1, out), sh("npm test", 0, "Tests  3 passed (3)"), edit("tests/test_data.py")), [["tests/test_data.py", false]]); // another tool's pass clears nothing
  assert.ok(isTest("app/tests.py") && isTest("src/FooTest.java") && isTest("pkg/a_tests.py") && !isTest("src/contests.py") && !isTest("src/Latest.java"));
});

// What a skeptic, told to disprove "a tick only for a pass that was seen", ran against the receipt.
test("a summary is credited only to the run it sums up: any failure on the line fails it, and a pass needs its own summary", () => {
  const res = (...cs: Call[]) => { const r = receipt(cs, CWD); return [r.tests, r.checks.map((c) => c.verdict)]; };
  // two runs on one line, the first failing: the last summary is not both runs'
  assert.deepEqual(res(sh("pytest a.py -q; pytest b.py -q", 0, "1 failed, 1 passed in 0.12s\n2 passed in 0.05s")), ["failed", ["failed", "passed"]]);
  // (the second is the line's last command and exited 0: that much was seen)
  assert.deepEqual(res(sh("for f in a b; do pytest $f.py -q; done", 0, "1 failed, 1 passed in 0.12s\n2 passed in 0.05s")), ["failed", ["failed"]]);
  assert.deepEqual(res(sh("node --test a.test.js; node --test b.test.js; echo done", 0, "ℹ pass 2\nℹ fail 0\nℹ pass 1\nℹ fail 1")), ["failed", ["failed", "failed"]]);
  // the first crashed with no summary, the second passed: one summary for two runs sums up neither for sure
  assert.deepEqual(res(sh("pytest a.py -q; pytest b.py -q | tail -1", 0, "Traceback (most recent call last)\n2 passed in 0.05s")), ["unseen", ["unseen", "unseen"]]);
  // a suite that failed to run fails the run, whatever its Tests line counts, and a pipe's exit code hides nothing
  assert.deepEqual(res(sh("npx jest 2>&1 | tail -20", 0, "Test Suites: 1 failed, 1 passed, 2 total\nTests:       5 passed, 5 total")), ["failed", ["failed"]]);
  assert.deepEqual(res(sh("npx vitest run | tail -5", 0, " Test Files  1 failed | 2 passed (3)\n      Tests  9 passed (9)")), ["failed", ["failed"]]);
  // go says a line a package and none for the run: cut by a pipe, a pass was not seen
  assert.deepEqual(res(sh("go test ./... | head -3", 0, "ok  \tpkg/a\t0.01s\nok  \tpkg/b\t0.01s")), ["unseen", ["unseen"]]);
  // after an `||` it ran only if the first command failed: exit 0 does not say it ran
  assert.deepEqual(res(sh("test -d .venv || pytest -q", 0)), ["unseen", ["unseen"]]);
  assert.deepEqual(res(sh("test -d .venv || pytest -q", 0, "3 passed in 0.1s")), ["passed", ["passed"]]);
});

test("the same command in another folder is another run: one's pass does not clear the other's failure", () => {
  let r = receipt([sh("cd packages/a && npm test", 1, "Tests:       1 failed, 2 passed, 3 total"), sh("cd ../b && npm test", 0, "Tests:       4 passed, 4 total")], CWD);
  assert.deepEqual([r.tests, r.checks.map((c) => c.verdict)], ["failed", ["failed", "passed"]]);
  // and in the same folder again, its last run decides
  r = receipt([sh("cd packages/a && npm test", 1, "Tests:       1 failed, 2 passed, 3 total"), sh("npm test", 0, "Tests:       3 passed, 3 total")], CWD);
  assert.deepEqual([r.tests, r.checks.length], ["passed", 1]);
});

test("a runner known only by its name is a test run, decided by its own exit code and by nothing else", () => {
  const found = (line: string, exit: number | null = 0) => receipt([sh(line, exit)], CWD).checks.map((c) => [c.tool, c.verdict]);
  assert.deepEqual(found("npm run test:unit", 1), [["npm test", "failed"]]);
  assert.deepEqual(found("bun test", 1), [["bun test", "failed"]]);
  assert.deepEqual(found("mvn -q test", 1), [["mvn", "failed"]]);
  assert.deepEqual(found("./gradlew test"), [["gradle", "passed"]]);
  assert.deepEqual(found("bundle exec rspec spec/models", 1), [["rspec", "failed"]]);
  assert.deepEqual(found("dotnet test", 1), [["dotnet test", "failed"]]);
  assert.deepEqual(found("docker compose run --rm app pytest -q", 1), [["pytest", "failed"]]);
  assert.deepEqual(found("mvn test | tail -5"), [["mvn", "unseen"]]); // the exit code is tail's, and it has no summary the receipt reads
  assert.equal(receipt([sh("bun test", 0, " 3 pass\n 0 fail")], CWD).checks[0]!.why, "its output says 3 pass, 0 fail");
});
