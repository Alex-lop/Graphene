// The preview stands in for VS Code: it answers the graph's `ready` with a fixture state (`?fixture=auto`
// picks one) and shows what the graph asked for in the footer. For screenshots, no editor needed.
import autoFx from "../../test/fixtures/auto.json";
import emptyFx from "../../test/fixtures/empty.json";
import proposalsFx from "../../test/fixtures/proposals.json";
import runningFx from "../../test/fixtures/running.json";
import { parseState } from "../state.ts";

const fixtures: Record<string, unknown> = { auto: autoFx, empty: emptyFx, proposals: proposalsFx, running: runningFx };
const params = new URLSearchParams(location.search);
const name = params.get("fixture") ?? "running";
const select = params.get("select"); // `&select=greet` opens that task's details, as a click would
const state = parseState(JSON.stringify(fixtures[name] ?? runningFx));
if (params.get("theme") === "light") document.documentElement.classList.add("light"); // VS Code's light colours

(window as unknown as { acquireVsCodeApi: () => unknown }).acquireVsCodeApi = () => ({
  postMessage(m: { type: string; act?: string; id?: string; target?: string }) {
    if (m.type === "ready") {
      window.postMessage({ type: "state", state }, "*");
      if (select) window.postMessage({ type: "select", id: select }, "*");
      return;
    }
    const line = `preview: the graph asked for ${m.act} ${m.id ?? ""} ${m.target ?? ""}`.trim();
    console.log(line);
    const hint = document.getElementById("hint");
    if (hint) hint.textContent = line;
  },
  getState: () => undefined,
  setState: () => undefined,
});
