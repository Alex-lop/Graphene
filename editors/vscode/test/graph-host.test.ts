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
export const env = { appName: "Visual Studio Code" };
export const ViewColumn = { Active: -1, Beside: -2 };
export const workspace = { settings: {}, getConfiguration() { return { get: (k, d) => (k in workspace.settings ? workspace.settings[k] : d) }; } };
export const commands = { ran: [], registered: [], fns: {}, registerCommand(id, fn) { this.registered.push(id); this.fns[id] = fn; return { dispose() {} }; },
  getCommands() { return Promise.resolve(["graphene.runReady", "graphene.stop", "graphene.openCockpit", "graphene.addStep", ...this.registered]); },
  executeCommand(id, arg) { this.ran.push([id, arg]); return Promise.resolve(this.fns[id]?.(arg)); } };
`;
const hooks = `
const STUB = ${JSON.stringify(`data:text/javascript,${encodeURIComponent(stub)}`)};
export async function resolve(spec, ctx, next) { return spec === "vscode" ? { url: STUB, shortCircuit: true } : next(spec, ctx); }
`;
register(`data:text/javascript,${encodeURIComponent(hooks)}`);

type Panel = { disposed: boolean; title: string; revealed: number; threw?: string; show?: unknown; dispose(): void; w: { html: string; receive(m: unknown): Promise<unknown> } };
const vscode = await import("vscode") as unknown as { panels: Panel[]; commands: { ran: [string, unknown][] }; workspace: { settings: Record<string, unknown> }; env: { appName: string };
                                                      tabs: { front: { input: unknown } | undefined; early: boolean } };
const { GraphHost } = await import("../src/graph.ts");
const context = { extensionUri: "ext", subscriptions: [], workspaceState: { get: (_: string, fallback: unknown) => fallback, update: async () => {} } } as never;
const session = { state: null, status: { kind: "reading", text: "Reading the plan…" }, onDidChange: () => ({ dispose() {} }), seen: new Set(), onDidSee: () => ({ dispose() {} }) } as never;

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
  // Graphene's icon is clicked: Home comes into view, and the tab opens with it, on any plan, once it is read
  const gone = live(), away = new GraphHost(context, gone as never);
  away.sidebar(); // before the first read (a folder not set up yet), and back to the Explorer
  away.sidebar(false);
  gone.state = read("empty"); // an hour later the folder is set up
  gone.fire();
  assert.equal(opened(), 2, "the side bar out of view no longer asks: a read much later opens nothing");
  const icon = live(), clicked = new GraphHost(context, icon as never);
  clicked.sidebar(); // before the first read: nothing to show yet
  assert.equal(opened(), 2);
  icon.state = read("empty");
  vscode.tabs.front = { input: { uri: "file:///repo/notes.md" } }; // a file in front
  icon.fire(); // an empty plan: no start, but the side bar asked
  vscode.tabs.front = undefined;
  assert.equal(opened(), 3, "a click on the icon lands on the graph, an empty plan's included");
  assert.deepEqual(vscode.panels.at(-1)!.show, { viewColumn: -1, preserveFocus: true },
    "in the active group, whole, a file in front or not (beside, it would be the narrow lanes), and the keyboard left in the side bar");
  clicked.sidebar(); // the side bar again, the tab there
  assert.equal(opened(), 3, "a tab that is there is left as it is");
  vscode.panels.at(-1)!.dispose();
  clicked.sidebar(); // the side bar again, after a person closed the tab
  assert.equal(opened(), 3, "closed in this window, it stays closed: Open the graph on Home brings it back");
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
  vscode.env.appName = "Cursor";
  assert.deepEqual(opened(file).show, { viewColumn: -1, preserveFocus: true }, "in Cursor, whose chat narrows the editor area, it opens in the file's group without the keyboard");
  vscode.env.appName = "Visual Studio Code";
});

test("a practice run's page and a replay's are sent no cost: no card, lane, attempt or Cost row can say one", async () => {
  const { parseState } = await import("../src/state.ts");
  const { readFileSync } = await import("node:fs");
  const running = parseState(readFileSync(new URL("./fixtures/running.json", import.meta.url), "utf8"));
  const sent = (state: unknown) => {
    const host = new GraphHost(context, { ...(session as object), state, onDidChange: () => ({ dispose() {} }) } as never);
    host.show();
    void vscode.panels.at(-1)!.w.receive({ type: "ready" });
    const w = vscode.panels.at(-1)!.w as unknown as { sent: { type: string; state?: typeof running }[] };
    return w.sent.find((m) => m.type === "state")!.state!;
  };
  const money = (s: typeof running) => [s.spent, ...s.tasks.flatMap((t) => [t.usd, ...t.forks.map((f) => f.usd)])].filter((x) => x !== null);
  assert.ok(money(sent(running)).length > 0, "a real run's cost is sent");
  assert.deepEqual(money(sent({ ...running, stand_in: true })), [], "the scripted stand-in's");
  assert.deepEqual(money(sent({ ...running, replay: { shown: "demo", day: "", repository: "" } })), [], "a replay's");
});

test("a replay's host runs no command of the person's, even before its plan is read; the person's own host does", async () => {
  // a replay's state is null before its store reads (and after a read fails): check() lets the acts that
  // take no id through then, and every command they name acts on the person's folder
  const acts = ["run", "stop", "cockpit", "add-under"];
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

test("in Cursor the page is told so (it says Cursor's own Agent does not plan here); in VS Code it is not", () => {
  new GraphHost(context, session).show();
  assert.doesNotMatch(vscode.panels.at(-1)!.w.html, /data-editor/);
  vscode.env.appName = "Cursor";
  new GraphHost(context, session).show();
  vscode.env.appName = "Visual Studio Code";
  assert.match(vscode.panels.at(-1)!.w.html, /<body data-editor="cursor">/);
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

test("the header's Start is Home's: every suggested task accepted, then the run; a question with no default holds it, and with Exact on any question", async () => {
  const { parseState } = await import("../src/state.ts");
  const { readFileSync } = await import("node:fs");
  const C = await import("../src/commands.ts");
  const plan = parseState(readFileSync(new URL("./fixtures/proposals.json", import.meta.url), "utf8")); // its question has a default
  const ran: string[][] = [];
  const page = (state: unknown, board = "off") => {
    new GraphHost(context, { ...(session as object), state, act: async (argv: string[]) => { ran.push(argv); return true; },
      run: async (argv: string[]) => { ran.push(argv); return { code: 0, stdout: `board: ${board}\n`, stderr: "" }; } } as never).show();
    return vscode.panels.at(-1)!.w;
  };
  const started = () => vscode.commands.ran.filter((r) => r[0] === "graphene.runReady").length, n = started();
  await page(plan).receive({ type: "act", act: "start", id: "" });
  assert.deepEqual([ran, started() - n], [[C.acceptAll()], 1], "accepted, then the run, as Home's Start");
  ran.length = 0;
  await page({ ...plan, questions: plan.questions.map((q) => ({ ...q, default: null })) }).receive({ type: "act", act: "start", id: "" });
  const exact = { ...plan, envelope: { ...plan.envelope, review: "every", auto: "off" } };
  await page(exact, "on").receive({ type: "act", act: "start", id: "" });
  assert.deepEqual([ran.filter((argv) => argv[0] !== "config"), started() - n], [[], 1], "held: nothing accepted, nothing run");
  const told = page(exact, "on") as unknown as { sent: { type: string; exact?: boolean }[]; receive(m: unknown): Promise<unknown> };
  await told.receive({ type: "ready" });
  await new Promise((r) => setTimeout(r, 0)); // `graphene config` answered
  assert.equal(told.sent.filter((m) => m.type === "state").at(-1)?.exact, true, "the page is told, so its Start is held before a click, as Home's");
  ran.length = 0;
  await page(exact, "off").receive({ type: "act", act: "start", id: "" });
  assert.deepEqual([ran.filter((argv) => argv[0] !== "config"), started() - n], [[C.acceptAll()], 2], "Exact off: the default answers, as Home's Start takes it");
});

test("Home's Stop after the plan, turned off with Exact on: Exact's three settings go back first, then auto turns on", async () => {
  const { HomeHost } = await import("../src/home.ts");
  const { parseState } = await import("../src/state.ts");
  const state = parseState(JSON.stringify({ envelope: { review: "every", auto: "off" } }));
  const ran: string[][] = [];
  const fake = { ...(session as object), state, seen: new Set(), onDidSee: () => ({ dispose() {} }), refresh: async () => {},
    run: async (argv: string[]) => { ran.push(argv); return argv.length === 1 ? { code: 0, stdout: "board: on\n", stderr: "" } : { code: argv[0] === "config" ? 0 : 1, stdout: "", stderr: "" }; },
    act: async (argv: string[]) => { ran.push(argv); return true; } } as never;
  let said: (m: unknown) => void = () => {};
  const page = { html: "", cspSource: "", options: {}, asWebviewUri: (u: unknown) => u, postMessage: () => Promise.resolve(true),
    onDidReceiveMessage(h: (m: unknown) => void) { said = h; return { dispose() {} }; } };
  new HomeHost(context, fake).resolveWebviewView({ webview: page, onDidDispose: () => ({ dispose() {} }), onDidChangeVisibility: () => ({ dispose() {} }), visible: true } as never);
  const settled = async () => { for (let i = 0; i < 50; i++) await new Promise((r) => setTimeout(r, 0)); };
  said({ type: "ready" }); // Home reads `board:` as it opens
  await settled();
  said({ type: "act", act: "stopAfter", flag: false });
  await settled();
  assert.deepEqual(ran.filter((argv) => argv[0] === "config" && argv.length > 1), [["config", "set", "board", "auto"], ["config", "set", "review", "every"], ["config", "set", "auto", "off"],
                                                                                  ["config", "set", "auto", "on"]], "Exact's three go back together, then the switch moves");
});

test("Home disables Start while it is busy (a workflow proposing), so a plan that appears cannot swallow the click", async () => {
  const { HomeHost } = await import("../src/home.ts");
  const { parseState } = await import("../src/state.ts");
  const { readFileSync } = await import("node:fs");
  const state = parseState(readFileSync(new URL("./fixtures/proposals.json", import.meta.url), "utf8"));
  const fake = { ...(session as object), state, seen: new Set(), onDidSee: () => ({ dispose() {} }) } as never;
  const host = new HomeHost(context, fake);
  const page = { html: "", cspSource: "", options: {}, asWebviewUri: (u: unknown) => u,
    sent: [] as { type: string; home: { sections: { buttons: { act: string; off?: boolean }[] }[] } }[],
    postMessage(m: never) { this.sent.push(m); return Promise.resolve(true); }, onDidReceiveMessage() { return { dispose() {} }; } };
  host.resolveWebviewView({ webview: page, onDidDispose: () => ({ dispose() {} }), onDidChangeVisibility: () => ({ dispose() {} }), visible: true } as never);
  const inspect = host as unknown as { busy: string; push(): void };
  const start = () => page.sent.at(-1)!.home.sections.flatMap((s) => s.buttons).find((b) => b.act === "startAll")!;
  inspect.busy = "Proposing fix-issue…";
  inspect.push();
  assert.equal(start().off, true);
  inspect.busy = "";
  inspect.push();
  assert.equal(start().off, false);
});

test("the pane's Send back… is Home's: a note asked, then graphene node reopen; and the page hears whose changes were opened", async () => {
  const { HomeHost } = await import("../src/home.ts");
  const { parseState } = await import("../src/state.ts");
  const { readFileSync } = await import("node:fs");
  const C = await import("../src/commands.ts");
  const state = parseState(readFileSync(new URL("./fixtures/running.json", import.meta.url), "utf8"));
  const acted: string[][] = [], saw: (() => void)[] = [];
  const fake = { ...(session as object), state, seen: new Set<string>(), tasks: () => state.tasks, onDidSee: (l: () => void) => { saw.push(l); return { dispose() {} }; },
                 act: async (argv: string[]) => { acted.push(argv); return true; } };
  new HomeHost(context, fake as never); // it registers graphene.sendBack
  (vscode as unknown as { window: Record<string, unknown> }).window.showInputBox = async () => "it names the wrong route";
  new GraphHost(context, fake as never).show();
  const page = vscode.panels.at(-1)!.w as unknown as { sent: { type: string; seen?: string[] }[]; receive(m: unknown): Promise<unknown> };
  await page.receive({ type: "act", act: "sendBack", id: "docs" });
  assert.deepEqual(acted, [C.reopen("docs", "it names the wrong route")]);
  await page.receive({ type: "ready" });
  assert.deepEqual(page.sent.filter((m) => m.type === "state").at(-1)?.seen, []);
  fake.seen.add("docs"); // its changes opened (diff.ts)
  for (const l of saw) l();
  assert.deepEqual(page.sent.filter((m) => m.type === "state").at(-1)?.seen, ["docs"], "so its pane's act is Approve now");
});
