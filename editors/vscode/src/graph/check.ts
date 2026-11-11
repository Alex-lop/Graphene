// What the page may ask the host, checked against the plan. Pure: no VS Code here, so `node --test` reads it.
import { CHANGES } from "./words.ts";

// link: id is A, target B, and B waits on A; unlink: id is B, target the A it stops waiting on;
// answer: id is a question's, target one of its options (none: the command asks);
// set: one field of the task's form, with its value; draw: a task drawn on the graph, whole, for `node add`;
// add-after and add-under with a sentence: the planner fills a drawn task in
export const ACTS = ["add-after", "add-under", "link", "unlink", "drop", "accept", "tell", "run", "stop", "auto", "cockpit",
                     "openDiff", "compareForks", "pickFork", "signOff", "answer", "handBack", "set", "draw"] as const;
export type Act = (typeof ACTS)[number];
export const FIELDS = ["title", "scope", "check", "forks", "signoff", "owner"] as const;
export type Field = (typeof FIELDS)[number];
export type Drawn = { key: string; title: string; files: string; check: string; approve: boolean; after: string | null; parent: string | null };
export type FromPage = { type: "ready" }
  | { type: "act"; act: Act; id: string; target?: string; fork?: string; field?: Field; value?: string | number | boolean; draft?: Drawn; sentence?: string; key?: string };
export type Plan = { replay?: unknown; tasks: { id: string; forks: { letter: string }[] }[]; goals?: { id: string }[];
                     questions: { id: string; options: string[]; default: string | null }[] } | null;

const LONG = 2000; // a title, a check or a line of globs longer than this is not one a person typed
const text = (v: unknown): v is string => typeof v === "string" && v.length <= LONG && !/[\u0000-\u0008\u000a-\u001f]/.test(v);

/** A form field's value, as its field takes it: words for a title (not empty), globs or a check (a check may
 *  be empty: none), 1 to 8 attempts, a yes or no for your approval and for doing it yourself. */
function valueOf(field: Field, v: unknown): string | number | boolean | undefined {
  if (field === "forks") return typeof v === "number" && Number.isInteger(v) && v >= 1 && v <= 8 ? v : undefined;
  if (field === "signoff" || field === "owner") return typeof v === "boolean" ? v : undefined;
  if (!text(v)) return undefined;
  return field === "check" || v.trim() ? v.trim() : undefined;
}

/** A drawn task, whole: a title, its files and its check as typed, where it goes among the plan's own. */
function drawn(v: unknown, tasks: { id: string }[], goals: { id: string }[]): Drawn | undefined {
  if (!v || typeof v !== "object") return undefined;
  const d = v as Record<string, unknown>;
  if (!text(d.key) || !text(d.title) || !d.title.trim() || !text(d.files) || !text(d.check) || typeof d.approve !== "boolean") return undefined;
  const after = d.after ?? null, parent = d.parent ?? null;
  if (after !== null && !tasks.some((t) => t.id === after)) return undefined;
  if (parent !== null && !goals.some((g) => g.id === parent)) return undefined;
  return { key: d.key, title: d.title.trim(), files: d.files, check: d.check.trim(), approve: d.approve, after: after as string | null, parent: parent as string | null };
}

/** A message from the page, checked against the plan: a known act; an id that is a task's (or, for answer,
 *  a question's), or empty for the acts that take none; a target that is a task's (or, for answer, one of
 *  the question's options); a fork the task has. Null for anything else, and for every act in CHANGES
 *  when the plan is a replay's: the commands they run act on the person's folder, not the replay's. */
export function check(m: unknown, session: { state: Plan }): FromPage | null {
  if (!m || typeof m !== "object") return null;
  const r = m as Record<string, unknown>;
  if (r.type === "ready") return { type: "ready" };
  if (r.type !== "act" || typeof r.act !== "string" || !(ACTS as readonly string[]).includes(r.act)) return null;
  const act = r.act as Act;
  if (session.state?.replay && CHANGES.includes(act)) return null;
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
  if (act === "draw") { // a task of the page's own: no id yet
    const draft = drawn(r.draft, tasks, s?.goals ?? []);
    return s && draft ? { type: "act", act, id: "", draft } : null;
  }
  if (!task && !(id === "" && global.includes(act))) return null;
  if (target !== undefined && !tasks.some((t) => t.id === target)) return null;
  if (fork !== undefined && !task?.forks.some((f) => f.letter === fork)) return null;
  if (act === "set") {
    const field = (FIELDS as readonly unknown[]).includes(r.field) ? (r.field as Field) : undefined;
    const value = field ? valueOf(field, r.value) : undefined;
    return field && value !== undefined ? { type: "act", act, id, field, value } : null;
  }
  if ((act === "add-after" || act === "add-under") && r.sentence !== undefined) { // the planner fills a drawn task in
    if (!text(r.sentence) || !r.sentence.trim() || !text(r.key)) return null;
    return { type: "act", act, id, sentence: r.sentence.trim(), key: r.key };
  }
  return { type: "act", act, id, target, fork };
}
