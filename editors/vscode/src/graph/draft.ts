// A task being drawn on the graph: a box with a title and its blanks, kept by the workspace until graphene takes it
// (`graphene node add`). Pure: no DOM here, so `node --test` reads it.

export interface Draft {
  key: string; // the workspace's own id for it: a space first, so it is never a task's
  title: string;
  files: string; // globs as typed, spaces or commas between
  check: string;
  approve: boolean; // waits for your approval
  after: string | null; // the task it waits on
  parent: string | null; // the sub-goal it sits under
  said?: string; // graphene's refusal, when it was offered and not taken
}

export const isDraft = (id: string | null | undefined): id is string => Boolean(id?.startsWith(" d"));
export const globs = (text: string): string[] => text.split(/[\s,]+/).filter(Boolean);

/** What it still lacks before graphene takes it, as `node add` judges a task: a title, files it may change,
 *  and a check or your approval. Nothing: it joins the plan. */
export function lacks(d: Draft): string[] {
  const out: string[] = [];
  if (!d.title.trim()) out.push("a title");
  if (!globs(d.files).length) out.push("the files it may change");
  if (!d.check.trim() && !d.approve) out.push("a check or your approval");
  return out;
}

/** The small line on its box: its blanks, until they are filled. */
export function blanks(d: Draft): string {
  const n = globs(d.files).length;
  return `${n ? `${n} file${n > 1 ? "s" : ""}` : "files ___"} · ${d.check.trim() ? "check ✓" : d.approve ? "your approval" : "check ___"}`;
}

/** The line under a draft's form: what it waits for, or graphene's refusal. */
export function draftLine(d: Draft): string {
  const l = lacks(d);
  const words = l.length > 1 ? `${l.slice(0, -1).join(", ")} and ${l[l.length - 1]}` : l[0];
  return l.length ? `A draft, yours alone: it joins the plan once it has ${words}.` : d.said ? "" : "Joining the plan…";
}

/** A persisted draft or a page's edit, checked before it reaches workspace storage. */
export function draftOf(value: unknown): Draft | null {
  if (!value || typeof value !== "object") return null;
  const d = value as Record<string, unknown>;
  const text = (v: unknown): v is string => typeof v === "string" && v.length <= 2000 && !/[\u0000-\u0008\u000a-\u001f]/.test(v);
  if (!draftKey(d.key) || !text(d.title) || !text(d.files) || !text(d.check) || typeof d.approve !== "boolean") return null;
  if (d.after !== null && !text(d.after) || d.parent !== null && !text(d.parent)) return null;
  return { key: d.key, title: d.title, files: d.files, check: d.check, approve: d.approve, after: d.after as string | null, parent: d.parent as string | null };
}

export const draftKey = (key: unknown): key is string => typeof key === "string" && /^ d[\w-]{1,64}$/.test(key);
