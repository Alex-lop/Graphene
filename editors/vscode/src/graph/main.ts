// The graph, in the webview: boxes for the tasks coloured by their state, bands for the sub-goals, the goal
// at the right (or at the foot, when the view is narrow), a forked task fanning out into its forks; or, in
// the sidebar, the same plan as lanes, one row a task, wave by wave. A click selects and opens the details
// pane whose buttons ask the extension to run graphene. No network, no library: SVG and DOM from the state.
// Boxes are keyed by task id and updated in place, so a snapshot that changed nothing moves nothing.
import { layout, modeFor, step, type Box, type Edge, type Layout } from "../layout.ts";
import { autoLine, SAY, usd, type State } from "../state.ts";
import { ICONS } from "./icons.ts";
import { blanks, draftLine, globs, isDraft, lacks, type Draft } from "./draft.ts";
import { actsFor, attemptsOf, cornerWord, cut, done, editable, fan, FIRST_HINT, fitWidth, forkActs, forkRow, forkWords, HEADER_ACTS, headerFor, KEYS, linkHint, paneKey,
         questionOn, sub, tabOrder, topLine, whenEdit, zoomK, type Button, type StateX, type TaskX } from "./words.ts";

declare function acquireVsCodeApi(): { postMessage(m: unknown): void; getState(): unknown; setState(s: unknown): void };

type Status = { kind: "reading" | "missing" | "uninitialised" | "error" | "nofolder"; text: string };
type Incoming = { type: "state"; state: StateX } | { type: "status"; status: Status } | { type: "select"; id: string }
  | { type: "said"; id?: string; key?: string; ok: boolean; line: string; made?: string }; // graphene's answer to a change made here
type Zoom = { k: number; tx: number; ty: number };
type View = "auto" | "graph" | "lanes";
type Saved = { zoom?: Zoom; hinted?: boolean; view?: View; drafts?: Draft[]; drew?: number };

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
// the tasks being drawn: the page's own until graphene takes them (kept with the page's state, so a hidden
// tab keeps them). ponytail: each page keeps its own, so a draft in the side bar is not in the tab; the plan
// would have to hold drafts for that
let drafts: Draft[] = (saved.drafts ?? []).filter((d) => d.title.trim());
let naming: string | null = null; // the draft whose title is being typed on its box
const offered = new Set<string>(); // drafts graphene is being asked to take: not offered twice
const refused = new Map<string, string>(); // a task's id -> graphene's refusal of the last change to it
let arriving: string | null = null; // a drawn task graphene took: selected once the plan shows it

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
    const near = state?.tasks.find((t) => t.id === id);
    if (b.act === "add-after" && near) return draw({ after: id, parent: near.parent });
    if (b.act === "add-under") return draw({ after: null, parent: near?.parent ?? null });
    api.postMessage({ type: "act", act: b.act, id, ...(b.fork ? { fork: b.fork } : {}) });
  });
  parent.appendChild(btn);
}

const cls = (word: string) => `st-${word.replace(/\s+/g, "-")}`;

function boxes(s: StateX): { boxes: Box[]; edges: Edge[]; goal: string | null } {
  const bs: Box[] = s.tasks.map((t) => {
    const n = fan(t, s.envelope.forks).length;
    return { id: t.id, band: t.parent ?? "", w: n ? FORK_DX + CHIP_W : BOX_W, h: BOX_H + (n ? FORK_H * n + 6 : 0) };
  });
  const edges: Edge[] = s.edges.filter(([, , kind]) => kind === "needs").map(([a, b]) => [a, b]);
  for (const d of drawn()) { // a drawn task is a box as any other, after the task it waits on
    bs.push({ id: d.key, band: d.parent ?? "", w: BOX_W, h: BOX_H });
    if (d.after) edges.push([d.after, d.key]);
  }
  const hasGoal = Boolean(s.goal) && s.tasks.length > 0;
  if (hasGoal) {
    bs.push({ id: GOAL, band: "", w: GOAL_W, h: GOAL_H });
    const needed = new Set(edges.map(([a]) => a));
    for (const b of bs) if (b.id !== GOAL && !needed.has(b.id)) edges.push([b.id, GOAL]);
  }
  return { boxes: bs, edges, goal: hasGoal ? GOAL : null };
}

// ---- drawing a task by hand ----

/** The drafts on screen: none in a replay, which is watched. */
const drawn = (): Draft[] => (replaying() ? [] : drafts);

/** A new draft box, after a task or on its own, its title typed on the box. */
function draw(at: { after: string | null; parent: string | null }) {
  if (!state || replaying()) return;
  first();
  const n = (saved.drew ?? 0) + 1;
  const d: Draft = { key: ` d${n}`, title: "", files: "", check: "", approve: false, ...at };
  drafts = [...drafts, d];
  remember({ drafts, drew: n });
  naming = d.key;
  select(d.key);
  reveal(d.key);
}

/** A draft's field changed: kept, and once it lacks nothing graphene is asked to take it (`node add`). */
function redraw(key: string, patch: Partial<Draft>) {
  const d = drafts.find((x) => x.key === key);
  if (!d) return;
  Object.assign(d, patch, { said: undefined });
  remember({ drafts });
  if (!lacks(d).length && !offered.has(key)) {
    offered.add(key);
    api.postMessage({ type: "act", act: "draw", id: "", draft: { key, title: d.title, files: d.files, check: d.check, approve: d.approve, after: d.after, parent: d.parent } });
  }
  setTimeout(render, 0); // once the focus has landed: a box left for the next one is not rebuilt under it
}

function discard(key: string) {
  drafts = drafts.filter((d) => d.key !== key);
  offered.delete(key);
  remember({ drafts });
  if (naming === key) naming = null;
  if (selected === key) selected = null;
  render();
}

/** The title typed on a draft's box: kept, and the files are next; an empty one takes the draft away. */
function named(key: string, title: string) {
  if (naming !== key) return; // Enter, then the blur of the box it took away
  naming = null;
  if (!title.trim()) return discard(key);
  redraw(key, { title: title.trim() });
  setTimeout(() => document.getElementById("f-files")?.focus(), 0);
}

/** The box a title is typed in, on a draft: Enter keeps it, Esc leaves it as it was. */
function nameInput(d: Draft): HTMLInputElement {
  const input = document.createElement("input");
  input.className = "name";
  input.value = d.title;
  input.placeholder = "what this task does";
  input.spellcheck = false;
  input.setAttribute("aria-label", "the new task's title");
  input.addEventListener("click", (e) => e.stopPropagation());
  input.addEventListener("mousedown", (e) => e.stopPropagation());
  input.addEventListener("keydown", (e) => {
    e.stopPropagation(); // typed words are not the graph's keys
    if (e.key === "Enter") named(d.key, input.value);
    if (e.key === "Escape") named(d.key, d.title);
  });
  input.addEventListener("blur", () => named(d.key, input.value));
  setTimeout(() => input.focus(), 0);
  return input;
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
  $("notice").hidden = s.tasks.length > 0 || drawn().length > 0;
  if (!s.tasks.length) {
    $("notice").className = "";
    $("notice").textContent = replaying() ? "Nothing is planned yet." : "Nothing is planned yet. Draw the first task here, or say what you want on Home.";
    if (!replaying()) button({ label: "Add task", act: "add-under", title: "draw a task: its title, then its files and its check", icon: "add", main: true }, "", $("notice"));
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
    path.classList.toggle("draft", isDraft(a) || isDraft(b));
  }
  for (const [key, path] of edgeEls) if (!seenEdges.has(key)) { path.remove(); edgeEls.delete(key); }
  // boxes: one group a task, rebuilt only when its words or its place changed
  const tasks = $("tasks") as unknown as SVGGElement;
  const seen = new Set<string>();
  const box = (id: string, key: string, paint: (g: SVGGElement, h: number) => void) => {
    const p = lay!.boxes[id];
    if (!p) return;
    seen.add(id);
    key = JSON.stringify([key, p.x, p.y, id === selected, down]);
    let have = taskEls.get(id);
    if (have && have.key === key) return;
    if (!have) {
      const grp = el("g", { class: "task fresh", "data-id": id, tabindex: 0, role: "button" });
      grp.style.transform = `translate(${p.x}px, ${p.y}px)`; // placed before it joins: no glide from the corner
      grp.addEventListener("click", (e) => { e.stopPropagation(); clicked(id); });
      grp.addEventListener("keydown", (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); e.stopPropagation(); clicked(id); } });
      tasks.appendChild(grp);
      have = { g: grp, key: "" };
      taskEls.set(id, have);
    }
    have.key = key;
    paint(have.g, p.h);
    have.g.style.transform = `translate(${p.x}px, ${p.y}px)`;
  };
  for (const t of s.tasks) box(t.id, JSON.stringify([t, s.envelope.forks]), (grp, h) => drawTask(grp, t, h, down, s.envelope.forks));
  for (const d of drawn()) box(d.key, JSON.stringify([d, naming === d.key]), (grp) => drawDraft(grp, d));
  for (const [id, have] of taskEls) if (!seen.has(id)) { have.g.remove(); taskEls.delete(id); }
  // Tab walks the boxes wave by wave, which is their order in the DOM: reordered only when it changed
  const want = tabOrder(lay, [...s.tasks.map((t) => t.id), ...drawn().map((d) => d.key)]);
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
function drawTask(grp: SVGGElement, t: TaskX, h: number, down: boolean, limit: number | null) {
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
  fan(t, limit).forEach((f, i) => { // before anything runs: one waiting chip for each attempt it is set to
    const y = BOX_H + 6 + i * FORK_H, x = FORK_DX;
    const kept = t.kept?.letter === f.letter;
    grp.appendChild(el("path", { class: "fan", d: `M10,${BOX_H} C10,${y + 10} ${x - 8},${y + 10} ${x},${y + 10}` }));
    const chip = el("g", { class: `fork ${cls(f.state || "waiting")}${kept ? " kept" : ""}${t.forks.length ? "" : " planned"}` });
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
  // its +, on the corner: a new task drawn after this one
  const plus = el("g", { class: "plus", "data-plus": t.id });
  plus.appendChild(el("circle", { cx: BOX_W - 1, cy: 1, r: 8 }));
  plus.appendChild(el("path", { d: `M${BOX_W - 5},1 h8 M${BOX_W - 1},-3 v8` }));
  plus.appendChild(el("title", {}, "draw a task after this one"));
  plus.addEventListener("click", (e) => { e.stopPropagation(); draw({ after: t.id, parent: t.parent }); });
  grp.appendChild(plus);
}

/** A draft's box: dashed, its title (typed here while it is new), and its blanks until they are filled. */
function drawDraft(grp: SVGGElement, d: Draft) {
  grp.replaceChildren();
  grp.setAttribute("class", `task draft${d.key === selected ? " selected" : ""}`);
  grp.setAttribute("aria-label", `a draft: ${d.title || "no title yet"}: ${blanks(d)}${d.key === selected ? ", selected" : ""}`);
  grp.appendChild(el("rect", { class: "box", x: 0, y: 0, width: BOX_W, height: BOX_H, rx: 6 }));
  grp.appendChild(el("rect", { class: "stripe", x: 0, y: 0, width: 5, height: BOX_H, rx: 2 }));
  if (naming === d.key) {
    const fo = el("foreignObject", { x: 9, y: 3, width: BOX_W - 16, height: 24 });
    fo.appendChild(nameInput(d));
    grp.appendChild(fo);
  } else {
    fitText(grp.appendChild(el("text", { class: "title", x: 12, y: 19 }, d.title)), BOX_W - 24);
  }
  grp.appendChild(el("text", { class: `sub${d.said ? " bad" : ""}`, x: 12, y: 36 }, d.said ? "not taken: see why" : blanks(d)));
  grp.appendChild(el("title", {}, `a draft: ${d.title} · ${blanks(d)}`));
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
  const key = JSON.stringify([waves.map((w) => w?.map((t) => t.id)), selected, s.goal, done(s.tasks), drawn(), naming]);
  const rows: HTMLElement[] = [];
  const seen = new Set<string>();
  waves.forEach((w, i) => {
    if (!w?.length) return;
    rows.push(div("wave", `wave ${i + 1} · ${done(w)} done`));
    for (const t of w) {
      seen.add(t.id);
      const k = JSON.stringify([t, t.id === selected, s.goals.find((x) => x.id === t.parent)?.title, s.envelope.forks]);
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
  if (drawn().length) rows.push(div("wave", "drawn, not in the plan yet"));
  for (const d of drawn()) { // few, so made again each time; kept only when the rows changed (the key above)
    const row = div(`lane draft${d.key === selected ? " selected" : ""}`);
    row.tabIndex = 0;
    row.setAttribute("role", "button");
    row.dataset.id = d.key;
    row.addEventListener("click", () => clicked(d.key));
    row.addEventListener("keydown", (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); clicked(d.key); } });
    div("l-stripe", undefined, row);
    const main = div("l-main", undefined, row);
    if (naming === d.key) main.appendChild(nameInput(d)); else div("l-title", d.title, main);
    div(`l-sub${d.said ? " bad" : ""}`, d.said ? "not taken: see why" : blanks(d), main);
    rows.push(row);
  }
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
  const attempts = fan(t, s.envelope.forks);
  if (attempts.length) {
    const forks = div("l-forks", undefined, main);
    for (const f of attempts) {
      const kept = t.kept?.letter === f.letter;
      const chip = div(`l-chip fork ${cls(f.state || "waiting")}${kept ? " kept" : ""}${t.forks.length ? "" : " planned"}`, forkWords(f, t.kept, 40), forks);
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
    if (isDraft(id)) redraw(id, { after: linking }); // a draft waits on it from the start
    else api.postMessage({ type: "act", act: "link", id: linking, target: id });
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
let paneOf: string | null = null; // whose pane is drawn

/** A line of the pane's form: its label and a box to type in. Enter goes on to the next box (and keeps what
 *  was typed, as leaving the box does); Esc puts back what was there. */
function field(parent: HTMLElement, name: string, label: string, value: string, placeholder: string, hover: string, on: (v: string) => void): HTMLInputElement {
  const r = div("row", undefined, parent);
  const k = document.createElement("label");
  k.className = "k";
  k.textContent = label;
  const input = document.createElement("input");
  input.id = k.htmlFor = `f-${name}`;
  input.className = "f";
  input.type = "text";
  input.value = value;
  input.placeholder = placeholder;
  input.title = hover;
  input.spellcheck = false;
  input.addEventListener("change", () => on(input.value));
  input.addEventListener("keydown", (e) => {
    e.stopPropagation(); // typed words are not the graph's keys
    if (e.key === "Enter") {
      const all = Array.from($("details").querySelectorAll<HTMLInputElement>("input.f"));
      const next = all[all.indexOf(input) + 1];
      if (next) next.focus(); else input.blur();
    }
    if (e.key === "Escape") { input.value = value; input.blur(); }
  });
  // what changed while it was typed in is drawn once the form is left (Enter goes on to the next box: not yet)
  input.addEventListener("blur", () => setTimeout(() => { if (paneLast === "stale") pane(); }, 0));
  r.append(k, input);
  return input;
}

/** A yes or no of the form: a tick box with its words. */
function tick(parent: HTMLElement, name: string, label: string, on: boolean, hover: string, set: (v: boolean) => void, off = false) {
  const l = document.createElement("label");
  l.className = "tick";
  l.title = hover;
  const c = document.createElement("input");
  c.type = "checkbox";
  c.id = `f-${name}`;
  c.checked = on;
  c.disabled = off;
  c.addEventListener("change", () => set(c.checked));
  l.append(c, document.createTextNode(label));
  parent.appendChild(l);
}

/** One field of a task, to graphene (`node set`): its answer comes back as `said`, and the plan after it. */
function setField(t: TaskX, name: "title" | "scope" | "check" | "forks" | "signoff" | "owner", value: string | number | boolean) {
  refused.delete(t.id);
  api.postMessage({ type: "act", act: "set", id: t.id, field: name, value });
}

/** A task's form: its title, the files it may change, its check, its attempts, your approval, and whether it
 *  is yours; each change is graphene's to take or refuse, and the line under them says what it does now. */
function form(body: HTMLElement, t: TaskX, s: StateX) {
  const same = (a: string, b: string) => a.trim() === b.trim();
  const back = () => setTimeout(() => { paneLast = ""; pane(); }, 0); // what was typed is not a change: the form as it was
  field(body, "title", "title", t.full || t.title, "what this task does", "the task, in a line",
        (v) => (!v.trim() || same(v, t.full || t.title) ? back() : setField(t, "title", v.trim())));
  field(body, "files", "files", t.scope.join(" "), "src/api/** tests/test_api.py", "the files it may change: paths or globs, a space between",
        (v) => (!globs(v).length || globs(v).join(" ") === t.scope.join(" ") ? back() : setField(t, "scope", globs(v).join(" "))));
  field(body, "check", "check", t.check ?? "", "a command that passes when it is done", "the command that passes only when the task is done; empty: your approval finishes it",
        (v) => (same(v, t.check ?? "") ? back() : setField(t, "check", v.trim())));
  const n = attemptsOf(t, s.envelope.forks);
  const r = div("row", undefined, body);
  div("k", "attempts", r);
  const v = div("v stepper", undefined, r);
  const step = (label: string, to: number, sign: string) => {
    const b = document.createElement("button");
    b.className = "quiet";
    b.textContent = sign;
    b.setAttribute("aria-label", label);
    b.title = t.check ? label : "attempts need a check to keep one";
    b.disabled = !t.check || to < 1 || to > 8;
    b.addEventListener("click", () => setField(t, "forks", to));
    v.appendChild(b);
  };
  step("one attempt fewer", n - 1, "−");
  div("count", String(n), v).setAttribute("aria-label", `${n} attempt${n > 1 ? "s" : ""}`);
  step("one more attempt", n + 1, "+");
  div("dim", !t.check ? "one agent: attempts need a check to keep one" : n > 1 ? "agents at once; its check keeps one" : "one agent", v);
  const unread = t.signoff === null; // `graphene plan --json` not read yet: a moment
  tick(body, "signoff", "wait for my approval", t.signoff === true, "it lands only once you approve it, as well as passing its check", (on) => setField(t, "signoff", on), unread);
  tick(body, "owner", "I will do this one", Boolean(t.owner) && t.owner !== "agent", "no agent takes it: it is yours to do", (on) => setField(t, "owner", on), unread);
  div("when", whenEdit(t), body);
  const no = refused.get(t.id);
  if (no) div("refused", no, body).setAttribute("role", "alert");
}

/** A draft's pane: the same form, its own; what it still lacks, or graphene's refusal; and the planner, a click away. */
function draftPane(pane: HTMLElement, d: Draft) {
  const head = div("d-head", undefined, pane);
  div("d-title st-draft", d.title || "A new task", head);
  div("d-id", "a draft · not in the plan yet", head);
  const close = document.createElement("button");
  close.className = "close";
  close.appendChild(icon("close"));
  close.title = "close (Esc)";
  close.setAttribute("aria-label", "close");
  close.addEventListener("click", () => select(null));
  head.appendChild(close);
  const body = div("d-body", undefined, pane);
  field(body, "title", "title", d.title, "what this task does", "the task, in a line", (v) => (v.trim() ? redraw(d.key, { title: v.trim() }) : redraw(d.key, {})));
  field(body, "files", "files", d.files, "src/api/** tests/test_api.py", "the files it may change: paths or globs, a space between", (v) => redraw(d.key, { files: v.trim() }));
  field(body, "check", "check", d.check, "a command that passes when it is done", "the command that passes only when the task is done", (v) => redraw(d.key, { check: v.trim() }));
  tick(body, "signoff", "wait for my approval", d.approve, "it lands only once you approve it", (on) => redraw(d.key, { approve: on }));
  const after = d.after ? state?.tasks.find((t) => t.id === d.after)?.title : "";
  row("after", after ?? "", body);
  const line = offered.has(d.key) && !d.said ? "Graphene is asked to take it…" : draftLine(d);
  if (line) div("when", line, body);
  if (d.said) div("refused", d.said, body).setAttribute("role", "alert");
  const acts = div("d-acts", undefined, pane);
  const act = (label: string, ico: string, title: string, on: () => void, main = false) => {
    const b = document.createElement("button");
    b.className = main ? "" : "quiet";
    b.append(icon(ico), document.createTextNode(label));
    b.title = title;
    b.addEventListener("mousedown", (e) => e.preventDefault()); // the box being typed in is not left first: Discard discards
    b.addEventListener("click", on);
    acts.appendChild(b);
  };
  act("Fill it in for me", "rocket", "the planner suggests its files and its check from the title", () => {
    const title = (document.getElementById("f-title") as HTMLInputElement | null)?.value.trim() || d.title;
    if (!title || offered.has(d.key)) return;
    Object.assign(d, { title, said: undefined });
    offered.add(d.key);
    api.postMessage({ type: "act", act: d.after ? "add-after" : "add-under", id: d.after ?? "", sentence: title, key: d.key });
    paneLast = "";
    render();
  });
  act("Discard", "trash", "take this draft away", () => discard(d.key));
}

/** The pane is rebuilt only when what it shows changed (its key); then the focused button, by its words,
 *  and the scroll are kept, so a keyboard user reaches its buttons while a run writes the store. A box being
 *  typed in is never rebuilt under the typing: the pane waits for it to be left. */
function pane() {
  const pane = $("details");
  const d = drawn().find((x) => x.key === selected);
  const key = d ? JSON.stringify([d, offered.has(d.key)]) : state ? paneKey(state, selected, replaying()) + (refused.get(selected ?? "") ?? "") + state.envelope.forks : "";
  if (key === paneLast) return;
  const at = document.activeElement as HTMLInputElement | null;
  if (paneOf === selected && at && pane.contains(at) && at.tagName === "INPUT" && at.type === "text") {
    paneLast = "stale"; // rebuilt once the box is left; a draft's own line is said now, as its box says its blanks
    const when = d ? pane.querySelector(".when") : null;
    if (d && when) when.textContent = offered.has(d.key) && !d.said ? "Graphene is asked to take it…" : draftLine(d);
    return;
  }
  paneLast = key;
  paneOf = selected;
  const t = state?.tasks.find((x) => x.id === selected);
  if (!state || (!t && !d) || !key) { pane.hidden = true; pane.replaceChildren(); return; }
  const was = pane.contains(document.activeElement) ? document.activeElement : null;
  const mark = (e: Element) => `${e.id}|${e.className}|${e.textContent}|${e.getAttribute("aria-label") ?? ""}`;
  const want = was ? mark(was) : "";
  const top = pane.querySelector(".d-body")?.scrollTop ?? 0; // wide, the body scrolls; narrow, the whole pane
  const paneTop = pane.scrollTop;
  pane.replaceChildren();
  const s = state;
  pane.hidden = false;
  queueMicrotask(() => {
    if (want) Array.from(pane.querySelectorAll<HTMLElement>("button, input")).find((b) => mark(b) === want)?.focus({ preventScroll: true });
    const now = pane.querySelector(".d-body");
    if (now) now.scrollTop = top;
    pane.scrollTop = paneTop;
  });
  if (d) return draftPane(pane, d);
  if (!t) return;
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
  if (editable(t, replaying())) form(body, t, s);
  else { // a finished task, or a replay: read, and the line says why
    row("what for", t.full, body);
    row("may change", t.scope.join("  "), body);
    row("done when", t.check ? `${t.check} passes` : "", body);
    if (!replaying()) div("when", whenEdit(t), body);
  }
  row("under", t.parent ? goalTitle(s, t.parent) : "", body);
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
    const has = (id: string | null) => state!.tasks.some((t) => t.id === id);
    if (arriving && has(arriving)) { selected = arriving; arriving = null; }
    if (selected && !has(selected) && !isDraft(selected)) selected = null;
    if (linking && !has(linking)) linking = null;
    for (const d of drafts) { // what a draft was drawn after, or under, may have gone
      if (d.after && !has(d.after)) d.after = null;
      if (d.parent && !state.goals.some((g) => g.id === d.parent)) d.parent = null;
    }
    render();
  } else if (m.type === "said") { // graphene's answer to a change made here
    if (m.id) { if (m.ok) refused.delete(m.id); else refused.set(m.id, m.line); }
    const d = m.key ? drafts.find((x) => x.key === m.key) : undefined;
    if (d) {
      offered.delete(d.key);
      if (m.ok) { // the plan has it: the draft goes, and the task it became is selected in its place
        const made = selected === d.key ? m.made : undefined;
        discard(d.key);
        if (made && state?.tasks.some((t) => t.id === made)) select(made); else arriving = made ?? null;
        return;
      }
      d.said = m.line;
    }
    paneLast = "";
    render();
    // a box of this task's form still being typed in keeps the form as it is: the refusal is said under it now
    const body = m.id && m.id === selected && !m.ok ? $("details").querySelector<HTMLElement>(".d-body") : null;
    if (body && !Array.from(body.querySelectorAll(".refused")).some((r) => r.textContent === m.line)) div("refused", m.line, body).setAttribute("role", "alert");
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
  if ((e.target as HTMLElement).tagName === "INPUT" && e.key !== "Escape") return; // a tick box: Space is its own
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
        if (isDraft(target)) redraw(target, { after: from });
        else api.postMessage({ type: "act", act: "link", id: from, target });
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
  top("b-add", "Add task", "add", "draw a task: its title, then its files and its check (or the planner fills them in)", () => draw({ after: null, parent: null }));
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
