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

export function auto(goal: string, budget?: number | null, planOnly = false): string[] {
  const argv = ["auto", goal];
  if (budget !== null && budget !== undefined && Number.isFinite(budget)) argv.push("--budget", String(budget));
  if (planOnly) argv.push("--plan"); // the plan your envelope accepts, shown, and nothing run
  return argv;
}

export function addStep(s: NewStep): string[] {
  const argv = ["node", "add", s.title];
  if (s.parent) argv.push("--parent", s.parent);
  for (const n of s.needs ?? []) argv.push("--needs", n);
  for (const g of s.scope ?? []) argv.push("--scope", g);
  if (s.check) argv.push("--check", s.check);
  return argv;
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
export const tell = (id: string, text: string): string[] => ["board", "note", text, "--about", id];
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
/** The plan's text from stdin, applied all or none; `since` is the snapshot's cursor when the text was read. */
export const planApply = (since: number): string[] => ["plan", "edit", "--from", "-", "--json", "--since", String(since)];
/** One sentence, one proposed step, after a task or under a goal. The sentence comes after `--`: free text. */
export function askStep(sentence: string, where: { after?: string | null; under?: string | null } = {}): string[] {
  const place = where.after ? ["--after", id(where.after)] : where.under ? ["--under", id(where.under)] : [];
  return ["ask", "--step", ...place, "--", sentence];
}
/** The auto replay played into a directory of its own, with no screen. */
export const demoInto = (dir: string): string[] => ["demo", "--auto", "--into", dir];

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

/** The line a refusal is read from: the first non-empty line of stderr, else stdout's, else a stock line. */
export function firstLine(stderr: string, stdout = "", fallback = "graphene said nothing"): string {
  for (const text of [stderr, stdout]) {
    const line = text.split(/\r?\n/).map((l) => l.trim()).find(Boolean);
    if (line) return line;
  }
  return fallback;
}

/** One line for a shell: the goal quoted so the person sees exactly what runs and may edit it. */
export function shellLine(path: string, argv: string[]): string {
  const q = (s: string) => (/^[\w./:=@-]+$/.test(s) ? s : `'${s.replace(/'/g, `'\\''`)}'`);
  return [q(path), ...argv.map(q)].join(" ");
}
