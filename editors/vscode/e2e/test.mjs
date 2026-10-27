// `npm test`: the extension, installed from its .vsix in a profile of its own, draws a fixture's tasks in the
// side bar's Graph view and in the graph panel of real VS Code. It fails when the graph does not render them.
// VSCODE_EXECUTABLE names the app (CI: a build @vscode/test-electron downloads, under xvfb); VSIX the package.
import { execFileSync } from "node:child_process";
import { existsSync, rmSync } from "node:fs";
import path from "node:path";
import * as L from "./lib.mjs";

const TASKS = [["top", "the CLI prints the top words"], ["reading", "a reading time in minutes"], ["hyphens", "hyphenated words stay whole"]];

const app = await L.findApp(process.env.E2E_APP || "code");
if (!app) { console.error("e2e: no app to drive (set VSCODE_EXECUTABLE)"); process.exit(1); }
const vsix = L.findVsix();
const graphene = L.findGraphene();
const base = L.scratch();
let session = null, failed = null;
try {
  const profile = L.makeProfile(base, { graphene });
  L.installVsix(app, profile, vsix);
  const fx = L.makeFixture(path.join(base, "wordkit"), graphene);
  for (const [id, title] of TASKS) {
    execFileSync(graphene, ["node", "add", title, "--id", id, "--scope", `wordkit/${id}.py`, "--check", "true"], { cwd: fx.dir, env: fx.env, stdio: "pipe" });
  }
  session = await L.launch(app, profile, fx.dir, { width: 1280, height: 800 });
  if (session.size.width !== 1280 || session.size.height !== 800) throw new Error(`the window took ${JSON.stringify(session.size)}, not 1280x800`);
  const inner = async () => session.page.evaluate(() => [window.innerWidth, window.innerHeight]);
  // setSize says what the window took: a size that fits every display, so it is the one asked for
  const got = await L.setSize(session.electronApp, session.page, 1200, 700);
  if (JSON.stringify(await inner()) !== JSON.stringify([got.width, got.height]) || got.width !== 1200) throw new Error(`setSize said ${JSON.stringify(got)}, the window is ${await inner()}`);
  await L.setSize(session.electronApp, session.page, 1280, 800);
  await L.openSidebar(session.page);
  const side = await L.waitForGraph(session.page, { min: TASKS.length, timeout: 60000 });
  const shown = await L.readGraph(side.frame);
  for (const [id] of TASKS) {
    if (!shown.tasks.some((t) => t.id === id)) throw new Error(`the side bar's graph lacks ${id}: ${JSON.stringify(shown)}`);
  }
  if (!shown.counts.includes(`0 of ${TASKS.length} done`)) throw new Error(`the counts read ${shown.counts}`);
  await L.openPanel(session.page);
  const frames = await L.graphFrames(session.page);
  if (frames.length < 2) throw new Error(`${frames.length} graph frame(s): the panel did not open`);
  let drawn = 0;
  for (const f of frames) drawn = Math.max(drawn, (await L.readGraph(f)).tasks.length);
  if (drawn < TASKS.length) throw new Error(`the panel drew ${drawn} tasks`);
  if (process.env.E2E_SHOT) await L.shot(session.page, process.env.E2E_SHOT);
  console.log(`e2e: ${app.name} drew ${TASKS.length} tasks in the side bar (${side.ms} ms after it opened) and in the panel`);
} catch (err) {
  failed = err;
  if (session) await L.shot(session.page, path.join(base, "failed.png")).catch(() => {});
} finally {
  if (session) await L.close(session);
  if (session && app.name === "cursor" && existsSync(L.cursorProjectDir(session.folder))) failed ??= new Error(`Cursor's ${L.cursorProjectDir(session.folder)} is still there`);
  if (failed) {
    console.error("e2e: failed", failed.message, `(profile kept at ${base})`);
    process.exit(1);
  }
  rmSync(base, { recursive: true, force: true });
}
