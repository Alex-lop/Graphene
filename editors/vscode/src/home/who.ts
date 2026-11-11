// Who plans and does the work, as Home's Set Up offers it: one pick for both. No imports, so the page's bundle
// and the host share it.
export const WHO = [
  { word: "claude", label: "Claude Code", note: "the claude command on this machine" },
  { word: "codex", label: "Codex", note: "the codex command on this machine" },
  { word: "nemotron", label: "Nemotron", note: "NVIDIA's models on Nebius Token Factory; needs an API key" },
] as const;

/** Exact, said on its switch and when it goes on: what it holds. Here, with no import of its own, so the page's
 *  bundle takes it without the host's modules. */
export const EXACT = "Exact: Start waits until you have answered every open question, and each finished task waits for your approval";
