import assert from "node:assert/strict";
import { test } from "node:test";
import * as C from "../src/commands.ts";

const landed = JSON.stringify({
  repo: "/r", left: "0123456789abcdef0123", right: "fedcba9876543210fedc",
  files: [{ path: "app.py", status: "M", old: null }, { path: "new.py", status: "A", old: null },
          { path: "gone.py", status: "D", old: null }, { path: "b.py", status: "R", old: "a.py" }],
  said: ["landed by its check"],
});

test("a landed diff is each file's two revisions; an added file has no left, a deleted one no right", () => {
  const d = C.parseDiff(landed);
  assert.deepEqual(C.diffPairs(d), [
    { path: "app.py", status: "M", left: { repo: "/r", path: "app.py", rev: "0123456789abcdef0123" }, right: { repo: "/r", path: "app.py", rev: "fedcba9876543210fedc" } },
    { path: "new.py", status: "A", left: { repo: "/r", path: "new.py", rev: "" }, right: { repo: "/r", path: "new.py", rev: "fedcba9876543210fedc" } },
    { path: "gone.py", status: "D", left: { repo: "/r", path: "gone.py", rev: "0123456789abcdef0123" }, right: { repo: "/r", path: "gone.py", rev: "" } },
    { path: "b.py", status: "R", left: { repo: "/r", path: "a.py", rev: "0123456789abcdef0123" }, right: { repo: "/r", path: "b.py", rev: "fedcba9876543210fedc" } },
  ]);
  assert.equal(C.diffTitle("greet route", null, d), "greet route: 0123456 → fedcba9");
  assert.deepEqual(d.said, ["landed by its check"]);
});

test("a running task's diff is its base against the files on disk in its own directory", () => {
  const d = C.parseDiff(JSON.stringify({ repo: "/r/wt", left: "base", right: null, files: [{ path: "app.py", status: "M" }], said: [] }));
  assert.deepEqual(C.diffPairs(d), [{ path: "app.py", status: "M", left: { repo: "/r/wt", path: "app.py", rev: "base" }, right: { repo: "/r/wt", path: "app.py", rev: null } }]);
  assert.equal(C.diffTitle("greet route", "b", d), "greet route · fork b: base → now");
});

test("a diff with no files is still a diff", () => {
  assert.deepEqual(C.diffPairs(C.parseDiff("{}")), []);
});

test("the agent's copy is the snapshot's checkout, else the run's own place", () => {
  assert.equal(C.agentCopy("/r", "ids", "/elsewhere/ids"), "/elsewhere/ids");
  assert.match(C.agentCopy("/r", "ids", null), /^\/r\/\.graphene\/worktrees\/ids$/);
  assert.match(C.agentCopy("/r", "ids", undefined, "b"), /\/ids\.b$/);
});
