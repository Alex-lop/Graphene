// The graph, built by hand in real VS Code, with no planner and no model ($0): on an empty plan a task is drawn,
// its title typed on its box and its files and check in the pane, and it joins the plan (`graphene node add`); a
// second is drawn after it from the + on its box, with your approval for a check; attempts are set on the stepper
// and the fan is drawn before anything runs; the form changes a title, takes a task for yourself and gives it
// back; graphene's refusal shows in the pane; and a task an agent holds says what an edit does now, and takes it.
// It fails when a step does not show what it should, and keeps a screenshot of each (E2E_SHOTS, else the scratch).
import { execFileSync } from "node:child_process";
import { rmSync } from "node:fs";
import path from "node:path";
import * as L from "./lib.mjs";

const app = await L.findApp(process.env.E2E_APP || "code");
if (!app) { console.error("draw: no app to drive (set VSCODE_EXECUTABLE)"); process.exit(1); }
const vsix = L.findVsix();
const graphene = L.findGraphene();
const base = L.scratch("graphene-draw-");
const shots = process.env.E2E_SHOTS ? path.resolve(process.env.E2E_SHOTS) : path.join(base, "shots");
let session = null, failed = null, step = 0;
const t0 = Date.now();
const say = (what) => console.log(`draw: ${((Date.now() - t0) / 1000).toFixed(1)} s  ${what}`);
const shot = async (name) => L.shot(session.page, path.join(shots, `draw-${String(++step).padStart(2, "0")}-${name}.png`));
const until = (frame, fn, arg, what, timeout = 30000) =>
  frame.waitForFunction(fn, arg, { timeout, polling: 100 }).catch(() => { throw new Error(`waited ${timeout / 1000} s for ${what}`); });

try {
  const profile = L.makeProfile(base, { graphene });
  L.installVsix(app, profile, vsix);
  const fx = L.makeFixture(path.join(base, "wordkit"), graphene);
  const cli = (argv, env = fx.env) => execFileSync(graphene, argv, { cwd: fx.dir, env, stdio: "pipe" }).toString();
  const plan = () => Object.fromEntries(JSON.parse(cli(["plan", "--json"])).nodes.map((n) => [n.title, n]));
  session = await L.launch(app, profile, fx.dir, { width: 1440, height: 900, video: process.env.E2E_VIDEO });
  const page = session.page;
  await L.openPanel(page);
  let g = (await L.graphFrames(page))[0];
  const focused = (id) => until(g, (i) => document.activeElement?.id === i, id, `the focus in ${id}`);
  const typeIn = async (id, text) => { await focused(id); await g.locator(`#${id}`).fill(text); await g.locator(`#${id}`).press("Enter"); };
  const box = (id) => g.locator(`#view g.task[data-id="${id}"]`); // by its id: a title is cut to its box, more where the font is wider
  const drawnAs = (title) => until(g, (t) => [...document.querySelectorAll("#view g.task:not(.draft) text.title")].some((x) => x.textContent === t)
    && !document.querySelector("#view g.task.draft"), title, `“${title}” in the plan`);

  // 1. an empty plan: draw the first task, typing nothing but its words
  await g.locator("#notice button", { hasText: "Add task" }).waitFor({ timeout: 20000 });
  await shot("empty");
  await g.locator("#notice button", { hasText: "Add task" }).click();
  let name = g.locator("#view g.task.draft input.name");
  await name.waitFor({ timeout: 10000 }).catch(() => { throw new Error("Add task drew no draft box to type in"); });
  await name.fill("print the top words");
  await shot("title");
  await name.press("Enter");
  await until(g, () => document.querySelector("#view g.task.draft text.sub")?.textContent === "files ___ · check ___", null, "the draft's blanks on its box");
  say("Add task on an empty plan drew a draft box; its title was typed on it, and its blanks show");
  await shot("draft");
  await typeIn("f-files", "wordkit/cli.py tests/test_top.py");
  await until(g, () => document.querySelector("#view g.task.draft text.sub")?.textContent === "2 files · check ___", null, "the files on the draft's box");
  await shot("files");
  // A draft belongs to the workspace: a second graph, a closed panel and a reloaded window retain it.
  await g.locator("#f-check").press("Escape");
  const graphIcon = page.locator('.activitybar .action-label[aria-label^="Graphene"]').first();
  if (await graphIcon.isVisible().catch(() => false)) await graphIcon.click();
  else await L.openSidebar(page);
  for (let i = 0; i < 100 && (await L.graphFrames(page)).length < 2; i++) await page.waitForTimeout(100);
  const side = (await L.graphFrames(page)).find((f) => f !== g);
  if (!side) throw new Error("no second graph for the shared draft");
  await until(side, () => document.querySelectorAll(".draft").length > 0, null, "the same draft in the sidebar");
  say("the sidebar has the shared draft");
  const graphTab = page.locator(".editor-group-container .tab.active");
  await graphTab.hover();
  await graphTab.getByRole("button", { name: /^Close/ }).click();
  await graphTab.waitFor({ state: "detached" });
  say("closed the graph tab");
  await L.openPanel(page);
  g = (await L.graphFrames(page)).find((f) => f !== side);
  await until(g, () => document.querySelector("g.task.draft text.title")?.textContent === "print the top words", null, "the draft after closing its panel");
  say("the reopened tab retained the draft");
  await L.palette(page, "Developer: Reload Window");
  await page.waitForTimeout(4000);
  if (app.name === "cursor") await L.cursorClassic(page, profile);
  await L.openPanel(page);
  await L.setSize(session.electronApp, page, 1440, 900);
  let widest = -1;
  for (const f of await L.graphFrames(page)) {
    const width = await f.locator("#canvas").evaluate((el) => el.clientWidth).catch(() => -1);
    if (width > widest) { widest = width; g = f; }
  }
  await until(g, () => document.querySelector("g.task.draft text.title")?.textContent === "print the top words", null, "the draft after a window reload");
  await g.locator("g.task.draft rect.box").click();
  await until(g, () => document.querySelector("#f-files")?.value === "wordkit/cli.py tests/test_top.py", null, "the draft's retained files");
  if (Object.keys(plan()).length !== 0) throw new Error("an incomplete draft entered the plan");
  say("the draft and its files survived a second graph, closing the panel and reloading the window");
  name = g.locator("#view g.task.draft input.name");
  await g.locator("#f-check").focus();
  await typeIn("f-check", "python3 -m unittest -q");
  await drawnAs("print the top words");
  const first = plan()["print the top words"];
  if (!first || first.check !== "python3 -m unittest -q" || first.scope.join(" ") !== "wordkit/cli.py tests/test_top.py" || first.state !== "open") {
    throw new Error(`the plan has ${JSON.stringify(first)}`);
  }
  say(`files and a check filled in: it joined the plan as ${first.id}, with no planner`);
  await shot("joined");

  // 2. the + on its box: a second task after it, your approval in place of a check
  await box(first.id).locator("rect.box").hover();
  await box(first.id).locator(".plus circle").click();
  await name.waitFor({ timeout: 10000 }).catch(() => { throw new Error("the + drew no draft box"); });
  await name.fill("say it in the README");
  await shot("plus");
  await name.press("Enter");
  await typeIn("f-files", "README.md");
  await focused("f-check");
  await g.locator("#f-signoff").check();
  await drawnAs("say it in the README");
  const second = plan()["say it in the README"];
  if (!second || !second.signoff || second.check || second.needs.join() !== first.id) throw new Error(`the plan has ${JSON.stringify(second)}`);
  say(`the + drew ${second.id} after ${first.id}; “wait for my approval” stood in for a check`);
  await shot("second");

  // 3. attempts on one task: the stepper, and the fan before anything runs
  await box(first.id).locator("rect.box").click();
  await until(g, () => document.querySelector("#details .d-id")?.textContent.includes("ready"), null, "the first task's pane");
  for (let i = 0; i < 2; i++) {
    await g.locator('#details button[aria-label="one more attempt"]').click();
    await until(g, (n) => document.querySelector("#details .count")?.textContent === String(n), i + 2, `${i + 2} attempts on the stepper`);
  }
  const fan = await box(first.id).locator("g.fork.planned").count();
  if (fan !== 3 || plan()["print the top words"].forks !== 3) throw new Error(`the fan has ${fan} chips; the plan says ${plan()["print the top words"].forks}`);
  say("the stepper set 3 attempts on that task alone, and the fan is drawn before anything runs");
  await shot("attempts");

  // 4. the form: a new title, typed in place; the task taken for yourself, and given back
  await g.locator("#f-title").fill("print the N most common words");
  await g.locator("#f-title").press("Enter");
  await until(g, () => [...document.querySelectorAll("#view text.title")].some((x) => x.textContent.startsWith("print the N most")), null, "the new title on the box");
  await g.locator("#f-files").press("Escape");
  await g.locator("#f-owner").check();
  await until(g, () => document.querySelector("#details .d-id")?.textContent.includes("yours") && document.querySelector("#f-owner")?.checked, null, "the task as yours, its box ticked");
  await g.locator("#f-owner").uncheck();
  await until(g, () => document.querySelector("#details .d-id")?.textContent.includes("ready"), null, "the task back with an agent");
  say("the form changed its title in place, took it for you and gave it back to an agent");

  // 5. graphene's refusal, in the pane: the second task may not write the first one's file
  await box(second.id).locator("rect.box").click();
  await until(g, () => document.querySelector("#details .d-id")?.textContent.includes("waiting"), null, "the second task's pane");
  await g.locator("#f-files").fill("wordkit/cli.py");
  await g.locator("#f-files").press("Enter");
  await until(g, () => Boolean(document.querySelector("#details .refused")?.textContent.trim()), null, "graphene's refusal in the pane");
  const refusal = await g.locator("#details .refused").first().textContent();
  if (plan()["say it in the README"].scope.join() !== "README.md") throw new Error("a refused change changed the plan");
  say(`a change graphene refuses is said in the pane, and the plan stands: “${refusal.trim().split("\n")[0]}”`);
  if (await page.locator(".notification-toast").filter({ hasText: refusal.trim().split("\n")[0] }).count()) {
    throw new Error("the inline refusal was duplicated in a notification");
  }
  await shot("refused");
  await g.locator("#f-check").press("Escape");

  // 6. while an agent holds a task: the pane says what an edit does now, and graphene takes it
  cli(["node", "start", first.id], { ...fx.env, CLAUDECODE: "1", CLAUDE_CODE_SESSION_ID: "e2e-draw-agent" });
  await box(first.id).locator("rect.box").click();
  await until(g, () => document.querySelector("#details .when")?.textContent.startsWith("Working now"), null, "the working task's line");
  await g.locator("#f-files").fill("wordkit/cli.py tests/test_top.py wordkit/count.py");
  await g.locator("#f-files").press("Enter");
  await until(g, () => document.querySelector("#f-files")?.value.includes("count.py") && document.activeElement?.id === "f-check", null, "the next box");
  await g.locator("#f-check").press("Escape");
  let held = plan()["print the N most common words"];
  for (let i = 0; i < 50 && !held.scope.includes("wordkit/count.py"); i++) { // the click's `node set` is a process of its own
    await page.waitForTimeout(100);
    held = plan()["print the N most common words"];
  }
  if (held.state !== "running" || !held.scope.includes("wordkit/count.py")) {
    throw new Error(`the held task is ${JSON.stringify([held.state, held.scope])}; the pane said: ${await g.locator("#details .refused").allTextContents()}`);
  }
  say("a task an agent holds says “Working now: new files hold its agent's next write…”, and the change is taken");
  await shot("working");
  console.log(`draw: passed in ${((Date.now() - t0) / 1000).toFixed(0)} s, ${step} screenshots in ${shots}`);
} catch (err) {
  failed = err;
  if (session) await L.shot(session.page, path.join(shots, "failed.png")).catch(() => {});
} finally {
  if (session) await L.close(session);
  if (failed) {
    console.error("draw: failed:", failed.stack, `(kept at ${base})`);
    process.exit(1);
  }
  if (!process.env.E2E_SHOTS) console.log(`draw: screenshots kept at ${shots}`);
  else rmSync(base, { recursive: true, force: true });
}
