// The direction above the plan on the page: the path from the top to the plan's node, root first, in
// the row grammar; one line when the plan hangs from no node; nothing without a direction.

import { renderToStaticMarkup } from "react-dom/server";
import { expect, test } from "vitest";

import { DirectionPath } from "./Direction";
import type { Direction, DirectionNode } from "./types";

const node = (id: string, parent: string | null, extra: Partial<DirectionNode> = {}): DirectionNode => ({
  id,
  title: `the ${id}`,
  proposed: false,
  parent,
  about: [],
  word: "quiet",
  you: 0,
  running: 0,
  next: null,
  earlier: [],
  ...extra,
});

const direction = (at: string | null): Direction => ({
  file: ".graphene/direction.txt",
  nodes: [node("product", null, { word: "yours", you: 2, running: 1, next: "ids" }), node("live", "product"), node("board", "product")],
  plan: { goal: "users come back with ids", node: at, done: 0, leaves: 2, you: 2, running: 1, next: "ids" },
  sessions: [],
  older: 0,
});

test("the path to the plan's node is drawn root first, each row with its id, its word and what is below it", () => {
  const html = renderToStaticMarkup(<DirectionPath direction={direction("live")} />);
  expect(html.indexOf('data-direction="product"')).toBeLessThan(html.indexOf('data-direction="live"'));
  expect(html).not.toContain('data-direction="board"'); // the path only, not the siblings
  expect(html).toContain("you 2 · 1 running · next: ids");
});

test("what waits on the person and what runs are named by the id they act on, not only counted", () => {
  const d = direction("live");
  d.nodes.push(node("mobile", "product", { proposed: true, word: "proposed" }));
  d.plan = { ...d.plan!, waiting: [{ id: "render", title: "render it", word: "review", do: "" }], leaves_running: [{ id: "template", title: "t", by: "5a1e0c3b" }] };
  d.sessions = [
    { key: "b7", short: "b7c24d1e", label: "", word: "your turn", last: "", at: "", node: null, how: "" },
    { key: "5a", short: "5a1e0c3b", label: "", word: "running", last: "", at: "", node: "plan", how: "", holds: "template" },
    { key: "c3", short: "c3d4e5f6", label: "", word: "running", last: "", at: "", node: "billing", how: "" },
  ];
  const html = renderToStaticMarkup(<DirectionPath direction={d} />);
  expect(html).toContain("waits on you: render (review), mobile (proposed), b7c24d1e (your turn) · running: template (5a1e0c3b), c3d4e5f6");
});

test("a plan that hangs from no node says how to hang it, and no direction draws nothing", () => {
  expect(renderToStaticMarkup(<DirectionPath direction={direction(null)} />)).toContain("graphene direction plan NODE");
  expect(renderToStaticMarkup(<DirectionPath direction={null} />)).toBe("");
});
