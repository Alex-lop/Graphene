// The graph's host: one webview panel, the graph's tab in the editor area, whose page is dist/graph.js under a
// strict CSP; the page asks, the host runs graphene and pushes the state.
// The host checks every message the page sends: a known act, an id the plan has, a fork the task has;
// nothing from the page reaches a shell, each act is a command's argument or a graphene argv.
import * as vscode from "vscode";
import * as C from "./commands.ts";
import { draftKey, draftOf, type Draft } from "./graph/draft.ts";
import { unanswered } from "./home/cards.ts";
import { check, type FromPage } from "./graph/check.ts";
import { beside, opens, seen, type Seen } from "./open.ts";
import type { Session } from "./session.ts";
import { unpriced } from "./state.ts";


export class GraphHost {
  private panel: vscode.WebviewPanel | null = null;
  private views = new Set<vscode.Webview>();
  private context: vscode.ExtensionContext;
  private session: Session;
  private title: string;
  private drafts: Draft[];
  private draftStore: string;
  private was: Seen | null = null; // the last snapshot read: a start is a change from it (open.ts)
  private shut = false; // a person closed the tab in this window: no start opens it again (open.ts)
  private wanted = false; // Graphene's side bar came into view, and no plan was read since
  private starting = false; // a Start is under way: a double click is one Start
  private closed = new vscode.EventEmitter<void>();
  /** The panel was closed (Watch the Demo ends its replay then). */
  readonly onDidClose = this.closed.event;

  constructor(context: vscode.ExtensionContext, session: Session, title = "Graphene") {
    this.context = context;
    this.session = session;
    this.title = title;
    this.draftStore = `graphene.drafts:${session.folder?.uri.fsPath ?? session.own ?? ""}`;
    const saved = context.workspaceState.get<unknown>(this.draftStore, []);
    this.drafts = (Array.isArray(saved) ? saved : []).map(draftOf).filter((d): d is Draft => d !== null);
    session.onDidChange(() => { this.push(); this.start(); });
  }

  /** The tab opens by itself, once for each start (the setting graphene.graph.openOnStart), without the
   *  keyboard and beside what a person has in front (in its group in Cursor), until a person closes it: then only asking opens it. A
   *  read that gave no plan is no snapshot: the next one is compared with the last that was, so a plan that
   *  could not be read for a moment is not a plan appearing. Never a replay's: Watch the Demo opens its own. */
  private start() {
    const s = this.session.state;
    if (!s || this.session.own) return;
    const now = seen(s);
    const on = vscode.workspace.getConfiguration("graphene").get<boolean>("graph.openOnStart", true);
    if (opens(this.was, now, { on, tab: this.panel !== null, shut: this.shut, sidebar: this.wanted })) this.show(undefined, true, this.wanted);
    this.wanted = false;
    this.was = now;
  }

  /** Graphene's side bar came into view (Home's host says so): the tab opens with it, as for a start, once a
   *  plan is read (this one, or the next if none is yet), so a click on the icon lands on the graph. Out of
   *  view before a plan was read, it no longer asks: a read an hour later does not open the tab. */
  sidebar(on = true) {
    this.wanted = on;
    if (on) this.start();
  }

  /** The panel, made or revealed; with ``select`` the page selects that task. ``quiet``: nobody asked for it
   *  (it opens by itself), so it does not take the keyboard, and it opens beside a file that is in front, not
   *  over it, but in Cursor (open.ts says why). ``whole``: the side bar opened it, so the keyboard is there, not in the file,
   *  and it takes the active group's whole width (beside, it would be the narrow lanes). Asked for, it opens
   *  in front of the active group and takes the keyboard. */
  show(select?: string, quiet = false, whole = false) {
    if (!this.panel) {
      const viewColumn = quiet && !whole && beside(front(), vscode.env.appName.includes("Cursor")) ? vscode.ViewColumn.Beside : vscode.ViewColumn.Active;
      const panel = vscode.window.createWebviewPanel("graphene.graphPanel", this.title, { viewColumn, preserveFocus: quiet }, {
        enableScripts: true, retainContextWhenHidden: true,
        localResourceRoots: [vscode.Uri.joinPath(this.context.extensionUri, "dist"), vscode.Uri.joinPath(this.context.extensionUri, "media")],
      });
      this.panel = panel;
      const icon = (f: string) => vscode.Uri.joinPath(this.context.extensionUri, "media", f);
      panel.iconPath = { light: icon("graphene-light.svg"), dark: icon("graphene-dark.svg") }; // an image: currentColor would be black
      const webview = panel.webview; // held now: a disposed panel throws on `webview`
      this.attach(webview);
      panel.onDidDispose(() => {
        this.views.delete(webview);
        if (this.panel === panel) this.panel = null;
        this.shut = true; // a person's close: the host never closes its own tab
        this.closed.fire();
      });
    } else {
      this.panel.reveal();
    }
    if (select) void this.panel.webview.postMessage({ type: "select", id: select });
  }

  /** Whether the graph is on screen: the poll runs only then. */
  get open(): boolean {
    return Boolean(this.panel?.visible);
  }

  dispose() {
    this.closed.dispose();
  }

  private attach(webview: vscode.Webview) {
    webview.html = this.html(webview);
    this.views.add(webview);
    webview.onDidReceiveMessage((m: unknown) => {
      const msg = check(m, this.session);
      if (!msg) { // a drawn task the host will not pass on is answered, so its page does not wait on it for ever
        const key = drawnKey(m);
        if (key) void webview.postMessage({ type: "said", key, ok: false, line: "Graphene was not asked: something this draft names has changed. Change it and it is offered again." });
        return;
      }
      if (msg.type === "ready") { this.pushDrafts(webview); return this.push(webview); }
      if (msg.type === "draft") {
        if (!this.session.own) this.keepDraft(msg.key, msg.draft);
        return;
      }
      // a replay is watched: check() refuses its acts once its state says `replay`, and before that state is
      // read (or after a read fails) the acts that take no id would run in the person's folder
      if (this.session.own) return;
      return this.act(msg, webview);
    });
  }

  private pushDrafts(only?: vscode.Webview) {
    for (const w of only ? [only] : this.views) void w.postMessage({ type: "drafts", drafts: this.session.own ? [] : this.drafts });
  }

  private keepDraft(key: string, draft: Draft | null) {
    this.drafts = this.drafts.filter((d) => d.key !== key);
    if (draft) this.drafts.push(draft);
    void this.context.workspaceState.update(this.draftStore, this.drafts);
    this.pushDrafts();
  }

  private push(only?: vscode.Webview) {
    const s = this.session.state;
    const message = s // an empty plan is a state too: the page says so under the goal
      ? { type: "state", state: unpriced(s), exact: this.exact } // a practice run or a replay: no cost to show
      : { type: "status", status: this.session.status };
    for (const w of only ? [only] : this.views) void w.postMessage(message);
    // ponytail: `graphene config` is read again at each push while Exact could hold Start (a suggestion, a
    // question, review every, auto off): the snapshot does not carry `board`, so Home's switch is followed so
    if (s && !this.session.own && s.questions.length && s.envelope.review === "every" && s.envelope.auto === "off"
        && s.tasks.some((t) => t.state === "proposed")) void this.readBoard();
  }

  /** `board:` as `graphene config` last said it: on, with every task to review and auto off, is Exact (home.ts). */
  private board = "";
  private boarding: Promise<void> | null = null; // one read at a time, as the session's own
  private get exact(): boolean {
    const e = this.session.state?.envelope;
    return this.board === "on" && e?.review === "every" && e.auto === "off";
  }
  private readBoard(): Promise<void> {
    return this.boarding ??= this.session.run(["config"]).then((out) => {
      const board = out.code === 0 ? /^board:\s*(\S+)/m.exec(out.stdout)?.[1] ?? "" : this.board;
      if (board !== this.board) { this.board = board; this.push(); } // the page's Start follows it
    }).finally(() => { this.boarding = null; });
  }

  /** What graphene answered to a change made on a page, for that page to show beside it: on the task's form
   *  (``id``), or on the drawn task (``key``), which is gone once the plan has it (``ok``). */
  private said(page: vscode.Webview, to: { id?: string; key?: string }, r: { ok: boolean; line: string }, made?: string | null) {
    if (this.views.has(page)) void page.postMessage({ type: "said", ...to, ok: r.ok, line: r.ok ? "" : r.line, made: made ?? undefined });
  }

  private async act(m: Extract<FromPage, { type: "act" }>, page: vscode.Webview) {
    const arg = { id: m.id };
    switch (m.act) {
      case "set": // one field of the pane's form: graphene's answer comes back to the form
        return m.field !== undefined && m.value !== undefined
          ? this.said(page, { id: m.id }, await this.session.change(C.editStep(m.id, m.field, m.field === "scope" ? C.globs(String(m.value)) : m.value))) : undefined;
      case "draw": { // a task drawn on the graph, whole: it joins the plan, or graphene says why not
        const d = m.draft;
        if (!d) return;
        const r = await this.session.change(C.byHand(d.title, d.parent, d.after ? [d.after] : [], d.files, d.check, d.approve));
        this.said(page, { key: d.key }, r, r.ok ? C.added(r.stdout) : null);
        if (r.ok) this.keepDraft(d.key, null);
        return;
      }
      case "add-after": case "add-under": {
        // "Fill it in for me": the drawn task's title to the planner, which proposes it with its files and
        // check, after the task it waits on or under its sub-goal
        const ok = await run("addStep", { ...(m.id ? arg : {}), [m.act === "add-after" ? "after" : "under"]: Boolean(m.id), sentence: m.sentence });
        return this.said(page, { key: m.key }, { ok: ok === true, line: ok === true ? "" : "the planner did not fill it in: its answer is in the notification" });
      }
      case "link": return m.target ? this.session.act(C.link(m.id, m.target)) : undefined;
      case "unlink": return m.target ? this.session.act(C.unlink(m.target, m.id)) : undefined;
      case "drop": return run("dropStep", arg);
      case "accept": return run("accept", arg);
      case "tell": return run("tell", arg);
      case "start": return this.startPlan();
      case "run": return run("runReady");
      case "stop": return run("stop");
      case "saveWorkflow": return run("saveWorkflow"); // the header's Save as workflow: Home's host asks its name and writes it
      case "markDone": return run("markDone", arg); // a step past the line: approving it runs its command
      case "cockpit": return run("openCockpit");
      case "openDiff": return run("openDiff", m.fork ? { ...arg, fork: m.fork } : arg);
      case "compareForks": return run("compareForks", arg);
      case "pickFork": return m.fork ? run("pickFork", { ...arg, fork: m.fork }) : undefined;
      case "signOff": return run("signOff", arg);
      case "answer": return run("answer", m.target !== undefined ? { ...arg, option: m.target } : arg);
      case "handBack": return run("handBack", arg);
    }
  }

  /** Start, as Home's (home.ts `start`): every suggested task accepted, then an agent on each that is ready, in a
   *  terminal. A question with no default stops it; with Exact on (Home's box: board on, every task reviewed, auto
   *  off) so does any open question, as Home's Start waits for every answer. The page holds its Start then too:
   *  this is for a board switched on since the page last heard. */
  private async startPlan() {
    const s = this.session.state;
    if (this.starting || !s || unanswered(s)) return;
    this.starting = true;
    try {
      if (s.questions.length && s.envelope.review === "every" && s.envelope.auto === "off") await this.readBoard();
      if (this.exact && s.questions.length) return void vscode.window.showInformationMessage("Exact is on: Start waits for your answer to the plan's question.");
      if (await this.session.act(C.acceptAll())) await run("runReady");
    } finally {
      this.starting = false;
      this.push(); // the page said Starting…: whatever happened, it draws the header again
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
  <link rel="stylesheet" href="${uri("media", "tokens.css")}">
  <link rel="stylesheet" href="${uri("media", "graph.css")}">
  <title>Graphene</title>
</head>
<body${vscode.env.appName.includes("Cursor") ? ' data-editor="cursor"' : ""}>
  <header>
    <div id="replay" hidden></div>
    <div id="goal">Graphene</div>
    <div id="auto" hidden></div>
    <div id="actions"></div>
  </header>
  <main>
    <div id="canvas">
      <svg id="svg" xmlns="http://www.w3.org/2000/svg"><g id="view"><g id="bands"></g><g id="edges"></g><g id="tasks"></g><g id="goalg" class="goal"></g><path id="wire" class="wire"></path></g></svg>
      <div id="lanes" hidden></div>
      <div id="notice" hidden></div>
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

/** What the active editor group has in front, as VS Code's tabs name it. Asked before VS Code has sent the
 *  window's tabs (they come once its editor groups are restored), the API throws: nothing is in front yet. */
function front(): unknown {
  try { return vscode.window.tabGroups.activeTabGroup.activeTab?.input; } catch { return undefined; }
}

/** The page's own key of the drawn task an unchecked message is about, when it reads as one (` d12`). */
function drawnKey(m: unknown): string | null {
  const r = (m ?? {}) as { act?: unknown; key?: unknown; draft?: { key?: unknown } };
  const key = r.act === "draw" ? r.draft?.key : r.act === "add-after" || r.act === "add-under" ? r.key : null;
  return draftKey(key) ? key : null;
}

/** A command of the extension's, or a message that it is not there yet: never a throw from the page. */
async function run(name: string, arg?: unknown) {
  const all = await vscode.commands.getCommands(true);
  const id = `graphene.${name}`;
  if (!all.includes(id)) return vscode.window.showInformationMessage(`Graphene: ${name} is not built yet.`);
  return arg === undefined ? vscode.commands.executeCommand(id) : vscode.commands.executeCommand(id, arg);
}
