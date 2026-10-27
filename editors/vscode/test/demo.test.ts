// The demo's session against a stand-in for the vscode module (a loader hook from this file, as
// graph-host.test.ts does): what the graph is handed for a replay.
import assert from "node:assert/strict";
import { existsSync, mkdtempSync, readFileSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
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

const { ReplaySession, STAND_IN, end } = await import("../src/demo.ts");
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

test("the replay's directory goes with it: at once when the editor quits, after the child's grace when the panel closes", async () => {
  const fake = () => { const c = { exitCode: null as number | null, signal: "", kill(sig: string) { c.signal = sig; c.exitCode = 0; return true; } }; return c; };
  const dir = () => { const d = mkdtempSync(join(tmpdir(), "graphene-demo-")); writeFileSync(join(d, "store"), ""); return d; };

  const quit = dir(), q = fake();
  end(q, quit, true); // the extension's dispose: no timer would fire, so the directory goes now
  assert.equal(existsSync(quit), false, "the directory is gone before dispose returns");
  assert.equal(q.signal, "SIGKILL");

  const closed = dir(), c = fake();
  end(c, closed, false); // the panel's close: TERM, then the directory once the child had its 500 ms
  assert.equal(c.signal, "SIGTERM");
  assert.equal(existsSync(closed), true, "the child gets its grace first");
  await new Promise((r) => setTimeout(r, 700));
  assert.equal(existsSync(closed), false);

  const gone = dir(), g = fake(); g.exitCode = 1; // a child that ended on its own is not killed again
  end(g, gone, true);
  assert.equal(g.signal, "");
  assert.equal(existsSync(gone), false);
});
