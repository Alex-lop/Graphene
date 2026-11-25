// The sessions' host (src/sessions/hub.ts) against a stand-in for the vscode module and session files in a scratch
// home: which sessions get a page by themselves, where it opens, what a reload brings back.
import assert from "node:assert/strict";
import { appendFileSync, mkdirSync, mkdtempSync, readdirSync, realpathSync, rmSync, writeFileSync } from "node:fs";
import { register } from "node:module";
import * as os from "node:os";
import * as path from "node:path";
import { after, test } from "node:test";

const stub = `
export const panels = [];
export class EventEmitter { constructor() { this.ls = []; this.event = (l) => { this.ls.push(l); return { dispose() {} }; }; }
  fire(v) { for (const l of this.ls) l(v); } dispose() {} }
class Webview { constructor() { this.html = ""; this.cspSource = "vscode-webview:"; this.sent = []; }
  asWebviewUri(u) { return u; } postMessage(m) { this.sent.push(m); return Promise.resolve(true); }
  onDidReceiveMessage(h) { this.h = h; return { dispose() {} }; } }
export class Panel { constructor(type, title, show) { this.type = type; this.title = title; this.show = show; this.viewColumn = show.viewColumn < 0 ? (show.viewColumn === -2 ? 2 : 1) : show.viewColumn;
    this.visible = true; this.webview = new Webview(); this.handlers = []; }
  onDidDispose(h) { this.handlers.push(h); return { dispose() {} }; } onDidChangeViewState() { return { dispose() {} }; }
  reveal() { this.revealed = true; } dispose() { for (const h of this.handlers) h(); } }
export class TabInputWebview { constructor(viewType) { this.viewType = viewType; } }
export const tabs = { front: undefined, active: 1, all: [] };
export const window = { createWebviewPanel(type, title, show) { const p = new Panel(type, title, show); panels.push(p); return p; },
  showInformationMessage() { return Promise.resolve(undefined); }, showErrorMessage() { return Promise.resolve(undefined); }, terminals: [],
  tabGroups: { get activeTabGroup() { return { activeTab: tabs.front, viewColumn: tabs.active }; }, get all() { return [{ tabs: tabs.all }]; } } };
export const Uri = { joinPath(...p) { return { fsPath: p.join("/") }; } };
export class ThemeIcon {}
export const env = { appName: "Visual Studio Code" };
export const ViewColumn = { Active: -1, Beside: -2 };
export const workspace = { workspaceFolders: [], settings: {}, getConfiguration() { return { get: (k, d) => (k in workspace.settings ? workspace.settings[k] : d) }; } };
`;
register(`data:text/javascript,${encodeURIComponent(`const STUB = ${JSON.stringify(`data:text/javascript,${encodeURIComponent(stub)}`)};
export async function resolve(spec, ctx, next) { return spec === "vscode" ? { url: STUB, shortCircuit: true } : next(spec, ctx); }`)}`);

type Panel = { title: string; show: { viewColumn: number; preserveFocus: boolean }; viewColumn: number; webview: { sent: { type: string; state?: { sessions: { id: string }[] } }[] }; dispose(): void };
const vscode = await import("vscode") as unknown as {
  panels: Panel[]; Panel: new (type: string, title: string, show: object) => Panel; TabInputWebview: new (viewType: string) => object;
  tabs: { front: unknown; active: number; all: { input: unknown }[] }; workspace: { workspaceFolders: unknown[]; settings: Record<string, unknown> } };
const { Hub, PAGE } = await import("../src/sessions/hub.ts");
const { encoded } = await import("../src/sessions/find.ts");

const home = realpathSync(mkdtempSync(path.join(os.tmpdir(), "graphene-hub-"))), folder = path.join(home, "work", "app");
process.env.CLAUDE_CONFIG_DIR = path.join(home, "claude");
process.env.CODEX_HOME = path.join(home, "codex");
const dir = path.join(home, "claude", "projects", encoded(folder));
mkdirSync(dir, { recursive: true });
mkdirSync(folder, { recursive: true });
vscode.workspace.workspaceFolders = [{ uri: { fsPath: folder } }];
const line = (text: string) => `${JSON.stringify({ type: "user", cwd: folder, sessionId: "s", timestamp: new Date().toISOString(), message: { content: text } })}\n`;
const file = (name: string) => path.join(dir, `${name}.jsonl`);
const memory = new Map<string, unknown>();
const context = { extensionUri: "ext", subscriptions: [], workspaceState: { get: (k: string, d: unknown) => memory.get(k) ?? d, update: async (k: string, v: unknown) => { memory.set(k, v); } } } as never;
const settle = () => new Promise((r) => setTimeout(r, 30));
// one host at a time, as a window has: each test lets its own go, with its pages
let live: InstanceType<typeof Hub> | null = null;
const hub = () => { live?.dispose(); for (const p of [...vscode.panels]) close(p); live = new Hub(context); return live; };
const close = (p: Panel) => { vscode.panels.splice(vscode.panels.indexOf(p), 1); p.dispose(); };
after(() => { live?.dispose(); rmSync(home, { recursive: true }); });

test("a session that begins or writes gets a page once, beside the file in front, without the keyboard; never the ones that were there", async () => {
  writeFileSync(file("old"), line("an old session"));
  const h = hub();
  h.start();
  await h.scan(); await settle();
  assert.equal(vscode.panels.length, 0, "no page for a session that was there before the window");
  vscode.tabs.front = { input: { uri: "notes.md" } }; // a file is in front, and typed in
  writeFileSync(file("new"), line("a new session"));
  await h.scan(); await settle();
  assert.equal(vscode.panels.length, 1);
  assert.deepEqual(vscode.panels[0]!.show, { viewColumn: -2, preserveFocus: true }); // beside it, and the keyboard stays
  appendFileSync(file("new"), line("more"));
  appendFileSync(file("old"), line("the old one writes too"));
  await h.scan(); await settle();
  assert.equal(vscode.panels.length, 2, "an old session that writes gets its page now");
  assert.equal(vscode.panels[1]!.show.viewColumn, 2, "in the group the first page stands in: pages gather there");
  // closed by the person, a session is not chased by its next line
  close(vscode.panels[0]!);
  appendFileSync(file("new"), line("and more"));
  await h.scan(); await settle();
  assert.equal(vscode.panels.length, 1);
  // the setting turns it off
  vscode.workspace.settings["graph.openOnStart"] = false;
  writeFileSync(file("third"), line("a third session"));
  await h.scan(); await settle();
  assert.equal(vscode.panels.length, 1);
  delete vscode.workspace.settings["graph.openOnStart"];
  for (const p of [...vscode.panels]) close(p);
});

test("a page asked for with a file in its own group is not where the next one opens over that file", async () => {
  const h = hub();
  h.start();
  await h.scan(); await settle();
  vscode.tabs.front = { input: { uri: "notes.md" } };
  vscode.tabs.active = 1;
  await h.show(file("old")); // asked for (Home, the palette): in the active group, the file's own
  assert.equal(vscode.panels[0]!.viewColumn, 1);
  writeFileSync(file("fourth"), line("a fourth session"));
  await h.scan(); await settle();
  assert.deepEqual(vscode.panels[1]!.show, { viewColumn: -2, preserveFocus: true }, "beside the file, not over it in the group the first page shares with it");
  assert.equal(await h.show(file("gone")), undefined, "a session the folder does not have opens no page");
  for (const p of [...vscode.panels]) close(p);
});

test("leaving strict mode is a first look again: no burst of pages for what was written meanwhile", async () => {
  const h = hub();
  h.start();
  await h.scan(); await settle();
  h.stop(); // the folder gained a plan
  for (const n of ["a", "b", "c"]) writeFileSync(file(`meanwhile-${n}`), line("written in strict mode"));
  h.start(); // and lost it
  await h.scan(); await settle();
  assert.equal(vscode.panels.length, 0);
});

test("a reload: a page behind another keeps its session until it is shown, and that session gets no second page", async () => {
  const before = hub();
  before.start();
  await before.scan(); await settle();
  await before.show(file("old"));
  await before.show(file("new"));
  assert.equal(vscode.panels.length, 2);
  assert.deepEqual(new Set(memory.get("graphene.sessions.paged") as string[]), new Set([file("old"), file("new")])); // the workspace remembers which sessions a page draws
  // the window reloads: both tabs are there, and the editor brings back only the one in front
  vscode.panels.length = 0; // gone with the window, not closed by the person
  vscode.tabs.all = [{ input: new vscode.TabInputWebview(`mainThreadWebview-${PAGE}`) }, { input: new vscode.TabInputWebview(`mainThreadWebview-${PAGE}`) }];
  const h = hub();
  h.start();
  const front = new vscode.Panel(PAGE, "", { viewColumn: 2 });
  await h.deserializeWebviewPanel(front as never, { page: [file("old")] });
  assert.equal(h.pages.length, 1);
  appendFileSync(file("new"), line("the session of the page behind writes"));
  await h.scan(); await settle();
  assert.equal(vscode.panels.length, 0, "no second page for a session whose page is a tab not shown yet");
  // its tab is shown: it comes back with its session, and still there is one page for it
  const behind = new vscode.Panel(PAGE, "", { viewColumn: 2 });
  await h.deserializeWebviewPanel(behind as never, { page: [file("new"), file("old"), 7, "/no/such.jsonl"] });
  // each page comes back with the sessions it drew (one may be on two pages: Add to page…); what is not a session of the folder's is left out
  assert.deepEqual(h.pages.map((p) => p.follows.map((f) => path.basename(f.found.file))), [["old.jsonl"], ["new.jsonl", "old.jsonl"]]);
  assert.equal(vscode.panels.length, 0, "and no page was opened beside the ones that came back");
  vscode.tabs.all = [];
});

test("in a folder with a plan a page a reload brought back is still read, and no session gets a page by itself", async () => {
  const h = hub(); // never started: strict mode
  const panel = new vscode.Panel(PAGE, "", { viewColumn: 1 });
  await h.deserializeWebviewPanel(panel as never, { page: [file("old")] });
  const page = h.pages[0]!;
  await page.refresh(new Map(), true);
  const sent = () => panel.webview.sent.filter((m) => m.type === "state").length;
  assert.equal(sent(), 1);
  appendFileSync(file("old"), line("it goes on"));
  await new Promise((r) => setTimeout(r, 1300)); // its files are read every second while the page is there
  assert.ok(sent() >= 2, "the page was drawn again from what its session wrote");
  writeFileSync(file("in-strict"), line("a session begins in strict mode"));
  await h.scan(); await settle();
  assert.equal(vscode.panels.length, 0);
  panel.dispose();
});

test("the status bar's count of sessions at work goes by what their files say: a turn that ended is over, whatever is still running", async () => {
  for (const f of readdirSync(dir)) rmSync(path.join(dir, f), { recursive: true }); // the sessions the tests above left asked and unanswered
  const h = hub();
  h.start();
  await h.scan(); await settle();
  assert.equal(await h.working(), 0);
  const said = (id: string, more: Record<string, unknown>) => `${JSON.stringify({ cwd: folder, sessionId: id, timestamp: new Date().toISOString(), ...more })}\n`;
  // one session asked and at work, one whose turn ended a moment ago: both written just now
  writeFileSync(file("at-work"), said("at-work", { type: "user", message: { content: "fix it" } }));
  writeFileSync(file("ended"), said("ended", { type: "user", message: { content: "say hello" } })
    + said("ended", { type: "assistant", message: { stop_reason: "end_turn", content: [{ type: "text", text: "hello" }] } }));
  await h.scan(); await settle();
  assert.equal(await h.working(), 1);
  // with its page behind another, or closed, the count is the same: read at a glance
  for (const p of [...vscode.panels]) close(p);
  assert.equal(await h.working(), 1);
  h.stop();
});

test("Home's glance at a long session proves nothing from a question its start left open: the answer is in what was not read", async () => {
  for (const f of readdirSync(dir)) rmSync(path.join(dir, f), { recursive: true });
  const h = hub();
  h.start();
  const said = (more: Record<string, unknown>) => `${JSON.stringify({ cwd: folder, sessionId: "long", timestamp: new Date().toISOString(), ...more })}\n`;
  const filler = said({ type: "assistant", message: { content: [{ type: "text", text: "x".repeat(2000) }] } });
  writeFileSync(file("long"),
    said({ type: "user", message: { content: "plan it, then do it" } })
    + said({ type: "assistant", message: { stop_reason: "tool_use", content: [{ type: "tool_use", id: "q1", name: "ExitPlanMode", input: { plan: "1. do it" } }] } })
    + filler.repeat(120) // 240 KB of work past the file's first 64 KB: the plan's approval is in here, unread at a glance
    + said({ type: "user", message: { content: [{ type: "tool_result", tool_use_id: "q1", content: "approved" }] } })
    + filler.repeat(200)); // and 400 KB more, of which the glance reads the last 256
  await h.scan(); await settle();
  for (const p of [...vscode.panels]) close(p); // no page follows it: Home reads it at a glance
  const [row] = await h.list();
  assert.equal(row!.status, "working");
  h.stop();
});
