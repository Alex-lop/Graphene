// The graph, in the webview: boxes for the tasks coloured by their state, bands for the sub-goals, the goal
// at the right (or at the foot, when the view is narrow), a forked task fanning out into its forks; or, in
// the sidebar, the same plan as lanes, one row a task, wave by wave. A click selects and opens the details
// pane whose buttons ask the extension to run graphene. No network, no library: SVG and DOM from the state.
// Boxes are keyed by task id and updated in place, so a snapshot that changed nothing moves nothing.
import { layout, modeFor, step, type Box, type Edge, type Layout } from "../layout.ts";
import { autoLine, SAY, usd, type State } from "../state.ts";
import { ICONS } from "./icons.ts";
import { actsFor, cornerWord, cut, done, FIRST_HINT, fitWidth, forkActs, forkRow, forkWords, HEADER_ACTS, headerFor, KEYS, linkHint, paneKey, questionOn,
         sub, tabOrder, topLine, zoomK, type Act, type Button, type StateX, type TaskX } from "./words.ts";

declare function acquireVsCodeApi(): { postMessage(m: unknown): void; getState(): unknown; setState(s: unknown): void };

type Status = { kind: "reading" | "missing" | "uninitialised" | "error" | "nofolder"; text: string };
type Incoming = { type: "state"; state: StateX } | { type: "status"; status: Status } | { type: "select"; id: string };
type Zoom = { k: number; tx: number; ty: number };
type View = "auto" | "graph" | "lanes";
type Saved = { zoom?: Zoom; hinted?: boolean; view?: View };

const GOAL = " goal";
const BOX_W = 200, BOX_H = 48, FORK_H = 20, FORK_DX = 22, CHIP_W = 228, GOAL_W = 200, GOAL_H = 66; // a chip holds 32 mono characters
/** The narrow view by default: lanes read better than a downward graph at 280 to 400 px (lane 1's notes). */
const NARROW_VIEW: "lanes" | "graph" = "lanes";
const api = acquireVsCodeApi();
const $ = <T extends HTMLElement>(id: string) => document.getElementById(id) as T;
const svgNS = "http://www.w3.org/2000/svg";

let state: StateX | null = null;
let lastJson = "";
let lay: Layout | null = null;
let selected: string | null = null;
let linking: string | null = null;
let wiring: { from: string; x: number; y: number } | null = null; // a drag from a task's dot: the link being drawn
let saved: Saved = (() => { try { return (api.getState() as Saved) ?? {}; } catch { return {}; } })();
let zoom: Zoom = saved.zoom ?? { k: 1, tx: 0, ty: 0 };
let moved = Boolean(saved.zoom); // the person zoomed or panned (now or last time): a resize no longer re-fits
let fitted = false;
let saving: ReturnType<typeof setTimeout> | undefined;

function remember(patch: Partial<Saved>) {
  saved = { ...saved, ...patch };
  clearTimeout(saving);
  saving = setTimeout(() => { try { api.setState(saved); } catch { /* the preview has no state */ } }, 150);
}

function el<K extends keyof SVGElementTagNameMap>(tag: K, attrs: Record<string, string | number> = {}, text?: string) {
  const node = document.createElementNS(svgNS, tag);
  for (const [k, v] of Object.entries(attrs)) node.setAttribute(k, String(v));
  if (text !== undefined) node.textContent = text;
  return node;
}

function div(cls: string, text?: string, parent?: HTMLElement): HTMLDivElement {
  const d = document.createElement("div");
  d.className = cls;
  if (text !== undefined) d.textContent = text;
  parent?.appendChild(d);
  return d;
}

/** An SVG text cut to ``max`` px by its drawn length. Not drawn yet (the SVG hidden), it is cut by a
 *  character count instead, so nothing runs past its box in the meantime. */
function fitText(text: SVGTextElement, max: number) {
  const whole = text.textContent ?? "";
  if (text.getComputedTextLength() === 0 && whole) { text.textContent = cut(whole, Math.max(2, Math.floor(max / 7))); return; }
  text.textContent = fitWidth(whole, max, (t) => { text.textContent = t; return text.getComputedTextLength(); });
}

/** A codicon, inline: its path in a 16 by 16 box. */
function icon(name: string): SVGSVGElement {
  const s = el("svg", { class: "ico", viewBox: "0 0 16 16", width: 16, height: 16, "aria-hidden": "true" });
  s.appendChild(el("path", { d: ICONS[name] ?? "" }));
  return s;
}

function button(b: Button, id: string, parent: HTMLElement) {
  const btn = document.createElement("button");
  if (b.icon) btn.appendChild(icon(b.icon));
  btn.appendChild(document.createTextNode(b.label));
  btn.title = b.title;
  btn.className = b.main ? "" : "quiet";
  btn.addEventListener("click", () => {
    if (b.act === "link") { linking = id; render(); return; }
    api.postMessage({ type: "act", act: b.act, id, ...(b.fork ? { fork: b.fork } : {}) });
  });
  parent.appendChild(btn);
}

const cls = (word: string) => `st-${word.replace(/\s+/g, "-")}`;

function boxes(s: StateX): { boxes: Box[]; edges: Edge[]; goal: string | null } {
  const bs: Box[] = s.tasks.map((t) => ({
    id: t.id, band: t.parent ?? "", w: t.forks.length ? FORK_DX + CHIP_W : BOX_W,
    h: BOX_H + (t.forks.length ? FORK_H * t.forks.length + 6 : 0),
  }));
  const edges: Edge[] = s.edges.filter(([, , kind]) => kind === "needs").map(([a, b]) => [a, b]);
  const hasGoal = Boolean(s.goal) && s.tasks.length > 0;
  if (hasGoal) {
    bs.push({ id: GOAL, band: "", w: GOAL_W, h: GOAL_H });
    const needed = new Set(edges.map(([a]) => a));
    for (const t of s.tasks) if (!needed.has(t.id)) edges.push([t.id, GOAL]);
  }
  return { boxes: bs, edges, goal: hasGoal ? GOAL : null };
}

function goalTitle(s: State, id: string): string {
  return s.goals.find((g) => g.id === id)?.title ?? id;
}

const replaying = () => Boolean(state?.replay);

/** The view on screen: lanes when the canvas is narrow, unless the person chose. */
function view(): "graph" | "lanes" {
  const want = saved.view ?? "auto";
  if (want !== "auto") return want;
  return modeFor($("canvas").clientWidth) === "down" ? NARROW_VIEW : "graph";
}

/** The graph's direction: downward when narrow, or as the preview page forces it (data-dir on body). */
function direction(): "across" | "down" {
  const forced = document.body.dataset.dir;
  if (forced === "down" || forced === "across") return forced;
  return modeFor($("canvas").clientWidth);
}

function render() {
  if (!state) return;
  const s = state;
  header(s);
  const v = view();
  const dir = direction();
  document.body.dataset.mode = v === "lanes" ? "lanes" : dir;
  $("lanes").hidden = v !== "lanes";
  ($("svg") as unknown as SVGSVGElement).style.display = v === "lanes" ? "none" : "block";
  $("canvas").classList.toggle("lanes", v === "lanes");
  $("notice").hidden = s.tasks.length > 0;
  if (!s.tasks.length) {
    $("notice").className = "";
    $("notice").textContent = "Nothing is planned yet: the graph shows your goal and the tasks under it.";
  }
  if (v === "lanes") { lanes(s); $("to-goal").hidden = true; } else graph(s, dir);
  pane();
  hint();
}

/** The side bar's width, or a narrow tab: the header folds to one line and the pane goes under the canvas. */
const narrow = () => matchMedia("(max-width: 700px)").matches;

function header(s: StateX) {
  const first = topLine(s); // a replay, or a live race against the stand-in: said before anything else
  $("replay").textContent = first;
  $("replay").hidden = !first;
  const h = headerFor(s, narrow());
  $("goal").textContent = h.goal;
  $("goal").title = h.hover;
  $("counts").textContent = h.counts;
  $("counts").hidden = !h.counts;
  $("auto").textContent = h.auto;
  $("auto").hidden = !h.auto;
  const run = $("b-run"); // while a run goes, the button that started it stops it
  run.replaceChildren(icon(s.run.going ? "debug-stop" : "play"), document.createTextNode(s.run.going ? "Stop" : "Run"));
  run.title = s.run.going ? "stop every agent: their tasks go back to the plan" : "start an agent on every task that is ready";
  for (const [id] of HEADER_ACTS) $(id).hidden = replaying(); // a replay is watched: nothing acts on a plan, or outside it
  const toggle = $("b-view");
  const v = view();
  toggle.replaceChildren(icon(v === "lanes" ? "type-hierarchy-sub" : "list-flat"), document.createTextNode(v === "lanes" ? "Graph" : "Lanes"));
}

// ---- the graph: SVG, keyed by task id ----

const taskEls = new Map<string, { g: SVGGElement; key: string }>();
const edgeEls = new Map<string, SVGPathElement>();
let goalKey = "";

function graph(s: StateX, dir: "across" | "down") {
  const svg = $("svg") as unknown as SVGSVGElement;
  const g = boxes(s);
  const down = dir === "down";
  lay = layout(g.boxes, g.edges, { goal: g.goal, boxW: BOX_W, boxH: BOX_H, labelH: 18, gapX: 56, down, width: down ? $("canvas").clientWidth / zoom.k : undefined });
  // bands: few, redrawn
  const bands = $("bands") as unknown as SVGGElement;
  bands.replaceChildren();
  for (const band of lay.bands) {
    if (!band.id) continue;
    const ts = s.tasks.filter((t) => t.parent === band.id);
    bands.appendChild(el("rect", { class: "band", x: 4, y: band.y0, width: lay.width - 8, height: band.y1 - band.y0, rx: 6 }));
    const label = bands.appendChild(el("text", { class: "band-label", x: 14, y: band.y0 + 16 }, `${goalTitle(s, band.id)} · ${done(ts)}`));
    fitText(label, Math.min(lay.width - 8, $("canvas").clientWidth / zoom.k) - 28); // the band's visible width
  }
  // edges: keyed by their ends; a changed path glides (CSS transitions d)
  const edges = $("edges") as unknown as SVGGElement;
  const seenEdges = new Set<string>();
  for (const [a, b] of g.edges) {
    const p = lay.boxes[a], q = lay.boxes[b];
    if (!p || !q) continue;
    const key = `${a}>${b}`;
    seenEdges.add(key);
    let path = edgeEls.get(key);
    if (!path) { path = el("path", { class: "edge" }); edgeEls.set(key, path); edges.appendChild(path); }
    path.setAttribute("d", edgeD(p, q, a, b, down));
    path.classList.toggle("hot", Boolean(selected && (a === selected || b === selected)));
  }
  for (const [key, path] of edgeEls) if (!seenEdges.has(key)) { path.remove(); edgeEls.delete(key); }
  // boxes: one group a task, rebuilt only when its words or its place changed
  const tasks = $("tasks") as unknown as SVGGElement;
  const seen = new Set<string>();
  for (const t of s.tasks) {
    const p = lay.boxes[t.id];
    if (!p) continue;
    seen.add(t.id);
    const key = JSON.stringify([t, p.x, p.y, t.id === selected, down]);
    let have = taskEls.get(t.id);
    if (have && have.key === key) continue;
    if (!have) {
      const grp = el("g", { class: "task fresh", "data-id": t.id, tabindex: 0, role: "button" });
      grp.style.transform = `translate(${p.x}px, ${p.y}px)`; // placed before it joins: no glide from the corner
      grp.addEventListener("click", (e) => { e.stopPropagation(); clicked(t.id); });
      grp.addEventListener("keydown", (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); e.stopPropagation(); clicked(t.id); } });
      tasks.appendChild(grp);
      have = { g: grp, key: "" };
      taskEls.set(t.id, have);
    }
    have.key = key;
    drawTask(have.g, t, p.h, down);
    have.g.style.transform = `translate(${p.x}px, ${p.y}px)`;
  }
  for (const [id, have] of taskEls) if (!seen.has(id)) { have.g.remove(); taskEls.delete(id); }
  // Tab walks the boxes wave by wave, which is their order in the DOM: reordered only when it changed
  const want = tabOrder(lay, s.tasks.map((t) => t.id));
  const have = Array.from(tasks.children).map((c) => c.getAttribute("data-id"));
  if (want.join("\n") !== have.join("\n")) for (const id of want) { const grp = taskEls.get(id)?.g; if (grp) tasks.appendChild(grp); }
  // the goal
  const goalG = $("goalg") as unknown as SVGGElement;
  const gp = g.goal ? lay.boxes[GOAL] : undefined;
  const gk = gp ? JSON.stringify([s.goal, done(s.tasks), gp.x, gp.y]) : "";
  if (gk !== goalKey) {
    goalKey = gk;
    goalG.replaceChildren();
    if (gp) {
      goalG.appendChild(el("rect", { class: "goal-box", x: 0, y: 0, width: gp.w, height: gp.h, rx: 8 }));
      goalG.appendChild(el("rect", { class: "goal-box inner", x: 4, y: 4, width: gp.w - 8, height: gp.h - 8, rx: 5 }));
      fitText(goalG.appendChild(el("text", { class: "goal-title", x: 14, y: 28 }, s.goal)), gp.w - 28);
      goalG.appendChild(el("text", { class: "sub", x: 14, y: 48 }, `goal · ${done(s.tasks)} done`));
      goalG.setAttribute("aria-label", `goal: ${s.goal}, ${done(s.tasks)} done`);
      goalG.setAttribute("role", "group"); // reachable by Tab and the arrows, announced
      goalG.setAttribute("tabindex", "0");
      goalG.appendChild(el("title", {}, s.goal));
      goalG.style.transform = `translate(${gp.x}px, ${gp.y}px)`;
    }
  }
  $("wire").setAttribute("d", wiring ? wireD() : "");
  svg.setAttribute("viewBox", `0 0 ${Math.max(lay.width, 10)} ${Math.max(lay.height, 10)}`);
  svg.setAttribute("width", String(lay.width));
  svg.setAttribute("height", String(lay.height));
  if (!fitted && !moved) fit(); else zoom = clamp(zoom);
  fitted = true;
  applyZoom();
}

/** An edge's curve: out of a box's right side into the next's left, or down out of its foot into the top. */
function edgeD(p: { x: number; y: number; w: number; h: number }, q: { x: number; y: number; w: number; h: number }, a: string, b: string, down: boolean): string {
  if (down) {
    const x1 = p.x + (a === GOAL ? p.w : BOX_W) / 2, y1 = p.y + p.h, x2 = q.x + q.w / 2, y2 = q.y;
    const dy = Math.max(16, (y2 - y1) / 2);
    return `M${x1},${y1} C${x1},${y1 + dy} ${x2},${y2 - dy} ${x2},${y2}`;
  }
  const x1 = p.x + BOX_W, y1 = p.y + BOX_H / 2, x2 = q.x, y2 = q.y + (b === GOAL ? q.h / 2 : BOX_H / 2);
  const dx = Math.max(24, (x2 - x1) / 2);
  return `M${x1},${y1} C${x1 + dx},${y1} ${x2 - dx},${y2} ${x2},${y2}`;
}

/** A task's box, drawn at the group's origin: the box, its stripe, title and sub line, the corner's word,
 *  its fork chips hanging under it, and the dot its lines leave from. */
function drawTask(grp: SVGGElement, t: TaskX, h: number, down: boolean) {
  grp.replaceChildren();
  grp.setAttribute("class", `task ${cls(t.state)}${t.id === selected ? " selected" : ""}${t.needs_you ? " needs-you" : ""}`);
  const line = sub(t);
  grp.setAttribute("aria-label", `${t.title}: ${line}${t.id === selected ? ", selected" : ""}`);
  grp.appendChild(el("rect", { class: "box", x: 0, y: 0, width: BOX_W, height: BOX_H, rx: 6 }));
  grp.appendChild(el("rect", { class: "stripe", x: 0, y: 0, width: 5, height: BOX_H, rx: 2 }));
  const corner = cornerWord(t);
  const cornerEl = corner ? grp.appendChild(el("text", { class: corner === "◆" ? "mark" : "model", x: BOX_W - 10, y: 17, "text-anchor": "end" }, corner)) : null;
  const title = grp.appendChild(el("text", { class: "title", x: 12, y: 19 }, t.title));
  fitText(title, BOX_W - 24 - (cornerEl ? cornerEl.getComputedTextLength() + 6 : 0)); // the title stops short of the corner's word
  grp.appendChild(el("text", { class: "sub", x: 12, y: 36 }, line));
  grp.appendChild(el("title", {}, `${t.title} · ${sub(t, 200)}`)); // the hover: the whole line
  // the fan: one chip a fork, hanging under the box, each on a line from the box's foot
  t.forks.forEach((f, i) => {
    const y = BOX_H + 6 + i * FORK_H, x = FORK_DX;
    const kept = t.kept?.letter === f.letter;
    grp.appendChild(el("path", { class: "fan", d: `M10,${BOX_H} C10,${y + 10} ${x - 8},${y + 10} ${x},${y + 10}` }));
    const chip = el("g", { class: `fork ${cls(f.state || "waiting")}${kept ? " kept" : ""}` });
    chip.appendChild(el("rect", { class: "chip", x, y: y + 1, width: CHIP_W, height: FORK_H - 3, rx: 4 }));
    chip.appendChild(el("text", { class: "chip-text", x: x + 8, y: y + 14 }, forkWords(f, t.kept)));
    const tip = el("title", {}, forkRow(f, t.kept));
    chip.appendChild(tip);
    grp.appendChild(chip);
  });
  // its dot, where its lines leave: drag it onto another task and that task waits on this one
  if (replaying()) return; // a replay is watched, not linked
  const port = el("circle", { class: "port", cx: down ? BOX_W / 2 : BOX_W, cy: down ? h : BOX_H / 2, r: 5, "data-port": t.id });
  port.appendChild(el("title", {}, "drag onto another task: it then waits on this one"));
  grp.appendChild(port);
}

// ---- the lanes: one row a task, wave by wave ----

const laneEls = new Map<string, { el: HTMLElement; key: string }>();
let lanesKey = "";

function lanes(s: StateX) {
  const root = $("lanes");
  const g = boxes(s);
  const order = layout(g.boxes, g.edges, { goal: g.goal, boxW: BOX_W, boxH: BOX_H });
  lay = null; // arrows walk the rows, not a drawing
  const waves: TaskX[][] = [];
  for (const t of s.tasks) {
    const r = order.boxes[t.id]?.rank ?? 0;
    (waves[r] ??= []).push(t);
  }
  for (const w of waves) w?.sort((p, q) => (order.boxes[p.id]?.y ?? 0) - (order.boxes[q.id]?.y ?? 0));
  const key = JSON.stringify([waves.map((w) => w?.map((t) => t.id)), selected, s.goal, done(s.tasks)]);
  const rows: HTMLElement[] = [];
  const seen = new Set<string>();
  waves.forEach((w, i) => {
    if (!w?.length) return;
    rows.push(div("wave", `wave ${i + 1} · ${done(w)} done`));
    for (const t of w) {
      seen.add(t.id);
      const k = JSON.stringify([t, t.id === selected, s.goals.find((x) => x.id === t.parent)?.title]);
      let have = laneEls.get(t.id);
      if (!have) {
        const row = div("lane fresh");
        row.tabIndex = 0;
        row.setAttribute("role", "button");
        row.dataset.id = t.id;
        row.addEventListener("click", () => clicked(t.id));
        row.addEventListener("keydown", (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); clicked(t.id); } });
        have = { el: row, key: "" };
        laneEls.set(t.id, have);
      }
      if (have.key !== k) { have.key = k; drawLane(have.el, t, s); }
      rows.push(have.el);
    }
  });
  for (const [id, have] of laneEls) if (!seen.has(id)) { have.el.remove(); laneEls.delete(id); }
  if (s.goal) {
    const goal = div("lane goal-row");
    goal.setAttribute("aria-label", `goal: ${s.goal}, ${done(s.tasks)} done`);
    goal.setAttribute("role", "group");
    goal.tabIndex = 0;
    div("l-title", s.goal, goal);
    div("l-sub", `goal · ${done(s.tasks)} done`, goal);
    rows.push(goal);
  }
  if (key === lanesKey) return; // the same rows in the same order: each row updated itself above
  lanesKey = key;
  root.replaceChildren(...rows); // a row that moved is moved, not made again
}

function drawLane(row: HTMLElement, t: TaskX, s: StateX) {
  row.replaceChildren();
  row.className = `lane ${cls(t.state)}${t.id === selected ? " selected" : ""}${t.needs_you ? " needs-you" : ""}`;
  const line = sub(t, 60);
  row.setAttribute("aria-label", `${t.title}: ${line}${t.id === selected ? ", selected" : ""}`);
  div("l-stripe", undefined, row);
  const main = div("l-main", undefined, row);
  const head = div("l-head", undefined, main);
  div("l-title", t.title, head);
  const corner = cornerWord(t);
  if (corner) div(corner === "◆" ? "l-mark" : "l-model", corner, head);
  div("l-sub", line, main);
  const band = t.parent ? goalTitle(s, t.parent) : "";
  if (band && band !== s.goal) div("l-band", band, main).title = band; // auto's root sub-goal is the goal itself: said once, at the foot
  if (t.forks.length) {
    const forks = div("l-forks", undefined, main);
    for (const f of t.forks) {
      const kept = t.kept?.letter === f.letter;
      const chip = div(`l-chip fork ${cls(f.state || "waiting")}${kept ? " kept" : ""}`, forkWords(f, t.kept, 40), forks);
      chip.title = forkRow(f, t.kept);
    }
  }
}

// ---- zoom and pan ----

/** The link being drawn: from the dragged task's dot to the pointer, curved as an edge is. */
function wireD(): string {
  const p = wiring && lay?.boxes[wiring.from];
  if (!wiring || !p || !lay) return "";
  if (lay.down) {
    const x1 = p.x + BOX_W / 2, y1 = p.y + p.h, dy = Math.max(16, Math.abs(wiring.y - y1) / 2);
    return `M${x1},${y1} C${x1},${y1 + dy} ${wiring.x},${wiring.y - dy} ${wiring.x},${wiring.y}`;
  }
  const x1 = p.x + BOX_W, y1 = p.y + BOX_H / 2, dx = Math.max(24, Math.abs(wiring.x - x1) / 2);
  return `M${x1},${y1} C${x1 + dx},${y1} ${wiring.x - dx},${wiring.y} ${wiring.x},${wiring.y}`;
}

/** Where the pointer is in the graph's own units: the SVG is drawn 1:1, then translated and scaled. */
function at(e: MouseEvent): { x: number; y: number } {
  const r = $("svg").getBoundingClientRect();
  return { x: (e.clientX - r.left) / zoom.k, y: (e.clientY - r.top) / zoom.k };
}

/** The whole graph in view when it fits at 1:1, else 1:1 from its top-left corner: never smaller than the
 *  type reads at, the rest is a pan or the `g` key away. */
function fit() {
  if (!lay) return;
  zoom = clamp({ k: 1, tx: 0, ty: 0 });
  fitted = true;
}

/** A pan never loses the graph: a graph wider than the canvas stays against an edge at most, a smaller one
 *  stays inside. */
function clamp(z: Zoom): Zoom {
  if (!lay) return z;
  const canvas = $("canvas");
  const w = canvas.clientWidth || 800, h = canvas.clientHeight || 600;
  const k = zoomK(z.k); // a remembered zoom from an older page is clamped as a new one is
  const gw = lay.width * k, gh = lay.height * k;
  const tx = gw <= w ? Math.max(0, (w - gw) / 2) : Math.min(0, Math.max(w - gw, z.tx));
  const ty = gh <= h ? Math.min(Math.max(0, z.ty), h - gh) : Math.min(0, Math.max(h - gh, z.ty));
  return { k, tx, ty };
}

function applyZoom() {
  const svg = $("svg");
  svg.style.transform = `translate(${zoom.tx}px, ${zoom.ty}px) scale(${zoom.k})`;
  svg.style.transformOrigin = "0 0";
  // the goal off screen, whole or in part: a chip at the edge says where it is, and a click brings it (as `g` does)
  const p = lay?.boxes[GOAL];
  const canvas = $("canvas");
  const off = Boolean(p && view() !== "lanes" && ((p.x + p.w) * zoom.k + zoom.tx > canvas.clientWidth || (p.y + p.h) * zoom.k + zoom.ty < 0
                      || p.y * zoom.k + zoom.ty > canvas.clientHeight || (p.x + p.w) * zoom.k + zoom.tx < 0));
  $("to-goal").hidden = !off;
  if (p && off) $("to-goal").classList.toggle("below", p.y * zoom.k + zoom.ty > canvas.clientHeight);
}

/** Pan so a box is on screen (the goal on `g`, a task the host selects). */
function reveal(id: string) {
  const p = lay?.boxes[id];
  if (!p || !lay) return;
  const canvas = $("canvas");
  const w = canvas.clientWidth, h = canvas.clientHeight;
  const x0 = p.x * zoom.k + zoom.tx, x1 = (p.x + p.w) * zoom.k + zoom.tx;
  const y0 = p.y * zoom.k + zoom.ty, y1 = (p.y + p.h) * zoom.k + zoom.ty;
  let { tx, ty } = zoom;
  if (x0 < 0) tx -= x0 - 12; else if (x1 > w) tx -= x1 - w + 12;
  if (y0 < 0) ty -= y0 - 12; else if (y1 > h) ty -= y1 - h + 12;
  zoom = clamp({ ...zoom, tx, ty });
  moved = true;
  remember({ zoom });
  applyZoom();
}

// ---- selection, the pane, the hint, the help ----

function clicked(id: string) {
  first();
  if (linking && linking !== id) {
    api.postMessage({ type: "act", act: "link", id: linking, target: id });
    linking = null;
    select(id);
    return;
  }
  select(id);
}

function select(id: string | null, focus = false) {
  selected = id;
  render();
  if (id && focus) {
    const node = (view() === "lanes" ? laneEls.get(id)?.el : taskEls.get(id)?.g) as HTMLElement | SVGGElement | undefined;
    node?.focus({ preventScroll: view() !== "lanes" });
    if (view() !== "lanes") reveal(id);
  }
}

/** Link mode off: nothing armed, no wire drawn. On Esc, Cancel, or a select from outside the graph. */
function disarm() {
  linking = null;
  wiring = null;
  $("canvas").classList.remove("wiring");
}

function hint() {
  const h = $("hint");
  const from = wiring?.from ?? linking;
  if (from && state) {
    const a = state.tasks.find((t) => t.id === from);
    const cancel = document.createElement("button");
    cancel.className = "quiet";
    cancel.textContent = "Cancel";
    cancel.title = "stop linking (Esc)";
    cancel.addEventListener("click", () => { disarm(); render(); });
    h.replaceChildren(div("hint-text", linkHint(a?.title ?? from, Boolean(wiring))), cancel);
    h.className = "linking";
  } else if (state?.questions.length) { // an open question outranks the news: answering it is the person's
    const q = state.questions[0]!;
    const about = q.about ? state.tasks.find((t) => t.id === q.about)?.title : "";
    h.textContent = `question${about ? ` on “${about}”` : ""}: ${q.text}${q.default ? ` (unanswered: ${q.default})` : ""}`;
    h.className = "asks";
  } else if (!saved.hinted) {
    h.textContent = FIRST_HINT;
    h.className = "";
  } else { // the news, or, narrow, the line the header has no room for
    h.textContent = state ? state.news[state.news.length - 1] || headerFor(state, narrow()).footer : "";
    h.className = "";
  }
}

function row(label: string, value: string, parent: HTMLElement): HTMLDivElement | null {
  if (!value) return null;
  const r = div("row", undefined, parent);
  div("k", label, r);
  div("v", value, r);
  return r;
}

let paneLast = "";

/** The pane is rebuilt only when what it shows changed (its key); then the focused button, by its words,
 *  and the scroll are kept, so a keyboard user reaches its buttons while a run writes the store. */
function pane() {
  const pane = $("details");
  const key = state ? paneKey(state, selected, replaying()) : "";
  if (key === paneLast) return;
  paneLast = key;
  const t = state?.tasks.find((x) => x.id === selected);
  if (!state || !t || !key) { pane.hidden = true; pane.replaceChildren(); return; }
  const was = pane.contains(document.activeElement) ? document.activeElement : null;
  const mark = (e: Element) => `${e.className}|${e.textContent}|${e.getAttribute("aria-label") ?? ""}`;
  const want = was ? mark(was) : "";
  const top = pane.querySelector(".d-body")?.scrollTop ?? 0; // wide, the body scrolls; narrow, the whole pane
  const paneTop = pane.scrollTop;
  pane.replaceChildren();
  const s = state;
  pane.hidden = false;
  queueMicrotask(() => {
    if (want) Array.from(pane.querySelectorAll("button")).find((b) => mark(b) === want)?.focus({ preventScroll: true });
    body.scrollTop = top;
    pane.scrollTop = paneTop;
  });
  const head = div("d-head", undefined, pane);
  div(`d-title ${cls(t.state)}`, t.title, head);
  div("d-id", `${t.id} · ${SAY[t.state]}${t.needs_you ? " · needs you" : ""}`, head);
  const close = document.createElement("button");
  close.className = "close";
  close.appendChild(icon("close"));
  close.title = "close (Esc)";
  close.setAttribute("aria-label", "close");
  close.addEventListener("click", () => select(null));
  head.appendChild(close);
  const body = div("d-body", undefined, pane);
  if (t.state === "came back" && t.why) div("why", t.why, body);
  const q = questionOn(s, t.id);
  if (q) { // its question, with the options to answer inline
    const ask = div("ask", undefined, body);
    div("ask-text", q.text, ask);
    if (!replaying()) {
      const opts = div("ask-opts", undefined, ask);
      const options = [...new Set([...(q.default ? [q.default] : []), ...q.options])];
      for (const o of options) {
        const b = document.createElement("button");
        b.className = o === q.default ? "" : "quiet";
        b.textContent = o;
        b.title = o === q.default ? "the default: what happens unanswered" : "answer with this";
        b.addEventListener("click", () => api.postMessage({ type: "act", act: "answer", id: q.id, target: o }));
        opts.appendChild(b);
      }
      const own = document.createElement("button");
      own.className = "quiet";
      own.appendChild(icon("comment-discussion"));
      own.appendChild(document.createTextNode("In your own words…"));
      own.addEventListener("click", () => api.postMessage({ type: "act", act: "answer", id: q.id }));
      opts.appendChild(own);
    }
  }
  row("what for", t.full, body);
  row("under", t.parent ? goalTitle(s, t.parent) : "", body);
  row("may change", t.scope.join("  "), body);
  row("done when", t.check ? `${t.check} passes` : "", body);
  if (t.hollow) div("hollow", "its check passed before the work too: it proves nothing new", body); // as the cockpit says
  if (t.needs.length) { // what it waits on, each with the × that stops it waiting
    const r = div("row", undefined, body);
    div("k", "after", r);
    const v = div("v", undefined, r);
    for (const n of t.needs) {
      const need = div("need", s.tasks.find((x) => x.id === n)?.title ?? n, v);
      if (replaying()) continue;
      const x = document.createElement("button");
      x.className = "unlink";
      x.appendChild(icon("close"));
      x.title = "stop waiting on it";
      x.setAttribute("aria-label", `stop waiting on ${s.tasks.find((y) => y.id === n)?.title ?? n}`);
      x.addEventListener("click", () => api.postMessage({ type: "act", act: "unlink", id: t.id, target: n }));
      need.appendChild(x);
    }
  }
  row("agent", t.agent ? `agent ${t.agent}${t.model ? ` · ${t.model}` : ""}` : "", body);
  row("tries", t.attempts !== undefined && t.attempts > 1 ? String(t.attempts) : "", body);
  row("cost", usd(t.usd), body);
  row("quiet", t.idle !== null && t.idle > 8 ? `${Math.round(t.idle)} s` : "", body);
  row("note", t.note, body);
  row("wanted", t.outside.join("  "), body);
  if (t.forks.length) {
    const r = div("row", undefined, body);
    div("k", "attempts", r);
    const v = div("v", undefined, r);
    for (const f of t.forks) {
      const kept = t.kept?.letter === f.letter;
      const fr = div(`fork-row ${cls(f.state || "waiting")}${kept ? " kept" : ""}`, undefined, v);
      div("fork-words", forkRow(f, t.kept), fr);
      const acts = div("fork-acts", undefined, fr);
      for (const b of forkActs(t, f, replaying())) button({ ...b, main: false }, t.id, acts);
    }
  }
  if (t.tail.length) {
    const r = div("row", undefined, body);
    div("k", "last moves", r);
    const v = div("v", undefined, r);
    for (const line of t.tail.slice(-6)) div("move", line, v);
  }
  const acts = div("d-acts", undefined, pane);
  for (const b of actsFor(t, replaying())) button(b, t.id, acts);
}

let helpFrom: Element | null = null; // where the focus was when ? opened: it goes back there on Esc

/** The keys, as a dialog: the focus moves into it and returns on Esc. */
function help(show: boolean) {
  const h = $("help");
  h.hidden = !show;
  if (!show) { (helpFrom as HTMLElement | null)?.focus?.({ preventScroll: true }); helpFrom = null; return; }
  helpFrom = document.activeElement;
  if (!h.childElementCount) {
    h.setAttribute("role", "dialog");
    h.setAttribute("aria-modal", "true");
    h.setAttribute("aria-label", "Keys");
    const card = div("help-card", undefined, h);
    card.tabIndex = -1;
    div("help-title", "Keys", card);
    const table = div("help-rows", undefined, card);
    for (const [key, what] of KEYS) {
      div("help-key", key, table);
      div("help-what", what, table);
    }
    div("help-foot", "Esc closes", card);
  }
  (h.firstElementChild as HTMLElement).focus({ preventScroll: true });
}

function notice(st: Status) {
  const n = $("notice");
  n.hidden = false;
  n.textContent = st.text;
  n.className = st.kind;
  for (const id of ["bands", "edges", "tasks", "goalg"]) ($(id) as unknown as SVGGElement).replaceChildren();
  taskEls.clear(); edgeEls.clear(); goalKey = "";
  $("lanes").replaceChildren(); laneEls.clear(); lanesKey = "";
  $("details").hidden = true; paneLast = "";
  $("goal").textContent = "Graphene";
  $("counts").textContent = "";
  $("auto").hidden = true;
  $("replay").hidden = true;
}

// ---- messages and keys ----

window.addEventListener("message", (e: MessageEvent<Incoming>) => {
  const m = e.data;
  if (!m || typeof m !== "object") return;
  if (m.type === "state") {
    const json = JSON.stringify(m.state);
    if (json === lastJson) return; // nothing changed: nothing moves
    lastJson = json;
    state = m.state;
    if (selected && !state.tasks.some((t) => t.id === selected)) selected = null;
    if (linking && !state.tasks.some((t) => t.id === linking)) linking = null;
    render();
  } else if (m.type === "status") {
    lastJson = "";
    notice(m.status);
  } else if (m.type === "select") { // a click in the Plan view: the link, if armed, is not for that task
    disarm();
    select(m.id, true);
  }
});

function first() { // the first touch: the first-time hint has done its work
  if (saved.hinted) return;
  remember({ hinted: true });
  hint();
}

window.addEventListener("keydown", (e) => {
  if ((e.target as HTMLElement).tagName === "BUTTON" && (e.key === "Enter" || e.key === " ")) return;
  if (e.key === "Escape") {
    if (!$("help").hidden) help(false);
    else if (wiring || linking) disarm();
    else selected = null;
    render();
    return;
  }
  if (e.key === "?") { help($("help").hidden); first(); return; }
  if (e.metaKey || e.ctrlKey || e.altKey) return;
  if (e.key === "g" && state) { // the goal, on screen
    if (view() === "lanes") $("lanes").querySelector(".goal-row")?.scrollIntoView({ block: "nearest" });
    else reveal(GOAL);
    return;
  }
  if (e.key === "f") { moved = false; fit(); remember({ zoom: undefined }); applyZoom(); return; }
  if (e.key === "v") { remember({ view: view() === "lanes" ? "graph" : "lanes" }); fitted = false; render(); return; }
  const keys: Record<string, "left" | "right" | "up" | "down"> = { ArrowLeft: "left", ArrowRight: "right", ArrowUp: "up", ArrowDown: "down" };
  const dir = keys[e.key];
  if (!dir || !state) return;
  e.preventDefault();
  first();
  const goalG = $("goalg");
  const from = document.activeElement === goalG ? GOAL : selected; // the arrows walk from the goal box too
  if (!from) { select(state.tasks[0]?.id ?? null, true); return; }
  if (!lay) { // the lanes: along the rows
    const rows = Array.from($("lanes").querySelectorAll<HTMLElement>(".lane[data-id]")).map((r) => r.dataset.id!);
    const i = rows.indexOf(from);
    const next = dir === "down" || dir === "right" ? rows[i + 1] : rows[i - 1];
    if (next) select(next, true);
    return;
  }
  const next = step(lay, from, dir);
  if (next === GOAL) { goalG.focus({ preventScroll: true }); reveal(GOAL); return; } // the goal is not a task: focused, not selected
  if (next) select(next, true);
});

function wire() {
  const canvas = $("canvas");
  canvas.addEventListener("wheel", (e) => {
    if (view() === "lanes") return; // the rows scroll as a list does
    e.preventDefault();
    first();
    if (e.ctrlKey || e.metaKey) { // a pinch, or the wheel with the modifier: zoom about the pointer
      const rect = canvas.getBoundingClientRect();
      const px = e.clientX - rect.left, py = e.clientY - rect.top;
      const k = zoomK(zoom.k * Math.exp(-e.deltaY * 0.01));
      zoom = clamp({ k, tx: px - (px - zoom.tx) * (k / zoom.k), ty: py - (py - zoom.ty) * (k / zoom.k) });
    } else {
      zoom = clamp({ ...zoom, tx: zoom.tx - e.deltaX, ty: zoom.ty - e.deltaY }); // the wheel scrolls, as a page does
    }
    moved = true;
    remember({ zoom });
    applyZoom();
  }, { passive: false });
  let drag: { x: number; y: number; tx: number; ty: number } | null = null;
  canvas.addEventListener("mousedown", (e) => {
    if (view() === "lanes") return;
    const port = (e.target as Element).closest("[data-port]");
    if (port && !replaying()) { // a drag from a task's dot draws a link
      e.preventDefault();
      first();
      wiring = { from: port.getAttribute("data-port")!, ...at(e) };
      canvas.classList.add("wiring");
      render();
      return;
    }
    if ((e.target as Element).closest(".task, .goal")) return;
    drag = { x: e.clientX, y: e.clientY, tx: zoom.tx, ty: zoom.ty };
    canvas.classList.add("dragging");
  });
  window.addEventListener("mousemove", (e) => {
    if (wiring) {
      Object.assign(wiring, at(e));
      $("wire").setAttribute("d", wireD());
      return;
    }
    if (!drag) return;
    zoom = clamp({ ...zoom, tx: drag.tx + e.clientX - drag.x, ty: drag.ty + e.clientY - drag.y });
    moved = true;
    applyZoom();
  });
  window.addEventListener("mouseup", (e) => {
    if (wiring) { // dropped on another task: it waits on the one dragged from, as Link to… then a click
      const from = wiring.from;
      const target = document.elementFromPoint(e.clientX, e.clientY)?.closest(".task")?.getAttribute("data-id");
      wiring = null;
      canvas.classList.remove("wiring");
      if (target && target !== from) {
        api.postMessage({ type: "act", act: "link", id: from, target });
        select(target);
      } else render();
      return;
    }
    if (drag) remember({ zoom });
    drag = null;
    canvas.classList.remove("dragging");
  });
  canvas.addEventListener("click", (e) => { if (!(e.target as Element).closest(".task, .lane, .goal")) first(); });
  canvas.addEventListener("dblclick", (e) => {
    if ((e.target as Element).closest(".task, .goal, .lane")) return;
    moved = false;
    fit();
    remember({ zoom: undefined });
    applyZoom();
  });
  // the details pane opening narrows the canvas, as does a narrower window: a narrow one turns to lanes or
  // lays the graph downward, and the graph keeps its corner in view until the person pans themselves
  let lastW = canvas.clientWidth;
  new ResizeObserver(() => {
    if (!state) return;
    const w = canvas.clientWidth;
    if (modeFor(w) !== modeFor(lastW) || (view() !== "lanes" && lay?.down)) { lastW = w; render(); return; }
    lastW = w;
    if (lay && !moved) { fit(); applyZoom(); } else if (lay) { zoom = clamp(zoom); applyZoom(); }
  }).observe(canvas);
  $("help").addEventListener("click", (e) => { if (e.target === $("help")) help(false); });
  const toGoal = $("to-goal");
  toGoal.appendChild(document.createTextNode("goal"));
  toGoal.appendChild(icon("arrow-right"));
  toGoal.title = "the goal is off screen: bring it (g)";
  toGoal.addEventListener("click", () => reveal(GOAL));
  // the header's buttons
  const actions = $("actions");
  const top = (id: string, label: string, ico: string, title: string, on: () => void) => {
    const b = document.createElement("button");
    b.id = id;
    b.className = "quiet";
    b.appendChild(icon(ico));
    b.appendChild(document.createTextNode(label));
    b.title = title;
    b.addEventListener("click", on);
    actions.appendChild(b);
  };
  top("b-add", "Add task…", "add", "a task in a sentence: the planner fills in its files and its check", () => api.postMessage({ type: "act", act: "add-under", id: "" }));
  top("b-run", "Run", "play", "start an agent on every task that is ready", () => api.postMessage({ type: "act", act: state?.run.going ? "stop" : "run", id: "" }));
  top("b-view", "Lanes", "list-flat", "graph or lanes (v)", () => { remember({ view: view() === "lanes" ? "graph" : "lanes" }); fitted = false; render(); });
  top("b-help", "", "question", "every key (?)", () => help($("help").hidden));
  $("b-help").setAttribute("aria-label", "keys");
  // narrow, the buttons hide behind one `…` beside the goal, so the header is one line
  const more = document.createElement("button");
  more.id = "b-more";
  more.className = "quiet";
  more.appendChild(icon("ellipsis"));
  more.title = "the buttons";
  more.setAttribute("aria-label", "the buttons");
  more.setAttribute("aria-expanded", "false");
  more.addEventListener("click", () => {
    const open = document.querySelector("header")!.classList.toggle("open");
    more.setAttribute("aria-expanded", String(open));
  });
  $("goal").after(more);
  matchMedia("(max-width: 700px)").addEventListener("change", render); // the header's lines move
  $("hint").setAttribute("aria-live", "polite"); // a question or a hand-back is announced
  api.postMessage({ type: "ready" });
}

wire();
