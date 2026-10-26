// The graph's host: one webview panel (Graphene: Show Plan Graph) and the sidebar's Graph view share the
// same page, dist/graph.js, under a strict CSP; the page asks, the host runs graphene and pushes the state.
import * as vscode from "vscode";
import * as C from "./commands.ts";
import type { Session } from "./extension.ts";

// link: id is A, target B, and B waits on A; unlink: id is B, target the A it stops waiting on
type Act = "add-after" | "add-under" | "link" | "unlink" | "edit" | "drop" | "accept" | "tell" | "run" | "auto" | "cockpit";
type FromPage = { type: "ready" } | { type: "act"; act: Act; id: string; target?: string };

export class GraphHost implements vscode.WebviewViewProvider {
  private panel: vscode.WebviewPanel | null = null;
  private views = new Set<vscode.Webview>();
  private sidebars = new Set<vscode.WebviewView>();
  private context: vscode.ExtensionContext;
  private session: Session;

  constructor(context: vscode.ExtensionContext, session: Session) {
    this.context = context;
    this.session = session;
    session.onDidChange(() => this.push());
  }

  /** The panel, made or revealed; with ``select`` the page selects that task. */
  show(select?: string) {
    if (!this.panel) {
      this.panel = vscode.window.createWebviewPanel("graphene.graphPanel", "Graphene", vscode.ViewColumn.Active, {
        enableScripts: true, retainContextWhenHidden: true,
        localResourceRoots: [vscode.Uri.joinPath(this.context.extensionUri, "dist"), vscode.Uri.joinPath(this.context.extensionUri, "media")],
      });
      this.panel.iconPath = vscode.Uri.joinPath(this.context.extensionUri, "media", "graphene.svg");
      this.attach(this.panel.webview);
      this.panel.onDidDispose(() => { this.views.delete(this.panel!.webview); this.panel = null; });
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

  private attach(webview: vscode.Webview) {
    webview.html = this.html(webview);
    this.views.add(webview);
    webview.onDidReceiveMessage((m: FromPage) => {
      if (m.type === "ready") return this.push(webview);
      if (m.type === "act") return this.act(m);
    });
  }

  private push(only?: vscode.Webview) {
    const message = this.session.state // an empty plan is a state too: the page says so under the goal
      ? { type: "state", state: this.session.state }
      : { type: "status", status: this.session.status };
    for (const w of only ? [only] : this.views) void w.postMessage(message);
  }

  private act(m: { act: Act; id: string; target?: string }) {
    const arg = { id: m.id };
    switch (m.act) {
      case "add-after": return vscode.commands.executeCommand("graphene.addStep", { ...arg, after: true });
      case "add-under": return vscode.commands.executeCommand("graphene.addStep", m.id ? { ...arg, under: true } : undefined);
      case "link": return m.target ? this.session.act(C.link(m.id, m.target)) : undefined;
      case "unlink": {
        const b = this.session.state?.tasks.find((t) => t.id === m.id);
        return b && m.target ? this.session.act(C.unlink(m.target, b.id, b.needs)) : undefined;
      }
      case "edit": return vscode.commands.executeCommand("graphene.editStep", arg);
      case "drop": return vscode.commands.executeCommand("graphene.dropStep", arg);
      case "accept": return vscode.commands.executeCommand("graphene.accept", arg);
      case "tell": return vscode.commands.executeCommand("graphene.tell", arg);
      case "run": return vscode.commands.executeCommand("graphene.runReady");
      case "auto": return vscode.commands.executeCommand("graphene.auto");
      case "cockpit": return vscode.commands.executeCommand("graphene.openCockpit");
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
    <div id="goal">Graphene</div>
    <div id="counts"></div>
    <div id="auto" hidden></div>
    <div id="actions">
      <button id="b-add" title="graphene node add">Add step…</button>
      <button id="b-run" title="graphene run --parallel 4">Run ready</button>
      <button id="b-auto" title="graphene auto">Auto…</button>
      <button id="b-cockpit" title="graphene watch">Cockpit</button>
    </div>
  </header>
  <main>
    <div id="canvas">
      <svg id="svg" xmlns="http://www.w3.org/2000/svg"><g id="view"></g></svg>
      <div id="notice" hidden></div>
    </div>
    <aside id="details" hidden></aside>
  </main>
  <footer id="hint"></footer>
  <script nonce="${nonce}" src="${uri("dist", "graph.js")}"></script>
</body>
</html>`;
  }
}
