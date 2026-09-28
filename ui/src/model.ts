// What the page works out for itself, and nothing more: where an open group or directory puts a
// lane or a row, which marks the viewport shows, and what lights when something is selected. Every
// number added here was already in the JSON; the page decides no order, no size and no position.

import type { Graph, Grade, Link, Mark, Plan, PlanNode, Shown } from "./types";

export const LANE_H = 28;
export const ROW_H = 22;

export type Open = ReadonlySet<string>;

export interface Selection {
  kind: "agent" | "file" | "dir" | "commit";
  id: string;
}

export interface Region {
  y: ReadonlyMap<string, number>; // id -> its y, with every open container added in
  shown: ReadonlySet<string>; // a member of a closed container is not drawn: its marks go on the container
  height: number;
}

interface Box {
  id: string;
  y: number;
  dy: number;
  extra: number;
}

function place<T extends Box>(items: readonly T[], within: (item: T) => string | null, open: Open, h: number): Region {
  const containers = items.filter((i) => within(i) === null && i.extra > 0 && open.has(i.id));
  const y = new Map<string, number>();
  const shown = new Set<string>();
  let height = 0;
  for (const item of items) {
    const container = within(item);
    // A member takes its own dy only while its container is open, and everything below an open
    // container moves down by the height that container added.
    const pushed = containers.reduce((sum, c) => (c.y < item.y ? sum + c.extra : sum), 0);
    const at = item.y + (container !== null && open.has(container) ? item.dy : 0) + pushed;
    y.set(item.id, at);
    if (container === null || open.has(container)) shown.add(item.id);
    height = Math.max(height, at + h);
  }
  return { y, shown, height };
}

export const laneRegion = (graph: Graph, open: Open): Region => place(graph.lanes, (l) => l.group, open, LANE_H);

export const rowRegion = (graph: Graph, open: Open): Region => place(graph.rows, (r) => r.dir, open, ROW_H);

/** The marks between two x, on an array already sorted by x. */
// Which labels to print is the viewport's business, like culling: every tick stays where Python put
// it, and a label is skipped when it would print over the one before it.
export function spaced<T>(items: readonly T[], at: (item: T) => number, gap: number): T[] {
  const kept: T[] = [];
  let last = -Infinity;
  for (const item of items) {
    if (at(item) - last >= gap) {
      kept.push(item);
      last = at(item);
    }
  }
  return kept;
}

export function cull(marks: readonly Mark[], x0: number, x1: number): Mark[] {
  let lo = 0;
  let hi = marks.length;
  while (lo < hi) {
    const mid = (lo + hi) >> 1;
    if (marks[mid]!.x < x0) lo = mid + 1;
    else hi = mid;
  }
  const out: Mark[] = [];
  for (let i = lo; i < marks.length && marks[i]!.x <= x1; i += 1) out.push(marks[i]!);
  return out;
}

export interface Chain {
  lanes: Set<string>;
  rows: Set<string>;
  marks: Set<string>;
  links: Set<string>;
}

const empty = (): Chain => ({ lanes: new Set(), rows: new Set(), marks: new Set(), links: new Set() });

interface End {
  mark?: string;
  lane?: string;
  row?: string;
}

/** Everything that belongs to one selected thing: its lanes, rows, marks and the links between
 * them. Nothing here is inferred — each member is reached by following a recorded link. */
export function chain(graph: Graph, selection: Selection | null): Chain | null {
  if (!selection) return null;
  const marks = new Map(graph.marks.map((m) => [m.id, m]));
  const rows = new Map(graph.rows.map((r) => [r.id, r]));
  const lit = empty();
  const addRow = (id: string) => {
    lit.rows.add(id);
    const dir = rows.get(id)?.dir;
    if (dir) lit.rows.add(dir); // the file lights its directory, which is all that shows when closed
  };
  const end = (id: string): End => {
    const mark = marks.get(id);
    if (mark) return { mark: id, [mark.region === "lanes" ? "lane" : "row"]: mark.at };
    return rows.has(id) ? { row: id } : { lane: id };
  };

  // The seed is the selection itself; a link is followed only when it starts or ends there.
  const seeded = { lanes: new Set<string>(), rows: new Set<string>(), marks: new Set<string>() };
  if (selection.kind === "agent") {
    seeded.lanes.add(selection.id);
    for (const m of graph.marks) {
      if ((m.region === "lanes" && m.at === selection.id) || m.agent === selection.id) seeded.marks.add(m.id);
    }
  } else if (selection.kind === "commit") {
    const commit = marks.get(selection.id);
    if (commit) {
      seeded.marks.add(commit.id);
      lit.lanes.add(commit.at);
      if (commit.agent) lit.lanes.add(commit.agent);
      for (const m of graph.marks) if (m.region === "rows" && m.ref === commit.ref) seeded.marks.add(m.id);
    }
  } else {
    for (const r of graph.rows) if (r.id === selection.id || r.dir === selection.id) seeded.rows.add(r.id);
    for (const m of graph.marks) if (m.region === "rows" && seeded.rows.has(m.at)) seeded.marks.add(m.id);
  }
  for (const id of seeded.lanes) lit.lanes.add(id);
  for (const id of seeded.rows) addRow(id);
  for (const id of seeded.marks) lit.marks.add(id);
  for (const link of graph.links) {
    const ends = [end(link.source), end(link.target)];
    const touches = ends.some(
      (e) =>
        (e.mark !== undefined && seeded.marks.has(e.mark)) ||
        (e.row !== undefined && e.mark === undefined && seeded.rows.has(e.row)) ||
        (e.lane !== undefined && e.mark === undefined && seeded.lanes.has(e.lane)),
    );
    if (!touches) continue;
    lit.links.add(link.id);
    for (const e of ends) {
      if (e.mark !== undefined) lit.marks.add(e.mark);
      if (e.row !== undefined) addRow(e.row);
      if (e.lane !== undefined) lit.lanes.add(e.lane);
    }
  }
  return lit;
}

export type Counter = keyof Graph["counters"];

/** What one header chip matches. Each population is the one its counter counted, so the number on
 * the chip and the marks it lights are the same records. */
export function matching(graph: Graph, counter: Counter): Chain {
  const lit = empty();
  const checks = graph.marks.filter((m) => m.kind === "check");
  const pick = (m: Mark): boolean => {
    switch (counter) {
      case "failed_checks":
        return m.kind === "check" && m.ok === false;
      case "rerun_green": // the failed check that a later run of the same command turned green
        return m.kind === "check" && m.ok === false && checks.some((o) => o.ok === true && o.label === m.label && o.x > m.x);
      case "collisions":
        return m.region === "rows" && (graph.rows.find((r) => r.id === m.at)?.collision ?? false);
      default: // refused, failures, outside: one mark kind each
        return m.kind === counter.replace(/s$/, "");
    }
  };
  for (const m of graph.marks) {
    if (!pick(m)) continue;
    lit.marks.add(m.id);
    if (m.region === "lanes") lit.lanes.add(m.at);
    else {
      lit.rows.add(m.at);
      const dir = graph.rows.find((r) => r.id === m.at)?.dir;
      if (dir) lit.rows.add(dir);
    }
  }
  if (counter === "collisions") {
    for (const r of graph.rows) if (r.collision) lit.rows.add(r.id);
  }
  return lit;
}

// -- words and numbers -------------------------------------------------------------------------

export const GRADE: Record<Grade, string> = {
  edit: "a recorded edit",
  shell: "in Claude Code's list of what a shell command changed",
  commit: "only a commit this agent is recorded making",
  window: "committed during the session by no identifiable agent",
  unknown: "nothing on record",
  record: "a recorded call",
};

export const COUNTER: Record<Counter, string> = {
  failed_checks: "failed checks",
  rerun_green: "rerun green",
  refused: "refused",
  failures: "other failed calls",
  outside: "outside the repo",
  collisions: "collisions",
};

// This machine's local time, ordered the way the terminal prints it so the two agree on sight.
// A moment is printed to the second, so a span and the duration beside it never disagree by a
// rounding; the axis and the tooltips, where the minute is the unit that reads, keep the minute.
const CLOCK = new Intl.DateTimeFormat("en-GB", { hour: "2-digit", minute: "2-digit", second: "2-digit", hour12: false });
const MINUTE = new Intl.DateTimeFormat("en-GB", { hour: "2-digit", minute: "2-digit", hour12: false });
const DAY = new Intl.DateTimeFormat("en-CA", { year: "numeric", month: "2-digit", day: "2-digit" });

/** A recorded moment in this machine's local time; `zone` says which time that is. */
export const stamp = (t: string | null): string => (t ? `${DAY.format(new Date(t))} ${CLOCK.format(new Date(t))}` : "?");

export const clock = (t: string | null): string => (t ? MINUTE.format(new Date(t)) : "?");

/** Two moments, with the second one's date dropped when it is the same day. */
export const between = (t0: string | null, t1: string | null): string =>
  `${stamp(t0)} → ${stamp(t0).slice(0, 10) === stamp(t1).slice(0, 10) ? stamp(t1).slice(11) : stamp(t1)}`;

export function zone(t: string | null): string {
  const minutes = t ? -new Date(t).getTimezoneOffset() : 0;
  const pad = (n: number) => String(Math.floor(Math.abs(n))).padStart(2, "0");
  return `UTC${minutes < 0 ? "−" : "+"}${pad(minutes / 60)}:${pad(minutes % 60)}`;
}

export function duration(t0: string | null, t1: string | null): string {
  if (!t0 || !t1) return "?";
  return span((new Date(t1).getTime() - new Date(t0).getTime()) / 1000);
}

export function span(seconds: number): string {
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  const s = Math.round(seconds % 60);
  if (h) return `${h}h ${String(m).padStart(2, "0")}m`;
  return m ? `${m}m${s ? ` ${s}s` : ""}` : `${s}s`;
}

/** Agent lanes take the eight hues in lane order; the main lane, a group and the unknown lane are
 * neutral, because they are not one agent's work. Past eight the hues repeat with a dash. */
export function hues(graph: Graph): Map<string, number> {
  const out = new Map<string, number>();
  let n = 0;
  for (const lane of graph.lanes) out.set(lane.id, lane.kind === "agent" ? n++ : -1);
  return out;
}

export const hue = (i: number | undefined): string => (i === undefined || i < 0 ? "var(--neutral)" : `var(--a${(i % 8) + 1})`);

export const dash = (i: number | undefined): string | undefined => (i !== undefined && i >= 8 ? "5 3" : undefined);

export const linksBy = (graph: Graph, kind: Link["kind"]): Link[] => graph.links.filter((l) => l.kind === kind);

// East Asian wide and fullwidth characters, and emoji, take two columns (a CJK glyph is about 1 em)
const WIDE = /[\u1100-\u115F\u2E80-\u303E\u3041-\u33FF\u3400-\u4DBF\u4E00-\u9FFF\uA000-\uA4CF\uAC00-\uD7A3\uF900-\uFAFF\uFE30-\uFE4F\uFF00-\uFF60\uFFE0-\uFFE6\u{20000}-\u{3FFFD}]|\p{Extended_Pictographic}/u;

/** How many columns a character takes: 2 for a wide one, as plan_view.cols counts them. */
export const cols = (char: string): number => (WIDE.test(char) ? 2 : 1);

/** A label that has to fit a fixed width, cut with an ellipsis; the whole text stays in the title. */
export const clip = (text: string, width: number, per: number): string => {
  const room = Math.floor(width / per);
  const chars = Array.from(text);
  if (chars.reduce((n, c) => n + cols(c), 0) <= room) return text;
  let used = 0;
  const kept = chars.filter((c) => (used += cols(c)) <= Math.max(1, room - 1));
  return `${kept.join("") || chars[0]}…`;
};

// -- the plan ------------------------------------------------------------------------------------

/** The two things the page can show: what will happen, and what did. The plan is the default. */
export type View = "plan" | "record";

/** The three ways the page draws the plan: the outline the terminal prints, the tree top-down, and
 * the graph of what waits on what, left to right. */
export type Layout = "outline" | "tree" | "graph";

export const PAD_X = 132; // the graph's lane-name gutter, which is the page's own margin, not a position
export const PAD_Y = 16;
const FIT = 0.8; // the least scale a drawing is chosen at: below it the says line is about 8 px

/** How wide each drawing is on the page, gutters and all. */
export const graphWidth = (plan: Plan): number => PAD_X + plan.width + 24;
export const treeWidth = (plan: Plan): number => plan.tree_width + PAD_Y * 2;

/** The layout the plan's shape calls for, and why: the graph when anything waits on anything and it
 * fits `room` pixels across at 0.8, else the tree when it fits, else the outline. Only the width
 * counts: a drawing taller than its pane pans down. */
export const layoutFor = (plan: Plan, room: number): [Layout, string] => {
  const waits = plan.edges.length > 0;
  const fits = (width: number) => width * FIT <= room;
  if (waits && fits(graphWidth(plan))) return ["graph", "some nodes wait on others, and the graph fits"];
  if (fits(treeWidth(plan))) return ["tree", waits ? "the graph is too wide for the window, and the tree fits" : "nothing waits on anything, and the tree fits"];
  return ["outline", waits ? "the graph and the tree are too wide for the window" : "nothing waits on anything, and the tree is too wide for the window"];
};

/** What the viewer clicked on this page: auto, a layout, or nothing yet (the repository's setting). */
export type Mode = "auto" | Layout | null;

// the repository's `view` setting, in the terminal's names (graphene watch --view), as the page draws it
const SETTING: Record<string, Layout> = { outline: "outline", tree: "tree", dag: "graph", graph: "graph" };

/** The layout drawn, the button pressed and why. The page opens in the repository's view setting,
 * the one the terminal reads (unset, or a view the page has not: auto); a click changes this page
 * only, and nothing keeps it, so the store stays the one place the preference lives. */
export const shownLayout = (plan: Plan, mode: Mode, room: number): { layout: Layout; mode: "auto" | Layout; why: string } => {
  const [auto, because] = layoutFor(plan, room);
  const set = SETTING[plan.view];
  if (mode === null && set) return { layout: set, mode: set, why: `this repo's view setting: ${plan.view}` };
  if (mode === null || mode === "auto") return { layout: auto, mode: "auto", why: `auto chose the ${auto}: ${because}` };
  return { layout: mode, mode, why: "your choice, on this page only" };
};

/** What a state is called on screen. It is printed as words beside the shape, never as colour alone. */
export const STATE: Record<Shown, string> = {
  proposed: "proposed",
  open: "open",
  waiting: "waiting",
  ready: "ready",
  "came back": "came back",
  running: "running",
  review: "waiting on a sign-off",
  done: "done",
  "sub-goal": "sub-goal",
};

export const STATE_COLOUR: Record<Shown, string> = {
  proposed: "var(--ask)",
  open: "var(--neutral)",
  waiting: "var(--neutral)",
  ready: "var(--accent)",
  "came back": "var(--ask)", // it waits on the person, as a sign-off does
  running: "var(--a1)",
  review: "var(--ask)",
  done: "var(--pass)",
  "sub-goal": "var(--neutral)",
};

export type Act = "accept" | "signoff" | "reopen" | "drop" | "edit";

/** Why a control on a node is disabled, or null when it is not. These are the page's own reasons,
 * shown before anything is sent; plan.py refuses for itself, and its sentence is what is printed
 * when a request is actually made. Where the two could disagree, the server's is the one that ran. */
export function why(node: PlanNode, plan: Plan): Record<Act, string | null> {
  const readOnly = plan.writable ? null : "this page cannot change the plan; it is read-only";
  const waiting = plan.nodes.filter((n) => n.needs.includes(node.id)).map((n) => n.id);
  const finished = node.state === "review" || node.state === "done";
  const is = `${node.id} is ${STATE[node.display_state]}`;
  return {
    accept: readOnly ?? (node.state === "proposed" ? null : `only a proposal is accepted, and ${is}`),
    signoff: readOnly ?? (node.state === "review" ? null : `a sign-off comes after \`graphene node done\`, and ${is}`),
    reopen: readOnly ?? (finished ? null : `only a finished node is sent back, and ${is}`),
    drop:
      readOnly ??
      (node.state === "running"
        ? `${node.id} is running (${node.executor ?? "someone holds it"}); it has to be handed back first`
        : waiting.length > 0
          ? `${waiting.join(", ")} waits on ${node.id}; change what they need first`
          : null),
    edit: readOnly ?? (node.state === "done" ? `${node.id} is done; send it back first to change its contract` : null),
  };
}
