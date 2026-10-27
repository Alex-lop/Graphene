import assert from "node:assert/strict";
import { test } from "node:test";
import { candidates, cannotRun, found, olderWords, which } from "../src/find.ts";

test("graphene is looked for on each PATH entry, then ~/.local/bin, then uv's own bin, each once", () => {
  const list = candidates("/usr/bin:/opt/bin", "/Users/alex", "/Users/alex/.local/bin", ":");
  assert.deepEqual(list, ["/usr/bin/graphene", "/opt/bin/graphene", "/Users/alex/.local/bin/graphene"]);
  const uv = candidates("/usr/bin", "/Users/alex", "/opt/uv/bin", ":");
  assert.deepEqual(uv, ["/usr/bin/graphene", "/Users/alex/.local/bin/graphene", "/opt/uv/bin/graphene"]);
  assert.deepEqual(candidates(undefined, "/h", null, ":"), ["/h/.local/bin/graphene"]);
});

test("the first one that exists wins, and whether it was on the PATH is said, so the status bar can say where", () => {
  const list = candidates("/usr/bin:/opt/bin", "/Users/alex", null, ":");
  assert.deepEqual(found(list, (p) => p === "/Users/alex/.local/bin/graphene", 2), { path: "/Users/alex/.local/bin/graphene", onPath: false });
  assert.deepEqual(found(list, (p) => p === "/opt/bin/graphene", 2), { path: "/opt/bin/graphene", onPath: true });
  assert.equal(found(list, () => false, 2), null);
});

test("the extension says which graphene it runs, its path and its version, and the older-CLI line names them", () => {
  // the stranger's hour: ~/.local/bin held 0.8.0 ahead of the new one, and nothing on screen said which ran
  assert.equal(which("/Users/alex/.local/bin/graphene", "graphene 0.8.0"), "graphene 0.8.0 at /Users/alex/.local/bin/graphene");
  assert.equal(which("graphene", null), "graphene at graphene (its version did not read)");
  const line = olderWords("/Users/alex/.local/bin/graphene", "graphene 0.8.0");
  assert.match(line, /older than the extension.*needs 0\.9/);
  assert.match(line, /runs graphene 0\.8\.0 at \/Users\/alex\/\.local\/bin\/graphene/);
});

test("a graphene.path that is not there, a directory, or without its x bit is 'not installed', with the offer; a refusal is not", () => {
  // execFile's err.code is the spawn error's name when nothing ran, the exit code (a number) when graphene refused
  for (const code of ["ENOENT", "EACCES", "EISDIR", "ENOTDIR", "EPERM"]) assert.ok(cannotRun(code), code);
  assert.ok(!cannotRun(1), "a refusal: graphene ran");
  assert.ok(!cannotRun(2));
  assert.ok(!cannotRun(undefined), "no error: it ran and answered");
  assert.ok(!cannotRun(null), "killed by a signal: it ran");
  assert.ok(!cannotRun("ERR_CHILD_PROCESS_STDIO_MAXBUFFER"), "it ran and said too much");
});
