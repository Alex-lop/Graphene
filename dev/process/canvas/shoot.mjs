// Watch the Demo at one moment, in real VS Code at 1920x1050, in dark and in light: the evidence for the canvas
// run's look (dev/SCOPE.md, leaf 2). The moment is the first frame in which three tasks are working with their
// attempts fanned out, so a before and an after show the same store. No model and no network: the demo replays
// a scripted stand-in.
//   cd editors/vscode && npm run package && cd e2e && npm ci      # once: the .vsix and the harness
//   node dev/process/canvas/shoot.mjs before|after [moment]       # writes NAME-demo-1920x1050-THEME.png here
//   node dev/process/canvas/shoot.mjs readme                      # writes editors/vscode/media/graph.png
// `moment` is `working` (the default) or `done` (every task landed). `readme` is the README's picture: dark, the
// graph's page alone at twice its size, so its words stay sharp shrunk to the README's width, in a 1260x895 window:
// as tall as the pane's Scope down to Stopped, and no taller, so no part is cut at the foot (read the picture after:
// a pane that says more needs the height again). At the frame in which three tasks are done and the fourth works
// with its attempts, "CLI prints the top words" selected: its check failed before the work and passed after it, and
// a write outside its files was stopped. A moment gone by the shot throws: run it again.
import path from "node:path";
import { fileURLToPath } from "node:url";
import * as L from "../../../editors/vscode/e2e/lib.mjs";

const name = process.argv[2] || "after", readme = name === "readme", moment = readme ? "readme" : process.argv[3] || "working";
const size = readme ? { width: 1260, height: 895, args: ["--force-device-scale-factor=2"] } : { width: 1920, height: 1050 };
const out = path.dirname(fileURLToPath(import.meta.url));
const app = await L.findApp("code");
if (!app) { console.error("shoot: no VS Code to drive (set VSCODE_EXECUTABLE)"); process.exit(1); }
const graphene = L.findGraphene(), vsix = L.findVsix();

for (const theme of readme ? ["dark"] : ["dark", "light"]) {
  const base = L.scratch("canvas-");
  const profile = L.makeProfile(base, { graphene, theme: L.THEMES[theme] });
  L.installVsix(app, profile, vsix);
  const fx = L.makeFixture(path.join(base, "wordkit"), graphene);
  const session = await L.launch(app, profile, fx.dir, size);
  try {
    const page = session.page;
    await L.palette(page, "View: Close Primary Side Bar"); // the canvas takes the window, as the target does
    await L.palette(page, "Graphene: Watch the Demo");
    const { frame } = await L.waitForGraph(page, { min: 3, timeout: 90000 });
    const at = moment === "done"
      ? () => { const t = [...document.querySelectorAll("#view g.task")]; return t.length >= 3 && t.every((g) => g.classList.contains("st-done")); }
      : readme
      ? () => document.querySelectorAll("#view g.task.st-done").length === 3 && document.querySelectorAll("#view g.task.st-running g.fork").length >= 3
      : () => document.querySelectorAll("#view g.task.st-running").length >= 3 && document.querySelectorAll("#view g.fork").length >= 9;
    await frame.waitForFunction(at, null, { timeout: 180000, polling: 100 });
    if (readme) {
      await frame.locator('#view g.task.st-done[aria-label^="CLI prints the top words:"] rect.box').click();
      await frame.waitForFunction(() => document.querySelector("#details button.tab.on")?.textContent === "Scope", null, { timeout: 10000 });
      await frame.locator("#canvas").press("f"); // the plan fitted beside the pane; choosing a card moves nothing
      await frame.locator("#canvas").hover({ position: { x: 8, y: 8 } }); // the pointer off the cards: no hover's dots
    }
    await page.waitForTimeout(600); // the boxes have glided to their places
    if (readme && !(await frame.evaluate(at))) throw new Error("shoot: the fourth task landed before the shot: run it again");
    const file = readme ? path.join(L.ROOT, "editors", "vscode", "media", "graph.png")
      : path.join(out, `${name}-demo-1920x1050-${theme}${moment === "working" ? "" : `-${moment}`}.png`);
    if (readme) { // the page from under its tab's title to its foot: the tab's strip overlaps its top
      const box = await (await frame.frameElement()).boundingBox();
      const top = (await page.locator(".editor-group-container.active .editor-container").boundingBox()).y;
      await page.screenshot({ path: file, clip: { x: box.x, y: top, width: box.width, height: box.y + box.height - top } });
    } else await L.shot(page, file);
    console.log(`shoot: ${path.relative(process.cwd(), file)} (${session.size.width}x${session.size.height})`);
  } finally {
    await L.close(session);
  }
}
