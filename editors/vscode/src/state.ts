// The shape of `graphene state --json` (schema 1) and a parse that fills what is missing with defaults
// and ignores what it does not know, so an older or newer CLI still draws a plan. Pure: no VS Code here.

export type Word = "running" | "review" | "came back" | "ready" | "waiting" | "proposed" | "done" | "yours";
export const WORDS: readonly Word[] = ["running", "review", "came back", "ready", "waiting", "proposed", "done", "yours"];

export interface Fork {
  letter: string;
  state: string;
  why: string;
  lines: number | null;
  model: string;
  usd: number | null;
  attempts: number;
  idle: number | null; // seconds quiet while it runs
  checkout: string | null; // its own directory while it runs
}

export interface Kept {
  letter: string;
  why: string;
  by: string;
}

export interface Task {
  id: string;
  title: string;
  full: string;
  state: Word;
  parent: string | null;
  scope: string[];
  needs: string[];
  check: string | null;
  agent: string;
  model: string;
  usd: number | null;
  idle: number | null;
  needs_you: boolean;
  tail: string[];
  note: string;
  why: string; // a task that came back: its reason, one line
  checkout: string | null; // where its agent works while it runs, or after it came back
  base: string | null; // the commit its work starts from
  attempts: number;
  offers: Record<string, string[]>; // a task that came back: the cockpit's key -> the command that takes it up
  changed: string[];
  stopped: string[];
  outside: string[];
  forks: Fork[];
  kept: Kept | null;
  hollow: boolean;
}

export interface Replay {
  shown: string; // "a scripted stand-in, no model ran"
  day: string;
  repository: string;
}

export interface Goal {
  id: string;
  title: string;
  parent: string | null;
  state: string;
  check: string | null;
}

export interface Question {
  id: string;
  text: string;
  default: string | null;
  options: string[];
  about: string | null;
  kind: string;
}

export interface Envelope {
  auto: string;
  budget: number | null;
  tasks: number | null;
  rounds: number | null;
  forks: number | null;
  review: string;
  protected: string[];
  readonly: string[];
  checks: string[];
}

export interface Auto {
  round: number | null;
  rounds: number | null;
  stage: string;
  spent: number | null;
  budget: number | null;
  check: string | null;
  why: string;
}

export interface Scoreboard {
  need_you: number;
  running: number;
  proven: number;
  total: number;
}

export interface State {
  schema: number;
  graphene: string;
  repo: string;
  replay: Replay | null; // the store is a replay's (Graphene: Watch the Demo), not a project's
  stand_in: boolean; // the run is against the scripted stand-in, no model
  cursor: number;
  goal: string;
  first: string;
  planner: string;
  executor: string;
  envelope: Envelope;
  auto: Auto | null;
  run: { going: boolean; pid: number | null };
  spent: number | null;
  scoreboard: Scoreboard;
  width: number | null;
  questions: Question[];
  goals: Goal[];
  tasks: Task[];
  edges: [string, string, string][];
  news: string[];
}

type Raw = Record<string, unknown>;

const obj = (v: unknown): Raw => (v !== null && typeof v === "object" && !Array.isArray(v) ? (v as Raw) : {});
const str = (v: unknown, d = ""): string => (typeof v === "string" ? v : d);
const num = (v: unknown): number | null => (typeof v === "number" && Number.isFinite(v) ? v : null);
const int = (v: unknown, d: number): number => (typeof v === "number" && Number.isFinite(v) ? Math.trunc(v) : d);
const bool = (v: unknown): boolean => v === true;
const strs = (v: unknown): string[] => (Array.isArray(v) ? v.filter((x): x is string => typeof x === "string") : []);
const list = (v: unknown): Raw[] => (Array.isArray(v) ? v.map(obj) : []);

const optStr = (v: unknown): string | null => (typeof v === "string" ? v : null);
const argvs = (v: unknown): Record<string, string[]> => {
  const out: Record<string, string[]> = {};
  for (const [k, a] of Object.entries(obj(v))) if (Array.isArray(a) && a.every((x) => typeof x === "string")) out[k] = a as string[];
  return out;
};

export function parseFork(r: Raw): Fork {
  return { letter: str(r.letter), state: str(r.state), why: str(r.why), lines: num(r.lines),
           model: str(r.model), usd: num(r.usd), attempts: int(r.attempts, 0), idle: num(r.idle), checkout: optStr(r.checkout) };
}

export function parseTask(r: Raw): Task {
  const state = str(r.state);
  const kept = r.kept === null || r.kept === undefined ? null : obj(r.kept);
  return {
    id: str(r.id), title: str(r.title), full: str(r.full),
    state: (WORDS as readonly string[]).includes(state) ? (state as Word) : "waiting",
    parent: typeof r.parent === "string" ? r.parent : null,
    scope: strs(r.scope), needs: strs(r.needs), check: typeof r.check === "string" ? r.check : null,
    agent: typeof r.agent === "number" ? String(r.agent) : str(r.agent),
    model: str(r.model), usd: num(r.usd), idle: num(r.idle), needs_you: bool(r.needs_you),
    tail: strs(r.tail), note: str(r.note), why: str(r.why), checkout: optStr(r.checkout), base: optStr(r.base),
    attempts: int(r.attempts, 0), offers: argvs(r.offers), changed: strs(r.changed), stopped: strs(r.stopped),
    outside: strs(r.outside), forks: list(r.forks).map(parseFork),
    kept: kept && str(kept.letter) ? { letter: str(kept.letter), why: str(kept.why), by: str(kept.by) } : null,
    hollow: bool(r.hollow),
  };
}

/** The line `graphene state --json` prints when there is no plan to read, `{"schema": 1, "error": why}`, and the
 *  stream prints when its store went away: its why. Null for a snapshot, or for a line that is not JSON. */
export function errorOf(text: string): string | null {
  try {
    const r = obj(JSON.parse(text));
    return typeof r.error === "string" && r.error ? r.error : null;
  } catch {
    return null;
  }
}

export function parseState(text: string): State {
  const r = obj(JSON.parse(text));
  if (typeof r.error === "string") throw new Error(r.error); // not a snapshot: `errorOf` reads it
  const env = obj(r.envelope);
  const auto = r.auto === null || r.auto === undefined ? null : obj(r.auto);
  const run = obj(r.run);
  const sb = obj(r.scoreboard);
  const tasks = list(r.tasks).map(parseTask).filter((t) => t.id);
  const goals = list(r.goals).map((g) => ({
    id: str(g.id), title: str(g.title), parent: typeof g.parent === "string" ? g.parent : null,
    state: str(g.state, "open"), check: typeof g.check === "string" ? g.check : null,
  })).filter((g) => g.id);
  const known = new Set([...tasks.map((t) => t.id), ...goals.map((g) => g.id)]);
  const edges = (Array.isArray(r.edges) ? r.edges : [])
    .filter((e): e is unknown[] => Array.isArray(e) && typeof e[0] === "string" && typeof e[1] === "string")
    .map((e) => [e[0] as string, e[1] as string, str(e[2], "needs")] as [string, string, string])
    .filter(([a, b]) => known.has(a) && known.has(b));
  const replay = obj(r.replay);
  return {
    schema: int(r.schema, 1), graphene: str(r.graphene), repo: str(r.repo), cursor: int(r.cursor, 0),
    replay: str(replay.shown) ? { shown: str(replay.shown), day: str(replay.day), repository: str(replay.repository) } : null,
    stand_in: bool(r.stand_in),
    goal: str(r.goal), first: str(r.first), planner: str(r.planner), executor: str(r.executor),
    envelope: {
      auto: str(env.auto, "off"), budget: num(env.budget), tasks: num(env.tasks), rounds: num(env.rounds),
      forks: num(env.forks), review: str(env.review, "off"), protected: strs(env.protected),
      readonly: strs(env.readonly), checks: strs(env.checks),
    },
    auto: auto && Object.keys(auto).length
      ? { round: num(auto.round), rounds: num(auto.rounds), stage: str(auto.stage), spent: num(auto.spent),
          budget: num(auto.budget), check: typeof auto.check === "string" ? auto.check : null, why: str(auto.why) }
      : null,
    run: { going: bool(run.going), pid: num(run.pid) },
    spent: num(r.spent),
    scoreboard: { need_you: int(sb.need_you, 0), running: int(sb.running, 0), proven: int(sb.proven, 0),
                  total: int(sb.total, tasks.length) },
    width: num(r.width),
    questions: list(r.questions).map((q) => ({
      id: str(q.id), text: str(q.text), default: typeof q.default === "string" ? q.default : null,
      options: strs(q.options), about: typeof q.about === "string" ? q.about : null, kind: str(q.kind, "question"),
    })).filter((q) => q.id),
    goals, tasks, edges, news: strs(r.news),
  };
}

/** `$0.42`; cents under a cent keep their digits (`$0.004`), less than a tenth of a cent is `<$0.001`, not
 *  `$0.000`; nothing at all for no spend. */
export function usd(n: number | null | undefined): string {
  if (n === null || n === undefined || !(n > 0)) return "";
  if (n < 0.001) return "<$0.001";
  return n >= 0.01 ? `$${n.toFixed(2)}` : `$${n.toFixed(3)}`;
}

/** The plan's words for a Markdown hover, as text: an agent writes some of them (a title it proposed, a command
 *  it ran, a note), so every Markdown character is escaped and none is read as a link, an image, HTML or an
 *  icon; spaces stay spaces, so a long line still wraps, and a line break is a space. */
export function mdText(s: string): string {
  return s.replace(/\s+/g, " ").replace(/[\\`*_{}[\]()#+\-.!|<>~$&:]/g, "\\$&");
}

/** The status bar's words: `2 running · 1 needs you · $0.42`, `3 of 6 done` when nothing runs; while auto is on,
 *  its round first (`auto round 2 · …`), or that it waits for you, or is done. */
export function summary(s: State): string {
  const sb = s.scoreboard;
  const parts: string[] = [];
  if (sb.running) parts.push(`${sb.running} running`);
  if (sb.need_you) parts.push(sb.need_you === 1 ? "1 needs you" : `${sb.need_you} need you`);
  if (!parts.length) parts.push(sb.total ? `${sb.proven} of ${sb.total} done` : "no plan yet");
  const spent = usd(s.spent);
  if (spent) parts.push(spent);
  const a = autoLine(s) ? s.auto : null;
  if (a?.stage) parts.unshift(a.stage === "waits" ? "auto waits" : a.stage === "done" ? "auto done" : `auto round ${a.round ?? 1}`);
  return parts.join(" · ");
}

/** The auto header, as the cockpit's: `auto · round 1 of 3 · running · $0.42 of $2.00` (a round is the first plan or
 * a fix round, `rounds + 1` in all); a fix round says what the goal failed on; empty when auto is off. */
export function autoLine(s: State): string {
  const a = s.auto;
  if (!a || s.envelope.auto !== "on" && !a.stage) return "";
  const parts = ["auto"];
  if (a.round !== null) parts.push(a.rounds !== null ? `round ${a.round} of ${a.rounds + 1}` : `round ${a.round}`);
  if (a.stage) parts.push(a.stage);
  const spent = a.spent === null ? "" : usd(a.spent) || "$0.00";
  if (spent) parts.push(a.budget !== null ? `${spent} of ${usd(a.budget) || "$0.00"}` : spent);
  if (a.why) parts.push(a.why);
  return parts.join(" · ");
}

/** What a change in auto mode's round says to the person, once, as it happens: it waits for them, it plans a fix,
 * or it is done. Null when nothing worth a notification changed (or on the first read, which is no change). */
export function autoNews(before: State | null, now: State): { kind: "waits" | "fixing" | "done"; text: string } | null {
  const was = before?.auto, a = now.auto;
  if (!before || !a || !a.stage || (was?.stage === a.stage && was?.round === a.round)) return null;
  const money = a.spent === null ? "" : ` · ${usd(a.spent) || "$0.00"}${a.budget !== null ? ` of ${usd(a.budget) || "$0.00"}` : ""}`;
  if (a.stage === "waits") return { kind: "waits", text: `Graphene auto waits for you: ${a.why || "see the plan"}` };
  if (a.stage === "fixing") return { kind: "fixing", text: `Graphene auto: the goal's check failed${a.why ? ` (${a.why})` : ""}; round ${a.round} plans the fix` };
  if (a.stage === "done") return { kind: "done", text: `Graphene auto is done: the goal's check passed in round ${a.round}${money}` };
  return null;
}
