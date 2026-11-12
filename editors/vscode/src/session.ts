// One folder's plan, read through the CLI: `graphene state --json` in the folder that holds the plan, again
// when the store's files change or on a poll while a view is open, and every change it makes is a graphene
// command run as the person (the agent marks are taken out of the environment). The person's folder has one;
// a replay (Graphene: Watch the Demo) has its own, in a directory of its own.
import { execFile } from "node:child_process";
import { existsSync } from "node:fs";
import * as path from "node:path";
import * as vscode from "vscode";
import * as C from "./commands.ts";
import type { GraphHost } from "./graph.ts";
import { cannotRun, olderWords, resolved } from "./find.ts";
import { errorOf, parseContracts, parseState, withContracts, type Contract, type State, type Task } from "./state.ts";
import { Stream } from "./stream.ts";
import type { Node, PlanTree } from "./tree.ts";

export type Status = { kind: "reading" | "missing" | "uninitialised" | "error" | "nofolder" | "ok" | "empty"; text: string };

export const STORE = path.join(".graphene", "graphene.db"); // the plan's store, under the repo's root
export const INSTALL = "Graphene is not installed, or not on this editor's PATH: `uv tool install graphene-map`, or set graphene.path.";
const INIT = "This folder has no plan yet: set it up on Graphene's Home, in one click (or `graphene init` in a terminal).";

/** What the feature modules share: the graph's host and the Plan view. */
export interface UI {
  graph: GraphHost;
  tree: PlanTree;
  treeView: vscode.TreeView<Node>;
}

export class Session {
  folder: vscode.WorkspaceFolder | undefined;
  state: State | null = null;
  status: Status = { kind: "reading", text: "Reading the plan…" };
  private emitter = new vscode.EventEmitter<void>();
  readonly onDidChange = this.emitter.event;
  private reading: Promise<void> | null = null;
  /** A directory of its own (a replay's), not one of the workspace's folders. */
  readonly own: string | undefined;
  /** graphene found off the PATH (find.ts), used while graphene.path is unset. */
  found: string | null = null;
  /** `graphene --version`'s line for `path`, read once per path (again after Install or a settings change). */
  version: string | null = null;
  /** The file `path` runs, for the hover and the older-CLI line: a bare word as the PATH resolves it. */
  file = "";
  private versioned = "";
  /** `graphene state --json --watch`, a snapshot a line, while the CLI has it. */
  readonly stream: Stream;

  constructor(own?: string) {
    this.own = own;
    this.folder = own ? { uri: vscode.Uri.file(own), name: path.basename(own), index: -1 } : planFolder();
    const self = this;
    this.stream = new Stream({
      get path() { return self.path; },
      get cwd() { return self.folder?.uri.fsPath; },
      onLine: (line) => {
        const why = errorOf(line); // the store went away mid-stream: a status, and the stream follows the next store
        if (why) return this.noPlan(why);
        try { this.take(parseState(line)); } catch { /* not a snapshot: the next line is */ }
      },
    });
  }

  /** `state --json` or the stream said there is no plan to read: still setting up (init asks at its terminal
   *  after it made the store, so the store's being there says nothing), or a plan that cannot be read. */
  private noPlan(why: string) {
    const store = this.folder && existsSync(path.join(this.folder.uri.fsPath, STORE));
    if (!store || /`graphene init`/.test(why)) return this.set(null, { kind: "uninitialised", text: INIT });
    this.set(null, { kind: "error", text: this.said(C.older(why)) });
  }

  /** The not-installed line; when a path is set and cannot run (a directory, no x bit), it says so first. */
  private install(why: string): string {
    return why ? `${why}. ${INSTALL}` : INSTALL;
  }

  /** A refusal's line as the person reads it: the older-CLI line names the graphene that answered. */
  private said(why: string): string {
    return why === C.OLDER ? olderWords(this.file || this.path, this.version) : why;
  }

  get path(): string {
    const set = vscode.workspace.getConfiguration("graphene").get<string>("path")?.trim();
    return set && set !== "graphene" ? set : this.found ?? "graphene";
  }

  get pollMs(): number {
    return Math.max(250, vscode.workspace.getConfiguration("graphene").get<number>("pollMs") ?? 1500);
  }

  /** The tasks whose changes the person opened in this window (diff.ts): Home asks before approving one unseen. */
  readonly seen = new Set<string>();
  private saw = new vscode.EventEmitter<void>();
  readonly onDidSee = this.saw.event;

  /** The person opened a task's changes: said once, apart from onDidChange (the plan did not change). */
  see(id: string) {
    if (this.seen.has(id)) return;
    this.seen.add(id);
    this.saw.fire();
  }

  /** graphene, in the plan's folder, as the person: exit code and both streams; -1 when it did not run at all
   *  (not found, a directory, no x bit), stderr saying which. ``signal`` stops it (TERM: graphene settles first). */
  run(argv: string[], input?: string, signal?: AbortSignal): Promise<{ code: number; stdout: string; stderr: string }> {
    return new Promise((resolve) => {
      const child = execFile(this.path, argv, { cwd: this.folder?.uri.fsPath, env: C.scrub(process.env), maxBuffer: 64 * 1024 * 1024, signal },
                             (err, stdout, stderr) => {
        const e = err as (NodeJS.ErrnoException & { code?: number | string }) | null;
        if (e && cannotRun(e.code)) return resolve({ code: -1, stdout: "", stderr: e.code === "ENOENT" ? "" : `${this.path} is not a command it can run (${e.code})` });
        resolve({ code: e ? (typeof e.code === "number" ? e.code : 1) : 0, stdout: String(stdout), stderr: String(stderr) });
      });
      if (input !== undefined) child.stdin?.end(input);
    });
  }

  /** Read the plan again; one read at a time. */
  refresh(): Promise<void> {
    if (!this.reading) this.reading = this.read().finally(() => { this.reading = null; });
    return this.reading;
  }

  private async read() {
    if (!this.own) this.folder ??= planFolder();
    if (!this.folder) return this.set(null, { kind: "nofolder", text: "Open a folder to see its plan." });
    if (this.versioned !== this.path) { // which graphene answers: said in the hover and the older-CLI line
      const v = await this.run(["--version"]);
      this.versioned = this.path;
      this.file = resolved(this.path, process.env.PATH, existsSync);
      this.version = v.code === 0 ? C.firstLine(v.stdout, "", "") || null : null;
    }
    const out = await this.run(C.stateJson());
    const initialised = existsSync(path.join(this.folder.uri.fsPath, STORE));
    if (out.code === -1) return this.set(null, { kind: "missing", text: this.install(out.stderr) });
    if (!initialised) return this.set(null, { kind: "uninitialised", text: INIT });
    if (out.code !== 0) return this.noPlan(errorOf(out.stdout) ?? C.firstLine(out.stderr, out.stdout));
    try {
      this.take(parseState(out.stdout));
    } catch {
      return this.set(null, { kind: "error", text: `graphene state --json gave no plan: ${C.firstLine(out.stderr, out.stdout)}` });
    }
    this.stream.start(); // a plan read once: from here the stream brings each change, while the CLI has it
  }

  /** A snapshot read some other way (a stream's line): the same as a read's. */
  take(state: State) {
    // a task's changes count as opened while it is to review or done; sent back or redone, it is new work
    // while a change of ours is read back, a snapshot waits: it would show the change beside the old
    // attempts, approval and owner (the stream brings it before `plan --json` answers)
    if (this.changing) { this.held = state; return; }
    for (const id of this.seen) if (!state.tasks.some((t) => t.id === id && (t.state === "review" || t.state === "done"))) this.seen.delete(id);
    this.set(withContracts(state, this.contracts), state.tasks.length ? { kind: "ok", text: "" } : { kind: "empty", text: "Nothing is planned yet." });
    void this.contract();
  }
  private changing = 0;
  private held: State | null = null;

  /** Each task's attempts, approval and owner, from `graphene plan --json`: the snapshot leaves them out, and
   *  the graph's form shows them. Read again when the plan's log moved, one read at a time and at most one a
   *  second, so a run that logs every move starts one small process a second, and an idle plan none. */
  private contracts = new Map<string, Contract>();
  private contractsAt = -1;
  private contracting = false;
  private contractDue: NodeJS.Timeout | undefined;

  private async contract() {
    const at = this.state?.cursor;
    if (at === undefined || this.contracting || at === this.contractsAt) return;
    this.contracting = true;
    try {
      const read = await this.readContracts();
      this.contractsAt = at; // read, or refused: not asked again until the plan moves
      if (!read || !this.state) return;
      const next = withContracts(this.state, this.contracts);
      if (JSON.stringify(next.tasks) !== JSON.stringify(this.state.tasks)) { this.state = next; this.emitter.fire(); }
    } finally {
      this.contracting = false;
      clearTimeout(this.contractDue);
      if (this.state && this.state.cursor !== this.contractsAt) this.contractDue = setTimeout(() => void this.contract(), 1000);
    }
  }

  /** The state before the last read: what changed, for auto mode's notifications. */
  before: State | null = null;

  private set(state: State | null, status: Status) {
    this.before = this.state;
    this.state = state;
    this.status = status;
    if (!this.own) void vscode.commands.executeCommand("setContext", "graphene.status", status.kind);
    this.emitter.fire();
  }

  private async readContracts(): Promise<boolean> {
    const out = await this.run(C.planJson());
    if (out.code === 0) this.contracts = parseContracts(out.stdout);
    return out.code === 0;
  }

  /** A change: run it, say the first line it answered, or its refusal; then read the plan again. */
  async act(argv: string[]): Promise<boolean> {
    const r = await this.change(argv);
    if (!r.ok) void vscode.window.showErrorMessage(C.refused(argv, C.plain(r.line)));
    return r.ok;
  }

  /** A change made on the graph, which shows the answer beside what was changed: whether graphene took it,
   *  the refusal's lines whole (or the first line it answered), and what it printed. */
  async change(argv: string[]): Promise<{ ok: boolean; line: string; stdout: string }> {
    this.changing++;
    let out: { code: number; stdout: string; stderr: string };
    try {
      out = await this.run(argv);
      if (out.code === 0) await this.readContracts(); // before the snapshot that shows the change
    } finally {
      this.changing--;
    }
    const held = this.changing ? null : this.held;
    if (held) { this.held = null; this.take(held); }
    const ok = out.code === 0;
    const first = ok ? C.firstLine(out.stdout, out.stderr, "done")
      : out.code === -1 ? this.install(out.stderr) : this.said(C.firstLine(out.stderr, out.stdout));
    // a refusal whole for the page (its second line is often what to do about it); its first line for the toast
    const whole = (out.stderr.trim() || out.stdout.trim()).split(/\r?\n/).map((l) => l.trim()).filter(Boolean).slice(0, 8).join("\n");
    const line = ok || out.code === -1 || first === this.said(C.OLDER) ? first : whole || first;
    if (ok) vscode.window.setStatusBarMessage(`$(check) ${C.plain(first)}`, 6000);
    void this.refresh();
    return { ok, line, stdout: out.stdout };
  }

  /** A long command the person watches and may Ctrl-C: in a terminal of its own, as the person. */
  terminal(name: string, argv: string[]): vscode.Terminal {
    const term = vscode.window.createTerminal({ name, cwd: this.folder?.uri, env: C.unmarked(), iconPath: new vscode.ThemeIcon("type-hierarchy-sub") });
    term.show(true);
    term.sendText(C.shellLine(this.path, argv), true);
    return term;
  }

  tasks(): Task[] {
    return this.state?.tasks ?? [];
  }

  /** The folder or the command changed (a setting, an install): the stream starts over there, the version is read again. */
  moved() {
    this.versioned = "";
    this.seen.clear(); // another folder's ids are other tasks
    this.stream.restart();
  }

  dispose() {
    clearTimeout(this.contractDue);
    this.stream.dispose();
    this.emitter.dispose();
    this.saw.dispose();
  }
}

/** The workspace folder whose plan this is: the first with a store, else the first folder. */
export function planFolder(): vscode.WorkspaceFolder | undefined {
  const folders = vscode.workspace.workspaceFolders ?? [];
  return folders.find((f) => existsSync(path.join(f.uri.fsPath, STORE))) ?? folders[0];
}
