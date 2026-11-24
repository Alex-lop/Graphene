// The walk, on real sessions: a real editor in a throwaway profile with only the extension installed, no
// `graphene` on its PATH, and a new git repository with no Graphene files, in which this script starts real
// Claude Code sessions (`claude -p`, a small model, small asks: they run on the subscription of whoever runs it).
//   node sessions.mjs [--app code|cursor] [--vsix FILE] [--out DIR] [--width 1280] [--height 800] [--keep]
//   node sessions.mjs --look DIR     only open a folder that has sessions already, and say what was drawn
//   node sessions.mjs --empty        a folder with no session: the empty page, and the recorded session it replays
// It fails when a step does not show what it should, and keeps a screenshot of each step under --out.
// The folder is a scratch one of its own: for Cursor, close() deletes the folder's entry under ~/.cursor/projects.
import { execFileSync, spawn } from "node:child_process";
import { mkdirSync, symlinkSync, writeFileSync } from "node:fs";
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
// no graphene anywhere the editor looks on its PATH, and its setting names none; `claude` is on it, by a link in a
// directory of the walk's own (the agent is the person's, wherever they installed it)
const base = L.scratch(`gw-${appName}-`);
mkdirSync(path.join(base, "bin"));
symlinkSync(claude, path.join(base, "bin", "claude"));
process.env.PATH = `${path.join(base, "bin")}${path.delimiter}${L.noGraphene(process.env.PATH)}`;
// the terminal's rows as text (no canvas), so the walk reads what a person sees in it
const profile = L.makeProfile(base, { graphene: undefined, settings: { "terminal.integrated.gpuAcceleration": "off", "terminal.integrated.shellIntegration.enabled": false } });
L.installVsix(app, profile, vsix);

/** A new repository with two small files and one commit: a word counter and its test. */
function repository(dir) {
  mkdirSync(dir, { recursive: true });
  writeFileSync(path.join(dir, "wordcount.py"), 'def count_words(text):\n    """How many words a text has."""\n    return len(text.split(" "))\n');
  writeFileSync(path.join(dir, "test_wordcount.py"), 'import unittest\n\nfrom wordcount import count_words\n\n\nclass CountWords(unittest.TestCase):\n    def test_plain(self):\n        self.assertEqual(count_words("one two three"), 3)\n\n\nif __name__ == "__main__":\n    unittest.main()\n');
  writeFileSync(path.join(dir, "notes.md"), "# Notes\n\n");
  const git = (...a) => execFileSync("git", a, { cwd: dir, stdio: "pipe" });
  git("init", "-q");
  git("config", "user.name", "Scratch");
  git("config", "user.email", "scratch@example.com");
  git("add", "-A");
  git("commit", "-qm", "a word counter and its test");
  // somewhere to push to that is no one's: a bare repository beside it
  execFileSync("git", ["init", "-q", "--bare", `${dir}-remote.git`], { stdio: "pipe" });
  git("remote", "add", "origin", `${dir}-remote.git`);
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

/** The terminal in front, as text: its rows, and the names of the terminals there are. */
const terminal = (page) => page.evaluate(() => ({
  rows: [...document.querySelectorAll(".terminal-wrapper.active .xterm-rows > div")].map((r) => r.textContent.replace(/\u00a0/g, " ").trimEnd()).filter(Boolean),
  names: [...document.querySelectorAll(".terminal-tabs-entry .monaco-icon-label, .panel .composite.title .single-terminal-tab")].map((e) => e.textContent.trim()),
}));
/** A card of a page, clicked as a person clicks it: on the canvas, or its row in a narrow tab's lanes. */
const clickCard = (p, title) => p.frame.locator(`g.task:has(text.title), #lanes:not([hidden]) .lane`).filter({ hasText: title.slice(0, 14) }).first().click();

/** A card's receipt as its page shows it without a click: its foot on the canvas, or its line in a narrow tab's lanes. */
const foot = (p, title) => p.frame.evaluate((t) => {
  const card = [...document.querySelectorAll("#view g.task")].find((g) => g.querySelector("text.title")?.textContent.startsWith(t));
  const lane = [...document.querySelectorAll("#lanes:not([hidden]) .lane")].find((r) => r.querySelector(".l-title")?.textContent.startsWith(t));
  return card?.querySelector(".foot-v")?.textContent ?? lane?.querySelector(".l-scope")?.textContent ?? "";
}, title.slice(0, 14));
/** The pane of the chosen card: the files it changed, the tests it ran, what is worth a second look, what git says. */
const receiptOf = (p) => p.frame.evaluate(() => ({
  files: [...document.querySelectorAll("#details .rc-file")].map((b) => b.textContent),
  tests: [...document.querySelectorAll("#details .checkrow")].map((r) => r.textContent),
  flags: [...document.querySelectorAll("#details .rc-flag")].map((f) => [f.querySelector(".rc-kind")?.textContent, f.querySelector("code")?.textContent]),
}));

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
    const firstEnded = Date.now();
    // 3. it finishes: the card says what it changed
    const done = await until("the first session's card done", async () => (await pages(page)).find((p) => p.tasks.length && p.tasks.every((t) => t.mark !== "working" && !t.sub.startsWith("working"))), 60000);
    say(`it finished: ${JSON.stringify(done.tasks.map((t) => [t.title, t.sub]))} · ${done.line}`);
    const receipt = await foot(done, one.goal);
    if (!/unittest passed/.test(receipt) || !/2 files changed · unittest passed/.test(done.line)) throw new Error(`its receipt does not say the two files and the pass: ${JSON.stringify([receipt, done.line])}`);
    say(`its card carries its receipt: ${JSON.stringify(receipt)}; the page's line: ${JSON.stringify(done.line)}`);
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
    // --- the terminal on click, three ways ---
    // (a) a session started outside the editor: its card opens its transcript's tail, read like a terminal
    await page.locator(".tabs-container .tab", { hasText: "2 sessions" }).first().click();
    const both = await until("the page of two bands in front", async () => (await pages(page)).find((p) => p.bands.length === 2), 15000);
    await clickCard(both, one.goal);
    const tail = await until("the transcript's tail in a terminal", async () => { const t = await terminal(page); return t.rows.some((r) => r.includes("its turn ended")) ? t : null; }, 20000);
    say(`a click on a card of a session started outside the editor: its transcript's tail in a terminal, ending ${JSON.stringify(tail.rows.slice(-3))}`);
    await shot(page, "terminal-transcript-tail");
    // its receipt, in its pane: the two files it changed, the test it ran and what decided its pass
    const r1 = await receiptOf(both);
    if (r1.files.length !== 2 || !r1.tests.some((t) => /python3 -m unittest.*unittest passed/.test(t))) throw new Error(`the first session's receipt: ${JSON.stringify(r1)}`);
    say(`its pane's receipt: changed ${JSON.stringify(r1.files)}, tests ${JSON.stringify(r1.tests)}`);
    // (c) it is idle and nothing has it open: its card offers Resume in terminal, which runs claude --resume with its id
    const resume = both.frame.locator("#details .d-acts button", { hasText: "Resume in terminal" });
    await resume.waitFor({ timeout: 10000 });
    await page.waitForTimeout(Math.max(0, 17000 - (Date.now() - firstEnded))); // a session whose file was written in the last fifteen seconds is not resumed: it may still be writing
    await resume.click();
    const resumed = await until("claude --resume in a new terminal", async () => { const t = await terminal(page); return t.rows.find((r) => /claude --resume [0-9a-f-]{36}/.test(r)); }, 20000);
    say(`Resume in terminal typed: ${JSON.stringify(resumed.trim().replace(/^.*?(claude --resume)/, "$1"))}`);
    await page.waitForTimeout(6000); // Claude Code starts in it
    await shot(page, "resume-in-terminal");
    // (b) a session that runs in one of the editor's own terminals: a click on its card reveals that terminal
    await L.palette(page, "Terminal: Create New Terminal");
    await page.waitForTimeout(1500);
    await page.keyboard.type("PROMPT='%1~ %# '; clear"); // the pictures name the folder, not whose machine it is
    await page.keyboard.press("Enter");
    await page.waitForTimeout(500);
    await page.keyboard.type('claude -p "Add a line to notes.md that says what test_wordcount.py tests. Then wait: run sleep 20." --model haiku --permission-mode acceptEdits --allowedTools "Bash(sleep 20)" Edit Read');
    await page.keyboard.press("Enter");
    const own = await until("a page for the session in the editor's terminal", async () => (await pages(page)).find((p) => p.goal.startsWith("Add a line to notes.md")), 90000);
    await page.locator(".tabs-container .tab", { hasText: "2 sessions" }).first().click(); // another terminal is put in front first: the tail's
    await clickCard(await until("the page of two bands again", async () => (await pages(page)).find((p) => p.bands.length === 2), 15000), one.goal);
    await until("the tail's terminal in front", async () => (await terminal(page)).rows.some((r) => r.includes("its turn ended")), 15000);
    await page.locator(".tabs-container .tab", { hasText: "Add a line to notes" }).first().click();
    const live = await until("its page in front", async () => { const p = (await pages(page)).find((x) => x.goal.startsWith("Add a line to notes.md")); return p && (await p.frame.locator("#goal").isVisible().catch(() => false)) ? p : null; }, 15000);
    await clickCard(live, "Add a line to notes.md");
    const revealed = await until("the editor's own terminal revealed", async () => { const t = await terminal(page); return t.rows.some((r) => r.includes('claude -p "Add a line to notes.md')) ? t : null; }, 20000);
    say(`a click on the card of a session running in the editor's terminal revealed that terminal: ${JSON.stringify(revealed.rows.find((r) => r.includes("claude -p")).trim().slice(0, 60))}`);
    // and while it writes, its card does not offer to resume it
    if (await live.frame.locator("#details .d-acts button", { hasText: "Resume in terminal" }).count()) throw new Error("a session still writing offers Resume in terminal");
    say("while it is working its card offers Terminal, and not Resume in terminal");
    await shot(page, "terminal-of-the-editor");
    void own;

    // --- receipts ---
    // a file a card changed opens its diff
    await page.locator(".tabs-container .tab", { hasText: "2 sessions" }).first().click();
    const again = await until("the page of two bands, for its receipts", async () => (await pages(page)).find((p) => p.bands.length === 2 && p.tasks.length), 15000);
    await clickCard(again, one.goal);
    await again.frame.locator("#details .rc-file", { hasText: "wordcount.py" }).first().click();
    await page.waitForSelector(".monaco-diff-editor, .multiDiffEditor, .multi-diff-editor", { timeout: 20000 }).catch(() => { throw new Error("a changed file opened no diff"); });
    say("a changed file on its card opened its diff");
    await page.waitForTimeout(800);
    await shot(page, "changed-file-diff");
    // the session that ran no test says so (the diff's tab is in front now: the page's is clicked back)
    await page.locator(".tabs-container .tab", { hasText: "2 sessions" }).first().click();
    await until("the page in front again", async () => again.frame.locator("#b-session").isVisible().catch(() => false), 15000);
    await clickCard(again, "Add a one-line docstring");
    const r2 = await until("the second session's receipt", async () => { const r = await receiptOf(again); return r.files.some((f) => f.includes("test_wordcount.py")) ? r : null; }, 10000);
    if (!r2.tests.some((t) => t === "ran no tests")) throw new Error(`a session that ran no test does not say so: ${JSON.stringify(r2)}`);
    say(`the session that ran no test says so: ${JSON.stringify(r2.tests)}, and its card's foot ${JSON.stringify(await foot(again, "Add a one-line docstring"))}`);
    await shot(page, "ran-no-tests");
    // a session that commits and pushes (to a bare repository beside the folder): the flag, with the line that shows it
    const pushing = ask(dir, 'Create CHANGES.md with the one line "pushed by the walk". Then run exactly: git add CHANGES.md, then git commit -m "changes", then git push -u origin HEAD.', ["Bash(git add:*)", "Bash(git commit:*)", "Bash(git push:*)"]);
    const pushed = await until("a page for the session that pushes", async () => (await pages(page)).find((p) => p.goal.startsWith("Create CHANGES.md")), 90000);
    await pushing;
    await page.locator(".tabs-container .tab", { hasText: "Create CHANGES.md" }).first().click();
    const flagged = await until("its card flagged", async () => { const p = (await pages(page)).find((x) => x.goal.startsWith("Create CHANGES.md")); return p && /to look at/.test(await foot(p, "Create CHANGES.md")) ? p : null; }, 60000);
    await clickCard(flagged, "Create CHANGES.md");
    const r3 = await until("its receipt's flag", async () => { const r = await receiptOf(flagged); return r.flags.some(([k]) => k === "push") ? r : null; }, 10000);
    say(`the session that pushed: its card's foot ${JSON.stringify(await foot(flagged, "Create CHANGES.md"))}; flags ${JSON.stringify(r3.flags)}; git ${JSON.stringify(r3.tests.filter((t) => /HEAD|tool call/.test(t)))}`);
    await shot(page, "pushed-flag");
    void pushed;
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
