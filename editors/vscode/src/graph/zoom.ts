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

/** A card at each level: whole (its files, its check, its status, its attempts), and the row it is cut down
 *  to when the plan is read from afar (its state's mark, its title, and what is news). */
export const CARD: Record<Level, Size> = { full: { w: 220, h: 84 }, compact: { w: 152, h: 44 } };
/** A fit keeps whole cards down to this scale: under it nobody reads them, and the plan is fitted as rows. */
export const FULL_FROM = 0.7;
/** Zooming: whole cards turn to rows under the first, rows to whole cards over the second. */
export const TO_COMPACT = 0.55, TO_FULL = 1.2;

/** The level after a zoom to ``k``. Between the two thresholds a level holds, so nothing flaps at either. */
export const levelFor = (level: Level, k: number): Level =>
  (level === "full" ? (k < TO_COMPACT ? "compact" : "full") : k > TO_FULL ? "full" : "compact");

/** How many times its drawn size a card of one level is, against the other, to cover as much of the screen. */
const ratio = (from: Size, to: Size) => Math.sqrt((from.w * from.h) / (to.w * to.h));

/** The scale across a change of level: the card covers as much of the screen after as before, so neither of
 *  its sides moves by more than about 15%, and the scale lands well inside the level it turned to. */
export const switchK = (k: number, from: Level, to: Level) => zoomK(k * ratio(CARD[from], CARD[to]));

/** The zoom as a person reads it: a card's size on screen against a whole card at its own size. One number
 *  across both levels: it falls all the way out and rises all the way in. */
export const percent = (level: Level, k: number) => Math.round((100 * k) / ratio(CARD.full, CARD[level]));

/** The scale and the place at which a drawing sits whole in its canvas, in the middle and clear of ``foot`` px
 *  at the canvas's foot (the zoom's buttons, the legend): the largest scale that fits, never over 1 (a small
 *  plan is not blown up). ``whole`` is false when even the smallest scale cannot hold it. */
export function fitView(canvas: Size, drawing: Size, foot = 0): Zoom & { whole: boolean } {
  const h = Math.max(1, canvas.h - foot);
  const want = Math.min(1, canvas.w / Math.max(1, drawing.w), h / Math.max(1, drawing.h));
  const k = Math.max(ZOOM_MIN, want);
  return { k, tx: Math.max(0, (canvas.w - drawing.w * k) / 2), ty: Math.max(0, (h - drawing.h * k) / 2), whole: want >= ZOOM_MIN };
}

/** How a plan opens in its pane: as whole cards where they fit at a scale they read at, else as rows, fitted;
 *  null when not even rows fit at the smallest scale. ``rows`` (the plan's size laid out as rows) is asked for
 *  only when it is needed. */
export function fitPlan(canvas: Size, full: Size, rows: () => Size, foot = 0): (Zoom & { level: Level }) | null {
  const whole = fitView(canvas, full, foot);
  if (whole.k >= FULL_FROM) return { level: "full", k: whole.k, tx: whole.tx, ty: whole.ty };
  const far = fitView(canvas, rows(), foot);
  return far.whole ? { level: "compact", k: far.k, tx: far.tx, ty: far.ty } : null;
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
