// The harness's own pieces that need no app: `node --test unit.test.mjs` (part of `npm test`).
import assert from "node:assert/strict";
import { execFileSync, spawnSync } from "node:child_process";
import { existsSync, mkdtempSync, readFileSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import { test } from "node:test";
import * as L from "./lib.mjs";
import { line, summary } from "./measure/stats.mjs";

const PYTHON = process.env.PYTHON || path.join(L.ROOT, ".venv", "bin", "python");
const moves = (manifest) => spawnSync(PYTHON, [path.join(L.HERE, "measure", "moves.py"), manifest], { encoding: "utf8" });

test("moves.py's table is the build it measures: every command it names is in the manifest, and the count follows", { skip: !existsSync(PYTHON) && "no venv python (uv sync)" }, () => {
  const manifest = path.join(L.EXT, "package.json");
  const out = moves(manifest);
  assert.equal(out.status, 0, out.stderr);
  const table = out.stdout.split("\n\ncockpit moves")[0];
  const commands = JSON.parse(readFileSync(manifest, "utf8")).contributes.commands.map((c) => c.command.replace("graphene.", ""));
  const named = new Set([...table.matchAll(/graphene\.(\w+)/g)].map((m) => m[1]));
  assert.deepEqual([...named].filter((c) => !commands.includes(c)), [], "the table names commands this build lacks");
  // the night's moves are in its table, not left as the cockpit's alone
  for (const c of ["answer", "handBack", "pickFork", "openDiff", "signOff", "editPlan"]) assert.ok(named.has(c), `${c} is not in the table`);
  assert.match(out.stdout, /cockpit moves: 17\. The editor \(0\.9\.\d+\) covers 9 whole and 5 in part; 3 not at all\./);
});

test("moves.py keeps the before's table for the before's manifest (0.8.0's: 4, 6 and 7)", { skip: !existsSync(PYTHON) && "no venv python (uv sync)" }, () => {
  let old;
  try { old = execFileSync("git", ["-C", L.ROOT, "show", "v0.8.0:editors/vscode/package.json"], { encoding: "utf8", stdio: "pipe" }); }
  catch { return; } // no v0.8.0 in this clone
  const file = path.join(mkdtempSync(path.join(tmpdir(), "moves-")), "package.json");
  writeFileSync(file, old);
  const out = moves(file);
  assert.equal(out.status, 0, out.stderr);
  assert.match(out.stdout, /cockpit moves: 17\. The editor \(0\.8\.0\) covers 4 whole and 6 in part; 7 not at all\./);
  // a table that names a command the manifest lacks is another build's: the script refuses it
  const bare = JSON.parse(old);
  bare.version = "0.9.0";
  writeFileSync(file, JSON.stringify(bare));
  const refused = moves(file);
  assert.equal(refused.status, 1);
  assert.match(refused.stderr, /names commands the manifest lacks: .*answer/);
});

test("shell keeps a quoted argument whole, as the driver's `sh` line needs", () => {
  const out = L.shell(process.execPath, `-e "console.log(JSON.stringify(process.argv.slice(1)))" node set top --title "a new title" --note 'two words'`, { encoding: "utf8" });
  assert.deepEqual(JSON.parse(out), ["node", "set", "top", "--title", "a new title", "--note", "two words"]);
});

test("Cursor's project dir for a folder: its path with dashes, under ~/.cursor/projects", () => {
  assert.equal(L.cursorProjectDir("/tmp/shots-cursor-sGsk18/wordkit"), `${process.env.HOME}/.cursor/projects/tmp-shots-cursor-sGsk18-wordkit`);
});

test("a sample's summary: nearest-rank percentiles, the mean rounded", () => {
  assert.deepEqual(summary([582, 515, 194, 537, 147]), { n: 5, min: 147, p50: 515, p90: 582, max: 582, mean: 395 });
  assert.deepEqual(summary([3, 1, 2, 4, 5, 6, 7, 8, 9, 10]), { n: 10, min: 1, p50: 5, p90: 9, max: 10, mean: 6 });
  assert.match(line([1, 2, 3]), /^n 3: p50 2 ms, p90 3, max 3, mean 2, min 1 \(load \d+\.\d\)$/);
});

test("an app the harness launches cannot reach the real Token Factory: no shell profile, a fake key, a local URL", () => {
  const dead = L.safeEnv();
  assert.equal(dead.NEBIUS_API_KEY, "fake-key");
  assert.equal(dead.GRAPHENE_KEYCHAIN, "off");
  assert.match(dead.GRAPHENE_TOKENFACTORY_URL, /^http:\/\/127\.0\.0\.1:/);
  assert.ok(dead.ZDOTDIR && dead.ZDOTDIR !== process.env.HOME, "zsh reads no profile in the app's terminals");
  assert.equal(L.safeEnv("http://127.0.0.1:5000/v1").GRAPHENE_TOKENFACTORY_URL, "http://127.0.0.1:5000/v1");
  // launch() puts it in the app's environment after the person's own variables, so it wins over them
  assert.match(L.launch.toString(), /\.\.\.cleanEnv\(\), \.\.\.safeEnv\(standin\)/);
});
