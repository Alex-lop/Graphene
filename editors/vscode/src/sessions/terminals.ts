// A card's terminal, in the editor. If the session runs in one of the editor's own terminals, that one (the
// running agent's record of itself names its process, and the process tree says which terminal is above it).
// Otherwise a view of its transcript's tail that reads like a terminal, followed as the file grows: a
// pseudoterminal that only prints. And for a session nothing has open, a new terminal that takes it up again.
// Nothing typed in the view reaches an agent, and nothing here writes to a session's file.
import { execFile } from "node:child_process";
import * as vscode from "vscode";
import type { Ev } from "./events.ts";
import { readerOf, type Found } from "./find.ts";
import { Tail } from "./tail.ts";
import { ancestors, dim, parents, resumeLine, Term } from "./term.ts";

/** Every process and its parent, as `ps` lists them; none where there is no `ps` (Windows), or it fails. */
export function processes(): Promise<Map<number, number>> {
  return new Promise((resolve) => {
    execFile("ps", ["-axo", "pid=,ppid="], { maxBuffer: 8 << 20 }, (err, out) => resolve(err ? new Map() : parents(String(out))));
  });
}

/** The editor's own terminal a process runs in: the one whose shell is above it. */
export async function terminalOf(pid: number): Promise<vscode.Terminal | undefined> {
  const above = new Set(ancestors(pid, await processes()));
  for (const t of vscode.window.terminals) {
    const shell = await t.processId;
    if (shell && above.has(shell)) return t;
  }
  return undefined;
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
  private readonly tail: Tail;
  private readonly term: Term;
  private readonly line: (line: string) => Ev[];
  private readonly what: string;

  constructor(file: string, found: Found, what: string) {
    this.tail = new Tail(file);
    this.term = new Term(found.cwd);
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
      let evs: Ev[];
      try { evs = this.line(line); } catch { return; }
      for (const ev of evs) { try { lines.push(...this.term.feed(ev)); } catch { /* a line it does not understand */ } }
      // read for the first time, only its tail is kept: a long session is megabytes of lines nobody scrolls through
      if (this.first && lines.length > 2 * KEPT) { cut += lines.length - KEPT; lines = lines.slice(-KEPT); }
    });
    if (this.first && lines.length > KEPT) { cut += lines.length - KEPT; lines = lines.slice(-KEPT); }
    if (r.error && this.first) lines.push(dim(r.error));
    if (cut) lines.unshift(dim(`… ${cut} earlier lines are in ${this.tail.file}`), "");
    this.first = false;
    this.print(lines);
  }
}

export class Terminals {
  private readonly views = new Map<string, vscode.Terminal>(); // a transcript's file -> the view of its tail

  /** The view of a transcript's tail, the one that is there already where there is one. */
  tailOf(file: string, found: Found, title: string, what: string): vscode.Terminal {
    const have = this.views.get(file);
    if (have && have.exitStatus === undefined && vscode.window.terminals.includes(have)) return have;
    const name = `◆ ${title.length > 24 ? `${title.slice(0, 23)}…` : title}`;
    const term = vscode.window.createTerminal({ name, pty: new TailView(file, found, what), iconPath: new vscode.ThemeIcon("type-hierarchy-sub") });
    this.views.set(file, term);
    return term;
  }

  /** A new terminal in the session's folder that takes it up again: `claude --resume <id>`, `codex resume <id>`.
   *  The caller has made sure nothing has the session open. */
  resume(found: Found): vscode.Terminal | undefined {
    const line = resumeLine(found.agent, found.id);
    if (!line) return undefined;
    const term = vscode.window.createTerminal({ name: line.split(" ").slice(0, 2).join(" "), cwd: found.cwd });
    term.show();
    term.sendText(line, true);
    return term;
  }
}
