// The graph, in the webview: boxes for the tasks coloured by their state, bands for the sub-goals, the goal
// at the right (or at the foot, when the view is narrow), a forked task fanning out into its forks; or, in
// the sidebar, the same plan as lanes, one row a task, grouped by sub-goal. A click selects and opens the details
// pane whose buttons ask the extension to run graphene. No network, no library: SVG and DOM from the state.
// Boxes are keyed by task id and updated in place, so a snapshot that changed nothing moves nothing.
import { DOWN, flip, layout, modeFor, rounded, route, routeDown, spread, step, type Box, type Edge, type Layout, type Point } from "../layout.ts";
import { autoLine, SAY, screenWords, usd, type DraftStep, type State } from "../state.ts";
import { wearInk } from "../ink.ts";
import { ICONS } from "./icons.ts";
import { blanks, draftLine, globs, isDraft, lacks, type Draft } from "./draft.ts";
import { attemptsMark, attemptsWhy, cardAct, cardLine, checkCut, covers, coversIn, checkLines, checkMark, cornerMark, cutWhole, doneWhen, filesLine, fitWhole, forkMark, goalBox, goalCells, legend, markWord, nextWanting, stateMark, tailPath, tally, wanting, wantingLine, wrap,
         type CheckMark, type Mark } from "./marks.ts";
import { actsFor, ASK_AGENT, askLine, asksYou, attemptsOf, commandChip, cornerWord, CURSOR_AGENT, cut, done, draftedSteps, earlier, edgeKind, editable,
         filesChip, forkActs, forkRow, forkWords, HEADER_ACTS, headerFor, heldWords, KEYS, linkHint, mainAct, mayRun, newsLine, paneKey, pipeline,
         planningLine, PROVES_NOTHING, provesNothing, questionOn, scopeTree, startAnswers, stopsOf, sub, tabOrder, tokenWords, topLine, whatFor, whenEdit, who, writtenOf,
         type Button, type ForkX, type StateX, type TaskX } from "./words.ts";
import { CARD, dotGap, FAR, FULL_FROM, fitPlan, fitView, hold, levelFor, miniFrame, miniSize, nearest, offScreen, onto, panTo, percent, ROWS_FROM, settle, switchK, wheelK, ZOOM_MAX, ZOOM_MIN, zoomK,
         type Level, type Size, type Zoom } from "./zoom.ts";

declare function acquireVsCodeApi(): { postMessage(m: unknown): void; getState(): unknown; setState(s: unknown): void };

type Status = { kind: "reading" | "missing" | "uninitialised" | "error" | "nofolder"; text: string };
type Incoming = { type: "state"; state: StateX; exact?: boolean; seen?: string[] } | { type: "status"; status: Status }
  | { type: "select"; id: string; focus?: boolean } // focus false: chosen while the keyboard is elsewhere (Home, a diff)
  | { type: "drafts"; drafts: Draft[] }
  | { type: "said"; id?: string; key?: string; ok: boolean; line: string; made?: string } // graphene's answer to a change made here
  | { type: "shown"; on: boolean } // the tab came in front, or went behind another
  | { type: "start"; ok: boolean }; // Start is over: a run was started (ok), or none was
type View = "auto" | "graph" | "lanes";
type Tab = "scope" | "edit" | "activity";
type Saved = { view?: View; drafts?: Draft[]; drew?: number; tab?: Tab };

const GOAL = " goal";
const PLAN = " p"; // before a step the planner is writing: a space first, so its box is never a task's
// A card (dev/ui/canvas.html), all of it inside its border: its title on up to two lines and a chip for its files;
// its status, its one act at the right; its attempts, a chip each, which make it taller; at its foot its check.
const BOX_W = CARD.full.w, BOX_H = CARD.full.h, PAD = 12, FORK_H = 22, FOOT_H = 22;
const STATUS_Y = BOX_H - FOOT_H - 11; // the status line's baseline: its act stands beside it
// A row, the card at the compact level (zoom.ts): its state's mark, its title on up to two lines, and what is news.
const ROW_W = CARD.compact.w, ROW_H = CARD.compact.h, ROW_X = 36;
// The goal, alone in the last column, a little wider than a card: its title on up to three lines, a cell a task
// under it, its own check at its foot; from afar a row with its ring, its title on up to three lines and its count,
// wider and taller than a task's row and in larger words, so it is still the clearest thing on the canvas.
const GOAL_W = 220, GOAL_ROW_W = ROW_W + 72, GOAL_ROW_H = 84;
/** The goal's title is read whole on its card: as many lines as it takes, up to six (a goal an agent wrote is a
 *  sentence, and its card is alone in its column), the card as tall as they need. */
const GOAL_LINES = 6;
/** What the layout and the lines between the cards measure by, at each level of detail. */
type Dims = { w: number; h: number; gapX: number; gapY: number; padX: number; padY: number; bandGap: number; label: number; inset: number };
// `label`: the room over a sub-goal's first row for its header, which is drawn larger over rows. A band reaches half
// a `gapY` past its rows, so two bands stand `bandGap - gapY` apart, 8 px, and never share an edge. Whole cards' top
// and foot pay for that room, so the running plan still opens as cards in a laptop's tab (1140 by 820). `inset`: a
// band's room either side of its cards, well under half a `gapX`, so a line down the middle of a gap (`edgeD`) keeps
// 10 px or more off a band's side and is never drawn along it, and two trunks side by side in it (`spread`) 7 px
const DIMS: Record<Level, Dims> = {
  full: { w: BOX_W, h: BOX_H, gapX: 34, gapY: 16, padX: 24, padY: 16, bandGap: 24, label: 28, inset: 7 },
  compact: { w: ROW_W, h: ROW_H, gapX: 36, gapY: 8, padX: 24, padY: 24, bandGap: 16, label: 30, inset: 6 },
};
/** A sub-goal's loose tasks (no line in or out but to the goal) stand at most this many high, then side by side. */
const STACK = 3;
const FOOT = 46; // the canvas's foot, where the zoom's buttons and the legend sit: the plan can always be clear of it
const AWAY_W = 264, AWAY_GAP = 20; // the region for what leaves this machine, right of the plan: never narrower than its label, the longest of which is "asks you first"
const AWAY_PAD = 44; // a step past the line sits this far inside the region, so the gate on the line is clear of it
const AWAY_TOP = 48; // and under the region's label
/** The narrow view by default: lanes read better than a downward graph at 280 to 400 px (lane 1's notes). */
const NARROW_VIEW: "lanes" | "graph" = "lanes";
const api = acquireVsCodeApi();
const $ = <T extends HTMLElement>(id: string) => document.getElementById(id) as T;
const svgNS = "http://www.w3.org/2000/svg";

let state: StateX | null = null;
let exact = false; // Exact is on (the host reads `board`): Start waits for every answer, as Home's
let seen = new Set<string>(); // the tasks whose changes were opened in this window (the host's Session.seen)
let lastJson = "";
let lay: Layout | null = null;
let selected: string | null = null;
let linking: string | null = null;
let wiring: { from: string; x: number; y: number } | null = null; // a drag from a task's dot: the link being drawn
let saved: Saved = (() => { try { return (api.getState() as Saved) ?? {}; } catch { return {}; } })();
let zoom: Zoom = { k: 1, tx: 0, ty: 0 }; // every page opens fitted: last time's pan and zoom were another plan's
let moved = false; // the person zoomed or panned: the plan is no longer fitted again under them
let level: Level = "full"; // the level of detail on screen: whole cards, or rows when the plan is read from afar
let D = DIMS.full; // and its measures
let tapped: string | null = null; // the card the last click chose: a double click is on that one, wherever its second click lands
let drawing: string | null = null; // a task drawn here and still open: the canvas holds still under it, and is the plan's again once it is left
let fitted = false;
let saving: ReturnType<typeof setTimeout> | undefined;
// Drafts live in the host's workspace storage, shared by every graph page.
let drafts: Draft[] = [];
const sentDrafts = new Map<string, string>();
let naming: string | null = null; // the draft whose title is being typed on its box
const offered = new Set<string>(); // drafts graphene is being asked to take: not offered twice
const refused = new Map<string, string>(); // a task's id -> graphene's refusal of the last change to it
let arriving: string | null = null; // a drawn task graphene took: selected once the plan shows it
let pressing = false; // a press inside the pane: it is not rebuilt between the press and its click
let chipStep = 0; // how short every files chip in the plan is spelt, 0 to 2: the most any one of them needs (`pill`)
let held = false; // a card under a press was not drawn again (`graph`): it is once the press is let go
const LONG = 2000; // the longest title, check or line of files the host passes on

function remember(patch: Partial<Saved>) {
  if (patch.drafts) {
    for (const key of sentDrafts.keys()) if (!patch.drafts.some((d) => d.key === key)) {
      api.postMessage({ type: "draft", key, draft: null }); sentDrafts.delete(key);
    }
    for (const draft of patch.drafts) {
      const json = JSON.stringify(draft);
      if (sentDrafts.get(draft.key) !== json) api.postMessage({ type: "draft", key: draft.key, draft });
      sentDrafts.set(draft.key, json);
    }
  }
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

/** An SVG text cut to ``max`` px by its drawn length, at a whole part of a word (marks.ts `cutWhole`). Not drawn
 *  yet (the SVG hidden), it is cut by a character count instead, so nothing runs past its box in the meantime. */
function fitText(text: SVGTextElement, max: number) {
  const whole = text.textContent ?? "";
  if (text.getComputedTextLength() === 0 && whole) { text.textContent = cutWhole(whole, Math.max(2, Math.floor(max / 7))); return; }
  text.textContent = fitWhole(whole, max, (t) => { text.textContent = t; return text.getComputedTextLength(); });
}

/** A codicon, inline: its path in a 16 by 16 box. */
function icon(name: string): SVGSVGElement {
  const s = el("svg", { class: "ico", viewBox: "0 0 16 16", width: 16, height: 16, "aria-hidden": "true" });
  s.appendChild(el("path", { d: ICONS[name] ?? "" }));
  return s;
}

/** A button pressed, in the pane or on a card: what it asks of the page, or of graphene. */
function press(b: Button, id: string) {
  if (b.act === "link") { linking = id; render(); return; }
  const near = state?.tasks.find((t) => t.id === id);
  if (b.act === "add-after" && near) return draw({ after: id, parent: near.parent });
  if (b.act === "add-under") return draw({ after: null, parent: near?.parent ?? null });
  api.postMessage({ type: "act", act: b.act, id, ...(b.fork ? { fork: b.fork } : {}) });
}

function button(b: Button, id: string, parent: HTMLElement) {
  const btn = document.createElement("button");
  if (b.icon) btn.appendChild(icon(b.icon));
  btn.appendChild(document.createTextNode(b.label));
  btn.title = b.title;
  btn.className = b.main ? "" : "quiet";
  btn.addEventListener("click", () => press(b, id));
  parent.appendChild(btn);
}

const cls = (word: string) => `st-${word.replace(/\s+/g, "-")}`;

/** How many lines the goal's title takes on its card at a level: measured as it is drawn, in the goal's group. */
function goalLines(title: string, lv: Level): number {
  const probe = titleLines($("goalg") as unknown as SVGGElement, "goal-title", title, 0, 0, 20, lv === "compact" ? GOAL_ROW_W - ROW_X - 10 : GOAL_W - 2 * PAD, GOAL_LINES);
  probe.remove();
  return probe.childElementCount;
}

function boxes(s: StateX, lv: Level = "full"): { boxes: Box[]; edges: Edge[]; goal: string | null } {
  const w = DIMS[lv].w, h = DIMS[lv].h; // a card's own box, at the level asked for
  const away = new Set(s.tasks.filter((t) => t.leaves).map((t) => t.id)); // past the line: placed in their region, not by the layout
  const bs: Box[] = s.tasks.filter((t) => !away.has(t.id)).map((t) => {
    const n = lv === "full" && t.state !== "done" ? t.forks.length : 0; // its attempts are on a whole card until it lands; a row wears them as marks
    return { id: t.id, band: t.parent ?? "", w, h: h + (n ? FORK_H * n + 6 : 0) };
  });
  const edges: Edge[] = s.edges.filter(([, , kind]) => kind === "needs").map(([a, b]) => [a, b]);
  for (const d of drawn()) { // a drawn task is a box as any other, after the task it waits on
    bs.push({ id: d.key, band: d.parent ?? "", w, h });
    if (d.after) edges.push([d.after, d.key]);
  }
  const steps = draftedSteps(s); // what the planner has written so far: a box a step, after the steps it needs
  const writing = new Set(steps.map((d) => d.id));
  for (const d of steps) {
    bs.push({ id: PLAN + d.id, band: d.parent ?? "", w, h });
    for (const n of d.needs) if (writing.has(n)) edges.push([PLAN + n, PLAN + d.id]); else if (s.tasks.some((t) => t.id === n)) edges.push([n, PLAN + d.id]);
  }
  const hasGoal = Boolean(s.goal) && s.tasks.length > 0;
  if (hasGoal) {
    const n = goalLines(s.goal, lv);
    bs.push(lv === "compact" ? { id: GOAL, band: "", w: GOAL_ROW_W, h: Math.max(GOAL_ROW_H, 19 * n + 27) } : { id: GOAL, band: "", w: GOAL_W, h: Math.max(BOX_H, 20 * n + 56) + (rootOf(s)?.check ? FOOT_H : 0) });
    const needed = new Set(edges.filter(([, b]) => !away.has(b)).map(([a]) => a)); // what only a step past the line waits on still ends the work here
    for (const b of bs) if (b.id !== GOAL && !needed.has(b.id)) edges.push([b.id, GOAL]);
    // the run crosses the line from the goal, as the target draws it: what a step past the line waits on here ends at the goal
    const crossing = edges.filter(([a, b]) => away.has(b) && !away.has(a));
    for (const e of crossing) edges.splice(edges.indexOf(e), 1);
    for (const b of new Set(crossing.map(([, x]) => x))) edges.push([GOAL, b]);
  }
  return { boxes: bs, edges, goal: hasGoal ? GOAL : null };
}

// ---- drawing a task by hand ----

/** The drafts on screen: none in a replay, which is watched. */
const drawn = (): Draft[] => (replaying() ? [] : drafts);

/** A new draft box, after a task or on its own, its title typed on the box. */
function draw(at: { after: string | null; parent: string | null }) {
  if (!state || replaying()) return;
  const n = (saved.drew ?? 0) + 1;
  const d: Draft = { key: ` d${crypto.randomUUID()}`, title: "", files: "", check: "", approve: false, ...at };
  drafts = [...drafts, d];
  remember({ drafts, drew: n });
  naming = d.key;
  select(d.key);
  if (view() === "lanes") return;
  // drawn on a plan seen from afar, it is opened as a double click opens a row: its title is typed at a size that reads
  const was = moved;
  if (level === "compact") detail(d.key);
  moved = was; // the page's own move, not the person's: the canvas holds still under what is typed for as long as
  drawing = d.key; // the draft is open, and then the plan is fitted again if no hand panned or zoomed
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
  if (naming === key) { naming = null; nameBox = null; }
  if (selected === key) selected = null;
  render();
}

/** The title typed on a draft's box: kept, and the files are next; an empty one takes the draft away. */
function named(key: string, title: string, on = false) {
  if (naming !== key) return; // Enter, then the blur of the box it took away
  naming = null;
  nameBox = null;
  if (!title.trim()) return discard(key);
  redraw(key, { title: title.trim() });
  if (on) setTimeout(() => document.getElementById("f-files")?.focus(), 0); // Enter goes on to its files
}

let nameBox: { key: string; input: HTMLInputElement } | null = null;
let painting = false; // the graph or the lanes are being redrawn: a box moved by that was not left

/** The box a title is typed in, on a draft: Enter keeps it, Esc leaves it as it was. One box for as long as
 *  the title is being typed: a redraw around it (a task joined, the view turned) moves it with what it holds,
 *  and whoever puts it on the page gives it the focus back. */
function nameInput(d: Draft): HTMLInputElement {
  if (nameBox?.key === d.key) return nameBox.input;
  const input = document.createElement("input");
  nameBox = { key: d.key, input };
  input.maxLength = LONG;
  input.className = "name";
  input.value = d.title;
  input.placeholder = "what this task does";
  input.spellcheck = false;
  input.setAttribute("aria-label", "the new task's title");
  input.addEventListener("input", () => { const current = drafts.find((x) => x.key === d.key); if (current) current.title = input.value; remember({ drafts }); });
  input.addEventListener("click", (e) => e.stopPropagation());
  input.addEventListener("mousedown", (e) => e.stopPropagation());
  input.addEventListener("keydown", (e) => {
    e.stopPropagation(); // typed words are not the graph's keys
    if (e.key === "Enter") named(d.key, input.value, true);
    if (e.key === "Escape") named(d.key, d.title);
  });
  // left for good, not moved by a redraw (which puts the focus back): then what was typed is the title
  input.addEventListener("blur", () => { if (!painting && document.activeElement !== input) named(d.key, input.value); });
  return input;
}

/** The root that is the goal: its own check, and whether it is done. */
const rootOf = (s: State) => s.goals.find((x) => !x.parent && x.title === s.goal);

function goalTitle(s: State, id: string): string {
  return s.goals.find((g) => g.id === id)?.title ?? s.drafting?.steps.find((d) => d.id === id)?.title ?? id;
}

const replaying = () => Boolean(state?.replay);

/** The tab's width, the canvas and a pane beside it: what says whether it is narrow. Not the canvas alone, which
 *  a pane opening beside it narrows: choosing a card would turn the graph to lanes, or lay it downward. */
const tabMode = () => modeFor($("canvas").parentElement!.clientWidth);

/** The view on screen: lanes when the tab is narrow, unless the person chose. */
function view(): "graph" | "lanes" {
  const want = saved.view ?? "auto";
  if (want !== "auto") return want;
  return tabMode() === "down" ? NARROW_VIEW : "graph";
}

/** The tab under its header, the canvas and a pane beside or under it: wider than tall, or not. */
const tabSize = (): Size => ({ w: $("canvas").parentElement!.clientWidth, h: $("canvas").parentElement!.clientHeight });

/** The graph's direction: downward when narrow, or as the preview page forces it (data-dir on body). And downward
 *  in a tab whose pane opens under the canvas (Cursor's, beside its agent's chat) where the plan across would not
 *  stand as whole cards, and downward is not much more than a page: across it opens as rows cut at the canvas's
 *  sides, downward as whole cards, the rest a short scroll. A plan longer than that stays across, in its sub-goals.
 *  Decided by the tab's width alone, against a page as tall as a tab that wide is, so a panel opening under the
 *  tab (Start's terminal) never lays the plan out again. */
function direction(s: StateX): "across" | "down" {
  const forced = document.body.dataset.dir;
  if (forced === "down" || forced === "across") return forced;
  if (tabMode() === "down") return "down";
  if (!narrow() || !s.tasks.length) return "across";
  const page = { w: tabSize().w, h: 1.3 * tabSize().w }, full = place(s, false, "full", 1);
  if (fitPlan(page, sizeOf(full.lay), () => ({ w: Infinity, h: Infinity }), FOOT, "compact", margin(full)).level === "full") return "across";
  return place(s, true, "full", 1).lay.height <= 1.5 * page.h ? "down" : "across";
}

let shown = true; // the tab is in front (the host says so): behind another, its size is no size to draw at
let chosen: { id: string; focus: boolean } | null = null; // chosen from outside while behind another: selected once in front

function render() {
  if (!state || !shown) return;
  const s = state;
  if (drawing && drawing !== selected) { drawing = null; fitRoom = ""; } // the drawn task was left (closed, discarded, or taken into the plan): the plan is fitted again
  // the pane first: it opens or closes beside the canvas, which is as wide as a plan fitted now is fitted to
  const shut = $("details").hidden, was = paneOf;
  pane();
  if ($("details").hidden !== shut) { paneMoved = true; closedOn = shut ? null : was; }
  const blank = !s.tasks.length && !drawn().length && !s.drafting; // nothing drawn: the notice says what to do, alone
  header(s, blank);
  const v = view();
  const dir = direction(s);
  document.body.dataset.mode = v === "lanes" ? "lanes" : dir;
  $("lanes").hidden = v !== "lanes";
  ($("svg") as unknown as SVGSVGElement).style.display = v === "lanes" ? "none" : "block";
  $("canvas").classList.toggle("lanes", v === "lanes");
  $("notice").hidden = !blank; // a planner writing says so at the canvas's foot
  $("zoom").style.display = blank ? "none" : ""; // nothing to zoom
  chips(s);
  const planning = planningLine(s);
  $("planning").textContent = planning;
  $("planning").hidden = !planning;
  if (!s.tasks.length) {
    $("notice").className = "";
    $("notice").replaceChildren();
    div("notice-head", "Nothing is planned yet.", $("notice")); // what is so, then what to do about it
    if (!replaying()) $("notice").append(ASK_AGENT);
    if (!replaying() && document.body.dataset.editor === "cursor") div("notice-aside", CURSOR_AGENT, $("notice")); // the host says which editor (graph.ts)
    if (!replaying()) button({ label: "Add task", act: "add-under", title: "draw a task: its title, then its files and its check", icon: "add", main: true }, "", $("notice"));
  }
  painting = true;
  try {
    if (v === "lanes") lanes(s); else graph(s, dir);
  } finally {
    painting = false;
  }
  paneMoved = false;
  if (nameBox?.input.isConnected && document.activeElement !== nameBox.input) nameBox.input.focus({ preventScroll: true });
  hint();
}

let asking = false; // the card of the plan's open question is out, under its chip
let answered = false; // a question was answered from that card: the keyboard is put somewhere once the card is gone, once

/** In the header, right of the stages, what needs you: how many tasks, a click showing the next; and the plan's open
 *  questions, a click opening the first under its chip, to answer there. A question about the whole plan is on
 *  no card, so this is where the graph shows it. A replay is watched: neither. */
function chips(s: StateX) {
  const half = (b: HTMLElement, line: string) => {
    const at = line.indexOf(" · "), n = at < 0 ? line : line.slice(0, at); // `3 tasks need you`, `show the next`: the count, and what a click does
    b.hidden = !n;
    b.children[1]!.textContent = n;
    b.children[2]!.textContent = at < 0 ? "" : line.slice(at);
  };
  half($("b-next"), wantingLine(wantYou().length));
  // Start and Run take the defaults of what is asked: the chip says which, so a click on either is no answer unseen
  const act = mainAct(s, exact), picks = act && (act.act === "start" || act.act === "run") && !act.off ? act.label : "";
  const asks = replaying() ? [] : s.questions;
  half($("b-ask"), askLine(asks, picks));
  $("b-ask").title = picks && startAnswers(s) ? `answer here, or ${picks} will ${startAnswers(s)}` : "the plan's open question: its answers";
  if (!asks.length) asking = false;
  $("b-ask").setAttribute("aria-expanded", String(asking));
  $("need").hidden = $("b-next").hidden && $("b-ask").hidden;
  const card = $("asked"), n = s.questions.length, q = s.questions.find((x) => !x.default) ?? s.questions[0]; // the one that holds Start first
  card.hidden = !asking || !q;
  // answered from its card, the keyboard stays on the chip while a question is left, then goes to what needs you, or to
  // the plan: never onto Start or Run, which a held Enter would press. Put once: a card clicked after is left alone
  const lost = (e: Element | null) => !e || e === document.body || !e.isConnected || (e instanceof HTMLElement && !e.offsetParent);
  if (answered) {
    const at = document.activeElement, chip = $("b-ask");
    if (lost(at)) {
      const to = [chip, $("b-next")].find((b) => !b.hidden) ?? $("canvas").querySelector<HTMLElement>('[tabindex="0"]');
      to?.focus({ preventScroll: true });
      answered = to === chip;
    } else if (at !== chip) answered = false;
  }
  if (card.hidden || !q || card.dataset.key === JSON.stringify(q)) return;
  card.dataset.key = JSON.stringify(q);
  const on = q.about ? (s.tasks.find((t) => t.id === q.about)?.title ?? goalTitle(s, q.about)).replace(/^\?\s+/, "") : ""; // a sub-goal's `? ` says it asks: the card says so
  card.replaceChildren();
  div("q-on", `Question${n > 1 ? ` 1 of ${n}` : ""} on ${on ? `“${on}”` : "the plan"}`, card); // answered, the next follows
  div("q-text", q.text, card);
  const opts = div("q-opts", undefined, card);
  const answer = (label: string, target?: string) => {
    const b = opts.appendChild(document.createElement("button"));
    b.className = "quiet"; // none filled: the default is said under them, not chosen for you
    if (target === undefined) b.appendChild(icon("comment-discussion"));
    b.append(label);
    b.title = target === undefined ? "answer in your own words" : "answer with this";
    b.addEventListener("click", () => { asking = false; answered = true; api.postMessage({ type: "act", act: "answer", id: q.id, ...(target === undefined ? {} : { target }) }); render(); });
  };
  for (const o of new Set([...(q.default ? [q.default] : []), ...q.options])) answer(o, o);
  answer("In your own words…");
  if (q.default) div("q-if", `If unanswered: ${q.default}`, card);
}

/** A narrow tab (the editor area beside the side bar and an agent's chat): the pane goes under the canvas. */
const narrow = () => matchMedia("(max-width: 700px)").matches;

let startedAt = 0; // when Start or Run was pressed, until the run is seen going
const START_WAIT = 15000; // nor longer: a run refused at its start says why in its terminal, and the host says so (session.ts)

function header(s: StateX, blank: boolean) {
  const first = topLine(s); // a replay, or a live race against the stand-in: said before anything else
  $("replay").textContent = first.split(" · ")[0]!; // `practice run`, `replay`: a pill never cut, its hover says it whole
  $("replay").title = first;
  $("replay").setAttribute("role", "note"); // and a screen reader reads it whole: no model ran is the point of it
  $("replay").setAttribute("aria-label", first);
  $("replay").hidden = !first;
  const h = headerFor(s); // each number once: the stages and Run's cost here, what needs you in its chip
  $("goal").textContent = $("goal").title = h.goal; // cut to its row: the hover says it whole
  $("auto").textContent = $("auto").title = h.auto;
  $("auto").hidden = !h.auto;
  // one pipeline, the plan first: Plan, Run, Review; none before there is a plan to be at a stage of
  $("pipe").hidden = !s.tasks.length;
  $("stages").replaceChildren(...h.stages.map((st, i) => {
    const stage = div(`stage ${st.at}`);
    stage.setAttribute("role", "listitem");
    stage.setAttribute("aria-current", st.at === "now" ? "step" : "false");
    div("n", String(i + 1), stage);
    stage.append(st.label);
    if (st.note) { const note = document.createElement("small"); note.textContent = st.note; stage.appendChild(note); }
    return stage;
  }));
  // a narrow tab cuts the stage's note to its room: a note cut (`6…`) says nothing, so it goes, and the names stay
  for (const note of Array.from($("stages").querySelectorAll("small"))) if (note.scrollWidth > note.clientWidth) note.hidden = true;
  for (const [id] of HEADER_ACTS) $(id).hidden = replaying(); // a replay is watched: nothing acts on a plan, or outside it
  if (blank) $("b-add").hidden = true; // the notice's own Add task is the act then
  if (!s.tasks.length) $("b-save").hidden = $("b-view").hidden = true; // no plan: nothing to save, or to see as lanes
  else $("b-view").hidden = false;
  // the one act on the whole plan: Start a suggestion, Run what is ready, Stop a run (words.ts `mainAct`). Pressed,
  // Start or Run says Starting… until the run is seen going, or what it was to run has moved on: the state between
  // (accepted, not yet running) offered Run for a moment, and a click there a second run, refused in red
  if (startedAt && (s.run.going || !s.tasks.some((t) => t.state === "ready" || t.state === "proposed") || Date.now() - startedAt > START_WAIT)) startedAt = 0;
  const act = mainAct(s, exact), run = $<HTMLButtonElement>("b-run");
  if (!act) run.hidden = true;
  else if (startedAt) { // busy, not off: its words read whole, its ring turns as a working card's (still, with less motion)
    const ring = el("svg", { class: "ico", width: 14, height: 14, viewBox: "-7 -7 14 14", "aria-hidden": "true" });
    mark(ring, "working", 0, 0, 6);
    run.replaceChildren(ring, document.createTextNode("Starting…"));
    run.title = "the run is starting: its agents show on the cards";
    run.className = "quiet";
    run.disabled = false;
    run.setAttribute("aria-busy", "true");
  } else {
    run.replaceChildren(icon(act.icon), document.createTextNode(act.label));
    run.title = act.title;
    run.className = act.main ? "" : "quiet"; // filled only when it starts something
    run.disabled = Boolean(act.off);
    run.removeAttribute("aria-busy");
  }
  const toggle = $("b-view"), lanes = view() === "lanes"; // what a click turns to
  toggle.replaceChildren(icon(lanes ? "type-hierarchy-sub" : "list-flat"));
  toggle.title = lanes ? "Graph (v)" : "Lanes (v)";
  toggle.setAttribute("aria-label", lanes ? "Graph" : "Lanes");
}

// ---- the graph: SVG, keyed by task id ----

const taskEls = new Map<string, { g: SVGGElement; key: string }>();
const edgeEls = new Map<string, SVGPathElement>();
let goalKey = "";
let fitSize = ""; // the drawing's size when the zoom was last set for it
let fitRoom = ""; // and the window's size then, whatever the pane took of it; "": the plan is fitted again at the next drawing
let paneMoved = false; // the pane opened or closed in this render: a plan fitted now glides to its new fit
let closedOn: string | null = null; // and the card whose pane it was, when it closed: the view stays on it
let sticky: { g: SVGGElement; x: number; room: number }[] = []; // each sub-goal's header, its band's left and how far it may slide right in it

type Placed = { lay: Layout; g: ReturnType<typeof boxes>; here: number; awayW: number };

/** The plan placed at a level of detail: the layout's boxes, and what leaves this machine in its region. ``k``: the
 *  zoom it is drawn at, which a fit sets afresh (1). */
function place(s: StateX, down: boolean, lv: Level, k = zoom.k): Placed {
  const d = DIMS[lv], h = d.h;
  const g = boxes(s, lv);
  // laid downward, a row wraps at what the canvas shows; zoomed out it shows more, and the rows stay as they are
  const opts = { goal: g.goal, boxW: d.w, boxH: h, labelH: d.label, gapX: d.gapX, gapY: d.gapY, bandGap: d.bandGap, stack: STACK,
                 ...(down ? {} : { padX: d.padX, padY: d.padY }), down, width: down ? $("canvas").clientWidth / Math.max(1, k) : undefined };
  let lay = layout(g.boxes, g.edges, opts);
  // loose tasks in a tab wider than tall, with no sub-goal or one (which says the goal again): not a narrow tower in
  // the middle of an empty canvas. Two to four stand in one row where it holds them whole at their own size (Start's
  // terminal under it), but not beside a goal card with no sub-goal to gather their lines: each would climb over the
  // next card and read as a chain. With no sub-goal, a tower the tab would not hold whole stands as a block, and so do
  // five or more with no goal card, so a fifth task does not turn their row into a tower
  const tab = tabSize(), named = lay.bands.filter((b) => b.id).length, n = g.boxes.filter((b) => b.id !== g.goal).length;
  const whole = (l: Layout) => fitView(tab, sizeOf(l), FOOT).k >= 1;
  if (!down && tab.w > tab.h && named <= 1) {
    const row = n <= 4 && lay.bands.length === 1 && (named || !g.goal) ? layout(g.boxes, g.edges, { ...opts, stack: 1, stackAll: true }) : null;
    if (row && whole(row)) lay = row;
    else if (!named && ((n > 4 && !g.goal) || !whole(lay))) lay = layout(g.boxes, g.edges, { ...opts, stackAll: true });
  }
  // across, the goal stands one gap further out: its lines gather on a trunk with a gap of its own (`graph`)
  const gp = g.goal && !down ? lay.boxes[g.goal] : undefined;
  if (gp) { gp.x += d.gapX; lay.width += d.gapX; }
  // across, the plan sits in "this machine", and what leaves it has a region of its own at the right; while no
  // step leaves there is no such region, and the plan has the width
  const here = down || !g.boxes.length ? 0 : lay.width;
  const leaving = s.tasks.filter((t) => t.leaves);
  const awayW = leaving.length ? Math.max(d.w + 2 * AWAY_PAD, AWAY_W) : 0;
  if (here && awayW) lay.width += AWAY_GAP + awayW;
  // a step past the line stands in its region, one under another in the middle; laid downward, the region is under
  // the plan, as wide as it is
  const tall = leaving.length * h + Math.max(0, leaving.length - 1) * d.gapY;
  if (here) lay.height = Math.max(lay.height, tall + AWAY_TOP + 24);
  leaving.forEach((t, i) => {
    const x = here ? here + AWAY_GAP - 8 + (awayW - d.w) / 2 : (lay.width - d.w) / 2; // in the region's middle, clear of the gate on its line; downward, in the middle as each row is
    const y = (here ? Math.max(AWAY_TOP, (lay.height - tall) / 2) : lay.height + AWAY_TOP) + i * (h + d.gapY);
    lay.boxes[t.id] = { id: t.id, x, y, w: d.w, h, rank: lay.ranks, band: "" };
  });
  if (leaving.length) lay.ranks += 1;
  if (!here && leaving.length) lay.height += AWAY_TOP + tall + 24;
  return { lay, g, here, awayW };
}

const paneSize = (): Size => ({ w: $("canvas").clientWidth || 800, h: $("canvas").clientHeight || 600 });
/** The canvas's foot, while the zoom's buttons are there (the side bar's canvas has none). */
const foot = () => ($("zoom").offsetHeight ? FOOT : 0);
const sizeOf = (l: Layout): Size => ({ w: l.width, h: l.height });
/** A plan wider than its canvas, its sides cutting no card to a sliver, ``id``'s card whole, the goal whole where it
 *  can be (zoom.ts `settle`). */
const settled = (z: Zoom, l: Layout, id?: string | null): Zoom =>
  settle(z, paneSize(), sizeOf(l), Object.values(l.boxes), id ? l.boxes[id] : undefined, l.boxes[GOAL]);

/** The plan and its bands in a drawing laid out as ``full`` is, and its empty margin round them, which a fit just
 *  too tight may cut (zoom.ts `fitPlan`): a band's side at the left, the goal's (or the region's) at the right, a
 *  band's edge top and foot. */
const margin = (full: Placed) => (l: Level, size: Size) => {
  const d = DIMS[l], x = d.padX - d.inset, y = Math.min(d.padY - d.gapY / 2, full.awayW ? 8 : Infinity);
  return { x, y, w: size.w - x - (full.awayW ? 8 : full.g.goal ? d.padX : x), h: size.h - 2 * y };
};

/** How the plan opens: the whole plan in the pane. Whole cards when they fit at a scale they read at, else rows
 *  (zoom.ts), never so small their titles do not read: a plan larger than that (a Cursor tab beside its agent's
 *  chat) opens on the card that matters, the chosen one, else the first that wants you, else the first at work.
 *  Asked for (`fitAll`: `f`, the fit button, a double click on the canvas), it is the whole plan however small.
 *  Laid downward it is whole cards: all of them where they fit at a size they read at, else at their own size from
 *  the top, on the card that matters. */
function opening(s: StateX, down: boolean): { level: Level; at: Placed; zoom: Zoom; whole: boolean } {
  const full = place(s, down, "full", 1), pane = paneSize(), f = foot();
  const matters = (l: Layout) => [selected, ...wantYou(), ...s.tasks.filter((t) => t.state === "running").map((t) => t.id)].find((x) => x && l.boxes[x]);
  let rows: Placed | undefined;
  const keep = fitted && !$("details").hidden ? level : "compact"; // a pane open beside whole cards keeps them whole a little further
  const room = { w: pane.w, h: pane.h - f };
  if (down) {
    const size = sizeOf(full.lay), z = fitView(pane, size, f, 1, fitAll ? ZOOM_MIN : FULL_FROM), id = matters(full.lay);
    if (z.whole) return { level: "full", at: full, zoom: z, whole: true };
    const start = { k: 1, tx: (room.w - size.w) / 2, ty: 0 }, p = id ? full.lay.boxes[id] : undefined, at = p ? onto(start, room, size, p) : hold(start, room, size);
    // from its top, the rest a scroll down; scrolled to the card that matters, so that the canvas's top and foot
    // cut no card through its words, as a plan wider than its canvas is moved across (zoom.ts `settle`, turned)
    const turn = (b: { x: number; y: number; w: number; h: number }) => ({ x: b.y, y: b.x, w: b.h, h: b.w });
    const ty = at.ty < 0 ? settle({ k: 1, tx: at.ty, ty: at.tx }, { w: pane.h - f, h: room.w }, { w: size.h, h: size.w }, Object.values(full.lay.boxes).map(turn), p && turn(p)).tx : at.ty;
    return { level: "full", at: full, zoom: { ...at, ty }, whole: false };
  }
  const fit = fitPlan(pane, sizeOf(full.lay), () => sizeOf((rows ??= place(s, down, "compact")).lay), f, keep, margin(full), fitAll ? ZOOM_MIN : ROWS_FROM);
  const at = fit.level === "compact" && rows ? rows : full, z = { k: fit.k, tx: fit.tx, ty: fit.ty };
  const id = fit.whole ? undefined : matters(at.lay), p = id ? at.lay.boxes[id] : undefined;
  return { level: fit.level, at, zoom: fit.whole ? z : settled(p ? onto(z, room, sizeOf(at.lay), p) : z, at.lay, id), whole: fit.whole };
}

function graph(s: StateX, dir: "across" | "down") {
  const svg = $("svg") as unknown as SVGSVGElement;
  const down = dir === "down";
  const was = svg.dataset.level ?? level; // the level of the drawing on screen
  if (down) level = "full"; // the narrow drawing keeps whole cards
  // Until the person pans or zooms, the whole plan is in the pane: fitted when the page opens, when the window
  // is resized, when the plan grows or shrinks, when the pane closes and the plan then fits whole (a plan fitted
  // beside it, in a narrow tab, would stay at half its size), and when asked (`f`, a select from outside the page).
  // The pane opening is none of these, nor is the footer growing a line: a card chosen here stays where it is, as
  // big as it is. Laid downward too: its rows wrap at the canvas's width, which only the window changes.
  const room = `${innerWidth}x${innerHeight}`;
  const sized = (l: Layout) => `${l.width}x${l.height}`;
  const free = !moved && !drawing;
  let at: Placed | null = place(s, down, level);
  const kept = at !== null && sized(at.lay) === fitSize && room === fitRoom; // neither the window nor the plan changed
  const same = kept && !(paneMoved && $("details").hidden); // nor did the pane close
  let opened = free && !same ? opening(s, down) : null;
  const stay = opened && kept && !opened.whole; // closed on a plan larger than its tab: the card just read stays where it is
  if (stay) opened = null;
  if (opened) level = opened.level;
  D = DIMS[level];
  at = opened?.at ?? at!;
  const { g, here, awayW } = at;
  lay = at.lay;
  svg.dataset.level = level;
  // another level is another drawing: every card is cut to it at once, and nothing glides from the one to the other
  svg.classList.toggle("cut", level !== was);
  if (level !== was) svg.classList.remove("glide");
  regions(s, here, awayW);
  gates(s, here, awayW);
  // bands: few, redrawn; their headers over the edges, which cross them on the way to a later column
  const bands = $("bands") as unknown as SVGGElement, heads = $("heads") as unknown as SVGGElement;
  bands.replaceChildren();
  heads.replaceChildren();
  sticky = [];
  // across, a band ends half a gap past its last column, short of the goal's (`place` set it a gap further out):
  // the goal is no band's, and each band runs into it as one line along a trunk in the gap between
  const gAt = g.goal && !down ? lay.boxes[GOAL] : undefined, right = gAt ? gAt.x - 1.5 * D.gapX : here - 18;
  const trunk = gAt ? (right + gAt.x) / 2 : 0;
  /** A bracket into the goal: along from x1 to the trunk, round a corner, down or up it, and into the goal. */
  const bracket = (x1: number, y1: number) => {
    const y2 = gAt!.y + gAt!.h / 2, x2 = gAt!.x, t = trunk, r = Math.min(8, Math.abs(y2 - y1) / 2), dir = Math.sign(y2 - y1);
    return r < 1 ? `M${x1},${y1} H${x2}` : `M${x1},${y1} H${t - r} Q${t},${y1} ${t},${y1 + dir * r} V${y2 - dir * r} Q${t},${y2} ${t + r},${y2} H${x2}`;
  };
  // a band is as wide as its tasks: from its first column to its last, or on to where its header ends, as far as
  // the trunk (a band one column wide is not one column of its title)
  const spans = new Map<string, { x0: number; x1: number }>();
  const headed: { band: Layout["bands"][number]; name: string; ts: TaskX[]; x0: number; end: number; said: number; at: number }[] = [];
  for (const band of lay.bands) {
    const ps = band.id ? Object.values(lay.boxes).filter((p) => p.band === band.id) : [];
    if (!ps.length) continue;
    const x0 = Math.min(...ps.map((p) => p.x)) - D.inset, x1 = Math.max(...ps.map((p) => p.x + p.w)) + D.inset, most = Math.max(x1, right);
    const { name, whole } = bandName(goalTitle(s, band.id));
    const rect = bands.appendChild(el("rect", { class: "band", x: x0, y: band.y0, height: band.y1 - band.y0, rx: 10 }));
    rect.appendChild(el("title", {}, whole));
    // its header has the band's room on to the trunk, wherever the plan is panned or zoomed, and a redraw never
    // cuts it to the part that was on it; a band whose start is panned off the canvas keeps it at the canvas's
    // edge while the band is there (`applyZoom`), not cut to its last words
    const ts = s.tasks.filter((t) => t.parent === band.id), said = bandHead(heads, name, ts, x0 + D.inset, band.y0 + D.label / 2 + 1, most - x0 - 2 * D.inset);
    const end = Math.min(most, Math.max(x1, x0 + said + 2 * D.inset));
    rect.setAttribute("width", String(end - x0));
    spans.set(band.id, { x0, x1: end });
    headed.push({ band, name, ts, x0, end, said, at: sticky.length });
    sticky.push({ g: heads.lastElementChild as SVGGElement, x: x0, room: end - x0 - said - 2 * D.inset });
  }
  // edges: keyed by their ends; a changed path glides (CSS transitions d)
  const edges = $("edges") as unknown as SVGGElement;
  const seenEdges = new Set<string>();
  const taskOf = new Map(s.tasks.map((t) => [t.id, t]));
  const line = (key: string, d: string, kind: string) => {
    seenEdges.add(key);
    let path = edgeEls.get(key);
    if (!path) { path = el("path", { class: "edge" }); edgeEls.set(key, path); edges.appendChild(path); }
    path.setAttribute("d", d);
    path.setAttribute("class", `edge ${kind}`);
  };
  // what a line across keeps clear of: every box, each sub-goal's header row (a line along it reads as the header's
  // underline), and its band's foot, which a line going round a card is never drawn along
  const blocks = [...Object.values(lay.boxes), ...headed.flatMap(({ band: b, x0, end }) =>
    [{ x: x0, y: b.y0, w: end - x0, h: D.label }, { x: x0, y: b.y1 - 1, w: end - x0, h: 2 }])];
  const routed: { key: string; kind: string; pts: Point[] }[] = [];
  for (const [a, b] of g.edges) {
    const p = lay.boxes[a], q = lay.boxes[b];
    if (!p || !q || (b === GOAL && gAt && p.band)) continue; // a sub-goal's last steps end in its band, and the band runs into the goal
    // the edge carries the work: moving where an agent is working, green where it landed, a hairline until then; a
    // step in no sub-goal joins the goal on the bands' trunk
    const key = `${a}>${b}`, kind = `${edgeKind(taskOf.get(a), taskOf.get(b))}${selected && (a === selected || b === selected) ? " hot" : ""}${isDraft(a) || isDraft(b) ? " draft" : ""}`;
    // into the goal along its trunk, in the gaps round any card beside it (loose tasks side by side)
    if (b === GOAL && gAt) line(key, rounded([...route(p.x + D.w, p.y + D.h / 2, trunk + D.gapX / 2, gAt.y + gAt.h / 2, D.gapX, D.gapY, blocks), [gAt.x, gAt.y + gAt.h / 2]]), kind);
    else routed.push({ key, kind, pts: edgeD(p, q, down, blocks) });
  }
  // the trunks set apart in their gaps, clear of a band's side by 4 px at least (layout.ts `spread`); downward, in
  // the gaps between the rows
  const apart = down ? spread(routed.map((r) => flip(r.pts)), DOWN.rankGap - 16).map(flip) : spread(routed.map((r) => r.pts), D.gapX - 2 * D.inset - 8);
  apart.forEach((pts, i) => line(routed[i]!.key, rounded(pts), routed[i]!.kind));
  // a line down through a sub-goal's header: the header ends before it (the cards under it wear each task's mark),
  // and stays where it is, as sliding along would bring its words onto the line
  for (const h of headed) {
    const y = h.band.y0 + D.label / 2, from = h.x0 + D.inset, to = from + h.said;
    const cross = apart.flatMap((pts) => pts.slice(1).flatMap(([x, b], i) => (x === pts[i]![0] && (b - y) * (pts[i]![1] - y) < 0 && x > from && x < to ? [x] : [])));
    if (!cross.length) continue;
    sticky[h.at]!.g.remove();
    bandHead(heads, h.name, h.ts, from, y + 1, h.end - h.x0 - 2 * D.inset, cross);
    sticky[h.at] = { g: heads.lastElementChild as SVGGElement, x: h.x0, room: 0 };
  }
  if (gAt) for (const band of lay.bands) { // a sub-goal into the goal: a bracket out of its band, along a trunk half way, into the goal
    const mine = band.id ? s.tasks.filter((t) => t.parent === band.id) : [], span = spans.get(band.id);
    if (!mine.length || !span) continue;
    const y2 = gAt.y + gAt.h / 2, y1 = Math.min(Math.max(y2, band.y0 + 16), band.y1 - 16);
    // lit for the chosen card only when this line stands for its own line into the goal
    const its = g.edges.some(([a, b]) => b === GOAL && a === selected && lay!.boxes[a]?.band === band.id);
    line(`band ${band.id}>${GOAL}`, bracket(span.x1, y1), `band-link ${mine.every((x) => x.state === "done") ? "done" : "wait"}${its ? " hot" : ""}`);
  }
  svg.classList.toggle("has-sel", Boolean(selected)); // the chosen card's lines lit, the rest faded
  for (const [key, path] of edgeEls) if (!seenEdges.has(key)) { path.remove(); edgeEls.delete(key); }
  // boxes: one group a task, rebuilt only when its words or its place changed
  const tasks = $("tasks") as unknown as SVGGElement;
  const shown = new Set<string>();
  const box = (id: string, key: string, paint: (g: SVGGElement, h: number) => void, watched = false) => {
    const p = lay!.boxes[id];
    if (!p) return;
    shown.add(id);
    key = JSON.stringify([key, p.x, p.y, id === selected, down, level, chipStep]);
    let have = taskEls.get(id);
    if (have && have.key === key) return;
    if (have?.g.matches(":active")) { held = true; return; } // under a press, on it or on its button: drawn again at the release, which is then still its click
    if (!have) {
      const grp = el("g", { class: "task fresh", "data-id": id, ...(watched ? { role: "img" } : { tabindex: 0, role: "button" }) });
      grp.style.transform = `translate(${p.x}px, ${p.y}px)`; // placed before it joins: no glide from the corner
      if (!watched) { // a step the planner is still writing is watched: it is clicked once it is a suggestion
        // a double click's second click is not another choice: the pane the first one opened may have moved the plan under it
        grp.addEventListener("click", (e) => { e.stopPropagation(); if (e.detail > 1) return; tapped = id; clicked(id); });
        grp.addEventListener("keydown", (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); e.stopPropagation(); clicked(id); } });
      }
      tasks.appendChild(grp);
      have = { g: grp, key: "" };
      taskEls.set(id, have);
    }
    have.key = key;
    paint(have.g, p.h);
    have.g.style.transform = `translate(${p.x}px, ${p.y}px)`;
  };
  const paint = () => {
    for (const t of s.tasks) box(t.id, JSON.stringify([t, s.envelope.forks, seen.has(t.id)]), (grp, h) => drawTask(grp, t, h, down, s.envelope.forks));
    for (const d of drawn()) box(d.key, JSON.stringify([d, naming === d.key]), (grp) => drawDraft(grp, d));
    for (const d of draftedSteps(s)) box(PLAN + d.id, JSON.stringify(d), (grp) => drawPlanned(grp, d, down), true);
  };
  paint();
  for (const [id, have] of taskEls) if (!shown.has(id)) { have.g.remove(); taskEls.delete(id); }
  // one spelling for every files chip in the plan, the shortest any one needs: when that changed, every card again
  const need = Math.max(0, ...Array.from(tasks.querySelectorAll<SVGGElement>(".pill.files"), (p) => Number(p.dataset.need)));
  if (need !== chipStep) { chipStep = need; paint(); }
  // Tab walks the boxes wave by wave, which is their order in the DOM: reordered only when it changed
  const want = tabOrder(lay, [...s.tasks.map((t) => t.id), ...drawn().map((d) => d.key), ...draftedSteps(s).map((d) => PLAN + d.id)]);
  const have = Array.from(tasks.children).map((c) => c.getAttribute("data-id"));
  if (want.join("\n") !== have.join("\n")) for (const id of want) { const grp = taskEls.get(id)?.g; if (grp) tasks.appendChild(grp); }
  // the goal
  const goalG = $("goalg") as unknown as SVGGElement;
  const gp = g.goal ? lay.boxes[GOAL] : undefined;
  const root = rootOf(s);
  const cells = goalCells(s.tasks, s.goals), all = tally(s.tasks);
  const gk = gp ? JSON.stringify([s.goal, root, cells, gp.x, gp.y, gp.h, down, level]) : "";
  if (gk !== goalKey) {
    goalKey = gk;
    goalG.replaceChildren();
    if (gp && level === "compact") { // as a row: a ring filled by what is done, its title, and the count under it
      goalG.appendChild(el("rect", { class: "goal-box", x: 0, y: 0, width: gp.w, height: gp.h, rx: 10 }));
      ring(goalG, all.portion, 19, gp.h / 2, 9.5);
      const title = titleLines(goalG, "goal-title", s.goal, ROW_X, 0, 19, gp.w - ROW_X - 10, GOAL_LINES), n = title.childElementCount;
      const top = (gp.h - 19 * (n - 1) - 32) / 2 + 12; // the title and the count, as one block in the row's middle
      title.setAttribute("transform", `translate(0 ${top})`);
      goalG.appendChild(el("text", { class: "sub", x: ROW_X, y: top + 19 * (n - 1) + 17 }, `${all.landed} of ${all.total} done`));
      goalG.appendChild(el("circle", { class: "port in", cx: 0, cy: gp.h / 2, r: 5 }));
    } else if (gp) { // the goal is a card as a task is: its title on up to three lines, and under it a cell a task (a group a sub-goal) and the count, in the card's middle; its own check at its foot
      goalG.appendChild(el("rect", { class: "goal-box", x: 0, y: 0, width: gp.w, height: gp.h, rx: 12 }));
      const title = titleLines(goalG, "goal-title", s.goal, PAD, 0, 20, gp.w - 2 * PAD, GOAL_LINES), n = title.childElementCount;
      const top = (gp.h - (root?.check ? FOOT_H : 0) - (20 * n + 18)) / 2, y = top + 20 * n + 4; // the title's block and the cells' row, as one, over its check
      title.setAttribute("transform", `translate(0 ${top + 12})`);
      const count = goalG.appendChild(el("text", { class: "sub", x: gp.w - PAD, y: y + 10, "text-anchor": "end" }, `${all.landed} of ${all.total} done`));
      const room = gp.w - 2 * PAD - (count.getComputedTextLength() || 70) - 12;
      const step = Math.min(14, room / (all.total + (cells.length - 1) * 0.7)); // the cells and the gaps between their groups share the room, however many
      let x = PAD;
      for (const group of cells) {
        for (const m of group.marks) { goalG.appendChild(el("rect", { class: "cell", "data-mark": m, x, y, width: step * 0.8, height: 10, rx: Math.min(1.5, step / 4) })); x += step; }
        x += step * 0.7;
      }
      if (root?.check) cardFoot(goalG, { box: goalBox(root), tone: goalBox(root) === "passed" ? "ok" : "dim", words: "" }, (n) => checkCut(root.check!, n), gp.h, gp.w);
      goalG.appendChild(el("circle", { class: "port in", cx: down ? gp.w / 2 : 0, cy: down ? 0 : gp.h / 2, r: 5 }));
    }
    if (gp) {
      goalG.setAttribute("aria-label", `goal: ${s.goal}, ${all.landed} of ${all.total} done`);
      goalG.setAttribute("role", "group"); // reachable by Tab and the arrows, announced
      goalG.setAttribute("tabindex", "0");
      goalG.appendChild(el("title", {}, s.goal));
      const first = !goalG.style.transform; // placed, as a task is: no glide from the corner the first time
      if (first) goalG.style.transition = "none";
      goalG.style.transform = `translate(${gp.x}px, ${gp.y}px)`;
      if (first) { void goalG.getBoundingClientRect(); goalG.style.transition = ""; }
    }
  }
  $("wire").setAttribute("d", wiring ? wireD() : "");
  svg.setAttribute("viewBox", `0 0 ${Math.max(lay.width, 10)} ${Math.max(lay.height, 10)}`);
  svg.setAttribute("width", String(lay.width));
  svg.setAttribute("height", String(lay.height));
  // fitted again because it grew or shrank, or because the pane closed, it glides to its new fit. Not fitted, it
  // is held to the canvas when the window or the plan changed, or the pane closed (then on the card just read, no
  // card cut to a sliver), and not for a pane opening beside it: a clamp then would shift it under the click. A
  // pane under the canvas (the narrow tab) takes half its height: there the plan is held to what is left, at the
  // same zoom, or its rows would sit under it
  if (opened) {
    if (fitted && level === was && (sized(lay) !== fitSize || paneMoved)) { svg.classList.add("glide"); setTimeout(() => svg.classList.remove("glide"), 300); }
    zoom = opened.zoom;
  } else if (!same) zoom = stay ? settled(clamp(zoom), lay, closedOn) : clamp(zoom);
  else if (paneMoved && narrow()) zoom = { ...clamp(zoom), tx: zoom.tx }; // it took height, not width: where the plan stood across holds
  fitSize = sized(lay);
  fitRoom = room;
  fitted = true;
  minimap(s, spans);
  legendRow(s);
  applyZoom();
  if (level !== was) { void svg.getBoundingClientRect(); svg.classList.remove("cut"); } // the cut is made: what moves next glides again
}

type Spot = Layout["boxes"][string];
/** An edge, port to port: across, out of a card's right side and into the next's left, square and in the gaps
 *  between the cards (layout.ts `route`), never along a card's border or behind one: its corners, which `graph`
 *  sets apart from the other lines' before drawing them. Laid downward the same, turned a quarter: out of a card's
 *  foot, along the gap over its target's row, into its top (layout.ts `routeDown`). A card's ports are at its own
 *  size's middle, however tall its attempts make it; the goal's at its own. */
function edgeD(p: Spot, q: Spot, down: boolean, blocks: readonly { x: number; y: number; w: number; h: number }[]): Point[] {
  const w = (b: Spot) => (b.id === GOAL ? b.w : D.w), h = (b: Spot) => (b.id === GOAL ? b.h : D.h);
  if (!down) return route(p.x + w(p), p.y + h(p) / 2, q.x, q.y + h(q) / 2, D.gapX, D.gapY, blocks);
  return routeDown(lay!, p, p.x + w(p) / 2, q, q.x + w(q) / 2, blocks);
}

/** The region for what leaves this machine (a push, a pull request), right of the plan, once a step does (laid
 *  downward, under it): its label says how many do, or that one asks you first. While none does nothing is drawn:
 *  the plan is this machine's, and a frame round all of it would say nothing. */
function regions(s: StateX, here: number, awayW: number) {
  const root = $("regions") as unknown as SVGGElement;
  root.replaceChildren();
  const out = s.tasks.filter((t) => t.leaves).length, asks = s.tasks.filter(asksYou).length, r = away(s, here, awayW);
  if (!r || !out) return;
  root.appendChild(el("rect", { class: "region away", x: r.x, y: r.y, width: r.w, height: r.h, rx: 14 }));
  const label = root.appendChild(el("text", { class: "region-label away", x: r.x + 16, y: r.y + 21 }, `Leaves your machine · ${asks ? "asks you first" : `${out} task${out > 1 ? "s" : ""}`}`));
  if (lay!.down) fitText(label, lay!.width / 2 - 42 - r.x - 16); // left of the line down into it, and of the gate on that line
}

/** Where the region for what leaves this machine stands, once a step does: right of the plan, or laid downward,
 *  under it from side to side. */
function away(s: StateX, here: number, awayW: number): { x: number; y: number; w: number; h: number } | null {
  if (!lay || (!here && !lay.down)) return null;
  if (here) return { x: here + AWAY_GAP - 8, y: 8, w: awayW, h: lay.height - 16 };
  const ys = s.tasks.filter((t) => t.leaves && lay!.boxes[t.id]).map((t) => lay!.boxes[t.id]!.y);
  if (!ys.length) return null;
  const y = Math.min(...ys) - AWAY_TOP + 8;
  return { x: 8, y, w: lay.width - 16, h: lay.height - 8 - y };
}

/** The approval on the line: where an edge crosses into "leaves your machine", a mark that the step past it
 *  asks you before it runs. Gone once the step has run. */
function gates(s: StateX, here: number, awayW: number) {
  const root = $("gates") as unknown as SVGGElement;
  root.replaceChildren();
  const r = away(s, here, awayW);
  if (!r) return;
  for (const t of s.tasks.filter((x) => x.leaves && x.state !== "done")) {
    const p = lay!.boxes[t.id];
    if (!p) continue;
    const at = lay!.down ? `${p.x + p.w / 2} ${r.y}` : `${r.x} ${p.y + D.h / 2}`; // on its line, where it crosses the region's edge
    const g = el("g", { class: `gate${asksYou(t) ? " now" : ""}`, transform: `translate(${at})`, "aria-hidden": "true" });
    g.appendChild(el("rect", { x: -34, y: -10, width: 68, height: 20, rx: 10 }));
    g.appendChild(el("text", { y: 4, "text-anchor": "middle" }, "asks you"));
    root.appendChild(g);
  }
}

/** A card is drawn again whenever its task changes, which for a working one is every snapshot (its seconds
 *  quiet move): what turns or breathes on it takes up where the page's clock is, so a redraw starts nothing again. */
function inStep<T extends SVGElement>(node: T, period: number): T {
  node.style.animationDelay = `-${Date.now() % period}ms`;
  return node;
}

/** A chip on a card, in the UI's font as its foot's check, cut to the card: the files the step may change (or has written, or wrote outside
 *  them), its command. A path too long for it says its file (`CookServiceImpl.java +2`), then its file's name
 *  (`RecipeLookupServiceImpl +1`) before it is cut; never `…/` before it, one more spelling in a band for a folder
 *  it does not name. Every card names its file, whether or not it fits whole: `2 files` beside a card that names
 *  one read as two rules. And every files chip in the plan is spelt the same way, the shortest any one of them
 *  needs (`chipStep`): `PlannerServiceImpl.java +1` beside `LibrarianServiceImpl +1` was a rule by pixel width.
 *  ``bad`` ends it in the came-back red (a refused write) and stays whole: the words give way to it, their last one
 *  (`files`) before a number is cut. */
function pill(grp: SVGGElement, kind: string, glyph: string, words: string, x: number, y: number, max: number, bad = "") {
  const g = el("g", { class: `pill ${kind}` });
  const rect = g.appendChild(el("rect", { x, y, width: max, height: 18, rx: 5 }));
  // a codicon, drawn: a font's glyph for an icon is a grey blob at 1x, and another shape in every font. `$` is a word
  if (ICONS[glyph]) g.appendChild(el("path", { class: "pill-mark", d: ICONS[glyph], transform: `translate(${x + 4} ${y + 3}) scale(0.75)` }));
  else g.appendChild(el("text", { class: "pill-mark", x: x + 6, y: y + 13 }, glyph));
  const text = g.appendChild(el("text", { class: "pill-text", x: x + 20, y: y + 13 }, bad));
  grp.appendChild(g);
  const more = / \+\d+$/.exec(words)?.[0] ?? ""; // how many more files: kept whole, as the refused writes are
  text.textContent = bad + more;
  const room = max - 26 - (bad || more ? text.getComputedTextLength() || (bad + more).length * 7.2 : 0);
  words = words.slice(0, words.length - more.length);
  text.textContent = words;
  const file = words.split(" ").map(tailPath).join(" ").replace(/(^|\s)…\//g, "$1"); // a path says its file, then its name
  const spelt = [words, file, file.replace(/\.\w+(?=\s|$)/g, "")];
  const need = spelt.findIndex((w) => { text.textContent = w; return text.getComputedTextLength() <= room; });
  g.dataset.need = String(need < 0 ? 2 : need); // what this chip alone needs: `graph` spells every files chip at the most
  text.textContent = words = spelt[Math.max(need < 0 ? 2 : need, kind.startsWith("files") ? chipStep : 0)]!;
  if (bad && text.getComputedTextLength() > room) text.textContent = words.replace(/ \S+$/, "");
  fitText(text, room);
  if (more) text.appendChild(document.createTextNode(more));
  if (bad) text.appendChild(el("tspan", { class: "bad" }, bad));
  const w = text.getComputedTextLength() || (text.textContent ?? "").length * 7.2;
  rect.setAttribute("width", String(Math.min(max, Math.ceil(w) + 26)));
}

// The marks, as paths about the origin in a box of 20, each with how it is painted (graph.css `.mk`): `line` an
// outline, `solid` filled, `ink` drawn on a solid in the canvas's colour. A circle is the run's own business, a
// diamond is the person, a triangle is trouble, a square is the check (marks.ts).
const RING = "M0,-8a8,8 0 1 1 0,16a8,8 0 1 1 0,-16", DIAMOND = "M0,-9L9,0L0,9L-9,0Z", TRIANGLE = "M0,-8L9,7.5L-9,7.5Z";
const SQUARE = "M-4.5,-7.5h9a3,3 0 0 1 3,3v9a3,3 0 0 1 -3,3h-9a3,3 0 0 1 -3,-3v-9a3,3 0 0 1 3,-3z";
const TICK = "M-4.2,0.4l3,3.2l5.6,-6.6", CROSS = "M-3.4,-3.4l6.8,6.8M3.4,-3.4l-6.8,6.8", BANG = "M0,-3v4.5M0,4.6v.1";
const MARKS: Record<Mark | CheckMark["box"] | "ended" | "warn" | "portion", [string, string][]> = {
  // a step's state (`stateMark`), the same shape at every size
  waiting: [["line dots", RING]], ready: [["line", RING]], working: [["line faint", RING], ["line spin", "M0,-8a8,8 0 0 1 8,8"]],
  you: [["solid", DIAMOND]], yours: [["line", DIAMOND]], back: [["solid", TRIANGLE], ["ink", BANG]],
  landed: [["solid", RING], ["ink", TICK]], suggested: [["line dashes", RING]],
  // an attempt that ended without passing (`forkMark`); a row whose check proves nothing yet
  ended: [["line", RING], ["line", CROSS]], warn: [["line", TRIANGLE], ["line", BANG]],
  // how much of a sub-goal, or of the goal, landed (`ring`): its arc is cut to the portion
  portion: [["line faint", RING], ["line", RING]],
  // the check's box (`checkMark`): a square Graphene alone ticks; with no check, the diamond of your approval
  approval: [["line", DIAMOND]], passed: [["solid", SQUARE], ["ink", TICK]], failed: [["solid", SQUARE], ["ink", CROSS]],
  hollow: [["line dashes", SQUARE], ["line", BANG]], tells: [["line", SQUARE]], unrun: [["line dots", SQUARE]],
};

/** A mark drawn about a point, ``r`` px from its middle to its edge. Its lines are never thinner than 1.3 px;
 *  what turns on it takes up where the page's clock is (`inStep`). Its line's width is set on its style, not as a
 *  `style` attribute, which the webview's policy drops: in the editor every mark was a 1 px line scaled down. */
function mark(grp: SVGElement, kind: keyof typeof MARKS, x: number, y: number, r: number): SVGGElement {
  const g = grp.appendChild(el("g", { class: `mk ${kind}`, transform: `translate(${x} ${y}) scale(${r / 10})`, "aria-hidden": "true" }));
  g.style.setProperty("--sw", String(Math.max(2, 13 / r)));
  for (const [how, d] of MARKS[kind]) { // a path's length is said as 100, so its dots and dashes meet where it closes
    const p = g.appendChild(el("path", { class: how, d, pathLength: 100 }));
    if (how.endsWith("spin")) inStep(p, 900);
  }
  return g;
}

/** A ring filled by the portion that landed, of a sub-goal's tasks or of the plan's: the ticked disc once all
 *  have, an empty ring while none has. */
function ring(grp: SVGElement, portion: number, x: number, y: number, r: number) {
  if (portion >= 1) return void mark(grp, "landed", x, y, r);
  const arc = mark(grp, "portion", x, y, r).lastElementChild as SVGPathElement;
  if (portion > 0) arc.style.strokeDasharray = `${portion * 100} 100`; else arc.remove();
}

/** A sub-goal's title as a band's header and a lanes group say it: without the plan text's `? ` (its mark for a
 *  suggestion, where a planner left it in a title), and where the planner wrote `Name: what it covers`, its name
 *  alone (`CLI`, not `CLI: the walking skeleton every provided test starts…`); ``whole`` for its hover. */
function bandName(title: string): { name: string; whole: string } {
  const whole = title.replace(/^\?\s+/, ""), at = whole.indexOf(": ");
  return { name: at > 0 && at <= 40 ? whole.slice(0, at) : whole, whole };
}

/** A sub-goal's header, over its first row: the ring, its title, `3 of 6`, then what wants you there in words,
 *  each in its mark's colour (the cards under it wear each task's mark). Larger over rows, so it reads in a
 *  fitted plan. It keeps to ``max`` px: where all of it has no room the words go, and the title is cut to what is
 *  left. ``cross``: where lines go down through it: the words after the title end before the first, so the header
 *  reads as one phrase and no line runs through its words. Its width, as drawn. */
function bandHead(root: SVGGElement, title: string, ts: readonly TaskX[], x: number, y: number, max: number, cross: readonly number[] = []): number {
  const t = tally(ts), rows = level === "compact", r = rows ? 8 : 6, gap = rows ? 10 : 8;
  const g = root.appendChild(el("g", { class: "band-head" }));
  ring(g, t.portion, x + r, y, r);
  const text = (kind: string, words: string) => g.appendChild(el("text", { class: kind, y: y + (rows ? 5 : 4) }, words));
  const wide = (n: SVGTextElement) => n.getComputedTextLength() || (n.textContent ?? "").length * (rows ? 8.5 : 6.5); // not drawn yet: by its characters
  const name = text("band-label", title), count = t.total ? text("band-count", `${t.landed} of ${t.total}`) : null;
  const wants = t.wants.map((w) => { const n = text("band-want", w.text); n.dataset.mark = w.mark; return n; });
  const cw = count ? wide(count) + gap : 0, ww = wants.reduce((sum, n) => sum + wide(n) + gap, 0);
  const room = max - 2 * r - gap, words = Math.min(wide(name), 90) + cw + ww <= room;
  if (!words) for (const n of wants.splice(0)) n.remove();
  fitText(name, room - cw - (words ? ww : 0));
  let at = x + 2 * r + gap;
  const put = (n: SVGTextElement) => { n.setAttribute("x", String(at)); at += wide(n) + gap; };
  put(name);
  let clear = true; // the count and the words, up to a line down through the header
  for (const n of [count, ...wants]) if (n) {
    clear &&= !cross.some((c) => at < c + gap && at + wide(n) > c - gap);
    if (clear) put(n); else n.remove();
  }
  // its words ringed in the band's own ground (graph.css), so a line crossing the header passes behind them and
  // goes on between them, not under a plate where it seems to end
  return at - gap - x;
}

/** A card's foot, which is its check's, along the card's own foot (``h``, its attempts above it): a hairline, the
 *  check's box (marks.ts `checkMark`) and the check (``says``, cut at its words to as many characters as there is
 *  room for), tinted where the verdict is news. Its hover says `done when` the check whole, and the verdict. A step
 *  with no check is done when you approve; a draft that has said neither wears no box (a dotted one is a check not
 *  run yet) and says ``blank``. */
function cardFoot(grp: SVGGElement, c: CheckMark, says: (n: number) => string, h = BOX_H, w = BOX_W, blank = "no check yet") {
  const y = h - FOOT_H;
  const g = grp.appendChild(el("g", { class: `foot ${c.tone}` }));
  g.appendChild(el("path", { class: "tint", d: `M0.5,${y}H${w - 0.5}V${h - 12}a11.5,11.5 0 0 1 -11.5,11.5H12a11.5,11.5 0 0 1 -11.5,-11.5Z` }));
  g.appendChild(el("path", { class: "hair", d: `M0.5,${y + 0.5}H${w - 0.5}` })); // on a pixel's middle: one crisp line, not two soft ones
  const whole = says(Infinity), hover = [whole ? `done when ${whole}` : "", c.words].filter(Boolean).join(" · ") || (c.box === "approval" ? "done when you approve" : "");
  const boxed = Boolean(whole) || c.box !== "unrun";
  if (boxed) mark(g, c.box, PAD + 7, y + 11, 7);
  if (hover) g.appendChild(el("title", {}, hover)); // a draft that has said neither has nothing to say yet
  const x = boxed ? PAD + 20 : PAD, room = w - PAD - x;
  const v = g.appendChild(el("text", { class: "foot-v", x, y: y + 15 }));
  const fill = (n: number) => (v.textContent = says(n) || (c.box === "approval" ? "you approve" : blank));
  let n = Math.floor(room / 5); // more characters than a 12 px line holds; then by its drawn length
  do fill(n); while (v.getComputedTextLength() > room && --n > 6);
  if (!v.getComputedTextLength()) fill(Math.floor(room / 7.2)); // not drawn yet: by a count that never runs past
  if (v.getComputedTextLength() > room || !v.textContent) v.remove();
}

/** The card's one act, a real button at the status line's right end: Tab stops on it after the card, Enter and
 *  Space press it, and a click on it is the pane's button's click (`press`, unless ``go`` says otherwise) and not
 *  the card's. Its left edge, where the status line's room ends. */
function actButton(grp: SVGGElement, act: Button, id: string, title: string, go = () => press(act, id), gate = false): number {
  const b = grp.appendChild(el("g", { class: gate ? "act waits" : "act", role: "button", tabindex: 0, "aria-label": `${act.label}: ${title}` }));
  const label = b.appendChild(el("text", { y: STATUS_Y }, act.label));
  const w = Math.ceil(label.getComputedTextLength() || act.label.length * 7) + 16, x = BOX_W - PAD - w;
  b.prepend(el("rect", { x, y: STATUS_Y - 14, width: w, height: 20, rx: 5 }));
  label.setAttribute("x", String(x + 8));
  b.appendChild(el("title", {}, act.title));
  b.addEventListener("click", (e) => { e.stopPropagation(); if (e.detail < 2) go(); }); // a double click presses it once
  b.addEventListener("keydown", (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); e.stopPropagation(); go(); } });
  return x;
}

/** A draft's foot (a task drawn by hand, a step the planner is writing): its check as one not run yet; with
 *  none, your approval where it asks for it, else that it has no check yet, unless its status names that blank
 *  already (``named``: `check ___`). */
const draftFoot = (grp: SVGGElement, check: string, approve = false, named = false) =>
  cardFoot(grp, check || approve ? checkMark({ check: check || null, checked: { before: null, after: null }, state: "proposed", hollow: false }) : { box: "unrun", tone: "dim", words: "" },
       (n) => checkCut(check, n), BOX_H, BOX_W, named ? "" : undefined);

/** A title on up to ``most`` lines of ``max`` px from (``x``, ``y``), ``lh`` apart: whole words on each line, the
 *  last cut to the room (marks.ts `wrap`). Its text reads as the title does, whichever way it is broken. */
function titleLines(grp: SVGGElement, kind: string, title: string, x: number, y: number, lh: number, max: number, most: number): SVGTextElement {
  const text = grp.appendChild(el("text", { class: kind, x }));
  // not drawn yet (the SVG hidden), a line is cut by a character count
  const lines = wrap(title, max, (t) => { text.textContent = t; return text.getComputedTextLength() || t.length * 8; }, most);
  text.replaceChildren(...lines.map((line, i) => el("tspan", { x, y: y + i * lh }, i < lines.length - 1 ? `${line} ` : line)));
  return text;
}

/** A row's title: on one line at the row's middle, or on two when it is longer, the second cut to ``max`` px. */
function rowTitle(grp: SVGGElement, title: string, max: number) {
  const text = titleLines(grp, "title", title, ROW_X, 0, 17, max, 2);
  text.setAttribute("transform", `translate(0 ${text.childElementCount > 1 ? ROW_H / 2 - 4 : ROW_H / 2 + 5})`);
}

/** A card at the compact level, where the plan is read from afar: a row filled and bordered by its state
 *  (graph.css, by the group's `data-mark`), its state's mark large at the left, its title, and the ports its
 *  lines join at. At its right end only what is news: that its check proves nothing yet, else its attempts as
 *  small marks (four to a line). Nothing else: the hover says the whole line, and a double click opens it. */
function drawCompact(grp: SVGGElement, c: { title: string; hover: string; mark: Mark; selected: boolean; port?: string; naming?: Draft;
                                            hollow?: boolean; forks?: readonly ForkX[] }) {
  if (c.selected) grp.appendChild(el("rect", { class: "ring", x: -5, y: -5, width: ROW_W + 10, height: ROW_H + 10, rx: 14 }));
  grp.appendChild(el("rect", { class: "box", x: 0.5, y: 0.5, width: ROW_W - 1, height: ROW_H - 1, rx: 9.5 })); // on a pixel's middle, as a card's (`frame`)
  mark(grp, c.mark, 19, ROW_H / 2, 9.5);
  const forks = c.hollow ? [] : c.forks ?? [], cols = Math.min(4, forks.length), lines = Math.ceil(forks.length / 4);
  if (c.hollow) mark(grp, "warn", ROW_W - 15, ROW_H / 2, 7.5);
  forks.forEach((f, i) => mark(grp, forkMark(f), ROW_W - 11 - (cols - 1 - (i % 4)) * 10, ROW_H / 2 + (Math.floor(i / 4) - (lines - 1) / 2) * 11, 4));
  const news = c.hollow ? 20 : cols ? cols * 10 + 4 : 0;
  if (c.naming) { // a draft whose title is being typed keeps its box to type in
    const fo = el("foreignObject", { x: ROW_X - 5, y: 10, width: ROW_W - ROW_X - 3, height: 24 });
    fo.appendChild(nameInput(c.naming));
    grp.appendChild(fo);
  } else rowTitle(grp, c.title, ROW_W - ROW_X - 8 - news);
  grp.appendChild(el("title", {}, c.hover));
  grp.appendChild(el("circle", { class: "port in", cx: 0, cy: ROW_H / 2, r: 5 }));
  const port = grp.appendChild(el("circle", { class: "port", cx: ROW_W, cy: ROW_H / 2, r: 5 }));
  if (!c.port) return;
  port.setAttribute("data-port", c.port); // a link is dragged from a row's dot as from a card's
  port.appendChild(el("title", {}, "drag onto another task: it then waits on this one"));
}

/** A whole card's frame, ``h`` tall (its attempts make it taller): the ring of the chosen one, the box. A working
 *  card has no halo: its turning mark and its moving edge say it works. The box's 1 px border is drawn half a pixel
 *  in, on a pixel's middle: on a whole one it was two half-grey pixels at 100%, a soft edge on a 1x screen. */
function frame(grp: SVGGElement, h: number, chosen: boolean) {
  if (chosen) grp.appendChild(el("rect", { class: "ring", x: -5, y: -5, width: BOX_W + 10, height: h + 10, rx: 16 }));
  grp.appendChild(el("rect", { class: "box", x: 0.5, y: 0.5, width: BOX_W - 1, height: h - 1, rx: 11.5 }));
}

/** A card's status line, in its room (``right``: where its act or its tail starts). ``words`` says it in as many
 *  characters as it is given, a part dropped at a time (words.ts `sub`), so no word is cut while a shorter line
 *  says it whole. */
function status(grp: SVGGElement, words: (n: number) => string, right: number, bad = false) {
  const room = right - PAD - 8, n = Math.floor(room / 6.6);
  let line = words(n);
  if (line.endsWith("…")) { // cut: back to the last whole part when a word or two of the next is all that shows (`asks yo…`); the pane says it whole
    const whole = words(1000), at = Math.max(0, ...[...whole.matchAll(/ · |: /g)].map((m) => m.index).filter((i) => i <= n));
    if (at && line.length - at < 10) line = whole.slice(0, at);
  }
  fitText(grp.appendChild(el("text", { class: `sub${bad ? " bad" : ""}`, x: PAD, y: STATUS_Y }, line)), room);
}

/** A card's title on up to two lines, set close so the second clears the files chip. One line starts where two
 *  do, so the titles in a row share a top. Its state's mark has its room at its right whether it is drawn or not
 *  (ready and waiting have none): a title wraps the same in every state, and does not jump as its task runs. */
function cardTitle(grp: SVGGElement, title: string) {
  titleLines(grp, "title", title, PAD, 21, 16, BOX_W - 2 * PAD - 20, 2);
}

/** A task's card, drawn at the group's origin, everything inside it: its title on up to two lines, its files;
 *  its status with its one act at the right (or its model while it runs, or the attempts it is set to); its
 *  attempts, a chip each, while it is not done; its foot, which is its check's; the ports its lines join at, and
 *  its state's mark on its corner. From afar (the compact level) it is a row instead. The group says its mark
 *  (`data-mark`: graph.css colours by it) and the attempts it is set to and has not started (`data-attempts`),
 *  for a script to read as a person reads `3 agents at once`. */
function drawTask(grp: SVGGElement, t: TaskX, h: number, down: boolean, limit: number | null) {
  const acting = grp.querySelector(".act:focus") !== null; // its button has the keyboard: it keeps it through the redraw
  grp.replaceChildren();
  grp.setAttribute("class", `task ${cls(t.state)}${t.id === selected ? " selected" : ""}${t.needs_you ? " needs-you" : ""}`);
  grp.setAttribute("data-mark", stateMark(t));
  const asked = state ? questionOn(state, t.id)?.text ?? "" : "";
  const line = cardLine(t, 60, asked), times = attemptsMark(t, limit), check = checkMark(t), what = covers(t);
  if (times) grp.dataset.attempts = String(parseInt(times)); else delete grp.dataset.attempts;
  // its state in words where its line says something else (a question): only its mark says it to the eye
  const word = markWord(stateMark(t), t), said = (l: string) => (l.startsWith(word) ? l : `${word}, ${l}`);
  grp.setAttribute("aria-label", `${t.title}: ${said(line)}${what ? `; ${what}` : ""}${t.id === selected ? ", selected" : ""}`);
  const hover = [t.title, what, said(cardLine(t, LONG, asked)), check.words].filter(Boolean).join(" · "); // what it covers whole, the whole line, and the check's verdict
  if (level === "compact") {
    return drawCompact(grp, { title: t.title, hover, mark: stateMark(t), selected: t.id === selected,
                              port: replaying() || t.leaves ? undefined : t.id, hollow: check.box === "hollow", forks: t.forks });
  }
  frame(grp, h, t.id === selected);
  const corner = cornerMark(t); // its state's mark, inside the card at its title's right, as a row has it at its left
  cardTitle(grp, t.title);
  if (corner) mark(grp, corner, BOX_W - PAD - 7, 16, 7);
  // a title on one line leaves its second to what the task covers past it (`Librarian service: collections, …`), dim:
  // no card in a row has an empty band where another has words, and the status row says the state
  if (what && grp.querySelector(".title")?.childElementCount === 1) {
    const c = grp.appendChild(el("text", { class: "covers", x: PAD, y: 37 })), room = BOX_W - 2 * PAD;
    let n = Math.floor(room / 6.2);
    do c.textContent = coversIn(what, n); while (c.getComputedTextLength() > room && --n > 4);
    if (!c.getComputedTextLength()) c.textContent = coversIn(what, Math.floor(room / 7)); // not drawn yet: by a count that never runs past
    if (!c.textContent) c.remove();
  }
  const files = filesLine(t); // the latest fact about its files: what it may change, has written, or wrote outside them
  if (t.command) pill(grp, "run", "$", commandChip(t.command), PAD, 48, BOX_W - 2 * PAD); // a command step: what runs, with no agent
  if (files.text) pill(grp, `files ${files.tone}`, files.mark, files.text, PAD, 48, BOX_W - 2 * PAD, files.refused && ` · ${files.refused}`);
  // the status; at its end the card's act, else its model while one agent runs it (attempts each name theirs), or
  // the agents it is set to, whose hover says what that costs. Chosen, it has none: its pane holds that act, once
  const chosen = t.id === selected;
  const act = chosen ? null : cardAct(t, replaying(), seen.has(t.id)); // its changes opened here: Approve, as its pane says
  let right = BOX_W - PAD;
  // a gate the run waits on is filled (graph.css `.act.waits`): a step past the line or of your own, a write stopped
  if (act) right = actButton(grp, act, t.id, t.title, undefined, act.act === "markDone" || (act.act === "handBack" && t.state === "running"));
  else if (!chosen && asked && stateMark(t) === "you" && !replaying()) { // it wants you for its question: its answers are in its pane, the first one focused
    right = actButton(grp, { label: "Answer…", act: "answer", icon: "", main: true, title: `its answers, in its pane: ${asked}` }, t.id, t.title,
                      () => { select(t.id); document.querySelector<HTMLElement>("#details .ask-opts button")?.focus(); });
  } else {
    const tail = t.state === "running" && t.model && t.forks.length < 2 ? cut(t.model, 14) : times;
    const end = tail ? grp.appendChild(el("text", { class: tail === times ? "times" : "model", x: right, y: STATUS_Y, "text-anchor": "end" }, tail)) : null;
    if (end) right -= (end.getComputedTextLength() || tail.length * 7) + 8;
    if (end && tail === times) end.appendChild(el("title", {}, attemptsWhy(parseInt(times))));
  }
  status(grp, (n) => cardLine(t, n, asked), right);
  if (acting) (grp.querySelector<SVGGElement>(".act") ?? grp).focus({ preventScroll: true }); // pressed, and gone: the card has it
  // its attempts: a row each, over its foot, its mark and its words as a status reads (no box: they are not
  // fields); the kept one on a quiet fill, its why in its hover. Once it is done they are history (the pane's Activity)
  (t.state === "done" ? [] : t.forks).forEach((f, i) => {
    const y = BOX_H - FOOT_H + 2 + i * FORK_H;
    const kept = t.kept?.letter === f.letter, room = BOX_W - 2 * PAD - 26;
    const chip = el("g", { class: `fork ${cls(f.state || "waiting")}${kept ? " kept" : ""}` });
    chip.appendChild(el("rect", { class: "chip", x: PAD, y, width: BOX_W - 2 * PAD, height: FORK_H - 4, rx: 5 })); // its hover's
    mark(chip, forkMark(f), PAD + 9, y + 9, 5);
    // the kept one says so where its state would be (`b · Nano · kept`), its mark already ticked
    const words = forkWords(kept ? { ...f, state: "kept" } : f, kept ? null : t.kept, Math.floor(room / 6.6));
    fitText(chip.appendChild(el("text", { class: "chip-text", x: PAD + 20, y: y + 13 }, words)), room);
    chip.appendChild(el("title", {}, forkRow(f, t.kept)));
    grp.appendChild(chip);
  });
  cardFoot(grp, check, (n) => doneWhen(t, n), h);
  grp.appendChild(el("title", {}, hover));
  // its ports, where its lines join: in at the left, out at the right (the top and the foot when laid downward)
  grp.appendChild(el("circle", { class: "port in", cx: down ? BOX_W / 2 : 0, cy: down ? 0 : BOX_H / 2, r: 5 }));
  const port = grp.appendChild(el("circle", { class: "port", cx: down ? BOX_W / 2 : BOX_W, cy: down ? h : BOX_H / 2, r: 5 }));
  if (replaying() || t.leaves) return; // a replay is watched, not linked; a task drawn after a step past the line would land in the first column
  // drag its out port onto another task and that task waits on this one
  port.setAttribute("data-port", t.id);
  port.appendChild(el("title", {}, "drag onto another task: it then waits on this one"));
  // its +, past the out port: a new task drawn after this one
  const plus = el("g", { class: "plus", "data-plus": t.id });
  const px = BOX_W + 17, py = BOX_H / 2;
  plus.appendChild(el("rect", { class: "reach", x: BOX_W + 5, y: py - 10, width: 22, height: 20 })); // the pointer crosses to it without leaving the task
  plus.appendChild(el("circle", { cx: px, cy: py, r: 8 }));
  plus.appendChild(el("path", { d: `M${px - 4},${py} h8 M${px},${py - 4} v8` }));
  plus.appendChild(el("title", {}, "draw a task after this one"));
  plus.addEventListener("click", (e) => { e.stopPropagation(); draw({ after: t.id, parent: t.parent }); });
  grp.appendChild(plus);
}

/** A draft's card: dashed, its title (typed here while it is new), its files and check once it has them, and
 *  in its status its blanks until they are filled. */
function drawDraft(grp: SVGGElement, d: Draft) {
  grp.replaceChildren();
  grp.setAttribute("class", `task draft${d.key === selected ? " selected" : ""}`);
  grp.setAttribute("data-mark", "suggested");
  grp.setAttribute("aria-label", `a draft: ${d.title || "no title yet"}: ${blanks(d)}${d.key === selected ? ", selected" : ""}`);
  if (level === "compact") {
    return drawCompact(grp, { title: d.title, hover: `a draft: ${d.title} · ${blanks(d)}`, mark: "suggested", selected: d.key === selected, naming: naming === d.key ? d : undefined });
  }
  frame(grp, BOX_H, d.key === selected);
  mark(grp, "suggested", BOX_W - PAD - 7, 16, 7); // the ring it will wear as a suggestion
  if (naming === d.key) {
    const fo = el("foreignObject", { x: PAD - 5, y: 10, width: BOX_W - 2 * PAD - 16, height: 24 }); // clear of its ring
    fo.appendChild(nameInput(d));
    grp.appendChild(fo);
  } else cardTitle(grp, d.title);
  const files = filesChip(globs(d.files));
  if (files) pill(grp, "files", "file", files, PAD, 48, BOX_W - 2 * PAD);
  status(grp, () => (d.said ? "not taken: see why" : blanks(d)), BOX_W - PAD, Boolean(d.said));
  draftFoot(grp, d.check, d.approve, !d.said);
  grp.appendChild(el("title", {}, `a draft: ${d.title} · ${blanks(d)}`));
}

/** A step the planner has written so far: a drafted card with what of its files and check it has said, and no
 *  buttons. It is watched while the plan is written, and is a suggested task once the plan arrives: it wears that
 *  card's shape and its ring already, so it lands as it looked. */
function drawPlanned(grp: SVGGElement, d: DraftStep, down: boolean) {
  grp.replaceChildren();
  grp.setAttribute("class", "task drafted");
  grp.setAttribute("data-mark", "suggested");
  grp.setAttribute("aria-label", `the planner is drafting: ${d.title}`);
  if (level === "compact") return drawCompact(grp, { title: d.title, hover: `the planner is drafting: ${d.title}`, mark: "suggested", selected: false });
  frame(grp, BOX_H, false);
  cardTitle(grp, d.title);
  mark(grp, "suggested", BOX_W - PAD - 7, 16, 7);
  const files = filesChip(d.scope);
  if (files) pill(grp, "files", "file", files, PAD, 48, BOX_W - 2 * PAD);
  status(grp, () => "drafted", BOX_W - PAD);
  draftFoot(grp, d.check ?? "");
  grp.appendChild(el("title", {}, `the planner is drafting: ${d.title}`));
  grp.appendChild(el("circle", { class: "port in", cx: down ? BOX_W / 2 : 0, cy: down ? 0 : BOX_H / 2, r: 5 }));
  grp.appendChild(el("circle", { class: "port", cx: down ? BOX_W / 2 : BOX_W, cy: down ? BOX_H : BOX_H / 2, r: 5 }));
}

// ---- the lanes: one row a task, grouped by sub-goal ----

const laneEls = new Map<string, { el: HTMLElement; key: string }>();
let lanesKey = "";

function lanes(s: StateX) {
  const root = $("lanes");
  const g = boxes(s);
  const order = layout(g.boxes, g.edges, { goal: g.goal, boxW: BOX_W, boxH: BOX_H });
  lay = null; // arrows walk the rows, not a drawing
  // a sub-goal a group, headed as its band is on the canvas, in the graph's order, its tasks in the order they
  // start; tasks in none (or in auto's root, which is the goal) last, over the goal, headed only where groups
  // stand above them, so they never read as the last group's; a step past the line after them all, under its own
  const AWAY = " away", groups = new Map<string, TaskX[]>(order.bands.filter((b) => b.id && goalTitle(s, b.id) !== s.goal).map((b) => [b.id, []]));
  groups.set("", []).set(AWAY, []);
  for (const t of s.tasks) groups.get(t.leaves ? AWAY : groups.has(t.parent ?? "") ? t.parent ?? "" : "")!.push(t);
  const box = (t: TaskX) => order.boxes[t.id];
  for (const ts of groups.values()) ts.sort((p, q) => (box(p)?.rank ?? 0) - (box(q)?.rank ?? 0) || (box(p)?.y ?? 0) - (box(q)?.y ?? 0));
  const heads = [...groups].filter(([, ts]) => ts.length).map(([id, ts]) => [id, ts, id === AWAY ? `leaves your machine${ts.some(asksYou) ? " · asks you first" : ""}` : id ? done(ts) : ""] as const);
  const steps = draftedSteps(s);
  const key = JSON.stringify([heads.map(([id, ts, n]) => [id, n, goalTitle(s, id), ts.map((t) => t.id)]), selected, s.goal, done(s.tasks), drawn(), naming, steps, planningLine(s)]);
  const rows: HTMLElement[] = [];
  const seen = new Set<string>();
  for (const [id, ts, n] of heads) {
    if (id === AWAY) rows.push(div("wave", n));
    else if (!id) { if (heads.some(([h]) => h && h !== AWAY)) rows.push(div("wave", "in no sub-goal")); }
    else {
      const { name, whole } = bandName(goalTitle(s, id)), head = div("wave");
      div("w-name", name, head).title = whole;
      head.append(n);
      rows.push(head);
    }
    for (const t of ts) {
      seen.add(t.id);
      const k = JSON.stringify([t, t.id === selected, s.envelope.forks]);
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
  }
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
  if (s.drafting) rows.push(div("wave planning", planningLine(s))); // the narrow view says it here, above the steps written so far
  for (const d of steps) {
    const row = div("lane drafted");
    row.setAttribute("aria-label", `the planner is drafting: ${d.title}`);
    div("l-stripe", undefined, row);
    const main = div("l-main", undefined, row);
    div("l-title", d.title, main);
    div("l-sub", ["drafted", filesChip(d.scope), d.check ?? ""].filter(Boolean).join(" · "), main);
    const b = d.parent ? bandName(goalTitle(s, d.parent)) : null;
    if (b && b.whole !== s.goal) div("l-band", b.name, main).title = b.whole; // a planner's root sub-goal is the goal itself: said once, at the foot
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
  const at = root.contains(document.activeElement) ? (document.activeElement as HTMLElement) : null;
  root.replaceChildren(...rows); // a row that moved is moved, not made again
  if (at?.isConnected) at.focus({ preventScroll: true }); // and the one with the focus keeps it
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
  const model = cornerWord(t), corner = cornerMark(t); // its model while it works, and its state's mark as its card's corner wears it
  if (model) div("l-model", model, head);
  if (corner) mark(head.appendChild(el("svg", { class: "l-mark", width: 14, height: 14, viewBox: "-7 -7 14 14" })), corner, 0, 0, 6);
  const times = attemptsMark(t, s.envelope.forks); // set to attempts it has not started: 3 attempts, as on its card
  div("l-sub", [line, times].filter(Boolean).join(" · "), main);
  if (times) row.dataset.attempts = String(parseInt(times)); else delete row.dataset.attempts;
  // its scope, as its card says it: the files it may change (or has written) by their names, and the check it is done when
  const files = filesLine(t), check = doneWhen(t, 48), what = [t.command ? commandChip(t.command) : files.text.split(" ").map((w) => tailPath(w).replace(/^…\//, "")).join(" "), check].filter(Boolean);
  if (what.length) div(`l-scope${files.tone === "back" ? " bad" : ""}`, what.join(" · "), main).title = [t.command ?? t.scope.join(" "), t.check ? `done when ${t.check}` : ""].filter(Boolean).join("\n");
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
    const x1 = p.x + D.w / 2, y1 = p.y + p.h, dy = Math.max(16, Math.abs(wiring.y - y1) / 2);
    return `M${x1},${y1} C${x1},${y1 + dy} ${wiring.x},${wiring.y - dy} ${wiring.x},${wiring.y}`;
  }
  const x1 = p.x + D.w, y1 = p.y + D.h / 2, dx = Math.max(24, Math.abs(wiring.x - x1) / 2);
  return `M${x1},${y1} C${x1 + dx},${y1} ${wiring.x - dx},${wiring.y} ${wiring.x},${wiring.y}`;
}

/** Where the pointer is in the graph's own units: the SVG is drawn 1:1, then translated and scaled. */
function at(e: MouseEvent): { x: number; y: number } {
  const r = $("svg").getBoundingClientRect();
  return { x: (e.clientX - r.left) / zoom.k, y: (e.clientY - r.top) / zoom.k };
}

/** The card under a point of the canvas, or the nearest to it, and where its middle is on screen: what holds
 *  still while every card turns to the other level of detail. */
function anchor(px: number, py: number): { id: string; sx: number; sy: number } | null {
  const p = lay ? nearest(Object.values(lay.boxes), (px - zoom.tx) / zoom.k, (py - zoom.ty) / zoom.k) : undefined;
  return p ? { id: p.id, sx: (p.x + D.w / 2) * zoom.k + zoom.tx, sy: (p.y + D.h / 2) * zoom.k + zoom.ty } : null;
}

/** The other level of detail at ``k``, the plan laid out again for it, with one card's middle at a point of
 *  the canvas. */
function turn(to: Level, k: number, at: { id: string; sx: number; sy: number }) {
  level = to;
  moved = true;
  zoom = { ...zoom, k };
  render();
  const p = lay?.boxes[at.id];
  if (p) zoom = clamp({ k, tx: at.sx - (p.x + D.w / 2) * k, ty: at.sy - (p.y + D.h / 2) * k });
  applyZoom();
}

/** Zoom to ``k`` about a point of the canvas (the pointer, or its middle for the buttons and the keys). Past
 *  a threshold (zoom.ts) whole cards turn to rows, or rows to whole cards: the card at the point stays there. */
function zoomAt(k: number, px: number, py: number) {
  k = zoomK(k);
  const to = lay && !lay.down ? levelFor(level, k) : level; // laid downward, the cards stay whole
  const at = to === level ? null : anchor(px, py);
  if (at) return turn(to, switchK(k, level, to), at);
  zoom = clamp({ k, tx: px - (px - zoom.tx) * (k / zoom.k), ty: py - (py - zoom.ty) * (k / zoom.k) });
  moved = true;
  applyZoom();
}

/** A step in or out about the canvas's middle: the buttons, and `-` and `=`. */
const nudge = (by: number) => zoomAt(zoom.k * by, $("canvas").clientWidth / 2, $("canvas").clientHeight / 2);

/** Back to whole cards at their own size (100%), about the canvas's middle: `0`, and a click on the percent. */
function actual() {
  const px = $("canvas").clientWidth / 2, py = $("canvas").clientHeight / 2;
  const at = level === "compact" ? anchor(px, py) : null;
  if (at) turn("full", 1, at); else zoomAt(1, px, py);
}

/** A row, opened by a double click: whole cards at their own size, that one in the canvas's middle. */
const detail = (id: string) => turn("full", 1, { id, sx: $("canvas").clientWidth / 2, sy: $("canvas").clientHeight / 2 });

/** The whole plan in the pane again, as `f` and a double click on the canvas ask: however small that draws it,
 *  which the plan opening does not (`opening`). */
let fitAll = false;
function refit() {
  moved = false;
  drawing = null;
  fitRoom = "";
  fitAll = true;
  render();
  fitAll = false;
}

/** The minimap, drawn again with the graph: every card a small rect in its mark's colour (as its row is), the
 *  sub-goals as outlines, and a frame (placed by `applyZoom`) for the part on screen. In the drawing's own units. */
function minimap(s: StateX, spans: ReadonlyMap<string, { x0: number; x1: number }>) {
  const map = $("minimap").firstElementChild;
  if (!lay || !map) return;
  const size = miniSize(sizeOf(lay));
  map.setAttribute("viewBox", `0 0 ${lay.width} ${lay.height}`);
  map.setAttribute("width", String(size.w));
  map.setAttribute("height", String(size.h));
  const kids: SVGElement[] = lay.bands.filter((b) => spans.has(b.id)).map((b) => el("rect", { class: "mm-band", x: spans.get(b.id)!.x0, y: b.y0, width: spans.get(b.id)!.x1 - spans.get(b.id)!.x0, height: b.y1 - b.y0, rx: 10 }));
  const of = new Map(s.tasks.map((t) => [t.id, t]));
  for (const p of Object.values(lay.boxes)) {
    const t = of.get(p.id);
    kids.push(el("rect", { class: "mm-box", "data-mark": t ? stateMark(t) : p.id === GOAL ? "goal" : "suggested", x: p.x, y: p.y, width: p.w, height: p.h, rx: 12 }));
  }
  kids.push(el("rect", { class: "mm-frame", rx: 6 }));
  map.replaceChildren(...kids);
}

/** The legend at the canvas's foot: the marks the plan has, each with its word and how many wear it, the
 *  loudest first (marks.ts `legend`). With no room beside the zoom's buttons it gives way: each card says its state. */
function legendRow(s: StateX) {
  const root = $("legend"), rows = legend(s.tasks, drawn().length + draftedSteps(s).length), key = JSON.stringify(rows);
  if (root.dataset.key !== key) {
    root.dataset.key = key;
    root.replaceChildren(...rows.map(([kind, word, n]) => {
      const row = div("", word);
      mark(row.insertBefore(el("svg", { width: 14, height: 14, viewBox: "-7 -7 14 14" }), row.firstChild), kind, 0, 0, 6);
      row.appendChild(document.createElement("b")).textContent = String(n);
      return row;
    }));
  }
  root.hidden = false;
  root.hidden = !rows.length || root.offsetWidth > $("canvas").clientWidth - $("zoom").offsetWidth - 56;
}

/** The steps to act on, in the plan's order: what the header's chip counts, and `n` walks.
 *  None in a replay, which is watched. */
const wantYou = (): string[] => (state && !replaying() ? wanting(state.tasks) : []);

/** The next step that wants you, selected and brought on screen; round again after the last. */
function showNext() {
  const id = nextWanting(wantYou(), selected);
  if (id) select(id, true);
}

/** A pan never loses the graph (zoom.ts `hold`). The canvas's foot is the buttons': the plan's last row can
 *  always be brought above it, and a plan smaller than the canvas stays above it. */
function clamp(z: Zoom): Zoom {
  return lay ? hold(z, { w: paneSize().w, h: paneSize().h - foot() }, sizeOf(lay)) : z;
}

let placed = ""; // the transform last applied: what says the plan moved since
let mapIdle: ReturnType<typeof setTimeout> | undefined;
/** The minimap fades a moment after the plan stops moving, unless the pointer is on it. */
function idle(map: HTMLElement) {
  clearTimeout(mapIdle);
  mapIdle = setTimeout(() => { if (!map.matches(":hover")) map.classList.remove("live"); }, 1500);
}

function applyZoom() {
  const svg = $("svg"), canvas = $("canvas");
  const to = `translate(${zoom.tx}px, ${zoom.ty}px) scale(${zoom.k})`, moving = to !== placed;
  placed = svg.style.transform = to;
  svg.style.transformOrigin = "0 0";
  svg.style.setProperty("--k", String(zoom.k)); // what must keep its size on screen divides by it (graph.css `.far`)
  svg.classList.toggle("far", level === "compact" && zoom.k < FAR);
  for (const h of sticky) { // a band's start off the canvas's left: its header slides along it, to the canvas's edge
    const by = Math.min(h.room, Math.max(0, -(h.x * zoom.k + zoom.tx) / zoom.k));
    h.g.style.transform = by > 0 ? `translate(${by}px, 0)` : "";
  }
  const dots = canvas.style, gap = dotGap(zoom.k); // the canvas's dots move with the plan, and thin out as it shrinks
  dots.backgroundPosition = `${zoom.tx}px ${zoom.ty}px`;
  dots.backgroundSize = `${gap}px ${gap}px`;
  // at the floor there is no zooming out, at the ceiling no zooming in; between them, how big a card is drawn
  ($("zoom-out") as HTMLButtonElement).disabled = zoom.k <= ZOOM_MIN;
  ($("zoom-in") as HTMLButtonElement).disabled = zoom.k >= ZOOM_MAX;
  const pct = percent(level, zoom.k);
  $("zoom-pct").textContent = `${pct}%`;
  $("zoom-pct").setAttribute("aria-label", `zoom ${pct}%: back to 100%`);
  // part of the plan off screen: the minimap shows all of it, and frames the part in view. Not while a pane is
  // open on a plan still fitted for the window: what is out of view then is what the pane's side hid, and the
  // minimap would stand on the cards beside it. It shows while a hand moves the plan, and a moment after: it is
  // never parked over the cards (graph.css `.live`)
  const map = $("minimap"), all = lay ? sizeOf(lay) : null;
  map.hidden = !all || view() === "lanes" || canvas.clientHeight < 240 || (!moved && !drawing && !$("details").hidden) || !offScreen(zoom, paneSize(), all);
  if (all && !map.hidden) {
    const f = miniFrame(zoom, paneSize(), all), frame = map.querySelector(".mm-frame");
    for (const [k, v] of [["x", f.x], ["y", f.y], ["width", f.w], ["height", f.h]] as const) frame?.setAttribute(k, String(v));
    if (moving && moved) { map.classList.add("live"); idle(map); }
  }
}

/** Pan so a box is on screen (the goal on `g`, a task the host selects). One on screen already moves nothing:
 *  a fitted plan stays fitted. ``own``: the pan is the page's (a card chosen, or reached by the keys), not the
 *  person's: the plan is still fitted again at the next resize. */
function reveal(id: string, own = false) {
  const p = lay?.boxes[id];
  if (!p || !lay) return;
  const canvas = $("canvas");
  const w = canvas.clientWidth, h = canvas.clientHeight - foot();
  const x0 = p.x * zoom.k + zoom.tx, x1 = (p.x + p.w) * zoom.k + zoom.tx;
  const y0 = p.y * zoom.k + zoom.ty, y1 = (p.y + p.h) * zoom.k + zoom.ty;
  let { tx, ty } = zoom;
  if (x0 < 0) tx -= x0 - 12; else if (x1 > w) tx -= x1 - w + 12;
  if (y0 < 0) ty += 12 - y0; else if (y1 > h) ty -= y1 - h + 12; // under the zoom's buttons it is not on screen
  if (tx === zoom.tx && ty === zoom.ty) return;
  zoom = clamp({ ...zoom, tx, ty });
  if (!own) moved = true;
  applyZoom();
}

// ---- selection, the pane, the hint, the help ----

function clicked(id: string) {
  if (linking && linking !== id) {
    if (isDraft(id)) redraw(id, { after: linking }); // a draft waits on it from the start
    else api.postMessage({ type: "act", act: "link", id: linking, target: id });
    linking = null;
    select(id);
    return;
  }
  select(id);
}

/** A card chosen: its pane opens beside the canvas, and nothing else moves: not the zoom, not the level. Only
 *  where that leaves the card out of view (under the pane's side of the canvas, or off it already) does the
 *  plan pan, just enough to show it. That pan is the page's own, not the person's: the next resize fits again. */
function select(id: string | null, focus = false) {
  selected = id;
  render();
  if (!id) return;
  const lanes = view() === "lanes";
  if (focus) ((lanes ? laneEls.get(id)?.el : taskEls.get(id)?.g) as HTMLElement | SVGGElement | undefined)?.focus({ preventScroll: !lanes });
  if (!lanes) reveal(id, true);
}

/** Link mode off: nothing armed, no wire drawn. On Esc, Cancel, or a select from outside the graph. */
function disarm() {
  linking = null;
  wiring = null;
  $("canvas").classList.remove("wiring");
}

/** The strip under the canvas, there only while a link is being drawn, with its way out (the header's ? lists the
 *  keys). Otherwise the cards, the chips and the header say what changed, and the latest news is in it for a screen
 *  reader alone (`sr`), not a log line over the editor's status bar. */
function hint() {
  const h = $("hint");
  h.hidden = false;
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
  } else {
    h.textContent = state ? newsLine(state, !$("auto").hidden) : "";
    h.className = "sr";
  }
}

/** A line of the pane: its label, and its value, in mono only where it is a path or a command. */
function row(label: string, value: string, parent: HTMLElement, mono = false): HTMLDivElement | null {
  if (!value) return null;
  const r = div("row", undefined, parent);
  div("k", label, r);
  if (mono) seams(value, div("v mono", undefined, r)); else div("v", value, r);
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
  input.className = name === "title" ? "f" : "f mono"; // files and a check are paths and a command
  input.type = "text";
  input.value = value;
  input.placeholder = placeholder;
  input.title = hover;
  input.spellcheck = false;
  input.maxLength = LONG;
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
  field(body, "title", "Title", t.full || t.title, "what this task does", "the task, in a line",
        (v) => (!v.trim() || same(v, t.full || t.title) ? back() : setField(t, "title", v.trim())));
  field(body, "files", "Files", t.scope.join(" "), "src/api/** tests/test_api.py", "the files it may change: paths or globs, a space between",
        (v) => (!globs(v).length || globs(v).join(" ") === t.scope.join(" ") ? back() : setField(t, "scope", globs(v).join(" "))));
  field(body, "check", "Check", t.check ?? "", "pytest -q", "the command that passes only when the task is done; empty: your approval finishes it",
        (v) => (same(v, t.check ?? "") ? back() : setField(t, "check", v.trim())));
  // its attempts are agents at once, each in its own copy and each spending: not retries, so it says so
  const n = attemptsOf(t, s.envelope.forks);
  const r = div("row", undefined, body);
  r.title = n > 1 ? `${n} attempts: ${n} agents work on it at once, each in its own copy; its check keeps one. About ${n}× the cost.`
    : "one agent works on it; with more attempts, more agents work at once, each in its own copy, and its check keeps one";
  div("k", "Attempts", r);
  const v = div("v stepper", undefined, r);
  const step = (label: string, to: number, sign: string) => {
    const b = document.createElement("button");
    b.className = "quiet";
    b.textContent = sign;
    b.setAttribute("aria-label", label);
    b.title = t.check ? label : "more attempts need a check to keep one";
    b.disabled = !t.check || to < 1 || to > 8;
    b.addEventListener("click", () => setField(t, "forks", to));
    v.appendChild(b);
  };
  step("one attempt fewer", n - 1, "−");
  div("count", String(n), v).setAttribute("aria-label", `${n} attempt${n > 1 ? "s" : ""} at once`);
  step("one more attempt", n + 1, "+");
  div("dim", !t.check ? "more need a check to keep one" : n > 1 ? `at once · about ${n}× the cost` : "", v);
  const unread = t.signoff === null; // `graphene plan --json` not read yet: a moment
  tick(body, "signoff", "Wait for my approval", t.signoff === true, "it lands only once you approve it, as well as passing its check", (on) => setField(t, "signoff", on), unread);
  tick(body, "owner", "I will do this one", Boolean(t.owner) && t.owner !== "agent", "no agent takes it: it is yours to do", (on) => setField(t, "owner", on), unread);
  div("when", whenEdit(t), body);
  const no = refused.get(t.id);
  if (no) div("refused", no, body).setAttribute("role", "alert");
}

/** The pane's ×, at its head's right. */
function closer(parent: HTMLElement) {
  const close = document.createElement("button");
  close.className = "close";
  close.appendChild(icon("close"));
  close.title = "close (Esc)";
  close.setAttribute("aria-label", "close");
  close.addEventListener("click", () => select(null));
  parent.appendChild(close);
}

/** A draft's pane: the same form, its own; what it still lacks, or graphene's refusal; and the planner, a click away. */
function draftPane(pane: HTMLElement, d: Draft) {
  const head = div("d-head", undefined, pane);
  div("d-title st-draft", d.title || "A new task", head);
  div("d-id", "a draft · not in the plan yet", head);
  closer(div("d-tools", undefined, head));
  const body = div("d-body", undefined, pane);
  const asked = offered.has(d.key) && !d.said; // graphene is deciding: what it was offered is not changed under it
  field(body, "title", "Title", d.title, "what this task does", "the task, in a line", (v) => (v.trim() ? redraw(d.key, { title: v.trim() }) : redraw(d.key, {}))).disabled = asked;
  field(body, "files", "Files", d.files, "src/api/** tests/test_api.py", "the files it may change: paths or globs, a space between", (v) => redraw(d.key, { files: v.trim() })).disabled = asked;
  field(body, "check", "Check", d.check, "pytest -q", "the command that passes only when the task is done", (v) => redraw(d.key, { check: v.trim() })).disabled = asked;
  tick(body, "signoff", "Wait for my approval", d.approve, "it lands only once you approve it", (on) => redraw(d.key, { approve: on }), asked);
  const after = d.after ? state?.tasks.find((t) => t.id === d.after)?.title : "";
  row("After", after ?? "", body);
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
    api.postMessage({ type: "act", act: d.after ? "add-after" : "add-under", id: d.after ?? d.parent ?? "", sentence: title, key: d.key });
    paneLast = "";
    render();
  });
  act("Discard", "trash", "take this draft away", () => discard(d.key));
}

/** The pane's tab: Scope until the person picks another, and then that one for every task they open. */
const tab = (): Tab => saved.tab ?? "scope";
const pane_ = () => pane();

/** A part of the Scope tab: its heading, with a few words at its right. */
function part(body: HTMLElement, title: string, aside = ""): HTMLElement {
  const sec = document.createElement("section");
  sec.className = "sc";
  const h = document.createElement("h3");
  h.textContent = title;
  if (aside) { const em = document.createElement("em"); em.textContent = aside; h.appendChild(em); }
  sec.appendChild(h);
  body.appendChild(sec);
  return sec;
}

let restOpen = false; // May change's fold, as the person left it
let wholeCheck = false; // a long check shown whole, as the person left it

/** A command or a path, breakable where it reads as a seam: its spaces; a path after its slashes; a long dotted name
 *  after its dots and underscores (`app.cookyourbooks.services.impl.` and `CookServiceImplTest`), never before its
 *  extension; a short piece with a hyphen held whole (`--tests`). <wbr>, so a copied command is the command. Home's
 *  code() (home/main.ts) is a near copy that does break before an extension: they are to be one function. */
function seams(text: string, parent: HTMLElement) {
  for (const w of text.split(/(\s+)/)) {
    w.split(w.includes("/") || w.length < 24 ? /(?<=\/)/ : /(?<=[._])(?![^._]{1,5}$)/).forEach((part, i) => {
      if (i) parent.append(document.createElement("wbr"));
      if (part.length < 24 && part.includes("-")) { const nb = document.createElement("span"); nb.className = "nb"; nb.textContent = part; parent.append(nb); }
      else parent.append(part);
    });
  }
}
const code = (text: string, parent: HTMLElement) => { const c = document.createElement("code"); seams(text, c); parent.appendChild(c); return c; };
const small = (text: string, parent: HTMLElement) => { const c = document.createElement("small"); c.textContent = text; parent.appendChild(c); return c; };

/** Scope: what this step may do, in plain view. May change (a tree, the glob behind it), done when, may run,
 *  outside, held by, stopped, tokens. Every word is what the snapshot says; where it says nothing, so does this. */
function scopeTab(body: HTMLElement, t: TaskX, s: StateX) {
  if (t.command) return commandScope(body, t);
  const wrote = writtenOf(t);
  const change = part(body, "May change", wrote && !wrote.startsWith("0 ") ? `✎ ${wrote}` : ""); // a count once something is written
  const tree = div("tree", undefined, change);
  const rows = scopeTree(t, s);
  // a deep path by its first two parts and its last, a file's folder too (`src/main/…/impl/`, `src/test/…/impl/`:
  // code and its test told apart); whole on the hover
  const short = (p: string) => {
    const at = p.split("/").filter(Boolean), end = p.endsWith("/") ? 1 : 2;
    return at.length > end + 3 ? `${[...at.slice(0, 2), "…", ...at.slice(-end)].join("/")}${p.endsWith("/") ? "/" : ""}` : p;
  };
  const line = (r: { name: string; kind: string; depth: number; note: string }, parent: HTMLElement) => {
    const row = div(`tr ${r.kind}${r.depth ? " in1" : ""}`, undefined, parent);
    const name = div("tr-name", undefined, row);
    name.title = r.name;
    // what is become of a file is a mark in the gutter before it, its word on the hover: never a word left alone on a
    // line under a long name
    const mark = ({ new: ["+", "new: not there yet, it may create it"], written: ["✎", "written"], "outside its files": ["✕", "written outside its files"] } as Record<string, string[]>)[r.note];
    if (mark) {
      const m = document.createElement("span");
      m.className = `tr-mark${r.note === "written" ? " wr" : ""}`;
      m.textContent = mark[0]!;
      m.title = mark[1]!;
      m.setAttribute("role", "img");
      m.setAttribute("aria-label", mark[1]!);
      name.append(m);
    }
    // it wraps after a slash, not inside a name
    (r.depth ? r.name : short(r.name)).split("/").forEach((bit, i) => name.append(...(i ? ["/", document.createElement("wbr")] : []), bit));
    if (r.note && !mark) { // another task's: after its name
      const note = document.createElement("span");
      note.className = "tr-note";
      note.textContent = r.note;
      name.append(" ", note);
    }
  };
  // its own files, then what it wrote outside them (as its card says it, in the came-back red); the rest of the
  // repository, which it may not change, folded under one line
  for (const r of rows.filter((x) => x.kind === "in")) line(r, tree);
  for (const f of t.outside) line({ name: f, kind: "bad", depth: 0, note: "outside its files" }, tree);
  const rest = rows.filter((x) => x.kind !== "in" && !t.outside.includes(x.name));
  if (!tree.childElementCount) div("tr out", "no files named", tree);
  if (rest.length) {
    const fold = document.createElement("details");
    fold.className = "rest";
    fold.open = restOpen; // kept open through a rebuild while a run writes the store
    fold.addEventListener("toggle", () => { restOpen = fold.open; });
    const sum = document.createElement("summary");
    sum.textContent = `The rest of the repository (${rest.length})`;
    fold.appendChild(sum);
    for (const r of rest) line(r, fold);
    tree.appendChild(fold);
  }
  if (t.scope.length) { // the glob is the plan's own word for it: shown when asked
    const glob = document.createElement("details");
    glob.className = "glob";
    const sum = document.createElement("summary");
    sum.textContent = "Paths as the plan wrote them";
    glob.appendChild(sum);
    for (const g of t.scope) code(g, glob);
    change.appendChild(glob);
  }
  // what decides Approve, Accept or Help it, next to the files: the rest is the same on most tasks
  const when = part(body, "Done when");
  const check = t.check ? code(t.check, div("", undefined, when)) : null;
  if (check && t.check!.length > 120) { // three --tests: four lines until asked, hidden from the eye alone, so a copy is whole
    const more = document.createElement("button");
    more.className = "more-link";
    const show = () => { check.classList.toggle("clamp", !wholeCheck); more.textContent = wholeCheck ? "less" : "the whole check"; more.setAttribute("aria-expanded", String(wholeCheck)); };
    more.addEventListener("click", () => { wholeCheck = !wholeCheck; show(); });
    show();
    when.appendChild(more);
    // ponytail: measured as the pane is built; a tab resized after keeps its link until the pane is next drawn
    if (!wholeCheck && check.scrollHeight <= check.clientHeight) more.remove(); // its four lines hold it all here
  }
  for (const c of checkLines(t)) { // the verdict after the work only where it stands, as the card's box wears it
    const row = div("checkrow", undefined, when);
    div(`dot ${c.tone}`, undefined, row);
    row.append(c.line);
  }
  if (t.hollow && t.checked.before !== "passes") div("checkrow warn", "its check passed before the work too: it proves nothing new", when);
  const run = part(body, "May run");
  const kv = div("kv", undefined, run);
  div("kv-k", "Commands", kv);
  const cmds = div("kv-v", undefined, kv);
  const may = mayRun(s, t);
  for (const c of may.commands) code(c, cmds);
  if (may.words) cmds.append(may.words);
  if (may.note) { // the check it cannot run, and where that is set: a flag in it as code
    const note = div("kv-note", undefined, cmds);
    may.note.split("`").forEach((bit, i) => (i % 2 ? code(bit, note) : note.append(bit)));
  }
  div("kv-k", "Outside", kv);
  div("kv-v", may.outside, kv);
  const held = heldWords(t);
  const hold = div(`held${held.shield ? "" : " none"}`, undefined, part(body, "Held by"));
  div("shield", held.shield ? "⛉" : "○", hold).setAttribute("aria-hidden", "true");
  const said = div("", held.line, hold);
  small(held.proof, said);
  // Stopped only where a write could be refused (a task nothing holds has nothing to refuse, one no agent has
  // been on has written nothing), and never as all clear under a write outside its files
  const stops = stopsOf(t, s.tasks);
  if (stops.rows.length || (held.shield && t.agent && !t.outside.length)) {
    const stopped = part(body, "Stopped", stops.rows.length ? stops.count : ""); // no count of nothing
    for (const x of stops.rows) small(x.note, div("stop", x.line, stopped));
    if (!stops.rows.length) div("dim", "no write was refused", stopped);
  }
  const spent = tokenWords(t);
  if (!spent) return; // nothing metered: no part to say so
  const tokens = part(body, "Tokens", spent.total);
  const bar = div("bar", undefined, tokens);
  div("read", undefined, bar).style.width = `${spent.read}%`;
  div("wrote", undefined, bar).style.width = `${spent.written}%`;
  div("checkrow dim", spent.line, tokens);
}

/** Scope, for a command step: no agent and no file. Its exit code, what runs, and whether it leaves this machine. */
function commandScope(body: HTMLElement, t: TaskX) {
  div("dim", "nothing: a command task changes no file of the repository", part(body, "May change"));
  const when = part(body, "Done when");
  const row = (tone: string, line: string) => { const r = div("checkrow", undefined, when); div(`dot ${tone}`, undefined, r); r.append(line); };
  row("dim", "its exit code is its check: 0 and it is done");
  const c = checkMark(t); // its exit, as its card's box says it: no line where that says nothing
  if (c.words) row(c.tone, c.words);
  const kv = div("kv", undefined, part(body, "May run"));
  div("kv-k", "Command", kv);
  const cmd = div("kv-v", undefined, kv);
  code(t.command ?? "", cmd).title = t.command ?? "";
  div("kv-note", "Graphene runs it itself, with no agent, in a clean copy.", cmd);
  div("kv-k", "Outside", kv);
  div("kv-v", t.leaves ? "it leaves your machine: it pushes or opens a pull request, and asks you first"
    : "nothing Graphene knows of: only a git push or a gh pr is read as leaving your machine", kv);
  const hold = div("held none", undefined, part(body, "Held by"));
  div("shield", "○", hold).setAttribute("aria-hidden", "true");
  small("What it writes in its clean copy is thrown away.", div("", "No agent writes here: there is nothing to hold.", hold));
}

/** Edit: the task's form (or, finished, a command step or in a replay, what it says), the sub-goal it is under and what it waits on. */
function editTab(body: HTMLElement, t: TaskX, s: StateX) {
  if (editable(t, replaying())) form(body, t, s);
  else { // a finished task, a command step, or a replay: read (what it is for is the head's), and the line says why
    row("May change", t.scope.join("\n"), body, true);
    row(t.command ? "Runs" : "Done when", t.command ?? t.check ?? "", body, true);
    if (!replaying()) div("when", whenEdit(t), body);
  }
  row("Under", t.parent ? bandName(goalTitle(s, t.parent)).whole : "", body); // without the plan text's `? `, as its band
  if (t.hollow) div("hollow", provesNothing(t) ? PROVES_NOTHING : "its check passed before the work too: it proves nothing new", body); // as the cockpit says
  if (t.needs.length) { // what it waits on, each with the × that stops it waiting
    const r = div("row", undefined, body);
    div("k", "After", r);
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
}

/** Activity (who is on it is the head's): an agent's try before it was open again, what it cost, what it said, what
 *  it changed and its check's verdict (Home's card for a task to review or done), its last moves, and each attempt
 *  with its changes. */
function activityTab(body: HTMLElement, t: TaskX) {
  const before = body.childElementCount;
  row("Earlier", earlier(t), body);
  row("Tries", t.attempts !== undefined && t.attempts > 1 ? String(t.attempts) : "", body);
  row("Cost", usd(t.usd), body);
  row("Quiet", t.idle !== null && t.idle > 8 ? `${Math.round(t.idle)} s` : "", body);
  row("Note", t.note !== t.why ? t.note : "", body); // why it needs help is the pane's red line already
  row("Changed", t.changed.join("\n"), body, true); // a path a line: two on one would break into three names
  // the verdict after the work only where it stands, as the card's box wears it; a command step's, its exit
  const c = t.command ? checkMark(t) : null, after = c ? { tone: c.tone, line: c.words } : checkLines(t)[1];
  row("Check", after && after.tone !== "dim" ? after.line : "", body);
  if (after?.tone === "ok" && t.hollow) div("hollow", provesNothing(t) ? PROVES_NOTHING : "its check passed before the work too: it proves nothing new", body); // as Edit says it
  row("Wrote outside", t.outside.join("\n"), body, true); // as Scope says it, in red
  if (t.forks.length) {
    const r = div("row", undefined, body);
    div("k", "Attempts", r);
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
    div("k", "Last moves", r);
    const v = div("v mono", undefined, r); // an agent's moves are its tools on paths and commands
    for (const line of t.tail.slice(-6)) div("move", screenWords(line), v);
  }
  if (body.childElementCount === before) div("dim", t.state === "done" ? "Done, with no moves recorded." : t.agent ? "Nothing reported yet." : "No agent has been on it yet.", body);
}

/** The pane is rebuilt only when what it shows changed (its key); then the focused button, by its words,
 *  and the scroll are kept, so a keyboard user reaches its buttons while a run writes the store. A box being
 *  typed in is never rebuilt under the typing: the pane waits for it to be left. */
function pane() {
  const pane = $("details");
  const d = drawn().find((x) => x.key === selected);
  const shown = state?.tasks.find((x) => x.id === selected);
  const scoped = shown && state && tab() === "scope" ? JSON.stringify([scopeTree(shown, state), stopsOf(shown, state.tasks).count, state.allows]) : "";
  const key = d ? JSON.stringify([d, offered.has(d.key)])
    : state ? paneKey(state, selected, replaying()) + (refused.get(selected ?? "") ?? "") + state.envelope.forks + tab() + scoped + seen.has(selected ?? "") : "";
  if (key === paneLast) return;
  const at = document.activeElement as HTMLInputElement | null;
  if (paneOf === selected && pressing) { paneLast = "stale"; return; } // rebuilt once the press has had its click
  if (paneOf === selected && at && pane.contains(at) && at.tagName === "INPUT" && at.type === "text") {
    paneLast = "stale"; // rebuilt once the box is left; a draft's own line is said now, as its box says its blanks
    const when = d ? pane.querySelector(".when") : null;
    if (d && when) when.textContent = offered.has(d.key) && !d.said ? "Graphene is asked to take it…" : draftLine(d);
    return;
  }
  paneLast = key;
  if (selected !== paneOf) menuOf = null; // another task, or none (× and Esc hide the pane with no event): its … starts closed
  paneOf = selected;
  const t = state?.tasks.find((x) => x.id === selected);
  if (!state || (!t && !d) || !key) { pane.hidden = true; pane.replaceChildren(); return; }
  const was = pane.contains(document.activeElement) ? document.activeElement : null;
  const mark = (e: Element) => `${e.id}|${(e as HTMLElement).dataset?.tab ?? e.className}|${e.textContent}|${e.getAttribute("aria-label") ?? ""}`; // a tab by its name: its class changes when chosen
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
  // the head: what it is, its state and who is on it (or, nobody on it yet, who it is for); the id, the CLI's
  // word for it, on the title's hover
  const head = div("d-head", undefined, pane);
  div(`d-title ${cls(t.state)}`, t.title, head).title = `${t.full || t.title} (${t.id})`;
  const what = whatFor(t); // past its title, as a suggestion's card says it
  if (what) div("d-for", what, head).title = what;
  const meta = div("d-id", undefined, head);
  div("d-state", SAY[t.state], meta);
  const w = who(t, s.executor);
  const on = t.agent && !["proposed", "ready", "waiting"].includes(t.state); // one that tried it before it was open again is Activity's
  meta.append(` · ${on ? `agent ${t.agent}${t.model ? ` · ${t.model}` : ""}` : w.kind === "you" || t.command ? w.label : `for ${w.label}`}`);
  // one act is the pane's to offer at its foot (the state's own; the looks at its work, and to review the verdicts
  // that are not the act now, beside them; a suggestion's Remove, Home's ×); the rest wait in the …, Compare too once
  // an attempt is kept (the race is settled), and Send back… once the work landed: a finished task's foot only looks
  const all = actsFor(t, replaying(), seen.has(t.id));
  const inFoot = (b: Button) => b.main || ["openDiff", "signOff"].includes(b.act) || (b.act === "sendBack" && t.state === "review")
    || (b.act === "drop" && t.state === "proposed") || (b.act === "compareForks" && !t.kept);
  const tools = div("d-tools", undefined, head);
  paneMenu(tools, t.id, all.filter((b) => !inFoot(b)));
  closer(tools);
  const body = div("d-body", undefined, pane);
  if (t.state === "came back" && t.why) div("why", screenWords(t.why), body);
  const q = questionOn(s, t.id);
  if (q) { // its question, with the options to answer inline
    const ask = div("ask", undefined, body);
    div("ask-text", q.text, ask);
    if (q.default && replaying()) div("ask-if", `If unanswered: ${q.default}`, ask); // no answers to wear it
    if (!replaying()) { // every answer quiet: the default filled would read as already chosen, so it says so on itself
      const opts = div("ask-opts", undefined, ask);
      const options = [...new Set([...(q.default ? [q.default] : []), ...q.options])];
      for (const o of options) {
        const b = document.createElement("button");
        b.className = "quiet";
        const words = div("", o, b);
        if (o === q.default) div("dim", "if unanswered", words); // the default says so under its words
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
  // three tabs: what it may do (the pane opens here), its form, and what its agents did
  const tabs = div("tabs", undefined, body);
  tabs.setAttribute("role", "tablist");
  for (const [key, label] of [["scope", "Scope"], ["edit", "Edit"], ["activity", "Activity"]] as const) {
    const b = document.createElement("button");
    b.className = `tab${tab() === key ? " on" : ""}`;
    b.textContent = label;
    b.dataset.tab = key;
    b.setAttribute("role", "tab");
    b.setAttribute("aria-selected", String(tab() === key));
    b.addEventListener("click", () => { remember({ tab: key }); paneLast = ""; pane_(); });
    tabs.appendChild(b);
  }
  if (tab() === "scope") scopeTab(body, t, s);
  else if (tab() === "edit") editTab(body, t, s);
  else activityTab(body, t);
  const foot = all.filter(inFoot);
  if (foot.length) { // Compare, in a word, so the quiet ones fit one row under the act; its hover says it whole
    const acts = div("d-acts", undefined, pane);
    for (const b of foot) button(b.act === "compareForks" && !b.main ? { ...b, label: "Compare", title: `Compare attempts: ${b.title}` } : b, t.id, acts);
  }
}

let menuOf: string | null = null; // the task whose … is open: open again when its pane is rebuilt under it

/** The pane's …: the acts a person reaches for less (add a task beside it, link, message its agent, remove),
 *  as a menu by the close. A popover, so a click outside or Esc closes it, and the focus goes back to the …. */
function paneMenu(tools: HTMLElement, id: string, acts: Button[]) {
  if (!acts.length) return;
  const more = document.createElement("button");
  more.className = "close more";
  more.appendChild(icon("ellipsis"));
  more.title = "more";
  more.setAttribute("aria-label", "more acts");
  more.setAttribute("aria-haspopup", "menu");
  const menu = div("d-menu", undefined, tools);
  menu.popover = "auto";
  menu.setAttribute("role", "menu");
  more.popoverTargetElement = menu;
  // Message agent and a landed task's Send back… apart (the menu opens on neither), Remove last, as the editor's own menus set them
  const late = (b: Button) => (b.act === "drop" ? 2 : b.act === "tell" || b.act === "sendBack" ? 1 : 0);
  let was = 0;
  for (const b of [...acts].sort((x, y) => late(x) - late(y))) {
    if (late(b) && !was && menu.childElementCount) div("d-sep", undefined, menu).setAttribute("role", "separator");
    was = late(b);
    const item = document.createElement("button");
    item.setAttribute("role", "menuitem");
    if (b.act === "drop") item.className = "danger";
    if (b.icon) item.appendChild(icon(b.icon));
    item.append(b.label);
    item.title = b.title;
    item.addEventListener("click", () => { menu.hidePopover(); press(b, id); });
    menu.appendChild(item);
  }
  menu.addEventListener("beforetoggle", (e) => {
    // closed by the person: this fires at once, while the menu is still here; a rebuild takes it away with no event
    if ((e as ToggleEvent).newState !== "open") { menuOf = null; return; }
    const r = more.getBoundingClientRect(); // under the …, its right edge on the …'s
    menu.style.top = `${r.bottom + 4}px`;
    menu.style.right = `${Math.max(8, innerWidth - r.right)}px`;
    // narrow, the whole pane scrolls and would leave it behind: it closes, as the editor's own menus do
    $("details").addEventListener("scroll", () => menu.hidePopover(), { once: true, passive: true });
  });
  menu.addEventListener("toggle", (e) => {
    if ((e as ToggleEvent).newState !== "open") return;
    if (menuOf !== id) menu.querySelector("button")?.focus(); // opened by the person, not again after a rebuild
    menuOf = id;
  });
  menu.addEventListener("keydown", (e) => {
    if (e.key === "Escape") { e.stopPropagation(); return; } // the menu's Esc, not the pane's
    const step = e.key === "ArrowDown" ? 1 : e.key === "ArrowUp" ? -1 : 0;
    if (!step) return;
    e.preventDefault();
    e.stopPropagation(); // the arrows walk the menu, not the cards
    const items = Array.from(menu.querySelectorAll("button")), at = items.indexOf(document.activeElement as HTMLButtonElement);
    items[(at + step + items.length) % items.length]?.focus();
  });
  tools.appendChild(more);
  if (menuOf === id) menu.showPopover();
}

let helpFrom: Element | null = null; // where the focus was when ? opened: it goes back there on Esc

/** The keys and the mouse, as a dialog: the focus moves into it and returns on Esc. */
function help(show: boolean) {
  const h = $("help");
  h.hidden = !show;
  if (!show) { (helpFrom as HTMLElement | null)?.focus?.({ preventScroll: true }); helpFrom = null; return; }
  helpFrom = document.activeElement;
  if (!h.childElementCount) {
    h.setAttribute("role", "dialog");
    h.setAttribute("aria-modal", "true");
    h.setAttribute("aria-label", "Keys and mouse");
    const card = div("help-card", undefined, h);
    card.tabIndex = -1;
    const head = div("help-head", undefined, card);
    div("help-title", "Keys and mouse", head);
    const close = head.appendChild(document.createElement("button"));
    close.className = "close"; // as the pane's ×: a backdrop click and Esc close it too
    close.appendChild(icon("close"));
    close.title = "Close (Esc)";
    close.setAttribute("aria-label", "Close");
    close.addEventListener("click", () => help(false));
    const table = div("help-rows", undefined, card);
    for (const [key, what] of KEYS) {
      div(/^[a-z]{4}/.test(key) ? "help-key gesture" : "help-key", key, table); // a gesture is words (drag a dot), not a key's name
      div("help-what", what, table);
    }
  }
  (h.firstElementChild as HTMLElement).focus({ preventScroll: true });
}

function notice(st: Status) {
  const n = $("notice");
  n.hidden = false;
  n.textContent = st.text;
  n.className = st.kind;
  for (const id of ["regions", "bands", "edges", "gates", "heads", "tasks", "goalg"]) ($(id) as unknown as SVGGElement).replaceChildren();
  taskEls.clear(); edgeEls.clear(); goalKey = "";
  $("lanes").replaceChildren(); laneEls.clear(); lanesKey = "";
  $("minimap").hidden = $("legend").hidden = $("need").hidden = true;
  $("details").hidden = true; paneLast = "";
  $("goal").textContent = "Graphene";
  $("auto").hidden = true;
  $("replay").hidden = true;
  $("pipe").hidden = true; // no plan to read: no stage to be at, and nothing to run or add to
  for (const [id] of HEADER_ACTS) $(id).hidden = true;
  $("zoom").style.display = "none";
  $("hint").hidden = true;
  $("planning").hidden = true;
}

// ---- messages and keys ----

window.addEventListener("message", (e: MessageEvent<Incoming>) => {
  const m = e.data;
  if (!m || typeof m !== "object") return;
  if (m.type === "state") {
    const json = JSON.stringify([m.state, m.exact === true, m.seen]);
    if (json === lastJson) return; // nothing changed: nothing moves
    lastJson = json;
    state = m.state;
    exact = m.exact === true;
    seen = new Set(m.seen ?? []);
    const has = (id: string | null) => state!.tasks.some((t) => t.id === id);
    if (arriving && has(arriving)) { selected = arriving; arriving = null; }
    if (selected && !has(selected) && !isDraft(selected)) selected = null;
    if (linking && !has(linking)) linking = null;
    for (const d of [...drafts]) { // what a draft was drawn after, or under, may have gone
      if (d.after && !has(d.after)) d.after = null;
      if (d.parent && !state.goals.some((g) => g.id === d.parent)) d.parent = null;
      // whole, and not offered that this page remembers (it was reloaded before the answer came): the plan has
      // it already, or it is offered now
      if (lacks(d).length || offered.has(d.key) || d.said) continue;
      const files = globs(d.files).join(" ");
      if (state.tasks.some((t) => (t.full || t.title) === d.title && t.scope.join(" ") === files)) discard(d.key); else redraw(d.key, {});
    }
    render();
  } else if (m.type === "drafts") {
    drafts = m.drafts;
    sentDrafts.clear();
    for (const d of drafts) sentDrafts.set(d.key, JSON.stringify(d));
    if (selected === null && drafts.length) selected = drafts[0]!.key;
    paneLast = "";
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
    state = null; // no plan to read: the one that was here is not drawn again when the canvas resizes under the notice
    notice(m.status);
  } else if (m.type === "start") { // no run was started (an accept refused, an answer held it): Start again
    if (!m.ok) { startedAt = 0; if (state) render(); }
  } else if (m.type === "shown") { // drawn again once in front, at its own size: hidden, Cursor said 260 px, the lanes'
    shown = m.on;
    if (shown) requestAnimationFrame(() => {
      const c = chosen;
      chosen = null;
      if (c) select(c.id, c.focus); else if (state) render(); // brought on screen at its own size, not the hidden 260 px
    });
  } else if (m.type === "select") { // a click in the Plan view: the link, if armed, is not for that task
    disarm();
    fitRoom = ""; // chosen from outside the page, as it is when the page opens on a task: the plan is fitted beside its pane
    if (shown) select(m.id, m.focus !== false); else chosen = { id: m.id, focus: m.focus !== false };
  }
});

window.addEventListener("keydown", (e) => {
  if ((e.target as HTMLElement).tagName === "BUTTON" && (e.key === "Enter" || e.key === " ")) return;
  if ((e.target as HTMLElement).tagName === "INPUT" && e.key !== "Escape") return; // a tick box: Space is its own
  if (e.key === "Escape") {
    if (!$("help").hidden) help(false);
    else if (asking) { asking = false; $("b-ask").focus(); }
    else if (wiring || linking) disarm();
    else selected = null;
    render();
    return;
  }
  if (e.key === "?") { help($("help").hidden); return; }
  if (e.metaKey || e.ctrlKey || e.altKey) return;
  if (e.key === "g" && state) { // the goal, on screen
    if (view() === "lanes") $("lanes").querySelector(".goal-row")?.scrollIntoView({ block: "nearest" });
    else reveal(GOAL);
    return;
  }
  if (e.key === "+" && state) { // a task drawn after the selected one, or on its own
    const near = state.tasks.find((t) => t.id === selected);
    if (near?.leaves) return; // nothing is drawn after a step past the line
    e.preventDefault(); // the key draws the task: it is not then typed into the title its box opens with
    draw(near ? { after: near.id, parent: near.parent } : { after: null, parent: null });
    return;
  }
  if (e.key === "f") return refit();
  if (e.key === "n") return showNext();
  if (view() !== "lanes" && (e.key === "-" || e.key === "=" || e.key === "0")) { // out, in, and back to 100%
    return e.key === "0" ? actual() : nudge(e.key === "-" ? 0.8 : 1.25);
  }
  if (e.key === "v") { remember({ view: view() === "lanes" ? "graph" : "lanes" }); fitted = false; render(); return; }
  const keys: Record<string, "left" | "right" | "up" | "down"> = { ArrowLeft: "left", ArrowRight: "right", ArrowUp: "up", ArrowDown: "down" };
  const dir = keys[e.key];
  if (!dir || !state) return;
  e.preventDefault();
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
  // the arrows walk the cards a person can act on: one the planner is still writing is watched, not selected
  const next = step({ ...lay, boxes: Object.fromEntries(Object.entries(lay.boxes).filter(([id]) => !id.startsWith(PLAN))) }, from, dir);
  if (next === GOAL) { goalG.focus({ preventScroll: true }); reveal(GOAL, true); return; } // the goal is not a task: focused, not selected
  if (next) select(next, true);
});

function wire() {
  wearInk(); // a filled button's words in a colour that reads on it (ink.ts)
  const canvas = $("canvas");
  canvas.addEventListener("wheel", (e) => {
    if (view() === "lanes") return; // the rows scroll as a list does
    e.preventDefault();
    if (e.ctrlKey || e.metaKey) { // a pinch, or the wheel with the modifier: zoom about the pointer
      const rect = canvas.getBoundingClientRect();
      return zoomAt(wheelK(zoom.k, e.deltaY), e.clientX - rect.left, e.clientY - rect.top);
    }
    zoom = clamp({ ...zoom, tx: zoom.tx - e.deltaX, ty: zoom.ty - e.deltaY }); // the wheel scrolls, as a page does
    moved = true;
    applyZoom();
  }, { passive: false });
  let drag: { x: number; y: number; tx: number; ty: number } | null = null;
  canvas.addEventListener("mousedown", (e) => {
    if (view() === "lanes") return;
    const port = (e.target as Element).closest("[data-port]");
    if (port && !replaying()) { // a drag from a task's dot draws a link
      e.preventDefault();
      wiring = { from: port.getAttribute("data-port")!, ...at(e) };
      canvas.classList.add("wiring");
      render();
      return;
    }
    if ((e.target as Element).closest(".task, .goal, #zoom, #minimap, button")) return;
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
      const target = document.elementFromPoint(e.clientX, e.clientY)?.closest(".task:not(.drafted)")?.getAttribute("data-id"); // a card the planner is still writing takes no link
      wiring = null;
      canvas.classList.remove("wiring");
      if (target && target !== from) {
        if (isDraft(target)) redraw(target, { after: from });
        else api.postMessage({ type: "act", act: "link", id: from, target });
        select(target);
      } else render();
      return;
    }
    drag = null;
    canvas.classList.remove("dragging");
  });
  // a double click on a card is heard wherever its second click lands: the pane its first click opened may be
  // under the pointer by then (beside the canvas, or under a narrow one). That click presses nothing there, takes
  // no focus and selects no word; a row opens: whole cards, that one in the middle
  const second = (e: MouseEvent) => e.detail > 1 && tapped !== null;
  window.addEventListener("mousedown", (e) => { if (second(e)) e.preventDefault(); }, true);
  window.addEventListener("click", (e) => {
    if (!second(e)) { tapped = null; return; } // any other click: the card's own handler says so if it chose one
    e.preventDefault();
    e.stopPropagation();
    if (level === "compact" && lay?.boxes[tapped!]) detail(tapped!);
  }, true);
  canvas.addEventListener("dblclick", (e) => {
    const on = e.target as Element;
    if (tapped || on.closest(".lane, #zoom, #minimap, button")) return; // a chosen card's: its second click opened it; a chip's two clicks are its own
    // a card no click chooses (the goal, a step the planner is writing) opens as a row does; the canvas fits the plan again
    const card = on.closest(".task, .goal");
    if (!card) refit(); else if (level === "compact") detail(card.getAttribute("data-id") ?? GOAL);
  });
  // Tab onto a card out of view pans it in, as choosing it does: the canvas itself never scrolls (graph.css). A
  // press is no keyboard's focus, so no card moves from under the pointer; nor is a card that kept its focus
  // through a redraw brought back from where a hand left it
  $("svg").addEventListener("focusin", (e) => {
    const on = e.target as Element;
    if (!painting && on.matches(":focus-visible")) reveal(on.closest(".task")?.getAttribute("data-id") ?? GOAL, true);
  });
  // the canvas narrows with the window, and with the details pane opening beside it: a narrow tab turns to
  // lanes or lays the graph downward (`tabMode`); the drawing says which of the two it was, and fits the plan
  // again for the window alone (`graph`)
  new ResizeObserver(() => { if (state) render(); }).observe(canvas);
  $("help").addEventListener("click", (e) => { if (e.target === $("help")) help(false); });
  // a press in the pane keeps the pane it pressed: a box left by that press is rebuilt after the click, not under it
  $("details").addEventListener("pointerdown", () => { pressing = true; });
  const released = () => {
    if (pressing) setTimeout(() => { pressing = false; if (paneLast === "stale") pane(); }, 0);
    if (held) { held = false; setTimeout(render, 0); } // the card the press kept as it was: drawn now, after its click
  };
  window.addEventListener("pointerup", released);
  window.addEventListener("pointercancel", released);
  window.addEventListener("pointermove", (e) => { if (e.buttons === 0) released(); }); // let go outside the page
  // what the canvas gains over the shell (the preview's is the same shell): the regions under the drawing, the
  // zoom's buttons at its foot, and the legend
  $("view").prepend(el("g", { id: "regions" }));
  $("edges").after(el("g", { id: "gates" }), el("g", { id: "heads" })); // on the line, over the edges that cross it; and the sub-goals' headers
  const zooms = div("", undefined, canvas);
  zooms.id = "zoom";
  for (const [id, label, sign, title, on] of [["zoom-fit", "fit the graph", icon("screen-full"), "fit the whole plan in the pane (f)", refit],
                                              ["zoom-out", "zoom out", "−", "zoom out (-, or ⌘ or Ctrl with the wheel)", () => nudge(0.8)],
                                              ["zoom-pct", "", "100%", "how big a card is drawn: click for 100%, whole cards at their own size (0)", actual],
                                              ["zoom-in", "zoom in", "+", "zoom in (=, or ⌘ or Ctrl with the wheel)", () => nudge(1.25)]] as const) {
    const b = document.createElement("button");
    b.id = id;
    b.className = "quiet";
    b.append(sign);
    b.title = title;
    if (label) b.setAttribute("aria-label", label);
    b.addEventListener("click", on);
    zooms.appendChild(b);
  }
  // the minimap, over the legend: shown while part of the plan is off screen; a click or a drag in it pans there
  const map = div("", undefined, canvas);
  map.id = "minimap";
  map.hidden = true;
  map.setAttribute("aria-hidden", "true"); // the plan is all there for a reader: Tab and the arrows walk it
  const mapSvg = map.appendChild(el("svg"));
  const panned = (e: PointerEvent) => {
    if (!lay) return;
    const r = mapSvg.getBoundingClientRect();
    zoom = clamp(panTo(((e.clientX - r.left) / r.width) * lay.width, ((e.clientY - r.top) / r.height) * lay.height, zoom.k, paneSize()));
    moved = true;
    applyZoom();
  };
  map.addEventListener("pointerdown", (e) => { e.preventDefault(); map.setPointerCapture(e.pointerId); panned(e); });
  map.addEventListener("pointermove", (e) => { if (e.buttons & 1) panned(e); });
  map.addEventListener("mouseleave", () => idle(map));
  const planning = div("", undefined, canvas); // while a planner writes: how many steps it has drawn so far
  planning.id = "planning";
  planning.hidden = true;
  planning.setAttribute("role", "status");
  const key = div("", undefined, canvas); // filled by `legendRow`
  key.id = "legend";
  key.setAttribute("aria-hidden", "true"); // each card says its state in words
  // what needs you (`chips`): the tasks, then the plan's questions and the card of the first. The header's, at the
  // right of the stages (graph.css): over the canvas it stood on cards whenever the canvas was short or a pane open
  const need = div("", undefined, document.querySelector("header")!);
  need.id = "need";
  need.hidden = true;
  const chip = (id: string, title: string, on: () => void) => {
    const b = need.appendChild(document.createElement("button"));
    b.id = id;
    b.className = "quiet";
    b.title = title;
    b.addEventListener("click", on);
    return b;
  };
  const next = chip("b-next", "select the next task that needs you, and bring it on screen (n)", showNext);
  mark(next.appendChild(el("svg", { width: 14, height: 14, viewBox: "-7 -7 14 14" })), "you", 0, 0, 6.5);
  next.append(document.createElement("b"), document.createElement("span"));
  const ask = chip("b-ask", "the plan's open question: its answers", () => {
    asking = !asking;
    render();
    if (asking) $("asked").querySelector("button")?.focus();
  });
  ask.append(icon("question"), document.createElement("b"), document.createElement("span"));
  const card = div("", undefined, need);
  card.id = "asked";
  card.hidden = true;
  card.setAttribute("role", "dialog");
  card.setAttribute("aria-label", "the plan's question");
  // a press anywhere else puts the card away, as a menu goes
  window.addEventListener("pointerdown", (e) => { if (asking && !need.contains(e.target as Node)) { asking = false; render(); } });
  // the header's buttons: the rare ones an icon each (their hover names them), Save as workflow (an icon too in a
  // narrower tab), Add task, and last the one act on the whole plan (`header` says which); none bordered but that
  // one, which fills when it starts something
  const actions = $("actions");
  const top = (id: string, label: string, ico: string, title: string, on: () => void) => {
    const b = actions.appendChild(document.createElement("button"));
    b.id = id;
    b.className = "quiet";
    b.append(icon(ico));
    if (label) b.appendChild(document.createElement("span")).append(label); // a tab too narrow for it shows the icon alone (graph.css)
    b.title = title;
    b.addEventListener("click", on);
    // a name where no words show: an icon, or words a tab too narrow for them hides. The main act is named by
    // its words, which `header` changes (Start, Run, Stop)
    if (id !== "b-run") b.setAttribute("aria-label", label || title.replace(/:.*| \(.*/, ""));
    if (!label) b.classList.add("icon");
  };
  top("b-view", "", "list-flat", "Lanes (v)", () => { remember({ view: view() === "lanes" ? "graph" : "lanes" }); fitted = false; render(); });
  top("b-help", "", "question", "Keys and mouse (?)", () => help($("help").hidden));
  top("b-save", "Save as workflow", "bookmark", "Save as workflow: this graph to workflows/, to run again on new inputs", () => api.postMessage({ type: "act", act: "saveWorkflow", id: "" }));
  top("b-add", "Add task", "add", "draw a task: its title, then its files and its check (or the planner fills them in)", () => draw({ after: null, parent: null }));
  top("b-run", "Run", "play", "", () => {
    const a = state && mainAct(state, exact);
    if (!a || startedAt) return; // Starting…: one run a click
    api.postMessage({ type: "act", act: a.act, id: "" });
    if (a.act === "start" || a.act === "run") { // Starting… until the run is seen (`header`), then drawn again at the wait's end
      startedAt = Date.now();
      setTimeout(() => { if (state) render(); }, START_WAIT + 100);
      render();
    }
  });
  // under the goal: the pipeline's three stages (made here, so the preview's shell has them too). Stop after the
  // plan is Home's, under its Settings: beside Start and Stop here it read as a third way to stop
  const pipe = div("", undefined, document.querySelector("header")!);
  pipe.id = "pipe";
  const stages = div("", undefined, pipe);
  stages.id = "stages";
  stages.setAttribute("role", "list");
  stages.setAttribute("aria-label", "Plan, Run, Review");
  $("hint").setAttribute("aria-live", "polite"); // the news is read out (`hint`): a hand-back, a task to review
  api.postMessage({ type: "ready" });
}

wire();
