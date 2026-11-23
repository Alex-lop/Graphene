// Who plans and does the work, as Home's Set Up offers it: one pick for both. No imports, so the page's bundle
// and the host share it.
export const WHO = [
  { word: "claude", label: "Claude Code", note: "the claude command on this machine" },
  { word: "codex", label: "Codex", note: "the codex command on this machine" },
] as const;

/** Where a plan comes from, in the same words on every screen: Graphene's hooks reach these two agents only.
 *  In Cursor, the one line more is said under it (the host knows the editor by `vscode.env.appName`). */
export const ASK = "Ask Claude Code or Codex for something, in its chat";
export const NOT_CURSOR = "Cursor's own Agent does not plan with Graphene yet.";

/** What Graphene is, in one sentence: the extension README's first, short of where the graph is drawn, so the
 *  walkthrough's header (three lines at most) shows it whole. Set Up says it and HOW, and so does the
 *  extension's description (package.json, pinned to these by home.test.ts). */
export const WHAT = "Your coding agent proposes a plan before it writes, and Graphene draws it as a graph.";
export const HOW = "Each task runs in its own copy of your repository and lands only when its check passes.";

/** Exact, on Home by what it adds to approval and the switch, which Settings show on their own; its hover says
 *  all it holds. Here, with no import of its own, so the page's bundle takes it without the host's modules. */
export const EXACT = "Wait for every answer";
export const EXACT_HOVER = "Start waits until you have answered every open question, even one with a default. Approval and Stop after the plan go on with it.";

/** The cost in Home's counts, on hover: what it paid for (cards.ts's countsLine says why in these words). */
export const COST_HOVER = "What this repository's planners and agents have cost so far, a dropped plan's included. On a subscription nothing is billed.";
