// The page's own arithmetic, against the golden graph of the synthetic run.

import { expect, test } from "vitest";

import golden from "../../tests/fixtures/run_graph.json";
import { chain, clip, cull, hues, laneRegion, matching, rowRegion, spaced, span, why, LANE_H, ROW_H } from "./model";
import type { Graph, Plan, PlanNode } from "./types";

const graph = golden as unknown as Graph;

const GROUP = "group:22222222:wf_ab12cd34-ef5";
const A2 = "lane:22222222:7a8b9cadbecfd0e8"; // "Add the HTTP API", the worktree outside the repo
const MEMBER = "lane:22222222:0a1b2c3d4e5f6071"; // "Build the parser", first in the group
const UNKNOWN = "lane:unknown";

test("closed, only the lanes that are not in a group are drawn", () => {
  const region = laneRegion(graph, new Set());
  expect(region.shown.size).toBe(5); // main, the group, two agents, unknown
  expect(region.shown.has(MEMBER)).toBe(false);
  expect(region.y.get(MEMBER)).toBe(region.y.get(GROUP)); // a member's marks land on its group
  expect(region.height).toBe(5 * LANE_H);
});

test("opening a group moves its members out and everything below down", () => {
  const closed = laneRegion(graph, new Set());
  const open = laneRegion(graph, new Set([GROUP]));
  expect(open.shown.size).toBe(11);
  expect(open.y.get(GROUP)).toBe(closed.y.get(GROUP));
  expect(open.y.get(MEMBER)).toBe(closed.y.get(GROUP)! + LANE_H);
  expect(open.y.get(A2)).toBe(closed.y.get(A2)! + 6 * LANE_H); // the group's extra, below it
  expect(open.y.get(UNKNOWN)).toBe(closed.y.get(UNKNOWN)! + 6 * LANE_H);
  expect(open.height).toBe(11 * LANE_H);
});

test("opening a directory moves its files out and the directories below down", () => {
  const closed = rowRegion(graph, new Set());
  const open = rowRegion(graph, new Set(["dir:app"]));
  expect(closed.shown.size).toBe(4); // app, docs, tests, .
  expect(closed.y.get("file:app/util.py")).toBe(closed.y.get("dir:app"));
  expect(open.y.get("file:app/parser.py")).toBe(ROW_H);
  expect(open.y.get("dir:docs")).toBe(closed.y.get("dir:docs")! + 9 * ROW_H);
  expect(open.shown.has("file:docs/guide.md")).toBe(false); // its own directory is still closed
});

test("culling keeps the marks inside the window, on the marks as the payload gives them", () => {
  const all = graph.marks; // every mark, lanes and rows together: what the page actually culls
  expect(all.map((m) => m.x)).toEqual([...all.map((m) => m.x)].sort((a, b) => a - b));
  expect(cull(all, 0, graph.axis.width)).toHaveLength(all.length);
  expect(cull(all, -50, -1)).toHaveLength(0);
  expect(cull(all, 1e9, 2e9)).toHaveLength(0);
  const middle = cull(all, 655, 805);
  expect(middle.every((m) => m.x >= 655 && m.x <= 805)).toBe(true);
  expect(middle.filter((m) => m.region === "rows").map((m) => m.at)).toEqual([
    "file:app/util.py",
    "file:app/util.py",
    "file:app/util.py",
    "file:app/core.py",
  ]);
  expect(middle.some((m) => m.region === "lanes")).toBe(true); // both regions, from one scan
});

test("a selected agent lights its lane, its files, its commit and the links between", () => {
  const lit = chain(graph, { kind: "agent", id: A2 })!;
  expect(lit.lanes.has(A2)).toBe(true);
  expect([...lit.rows].sort()).toEqual(["dir:app", "dir:tests", "file:app/api.py", "file:tests/test_api.py"]);
  expect(lit.marks.has(`commit:${A2}:commit:2d045414144e90cce7824c493e2195517476e99f`)).toBe(true);
  expect(lit.marks.has("change:file:app/api.py:event:22222222:toolu_a2_write")).toBe(true);
  expect(lit.marks.has("change:file:docs/guide.md:event:22222222:toolu_a1_edit")).toBe(false);
  expect([...lit.links].filter((id) => id.startsWith("touched")).length).toBe(2);
  expect([...lit.links].filter((id) => id.startsWith("committed-in")).length).toBe(2);
  expect(lit.links.has(`returned:${A2}>lane:22222222:main`)).toBe(true);
});

test("a selected file lights the agents that touched it and the commit that carries it", () => {
  const lit = chain(graph, { kind: "file", id: "file:app/util.py" })!;
  expect([...lit.rows].sort()).toEqual(["dir:app", "file:app/util.py"]);
  expect([...lit.lanes].sort()).toEqual([
    "lane:22222222:4a5b6c7d8e9fa0b5",
    "lane:22222222:5a6b7c8d9eafb0c6",
  ]);
  expect([...lit.links].filter((id) => id.startsWith("touched")).length).toBe(2); // the collision
  expect(lit.marks.size).toBe(4); // three writes and the commit they land in
});

test("a selected commit lights its files and the grade each of them has", () => {
  const sha = "a8bc60f696fd40322a48bd364e07cb3758fd7a6f";
  const lit = chain(graph, { kind: "commit", id: `commit:lane:22222222:3a4b5c6d7e8f90a4:commit:${sha}` })!;
  expect([...lit.rows].sort()).toEqual(["dir:app", "file:app/gen_a.py", "file:app/gen_b.py", "file:app/schema.py"]);
  expect(lit.marks.has(`evidence:file:app/gen_a.py:commit:${sha}`)).toBe(true);
  expect([...lit.links].every((id) => id.startsWith("committed-in"))).toBe(true);
});

test("the unknown lane lights the commit nobody is recorded making", () => {
  const lit = chain(graph, { kind: "agent", id: UNKNOWN })!;
  expect([...lit.rows]).toEqual(["file:pyproject.toml", "dir:."]);
  expect(lit.marks.has("evidence:file:pyproject.toml:commit:e4fe8111d3f92bc5b951f2f1a89d1375f4cd8d5c")).toBe(true);
});

test("nothing is lit without a selection", () => {
  expect(chain(graph, null)).toBe(null);
});

test("a chip lights exactly the records its counter counted", () => {
  expect(matching(graph, "failed_checks").marks.size).toBe(graph.counters.failed_checks);
  expect(matching(graph, "rerun_green").marks.size).toBe(graph.counters.rerun_green);
  expect(matching(graph, "refused").marks.size).toBe(graph.counters.refused);
  expect(matching(graph, "outside").marks.size).toBe(graph.counters.outside);
  const collisions = matching(graph, "collisions");
  expect(collisions.rows.has("file:app/util.py")).toBe(true);
  expect(collisions.rows.has("dir:app")).toBe(true);
});

test("the eight hues go to the agent lanes, in lane order", () => {
  const index = hues(graph);
  expect(index.get("lane:22222222:main")).toBe(-1);
  expect(index.get(GROUP)).toBe(-1);
  expect(index.get(UNKNOWN)).toBe(-1);
  expect(index.get(MEMBER)).toBe(0);
  expect(index.get(A2)).toBe(7);
});

test("a span reads the way the terminal prints it", () => {
  expect(span(2455)).toBe("40m 55s");
  expect(span(830)).toBe("13m 50s");
  expect(span(7380)).toBe("2h 03m");
  expect(span(45)).toBe("45s");
});

test("a label that would print over the one before it is skipped, and nothing moves", () => {
  const ticks = [0, 30, 60, 61, 200].map((x) => ({ x }));
  expect(spaced(ticks, (t) => t.x, 56).map((t) => t.x)).toEqual([0, 60, 200]);
  expect(spaced(ticks, (t) => t.x * 100, 56)).toEqual(ticks); // zoomed in, every label has room
  expect(spaced([], (t: { x: number }) => t.x, 56)).toEqual([]);
});

// -- the plan's controls -------------------------------------------------------------------------

const node = (over: Partial<PlanNode>): PlanNode =>
  ({
    id: "n1",
    title: "the endpoint",
    goal: "",
    scope: ["src/api/**"],
    check: "true",
    signoff: false,
    needs: [],
    owner: "agent",
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
    ...over,
  }) as PlanNode;

const planOf = (nodes: PlanNode[], writable = true): Plan => ({ nodes, writable }) as Plan;

test("a control the state does not allow is disabled, and says which state", () => {
  const open = node({});
  const only = (n: PlanNode, p: Plan) => Object.entries(why(n, p)).filter(([, no]) => no === null).map(([act]) => act);
  expect(only(open, planOf([open]))).toEqual(["drop", "edit"]);
  expect(why(open, planOf([open])).signoff).toContain("n1 is ready");
  const proposed = node({ state: "proposed" });
  expect(only(proposed, planOf([proposed]))).toEqual(["accept", "drop", "edit"]);
  const review = node({ state: "review", signoff: true });
  expect(only(review, planOf([review]))).toEqual(["signoff", "reopen", "drop", "edit"]);
  const done = node({ state: "done" });
  expect(only(done, planOf([done]))).toEqual(["reopen", "drop"]);
  expect(why(done, planOf([done])).edit).toContain("send it back");
});

test("a running node cannot be dropped, nor one something else waits on", () => {
  const running = node({ state: "running", executor: "claude:aa11" });
  expect(why(running, planOf([running])).drop).toContain("claude:aa11");
  const first = node({});
  const second = node({ id: "n2", needs: ["n1"] });
  expect(why(first, planOf([first, second])).drop).toBe("n2 waits on n1; change what they need first");
  expect(why(second, planOf([first, second])).drop).toBe(null);
});

test("a read-only page disables every control, with the same reason", () => {
  const one = node({ state: "review" });
  const reasons = Object.values(why(one, planOf([one], false)));
  expect(new Set(reasons)).toEqual(new Set(["this page cannot change the plan; it is read-only"]));
});

test("a label that has to fit is cut with an ellipsis, never mid-layout", () => {
  expect(clip("users endpoint", 200, 6.4)).toBe("users endpoint");
  expect(clip("a title far too long to fit in this box", 60, 6.4)).toBe("a title …"); // nine characters fit at 6.4 px each, and the last is the ellipsis
});
