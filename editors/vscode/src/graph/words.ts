// The graph's words, pure: what a box and a fork chip say, what the header says of a replay, which acts a
// task offers, and the keys. No DOM here, so `node --test` reads them.
import type { Layout } from "../layout.ts";
import { autoLine, usd, type Fork, type Kept, type Question, type State, type Task } from "../state.ts";

/** What the snapshot gains tonight (dev/process/editor/CONTRACT.md): read when present, nothing when not. */
export type ForkX = Fork & { attempts?: number; idle?: number | null };
export type TaskX = Omit<Task, "forks"> & { why?: string; attempts?: number; forks: ForkX[] };
export type Replay = { shown: string; day: string; repository: string } | null;
/** `stand_in`: every model call on record went to the scripted stand-in (the snapshot's, since 867c326c). */
export type StateX = Omit<State, "tasks"> & { replay?: Replay; stand_in?: boolean; tasks: TaskX[] };

export type Act = "add-after" | "add-under" | "link" | "unlink" | "edit" | "drop" | "accept" | "tell" | "run" | "stop" | "auto" | "cockpit"
  | "openDiff" | "compareForks" | "pickFork" | "signOff" | "answer" | "handBack";

/** The acts a replay offers none of: they change a plan, or they act outside the replay (the cockpit opens
 *  `graphene watch` in the person's own folder; openDiff and compareForks look the id up in the person's
 *  plan). That is every act: a replay is watched. The host refuses them too (check.ts). */
export const CHANGES: readonly Act[] = ["add-after", "add-under", "link", "unlink", "edit", "drop", "accept", "tell", "run", "stop", "auto",
                                        "cockpit", "openDiff", "compareForks", "pickFork", "signOff", "answer", "handBack"];

/** The header's act buttons, by their element id: each one is hidden in a replay. */
export const HEADER_ACTS: readonly [string, Act][] = [["b-add", "add-under"], ["b-run", "run"], ["b-auto", "auto"], ["b-cockpit", "cockpit"]];

export const cut = (s: string, n: number) => (s.length > n ? s.slice(0, n - 1).trimEnd() + "…" : s);

/** Text cut with an ellipsis to ``max`` px as ``width`` measures it (the drawn text's own length): a guess
 *  from the whole text's width, then a character off at a time until it fits. A few measures, never empty. */
export function fitWidth(s: string, max: number, width: (t: string) => number): string {
  const whole = width(s);
  if (whole <= max) return s;
  let n = Math.max(2, Math.min(s.length, Math.floor((s.length * max) / whole) + 1));
  let out = cut(s, n);
  while (n > 2 && width(out) > max) out = cut(s, --n);
  return out;
}

/** Words joined with ` · `, the last dropped until they fit ``max`` characters; the first always stays. */
export function fitWords(words: string[], max: number): string {
  const parts = words.filter(Boolean);
  while (parts.length > 1 && parts.join(" · ").length > max) parts.pop();
  return parts.join(" · ");
}

export function forkWord(f: Fork): string {
  return f.state || "waiting";
}

/** The zoom's bounds: never under 1, where the smallest text is drawn at its 11 px (pan and scroll show
 *  more, never a shrink past reading), never over 3. */
export const zoomK = (k: number) => (Number.isFinite(k) ? Math.min(3, Math.max(1, k)) : 1);

/** The box's corner: the model while the task runs, cut to about six characters (`Nano`, `claude…`), or the
 *  mark that it needs you. The hover and the pane say the model whole. */
export function cornerWord(t: TaskX): string {
  return t.state === "running" && t.model ? cut(t.model, 7) : t.needs_you ? "◆" : "";
}

const quiet = (idle: number | null | undefined) => (idle !== null && idle !== undefined && idle > 8 ? `${Math.round(idle)} s quiet` : "");
const tries = (n: number | undefined) => (n !== undefined && n > 1 ? `${n} tries` : "");

/** The small line under a box's title: the state first, then what matters for it. A task that came back
 *  says why on the box. */
export function sub(t: TaskX, max = 25): string {
  const parts: string[] = [];
  if (t.state === "running") parts.push(`agent ${t.agent || "?"}`, t.forks.length ? `${t.forks.length} forks` : "running");
  else parts.push(t.state);
  if (t.state === "came back" && t.why) return cut(fitWords([`came back · ${t.why}`, tries(t.attempts), usd(t.usd)], max), max); // the reason, cut, not dropped
  if (t.state === "came back" && t.outside.length) parts.push(`${t.outside.length} outside`);
  if (t.state === "review") parts.push("sign off");
  parts.push(tries(t.attempts), usd(t.usd), t.state === "running" ? quiet(t.idle) : "");
  return fitWords(parts, max);
}

/** A fork's chip: its letter and model, then that it is kept and why (`b ✓ kept: 4 lines against 12`, the
 *  cockpit's words), then as many as fit of its words. While it runs the numbers are the news, so its
 *  lines, seconds quiet and dollars come before the state word (its border says it runs anyway); once it
 *  ended the state word is the news and comes first. The default width is the chip's, 32 mono characters. */
export function forkWords(f: ForkX, kept: Kept | null, max = 32): string {
  const isKept = kept?.letter === f.letter;
  const head = cut(isKept ? `${f.letter} ✓ kept${kept?.why ? `: ${kept.why}` : ""}` : `${f.letter} · ${f.model || forkWord(f)}`, max);
  const word = isKept || !f.model ? "" : forkWord(f);
  const lines = f.lines !== null ? `${f.lines} lines` : "";
  const parts = f.state === "running"
    ? [head, lines, quiet(f.idle), usd(f.usd), tries(f.attempts), word]
    : [head, word, lines, tries(f.attempts), usd(f.usd)];
  return fitWords(parts, max);
}

/** A fork's row in the details pane: everything, in one line. */
export function forkRow(f: ForkX, kept: Kept | null): string {
  const isKept = kept?.letter === f.letter;
  return [f.letter, f.model, isKept ? `✓ kept${kept?.why ? `: ${kept.why}` : ""}` : forkWord(f), f.lines !== null ? `${f.lines} lines` : "",
          tries(f.attempts), usd(f.usd), f.state === "running" ? quiet(f.idle) : "", isKept ? "" : f.why].filter(Boolean).join(" · ");
}

/** The header's first line when the store is a replay's, as the terminal replay's top line says it. */
export function replayLine(r: Replay | undefined): string {
  return r ? ["replay", r.shown, r.day].filter(Boolean).join(" · ") : "";
}

/** The header's first words, when the store is not a real run's: a replay says what it is; a live race
 *  against the scripted stand-in says so. Nothing for a run whose model was real, or an older snapshot. */
export function topLine(s: Pick<StateX, "replay" | "stand_in">): string {
  return replayLine(s.replay) || (s.stand_in ? "against the scripted stand-in" : "");
}

/** The counts under the goal: `run going · 2 running · 2 need you · 2 of 7 done · width 3 · $0.42`. */
export function counts(s: State): string {
  const sb = s.scoreboard;
  const parts = [`${sb.running} running`, `${sb.need_you} need${sb.need_you === 1 ? "s" : ""} you`, `${sb.proven} of ${sb.total} done`];
  if (s.width) parts.push(`width ${s.width}`);
  const spent = usd(s.spent);
  if (spent) parts.push(spent);
  if (s.run.going) parts.unshift("run going");
  return parts.join(" · ");
}

/** The header's lines. Narrow (the side bar), the header is the goal alone, one line, so the first wave
 *  shows in whatever height the view gets: the counts and the auto line move to the goal's hover and to
 *  the footer, the live line first. */
export function headerFor(s: StateX, narrow: boolean): { goal: string; hover: string; counts: string; auto: string; footer: string } {
  const goal = s.goal || "no goal yet";
  const c = counts(s), a = autoLine(s);
  if (!narrow) return { goal, hover: "", counts: c, auto: a, footer: "" };
  return { goal, hover: [goal, c, a].filter(Boolean).join("\n"), counts: "", auto: "", footer: a || c };
}

export function done(ts: Task[]): string {
  const n = ts.filter((t) => t.state === "done").length;
  return `${n} of ${ts.length}${n === ts.length && ts.length ? " ✓" : ""}`;
}

export interface Button {
  label: string;
  act: Act;
  title: string; // the hover: the graphene command it runs, or what it does
  icon: string; // a codicon's name, "" for none
  fork?: string;
  main?: boolean; // drawn as the primary button
}

/** The buttons a task's pane offers, in order. A replay offers none: its pane reads. */
export function actsFor(t: TaskX, replay: boolean): Button[] {
  const out: Button[] = [];
  if (replay) return out;
  const hasChanges = t.changed.length > 0 || ["running", "review", "done", "came back"].includes(t.state);
  if (t.state === "review") out.push({ label: "Sign off", act: "signOff", title: "it lands: graphene node approve", icon: "check", main: true });
  if (t.state === "proposed") out.push({ label: "Accept", act: "accept", title: "graphene plan accept", icon: "check", main: true });
  if (t.state === "came back") out.push({ label: "Take it up", act: "handBack", title: "widen it, reopen its owner, or try again", icon: "debug-step-back", main: true });
  if (hasChanges) out.push({ label: "Open changes", act: "openDiff", title: "its changes so far, in the diff editor", icon: "diff" });
  if (t.forks.length >= 2) out.push({ label: "Compare forks", act: "compareForks", title: "the forks side by side", icon: "split-horizontal" });
  out.push({ label: "Add step after", act: "add-after", title: "a new task that waits on this one", icon: "add" });
  out.push({ label: "Add step under", act: "add-under", title: "a new task under the same sub-goal", icon: "add" });
  out.push({ label: "Link to…", act: "link", title: "then click the task that waits on this one", icon: "link" });
  if (t.state !== "done") out.push({ label: "Edit", act: "edit", title: "title, scope or check", icon: "edit" });
  if (["proposed", "ready", "waiting"].includes(t.state)) out.push({ label: "Drop", act: "drop", title: "graphene node drop", icon: "trash" });
  if (["running", "ready", "waiting", "came back"].includes(t.state)) out.push({ label: "Tell", act: "tell", title: "a line for the agent on it", icon: "comment" });
  return out;
}

/** What a fork's row offers: its changes, and Keep while the task is in review. Nothing in a replay. */
export function forkActs(t: TaskX, f: Fork, replay: boolean): Button[] {
  if (replay) return [];
  const out: Button[] = [{ label: "Changes", act: "openDiff", title: `fork ${f.letter}'s changes, in the diff editor`, icon: "diff", fork: f.letter }];
  if (t.state === "review" && t.forks.length >= 2) {
    out.push({ label: "Keep", act: "pickFork", title: `keep fork ${f.letter}: graphene node pick`, icon: "pass", fork: f.letter });
  }
  return out;
}

/** The open question on a task, if any. */
export function questionOn(s: State, id: string): Question | undefined {
  return s.questions.find((q) => q.about === id);
}

/** What the details pane is drawn from: the selected task, its question, the names it shows, and whether
 *  the store is a replay's. The same key, the same pane: a change elsewhere leaves it, and its focus,
 *  alone. Empty when nothing is selected. */
export function paneKey(s: StateX, selected: string | null, replay: boolean): string {
  const t = s.tasks.find((x) => x.id === selected);
  if (!t) return "";
  const name = (id: string) => s.tasks.find((x) => x.id === id)?.title ?? id;
  return JSON.stringify([t, questionOn(s, t.id) ?? null, replay, t.needs.map(name), t.parent ? s.goals.find((g) => g.id === t.parent)?.title : ""]);
}

/** The order Tab walks the boxes in: wave by wave, then down each wave, as the eye reads the graph. */
export function tabOrder(lay: Layout, ids: string[]): string[] {
  const at = (id: string) => lay.boxes[id];
  return ids.filter(at).sort((a, b) => (at(a)!.rank - at(b)!.rank) || (at(a)!.y - at(b)!.y) || (at(a)!.x - at(b)!.x));
}

/** Every key the page answers, for the `?` overlay. */
export const KEYS: readonly [string, string][] = [
  ["Tab", "the next box"],
  ["← → ↑ ↓", "the box beside it (across the waves, or along one)"],
  ["Enter", "open the box's details"],
  ["Esc", "close the details, or stop linking"],
  ["g", "bring the goal on screen"],
  ["f", "fit the graph again"],
  ["v", "graph or lanes"],
  ["?", "this list"],
  ["drag a dot", "onto another task: that task waits on this one"],
  ["×", "beside a need: it stops waiting on it"],
  ["wheel · drag", "scroll · pan; ⌘ or Ctrl with the wheel zooms"],
];

/** The hint while a link is armed: what to click or where to drop, and the two ways out. Esc works only with
 *  the focus in the graph, so the footer offers Cancel beside it. */
export function linkHint(title: string, dragging: boolean): string {
  return `link: ${dragging ? "drop it on" : "click"} the task that waits on “${title}” · Cancel or Esc stops it`;
}

/** The first-time hint under the graph. */
export const FIRST_HINT = "click a task · drag its dot onto another to link them · ? lists every key";
