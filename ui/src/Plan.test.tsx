// What the tree forces on the page, rendered: the outline is indented by the depth Python computed,
// a sub-goal says how many of the leaves beneath it are done instead of a scope and a check, and a
// node's detail opens with why it is being done at all. React renders to a string here, so this
// needs no browser and no test framework beyond the one already installed.

import { renderToStaticMarkup } from "react-dom/server";
import { expect, test } from "vitest";

import { PlanHeader, PlanInspector, PlanTree } from "./Plan";
import type { Plan, PlanNode } from "./types";

const node = (id: string, extra: Partial<PlanNode> = {}): PlanNode => ({
  id,
  title: `do ${id}`,
  goal: "",
  scope: ["src/**"],
  check: "true",
  signoff: false,
  needs: [],
  owner: "agent",
  parent: null,
  aside: false,
  sub_goal: false,
  depth: 0,
  why: ["people can sign in"],
  leaves_done: 0,
  leaves_total: 0,
  state: "open",
  display_state: "ready",
  rev: 1,
  executor: null,
  started_at: null,
  finished_at: null,
  waits: [],
  log: [],
  forks: [],
  lane: "agent",
  column: 0,
  row: 0,
  x: 0,
  y: 0,
  width: 200,
  height: 76,
  ...extra,
});

const plan: Plan = {
  version: 1,
  repo: "toy",
  goal: "people can sign in",
  person: "alex",
  paused: false,
  width: 200,
  height: 76,
  nodes: [
    node("signin", { sub_goal: true, display_state: "sub-goal", scope: [], check: null, leaves_total: 2 }),
    node("api", { parent: "signin", depth: 1, why: ["people can sign in", "do signin (signin)"] }),
    node("typed", { aside: true, state: "done", display_state: "done" }),
  ],
  lanes: [],
  edges: [],
  counts: { proposed: 0, open: 2, running: 0, review: 0, done: 1 },
  waiting_on_person: [],
  loose: [],
  all_done: false,
  forecast: { runs: [], waits: [] },
  holes: { scope: "", check: "", stop: "", person: "" },
  writable: false,
  token: null,
};

test("the tree is indented by depth, and a sub-goal counts its leaves instead of naming a scope", () => {
  const html = renderToStaticMarkup(<PlanTree plan={plan} picked={null} onPick={() => undefined} />);
  expect(html).toMatch(/data-tree="signin" data-depth="0" style="padding-left:12px"/);
  expect(html).toMatch(/data-tree="api" data-depth="1" style="padding-left:32px"/); // one level in
  expect(html).toContain("0/2 done");
  expect(html).toContain("sub-goal");
  expect(html.indexOf('data-tree="signin"')).toBeLessThan(html.indexOf('data-tree="api"'));
  expect(html).not.toContain('data-tree="typed"'); // a done aside folds into one line below the tree
  expect(html).toContain("✓ 1 done from a prompt");
});

test("under a leaf that forked, the tree of sandboxes: each fork, its model and how it ended, the winner marked", () => {
  const forked: Plan = {
    ...plan,
    nodes: [
      node("greet", {
        state: "done",
        display_state: "done",
        forks: [
          { fork: 1, of: 2, model: "nvidia/Nemotron-3-Nano-fake", state: "check failed", why: "its check failed (exit 1)", checkpoint: "made", ops: 6, seconds: 4.25 },
          { fork: 2, of: 2, model: "nvidia/Nemotron-3-Nano-fake", state: "passed", why: "its check passed first", checkpoint: "forked", ops: 4, seconds: 2 },
        ],
      }),
      node("schema"),
    ],
  };
  const html = renderToStaticMarkup(<PlanTree plan={forked} picked={null} onPick={() => undefined} />);
  const under = html.slice(html.indexOf('data-tree="greet"'), html.indexOf('data-tree="schema"'));
  expect(under).toContain('data-forks="greet"'); // inside the leaf's own item: a level in, not a node
  expect(under).toMatch(/data-fork="1" data-state="check failed">.*<b>fork 1 of 2<\/b><span class="what">Nemotron-3-Nano-fake/);
  expect(under).toContain("its check failed (exit 1) · sandbox made, 6 operations, 4.3 s");
  expect(under).toMatch(/data-fork="2" data-state="passed"><button type="button" class="row fork won">.*✓ won/);
  expect(under).toContain("sandbox forked from the checkpoint, 4 operations, 2.0 s");
  expect(html.slice(html.indexOf('data-tree="schema"'))).not.toContain("data-fork"); // a leaf that did not fork
});

test("a node's detail opens with the path from the goal down to it, root first", () => {
  const html = renderToStaticMarkup(
    <PlanInspector plan={plan} picked="api" write={async () => null} />,
  );
  const why = html.slice(html.indexOf('data-testid="why"'));
  expect(why.indexOf("people can sign in")).toBeLessThan(why.indexOf("do signin (signin)"));
  expect(why).toMatch(/style="padding-left:12px">do signin \(signin\)/); // a level in from the root
  expect(html).toContain("src/**"); // and a leaf still says what it may touch
});

test("with no Claude Code session recorded, the record screen cannot be opened and the button says why", () => {
  // a run by any other executor (graphene run --with …) records no session: its record is on the plan
  const header = (recorded: number) =>
    renderToStaticMarkup(<PlanHeader plan={plan} view="plan" onView={() => undefined} recorded={recorded} />);
  const record = (html: string) => html.slice(html.lastIndexOf("<button", html.indexOf("the record")));
  expect(record(header(0))).toMatch(/^<button[^>]* disabled="" title="no Claude Code session was recorded in this repo/);
  expect(record(header(1))).not.toContain("disabled");
});
