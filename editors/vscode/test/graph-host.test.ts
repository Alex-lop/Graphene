// The graph's host against a stand-in for the vscode module: a panel that, once disposed, throws on
// `webview` and `visible` as the real one does. The stub is registered as a loader hook from this file,
// so the test needs no extra module on disk.
import assert from "node:assert/strict";
import { register } from "node:module";
import { test } from "node:test";

const stub = `
export const panels = [];
export class EventEmitter { constructor() { this.ls = []; this.event = (l) => { this.ls.push(l); return { dispose() {} }; }; }
  fire(v) { for (const l of this.ls) l(v); } dispose() {} }
class Webview { constructor() { this.html = ""; this.cspSource = "vscode-webview:"; this.sent = []; }
  asWebviewUri(u) { return u; } postMessage(m) { this.sent.push(m); return Promise.resolve(true); }
  onDidReceiveMessage(h) { this.h = h; return { dispose() {} }; } receive(m) { return this.h(m); } }
class Panel { constructor(type, title) { this.type = type; this.title = title; this.disposed = false; this.revealed = 0; this.w = new Webview(); this.handlers = []; }
  get webview() { if (this.disposed) throw new Error("Webview is disposed"); return this.w; }
  get visible() { if (this.disposed) throw new Error("Webview is disposed"); return true; }
  onDidDispose(h) { this.handlers.push(h); return { dispose() {} }; }
  reveal() { if (this.disposed) throw new Error("Webview is disposed"); this.revealed++; }
  dispose() { this.disposed = true; for (const h of this.handlers) { try { h(); } catch (e) { this.threw = String(e); } } } }
export const window = { createWebviewPanel(type, title) { const p = new Panel(type, title); panels.push(p); return p; },
  showInformationMessage() { return Promise.resolve(undefined); } };
export const Uri = { joinPath(...p) { return p.join("/"); } };
export const ViewColumn = { Active: -1 };
export const commands = { ran: [], getCommands() { return Promise.resolve(["graphene.runReady", "graphene.stop", "graphene.auto", "graphene.openCockpit", "graphene.addStep"]); },
  executeCommand(id, arg) { this.ran.push([id, arg]); return Promise.resolve(); } };
`;
const hooks = `
const STUB = ${JSON.stringify(`data:text/javascript,${encodeURIComponent(stub)}`)};
export async function resolve(spec, ctx, next) { return spec === "vscode" ? { url: STUB, shortCircuit: true } : next(spec, ctx); }
`;
register(`data:text/javascript,${encodeURIComponent(hooks)}`);

type Panel = { disposed: boolean; title: string; revealed: number; threw?: string; dispose(): void; w: { receive(m: unknown): Promise<unknown> } };
const vscode = await import("vscode") as unknown as { panels: Panel[]; commands: { ran: [string, unknown][] } };
const { GraphHost } = await import("../src/graph.ts");
const context = { extensionUri: "ext", subscriptions: [] } as never;
const session = { state: null, status: { kind: "reading", text: "Reading the plan…" }, onDidChange: () => ({ dispose() {} }) } as never;

test("a closed panel is let go: open is false, a new show makes a new panel, and onDidClose fires once", () => {
  const host = new GraphHost(context, session);
  let closed = 0;
  host.onDidClose(() => closed++);
  host.show();
  assert.equal(vscode.panels.length, 1);
  assert.equal(host.open, true);
  vscode.panels[0]!.dispose();
  assert.equal(vscode.panels[0]!.threw, undefined, "the dispose handler must not touch the disposed webview");
  assert.equal(host.open, false);
  assert.equal(closed, 1);
  host.show("hello");
  assert.equal(vscode.panels.length, 2, "a show after the close makes a new panel, not a reveal of the dead one");
  assert.equal(vscode.panels[0]!.revealed, 0);
});

test("a replay's host runs no command of the person's, even before its plan is read; the person's own host does", async () => {
  // a replay's state is null before its store reads (and after a read fails): check() lets the acts that
  // take no id through then, and every command they name acts on the person's folder
  const acts = ["run", "stop", "auto", "cockpit", "add-under"];
  const replay = new GraphHost(context, { ...(session as object), own: "/tmp/graphene-demo-x" } as never, "Graphene demo");
  replay.show();
  const w = vscode.panels.at(-1)!.w;
  for (const act of acts) await w.receive({ type: "act", act, id: "" });
  const ran = () => vscode.commands.ran.map((r) => r[0]);
  assert.deepEqual(ran(), [], "a replay is watched: nothing it asks reaches the person's plan");
  await w.receive({ type: "ready" });
  assert.deepEqual(ran(), [], "ready is answered with a push, not a command");
  const own = new GraphHost(context, session);
  own.show();
  await vscode.panels.at(-1)!.w.receive({ type: "act", act: "cockpit", id: "" });
  assert.deepEqual(ran(), ["graphene.openCockpit"]);
});

test("the panel takes the title the host was given; Graphene by default", () => {
  const n = vscode.panels.length;
  new GraphHost(context, session, "Graphene demo").show();
  new GraphHost(context, session).show();
  assert.equal(vscode.panels[n]!.title, "Graphene demo");
  assert.equal(vscode.panels[n + 1]!.title, "Graphene");
});
