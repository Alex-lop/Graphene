// The rules behind the graph's cards, pure: which mark a step's state wears, what a band, the goal, the legend
// and the "need you" chip count from those marks, and what the check's box at a card's foot says. A mark is
// drawn only for what a field of the snapshot says (state.ts); the words are words.ts's and `SAY`'s. No DOM
// here, so `node --test` reads them.
import { SAY, type Goal } from "../state.ts";
import { asksYou, badge, checkWords, fan, filesChip, provesNothing, writtenOf, type TaskX } from "./words.ts";

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
 *  to review or `needs_you`, working, ready, waiting. `badge` (words.ts) decides the corner's four; this names
 *  the rest. A step of the person's own stays `yours` whatever `needs_you` says: the snapshot says it of every
 *  yours step (cockpit/model.py `needs_you`), so read first it would leave no step to wear the hollow diamond. */
export function stateMark(t: Stated): Mark {
  const b = badge(t);
  if (b === "done") return "landed";
  if (b === "back") return "back";
  if (b === "running") return "working";
  if (b === "you") return t.state === "yours" && !asksYou(t) ? "yours" : "you";
  return t.state === "proposed" ? "suggested" : t.state === "ready" ? "ready" : "waiting";
}

/** The full card's corner: the state's mark, or none for waiting, ready and suggested (their words and their
 *  border say it). */
export function cornerMark(t: Stated): Mark | "" {
  const m = stateMark(t);
  return m === "waiting" || m === "ready" || m === "suggested" ? "" : m;
}

const WORD: Record<Mark, string> = { waiting: SAY.waiting, ready: SAY.ready, working: SAY.running, you: SAY.review, yours: SAY.yours,
                                     back: "came back", landed: "landed", suggested: SAY.proposed };
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
 *  for what needs the person there (`1 to review`, `1 came back`, `1 yours`, `1 asks you`; none when nothing does). */
export function tally(tasks: readonly Stated[]): Tally {
  const own = tasks.map(stateMark);
  const landed = own.filter((m) => m === "landed").length;
  const wants: Want[] = [];
  for (const word of [WORD.you, WORD.back, WORD.yours, ASKS]) {
    const mine = own.filter((m, i) => WANTS.includes(m) && markWord(m, tasks[i]) === word);
    if (mine.length) wants.push({ mark: mine[0]!, text: `${mine.length} ${word === ASKS && mine.length > 1 ? "ask you" : word}` });
  }
  return { landed, total: tasks.length, portion: tasks.length ? landed / tasks.length : 0,
           marks: [...own].sort((a, b) => BAR.indexOf(a) - BAR.indexOf(b)), wants };
}

/** The steps that want the person (their mark is you, yours or back), by id, in the plan's order. */
export const wanting = (tasks: readonly (Stated & Pick<TaskX, "id">)[]): string[] => tasks.filter((t) => WANTS.includes(stateMark(t))).map((t) => t.id);

/** The step the chip, or the `n` key, shows next: the one after the selected, round again after the last; the
 *  first when none of them is selected. Null when no step wants the person. */
export const nextWanting = (ids: readonly string[], selected: string | null): string | null => ids[(ids.indexOf(selected ?? "") + 1) % ids.length] ?? null;

/** The chip's words: `3 need you · show the next`, `1 needs you · show it`; nothing for none. */
export const wantingLine = (n: number): string => (n > 1 ? `${n} need you · show the next` : n === 1 ? "1 needs you · show it" : "");

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

/** What the check's box says, by the snapshot's `checked` and nothing else: a tick or a cross only for a
 *  verdict after the work; before it, hollow, telling or not run. The box and its words are read off the
 *  pane's own table (`checkWords`), so the card and the pane cannot say two things of one check: a verdict
 *  the pane warns of is hollow here, one it has no line for is no verdict. `hollow` is the cockpit saying
 *  the check passed before the work, the same verdict as `before: passes`. An older CLI says no verdict at
 *  all: the box is dotted, a step not started says it has not run, one at work says when it runs, and a
 *  step that is done or to review says nothing. A command step's command is its check: its box by its exit. */
export function checkMark(t: Checked): CheckMark {
  const open = provesNothing({ hollow: true, state: t.state }); // its work is not finished: words.ts's one rule for it
  if (t.command) {
    if (t.checked.after === "passed") return { box: "passed", tone: "ok", words: "it ran, and exited 0" };
    if (t.checked.after === "failed") return { box: "failed", tone: "red", words: "it ran, and failed" };
    return { box: "unrun", tone: "dim", words: !open ? "" : t.leaves ? "it runs when you approve it" : "it runs once what it waits on has landed" };
  }
  const before = t.hollow ? "passes" : t.checked.before;
  const [b, a] = checkWords({ check: t.check, state: t.state, checked: { before, after: t.checked.after } });
  if (!a) return { box: "approval", tone: "you", words: b!.line }; // no check: the pane's one line
  const unsaid = checkWords({ check: t.check, state: t.state, checked: { before: null, after: null } })[0]!.line;
  const said = b!.line === unsaid ? "" : b!.line; // what the snapshot said of the code as it was, if anything
  const both = [said, a.line].filter(Boolean).join(" · ");
  if (a.tone === "ok") return { box: "passed", tone: before === "passes" ? "warn" : "ok", words: both };
  if (a.tone === "red") return { box: "failed", tone: "red", words: both };
  if (b!.tone === "warn" && open) return { box: "hollow", tone: "warn", words: said };
  if (b!.tone === "red") return { box: "tells", tone: "plain", words: said };
  return { box: "unrun", tone: "dim", words: said || (!open ? "" : t.state === "running" || t.state === "came back" ? a.line : unsaid) };
}

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

/** `×3` at the status line's end for a step set to two or more attempts that has started none: exactly when
 *  `fan` hangs its waiting placeholder chips today, which this replaces. Real attempts keep their chips. */
export function attemptsMark(t: TaskX, limit: number | null | undefined): string {
  const n = t.forks.length ? 0 : fan(t, limit).length;
  return n ? `×${n}` : "";
}
