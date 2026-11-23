// The demo's session against a stand-in for the vscode module (a loader hook from this file, as
// graph-host.test.ts does): what the graph is handed for a replay.
import assert from "node:assert/strict";
import { chmodSync, existsSync, mkdtempSync, readFileSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { register } from "node:module";
import { test } from "node:test";
import type { Act, StateX } from "../src/graph/words.ts";

const stub = `
export class EventEmitter { constructor() { this.ls = []; this.event = (l) => { this.ls.push(l); return { dispose() {} }; }; }
  fire(v) { for (const l of this.ls) l(v); } dispose() {} }
export const Uri = { file(p) { return { fsPath: p, path: p, scheme: "file" }; }, joinPath(...p) { return p.join("/"); } };
export const workspace = { getConfiguration() { return { get(k) { return globalThis.settings?.[k]; } }; }, workspaceFolders: [] };
export const registered = {}, warned = [], told = [], panels = [];
export const commands = { executeCommand() { return Promise.resolve(); }, registerCommand(id, f) { registered[id] = f; return { dispose() {} }; },
  getCommands() { return Promise.resolve([]); } };
const webview = { cspSource: "", html: "", asWebviewUri(u) { return u; }, postMessage() { return Promise.resolve(true); }, onDidReceiveMessage() { return { dispose() {} }; } };
class Panel { constructor() { this.webview = webview; this.closed = []; } onDidDispose(h) { this.closed.push(h); return { dispose() {} }; } onDidChangeViewState() { return { dispose() {} }; }
  get visible() { return true; } reveal() {} dispose() { for (const h of this.closed) h(); } }
export const window = { showInformationMessage(m) { told.push(m); return Promise.resolve(undefined); }, showErrorMessage() { return Promise.resolve(undefined); },
  showWarningMessage(...m) { warned.push(m); return Promise.resolve(undefined); },
  createWebviewPanel() { const p = new Panel(); panels.push(p); return p; } };
export const env = { appName: "Visual Studio Code" };
export const ViewColumn = { Active: -1, Beside: -2 };
`;
const hooks = `
const STUB = ${JSON.stringify(`data:text/javascript,${encodeURIComponent(stub)}`)};
export async function resolve(spec, ctx, next) { return spec === "vscode" ? { url: STUB, shortCircuit: true } : next(spec, ctx); }
`;
register(`data:text/javascript,${encodeURIComponent(hooks)}`);

const { ReplaySession, STAND_IN, end, NEEDS, register: demo } = await import("../src/demo.ts");
const vs = (await import("vscode")) as unknown as { registered: Record<string, () => Promise<void>>; warned: unknown[][]; told: string[]; panels: { dispose(): void }[] };
const { STORE } = await import("../src/session.ts");
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

test("with no graphene, Watch the Demo says what it needs and offers Install, not a spawn's error code", async () => {
  const context = { subscriptions: [] as { dispose(): void }[], workspaceState: { get: (_k: string, d: unknown) => d } };
  const watch = async (session: object) => {
    vs.warned.length = 0;
    demo(context as never, session as never, {} as never);
    await vs.registered["graphene.watchDemo"]!();
  };
  await watch({ status: { kind: "missing", text: "" }, path: "graphene" }); // Home and the walkthrough know it already
  assert.deepEqual(vs.warned, [[NEEDS, "Install Graphene"]]);
  await watch({ status: { kind: "nofolder", text: "" }, path: join(tmpdir(), "no-such-graphene") }); // no folder: the spawn finds out
  assert.deepEqual(vs.warned, [[NEEDS, "Install Graphene"]]);
  for (const d of context.subscriptions) d.dispose();
});

test("an old demo's graph closing does not end the demo playing now", async (t) => {
  // its poll a mock, and its replay a few seconds long: a lost demo, the fault this test is for, ends the file anyway
  t.mock.timers.enable({ apis: ["setInterval"] });
  // a stand-in graphene: `demo` makes its store, then plays for as long as `nap` says; anything else fails
  const bin = mkdtempSync(join(tmpdir(), "graphene-bin-")), fake = join(bin, "graphene"), nap = join(bin, "nap"), store = `"$4/${STORE}"`;
  writeFileSync(fake, `#!/bin/sh\n[ "$1" = demo ] || exit 1\nmkdir -p "$(dirname ${store})" && : > ${store}\nexec sleep "$(cat "${nap}")"\n`);
  chmodSync(fake, 0o755);
  (globalThis as { settings?: object }).settings = { path: fake };
  const context = { subscriptions: [] as { dispose(): void }[], workspaceState: { get: (_k: string, d: unknown) => d } };
  demo(context as never, { status: { kind: "ok", text: "" }, path: fake } as never, {} as never);
  const watch = vs.registered["graphene.watchDemo"]!;

  writeFileSync(nap, "1");
  await watch(); // the first plays to its end, and its graph stays open
  await new Promise((r) => setTimeout(r, 1300));
  writeFileSync(nap, "5");
  await watch(); // the second plays on
  assert.equal(vs.panels.length, 2);
  vs.panels[0]!.dispose(); // the first one's graph closed
  vs.told.length = 0;
  await watch();
  assert.deepEqual(vs.told, ["The demo is already playing. Close its graph to stop it."]);
  assert.equal(vs.panels.length, 2, "no third demo");
  vs.panels[1]!.dispose(); // the second's own graph ends it
});
