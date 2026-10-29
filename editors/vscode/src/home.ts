// Home, the first view in Graphene's side bar: everything a person does, with a click. Set the folder up, say
// what you want, start the agents on the suggested plan, and review what each one did before it lands. The host
// runs graphene as the person (Session); the page (home/main.ts) draws what cards.ts says, and every message it
// sends is checked first (cards.ts checkHome): nothing from the page reaches a shell but as an argument.
import * as vscode from "vscode";
import * as C from "./commands.ts";
import { checkHome, home, said, type FromHome } from "./home/cards.ts";
import { WHO } from "./home/who.ts";
import { keyTrouble, needs, tryAgain, widen } from "./needs.ts";
import type { Session } from "./session.ts";
import type { Task } from "./state.ts";

type Last = { n: number; lines: string[]; bad: boolean; asked?: string; key?: boolean };

export class HomeHost implements vscode.WebviewViewProvider {
  private views = new Set<vscode.WebviewView>();
  private planning: AbortController | null = null;
  /** What Home is doing now ("Planning…"), and what the last thing it did said, for the page. */
  private busy = "";
  private last: Last = { n: 0, lines: [], bad: false };
  /** What was last planned here: the headline once the plan's news no longer says it (an ask sets no goal). */
  private asked = "";
  private readonly context: vscode.ExtensionContext;
  private readonly session: Session;

  constructor(context: vscode.ExtensionContext, session: Session) {
    this.context = context;
    this.session = session;
    session.onDidChange(() => this.push());
    session.onDidSee(() => this.push());
  }

  resolveWebviewView(view: vscode.WebviewView) {
    const roots = [vscode.Uri.joinPath(this.context.extensionUri, "dist"), vscode.Uri.joinPath(this.context.extensionUri, "media")];
    view.webview.options = { enableScripts: true, localResourceRoots: roots };
    view.webview.html = this.html(view.webview);
    this.views.add(view);
    view.onDidDispose(() => this.views.delete(view));
    view.webview.onDidReceiveMessage((m: unknown) => {
      const msg = checkHome(m, this.session.state);
      if (!msg) return;
      if (msg.type === "ready") return this.push();
      void this.act(msg);
    });
  }

  private push() {
    const s = this.session.state;
    const h = s ? home(s, this.session.seen) : null;
    if (h && !s?.goal && this.asked) h.goal = this.asked; // whole: the news cuts what was asked at 60 characters
    const model = { type: "home", status: this.session.status, home: h, review: s?.envelope.review === "every", busy: this.busy,
                    planning: Boolean(this.planning), last: this.last };
    const n = s ? needs(s).length : 0;
    for (const v of this.views) {
      v.badge = n ? { value: n, tooltip: n === 1 ? "1 thing needs you" : `${n} things need you` } : undefined;
      void v.webview.postMessage(model);
    }
  }

  private say(lines: string[], more: Partial<Last> = {}) {
    this.last = { n: this.last.n + 1, lines, bad: false, ...more };
  }

  /** Home's own pages are on screen: the extension's poll runs while one is, when the stream is not live. */
  get open(): boolean {
    return [...this.views].some((v) => v.visible);
  }

  private async act(m: Extract<FromHome, { type: "act" }>) {
    const s = this.session;
    // one Set Up, Start or Discard at a time: a double click is one click
    if (this.busy && (m.act === "setup" || m.act === "startAll" || m.act === "discardAll")) return;
    const task = () => s.tasks().find((t) => t.id === m.id);
    const run = (name: string, arg?: unknown) => vscode.commands.executeCommand(`graphene.${name}`, arg);
    switch (m.act) {
      case "ask": return this.ask(m.arg!);
      case "cancel": return this.planning?.abort();
      case "setup": return this.setUp(m.arg!, m.flag === true);
      case "startAll": return this.start();
      case "discardAll": return this.discard();
      case "run": return void s.terminal("graphene run", C.runReady());
      case "stop": return s.act(C.stop());
      case "drop": return run("dropStep", { id: m.id });
      case "answer": return run("answer", m.arg !== undefined ? { id: m.id, option: m.arg } : { id: m.id });
      case "openDiff": return run("openDiff", { id: m.id });
      case "compare": return run("compareForks", { id: m.id });
      case "keep": return run("pickFork", { id: m.id, fork: m.arg });
      case "approve": return run("signOff", { id: m.id }); // diff.ts asks first when its changes were never opened
      case "sendBack": { const t = task(); return t && this.sendBack(t); }
      case "offer": { const t = task(); return t && Object.hasOwn(t.offers, m.arg!) && s.act(t.offers[m.arg!]!); }
      case "tryAgain": return void s.terminal("graphene run", tryAgain(m.id));
      case "allow": return s.act(task()?.offers.w ?? widen(m.id));
      case "message": return run("tell", { id: m.id });
      case "markDone": return run("markDone", { id: m.id });
      case "showGraph": return run("showGraph", m.id || undefined);
      case "demo": return run("watchDemo");
      case "install": return run("install");
      case "setKey": return run("setKey", m.arg);
      case "refresh": return s.refresh();
      case "openFolder": return vscode.commands.executeCommand("workbench.action.files.openFolder");
    }
  }

  /** `graphene ask`: the planner suggests tasks, and nothing runs until the person starts them. Cancel stops it. */
  private async ask(text: string) {
    if (this.planning) return;
    const stop = new AbortController();
    this.planning = stop;
    this.busy = "Planning: the planner is reading your repository…";
    this.push();
    const out = await this.session.run(C.ask(text), undefined, stop.signal);
    this.planning = null;
    this.busy = "";
    if (stop.signal.aborted) this.say(["Planning stopped."]);
    else if (out.code !== 0) {
      const why = out.code === -1 ? "graphene was not found" : C.refusal(out.stderr, out.stdout);
      this.say([why], { bad: true, key: keyTrouble(why).key });
    } else {
      this.asked = text;
      this.say(said(out.stdout), { asked: text });
    }
    this.push();
    void this.session.refresh();
  }

  /** Set Up: one AI plans and does the work (`graphene init` with both named, so it asks nothing), then, unless
   *  the person unticked it, every finished task waits for their approval before it lands (`review: every`). */
  private async setUp(who: string, review: boolean) {
    this.busy = "Setting up this folder…";
    this.say([]);
    this.push();
    const out = await this.session.run(C.initWith(who));
    if (out.code === 0 && review) await this.session.run(C.setting("review", "every"));
    this.busy = "";
    if (out.code !== 0) {
      const why = out.code === -1 ? "graphene was not found" : C.firstLine(out.stderr, out.stdout);
      this.say([why], { bad: true, key: keyTrouble(why).key || (who === "nemotron" && /key/i.test(why)) });
    } else {
      const label = WHO.find((w) => w.word === who)?.label ?? who;
      const warn = `${out.stdout}\n${out.stderr}`.split(/\r?\n/).filter((l) => /no commit yet|^warning:/.test(l.trim()));
      this.say([`${label} plans and does the work here.`, ...(review ? ["Each finished task waits for your approval before it lands."] : []), ...warn]);
    }
    this.session.moved();
    await this.session.refresh();
  }

  /** Start: the suggested tasks accepted, then an agent on each that is ready, in a terminal the person can watch. */
  private async start() {
    this.say([]); // the planner's words were about the plan just started
    this.busy = "Starting…";
    this.push();
    try {
      if (await this.session.act(C.acceptAll())) this.session.terminal("graphene run", C.runReady());
    } finally {
      this.busy = "";
      this.push();
    }
  }

  /** Discard all: every suggested task and sub-goal, in one drop, so one that another waits on goes with it
   *  (`graphene plan undo` puts them all back). */
  private async discard() {
    const s = this.session.state;
    const tasks = (s?.tasks ?? []).filter((t) => t.state === "proposed");
    const ids = [...tasks.map((t) => t.id), ...(s?.goals ?? []).filter((g) => g.state === "proposed").map((g) => g.id)];
    if (!ids.length) return;
    const ok = await vscode.window.showWarningMessage(`Discard the ${tasks.length} suggested task${tasks.length === 1 ? "" : "s"}?`,
                                                      { modal: true }, "Discard");
    if (ok && await this.session.act(C.dropAll(ids))) this.say([]);
  }

  /** Send back: what is wrong, in the person's words, to whoever takes the task next (`graphene node reopen`). */
  private async sendBack(t: Task) {
    const note = await vscode.window.showInputBox({
      prompt: C.plain(`What is wrong with “${t.title}”? The next agent on it reads this.`), placeHolder: "the test only covers one word",
      ignoreFocusOut: true, validateInput: (v) => (v.trim() ? undefined : "say what is wrong"),
    });
    if (!note?.trim() || !(await this.session.act(C.reopen(t.id, note.trim())))) return;
    const again = await vscode.window.showInformationMessage(C.plain(`“${t.title}” goes back to an agent with your note.`), "Run It Now");
    if (again) this.session.terminal("graphene run", tryAgain(t.id));
  }

  private html(webview: vscode.Webview): string {
    const uri = (...p: string[]) => webview.asWebviewUri(vscode.Uri.joinPath(this.context.extensionUri, ...p));
    const nonce = Array.from({ length: 24 }, () => "abcdefghijklmnopqrstuvwxyz0123456789"[Math.floor(Math.random() * 36)]).join("");
    return `<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src ${webview.cspSource}; script-src 'nonce-${nonce}';">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <link rel="stylesheet" href="${uri("media", "home.css")}">
  <title>Graphene</title>
</head>
<body>
  <script nonce="${nonce}" src="${uri("dist", "home.js")}"></script>
</body>
</html>`;
  }
}
