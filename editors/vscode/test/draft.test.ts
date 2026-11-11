import assert from "node:assert/strict";
import { test } from "node:test";
import { blanks, draftLine, isDraft, lacks, type Draft } from "../src/graph/draft.ts";

const d = (over: Partial<Draft> = {}): Draft => ({ key: " d1", title: "a flag", files: "", check: "", approve: false, after: null, parent: null, ...over });

test("a draft's key is never a task's id; its blanks are on its box until they are filled", () => {
  assert.ok(isDraft(" d1"));
  assert.ok(!isDraft("d1") && !isDraft(null) && !isDraft(" goal"));
  assert.equal(blanks(d()), "files ___ · check ___");
  assert.equal(blanks(d({ files: "cli.py, tests/test_cli.py" })), "2 files · check ___");
  assert.equal(blanks(d({ files: "cli.py", check: "pytest -q" })), "1 file · check ✓");
  assert.equal(blanks(d({ files: "cli.py", approve: true })), "1 file · your approval");
  assert.ok(blanks(d()).length <= 25, "it fits the box's small line");
});

test("a draft joins the plan when it lacks nothing graphene asks of a task: a title, files, a check or your approval", () => {
  assert.deepEqual(lacks(d({ title: " " })), ["a title", "the files it may change", "a check or your approval"]);
  assert.deepEqual(lacks(d({ files: "cli.py" })), ["a check or your approval"]);
  assert.deepEqual(lacks(d({ files: "cli.py", check: "pytest -q" })), []);
  assert.deepEqual(lacks(d({ files: " , ", approve: true })), ["the files it may change"]);
  assert.deepEqual(lacks(d({ files: "cli.py", approve: true })), []);
  assert.match(draftLine(d({ files: "cli.py" })), /joins the plan once it has a check or your approval\./);
  assert.match(draftLine(d({ title: "" })), /once it has a title, the files it may change and a check or your approval\./);
  assert.equal(draftLine(d({ files: "cli.py", approve: true, said: "n9: its files are another task's" })), "", "the refusal is said in its place");
});
