// The graph's host: one webview panel (Graphene: Show Plan Graph) and the sidebar's Graph view share the
// same page, dist/graph.js, under a strict CSP; the page asks, the host runs graphene and pushes the state.
// The host checks every message the page sends: a known act, an id the plan has, a fork the task has;
// nothing from the page reaches a shell, each act is a command's argument or a graphene argv.
import * as vscode from "vscode";
import * as C from "./commands.ts";
import { check, type Act } from "./graph/check.ts";
import type { Session } from "./session.ts";


export class GraphHost implements vscode.WebviewViewProvider {
  private panel: vscode.WebviewPanel | null = null;
  private views = new Set<vscode.Webview>();
  private sidebars = new Set<vscode.WebviewView>();
  private context: vscode.ExtensionContext;
  private session: Session;
  private title: string;
  private closed = new vscode.EventEmitter<void>();
  /** The panel was closed (Watch the Demo ends its replay then). */
  readonly onDidClose = this.closed.event;

  constructor(context: vscode.ExtensionContext, session: Session, title = "Graphene") {
    this.context = context;
    this.session = session;
    this.title = title;
    session.onDidChange(() => this.push());
  }

  /** The panel, made or revealed; with ``select`` the page selects that task. */
  show(select?: string) {
    if (!this.panel) {
      const panel = vscode.window.createWebviewPanel("graphene.graphPanel", this.title, vscode.ViewColumn.Active, {
        enableScripts: true, retainContextWhenHidden: true,
        localResourceRoots: [vscode.Uri.joinPath(this.context.extensionUri, "dist"), vscode.Uri.joinPath(this.context.extensionUri, "media")],
      });
      this.panel = panel;
      panel.iconPath = vscode.Uri.joinPath(this.context.extensionUri, "media", "graphene.svg");
      const webview = panel.webview; // held now: a disposed panel throws on `webview`
      this.attach(webview);
      panel.onDidDispose(() => {
        this.views.delete(webview);
        if (this.panel === panel) this.panel = null;
        this.closed.fire();
      });
    } else {
      this.panel.reveal();
    }
    if (select) void this.panel.webview.postMessage({ type: "select", id: select });
  }

  resolveWebviewView(view: vscode.WebviewView) {
    view.webview.options = {
      enableScripts: true,
      localResourceRoots: [vscode.Uri.joinPath(this.context.extensionUri, "dist"), vscode.Uri.joinPath(this.context.extensionUri, "media")],
    };
    this.attach(view.webview);
    this.sidebars.add(view);
    view.onDidDispose(() => { this.views.delete(view.webview); this.sidebars.delete(view); });
  }

  /** Whether a graph is on screen: the poll runs only then. */
  get open(): boolean {
    return Boolean(this.panel?.visible) || [...this.sidebars].some((v) => v.visible);
  }

  dispose() {
    this.closed.dispose();
  }

  private attach(webview: vscode.Webview) {
    webview.html = this.html(webview);
    this.views.add(webview);
    webview.onDidReceiveMessage((m: unknown) => {
      const msg = check(m, this.session);
      if (!msg) return;
      if (msg.type === "ready") return this.push(webview);
      // a replay is watched: check() refuses its acts once its state says `replay`, and before that state is
      // read (or after a read fails) the acts that take no id would run in the person's folder
      if (this.session.own) return;
      return this.act(msg);
    });
  }

  private push(only?: vscode.Webview) {
    const message = this.session.state // an empty plan is a state too: the page says so under the goal
      ? { type: "state", state: this.session.state }
      : { type: "status", status: this.session.status };
    for (const w of only ? [only] : this.views) void w.postMessage(message);
  }

  private act(m: { act: Act; id: string; target?: string; fork?: string }) {
    const arg = { id: m.id };
    switch (m.act) {
      case "add-after": return run("addStep", { ...arg, after: m.id });
      case "add-under": return run("addStep", m.id ? { ...arg, under: m.id } : undefined);
      case "link": return m.target ? this.session.act(C.link(m.id, m.target)) : undefined;
      case "unlink": return m.target ? this.session.act(C.unlink(m.target, m.id)) : undefined;
      case "edit": return run("editStep", arg);
      case "drop": return run("dropStep", arg);
      case "accept": return run("accept", arg);
      case "tell": return run("tell", arg);
      case "run": return run("runReady");
      case "stop": return run("stop");
      case "auto": return run("auto");
      case "cockpit": return run("openCockpit");
      case "openDiff": return run("openDiff", m.fork ? { ...arg, fork: m.fork } : arg);
      case "compareForks": return run("compareForks", arg);
      case "pickFork": return m.fork ? run("pickFork", { ...arg, fork: m.fork }) : undefined;
      case "signOff": return run("signOff", arg);
      case "answer": return run("answer", m.target !== undefined ? { ...arg, option: m.target } : arg);
      case "handBack": return run("handBack", arg);
    }
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
  <link rel="stylesheet" href="${uri("media", "graph.css")}">
  <title>Graphene</title>
</head>
<body>
  <header>
    <div id="replay" hidden></div>
    <div id="goal">Graphene</div>
    <div id="counts"></div>
    <div id="auto" hidden></div>
    <div id="actions"></div>
  </header>
  <main>
    <div id="canvas">
      <svg id="svg" xmlns="http://www.w3.org/2000/svg"><g id="view"><g id="bands"></g><g id="edges"></g><g id="tasks"></g><g id="goalg" class="goal"></g><path id="wire" class="wire"></path></g></svg>
      <div id="lanes" hidden></div>
      <div id="notice" hidden></div>
      <button id="to-goal" class="quiet" hidden></button>
    </div>
    <aside id="details" hidden></aside>
  </main>
  <footer id="hint"></footer>
  <div id="help" hidden></div>
  <script nonce="${nonce}" src="${uri("dist", "graph.js")}"></script>
</body>
</html>`;
  }
}

/** A command of the extension's, or a message that it is not there yet: never a throw from the page. */
async function run(name: string, arg?: unknown) {
  const all = await vscode.commands.getCommands(true);
  const id = `graphene.${name}`;
  if (!all.includes(id)) return vscode.window.showInformationMessage(`Graphene: ${name} is not built yet.`);
  return arg === undefined ? vscode.commands.executeCommand(id) : vscode.commands.executeCommand(id, arg);
}
