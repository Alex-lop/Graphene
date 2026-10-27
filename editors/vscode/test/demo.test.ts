// The demo's session against a stand-in for the vscode module (a loader hook from this file, as
// graph-host.test.ts does): what the graph is handed for a replay.
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { register } from "node:module";
import { test } from "node:test";
import type { Act, StateX } from "../src/graph/words.ts";

const stub = `
export class EventEmitter { constructor() { this.ls = []; this.event = (l) => { this.ls.push(l); return { dispose() {} }; }; }
  fire(v) { for (const l of this.ls) l(v); } dispose() {} }
export const Uri = { file(p) { return { fsPath: p, path: p, scheme: "file" }; }, joinPath(...p) { return p.join("/"); } };
export const workspace = { getConfiguration() { return { get() { return undefined; } }; }, workspaceFolders: [] };
export const commands = { executeCommand() { return Promise.resolve(); }, registerCommand() { return { dispose() {} }; },
  getCommands() { return Promise.resolve([]); } };
export const window = { showInformationMessage() { return Promise.resolve(undefined); }, showErrorMessage() { return Promise.resolve(undefined); } };
export const ViewColumn = { Active: -1 };
`;
const hooks = `
const STUB = ${JSON.stringify(`data:text/javascript,${encodeURIComponent(stub)}`)};
export async function resolve(spec, ctx, next) { return spec === "vscode" ? { url: STUB, shortCircuit: true } : next(spec, ctx); }
`;
register(`data:text/javascript,${encodeURIComponent(hooks)}`);

const { ReplaySession, STAND_IN } = await import("../src/demo.ts");
const { parseReplay } = await import("../src/commands.ts");
const { parseState } = await import("../src/state.ts");
const { actsFor, CHANGES, replayLine } = await import("../src/graph/words.ts");
const raw = readFileSync(new URL("./fixtures/graph-race.json", import.meta.url), "utf8");

test("a replay's state says so, whatever its store says, so the graph offers nothing that changes a plan", () => {
  const s = new ReplaySession("/tmp/graphene-demo-test");
  s.take(parseState(raw));
  const state = s.state as StateX;
  assert.deepEqual(state.replay, STAND_IN);
  assert.equal(replayLine(state.replay), "replay · a scripted stand-in, no model ran");
  assert.ok(state.tasks.length > 1);
  for (const t of state.tasks) {
    const acts: Act[] = actsFor(t, Boolean(state.replay)).map((b) => b.act);
    assert.deepEqual(acts.filter((a) => CHANGES.includes(a)), [], `${t.id} (${t.state}) offers ${acts.join(", ")}`);
  }
});

test("the store's own replay words, once read, are what the header says", () => {
  const s = new ReplaySession("/tmp/graphene-demo-test");
  s.replay = parseReplay(JSON.stringify({ replay: { shown: "a scripted stand-in, no model ran", day: "2026-10-26", repository: "wordkit" } }))!;
  s.take(parseState(raw));
  assert.equal(replayLine((s.state as StateX).replay), "replay · a scripted stand-in, no model ran · 2026-10-26");
  assert.equal(parseReplay(JSON.stringify({ replay: null })), null);
  assert.equal(parseReplay("not json"), null);
});
