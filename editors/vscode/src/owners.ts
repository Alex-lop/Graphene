// Whose a file is, as the Explorer marks it: Graphene's scope globs read as the CLI reads them (plan.py's
// `_pattern` and `in_scope`; test/fixtures/scope-cases.json holds both to one table, and
// tests/test_vscode_scope_parity.py checks the Python side), and the live task whose scope holds the path.
// Pure: the decoration provider in extension.ts draws what this returns.
import type { Task } from "./state.ts";

/** One glob as plan.py's `_pattern`: `**` crosses directories, `*` and `?` stay in one, and a last name with
 *  no wildcard covers what is beneath it (`src/api` is `src/api/**`). */
export function pattern(glob: string): RegExp {
  let g = glob.trim().replace(/^\.\//, "");
  if (g.endsWith("/")) g += "**";
  let out = "";
  for (let i = 0; i < g.length;) {
    if (g.startsWith("**/", i)) { out += "(?:.*/)?"; i += 3; }
    else if (g.startsWith("**", i)) { out += ".*"; i += 2; }
    else if (g[i] === "*") { out += "[^/]*"; i += 1; }
    else if (g[i] === "?") { out += "[^/]"; i += 1; }
    else { out += g[i]!.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"); i += 1; }
  }
  const last = g.split("/").pop() ?? "";
  return new RegExp(`^${out}${/[*?]/.test(last) ? "" : "(?:/.*)?"}$`);
}

/** Is the repo-relative path inside the scope? The last glob that matches decides, `!` keeps out. */
export function inScope(path: string, scope: string[]): boolean {
  let inside = false;
  for (const glob of scope) {
    const negated = glob.startsWith("!");
    if (pattern(negated ? glob.slice(1) : glob).test(path)) inside = !negated;
  }
  return inside;
}

/** The directories a glob names before its first wildcard (plan.py's `_fixed`), joined. */
function fixed(glob: string): string {
  const parts = glob.trim().replace(/^\.\//, "").replace(/\/+$/, "").split("/");
  const upto = parts.findIndex((p) => /[*?]/.test(p));
  return parts.slice(0, upto < 0 ? parts.length : upto).join("/");
}

/** One colour a step, the same on its card's tile and on its files in the Explorer, so a person sees in their
 *  own file tree which step is where: theme colours' ids, by the step's place in the plan. The chart colours
 *  that say a state (amber, green, purple, blue, red) are left to the states, and the three terminal colours
 *  near a state's hue (bright blue, green, yellow) come last, so a plan's first five steps never look like one. */
export const STEP_COLOURS = ["charts.orange", "terminal.ansiCyan", "terminal.ansiMagenta", "terminal.ansiBrightCyan", "terminal.ansiBrightMagenta",
                             "terminal.ansiBrightBlue", "terminal.ansiBrightGreen", "terminal.ansiBrightYellow"] as const;

/** The same colours for a page that has no theme to ask (the preview), in the palette's order: Dark+'s own. */
export const STEP_FALLBACKS = ["#d18616", "#11a8cd", "#bc3fbc", "#29b8db", "#d670d6", "#3b8eea", "#23d18b", "#f5f543"] as const;

/** Which of the step colours a task takes: its place among the plan's tasks, round the palette. */
export function stepColour(id: string, tasks: readonly { id: string }[]): number {
  return Math.max(0, tasks.findIndex((t) => t.id === id)) % STEP_COLOURS.length;
}

export interface Owner {
  badge: string; // two characters at most, as VS Code wants
  tooltip: string;
  state: string; // the task's: running, review, came back, ready, waiting (its badge says it)
  colour: string; // the step's own colour, a theme colour's id: the same as its card's tile
}

// the tasks that own their files: accepted and not done (one writer a path, so two never share one)
const LIVE = ["running", "review", "came back", "ready", "waiting"];

/** The live task whose files ``path`` is one of (repo-relative, `/` between names): its scope holds the path,
 *  or names it as the directory it works in; a running one first. Its badge: the agent's number while it
 *  runs, ✓ waiting for your sign-off, ! came back, · not started. Null for a path no live task holds, and
 *  for git's and the plan store's own directories. */
export function owner(path: string, tasks: Task[]): Owner | null {
  if (!path || /^\.(graphene|git)(\/|$)/.test(path)) return null;
  const holds = (x: Task) => inScope(path, x.scope) || x.scope.some((g) => !g.startsWith("!") && fixed(g) === path);
  const live = tasks.filter((x) => LIVE.includes(x.state) && holds(x));
  const t = live.find((x) => x.state === "running") ?? live[0];
  if (!t) return null;
  if (t.state === "running") {
    const forks = t.forks.length ? ` · ${t.forks.length} attempts racing` : "";
    return { badge: t.agent && t.agent.length <= 2 ? t.agent : "◆", state: t.state, colour: STEP_COLOURS[stepColour(t.id, tasks)]!,
      tooltip: `${t.title} · agent ${t.agent || "?"}${t.model ? ` · ${t.model}` : ""}${forks}: writing these files now` };
  }
  const [badge, said] = t.state === "review" ? ["✓", "passed, waits for your sign-off"]
    : t.state === "came back" ? ["!", "came back"] : ["·", `${t.state}: its files once it runs`];
  return { badge, state: t.state, colour: STEP_COLOURS[stepColour(t.id, tasks)]!, tooltip: `${t.title} · ${said}` };
}
