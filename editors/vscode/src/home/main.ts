// Home, in the webview: draws what the host sends (cards.ts's model) and asks the host to act. Plain DOM, no
// library, and every word goes in as text, never as markup: task titles and the planner's words are a model's.
// The ask box is made once and kept, so a snapshot that arrives while the person types moves nothing under them.
import type { Act, Btn, Card, Home, Section } from "./cards.ts";
import { WHO } from "./who.ts";

declare function acquireVsCodeApi(): { postMessage(m: unknown): void; getState(): unknown; setState(s: unknown): void };

type Status = { kind: string; text: string };
type Last = { n: number; lines: string[]; bad: boolean; asked?: string; key?: boolean };
type Model = { type: "home"; status: Status; home: Home | null; review: boolean; busy: string; planning: boolean; last: Last };
type Saved = { open?: Record<string, boolean>; draft?: string; review?: boolean; cleared?: number };

const PLACEHOLDER = "What do you want done? For example: a --json flag on the list command, with a test";
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
  btn.dataset.mark = `${b.act}|${b.id ?? ""}|${b.arg ?? ""}`; // the same button after a redraw, for the focus
  btn.addEventListener("click", () => send(b.act, { id: b.id ?? "", ...(b.arg !== undefined ? { arg: b.arg } : {}) }));
  return btn;
}

// ---- the page, made once ----

const banner = el("div", "banner");
const screen = el("section", "screen");
const work = el("section", "work");
const head = el("div", "head", undefined, work);
const goal = el("div", "goal", undefined, head);
const counts = el("div", "counts", undefined, head);
const ask = el("div", "ask", undefined, work);
const box = el("textarea", "", undefined, ask);
box.rows = 3;
box.placeholder = PLACEHOLDER;
box.setAttribute("aria-label", "What do you want done?");
box.value = saved.draft ?? "";
const row = el("div", "ask-row", undefined, ask);
const go = el("button", "", "Plan it", row);
go.title = "the planner reads your repository and suggests tasks; nothing runs until you start them (⌘ or Ctrl + Enter)";
const cancel = el("button", "quiet", "Cancel", row);
const busy = el("span", "busy", "", row);
const out = el("div", "said", undefined, ask);
const intro = el("p", "intro", undefined, work);
const sections = el("div", "sections", undefined, work);
const foot = el("div", "foot", undefined, work);
button({ label: "Show graph", act: "showGraph" }, foot);
button({ label: "Watch the demo", act: "demo" }, foot);
document.body.append(banner, screen, work);
work.hidden = screen.hidden = banner.hidden = cancel.hidden = true;

let model: Model | null = null;
const submit = () => {
  const text = box.value.trim();
  if (text && !model?.planning) send("ask", { arg: text });
};
go.addEventListener("click", submit);
box.addEventListener("keydown", (e) => { if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) { e.preventDefault(); submit(); } });
box.addEventListener("input", () => remember({ draft: box.value }));
cancel.addEventListener("click", () => send("cancel"));

// ---- drawing ----

function render(m: Model) {
  const ok = m.status.kind === "ok" || m.status.kind === "empty";
  work.hidden = !ok;
  screen.hidden = ok;
  if (!ok || !m.home) { banner.hidden = true; return drawScreen(m); }
  const h = m.home;
  banner.textContent = h.banner;
  banner.hidden = !h.banner;
  goal.textContent = h.goal || "Nothing asked yet";
  goal.title = h.goal; // three lines at most on the page
  goal.classList.toggle("dim", !h.goal);
  goal.hidden = !h.goal && !h.empty; // a plan whose ask is no longer known: no headline rather than a wrong one
  counts.textContent = h.counts;
  counts.hidden = !h.counts;
  box.disabled = m.planning;
  go.hidden = m.planning;
  cancel.hidden = !m.planning;
  busy.textContent = m.busy;
  busy.hidden = !m.busy;
  if (m.last.asked && m.last.n !== saved.cleared) { // planned: the box is free for the next thing
    if (box.value.trim() === m.last.asked) box.value = "";
    remember({ draft: box.value, cleared: m.last.n });
  }
  box.placeholder = h.sections.some((s) => s.key === "suggested") ? "Ask for something else…" : PLACEHOLDER;
  ask.classList.toggle("compact", h.sections.length > 0); // one line while there is work to read; it grows on focus
  drawSaid(out, m.last);
  intro.hidden = !h.empty;
  intro.textContent = "Say what you want done, in a sentence or a paragraph. The planner splits it into small tasks; you read "
    + "them, remove what you do not want, and start the agents. Each agent works in its own copy of your repository, and "
    + `a task lands only when its check passes${m.review ? " and you approve it" : ""}.`;
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
  const fold = el("button", "fold", `${open ? "▾" : "▸"} ${s.title}`, top);
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
  const top = el("div", "c-head", undefined, card);
  el("div", "c-title", c.title, top);
  el("span", "c-tag", c.tag, top);
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
