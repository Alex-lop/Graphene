// The Needs You view: what waits for the person, first, each row with its move inline and on its click, in
// the cockpit's order (cockpit/model.py `order`): auto mode waiting, then questions, then the tasks whose move
// is the person's (a sign-off, a hand-back, their own task, a proposal, a running task the gate stopped).
// Nothing here sends anyone to the cockpit. Pure: no VS Code here; needsView.ts draws what this returns.
import type { Question, State, Task } from "./state.ts";

export type Need =
  | { kind: "auto"; why: string; endpoint: string | null; key: boolean } // auto waits; key: a key would free it
  | { kind: "question"; q: Question }
  | { kind: "proposal" | "hand-back" | "sign-off" | "yours" | "stopped"; t: Task };

type TaskNeed = Extract<Need, { t: Task }>["kind"];
const NEEDS_YOU: Record<string, TaskNeed> = { proposed: "proposal", "came back": "hand-back", review: "sign-off", yours: "yours" };

/** The states Drop Step may take: a task that came back is one of them (plan.drop refuses a running one). */
export const DROPPABLE: readonly string[] = ["proposed", "ready", "waiting", "came back"];

/** Does auto's reason say a key would free it? The CLI's own line (`graphene key set`, with the host it names),
 *  or Token Factory's refusal as auto quotes it: a 401, "token is not present", "invalid token", or no key set.
 *  Waiting on a key is a dead end on screen unless Set Key is offered right there. */
export function keyTrouble(why: string): { key: boolean; endpoint: string | null } {
  const said = /`graphene key set(?: --endpoint (\w+))?`/.exec(why);
  if (said) return { key: true, endpoint: said[1] ?? null };
  return { key: /\b401\b|token is not present|invalid token|\bno key\b|NEBIUS_API_KEY is not set/i.test(why), endpoint: null };
}

/** What needs the person, in the order a person should look at it. A task counts when the snapshot says so or
 *  its state does (an older CLI says nothing): review, came back, yours, proposed, or running with a write the
 *  gate stopped, which only the person can widen its scope to. */
export function needs(s: State): Need[] {
  const out: Need[] = [];
  if (s.auto?.stage === "waits") out.push({ kind: "auto", why: s.auto.why || "see the plan", ...keyTrouble(s.auto.why) });
  for (const q of s.questions) out.push({ kind: "question", q });
  for (const t of s.tasks) {
    const kind: TaskNeed | null = NEEDS_YOU[t.state] ?? (t.state === "running" && t.stopped.length ? "stopped" : null);
    if (kind) out.push({ kind, t });
  }
  return out;
}

/** The tooltip's one-line count: `2 need you`. */
export function count(list: Need[]): string {
  return list.length === 1 ? "1 needs you" : `${list.length} need you`;
}

// the moves, each the graphene command the cockpit runs for the same key
export const takeDefault = (id: string): string[] => ["board", "take", id];
export const pickOption = (id: string, n: number): string[] => ["board", "pick", id, String(n)]; // from 1
export const answerWords = (id: string, words: string): string[] => ["board", "answer", id, words];
export const tryAgain = (id: string): string[] => ["run", "--parallel", "4", "--node", id]; // the cockpit's ⏎

/** An answer given with the command (the graph's pane sends the option it shows): one of the question's options
 *  by its words, its default, or the person's own words. */
export function answerWith(q: Question, option: string): string[] {
  const i = q.options.indexOf(option);
  if (i >= 0) return pickOption(q.id, i + 1);
  return option === q.default ? takeDefault(q.id) : answerWords(q.id, option);
}
export const markDone = (id: string): string[] => ["node", "done", id]; // runs its check: a terminal
export const widen = (id: string): string[] => ["node", "widen", id]; // exactly what the gate stopped

export const OFFERS: [string, string][] = [["w", "Widen its scope"], ["b", "A new task"], ["n", "Wait on"], ["r", "Reopen"]];

/** What an offer acts on, read from its command as the cockpit reads it (rows.py `offered`): the paths a widen
 *  or a new task takes, the tasks it would wait on, the tasks it reopens. */
export function offerOn(key: string, argv: string[], t: Task, titles: Record<string, string> = {}): string {
  const name = (id: string) => titles[id] ?? id;
  if (key === "w" || key === "b") return argv.slice(3).join(", ");
  if (key === "n") return argv.filter((x, i) => argv[i - 1] === "--needs" && !t.needs.includes(x)).map(name).join(", ");
  const at = argv.indexOf("--note");
  return argv.slice(2, at < 0 ? undefined : at).map(name).join(", ");
}

/** The hand-back's moves as a quick pick says them: each offer the snapshot carries, with what it acts on, in
 *  the cockpit's order, then trying it again. A running task the gate stopped offers the widen alone. */
export function offerWords(t: Task, titles: Record<string, string> = {}): { label: string; detail: string; argv: string[]; long: boolean }[] {
  if (t.state === "running") {
    const path = t.stopped[t.stopped.length - 1] ?? "";
    return [{ label: `Widen its scope to ${path}`, detail: `graphene ${widen(t.id).join(" ")}: the agent may write it`, argv: t.offers.w ?? widen(t.id), long: false }];
  }
  const out = OFFERS.filter(([k]) => t.offers[k]).map(([k, what]) => {
    const argv = t.offers[k]!;
    const on = offerOn(k, argv, t, titles);
    const label = k === "b" ? `A new task for ${on}; this one waits on it` : on ? `${what} ${on}` : what;
    return { label, detail: `graphene ${argv.join(" ")}`, argv, long: false };
  });
  out.push({ label: "Try it again", detail: `graphene ${tryAgain(t.id).join(" ")}: a new agent, told why it came back`, argv: tryAgain(t.id), long: true });
  return out;
}
