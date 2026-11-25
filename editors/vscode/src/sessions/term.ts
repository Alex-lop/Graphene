// A transcript's tail as a terminal would have shown it: what the person asked, what the agent said, each
// command, the end of its output, each file it wrote. For a session that does not run in one of the editor's
// own terminals, this is the view its card opens. Pure: events in, lines out (with a terminal's colours); the
// editor's pseudoterminal that prints them is hub.ts's.
import { COMMAND, str, SUBAGENT, WRITES, type Ev } from "./events.ts";

const ESC = "\x1b[";
const paint = (code: string) => (s: string) => `${ESC}${code}m${s}${ESC}0m`;
export const bold = paint("1"), dim = paint("2"), red = paint("31"), green = paint("32"), yellow = paint("33"), cyan = paint("36");

/** The end of a command's output that is shown: a test run sums up in its last lines. */
export const OUTPUT_LINES = 14;
/** A line an agent wrote is not trusted with the terminal: only printing characters and tabs go through, so no
 *  escape sequence from a transcript moves the cursor, renames the tab or asks the terminal a question. */
export const safe = (s: string): string => s.replace(/[\u0000-\u0008\u000b-\u001f\u007f-\u009f\u200b-\u200f\u2028-\u202e\u2066-\u2069\ufeff]/g, ""); // controls, and what reorders or hides text
const rows = (text: string): string[] => text.replace(/\r\n?/g, "\n").split("\n").map(safe);

/** One session's (or one subagent's) events, turned into a terminal's lines as they come. */
export class Term {
  private calls = new Map<string, string>(); // a call's id -> its tool's name: a result is printed as its tool's
  private over = false; // its turn's end was printed: a transcript says it on each of a reply's last lines, a terminal once
  private readonly cwd: string;
  private readonly own: string | null;

  /** `own`: the one thread whose lines are printed ("" the session's own, a subagent's id); null prints them all. */
  constructor(cwd = "", own: string | null = null) { this.cwd = cwd; this.own = own; }

  /** The lines an event prints; none for what a terminal would not have shown. */
  feed(ev: Ev): string[] {
    if (ev.k === "meta") return [];
    if (this.own !== null && ev.k !== "result" && ev.side !== this.own) return []; // another thread's line (an older transcript mixes them)
    const was = this.over;
    this.over = ev.k === "end" || ev.k === "stop";
    if (was && this.over) return [];
    switch (ev.k) {
      case "ask": return ["", ...rows(ev.text).slice(0, 8).map((l, i) => bold(`${i ? "  " : "❯ "}${l}`)), ""];
      case "say": return [...rows(ev.text.trim()), ""];
      case "tool": {
        this.calls.set(ev.id, ev.name);
        const file = this.rel(str(ev.input.file_path) || str(ev.input.notebook_path));
        if (ev.name === COMMAND) return rows(str(ev.input.command)).map((l, i) => cyan(`${i ? "  " : "$ "}${l}`));
        if (WRITES.includes(ev.name)) return [yellow(`✎ ${ev.name === "Write" ? "write" : "edit"} ${file}`)];
        if (ev.name === "Read") return [dim(`· read ${file}`)];
        if (SUBAGENT.includes(ev.name)) return [dim(`· subagent: ${safe(str(ev.input.description))}`)];
        return [dim(`· ${safe(ev.name)}`)];
      }
      case "result": {
        const name = this.calls.get(ev.id);
        this.calls.delete(ev.id);
        if (name !== COMMAND) return ev.error ? [red(`  ✗ ${rows(ev.out)[0] ?? "failed"}`)] : [];
        const out = rows([ev.out, ev.err].filter((s) => s.trim()).join("\n").trimEnd()).filter((l, i, all) => l.trim() || (i > 0 && i < all.length - 1));
        const shown = out.slice(-OUTPUT_LINES);
        return [...(out.length > shown.length ? [dim(`  … ${out.length - shown.length} lines above`)] : []), ...shown.map((l) => dim(`  ${l}`)),
                ...(ev.exit !== null && ev.exit !== 0 ? [red(`  ✗ exit ${ev.exit}`)] : ev.error && ev.exit === null ? [red("  ✗ did not run")] : []), ""];
      }
      case "end": return [dim("— its turn ended —"), ""];
      case "stop": return [dim("— interrupted —"), ""];
    }
    return [];
  }

  /** A file's name is an agent's words too (git allows a control byte in one): made safe wherever it is printed. */
  private rel(file: string): string {
    return safe(this.cwd && file.startsWith(`${this.cwd}/`) ? file.slice(this.cwd.length + 1) : file);
  }
}

/** `ps -axo pid=,ppid=` as a table: each process's parent. */
export function parents(ps: string): Map<number, number> {
  const out = new Map<number, number>();
  for (const line of ps.split("\n")) {
    const m = /^\s*(\d+)\s+(\d+)/.exec(line);
    if (m) out.set(Number(m[1]), Number(m[2]));
  }
  return out;
}

/** `ps -axo pid=,ppid=,command=` as each process's command line. */
export function commandsOf(ps: string): Map<number, string> {
  const out = new Map<number, string>();
  for (const line of ps.split("\n")) {
    const m = /^\s*(\d+)\s+\d+\s+(.*)$/.exec(line);
    if (m) out.set(Number(m[1]), m[2]!);
  }
  return out;
}

/** Whether a command line is that agent's own program: its first word, or the script a `node` runs, is named so.
 *  What a record of a process is held to before it is believed: a pid is given to another program in time. */
export function runs(command: string, agent: "claude" | "codex"): boolean {
  const line = command.trim(), words = line.split(/\s+/), name = (w: string | undefined) => (w ?? "").split("/").pop()!.replace(/\.(js|mjs|cjs|exe)$/, "");
  // started by its versioned binary (…/claude/versions/2.1.331), or from a path with a space in it: still the agent
  if (words[0]!.includes(`/${agent}/`) || (line.startsWith("/") && line.split(/\s+-/)[0]!.endsWith(`/${agent}`))) return true;
  return name(words[0]) === agent || (/^(node|bun|deno)$/.test(name(words[0])) && words.slice(1, 4).some((w) => !w.startsWith("-") && (name(w) === agent || w.includes(`/${agent}`))));
}

/** A process and every process above it, nearest first: the shell that started an agent, the terminal that
 *  started the shell. A table that loops (it never should) ends the walk. */
export function ancestors(pid: number, table: ReadonlyMap<number, number>): number[] {
  const out: number[] = [];
  for (let p: number | undefined = pid; p !== undefined && p > 0 && !out.includes(p); p = table.get(p)) out.push(p);
  return out;
}

/** The command that takes a session up again in a terminal, or "" for an id that is not one: the id is a file's
 *  name, and only letters, digits and dashes go on a shell's line. */
export function resumeLine(agent: "claude" | "codex", id: string): string {
  if (!/^[A-Za-z0-9][A-Za-z0-9_-]{5,80}$/.test(id)) return "";
  return agent === "codex" ? `codex resume ${id}` : `claude --resume ${id}`;
}
