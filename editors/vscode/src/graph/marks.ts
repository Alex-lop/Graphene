// The rules behind the graph's cards, pure: which mark a step's state wears, what a band, the goal, the legend
// and the "need you" chip count from those marks, what the check's box at a card's foot says, the files
// chip's latest fact, and the one act a card wears. A mark is drawn only for what a field of the snapshot
// says (state.ts); the words are words.ts's and `SAY`'s. No DOM here, so `node --test` reads them.
import { SAY, type Goal } from "../state.ts";
import { actsFor, asksYou, attemptsOf, checkWords, filesChip, provesNothing, writtenOf, type Button, type ForkX, type TaskX } from "./words.ts";

/** The one mark a step's state wears, the same shape at every size: a circle is the run's own business
 *  (waiting, ready, working, landed, suggested), a diamond is the person (you, yours), a triangle is trouble (back). */
export type Mark = "waiting" | "ready" | "working" | "you" | "yours" | "back" | "landed" | "suggested";

type Stated = Pick<TaskX, "state" | "needs_you" | "leaves">;

/** Loudest first, as the legend lists them. A bar reads landed first, then the same order. */
const LOUD: readonly Mark[] = ["you", "back", "yours", "working", "landed", "ready", "waiting", "suggested"];
const BAR: readonly Mark[] = ["landed", ...LOUD.filter((m) => m !== "landed")];
/** The marks that want the person: the "need you" chip, and a band's words, count these. */
const WANTS: readonly Mark[] = ["you", "yours", "back"];

/** The mark a step wears, first match: landed, came back, suggested, asks you (a step past the line), yours,
 *  to review or `needs_you`, working, ready, waiting. A suggested step is not the person's move though the
 *  snapshot says `needs_you` of it: accepting the plan is one act for them all. A step of the person's own
 *  stays `yours` whatever `needs_you` says: the snapshot says it of every yours step (cockpit/model.py
 *  `needs_you`), so read first it would leave no step to wear the hollow diamond. */
export function stateMark(t: Stated): Mark {
  if (t.state === "done") return "landed";
  if (t.state === "came back") return "back";
  if (t.state === "proposed") return "suggested";
  if (t.state === "yours") return asksYou(t) ? "you" : "yours";
  if (t.state === "review" || t.needs_you) return "you";
  return t.state === "running" ? "working" : t.state === "ready" ? "ready" : "waiting";
}

/** The full card's corner: the state's mark, or none for waiting, ready and suggested (their words and their
 *  border say it). */
export function cornerMark(t: Stated): Mark | "" {
  const m = stateMark(t);
  return m === "waiting" || m === "ready" || m === "suggested" ? "" : m;
}

const WORD: Record<Mark, string> = { waiting: SAY.waiting, ready: SAY.ready, working: SAY.running, you: SAY.review, yours: SAY.yours,
                                     back: SAY["came back"], landed: SAY.done, suggested: SAY.proposed };
const ASKS = "asks you";
/** What the legend says of a hand-drawn draft or a planner's drafted step: no task yet, the same dashed ring. */
export const DRAFT = "a draft";

/** The word a mark says, in the legend and in a label. The filled diamond says `to review`; with the step it
 *  is on, `asks you` when that step is not to review (it is past the line, or the run stopped for the person). */
export const markWord = (mark: Mark, t?: Pick<TaskX, "state">): string => (mark === "you" && t && t.state !== "review" ? ASKS : WORD[mark]);

/** What wants the person, in words, with its mark so the drawing can colour it. */
export interface Want { mark: Mark; text: string }
/** A band's header and the goal's ring: how many landed of how many, that as a portion (0 for none), every
 *  task's mark with landed first and then loudest first (so they read as a bar), and what wants the person. */
export interface Tally { landed: number; total: number; portion: number; marks: Mark[]; wants: Want[] }

/** The count of a band's tasks, or the plan's: `3 of 6`, the ring's portion, the bar of marks, and the words
 *  for what needs the person there (`1 to review`, `1 needs help`, `2 need help`, `1 yours`, `1 asks you`; none when nothing does). */
export function tally(tasks: readonly Stated[]): Tally {
  const own = tasks.map(stateMark);
  const landed = own.filter((m) => m === "landed").length;
  const wants: Want[] = [];
  for (const word of [WORD.you, WORD.back, WORD.yours, ASKS]) {
    const mine = own.filter((m, i) => WANTS.includes(m) && markWord(m, tasks[i]) === word);
    if (mine.length) wants.push({ mark: mine[0]!, text: `${mine.length} ${mine.length > 1 ? word.replace(/^(ask|need)s /, "$1 ") : word}` });
  }
  return { landed, total: tasks.length, portion: tasks.length ? landed / tasks.length : 0,
           marks: [...own].sort((a, b) => BAR.indexOf(a) - BAR.indexOf(b)), wants };
}

/** The steps that want the person (their mark is you, yours or back), by id, in the plan's order. */
export const wanting = (tasks: readonly (Stated & Pick<TaskX, "id">)[]): string[] => tasks.filter((t) => WANTS.includes(stateMark(t))).map((t) => t.id);

/** The step the chip, or the `n` key, shows next: the one after the selected, round again after the last; the
 *  first when none of them is selected. Null when no step wants the person. */
export const nextWanting = (ids: readonly string[], selected: string | null): string | null => ids[(ids.indexOf(selected ?? "") + 1) % ids.length] ?? null;

/** The chip's words: `3 tasks need you · show the next`, `1 task needs you · show it`; nothing for none. It
 *  names what it counts, the steps to act on: the header's `4 need you` (words.ts `counts`) is the engine's
 *  sum, with every suggested step and every open question in it, so the same words would carry two numbers. */
export const wantingLine = (n: number): string => (n > 1 ? `${n} tasks need you · show the next` : n === 1 ? "1 task needs you · show it" : "");

/** The legend's rows, loudest first, only the marks the plan has: the mark, its word, how many. Two words
 *  where its steps say two (`to review / asks you`). ``drafts``: the hand-drawn drafts and the planner's
 *  drafted steps on the canvas, counted with the suggested. */
export function legend(tasks: readonly Stated[], drafts = 0): [Mark, string, number][] {
  return LOUD.map((m): [Mark, string, number] => {
    const mine = tasks.filter((t) => stateMark(t) === m);
    const words = [...new Set(mine.map((t) => markWord(m, t)))].sort((a, b) => Number(a !== WORD[m]) - Number(b !== WORD[m])); // its own word first
    const more = m === "suggested" ? Math.max(0, drafts) : 0;
    return [m, [...words, ...(more ? [DRAFT] : [])].join(" / "), mine.length + more];
  }).filter(([, , n]) => n > 0);
}

/** The goal card's row: a cell a task, grouped by sub-goal, each group a bar (landed first). The groups come
 *  in the bands' own order, which is the order the plan's tasks first name them (layout.ts), and the tasks
 *  under no sub-goal are a group like any other, where the plan first has one: neither first nor last by rule,
 *  so the row reads left to right as the bands read top to bottom. */
export function goalCells(tasks: readonly (Stated & Pick<TaskX, "parent">)[], goals: readonly Pick<Goal, "id" | "title">[]): { id: string; title: string; marks: Mark[] }[] {
  const groups = new Map<string, (Stated & Pick<TaskX, "parent">)[]>();
  for (const t of tasks) groups.set(t.parent ?? "", [...(groups.get(t.parent ?? "") ?? []), t]);
  return [...groups].map(([id, ts]) => ({ id, title: goals.find((g) => g.id === id)?.title ?? id, marks: tally(ts).marks }));
}

// ---- the check: the foot of a full card ----

/** The check's box, a square only Graphene ticks: `approval` (no check: a hollow diamond, no box), `passed`
 *  (filled, ticked), `failed` (filled, crossed), `hollow` (dashed: it proves nothing yet, or could not tell),
 *  `tells` (solid, empty: it fails now, as it should), `unrun` (dotted, empty: no verdict). */
export type Box = "approval" | "passed" | "failed" | "hollow" | "tells" | "unrun";
/** A box, its tone (`plain`: no colour of its own; a check that fails before the work is good news, never
 *  red) and the hover's words: the pane's own Done when lines for the same fields, or none. */
export interface CheckMark { box: Box; tone: "you" | "ok" | "warn" | "red" | "plain" | "dim"; words: string }

type Checked = Pick<TaskX, "check" | "checked" | "state" | "hollow"> & { command?: string | null; leaves?: boolean };
/** Its work is not finished: words.ts's one rule for it. */
const unfinished = (t: Pick<TaskX, "state">) => provesNothing({ hollow: true, state: t.state });

/** The verdict after the work, where it is this card's to wear. The snapshot's `after` is the task's last
 *  check row whichever attempt wrote it (state.py `checked`): it outlives a send back, a reopen and a new
 *  start, so the step's own state says whether it stands. A pass that counts puts a step to review or lands
 *  it (plan.finish): on any other step the work it passed on was sent back or reopened, or its done was
 *  refused, and a tick would say proven of work that is not. A fail is the work's as it lies (it came back, it
 *  is the person's own, the person landed it over its check), never an attempt's that is to come or under
 *  way: ready, waiting, suggested, working. A command step has no attempts: its last exit stands until a run
 *  tries it again. */
function standing(t: Checked): "passed" | "failed" | null {
  if (t.checked.after === "passed") return unfinished(t) ? null : "passed";
  return t.checked.after === "failed" && (t.command || !unfinished(t) || t.state === "came back" || t.state === "yours") ? "failed" : null;
}

/** The pane's Done when lines for a step's check: its own table (`checkWords`), read with the verdict after
 *  the work only where it stands, as the box below reads it. */
export const checkLines = (t: Checked) => checkWords({ check: t.check, state: t.state, checked: { before: t.checked.before, after: standing(t) } });

/** What the check's box says, by the snapshot's `checked` and nothing else: a tick or a cross only for a
 *  verdict after the work that still stands (`standing`); else by the verdict before it, hollow, telling or
 *  not run. The box and its words are read off the pane's own table (`checkWords`), so the card and the pane
 *  cannot say two things of one check: a verdict the pane warns of is hollow here, one it has no line for is
 *  no verdict. `hollow` warns: the check passed before the work, by the verdict the snapshot gives (`passes`,
 *  or `landed` on a step landed again on the check it landed with), and `passes` where an older CLI gives
 *  none. That CLI says no verdict at all: the box is dotted, a step not started says it has not run, one at
 *  work says when it runs, and a step that is done or to review says nothing. A command step's command is
 *  its check: its box by its exit. */
export function checkMark(t: Checked): CheckMark {
  const open = unfinished(t), after = standing(t);
  if (t.command) {
    if (after === "passed") return { box: "passed", tone: "ok", words: "it ran, and exited 0" };
    if (after === "failed") return { box: "failed", tone: "red", words: "it ran, and failed" };
    return { box: "unrun", tone: "dim", words: !open ? "" : t.leaves ? "it runs when you approve it" : "it runs once what it waits on has landed" };
  }
  const before = t.checked.before ?? (t.hollow ? "passes" : null);
  const [b, a] = checkWords({ check: t.check, state: t.state, checked: { before, after } });
  if (!a) return { box: "approval", tone: "you", words: b!.line }; // no check: the pane's one line
  const unsaid = checkWords({ check: t.check, state: t.state, checked: { before: null, after: null } })[0]!.line;
  const said = b!.line === unsaid ? "" : b!.line; // what the snapshot said of the code as it was, if anything
  const both = [said, a.line].filter(Boolean).join(" · ");
  if (a.tone === "ok") return { box: "passed", tone: t.hollow || before === "passes" ? "warn" : "ok", words: both };
  if (a.tone === "red") return { box: "failed", tone: "red", words: both };
  if (b!.tone === "warn" && open) return { box: "hollow", tone: "warn", words: said };
  if (b!.tone === "red") return { box: "tells", tone: "plain", words: said };
  return { box: "unrun", tone: "dim", words: said || (!open ? "" : t.state === "running" || t.state === "came back" ? a.line : unsaid) };
}

/** The box on the goal's own check: ticked once the goal itself is done, which the engine says only after that
 *  check passed (plan.py `roll_up`); until then nothing says it ran, and the box is dotted. */
export const goalBox = (g: Pick<Goal, "state">): Box => (g.state === "done" ? "passed" : "unrun");

/** A string cut in its middle with an ellipsis to ``n`` characters, the end kept twice as long as the start:
 *  a check's news is its last words (`uv run…test_cache.py`). Short strings untouched; never longer than ``n``. */
export function midCut(s: string, n: number): string {
  if (s.length <= n) return s;
  if (!(n >= 2)) return n >= 1 ? "…" : "";
  const head = Math.floor((Math.floor(n) - 1) / 3), tail = Math.floor(n) - 1 - head;
  return `${s.slice(0, head).trimEnd()}…${s.slice(s.length - tail).trimStart()}`;
}

/** What follows `done when` on a card's foot: the check, cut in its middle to ``n`` characters; `it exits 0`
 *  for a command step, whose command is its check (its chip names it); nothing for a step with no check. */
export const doneWhen = (t: Pick<TaskX, "check"> & { command?: string | null }, n: number): string => (t.command ? "it exits 0" : midCut(t.check ?? "", n));

// ---- the files chip, and the attempts a step is set to ----

/** The files chip: its glyph (`▤` the files it may change, `✎` those written so far, `✕` a write outside
 *  them), its words, its tone (`back` is the came-back red), and the refused writes (`1 refused`), apart so
 *  they can wear that red beside a chip that does not: drawn after the words, ` · ` between. */
export interface FilesLine { tone: "plain" | "working" | "back"; mark: string; text: string; refused: string }

/** The latest fact about a step's files: what it may change (`filesChip`); while it runs and the snapshot
 *  counts its files, how many it has written (`2 of 4 files`) and how many of its writes were refused; once it
 *  came back for a write outside them, which (`wrote store/repo.py +1`). No words for a step with no files,
 *  nor for a command step, which keeps its `$ command` chip. */
export function filesLine(t: Pick<TaskX, "state" | "scope" | "files" | "filesN" | "touched" | "changed" | "stops" | "outside"> & { command?: string | null }): FilesLine {
  if (t.command) return { tone: "plain", mark: "", text: "", refused: "" };
  if (t.state === "came back" && t.outside.length) return { tone: "back", mark: "✕", text: `wrote ${filesChip(t.outside)}`, refused: "" };
  const wrote = t.state === "running" ? writtenOf(t) : "";
  const refused = t.state === "running" && t.stops.length ? `${t.stops.length} refused` : "";
  if (wrote) return { tone: "working", mark: "✎", text: `${wrote} file${wrote.endsWith(" of 1") ? "" : "s"}`, refused };
  const text = filesChip(t.scope);
  return { tone: "plain", mark: text ? "▤" : "", text, refused: text ? refused : "" };
}

/** `×3` at the status line's end for a step set to two or more attempts that has started none, and has a
 *  check to keep one (without a check it runs as one agent; a command step runs once, with no agent). Real
 *  attempts are chips under the card, and small marks on its row (`forkMark`). */
export function attemptsMark(t: TaskX, limit: number | null | undefined): string {
  const n = attemptsOf(t, limit);
  return n < 2 || t.forks.length || !t.check || t.command || !["proposed", "ready", "waiting"].includes(t.state) ? "" : `×${n}`;
}

/** An attempt's small mark on a row, by its own state and nothing else: working, passed its check (the tick),
 *  ended without passing (`ended`: a crossed ring), or not started. */
export const forkMark = (f: Pick<ForkX, "state">): Mark | "ended" =>
  (f.state === "running" ? "working" : f.state === "passed" ? "landed" : ["gave up", "failed", "ended"].includes(f.state) ? "ended" : "waiting");

// ---- the one act a full card wears ----

/** The one button on a full card, for the step that needs the person: the first main act its pane offers
 *  (`actsFor`), so a click goes through the same command and asks whatever that command asks first: to review
 *  `Approve`, came back `Help it…`, past the line `Approve and run`, a step of your own `Mark done`, at work
 *  with a write stopped `Allow the write…`: every step `wanting` lists wears one. Never Accept: accepting
 *  the plan is one act for every suggested step. None in a replay, which is watched. */
export const cardAct = (t: TaskX, replay: boolean): Button | null => actsFor(t, replay).find((b) => b.main && b.act !== "accept") ?? null;
