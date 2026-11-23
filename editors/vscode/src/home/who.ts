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

/** Exact, on Home by what it adds to approval and the switch, which Settings show on their own; its hover says
 *  all it holds. Here, with no import of its own, so the page's bundle takes it without the host's modules. */
export const EXACT = "Wait for every answer";
export const EXACT_HOVER = "Start waits until you have answered every open question, even one with a default. Approval and Stop after the plan go on with it.";
