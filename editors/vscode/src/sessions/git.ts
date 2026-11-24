// What git knows that tool calls do not. When a session is first seen its folder's HEAD and its dirty files are
// noted; later the folder is compared with that note, and what changed with no tool call of the session to
// explain it is said (a command the agent ran, a formatter, the person's own edit: git cannot tell which, and
// the receipt does not guess). Read-only: `git rev-parse`, `git status`, `git diff --name-only`,
// `git rev-list --count`, `git hash-object`. Nothing is written, staged or fetched.
import { execFile } from "node:child_process";
import * as path from "node:path";

/** A folder's repository as git has it at one moment: its top, its HEAD, and each dirty file (as a path from the
 *  top) with a hash of what it holds, "" where none was taken. */
export interface Note { top: string; head: string; dirty: Map<string, string>; at: number }
/** What moved since a note: HEAD (and how many commits on top of the noted one), and the files that differ. */
export interface Since { head: string; commits: number; changed: string[] }

function git(cwd: string, args: string[]): Promise<string | null> {
  return new Promise((resolve) => {
    execFile("git", args, { cwd, maxBuffer: 16 << 20, timeout: 10_000 }, (err, out) => resolve(err ? null : String(out)));
  });
}

/** `git status --porcelain -z` as paths: a renamed file's new name, a deleted one's own. */
export function porcelain(out: string): string[] {
  const files: string[] = [], parts = out.split("\0");
  for (let i = 0; i < parts.length; i++) {
    const p = parts[i]!;
    if (p.length < 4) continue;
    files.push(p.slice(3));
    if (p[0] === "R" || p[0] === "C") i++; // the name it had before follows: not a file of its own
  }
  return files;
}

/** The most dirty files hashed for a note: a folder with thousands of them is noted by their names alone. */
const HASHED = 300;

/** The folder's repository as it is now; null where there is no git, or no repository. */
export async function note(cwd: string): Promise<Note | null> {
  const top = (await git(cwd, ["rev-parse", "--show-toplevel"]))?.trim();
  if (!top) return null;
  const head = (await git(top, ["rev-parse", "--verify", "-q", "HEAD"]))?.trim() ?? ""; // none yet in a repository with no commit
  const files = porcelain((await git(top, ["status", "--porcelain", "-z", "--untracked-files=all"])) ?? "");
  const dirty = new Map<string, string>(files.map((f) => [f, ""]));
  // one at a time would be a process a file; all at once fails on a file that was deleted, so those are left out
  const there = files.length <= HASHED ? files.filter((f) => !f.endsWith("/")) : [];
  const hashes = there.length ? (await git(top, ["hash-object", "--no-filters", "--", ...there]))?.trim().split("\n") : undefined;
  if (hashes?.length === there.length) there.forEach((f, i) => dirty.set(f, hashes[i]!));
  return { top, head, dirty, at: Date.now() };
}

/** What differs between a note and the repository now: files committed since, files dirty now that were clean
 *  then, files clean now that were dirty then, and files dirty at both that hold something else now (where both
 *  were hashed: where one was not, nothing is said of the file). */
export async function since(was: Note): Promise<Since | null> {
  const now = await note(was.top);
  if (!now) return null;
  const changed = new Set<string>();
  let commits = 0;
  if (was.head && now.head && was.head !== now.head) {
    for (const f of (await git(was.top, ["diff", "--name-only", "-z", was.head, now.head]))?.split("\0").filter(Boolean) ?? []) changed.add(f);
    commits = Number((await git(was.top, ["rev-list", "--count", `${was.head}..${now.head}`]))?.trim() ?? 0) || 0;
  }
  for (const [f, h] of now.dirty) {
    const then = was.dirty.get(f);
    if (then === undefined || (h && then && h !== then)) changed.add(f);
  }
  for (const f of was.dirty.keys()) if (!now.dirty.has(f)) changed.add(f);
  return { head: now.head, commits, changed: [...changed].sort() };
}

/** A file as a commit has it; "" for one the commit does not have (a new file), or where git cannot say. */
export async function show(top: string, rev: string, rel: string): Promise<string> {
  return (await git(top, ["show", `${rev}:${rel}`])) ?? "";
}

/** Of what git says changed (paths from the repository's top), the files no write of the session's explains.
 *  `written`: the files its tool calls wrote, as the receipt names them (from the session's folder, or absolute). */
export function unexplained(changed: readonly string[], written: readonly string[], top: string, cwd: string): string[] {
  const mine = new Set(written.map((f) => path.relative(top, path.resolve(cwd, f)).split(path.sep).join("/")));
  return changed.filter((f) => !mine.has(f));
}
