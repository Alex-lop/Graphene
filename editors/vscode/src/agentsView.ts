// The Agents view: a row a running agent (agents.ts), the seconds quiet ticking on screen between snapshots
// with no read, a badge with the count; a click opens its changes so far.
import * as vscode from "vscode";
import { agentRows, ago, description, quiet, type AgentRow } from "./agents.ts";
import type { Session, UI } from "./session.ts";
import { mdText, usd, type State } from "./state.ts";

export class AgentsTree implements vscode.TreeDataProvider<AgentRow> {
  private emitter = new vscode.EventEmitter<void>();
  readonly onDidChangeTreeData = this.emitter.event;
  rows: AgentRow[] = [];
  at = 0; // when the snapshot was taken, ms

  set(state: State | null) {
    this.rows = state ? agentRows(state) : [];
    this.at = Date.now();
    this.emitter.fire();
  }

  /** The seconds tick: the rows again, from the same snapshot. */
  tick() {
    if (this.rows.length) this.emitter.fire();
  }

  getTreeItem(r: AgentRow): vscode.TreeItem {
    const secs = quiet(r.idle, this.at, Date.now());
    const it = new vscode.TreeItem(`${r.number}  ${r.title}`, vscode.TreeItemCollapsibleState.None);
    it.id = `agent:${r.id}:${r.fork ?? ""}`;
    it.description = description(r, secs);
    const long = secs !== null && secs > 8; // the cockpit's ⏸: quiet past 8 s is worth a colour
    it.iconPath = new vscode.ThemeIcon(long ? "debug-pause" : "loading~spin", new vscode.ThemeColor(long ? "charts.orange" : "charts.yellow"));
    it.contextValue = r.fork ? "agent:fork" : "agent";
    const md = new vscode.MarkdownString(undefined, true);
    md.appendMarkdown(`**agent ${mdText(r.number)}** on **${mdText(r.title)}**${r.model ? ` · ${mdText(r.model)}` : ""}${r.fork ? ` · fork ${mdText(r.fork)}` : ""}\n\n`);
    if (r.now) md.appendMarkdown(`now: ${mdText(r.now)}\n\n`);
    if (secs !== null) md.appendMarkdown(`quiet ${ago(secs)}\n\n`);
    if (usd(r.usd)) md.appendMarkdown(`${mdText(usd(r.usd))} so far\n\n`);
    md.appendMarkdown("Click to open its changes so far.");
    it.tooltip = md;
    it.command = { command: "graphene.openDiff", title: "Open Changes", arguments: [{ id: r.id, fork: r.fork ?? undefined }] };
    return it;
  }

  getChildren(r?: AgentRow): AgentRow[] {
    return r ? [] : this.rows;
  }
}

export function register(context: vscode.ExtensionContext, session: Session, _ui: UI) {
  const tree = new AgentsTree();
  const view = vscode.window.createTreeView("graphene.agents", { treeDataProvider: tree });
  context.subscriptions.push(view, session.onDidChange(() => {
    tree.set(session.state);
    view.badge = tree.rows.length ? { value: tree.rows.length, tooltip: `${tree.rows.length} running` } : undefined;
  }));
  const clock = setInterval(() => { if (view.visible) tree.tick(); }, 1000);
  context.subscriptions.push({ dispose: () => clearInterval(clock) });
}
