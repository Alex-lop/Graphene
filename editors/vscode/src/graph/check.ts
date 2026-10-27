// What the page may ask the host, checked against the plan. Pure: no VS Code here, so `node --test` reads it.

// link: id is A, target B, and B waits on A; unlink: id is B, target the A it stops waiting on;
// answer: id is a question's, target one of its options (none: the command asks)
export const ACTS = ["add-after", "add-under", "link", "unlink", "edit", "drop", "accept", "tell", "run", "stop", "auto", "cockpit",
                     "openDiff", "compareForks", "pickFork", "signOff", "answer", "handBack"] as const;
export type Act = (typeof ACTS)[number];
export type FromPage = { type: "ready" } | { type: "act"; act: Act; id: string; target?: string; fork?: string };
export type Plan = { tasks: { id: string; forks: { letter: string }[] }[]; questions: { id: string; options: string[]; default: string | null }[] } | null;

/** A message from the page, checked against the plan: a known act; an id that is a task's (or, for answer,
 *  a question's), or empty for the acts that take none; a target that is a task's (or, for answer, one of
 *  the question's options); a fork the task has. Null for anything else. */
export function check(m: unknown, session: { state: Plan }): FromPage | null {
  if (!m || typeof m !== "object") return null;
  const r = m as Record<string, unknown>;
  if (r.type === "ready") return { type: "ready" };
  if (r.type !== "act" || typeof r.act !== "string" || !(ACTS as readonly string[]).includes(r.act)) return null;
  const act = r.act as Act;
  const id = typeof r.id === "string" ? r.id : "";
  const target = typeof r.target === "string" ? r.target : undefined;
  const fork = typeof r.fork === "string" ? r.fork : undefined;
  const s = session.state;
  const tasks = s?.tasks ?? [];
  const task = tasks.find((t) => t.id === id);
  const global: readonly Act[] = ["run", "stop", "auto", "cockpit", "add-under"];
  if (act === "answer") {
    const q = s?.questions.find((x) => x.id === id);
    if (!q) return null;
    if (target !== undefined && target !== q.default && !q.options.includes(target)) return null;
    return { type: "act", act, id, target };
  }
  if (!task && !(id === "" && global.includes(act))) return null;
  if (target !== undefined && !tasks.some((t) => t.id === target)) return null;
  if (fork !== undefined && !task?.forks.some((f) => f.letter === fork)) return null;
  return { type: "act", act, id, target, fork };
}
