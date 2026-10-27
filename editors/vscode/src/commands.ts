// Every change the extension makes is a graphene command; here is each one's argv, pure, so a test can
// read them. The extension runs them with `execFile` in the plan's folder, with the agent marks taken out
// of the environment (`scrub`): a click in VS Code is the person's, whatever shell the editor came from.

import { join } from "node:path";

export const MARKS = ["CLAUDECODE", "CLAUDE_CODE_SESSION_ID", "CODEX_SESSION_ID", "CODEX_SANDBOX", "AI_AGENT",
                      "GRAPHENE_NODE", "GRAPHENE_PLANNER", "GEMINI_CLI", "CURSOR_AGENT"] as const;

/** A copy of ``env`` without the marks that make graphene take the caller for an agent. */
export function scrub(env: NodeJS.ProcessEnv): NodeJS.ProcessEnv {
  const out: NodeJS.ProcessEnv = {};
  for (const [k, v] of Object.entries(env)) if (!(MARKS as readonly string[]).includes(k)) out[k] = v;
  return out;
}

/** The same marks as `null`, for a terminal's env: VS Code deletes a variable set to null. */
export function unmarked(): Record<string, null> {
  return Object.fromEntries(MARKS.map((m) => [m, null]));
}

export interface NewStep {
  title: string;
  parent?: string | null;
  needs?: string[];
  scope?: string[];
  check?: string | null;
  signoff?: boolean; // a person's sign-off finishes it: the CLI refuses a leaf with neither a check nor this
}

export const stateJson = (): string[] => ["state", "--json"];
/** The plan's log, a JSON object a line, after the row ``since`` (the Rounds view reads only what is new). */
export const logJson = (since = 0): string[] => ["plan", "log", "--json", ...(since > 0 ? ["--since", String(since)] : [])];
export const stop = (): string[] => ["run", "--stop"];
export const runReady = (): string[] => ["run", "--parallel", "4"];
export const watch = (): string[] => ["watch"];
export const init = (): string[] => ["init"]; // asks which planner and executor: a terminal of its own
/** `graphene key set`, for the host a refusal named (`--endpoint nim`): it asks for the key, hidden, in a terminal. */
export const keySet = (endpoint?: string): string[] => ["key", "set", ...(endpoint ? ["--endpoint", endpoint] : [])];
export const refreshable = (): string[] => ["--version"];

// Free text (a goal, a title, a note, an answer) comes last, after `--`: typed words that start with a dash
// are words to the CLI, not an option it refuses.
export function auto(goal: string, budget?: number | null, planOnly = false): string[] {
  const argv = ["auto"];
  if (budget !== null && budget !== undefined && Number.isFinite(budget)) argv.push("--budget", String(budget));
  if (planOnly) argv.push("--plan"); // the plan your envelope accepts, shown, and nothing run
  return [...argv, "--", goal];
}

export function addStep(s: NewStep): string[] {
  const argv = ["node", "add"];
  if (s.parent) argv.push("--parent", s.parent);
  for (const n of s.needs ?? []) argv.push("--needs", n);
  for (const g of s.scope ?? []) argv.push("--scope", g);
  if (s.check) argv.push("--check", s.check);
  if (s.signoff) argv.push("--signoff");
  return [...argv, "--", s.title];
}

/** Add Step by Hand's four boxes as one step: a check when one was typed, else the person's sign-off. */
export function byHand(title: string, parent: string | null, needs: string[], scope: string, check: string): string[] {
  return addStep({ title: title.trim(), parent, needs, scope: globs(scope), check: check.trim() || null, signoff: !check.trim() });
}

/** B waits on A: adds to B's needs, keeping what it already waits on. */
export const link = (a: string, b: string): string[] => ["node", "set", b, "--add-needs", a];

/** B stops waiting on A; what else B waits on stays, as the CLI reads it then. */
export const unlink = (a: string, b: string): string[] => ["node", "set", b, "--drop-needs", a];

export type Field = "title" | "scope" | "check";

export function editStep(id: string, field: Field, value: string | string[]): string[] {
  const argv = ["node", "set", id];
  if (field === "scope") for (const g of Array.isArray(value) ? value : [value]) argv.push("--scope", g);
  else argv.push(`--${field}`, Array.isArray(value) ? value.join(" ") : value);
  return argv;
}

export const dropStep = (id: string): string[] => ["node", "drop", id];
export const accept = (id?: string | null): string[] => (id ? ["plan", "accept", id] : ["plan", "accept"]);
export const acceptAll = (): string[] => ["plan", "accept"];
export const tell = (id: string, text: string): string[] => ["board", "note", "--about", id, "--", text];
/** One setting of the envelope (`auto`, `budget`, `tasks`, `rounds`, `forks`), as the person sets it. */
export const setting = (key: string, value: string): string[] => ["config", "set", key, value];

/** An id, or a fork's letter, as argv takes it. One that starts with "-" would be read as an option, so it is
 *  refused here, before anything runs. */
export function id(s: string): string {
  if (!s || s.startsWith("-")) throw new Error(`"${s}" is not an id`);
  return s;
}

// -- what lane 3's CLI gives the editor (dev/process/editor/CONTRACT.md) ----------------------------------

/** A task's changes, or one fork's, as JSON the diff editor can open. */
export const nodeDiff = (node: string, fork?: string | null): string[] =>
  ["node", "diff", id(node), ...(fork ? ["--fork", id(fork)] : []), "--json"];
export const pickFork = (node: string, fork: string): string[] => ["node", "pick", id(node), id(fork)];
export const signOff = (node: string): string[] => ["node", "signoff", id(node)];
export const planText = (): string[] => ["plan", "--text"];
/** The tasks Open Changes can show, when the palette gives none: those with a diff to read (running, in
 *  review, came back, done). Compare Forks: those with lettered forks racing. */
type Forked = { id: string; state: string; forks: { letter: string }[] };
export const withChanges = <T extends Forked>(tasks: T[]): T[] =>
  tasks.filter((t) => ["running", "review", "came back", "done"].includes(t.state));
export const forked = <T extends Forked>(tasks: T[]): T[] => tasks.filter((t) => t.forks.some((f) => f.letter));

/** The plan's text from stdin, applied all or none; `since` is the snapshot's cursor when the text was read. */
export const planApply = (since: number): string[] => ["plan", "edit", "--from", "-", "--json", "--since", String(since)];
/** One sentence, one proposed step, after a task or under a goal. The sentence comes after `--`: free text. */
export function askStep(sentence: string, where: { after?: string | null; under?: string | null } = {}): string[] {
  const place = where.after ? ["--after", id(where.after)] : where.under ? ["--under", id(where.under)] : [];
  return ["ask", "--step", ...place, "--", sentence];
}
/** The auto replay played into a directory of its own, with no screen. */
export const demoInto = (dir: string): string[] => ["demo", "--auto", "--into", dir];

/** The snapshot's `replay`: what a replay's store says of itself (`graphene demo --into`). */
export interface Replay { shown: string; day: string; repository: string }

/** `replay` read loosely from `state --json`'s output; null when the store is not a replay's. */
export function parseReplay(stdout: string): Replay | null {
  try {
    const r = (JSON.parse(stdout) as { replay?: unknown }).replay;
    if (!r || typeof r !== "object") return null;
    const o = r as Record<string, unknown>;
    return { shown: String(o.shown ?? ""), day: String(o.day ?? ""), repository: String(o.repository ?? "") };
  } catch { return null; }
}

/** `graphene node diff --json`: `right` null is the working tree in `repo`, a running agent's changes so far. */
export interface Diff {
  repo: string;
  left: string;
  right: string | null;
  files: { path: string; status: string; old: string | null }[];
  said: string[];
}

/** One side of a file's diff: `rev` is a git revision in `repo`; null is the file on disk in `repo`; "" is
 *  nothing, for a side the file is not on (added, or deleted). */
export interface Side { repo: string; path: string; rev: string | null }
export interface Pair { path: string; status: string; left: Side; right: Side }

/** The scheme every side of our diffs is read under, and the query its URI carries: which diff it is in. */
export const SCHEME = "graphene-git";
export interface Query { repo: string; rev: string | null; id: string; fork: string | null }

/** Which diff of ours a tab shows, read from its input: a diff editor's two sides, or a multi-file editor's
 *  list of them (its class is newer than the API this extension is typed against, so it is read loosely).
 *  Null for a tab that is not one of our diffs. */
export function diffOf(input: unknown): { id: string; fork: string | null } | null {
  type U = { scheme?: string; query?: string } | undefined;
  const r = input as { original?: U; modified?: U; textDiffs?: { original?: U; modified?: U }[] } | undefined;
  const sides = r?.textDiffs ? r.textDiffs.flatMap((d) => [d.original, d.modified]) : [r?.original, r?.modified];
  for (const u of sides) {
    if (u?.scheme !== SCHEME || !u.query) continue;
    try {
      const q = JSON.parse(u.query) as Partial<Query>;
      if (typeof q.id === "string") return { id: q.id, fork: typeof q.fork === "string" ? q.fork : null };
    } catch { /* not a query of ours */ }
  }
  return null;
}

export function parseDiff(text: string): Diff {
  const r = JSON.parse(text) as Record<string, unknown>;
  const files = Array.isArray(r.files) ? r.files : [];
  return {
    repo: String(r.repo ?? ""), left: String(r.left ?? ""), right: typeof r.right === "string" ? r.right : null,
    files: files.map((f: Record<string, unknown>) => ({
      path: String(f.path ?? ""), status: String(f.status ?? "M"), old: typeof f.old === "string" ? f.old : null })),
    said: Array.isArray(r.said) ? r.said.map(String) : [],
  };
}

/** Each file as the two sides the diff editor shows: the left at `left`, under the file's old name when it
 *  was renamed; the right at `right`, or on disk when `right` is null. */
export function diffPairs(d: Diff): Pair[] {
  return d.files.map((f) => ({
    path: f.path, status: f.status,
    left: { repo: d.repo, path: f.old ?? f.path, rev: f.status === "A" ? "" : d.left },
    right: { repo: d.repo, path: f.path, rev: f.status === "D" ? "" : d.right },
  }));
}

/** The diff editor's title: whose changes, between what (the multi-file editor adds its own file count). */
export function diffTitle(name: string, fork: string | null | undefined, d: Diff): string {
  const short = (rev: string) => (/^[0-9a-f]{12,}$/.test(rev) ? rev.slice(0, 7) : rev);
  return `${name}${fork ? ` · fork ${fork}` : ""}: ${short(d.left)} → ${d.right === null ? "now" : short(d.right)}`;
}

/** `graphene plan edit --from - --json`: applied, or refused with each fault on its line of the text. */
export interface Applied { applied: boolean; said: string[]; faults: { line: number; text: string }[] }

export function parseApplied(stdout: string, stderr = ""): Applied {
  try {
    const r = JSON.parse(stdout) as Record<string, unknown>;
    const faults = Array.isArray(r.faults) ? r.faults : [];
    return { applied: r.applied === true, said: Array.isArray(r.said) ? r.said.map(String) : [],
             faults: faults.map((f: Record<string, unknown>) => ({ line: Number(f.line) || 1, text: String(f.text ?? "") })) };
  } catch {
    return { applied: false, said: [], faults: [{ line: 1, text: firstLine(stderr, stdout) }] };
  }
}

/** Where each fault goes in the text: its line, 0-based and inside the text, over the line's own words. */
export function faultRanges(faults: { line: number; text: string }[], lines: string[]): { line: number; start: number; end: number; text: string }[] {
  const last = Math.max(0, lines.length - 1);
  return faults.map((f) => {
    const line = Math.min(last, Math.max(0, f.line - 1));
    const words = lines[line] ?? "";
    const start = words.length - words.trimStart().length;
    return { line, start, end: Math.max(start, words.trimEnd().length), text: f.text };
  });
}

/** `graphene ask --step` prints `proposed ID: TITLE` on its first line; null when it did not. */
export function proposed(stdout: string): { id: string; title: string } | null {
  const m = /^proposed (\S+): (.*)$/m.exec(stdout);
  return m ? { id: m[1]!, title: m[2]!.trim() } : null;
}

/** Where a running agent's copy of the repo is: the snapshot's `checkout` for the task or fork; on an older CLI,
 *  the run's own place under the store. */
export function agentCopy(root: string, node: string, checkout: string | null | undefined, fork?: string | null): string {
  if (checkout) return checkout;
  return join(root, ".graphene", "worktrees", fork ? `${node}.${fork}` : node);
}

/** Globs typed in one box: spaces or commas between them. */
export function globs(text: string): string[] {
  return text.split(/[\s,]+/).map((g) => g.trim()).filter(Boolean);
}

export const OLDER = "This Graphene is older than the extension: it needs 0.9 (`uv tool upgrade graphene-map`).";

/** A CLI that does not know an option or a command of this extension's is an older one: that is the line,
 *  wherever the refusal is shown (an id or free text never reaches argv as an option, so nothing else says it). */
export const older = (line: string): string => (/no such (option|command)/i.test(line) ? OLDER : line);

/** The line a refusal is read from: the first non-empty line of stderr, else stdout's, else a stock line. */
export function firstLine(stderr: string, stdout = "", fallback = "graphene said nothing"): string {
  for (const text of [stderr, stdout]) {
    const line = text.split(/\r?\n/).map((l) => l.trim()).find(Boolean);
    if (line) return older(line);
  }
  return fallback;
}

/** A refusal's toast: the command, then why; the CLI's own usage line names the command already. */
export function refused(argv: string[], why: string): string {
  return /^graphene /.test(why) ? why : `graphene ${argv.slice(0, 2).join(" ")}: ${why}`;
}

/** The line a refusal is read from when progress came first (`asking the planner…`): the first non-empty
 *  line of stderr that is not a progress line, one ending in an ellipsis; else `firstLine`'s. */
export function refusal(stderr: string, stdout = "", fallback = "graphene said nothing"): string {
  const line = stderr.split(/\r?\n/).map((l) => l.trim()).find((l) => l && !l.endsWith("…"));
  return line ? older(line) : firstLine(stderr, stdout, fallback);
}

/** Words a model or an agent wrote (a title, a note, the CLI's line quoting one), as a notification or the
 *  status bar shows them: text. VS Code reads `[words](command:…)` there as a link that runs on click and
 *  `$(name)` as an icon; a space inside each pair leaves the words and takes the markup (a hover's words go
 *  through `mdText` instead, which escapes for Markdown proper). */
export function plain(s: string): string {
  return s.replace(/\s+/g, " ").replace(/\]\(/g, "] (").replace(/\$\(/g, "$ (");
}

/** One line for a shell: the goal quoted so the person sees exactly what runs and may edit it. */
export function shellLine(path: string, argv: string[]): string {
  const q = (s: string) => (/^[\w./:=@-]+$/.test(s) ? s : `'${s.replace(/'/g, `'\\''`)}'`);
  return [q(path), ...argv.map(q)].join(" ");
}
