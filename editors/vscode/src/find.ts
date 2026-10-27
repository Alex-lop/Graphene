// First run without hunting: find graphene on PATH, in ~/.local/bin or in `uv tool dir --bin`; use the one
// found when graphene.path is unset and say where in the status bar; offer to install it when none is; Set
// Up This Folder as a pair of quick picks, then `graphene init` in a terminal (an init that sees no terminal
// leaves the gate open), then Auto…. Pure: no VS Code here; setup.ts does the asking.
import * as path from "node:path";

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
