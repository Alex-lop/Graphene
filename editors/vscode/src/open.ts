// When the graph opens by itself in the editor area (the setting graphene.graph.openOnStart): once for each
// start. A start is the window opening on a plan with work to show, a plan appearing where there was none, or
// a run starting. Only a start opens it, so a person who closes the tab is not chased: nothing here remembers
// the close, and nothing reopens the tab until the next start. Pure: no VS Code here.
import type { State } from "./state.ts";

/** What of a snapshot a start is read from: work to show (a task that is not done, or a planner writing a
 *  plan), and a run going. */
export interface Seen { work: boolean; going: boolean }

export function seen(s: Pick<State, "tasks" | "drafting" | "run">): Seen {
  return { work: s.drafting !== null || s.tasks.some((t) => t.state !== "done"), going: s.run.going };
}

/** Whether the tab opens now. `was`: the snapshot read before this one, null when this is the first (the
 *  window just opened). `on`: the setting. `tab`: the tab is already there, in front or behind another, and
 *  is left as it is. */
export function opens(was: Seen | null, now: Seen, o: { on: boolean; tab: boolean }): boolean {
  if (!o.on || o.tab) return false;
  return (now.work && !was?.work) || (now.going && !was?.going);
}
