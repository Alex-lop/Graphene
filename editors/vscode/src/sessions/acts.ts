// What a page of sessions may ask its host, checked against what the page draws. Pure: no VS Code here, so
// `node --test` reads it. Nothing from the page reaches a shell or names a file: an act carries the id of a card
// or of a session the page has, and the host looks up the rest itself.
import type { State } from "../state.ts";

/** addSession: another of the folder's sessions onto this page (the host asks which). takeOff: a session off it.
 *  terminal: a card's terminal, or its transcript's tail. resume: a session, in a terminal of the editor's.
 *  openFile: a file a card changed, as its diff (`file` is one the card names). replay: the recorded session
 *  the extension carries, on an empty page. */
export const PAGE_ACTS = ["addSession", "takeOff", "terminal", "resume", "openFile", "replay"] as const;
export type PageAct = (typeof PAGE_ACTS)[number];
export type FromPage = { type: "ready" } | { type: "act"; act: PageAct; id: string; file?: string };

type Drawn = Pick<State, "tasks" | "sessions">;

/** A message from a page of sessions, or null: an act it does not know, a card or a session the page does not
 *  draw, a file the card does not name. */
export function checkPage(m: unknown, s: Drawn | null): FromPage | null {
  if (!m || typeof m !== "object") return null;
  const r = m as Record<string, unknown>;
  if (r.type === "ready") return { type: "ready" };
  if (r.type !== "act" || typeof r.act !== "string" || !(PAGE_ACTS as readonly string[]).includes(r.act)) return null;
  const act = r.act as PageAct, id = typeof r.id === "string" ? r.id : "";
  if (act === "addSession" || act === "replay") return { type: "act", act, id: "" };
  if (act === "takeOff" || act === "resume") return s?.sessions?.some((x) => x.id === id) ? { type: "act", act, id } : null;
  const card = s?.tasks.find((t) => t.id === id && t.card);
  if (!card) return null;
  if (act === "terminal") return { type: "act", act, id };
  return typeof r.file === "string" && card.changed.includes(r.file) ? { type: "act", act, id, file: r.file } : null;
}
