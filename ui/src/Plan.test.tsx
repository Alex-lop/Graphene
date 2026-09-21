// What the tree forces on the page, rendered: the outline is indented by the depth Python computed,
// a sub-goal says how many of the leaves beneath it are done instead of a scope and a check, and a
// node's detail opens with why it is being done at all. React renders to a string here, so this
// needs no browser and no test framework beyond the one already installed.

import { renderToStaticMarkup } from "react-dom/server";
import { expect, test } from "vitest";

import { PlanInspector, PlanTree } from "./Plan";
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

test("a node's detail opens with the path from the goal down to it, root first", () => {
  const html = renderToStaticMarkup(
    <PlanInspector plan={plan} picked="api" write={async () => null} />,
  );
  const why = html.slice(html.indexOf('data-testid="why"'));
  expect(why.indexOf("people can sign in")).toBeLessThan(why.indexOf("do signin (signin)"));
  expect(why).toMatch(/style="padding-left:12px">do signin \(signin\)/); // a level in from the root
  expect(html).toContain("src/**"); // and a leaf still says what it may touch
});
