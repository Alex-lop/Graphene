// Every change the extension makes is a graphene command; here is each one's argv, pure, so a test can
// read them. The extension runs them with `execFile` in the plan's folder, with the agent marks taken out
// of the environment (`scrub`): a click in VS Code is the person's, whatever shell the editor came from.

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
export const stop = (): string[] => ["run", "--stop"];
export const runReady = (): string[] => ["run", "--parallel", "4"];
export const watch = (): string[] => ["watch"];
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
