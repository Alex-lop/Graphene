import assert from "node:assert/strict";
import { test } from "node:test";
import { KEYS } from "../src/graph/words.ts";
import { wrap } from "../src/graph/marks.ts";
import { CARD, CARD_TEXT, dotGap, FAR, fitPlan, fitView, FULL_FROM, FULL_KEEP, hold, ROW_TEXT, ROWS_FROM, ROWS_MOST, levelFor, miniFrame, miniSize, nearest, offScreen, onto, panTo, percent, switchK, TO_COMPACT, TO_FULL, wheelK,
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

test("a plan opens as whole cards where they fit at 11/12 or more, else as rows, fitted, never under 11 px", () => {
  const canvas = { w: 1280, h: 670 }, never = () => { throw new Error("the rows were not needed"); };
  // a few tasks: whole cards at 0.93, their smallest words over 11 px
  const some = fitPlan(canvas, { w: 1380, h: 600 }, never, 46);
  assert.equal(some.level, "full");
  assert.ok(Math.abs(some.k - 1280 / 1380) < 1e-9 && some.tx === 0 && Math.abs(some.ty - (624 - 600 * some.k) / 2) < 1e-9 && some.whole);
  assert.ok(FULL_FROM * CARD_TEXT >= 11 - 1e-9 && CARD_TEXT >= 12, "a whole card's smallest words are drawn at 11 px or more");
  // at the threshold, still whole; a hair under it, rows
  assert.equal(fitPlan({ w: 917, h: 2000 }, { w: 1000, h: 100 }, never).level, "full");
  assert.equal(fitPlan({ w: 916, h: 2000 }, { w: 1000, h: 100 }, () => ({ w: 700, h: 60 })).level, "compact");
  // twenty-six in a wide tab: whole cards would sit at a third, so rows, fitted to the width, in the middle above the foot
  const many = fitPlan({ w: 1440, h: 800 }, { w: 2618, h: 1982 }, () => ({ w: 1744, h: 784 }), 46);
  assert.equal(many.level, "compact");
  assert.ok(Math.abs(many.k - 1440 / 1744) < 1e-9 && many.tx === 0 && Math.abs(many.ty - (754 - 784 * many.k) / 2) < 1e-9 && many.whole);
  // rows that would fit at more than their own size are drawn at it, never blown up, and stay rows
  assert.equal(fitPlan({ w: 2600, h: 1400 }, { w: 2618, h: 1982 }, () => ({ w: 1744, h: 784 }), 46).k, ROWS_MOST);
  assert.equal(ROWS_MOST, 1);
  assert.equal(levelFor("compact", ROWS_MOST), "compact");
  // fitted again with whole cards on screen (a pane opened beside them), they hold down to FULL_KEEP
  assert.equal(fitPlan({ w: 780, h: 2000 }, { w: 1000, h: 100 }, never, 0, "full").level, "full");
  assert.equal(fitPlan({ w: 700, h: 2000 }, { w: 1000, h: 100 }, never, 0, "full").level, "full");
  assert.equal(fitPlan({ w: 699, h: 2000 }, { w: 1000, h: 100 }, () => ({ w: 700, h: 60 }), 0, "full").level, "compact");
  assert.equal(fitPlan({ w: 780, h: 2000 }, { w: 1000, h: 100 }, () => ({ w: 700, h: 60 }), 0, "compact").level, "compact");
  assert.ok(FULL_KEEP > TO_COMPACT && FULL_KEEP < FULL_FROM);
  // a Cursor tab beside its agent's chat (680 px), a pane beside the plan, hundreds of tasks: rows at the floor,
  // their titles at 11 px, larger than the pane (``whole`` false), at its top left; never blank bars
  assert.ok(ROWS_FROM * ROW_TEXT >= 11 - 1e-9 && ROWS_FROM > FAR, "a fitted row's title reads");
  for (const [room, rows] of [[{ w: 680, h: 780 }, { w: 1744, h: 784 }], [{ w: 440, h: 700 }, { w: 690, h: 300 }], [canvas, { w: 12000, h: 4000 }]] as const) {
    const fit = fitPlan(room, { w: 20000, h: 9000 }, () => rows, 46);
    assert.deepEqual(fit, { level: "compact", k: ROWS_FROM, tx: 0, ty: rows.h * ROWS_FROM <= room.h - 46 ? (room.h - 46 - rows.h * ROWS_FROM) / 2 : 0, whole: false });
  }
});

test("a fit just too tight for whole cards cuts the drawing's empty margin, evenly, to keep them; a looser one keeps it", () => {
  const rows = () => ({ w: 1100, h: 400 }), cut = () => ({ w: 28, h: 16 });
  // the running plan in a 1280 by 800 tab: 1228 by 721 with its margin, short of 11/12 by 11 px of height
  const tight = fitPlan({ w: 1280, h: 697 }, { w: 1228, h: 721 }, rows, 46, "compact", cut);
  assert.deepEqual([tight.level, tight.k, tight.whole], ["full", FULL_FROM, true]);
  assert.ok(Math.abs(tight.ty - (651 - 721 * FULL_FROM) / 2) < 1e-9 && tight.ty < 0 && tight.ty > -8, "its margin cut evenly, under its 8 px");
  assert.ok(tight.tx > 0, "in the middle across, where it has room");
  // without the margin to cut, rows; with room, all of it, as before
  assert.equal(fitPlan({ w: 1280, h: 697 }, { w: 1228, h: 721 }, rows, 46).level, "compact");
  assert.deepEqual(fitPlan({ w: 1440, h: 800 }, { w: 1228, h: 721 }, rows, 46, "compact", cut), fitPlan({ w: 1440, h: 800 }, { w: 1228, h: 721 }, rows, 46));
  // a plan whole cards do not hold even without their margin is rows, its margin kept
  assert.equal(fitPlan({ w: 1000, h: 697 }, { w: 1228, h: 721 }, rows, 46, "compact", cut).level, "compact");
});

test("a plan larger than its pane opens moved just enough to show the card that matters, its start kept where it can be", () => {
  const canvas = { w: 680, h: 500 }, drawing = { w: 1744, h: 784 }, k = ROWS_FROM, fit = { k, tx: 0, ty: 0 };
  // in view already: nothing moves, the plan's start and its sub-goals' titles stay on screen
  assert.deepEqual(onto(fit, canvas, drawing, { x: 400, y: 100, w: 168, h: 48 }), fit);
  // past the right edge: in by just enough to stand 24 px inside it
  const far = onto(fit, canvas, drawing, { x: 1200, y: 100, w: 168, h: 48 });
  assert.ok(Math.abs((1200 + 168) * k + far.tx - (680 - 24)) < 1e-9 && far.ty === 0);
  // below the foot: up; and never past the drawing's own edges
  const low = onto(fit, canvas, drawing, { x: 0, y: 760, w: 168, h: 24 });
  assert.equal(low.ty, 500 - 784 * k);
  assert.equal(onto(fit, canvas, drawing, { x: 1700, y: 0, w: 44, h: 48 }).tx, 680 - 1744 * k);
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

test("across a change of level a card covers as much of the screen, a row turned to reads, and the level holds", () => {
  // a row is much shorter than a card (its title alone): it turns wider on screen and its title larger, drawn at
  // 11 px or more where whole cards turn to rows
  assert.ok(14 * switchK(TO_COMPACT, "full", "compact") >= 11, "a row's title reads the moment it is a row");
  for (const [from, to, k] of [["full", "compact", TO_COMPACT - 0.001], ["compact", "full", TO_FULL + 0.001]] as const) {
    const k2 = switchK(k, from, to);
    const w = (CARD[to].w * k2) / (CARD[from].w * k), h = (CARD[to].h * k2) / (CARD[from].h * k);
    assert.ok(Math.abs(w * h - 1) < 1e-9, "the same area");
    assert.ok(Math.abs(w - 1) <= 0.45 && Math.abs(h - 1) <= 0.45, `no side jumps by half: ${w.toFixed(2)} by ${h.toFixed(2)}`);
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
  // the numbers the changelog gives a person, who reads the percent and not the scale: the floor, where the titles go, the ceiling
  assert.deepEqual([percent("compact", ZOOM_MIN), percent("compact", FAR), percent("full", ZOOM_MAX)], [12, 27, 300]);
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

test("a row's title takes two lines (marks.ts `wrap`): whole words on the first, the rest cut on the second", () => {
  const mono = (t: string) => t.length * 7;
  assert.deepEqual(wrap("greet route", 105, mono, 2), ["greet route"]);
  assert.deepEqual(wrap("orders table and its migration", 105, mono, 2), ["orders table", "and its migrat…"]);
  assert.deepEqual(wrap("repository reads and writes", 105, mono, 2), ["repository", "reads and…"], "cut at a whole word where one fills most of the line");
  assert.deepEqual(wrap("bye says goodbye", 105, mono, 2), ["bye says", "goodbye"], "the last word goes down, not off the row");
  assert.deepEqual(wrap("internationalisation everywhere", 105, mono, 2), ["internationali…"], "a first word too long for a line is cut");
  for (const lines of [wrap("a b c d e f g h i j k l m n o p q r s t", 30, mono, 2), wrap("  spaced   out   words  ", 40, mono, 2)]) {
    assert.ok(lines.length <= 2 && lines.every((l) => mono(l) <= 40 && l.trim() === l && l.length > 0), JSON.stringify(lines));
  }
});

test("the keys' list says each key the zoom answers", () => {
  const keys = KEYS.map(([k]) => k);
  for (const k of ["f", "- · =", "0", "wheel · drag", "double click"]) assert.ok(keys.includes(k), `no ${k} in the list`);
  assert.ok(keys.includes("+"), "+ still draws a task");
  assert.match(KEYS.find(([k]) => k === "wheel · drag")![1], /pinch/);
  assert.doesNotMatch(KEYS.map(([, what]) => what).join("\n"), /title alone/, "a row is its mark and its title, and far out its mark alone");
});
