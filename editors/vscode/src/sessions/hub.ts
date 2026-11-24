// The folder's sessions in the editor, with nothing installed and nothing set up: found by their own files
// (find.ts), followed as they grow (follow.ts), and drawn by the graph's own page from the snapshot they make
// (snapshot.ts). A session that begins or writes while the window is open gets a page; a page can draw several,
// a band each, and remembers them across a reload. No graphene command runs here and nothing is written
// anywhere: the files are read, never changed, and nothing leaves the machine.
import { readFile } from "node:fs/promises";
import * as vscode from "vscode";
import { graphHtml } from "../graph.ts";
import { beside, pages, wrote } from "../open.ts";
import type { SessionInfo, State } from "../state.ts";
import { checkPage, type FromPage } from "./acts.ts";
import { glance, procs, readerOf, Scan, type Found, type Proc } from "./find.ts";
import { Follow } from "./follow.ts";
import { empty, fold, type Model } from "./model.ts";
import { Replay } from "./replay.ts";
import { info, snapshot, status } from "./snapshot.ts";

/** How often the folder is looked at for sessions, and an open page's files for what is new.
 *  ponytail: a poll, a few dozen stats a look (find.ts `Scan`); watch the directories if idle CPU matters. */
const SCAN_MS = 2000, READ_MS = 1000;
/** A replay plays an event this often: the recording's two minutes in half of one. */
const REPLAY_MS = 350;
export const PAGE = "graphene.sessionPage";

/** One graph tab: the sessions it draws, each followed while the tab is there; or a replay of the recorded one. */
export class Page {
  readonly panel: vscode.WebviewPanel;
  readonly follows: Follow[] = [];
  replay: Replay | null = null;
  /** What the page was last sent: what a message from it is checked against. */
  drawn: State | null = null;
  private last = "";
  private gone = false;

  constructor(panel: vscode.WebviewPanel, context: vscode.ExtensionContext) {
    this.panel = panel;
    const roots = [vscode.Uri.joinPath(context.extensionUri, "dist"), vscode.Uri.joinPath(context.extensionUri, "media")];
    panel.webview.options = { enableScripts: true, localResourceRoots: roots }; // a page brought back by a reload has none
    panel.webview.html = graphHtml(context, panel.webview);
    const icon = (f: string) => vscode.Uri.joinPath(context.extensionUri, "media", f);
    panel.iconPath = { light: icon("graphene-light.svg"), dark: icon("graphene-dark.svg") };
    panel.onDidChangeViewState((e) => this.post({ type: "shown", on: e.webviewPanel.visible }));
    panel.onDidDispose(() => { this.gone = true; });
  }

  has(file: string): boolean { return this.follows.some((f) => f.found.file === file); }

  add(found: Found) { if (!this.has(found.file)) this.follows.push(new Follow(found)); }

  remove(session: string) {
    const at = this.follows.findIndex((f) => f.model.id === session);
    if (at >= 0) this.follows.splice(at, 1);
  }

  /** A closed tab's page is posted nothing: its webview is gone. */
  post(message: unknown) { if (!this.gone) void this.panel.webview.postMessage(message); }

  /** Read what is new in the page's files and draw it; `force`: draw it again though nothing was. */
  async refresh(live: ReadonlyMap<string, Proc>, force = false) {
    const read = this.replay ? [] : await Promise.all(this.follows.map((f) => f.read()));
    if (this.gone) return;
    const state = this.replay
      ? { ...snapshot([this.replay.model], this.replay.clock + 500), replay: { shown: "a recorded Claude Code session", day: "", repository: "" } }
      : snapshot(this.follows.map((f) => f.model), Date.now(), live);
    // drawn again when a file grew, and when what is said of it moved on (working to idle, with no line written)
    const key = JSON.stringify([state.sessions, state.tasks.map((t) => [t.state, t.card?.says, t.note])]);
    if (!force && !read.some(Boolean) && key === this.last) return;
    this.last = key;
    this.drawn = state;
    this.panel.title = this.replay ? "Graphene replay" : title(state);
    this.post({ type: "state", state, seen: [] });
  }
}

/** A tab's title: its session's, or how many it draws. */
function title(s: State): string {
  const all = s.sessions ?? [];
  if (all.length !== 1) return all.length ? `${all.length} sessions` : "Graphene";
  const t = all[0]!.title;
  return t.length > 28 ? `${t.slice(0, 27)}…` : t;
}

/** What the active editor group has in front, as VS Code's tabs name it; nothing before the window's tabs are there. */
function front(): unknown {
  try { return vscode.window.tabGroups.activeTabGroup.activeTab?.input; } catch { return undefined; }
}

export class Hub implements vscode.Disposable, vscode.WebviewPanelSerializer {
  /** The folder's sessions, the last written first. */
  found: Found[] = [];
  live = new Map<string, Proc>();
  readonly pages: Page[] = [];
  private readonly context: vscode.ExtensionContext;
  private readonly changed = new vscode.EventEmitter<void>();
  /** The folder's sessions changed: one began, one wrote, one went quiet. */
  readonly onDidChange = this.changed.event;
  private timers: NodeJS.Timeout[] = [];
  private scanning: Promise<void> | null = null;
  private key = "";
  private sizes: Map<string, number> | null = null; // each session file's size at the last look; none before the first
  private readonly opened = new Set<string>(); // the sessions whose page opened by itself in this window: once each

  constructor(context: vscode.ExtensionContext) { this.context = context; }

  get folder(): string | undefined { return vscode.workspace.workspaceFolders?.[0]?.uri.fsPath; }

  /** Start looking: at the folder for its sessions, at the open pages for what is new. */
  start() {
    if (this.timers.length) return;
    this.timers = [setInterval(() => void this.scan(), SCAN_MS), setInterval(() => void this.read(), READ_MS),
                   setInterval(() => this.play(), REPLAY_MS)];
    void this.scan();
  }

  stop() {
    for (const t of this.timers) clearInterval(t);
    this.timers = [];
  }

  /** The folder's sessions and the running agents' own records, read again; one read at a time. */
  scan(): Promise<void> {
    return this.scanning ??= this.look().finally(() => { this.scanning = null; });
  }

  private scanner: Scan | null = null;
  private scanned = "";

  private async look() {
    const folder = this.folder;
    if (folder !== this.scanned) { this.scanned = folder ?? ""; this.scanner = folder ? new Scan(folder) : null; }
    [this.found, this.live] = await Promise.all([this.scanner?.look() ?? Promise.resolve([]), procs()]);
    // a session that began or wrote since the last look gets a page, beside what is in front, once
    const on = vscode.workspace.getConfiguration("graphene").get<boolean>("graph.openOnStart", true);
    for (const file of wrote(this.sizes, this.found)) {
      if (!pages({ on, paged: this.pages.some((p) => p.has(file)), opened: this.opened.has(file) })) continue;
      this.opened.add(file);
      void this.show(file, true);
    }
    this.sizes = new Map(this.found.map((f) => [f.file, f.size]));
    const key = JSON.stringify([this.found.map((f) => [f.file, f.size]), [...this.live.values()].map((p) => [p.session, p.status])]);
    if (key === this.key) return;
    this.key = key;
    this.changed.fire();
  }

  private async read() {
    await Promise.all(this.pages.filter((p) => p.panel.visible && !p.replay).map((p) => p.refresh(this.live)));
  }

  /** Each replay moves on by an event; at its end it stays as it is. */
  private play() {
    for (const p of this.pages) if (p.replay && p.panel.visible && !p.replay.over) { p.replay.step(); void p.refresh(this.live); }
  }

  /** What a list says of each session, the newest few: as its page has it where one draws it, else at a glance
   *  (its file's start and its end, read again only when it has grown). */
  async list(most = 12): Promise<SessionInfo[]> {
    const out: SessionInfo[] = [], newest = this.found.slice(0, most), now = Date.now();
    for (const f of newest) {
      let m: Model | undefined = this.pages.flatMap((p) => p.follows).find((x) => x.found.file === f.file)?.model;
      if (!m) {
        let g = this.glanced.get(f.file);
        if (!g || g.size !== f.size) {
          g = { size: f.size, model: empty(f.agent, f.file, f.id) };
          g.model.cwd = f.cwd;
          const line = readerOf(f.agent).line;
          for (const l of await glance(f)) { try { for (const ev of line(l)) fold(g.model, ev); } catch { /* a line it does not understand */ } }
          this.glanced.set(f.file, g);
        }
        m = g.model;
      }
      out.push(info(m, status(m, now, this.live.get(m.id))));
    }
    for (const file of [...this.glanced.keys()]) if (!newest.some((f) => f.file === file)) this.glanced.delete(file);
    return out;
  }
  private glanced = new Map<string, { size: number; model: Model }>(); // the listed sessions no page follows

  /** The page that draws a session, made if there is none; with no session named, the folder's newest, or an
   *  empty page. `quiet`: nobody asked for it (it opens by itself), so it leaves the keyboard where it is, and
   *  opens beside a file that is in front, never over it: in the group of a page that is there already, so pages
   *  gather in one group and do not halve the editor again. */
  async show(file?: string, quiet = false): Promise<Page | undefined> {
    if (!this.found.length || (file && !this.found.some((f) => f.file === file))) await this.scan();
    const found = file ? this.found.find((f) => f.file === file) : this.found[0];
    if (file && !found) return undefined; // a session the folder no longer has: no page opens in its place
    const have = found ? this.pages.find((p) => p.has(found.file)) : this.pages.find((p) => !p.replay);
    if (have) { if (!quiet) have.panel.reveal(undefined, false); return have; }
    const other = this.pages[0]?.panel.viewColumn;
    const viewColumn = quiet ? other ?? (beside(front()) ? vscode.ViewColumn.Beside : vscode.ViewColumn.Active) : vscode.ViewColumn.Active;
    const panel = vscode.window.createWebviewPanel(PAGE, "Graphene", { viewColumn, preserveFocus: quiet }, { enableScripts: true, retainContextWhenHidden: true });
    return this.adopt(panel, found ? [found] : []);
  }

  /** A panel as one of the pages: its sessions followed, its messages heard, forgotten when it is closed. */
  adopt(panel: vscode.WebviewPanel, sessions: Found[]): Page {
    const page = new Page(panel, this.context);
    for (const f of sessions) { page.add(f); this.opened.add(f.file); }
    this.pages.push(page);
    panel.webview.onDidReceiveMessage((m: unknown) => {
      const msg = checkPage(m, page.drawn);
      if (msg) void this.act(page, msg);
    });
    panel.onDidDispose(() => { this.pages.splice(this.pages.indexOf(page), 1); });
    return page;
  }

  /** A page brought back by a reload: the sessions it drew, as its own state names them, where the folder still
   *  has them. */
  async deserializeWebviewPanel(panel: vscode.WebviewPanel, state: unknown) {
    const files = ((state ?? {}) as { page?: unknown }).page;
    await this.scan();
    const wanted = Array.isArray(files) ? files.filter((f): f is string => typeof f === "string") : [];
    this.adopt(panel, wanted.map((f) => this.found.find((x) => x.file === f)).filter((f): f is Found => f !== undefined));
  }

  private async act(page: Page, m: FromPage) {
    if (m.type === "ready") return page.refresh(this.live, true);
    switch (m.act) {
      case "addSession": return this.add(page);
      case "takeOff": page.remove(m.id); return page.refresh(this.live, true);
      case "replay": return this.playRecorded(page);
    }
  }

  /** Add to page…: another of the folder's sessions, picked from a list, drawn as a band of its own. */
  private async add(page: Page) {
    const rest = (await this.list(30)).filter((s) => !page.has(s.file));
    if (!rest.length) return void vscode.window.showInformationMessage("This folder has no other session to add.");
    const pick = await vscode.window.showQuickPick(rest.map((s) => ({
      label: s.title, description: `${s.agent === "codex" ? "Codex" : "Claude Code"} · ${s.status}`, file: s.file,
    })), { placeHolder: "the session to draw on this page, as a band of its own" });
    const found = pick && this.found.find((f) => f.file === pick.file);
    if (!found) return;
    page.replay = null;
    page.add(found);
    await page.refresh(this.live, true);
  }

  /** The recorded session the extension carries, played on a page that has none. */
  private async playRecorded(page: Page) {
    if (page.follows.length) return;
    try {
      page.replay = new Replay(await readFile(vscode.Uri.joinPath(this.context.extensionUri, "media", "replay.jsonl").fsPath, "utf8"));
    } catch (e) {
      return void vscode.window.showErrorMessage(`Graphene could not read its recorded session: ${(e as Error).message}`);
    }
    page.replay.step(2);
    await page.refresh(this.live, true);
  }

  dispose() {
    this.stop();
    this.changed.dispose();
  }
}
