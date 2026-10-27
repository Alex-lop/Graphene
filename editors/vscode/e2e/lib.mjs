// The harness: real VS Code or Cursor, driven with Playwright's Electron driver the way VS Code's own
// smoke tests drive it. Every launch has a --user-data-dir and --extensions-dir of its own, never the
// person's. The pieces: find the app, make a profile, install a .vsix, make a fixture repository, run
// `graphene auto` against the stand-in, launch, open the views, reach into the webview's frames, shoot.
import "./pw-env.mjs";
import { execFileSync, spawn, spawnSync } from "node:child_process";
import { existsSync, mkdirSync, mkdtempSync, openSync, readdirSync, readFileSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { _electron as electron } from "playwright-core";

export const HERE = path.dirname(fileURLToPath(import.meta.url));
export const EXT = path.resolve(HERE, ".."); // editors/vscode
export const ROOT = path.resolve(EXT, "..", ".."); // the repository
export const MAC = process.platform === "darwin";

// VS Code listens on a Unix socket under --user-data-dir; a socket path over 103 bytes fails on macOS,
// so profiles live under a short temp dir (E2E_TMP to choose it).
export const SHORT = process.env.E2E_TMP || (tmpdir().length <= 40 ? tmpdir() : "/tmp");

export const THEMES = {
  dark: "Default Dark Modern",
  light: "Default Light Modern",
  hc: "Default High Contrast",
};

/** The app: `code` (VSCODE_EXECUTABLE, the Mac's app, or a build @vscode/test-electron downloads) or `cursor`. */
export async function findApp(name = "code") {
  if (name === "cursor") {
    const exe = process.env.CURSOR_EXECUTABLE || "/Applications/Cursor.app/Contents/MacOS/Cursor";
    if (!existsSync(exe)) return null;
    return { name, exe, cli: cliBeside(exe, "cursor") };
  }
  let exe = process.env.VSCODE_EXECUTABLE;
  if (!exe && MAC) {
    exe = ["Code", "Electron"].map((n) => `/Applications/Visual Studio Code.app/Contents/MacOS/${n}`).find(existsSync);
  }
  if (!exe) {
    const { downloadAndUnzipVSCode } = await import("@vscode/test-electron");
    exe = await downloadAndUnzipVSCode({ version: process.env.VSCODE_VERSION || "stable", cachePath: path.join(SHORT, "vscode-e2e-download") });
  }
  if (!existsSync(exe)) return null;
  return { name: "code", exe, cli: cliBeside(exe, "code") };
}

/** The app's command line (`bin/code`), from where its Electron binary is. */
function cliBeside(exe, bin) {
  const candidates = MAC
    ? [path.resolve(exe, "..", "..", "Resources", "app", "bin", bin)]
    : [path.resolve(exe, "..", "bin", bin), path.resolve(exe, "..", "bin", "code"), path.resolve(exe, "..", "bin", "code-insiders")];
  return candidates.find(existsSync) || null;
}

/** A profile of its own: user data, extensions, and the settings the harness needs. */
export function makeProfile(base, { graphene, theme = THEMES.dark, settings = {} } = {}) {
  const userDataDir = path.join(base, "user"), extensionsDir = path.join(base, "ext");
  mkdirSync(path.join(userDataDir, "User"), { recursive: true });
  mkdirSync(extensionsDir, { recursive: true });
  const profile = { base, userDataDir, extensionsDir, settings: { ...settings } };
  writeSettings(profile, {
    "graphene.path": graphene,
    "workbench.colorTheme": theme,
    "workbench.startupEditor": "none",
    "workbench.tips.enabled": false,
    "workbench.enableExperiments": false,
    "security.workspace.trust.enabled": false, // the extension is off in Restricted Mode
    "update.mode": "none",
    "update.showReleaseNotes": false,
    "telemetry.telemetryLevel": "off",
    "extensions.autoUpdate": false,
    "extensions.autoCheckUpdates": false,
    "extensions.ignoreRecommendations": true,
    "window.restoreWindows": "none",
    "window.newWindowDimensions": "default",
    "git.openRepositoryInParentFolders": "never",
    "chat.commandCenter.enabled": false,
    "workbench.secondarySideBar.defaultVisibility": "hidden", // the Chat pane, else open on a fresh profile
    "editor.accessibilitySupport": "off", // else a "screen reader detected" toast: the driver looks like one
    ...settings,
  });
  return profile;
}

/** Writes (or changes) the profile's user settings; a running window takes a change at once. */
export function writeSettings(profile, more) {
  Object.assign(profile.settings, more);
  writeFileSync(path.join(profile.userDataDir, "User", "settings.json"), JSON.stringify(profile.settings, null, 2));
}

/** The app's CLI installs the .vsix into the profile's extensions dir. */
export function installVsix(app, profile, vsix) {
  const args = ["--install-extension", vsix, "--force", "--extensions-dir", profile.extensionsDir, "--user-data-dir", profile.userDataDir];
  const done = app.cli
    ? spawnSync(app.cli, args, { encoding: "utf8", env: cleanEnv() })
    : spawnSync(app.exe, args, { encoding: "utf8", env: { ...cleanEnv(), ELECTRON_RUN_AS_NODE: undefined } });
  if (done.status !== 0) throw new Error(`install failed: ${done.stdout}\n${done.stderr}`);
  return done.stdout;
}

/** The newest .vsix in editors/vscode (or VSIX). */
export function findVsix() {
  if (process.env.VSIX) return path.resolve(process.env.VSIX);
  const found = readdirSync(EXT).filter((f) => f.endsWith(".vsix")).sort();
  if (!found.length) throw new Error("no .vsix in editors/vscode: npm run package there, or set VSIX");
  return path.join(EXT, found.at(-1));
}

/** The environment graphene runs in from here: the agent's marks gone (it is the person's run), the
 *  stand-in's key, no keychain. */
export function cleanEnv(more = {}) {
  const env = {};
  for (const [k, v] of Object.entries(process.env)) {
    if (/^(GRAPHENE_|CLAUDE|CODEX|NEBIUS_)/.test(k) || k === "AI_AGENT") continue;
    env[k] = v;
  }
  return { ...env, GRAPHENE_KEYCHAIN: "off", ...more };
}

/** The clone's own graphene (the venv's), or GRAPHENE. */
export function findGraphene() {
  const own = process.env.GRAPHENE || path.join(ROOT, ".venv", "bin", "graphene");
  if (!existsSync(own)) throw new Error(`no graphene at ${own}: uv sync in the clone, or set GRAPHENE`);
  return own;
}

/** The fixture: wordkit (dev/proof/make_wordkit.py) with `graphene init --planner nemotron --executor nemotron`. */
export function makeFixture(dir, graphene, { standin } = {}) {
  const python = process.env.PYTHON || path.join(ROOT, ".venv", "bin", "python");
  execFileSync(existsSync(python) ? python : "python3", [path.join(ROOT, "dev", "proof", "make_wordkit.py"), dir], { stdio: "pipe" });
  const env = fixtureEnv(standin);
  execFileSync(graphene, ["init", "--planner", "nemotron", "--executor", "nemotron"], { cwd: dir, env, stdio: "pipe" });
  return { dir, graphene, env };
}

export function fixtureEnv(standin) {
  return cleanEnv(standin ? { GRAPHENE_TOKENFACTORY_URL: standin, NEBIUS_API_KEY: "fake-key" } : {});
}

/** The stand-in (dev/proof/standin.py) as a child: its URL is its first line. */
export async function startStandin() {
  const python = process.env.PYTHON || path.join(ROOT, ".venv", "bin", "python");
  const child = spawn(existsSync(python) ? python : "python3", [path.join(ROOT, "dev", "proof", "standin.py")], { stdio: ["ignore", "pipe", "inherit"] });
  const url = await new Promise((resolve, reject) => {
    let buf = "";
    child.stdout.on("data", (d) => { buf += d; const nl = buf.indexOf("\n"); if (nl >= 0) resolve(buf.slice(0, nl).trim()); });
    child.on("exit", (c) => reject(new Error(`the stand-in ended early (${c})`)));
    setTimeout(() => reject(new Error("the stand-in said nothing in 30 s")), 30000);
  });
  return { url, child, stop: () => child.kill("SIGTERM") };
}

export const GOAL = "wordkit grows three things at once: a --top N option on the CLI that prints the N most common words with their counts; a reading time in whole minutes, rounded up, at 200 words a minute; and hyphenated words like well-known counted as one word.";

/** `graphene auto` against the stand-in, in the background: the store changes as it would live. */
export function startAuto(fixture, { rounds = 2, forks = 3, log } = {}) {
  let out = "ignore";
  if (log) {
    mkdirSync(path.dirname(log), { recursive: true });
    const fd = openSync(log, "a");
    out = ["ignore", fd, fd];
  }
  const child = spawn(fixture.graphene, ["auto", GOAL, "--budget", "2", "--forks", String(forks), "--rounds", String(rounds), "--parallel", "4",
                                          "--check", "python3 -m unittest"], { cwd: fixture.dir, env: fixture.env, stdio: out });
  return child;
}

/** Launch the app on a folder with the profile. Returns {app, page, size}. */
export async function launch(app, profile, folder, { width = 1280, height = 800, video, timeout = 90000 } = {}) {
  const args = [
    folder,
    "--user-data-dir", profile.userDataDir, "--extensions-dir", profile.extensionsDir,
    "--skip-welcome", "--skip-release-notes", "--disable-updates", "--disable-telemetry", "--disable-crash-reporter",
    "--disable-workspace-trust", "--no-cached-data", "--disable-gpu", "--new-window",
  ];
  const env = { ...cleanEnv(), VSCODE_SKIP_PRELAUNCH: "1", ELECTRON_ENABLE_LOGGING: process.env.E2E_LOG ? "1" : undefined };
  delete env.ELECTRON_RUN_AS_NODE;
  const options = { executablePath: app.exe, args, env, timeout };
  if (video) {
    ensureFfmpeg(); // without Playwright's own ffmpeg the window never loads: it waits for the recorder
    mkdirSync(video, { recursive: true });
    options.recordVideo = { dir: video, size: { width, height } };
  }
  const electronApp = await electron.launch(options);
  const page = await electronApp.firstWindow({ timeout });
  await page.waitForSelector(".monaco-workbench", { timeout });
  await setSize(electronApp, page, width, height);
  if (app.name === "cursor") await cursorClassic(page, profile);
  return { app, electronApp, page, profile, folder, video };
}

/** Cursor 3 on a fresh profile: a log-in wall covers the window, and its agent layout keeps the primary
 *  side bar at display:none. The harness hides the wall, closes the agents pane, and lets the side bar
 *  show, so the extension's views can be looked at without an account. */
export async function cursorClassic(page, profile) {
  await page.waitForTimeout(1500);
  await page.evaluate(() => { const o = document.querySelector(".onboarding-v2-overlay"); if (o) o.style.display = "none"; });
  await command(page, profile, "workbench.action.toggleAgents");
  await page.waitForTimeout(800);
  await page.addStyleTag({ content: ".monaco-workbench .part.sidebar { display: block !important; }" });
}

/** Playwright's ffmpeg, the revision this playwright-core wants, in e2e/.pw: fetched once. */
export function ensureFfmpeg() {
  const dir = process.env.PLAYWRIGHT_BROWSERS_PATH;
  const have = existsSync(dir) && readdirSync(dir).some((d) => d.startsWith("ffmpeg-") && existsSync(path.join(dir, d, "INSTALLATION_COMPLETE")));
  if (have) return;
  execFileSync(process.execPath, [path.join(HERE, "node_modules", "playwright-core", "cli.js"), "install", "ffmpeg"], { stdio: "inherit" });
}

/** The window's content size, set in the main process. */
export async function setSize(electronApp, page, width, height) {
  await electronApp.evaluate(({ BrowserWindow }, [w, h]) => {
    const win = BrowserWindow.getAllWindows().find((x) => x.isVisible()) || BrowserWindow.getAllWindows()[0];
    win.setContentSize(w, h);
  }, [width, height]);
  await page.waitForFunction(([w, h]) => Math.abs(window.innerWidth - w) <= 2 && Math.abs(window.innerHeight - h) <= 2, [width, height], { timeout: 10000 }).catch(() => {});
}

/** The command palette, typed to: the first entry that matches `title` runs. */
export async function palette(page, title) {
  await page.keyboard.press("F1");
  const input = page.locator(".quick-input-widget .quick-input-box input"); // Cursor's palette has checkboxes too
  await input.waitFor({ timeout: 10000 });
  await input.fill(">" + title);
  const row = page.locator(".quick-input-list .monaco-list-row").filter({ hasText: title }).first();
  await row.waitFor({ timeout: 10000 });
  await page.keyboard.press("Enter");
  await page.waitForSelector(".quick-input-widget", { state: "hidden", timeout: 10000 }).catch(() => {});
}

/** Run a command by its id: the profile's keybindings.json binds a spare chord to it, and the chord is
 *  pressed. For commands the palette does not list by a title (Cursor's own, a view's id). */
export async function command(page, profile, id) {
  const chord = "Control+Alt+Shift+F9";
  profile.keybindings = (profile.keybindings || []).filter((k) => k.key !== chord.toLowerCase());
  profile.keybindings.push({ key: chord.toLowerCase().replace("control", "ctrl"), command: id });
  writeFileSync(path.join(profile.userDataDir, "User", "keybindings.json"), JSON.stringify(profile.keybindings, null, 2));
  await page.waitForTimeout(600); // the keybinding service reads the file
  await page.keyboard.press(chord);
}

/** Graphene's side bar container, and its Graph view in it. */
export async function openSidebar(page) {
  await palette(page, "View: Show Graphene");
  await page.waitForSelector(".sidebar .pane-header", { timeout: 20000, state: "attached" });
  const flat = await page.evaluate(() => (document.querySelector(".sidebar .pane-header")?.getBoundingClientRect().height ?? 0) === 0);
  if (flat) { // Cursor: the part was hidden when the views came; a nudge to the window lays them out
    await page.evaluate(() => window.dispatchEvent(new Event("resize")));
    await page.waitForTimeout(500);
  }
  await page.waitForSelector(".sidebar .pane-header", { timeout: 20000 });
}

/** The graph in the editor area (Graphene: Show Plan Graph). */
export async function openPanel(page) {
  const before = (await graphFrames(page)).length;
  await palette(page, "Graphene: Show Plan Graph");
  const t0 = Date.now();
  while ((await graphFrames(page)).length <= before) {
    if (Date.now() - t0 > 20000) throw new Error("the graph panel did not open");
    await page.waitForTimeout(100);
  }
  await page.waitForSelector(".editor-group-container .tab", { timeout: 10000 }).catch(() => {});
}

/** The side bar's width in px, by dragging its sash. */
export async function setSidebarWidth(page, width) {
  const sidebar = page.locator(".monaco-workbench .part.sidebar");
  for (let i = 0; i < 6; i++) {
    const box = await sidebar.boundingBox();
    if (!box) throw new Error("no side bar on screen");
    if (Math.abs(box.width - width) <= 1) return box.width;
    const sashes = await page.locator(".monaco-sash.vertical").all();
    let sash = null, best = 1e9;
    for (const s of sashes) {
      const b = await s.boundingBox();
      if (!b) continue;
      const d = Math.abs(b.x + b.width / 2 - (box.x + box.width));
      if (d < best) { best = d; sash = b; }
    }
    if (!sash) throw new Error("no sash beside the side bar");
    const y = sash.y + Math.min(200, sash.height / 2);
    const x0 = sash.x + sash.width / 2;
    await page.mouse.move(x0, y);
    await page.mouse.down();
    await page.mouse.move(x0 + (width - box.width) / 2, y, { steps: 4 });
    await page.mouse.move(x0 + (width - box.width), y, { steps: 4 });
    await page.mouse.up();
    await page.waitForTimeout(200);
  }
  return (await sidebar.boundingBox())?.width;
}

/** Set the theme by its name and wait for the workbench to wear it. */
export async function setTheme(page, profile, theme) {
  writeSettings(profile, { "workbench.colorTheme": theme });
  const cls = theme.includes("High Contrast") ? (theme.includes("Light") ? "hc-light" : "hc-black") : theme.includes("Light") ? "vs" : "vs-dark";
  await page.waitForFunction((c) => {
    const w = document.querySelector(".monaco-workbench");
    return w && w.classList.contains(c) && (c !== "vs" || !w.classList.contains("vs-dark"));
  }, cls, { timeout: 15000 });
  await page.waitForTimeout(400); // the webview's colours follow a beat later
}

/** The frames that hold a Graphene graph page (the sidebar's, the panel's), found by their content. */
export async function graphFrames(page) {
  const found = [];
  for (const f of page.frames()) {
    try {
      if (await f.evaluate(() => Boolean(document.querySelector("#svg #view") && document.querySelector("#goal")))) found.push(f);
    } catch { /* a frame that is going away */ }
  }
  return found;
}

/** Wait for a graph frame that has drawn at least `min` tasks. */
export async function waitForGraph(page, { min = 1, timeout = 60000 } = {}) {
  const t0 = Date.now();
  while (Date.now() - t0 < timeout) {
    for (const f of await graphFrames(page)) {
      const n = await f.evaluate(() => document.querySelectorAll("#view g.task").length).catch(() => 0);
      if (n >= min) return { frame: f, tasks: n, ms: Date.now() - t0 };
    }
    await page.waitForTimeout(100);
  }
  throw new Error(`no graph with ${min} task(s) in ${timeout} ms`);
}

/** What a graph frame shows: the goal, the counts, the tasks' titles and states. */
export async function readGraph(frame) {
  return frame.evaluate(() => ({
    goal: document.querySelector("#goal")?.textContent ?? "",
    counts: document.querySelector("#counts")?.textContent ?? "",
    notice: document.querySelector("#notice:not([hidden])")?.textContent ?? "",
    tasks: [...document.querySelectorAll("#view g.task")].map((g) => ({
      id: g.getAttribute("data-id"),
      title: g.querySelector("text.title")?.textContent ?? "",
      sub: g.querySelector("text.sub")?.textContent ?? "",
      state: [...g.classList].filter((c) => c !== "task" && c !== "selected").join(" "),
      forks: g.querySelectorAll("g.fork").length,
    })),
  }));
}

/** The smallest text drawn in a graph frame, in CSS px as rendered: font size times the SVG's scale. */
export async function smallestText(frame) {
  return frame.evaluate(() => {
    const svg = document.querySelector("#svg");
    const m = new DOMMatrix(getComputedStyle(svg).transform);
    const k = Math.hypot(m.a, m.b) || 1;
    let min = Infinity, which = "";
    for (const t of document.querySelectorAll("#svg text")) {
      const px = parseFloat(getComputedStyle(t).fontSize) * k;
      if (px < min) { min = px; which = `${t.getAttribute("class")}: ${t.textContent}`; }
    }
    return { px: Number.isFinite(min) ? Math.round(min * 100) / 100 : null, scale: Math.round(k * 1000) / 1000, which,
             canvas: document.querySelector("#canvas")?.clientWidth ?? 0 };
  });
}

/** Every frame's text, for a reader with no screen. */
export async function framesText(page) {
  const out = [];
  for (const f of page.frames()) {
    let text = "";
    try { text = await f.evaluate(() => document.body?.innerText ?? ""); } catch { continue; }
    text = text.replace(/\n{3,}/g, "\n\n").trim();
    if (text) out.push({ url: f.url().slice(0, 80), text });
  }
  return out;
}

/** A screenshot of the window. */
export async function shot(page, file) {
  mkdirSync(path.dirname(file), { recursive: true });
  await page.screenshot({ path: file });
  return file;
}

/** A fresh scratch dir under SHORT. */
export function scratch(prefix = "graphene-e2e-") {
  return mkdtempSync(path.join(SHORT, prefix));
}

export function readJson(file) {
  return JSON.parse(readFileSync(file, "utf8"));
}
