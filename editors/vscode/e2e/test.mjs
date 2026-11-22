// `npm test`: the extension, installed from its .vsix in a profile of its own, draws a fixture's tasks in the
// graph's tab and in the side bar's Graph view of real VS Code. The profile leaves graphene.graph.openOnStart at
// its default, so the tab is not asked for: the window opens on a plan with work left and the tab opens by itself,
// without taking the keyboard. It fails when the tab does not open, takes the keyboard, or a graph lacks a task.
// VSCODE_EXECUTABLE names the app (CI: a build @vscode/test-electron downloads, under xvfb); VSIX the package.
import { execFileSync } from "node:child_process";
import { existsSync, rmSync } from "node:fs";
import path from "node:path";
import * as L from "./lib.mjs";

const TASKS = [["top", "the CLI prints the top words"], ["reading", "a reading time in minutes"], ["hyphens", "hyphenated words stay whole"]];

/** In the window's own page: whether the keyboard is in a webview laid over the editor area. A focused webview is
 *  the window's active element, its iframe (VS Code's own test of it), and the tab's lies over the editor part;
 *  the side bar's views lie over the side bar. */
const inTab = () => {
  const a = document.activeElement, part = document.querySelector(".part.editor")?.getBoundingClientRect();
  if (!a || a.tagName !== "IFRAME" || !part) return false;
  const r = a.getBoundingClientRect(), x = r.left + r.width / 2, y = r.top + r.height / 2;
  return x > part.left && x < part.right && y > part.top && y < part.bottom;
};

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
  const page = session.page;
  // No command is run and nothing is clicked: the plan has work left, so the graph's tab opens by itself. The side
  // bar is still the Explorer's (a fresh profile), so the only graph there can be is the tab's.
  const own = await L.waitForGraph(page, { min: TASKS.length, timeout: 60000 })
    .catch(() => { throw new Error("no graph drew by itself: the window opened on a plan with work left, and the tab did not open"); });
  const tabs = page.locator(".editor-group-container .tab", { hasText: "Graphene" });
  await tabs.first().waitFor({ timeout: 10000 }).catch(() => { throw new Error("a graph drew by itself, but not in a tab of the editor area"); });
  if (await page.evaluate(inTab)) throw new Error("the tab that opened by itself took the keyboard");
  await L.openSidebar(page);
  let side, shown = { tasks: [], counts: "" };
  for (const t0 = Date.now(); shown.tasks.length < TASKS.length; await page.waitForTimeout(100)) { // the side bar's own frame, drawn
    if (Date.now() - t0 > 60000) throw new Error(`the side bar's graph drew ${shown.tasks.length} of ${TASKS.length} tasks: ${JSON.stringify(shown)}`);
    side = (await L.graphFrames(page)).find((f) => f !== own.frame);
    if (side) shown = await L.readGraph(side).catch(() => shown);
  }
  for (const [id] of TASKS) {
    if (!shown.tasks.some((t) => t.id === id)) throw new Error(`the side bar's graph lacks ${id}: ${JSON.stringify(shown)}`);
  }
  if (!shown.counts.includes(`0 of ${TASKS.length} done`)) throw new Error(`the counts read ${shown.counts}`);
  const inOwn = await L.readGraph(own.frame);
  for (const [id] of TASKS) {
    if (!inOwn.tasks.some((t) => t.id === id)) throw new Error(`the tab's graph lacks ${id}: ${JSON.stringify(inOwn)}`);
  }
  // Show Graph, asked for, reveals that tab: there is still one, and it may take the keyboard now. Whether it did
  // is said, not required: it is what shows the check above can tell a tab that took the keyboard from one that did not.
  await L.palette(page, "Graphene: Show Graph");
  const took = await page.waitForFunction(inTab, null, { timeout: 5000 }).then(() => true, () => false);
  if (await tabs.count() !== 1) throw new Error(`${await tabs.count()} Graphene tabs after Show Graph: it reveals the one that is there`);
  if (process.env.E2E_SHOT) await L.shot(page, process.env.E2E_SHOT);
  console.log(`e2e: ${app.name} opened the graph's tab by itself on a plan with work left, the keyboard left where it was, and drew ${TASKS.length} tasks in it and in the side bar; `
    + `Show Graph revealed the same tab${took ? " and gave it the keyboard" : ", and the keyboard was not seen in it (so the check that it was left alone proved nothing)"}`);
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
