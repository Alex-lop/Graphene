// What the tree forces on the page, rendered: the outline is indented by the depth Python computed,
// a sub-goal says how many of the leaves beneath it are done instead of a scope and a check, and a
// node's detail opens with why it is being done at all. React renders to a string here, so this
// needs no browser and no test framework beyond the one already installed.

import { renderToStaticMarkup } from "react-dom/server";
import { expect, test } from "vitest";

import { layoutFor } from "./model";
import { LayoutBar, PlanHeader, PlanInspector, PlanTopDown, PlanTree, PlanView } from "./Plan";
import type { Plan, PlanEdge, PlanNode } from "./types";

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
  tree_x: 0,
  tree_y: 124,
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
  critical: [],
  ready: [],
  tree_width: 200,
  tree_height: 200,
  tree_goal: [0, 0],
  tree_links: [],
};

// feeds, as plan_view.py lays it out: two chains into one leaf, the longer one critical
const edge = (source: string, target: string, critical: boolean): PlanEdge => ({ id: `${source}>${target}`, source, target, points: [[200, 38], [240, 38]], critical });
const feeds: Plan = {
  ...plan,
  nodes: [node("xml-reader"), node("xml-wire", { needs: ["xml-reader"], display_state: "waiting" }), node("zero-rule"), node("xml-e2e", { needs: ["xml-wire", "zero-rule"], display_state: "waiting" })],
  edges: [edge("xml-reader", "xml-wire", true), edge("xml-wire", "xml-e2e", true), edge("zero-rule", "xml-e2e", false)],
  critical: ["xml-reader", "xml-wire", "xml-e2e"],
  ready: ["xml-reader", "zero-rule"],
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

test("a fork still running shows no count: its row holds the operations it started with, and the terminal waits too", () => {
  const running: Plan = {
    ...plan,
    nodes: [
      node("greet", {
        state: "running",
        display_state: "running",
        forks: [{ fork: 1, of: 1, model: "nvidia/Nemotron-3-Nano-fake", state: "running", why: "", checkpoint: "forked", ops: 0, seconds: 0 }],
      }),
    ],
  };
  const html = renderToStaticMarkup(<PlanTree plan={running} picked={null} onPick={() => undefined} />);
  expect(html).toMatch(/data-fork="1" data-state="running">.*<b>fork 1 of 1<\/b>/);
  expect(html).not.toContain("operations");
  expect(html).not.toContain("0.0 s");
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

test("the page draws the plan the way its shape calls for: the graph when anything waits, else the tree when it fits, else the outline", () => {
  expect(layoutFor(feeds, 2000)).toBe("graph");
  expect(layoutFor(feeds, 100)).toBe("graph"); // what waits on what is the thing to see, and it pans
  expect(layoutFor(plan, 1000)).toBe("tree");
  expect(layoutFor({ ...plan, tree_width: 4000 }, 1000)).toBe("outline");
});

test("the switch has the three layouts, says why this one was chosen, and says the critical path and what can start now in words", () => {
  const bar = (picked: boolean) => renderToStaticMarkup(<LayoutBar plan={feeds} layout="graph" picked={picked} onLayout={() => undefined} />);
  const html = bar(false);
  expect(html).toMatch(/data-layout="graph"/);
  expect(html.match(/<button/g)).toHaveLength(3);
  expect(html).toMatch(/aria-pressed="false"[^>]*>outline<\/button>.*aria-pressed="false"[^>]*>tree<\/button>.*class="on" aria-pressed="true"[^>]*>graph<\/button>/);
  expect(html).toContain("chosen: some nodes wait on others");
  expect(html).toContain("critical path: xml-reader → xml-wire → xml-e2e");
  expect(html).toContain("can start now: xml-reader, zero-rule");
  expect(bar(true)).toContain("your choice, kept in this browser");
  expect(renderToStaticMarkup(<LayoutBar plan={plan} layout="tree" picked={false} onLayout={() => undefined} />)).toContain("no critical path: nothing waits on anything");
});

test("in the graph the critical path is drawn heavier, its edges and its boxes, and a leaf that can start now is marked", () => {
  const html = renderToStaticMarkup(<PlanView plan={feeds} picked={null} onPick={() => undefined} />);
  expect(html).toMatch(/data-edge="xml-reader&gt;xml-wire" data-critical="true" class="edge critical"/);
  expect(html).toMatch(/data-edge="xml-wire&gt;xml-e2e" data-critical="true" class="edge critical"/);
  expect(html).toMatch(/data-edge="zero-rule&gt;xml-e2e" data-critical="false" class="edge"/);
  expect(html).toMatch(/class="node critical now" data-node="xml-reader"/);
  expect(html).toMatch(/class="node critical" data-node="xml-e2e"/);
  expect(html).toMatch(/class="node now" data-node="zero-rule" data-state="ready" data-critical="false" data-now="true"/);
  expect(html).toMatch(/data-pans="false"/); // a static render measures no pane, so it draws the plan whole
});

test("the tree is drawn top-down from Python's positions: the goal on top, a link to each node, the same boxes", () => {
  const tree: Plan = {
    ...plan,
    tree_goal: [112, 0],
    tree_links: [{ id: ">signin", source: "", target: "signin", points: [[212, 76], [212, 124]], critical: false }],
  };
  const html = renderToStaticMarkup(<PlanTopDown plan={tree} picked="api" onPick={() => undefined} />);
  expect(html).toMatch(/data-goal="" transform="translate\(128,16\)"/);
  expect(html).toContain("people can sign in");
  expect(html).toMatch(/data-link="&gt;signin" class="edge link" points="228,92 228,140"/);
  expect(html).toMatch(/class="node" data-node="signin" data-state="sub-goal"[^>]*transform="translate\(16,140\)"/);
  expect(html).toMatch(/class="node on" data-node="api"/);
  expect(html).not.toContain("lane-band"); // the tree has no lanes: whose a node is, is in the box
});
