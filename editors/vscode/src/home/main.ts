// Home, in the webview: draws what the host sends (cards.ts's model) and asks the host to act. Plain DOM, no
// library, and every word goes in as text, never as markup: task titles and the planner's words are a model's.
// Nothing is typed here: a plan comes from the person's coding agent, in its chat (`graphene plan propose`).
import { STOP_AFTER, STOP_AFTER_HOVER } from "../graph/words.ts";
import type { Act, Btn, Card, Home, Section } from "./cards.ts";
import { EXACT, WHO } from "./who.ts";

declare function acquireVsCodeApi(): { postMessage(m: unknown): void; getState(): unknown; setState(s: unknown): void };

type Status = { kind: string; text: string };
type Last = { n: number; lines: string[]; bad: boolean; key?: boolean };
type Model = { type: "home"; status: Status; home: Home | null; review: boolean; exact: boolean; busy: string; last: Last };
type Saved = { open?: Record<string, boolean>; review?: boolean };
const api = acquireVsCodeApi();
let saved: Saved = (() => { try { return (api.getState() as Saved) ?? {}; } catch { return {}; } })();
const remember = (patch: Partial<Saved>) => {
  saved = { ...saved, ...patch };
  try { api.setState(saved); } catch { /* a preview has no state */ }
};
const send = (act: Act, more: { id?: string; arg?: string; flag?: boolean } = {}) => api.postMessage({ type: "act", act, id: "", ...more });

function el<K extends keyof HTMLElementTagNameMap>(tag: K, cls = "", text?: string, parent?: HTMLElement): HTMLElementTagNameMap[K] {
  const e = document.createElement(tag);
  if (cls) e.className = cls;
  if (text !== undefined) e.textContent = text;
  parent?.appendChild(e);
  return e;
}

function button(b: Btn, parent: HTMLElement): HTMLButtonElement {
  const btn = el("button", b.main ? "" : "quiet", b.label, parent);
  if (b.title) btn.title = b.title;
  btn.disabled = b.off === true;
  btn.dataset.mark = `${b.act}|${b.id ?? ""}|${b.arg ?? ""}`; // the same button after a redraw, for the focus
  btn.addEventListener("click", () => send(b.act, { id: b.id ?? "", ...(b.arg !== undefined ? { arg: b.arg } : {}) }));
  return btn;
}

// ---- the page, made once ----

/** The graph's mark, three tasks and their links, drawn in the button's own colour. */
function mark(parent: HTMLElement) {
  const NS = "http://www.w3.org/2000/svg";
  const svg = document.createElementNS(NS, "svg");
  svg.setAttribute("viewBox", "0 0 16 16");
  svg.setAttribute("aria-hidden", "true");
  for (const [tag, attrs] of [["path", { d: "M4.5 5.5 11 8M4.5 10.5 11 8" }], ["circle", { cx: "3.5", cy: "5", r: "2" }],
                               ["circle", { cx: "3.5", cy: "11", r: "2" }], ["circle", { cx: "12", cy: "8", r: "2.5" }]] as const) {
    const e = document.createElementNS(NS, tag);
    for (const [k, v] of Object.entries(attrs)) e.setAttribute(k, v);
    svg.appendChild(e);
  }
  parent.appendChild(svg);
}

const banner = el("div", "banner");
const screen = el("section", "screen");
const work = el("section", "work");
const head = el("div", "head", undefined, work); // the hero: the plan in one card, and the way into the graph
const goal = el("div", "goal", undefined, head);
const counts = el("div", "counts", undefined, head);
const intro = el("p", "intro", undefined, head);
const pipe = el("div", "pipe", undefined, head); // Plan, Run, Review: where the work is
pipe.setAttribute("role", "list");
const toGraph = el("button", "open", undefined, head);
mark(toGraph);
toGraph.append("Open the graph");
toGraph.title = "the whole plan in a tab of the editor: every task, what it waits on, and what proves it";
toGraph.addEventListener("click", () => send("showGraph"));
const hand = el("p", "hand", "On the graph, Add task draws a task by hand.", head);
const busy = el("div", "busy", "", head);
const out = el("div", "said", undefined, work);
const sections = el("div", "sections", undefined, work);
const prefs = el("div", "prefs", undefined, work); // engine settings, which plans from any agent follow too
el("div", "prefs-head", "Settings", prefs);
const stopAfter = el("button", "switch", undefined, prefs); // the one switch: off is auto
stopAfter.setAttribute("role", "switch");
el("i", "", undefined, stopAfter);
stopAfter.append(STOP_AFTER);
stopAfter.title = STOP_AFTER_HOVER;
stopAfter.addEventListener("click", () => send("stopAfter", { flag: stopAfter.getAttribute("aria-checked") !== "true" }));
const stopNote = el("p", "pref-note", "", prefs);
const exactLabel = el("label", "tick exact", undefined, prefs);
const exact = el("input", "", undefined, exactLabel);
exact.type = "checkbox";
exactLabel.append(" Exact");
exactLabel.title = EXACT;
exact.addEventListener("change", () => send("exact", { flag: exact.checked }));
el("p", "pref-note", "Start waits for every answer, and each finished task for your approval.", prefs);
const foot = el("div", "foot", undefined, work);
button({ label: "Watch the demo", act: "demo" }, foot);
document.body.append(banner, screen, work);
work.hidden = screen.hidden = banner.hidden = true;

let model: Model | null = null;

// ---- drawing ----

function render(m: Model) {
  const ok = m.status.kind === "ok" || m.status.kind === "empty";
  work.hidden = !ok;
  screen.hidden = ok;
  if (!ok || !m.home) { banner.hidden = true; return drawScreen(m); }
  const h = m.home;
  banner.textContent = h.banner;
  banner.hidden = !h.banner;
  head.classList.toggle("empty", h.empty);
  goal.textContent = h.goal || (h.empty ? "No plan yet" : "");
  goal.title = h.goal; // three lines at most on the page
  goal.hidden = !goal.textContent; // a plan whose ask is no longer known: no headline rather than a wrong one
  counts.textContent = h.counts;
  counts.hidden = !h.counts || h.empty;
  pipe.replaceChildren(...h.stages.map((st) => {
    const stage = el("span", `stage ${st.at}`);
    stage.setAttribute("role", "listitem");
    stage.setAttribute("aria-current", st.at === "now" ? "step" : "false");
    el("b", "", st.label, stage);
    el("small", "", st.note || "\u00a0", stage); // the bars line up whether or not a stage says more
    return stage;
  }));
  pipe.hidden = h.empty; // no plan yet: the intro says where one comes from
  intro.hidden = hand.hidden = !h.empty;
  intro.textContent = "Ask your coding agent for something, in its chat: Claude Code or Codex. Its plan shows here and on the graph, "
    + (h.stopAfter ? "and nothing runs until you start it. " : "and what fits your limits runs without waiting. ")
    + `Each task lands only when its check passes${m.review ? " and you approve it" : ""}.`;
  stopAfter.setAttribute("aria-checked", String(h.stopAfter));
  stopNote.textContent = h.stopAfter ? "A plan your agent proposes waits for your Start." : "Off: a plan that fits your limits runs at once.";
  busy.textContent = m.busy;
  busy.hidden = !m.busy;
  exact.checked = m.exact;
  drawSaid(out, m.last);
  const focused = document.activeElement instanceof HTMLButtonElement && sections.contains(document.activeElement)
    ? document.activeElement.dataset.mark : "";
  sections.replaceChildren(...h.sections.map(drawSection));
  if (focused) Array.from(sections.querySelectorAll("button")).find((b) => b.dataset.mark === focused)?.focus({ preventScroll: true });
}

function drawSaid(at: HTMLElement, last: Last) {
  at.replaceChildren();
  at.className = `said${last.bad ? " bad" : ""}`;
  for (const l of last.lines) el("div", "", l, at);
  if (last.key) button({ label: "Set API key", act: "setKey", main: true }, at);
  at.hidden = !last.lines.length && !last.key;
}

function drawSection(s: Section): HTMLElement {
  const open = saved.open?.[s.key] ?? !s.folded;
  const sec = el("section", `sec sec-${s.key}`);
  const top = el("div", "sec-head", undefined, sec);
  const fold = el("button", "fold", undefined, top);
  el("span", "chev", open ? "▾" : "▸", fold);
  fold.append(s.title);
  fold.setAttribute("aria-expanded", String(open));
  fold.dataset.mark = `fold|${s.key}`;
  fold.addEventListener("click", () => { remember({ open: { ...saved.open, [s.key]: !open } }); if (model) render(model); });
  const acts = el("span", "sec-acts", undefined, top);
  for (const b of s.buttons) button(b, acts);
  if (!open) return sec;
  if (s.note) el("p", "sec-note", s.note, sec);
  for (const c of s.cards) sec.appendChild(drawCard(c));
  return sec;
}

function drawCard(c: Card): HTMLElement {
  const card = el("article", `card tone-${c.tone}`);
  el("div", "c-tag", c.tag, card); // what it is, in its state's colour, above what it is called
  el("div", "c-title", c.title, card);
  if (c.lines.length) {
    const dl = el("dl", "c-lines", undefined, card);
    for (const l of c.lines) {
      const r = el("div", `c-line${l.warn ? " warn" : ""}${l.k ? "" : " wide"}`, undefined, dl);
      if (l.k) el("dt", "", l.k, r);
      el("dd", l.mono ? "mono" : "", l.v, r);
    }
  }
  if (c.buttons.length) {
    const acts = el("div", "c-acts", undefined, card);
    for (const b of c.buttons) button(b, acts);
  }
  return card;
}

/** Everything that is not a plan to show: reading, no folder, no graphene, a folder to set up, an error. */
function drawScreen(m: Model) {
  screen.replaceChildren();
  const k = m.status.kind;
  const acts = () => el("div", "acts", undefined, screen);
  if (k === "reading") { el("p", "dim", "Reading the plan…", screen); return; }
  if (k === "nofolder") {
    el("h2", "", "Open a folder to start", screen);
    el("p", "", "Graphene works in one repository at a time.", screen);
    button({ label: "Open Folder", act: "openFolder", main: true }, acts());
    return;
  }
  if (k === "missing") {
    el("h2", "", "Graphene is not installed", screen);
    el("p", "", "This extension drives the graphene command. Install it once with uv, or set graphene.path in Settings if it is "
      + "somewhere else.", screen);
    const a = acts();
    button({ label: "Install Graphene", act: "install", main: true }, a);
    button({ label: "Watch the demo", act: "demo" }, a);
    return;
  }
  if (k === "uninitialised") return drawSetUp(m);
  el("h2", "", "Graphene could not read the plan", screen);
  el("p", "bad", m.status.text, screen);
  button({ label: "Try again", act: "refresh", main: true }, acts());
}

function drawSetUp(m: Model) {
  el("h2", "", "Set up Graphene in this folder", screen);
  el("p", "", "Graphene turns what you ask for into small tasks, runs an agent on each in its own copy of this repository, "
    + "and checks each one before it reaches your code.", screen);
  const label = el("label", "tick", undefined, screen);
  const tick = el("input", "", undefined, label);
  tick.type = "checkbox";
  tick.checked = saved.review ?? true;
  tick.addEventListener("change", () => remember({ review: tick.checked }));
  label.append(" Ask me to approve each finished task before it lands (recommended)");
  el("p", "strong", "Who should plan and do the work?", screen);
  const picks = el("div", "picks", undefined, screen);
  for (const w of WHO) {
    const b = el("button", "pick quiet", undefined, picks);
    el("span", "pick-name", w.label, b);
    el("span", "pick-note", w.note, b);
    b.disabled = Boolean(m.busy);
    b.addEventListener("click", () => send("setup", { arg: w.word, flag: tick.checked }));
  }
  if (m.busy) el("p", "busy", m.busy, screen);
  if (m.last.lines.length || m.last.key) drawSaid(el("div", "said", undefined, screen), m.last);
  button({ label: "Watch the demo first", act: "demo" }, acts());
  function acts() { return el("div", "acts", undefined, screen); }
}

window.addEventListener("message", (e: MessageEvent<Model>) => {
  const m = e.data;
  if (!m || m.type !== "home") return;
  model = m;
  render(m);
});
api.postMessage({ type: "ready" });
