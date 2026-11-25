// What a session's file says, whoever wrote it: one small vocabulary that Claude Code's transcript lines
// (claude.ts) and Codex's rollout lines (codex.ts) are both read into, so the cards, the receipts and the
// terminal view are written once. Pure: no VS Code, no file system.

export type Agent = "claude" | "codex";
export type Raw = Record<string, unknown>;

/** `side`: "" on the session's own thread, a subagent's id on its lines. `at`: the line's timestamp, ISO. */
export type Ev =
  | { k: "meta"; id?: string; cwd?: string; branch?: string; title?: string; head?: string }
  | { k: "ask"; at: string; text: string; side: string } // a request the person made
  | { k: "say"; at: string; text: string; side: string; model: string } // what the agent said
  | { k: "tool"; at: string; id: string; name: string; input: Raw; side: string } // a tool call: activity inside a card
  | { k: "result"; at: string; id: string; error: boolean; out: string; err: string; interrupted: boolean; exit: number | null; more: Raw }
  | { k: "end"; at: string; side: string } // the turn is over: the agent stopped by itself
  | { k: "stop"; at: string; side: string }; // the person interrupted it

export const obj = (v: unknown): Raw => (v !== null && typeof v === "object" && !Array.isArray(v) ? (v as Raw) : {});
export const str = (v: unknown, d = ""): string => (typeof v === "string" ? v : d);
export const list = (v: unknown): unknown[] => (Array.isArray(v) ? v : []);

/** A line as JSON, or null: a truncated line, a line that is not an object, a line of another format. */
export function json(line: string): Raw | null {
  try {
    const v: unknown = JSON.parse(line);
    return v !== null && typeof v === "object" && !Array.isArray(v) ? (v as Raw) : null;
  } catch {
    return null;
  }
}

/** A command's output as a card keeps it: its start (where an exit code is said) and its end (where a test
 *  run sums up), not the megabytes between. */
export const clip = (s: string, head = 1000, tail = 6000): string => (s.length <= head + tail ? s : `${s.slice(0, head)}\n…\n${s.slice(-tail)}`);

/** A tool call's input as a card keeps it: a file's whole text, both sides of an edit and a workflow's script are
 *  cut (the transcript has them; a card says which file). A command and a subagent's prompt stay whole. */
const LONG: readonly string[] = ["content", "old_string", "new_string", "new_source", "script", "edits"];
export function slim(input: Raw): Raw {
  const out: Raw = {};
  for (const [k, v] of Object.entries(input)) out[k] = !LONG.includes(k) ? v : typeof v === "string" ? v.slice(0, 2000) : undefined;
  return out;
}

/** What of a tool's own result record is read later (model.ts, snapshot.ts): never a file's text before an edit. */
const READ: readonly string[] = ["agentId", "status", "isAsync", "runId", "workflowName", "resolvedModel", "task", "type", "filePath"];
export function kept(more: Raw): Raw {
  const out: Raw = {};
  for (const k of READ) if (k in more) out[k] = more[k];
  return out;
}

/** The names both agents' tools are read under: a command, a write to a file, a subagent, a workflow. Codex's
 *  rollout is read into Claude Code's names, so what follows asks one question, not two. */
export const COMMAND = "Bash";
export const WRITES: readonly string[] = ["Edit", "Write", "MultiEdit", "NotebookEdit"];
export const SUBAGENT: readonly string[] = ["Agent", "Task"];
export const WORKFLOW = "Workflow";
