// `npm test`: the extension, installed from its .vsix in a profile of its own, draws a fixture's tasks in the
// graph's tab and in the side bar's Graph view of real VS Code. The profile leaves graphene.graph.openOnStart at
// its default, so the tab is not asked for: the window opens on a plan with work left and the tab opens by itself,
// without taking the keyboard. It fails when the tab does not open, takes the keyboard, or a graph lacks a task.
// Then the tab is closed and a plan appears: it must stay closed. Then, in a second window, where the tab was never
// closed, a file is in front with the caret in it when a plan appears: the tab must open beside the file, not over it.
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
/** In the window's own page: whether the keyboard is in a text editor of the editor area (a file's). */
const inFile = () => Boolean(document.activeElement?.closest(".part.editor .monaco-editor"));

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
  let page = session.page;
  // No command is run and nothing is clicked: the plan has work left, so the graph's tab opens by itself. The side
  // bar is still the Explorer's (a fresh profile), so the only graph there can be is the tab's.
  const own = await L.waitForGraph(page, { min: TASKS.length, timeout: 60000 })
    .catch(() => { throw new Error("no graph drew by itself: the window opened on a plan with work left, and the tab did not open"); });
  const tabs = () => page.locator(".editor-group-container .tab", { hasText: "Graphene" });
  await tabs().first().waitFor({ timeout: 10000 }).catch(() => { throw new Error("a graph drew by itself, but not in a tab of the editor area"); });
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
  if (await tabs().count() !== 1) throw new Error(`${await tabs().count()} Graphene tabs after Show Graph: it reveals the one that is there`);
  // The tab is closed, and a start nobody clicked for follows: the plan is emptied, and a task joins it from outside
  // the window, as an agent's proposal does. A tab a person closed stays closed in that window: the side bar's
  // graph draws the task, and no tab opens.
  const cli = (argv, at = fx) => execFileSync(graphene, argv, { cwd: at.dir, env: at.env, stdio: "pipe" });
  const joins = ["node", "add", "a count of sentences", "--id", "sentences", "--scope", "wordkit/sentences.py", "--check", "true"];
  cli(["node", "drop", ...TASKS.map(([id]) => id)]);
  for (const t0 = Date.now(); shown.tasks.length; await page.waitForTimeout(100)) { // the window has read the empty plan
    if (Date.now() - t0 > 60000) throw new Error(`every task was dropped, and the side bar's graph still draws ${JSON.stringify(shown.tasks)}`);
    shown = await L.readGraph(side).catch(() => shown);
  }
  await L.palette(page, "View: Close All Editors");
  await tabs().first().waitFor({ state: "detached", timeout: 10000 }).catch(() => { throw new Error("Close All Editors left the graph's tab open"); });
  cli(joins);
  for (const t0 = Date.now(); !shown.tasks.length; await page.waitForTimeout(100)) { // the window has read the plan that appeared
    if (Date.now() - t0 > 60000) throw new Error("a task joined the plan, and the side bar's graph does not draw it");
    shown = await L.readGraph(side).catch(() => shown);
  }
  await page.waitForTimeout(2000); // the read that drew the task is the one that would have opened the tab
  if (await tabs().count()) throw new Error("the tab was closed, a plan appeared, and the tab opened by itself again: closed, it stays closed in that window");
  // A file in front with the caret in it, and a start nobody clicked for, in a window where the tab was never
  // closed: a second one, on a folder whose plan is empty. A file is opened, and the task joins that plan. In the
  // file's group the tab would hide the file and VS Code would leave the keyboard in nothing: it must open beside it.
  await L.close(session);
  const fx2 = L.makeFixture(path.join(base, "wordkit-beside"), graphene);
  session = await L.launch(app, profile, fx2.dir, { width: 1280, height: 800 });
  page = session.page;
  await L.palette(page, "File: New Untitled Text File");
  await page.locator(".editor-group-container .tab", { hasText: "Untitled-1" }).waitFor({ timeout: 10000 })
    .catch(() => { throw new Error("no untitled file opened to stand in front"); });
  // whether the caret was seen in the file before the start: said, not required, as the keyboard in the tab is above
  const typing = await page.waitForFunction(inFile, null, { timeout: 5000 }).then(() => true, () => false);
  cli(joins, fx2);
  await L.waitForGraph(page, { timeout: 60000 }) // nothing of Graphene's was opened in this window: the graph that draws is the tab's
    .catch(() => { throw new Error("a plan appeared with a file in front, and no graph's tab opened by itself"); });
  await tabs().first().waitFor({ timeout: 10000 }).catch(() => { throw new Error("a graph drew by itself beside a file, but not in a tab of the editor area"); });
  const group = (label) => page.locator(".editor-group-container", { has: page.locator(".tab", { hasText: label }) });
  if (await group("Graphene").filter({ has: page.locator(".tab", { hasText: "Untitled-1" }) }).count()) throw new Error("the tab opened by itself in the group of the file in front: over the file, not beside it");
  if (await group("Untitled-1").count() !== 1) throw new Error("the file that was in front is gone from the editor area");
  if (await page.evaluate(inTab)) throw new Error("the tab that opened by itself beside a file took the keyboard");
  if (typing && !(await page.evaluate(inFile))) throw new Error("the tab that opened by itself took the keyboard out of the file it was in");
  if (process.env.E2E_SHOT) await L.shot(page, process.env.E2E_SHOT);
  console.log(`e2e: ${app.name} opened the graph's tab by itself on a plan with work left, the keyboard not in it, and drew ${TASKS.length} tasks in it and in the side bar; `
    + `Show Graph revealed the same tab${took ? " and gave it the keyboard" : ", and the keyboard was not seen in it (so the check that it was left alone proved nothing)"}; `
    + `closed, the tab stayed closed when a plan appeared; in a second window with a file in front, a plan that appeared opened the tab beside the file${typing ? " and the keyboard stayed in the file" : ", and the keyboard was not seen in the file before it (so where it stayed is not known)"}`);
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
