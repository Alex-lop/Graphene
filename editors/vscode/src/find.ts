// First run without hunting: find graphene on PATH, in ~/.local/bin or in `uv tool dir --bin`; use the one
// found when graphene.path is unset and say where in the status bar; offer to install it when none is; Set
// Up This Folder as a pair of quick picks, then `graphene init` in a terminal (an init that sees no terminal
// leaves the gate open), then Auto…. Pure: no VS Code here; setup.ts does the asking.
import * as path from "node:path";
import { OLDER } from "./commands.ts";

/** Where graphene may be, in the order to look: each PATH entry, then ~/.local/bin, then uv's own bin. */
export function candidates(pathEnv: string | undefined, home: string, uvBin: string | null, sep = path.delimiter): string[] {
  const dirs = (pathEnv ?? "").split(sep).filter(Boolean);
  for (const d of [path.join(home, ".local", "bin"), uvBin]) if (d && !dirs.includes(d)) dirs.push(d);
  return dirs.map((d) => path.join(d, process.platform === "win32" ? "graphene.exe" : "graphene"));
}

/** The first candidate that exists, and whether it was on PATH. */
export function found(list: string[], exists: (p: string) => boolean, onPath: number): { path: string; onPath: boolean } | null {
  const i = list.findIndex(exists);
  return i < 0 ? null : { path: list[i]!, onPath: i < onPath };
}

/** Did the command not run at all? execFile's `err.code` is the spawn error's name then (ENOENT, EACCES for a
 *  file without its x bit, EISDIR for a directory, ENOTDIR, EPERM): the not-installed offer, not "graphene said
 *  nothing". A number is graphene's own exit code, null a signal, ERR_* Node's own after it ran. */
export function cannotRun(code: unknown): boolean {
  return typeof code === "string" && /^E[A-Z]+$/.test(code);
}

/** Which graphene the extension runs, as the status bar's hover says it: `graphene --version`'s line and the
 *  path (a machine may hold two: uv's in ~/.local/bin and the one on the PATH). */
export function which(path: string, version: string | null): string {
  return `${version || "graphene"} at ${path}${version ? "" : " (its version did not read)"}`;
}

/** The older-CLI line, naming the graphene that answered: the person sees which one to upgrade or point past. */
export function olderWords(path: string, version: string | null): string {
  return `${OLDER} This editor runs ${which(path, version)}.`;
}
