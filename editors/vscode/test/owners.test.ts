import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";
import { inScope, owner, STEP_COLOURS, STEP_FALLBACKS, stepColour } from "../src/owners.ts";
import { parseState } from "../src/state.ts";

// in_scope's own answers (plan.py), which tests/test_vscode_scope_parity.py asks it for again: the port gives each
const cases = JSON.parse(readFileSync(new URL("./fixtures/scope-cases.json", import.meta.url), "utf8")) as
  { scope: string[]; path: string; inside: boolean }[];

test("a scope holds a path exactly as the CLI's in_scope says", () => {
  for (const c of cases) assert.equal(inScope(c.path, c.scope), c.inside, `${c.path} in ${c.scope.join(", ")}`);
  assert.ok(cases.length > 200 && cases.some((c) => c.inside) && cases.some((c) => !c.inside));
});

const tasks = parseState(JSON.stringify({
  schema: 1,
  tasks: [
    { id: "api", title: "the API", state: "running", scope: ["src/api/**", "!src/api/vendor/**"], agent: 3,
      model: "Nano", forks: [{ letter: "a" }, { letter: "b" }, { letter: "c" }] },
    { id: "web", title: "the page", state: "ready", scope: ["src/web/**"] },
    { id: "docs", title: "the docs", state: "review", scope: ["docs/**"] },
    { id: "old", title: "the old one", state: "done", scope: ["src/old.py"] },
  ],
})).tasks;

test("the Explorer marks each live task's files: a running one with its agent's number, the rest by state", () => {
  const api = owner("src/api/routes.ts", tasks);
  assert.equal(api?.badge, "3");
  assert.equal(api?.tooltip, "the API · agent 3 · Nano · 3 attempts racing: writing these files now");
  assert.equal(owner("src/api", tasks)?.badge, "3"); // the directory it works in
  assert.equal(owner("src/api/vendor/lib.js", tasks), null); // kept out of its scope
  assert.deepEqual(owner("src/web/page.tsx", tasks), { badge: "·", state: "ready", colour: "terminal.ansiCyan",
    tooltip: "the page · ready: its files once it runs" });
  assert.equal(owner("docs/a.md", tasks)?.badge, "✓");
  assert.equal(owner("src/old.py", tasks), null); // done: nobody's now
  assert.equal(owner("src", tasks), null);
  assert.equal(owner(".graphene/worktrees/api/src/api/routes.ts", tasks), null); // the store's own
});

test("each step has one colour, by its place in the plan: its files in the Explorer wear it, whatever its state", () => {
  assert.deepEqual(["api", "web", "docs"].map((id) => stepColour(id, tasks)), [0, 1, 2]);
  assert.equal(owner("src/api/routes.ts", tasks)?.colour, STEP_COLOURS[0]);
  assert.equal(owner("docs/a.md", tasks)?.colour, STEP_COLOURS[2]);
  const many = Array.from({ length: STEP_COLOURS.length + 2 }, (_, i) => ({ id: `t${i}` }));
  assert.equal(stepColour(`t${STEP_COLOURS.length}`, many), 0, "more steps than colours: round again");
  assert.equal(stepColour("not in the plan", many), 0);
  assert.ok(STEP_COLOURS.every((c) => !/^charts\.(yellow|green|purple|blue|red)$/.test(c)), "a state's colour is never a step's");
  assert.equal(STEP_FALLBACKS.length, STEP_COLOURS.length, "a fallback for each");
});
