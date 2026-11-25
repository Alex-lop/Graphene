// The folder's sessions in the editor, with nothing installed and nothing set up: found by their own files
// (find.ts), followed as they grow (follow.ts), and drawn by the graph's own page from the snapshot they make
// (snapshot.ts). A session that begins or writes while the window is open gets a page; a page can draw several,
// a band each, and remembers them across a reload. No graphene command runs here and nothing is written
// anywhere: the files are read, never changed, and nothing leaves the machine.
import { readFile, stat } from "node:fs/promises";
import * as path from "node:path";
import * as vscode from "vscode";
import { graphHtml } from "../graph.ts";
import { column, pages, wrote } from "../open.ts";
import type { GitFacts, SessionInfo, State } from "../state.ts";
import { checkPage, type FromPage } from "./acts.ts";
import { GAP, glance, isAlive, procs, readerOf, Scan, type Found, type Proc } from "./find.ts";
import { Follow } from "./follow.ts";
import { note, show, since, unexplained, type Note } from "./git.ts";
import { receipt } from "./receipt.ts";
import { empty, fold, type Model } from "./model.ts";
import { Replay } from "./replay.ts";
import { info, QUIET, snapshot, status, type Live } from "./snapshot.ts";
import { runs } from "./term.ts";
import { codexMayHave, processes, Terminals, terminalOf } from "./terminals.ts";

/** How often the folder is looked at for sessions, and an open page's files for what is new.
 *  ponytail: a poll, a few dozen stats a look (find.ts `Scan`); watch the directories if idle CPU matters. */
const SCAN_MS = 2000, READ_MS = 1000;
/** A replay plays an event this often: the recording's two minutes in half of one. */
const REPLAY_MS = 350;
export const PAGE = "graphene.sessionPage";
/** The scheme of a changed file's left side: the file as the commit the session began on has it. */
export const BEFORE = "graphene-before";
const PAGED = "graphene.sessions.paged"; // the workspace's memory of which session files a page draws

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

  /** Read what is new in the page's files and draw it; `force`: draw it again though nothing was. `git`: what git
   *  says of each session's folder since it was first seen, by the session's id. */
  async refresh(live: ReadonlyMap<string, Live>, force = false, git: ReadonlyMap<string, GitFacts> = new Map()) {
    const read = this.replay ? [] : await Promise.all(this.follows.map((f) => f.read()));
    if (this.gone) return;
    const state = this.replay
      ? { ...snapshot([this.replay.model], this.replay.clock + 500), replay: { shown: "a recorded Claude Code session", day: "", repository: "" } }
      : snapshot(this.follows.map((f) => f.model), Date.now(), live, git);
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
function activeColumn(): number | undefined {
  try { return vscode.window.tabGroups.activeTabGroup.viewColumn; } catch { return undefined; }
}
/** What is in front is one of the pages. */
function ownInFront(): boolean {
  const input = front();
  return input instanceof vscode.TabInputWebview && input.viewType.includes(PAGE);
}

/** The sessions a list shows, the newest: Home's, and the ones the status bar counts. */
const LISTED = 12;

export class Hub implements vscode.Disposable, vscode.WebviewPanelSerializer {
  /** The folder's sessions, the last written first. */
  found: Found[] = [];
  live = new Map<string, Proc>();
  readonly pages: Page[] = [];
  private readonly context: vscode.ExtensionContext;
  private readonly changed = new vscode.EventEmitter<void>();
  /** The folder's sessions changed: one began, one wrote, one went quiet. */
  readonly onDidChange = this.changed.event;
  private timers: NodeJS.Timeout[] = []; // the folder looked at: while there is no plan
  private pageTimers: NodeJS.Timeout[] = []; // the open pages read and replayed: while there is a page, in either mode
  private watching = false; // sessions get pages by themselves: only where there is no plan
  private scanning: Promise<void> | null = null;
  private key = "";
  private sizes: Map<string, number> | null = null; // each session file's size at the last look; none before the first
  private readonly opened = new Set<string>(); // the sessions whose page opened by itself in this window: once each

  constructor(context: vscode.ExtensionContext) { this.context = context; }

  get folder(): string | undefined { return vscode.workspace.workspaceFolders?.[0]?.uri.fsPath; }

  /** Start looking at the folder for its sessions: one that begins or writes from now on gets a page. What is
   *  there at this first look is old, whatever was seen before a stop. */
  start() {
    if (this.timers.length) return;
    this.watching = true;
    this.sizes = null;
    this.timers = [setInterval(() => void this.scan(), SCAN_MS)];
    void this.scan();
  }

  stop() {
    this.watching = false;
    for (const t of this.timers) clearInterval(t);
    this.timers = [];
  }

  /** The open pages are read for what is new, and a replay moves on, while there is a page: in a folder with a
   *  plan too, where a page a reload brought back is still a page. */
  private tick() {
    if (this.pages.length && !this.pageTimers.length) this.pageTimers = [setInterval(() => void this.read(), READ_MS), setInterval(() => this.play(), REPLAY_MS)];
    if (!this.pages.length) { for (const t of this.pageTimers) clearInterval(t); this.pageTimers = []; }
    // which sessions have a page, for the next window: a page behind another is brought back only when it is shown
    void this.context.workspaceState.update(PAGED, [...new Set([...this.pages.flatMap((p) => p.follows.map((f) => f.found.file)), ...this.dormant()])]);
  }

  /** The sessions of pages a reload has not brought back yet: the editor restores a page behind another only when
   *  its tab is shown, so until then its sessions are a page's all the same, and get no second one. */
  private dormant(): string[] {
    try {
      const tabs = vscode.window.tabGroups.all.flatMap((g) => g.tabs).filter((t) => t.input instanceof vscode.TabInputWebview && t.input.viewType.includes(PAGE)).length;
      return tabs > this.pages.length ? this.context.workspaceState.get<string[]>(PAGED, []) : [];
    } catch { return []; }
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
    const was = [...this.live];
    [this.found, this.live] = await Promise.all([this.scanner?.look() ?? Promise.resolve([]), procs()]);
    // a record of a process is believed only while that process is the agent's: a pid is given to another program in time
    if (this.live.size) {
      const { command } = await processes();
      for (const [id, p] of this.live) if (command.size && !runs(command.get(p.pid) ?? "", "claude")) this.live.delete(id);
    }
    // a process that was there at the last look and has ended: its session is not at work, whatever it left open.
    // (Its record missing for a moment while it is rewritten is not that: the process itself is asked)
    for (const [id, p] of was) if (!this.live.has(id) && !isAlive(p.pid)) this.gone.add(id);
    for (const id of this.live.keys()) this.gone.delete(id);
    // a session that began or wrote since the last look gets a page, beside what is in front, once
    const on = this.watching && vscode.workspace.getConfiguration("graphene").get<boolean>("graph.openOnStart", true);
    const dormant = this.dormant();
    // a session that began since the last look: its folder's HEAD and dirty files are noted now, for its receipt to
    // compare with at the end. One that was there before the window has no before to note
    for (const f of this.found) if (this.sizes && !this.sizes.has(f.file) && !this.notes.has(f.file)) {
      this.notes.set(f.file, null);
      void note(f.cwd).then((n) => { this.notes.set(f.file, n); });
    }
    for (const file of wrote(this.sizes, this.found)) {
      if (!pages({ on, paged: this.pages.some((p) => p.has(file)) || dormant.includes(file), opened: this.opened.has(file) })) continue;
      this.opened.add(file);
      void this.show(file, true);
    }
    if (this.watching) this.sizes = new Map(this.found.map((f) => [f.file, f.size]));
    // what a listener would say differently: a file that grew, a process's record, a session gone quiet with no line to say so
    const fresh = this.found.filter((f) => Date.now() - f.mtime <= QUIET).length;
    const key = JSON.stringify([this.found.map((f) => [f.file, f.size]), [...this.live.values()].map((p) => [p.session, p.status]), fresh, this.gone.size]);
    if (key === this.key) return;
    this.key = key;
    this.changed.fire();
  }

  private async read() {
    await Promise.all(this.pages.filter((p) => p.panel.visible && !p.replay).map((p) => p.refresh(this.lives, false, this.git(p))));
  }

  private readonly gone = new Set<string>(); // sessions whose process was seen running, and then was not
  /** What is known of each session's process: its own record while it runs, and that it is gone once it has ended. */
  private get lives(): Map<string, Live> {
    return new Map<string, Live>([...[...this.gone].map((id) => [id, { status: "gone" }] as const), ...this.live]);
  }

  /** How many of the folder's sessions are at work, by the rule their pages go by (snapshot.ts `status`: a turn
   *  that ended is over, whatever its process's record says). Only a session with a process, or a line written
   *  not long ago, is read for it: as a page in front has it, else at a glance. */
  async working(): Promise<number> {
    const now = Date.now(), shown = this.pages.filter((p) => p.panel.visible).flatMap((p) => p.follows);
    let n = 0;
    for (const f of this.found.slice(0, LISTED)) {
      if (!this.live.has(f.id) && now - f.mtime > QUIET) continue;
      const drawn = shown.find((x) => x.found.file === f.file)?.model; // a page that has just opened has read nothing yet
      const m = drawn?.last ? drawn : await this.glance(f);
      if (status(m, now, this.lives.get(m.id)) === "working") n++;
    }
    return n;
  }

  private readonly notes = new Map<string, Note | null>(); // a session's file -> its folder's git when the session was first seen
  private readonly facts = new Map<string, { key: string; at: number; facts: GitFacts }>(); // and what moved since, as last compared
  private readonly repos = new Map<string, boolean>(); // a folder -> whether git has it

  /** What git says of each of a page's sessions, as last compared; a comparison that is due is started, and the
   *  page drawn again when it ends. Compared when the session's file has grown, at most every five seconds, and
   *  only for a page that is shown: what a comparison finds changed since the note, it does not say who changed. */
  private git(page: Page): Map<string, GitFacts> {
    const out = new Map<string, GitFacts>();
    // noted, and not compared yet: nothing is said of what moved until a comparison has come back
    const none: GitFacts = { noted: true, compared: false, commits: 0, dropped: 0, unexplained: [] };
    for (const f of page.follows) {
      const m = f.model, file = f.found.file, was = this.notes.get(file);
      if (!this.repos.has(m.cwd)) { this.repos.set(m.cwd, false); void note(m.cwd).then((n) => { this.repos.set(m.cwd, n !== null); }); }
      if (!was) { if (this.repos.get(m.cwd) && !this.notes.has(file)) out.set(m.id, { ...none, noted: false }); continue; }
      const have = this.facts.get(file), key = m.last;
      out.set(m.id, have?.facts ?? none);
      if (have?.key === key || Date.now() - (have?.at ?? 0) < 5000) continue;
      this.facts.set(file, { key, at: Date.now(), facts: have?.facts ?? none });
      void since(was).then((now) => {
        if (!now) return;
        const written = receipt([...m.calls.values()], m.cwd).changed.map((c) => c.file);
        this.facts.set(file, { key, at: Date.now(), facts: { noted: true, compared: true, commits: now.commits, dropped: now.dropped, unexplained: unexplained(now.changed, written, was.top, m.cwd) } });
        void page.refresh(this.lives, true, this.git(page));
      });
    }
    return out;
  }

  /** Each replay moves on by an event; at its end it stays as it is. */
  private play() {
    for (const p of this.pages) if (p.replay && p.panel.visible && !p.replay.over) { p.replay.step(); void p.refresh(this.live); }
  }

  /** What a list says of each session, the newest few: as its page has it where one draws it, else at a glance
   *  (its file's start and its end, read again only when it has grown). */
  async list(most = LISTED): Promise<SessionInfo[]> {
    const out: SessionInfo[] = [], newest = this.found.slice(0, most), now = Date.now();
    for (const f of newest) {
      const m = this.pages.flatMap((p) => p.follows).find((x) => x.found.file === f.file)?.model ?? await this.glance(f);
      out.push(info(m, status(m, now, this.lives.get(m.id)), this.live.has(m.id)));
    }
    for (const file of [...this.glanced.keys()]) if (!newest.some((f) => f.file === file)) this.glanced.delete(file);
    return out;
  }
  private glanced = new Map<string, { size: number; model: Model }>(); // the listed sessions no page follows
  /** A session at a glance: its file's start and its end, read again only when it has grown. */
  private async glance(f: Found): Promise<Model> {
    let g = this.glanced.get(f.file);
    if (!g || g.size !== f.size) {
      g = { size: f.size, model: empty(f.agent, f.file, f.id) };
      g.model.cwd = f.cwd;
      const line = readerOf(f.agent).line;
      for (const l of await glance(f)) {
        // past what was left out: a call the start left open was answered there, or never: it is no proof now
        if (l === GAP) { for (const c of g.model.calls.values()) c.done = true; continue; }
        try { for (const ev of line(l)) fold(g.model, ev); } catch { /* a line it does not understand */ }
      }
      this.glanced.set(f.file, g);
    }
    return g.model;
  }

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
    const to = quiet ? column({ front: front(), own: ownInFront(), active: activeColumn(), pages: this.pages.map((p) => p.panel.viewColumn) }) : "active";
    const viewColumn = to === "beside" ? vscode.ViewColumn.Beside : to === "active" ? vscode.ViewColumn.Active : to;
    const panel = vscode.window.createWebviewPanel(PAGE, "Graphene", { viewColumn, preserveFocus: quiet }, { enableScripts: true, retainContextWhenHidden: true });
    return this.adopt(panel, found ? [found] : []);
  }

  /** A panel as one of the pages: its sessions followed, its messages heard, forgotten when it is closed. */
  adopt(panel: vscode.WebviewPanel, sessions: Found[]): Page {
    const page = new Page(panel, this.context);
    for (const f of sessions) { page.add(f); this.opened.add(f.file); } // a session may be on two pages (Add to page…): each keeps its own
    this.pages.push(page);
    this.tick();
    panel.webview.onDidReceiveMessage((m: unknown) => {
      const msg = checkPage(m, page.drawn);
      if (msg) void this.act(page, msg);
    });
    panel.onDidDispose(() => { this.pages.splice(this.pages.indexOf(page), 1); this.tick(); });
    return page;
  }

  /** A page brought back by a reload: the sessions it drew, as its own state names them, where the folder still
   *  has them. */
  async deserializeWebviewPanel(panel: vscode.WebviewPanel, state: unknown) {
    const files = ((state ?? {}) as { page?: unknown }).page;
    const wanted = Array.isArray(files) ? files.filter((f): f is string => typeof f === "string") : [];
    for (const f of wanted) this.opened.add(f); // before the look below: its sessions have this page, and get no other
    await this.scan();
    this.adopt(panel, wanted.map((f) => this.found.find((x) => x.file === f)).filter((f): f is Found => f !== undefined));
  }

  private async act(page: Page, m: FromPage) {
    if (m.type === "ready") return page.refresh(this.lives, true, this.git(page));
    switch (m.act) {
      case "addSession": return this.add(page);
      case "takeOff": page.remove(m.id); this.tick(); return page.refresh(this.lives, true, this.git(page));
      case "replay": return this.playRecorded(page);
      case "terminal": return this.terminal(page, m.id);
      case "resume": return this.resume(page, m.id);
      case "openFile": return this.openFile(page, m.id, m.file ?? "");
    }
  }

  /** A file a card changed, as its diff: on the left the file as the commit the session began on has it (the
   *  last commit, for a session git was not noted for), on the right the file as it is. Where there is no
   *  repository, the file itself. The file is one the card names, and the left side is read with `git show`. */
  private async openFile(page: Page, id: string, file: string) {
    const card = page.drawn?.tasks.find((t) => t.id === id)?.card;
    const follow = card && page.follows.find((f) => f.model.id === card.session);
    if (!follow || !file) return;
    const abs = path.resolve(follow.model.cwd, file), was = this.notes.get(follow.found.file) ?? await note(follow.model.cwd);
    const there = await stat(abs).then(() => true, () => false);
    if (!was) {
      if (there) return void vscode.window.showTextDocument(vscode.Uri.file(abs), { preview: true });
      return void vscode.window.showInformationMessage(`${file} is not there to open: it was deleted, or moved.`);
    }
    const rev = was.head || "HEAD", side = (r: string) => vscode.Uri.file(abs).with({ scheme: BEFORE, query: JSON.stringify({ top: was.top, rev: r }) });
    // a deleted file's right side is nothing, not a missing file
    await vscode.commands.executeCommand("vscode.diff", side(rev), there ? vscode.Uri.file(abs) : side(""), `${path.basename(file)} · since ${was.head ? was.head.slice(0, 7) : "the last commit"}`, { preview: true });
  }

  /** The left side of such a diff: the file as a commit has it; nothing for a revision of "". */
  before(uri: vscode.Uri): Promise<string> | string {
    try {
      const q = JSON.parse(uri.query) as { top?: unknown; rev?: unknown };
      if (typeof q.top !== "string" || typeof q.rev !== "string" || !q.rev || !/^[0-9a-f]{7,40}$|^HEAD$/.test(q.rev)) return "";
      return show(q.top, q.rev, path.relative(q.top, uri.fsPath));
    } catch { return ""; }
  }

  private readonly terminals = new Terminals();

  /** A card's terminal: the editor's own terminal its session runs in, where it runs in one; else its transcript's
   *  tail as a terminal would have shown it; a subagent's card, the subagent's own transcript. The keyboard stays
   *  where it is: a click on a card is a look, not a move. */
  private async terminal(page: Page, id: string) {
    const card = page.drawn?.tasks.find((t) => t.id === id)?.card;
    const follow = card && page.follows.find((f) => f.model.id === card.session);
    if (!card || !follow) return;
    const side = card.side ? follow.model.sides.get(card.side) : undefined;
    const pid = this.live.get(follow.model.id)?.pid;
    const own = !side && pid ? await terminalOf(pid) : undefined;
    if (own) return own.show(true);
    const who = follow.found.agent === "codex" ? "Codex" : "Claude Code", title = page.drawn?.tasks.find((t) => t.id === id)?.title ?? "";
    const view = side?.file
      ? this.terminals.tailOf(side.file, follow.found, title, "the tail of this subagent's own transcript", null)
      : this.terminals.tailOf(follow.found.file, follow.found, info(follow.model, "idle").title, `the tail of this ${who} session's transcript`, "");
    view.show(true);
  }

  /** Resume in terminal: only a session that is not writing and that nothing has open, looked at again now: two
   *  writers on one session corrupt it. One a running agent has open in a terminal of the editor's is shown there. */
  private async resume(page: Page, session: string) {
    const follow = page.follows.find((f) => f.model.id === session);
    if (!follow) return;
    await Promise.all([follow.read(), this.scan()]);
    const m = follow.model, open = this.live.get(m.id);
    if (open) {
      const own = await terminalOf(open.pid);
      own?.show();
      return void vscode.window.showInformationMessage(own ? "This session is open in this terminal: it is not started a second time." : "This session is open in a terminal outside the editor: it is not started a second time.");
    }
    // any write to its file in the last fifteen seconds, a line this reader skips included, is a session still at work
    if (status(m, Date.now(), null) !== "idle" || Date.now() - Math.max(Date.parse(m.last) || 0, m.touched) < 15_000) {
      return void vscode.window.showInformationMessage("This session is still writing: resume it once it is idle.");
    }
    // Codex keeps no record of which session a running one has open: one that is running in this folder may have this one
    if (m.agent === "codex" && await codexMayHave(m.id, m.cwd)) {
      return void vscode.window.showInformationMessage("A Codex is running in this session's folder. If it has this session open, a second one would corrupt it: close it first.");
    }
    if (!this.terminals.resume(follow.found)) void vscode.window.showErrorMessage("Graphene could not tell this session's id from its file.");
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
    this.tick();
    await page.refresh(this.lives, true, this.git(page));
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
    for (const t of this.pageTimers) clearInterval(t);
    this.changed.dispose();
  }
}
