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
  /** A named band's loose boxes at one rank (no edge in, and none out but to the goal) stand at most this many
   *  high; more stand side by side in that rank, row by row, so a sub-goal of many tasks at once is a block and
   *  not a tower. Across only; unset, a rank is one column. */
  stack?: number;
  /** The nameless band's loose boxes too: for a plan with no sub-goals whose tower a canvas wider than tall would
   *  not hold whole, fitted small in the middle of an empty canvas (the graph's `place` says when). */
  stackAll?: boolean;
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
  // rows: in each band, each rank's boxes stack top to bottom in their order; loose ones past `stack` side by side
  const rowOf = new Map<string, number>(), sideOf = new Map<string, number>();
  const bandRows = new Map<string, number>(bandIds.map((b) => [b, 0]));
  const loose = (id: string) => !edges.some(([a, b]) => b === id || (a === id && b !== goal));
  const wide = cols.map(() => 1); // how many boxes stand side by side in a rank, in its widest band
  // a band with nothing past the rank it stacks at takes the next ranks' columns, which it leaves empty: a loose box
  // says no order, and widening the rank would leave a card-wide hole in every other band
  const lastOf = new Map<string, number>();
  for (const id of tasks) lastOf.set(by.get(id)!.band, Math.max(lastOf.get(by.get(id)!.band) ?? 0, rank[id] ?? 0));
  const spread = new Set<string>();
  cols.forEach((col, k) => {
    const groups = new Map<string, string[]>();
    for (const id of col) if (id !== goal) groups.set(by.get(id)!.band, [...(groups.get(by.get(id)!.band) ?? []), id]);
    for (const [band, g] of groups) {
      const n = (band || o.stackAll) && o.stack && g.length > o.stack && g.every(loose) ? Math.ceil(g.length / o.stack) : 1;
      if (n > 1 && lastOf.get(band) === k && k + n - 1 < last) g.forEach((id) => spread.add(id));
      else wide[k] = Math.max(wide[k]!, n);
      g.forEach((id, i) => { rowOf.set(id, Math.floor(i / n)); sideOf.set(id, i % n); });
      bandRows.set(band, Math.max(bandRows.get(band) ?? 0, Math.ceil(g.length / n)));
    }
  });
  const colW = cols.map((col) => Math.max(o.boxW, ...col.map((id) => by.get(id)!.w ?? o.boxW)));
  const columns: number[] = [];
  let x = o.padX;
  colW.forEach((w, k) => { columns.push(x); x += (w + o.gapX) * wide[k]!; });
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
  // a line inside a sub-goal past a card on its last row: it goes round the card, under it, and the band has the room
  // for it at its foot, so the line stays inside it and is not drawn along its edge
  const round = new Set(edges.flatMap(([a, b]) => {
    const band = by.get(a)?.band, row = rowOf.get(a);
    if (!band || band !== by.get(b)?.band || row !== (bandRows.get(band) ?? 1) - 1) return [];
    return tasks.some((c) => by.get(c)!.band === band && rowOf.get(c) === row && rank[c]! > rank[a]! && rank[c]! < rank[b]!) ? [band] : [];
  }));
  const bands: Band[] = [];
  const bandTop = new Map<string, number>();
  let y = o.padY;
  for (const band of bandIds) {
    const hs = rowH.get(band)!;
    const tall = hs.reduce((s, h) => s + h, 0) + Math.max(0, hs.length - 1) * o.gapY + (round.has(band) ? ROUND : 0);
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
      const side = sideOf.get(id) ?? 0;
      placed[id] = { id, x: spread.has(id) ? columns[k + side]! : columns[k]! + side * (colW[k]! + o.gapX), y: top, w, h, rank: k, band: b.band };
    }
  }
  return { boxes: placed, bands, columns, width, height, ranks: cols.length, down: false };
}

/** Laid downward, the room between two boxes in a row (a card's + and the next one's selection ring) and between
 *  two rows (the lines'). */
export const DOWN = { gap: 32, rankGap: 44 };

/** Waves as rows: each rank's boxes side by side, wrapping when the row would pass ``width`` (a wave's rows as far
 *  apart as two waves', where the lines between rows run), each row centred, the goal last. No sub-goal is drawn
 *  here, so ``bands`` is empty. */
function downward(cols: string[][], by: Map<string, Box>, goal: string | null, o: typeof D & Options): Layout {
  const maxW = Math.max(o.width ?? Infinity, o.padX * 2 + o.boxW);
  const { gap, rankGap } = DOWN;
  const placed: Record<string, Placed> = {};
  const columns: number[] = [];
  const rows: Placed[][] = [];
  let y = o.padY;
  let widest = o.padX * 2 + o.boxW;
  for (let k = 0; k < cols.length; k++) {
    columns.push(y);
    let x = o.padX, rowH = 0;
    rows.push([]);
    for (const id of cols[k]!) {
      const b = by.get(id)!;
      const w = b.w ?? o.boxW, h = b.h ?? o.boxH;
      if (x > o.padX && x + w > maxW - o.padX) { y += rowH + rankGap; x = o.padX; rowH = 0; rows.push([]); } // wrap
      placed[id] = { id, x, y, w, h, rank: k, band: id === goal ? "" : b.band };
      rows.at(-1)!.push(placed[id]!);
      x += w + gap;
      rowH = Math.max(rowH, h);
      widest = Math.max(widest, x - gap + o.padX);
    }
    y += rowH + rankGap;
  }
  const width = Number.isFinite(maxW) ? Math.max(maxW, widest) : widest;
  for (const row of rows) { // in the middle of the width, as a column of cards down a page is
    const shift = row.length ? (width - (row.at(-1)!.x + row.at(-1)!.w + o.padX)) / 2 : 0;
    for (const p of row) p.x += shift;
  }
  const height = Math.max(y - rankGap + o.padY, o.padY * 2 + o.boxH);
  return { boxes: placed, bands: [], columns, width, height, ranks: cols.length, down: true };
}

type Rect = { x: number; y: number; w: number; h: number };
export type Point = [number, number];

/** A band's foot, where a line inside it goes round a card: 14 px under the card (`route`), 16 over the foot. */
const ROUND = 24;

/** An edge's corners across, from (x1, y1) on a box's right side to (x2, y2) on a later one's left, square and in
 *  the gaps, as a DAG view routes them: along to the gap before the target's column (``gap`` wide), down or up it,
 *  and in, so edges into one box share that trunk. Where its own height is blocked on the way (a box in a column it
 *  skips, a sub-goal's header), it turns down the first gap and goes along the target's height, else along the
 *  clear row gap between the two trunks that keeps it shortest: one with room round it, or the middle of a
 *  ``rowGap`` between two boxes one over another, which counts 40 px longer (but less than a way round a band). */
export function route(x1: number, y1: number, x2: number, y2: number, gap: number, rowGap: number, blocks: readonly Rect[]): Point[] {
  const t1 = x1 + gap / 2, t2 = x2 - gap / 2;
  if (t2 < x1) return [[x1, y1], [x2, y2]]; // not a later column: the straight line says it
  const clear = (y: number, from: number, to: number, m = 2) => !blocks.some((r) => r.x < to && r.x + r.w > from && r.y - m < y && r.y + r.h + m > y);
  if (clear(y1, x1, t2)) return [[x1, y1], [t2, y1], [t2, y2], [x2, y2]];
  if (clear(y2, t1, x2)) return [[x1, y1], [t1, y1], [t1, y2], [x2, y2]];
  const ways = blocks.filter((r) => r.x < t2 && r.x + r.w > t1).flatMap((r) => [14, rowGap / 2].flatMap((m) => [[r.y - m, m], [r.y + r.h + m, m]]));
  const cost = ([v, m]: number[]) => Math.abs(v! - y1) + Math.abs(v! - y2) + (m === 14 ? 0 : 40);
  const y = ways.sort((a, b) => cost(a) - cost(b)).find(([v, m]) => clear(v!, t1, t2, m! - 0.5))?.[0] ?? y1;
  return [[x1, y1], [t1, y1], [t1, y], [t2, y], [t2, y2], [x2, y2]];
}

/** A route's corners turned a quarter, x for y: what `route` and `spread` say across, said downward. */
export const flip = (pts: readonly Point[]): Point[] => pts.map(([a, b]) => [b, a]);

/** Laid downward, an edge's corners: `route` turned a quarter, from ``x1`` on the foot of ``from`` to ``x2`` on the
 *  top of ``to``, in the gaps between the rows. It sets out from the foot of the row ``from`` stands in, a stub down
 *  from a card shorter than its row: a line turning under its own card would run inside a taller one beside it. */
export function routeDown(lay: Layout, from: Placed, x1: number, to: Placed, x2: number, blocks: readonly Rect[]): Point[] {
  const foot = Math.max(...Object.values(lay.boxes).filter((b) => b.y === from.y).map((b) => b.y + b.h));
  const pts = flip(route(foot, x1, to.y, x2, DOWN.rankGap, DOWN.gap, blocks.map((r) => ({ x: r.y, y: r.x, w: r.h, h: r.w }))));
  return foot > from.y + from.h ? [[x1, from.y + from.h], ...pts] : pts;
}

/** Routes' trunks spread in their gaps. A trunk is a route's vertical leg; its last is its target's, any other its
 *  source's, and an only leg is its source's where that source has more lines in this gap than its target has: lines
 *  into one card share its trunk, and lines out of one card into several share the card's own, which branches into
 *  each, where a trunk for each target stood three lines side by side out of one card. But two trunks in one gap that share
 *  any stretch of height (or meet end to end: a line out of a card turning down just where another turns into the
 *  card beside it) stand apart, at most ``most`` px and within ``room``, so no line seems to run on into another's
 *  card. Of two side by side, the one going further down stands left (further up, left too), so their legs do not
 *  cross. */
export function spread(routes: readonly Point[][], room: number, most = 6): Point[][] {
  type Trunk = { x: number; y0: number; y1: number; from: number; to: number; legs: [number, number][] };
  const legsOf = routes.map((pts) => pts.slice(1).flatMap((p, i) => (p[0] === pts[i]![0] && p[1] !== pts[i]![1] ? [i] : [])));
  const keys = (pts: readonly Point[], i: number) => [`${pts[i]![0]} in ${pts.at(-1)}`, `${pts[i]![0]} out ${pts[0]}`] as const;
  const count = new Map<string, number>(), add = (k: string) => count.set(k, (count.get(k) ?? 0) + 1);
  routes.forEach((pts, r) => legsOf[r]!.forEach((i, n, legs) => {
    const [into, outOf] = keys(pts, i);
    if (n === legs.length - 1) add(into);
    if (n === 0) add(outOf);
  }));
  const trunks = new Map<string, Trunk>();
  routes.forEach((pts, r) => legsOf[r]!.forEach((i, n, legs) => {
    const [x, a] = pts[i]!, b = pts[i + 1]![1], [into, outOf] = keys(pts, i);
    const key = n < legs.length - 1 || (n === 0 && count.get(outOf)! > count.get(into)!) ? outOf : into;
    const t = trunks.get(key) ?? { x, y0: Infinity, y1: -Infinity, from: 0, to: 0, legs: [] };
    t.y0 = Math.min(t.y0, a, b); t.y1 = Math.max(t.y1, a, b); t.from += a; t.to += b; t.legs.push([r, i]);
    trunks.set(key, t);
  }));
  const out = routes.map((pts) => pts.map((p) => [...p] as Point));
  const gaps = new Map<number, Trunk[]>();
  for (const t of trunks.values()) gaps.set(t.x, [...(gaps.get(t.x) ?? []), t]);
  for (const ts of gaps.values()) {
    const down = (t: Trunk) => t.to > t.from, end = (t: Trunk) => t.to / t.legs.length;
    ts.sort((p, q) => (down(p) === down(q) ? (down(p) ? end(q) - end(p) : end(p) - end(q)) : down(p) ? -1 : 1));
    const slot = new Map<Trunk, number>(), near = (t: Trunk, u: Trunk) => u.y0 <= t.y1 + most && t.y0 <= u.y1 + most;
    for (const t of ts) { // the first slot no trunk beside it in height has
      let s = 0;
      while (ts.some((u) => slot.get(u) === s && near(t, u))) s++;
      slot.set(t, s);
    }
    for (const t of ts) { // in the middle of the gap, or of the trunks beside it
      const n = 1 + Math.max(...ts.filter((u) => near(t, u)).map((u) => slot.get(u)!));
      const x = n > 1 ? t.x + (slot.get(t)! - (n - 1) / 2) * Math.min(most, room / (n - 1)) : t.x;
      for (const [r, i] of t.legs) { out[r]![i]![0] = x; out[r]![i + 1]![0] = x; }
    }
  }
  return out;
}

/** A route as a path, each corner rounded to ``r`` px (less where a leg is short). */
export function rounded(pts: readonly Point[], r = 8): string {
  let d = `M${pts[0]![0]},${pts[0]![1]}`;
  for (let i = 1; i < pts.length - 1; i++) {
    const [px, py] = pts[i - 1]!, [x, y] = pts[i]!, [nx, ny] = pts[i + 1]!;
    const a = Math.min(r, Math.hypot(x - px, y - py) / 2, Math.hypot(nx - x, ny - y) / 2);
    d += ` L${x - Math.sign(x - px) * a},${y - Math.sign(y - py) * a} Q${x},${y} ${x + Math.sign(nx - x) * a},${y + Math.sign(ny - y) * a}`;
  }
  return `${d} L${pts.at(-1)![0]},${pts.at(-1)![1]}`;
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
  const across = lay.down ? (p: Placed) => p.y + p.h / 2 : (p: Placed) => p.x + p.w / 2;
  // the nearest along the rank, then the nearest across it: of two side by side (`stack`), the one in line
  const nearest = (ps: Placed[]) => ps.reduce((best, p) => {
    const d = Math.abs(along(p) - along(here)) - Math.abs(along(best) - along(here));
    return d < 0 || (d === 0 && Math.abs(across(p) - across(here)) < Math.abs(across(best) - across(here))) ? p : best;
  }).id;
  if (toNextRank) {
    // loose boxes side by side in one rank: the one beside it on its row comes before the next rank
    const beside = lay.down ? [] : all.filter((p) => p.rank === here.rank && p.id !== from && p.y === here.y && (forward ? p.x > here.x : p.x < here.x));
    if (beside.length) return beside.reduce((best, p) => (Math.abs(p.x - here.x) < Math.abs(best.x - here.x) ? p : best)).id;
    const want = here.rank + (forward ? 1 : -1);
    const col = all.filter((p) => p.rank === want);
    return col.length ? nearest(col) : null;
  }
  const col = all.filter((p) => p.rank === here.rank && p.id !== from);
  const next = col.filter((p) => (forward ? along(p) > along(here) : along(p) < along(here)));
  return next.length ? nearest(next) : null;
}
