// The walk, on real sessions: a real editor in a throwaway profile with only the extension installed, no
// `graphene` on its PATH, and a new git repository with no Graphene files, in which this script starts real
// Claude Code sessions (`claude -p`, a small model, small asks: they run on the subscription of whoever runs it).
//   node sessions.mjs [--app code|cursor] [--vsix FILE] [--out DIR] [--width 1280] [--height 800] [--keep]
//   node sessions.mjs --look DIR     only open a folder that has sessions already, and say what was drawn
//   node sessions.mjs --empty        a folder with no session: the empty page, and the recorded session it replays
// It fails when a step does not show what it should, and keeps a screenshot of each step under --out.
// The folder is a scratch one of its own: for Cursor, close() deletes the folder's entry under ~/.cursor/projects.
import { execFileSync, spawn } from "node:child_process";
import { mkdirSync, writeFileSync } from "node:fs";
import path from "node:path";
import * as L from "./lib.mjs";

const arg = (k, d) => { const i = process.argv.indexOf(k); return i > 0 ? process.argv[i + 1] : d; };
const appName = arg("--app", "code"), out = path.resolve(arg("--out", "sessions-shots")), look = arg("--look", "");
const vsix = arg("--vsix", null) ? path.resolve(arg("--vsix")) : L.findVsix();
const t0 = Date.now(), say = (l) => console.log(`${((Date.now() - t0) / 1000).toFixed(1)}s ${l}`);
let step = 0;
const shot = (page, name) => L.shot(page, path.join(out, `${appName}-${String(++step).padStart(2, "0")}-${name}.png`));
const until = async (what, fn, timeout = 60000) => {
  for (const end = Date.now() + timeout; Date.now() < end; await new Promise((r) => setTimeout(r, 250))) { const v = await fn(); if (v) return v; }
  throw new Error(`waited ${timeout / 1000} s for ${what}`);
};

const app = await L.findApp(appName);
if (!app) { console.error(`no ${appName} here`); process.exit(1); }
const claude = execFileSync("/bin/sh", ["-c", "command -v claude"], { encoding: "utf8" }).trim(); // found before the PATH loses graphene's directory
// no graphene anywhere the editor looks on its PATH, and its setting names none
process.env.PATH = L.noGraphene(process.env.PATH);
const base = L.scratch(`gw-${appName}-`);
const profile = L.makeProfile(base, { graphene: undefined });
L.installVsix(app, profile, vsix);

/** A new repository with two small files and one commit: a word counter and its test. */
function repository(dir) {
  mkdirSync(dir, { recursive: true });
  writeFileSync(path.join(dir, "wordcount.py"), 'def count_words(text):\n    """How many words a text has."""\n    return len(text.split(" "))\n');
  writeFileSync(path.join(dir, "test_wordcount.py"), 'import unittest\n\nfrom wordcount import count_words\n\n\nclass CountWords(unittest.TestCase):\n    def test_plain(self):\n        self.assertEqual(count_words("one two three"), 3)\n\n\nif __name__ == "__main__":\n    unittest.main()\n');
  writeFileSync(path.join(dir, "notes.md"), "# Notes\n\n");
  const git = (...a) => execFileSync("git", a, { cwd: dir, stdio: "pipe" });
  git("init", "-q");
  git("add", "-A");
  git("-c", "user.name=Scratch", "-c", "user.email=scratch@example.com", "commit", "-qm", "a word counter and its test");
  return dir;
}

/** A real Claude Code session in the folder, as a person starts one in a terminal outside the editor. */
function ask(dir, prompt, more = []) {
  const child = spawn(claude, ["-p", prompt, "--model", "haiku", "--permission-mode", "acceptEdits", "--allowedTools",
                               "Bash(python3 -m unittest:*)", "Bash(python3 -m unittest)", "Edit", "Write", "Read", ...more], { cwd: dir, stdio: "ignore" });
  return new Promise((resolve) => child.on("exit", resolve));
}

/** Each graph page in the window, as a person reads it: its header, its cards, its bands. */
async function pages(page) {
  const all = [];
  for (const f of await L.graphFrames(page)) {
    const g = await L.readGraph(f).catch(() => null);
    if (!g) continue;
    const more = await f.evaluate(() => ({ bands: [...document.querySelectorAll("#heads .band-label, #lanes:not([hidden]) .wave .w-name")].map((b) => b.textContent), line: document.querySelector("#auto")?.textContent ?? "" })).catch(() => ({ bands: [], line: "" }));
    all.push({ frame: f, ...g, ...more });
  }
  return all;
}

/** What the file in front holds, and whether the keyboard is in it. */
const typed = (page) => page.evaluate(() => ({
  text: [...document.querySelectorAll(".editor-group-container.active .monaco-editor .view-line")].map((l) => l.textContent.replace(/\u00a0/g, " ")).join("\n"), // the editor draws a space as a no-break one
  inEditor: Boolean(document.activeElement?.closest(".monaco-editor")),
}));

let session = null, failed = "";
try {
  if (process.argv.includes("--empty")) {
    session = await L.launch(app, profile, repository(path.join(base, "wordcount")), { width: Number(arg("--width", 1280)), height: Number(arg("--height", 800)) });
    await L.openPanel(session.page);
    const frame = await until("the empty page", async () => (await L.graphFrames(session.page))[0], 20000);
    const notice = await until("what the empty page says", () => frame.evaluate(() => document.querySelector("#notice:not([hidden])")?.textContent ?? ""), 20000);
    say(`the empty page says: ${JSON.stringify(notice)}`);
    await shot(session.page, "empty-page");
    await frame.locator("#notice button", { hasText: "Replay a recorded session" }).click();
    const seen = new Set();
    await until("the recorded session drawn to its end", async () => {
      const g = await L.readGraph(frame);
      for (const t of g.tasks) seen.add(t.sub.split(" · ")[0]);
      if (g.tasks.length === 2 && seen.size < 9) { seen.add("shot"); await shot(session.page, "replay-playing"); }
      return g.tasks.length === 4 && g.tasks.every((t) => t.sub.startsWith("done"));
    }, 90000);
    const g = await L.readGraph(frame);
    say(`the replay drew ${g.tasks.length} cards (${JSON.stringify(g.tasks.map((t) => t.title))}), under ${JSON.stringify(await frame.evaluate(() => document.querySelector("#replay")?.textContent))}`);
    if (!seen.has("working")) throw new Error("no card of the replay was ever seen at work");
    await shot(session.page, "replay-over");
  } else if (look) {
    session = await L.launch(app, profile, path.resolve(look), { width: Number(arg("--width", 1280)), height: Number(arg("--height", 800)) });
    await L.openPanel(session.page);
    const { frame, tasks } = await L.waitForGraph(session.page, { timeout: 30000 });
    say(`the graph drew ${tasks} card(s): ${JSON.stringify((await L.readGraph(frame)).tasks.map((t) => [t.title, t.sub, t.mark]))}`);
    await shot(session.page, "graph");
    await L.openSidebar(session.page);
    const home = await L.homeFrame(session.page, 30000);
    await home.waitForSelector(".screen h2", { timeout: 20000 });
    say(`Home: ${JSON.stringify(await home.evaluate(() => [...document.querySelectorAll(".screen h2, .screen p, .screen .pick")].map((e) => e.textContent)))}`);
    await shot(session.page, "home");
  } else {
    const dir = repository(path.join(base, "wordcount"));
    // an old session, there before the window opens: it gets no page of its own
    await ask(dir, "Say in one short sentence what wordcount.py does. Change nothing.");
    session = await L.launch(app, profile, dir, { width: Number(arg("--width", 1280)), height: Number(arg("--height", 800)), args: [path.join(dir, "notes.md")] });
    const page = session.page;
    say(`launched ${appName} on a new repository with one old session`);
    await page.locator(".monaco-editor .view-lines").first().click();
    await page.keyboard.press("Meta+ArrowDown");
    await page.keyboard.type("typed before any session. ");
    await page.waitForTimeout(5000); // two looks at the folder: the old session is seen, and left alone
    if ((await pages(page)).length) throw new Error("a page opened for a session that was there before the window");
    say("no page for the session that was there before the window opened");

    // 1. a session starts: a page opens by itself, beside the file, and the file keeps the keyboard
    const first = ask(dir, "count_words in wordcount.py counts wrongly when there are two spaces in a row or a tab. Fix it in wordcount.py, add a test for it to test_wordcount.py, and run the tests with python3 -m unittest.");
    const typing = setInterval(() => void page.keyboard.type("k").catch(() => {}), 400); // a person typing in the file, the whole time
    let seenWorking = "";
    const one = await until("a page for the first session", async () => (await pages(page)).find((p) => p.tasks.length), 90000);
    say(`a page opened by itself: ${JSON.stringify(one.goal)} · ${one.line}`);
    await shot(page, "page-opens-by-itself");
    // 2. while it works, its card says so
    await until("its card at work", async () => { const p = (await pages(page))[0]; seenWorking = p?.tasks.find((t) => t.mark === "working" || t.sub.startsWith("working"))?.sub ?? ""; return seenWorking; }, 60000); // a card, or a lane in a narrow tab
    say(`while it works its card says: ${JSON.stringify(seenWorking)}`);
    await shot(page, "card-working");
    await first;
    // 3. it finishes: the card says what it changed
    const done = await until("the first session's card done", async () => (await pages(page)).find((p) => p.tasks.length && p.tasks.every((t) => t.mark !== "working" && !t.sub.startsWith("working"))), 60000);
    say(`it finished: ${JSON.stringify(done.tasks.map((t) => [t.title, t.sub]))} · ${done.line}`);
    await shot(page, "card-done");

    // 4. a second session: a second page; then added to the first page, two bands
    const second = ask(dir, "Add a one-line docstring to the CountWords class in test_wordcount.py. Do not run anything.");
    await until("a second page", async () => (await pages(page)).filter((p) => p.tasks.length).length === 2, 90000);
    say("a second session began: a second page");
    await second;
    await page.waitForTimeout(2500);
    await shot(page, "two-pages");
    // the file kept the keyboard throughout: it is still in it, and every key typed while the pages opened landed
    clearInterval(typing);
    await page.waitForTimeout(600);
    const file = await typed(page);
    const keys = (file.text.match(/k/g) ?? []).length;
    if (!file.inEditor || !file.text.includes("typed before any session.") || keys < 20) throw new Error(`the file lost the keyboard: ${JSON.stringify(file)}`);
    say(`the file being typed in kept the keyboard: ${keys} keys landed in it while two pages opened beside it`);
    // the first session's page is a tab behind the second's: brought in front, as a person clicks its tab
    await page.locator(".tabs-container .tab", { hasText: one.goal.slice(0, 18) }).first().click();
    const firstPage = await until("the first page in front", async () => {
      const p = (await pages(page)).find((x) => x.goal === one.goal);
      return p && (await p.frame.locator("#b-session").isVisible().catch(() => false)) ? p : null;
    }, 15000);
    await firstPage.frame.locator("#b-session").click();
    const row = page.locator(".quick-input-list .monaco-list-row").first();
    await row.waitFor({ timeout: 10000 });
    await shot(page, "add-to-page");
    await row.click();
    const two = await until("one page with two bands", async () => (await pages(page)).find((p) => p.bands.length === 2), 20000);
    say(`Add to page…: one page, two bands: ${JSON.stringify(two.bands)}`);
    await page.waitForTimeout(600);
    await shot(page, "two-bands");

    // taken off again: the page is one session's
    await two.frame.locator(".band-off, #lanes:not([hidden]) .w-off").last().click();
    await until("the session taken off", async () => (await pages(page)).every((p) => p.bands.length < 2), 15000);
    say("taken off again: the page draws one session");

    // 5. a reload brings the pages back
    await two.frame.locator("#b-session").click();
    await page.locator(".quick-input-list .monaco-list-row").first().click();
    await until("two bands again", async () => (await pages(page)).find((p) => p.bands.length === 2), 20000);
    await L.palette(page, "Developer: Reload Window");
    await page.waitForSelector(".monaco-workbench", { timeout: 60000 });
    // the page in front is back with its two sessions; the other tab is there, and its page draws once it is shown
    // (the editor brings a page behind another back only then)
    const front = await until("the page of two bands back after a reload", async () => (await pages(page)).find((p) => p.bands.length === 2), 60000);
    const tabs = () => page.locator(".tabs-container .tab").allTextContents();
    await until("both pages' tabs back", async () => (await tabs()).filter((t) => t.includes("2 sessions") || t.includes("Add a one-line")).length === 2, 20000);
    await shot(page, "after-reload");
    await page.locator(".tabs-container .tab", { hasText: "Add a one-line" }).first().click();
    const other = await until("the second page drawn again", async () => (await pages(page)).find((p) => p.bands.length < 2 && p.tasks.length), 30000);
    const back = [front, other];
    say(`after a reload the pages are back: ${JSON.stringify(back.map((p) => [p.goal, p.bands.length]))}`);
    writeFileSync(path.join(out, `${appName}-walk.json`), JSON.stringify({ folder: dir, typedKeys: keys, pages: back.map((p) => ({ goal: p.goal, line: p.line, bands: p.bands, tasks: p.tasks })) }, null, 1));
  }
} catch (e) {
  failed = String(e?.stack ?? e);
  if (session) await L.shot(session.page, path.join(out, `${appName}-failed.png`)).catch(() => {});
} finally {
  if (session && !process.argv.includes("--keep")) await L.close(session);
}
if (failed) { console.error(`FAILED: ${failed}`); process.exit(1); }
say(`pictures in ${out}`);
