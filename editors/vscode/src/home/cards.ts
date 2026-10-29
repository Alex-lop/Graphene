// Home, pure: what a person sees first in Graphene's side bar, from the snapshot, in plain words. Sections come
// in the order a person acts on them (what needs you, the suggested plan, who is working, what is up next, what
// is done); each card says what its task is for and what proves it, with its buttons. No VS Code and no DOM
// here: home.ts sends what this returns, home/main.ts draws it, and checkHome reads what the page sends back.
import { usd, type State } from "../state.ts";

export const ACTS = ["ask", "cancel", "startAll", "discardAll", "run", "stop", "drop", "answer", "openDiff", "compare", "keep",
                     "approve", "sendBack", "offer", "tryAgain", "allow", "message", "markDone", "showGraph", "demo", "setup",
                     "install", "setKey", "refresh", "openFolder"] as const;
export type Act = (typeof ACTS)[number];

export interface Btn { label: string; act: Act; id?: string; arg?: string; main?: boolean; title?: string }
export interface Line { k?: string; v: string; mono?: boolean; warn?: boolean }
export type Tone = "question" | "proposed" | "running" | "review" | "came-back" | "ready" | "waiting" | "done" | "yours";
export interface Card { key: string; tone: Tone; title: string; tag: string; lines: Line[]; buttons: Btn[] }
export interface Section { key: string; title: string; note: string; buttons: Btn[]; cards: Card[]; folded: boolean }
export interface Home { banner: string; goal: string; counts: string; sections: Section[]; empty: boolean }

/** The first words on the page when this is not a real run: a replay, or a race against the scripted stand-in. */
export function banner(s: State): string {
  if (s.replay) return `Demo replay: ${s.replay.shown}`;
  return s.stand_in ? "Practice run: a scripted stand-in answers for the AI, so nothing is spent" : "";
}

/** `2 working · 1 needs you · 3 of 6 done · $0.42 spent` */
export function countsLine(s: State): string {
  const sb = s.scoreboard;
  const parts: string[] = [];
  if (sb.running) parts.push(`${sb.running} working`);
  if (sb.need_you) parts.push(`${sb.need_you} need${sb.need_you === 1 ? "s" : ""} you`);
  if (sb.total) parts.push(`${sb.proven} of ${sb.total} done`);
  const spent = usd(s.spent);
  if (spent) parts.push(`${spent} spent`);
  return parts.join(" · ");
}
