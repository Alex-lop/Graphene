// A session as the snapshot the graph already draws (state.ts `State`): a handful of cards at the level a
// person thinks at. A card a request the person made, titled from their words, and after it what the agent
// wrote for itself while answering it, the first of these that it has: its own task list, or the plan it put
// to the person; else the subagents and workflows it launched, fanning out from the request. A tool call is
// never a card: it is the activity inside one.
// Pure: sessions in, a snapshot out.
import * as path from "node:path";
import { cutWhole } from "../graph/marks.ts";
import { parseState, type Card, type GitFacts, type Receipt, type SessionInfo, type State, type Word } from "../state.ts";
import { COMMAND, str, SUBAGENT, WORKFLOW, WRITES, type Raw } from "./events.ts";
import { sidesOf, subOver, type Call, type Model, type Sub, type Turn } from "./model.ts";
import { receipt, shared } from "./receipt.ts";

export type Status = SessionInfo["status"];
/** What the agent's own record of its process says while it runs (find.ts `procs`): `busy` or `idle`; `gone` once
 *  a process that was seen has ended (the hub says so). */
export interface Live { status: string }

/** A request under way that wrote nothing for this long is no longer called working, unless a tool call is
 *  still out (a test run, a subagent), which may be quiet for longer. With no record of its process to ask,
 *  this is all there is to go by. */
export const QUIET = 120_000, OUT = 30 * 60_000;
/** The tools that stop and wait for the person: a call of one with no answer yet is proof the session needs them. */
const ASKS: readonly string[] = ["AskUserQuestion", "ExitPlanMode"];
/** The requests drawn as cards, the newest: the ones before them are one card, `12 earlier requests`. */
export const SHOWN = 8;

const ms = (iso: string): number => { const t = Date.parse(iso); return Number.isFinite(t) ? t : 0; };

/** What the session is doing: `needs you` only when its file proves it (a question or a plan it put to the
 *  person, unanswered), `working` while a request is under way and something says it still runs, else `idle`. */
export function status(m: Model, now: number, live?: Live | null): Status {
  const t = m.turns.at(-1);
  if (!t) return "idle";
  const quiet = now - Math.max(ms(m.last), m.touched); // its last line read, or its file's last write of any line
  // a subagent or a workflow the request left running behind it: the request is over, the work is not
  const behind = m.agent === "claude" && m.subs.some((s) => s.turn === t.n && !subOver(m, s));
  if (t.ended) return behind && quiet < OUT ? "working" : "idle";
  // its process was seen running and is gone (killed, its terminal closed): whatever it left open, nobody is there
  if (live?.status === "gone") return "idle";
  // it asked, and something says it is still there to be answered: its process, or a line written not long ago
  if (t.calls.some((c) => !c.done && ASKS.includes(c.name))) return live || quiet < OUT ? "needs you" : "idle";
  if (live) return live.status === "idle" ? "idle" : "working";
  return quiet < QUIET || (quiet < OUT && (behind || t.calls.some((c) => !c.done))) ? "working" : "idle";
}

/** A path as a person reads it: from the session's folder when it is inside it. */
export function rel(file: string, cwd: string): string {
  if (!file || !cwd || !path.isAbsolute(file)) return file;
  const r = path.relative(cwd, file);
  return r && !r.startsWith("..") && !path.isAbsolute(r) ? r.split(path.sep).join("/") : file;
}

const oneLine = (s: string): string => s.replace(/\s+/g, " ").trim();

/** A tool call in a line, as a terminal would say it: the command, the file, what was searched for. */
export function doing(c: Call, cwd: string): string {
  const i = c.input, file = rel(str(i.file_path) || str(i.notebook_path), cwd);
  if (c.name === COMMAND) return `$ ${oneLine(str(i.command))}`;
  if (WRITES.includes(c.name)) return `${c.name === "Write" ? "write" : "edit"} ${file}`;
  if (c.name === "Read") return `read ${file}`;
  if (c.name === "Grep" || c.name === "Glob") return `search ${oneLine(str(i.pattern))}`;
  if (SUBAGENT.includes(c.name)) return `subagent: ${oneLine(str(i.description))}`;
  if (c.name === WORKFLOW) return "workflow";
  if (c.name.startsWith("mcp__")) return c.name.split("__").slice(1).join(" ");
  return c.name;
}

/** A card's title, from the person's words: their first line that says something, without its markup, cut at
 *  a word. */
export function titleOf(text: string, n = 72): string {
  // a heading's, a quote's or a list's mark goes; a code fence's line is not words
  const line = text.split(/\r?\n/).filter((l) => !/^\s*```/.test(l)).map((l) => l.replace(/^[#>*\-\s]+/, "").trim()).find((l) => /\p{L}|\p{N}/u.test(l)) ?? "";
  return cutWhole(oneLine(line), n);
}

/** A plan's steps, out of the text ExitPlanMode carried: its numbered items, else its second-level headings.
 *  Fewer than two is no plan to draw. */
export function planSteps(plan: string): string[] {
  const lines = plan.split(/\r?\n/);
  const numbered = lines.map((l) => /^\s{0,3}\d+[.)]\s+(.+)/.exec(l)?.[1] ?? "").filter(Boolean);
  const heads = lines.map((l) => /^#{2,3}\s+(.+)/.exec(l)?.[1] ?? "").filter(Boolean);
  const steps = numbered.length >= 2 ? numbered : heads;
  return steps.length >= 2 ? steps.slice(0, 12).map((s) => titleOf(s)) : [];
}

type RawTask = Raw & { id: string };
type Drawn = { tasks: RawTask[]; edges: [string, string, string][] };

/** The last few things a card's calls did, oldest first, for its Activity. */
const tailOf = (calls: readonly Call[], cwd: string, n = 8): string[] => calls.slice(-n).map((c) => `${doing(c, cwd)}${c.done && c.error ? "  (failed)" : ""}`);

/** What a card is doing now, in one line: the call still out, else its last one; over, the agent's last words. */
function line(calls: readonly Call[], said: readonly string[], over: boolean, cwd: string): string {
  const last = over ? undefined : calls.filter((c) => !c.done).at(-1) ?? calls.at(-1);
  if (last) return doing(last, cwd);
  return titleOf(said.at(-1) ?? "", 160) || (calls.length ? doing(calls.at(-1)!, cwd) : "");
}

/** One session's cards and the lines between them. `band`: the sub-goal they stand under, when the page draws
 *  more than one session. */
export function cards(m: Model, st: Status, now: number, band: string | null): Drawn {
  // the end of a session's id, not its start: Codex's begins with the time, which two sessions a minute apart share
  const key = m.id.slice(-12) || "session", id = (k: string) => `${key}/${k}`;
  const who = m.agent === "codex" ? "Codex" : "Claude Code";
  const idle = m.last ? Math.max(0, Math.round((now - ms(m.last)) / 1000)) : null;
  // a card still under way says what the session says: working, needs you (a diamond, as a task that asks), or idle
  const under = (): { state: Word; needs_you: boolean; says: string } =>
    st === "working" ? { state: "running", needs_you: false, says: "working" }
      : st === "needs you" ? { state: "running", needs_you: true, says: "needs you" } : { state: "waiting", needs_you: false, says: "idle" };
  const base = (k: string, title: string, full: string, kind: Card["kind"], side = ""): RawTask => ({
    id: id(k), title, full, parent: band, agent: who, model: m.model, scope: [], needs: [], check: null, card: { session: m.id, kind, says: "", side, receipt: null },
  });
  /** What a card did, after the fact: its receipt, and the files of it for the card's chip. */
  const did = (t: RawTask, calls: readonly Call[]) => {
    const r = receipt(calls, m.cwd);
    (t.card as Card).receipt = r;
    t.changed = r.changed.map((c) => c.file);
    return t;
  };
  const say = (t: RawTask, s: { state: Word; needs_you?: boolean; says: string }) => {
    Object.assign(t, { state: s.state, needs_you: s.needs_you === true, idle: s.state === "running" ? idle : null });
    (t.card as Card).says = s.says;
    return t;
  };
  const tasks: RawTask[] = [], edges: Drawn["edges"] = [];

  // a card a request, the newest `SHOWN`. What the agent wrote for itself in a request is drawn after it, the first
  // of these that it has: its task list, a card a task in the list's order; the plan it put to the person, a card
  // a step; the subagents and workflows it launched, a card each, fanning out from the request
  const turns = m.turns.filter((t) => t.text || t.calls.length), shown = turns.slice(-SHOWN), before = turns.slice(0, -SHOWN);
  let prev: string[] = [];
  if (before.length) {
    const calls = before.flatMap((t) => t.calls);
    const c = base("earlier", `${before.length} earlier request${before.length > 1 ? "s" : ""}`, before.map((t) => titleOf(t.text)).filter(Boolean).join("\n"), "earlier");
    Object.assign(did(c, calls), { tail: [], note: titleOf(before[0]!.text, 160) });
    tasks.push(say(c, { state: "done", says: "done" }));
    prev = [c.id];
  }
  const last = turns.at(-1);
  for (const t of shown) {
    const over = t !== last || t.ended;
    const c = base(`r${t.n}`, titleOf(t.text) || "continued", t.text, "request");
    Object.assign(did(c, t.calls), { tail: tailOf(t.calls, m.cwd), note: line(t.calls, t.said, over, m.cwd) });
    tasks.push(say(c, over ? { state: "done", says: t.stopped ? "interrupted" : "done" } : under()));
    for (const p of prev) edges.push([p, c.id, "needs"]);
    prev = [c.id];
    const steps = t.todos.length ? [] : planSteps(t.plan);
    for (const todo of t.todos) {
      const d = base(`r${t.n}t${todo.id}`, titleOf(todo.title), todo.title, "task"), now_ = todo.state === "in_progress";
      Object.assign(did(d, todo.calls), { tail: tailOf(todo.calls, m.cwd), note: now_ ? line(todo.calls, [todo.doing], over, m.cwd) : "" });
      if (todo.state === "pending" && !todo.calls.length) (d.card as Card).receipt = null; // not started: nothing happened to give a receipt of
      // a task left in progress by a request that is over was not finished: the list says so, and so does its card
      tasks.push(say(d, todo.state === "completed" ? { state: "done", says: "done" } : now_ ? (over ? { state: "waiting", says: "left in progress" } : under()) : { state: "waiting", says: "not started" }));
      edges.push([prev[0]!, d.id, "needs"]);
      prev = [d.id];
    }
    // a plan's steps: the file says the plan, never which step is under way
    steps.forEach((step, i) => {
      const d = say(base(`r${t.n}p${i + 1}`, step, step, "step"), { state: "waiting", says: "planned" });
      tasks.push(d);
      edges.push([prev[0]!, d.id, "needs"]);
      prev = [d.id];
    });
    if (t.todos.length || steps.length) continue;
    const subs = m.subs.filter((s) => s.turn === t.n), after: string[] = [];
    subs.forEach((s, i) => {
      const d = sub(m, s, `r${t.n}s${i + 1}`, base, over);
      tasks.push(say(d.task, d.over ? { state: s.call.error ? "came back" : "done", says: s.call.error ? "failed" : "done" } : under()));
      edges.push([c.id, d.task.id, "needs"]);
      if (d.over) after.push(d.task.id);
    });
    // the next request follows what was over before it: the subagents that ended, else the request itself
    if (after.length) prev = after;
  }
  return { tasks, edges };
}

/** A subagent's or a workflow's card: its title as the agent named it, what its own thread did. Codex's file says a
 *  subagent's launch and never its end: it is over with the request that launched it. */
function sub(m: Model, s: Sub, k: string, base: (k: string, title: string, full: string, kind: Card["kind"], side?: string) => RawTask, turnOver: boolean): { task: RawTask; over: boolean } {
  const sides = sidesOf(m, s), calls = sides.flatMap((x) => x.calls), said = sides.at(-1)?.said ?? [];
  const over = m.agent === "codex" ? turnOver : subOver(m, s);
  const title = titleOf(s.title) || (s.kind === "workflow" ? "workflow" : "subagent");
  const task = base(k, title, str(s.call.input.prompt) || s.title, s.kind, s.kind === "subagent" ? sides[0]?.id ?? "" : "");
  const r = receipt(calls, m.cwd);
  (task.card as Card).receipt = r;
  Object.assign(task, { agent: s.kind === "workflow" ? "workflow" : s.type || "subagent", model: str(s.call.more.resolvedModel) || str(s.call.input.model),
                        changed: r.changed.map((c) => c.file), tail: tailOf(calls, m.cwd), note: line(calls, said, over, m.cwd) });
  return { task, over };
}

/** What Home and a page's band say of a session. */
export function info(m: Model, st: Status, open = false, git: GitFacts | null = null): SessionInfo {
  const first = m.turns.find((t) => t.text)?.text ?? "";
  return { id: m.id, agent: m.agent, title: m.title || titleOf(first) || "a session with no request yet", status: st, cwd: m.cwd, branch: m.branch, file: m.file, last: m.last,
           requests: m.turns.filter((t) => t.text).length, error: m.error, open,
           // the session as a whole: every call of its own thread and of its subagents', in the order they were made
           receipt: receipt([...m.calls.values()], m.cwd), git };
}

/** The sessions of one page as one snapshot: a session alone fills the page; two or more are a band each, under
 *  its title. `live`: each session's own process record, by its id, where there is one. */
export function snapshot(models: readonly Model[], now: number, live: ReadonlyMap<string, Live> = new Map(), git: ReadonlyMap<string, GitFacts> = new Map()): State {
  const many = models.length > 1;
  const sessions: SessionInfo[] = [], tasks: RawTask[] = [], edges: Drawn["edges"] = [], goals: Raw[] = [];
  for (const m of models) {
    const st = status(m, now, live.get(m.id)), s = info(m, st, live.has(m.id) && live.get(m.id)!.status !== "gone", git.get(m.id) ?? null), band = many ? `session ${m.id}` : null;
    sessions.push(s);
    if (band) goals.push({ id: band, title: s.title, parent: null, state: "open", check: null });
    const d = cards(m, st, now, band);
    tasks.push(...d.tasks);
    edges.push(...d.edges);
  }
  // a file two of the page's sessions wrote is said on both, and on each card of theirs that wrote it
  const folder = new Map(models.map((m) => [m.id, m.cwd]));
  const wrote = sessions.map((s) => ({ id: s.id, title: s.title, cwd: folder.get(s.id) ?? "", files: s.receipt?.changed.map((c) => c.file) ?? [] }));
  const others = (id: string) => wrote.filter((w) => w.id !== id);
  for (const s of sessions) if (s.receipt) s.receipt.flags.push(...shared(s.receipt, folder.get(s.id) ?? "", others(s.id)));
  for (const t of tasks) { const c = t.card as Card; if (c.receipt) c.receipt.flags.push(...shared(c.receipt, folder.get(c.session) ?? "", others(c.session))); }
  const running = tasks.filter((t) => t.state === "running" && !t.needs_you).length, need = tasks.filter((t) => t.needs_you).length;
  return parseState(JSON.stringify({
    schema: 1, graphene: "", repo: models[0]?.cwd ?? "", goal: "", asked: sessions.length === 1 ? sessions[0]!.title : "", goals, tasks, edges, sessions,
    news: [], run: { going: sessions.some((s) => s.status === "working"), pid: null },
    scoreboard: { need_you: need, running, proven: tasks.filter((t) => t.state === "done").length, total: tasks.length },
  }));
}
