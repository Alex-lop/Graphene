import assert from "node:assert/strict";
import { mkdtempSync, writeFileSync } from "node:fs";
import { register } from "node:module";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { test } from "node:test";
import * as C from "../src/commands.ts";

// a stand-in for the vscode module (a loader hook, as graph-host.test.ts does), enough for diff.ts's URIs
const stub = `
export class EventEmitter { constructor() { this.event = () => ({ dispose() {} }); } fire() {} dispose() {} }
export const Uri = { file(p) { return { scheme: "file", path: p, fsPath: p, query: "", with(c) { return { ...this, ...c }; } }; } };
`;
const hooks = `
const STUB = ${JSON.stringify(`data:text/javascript,${encodeURIComponent(stub)}`)};
export async function resolve(spec, ctx, next) { return spec === "vscode" ? { url: STUB, shortCircuit: true } : next(spec, ctx); }
`;
register(`data:text/javascript,${encodeURIComponent(hooks)}`);
const D = await import("../src/diff.ts");

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

test("a title action reads the diff on screen from a multi-file tab as from a single diff editor", () => {
  const side = (id: string, fork: string | null, rev = "abc") => ({ scheme: C.SCHEME, query: JSON.stringify({ repo: "/r", rev, id, fork }) });
  const file = { scheme: "file", query: "" };
  assert.deepEqual(C.diffOf({ original: side("n0", null), modified: side("n0", null) }), { id: "n0", fork: null });
  assert.deepEqual(C.diffOf({ textDiffs: [{ original: side("n1", "c"), modified: side("n1", "c") }, { original: side("n1", "c"), modified: side("n1", "c", "") }] }),
                   { id: "n1", fork: "c" });
  assert.deepEqual(C.diffOf({ original: side("n2", null), modified: file }), { id: "n2", fork: null }, "a running task's side on disk");
  assert.equal(C.diffOf({ original: file, modified: file }), null, "someone else's diff");
  assert.equal(C.diffOf({ uri: file }), null, "an ordinary editor");
  assert.equal(C.diffOf(undefined), null, "no tab");
});

test("a running agent's side on disk is read under our scheme, read-only, not opened as its file", async () => {
  const u = D.sideUri({ repo: "/r", path: "a.py", rev: null }, "n2", null);
  assert.equal(u.scheme, C.SCHEME);
  assert.deepEqual(JSON.parse(u.query), { repo: "/r", rev: null, id: "n2", fork: null });
  const dir = mkdtempSync(join(tmpdir(), "graphene-diff-"));
  writeFileSync(join(dir, "a.py"), "so far\n");
  assert.equal(await D.contentOf({ repo: dir, rev: null, id: "n2", fork: null }, join(dir, "a.py")), "so far\n");
  assert.equal(await D.contentOf({ repo: dir, rev: null, id: "n2", fork: null }, join(dir, "gone.py")), "", "not written yet");
  assert.equal(await D.contentOf({ repo: dir, rev: "", id: "n2", fork: null }, join(dir, "a.py")), "", "a side the file is not on");
});

test("the agent's copy is the snapshot's checkout, else the run's own place", () => {
  assert.equal(C.agentCopy("/r", "ids", "/elsewhere/ids"), "/elsewhere/ids");
  assert.match(C.agentCopy("/r", "ids", null), /^\/r\/\.graphene\/worktrees\/ids$/);
  assert.match(C.agentCopy("/r", "ids", undefined, "b"), /\/ids\.b$/);
});

test("from the palette, Open Changes offers the tasks that have changes and Compare Forks the ones racing", () => {
  const t = (id: string, state: string, letters: string[] = []) =>
    ({ id, state, forks: letters.map((letter) => ({ letter })) }) as unknown as import("../src/state.ts").Task;
  const tasks = [t("a", "running"), t("b", "review", ["a", "b"]), t("c", "came back"), t("d", "done"),
                 t("e", "ready"), t("f", "waiting"), t("g", "proposed"), t("h", "yours"), t("i", "running", [""])];
  assert.deepEqual(C.withChanges(tasks).map((x) => x.id), ["a", "b", "c", "d", "i"]);
  assert.deepEqual(C.forked(tasks).map((x) => x.id), ["b"], "a fork with no letter is not one to compare");
  assert.deepEqual(C.withChanges([]), []);
});
