// The graph's words, pure: what a box and a fork chip say, what the header says of a replay, which acts a
// task offers, and the keys. No DOM here, so `node --test` reads them.
import { ASK, NOT_CURSOR } from "../home/who.ts"; // Home's words for the agents, said the same on the graph
import type { Layout } from "../layout.ts";
import { inScope } from "../owners.ts";
import { autoLine, free, headline, SAY, screenWords, usd, type DraftStep, type Fork, type Kept, type Question, type State, type Task } from "../state.ts";

/** What the snapshot gains tonight (dev/process/editor/CONTRACT.md): read when present, nothing when not. */
export type ForkX = Fork & { attempts?: number; idle?: number | null };
export type TaskX = Omit<Task, "forks"> & { why?: string; attempts?: number; forks: ForkX[] };
export type Replay = { shown: string; day: string; repository: string } | null;
/** `stand_in`: every model call on record went to the scripted stand-in (the snapshot's, since 867c326c). */
export type StateX = Omit<State, "tasks"> & { replay?: Replay; stand_in?: boolean; tasks: TaskX[] };

export type Act = "add-after" | "add-under" | "link" | "unlink" | "drop" | "accept" | "tell" | "start" | "run" | "stop" | "cockpit"
  | "openDiff" | "compareForks" | "pickFork" | "signOff" | "sendBack" | "answer" | "handBack" | "set" | "draw" | "saveWorkflow" | "markDone";

/** The acts a replay offers none of: they change a plan, or they act outside the replay (the cockpit opens
 *  `graphene watch` in the person's own folder; openDiff and compareForks look the id up in the person's
 *  plan). That is every act: a replay is watched. The host refuses them too (check.ts). */
export const CHANGES: readonly Act[] = ["add-after", "add-under", "link", "unlink", "drop", "accept", "tell", "start", "run", "stop",
                                        "cockpit", "openDiff", "compareForks", "pickFork", "signOff", "sendBack", "answer", "handBack", "set", "draw",
                                        "saveWorkflow", "markDone"];

/** The header's act buttons, by their element id: each one is hidden in a replay. Auto and the cockpit are
 *  Home's and the palette's (with graphene.advanced), not the graph's. */
export const HEADER_ACTS: readonly [string, Act][] = [["b-add", "add-under"], ["b-run", "run"], ["b-save", "saveWorkflow"]];

/** ``s`` cut to ``n`` characters, the ellipsis one of them; no space or stop left before it (`1.…` is `1…`). */
export const cut = (s: string, n: number) => (s.length > n ? s.slice(0, n - 1).replace(/[\s.,:;·-]+$/, "") + "…" : s);

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

/** A title on up to two lines of ``max`` px, for a compact card: whole words on the first while they fit, the
 *  rest on the second, cut as `fitWidth` cuts. One line when it all fits, or when its first word alone does not
 *  (then that line is cut). */
export function twoLines(s: string, max: number, width: (t: string) => number): string[] {
  if (width(s) <= max) return [s];
  const words = s.split(/\s+/).filter(Boolean);
  let n = 0;
  while (n < words.length - 1 && width(words.slice(0, n + 1).join(" ")) <= max) n++;
  if (!n) return [fitWidth(words.join(" "), max, width)];
  return [words.slice(0, n).join(" "), fitWidth(words.slice(n).join(" "), max, width)];
}

/** Words joined with ` · `, the last dropped until they fit ``max`` characters; the first always stays. */
export function fitWords(words: string[], max: number): string {
  const parts = words.filter(Boolean);
  while (parts.length > 1 && parts.join(" · ").length > max) parts.pop();
  return parts.join(" · ");
}

export function forkWord(f: Fork): string {
  return f.state === "running" ? SAY.running : f.state || "waiting";
}

/** A lane's corner: the model while the task runs, cut to about six characters (`Nano`, `claude…`); the pane
 *  says it whole. Beside it the row wears its state's mark, which is marks.ts's to say (`cornerMark`). */
export function cornerWord(t: TaskX): string {
  return t.state === "running" && t.model ? cut(t.model, 7) : "";
}

/** Who does a step, for the tile on its card: you, or the executor by a letter (Claude Code `C`, Codex `X`, any
 *  other named one by its first), or a command of your own by its first two letters, as a terminal names it. */
export function who(t: Pick<TaskX, "state" | "owner"> & { command?: string | null }, executor: string):
  { kind: "you" | "claude" | "codex" | "agent" | "cmd"; mark: string; label: string } {
  if (t.command) return { kind: "cmd", mark: commandWord(t.command).slice(0, 3), label: "a command, with no agent" }; // a workflow's `run:` step
  if (t.state === "yours" || (t.owner && t.owner !== "agent")) return { kind: "you", mark: "◆", label: "you" };
  const words = executor.trim().split(/\s+/).filter(Boolean);
  const name = family((words[0] ?? "").split("/").pop() ?? ""); // `claude` of the setting's `claude:opus`
  if (name === "claude") return { kind: "claude", mark: "C", label: "Claude Code" };
  if (name === "codex") return { kind: "codex", mark: "X", label: "Codex" };
  if (!name) return { kind: "agent", mark: "?", label: "an agent" };
  return words.length > 1 || words[0]!.includes("/") ? { kind: "cmd", mark: name.slice(0, 2), label: name } : { kind: "agent", mark: name[0]!.toUpperCase(), label: named(name) };
}

/** An agent's name as a person writes it (`Nemotron`, not the setting's `nemotron`). */
const named = (word: string) => word.charAt(0).toUpperCase() + word.slice(1);

/** The part of a command step's command its chip shows: the one its tile names (`gh pr create --draft` of
 *  `cd .. && git push && gh pr create --draft`), so the chip says what leaves the machine and not the `cd` before it. */
export const commandChip = (command: string): string =>
  command.split(/&&|\|\||;/).map((x) => x.trim()).find((x) => ((x.split(/\s+/)[0] ?? "").split("/").pop() ?? "") === commandWord(command)) ?? command;

/** The word a command step's tile shows, as a terminal names what runs: `python3` of `/usr/bin/python3 -m unittest`;
 *  of a line of several commands, the one that leaves the machine (`gh` of `cd .. && git push && gh pr create`,
 *  else `git`), else the first that is not a `cd`. */
export function commandWord(command: string): string {
  if (/\bgh\s+pr\b/.test(command)) return "gh";
  if (/\bgit\s+push\b/.test(command)) return "git";
  const parts = command.split(/&&|\|\||;/).map((x) => x.trim()).filter(Boolean);
  const first = parts.find((x) => !/^cd(\s|$)/.test(x)) ?? parts[0] ?? "";
  return ((first.split(/\s+/)[0] ?? "").split("/").pop() ?? "") || "$";
}

/** A step past the "leaves your machine" line that is the person's move now: approving it runs its command. */
export const asksYou = (t: Pick<TaskX, "leaves" | "state">): boolean => t.leaves && t.state === "yours";

// ---- the pane's Scope tab: what a step may do, as a person reads it ----

export interface TreeRow { name: string; depth: 0 | 1; kind: "in" | "other" | "out"; note: string }

const dirOf = (path: string) => (path.includes("/") ? `${path.slice(0, path.lastIndexOf("/"))}/` : "");
const topOf = (path: string) => (path.includes("/") ? `${path.slice(0, path.indexOf("/"))}/` : path);
/** What a glob names before its first wildcard: `src/export/**` is `src/export/`, `README.md` itself. */
const fixedOf = (glob: string) => {
  const parts = glob.replace(/^\.\//, "").split("/");
  const upto = parts.findIndex((x) => /[*?]/.test(x));
  return upto < 0 ? glob : `${parts.slice(0, upto).join("/")}${upto ? "/" : ""}`;
};

/** May change, as a tree: the repository's top-level entries; this step's folders opened to the files it covers
 *  (a written one says so, at most ``most`` a folder); a path it may create that is not there yet (new; a file under
 *  its folder); another step's entries named; everything else dim. The glob itself is the pane's to show when asked. */
export function scopeTree(t: Pick<TaskX, "id" | "scope" | "files" | "filesN" | "touched" | "changed">, s: Pick<StateX, "tree" | "tasks">, most = 12): TreeRow[] {
  const wrote = writtenIn(t), written = new Set(wrote);
  const files = [...new Set([...t.files, ...wrote])].sort(); // a file it created is one of its files, though git does not track it yet
  const cut = t.filesN > t.files.length; // the snapshot lists 200 at most: the rest are its own all the same
  const globs = t.scope.filter((g) => !g.startsWith("!")).map(fixedOf);
  const fresh = cut ? [] : globs.filter((g) => g && !files.some((f) => f === g || f.startsWith(g))); // nothing there yet
  // a file it may create stands under its folder, as its files do, so a deep path never wraps into what reads as a child
  const born = new Set(fresh.filter((g) => g.includes("/") && !g.endsWith("/")));
  const isNew = s.tree.length ? "new" : ""; // no tree (a replay, an older CLI): nobody knows what is there
  const mine = new Map<string, string[]>(); // a folder of its files -> the files
  for (const f of [...files, ...born].sort()) mine.set(dirOf(f), [...(mine.get(dirOf(f)) ?? []), f]);
  const others = new Map<string, string>(); // a top-level entry -> the other step whose files are under it
  for (const o of s.tasks) {
    if (o.id === t.id) continue;
    for (const f of o.files.length ? o.files : o.scope.filter((g) => !g.startsWith("!")).map(fixedOf)) if (f && !others.has(topOf(f))) others.set(topOf(f), o.title);
  }
  const tops = s.tree.length ? [...s.tree] : [...new Set([...files, ...fresh, ...others.keys()].map(topOf))].sort();
  for (const f of [...files, ...fresh]) if (!tops.includes(topOf(f))) tops.push(topOf(f)); // a path it will create
  const rows: TreeRow[] = [];
  const open = (dir: string) => {
    const files = mine.get(dir) ?? [];
    if (dir) rows.push({ name: dir, depth: 0, kind: "in", note: "" });
    for (const f of files.slice(0, most)) rows.push({ name: dir ? f.slice(dir.length) : f, depth: dir ? 1 : 0, kind: "in", note: written.has(f) ? "written" : born.has(f) ? isNew : "" });
    if (files.length > most) rows.push({ name: `… and ${files.length - most} more`, depth: dir ? 1 : 0, kind: "in", note: "" });
  };
  for (const top of tops) {
    const dirs = [...mine.keys()].filter((d) => (top.endsWith("/") ? d.startsWith(top) : false)).sort();
    const here = fresh.filter((g) => topOf(g) === top && !born.has(g));
    if (!top.endsWith("/") && files.includes(top)) rows.push({ name: top, depth: 0, kind: "in", note: written.has(top) ? "written" : "" });
    else if (dirs.length || here.length) {
      for (const d of dirs) open(d);
      for (const g of here) rows.push({ name: g, depth: 0, kind: "in", note: isNew });
    } else if (cut && globs.some((g) => !g || g.startsWith(top))) rows.push({ name: top, depth: 0, kind: "in", note: "" }); // its own, past the list's cut
    else rows.push({ name: top, depth: 0, kind: others.has(top) ? "other" : "out", note: others.has(top) ? "another task's" : "" });
  }
  if (cut) rows.push({ name: `… and ${t.filesN - t.files.length} more files`, depth: 0, kind: "in", note: "" });
  return rows;
}

/** What a step has written inside its files. A write outside them is the Stopped part's and the finish's to
 *  say: it is never counted as one of its files. */
const writtenIn = (t: Pick<TaskX, "scope" | "touched" | "changed">): string[] => [...new Set([...t.touched, ...t.changed])].filter((f) => inScope(f, t.scope));

/** How many of its files a step has written so far: `2 of 4`. A file it created is one of its files too, though
 *  git does not track it yet. Nothing while its scope covers no file and it has written none. */
export function writtenOf(t: Pick<TaskX, "scope" | "files" | "filesN" | "touched" | "changed">): string {
  const written = writtenIn(t);
  // ponytail: past the list's cut (200 files) a written file cannot be told from a new one, so the count stays the scope's
  const all = t.filesN > t.files.length ? Math.max(t.filesN, written.length) : t.filesN + written.filter((f) => !t.files.includes(f)).length;
  return all ? `${written.length} of ${all}` : "";
}

/** An executor's family: `claude` of `claude:opus`. The setting names the model too; a run names who holds a step by family alone. */
const family = (by: string) => by.split(":")[0]!;

/** May run: the commands the repository's executor may run without asking, as its own command line lists them
 *  (`allows`), or that it names no list. The list is that executor's: a step someone else holds (another agent
 *  a run was given, you) is not under it. Graphene's own two (`graphene node *`, `graphene plan *`, how the agent
 *  says it is done) are left out: they are not the repository's. Where the list does not let it run its own
 *  check (`./gradlew` with the default list), the ``note`` says so, and where that is set (a flag in it between
 *  backticks): `graphene init --executor` takes the executor's whole command, so naming it alone would lead nowhere. Outside: Graphene grants a step nothing, and says no more than that of an agent whose own
 *  settings decide what it reaches. */
export function mayRun(s: Pick<StateX, "allows" | "executor">, t: Pick<TaskX, "held" | "check">): { commands: string[]; words: string; note: string; outside: string } {
  if (s.allows && family(t.held.by) === family(s.executor)) {
    const commands = s.allows.filter((c) => !/^graphene (node|plan)\b/.test(c));
    // `./gradlew` of `cd app && ./gradlew test`; `pytest` of `PYTHONPATH=. pytest -q`, not the setting before it
    const check = commandChip((t.check ?? "").trim()), first = check.split(/\s+/).find((w) => !/^\w+=/.test(w)) ?? "";
    const can = !first || commands.some((c) => check.startsWith(c.replace(/:?\*$/, "").trim())); // `npm test *`, `npm run test:*`
    return { commands, words: commands.length ? "" : "no shell command", outside: OUTSIDE,
             note: can ? "" : `It cannot run ${first}, so it never runs its own check. What it may run is set by the executor's \`--allowedTools\`.` };
  }
  const held = t.held.state === "refused" || t.held.state === "caught";
  return { commands: [], words: held ? "any command: what a command writes is still held to its files" : "any command", note: "", outside: OUTSIDE_OWN };
}
export const OUTSIDE = "none";
export const OUTSIDE_OWN = "none granted by Graphene: this agent's own settings decide what else it reaches";

/** Held by, in one of three states and never more than the tests prove (tests/test_every_agent.py,
 *  dev/process/graph-edit/hooks.md): refused before the write, caught when it finishes, or not held. A
 *  Graphene that does not say reads as not held: no shield for an agent nobody has tested. */
export function heldWords(t: Pick<TaskX, "held">): { shield: boolean; line: string; proof: string } {
  const by = family(t.held.by) === "claude" ? "Claude Code" : family(t.held.by) === "codex" ? "Codex" : named(family(t.held.by)) || "This agent";
  if (t.held.state === "refused") return { shield: true, line: "A write outside its files is refused before it happens.", proof: `${by}'s hook stops it, and its finish checks again.` };
  if (t.held.state === "caught") return { shield: true, line: "A write outside its files is caught when it finishes, at the latest.",
                                          proof: "Its finish checks what changed against its files: then none of its work lands, and the task needs your help." };
  return { shield: false, line: "Not held: nothing stops a write outside its files.",
           proof: t.held.state === "none" ? "A task you do yourself, or give to an editor's own agent (Cursor, Copilot), is checked only when you mark it done."
             : "This version of Graphene does not say how this task is held." };
}

/** Stopped: this step's refused writes against the run's, then each with its time as the clock here reads it. */
export function stopsOf(t: Pick<TaskX, "id" | "title" | "stops">, tasks: readonly Pick<TaskX, "id" | "title" | "stops" | "state">[], clock = (iso: string) => new Date(iso)):
  { count: string; rows: { line: string; note: string }[] } {
  const went = (state: string) => state === "running" || state === "review" || state === "done"; // it carried on: said only where it did
  const all = tasks.flatMap((o) => o.stops.map((x) => ({ ...x, id: o.id, title: o.title, on: went(o.state) })));
  const time = (iso: string) => { const d = clock(iso); return Number.isNaN(d.getTime()) ? "" : ` ${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}`; };
  const shown = t.stops.length ? all.filter((x) => x.id === t.id) : all.slice(-3); // none here: the run's last ones, so a person sees where
  return { count: `${t.stops.length} here · ${all.length} in the run`,
           rows: shown.map((x) => ({ line: x.id === t.id ? `tried ${x.path}` : `“${x.title}” tried ${x.path}`,
                                     note: `refused${time(x.at)}${x.how ? ` · ${x.how}` : ""}${x.on ? " · it carried on in its own files" : ""}` })) };
}

/** Done when: the check's result on the code as it was, and after the work. */
export function checkWords(t: Pick<TaskX, "check" | "checked" | "state">): { tone: "red" | "warn" | "ok" | "dim"; line: string }[] {
  if (!t.check) return [{ tone: "dim", line: "no check: your approval finishes it" }];
  const before: Record<string, [("red" | "warn" | "ok" | "dim"), string]> = {
    red: ["red", "failed before the work, so it can tell"],
    passes: ["warn", "passed before the work: it proves nothing yet"],
    outside: ["warn", "failed before the work on a path outside its files"],
    environment: ["warn", "could not be run here before the work"],
    landed: ["dim", "passed when it landed; reopened, it passes until the check is changed"],
  };
  const b = before[t.checked.before ?? ""] ?? ["dim", "not run on the code as it is yet: it runs once before the work starts"];
  const a: [("red" | "warn" | "ok" | "dim"), string] = t.checked.after === "passed" ? ["ok", "passed after the work, in a clean copy"]
    : t.checked.after === "failed" ? ["red", "failed after the work"]
    : ["dim", t.state === "running" ? "runs in a clean copy when the agent says done" : "runs in a clean copy after the work"];
  return [{ tone: b[0], line: b[1] }, { tone: a[0], line: a[1] }];
}

const bare = (s: string) => s.trim().replace(/^(an?|the)\s+/i, "").toLowerCase();
/** What a task is for, under its title in the pane: what follows `title:` in the plan's line (`Librarian service:
 *  collections, …` says `Collections, …`); nothing where the line is its title again or starts with it (`hello says
 *  hello to the person by name`: the title's hover has it whole); else the line. */
export function whatFor(t: Pick<TaskX, "title" | "full">): string {
  const full = t.full.trim(), title = bare(t.title);
  if (!title || !bare(full).startsWith(title)) return full;
  const rest = full.slice(full.toLowerCase().indexOf(title) + title.length).trim();
  const said = rest.startsWith(":") ? rest.slice(1).trim() : "";
  return said && said[0]!.toUpperCase() + said.slice(1);
}

/** Activity's line for a task open again after an agent was on it (sent back, tried again, or stopped): what the
 *  snapshot keeps of that try, its agent and its check's last verdict, which the card does not wear, as it no longer
 *  stands (marks.ts `standing`). Work that passed is open again only by a person's send back, whose note the next
 *  agent is given (plan.reopen); its moves, its files and that note are not in the snapshot. Nothing for any other task. */
export function earlier(t: Pick<TaskX, "state" | "agent" | "checked">): string {
  if (!t.agent || (t.state !== "ready" && t.state !== "waiting")) return "";
  if (t.checked.after === "passed") return `agent ${t.agent}'s work passed its check and was sent back: your note goes to the agent that takes it next`;
  return `agent ${t.agent} tried it${t.checked.after === "failed" ? ", and its check failed" : ""}`;
}

const thousands = (n: number) => (n >= 1000 ? `${Math.round(n / 1000)}k` : String(n));
/** Tokens: what its attempts read and wrote, as shares; the check is Graphene's to run and costs none. */
export function tokenWords(t: Pick<TaskX, "tokens">): { total: string; read: number; written: number; line: string } | null {
  if (!t.tokens || !(t.tokens.read + t.tokens.written)) return null;
  const all = t.tokens.read + t.tokens.written, read = Math.round((t.tokens.read / all) * 100);
  const cached = t.tokens.cached ? ` (${thousands(t.tokens.cached)} of it from cache)` : "";
  return { total: `${thousands(t.tokens.read)} in · ${thousands(t.tokens.written)} out`, read, written: 100 - read,
           line: `reading ${read}%${cached} · writing ${100 - read}% · its check 0%: Graphene runs it, no model` };
}

export interface Stage { key: "plan" | "run" | "review"; label: string; at: "done" | "now" | "next"; note: string }

/** One pipeline, the plan always first: Plan, Run, Review. Where the work is (the first stage not finished is
 *  `now`), and a few words under each: how big the plan is, who is working, what waits for you. Auto is the same pipeline with no stop after the plan (`stopAfterPlan`). A command step is never
 *  `running` (the run executes it itself): a run going with one ready is running it, not starting. */
export function pipeline(s: Pick<StateX, "drafting" | "tasks" | "goals" | "run">): Stage[] {
  const n = (k: TaskX["state"]) => s.tasks.filter((t) => t.state === k).length;
  const count = (k: number, word: string) => `${k} ${word}${k === 1 ? "" : "s"}`;
  const planned = s.tasks.length > 0 && (n("running") > 0 || (!n("proposed") && !s.drafting)); // agents at work: the plan was started
  const ran = planned && s.tasks.every((t) => t.state === "review" || t.state === "done");
  const landed = ran && !n("review");
  const plan = s.drafting ? (s.drafting.live ? `${count(draftedSteps(s).length, "task")} so far` : "the planner is writing")
    : [s.tasks.length ? count(s.tasks.length, "task") : "", planned && n("proposed") ? `${n("proposed")} suggested` : ""].filter(Boolean).join(" · "); // an open question is its chip's to say
  const run = !planned || ran ? "" : n("running") ? `${n("running")} working` : n("came back") ? `${n("came back")} need${n("came back") === 1 ? "s" : ""} help` : s.run.going ? (s.tasks.some((t) => t.command && !t.leaves && t.state === "ready") ? "running a command" : "starting")
    : n("yours") ? `${n("yours")} ask${n("yours") === 1 ? "s" : ""} you` : n("ready") ? `${n("ready")} ready` : "waiting";
  const review = n("review") ? `${n("review")} to review` : landed ? "done" : "";
  return [
    { key: "plan", label: "Plan", at: planned ? "done" : "now", note: plan },
    { key: "run", label: "Run", at: !planned ? "next" : ran ? "done" : "now", note: run },
    { key: "review", label: "Review", at: !ran ? "next" : landed ? "done" : "now", note: review },
  ];
}

/** Before Run each step's check runs once on the code as it is. One that passes there proves nothing yet: said
 *  on the card of a task whose work is not finished (the snapshot's `hollow`). */
export const PROVES_NOTHING = "This check already passes, before any work: it proves nothing yet. Give the task a check that fails now.";
/** Whether a task's card carries that mark: its check passed before the work, and the work is not done. */
export const provesNothing = (t: Pick<TaskX, "hollow" | "state">): boolean => t.hollow && t.state !== "done" && t.state !== "review";

/** The one switch: on (the default), the run waits for you after the plan; off is auto, and the plan is still
 *  drawn first. It is the envelope's `auto` setting, read the other way round. */
export const stopAfterPlan = (s: { envelope: { auto: string } }): boolean => s.envelope.auto !== "on";
export const STOP_AFTER = "Stop after the plan";
export const STOP_AFTER_HOVER = "On: the plan is drawn and waits for you to start it. Off is auto: the plan is still drawn first, then what fits your limits "
  + "runs without waiting. A question with no default stops it either way: Start waits for its answer, and so does auto.";

/** The steps to draw while a planner writes: each one it has finished a line for that is a task, not a
 *  sub-goal, and is not in the plan already (a line that names a task the plan has is an anchor, not a step). */
export function draftedSteps(s: Pick<StateX, "drafting" | "tasks" | "goals">): DraftStep[] {
  const have = new Set([...s.tasks.map((t) => t.id), ...s.goals.map((g) => g.id)]);
  return (s.drafting?.steps ?? []).filter((d) => d.leaf && !have.has(d.id));
}

/** The line at the canvas's foot while a planner writes: how many steps it has drawn so far, or, when its
 *  stream carries no text, that the boxes appear when the plan arrives. Nothing when no planner is writing. */
export function planningLine(s: Pick<StateX, "drafting" | "tasks" | "goals">): string {
  if (!s.drafting) return "";
  const by = s.drafting.by ? ` (${s.drafting.by})` : "";
  if (!s.drafting.live) return `The planner${by} is writing: its tasks appear when the plan arrives`;
  const n = draftedSteps(s).length;
  return `The planner${by} is drawing: ${n} task${n === 1 ? "" : "s"} so far`;
}

/** The files chip on a card: the first of the paths it may change, and how many more there are. */
export const filesChip = (scope: readonly string[]): string => (scope.length > 1 ? `${scope[0]} +${scope.length - 1}` : scope[0] ?? "");

/** How an edge is drawn, by the tasks at its ends (the goal has none): `run` where an agent is working on what
 *  it leads to, `done` where the work it carries landed, `wait` until then. Either end done says it landed: a
 *  done task's needs are done, and the edge that crosses the line starts at the goal. */
export function edgeKind(from: Pick<TaskX, "state"> | undefined, to: Pick<TaskX, "state"> | undefined): "run" | "done" | "wait" {
  if (to?.state === "running") return "run";
  return from?.state === "done" || to?.state === "done" ? "done" : "wait";
}

/** How many attempts a task runs as: its own number, else the limits' (Set Limits…), else one. */
export const attemptsOf = (t: Pick<TaskX, "planned">, limit: number | null | undefined): number => Math.min(8, Math.max(1, t.planned ?? limit ?? 1));

/** What a change to a task does now, by its state: the one line under the pane's form. It says what
 *  `graphene node set` does (dev/process/graph-edit/edits.md has each state's answer, as the engine gave it).
 *  A command step has no form: its line says where it changes. */
export function whenEdit(t: Pick<TaskX, "state"> & { command?: string | null }): string {
  if (t.command && t.state !== "done") return "A command task is its command alone: no files, no attempts, no agent. Change its run: line in the plan's text.";
  switch (t.state) {
    case "proposed": return "Suggested: nothing runs yet. A change binds once you accept it.";
    case "ready": case "waiting": return "Not started: its agent starts from what you set here.";
    case "running": return "Working now: new files hold its agent's next write; a new check, or your approval, its finish. Attempts wait for its next start.";
    case "review": return "To review: its work is finished. A change binds when it starts again, if you send it back.";
    case "came back": return "Needs help: a change binds when it starts again.";
    case "yours": return "Yours: no agent takes it. Untick “I will do this one” and one can.";
    case "done": return `Done: a finished task is not edited.${t.command ? "" : " Send it back, from the …, to open it again."}`; // actsFor's Send back…
  }
}

/** Whether the pane's form takes edits: graphene refuses a change to a finished task, and a replay is watched.
 *  Nor a command step: `node set` takes files, attempts, an owner and an approval on one, and each makes it
 *  something else (with files it is no command step: off the line, its approval gone). */
export const editable = (t: Pick<TaskX, "state"> & { command?: string | null }, replay: boolean): boolean => !replay && t.state !== "done" && !t.command;

const quiet = (idle: number | null | undefined) => (idle !== null && idle !== undefined && idle > 8 ? `${Math.round(idle)} s quiet` : "");
const tries = (n: number | undefined) => (n !== undefined && n > 1 ? `${n} tries` : "");

/** The small line under a box's title: the state first, in plain words, then what matters for it. A task that
 *  needs help says why on the box. */
export function sub(t: TaskX, max = 25): string {
  if (asksYou(t)) return cut("asks you: it leaves your machine", max);
  if (t.command && t.checked.after === "failed" && t.state !== "done") return cut("its command failed: a run tries it again", max);
  const parts: string[] = [];
  if (t.state === "running") parts.push(`agent ${t.agent || "?"}`, t.forks.length ? `${t.forks.length} attempts` : SAY.running);
  else parts.push(SAY[t.state]);
  if (t.state === "came back" && t.why) return cut(fitWords([`${SAY["came back"]} · ${screenWords(t.why)}`, tries(t.attempts), usd(t.usd)], max), max); // the reason, cut, not dropped
  if (t.state === "came back" && t.outside.length) parts.push(`${t.outside.length} outside`);
  if (provesNothing(t)) parts.push("check already passes"); // it proves nothing yet: said before the cost and the tries
  parts.push(tries(t.attempts), usd(t.usd), t.state === "running" ? quiet(t.idle) : "");
  return fitWords(parts, max);
}

/** A fork's chip: its letter and model, then that it is kept and why (`b ✓ kept: 4 lines against 12`, the
 *  cockpit's words), then as many as fit of its words. While it runs the numbers are the news, so its
 *  lines, seconds quiet and dollars come before the state word (its border says it runs anyway); once it
 *  ended the state word is the news and comes first. The default width is the chip's, 32 mono characters. */
export function forkWords(f: ForkX, kept: Kept | null, max = 32): string {
  const isKept = kept?.letter === f.letter;
  const head = cut(isKept ? `${f.letter} ✓ kept${kept?.why ? `: ${screenWords(kept.why)}` : ""}` : `${f.letter} · ${f.model || forkWord(f)}`, max);
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
  return [f.letter, f.model, isKept ? `✓ kept${kept?.why ? `: ${screenWords(kept.why)}` : ""}` : forkWord(f), f.lines !== null ? `${f.lines} lines` : "",
          tries(f.attempts), usd(f.usd), f.state === "running" ? quiet(f.idle) : "", isKept ? "" : screenWords(f.why)].filter(Boolean).join(" · ");
}

/** The header's first line when the store is a replay's, as the terminal replay's top line says it. */
export function replayLine(r: Replay | undefined): string {
  return r ? ["replay", r.shown, r.day].filter(Boolean).join(" · ") : "";
}

/** The header's first words, when the store is not a real run's: a replay says what it is; a live race
 *  against the scripted stand-in says it is practice. Nothing for a run whose model was real, or an older snapshot. */
export function topLine(s: Pick<StateX, "replay" | "stand_in">): string {
  return replayLine(s.replay) || (s.stand_in ? "practice run · a scripted stand-in, no real AI" : "");
}

/** The header: the goal (what was asked, or the sub-goal a planner is drawing), the stages with what the run has
 *  cost in Run's note, and auto's line while auto is at work (`done`, it is said by the stages and the status
 *  bar). The cost is said once: not beside an auto line that says it against its budget, and not for a race
 *  against the scripted stand-in or a replay, which spend nothing (state.ts `free`). */
export function headerFor(s: StateX): { goal: string; auto: string; stages: Stage[] } {
  const drawing = s.drafting?.steps.find((d) => !d.leaf && !d.parent)?.title;
  const goal = headline(s) || drawing || (s.tasks.length ? "your plan" : "Graphene"); // an ask sets no goal: what was asked
  const auto = s.auto?.stage === "done" ? "" : autoLine(s);
  const spent = free(s) || (auto && s.auto?.spent !== null) ? "" : usd(s.spent);
  const stages = pipeline(s).map((st) => (st.key === "run" && spent && st.at !== "next" ? { ...st, note: [st.note, spent].filter(Boolean).join(" · ") } : st));
  return { goal, auto, stages };
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
  off?: boolean; // shown, and not pressed: its hover says why
}

/** The header's one act on the whole plan: Stop while a run goes; Start while any task is a suggestion and none
 *  works (Home's Start: every suggested task accepted, the plan's open questions answered with their defaults,
 *  then the run), so a task accepted alone in its pane does not turn it into a Run that leaves the rest behind;
 *  else Run, filled while a task is ready. Start is held as Home's is: while a question with no default is open,
 *  and with Exact on (the host says) while any question is. Run is not, as Home's and `graphene run` are not: it
 *  leaves such a question open. None for no plan, or one all done: nothing to start. */
export function mainAct(s: Pick<StateX, "run" | "tasks" | "questions">, exact = false): Button | null {
  if (!s.tasks.length || (!s.run.going && s.tasks.every((t) => t.state === "done"))) return null;
  if (s.run.going) return { label: "Stop", act: "stop", icon: "debug-stop", title: "stop every agent: their tasks go back to the plan" };
  const n = (k: TaskX["state"]) => s.tasks.filter((t) => t.state === k).length;
  const answers = startAnswers(s);
  if (n("proposed") && !n("running")) {
    const waits = exact && s.questions.length > 0, held = waits || s.questions.some((q) => !q.default); // home/cards.ts `unanswered`
    return { label: "Start", act: "start", icon: "play", main: !held, off: held,
             title: waits ? "Exact is on: it waits for your answers" : held ? "it waits for an answer: a question with no default is open"
               : `accept the ${n("proposed")} suggested${answers ? `, ${answers}` : ""}, then start an agent on each that is ready` };
  }
  const ready = n("ready");
  return { label: "Run", act: "run", icon: "play", main: ready > 0, off: !ready,
           title: !ready ? "nothing is ready to run" : `${answers ? `${answers}, then ` : ""}start an agent on every task that is ready` };
}

/** What Start and Run do to the plan's open questions: each with a default takes it, as `graphene run` and
 *  accepting the whole plan do (one with none stays open, and holds Start). Said in their hover and under the
 *  question's chip, so a click on either is not an answer nobody saw. */
export function startAnswers(s: Pick<StateX, "questions">): string {
  const q = s.questions.filter((x) => x.default), all = q.length === s.questions.length;
  if (!q.length) return "";
  if (q.length === 1) return `answer ${all ? "the" : "an"} open question with its default (“${cut(q[0]!.default!, 60)}”)`;
  return `answer ${all ? "the " : ""}${q.length} open questions with their defaults`;
}

/** The buttons a task's pane offers, in order, its main one first. A replay offers none: its pane reads. A step
 *  past the line offers nothing after it (a task drawn there lands in the first column, its edge running
 *  backwards), and a command step has no agent to message. To review, it is Home's card (home/cards.ts): Compare
 *  first while two attempts passed and none is kept, else Open changes until they were ``opened`` in this
 *  window, and only then a filled Approve; Send back… beside them either way. */
export function actsFor(t: TaskX, replay: boolean, opened = false): Button[] {
  const out: Button[] = [];
  if (replay) return out;
  const hasChanges = t.changed.length > 0 || ["running", "review", "done", "came back"].includes(t.state);
  const review = t.state === "review";
  const choose = review && !t.kept && t.forks.filter((f) => f.state === "passed").length > 1; // its check could not choose: the person keeps one
  const look = review && !choose && !opened;
  if (asksYou(t)) out.push({ label: "Approve and run", act: "markDone", title: `it leaves your machine: graphene node done runs ${cut(t.command ?? "", 80)}`, icon: "check", main: true });
  else if (t.state === "yours") out.push({ label: "Mark done", act: "markDone", icon: "check", main: true, // a step of your own, as Home's Mark done
                                           title: `you did it yourself: graphene node done ${t.check ? "runs its check first, in a terminal" : "finishes it, it has no check to run"}` });
  if (choose) out.push({ label: "Compare attempts", act: "compareForks", title: "more than one attempt passed its check: compare them and keep one, then approve it", icon: "split-horizontal", main: true });
  if (look) out.push({ label: "Open changes", act: "openDiff", title: "you have not opened its changes yet: the diff editor shows them", icon: "diff", main: true });
  if (review && !choose) out.push({ label: "Approve", act: "signOff", title: "it lands in your repository: graphene node signoff", icon: "check", main: !look });
  // one task alone, from the …: the header's Start accepts every suggested task, and a card's × leaves one out
  if (t.state === "proposed") out.push({ label: "Accept only this task", act: "accept", title: "the others stay suggested: graphene plan accept", icon: "check" });
  if (t.state === "came back") out.push({ label: "Help it…", act: "handBack", title: "allow what it needs, add a task for it, or try again", icon: "debug-step-back", main: true });
  if (t.state === "running" && t.stopped.length) out.push({ label: "Allow the write…", act: "handBack", icon: "check", main: true, // the run waits on it, as Home's Allow it to change
                                                           title: `it was stopped writing ${cut(t.stopped[t.stopped.length - 1]!, 60)}, outside its files: graphene node widen lets it` });
  if (hasChanges && !look) out.push({ label: "Open changes", act: "openDiff", title: "its changes so far, in the diff editor", icon: "diff" });
  if (t.forks.length >= 2 && !choose) out.push({ label: "Compare attempts", act: "compareForks", title: "the attempts side by side", icon: "split-horizontal" });
  if (review || (t.state === "done" && !t.command)) out.push({ label: "Send back…", act: "sendBack", icon: "debug-step-back", // as Home's, and Edit's line for a finished task says it
                                                                title: review ? "say what is wrong, and an agent takes it again: graphene node reopen"
                                                                  : "what landed stays: say what is wrong, and an agent takes it again from there: graphene node reopen" });
  if (!t.leaves) out.push({ label: "Add task after", act: "add-after", title: "draw a new task that waits on this one", icon: "add" });
  out.push({ label: "Add task beside", act: "add-under", title: "draw a new task under the same sub-goal", icon: "add" });
  if (!t.leaves) out.push({ label: "Link to…", act: "link", title: "then click the task that waits on this one", icon: "link" });
  if (["proposed", "ready", "waiting"].includes(t.state)) out.push({ label: "Remove", act: "drop", title: "take it out of the plan: graphene node drop", icon: "trash" });
  if (!t.command && ["running", "ready", "waiting", "came back"].includes(t.state)) out.push({ label: "Message agent", act: "tell", title: "a line the agent on it reads with its next move", icon: "comment" });
  return out;
}

/** What an attempt's row offers: its changes, and Keep while the task is to review. Nothing in a replay. */
export function forkActs(t: TaskX, f: Fork, replay: boolean): Button[] {
  if (replay) return [];
  const out: Button[] = [{ label: "Changes", act: "openDiff", title: `attempt ${f.letter}'s changes, in the diff editor`, icon: "diff", fork: f.letter }];
  if (t.state === "review" && t.forks.length >= 2) {
    out.push({ label: "Keep", act: "pickFork", title: `keep attempt ${f.letter}: graphene node pick`, icon: "pass", fork: f.letter });
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

/** Every key the page answers and what the mouse does, for the `?` overlay, in the screen's words: what a person
 *  moves between, adds, links and sees, then how the view moves. */
export const KEYS: readonly [string, string][] = [
  ["Tab", "the next task"],
  ["← → ↑ ↓", "move between tasks"],
  ["Enter", "open the task's details"],
  ["Esc", "close what is open, or stop linking"],
  ["n", "the next task that needs you"],
  ["g", "the goal"],
  ["+", "add a task, after the selected one if there is one"],
  ["drag a dot", "onto another task: that task waits on this one"],
  ["v", "graph or lanes"],
  ["f", "fit the plan"],
  ["- · =", "zoom out · zoom in"],
  ["0", "100%: whole cards at their own size"],
  ["wheel · drag", "scroll · pan; with ⌘ or Ctrl, or a pinch, zoom"],
  ["double click", "a row: open it as a card; the canvas: fit the plan"],
  ["?", "this list"],
];

/** The hint while a link is armed: what to click or where to drop, and the two ways out. Esc works only with
 *  the focus in the graph, so the footer offers Cancel beside it. */
export function linkHint(title: string, dragging: boolean): string {
  return `link: ${dragging ? "drop it on" : "click"} the task that waits on “${title}” · Cancel or Esc stops it`;
}

/** The empty graph's words: who plans here, by name. Graphene's hooks reach Claude Code and Codex alone, not
 *  Cursor's own Agent: in Cursor that is said too, in the same words wherever a screen points to an agent. */
export const ASK_AGENT = `${ASK}: its plan appears here. Or draw the first task.`;
export const CURSOR_AGENT = NOT_CURSOR;

/** The question chip's words, its two halves as the tasks' chip has them: `1 question · answer`; none for none. */
export const askLine = (n: number): string => (n ? `${n} question${n === 1 ? "" : "s"} · answer` : "");
/** The line under that chip while the main act would take the defaults of `n` of them (`startAnswers`): it reads
 *  with the chip's `· answer` or without it (a narrow tab hides that). */
export const askNote = (n: number, act: string): string => `${act} takes ${n === 1 ? "its default" : "their defaults"}`;

/** The news a screen reader hears from the graph: the latest line that nothing on screen says already (the
 *  plan's open question has its chip, auto's wait its line in the header), in the screen's words, so the CLI's
 *  `proposed` is suggested and `came back` needs help. */
export function newsLine(s: Pick<StateX, "news" | "questions">, autoShown: boolean): string {
  const said = (line: string) => (s.questions.length > 0 && /^asks: |\bquestions? waits? for you\b/.test(line)) || (autoShown && /^auto\b/.test(line));
  return newsWords([...s.news].reverse().find((l) => !said(l)) ?? "");
}
/** A news line in the screen's words (the status bar's hover reads them too): only the narrator's own verbs
 *  (`proposed: <title>`, `proposed goal: …`, `<title> came back: why`), so a title that says proposed keeps it. */
export const newsWords = (line: string): string =>
  screenWords(line).replace(/^(the planner )?proposed(?=:| goal:| \d)/, `$1${SAY.proposed}`).replace(/ came back(?=: )/, ` ${SAY["came back"]}`);
