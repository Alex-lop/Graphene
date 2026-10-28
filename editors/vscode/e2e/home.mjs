// Home, clicked through in real VS Code against the scripted stand-in ($0): a folder with no plan is set up with one
// click, an ask is planned, Start runs the agents, and each finished task is reviewed: Approve before its changes
// were opened asks first, Open Changes shows them, Approve lands it, Send back… returns another with a note. It
// fails when a step does not show what it should, and keeps a screenshot of each step (E2E_SHOTS, else the scratch).
import { execFileSync } from "node:child_process";
import { existsSync, rmSync } from "node:fs";
import path from "node:path";
import * as L from "./lib.mjs";

const ASK = "wordkit grows three things: a --top N option, a reading time in minutes, and hyphenated words counted as one";

const app = await L.findApp(process.env.E2E_APP || "code");
if (!app) { console.error("home: no app to drive (set VSCODE_EXECUTABLE)"); process.exit(1); }
const vsix = L.findVsix();
const graphene = L.findGraphene();
const base = L.scratch("graphene-home-");
const shots = process.env.E2E_SHOTS ? path.resolve(process.env.E2E_SHOTS) : path.join(base, "shots");
const standin = await L.startStandin();
let session = null, failed = null, step = 0;
const t0 = Date.now();
const say = (what) => console.log(`home: ${((Date.now() - t0) / 1000).toFixed(1)} s  ${what}`);
const shot = async (name) => L.shot(session.page, path.join(shots, `home-${String(++step).padStart(2, "0")}-${name}.png`));

/** The frame that holds Home's page, found by its content. */
async function homeFrame(page, timeout = 60000) {
  const end = Date.now() + timeout;
  while (Date.now() < end) {
    for (const f of page.frames()) {
      const is = await f.evaluate(() => Boolean(document.querySelector("section.screen") && document.querySelector("section.work"))).catch(() => false);
      if (is) return f;
    }
    await page.waitForTimeout(200);
  }
  throw new Error("Home's page never appeared");
}

const until = (frame, fn, arg, what, timeout = 60000) =>
  frame.waitForFunction(fn, arg, { timeout, polling: 200 }).catch(() => { throw new Error(`waited ${timeout / 1000} s for ${what}`); });
const sectionShown = (frame, words, what, timeout) =>
  until(frame, (w) => [...document.querySelectorAll(".sec-head .fold")].some((b) => b.textContent.includes(w)), words, what, timeout);
const state = (dir) => JSON.parse(execFileSync(graphene, ["state", "--json"], { cwd: dir, env: L.cleanEnv(L.safeEnv(standin.url)) }));

try {
  const profile = L.makeProfile(base, { graphene, settings: { "window.dialogStyle": "custom" } }); // a modal the driver can click
  L.installVsix(app, profile, vsix);
  const dir = path.join(base, "wordkit");
  const python = path.join(L.ROOT, ".venv", "bin", "python");
  execFileSync(existsSync(python) ? python : "python3", [path.join(L.ROOT, "dev", "proof", "make_wordkit.py"), dir], { stdio: "pipe" });
  session = await L.launch(app, profile, dir, { width: 1440, height: 900, standin: standin.url });
  const page = session.page;
  await L.openSidebar(page);
  await L.setSidebarWidth(page, 400);
  let home = await homeFrame(page);
  await until(home, () => document.querySelector("section.screen h2")?.textContent === "Set up Graphene in this folder", null, "the Set Up screen");
  say("a folder with no plan opens on Set Up");
  await shot("setup");

  await home.locator("button.pick", { hasText: "Nemotron" }).click();
  await until(home, () => !document.querySelector("section.work").hidden && Boolean(document.querySelector("textarea"))
    && document.querySelector(".said")?.textContent.includes("waits for your approval"), null, "Set Up done, review on"); // init, then config set
  const set = state(dir);
  if (set.envelope.review !== "every") throw new Error(`Set Up left review ${set.envelope.review}, not every`);
  say("one click set it up: Nemotron plans and works, and review is every");
  await shot("ask");

  home = await homeFrame(page);
  await home.locator("textarea").fill(ASK);
  await home.locator("button", { hasText: "Plan it" }).click();
  await sectionShown(home, "Suggested plan", "the suggested plan");
  const suggested = await home.locator("article.tone-proposed").count();
  if (suggested < 1) throw new Error("no suggested task");
  say(`Plan it: ${suggested} suggested tasks, each with what it may change and what proves it`);
  await shot("suggested");

  await home.locator(".sec-suggested .sec-head button", { hasText: "Start" }).click();
  await until(home, () => document.querySelectorAll("article.tone-review").length >= 1, null, "a task to review", 120000);
  await page.waitForTimeout(3000); // the others land in review too
  const reviews = await home.locator("article.tone-review").count();
  say(`Start: the agents ran; ${reviews} tasks wait for review`);
  await shot("review");

  const first = home.locator("article.tone-review").first();
  const title = await first.locator(".c-title").textContent();
  await first.locator("button", { hasText: "Approve" }).click();
  const dialog = page.locator(".monaco-dialog-box");
  await dialog.waitFor({ timeout: 10000 }).catch(() => { throw new Error("Approve before opening the changes asked nothing"); });
  if (!(await dialog.textContent()).includes("You have not opened the changes")) throw new Error(`the dialog said: ${await dialog.textContent()}`);
  say("Approve before opening the changes asks first");
  await shot("approve-asks");
  await dialog.locator(".monaco-button", { hasText: "Open Changes" }).click();
  await page.waitForSelector(".monaco-diff-editor, .multiDiffEditor, .multi-diff-editor", { timeout: 20000 })
    .catch(() => { throw new Error("Open Changes opened no diff"); });
  await page.waitForTimeout(1200);
  say("Open Changes shows the task's diff in VS Code's diff editor");
  await shot("changes");

  const card = home.locator("article.tone-review", { has: home.locator(".c-title", { hasText: title }) });
  await until(home, (t) => [...document.querySelectorAll("article.tone-review")].some((c) => c.querySelector(".c-title")?.textContent === t
    && c.textContent.includes("You opened these changes.")), title, "the card to say its changes were opened");
  await card.locator("button", { hasText: "Approve" }).click();
  await sectionShown(home, "Done · 1", "the approved task under Done");
  say(`Approve landed “${title}”`);

  const next = home.locator("article.tone-review").first();
  const back = await next.locator(".c-title").textContent();
  await next.locator("button", { hasText: "Send back…" }).click();
  const box = page.locator(".quick-input-widget input");
  await box.waitFor({ timeout: 10000 });
  await box.fill("the test only covers one case");
  await page.keyboard.press("Enter");
  await sectionShown(home, "Up next", "the task sent back, up next");
  say(`Send back returned “${back}” with a note`);
  await shot("after-review");

  const end = state(dir);
  const by = Object.fromEntries(end.tasks.map((t) => [t.title, t.state]));
  if (by[title] !== "done") throw new Error(`“${title}” is ${by[title]}, not done`);
  if (!["ready", "waiting"].includes(by[back])) throw new Error(`“${back}” is ${by[back]}, not back on the plan`);
  console.log(`home: passed in ${((Date.now() - t0) / 1000).toFixed(0)} s, ${step} screenshots in ${shots}`);
} catch (err) {
  failed = err;
  if (session) await L.shot(session.page, path.join(shots, "failed.png")).catch(() => {});
} finally {
  if (session) await L.close(session);
  standin.stop();
  if (failed) {
    console.error("home: failed:", failed.message, `(kept at ${base})`);
    process.exit(1);
  }
  if (!process.env.E2E_SHOTS) console.log(`home: screenshots kept at ${shots}`);
  else rmSync(base, { recursive: true, force: true });
}
