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
export const notifications = [];
export const window = { showErrorMessage(m) { notifications.push(m); return Promise.resolve(undefined); }, createWebviewPanel(type, title) { const p = new Panel(type, title); panels.push(p); return p; },
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
const context = { extensionUri: "ext", subscriptions: [], workspaceState: { get: (_: string, fallback: unknown) => fallback, update: async () => {} } } as never;
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

test("a field set on the page is one `node set`, a drawn task one `node add`; graphene's answer goes back to the page", async () => {
  const { parseState } = await import("../src/state.ts");
  const { readFileSync } = await import("node:fs");
  const state = parseState(readFileSync(new URL("./fixtures/graph-race.json", import.meta.url), "utf8"));
  const ran: string[][] = [];
  const change = async (argv: string[]) => {
    ran.push(argv);
    return argv.includes("--forks") ? { ok: false, line: "ship: 3 forks need a check to keep one", stdout: "" } : { ok: true, line: "done", stdout: "○ a flag  n9  ready\n" };
  };
  new GraphHost(context, { ...(session as object), state, change } as never).show();
  const w = vscode.panels.at(-1)!.w as unknown as { sent: unknown[]; receive(m: unknown): Promise<unknown> };
  await w.receive({ type: "act", act: "set", id: "ship", field: "forks", value: 3 });
  assert.deepEqual(ran.at(-1), ["node", "set", "ship", "--forks", "3"]);
  assert.deepEqual(w.sent.at(-1), { type: "said", id: "ship", ok: false, line: "ship: 3 forks need a check to keep one", made: undefined }, "the refusal, whole, for the form");
  await w.receive({ type: "act", act: "set", id: "ship", field: "scope", value: "app.py  tests/**" });
  assert.deepEqual(ran.at(-1), ["node", "set", "ship", "--scope", "app.py", "--scope", "tests/**"]);
  await w.receive({ type: "act", act: "draw", id: "", draft: { key: " d1", title: "a flag", files: "cli.py", check: "pytest -q", approve: true, after: "hello", parent: null } });
  assert.deepEqual(ran.at(-1), ["node", "add", "--needs", "hello", "--scope", "cli.py", "--check", "pytest -q", "--signoff", "--", "a flag"]);
  assert.deepEqual(w.sent.filter((m) => (m as { type: string }).type === "said").at(-1), { type: "said", key: " d1", ok: true, line: "", made: "n9" }, "the draft goes, and the task it became is named");
  const n = ran.length;
  await w.receive({ type: "act", act: "set", id: "ship", field: "forks", value: 99 });
  assert.equal(ran.length, n, "a value the field does not take runs nothing");
  // a drawn task the host will not pass on is still answered, so its page does not wait for ever
  await w.receive({ type: "act", act: "draw", id: "", draft: { key: " d2", title: "x", files: "a.py", check: "true", approve: false, after: "gone", parent: null } });
  assert.equal(ran.length, n);
  const last = w.sent.at(-1) as { type: string; key: string; ok: boolean };
  assert.deepEqual([last.type, last.key, last.ok], ["said", " d2", false]);
});

test("graphene's answer goes to the page that asked: another page's draft has the same key", async () => {
  const { parseState } = await import("../src/state.ts");
  const { readFileSync } = await import("node:fs");
  const state = parseState(readFileSync(new URL("./fixtures/graph-race.json", import.meta.url), "utf8"));
  const host = new GraphHost(context, { ...(session as object), state, change: async () => ({ ok: true, line: "done", stdout: "○ a flag  n9  ready\n" }) } as never);
  host.show();
  const panel = vscode.panels.at(-1)!.w as unknown as { sent: unknown[]; receive(m: unknown): Promise<unknown> };
  const side = { html: "", cspSource: "", sent: [] as unknown[], options: {}, asWebviewUri: (u: unknown) => u, h: (_: unknown) => undefined as unknown,
                 postMessage(m: unknown) { this.sent.push(m); return Promise.resolve(true); }, onDidReceiveMessage(h: (m: unknown) => unknown) { this.h = h; return { dispose() {} }; } };
  host.resolveWebviewView({ webview: side, onDidDispose: () => ({ dispose() {} }), visible: true } as never);
  await panel.receive({ type: "act", act: "draw", id: "", draft: { key: " d1", title: "a flag", files: "cli.py", check: "true", approve: false, after: null, parent: null } });
  assert.ok(panel.sent.some((m) => (m as { type: string }).type === "said"));
  assert.ok(!side.sent.some((m) => (m as { type: string }).type === "said"), "the side bar's own ` d1` is not taken away by the tab's answer");
});

test("draft edits survive a new host, reach both pages, and preserve another page's concurrent draft", async () => {
  const stored = new Map<string, unknown>();
  const ctx = { extensionUri: "ext", subscriptions: [], workspaceState: {
    get: (key: string, fallback: unknown) => stored.get(key) ?? fallback,
    update: async (key: string, value: unknown) => { stored.set(key, structuredClone(value)); },
  } } as never;
  const own = { ...(session as object), folder: { uri: { fsPath: "/fixture" } } } as never;
  const host = new GraphHost(ctx, own);
  host.show();
  const panel = vscode.panels.at(-1)!.w as unknown as { sent: { type: string; drafts?: unknown[] }[]; receive(m: unknown): Promise<unknown> };
  const draft = (key: string) => ({ key, title: "unfinished", files: "a.py", check: "", approve: false, after: null, parent: null });
  await panel.receive({ type: "draft", key: " d1", draft: draft(" d1") });
  await panel.receive({ type: "draft", key: " d2", draft: draft(" d2") });
  await panel.receive({ type: "draft", key: " d1", draft: { ...draft(" d1"), title: "changed" } });
  const restored = new GraphHost(ctx, own);
  restored.show();
  const next = vscode.panels.at(-1)!.w as unknown as typeof panel;
  await next.receive({ type: "ready" });
  assert.equal(next.sent.filter((m) => m.type === "drafts").at(-1)?.drafts?.length, 2);
  await next.receive({ type: "draft", key: " d1", draft: null });
  assert.equal(next.sent.filter((m) => m.type === "drafts").at(-1)?.drafts?.length, 1);
  const otherFolder = new GraphHost(ctx, { ...(own as object), folder: { uri: { fsPath: "/other" } } } as never);
  otherFolder.show();
  const other = vscode.panels.at(-1)!.w as unknown as typeof panel;
  await other.receive({ type: "ready" });
  assert.deepEqual(other.sent.filter((m) => m.type === "drafts").at(-1)?.drafts, []);
});
