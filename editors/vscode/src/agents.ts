// The Agents view: every running agent, a row each (a forked task's running forks are a row each, `3b`): its
// number, task, model and fork, what it is doing now (the last line of its tail), seconds quiet and dollars.
// The seconds tick on screen between snapshots, counted from the snapshot's idle, with no read. A click
// opens its changes so far (graphene.openDiff, lane 2b's). Pure: no VS Code here; agentsView.ts draws it.
import { usd, type State } from "./state.ts";

export interface AgentRow {
  id: string; // the task's
  fork: string | null; // the fork's letter, when the task's hold forked
  number: string; // `3`, or `3b`
  title: string;
  model: string;
  now: string; // its last move, such as `edit app.py`
  idle: number | null; // seconds quiet at the snapshot
  usd: number | null;
}

/** A row for every running agent: a task's, or each running fork's of a task that forked (the fork's model,
 *  dollars and quiet where the snapshot has them, the task's otherwise). */
export function agentRows(s: State): AgentRow[] {
  const out: AgentRow[] = [];
  for (const t of s.tasks) {
    if (t.state !== "running") continue;
    const now = t.tail[t.tail.length - 1] ?? "";
    const racing = t.forks.filter((f) => f.state === "running");
    if (!racing.length) { out.push({ id: t.id, fork: null, number: t.agent || "?", title: t.title, model: t.model, now, idle: t.idle, usd: t.usd }); continue; }
    for (const f of racing) out.push({ id: t.id, fork: f.letter, number: `${t.agent || "?"}${f.letter}`, title: t.title,
                                        model: f.model || t.model, now, idle: f.idle ?? t.idle, usd: f.usd ?? null });
  }
  return out;
}

/** Seconds quiet now: the snapshot's, plus the seconds since it was taken (``at`` and ``now`` in ms). */
export function quiet(idle: number | null, at: number, now: number): number | null {
  return idle === null ? null : Math.max(0, Math.floor(idle + (now - at) / 1000));
}

/** `12s`, `3m 05s`: how long, as the cockpit's `ago` says it. */
export function ago(seconds: number): string {
  if (seconds < 60) return `${seconds}s`;
  return `${Math.floor(seconds / 60)}m ${String(seconds % 60).padStart(2, "0")}s`;
}

/** `Nano · edit app.py · quiet 12s · $0.31`: what is beside the row's title. */
export function description(r: AgentRow, secs: number | null): string {
  const parts: string[] = [];
  if (r.model) parts.push(r.model);
  if (r.now) parts.push(r.now);
  if (secs !== null) parts.push(`quiet ${ago(secs)}`);
  const spent = usd(r.usd);
  if (spent) parts.push(spent);
  return parts.join(" · ");
}
