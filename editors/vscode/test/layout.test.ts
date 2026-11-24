import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";
import { curve, layout, modeFor, order, ranks, rounded, route, routeDown, spread, step, type Edge } from "../src/layout.ts";
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
  // each row in the middle of the width, as a column of cards down a page is: none left at the side
  for (const y of new Set(Object.values(wide.boxes).map((p) => p.y))) {
    const row = Object.values(wide.boxes).filter((p) => p.y === y);
    const left = Math.min(...row.map((p) => p.x)), right = Math.max(...row.map((p) => p.x + p.w));
    assert.ok(Math.abs(left - (600 - right)) <= 1, `the row at ${y} stands at the side`);
  }
  assert.equal(lay.boxes[" goal"]!.x, (320 - 200) / 2);
  assert.equal(lay.width, 320);
  assert.ok(lay.height > lay.boxes[" goal"]!.y + 66);
});

test("downward, a line runs in the gaps between rows, a wave's wrapped rows too: through no box but its two ends", () => {
  // four at once wrap two to a row at 680, one of them taller (its attempts) than the card beside it
  const boxes = [{ id: "a", band: "" }, { id: "b", band: "", h: 200 }, { id: "c", band: "" }, { id: "d", band: "" }, { id: "e", band: "" }, { id: "f", band: "" }, { id: "g", band: "" }];
  const edges: Edge[] = [["a", "e"], ["a", "f"], ["b", "e"], ["c", "f"], ["d", "e"], ["d", "f"], ["e", "g"], ["f", "g"]];
  const lay = layout(boxes, edges, { goal: "g", boxW: 200, boxH: 116, down: true, width: 680 });
  assert.notEqual(lay.boxes.a!.y, lay.boxes.c!.y, "the wave wraps");
  const all = Object.values(lay.boxes);
  for (const [a, b] of edges) {
    const p = lay.boxes[a]!, q = lay.boxes[b]!, pts = routeDown(lay, p, p.x + p.w / 2, q, q.x + q.w / 2, all);
    pts.slice(1).forEach(([x2, y2], i) => {
      const [x1, y1] = pts[i]!;
      for (const r of all.filter((r) => r !== p && r !== q)) {
        const inX = Math.max(Math.min(x1, x2), r.x + 1) <= Math.min(Math.max(x1, x2), r.x + r.w - 1);
        const inY = Math.max(Math.min(y1, y2), r.y + 1) <= Math.min(Math.max(y1, y2), r.y + r.h - 1);
        assert.ok(!(inX && inY), `${a}>${b} runs through ${r.id}`);
      }
    });
  }
  // a line out of a card shorter than its row sets out under the row: turning under its own card, it would run
  // through the taller one beside it
  const at = (id: string, x: number, y: number, h = 116) => ({ id, x, y, w: 200, h, rank: 0, band: "" });
  const rows = [at("a", 118, 16), at("b", 350, 16, 200), at("c", 582, 16), at("d", 118, 260), at("e", 350, 260), at("f", 582, 260), at("x", 118, 420)];
  const hand = { boxes: Object.fromEntries(rows.map((p) => [p.id, p])), bands: [], columns: [], width: 900, height: 552, ranks: 2, down: true };
  const out = routeDown(hand, hand.boxes.c!, 682, hand.boxes.x!, 218, rows);
  assert.ok(out.every(([, y], i) => i < 2 || y >= 216 + 8), `c>x turns inside b: ${JSON.stringify(out)}`);
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

test("a sub-goal's loose tasks stand side by side past `stack`, row by row; tied ones keep one column, and a nameless band's unless asked", () => {
  const five = ["a", "b", "c", "d", "e"].map((id) => ({ id, band: "s" }));
  const lay = layout([...five, { id: "g", band: "" }], five.map((b) => [b.id, "g"] as Edge), { goal: "g", boxW: 100, boxH: 40, gapX: 20, gapY: 10, padX: 0, padY: 0, stack: 3 });
  const at = (id: string) => [lay.boxes[id]!.x, lay.boxes[id]!.y];
  assert.deepEqual(five.map((b) => at(b.id)), [[0, 0], [120, 0], [0, 50], [120, 50], [0, 100]], "two side by side, three rows");
  assert.ok(five.every((b) => lay.boxes[b.id]!.rank === 0), "one rank still: nothing waits on another");
  assert.equal(lay.boxes.g!.x, 240, "the goal past both");
  // the arrows: across the row first, then on to the goal; down the column, the one in line
  assert.equal(step(lay, "a", "right"), "b");
  assert.equal(step(lay, "b", "right"), "g");
  assert.equal(step(lay, "b", "left"), "a");
  assert.equal(step(lay, "b", "down"), "d");
  assert.equal(step(lay, "c", "up"), "a");
  // a task that waits on another, or one in no sub-goal, keeps the column
  const tied = layout(five, [["a", "b"]], { boxW: 100, boxH: 40, gapX: 20, gapY: 10, padX: 0, padY: 0, stack: 3 });
  assert.deepEqual(["c", "d", "e"].map((id) => tied.boxes[id]!.x), [0, 0, 0]);
  const loose = layout(five.map((b) => ({ ...b, band: "" })), [], { boxW: 100, boxH: 40, gapX: 20, gapY: 10, padX: 0, padY: 0, stack: 3 });
  assert.ok(Object.values(loose.boxes).every((p) => p.x === 0));
  // a plan with no sub-goals in a canvas wider than tall: its loose tasks a block, not a tower in the middle
  const block = layout(five.map((b) => ({ ...b, band: "" })), [], { boxW: 100, boxH: 40, gapX: 20, gapY: 10, padX: 0, padY: 0, stack: 3, stackAll: true });
  assert.deepEqual(five.map((b) => block.boxes[b.id]!.x), [0, 120, 0, 120, 0]);
  // and two to four of them one row (the graph's `place`, at `stack: 1`), not a narrow tower of three
  const row = layout(five.slice(0, 3).map((b) => ({ ...b, band: "" })), [], { boxW: 100, boxH: 40, gapX: 20, gapY: 10, padX: 0, padY: 0, stack: 1, stackAll: true });
  assert.deepEqual(["a", "b", "c"].map((id) => [row.boxes[id]!.x, row.boxes[id]!.y]), [[0, 0], [120, 0], [240, 0]]);
  // as the three of one sub-goal (the planner's, which says the goal again) do, their lines still one trunk to the goal
  const one = layout([...five.slice(0, 3), { id: "g", band: "" }], five.slice(0, 3).map((b) => [b.id, "g"] as Edge), { goal: "g", boxW: 100, boxH: 40, gapX: 20, gapY: 10, padX: 0, padY: 0, stack: 1 });
  assert.deepEqual(["a", "b", "c"].map((id) => [one.boxes[id]!.x, one.boxes[id]!.y - one.boxes.a!.y]), [[0, 0], [120, 0], [240, 0]]);
  assert.ok(Object.values(layout(five, [], { boxW: 100, boxH: 40, padX: 0 }).boxes).every((p) => p.x === 0), "unset, a rank is one column");
  // a band with nothing past that rank stands in the next ranks' columns, so another band's rank 1 is not pushed
  // a card further out, leaving a hole
  const two = layout([...five.slice(0, 4), { id: "x", band: "t" }, { id: "y", band: "t" }], [["x", "y"]], { boxW: 100, boxH: 40, gapX: 20, gapY: 10, padX: 0, padY: 0, stack: 3 });
  assert.deepEqual(two.columns, [0, 120]);
  assert.deepEqual(["a", "b", "x", "y"].map((id) => two.boxes[id]!.x), [0, 120, 0, 120]);
  assert.equal(two.boxes.b!.rank, 0, "still the rank it is");
});

test("an edge across is square and in the gaps: along, down the gap before its target, in; round what is in its way", () => {
  // the next column: along its own height to the middle of the gap, down it, in at the target's height
  assert.deepEqual(route(100, 50, 132, 150, 32, 16, []), [[100, 50], [116, 50], [116, 150], [132, 150]]);
  // a column skipped, a box in the way at the source's height: down the first gap and along the target's
  const skip = [{ x: 132, y: 30, w: 100, h: 40 }];
  assert.deepEqual(route(100, 50, 264, 150, 32, 16, skip), [[100, 50], [116, 50], [116, 150], [264, 150]]);
  // in the way at both heights: along the row gap under the box in the way, which has room round it
  const both = [{ x: 132, y: 30, w: 100, h: 40 }, { x: 132, y: 86, w: 100, h: 200 }];
  const r = route(100, 50, 264, 50, 32, 16, both.slice(0, 1));
  assert.equal(r.length, 6);
  assert.ok(r[2]![1] === 30 - 14 || r[2]![1] === 70 + 14, `around the box with room: ${r[2]![1]}`);
  // boxes one over another 16 apart: the line takes the middle of their gap, never a box's border
  const tight = route(100, 50, 264, 50, 32, 16, both);
  assert.equal(tight[2]![1], 16, "over the box in the way, where there is room");
  assert.equal(route(100, 50, 264, 50, 32, 16, [...both, { x: 132, y: -100, w: 100, h: 116 }])[2]![1], 78, "else the middle of the row gap");
  // a box not in a later column is joined straight
  assert.deepEqual(route(300, 50, 132, 150, 32, 16, []), [[300, 50], [132, 150]]);
  // round a box in a one-row band, under its header: 14 under the box would run 6 px along the band's foot (a thin
  // block 8 under the box), so the line goes 14 under the band
  const band = [{ x: 0, y: 0, w: 400, h: 28 }, { x: 132, y: 30, w: 100, h: 40 }];
  assert.equal(route(100, 50, 264, 50, 32, 16, band)[2]![1], 84);
  assert.equal(route(100, 50, 264, 50, 32, 16, [...band, { x: 0, y: 77, w: 400, h: 2 }])[2]![1], 93);
  // drawn with each corner rounded, never wider than half a leg
  assert.equal(rounded([[0, 0], [16, 0], [16, 100], [32, 100]]), "M0,0 L8,0 Q16,0 16,8 L16,92 Q16,100 24,100 L32,100");
  assert.equal(rounded([[0, 0], [16, 0], [16, 4], [32, 4]]), "M0,0 L14,0 Q16,0 16,2 L16,2 Q16,4 18,4 L32,4");
});

test("a line inside a sub-goal past a card on its last row goes round it under it, inside the band: the band has the room", () => {
  const three = ["a", "b", "c"].map((id) => ({ id, band: "s" }));
  const chain: Edge[] = [["a", "b"], ["b", "c"]], o = { boxW: 100, boxH: 40, gapX: 32, gapY: 12, labelH: 20 };
  const plain = layout(three, chain, o), skip = layout(three, [...chain, ["a", "c"]], o);
  const band = skip.bands.find((b) => b.id === "s")!, b = skip.boxes.b!;
  assert.ok(band.y1 - band.y0 > plain.bands[0]!.y1 - plain.bands[0]!.y0, "no room was made");
  // what the graph routes it round: each box, the band's header row, and its foot, which a line is never drawn along
  const pts = route(skip.boxes.a!.x + 100, skip.boxes.a!.y + 20, skip.boxes.c!.x, skip.boxes.c!.y + 20, 32, 12,
                    [...Object.values(skip.boxes), { x: 0, y: band.y0, w: 500, h: 20 }, { x: 0, y: band.y1 - 1, w: 500, h: 2 }]);
  const low = Math.max(...pts.map(([, y]) => y));
  assert.ok(low > b.y + b.h && low < band.y1, `the line at ${low} is not inside the band's foot (${b.y + b.h} to ${band.y1})`);
});

test("lines into two cards never share a trunk where they meet: the one going further down stands left; one card's lines share its own", () => {
  // the running plan: bye (50) into farewell (150), and greet (150, beside farewell) into README (250), one gap
  const toFarewell = route(100, 50, 132, 150, 32, 16, []), toReadme = route(100, 150, 132, 250, 32, 16, []);
  assert.equal(toFarewell[1]![0], toReadme[1]![0], "routed alone, they turn at the same x: greet's line seems to run on into farewell");
  const alsoReadme = route(100, 50, 132, 250, 32, 16, []), far = route(100, 600, 132, 700, 32, 16, []);
  const [f, r, also, away] = spread([toFarewell, toReadme, alsoReadme, far], 12);
  assert.ok(r![1]![0] < f![1]![0] && f![1]![0] - r![1]![0] === 6, "6 px apart, README's left");
  assert.deepEqual([r![1]![0], r![2]![0]], [also![1]![0], also![2]![0]], "README's lines share its trunk");
  assert.equal(away![1]![0], 116, "a trunk with none beside it keeps the gap's middle");
  assert.deepEqual([f![0], f![3]], [toFarewell[0], toFarewell[3]], "the ports do not move");
  // lines out of one card into several: one trunk, the card's own, branching into each, not one a card side by side
  const fan = spread([route(100, 150, 132, 50, 32, 16, []), route(100, 150, 132, 150, 32, 16, []), route(100, 150, 132, 250, 32, 16, [])], 12);
  assert.equal(new Set(fan.flatMap((p) => p.length > 2 ? [p[1]![0]] : [])).size, 1);
  // more trunks than room: closer together, inside it
  const many = spread([0, 1, 2, 3].map((i) => route(100, 50 + i * 10, 132, 400 - i * 10, 32, 16, [])), 12).map((p) => p[1]![0]);
  assert.ok(Math.max(...many) - Math.min(...many) <= 12 && new Set(many).size === 4);
});

test("an edge is one curve, port to port: it leaves a card level and arrives level, across or downward", () => {
  // across: out of the right side at (200, 47), into the next card's left at (234, 163); its handles pull along x only
  assert.equal(curve(200, 47, 234, 163), "M200,47 C224,47 210,163 234,163");
  assert.equal(curve(200, 47, 500, 47), "M200,47 C350,47 350,47 500,47"); // a card two columns on: a longer, shallower curve; level, it is a straight line
  // downward: out of the foot and into the top, its handles along y
  assert.equal(curve(100, 94, 300, 160, true), "M100,94 C100,127 300,127 300,160");
  assert.equal(curve(100, 94, 100, 100, true), "M100,94 C100,110 100,84 100,100"); // close together it still leaves downward
  // a card behind its source: the same curve, wide enough to be seen to turn
  assert.equal(curve(500, 40, 300, 200), "M500,40 C600,40 200,200 300,200");
});
