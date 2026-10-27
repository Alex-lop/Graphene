// The take as Alex films it, rehearsed: ENDPOINT=standin PAUSE=1 dev/proof/auto.sh DIR; at the pause, the
// harness's VS Code opens DIR with the night's .vsix in a profile of its own; Enter; then a shot at each beat
// the editor shows, by polling `graphene state --json` in DIR.
//   E2E_TMP=/tmp/gv-take-1 node dev/process/editor/take/rehearse.mjs --clone . --dir /tmp/gv-take-1/wordkit --out shots [--app code|cursor]
// It needs the clone's .venv (uv sync), a .vsix in editors/vscode (npm run package) and the harness's npm ci
// in editors/vscode/e2e. DIR must not exist. E2E_TMP keeps VS Code's profile under a short path.
import { execFileSync, spawn } from "node:child_process";
import { mkdirSync, openSync, readFileSync, writeFileSync } from "node:fs";
import path from "node:path";

const arg = (k, d) => { const i = process.argv.indexOf(k); return i > 0 ? process.argv[i + 1] : d; };
const clone = path.resolve(arg("--clone"));
const dir = path.resolve(arg("--dir"));
const out = path.resolve(arg("--out", "shots"));
const appName = arg("--app", "code");
mkdirSync(out, { recursive: true });
const L = await import(path.join(clone, "editors/vscode/e2e/lib.mjs"));

const graphene = path.join(clone, ".venv/bin/graphene");
const env = L.cleanEnv({ PATH: `${path.dirname(graphene)}:${process.env.PATH}`, ENDPOINT: "standin", PAUSE: "1",
                         RECORD: path.join(out, "take.jsonl") });
const logFd = openSync(path.join(out, "take.log"), "w");
const t0 = Date.now();
const stamp = () => `${((Date.now() - t0) / 1000).toFixed(1)}s`;
const log = (...a) => { console.log(stamp(), ...a); };

// 1. the take, paused after init
const take = spawn("bash", [path.join(clone, "dev/proof/auto.sh"), dir], { env, stdio: ["pipe", "pipe", logFd] });
let said = "";
take.stdout.on("data", (d) => { said += d; writeFileSync(logFd, d); });
while (!said.includes("then press Enter")) {
  if (take.exitCode !== null) throw new Error(`the take ended early:\n${said}`);
  await new Promise((r) => setTimeout(r, 100));
}
log("paused after init");

// 2. VS Code on DIR, the sidebar and the graph panel
const app = await L.findApp(appName);
const profile = L.makeProfile(L.scratch(`take-${appName}-`), { graphene });
L.installVsix(app, profile, L.findVsix());
const session = await L.launch(app, profile, dir, { width: 1920, height: 1080 });
const page = session.page;
await L.openSidebar(page);
await L.openPanel(page);
await page.waitForTimeout(1500);
await L.shot(page, path.join(out, "beat6-editor-paused-after-init.png"));
log("VS Code open on the folder");

// 3. Enter
take.stdin.write("\n");
take.stdin.end();

const state = () => JSON.parse(execFileSync(graphene, ["state", "--json"], { cwd: dir, env: L.cleanEnv(), encoding: "utf8" }));
const beats = [
  ["beat2-aha-race-fans-out", (s) => s.tasks.some((t) => t.forks.filter((f) => f.state === "running").length >= 2)],
  ["beat3-check-a-fork-kept", (s) => s.tasks.some((t) => t.state === "done" && t.kept && Object.keys(t.kept).length)],
  ["beat3-check-goal-red", (s) => (s.auto?.check && s.auto.check !== "passed") || s.auto?.stage === "fixing" || s.tasks.some((t) => t.id === "count-test")],
  ["beat3-check-the-fix-races", (s) => s.tasks.some((t) => t.id === "count-test" && t.forks.some((f) => f.state === "running"))],
  ["beat3-check-the-fix-lands", (s) => s.tasks.some((t) => t.id === "count-test" && t.state === "done")],
];
const seen = new Set();
let explorerShot = false;
const notes = [];
while (take.exitCode === null || seen.size < beats.length) {
  let s;
  try { s = state(); } catch { await new Promise((r) => setTimeout(r, 300)); continue; }
  for (const [name, when] of beats) {
    if (seen.has(name) || !when(s)) continue;
    seen.add(name);
    await page.waitForTimeout(700); // the stream's write to the screen
    await L.shot(page, path.join(out, `${name}.png`));
    notes.push(`${stamp()} ${name}: auto ${JSON.stringify(s.auto)}; tasks ${s.tasks.map((t) => `${t.id}:${t.state}[${t.forks.map((f) => f.state[0]).join("")}]`).join(" ")}`);
    log(name);
    if (name === "beat2-aha-race-fans-out" && !explorerShot) {
      explorerShot = true;
      await L.palette(page, "View: Show Explorer");
      await page.waitForTimeout(1200);
      for (const name of ["wordkit", "tests"]) { // the folders open, so each file's owner shows
        const row = page.locator(".explorer-folders-view .monaco-list-row .label-name", { hasText: new RegExp(`^${name}$`) }).first();
        const n = await row.count();
        notes.push(`explorer row ${name}: ${n}`);
        if (n) { await row.click({ timeout: 3000 }).catch((e) => notes.push(`click ${name}: ${e.message.split("\n")[0]}`)); await page.waitForTimeout(600); }
      }
      await page.waitForTimeout(1200);
      await L.shot(page, path.join(out, "beat6-editor-explorer-owners.png"));
      await L.palette(page, "View: Show Graphene");
      await page.waitForTimeout(500);
    }
  }
  if (take.exitCode !== null && seen.size < beats.length) { notes.push(`the take ended with ${[...beats.map((b) => b[0])].filter((n) => !seen.has(n))} unseen`); break; }
  await new Promise((r) => setTimeout(r, 300));
}
await new Promise((r) => take.exitCode !== null ? r() : take.on("exit", r));
await page.waitForTimeout(1500);
await L.shot(page, path.join(out, "beat4-real-the-end.png"));
notes.push(`${stamp()} the take exited ${take.exitCode}`);
// the side bar alone, at 1280x800, as a judge's laptop shows it
await L.setSize(session.electronApp, page, 1280, 800);
await page.waitForTimeout(800);
await L.shot(page, path.join(out, "beat6-editor-1280-the-end.png"));
writeFileSync(path.join(out, "beats.txt"), notes.join("\n") + "\n");
console.log(notes.join("\n"));
await session.electronApp.close().catch(() => {});
process.exit(take.exitCode ?? 1);
