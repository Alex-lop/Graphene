// Where the agents keep their sessions, and which of them are a folder's. Claude Code:
// ~/.claude/projects/<the folder's path, each character that is no letter or digit a dash>/<session id>.jsonl.
// Codex: ~/.codex/sessions/YYYY/MM/DD/rollout-<time>-<id>.jsonl. A session is a folder's by the `cwd` its own
// lines say, never by a directory's name: the name loses what the dashes stood for, and Codex's has no folder
// in it at all. Node's file system only: no VS Code here, so `node --test` reads it.
import { open, readdir, readFile, realpath, stat } from "node:fs/promises";
import * as os from "node:os";
import * as path from "node:path";
import { claudeLine } from "./claude.ts";
import { codexLine } from "./codex.ts";
import type { Agent, Ev } from "./events.ts";

/** A session's file, and whose it is. */
export interface Found { agent: Agent; file: string; id: string; cwd: string; mtime: number; size: number }

/** One agent's sessions, behind the one interface the rest is written to: how its lines read, where its files are. */
export interface Reader {
  agent: Agent;
  name: string;
  line(line: string): Ev[];
  find(folder: string, home?: string): Promise<Found[]>;
}

export const claudeHome = (env: NodeJS.ProcessEnv = process.env): string => env.CLAUDE_CONFIG_DIR || path.join(os.homedir(), ".claude");
export const codexHome = (env: NodeJS.ProcessEnv = process.env): string => env.CODEX_HOME || path.join(os.homedir(), ".codex");

/** Claude Code's name for a folder's sessions: its path with every character that is no letter or digit a dash. */
export const encoded = (folder: string): string => folder.replace(/[^A-Za-z0-9]/g, "-");

/** Whether a session that started in `cwd` is this folder's: started in it, or in a folder inside it. */
export function inside(cwd: string, folder: string): boolean {
  if (!cwd || !folder) return false;
  const r = path.relative(folder, cwd);
  return r === "" || (!r.startsWith("..") && !path.isAbsolute(r));
}

/** The first bytes of a file, as text; "" for a file that cannot be read. */
export async function head(file: string, bytes = 1 << 16): Promise<string> {
  try {
    const fh = await open(file, "r");
    try {
      const buf = Buffer.alloc(bytes), { bytesRead } = await fh.read(buf, 0, bytes, 0);
      return buf.subarray(0, bytesRead).toString("utf8");
    } finally { await fh.close(); }
  } catch { return ""; }
}

/** The first `cwd` a file's lines say: where its session started. */
export function cwdOf(text: string): string {
  const m = /"cwd":\s*("(?:[^"\\]|\\.)*")/.exec(text);
  try { return m ? String(JSON.parse(m[1]!)) : ""; } catch { return ""; }
}

/** A folder as the agents name it: its real path, which is what a process's working directory is. */
async function real(folder: string): Promise<string> {
  try { return await realpath(folder); } catch { return folder; }
}

const started = new Map<string, string>(); // a session file -> where it started: read once, it never changes

async function cwdIn(file: string): Promise<string> {
  let cwd = started.get(file);
  if (cwd === undefined) {
    cwd = cwdOf(await head(file)) || cwdOf(await head(file, 1 << 20)); // past a long first line
    if (cwd) started.set(file, cwd);
  }
  return cwd;
}

async function found(agent: Agent, file: string, id: string, folders: readonly string[]): Promise<Found | null> {
  try {
    const s = await stat(file);
    if (!s.isFile() || !s.size) return null;
    const cwd = await cwdIn(file);
    return folders.some((f) => inside(cwd, f)) ? { agent, file, id, cwd, mtime: s.mtimeMs, size: s.size } : null;
  } catch { return null; }
}

/** Claude Code's sessions that started in the folder or inside it. Only the directories whose name begins as the
 *  folder's does are opened (hundreds of projects are not read for one), then each file's own `cwd` decides.
 *  ponytail: Claude Code shortens a very long path's name with a hash, so a folder whose path is past some 200
 *  characters is not found by its name; read every directory's first file then. */
export async function findClaude(folder: string, home = claudeHome()): Promise<Found[]> {
  const root = path.join(home, "projects"), here = [...new Set([await real(folder), folder])]; // as the agent's process names it, and as the editor does
  const names = here.map(encoded);
  let dirs: string[];
  try { dirs = (await readdir(root)).filter((d) => names.some((n) => d === n || d.startsWith(`${n}-`))); } catch { return []; }
  const out: (Found | null)[] = [];
  for (const d of dirs) {
    let files: string[];
    try { files = (await readdir(path.join(root, d))).filter((f) => f.endsWith(".jsonl")); } catch { continue; }
    out.push(...await Promise.all(files.map((f) => found("claude", path.join(root, d, f), f.slice(0, -6), here))));
  }
  return out.filter((f): f is Found => f !== null);
}

/** Codex's sessions that started in the folder or inside it, among the rollouts of the last `days` days (a
 *  session lives in the day it began). */
export async function findCodex(folder: string, home = codexHome(), days = 30, now = Date.now()): Promise<Found[]> {
  const root = path.join(home, "sessions"), here = [...new Set([await real(folder), folder])], out: (Found | null)[] = [];
  for (let d = 0; d < days; d++) {
    const day = new Date(now - d * 86_400_000);
    const dir = path.join(root, String(day.getFullYear()), String(day.getMonth() + 1).padStart(2, "0"), String(day.getDate()).padStart(2, "0"));
    let files: string[];
    try { files = (await readdir(dir)).filter((f) => f.startsWith("rollout-") && f.endsWith(".jsonl")); } catch { continue; }
    // rollout-2026-11-24T17-00-21-<id>.jsonl: the id is what `codex resume` takes
    out.push(...await Promise.all(files.map((f) => found("codex", path.join(dir, f), /^rollout-\d{4}-\d\d-\d\dT\d\d-\d\d-\d\d-(.+)\.jsonl$/.exec(f)?.[1] ?? f.slice(8, -6), here))));
  }
  return out.filter((f): f is Found => f !== null);
}

export const CLAUDE: Reader = { agent: "claude", name: "Claude Code", line: claudeLine, find: findClaude };
export const CODEX: Reader = { agent: "codex", name: "Codex", line: codexLine, find: findCodex };
export const READERS: readonly Reader[] = [CLAUDE, CODEX];
export const readerOf = (agent: Agent): Reader => (agent === "codex" ? CODEX : CLAUDE);

/** Every session of the folder, both agents', the last written first. */
export async function findAll(folder: string, homes: { claude?: string; codex?: string } = {}): Promise<Found[]> {
  const all = await Promise.all([findClaude(folder, homes.claude), findCodex(folder, homes.codex)]);
  return all.flat().sort((a, b) => b.mtime - a.mtime);
}

/** A running Claude Code's own record of itself, ~/.claude/sessions/<pid>.json: the session it has open and
 *  whether it is busy. Undocumented, and there only while the process runs (2.1.331 writes it). */
export interface Proc { pid: number; session: string; cwd: string; status: string }

/** The records of the Claude Code processes that are running now, by the session each has open. A record whose
 *  process is gone is not one. */
export async function procs(home = claudeHome(), alive: (pid: number) => boolean = isAlive): Promise<Map<string, Proc>> {
  const out = new Map<string, Proc>(), dir = path.join(home, "sessions");
  let files: string[];
  try { files = (await readdir(dir)).filter((f) => /^\d+\.json$/.test(f)); } catch { return out; }
  for (const f of files) {
    try {
      const r = JSON.parse(await readFile(path.join(dir, f), "utf8")) as Record<string, unknown>;
      const pid = typeof r.pid === "number" ? r.pid : Number(f.slice(0, -5));
      if (typeof r.sessionId === "string" && alive(pid)) out.set(r.sessionId, { pid, session: r.sessionId, cwd: String(r.cwd ?? ""), status: String(r.status ?? "") });
    } catch { /* half written, or not a record: the next read has it */ }
  }
  return out;
}

function isAlive(pid: number): boolean {
  try { process.kill(pid, 0); return true; } catch (e) { return (e as NodeJS.ErrnoException).code === "EPERM"; }
}
