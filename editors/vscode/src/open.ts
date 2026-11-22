// When the graph opens by itself in the editor area (the setting graphene.graph.openOnStart): once for each
// start, until a person closes the tab. A start is the window opening on a plan with work to show, a plan
// appearing where there was none, or a run starting. A person who closes the tab is not chased: each round of
// `graphene auto` is a plan appearing and a run starting, so a start is no reason to bring back what they put
// away. Closed, it stays closed in this window until they ask for it. Where it opens leaves a person's work as
// it was: beside what they have in front, never over it. Pure: no VS Code here.
import type { State } from "./state.ts";

/** What of a snapshot a start is read from: work to show (a task that is not done, or a planner writing a
 *  plan), and a run going. */
export interface Seen { work: boolean; going: boolean }

export function seen(s: Pick<State, "tasks" | "drafting" | "run">): Seen {
  return { work: s.drafting !== null || s.tasks.some((t) => t.state !== "done"), going: s.run.going };
}

/** Whether the tab opens now. `was`: the snapshot read before this one, null when this is the first (the
 *  window just opened). `on`: the setting. `tab`: the tab is already there, in front or behind another, and
 *  is left as it is. `shut`: a person closed the tab in this window and has not asked for it since. */
export function opens(was: Seen | null, now: Seen, o: { on: boolean; tab: boolean; shut: boolean }): boolean {
  if (!o.on || o.tab || o.shut) return false;
  return (now.work && !was?.work) || (now.going && !was?.going);
}

/** Whether it opens beside the active group, not in it. `front`: the input of the tab that group has in front,
 *  as VS Code's tabs name it: a file, a diff, a notebook, a terminal, another extension's page; nothing for an
 *  empty group and for a page of VS Code's own (Welcome, Settings). In the group, the tab would take the place
 *  of what is in front and VS Code would leave the keyboard in nothing (opened without focus, the editor it
 *  hides loses the caret and the tab is not given it); beside, in the group to its side or a new one, the file
 *  stays and so does its caret. */
export function beside(front: unknown): boolean {
  // ponytail: Settings is covered as Welcome is (VS Code names neither); tell them apart by the tab if a box there matters
  return front !== undefined && front !== null;
}
