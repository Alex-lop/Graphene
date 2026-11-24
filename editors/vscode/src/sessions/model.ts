// A session as it stands: the requests the person made and what the agent did for each, the task list or
// plan the agent wrote for itself, and the subagents and workflows it launched. Built an event at a time
// (`fold`), so a transcript is read once and then only as it grows. Pure: no VS Code, no file system.
import { obj, str, list, SUBAGENT, WORKFLOW, type Agent, type Ev, type Raw } from "./events.ts";

/** A tool call and, once it is back, its result. Never a card: the activity inside one. */
export interface Call {
  id: string; name: string; input: Raw; at: string; side: string;
  done: boolean; error: boolean; out: string; err: string; interrupted: boolean; exit: number | null; endAt: string; more: Raw;
}

/** A task on the agent's own list (TodoWrite, or TaskCreate and TaskUpdate). `calls`: what it did while this was the
 *  one in progress. */
export interface Todo { id: string; title: string; doing: string; state: "pending" | "in_progress" | "completed"; calls: Call[]; at: string }

/** One request the person made, and what the agent did for it on the session's own thread: its calls, its last
 *  words, and the task list or the plan it wrote for itself while answering it. */
export interface Turn {
  n: number; at: string; text: string;
  calls: Call[]; said: string[];
  todos: Todo[]; plan: string;
  ended: boolean; stopped: boolean; endAt: string;
}

/** A subagent or a workflow the agent launched: the call that launched it, in the request it was launched from. */
export interface Sub { id: string; kind: "subagent" | "workflow"; title: string; type: string; turn: number; call: Call }

/** A subagent's own thread, as its transcript says it. `call`: the tool call that launched it, where the
 *  transcript's own file says so; `prompt`: its first line, which is that call's prompt word for word. */
export interface Side { id: string; call: string; run: string; prompt: string; calls: Call[]; said: string[]; ended: boolean; last: string; file: string }

export interface Model {
  agent: Agent; id: string; file: string; cwd: string; branch: string; title: string; head: string; model: string;
  turns: Turn[]; subs: Sub[]; sides: Map<string, Side>;
  calls: Map<string, Call>;
  first: string; last: string;
  /** The task in progress now: what a call is counted under. */
  doing: Todo | null;
  /** A line this could not read, the last one: said on the page in one line. */
  error: string;
}

export const empty = (agent: Agent, file: string, id = ""): Model => ({
  agent, id, file, cwd: "", branch: "", title: "", head: "", model: "",
  turns: [], subs: [], sides: new Map(), calls: new Map(), first: "", last: "", doing: null, error: "",
});

const SAID = 40; // the agent's last words kept for a card: the terminal view reads the file itself

/** The thread a subagent's lines belong to, made when its first line is read. */
export function sideOf(m: Model, id: string): Side {
  let s = m.sides.get(id);
  if (!s) { s = { id, call: "", run: "", prompt: "", calls: [], said: [], ended: false, last: "", file: "" }; m.sides.set(id, s); }
  return s;
}

/** The request under way; a session that begins with no request of its own (a resumed one, a compacted one)
 *  has one made for it, with no words. */
function turn(m: Model, at: string): Turn {
  let t = m.turns.at(-1);
  if (!t) { t = newTurn(1, at, ""); m.turns.push(t); }
  return t;
}

const newTurn = (n: number, at: string, text: string): Turn => ({ n, at, text, calls: [], said: [], todos: [], plan: "", ended: false, stopped: false, endAt: "" });

/** Every task the agent listed, in any request: TaskUpdate names one by its id long after the request that made it. */
const todos = (m: Model): Todo[] => m.turns.flatMap((t) => t.todos);
const inProgress = (m: Model): Todo | null => todos(m).filter((t) => t.state === "in_progress").at(-1) ?? null;

const keep = (said: string[], text: string) => { said.push(text); if (said.length > SAID) said.shift(); };

/** A workflow's name, out of its script's first lines (`export const meta = { name: '…' }`). */
const workflowName = (script: string): string => /\bname:\s*['"`]([^'"`]{1,80})['"`]/.exec(script.slice(0, 2000))?.[1] ?? "";

/** The agent's own list, as TodoWrite rewrites it whole, for the request it is rewritten in: a task keeps its
 *  calls while its words stay the same. */
function rewrite(m: Model, turn: Turn, items: unknown, at: string) {
  const was = new Map(turn.todos.map((t) => [t.title, t]));
  turn.todos = list(items).map(obj).filter((t) => str(t.content)).map((t, i) => {
    const state = str(t.status);
    return { id: String(i + 1), title: str(t.content), doing: str(t.activeForm), calls: was.get(str(t.content))?.calls ?? [], at: was.get(str(t.content))?.at ?? at,
             state: state === "in_progress" || state === "completed" ? state : "pending" };
  });
  m.doing = inProgress(m);
}

/** One event into the session. */
export function fold(m: Model, ev: Ev): void {
  if (ev.k === "meta") {
    m.id ||= ev.id ?? "";
    m.cwd ||= ev.cwd ?? ""; // where it started: an agent that changes directory is still that folder's session
    m.head ||= ev.head ?? "";
    if (ev.branch) m.branch = ev.branch;
    if (ev.title) m.title = ev.title;
    return;
  }
  if (ev.at) { m.first ||= ev.at; if (ev.at > m.last) m.last = ev.at; }
  const side = ev.k !== "result" && ev.side ? sideOf(m, ev.side) : null;
  if (side && "at" in ev && ev.at > side.last) side.last = ev.at;
  switch (ev.k) {
    case "ask":
      if (side) { side.prompt ||= ev.text; return; }
      m.turns.push(newTurn(m.turns.length + 1, ev.at, ev.text));
      return;
    case "say": {
      if (ev.model) m.model = ev.model;
      if (side) { side.ended = false; return keep(side.said, ev.text); }
      const t = turn(m, ev.at);
      t.ended = t.stopped = false; // it went on (a background task's notice woke it): the request is under way again
      return keep(t.said, ev.text);
    }
    case "tool": {
      if (m.calls.has(ev.id)) return; // a line read twice
      const c: Call = { id: ev.id, name: ev.name, input: ev.input, at: ev.at, side: ev.side, done: false, error: false, out: "", err: "", interrupted: false, exit: null, endAt: "", more: {} };
      m.calls.set(c.id, c);
      m.doing?.calls.push(c);
      if (side) { side.ended = false; side.calls.push(c); return; }
      const t = turn(m, ev.at);
      t.ended = t.stopped = false;
      t.calls.push(c);
      if (c.name === "TodoWrite") rewrite(m, t, c.input.todos, ev.at);
      if (c.name === "ExitPlanMode" && str(c.input.plan)) t.plan = str(c.input.plan);
      if (SUBAGENT.includes(c.name)) m.subs.push({ id: c.id, kind: "subagent", title: str(c.input.description) || str(c.input.prompt), type: str(c.input.subagent_type), turn: t.n, call: c });
      if (c.name === WORKFLOW) m.subs.push({ id: c.id, kind: "workflow", title: str(c.input.name) || workflowName(str(c.input.script)), type: "workflow", turn: t.n, call: c });
      return;
    }
    case "result": {
      const c = m.calls.get(ev.id);
      if (!c) return; // its call is in a part of the file not read (cut off by a compaction): nothing to say of it
      Object.assign(c, { done: true, error: ev.error, out: ev.out, err: ev.err, interrupted: ev.interrupted, exit: ev.exit, endAt: ev.at, more: ev.more });
      if (ev.error) return;
      if (c.name === "TaskCreate") {
        const id = str(obj(ev.more.task).id);
        if (id && !todos(m).some((t) => t.id === id)) turn(m, ev.at).todos.push({ id, title: str(c.input.subject) || str(obj(ev.more.task).subject), doing: str(c.input.activeForm), state: "pending", calls: [], at: ev.at });
      }
      if (c.name === "TaskUpdate") {
        const t = todos(m).filter((x) => x.id === str(c.input.taskId)).at(-1), state = str(c.input.status);
        if (t && state === "deleted") for (const x of m.turns) x.todos = x.todos.filter((y) => y !== t);
        else if (t) {
          if (state === "pending" || state === "in_progress" || state === "completed") t.state = state;
          if (str(c.input.subject)) t.title = str(c.input.subject);
          if (str(c.input.activeForm)) t.doing = str(c.input.activeForm);
        }
        m.doing = inProgress(m);
      }
      if (c.name === WORKFLOW) { const s = m.subs.find((x) => x.id === c.id); if (s && str(ev.more.workflowName)) s.title = str(ev.more.workflowName); }
      return;
    }
    case "end": case "stop": {
      if (side) { side.ended = true; return; }
      const t = m.turns.at(-1);
      if (!t) return;
      t.ended = true; t.endAt = ev.at;
      if (ev.k === "stop") t.stopped = true;
      return;
    }
  }
}

/** The thread of a subagent or a workflow: named by the result of the call that launched it, else by its own file
 *  (the call's id, a workflow's run), else by its first line being the call's prompt. Several for a workflow. */
export function sidesOf(m: Model, s: Sub): Side[] {
  const all = [...m.sides.values()];
  if (s.kind === "workflow") {
    const run = str(s.call.more.runId);
    return run ? all.filter((x) => x.run === run) : [];
  }
  const id = str(s.call.more.agentId), prompt = str(s.call.input.prompt);
  const one = (id && m.sides.get(id)) || all.find((x) => x.call === s.id) || (prompt ? all.find((x) => !x.run && !x.call && x.prompt === prompt) : undefined);
  return one ? [one] : [];
}

/** Whether a launched subagent or workflow is over: its call answered and not left running behind the request,
 *  or its own thread at its end. A workflow launched in the background says its end nowhere in the session's
 *  own file but as a notice, so its agents' threads say it: all of them ended, and one at least. */
export function subOver(m: Model, s: Sub): boolean {
  const c = s.call, behind = c.more.isAsync === true || s.kind === "workflow" || str(c.more.status) === "async_launched";
  if (c.done && (c.error || !behind)) return true;
  const sides = sidesOf(m, s);
  return c.done && sides.length > 0 && sides.every((x) => x.ended);
}
