// The folder's sessions in the editor, with nothing installed and nothing set up: found by their own files
// (find.ts), followed as they grow (follow.ts), and drawn by the graph's own page from the snapshot they make
// (snapshot.ts). No graphene command runs here and nothing is written anywhere: the files are read, never
// changed, and nothing leaves the machine.
import * as vscode from "vscode";
import { graphHtml } from "../graph.ts";
import type { SessionInfo, State } from "../state.ts";
import { glance, procs, readerOf, Scan, type Found, type Proc } from "./find.ts";
import { Follow } from "./follow.ts";
import { empty, fold, type Model } from "./model.ts";
import { info, snapshot, status } from "./snapshot.ts";

/** How often the folder is looked at for sessions, and an open page's files for what is new.
 *  ponytail: a poll, a few dozen stats a look (find.ts `Scan`); watch the directories if idle CPU matters. */
const SCAN_MS = 2000, READ_MS = 1000;

/** One graph tab: the sessions it draws, each followed while the tab is there. */
export class Page {
  readonly panel: vscode.WebviewPanel;
  readonly follows: Follow[] = [];
  private last = "";
  private gone = false; // its tab was closed: a read that ends after that draws nothing

  constructor(panel: vscode.WebviewPanel, context: vscode.ExtensionContext) {
    this.panel = panel;
    panel.onDidDispose(() => { this.gone = true; });
    panel.webview.html = graphHtml(context, panel.webview);
    const icon = (f: string) => vscode.Uri.joinPath(context.extensionUri, "media", f);
    panel.iconPath = { light: icon("graphene-light.svg"), dark: icon("graphene-dark.svg") };
    panel.onDidChangeViewState((e) => void panel.webview.postMessage({ type: "shown", on: e.webviewPanel.visible }));
  }

  has(file: string): boolean { return this.follows.some((f) => f.found.file === file); }

  add(found: Found) { if (!this.has(found.file)) this.follows.push(new Follow(found)); }

  /** The snapshot of what the page draws now. */
  state(live: ReadonlyMap<string, Proc>): State {
    return snapshot(this.follows.map((f) => f.model), Date.now(), live);
  }

  /** Read what is new in the page's files and draw it; `force`: draw it again though nothing was. */
  async refresh(live: ReadonlyMap<string, Proc>, force = false) {
    const read = await Promise.all(this.follows.map((f) => f.read()));
    if (this.gone) return;
    const state = this.state(live);
    // drawn again when a file grew, and when what is said of it moved on (working to idle, with no line written)
    const key = JSON.stringify([state.sessions, state.tasks.map((t) => [t.state, t.card?.says])]);
    if (!force && !read.some(Boolean) && key === this.last) return;
    this.last = key;
    this.panel.title = title(state);
    void this.panel.webview.postMessage({ type: "state", state, seen: [] });
  }
}

/** A tab's title: its session's, or how many it draws. */
function title(s: State): string {
  const all = s.sessions ?? [];
  if (all.length !== 1) return all.length ? `${all.length} sessions` : "Graphene";
  const t = all[0]!.title;
  return t.length > 28 ? `${t.slice(0, 27)}…` : t;
}

export class Hub implements vscode.Disposable {
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

  constructor(context: vscode.ExtensionContext) { this.context = context; }

  get folder(): string | undefined { return vscode.workspace.workspaceFolders?.[0]?.uri.fsPath; }

  /** Start looking: at the folder for its sessions, at the open pages for what is new. */
  start() {
    if (this.timers.length) return;
    this.timers = [setInterval(() => void this.scan(), SCAN_MS), setInterval(() => void this.read(), READ_MS)];
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
    const key = JSON.stringify([this.found.map((f) => [f.file, f.size]), [...this.live.values()].map((p) => [p.session, p.status])]);
    if (key === this.key) return;
    this.key = key;
    this.changed.fire();
  }

  private async read() {
    await Promise.all(this.pages.filter((p) => p.panel.visible).map((p) => p.refresh(this.live)));
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

  /** The page that draws a session, made if there is none; with no session named, the folder's newest. `quiet`:
   *  nobody asked for it, so it opens beside what is in front and leaves the keyboard where it is. */
  async show(file?: string, quiet = false): Promise<Page | undefined> {
    if (!this.found.length || (file && !this.found.some((f) => f.file === file))) await this.scan();
    const found = file ? this.found.find((f) => f.file === file) : this.found[0];
    if (file && !found) return undefined; // a session the folder no longer has: no page opens in its place
    const have = found ? this.pages.find((p) => p.has(found.file)) : this.pages[0];
    if (have) { if (!quiet) have.panel.reveal(undefined, false); return have; }
    const panel = vscode.window.createWebviewPanel("graphene.sessionPage", "Graphene", { viewColumn: quiet ? vscode.ViewColumn.Beside : vscode.ViewColumn.Active, preserveFocus: quiet }, {
      enableScripts: true, retainContextWhenHidden: true,
      localResourceRoots: [vscode.Uri.joinPath(this.context.extensionUri, "dist"), vscode.Uri.joinPath(this.context.extensionUri, "media")],
    });
    return this.adopt(panel, found ? [found] : []);
  }

  /** A panel as one of the pages: its sessions followed, its messages heard, forgotten when it is closed. */
  adopt(panel: vscode.WebviewPanel, sessions: Found[]): Page {
    const page = new Page(panel, this.context);
    for (const f of sessions) page.add(f);
    this.pages.push(page);
    panel.webview.onDidReceiveMessage((m: unknown) => {
      if ((m as { type?: unknown } | null)?.type === "ready") void page.refresh(this.live, true);
    });
    panel.onDidDispose(() => { this.pages.splice(this.pages.indexOf(page), 1); });
    return page;
  }

  dispose() {
    this.stop();
    this.changed.dispose();
  }
}
