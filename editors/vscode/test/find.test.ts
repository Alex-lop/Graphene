import assert from "node:assert/strict";
import { test } from "node:test";
import { candidates, found } from "../src/find.ts";

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
