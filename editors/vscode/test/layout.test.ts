import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";
import { layout, modeFor, order, ranks, step } from "../src/layout.ts";
import { parseState } from "../src/state.ts";

const fixture = (name: string) => readFileSync(new URL(`./fixtures/${name}.json`, import.meta.url), "utf8");

test("a rank is the longest chain of needs before a task", () => {
  const r = ranks(["a", "b", "c", "d"], [["a", "b"], ["b", "c"], ["a", "c"], ["d", "c"]]);
  assert.deepEqual(r, { a: 0, b: 1, c: 2, d: 0 });
});

test("an edge that closes a cycle counts for nothing, and an edge to a stranger is ignored", () => {
  const r = ranks(["a", "b"], [["a", "b"], ["b", "a"], ["a", "zz"]]);
  assert.deepEqual(r, { a: 0, b: 1 });
});

test("the goal is pinned to the last rank, alone, at the right", () => {
  const lay = layout([{ id: "a", band: "" }, { id: "b", band: "" }, { id: " goal", band: "" }],
                     [["a", "b"], ["b", " goal"]], { goal: " goal" });
  assert.equal(lay.ranks, 3);
  assert.equal(lay.boxes[" goal"]!.rank, 2);
  assert.ok(lay.boxes[" goal"]!.x > lay.boxes.b!.x && lay.boxes.b!.x > lay.boxes.a!.x);
});

test("barycentre ordering puts a task beside what it waits on", () => {
  // c (waits on b) is listed before d (waits on a); after ordering d sits with a, c with b
  const ids = ["a", "b", "c", "d"];
  const edges: [string, string][] = [["b", "c"], ["a", "d"]];
  const cols = order(ids, edges, ranks(ids, edges));
  assert.deepEqual(cols, [["a", "b"], ["d", "c"]]);
});

test("boxes never overlap, and a sub-goal's boxes stay inside its band", () => {
  const s = parseState(fixture("running"));
  const boxes = s.tasks.map((t) => ({ id: t.id, band: t.parent ?? "", h: t.forks.length ? 46 + 18 * t.forks.length : 46 }));
  boxes.push({ id: " goal", band: "", h: 60 });
  const lay = layout(boxes, [...s.edges.map(([a, b]) => [a, b] as [string, string]), ["ship", " goal"], ["logs", " goal"]], { goal: " goal" });
  const all = Object.values(lay.boxes);
  for (const p of all) for (const q of all) {
    if (p.id === q.id) continue;
    const apart = p.x + p.w <= q.x || q.x + q.w <= p.x || p.y + p.h <= q.y || q.y + q.h <= p.y;
    assert.ok(apart, `${p.id} overlaps ${q.id}`);
  }
  for (const band of lay.bands) {
    for (const p of all.filter((b) => b.band === band.id && b.id !== " goal")) { // the goal spans the bands
      assert.ok(p.y >= band.y0 && p.y + p.h <= band.y1, `${p.id} leaves band ${band.id}`);
    }
  }
  assert.deepEqual(lay.bands.map((b) => b.id), ["words", "routes", "api", ""]);
  assert.ok(lay.width > 0 && lay.height > 0);
  // ranks follow the needs: hello 0, bye/greet 1, farewell/docs 2, ship 3, goal 4
  assert.equal(lay.boxes.hello!.rank, 0);
  assert.equal(lay.boxes.ship!.rank, 3);
  assert.equal(lay.boxes[" goal"]!.rank, 4);
});

test("a plan with no edges still lays out, one column", () => {
  const lay = layout([{ id: "a", band: "" }, { id: "b", band: "" }], []);
  assert.equal(lay.ranks, 1);
  assert.notEqual(lay.boxes.a!.y, lay.boxes.b!.y);
  assert.deepEqual(layout([], []).boxes, {});
});

test("arrow keys move to the nearest box in the next rank, or the next by height in this one", () => {
  const s = parseState(fixture("running"));
  const lay = layout(s.tasks.map((t) => ({ id: t.id, band: t.parent ?? "" })), s.edges.map(([a, b]) => [a, b]));
  assert.equal(step(lay, "hello", "right"), lay.boxes.bye!.y < lay.boxes.greet!.y ? "bye" : "greet");
  assert.equal(step(lay, "hello", "left"), null);
  const col1 = ["bye", "greet"].sort((p, q) => lay.boxes[p]!.y - lay.boxes[q]!.y);
  assert.equal(step(lay, col1[0]!, "down"), col1[1]);
  assert.equal(step(lay, col1[1]!, "up"), col1[0]);
  assert.equal(step(lay, "nobody", "up"), null);
});

test("a narrow canvas lays the graph downward, a wide one across", () => {
  assert.equal(modeFor(320), "down");
  assert.equal(modeFor(400), "down");
  assert.equal(modeFor(559), "down");
  assert.equal(modeFor(560), "across");
  assert.equal(modeFor(1280), "across");
});

test("downward: waves are rows top to bottom, a row wraps at the width, the goal is last and centred", () => {
  const s = parseState(fixture("running"));
  const boxes = s.tasks.map((t) => ({ id: t.id, band: t.parent ?? "", w: 184, h: t.forks.length ? 48 + 20 * t.forks.length + 6 : 48 }));
  boxes.push({ id: " goal", band: "", w: 200, h: 66 });
  const edges: [string, string][] = [...s.edges.map(([a, b]) => [a, b] as [string, string]), ["ship", " goal"], ["logs", " goal"]];
  const lay = layout(boxes, edges, { goal: " goal", boxW: 184, boxH: 48, down: true, width: 320 });
  assert.equal(lay.down, true);
  assert.deepEqual(lay.bands, []); // no regions when narrow
  const all = Object.values(lay.boxes);
  // every box fits inside the width, and none overlaps another
  for (const p of all) assert.ok(p.x >= 16 && p.x + p.w <= 320, `${p.id} leaves the width`);
  for (const p of all) for (const q of all) {
    if (p.id === q.id) continue;
    const apart = p.x + p.w <= q.x || q.x + q.w <= p.x || p.y + p.h <= q.y || q.y + q.h <= p.y;
    assert.ok(apart, `${p.id} overlaps ${q.id}`);
  }
  // a later wave is lower: hello (0) above bye and greet (1), above ship (3), above the goal
  assert.ok(lay.boxes.hello!.y < lay.boxes.bye!.y && lay.boxes.bye!.y < lay.boxes.ship!.y && lay.boxes.ship!.y < lay.boxes[" goal"]!.y);
  // two boxes in one wave wrap under each other at 320, side by side at 600
  assert.notEqual(lay.boxes.bye!.y, lay.boxes.greet!.y);
  const wide = layout(boxes, edges, { goal: " goal", boxW: 184, boxH: 48, down: true, width: 600 });
  assert.equal(wide.boxes.bye!.y, wide.boxes.greet!.y);
  assert.equal(lay.boxes[" goal"]!.x, (320 - 200) / 2);
  assert.equal(lay.width, 320);
  assert.ok(lay.height > lay.boxes[" goal"]!.y + 66);
});

test("downward, the arrows walk the rows: down and up across the waves, left and right along one", () => {
  const s = parseState(fixture("running"));
  const boxes = s.tasks.map((t) => ({ id: t.id, band: t.parent ?? "" }));
  const lay = layout(boxes, s.edges.map(([a, b]) => [a, b]), { down: true, width: 600 });
  const first = step(lay, "hello", "down");
  assert.ok(first === "bye" || first === "greet");
  assert.equal(step(lay, "hello", "up"), null);
  const row1 = ["bye", "greet"].sort((p, q) => lay.boxes[p]!.x - lay.boxes[q]!.x);
  assert.equal(step(lay, row1[0]!, "right"), row1[1]);
  assert.equal(step(lay, row1[1]!, "left"), row1[0]);
  assert.equal(step(lay, row1[0]!, "up"), "hello");
});
