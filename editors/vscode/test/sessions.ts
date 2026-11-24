// What the session tests share: the hand-made files (test/fixtures/sessions) and a session read whole from one.
import { mkdtempSync } from "node:fs";
import * as os from "node:os";
import * as path from "node:path";
import { fileURLToPath } from "node:url";
import type { Found } from "../src/sessions/find.ts";
import { Follow } from "../src/sessions/follow.ts";
import type { Model } from "../src/sessions/model.ts";

export const FIX = fileURLToPath(new URL("./fixtures/sessions/", import.meta.url));
export const ROLLOUT = "rollout-2026-11-24T10-00-00-01a20f92-0000-7000-8000-000000000001.jsonl";
export const at = (iso: string) => Date.parse(iso);
export const found = (file: string, agent: Found["agent"] = "claude"): Found =>
  ({ agent, file: path.join(FIX, file), id: path.basename(file, ".jsonl").replace(/^rollout-[\dT-]{19}-/, ""), cwd: "/work/app", mtime: 0, size: 1 });
export async function read(file: string, agent: Found["agent"] = "claude"): Promise<Model> {
  const f = new Follow(found(file, agent));
  await f.read();
  f.model.touched = 0; // a fixture is not a file being written: when it was checked out says nothing of its session
  return f.model;
}
export const scratch = () => mkdtempSync(path.join(os.tmpdir(), "graphene-sessions-"));
