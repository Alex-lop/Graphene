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
export const tabs = { front: undefined, early: false }; // the tab the active group has in front; early: asked before VS Code sent its tabs
export const window = { showErrorMessage(m) { notifications.push(m); return Promise.resolve(undefined); }, createWebviewPanel(type, title, show) { const p = new Panel(type, title); p.show = show; panels.push(p); return p; },
  showInformationMessage() { return Promise.resolve(undefined); },
  tabGroups: { get activeTabGroup() { if (tabs.early) throw new Error("Assertion Failed: argument is undefined or null"); return { activeTab: tabs.front }; } } };
export const Uri = { joinPath(...p) { return p.join("/"); } };
export const ViewColumn = { Active: -1, Beside: -2 };
export const workspace = { settings: {}, getConfiguration() { return { get: (k, d) => (k in workspace.settings ? workspace.settings[k] : d) }; } };
export const commands = { ran: [], registered: [], fns: {}, registerCommand(id, fn) { this.registered.push(id); this.fns[id] = fn; return { dispose() {} }; },
  getCommands() { return Promise.resolve(["graphene.runReady", "graphene.stop", "graphene.auto", "graphene.openCockpit", "graphene.addStep", ...this.registered]); },
  executeCommand(id, arg) { this.ran.push([id, arg]); return Promise.resolve(this.fns[id]?.(arg)); } };
`;
const hooks = `
const STUB = ${JSON.stringify(`data:text/javascript,${encodeURIComponent(stub)}`)};
export async function resolve(spec, ctx, next) { return spec === "vscode" ? { url: STUB, shortCircuit: true } : next(spec, ctx); }
`;
register(`data:text/javascript,${encodeURIComponent(hooks)}`);

type Panel = { disposed: boolean; title: string; revealed: number; threw?: string; show?: unknown; dispose(): void; w: { receive(m: unknown): Promise<unknown> } };
const vscode = await import("vscode") as unknown as { panels: Panel[]; commands: { ran: [string, unknown][] }; workspace: { settings: Record<string, unknown> };
                                                      tabs: { front: { input: unknown } | undefined; early: boolean } };
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

test("the tab opens by itself on a start, without the keyboard; Show graph reveals the same tab and may take it; closed by a person, no start opens it again; a replay's never opens by itself", async () => {
  const { parseState } = await import("../src/state.ts");
  const { readFileSync } = await import("node:fs");
  const read = (name: string) => parseState(readFileSync(new URL(`./fixtures/${name}.json`, import.meta.url), "utf8"));
  /** A session whose change the test fires, as a read or the stream does. */
  const live = (over: object = {}) => {
    const s = { ...(session as object), state: null as unknown, fire: () => {}, onDidChange(l: () => void) { s.fire = l; return { dispose() {} }; }, ...over };
    return s;
  };
  const n = vscode.panels.length, opened = () => vscode.panels.length - n;
  const own = live(), host = new GraphHost(context, own as never);
  own.fire(); // a read that gave no plan yet
  assert.equal(opened(), 0);
  own.state = read("proposals"); // the window opened on a plan with work to show
  own.fire();
  own.fire(); // the same snapshot again (its contracts were read): not a second start
  assert.equal(opened(), 1);
  const tab = vscode.panels[n]!;
  assert.deepEqual(tab.show, { viewColumn: -1, preserveFocus: true }, "nobody asked for it: it is not given the keyboard");
  host.show(); // Show graph on Home, a task in the Plan view, the palette
  assert.equal(opened(), 1, "the same tab, not a second one");
  assert.equal(tab.revealed, 1, "revealed, and it may take the keyboard");
  const running = read("running");
  own.state = running; // a run starts while the tab is there
  own.fire();
  assert.deepEqual([opened(), tab.revealed], [1, 1], "it is left as it is: no second tab, and not brought to the front");
  tab.dispose(); // the person closes it
  own.state = { ...running, cursor: 99 }; // the plan moves on
  own.fire();
  own.state = null; // and cannot be read for a moment
  own.fire();
  own.state = { ...running, run: { going: false, pid: null } }; // the run ends
  own.fire();
  assert.equal(opened(), 1, "closed, it stays closed: none of that is a start");
  const again = () => { // a round of `graphene auto`: the plan is done, another appears, its run starts
    for (const next of [{ ...running, tasks: [], run: { going: false, pid: null } }, read("proposals"), running]) { own.state = next; own.fire(); }
  };
  again();
  assert.equal(opened(), 1, "nor do the next plan and the next run open it: a person closed it in this window");
  host.show(); // they ask for it
  assert.deepEqual(vscode.panels[n + 1]!.show, { viewColumn: -1, preserveFocus: false }, "asked for, it opens and takes the keyboard as it did");
  vscode.panels[n + 1]!.dispose(); // and close it again
  again();
  assert.equal(opened(), 2, "closed again, it stays closed again");
  vscode.workspace.settings["graph.openOnStart"] = false;
  const off = live({ state: read("proposals") });
  new GraphHost(context, off as never);
  off.fire();
  delete vscode.workspace.settings["graph.openOnStart"];
  assert.equal(opened(), 2, "the setting off: only Show graph opens it");
  const replay = live({ state: read("running"), own: "/tmp/graphene-demo-x" });
  new GraphHost(context, replay as never, "Graphene demo");
  replay.fire();
  assert.equal(opened(), 2, "Watch the Demo opens its own graph itself");
});

test("by itself the tab opens beside what a person has in front, never over it; asked for, it opens in front as it did", async () => {
  const { parseState } = await import("../src/state.ts");
  const { readFileSync } = await import("node:fs");
  const plan = parseState(readFileSync(new URL("./fixtures/proposals.json", import.meta.url), "utf8"));
  /** A window that opens on a plan with work left, the active group showing `front`: how the tab was asked for. */
  const opened = (front: { input: unknown } | undefined, early = false) => {
    Object.assign(vscode.tabs, { front, early });
    const s = { ...(session as object), state: plan, fire: () => {}, onDidChange(l: () => void) { s.fire = l; return { dispose() {} }; } };
    const host = new GraphHost(context, s as never);
    s.fire();
    const tab = vscode.panels.at(-1)!;
    Object.assign(vscode.tabs, { front: undefined, early: false });
    return { host, tab, show: tab.show };
  };
  const file = { input: { uri: "file:///repo/notes.md" } };
  // in the file's own group the tab would hide the file, and VS Code would leave the keyboard in nothing
  assert.deepEqual(opened(file).show, { viewColumn: -2, preserveFocus: true }, "a file in front stays in front, with its caret: the tab opens beside it");
  assert.deepEqual(opened({ input: { viewType: "another.page" } }).show, { viewColumn: -2, preserveFocus: true }, "so does a page of another extension's");
  assert.deepEqual(opened(undefined).show, { viewColumn: -1, preserveFocus: true }, "an empty editor area: the tab has it");
  assert.deepEqual(opened({ input: undefined }).show, { viewColumn: -1, preserveFocus: true }, "a page of VS Code's own (Welcome): the tab opens in front of it");
  assert.deepEqual(opened(file, true).show, { viewColumn: -1, preserveFocus: true }, "VS Code has not said what is in front yet: nothing is");
  const { host, tab } = opened(file);
  tab.dispose();
  vscode.tabs.front = file;
  host.show(); // Show graph, with the same file in front
  vscode.tabs.front = undefined;
  assert.deepEqual(vscode.panels.at(-1)!.show, { viewColumn: -1, preserveFocus: false }, "asked for, it opens where the person is and takes the keyboard");
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


test("a form refusal is inline once; an act with no form still gets a notification", async () => {
  const { Session } = await import("../src/session.ts");
  const ui = await import("vscode") as unknown as { notifications: string[] };
  ui.notifications.length = 0;
  const fake = { changing: 0, held: null, run: async () => ({ code: 1, stdout: "", stderr: "3 forks need a check\nChoose a check" }),
                 said: (s: string) => s, refresh: async () => {} };
  const result = await Session.prototype.change.call(fake as never, ["node", "set", "n1", "--forks", "3"]);
  assert.equal(result.ok, false);
  assert.match(result.line, /Choose a check/);
  assert.match(result.line, /3 attempts need a check/);
  assert.deepEqual(ui.notifications, [], "the form displays the refusal, so no toast duplicates it");
  await Session.prototype.act.call({ change: async () => result } as never, ["node", "set", "n1"]);
  assert.equal(ui.notifications.length, 1);
});

test("the graph header's switch moves as Home's does: with Exact on, its three settings go back before auto turns on", async () => {
  const { HomeHost } = await import("../src/home.ts");
  const { parseState } = await import("../src/state.ts");
  const state = parseState(JSON.stringify({ envelope: { review: "every", auto: "off" } }));
  const ran: string[][] = [];
  const fake = { ...(session as object), state, seen: new Set(), onDidSee: () => ({ dispose() {} }), refresh: async () => {},
    run: async (argv: string[]) => { ran.push(argv); return { code: 0, stdout: "board: on\n", stderr: "" }; }, // `graphene config`: Exact is on
    act: async (argv: string[]) => { ran.push(argv); return true; } } as never;
  new HomeHost(context, fake); // it registers graphene.stopAfter; Home's page was never opened, so the board setting is read then
  new GraphHost(context, fake).show();
  await vscode.panels.at(-1)!.w.receive({ type: "act", act: "stopAfter", id: "", value: false });
  assert.deepEqual(vscode.commands.ran.at(-1), ["graphene.stopAfter", false]);
  assert.deepEqual(ran.filter((argv) => argv.length > 1), [["config", "set", "board", "auto"], ["config", "set", "review", "every"], ["config", "set", "auto", "off"],
                                                          ["config", "set", "auto", "on"]], "Exact's three go back together, then the switch moves");
});

test("Home disables Start while planning finishes, so a visible plan cannot swallow the click", async () => {
  const { HomeHost } = await import("../src/home.ts");
  const { parseState } = await import("../src/state.ts");
  const { readFileSync } = await import("node:fs");
  const state = parseState(readFileSync(new URL("./fixtures/proposals.json", import.meta.url), "utf8"));
  const fake = { ...(session as object), state, seen: new Set(), onDidSee: () => ({ dispose() {} }) } as never;
  const host = new HomeHost(context, fake);
  const page = { html: "", cspSource: "", options: {}, asWebviewUri: (u: unknown) => u,
    sent: [] as { type: string; home: { sections: { buttons: { act: string; off?: boolean }[] }[] } }[],
    postMessage(m: never) { this.sent.push(m); return Promise.resolve(true); }, onDidReceiveMessage() { return { dispose() {} }; } };
  host.resolveWebviewView({ webview: page, onDidDispose: () => ({ dispose() {} }), visible: true } as never);
  const inspect = host as unknown as { busy: string; push(): void };
  const start = () => page.sent.at(-1)!.home.sections.flatMap((s) => s.buttons).find((b) => b.act === "startAll")!;
  inspect.busy = "Planning…";
  inspect.push();
  assert.equal(start().off, true);
  inspect.busy = "";
  inspect.push();
  assert.equal(start().off, false);
});
