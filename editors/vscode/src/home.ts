// Home, Graphene's side bar: everything a person does, with a click. Set the folder up, open the graph, start
// the agents on the plan your coding agent proposed, and review what each one did before it lands. The host
// runs graphene as the person (Session); the page (home/main.ts) draws what cards.ts says, and every message it
// sends is checked first (cards.ts checkHome): nothing from the page reaches a shell but as an argument.
import * as vscode from "vscode";
import * as C from "./commands.ts";
import { checkHome, home, unanswered, type FromHome } from "./home/cards.ts";
import { EXACT, WHO } from "./home/who.ts";
import { keyTrouble, needs, tryAgain, widen } from "./needs.ts";
import type { Session } from "./session.ts";
import type { Task } from "./state.ts";

type Last = { n: number; lines: string[]; bad: boolean; key?: boolean };

export class HomeHost implements vscode.WebviewViewProvider {
  private views = new Set<vscode.WebviewView>();
  /** What Home is doing now ("Setting up this folder…"), and what the last thing it did said, for the page. */
  private busy = "";
  private last: Last = { n: 0, lines: [], bad: false };
  /** `board:` as `graphene config` last said it: on, with every task to review and auto off, is Exact.
   *  ponytail: read when Home opens and when its switch moves, so a `config set board` typed in a terminal
   *  shows here at the next of those; the snapshot would have to carry the setting to follow it live. */
  private board = "";
  /** The repository's workflows as `graphene workflow --json` last listed them, and the inputs the last one
   *  proposed here was given (Save as workflow offers them). Read when Home opens and after a run or a save. */
  private workflows: C.Workflow[] = [];
  private lastWorkflow: { name: string; inputs: Record<string, string> } | null = null;
  private readonly context: vscode.ExtensionContext;
  private readonly session: Session;
  /** Home came into view, or went out of it: the graph's tab opens with it (graph.ts sidebar). */
  private readonly shown: (on: boolean) => void;

  constructor(context: vscode.ExtensionContext, session: Session, shown: (on: boolean) => void = () => {}) {
    this.context = context;
    this.session = session;
    this.shown = shown;
    session.onDidChange(() => this.push());
    session.onDidSee(() => this.push());
    // the graph's header asks for these by name: its Save as workflow button, and its switch, which moves as Home's
    // does (Exact's settings go back with it). Home may never have opened: the board setting is read first.
    context.subscriptions.push(vscode.commands.registerCommand("graphene.saveWorkflow", () => this.saveWorkflow()),
                               vscode.commands.registerCommand("graphene.stopAfter", async (flag?: unknown) => { await this.readBoard(); return this.setStopAfter(flag === true); }));
  }

  resolveWebviewView(view: vscode.WebviewView) {
    const roots = [vscode.Uri.joinPath(this.context.extensionUri, "dist"), vscode.Uri.joinPath(this.context.extensionUri, "media")];
    view.webview.options = { enableScripts: true, localResourceRoots: roots };
    view.webview.html = this.html(view.webview);
    this.views.add(view);
    view.onDidDispose(() => this.views.delete(view));
    const seen = () => this.shown(view.visible); // a click on Graphene's icon lands on the graph
    seen();
    view.onDidChangeVisibility(seen);
    view.webview.onDidReceiveMessage((m: unknown) => {
      const msg = checkHome(m, this.session.state, this.workflows);
      if (!msg) return;
      if (msg.type === "ready") return void Promise.all([this.readBoard(), this.readWorkflows()]).then(() => this.push());
      void this.act(msg);
    });
  }

  private push() {
    const s = this.session.state;
    const h = s ? home(s, this.session.seen, this.exact, this.workflows) : null;
    if (h && this.busy) for (const section of h.sections) for (const button of section.buttons) {
      if (button.act === "startAll" || button.act === "discardAll") button.off = true;
    }
    const model = { type: "home", status: this.session.status, home: h, review: s?.envelope.review === "every", exact: this.exact, busy: this.busy,
                    last: this.last, cursor: vscode.env?.appName.includes("Cursor") === true }; // no env: the tests' stand-in for vscode
    const n = s ? needs(s).length : 0;
    for (const v of this.views) {
      v.badge = n ? { value: n, tooltip: n === 1 ? "1 thing needs you" : `${n} things need you` } : undefined;
      void v.webview.postMessage(model);
    }
  }

  /** Exact is three settings that exist, all holding: every open item shown (`board: on`), every finished task
   *  to review (`review: every`), nothing accepted for you (`auto: off`). Home's own Start then waits for your
   *  answers; `graphene plan accept` in a terminal still takes the defaults (the engine's rule, not changed here). */
  private get exact(): boolean {
    const e = this.session.state?.envelope;
    return this.board === "on" && e?.review === "every" && e.auto === "off";
  }

  private async readBoard() {
    const out = await this.session.run(["config"]);
    if (out.code === 0) this.board = /^board:\s*(\S+)/m.exec(out.stdout)?.[1] ?? "";
  }

  private async readWorkflows() {
    const out = await this.session.run(C.workflows());
    if (out.code !== 0) return; // an older graphene has no such command: no workflows are listed
    ({ workflows: this.workflows, last: this.lastWorkflow } = C.parseWorkflows(out.stdout));
  }

  /** Run a workflow: ask for each input (its default offered), then `graphene workflow NAME -i …` proposes the
   *  plan with its holes filled and no planner call. It is a suggested plan that waits for Start, whatever the
   *  switch says: its command steps are shell lines from a file, read before they run (auto holds such a step
   *  back too: a step with no files never fits its limits). */
  private async runWorkflow(name: string) {
    const w = this.workflows.find((x) => x.name === name);
    if (!w || this.busy) return;
    const inputs: Record<string, string> = {};
    for (const i of w.inputs) {
      const v = await vscode.window.showInputBox({
        title: C.plain(`${name}: ${i.name}`), prompt: C.plain(`“${i.name}” for the workflow ${name}`), value: i.default ?? "", ignoreFocusOut: true,
        validateInput: (x) => (x.trim() ? undefined : "it needs a value"),
      });
      if (v === undefined) return; // Esc: nothing is proposed
      inputs[i.name] = v.trim();
    }
    this.busy = `Proposing ${name}…`;
    this.say([]);
    this.push();
    const out = await this.session.run(C.workflow(name, inputs));
    this.busy = "";
    if (out.code !== 0) this.say([out.code === -1 ? "graphene was not found" : C.refusal(out.stderr, out.stdout)], { bad: true });
    else this.say([`${name}: its plan is proposed, with no planner call. Read it, then start.`]);
    await this.readWorkflows();
    await this.session.refresh();
    this.push();
  }

  /** Save as workflow, from the graph's header: its name, then what varies from run to run as `name=value` pairs
   *  (each value becomes an input, a hole in the text), and `graphene workflow NAME --save` writes workflows/NAME.md. */
  private async saveWorkflow() {
    if (!this.session.state?.tasks.length) return void vscode.window.showInformationMessage("There is no graph to save yet.");
    await this.readWorkflows();
    const named = await vscode.window.showInputBox({
      title: "Save as workflow", prompt: "Its name: it is written to workflows/<name>.md", value: this.lastWorkflow?.name ?? "", placeHolder: "fix-issue",
      ignoreFocusOut: true, validateInput: (v) => (/^[A-Za-z][A-Za-z0-9_-]*$/.test(v.trim()) ? undefined : "a letter, then letters, digits, - and _"), // the engine's own rule (workflow.py NAME)
    });
    const name = named?.trim();
    if (!name) return;
    const varies = await vscode.window.showInputBox({
      title: "Save as workflow", prompt: "What varies from run to run? name=value pairs, a comma between. Each value becomes an input. Empty: nothing varies.",
      value: Object.entries(this.lastWorkflow?.inputs ?? {}).map(([k, v]) => `${k}=${v}`).join(", "), placeHolder: "issue=48, test=pytest -k export",
      ignoreFocusOut: true, validateInput: (v) => (C.pairs(v) ? undefined : "write name=value, with a comma between pairs"),
    });
    const inputs = varies === undefined ? null : C.pairs(varies);
    if (!inputs) return;
    let out = await this.session.run(C.saveWorkflow(name, inputs));
    if (out.code !== 0 && /--force/.test(`${out.stderr}${out.stdout}`)) { // one by that name is there: replacing it is the person's to say
      const ok = await vscode.window.showWarningMessage(`workflows/${name}.md is there already. Replace it?`, { modal: true }, "Replace");
      if (!ok) return;
      out = await this.session.run(C.saveWorkflow(name, inputs, true));
    }
    if (out.code !== 0) return void vscode.window.showErrorMessage(C.plain(out.code === -1 ? "graphene was not found" : C.refusal(out.stderr, out.stdout)));
    await this.readWorkflows();
    this.push();
    const folder = this.session.folder;
    const open = await vscode.window.showInformationMessage(`Saved as workflows/${name}.md. Home lists it under Workflows.`, "Open It");
    if (open && folder) void vscode.window.showTextDocument(vscode.Uri.joinPath(folder.uri, "workflows", `${name}.md`));
  }

  /** The switch: on sets the three settings and keeps what review and auto were; off puts them back and forgets
   *  them. All three or none: a setting graphene refuses takes the others back. One move of the switch at a time. */
  private async setExact(on: boolean) {
    const e = this.session.state?.envelope;
    if (!e || this.switching || on === this.exact) return this.push();
    this.switching = true;
    try {
      const KEY = "graphene.exact.before";
      if (on) await this.context.workspaceState.update(KEY, { review: e.review, auto: e.auto });
      const before = this.context.workspaceState.get<{ review: string; auto: string }>(KEY);
      const set = async (want: [string, string][]) => {
        for (const [key, value] of want) if ((await this.session.run(C.setting(key, value))).code !== 0) return false;
        return true;
      };
      const off: [string, string][] = [["board", "auto"], ["review", before?.review ?? e.review], ["auto", before?.auto ?? e.auto]];
      const ok = await set(on ? [["board", "on"], ["review", "every"], ["auto", "off"]] : off);
      if (on && !ok) await set(off);
      if (!on || !ok) await this.context.workspaceState.update(KEY, undefined);
      await this.readBoard();
      await this.session.refresh();
      this.say(!ok ? ["Exact did not change: graphene refused a setting."] : on ? [`${EXACT}.`] : ["Exact is off: what you leave unanswered takes its default at Start."],
               { bad: !ok });
    } finally {
      this.switching = false;
      this.push();
    }
  }
  private switching = false;

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
      case "setup": return this.setUp(m.arg!, m.flag === true);
      // Exact: Start waits for every answer; and a question with no default stops the run either way
      case "startAll": return (this.exact && s.state?.questions.length) || (s.state && unanswered(s.state)) ? undefined : this.start();
      case "exact": return this.setExact(m.flag === true);
      case "stopAfter": return this.setStopAfter(m.flag === true);
      case "runWorkflow": return this.runWorkflow(m.arg!);
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

  /** The one switch (decision 225). On, a plan your agent proposes waits for Start; off is auto: what fits your
   *  limits is accepted and runs. It is the `auto` setting, so the terminal and the graph's header see the same one. */
  private async setStopAfter(on: boolean) {
    if (!on && this.exact) await this.setExact(false); // Exact holds `auto: off`: its three settings go back together, then the switch moves
    if (!(await this.session.act(C.stopAfter(on)))) return;
    this.say([on ? "Stop after the plan is on: a plan your agent proposes waits here for you to start it."
      : "Stop after the plan is off: a plan that fits your limits runs without waiting. A question with no default still stops it."]);
    this.push();
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
  <link rel="stylesheet" href="${uri("media", "tokens.css")}">
  <link rel="stylesheet" href="${uri("media", "home.css")}">
  <title>Graphene</title>
</head>
<body>
  <script nonce="${nonce}" src="${uri("dist", "home.js")}"></script>
</body>
</html>`;
  }
}
