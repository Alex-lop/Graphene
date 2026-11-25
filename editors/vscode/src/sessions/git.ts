// What git knows that tool calls do not, of the session's own folder and what is under it (a folder inside a
// larger repository, or one that only an enclosing repository holds, is not that whole repository: nothing of it
// outside the folder is read). When a session is first seen its folder's HEAD and its dirty files are
// noted; later the folder is compared with that note, and what changed with no tool call of the session to
// explain it is said (a command the agent ran, a formatter, the person's own edit: git cannot tell which, and
// the receipt does not guess). Read-only: `git rev-parse`, `git status`, `git diff --name-only`,
// `git rev-list --count`, `git hash-object`. Nothing is written, staged or fetched.
import { execFile } from "node:child_process";
import { realpathSync, statSync } from "node:fs";
import * as path from "node:path";

/** A folder's repository as git has it at one moment: its top, the folder from there (`.` for the top itself),
 *  its HEAD, and each dirty file under the folder (as a path from the top) with a hash of what it holds, "" where
 *  none was taken. */
export interface Note { top: string; dir: string; head: string; dirty: Map<string, string>; at: number }
/** What moved since a note: HEAD (how many commits it has now that the noted one did not, and how many the noted
 *  one had that it has not: a reset, or another branch), and the files that differ. */
export interface Since { head: string; commits: number; dropped: number; changed: string[] }

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

/** A path as the disk has it (/tmp is /private/tmp): git's top is one, and a session names its folder as it was
 *  given. A file that is gone has no real path of its own: its folder's, then. */
const real = (p: string): string => { try { return realpathSync(p); } catch { const up = path.dirname(p); return up === p ? p : path.join(real(up), path.basename(p)); } };

/** The folder's repository as it is now; null where there is no git, or no repository. */
export async function note(cwd: string): Promise<Note | null> {
  const top = (await git(cwd, ["rev-parse", "--show-toplevel"]))?.trim();
  return top ? read(top, path.relative(top, real(cwd)).split(path.sep).join("/") || ".") : null;
}

async function read(top: string, dir: string): Promise<Note | null> {
  const head = (await git(top, ["rev-parse", "--verify", "-q", "HEAD"]))?.trim() ?? ""; // none yet in a repository with no commit
  const files = porcelain((await git(top, ["status", "--porcelain", "-z", "--untracked-files=all", "--", dir])) ?? "");
  const dirty = new Map<string, string>(files.map((f) => [f, ""]));
  // one at a time would be a process a file; all at once fails on a single file that is not there (a deleted one
  // is dirty too), so only files that are there are hashed, and of a great many only the first
  const there = files.filter((f) => statSync(path.join(top, f), { throwIfNoEntry: false })?.isFile()).slice(0, HASHED);
  const hashes = there.length ? (await git(top, ["hash-object", "--no-filters", "--", ...there]))?.trim().split("\n") : undefined;
  if (hashes?.length === there.length) there.forEach((f, i) => dirty.set(f, hashes[i]!));
  return { top, dir, head, dirty, at: Date.now() };
}

/** What differs between a note and the repository now: files committed since, files dirty now that were clean
 *  then, files clean now that were dirty then, and files dirty at both that hold something else now (where both
 *  were hashed: where one was not, nothing is said of the file). */
export async function since(was: Note): Promise<Since | null> {
  const now = await read(was.top, was.dir);
  if (!now) return null;
  const changed = new Set<string>();
  let commits = 0, dropped = 0;
  const count = async (range: string) => Number((await git(was.top, ["rev-list", "--count", range]))?.trim() ?? 0) || 0;
  if (was.head && now.head && was.head !== now.head) {
    for (const f of (await git(was.top, ["diff", "--name-only", "-z", was.head, now.head, "--", was.dir]))?.split("\0").filter(Boolean) ?? []) changed.add(f);
    commits = await count(`${was.head}..${now.head}`);
    dropped = await count(`${now.head}..${was.head}`);
  }
  for (const [f, h] of now.dirty) {
    const then = was.dirty.get(f);
    if (then === undefined || (h && then && h !== then)) changed.add(f);
  }
  for (const f of was.dirty.keys()) if (!now.dirty.has(f)) changed.add(f);
  return { head: now.head, commits, dropped, changed: [...changed].sort() };
}

/** A file as a commit has it; "" for one the commit does not have (a new file), or where git cannot say. */
export async function show(top: string, rev: string, rel: string): Promise<string> {
  return (await git(top, ["show", `${rev}:${rel}`])) ?? "";
}

/** Of what git says changed (paths from the repository's top), the files no write of the session's explains.
 *  `written`: the files its tool calls wrote, as the receipt names them (from the session's folder, or absolute). */
export function unexplained(changed: readonly string[], written: readonly string[], top: string, cwd: string): string[] {
  const at = real(cwd), mine = new Set(written.map((f) => path.relative(top, path.isAbsolute(f) ? real(f) : path.resolve(at, f)).split(path.sep).join("/")));
  return changed.filter((f) => !mine.has(f));
}
