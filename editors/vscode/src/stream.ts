// The stream: one long-lived `graphene state --json --watch` per session, as the person, a snapshot a line
// (dev/process/editor/CONTRACT.md, lane 3). Each line goes to Session.take. It is started again with a
// backoff when it dies, and given up for the poll when the CLI answers "No such option" (an older CLI). The
// pure parts, `lines` and `unsupported`, have no VS Code in them.
import { spawn, type ChildProcess } from "node:child_process";
import * as C from "./commands.ts";

export const WATCH = (): string[] => ["state", "--json", "--watch"];

/** The complete lines in ``buffer`` plus ``chunk``, and what is left: a snapshot is one line, and a chunk may
 *  end mid-line or hold several. */
export function lines(buffer: string, chunk: string): { whole: string[]; rest: string } {
  const parts = (buffer + chunk).split("\n");
  const rest = parts.pop() ?? "";
  return { whole: parts.map((l) => l.trim()).filter(Boolean), rest };
}

/** Did the CLI refuse `--watch` itself? Then it is an older graphene: the poll does its job. */
export function unsupported(stderr: string): boolean {
  return /no such option/i.test(stderr);
}

/** The next wait before starting the child again: 1 s, then doubling, at most 30 s. */
export function backoff(tries: number): number {
  return Math.min(30000, 1000 * 2 ** Math.max(0, tries - 1));
}

export interface StreamHost {
  path: string; // the graphene command
  cwd: string | undefined;
  onLine(line: string): void;
}

export class Stream {
  private child: ChildProcess | null = null;
  private timer: NodeJS.Timeout | undefined;
  private tries = 0;
  private stopped = false;
  /** The stream is up and the CLI has it: the poll and the watcher rest. False until the first line. */
  live = false;
  /** The CLI answered "No such option": the poll is the way, until the CLI changes. */
  unsupported = false;

  private host: StreamHost;

  constructor(host: StreamHost) {
    this.host = host;
  }

  start() {
    if (this.stopped || this.unsupported || this.child) return;
    let buffer = "";
    let stderr = "";
    let child: ChildProcess;
    try {
      child = spawn(this.host.path, WATCH(), { cwd: this.host.cwd, env: C.scrub(process.env), stdio: ["ignore", "pipe", "pipe"] });
    } catch {
      return this.again();
    }
    this.child = child;
    child.stdout?.setEncoding("utf8");
    child.stderr?.setEncoding("utf8");
    child.stdout?.on("data", (chunk: string) => {
      const got = lines(buffer, chunk);
      buffer = got.rest;
      for (const line of got.whole) {
        this.live = true;
        this.tries = 0;
        this.host.onLine(line);
      }
    });
    child.stderr?.on("data", (chunk: string) => { stderr = (stderr + chunk).slice(-4000); });
    child.on("error", () => { /* exit follows */ });
    child.on("exit", () => {
      this.child = null;
      this.live = false;
      if (unsupported(stderr)) { this.unsupported = true; return; }
      this.again();
    });
  }

  private again() {
    if (this.stopped) return;
    this.tries += 1;
    clearTimeout(this.timer);
    this.timer = setTimeout(() => this.start(), backoff(this.tries));
  }

  /** Start over (the folder or the command changed): the child ends, a new one starts. */
  restart() {
    this.unsupported = false;
    this.tries = 0;
    const child = this.child;
    this.child = null;
    child?.kill();
    clearTimeout(this.timer);
    this.start();
  }

  dispose() {
    this.stopped = true;
    clearTimeout(this.timer);
    this.child?.kill();
    this.child = null;
    this.live = false;
  }
}
