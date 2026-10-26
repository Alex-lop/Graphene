// The graph, in the webview: boxes for the tasks coloured by their state, bands for the sub-goals, the goal
// at the right, a forked task fanning out into its forks; a click selects and opens the details pane whose
// buttons ask the extension to run graphene. No network, no library: SVG drawn from the state.
import { layout, step, type Box, type Edge, type Layout } from "../layout.ts";
import { autoLine, usd, type Fork, type State, type Task } from "../state.ts";

declare function acquireVsCodeApi(): { postMessage(m: unknown): void };

type Status = { kind: "reading" | "missing" | "uninitialised" | "error" | "nofolder"; text: string };
type Incoming = { type: "state"; state: State } | { type: "status"; status: Status } | { type: "select"; id: string };
export type Act = "add-after" | "add-under" | "link" | "unlink" | "edit" | "drop" | "accept" | "tell" | "run" | "stop" | "auto" | "cockpit";

const GOAL = " goal";
const BOX_W = 184, BOX_H = 48, FORK_H = 20, FORK_DX = 22, GOAL_W = 200, GOAL_H = 66;
const api = acquireVsCodeApi();
const $ = <T extends HTMLElement>(id: string) => document.getElementById(id) as T;
const svgNS = "http://www.w3.org/2000/svg";

let state: State | null = null;
let lay: Layout | null = null;
let selected: string | null = null;
let linking: string | null = null;
let wiring: { from: string; x: number; y: number } | null = null; // a drag from a task's dot: the link being drawn
let zoom = { k: 1, tx: 0, ty: 0 };
let fitted = false;
let moved = false; // the person zoomed or panned: a resize no longer re-fits until a double-click

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

const cls = (word: string) => `st-${word.replace(/\s+/g, "-")}`;
const cut = (s: string, n: number) => (s.length > n ? s.slice(0, n - 1).trimEnd() + "…" : s);

function forkWord(f: Fork): string {
  return f.state === "running" ? "running" : f.state === "passed" ? "passed" : f.state ? f.state : "";
}

/** The small line under a box's title: who is on it and its state, the spend, as the cockpit's row says
 *  them; the model goes on the box's corner (`model`). */
function sub(t: Task): string {
  const parts: string[] = [];
  if (t.state === "running") parts.push(`agent ${t.agent || "?"}`, t.forks.length ? `${t.forks.length} forks` : "running");
  else parts.push(t.state);
  if (t.state === "came back" && t.outside.length) parts.push(`${t.outside.length} outside`);
  if (t.state === "review") parts.push("sign off");
  const spent = usd(t.usd);
  if (spent) parts.push(spent);
  while (parts.length > 1 && parts.join(" · ").length > 25) parts.pop(); // what fits the box, the state first
  return parts.join(" · ");
}

function boxes(s: State): { boxes: Box[]; edges: Edge[]; goal: string | null } {
  const bs: Box[] = s.tasks.map((t) => ({
    id: t.id, band: t.parent ?? "", w: BOX_W + (t.forks.length ? FORK_DX : 0),
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

function count(ts: Task[]): string {
  const done = ts.filter((t) => t.state === "done").length;
  return `${done} of ${ts.length}${done === ts.length && ts.length ? " ✓" : ""}`;
}

function render() {
  const svg = $("svg") as unknown as SVGSVGElement;
  const view = $("view") as unknown as SVGGElement;
  view.replaceChildren();
  if (!state) return;
  const s = state;
  const g = boxes(s);
  lay = layout(g.boxes, g.edges, { goal: g.goal, boxW: BOX_W, boxH: BOX_H, labelH: 18 });
  $("goal").textContent = s.goal || "no goal yet";
  const sb = s.scoreboard;
  const counts = [`${sb.running} running`, `${sb.need_you} need${sb.need_you === 1 ? "s" : ""} you`,
                  `${sb.proven} of ${sb.total} done`];
  if (s.width) counts.push(`width ${s.width}`);
  if (s.spent) counts.push(usd(s.spent));
  if (s.run.going) counts.unshift("run going");
  const run = $("b-run"); // while a run goes, the button that started it stops it
  run.textContent = s.run.going ? "Stop" : "Run ready";
  run.title = s.run.going ? "graphene run --stop: what runs goes back to the plan" : "graphene run --parallel 4";
  $("counts").textContent = counts.join(" · ");
  const auto = autoLine(s);
  $("auto").textContent = auto;
  $("auto").hidden = !auto;
  $("notice").hidden = true;
  if (!s.tasks.length) {
    $("notice").hidden = false;
    $("notice").textContent = "Nothing is planned yet: the graph shows your goal and the tasks under it.";
  }
  // bands
  for (const band of lay.bands) {
    if (!band.id) continue;
    const ts = s.tasks.filter((t) => t.parent === band.id);
    view.appendChild(el("rect", { class: "band", x: 4, y: band.y0, width: lay.width - 8, height: band.y1 - band.y0, rx: 6 }));
    view.appendChild(el("text", { class: "band-label", x: 14, y: band.y0 + 16 }, `${goalTitle(s, band.id)} · ${count(ts)}`));
  }
  // edges
  for (const [a, b] of g.edges) {
    const p = lay.boxes[a], q = lay.boxes[b];
    if (!p || !q) continue;
    const x1 = p.x + p.w - (a !== GOAL && s.tasks.find((t) => t.id === a)?.forks.length ? FORK_DX : 0);
    const y1 = p.y + BOX_H / 2, x2 = q.x, y2 = q.y + (b === GOAL ? q.h / 2 : BOX_H / 2);
    const dx = Math.max(24, (x2 - x1) / 2);
    const hot = selected && (a === selected || b === selected);
    const path = el("path", { class: `edge${hot ? " hot" : ""}`, d: `M${x1},${y1} C${x1 + dx},${y1} ${x2 - dx},${y2} ${x2},${y2}` });
    view.appendChild(path);
  }
  // boxes
  for (const t of s.tasks) {
    const p = lay.boxes[t.id];
    if (!p) continue;
    const grp = el("g", { class: `task ${cls(t.state)}${t.id === selected ? " selected" : ""}`, "data-id": t.id, tabindex: -1 });
    grp.appendChild(el("rect", { class: "box", x: p.x, y: p.y, width: BOX_W, height: BOX_H, rx: 6 }));
    grp.appendChild(el("rect", { class: "stripe", x: p.x, y: p.y, width: 5, height: BOX_H, rx: 2 }));
    const corner = t.state === "running" && t.model ? t.model : t.needs_you ? "◆" : "";
    const room = corner ? 21 - Math.min(6, corner.length) : 23; // the title stops short of the corner's word
    grp.appendChild(el("text", { class: "title", x: p.x + 12, y: p.y + 19 }, cut(t.title, room)));
    grp.appendChild(el("text", { class: "sub", x: p.x + 12, y: p.y + 36 }, cut(sub(t), 25)));
    if (corner) {
      grp.appendChild(el("text", { class: corner === "◆" ? "mark" : "model", x: p.x + BOX_W - 10, y: p.y + 17, "text-anchor": "end" }, corner));
    }
    // the fan: one chip a fork, hanging under the box, each on a line from the box's foot
    t.forks.forEach((f, i) => {
      const y = p.y + BOX_H + 6 + i * FORK_H;
      const x = p.x + FORK_DX;
      const kept = t.kept?.letter === f.letter;
      grp.appendChild(el("path", { class: "fan", d: `M${p.x + 10},${p.y + BOX_H} C${p.x + 10},${y + 10} ${x - 8},${y + 10} ${x},${y + 10}` }));
      const chip = el("g", { class: `fork ${cls(forkWord(f) || "waiting")}${kept ? " kept" : ""}` });
      chip.appendChild(el("rect", { class: "chip", x, y: y + 1, width: BOX_W, height: FORK_H - 3, rx: 4 }));
      const words = [f.letter, f.model || "", kept ? "✓ kept" : forkWord(f), f.lines !== null ? `${f.lines} lines` : ""].filter(Boolean);
      while (words.length > 1 && words.join(" · ").length > 24) words.pop(); // what fits the chip
      chip.appendChild(el("text", { class: "chip-text", x: x + 8, y: y + 14 }, words.join(" · ")));
      grp.appendChild(chip);
    });
    // its dot, where its lines leave: drag it onto another task and that task waits on this one
    grp.appendChild(el("circle", { class: "port", cx: p.x + BOX_W, cy: p.y + BOX_H / 2, r: 5, "data-port": t.id }));
    grp.addEventListener("click", (e) => { e.stopPropagation(); clicked(t.id); });
    view.appendChild(grp);
  }
  if (g.goal) {
    const p = lay.boxes[GOAL]!;
    const grp = el("g", { class: "goal" });
    grp.appendChild(el("rect", { class: "goal-box", x: p.x, y: p.y, width: p.w, height: p.h, rx: 8 }));
    grp.appendChild(el("rect", { class: "goal-box inner", x: p.x + 4, y: p.y + 4, width: p.w - 8, height: p.h - 8, rx: 5 }));
    grp.appendChild(el("text", { class: "goal-title", x: p.x + 14, y: p.y + 28 }, cut(s.goal, 24)));
    grp.appendChild(el("text", { class: "sub", x: p.x + 14, y: p.y + 48 }, `goal · ${count(s.tasks)} done`));
    view.appendChild(grp);
  }
  if (wiring) view.appendChild(el("path", { id: "wire", class: "wire", d: wireD() }));
  svg.setAttribute("viewBox", `0 0 ${Math.max(lay.width, 10)} ${Math.max(lay.height, 10)}`);
  svg.setAttribute("width", String(lay.width));
  svg.setAttribute("height", String(lay.height));
  if (!fitted) fit();
  applyZoom();
  details();
  hint();
}

/** The link being drawn: from the dragged task's dot to the pointer, curved as an edge is. */
function wireD(): string {
  const p = wiring && lay?.boxes[wiring.from];
  if (!wiring || !p) return "";
  const x1 = p.x + BOX_W, y1 = p.y + BOX_H / 2, dx = Math.max(24, Math.abs(wiring.x - x1) / 2);
  return `M${x1},${y1} C${x1 + dx},${y1} ${wiring.x - dx},${wiring.y} ${wiring.x},${wiring.y}`;
}

/** Where the pointer is in the graph's own units: the SVG is drawn 1:1, then translated and scaled. */
function at(e: MouseEvent): { x: number; y: number } {
  const r = $("svg").getBoundingClientRect();
  return { x: (e.clientX - r.left) / zoom.k, y: (e.clientY - r.top) / zoom.k };
}

function fit() {
  if (!lay) return;
  const canvas = $("canvas");
  const w = canvas.clientWidth || 800, h = canvas.clientHeight || 600; // both: the goal is last on the right
  const k = Math.min(1, (w - 24) / Math.max(lay.width, 1), (h - 24) / Math.max(lay.height, 1));
  zoom = { k: Math.max(0.35, k), tx: 0, ty: 0 };
  fitted = true;
}

function applyZoom() {
  const svg = $("svg");
  svg.style.transform = `translate(${zoom.tx}px, ${zoom.ty}px) scale(${zoom.k})`;
  svg.style.transformOrigin = "0 0";
}

function clicked(id: string) {
  if (linking && linking !== id) {
    api.postMessage({ type: "act", act: "link", id: linking, target: id });
    linking = null;
    select(id);
    return;
  }
  select(id);
}

function select(id: string | null) {
  selected = id;
  render();
}

function hint() {
  const h = $("hint");
  const from = wiring?.from ?? linking;
  if (from && state) {
    const a = state.tasks.find((t) => t.id === from);
    h.textContent = `link: ${wiring ? "drop it on" : "click"} the task that waits on “${a?.title ?? from}” · Esc cancels`;
    h.className = "linking";
  } else if (state?.questions.length) { // an open question outranks the news: answering it is the person's
    const q = state.questions[0]!;
    const about = q.about ? state.tasks.find((t) => t.id === q.about)?.title : "";
    h.textContent = `question${about ? ` on “${about}”` : ""}: ${q.text}${q.default ? ` (unanswered: ${q.default})` : ""} · answer it in the cockpit`;
    h.className = "asks";
  } else {
    h.textContent = state?.news.length ? state.news[state.news.length - 1]!
      : "click a task · drag its dot onto another to link them · wheel zooms · drag pans";
    h.className = "";
  }
}

function button(label: string, act: Act, id: string, parent: HTMLElement, title?: string) {
  const b = document.createElement("button");
  b.textContent = label;
  if (title) b.title = title;
  b.addEventListener("click", () => {
    if (act === "link") { linking = id; render(); return; }
    api.postMessage({ type: "act", act, id });
  });
  parent.appendChild(b);
}

function row(label: string, value: string, parent: HTMLElement) {
  if (!value) return;
  const r = div("row", undefined, parent);
  div("k", label, r);
  div("v", value, r);
}

function details() {
  const pane = $("details");
  pane.replaceChildren();
  const t = state?.tasks.find((x) => x.id === selected);
  if (!state || !t) { pane.hidden = true; return; }
  pane.hidden = false;
  const head = div("d-head", undefined, pane);
  div(`d-title ${cls(t.state)}`, t.title, head);
  div("d-id", `${t.id} · ${t.state}${t.needs_you ? " · needs you" : ""}`, head);
  const close = document.createElement("button");
  close.className = "close";
  close.textContent = "×";
  close.title = "close (Esc)";
  close.addEventListener("click", () => select(null));
  head.appendChild(close);
  const body = div("d-body", undefined, pane);
  row("goal", t.full, body);
  row("under", t.parent ? goalTitle(state, t.parent) : "", body);
  row("scope", t.scope.join("  "), body);
  row("check", t.check ?? "", body);
  if (t.hollow) div("hollow", "its check passed before the work too: it proves nothing new", body); // as the cockpit says
  if (t.needs.length) { // what it waits on, each with the × that stops it waiting
    const r = div("row", undefined, body);
    div("k", "needs", r);
    const v = div("v", undefined, r);
    for (const n of t.needs) {
      const need = div("need", state.tasks.find((x) => x.id === n)?.title ?? n, v);
      const x = document.createElement("button");
      x.className = "unlink";
      x.textContent = "×";
      x.title = "stop waiting on it";
      x.addEventListener("click", () => api.postMessage({ type: "act", act: "unlink", id: t.id, target: n }));
      need.appendChild(x);
    }
  }
  row("agent", t.agent ? `agent ${t.agent}${t.model ? ` · ${t.model}` : ""}` : "", body);
  row("cost", usd(t.usd), body);
  row("idle", t.idle !== null && t.idle > 8 ? `${Math.round(t.idle)} s quiet` : "", body);
  row("note", t.note, body);
  row("outside", t.outside.join("  "), body);
  if (t.forks.length) {
    const r = div("row", undefined, body);
    div("k", "forks", r);
    const v = div("v", undefined, r);
    for (const f of t.forks) {
      const kept = t.kept?.letter === f.letter;
      div(`fork-row ${cls(forkWord(f) || "waiting")}${kept ? " kept" : ""}`,
          [f.letter, f.model, forkWord(f), f.lines !== null ? `${f.lines} lines` : "", usd(f.usd), kept ? `✓ kept · ${t.kept?.why ?? ""}` : f.why]
            .filter(Boolean).join(" · "), v);
    }
  }
  if (t.tail.length) {
    const r = div("row", undefined, body);
    div("k", "last moves", r);
    const v = div("v", undefined, r);
    for (const line of t.tail.slice(-6)) div("move", line, v);
  }
  const acts = div("d-acts", undefined, pane);
  if (t.state === "proposed") button("Accept", "accept", t.id, acts, "graphene plan accept");
  button("Add step after", "add-after", t.id, acts, "a new task that waits on this one");
  button("Add step under", "add-under", t.id, acts, "a new task under the same sub-goal");
  button("Link to…", "link", t.id, acts, "then click the task that waits on this one");
  if (t.state !== "done") button("Edit", "edit", t.id, acts, "title, scope or check");
  if (["proposed", "ready", "waiting"].includes(t.state)) button("Drop", "drop", t.id, acts, "graphene node drop");
  if (["running", "ready", "waiting", "came back"].includes(t.state)) button("Tell", "tell", t.id, acts, "a line for the agent on it");
}

function notice(st: Status) {
  const n = $("notice");
  n.hidden = false;
  n.textContent = st.text;
  n.className = st.kind;
  ($("view") as unknown as SVGGElement).replaceChildren();
  $("details").hidden = true;
  $("goal").textContent = "Graphene";
  $("counts").textContent = "";
  $("auto").hidden = true;
}

window.addEventListener("message", (e: MessageEvent<Incoming>) => {
  const m = e.data;
  if (!m || typeof m !== "object") return;
  if (m.type === "state") {
    state = m.state;
    if (selected && !state.tasks.some((t) => t.id === selected)) selected = null;
    if (linking && !state.tasks.some((t) => t.id === linking)) linking = null;
    render();
  } else if (m.type === "status") {
    notice(m.status);
  } else if (m.type === "select") {
    select(m.id);
  }
});

window.addEventListener("keydown", (e) => {
  if (e.key === "Escape") {
    if (wiring) { wiring = null; $("canvas").classList.remove("wiring"); }
    else if (linking) linking = null; else selected = null;
    render();
    return;
  }
  if (!lay) return;
  const keys: Record<string, "left" | "right" | "up" | "down"> = { ArrowLeft: "left", ArrowRight: "right", ArrowUp: "up", ArrowDown: "down" };
  const dir = keys[e.key];
  if (!dir) return;
  e.preventDefault();
  if (!selected) {
    const first = state?.tasks[0]?.id ?? null;
    select(first);
    return;
  }
  let next = step(lay, selected, dir);
  if (next === GOAL) next = null; // the goal is not a task
  if (next) select(next);
});

function wire() {
  const canvas = $("canvas");
  canvas.addEventListener("wheel", (e) => {
    e.preventDefault();
    const rect = canvas.getBoundingClientRect();
    const px = e.clientX - rect.left + canvas.scrollLeft, py = e.clientY - rect.top + canvas.scrollTop;
    const k = Math.min(3, Math.max(0.25, zoom.k * Math.exp(-e.deltaY * 0.0015)));
    zoom = { k, tx: px - (px - zoom.tx) * (k / zoom.k), ty: py - (py - zoom.ty) * (k / zoom.k) };
    moved = true;
    applyZoom();
  }, { passive: false });
  let drag: { x: number; y: number; tx: number; ty: number } | null = null;
  canvas.addEventListener("mousedown", (e) => {
    const port = (e.target as Element).closest("[data-port]");
    if (port) { // a drag from a task's dot draws a link
      e.preventDefault();
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
      $("wire")?.setAttribute("d", wireD());
      return;
    }
    if (!drag) return;
    zoom = { ...zoom, tx: drag.tx + e.clientX - drag.x, ty: drag.ty + e.clientY - drag.y };
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
    drag = null;
    canvas.classList.remove("dragging");
  });
  canvas.addEventListener("dblclick", (e) => {
    if ((e.target as Element).closest(".task, .goal")) return;
    fitted = false;
    moved = false;
    render();
  });
  // the details pane opening narrows the canvas, as does a narrower window: the whole graph stays in view, the
  // goal box included, until the person zooms or pans themselves
  new ResizeObserver(() => {
    if (lay && !moved) {
      fit();
      applyZoom();
    }
  }).observe(canvas);
  $("b-run").addEventListener("click", () => api.postMessage({ type: "act", act: state?.run.going ? "stop" : "run", id: "" }));
  $("b-auto").addEventListener("click", () => api.postMessage({ type: "act", act: "auto", id: "" }));
  $("b-cockpit").addEventListener("click", () => api.postMessage({ type: "act", act: "cockpit", id: "" }));
  $("b-add").addEventListener("click", () => api.postMessage({ type: "act", act: "add-under", id: "" }));
  api.postMessage({ type: "ready" });
}

wire();
