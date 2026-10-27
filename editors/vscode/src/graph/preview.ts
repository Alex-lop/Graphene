// The preview stands in for VS Code: it answers the graph's `ready` with a fixture state (`?fixture=auto`
// picks one) and shows what the graph asked for in the footer. For screenshots, no editor needed.
import autoFx from "../../test/fixtures/auto.json";
import emptyFx from "../../test/fixtures/empty.json";
import proposalsFx from "../../test/fixtures/proposals.json";
import runningFx from "../../test/fixtures/running.json";
import realAutoFx from "../../test/fixtures/real-auto.json";
import raceFx from "../../test/fixtures/graph-race.json";
import { parseState } from "../state.ts";

const fixtures: Record<string, unknown> = { auto: autoFx, empty: emptyFx, proposals: proposalsFx, running: runningFx,
  real: realAutoFx, race: raceFx };
const params = new URLSearchParams(location.search);
const name = params.get("fixture") ?? "running";
const select = params.get("select"); // `&select=greet` opens that task's details, as a click would
const raw = (fixtures[name] ?? runningFx) as Record<string, unknown>;
const state = parseState(JSON.stringify(raw)) as unknown as Record<string, unknown> & { tasks: Record<string, unknown>[] };
// what the snapshot gains tonight, until the parser knows it (CONTRACT.md): replay, a task's why and attempts,
// a fork's attempts and idle
state.replay = params.get("replay") ? { shown: "a scripted stand-in, no model ran", day: "2026-10-26", repository: "wordkit" } : raw.replay ?? null;
const rawTasks = (raw.tasks as Record<string, unknown>[] | undefined) ?? [];
for (const t of state.tasks) {
  const r = rawTasks.find((x) => x.id === t.id);
  if (!r) continue;
  if (typeof r.why === "string") t.why = r.why;
  if (typeof r.attempts === "number") t.attempts = r.attempts;
  const forks = (r.forks as Record<string, unknown>[] | undefined) ?? [];
  for (const f of t.forks as Record<string, unknown>[]) {
    const rf = forks.find((x) => x.letter === f.letter);
    if (!rf) continue;
    if (typeof rf.attempts === "number") f.attempts = rf.attempts;
    if (typeof rf.idle === "number") f.idle = rf.idle;
  }
}
const theme = params.get("theme");
if (theme === "light") document.documentElement.classList.add("light"); // VS Code's light colours
if (theme === "hc") { document.documentElement.classList.add("hc"); document.body.classList.add("vscode-high-contrast"); }
const dir = params.get("dir");
if (dir) document.body.dataset.dir = dir;
let saved: unknown = params.get("view") ? { view: params.get("view") } : undefined;

(window as unknown as { acquireVsCodeApi: () => unknown }).acquireVsCodeApi = () => ({
  postMessage(m: { type: string; act?: string; id?: string; target?: string; fork?: string }) {
    if (m.type === "ready") {
      window.postMessage({ type: "state", state }, "*");
      if (select) window.postMessage({ type: "select", id: select }, "*");
      return;
    }
    const line = `preview: the graph asked for ${m.act} ${m.id ?? ""} ${m.target ?? ""} ${m.fork ?? ""}`.trim();
    console.log(line);
    const hint = document.getElementById("hint");
    if (hint) hint.textContent = line;
  },
  getState: () => saved,
  setState: (s: unknown) => { saved = s; },
});
