// A card's terminal, in the editor. If the session runs in one of the editor's own terminals, that one (the
// running agent's record of itself names its process, and the process tree says which terminal is above it).
// Otherwise a view of its transcript's tail that reads like a terminal, followed as the file grows: a
// pseudoterminal that only prints. And for a session nothing has open, a new terminal that takes it up again.
// Nothing typed in the view reaches an agent, and nothing here writes to a session's file.
import { execFile } from "node:child_process";
import { readlink } from "node:fs";
import * as vscode from "vscode";
import type { Ev } from "./events.ts";
import { readerOf, type Found } from "./find.ts";
import { Tail } from "./tail.ts";
import { ancestors, commandsOf, dim, parents, resumeLine, runs, safe, Term } from "./term.ts";

/** Every process, its parent and its command line, as `ps` lists them; none where there is no `ps` (Windows), or
 *  it fails. */
export function processes(): Promise<{ parent: Map<number, number>; command: Map<number, string> }> {
  return new Promise((resolve) => {
    execFile("ps", ["-axo", "pid=,ppid=,command="], { maxBuffer: 16 << 20, timeout: 5000 }, (err, out) =>
      resolve(err ? { parent: new Map(), command: new Map() } : { parent: parents(String(out)), command: commandsOf(String(out)) }));
  });
}

/** The editor's own terminal a process runs in: the one whose shell is above it. A terminal that never says its
 *  process (one that failed to start) is passed over after a second, not waited on. */
export async function terminalOf(pid: number): Promise<vscode.Terminal | undefined> {
  const above = new Set(ancestors(pid, (await processes()).parent));
  for (const t of vscode.window.terminals) {
    const shell = await Promise.race([t.processId, new Promise<undefined>((r) => setTimeout(() => r(undefined), 1000))]);
    if (shell && above.has(shell)) return t;
  }
  return undefined;
}

/** Where a process is working: /proc on Linux, `lsof` on macOS; "" where neither says. */
function cwdOf(pid: number): Promise<string> {
  return new Promise((resolve) => {
    readlink(`/proc/${pid}/cwd`, (err, link) => {
      if (!err) return resolve(link);
      execFile("lsof", ["-a", "-p", String(pid), "-d", "cwd", "-Fn"], { timeout: 3000 }, (e, out) => resolve(e ? "" : /^n(.+)$/m.exec(String(out))?.[1] ?? ""));
    });
  });
}

/** Whether a Codex that is running may have this session open: one whose command line names its id, or one that
 *  works in its folder (or will not say where). Codex keeps no record of which session a process has, so this is
 *  what there is to go by, and it errs toward yes. */
export async function codexMayHave(id: string, cwd: string): Promise<boolean> {
  const { command } = await processes();
  for (const [pid, line] of command) {
    if (pid === process.pid || !runs(line, "codex")) continue;
    if (line.includes(id)) return true;
    const at = await cwdOf(pid);
    if (!at || at === cwd) return true;
  }
  return false;
}

/** The lines kept of a transcript read for the first time: its tail. */
const KEPT = 400;

/** A transcript's tail, printed as its terminal would have shown it and followed as it grows. It takes no input
 *  but `q` and Ctrl+C, which close it. `side`: a subagent's own transcript, every line of which is its thread's. */
class TailView implements vscode.Pseudoterminal {
  private readonly writer = new vscode.EventEmitter<string>();
  private readonly closer = new vscode.EventEmitter<void>();
  readonly onDidWrite = this.writer.event;
  readonly onDidClose = this.closer.event;
  private timer: NodeJS.Timeout | undefined;
  private first = true;
  private resets = 0;
  private readonly tail: Tail;
  private term: Term;
  private readonly cwd: string;
  private readonly side: string | null;
  private readonly line: (line: string) => Ev[];
  private readonly what: string;

  /** `side`: the session's own thread (""), or null for a subagent's own file, every line of which is its thread's. */
  constructor(file: string, found: Found, what: string, side: string | null) {
    this.tail = new Tail(file);
    this.cwd = found.cwd;
    this.side = side;
    this.term = new Term(found.cwd, side);
    this.line = readerOf(found.agent).line;
    this.what = what;
  }

  open() {
    this.print([dim(`Graphene: ${this.what}, read from its file as it grows. Nothing typed here reaches the agent; q closes this view.`), ""]);
    void this.read();
    this.timer = setInterval(() => void this.read(), 1000);
  }

  close() { clearInterval(this.timer); }

  handleInput(data: string) { if (data === "q" || data === "\x03") { this.close(); this.closer.fire(); } }

  private print(lines: string[]) { if (lines.length) this.writer.fire(`${lines.join("\r\n")}\r\n`); }

  private async read() {
    let lines: string[] = [], cut = 0;
    const r = await this.tail.read((line) => {
      // rewritten under the view: read from its start, as a transcript opened for the first time
      if (this.tail.resets !== this.resets) { this.resets = this.tail.resets; this.first = true; this.term = new Term(this.cwd, this.side); lines = [dim("— the transcript was rewritten: from its start —"), ""]; cut = 0; }
      let evs: Ev[];
      try { evs = this.line(line); } catch { return; }
      for (const ev of evs) { try { lines.push(...this.term.feed(ev)); } catch { /* a line it does not understand */ } }
      // read for the first time, only its tail is kept: a long session is megabytes of lines nobody scrolls through
      if (this.first && lines.length > 2 * KEPT) { cut += lines.length - KEPT; lines = lines.slice(-KEPT); }
    });
    if (this.first && lines.length > KEPT) { cut += lines.length - KEPT; lines = lines.slice(-KEPT); }
    if (r.error && this.first) lines.push(dim(safe(r.error)));
    if (cut) lines.unshift(dim(`… ${cut} earlier lines are in ${safe(this.tail.file)}`), "");
    this.first = false;
    this.print(lines);
  }
}

export class Terminals {
  private readonly views = new Map<string, vscode.Terminal>(); // a transcript's file -> the view of its tail

  /** The view of a transcript's tail, the one that is there already where there is one. `side`: "" for the
   *  session's own file, null for a subagent's own. */
  tailOf(file: string, found: Found, title: string, what: string, side: string | null): vscode.Terminal {
    const have = this.views.get(file);
    if (have && have.exitStatus === undefined && vscode.window.terminals.includes(have)) return have;
    const name = `◆ ${safe(title.length > 24 ? `${title.slice(0, 23)}…` : title)}`;
    const term = vscode.window.createTerminal({ name, pty: new TailView(file, found, what, side), iconPath: new vscode.ThemeIcon("type-hierarchy-sub") });
    this.views.set(file, term);
    return term;
  }

  /** A new terminal in the session's folder that takes it up again: `claude --resume <id>`, `codex resume <id>`.
   *  The caller has made sure nothing has the session open. */
  resume(found: Found): vscode.Terminal | undefined {
    // resumed here already, and that terminal is still there: shown, never a second writer beside it
    const was = this.resumed.get(found.file);
    if (was && was.exitStatus === undefined && vscode.window.terminals.includes(was)) { was.show(); return was; }
    const line = resumeLine(found.agent, found.id);
    if (!line) return undefined;
    const term = vscode.window.createTerminal({ name: line.split(" ").slice(0, 2).join(" "), cwd: found.cwd });
    this.resumed.set(found.file, term);
    term.show();
    term.sendText(line, true);
    return term;
  }
  private readonly resumed = new Map<string, vscode.Terminal>(); // a session's file -> the terminal it was resumed in
}
