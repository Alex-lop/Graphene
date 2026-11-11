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
state.stand_in = params.get("standin") ? true : raw.stand_in === true; // &standin=1: a live race against the stand-in
const rawTasks = (raw.tasks as Record<string, unknown>[] | undefined) ?? [];
for (const t of state.tasks) {
  const r = rawTasks.find((x) => x.id === t.id);
  Object.assign(t, { planned: typeof r?.planned === "number" ? r.planned : null, signoff: r?.signoff === true, owner: "agent" }); // as `plan --json` would say
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
  postMessage(m: { type: string; act?: string; id?: string; target?: string; fork?: string; field?: string; value?: unknown; key?: string;
                   draft?: { key: string; title: string; files: string; check: string; approve: boolean; after: string | null; parent: string | null } }) {
    if (m.type === "ready") {
      window.postMessage({ type: "state", state }, "*");
      if (select) window.postMessage({ type: "select", id: select }, "*");
      return;
    }
    // the form and a drawn task, answered as graphene would in the plain case, so the page can be tried here
    const again = () => window.postMessage({ type: "state", state: JSON.parse(JSON.stringify(state)) }, "*");
    const t = state.tasks.find((x) => x.id === m.id);
    if (m.act === "set" && t && m.field) {
      const key = ({ scope: "scope", forks: "planned", owner: "owner", signoff: "signoff", check: "check", title: "title" } as Record<string, string>)[m.field]!;
      t[key] = m.field === "scope" ? String(m.value).split(/\s+/) : m.field === "owner" ? (m.value ? "you" : "agent") : m.value;
      if (m.field === "title") t.full = m.value;
      if (m.field === "owner") t.state = m.value ? "yours" : "ready";
      window.postMessage({ type: "said", id: m.id, ok: true, line: "" }, "*");
      again();
    }
    if (m.act === "draw" && m.draft) {
      const d = m.draft, id = `n${state.tasks.length + 1}`;
      const made = parseState(JSON.stringify({ tasks: [{ id, title: d.title, full: d.title, state: d.after ? "waiting" : "ready", parent: d.parent,
        scope: d.files.split(/[\s,]+/).filter(Boolean), needs: d.after ? [d.after] : [], check: d.check || null }] })).tasks[0] as unknown as Record<string, unknown>;
      Object.assign(made, { planned: null, signoff: d.approve || !d.check, owner: "agent" });
      state.tasks.push(made);
      if (d.after) (state.edges as unknown[]).push([d.after, id, "needs"]);
      again();
      window.postMessage({ type: "said", key: d.key, ok: true, line: "", made: id }, "*");
    }
    const line = `preview: the graph asked for ${m.act} ${m.id ?? ""} ${m.target ?? ""} ${m.fork ?? ""}`.trim();
    console.log(line);
    const hint = document.getElementById("hint");
    if (hint) hint.textContent = line;
  },
  getState: () => saved,
  setState: (s: unknown) => { saved = s; },
});
