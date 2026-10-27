// The graph's words, pure: what a box and a fork chip say, what the header says of a replay, which acts a
// task offers, and the keys. No DOM here, so `node --test` reads them.
import { usd, type Fork, type Kept, type Question, type State, type Task } from "../state.ts";

/** What the snapshot gains tonight (dev/process/editor/CONTRACT.md): read when present, nothing when not. */
export type ForkX = Fork & { attempts?: number; idle?: number | null };
export type TaskX = Omit<Task, "forks"> & { why?: string; attempts?: number; forks: ForkX[] };
export type Replay = { shown: string; day: string; repository: string } | null;
export type StateX = Omit<State, "tasks"> & { replay?: Replay; tasks: TaskX[] };

export type Act = "add-after" | "add-under" | "link" | "unlink" | "edit" | "drop" | "accept" | "tell" | "run" | "stop" | "auto" | "cockpit"
  | "openDiff" | "compareForks" | "pickFork" | "signOff" | "answer" | "handBack";

/** The acts that change a plan: a replay offers none of them. */
export const CHANGES: readonly Act[] = ["add-after", "add-under", "link", "unlink", "edit", "drop", "accept", "tell", "run", "stop", "auto",
                                        "pickFork", "signOff", "answer", "handBack"];

export const cut = (s: string, n: number) => (s.length > n ? s.slice(0, n - 1).trimEnd() + "…" : s);

/** Words joined with ` · `, the last dropped until they fit ``max`` characters; the first always stays. */
export function fitWords(words: string[], max: number): string {
  const parts = words.filter(Boolean);
  while (parts.length > 1 && parts.join(" · ").length > max) parts.pop();
  return parts.join(" · ");
}

export function forkWord(f: Fork): string {
  return f.state || "waiting";
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

/** A fork's chip: its letter, then that it is kept and why (`b ✓ kept: 4 lines against 12`, the cockpit's
 *  words) or its state, then its lines, tries, dollars and seconds quiet, as many as fit. */
export function forkWords(f: ForkX, kept: Kept | null, max = 28): string {
  const isKept = kept?.letter === f.letter;
  const head = isKept ? `${f.letter} ✓ kept${kept?.why ? `: ${kept.why}` : ""}` : `${f.letter} · ${f.model || forkWord(f)}`;
  const parts = [head, isKept ? "" : f.model ? forkWord(f) : "", f.lines !== null ? `${f.lines} lines` : "",
                 tries(f.attempts), usd(f.usd), f.state === "running" ? quiet(f.idle) : ""];
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

/** The buttons a task's pane offers, in order. A replay offers only what reads. */
export function actsFor(t: TaskX, replay: boolean): Button[] {
  const out: Button[] = [];
  const hasChanges = t.changed.length > 0 || ["running", "review", "done", "came back"].includes(t.state);
  if (t.state === "review" && !replay) out.push({ label: "Sign off", act: "signOff", title: "it lands: graphene node approve", icon: "check", main: true });
  if (t.state === "proposed" && !replay) out.push({ label: "Accept", act: "accept", title: "graphene plan accept", icon: "check", main: true });
  if (t.state === "came back" && !replay) out.push({ label: "Take it up", act: "handBack", title: "widen it, reopen its owner, or try again", icon: "debug-step-back", main: true });
  if (hasChanges) out.push({ label: "Open changes", act: "openDiff", title: "its changes so far, in the diff editor", icon: "diff" });
  if (t.forks.length >= 2) out.push({ label: "Compare forks", act: "compareForks", title: "the forks side by side", icon: "split-horizontal" });
  if (replay) return out;
  out.push({ label: "Add step after", act: "add-after", title: "a new task that waits on this one", icon: "add" });
  out.push({ label: "Add step under", act: "add-under", title: "a new task under the same sub-goal", icon: "add" });
  out.push({ label: "Link to…", act: "link", title: "then click the task that waits on this one", icon: "link" });
  if (t.state !== "done") out.push({ label: "Edit", act: "edit", title: "title, scope or check", icon: "edit" });
  if (["proposed", "ready", "waiting"].includes(t.state)) out.push({ label: "Drop", act: "drop", title: "graphene node drop", icon: "trash" });
  if (["running", "ready", "waiting", "came back"].includes(t.state)) out.push({ label: "Tell", act: "tell", title: "a line for the agent on it", icon: "comment" });
  return out;
}

/** What a fork's row offers: its changes, and Keep while the task is in review. */
export function forkActs(t: TaskX, f: Fork, replay: boolean): Button[] {
  const out: Button[] = [{ label: "Changes", act: "openDiff", title: `fork ${f.letter}'s changes, in the diff editor`, icon: "diff", fork: f.letter }];
  if (t.state === "review" && !replay && t.forks.length >= 2) {
    out.push({ label: "Keep", act: "pickFork", title: `keep fork ${f.letter}: graphene node pick`, icon: "pass", fork: f.letter });
  }
  return out;
}

/** The open question on a task, if any. */
export function questionOn(s: State, id: string): Question | undefined {
  return s.questions.find((q) => q.about === id);
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

/** The first-time hint under the graph. */
export const FIRST_HINT = "click a task · drag its dot onto another to link them · ? lists every key";
