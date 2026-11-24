// The shape of `graphene state --json` (schema 1) and a parse that fills what is missing with defaults
// and ignores what it does not know, so an older or newer CLI still draws a plan. Pure: no VS Code here.

export type Word = "running" | "review" | "came back" | "ready" | "waiting" | "proposed" | "done" | "yours";
export const WORDS: readonly Word[] = ["running", "review", "came back", "ready", "waiting", "proposed", "done", "yours"];

/** A state as the editor says it to a person: plain words. The CLI and the cockpit keep their own. */
export const SAY: Record<Word, string> = {
  running: "working", review: "to review", "came back": "needs help", ready: "ready", waiting: "waiting",
  proposed: "suggested", done: "done", yours: "yours",
};

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

/** A write the gate refused: the path, when (as the log stamps it), and the tool that tried it. */
export interface Stop { path: string; at: string; how: string }

/** What a task's attempts read and wrote, in tokens, from the meter. `cached`: how much of the reading came from
 *  cache; null when the meter does not say. */
export interface Tokens { read: number; cached: number | null; written: number; turns: number }

/** How a write outside a task's files is held, by what the tests prove and nothing more: refused before the
 *  write, caught when the task finishes, or not held. "" from an older CLI: nobody has said, so not held. */
export interface Held { state: "refused" | "caught" | "none" | ""; by: string }

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
  /** Its scope as the files it covers now (at most 200 named; `filesN` counts them all), the ones its agent
   *  has written in the attempt going now, every write of its that was refused, its check's verdict on the
   *  code as it was (red, passes, outside, environment, landed) and after the work (passed, failed), the
   *  tokens its attempts read and wrote, and how it is held. An older CLI says none of them. */
  files: string[];
  filesN: number;
  touched: string[];
  stops: Stop[];
  checked: { before: string | null; after: string | null };
  tokens: Tokens | null;
  held: Held;
  /** A command step (a workflow's `run:`): the command that runs with no agent, its exit code its check; null
   *  for a step an agent or a person does. `leaves`: its command pushes or opens a pull request, so it is drawn
   *  past the "leaves your machine" line and waits for your approval. */
  command: string | null;
  leaves: boolean;
  /** What the snapshot does not say and `graphene plan --json` does (`withContracts`): the attempts set on the
   *  task itself (null: unset, the limits' number decides), whether it waits for your approval and whose it
   *  is ("agent", or a person's name). `signoff` null and `owner` "": not read yet. */
  planned: number | null;
  signoff: boolean | null;
  owner: string;
  /** Set on a card drawn from a session; a plan's task has none. */
  card?: Card;
}

/** A receipt: what a card, or a page's session, says about the work after it happened (sessions/receipt.ts). The
 *  files it changed; each test or check tool's last run with what decided its verdict; `tests`, the three honest
 *  states and the fourth it does not hide (ran, result not seen); and what is worth a second look, each a fact
 *  with the line that shows it, a guess said to be one. */
export interface Changed { file: string; how: "created" | "edited" | "deleted"; outside: boolean }
export interface Check { tool: string; kind: "test" | "check"; command: string; verdict: "passed" | "failed" | "unseen" | "none"; why: string; at: string }
export type FlagKind = "push" | "pull request" | "delete" | "force" | "hard reset" | "test edited after it failed" | "written by two sessions"
  | "outside the folder";
export interface Flag { kind: FlagKind; line: string; note: string; guess: boolean }
export type Tests = "passed" | "failed" | "none" | "unseen";
export interface Receipt { changed: Changed[]; checks: Check[]; tests: Tests; flags: Flag[] }

/** What git says of a session's folder since the session was first seen. `noted`: its HEAD and dirty files were
 *  noted then (a session Graphene did not see begin has no such note, and nothing is claimed of it). `compared`:
 *  the folder has been compared with that note since; until it has, nothing is said of what moved. `commits`:
 *  how many HEAD has now that it did not have then. `dropped`: how many it had then that it does not have now (a
 *  reset, or another branch). `unexplained`: the files that changed with no tool call of the session's that wrote
 *  them. */
export interface GitFacts { noted: boolean; compared: boolean; commits: number; dropped: number; unexplained: string[] }

/** A card that comes from a session's own file (sessions/), not from a plan. `says`: its state in a session's
 *  words (working, needs you, idle, done, interrupted, failed, not started), which the plan's `state` only
 *  approximates. `side`: a subagent's id, whose own transcript is the card's terminal view. */
export interface Card {
  session: string;
  kind: "request" | "task" | "step" | "subagent" | "workflow" | "earlier";
  says: string;
  side: string;
  /** What it did, after the fact; null for a card with no work of its own to read (a plan's step). */
  receipt: Receipt | null;
}

/** A session on a page: one agent conversation, as Claude Code or Codex records it on disk. `status`: needs you
 *  only when the file proves it, else working or idle. `error`: a file that could not be read, in one line. */
export interface SessionInfo {
  id: string;
  agent: "claude" | "codex";
  title: string;
  status: "working" | "needs you" | "idle";
  cwd: string;
  branch: string;
  file: string;
  last: string; // when it last wrote, ISO
  requests: number;
  error: string;
  /** A running agent has it open (its own record of its process says so): it is not offered to be resumed, as two
   *  writers on one session corrupt it. */
  open: boolean;
  /** The receipt of the session as a whole, its subagents' work included, and what git says of its folder. */
  receipt: Receipt | null;
  git: GitFacts | null;
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

/** A step the planner has written so far: a plan-text line that is complete, with those of its own lines that
 *  are. Not a task yet: nothing of it is in the plan until the proposals land, and then it is one of `tasks`. */
export interface DraftStep {
  id: string;
  title: string;
  parent: string | null;
  leaf: boolean; // false once a step is written under it: a sub-goal, drawn as a band
  scope: string[];
  check: string | null;
  needs: string[];
}

/** A planner is writing a plan now. `live`: its stream carries the plan's text as it is written, so its steps
 *  appear one by one; otherwise the plan arrives whole and `steps` stays empty until it does. */
export interface Drafting {
  by: string;
  live: boolean;
  steps: DraftStep[];
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
  /** The newest ask, whole: the news cuts it at 60 characters. "" from an older CLI, which does not say it. */
  asked?: string;
  /** What the person last asked for, as the editor keeps it (session.ts) once the news no longer says it. */
  kept?: string;
  first: string;
  planner: string;
  executor: string;
  envelope: Envelope;
  auto: Auto | null;
  run: { going: boolean; pid: number | null };
  /** The repository's top-level entries (a folder ends with `/`), and the shell commands the executor's own
   *  command line lets it run without asking (null: it names no list, so any command). */
  tree: string[];
  allows: string[] | null;
  drafting: Drafting | null; // a planner is writing: the steps it has written so far
  spent: number | null;
  scoreboard: Scoreboard;
  width: number | null;
  questions: Question[];
  goals: Goal[];
  tasks: Task[];
  edges: [string, string, string][];
  news: string[];
  /** The sessions this page draws, when its source is their files and not a plan (sessions/): each a band of
   *  cards. Absent for a plan. */
  sessions?: SessionInfo[];
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
  const files = strs(r.files), checked = obj(r.checked), tokens = r.tokens && typeof r.tokens === "object" ? obj(r.tokens) : null;
  const held = str(obj(r.held).state);
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
    files, filesN: int(r.files_n, files.length), touched: strs(r.touched),
    stops: list(r.stops).map((x) => ({ path: str(x.path), at: str(x.at), how: str(x.how) })).filter((x) => x.path),
    checked: { before: optStr(checked.before), after: optStr(checked.after) },
    tokens: tokens && { read: int(tokens.read, 0), cached: num(tokens.cached), written: int(tokens.written, 0), turns: int(tokens.turns, 0) },
    held: { state: held === "refused" || held === "caught" || held === "none" ? held : "", by: str(obj(r.held).by) },
    command: optStr(r.command), leaves: bool(r.leaves),
    planned: null, signoff: null, owner: "",
    ...(r.card && typeof r.card === "object" ? { card: parseCard(obj(r.card)) } : {}),
  };
}

const KINDS: readonly Card["kind"][] = ["request", "task", "step", "subagent", "workflow", "earlier"];

function parseCard(r: Raw): Card {
  const kind = str(r.kind) as Card["kind"];
  return { session: str(r.session), kind: KINDS.includes(kind) ? kind : "request", says: str(r.says), side: str(r.side), receipt: parseReceipt(r.receipt) };
}

const one = <T extends string>(v: unknown, all: readonly T[], d: T): T => (all.includes(v as T) ? (v as T) : d);
const FLAGS: readonly FlagKind[] = ["push", "pull request", "delete", "force", "hard reset", "test edited after it failed", "written by two sessions", "outside the folder"];

function parseReceipt(v: unknown): Receipt | null {
  if (v === null || typeof v !== "object" || Array.isArray(v)) return null;
  const r = v as Raw;
  return {
    changed: list(r.changed).filter((c) => str(c.file)).map((c) => ({ file: str(c.file), how: one(c.how, ["created", "edited", "deleted"] as const, "edited"), outside: bool(c.outside) })),
    checks: list(r.checks).filter((c) => str(c.tool)).map((c) => ({ tool: str(c.tool), kind: one(c.kind, ["test", "check"] as const, "check"), command: str(c.command),
                                                              verdict: one(c.verdict, ["passed", "failed", "unseen", "none"] as const, "unseen"), why: str(c.why), at: str(c.at) })),
    tests: one(r.tests, ["passed", "failed", "none", "unseen"] as const, "none"),
    // a kind this build does not know is not a flag it can word: left out, never guessed at
    flags: list(r.flags).filter((f) => FLAGS.includes(f.kind as FlagKind)).map((f) => ({ kind: f.kind as FlagKind, line: str(f.line), note: str(f.note), guess: bool(f.guess) })),
  };
}

function parseSession(r: Raw): SessionInfo {
  const status = str(r.status);
  return { id: str(r.id), agent: r.agent === "codex" ? "codex" : "claude", title: str(r.title),
           status: status === "working" || status === "needs you" ? status : "idle",
           cwd: str(r.cwd), branch: str(r.branch), file: str(r.file), last: str(r.last), requests: int(r.requests, 0), error: str(r.error), open: bool(r.open),
           receipt: parseReceipt(r.receipt),
           git: r.git && typeof r.git === "object" ? { noted: bool(obj(r.git).noted), compared: bool(obj(r.git).compared), commits: int(obj(r.git).commits, 0), dropped: int(obj(r.git).dropped, 0), unexplained: strs(obj(r.git).unexplained) } : null };
}

export interface Contract { planned: number | null; signoff: boolean; owner: string }

/** `graphene plan --json`, read for what the snapshot leaves out of a task: its own attempts, your approval,
 *  its owner. Empty for anything that is not that JSON. */
export function parseContracts(text: string): Map<string, Contract> {
  const out = new Map<string, Contract>();
  try {
    for (const n of list(obj(JSON.parse(text)).nodes)) {
      const forks = num(n.forks);
      if (str(n.id)) out.set(str(n.id), { planned: forks !== null && forks >= 1 ? Math.trunc(forks) : null, signoff: bool(n.signoff), owner: str(n.owner, "agent") });
    }
  } catch { /* not the plan's JSON: nothing known */ }
  return out;
}

/** The snapshot with each task's contract filled in; a task the plan's JSON did not name stays unread. */
export function withContracts(s: State, contracts: Map<string, Contract>): State {
  return { ...s, tasks: s.tasks.map((t) => ({ ...t, ...(contracts.get(t.id) ?? { planned: null, signoff: null, owner: "" }) })) };
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
  const drafting = r.drafting && typeof r.drafting === "object" && !Array.isArray(r.drafting) ? obj(r.drafting) : null; // an older CLI says nothing: no planner is seen writing
  return {
    schema: int(r.schema, 1), graphene: str(r.graphene), repo: str(r.repo), cursor: int(r.cursor, 0),
    replay: str(replay.shown) ? { shown: str(replay.shown), day: str(replay.day), repository: str(replay.repository) } : null,
    stand_in: bool(r.stand_in),
    goal: str(r.goal), asked: str(r.asked), first: str(r.first), planner: str(r.planner), executor: str(r.executor),
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
    tree: strs(r.tree), allows: Array.isArray(r.allows) ? strs(r.allows) : null,
    drafting: drafting && {
      by: str(drafting.by), live: bool(drafting.live),
      steps: list(drafting.steps).map((d) => ({
        id: str(d.id), title: str(d.title), parent: typeof d.parent === "string" ? d.parent : null, leaf: d.leaf !== false,
        scope: strs(d.scope), check: typeof d.check === "string" ? d.check : null, needs: strs(d.needs),
      })).filter((d) => d.id),
    },
    spent: num(r.spent),
    scoreboard: { need_you: int(sb.need_you, 0), running: int(sb.running, 0), proven: int(sb.proven, 0),
                  total: int(sb.total, tasks.length) },
    width: num(r.width),
    questions: list(r.questions).map((q) => ({
      id: str(q.id), text: str(q.text), default: typeof q.default === "string" ? q.default : null,
      options: strs(q.options), about: typeof q.about === "string" ? q.about : null, kind: str(q.kind, "question"),
    })).filter((q) => q.id),
    goals, tasks, edges, news: strs(r.news),
    ...(Array.isArray(r.sessions) ? { sessions: list(r.sessions).map(parseSession).filter((x) => x.id) } : {}),
  };
}

/** `$0.42`; cents under a cent keep their digits (`$0.004`), less than a tenth of a cent is `<$0.001`, not
 *  `$0.000`; nothing at all for no spend. */
export function usd(n: number | null | undefined): string {
  if (n === null || n === undefined || !(n > 0)) return "";
  if (n < 0.001) return "<$0.001";
  return n >= 0.01 ? `$${n.toFixed(2)}` : `$${n.toFixed(3)}`;
}

/** What the plan is for: its goal, else what the person last asked for (`graphene ask` sets no goal), from the
 *  news or, once it scrolled out of them, as the editor kept it; "" when nobody knows. */
export function headline(s: Pick<State, "goal" | "news" | "asked" | "kept">): string {
  if (s.goal) return s.goal;
  const line = [...s.news].reverse().find((l) => l.startsWith("you asked: "))?.slice("you asked: ".length);
  if (!line) return s.kept ?? "";
  // the news line is cut (`…`); the snapshot's `asked` is that same ask whole, and the header has the room
  const whole = s.asked ?? "";
  return whole && (whole === line || (line.endsWith("…") && whole.startsWith(line.slice(0, -1)))) ? whole : line;
}

/** The plan's words for a Markdown hover, as text: an agent writes some of them (a title it proposed, a command
 *  it ran, a note), so every Markdown character is escaped and none is read as a link, an image, HTML or an
 *  icon; spaces stay spaces, so a long line still wraps, and a line break is a space. */
export function mdText(s: string): string {
  return s.replace(/\s+/g, " ").replace(/[\\`*_{}[\]()#+\-.!|<>~$&:]/g, "\\$&");
}

/** A practice run (every model call went to the scripted stand-in) or a replay (no model runs): nothing is spent
 *  here, so no screen says a cost, the status bar, auto's line and the graph's (graph.ts sends it none) alike. */
export const free = (s: Pick<State, "stand_in" | "replay">): boolean => s.stand_in || Boolean(s.replay);
/** The snapshot a page is sent: a free one with no cost in it to put on a card, a lane, an attempt or a Cost row. */
export function unpriced(s: State): State {
  return free(s) ? { ...s, spent: null, tasks: s.tasks.map((t) => ({ ...t, usd: null, forks: t.forks.map((f) => ({ ...f, usd: null })) })) } : s;
}

/** The status bar's words: `2 working · 1 needs you · $0.42`, `3 of 6 done` when nothing runs; while auto plans,
 *  runs and fixes on its own, its round first (`on its own, round 2 · …`), and that it waits for you when no task
 *  says so. Not once it is done: the counts say what is left, and "done" beside three waiting tasks read as all done. */
export function summary(s: State): string {
  const sb = s.scoreboard;
  const parts: string[] = [];
  if (sb.running) parts.push(`${sb.running} working`);
  if (sb.need_you) parts.push(sb.need_you === 1 ? "1 needs you" : `${sb.need_you} need you`);
  if (!parts.length) parts.push(sb.total ? `${sb.proven} of ${sb.total} done` : "no plan yet");
  const spent = usd(s.spent);
  if (spent && !free(s)) parts.push(spent);
  const a = autoLine(s) ? s.auto : null;
  if (a?.stage === "waits" ? !sb.need_you : a?.stage && a.stage !== "done") parts.unshift(a!.stage === "waits" ? "waits for you" : `on its own, round ${a!.round ?? 1}`);
  return parts.join(" · ");
}

/** What auto is at, in the screen's words: it is the plan run on its own (Stop after the plan off), so it is said so,
 *  not by the CLI's word. Waiting, it is not on its own: `waits for you`, as the CLI, the status bar and the toast say. */
const AT: Record<string, string> = { planning: "planning on its own", running: "running on its own", checking: "checking the goal on its own",
                                     fixing: "fixing on its own", done: "done on its own", waits: "waits for you" };

/** The auto header: `waits for you: the goal's check is still red · round 2 of 3 · $1.37 of $2.00` (a
 * round is the first plan or a fix round, `rounds + 1` in all). What it is at and why come first, so a tab too narrow
 * for the line cuts the bookkeeping, not the reason it stopped; empty when auto is off. */
export function autoLine(s: State): string {
  const a = s.auto;
  if (!a || s.envelope.auto !== "on" && !a.stage) return "";
  const parts = [`${AT[a.stage] ?? (a.stage ? `${a.stage} on its own` : "on its own")}${a.why ? `: ${screenWords(a.why)}` : ""}`];
  if (a.round !== null) parts.push(a.rounds !== null ? `round ${a.round} of ${a.rounds + 1}` : `round ${a.round}`);
  const spent = a.spent === null ? "" : usd(a.spent) || "$0.00";
  if (spent && !free(s)) parts.push(a.budget !== null ? `${spent} of ${usd(a.budget) || "$0.00"}` : spent);
  return parts.join(" · ");
}

/** What a change in auto mode's round says to the person, once, as it happens: it waits for them, it plans a fix,
 * or it is done. Null when nothing worth a notification changed (or on the first read, which is no change). */
export function autoNews(before: State | null, now: State): { kind: "waits" | "fixing" | "done"; text: string } | null {
  const was = before?.auto, a = now.auto;
  if (!before || !a || !a.stage || (was?.stage === a.stage && was?.round === a.round)) return null;
  const money = a.spent === null || free(now) ? "" : ` · ${usd(a.spent) || "$0.00"}${a.budget !== null ? ` of ${usd(a.budget) || "$0.00"}` : ""}`;
  if (a.stage === "waits") return { kind: "waits", text: `Graphene waits for you: ${screenWords(a.why) || "see the plan"}` };
  if (a.stage === "fixing") return { kind: "fixing", text: `Graphene, on its own: the goal's check failed${a.why ? ` (${screenWords(a.why)})` : ""}; round ${a.round} plans the fix` };
  if (a.stage === "done") return { kind: "done", text: `Graphene finished on its own: the goal's check passed in round ${a.round}${money}` };
  return null;
}

/** Translate engine prose at the display boundary; keep copied commands and file paths verbatim. */
export function screenWords(text: string): string {
  const words: Record<string, string> = { fork: "attempt", forks: "attempts", leaf: "task", leaves: "tasks", node: "task", nodes: "tasks", scope: "files" };
  return text.replace(/`[^`]*`|\bgraphene[^\n]*|(?<![\w./-])(forks?|leaves|leaf|nodes?|scope)(?![\w./-])/gi,
                      (word) => words[word.toLowerCase()] ?? word);
}
