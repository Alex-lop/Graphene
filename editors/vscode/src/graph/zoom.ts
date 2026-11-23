// The graph's zoom, as numbers: how far it goes, the scale at which a plan sits whole in its pane, the two
// levels of detail and when one turns to the other, and the minimap's measures. Pure: sizes in, numbers out.

export type Level = "full" | "compact";
export type Size = { w: number; h: number };
export type Zoom = { k: number; tx: number; ty: number };
type Rect = { x: number; y: number; w: number; h: number };

/** The zoom's bounds: out to a fifth, where a plan of hundreds is still a shape, in to three times. */
export const ZOOM_MIN = 0.2, ZOOM_MAX = 3;
export const zoomK = (k: number) => (Number.isFinite(k) ? Math.min(ZOOM_MAX, Math.max(ZOOM_MIN, k)) : 1);

/** One move of the wheel (with ⌘ or Ctrl) or of a pinch: a quarter in or out at most, as a button's step is,
 *  however far a mouse says its notch turned. */
export const wheelK = (k: number, deltaY: number) => zoomK(k * Math.exp(-Math.max(-22, Math.min(22, deltaY)) * 0.01));

/** A card at each level: whole (its title on two lines, its files, its status and its act, its check; its
 *  attempts make it taller), and the row it is cut down to when the plan is read from afar (its state's mark, its
 *  title on two lines, about 32 characters, and what is news). */
export const CARD: Record<Level, Size> = { full: { w: 200, h: 116 }, compact: { w: 168, h: 48 } };
/** A whole card's smallest words, in px at the drawing's own size: its files, its status, its check. */
export const CARD_TEXT = 12;
/** A fit keeps whole cards down to this scale, where a card's smallest words are still drawn at 11 px: under
 *  it nobody reads them, and the plan is fitted as rows. */
export const FULL_FROM = 11 / CARD_TEXT;
/** Fitted again with whole cards on screen (a pane opened beside them, a task chosen from Home), they stay whole
 *  down to this: the card the person asked to see keeps its files and its check. */
export const FULL_KEEP = 0.7;
/** Rows a fit draws no larger than their own size: a plan that has room enough is whole cards, and rows blown
 *  up past their size are only big, with nothing more in them. Under TO_FULL, so a fitted plan stays rows. */
export const ROWS_MOST = 1;
/** A row's title, in px at the drawing's own size. */
export const ROW_TEXT = 14;
/** Nor smaller than this, where a row's title is still drawn at 11 px: a plan too big to read whole at it (a
 *  Cursor tab beside its agent's chat, a pane open beside it) opens at it on the card that matters, the rest a pan
 *  away. Under it a fitted plan was blank bars. */
export const ROWS_FROM = 11 / ROW_TEXT;
/** Zooming: whole cards turn to rows under the first, rows to whole cards over the second. */
export const TO_COMPACT = 0.55, TO_FULL = 1.2;

/** Rows drawn smaller than this are read from far: nobody reads a title there, so the page drops it and lets
 *  the row's fill and what wants the person say the plan. */
export const FAR = 0.45;

/** The level after a zoom to ``k``. Between the two thresholds a level holds, so nothing flaps at either. */
export const levelFor = (level: Level, k: number): Level =>
  (level === "full" ? (k < TO_COMPACT ? "compact" : "full") : k > TO_FULL ? "full" : "compact");

/** How many times its drawn size a card of one level is, against the other, to cover as much of the screen. */
const ratio = (from: Size, to: Size) => Math.sqrt((from.w * from.h) / (to.w * to.h));

/** The scale across a change of level: the card covers as much of the screen after as before, and the scale lands
 *  well inside the level it turned to. A row is its title alone, so it is wider and shorter than its card on screen,
 *  by under half either way. */
export const switchK = (k: number, from: Level, to: Level) => zoomK(k * ratio(CARD[from], CARD[to]));

/** The zoom as a person reads it: a card's size on screen against a whole card at its own size. One number
 *  across both levels: it falls all the way out and rises all the way in. */
export const percent = (level: Level, k: number) => Math.round((100 * k) / ratio(CARD.full, CARD[level]));

/** The scale and the place at which a drawing sits whole in its canvas, in the middle and clear of ``foot`` px
 *  at the canvas's foot (the zoom's buttons, the legend): the largest scale that fits, never over ``most`` (a
 *  small plan is not blown up past it), nor under ``least``. ``whole`` is false when it cannot hold it at ``least``:
 *  it is then at its top left along each side it overflows. */
export function fitView(canvas: Size, drawing: Size, foot = 0, most = 1, least = ZOOM_MIN): Zoom & { whole: boolean } {
  const h = Math.max(1, canvas.h - foot);
  const want = Math.min(most, canvas.w / Math.max(1, drawing.w), h / Math.max(1, drawing.h));
  const k = Math.max(least, want);
  return { k, tx: Math.max(0, (canvas.w - drawing.w * k) / 2), ty: Math.max(0, (h - drawing.h * k) / 2), whole: want >= least };
}

/** How a plan opens in its pane: as whole cards where they fit at a scale they read at (``keep``: the level on
 *  screen, which whole cards hold down to FULL_KEEP), else as rows, fitted and drawn no larger than their own size
 *  nor smaller than ROWS_FROM (``whole`` false: the plan is larger than its pane). ``rows`` (the plan's size laid
 *  out as rows) is asked for only when it is needed. ``cut``: how much of a level's drawing is empty margin round
 *  the plan, which a fit just too tight for that level may cut, evenly, so as to keep it (a laptop's tab opens the
 *  running plan as whole cards, not as rows for want of 10 px of nothing); a looser fit keeps all of it. ``least``:
 *  the rows' floor, which a fit the person asks for (`f`) lowers to the zoom's own, to show the whole plan. */
export function fitPlan(canvas: Size, full: Size, rows: () => Size, foot = 0, keep: Level = "compact",
                        cut: (l: Level) => Size = () => ({ w: 0, h: 0 }), least = ROWS_FROM): Zoom & { level: Level; whole: boolean } {
  const fits = (l: Level, size: Size, least: number) => {
    const z = fitView(canvas, size, foot, l === "full" ? 1 : ROWS_MOST, least), c = cut(l);
    if (z.whole || !fitView(canvas, { w: size.w - c.w, h: size.h - c.h }, foot, 1, least).whole) return z;
    return { k: least, tx: (canvas.w - size.w * least) / 2, ty: (Math.max(1, canvas.h - foot) - size.h * least) / 2, whole: true };
  };
  const whole = fits("full", full, keep === "full" ? FULL_KEEP : FULL_FROM);
  return whole.whole ? { level: "full", ...whole } : { level: "compact", ...fits("compact", rows(), least) };
}

/** A fit larger than its canvas, moved just enough to bring a box of the drawing (the card that matters) ``margin``
 *  px inside the canvas, and held to it: the plan's start and its sub-goals' titles stay in view where they can. */
export function onto(z: Zoom, canvas: Size, drawing: Size, b: Rect, margin = 24): Zoom {
  const along = (t: number, room: number, at: number, len: number) => {
    const lo = at * z.k + t, hi = (at + len) * z.k + t;
    return hi > room - margin ? t - (hi - room + margin) : lo < margin ? t - lo + margin : t;
  };
  return hold({ k: z.k, tx: along(z.tx, canvas.w, b.x, b.w), ty: along(z.ty, canvas.h, b.y, b.h) }, canvas, drawing);
}

/** A pan never loses the drawing: one larger than the canvas stays against an edge at most, a smaller one
 *  stays inside it, wherever it was put. */
export function hold(z: Zoom, canvas: Size, drawing: Size): Zoom {
  const k = zoomK(z.k);
  const along = (t: number, room: number, len: number) => (len <= room ? Math.min(Math.max(0, t), room - len) : Math.min(0, Math.max(room - len, t)));
  return { k, tx: along(z.tx, canvas.w, drawing.w * k), ty: along(z.ty, canvas.h, drawing.h * k) };
}

/** The box under a point of the drawing, else the nearest to it: the card a change of level holds still. */
export function nearest<T extends Rect>(boxes: readonly T[], x: number, y: number): T | undefined {
  let best: T | undefined, least = Infinity;
  for (const b of boxes) {
    const dx = Math.max(b.x - x, 0, x - (b.x + b.w)), dy = Math.max(b.y - y, 0, y - (b.y + b.h));
    if (dx * dx + dy * dy < least) { least = dx * dx + dy * dy; best = b; }
  }
  return best;
}

/** The canvas's dots: 22 px apart at the drawing's own size and moving with it; as it shrinks every other one
 *  is dropped, so they never crowd to noise. */
export function dotGap(k: number): number {
  let gap = 22 * (k > 0 ? k : 1);
  while (gap < 16) gap *= 2;
  return gap;
}

/** The minimap's size for a drawing: the drawing's shape, within 180 by 120 px. */
export function miniSize(drawing: Size, max: Size = { w: 180, h: 120 }): Size {
  const s = Math.min(max.w / Math.max(1, drawing.w), max.h / Math.max(1, drawing.h));
  return { w: Math.round(drawing.w * s), h: Math.round(drawing.h * s) };
}

/** The part of the drawing on screen, in the drawing's own units and cut to it: the minimap's frame. */
export function miniFrame(z: Zoom, canvas: Size, drawing: Size): Rect {
  const x = Math.max(0, -z.tx / z.k), y = Math.max(0, -z.ty / z.k);
  const x1 = Math.min(drawing.w, (canvas.w - z.tx) / z.k), y1 = Math.min(drawing.h, (canvas.h - z.ty) / z.k);
  return { x, y, w: Math.max(0, x1 - x), h: Math.max(0, y1 - y) };
}

/** Part of the drawing is off screen: the minimap has something to say. */
export function offScreen(z: Zoom, canvas: Size, drawing: Size): boolean {
  const f = miniFrame(z, canvas, drawing);
  return f.w < drawing.w - 1 || f.h < drawing.h - 1;
}

/** The pan that puts a point of the drawing in the canvas's middle: a click or a drag in the minimap. */
export const panTo = (x: number, y: number, k: number, canvas: Size): Zoom => ({ k, tx: canvas.w / 2 - x * k, ty: canvas.h / 2 - y * k });
