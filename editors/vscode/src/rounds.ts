// Auto mode's rounds, from `graphene plan log --json` (a JSON object a line): the plan's iterations as a person
// reads them, each round with what the envelope accepted, which fork each task kept and why, what landed, the
// goal's check and the dollars. Pure: the Rounds view draws what this returns.

export interface LogRow {
  id: number;
  node_id: string;
  kind: string;
  detail: Record<string, unknown>;
}

export interface Round {
  n: number;
  stage: string; // its last stage: planning, running, checking, fixing, done, waits
  why: string; // why it waits, or what the goal's check failed on while fixing
  spent: number | null;
  accepted: string[]; // what the envelope took for the person this round
  kept: string[]; // "top kept b of 3: finished first"
  landed: string[];
  check: string; // the goal's check: pass, fail, or "" before it ran
  failed: string; // a fix round: the line the goal's check failed on, which sent it here
}

export function parseLog(text: string): LogRow[] {
  const rows: LogRow[] = [];
  for (const line of text.split("\n")) {
    if (!line.trim()) continue;
    try {
      const r = JSON.parse(line) as Partial<LogRow>;
      if (typeof r.kind === "string" && typeof r.node_id === "string") {
        rows.push({ id: Number(r.id) || 0, node_id: r.node_id, kind: r.kind, detail: (r.detail ?? {}) as Record<string, unknown> });
      }
    } catch {
      // a line that is not JSON (a warning on stdout) is no row
    }
  }
  return rows;
}

/** The rounds of auto mode in the log, oldest first; a row belongs to the round the last `auto` row before it named.
 *  Only the newest goal's: an `auto` row naming another root starts the list again (its round 1 is not the last's). */
export function rounds(rows: LogRow[]): Round[] {
  const out: Round[] = [];
  let current: Round | null = null;
  let goal = "";
  const at = (n: number): Round => {
    let r = out.find((x) => x.n === n);
    if (!r) {
      r = { n, stage: "", why: "", spent: null, accepted: [], kept: [], landed: [], check: "", failed: "" };
      out.push(r);
    }
    return r;
  };
  for (const row of rows) {
    const d = row.detail;
    if (row.kind === "auto") {
      const root = typeof d.root === "string" ? d.root : "";
      if (root && root !== goal) {
        if (goal) out.length = 0; // another goal: the view follows the newest
        goal = root;
      }
      current = at(Number(d.round) || 1);
      current.stage = String(d.stage ?? current.stage);
      current.why = String(d.why ?? "");
      current.spent = typeof d.spent === "number" ? d.spent : current.spent;
      if (d.check === "pass" || d.check === "fail") current.check = d.check as string;
      if (d.stage === "fixing") {
        current.failed = String(d.why ?? "");
        if (out.length > 1) out[out.length - 2]!.check = "fail"; // the round before failed it
      }
      if (d.stage === "done") current.check = "pass";
    } else if (row.kind === "accepted" && d.by === "auto") {
      at(Number(d.round) || current?.n || 1).accepted.push(row.node_id);
    } else if (row.kind === "picked" && current) {
      current.kept.push(`${row.node_id} kept ${String(d.fork)} of ${String(d.of)}${d.reason ? `: ${String(d.reason)}` : ""}`);
    } else if (row.kind === "landed" && current) {
      current.landed.push(row.node_id);
    }
  }
  return out.sort((a, b) => a.n - b.n);
}

/** A round in one line, for the view's row. */
export function roundLine(r: Round): string {
  const parts = [`Round ${r.n}`, r.stage];
  if (r.accepted.length) parts.push(`${r.accepted.length} accepted`);
  if (r.landed.length) parts.push(`${r.landed.length} landed`);
  if (r.check) parts.push(`goal ${r.check === "pass" ? "✓" : "✗"}`);
  if (r.spent !== null) parts.push(`$${r.spent < 0.01 && r.spent > 0 ? r.spent.toFixed(4) : r.spent.toFixed(2)}`);
  return parts.filter(Boolean).join(" · ");
}
