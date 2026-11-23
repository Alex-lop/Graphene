// Home with a fixture state and no VS Code (media/home-preview.html): it answers the page's `ready` with what the
// host would send for that state, and shows what the page asked for at its foot. ?fixture= as the graph's preview
// (running by default; none: a folder with no plan yet), ?theme= as there.
import autoFx from "../../test/fixtures/auto.json";
import bigFx from "../../test/fixtures/big.json";
import emptyFx from "../../test/fixtures/empty.json";
import proposalsFx from "../../test/fixtures/proposals.json";
import runningFx from "../../test/fixtures/running.json";
import workflowFx from "../../test/fixtures/workflow.json";
import { wearTheme } from "../previewTheme.ts";
import { parseState } from "../state.ts";
import { home } from "./cards.ts";

const fixtures: Record<string, unknown> = { auto: autoFx, big: bigFx, empty: emptyFx, proposals: proposalsFx, running: runningFx, workflow: workflowFx };
const params = new URLSearchParams(location.search);
const name = params.get("fixture") ?? "running";
wearTheme(params.get("theme"));
const state = parseState(JSON.stringify(fixtures[name] ?? runningFx));
const kind = name === "none" ? "uninitialised" : name === "missing" ? "missing" : state.tasks.length ? "ok" : "empty";
const model = { type: "home", status: { kind, text: "" }, home: kind === "ok" || kind === "empty" ? home(state) : null,
                review: state.envelope.review === "every", exact: false, busy: "", last: { n: 0, lines: [], bad: false },
                older: params.has("older") ? "This Graphene is older than the extension: it needs 0.10 (uv tool upgrade graphene-map). This editor runs graphene 0.9.0 at /Users/you/.local/bin/graphene." : "",
                cursor: /^(cursor|midnight)/.test(params.get("theme") ?? "") }; // a Cursor theme: the page is in Cursor
let saved: unknown;
(window as unknown as { acquireVsCodeApi: () => unknown }).acquireVsCodeApi = () => ({
  postMessage(m: { type: string; act?: string; id?: string; arg?: string }) {
    if (m.type === "ready") return void window.postMessage(model, "*");
    const line = `preview: Home asked for ${m.act ?? m.type} ${m.id ?? ""} ${m.arg ?? ""}`.trim();
    console.log(line);
    const hint = document.getElementById("hint");
    if (hint) hint.textContent = line;
  },
  getState: () => saved,
  setState: (s: unknown) => { saved = s; },
});
