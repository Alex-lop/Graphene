// Home, clicked through in real VS Code against the scripted stand-in ($0): a folder with no plan is set up with one
// click (then pointed at the stand-in from the shell), a plan arrives as an agent's does (graphene on the shell: Home takes no ask), Start runs the agents, and each finished task is reviewed: Approve before its changes
// were opened asks first, Open Changes shows them, Approve lands it, Send back… returns another with a note. It
// fails when a step does not show what it should, and keeps a screenshot of each step (E2E_SHOTS, else the scratch).
// Then the Exact switch: on, it sets board on, review every and auto off, and Start waits while a question is open.
// Then the other position of Stop after the plan, on a folder of its own: off is auto, so a goal given to
// `graphene auto` is drawn and run with no Start. Home's three stages are read at each end.
// Last, a workflow, on a third folder: Home lists workflows/fix-issue.md, Run asks for its inputs and proposes its
// four steps with no planner call, Start runs the two agent steps and the suite's command, and the run stops at
// the line: the pull request step is drawn past it and asks first. Nothing is pushed. Save as workflow, in the
// graph's header, then writes the plan back as a second workflow.
import { execFileSync } from "node:child_process";
import { cpSync, existsSync, mkdirSync, readFileSync, rmSync } from "node:fs";
import path from "node:path";
import * as L from "./lib.mjs";

const ASK = "wordkit grows three things: a --top N option, a reading time in minutes, and hyphenated words counted as one";

const ASKS = `question: how many words does --top print with no number?  [q-top-n]
    default: ten
    option: five
- say what --top prints in the README  [top-docs]
    scope: docs/TOP.md
    check: python3 -m unittest -q
`;

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

const until = (frame, fn, arg, what, timeout = 60000) =>
  frame.waitForFunction(fn, arg, { timeout, polling: 200 }).catch(() => { throw new Error(`waited ${timeout / 1000} s for ${what}`); });
const sectionShown = (frame, words, what, timeout) =>
  until(frame, (w) => [...document.querySelectorAll(".sec-head .fold")].some((b) => b.textContent.includes(w)), words, what, timeout);
const state = (dir) => JSON.parse(execFileSync(graphene, ["state", "--json"], { cwd: dir, env: L.cleanEnv(L.safeEnv(standin.url)) }));

try {
  // a modal the driver can click; and the graph's tab only when the walk opens it (its last part counts on that)
  const profile = L.makeProfile(base, { graphene, settings: { "window.dialogStyle": "custom", ...L.ASKED_ONLY } });
  L.installVsix(app, profile, vsix);
  const dir = path.join(base, "wordkit");
  const python = path.join(L.ROOT, ".venv", "bin", "python");
  execFileSync(existsSync(python) ? python : "python3", [path.join(L.ROOT, "dev", "proof", "make_wordkit.py"), dir], { stdio: "pipe" });
  session = await L.launch(app, profile, dir, { width: 1440, height: 900, standin: standin.url });
  const page = session.page;
  await L.openSidebar(page);
  await L.setSidebarWidth(page, 400);
  let home = await L.homeFrame(page);
  await until(home, () => document.querySelector("section.screen h2")?.textContent === "Set up Graphene in this folder", null, "the Set Up screen");
  say("a folder with no plan opens on Set Up");
  await shot("setup");

  await home.locator("button.pick", { hasText: "Claude Code" }).click();
  await until(home, () => !document.querySelector("section.work").hidden && document.querySelector(".head.empty button.open")
    && document.querySelector(".said")?.textContent.includes("waits for your approval"), null, "Set Up done, review on"); // init, then config set
  if (await home.locator("textarea").count()) throw new Error("Home offers a box to type an ask in: a plan comes from the agent's chat");
  const set = state(dir);
  if (set.envelope.review !== "every") throw new Error(`Set Up left review ${set.envelope.review}, not every`);
  if (set.planner !== "claude" || set.executor !== "claude") throw new Error(`Set Up chose ${set.planner} and ${set.executor}, not claude`);
  say("one click set it up: Claude Code plans and works, and review is every");
  // the walk runs on the scripted stand-in, which answers as the frozen nemotron executor: the CLI still takes it
  execFileSync(graphene, ["init", "--planner", "nemotron", "--executor", "nemotron"], { cwd: dir, env: L.cleanEnv(L.safeEnv(standin.url)), stdio: "pipe" });
  if (state(dir).envelope.review !== "every") throw new Error("pointing the folder at the stand-in lost review: every");
  await shot("ask");

  home = await L.homeFrame(page);
  // the person asks their coding agent, in its chat; the plan reaches Graphene as this does
  execFileSync(graphene, ["ask", "--", ASK], { cwd: dir, env: L.cleanEnv(L.safeEnv(standin.url)), stdio: "pipe", timeout: 120000 });
  await sectionShown(home, "Suggested plan", "the suggested plan");
  const suggested = await home.locator("article.tone-proposed").count();
  if (suggested < 1) throw new Error("no suggested task");
  const stage = () => home.evaluate(() => document.querySelector(".pipe .stage.now")?.textContent ?? "");
  if (!(await stage()).includes("Plan")) throw new Error(`a suggested plan, yet the stage is “${await stage()}”, not Plan`);
  if ((await home.locator("button.switch").getAttribute("aria-checked")) !== "true") throw new Error("Stop after the plan is not on by default");
  say(`an ask from outside: ${suggested} suggested tasks, each with what it may change and what proves it; the stage is Plan, and it stopped there`);
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
  const box = page.locator(".quick-input-widget .quick-input-box input");
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

  // Exact, off until its box is ticked: three settings that exist, and Home's Start waits for your answers
  const env = L.cleanEnv(L.safeEnv(standin.url));
  const settings = () => execFileSync(graphene, ["config"], { cwd: dir, env }).toString().split("\n");
  const exact = home.locator(".tick.exact input");
  if (await exact.isChecked()) throw new Error("Exact is on before anyone turned it on");
  execFileSync(graphene, ["config", "set", "review", "off"], { cwd: dir, env, stdio: "pipe" }); // so that off has something to put back
  await page.waitForTimeout(1000); // the stream brings Home the setting
  await exact.check();
  await until(home, () => document.querySelector(".said")?.textContent.startsWith("Exact: Start waits"), null, "Exact said on");
  for (const line of ["board: on", "review: every", "auto: off"]) if (!settings().includes(line)) throw new Error(`Exact on left no “${line}”`);
  execFileSync(graphene, ["plan", "propose", "-"], { cwd: dir, input: ASKS, stdio: ["pipe", "pipe", "pipe"], // a plan that asks something, as an agent proposes one
                                                    env: { ...env, CLAUDECODE: "1", CLAUDE_CODE_SESSION_ID: "e2e-home-agent" } });
  await sectionShown(home, "Suggested plan", "the suggested plan that asks something");
  const start = home.locator(".sec-suggested .sec-head button", { hasText: "Start" });
  if (!(await start.isDisabled())) throw new Error("Exact is on and a question is open, yet Start is offered");
  say("Exact on: board on, review every, auto off; Start waits while the plan's question is open");
  await shot("exact");
  await home.locator("article.tone-question button", { hasText: "ten" }).click(); // the default's button confirms it
  await until(home, () => [...document.querySelectorAll(".sec-suggested .sec-head button")].some((x) => x.textContent === "Start" && !x.disabled), null,
              "Start, once the question is answered");
  await exact.uncheck();
  await until(home, () => document.querySelector(".said")?.textContent.startsWith("Exact is off"), null, "Exact said off");
  for (const line of ["board: auto", "review: off", "auto: off"]) if (!settings().includes(line)) throw new Error(`Exact off left no “${line}”`);
  say("the default's button confirmed it and Start came back; Exact off put the board and review back as they were");

  // Stop after the plan, off: auto. A folder of its own (auto stops on any proposal a plan still holds), set up
  // for the stand-in. Nothing is clicked between the goal and the landed tasks.
  await L.close(session);
  const fx = L.makeFixture(path.join(base, "wordkit-auto"), graphene, { standin: standin.url });
  session = await L.launch(app, profile, fx.dir, { width: 1440, height: 900, standin: standin.url });
  await L.openSidebar(session.page);
  await L.setSidebarWidth(session.page, 400);
  home = await L.homeFrame(session.page);
  const checked = (want) => until(home, (w) => document.querySelector("button.switch")?.getAttribute("aria-checked") === w, want, `the switch ${want}`);
  await checked("true");
  await home.locator("button.switch").click();
  await checked("false");
  await until(home, () => document.querySelector(".said")?.textContent.startsWith("Stop after the plan is off"), null, "the switch said off");
  if (state(fx.dir).envelope.auto !== "on") throw new Error("the switch went off, yet auto is not on");
  await shot("switch-off");
  execFileSync(graphene, ["auto", "--", ASK], { cwd: fx.dir, env: L.cleanEnv(L.safeEnv(standin.url)), stdio: "pipe", timeout: 180000 });
  await sectionShown(home, "Done · 3", "the three tasks landed with no Start", 120000);
  await until(home, () => [...document.querySelectorAll(".pipe .stage small")].at(-1)?.textContent === "done", null, "the Review stage to say done");
  const ran = state(fx.dir);
  if (ran.tasks.length !== 3 || ran.tasks.some((t) => t.state !== "done")) throw new Error(`auto left ${ran.tasks.map((t) => `${t.id} ${t.state}`).join(", ")}`);
  if (await home.locator(".sec-suggested").count()) throw new Error("auto ran, yet a suggested plan still waits for Start");
  say("Stop after the plan off: auto drew the plan and ran it with no Start; 3 tasks landed, and the stage is Review, done");
  await shot("auto-landed");
  await home.locator("button.switch").click();
  await checked("true");
  if (state(fx.dir).envelope.auto !== "off") throw new Error("the switch went back on, yet auto is not off");

  // A workflow: fix-issue, as shipped, run from Home on the stand-in. The stand-in plays its `reading` script for
  // a step whose id ends in reading, so the issue is "reading": the first step writes the test, the second the fix.
  await L.close(session);
  const flow = L.makeFixture(path.join(base, "wordkit-flow"), graphene, { standin: standin.url });
  mkdirSync(path.join(flow.dir, "workflows"));
  cpSync(path.join(L.ROOT, "workflows", "fix-issue.md"), path.join(flow.dir, "workflows", "fix-issue.md"));
  execFileSync("git", ["-C", flow.dir, "add", "workflows"], { stdio: "pipe" });
  execFileSync("git", ["-C", flow.dir, "-c", "user.name=e2e", "-c", "user.email=e2e@example.com", "commit", "-qm", "the fix-issue workflow"], { stdio: "pipe" });
  session = await L.launch(app, profile, flow.dir, { width: 1440, height: 900, standin: standin.url });
  await L.openSidebar(session.page);
  await L.setSidebarWidth(session.page, 400);
  home = await L.homeFrame(session.page);
  await sectionShown(home, "Workflows · 1", "the repository's workflows on Home");
  await shot("workflows");
  await home.locator("article.card", { has: home.locator(".c-title", { hasText: "fix-issue" }) }).locator("button", { hasText: "Run" }).click();
  const input = session.page.locator(".quick-input-widget .quick-input-box input");
  const INPUTS = [["issue", "reading"], ["file", "tests/test_reading.py"], ["test", "python3 -m unittest tests.test_reading"], ["src", "wordkit/**"], ["suite", "python3 -m unittest"]];
  for (const [name, value] of INPUTS) { // Run asks for each input in turn, its default offered
    await session.page.waitForFunction((n) => {
      const widget = document.querySelector(".quick-input-widget");
      return widget && widget.style.display !== "none" && widget.querySelector(".quick-input-title")?.textContent?.endsWith(`: ${n}`);
    }, name, { timeout: 15000 }).catch(() => { throw new Error(`Run did not ask for “${name}”`); });
    await input.fill(value);
    await session.page.keyboard.press("Enter");
  }
  await sectionShown(home, "Suggested plan · 4", "the workflow's four steps, suggested");
  const proposed = state(flow.dir);
  if (proposed.tasks.map((t) => `${t.id} ${t.state}`).join() !== "test-reading proposed,fix-reading proposed,suite-reading proposed,pr-reading proposed") {
    throw new Error(`the workflow proposed ${proposed.tasks.map((t) => `${t.id} ${t.state}`).join(", ")}`);
  }
  if (proposed.spent) throw new Error(`a workflow calls no planner, yet $${proposed.spent} is spent before anything ran`);
  say("Run on fix-issue asked for its five inputs and proposed its four steps with no planner call");
  await shot("workflow-suggested");
  await home.locator(".sec-suggested .sec-head button", { hasText: "Start" }).click();
  await until(home, () => [...document.querySelectorAll("article.tone-yours .c-tag")].some((x) => x.textContent === "asks you"), null,
              "the pull request step to ask first", 180000);
  const step4 = Object.fromEntries(state(flow.dir).tasks.map((t) => [t.id, t]));
  for (const id of ["test-reading", "fix-reading", "suite-reading"]) if (step4[id]?.state !== "done") throw new Error(`${id} is ${step4[id]?.state}, not done`);
  if (step4["pr-reading"]?.state !== "yours" || !step4["pr-reading"].leaves) throw new Error(`the pull request step is ${step4["pr-reading"]?.state}, leaves ${step4["pr-reading"]?.leaves}`);
  if (step4["pr-reading"].checked.after !== null) throw new Error(`the run ran the step past the line: its command ${step4["pr-reading"].checked.after}`); // stopped at it, not crossed and failed
  if (step4["suite-reading"].command !== "python3 -m unittest") throw new Error(`the suite step's command is ${step4["suite-reading"].command}`);
  if (!(await home.locator("article.tone-yours button", { hasText: "Approve and run" }).count())) throw new Error("the step past the line offers no Approve and run");
  await L.openPanel(session.page);
  const wide = (await L.graphFrames(session.page)).at(-1);
  await until(wide, () => Boolean(document.querySelector("#gates .gate.now")) && /asks you first/.test(document.querySelector("#regions .region-label.away")?.textContent ?? ""), null,
              "the graph to draw the step past the line, with its gate");
  say("Start ran the test, the fix and the suite's command; the run stopped at the line, and the pull request step asks first");
  await shot("workflow-at-the-line");
  // Save as workflow, in the graph's header: the plan as it stands goes to workflows/<name>.md, and what the
  // last run was given is offered as what varies, so each value becomes a hole again.
  await wide.locator("#b-save").click();
  const asked = (want) => session.page.waitForFunction((w) => {
    const widget = document.querySelector(".quick-input-widget");
    return widget && widget.style.display !== "none" && widget.querySelector(".quick-input-title")?.textContent === "Save as workflow"
      && widget.querySelector(".quick-input-box input")?.value.startsWith(w);
  }, want, { timeout: 15000 }).catch(() => { throw new Error(`Save as workflow did not offer “${want}…”`); });
  await asked("fix-issue"); // the name of the one that was run
  await input.fill("fix-again");
  await session.page.keyboard.press("Enter");
  await asked("issue=reading, "); // its inputs, as name=value pairs
  await session.page.keyboard.press("Enter");
  await sectionShown(home, "Workflows · 2", "the saved workflow listed on Home");
  const saved = readFileSync(path.join(flow.dir, "workflows", "fix-again.md"), "utf8");
  for (const want of ["workflow: fix-again\n", "input: issue\n", "goal: fix issue {{issue}}", "[pr-{{issue}}]", "run: {{suite}}"]) {
    if (!saved.includes(want)) throw new Error(`workflows/fix-again.md has no “${want.trim()}”:\n${saved}`);
  }
  if (saved.includes("reading")) throw new Error(`a value stayed in workflows/fix-again.md where its hole belongs:\n${saved}`);
  say("Save as workflow wrote workflows/fix-again.md with the run's values as holes, and Home lists it");
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
