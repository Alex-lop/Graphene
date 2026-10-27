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
import { errorOf, parseState, type State, type Task } from "./state.ts";
import { Stream } from "./stream.ts";
import type { Node, PlanTree } from "./tree.ts";

export type Status = { kind: "reading" | "missing" | "uninitialised" | "error" | "nofolder" | "ok" | "empty"; text: string };

export const STORE = path.join(".graphene", "graphene.db"); // the plan's store, under the repo's root
export const INSTALL = "Graphene is not installed, or not on this editor's PATH: `uv tool install graphene-map`, or set graphene.path.";
const INIT = "This folder has no plan yet: run `graphene init` in it, then `graphene ask` or Graphene: Auto…";
const OLDER = C.OLDER; // the same line wherever an older CLI refuses a new shape (firstLine, refusal say it too)

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
    this.set(null, { kind: "error", text: /no such command/i.test(why) ? OLDER : why });
  }

  get path(): string {
    const set = vscode.workspace.getConfiguration("graphene").get<string>("path")?.trim();
    return set && set !== "graphene" ? set : this.found ?? "graphene";
  }

  get pollMs(): number {
    return Math.max(250, vscode.workspace.getConfiguration("graphene").get<number>("pollMs") ?? 1500);
  }

  /** graphene, in the plan's folder, as the person: exit code and both streams; -1 when it is not found. */
  run(argv: string[], input?: string): Promise<{ code: number; stdout: string; stderr: string }> {
    return new Promise((resolve) => {
      const child = execFile(this.path, argv, { cwd: this.folder?.uri.fsPath, env: C.scrub(process.env), maxBuffer: 64 * 1024 * 1024 },
                             (err, stdout, stderr) => {
        const e = err as (NodeJS.ErrnoException & { code?: number | string }) | null;
        if (e && e.code === "ENOENT") return resolve({ code: -1, stdout: "", stderr: `${this.path} was not found` });
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
    const out = await this.run(C.stateJson());
    const initialised = existsSync(path.join(this.folder.uri.fsPath, STORE));
    if (out.code === -1) return this.set(null, { kind: "missing", text: INSTALL });
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
    this.set(state, state.tasks.length ? { kind: "ok", text: "" } : { kind: "empty", text: "Nothing is planned yet." });
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

  /** A change: run it, say the first line it answered, or its refusal; then read the plan again. */
  async act(argv: string[]): Promise<boolean> {
    const out = await this.run(argv);
    if (out.code !== 0) {
      const why = out.code === -1 ? INSTALL : C.firstLine(out.stderr, out.stdout);
      void vscode.window.showErrorMessage(C.refused(argv, C.plain(why)));
    } else {
      vscode.window.setStatusBarMessage(`$(check) ${C.plain(C.firstLine(out.stdout, out.stderr, "done"))}`, 6000);
    }
    void this.refresh();
    return out.code === 0;
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

  /** The folder or the command changed: the stream starts over there. */
  moved() {
    this.stream.restart();
  }

  dispose() {
    this.stream.dispose();
    this.emitter.dispose();
  }
}

/** The workspace folder whose plan this is: the first with a store, else the first folder. */
export function planFolder(): vscode.WorkspaceFolder | undefined {
  const folders = vscode.workspace.workspaceFolders ?? [];
  return folders.find((f) => existsSync(path.join(f.uri.fsPath, STORE))) ?? folders[0];
}
