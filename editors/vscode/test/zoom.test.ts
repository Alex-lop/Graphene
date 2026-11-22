import assert from "node:assert/strict";
import { test } from "node:test";
import { KEYS, twoLines } from "../src/graph/words.ts";
import { CARD, dotGap, FAR, fitPlan, fitView, FULL_FROM, hold, levelFor, miniFrame, miniSize, nearest, offScreen, panTo, percent, switchK, TO_COMPACT, TO_FULL, wheelK,
         ZOOM_MAX, ZOOM_MIN, zoomK } from "../src/graph/zoom.ts";

test("the zoom goes out to a fifth and in to three times; what is not a number is 1", () => {
  assert.equal(zoomK(0.05), 0.2);
  assert.equal(zoomK(0.5), 0.5);
  assert.equal(zoomK(1), 1);
  assert.equal(zoomK(5), 3);
  assert.equal(zoomK(Number.NaN), 1);
  assert.deepEqual([ZOOM_MIN, ZOOM_MAX], [0.2, 3]);
});

test("one move of the wheel is a quarter at most, a mouse's notch as a pinch's nudge, and stops at the bounds", () => {
  assert.ok(Math.abs(wheelK(1, 4) - Math.exp(-0.04)) < 1e-9, "a pinch's small move is taken as it is");
  assert.ok(wheelK(1, 100) > 0.79 && wheelK(1, 100) < 0.81, "a notch of 100 zooms out a fifth, not to a third");
  assert.ok(wheelK(1, -120) > 1.24 && wheelK(1, -120) < 1.25);
  assert.equal(wheelK(0.21, 100), 0.2);
  assert.equal(wheelK(2.9, -100), 3);
});

test("a fit is the largest scale that holds the whole drawing, never over 1, in the middle and clear of the foot", () => {
  // a small plan is not blown up: it sits in the middle of what is above the foot
  assert.deepEqual(fitView({ w: 1280, h: 670 }, { w: 812, h: 342 }, 46), { k: 1, tx: 234, ty: 141, whole: true });
  // a wide one is scaled to the width, a tall one to the height less the foot
  const wide = fitView({ w: 1280, h: 670 }, { w: 2560, h: 400 }, 46);
  assert.deepEqual(wide, { k: 0.5, tx: 0, ty: 212, whole: true });
  const tall = fitView({ w: 1280, h: 670 }, { w: 1000, h: 1248 }, 46);
  assert.deepEqual(tall, { k: 0.5, tx: 390, ty: 0, whole: true });
  assert.ok(tall.ty + 1248 * tall.k <= 670 - 46, "its foot is above the buttons");
  // one no scale can hold: the floor, and it says so
  const vast = fitView({ w: 1280, h: 670 }, { w: 9000, h: 4000 }, 46);
  assert.equal(vast.k, ZOOM_MIN);
  assert.equal(vast.whole, false);
  assert.equal(fitView({ w: 1280, h: 670 }, { w: 6400, h: 1000 }).whole, true, "at the floor exactly it still fits");
});

test("a plan opens as whole cards where they fit at 0.7 or more, else as rows, fitted; no scale may hold it", () => {
  const canvas = { w: 1280, h: 670 }, never = () => { throw new Error("the rows were not needed"); };
  // seven tasks: whole cards at three quarters
  const some = fitPlan(canvas, { w: 1700, h: 804 }, never, 46)!;
  assert.equal(some.level, "full");
  assert.ok(Math.abs(some.k - 1280 / 1700) < 1e-9 && some.tx === 0 && Math.abs(some.ty - (624 - 804 * some.k) / 2) < 1e-9);
  // at the threshold exactly, still whole; a hair under it, rows
  assert.equal(fitPlan({ w: 700, h: 2000 }, { w: 1000, h: 100 }, never)!.level, "full");
  // twenty-six: whole cards would sit at a third, so rows, fitted to the width, in the middle above the foot
  const many = fitPlan(canvas, { w: 2618, h: 1982 }, () => ({ w: 1744, h: 784 }), 46)!;
  assert.equal(many.level, "compact");
  assert.ok(Math.abs(many.k - 1280 / 1744) < 1e-9 && many.tx === 0 && Math.abs(many.ty - (624 - 784 * many.k) / 2) < 1e-9);
  assert.ok(many.k * 14 >= 9, "a row's title is drawn at 9 px or more there");
  // rows that fit at more than their own size are not blown up
  assert.equal(fitPlan({ w: 1920, h: 950 }, { w: 2618, h: 1982 }, () => ({ w: 1744, h: 784 }), 46)!.k, 1);
  // hundreds of tasks: not even rows fit at the floor
  assert.equal(fitPlan(canvas, { w: 20000, h: 9000 }, () => ({ w: 12000, h: 4000 }), 46), null);
});

test("whole cards turn to rows under 0.55 and rows to whole cards over 1.2; between the two a level holds", () => {
  assert.equal(levelFor("full", 0.56), "full");
  assert.equal(levelFor("full", TO_COMPACT), "full");
  assert.equal(levelFor("full", 0.54), "compact");
  assert.equal(levelFor("compact", 0.54), "compact");
  assert.equal(levelFor("compact", TO_FULL), "compact");
  assert.equal(levelFor("compact", 1.21), "full");
  for (const k of [0.6, 0.8, 1, 1.19]) { // the band both levels hold in: nothing flaps
    assert.equal(levelFor("full", k), "full");
    assert.equal(levelFor("compact", k), "compact");
  }
  assert.ok(FULL_FROM > TO_COMPACT, "a plan fitted as whole cards is not one step from rows");
  // rows are read from far well after they were turned to (switchK lands near 0.9), and before the floor
  assert.ok(FAR > ZOOM_MIN && FAR < switchK(TO_COMPACT, "full", "compact") - 0.3, `far at ${FAR}`);
});

test("across a change of level a card covers as much of the screen, no side moves by more than 15%, and the level holds", () => {
  for (const [from, to, k] of [["full", "compact", TO_COMPACT - 0.001], ["compact", "full", TO_FULL + 0.001]] as const) {
    const k2 = switchK(k, from, to);
    const w = (CARD[to].w * k2) / (CARD[from].w * k), h = (CARD[to].h * k2) / (CARD[from].h * k);
    assert.ok(Math.abs(w - 1) <= 0.15 && Math.abs(h - 1) <= 0.15, `${from} to ${to}: its width by ${w.toFixed(3)}, its height by ${h.toFixed(3)}`);
    assert.ok(Math.abs(w * h - 1) < 1e-9, "the same area");
    assert.equal(levelFor(to, k2), to, `${to} at ${k2.toFixed(3)} does not turn straight back`);
    // nor on the next move the same way, nor on one move back
    assert.equal(levelFor(to, wheelK(k2, from === "full" ? 100 : -100)), to);
    assert.equal(levelFor(to, wheelK(k2, from === "full" ? -100 : 100)), to);
  }
  assert.ok(Math.abs(switchK(switchK(0.5, "full", "compact"), "compact", "full") - 0.5) < 1e-9, "there and back is where it was");
  assert.equal(switchK(2.9, "full", "compact"), ZOOM_MAX, "within the bounds");
});

test("the percent a person reads is a card's size against a whole card at 100%: one number across both levels", () => {
  assert.equal(percent("full", 1), 100);
  assert.equal(percent("full", 0.62), 62);
  for (const [from, to, k] of [["full", "compact", 0.54], ["compact", "full", 1.21]] as const) {
    assert.equal(percent(to, switchK(k, from, to)), percent(from, k), `${from} at ${k} reads the same after it turns to ${to}`);
  }
  assert.ok(percent("compact", 0.3) < percent("compact", 0.6) && percent("compact", 1.2) < percent("full", 1), "it rises all the way in");
});

test("a pan never loses the drawing: a larger one keeps to the edges, a smaller one stays inside where it was put", () => {
  const canvas = { w: 1000, h: 600 }, big = { w: 2000, h: 1200 }, small = { w: 400, h: 300 };
  assert.deepEqual(hold({ k: 1, tx: 50, ty: 50 }, canvas, big), { k: 1, tx: 0, ty: 0 });
  assert.deepEqual(hold({ k: 1, tx: -5000, ty: -5000 }, canvas, big), { k: 1, tx: -1000, ty: -600 });
  assert.deepEqual(hold({ k: 1, tx: -300, ty: -200 }, canvas, big), { k: 1, tx: -300, ty: -200 });
  assert.deepEqual(hold({ k: 1, tx: 120, ty: 80 }, canvas, small), { k: 1, tx: 120, ty: 80 }, "not pulled to the middle");
  assert.deepEqual(hold({ k: 1, tx: -40, ty: 900 }, canvas, small), { k: 1, tx: 0, ty: 300 });
  assert.deepEqual(hold({ k: 9, tx: -900, ty: -900 }, canvas, small), { k: 3, tx: -200, ty: -300 }, "a scale past the bounds is brought in first");
});

test("the card a change of level holds still is the one under the point, else the nearest", () => {
  const boxes = [{ id: "a", x: 0, y: 0, w: 100, h: 40 }, { id: "b", x: 200, y: 0, w: 100, h: 40 }, { id: "c", x: 0, y: 200, w: 100, h: 40 }];
  assert.equal(nearest(boxes, 250, 20)?.id, "b");
  assert.equal(nearest(boxes, 140, 20)?.id, "a"); // 40 from a, 60 from b
  assert.equal(nearest(boxes, 30, 150)?.id, "c");
  assert.equal(nearest([], 0, 0), undefined);
});

test("the canvas's dots thin out as the plan shrinks, and never crowd", () => {
  assert.equal(dotGap(1), 22);
  assert.equal(dotGap(3), 66);
  assert.equal(dotGap(0.5), 22); // every other one
  assert.equal(dotGap(0.25), 22); // one in four
  for (const k of [0.2, 0.3, 0.45, 0.6, 0.72, 0.9]) assert.ok(dotGap(k) >= 16 && dotGap(k) < 32, `${k}: ${dotGap(k)}`);
  assert.equal(dotGap(0), 22);
});

test("the minimap is the drawing's shape within 180 by 120; its frame is the part on screen; a click pans there", () => {
  assert.deepEqual(miniSize({ w: 2618, h: 1982 }), { w: 159, h: 120 });
  assert.deepEqual(miniSize({ w: 3600, h: 400 }), { w: 180, h: 20 });
  const canvas = { w: 1280, h: 670 }, drawing = { w: 2618, h: 1982 };
  // at 1:1 from the corner: the canvas's own size; panned and zoomed, in the drawing's units
  assert.deepEqual(miniFrame({ k: 1, tx: 0, ty: 0 }, canvas, drawing), { x: 0, y: 0, w: 1280, h: 670 });
  assert.deepEqual(miniFrame({ k: 2, tx: -400, ty: -200 }, canvas, drawing), { x: 200, y: 100, w: 640, h: 335 });
  // cut to the drawing where the canvas shows past its edge
  assert.deepEqual(miniFrame({ k: 0.5, tx: 100, ty: 0 }, { w: 1280, h: 2000 }, drawing), { x: 0, y: 0, w: 2360, h: 1982 });
  assert.equal(offScreen({ k: 1, tx: 0, ty: 0 }, canvas, drawing), true);
  const whole = fitView(canvas, drawing, 46);
  assert.equal(offScreen(whole, canvas, drawing), false, "a fitted plan is all on screen: no minimap");
  assert.equal(offScreen({ ...whole, tx: -50 }, canvas, drawing), true);
  // a click on a point of the drawing puts that point in the canvas's middle
  const z = panTo(1309, 991, 1, canvas);
  assert.deepEqual(z, { k: 1, tx: -669, ty: -656 });
  const f = miniFrame(z, canvas, drawing);
  assert.deepEqual([f.x + f.w / 2, f.y + f.h / 2], [1309, 991]);
});

test("a row's title takes two lines: whole words on the first, the rest cut on the second", () => {
  const mono = (t: string) => t.length * 7;
  assert.deepEqual(twoLines("greet route", 105, mono), ["greet route"]);
  assert.deepEqual(twoLines("orders table and its migration", 105, mono), ["orders table", "and its migrat…"]);
  assert.deepEqual(twoLines("repository reads and writes", 105, mono), ["repository", "reads and writ…"]);
  assert.deepEqual(twoLines("bye says goodbye", 105, mono), ["bye says", "goodbye"], "the last word goes down, not off the row");
  assert.deepEqual(twoLines("internationalisation everywhere", 105, mono), ["internationali…"], "a first word too long for a line is cut");
  for (const lines of [twoLines("a b c d e f g h i j k l m n o p q r s t", 30, mono), twoLines("  spaced   out   words  ", 40, mono)]) {
    assert.ok(lines.length <= 2 && lines.every((l) => mono(l) <= 40 && l.trim() === l && l.length > 0), JSON.stringify(lines));
  }
});

test("the keys' list says each key the zoom answers", () => {
  const keys = KEYS.map(([k]) => k);
  for (const k of ["f", "- · =", "0", "wheel · drag", "double click"]) assert.ok(keys.includes(k), `no ${k} in the list`);
  assert.ok(keys.includes("+"), "+ still draws a task");
  assert.match(KEYS.find(([k]) => k === "wheel · drag")![1], /pinch/);
});
