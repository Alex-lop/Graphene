// The graph's layout, as the cockpit draws it: left to right by the longest chain of needs, the goal last
// at the right, sub-goals as bands top to bottom, and in each column the order that crosses the fewest
// arrows (barycentre sweeps). Pure: boxes in, coordinates out.

export interface Box {
  id: string;
  band: string; // the sub-goal the box sits under; "" for none
  w?: number;
  h?: number;
}

export type Edge = [string, string]; // a must land before b

export interface Placed {
  id: string;
  x: number;
  y: number;
  w: number;
  h: number;
  rank: number;
  band: string;
}

export interface Band {
  id: string;
  y0: number;
  y1: number;
}

export interface Layout {
  boxes: Record<string, Placed>;
  bands: Band[];
  columns: number[]; // each rank's left x (its top y when laid out downward)
  width: number;
  height: number;
  ranks: number;
  down: boolean; // ranks go top to bottom, as rows, instead of left to right
}

export interface Options {
  boxW?: number;
  boxH?: number;
  gapX?: number;
  gapY?: number;
  bandGap?: number;
  padX?: number;
  padY?: number;
  labelH?: number; // room at the top of a named band for its label
  goal?: string | null; // a box pinned to the last rank, alone
  sweeps?: number;
  /** Lay the ranks out as rows, top to bottom, each row's boxes left to right and wrapping at ``width``
   *  (the canvas's width): the narrow drawing, with no bands. */
  down?: boolean;
  width?: number;
}

const D = { boxW: 180, boxH: 46, gapX: 70, gapY: 12, bandGap: 28, padX: 16, padY: 16, labelH: 0, sweeps: 4 };

/** The narrow drawing's rule: under this many pixels across, the graph is laid out downward. */
export const NARROW = 560;

/** How a canvas this wide draws the graph: left to right, or downward with waves as rows. */
export const modeFor = (width: number): "across" | "down" => (width < NARROW ? "down" : "across");

/** Each box's rank: the longest chain of edges before it; an edge that closes a cycle counts for nothing. */
export function ranks(ids: string[], edges: Edge[]): Record<string, number> {
  const known = new Set(ids);
  const out = new Map<string, string[]>(ids.map((id) => [id, []]));
  for (const [a, b] of edges) if (known.has(a) && known.has(b) && a !== b) out.get(a)!.push(b);
  // drop back edges by a depth-first walk in the given order, as a cockpit's `_split` does
  const colour = new Map<string, number>(); // 1 on the stack, 2 done
  const forward = new Map<string, string[]>(ids.map((id) => [id, []]));
  const visit = (v: string) => {
    colour.set(v, 1);
    for (const w of out.get(v) ?? []) {
      const c = colour.get(w);
      if (c === 1) continue; // closes a cycle
      forward.get(v)!.push(w);
      if (!c) visit(w);
    }
    colour.set(v, 2);
  };
  for (const id of ids) if (!colour.has(id)) visit(id);
  const rank: Record<string, number> = {};
  const memo = new Map<string, number>();
  const into = new Map<string, string[]>(ids.map((id) => [id, []]));
  for (const [a, bs] of forward) for (const b of bs) into.get(b)!.push(a);
  const depth = (v: string): number => {
    const seen = memo.get(v);
    if (seen !== undefined) return seen;
    memo.set(v, 0);
    const d = Math.max(0, ...(into.get(v) ?? []).map((u) => depth(u) + 1));
    memo.set(v, d);
    return d;
  };
  for (const id of ids) rank[id] = depth(id);
  return rank;
}

/** Order the boxes of each rank by the mean position of their neighbours in the rank before (then after),
 *  a few sweeps each way; ties keep the given order. */
export function order(ids: string[], edges: Edge[], rank: Record<string, number>, sweeps = D.sweeps): string[][] {
  const most = ids.length ? Math.max(...ids.map((id) => rank[id] ?? 0)) : -1;
  const cols: string[][] = Array.from({ length: most + 1 }, () => []);
  for (const id of ids) cols[rank[id] ?? 0]!.push(id);
  const before = new Map<string, string[]>(ids.map((id) => [id, []]));
  const after = new Map<string, string[]>(ids.map((id) => [id, []]));
  for (const [a, b] of edges) {
    if (!before.has(a) || !before.has(b)) continue;
    if ((rank[a] ?? 0) < (rank[b] ?? 0)) { before.get(b)!.push(a); after.get(a)!.push(b); }
  }
  const pos = new Map<string, number>();
  const settle = () => cols.forEach((col) => col.forEach((id, i) => pos.set(id, i)));
  settle();
  const sort = (col: string[], of: Map<string, string[]>) => {
    const key = new Map(col.map((id, i) => {
      const ns = (of.get(id) ?? []).map((n) => pos.get(n) ?? 0);
      return [id, ns.length ? ns.reduce((s, p) => s + p, 0) / ns.length : i] as const;
    }));
    col.sort((p, q) => (key.get(p)! - key.get(q)!) || (pos.get(p)! - pos.get(q)!));
  };
  for (let s = 0; s < sweeps; s++) {
    for (let k = 1; k < cols.length; k++) { sort(cols[k]!, before); settle(); }
    for (let k = cols.length - 2; k >= 0; k--) { sort(cols[k]!, after); settle(); }
  }
  return cols;
}

export function layout(boxes: Box[], edges: Edge[], opts: Options = {}): Layout {
  const o = { ...D, ...opts };
  const ids = boxes.map((b) => b.id);
  const by = new Map(boxes.map((b) => [b.id, b]));
  const goal = o.goal && by.has(o.goal) ? o.goal : null;
  const tasks = ids.filter((id) => id !== goal);
  const rank = ranks(tasks, edges.filter(([a, b]) => a !== goal && b !== goal));
  const last = tasks.length ? Math.max(...tasks.map((id) => rank[id] ?? 0)) + 1 : 0;
  if (goal) rank[goal] = last;
  const cols = order(tasks, edges, rank);
  if (goal) cols.push([goal]);
  if (o.down) return downward(cols, by, goal, o);
  // bands in the order the boxes name them; the goal sits in its own band at the bottom-right? No: the
  // goal spans every band, so it is placed last, centred on the whole height
  const bandIds: string[] = [];
  for (const b of boxes) if (b.id !== goal && !bandIds.includes(b.band)) bandIds.push(b.band);
  // rows: in each band, each rank's boxes stack top to bottom in their order
  const rowOf = new Map<string, number>();
  const bandRows = new Map<string, number>(bandIds.map((b) => [b, 0]));
  for (const col of cols) {
    const seen = new Map<string, number>();
    for (const id of col) {
      if (id === goal) continue;
      const band = by.get(id)!.band;
      const r = seen.get(band) ?? 0;
      rowOf.set(id, r);
      seen.set(band, r + 1);
      bandRows.set(band, Math.max(bandRows.get(band) ?? 0, r + 1));
    }
  }
  const colW = cols.map((col) => Math.max(o.boxW, ...col.map((id) => by.get(id)!.w ?? o.boxW)));
  const columns: number[] = [];
  let x = o.padX;
  for (const w of colW) { columns.push(x); x += w + o.gapX; }
  const width = Math.max(x - o.gapX + o.padX, o.padX * 2);
  // row heights per band: a row is as tall as its tallest box
  const rowH = new Map<string, number[]>();
  for (const band of bandIds) rowH.set(band, Array.from({ length: bandRows.get(band) ?? 0 }, () => o.boxH));
  for (const id of tasks) {
    const b = by.get(id)!;
    const hs = rowH.get(b.band)!;
    const r = rowOf.get(id) ?? 0;
    hs[r] = Math.max(hs[r] ?? o.boxH, b.h ?? o.boxH);
  }
  const bands: Band[] = [];
  const bandTop = new Map<string, number>();
  let y = o.padY;
  for (const band of bandIds) {
    const hs = rowH.get(band)!;
    const tall = hs.reduce((s, h) => s + h, 0) + Math.max(0, hs.length - 1) * o.gapY;
    const label = band ? o.labelH : 0; // a nameless band has no label to make room for
    bandTop.set(band, y + label);
    bands.push({ id: band, y0: y - o.gapY / 2, y1: y + label + tall + o.gapY / 2 });
    y += label + tall + o.bandGap;
  }
  const height = Math.max(y - o.bandGap + o.padY, o.padY * 2 + o.boxH);
  const placed: Record<string, Placed> = {};
  for (let k = 0; k < cols.length; k++) {
    for (const id of cols[k]!) {
      const b = by.get(id)!;
      const w = b.w ?? o.boxW;
      const h = b.h ?? o.boxH;
      if (id === goal) {
        placed[id] = { id, x: columns[k]!, y: Math.max(o.padY, (height - h) / 2), w, h, rank: k, band: "" };
        continue;
      }
      const hs = rowH.get(b.band)!;
      const r = rowOf.get(id) ?? 0;
      const top = (bandTop.get(b.band) ?? o.padY) + hs.slice(0, r).reduce((s, hh) => s + hh + o.gapY, 0);
      placed[id] = { id, x: columns[k]!, y: top, w, h, rank: k, band: b.band };
    }
  }
  return { boxes: placed, bands, columns, width, height, ranks: cols.length, down: false };
}

/** Waves as rows: each rank's boxes side by side, wrapping when the row would pass ``width``; the goal
 *  in the last row, centred. A band is a tint on its boxes here, not a region, so ``bands`` is empty. */
function downward(cols: string[][], by: Map<string, Box>, goal: string | null, o: typeof D & Options): Layout {
  const maxW = Math.max(o.width ?? Infinity, o.padX * 2 + o.boxW);
  const gap = 16; // between boxes in a row
  const rankGap = 44; // between rows: room for the arrows
  const placed: Record<string, Placed> = {};
  const columns: number[] = [];
  let y = o.padY;
  let widest = o.padX * 2 + o.boxW;
  for (let k = 0; k < cols.length; k++) {
    columns.push(y);
    let x = o.padX, rowH = 0;
    for (const id of cols[k]!) {
      const b = by.get(id)!;
      const w = b.w ?? o.boxW, h = b.h ?? o.boxH;
      if (x > o.padX && x + w > maxW - o.padX) { y += rowH + o.gapY; x = o.padX; rowH = 0; } // wrap
      placed[id] = { id, x, y, w, h, rank: k, band: id === goal ? "" : b.band };
      x += w + gap;
      rowH = Math.max(rowH, h);
      widest = Math.max(widest, x - gap + o.padX);
    }
    y += rowH + rankGap;
  }
  const width = Number.isFinite(maxW) ? Math.max(maxW, widest) : widest;
  if (goal && placed[goal]) placed[goal]!.x = Math.max(o.padX, (width - placed[goal]!.w) / 2);
  const height = Math.max(y - rankGap + o.padY, o.padY * 2 + o.boxH);
  return { boxes: placed, bands: [], columns, width, height, ranks: cols.length, down: true };
}

/** The box an arrow key lands on from ``from``: along the ranks (right/left across, down/up when the
 *  layout runs downward) the nearest in the next/previous rank; within a rank, the next one along.
 *  Null when there is none. */
export function step(lay: Layout, from: string, key: "left" | "right" | "up" | "down"): string | null {
  const here = lay.boxes[from];
  if (!here) return null;
  const all = Object.values(lay.boxes);
  // the axis a rank runs along: y across, x downward
  const along = lay.down ? (p: Placed) => p.x + p.w / 2 : (p: Placed) => p.y + p.h / 2;
  const toNextRank = lay.down ? key === "down" || key === "up" : key === "left" || key === "right";
  const forward = key === "right" || key === "down";
  if (toNextRank) {
    const want = here.rank + (forward ? 1 : -1);
    const col = all.filter((p) => p.rank === want);
    if (!col.length) return null;
    return col.reduce((best, p) => (Math.abs(along(p) - along(here)) < Math.abs(along(best) - along(here)) ? p : best)).id;
  }
  const col = all.filter((p) => p.rank === here.rank && p.id !== from);
  const next = col.filter((p) => (forward ? along(p) > along(here) : along(p) < along(here)));
  if (!next.length) return null;
  return next.reduce((best, p) => (Math.abs(along(p) - along(here)) < Math.abs(along(best) - along(here)) ? p : best)).id;
}
