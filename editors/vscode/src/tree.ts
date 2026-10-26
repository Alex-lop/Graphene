// The Plan view: goal → sub-goals → tasks, a codicon a state, `model · forks · $` beside the title, the
// contract in the tooltip; a click opens the graph on that task. Context menus are chosen by `task:<state>`.
import * as vscode from "vscode";
import { mdText, usd, type Goal, type State, type Task } from "./state.ts";

export type Node = { kind: "goal"; goal: Goal } | { kind: "task"; task: Task };

const ICONS: Record<string, [string, string]> = {
  running: ["loading~spin", "charts.yellow"], review: ["eye", "charts.purple"], "came back": ["debug-step-back", "charts.red"],
  ready: ["circle-outline", "foreground"], waiting: ["clock", "descriptionForeground"], proposed: ["diff-added", "charts.blue"],
  done: ["pass", "charts.green"], yours: ["person", "charts.purple"],
};

export function icon(state: string): vscode.ThemeIcon {
  const [name, colour] = ICONS[state] ?? ICONS.waiting!;
  return new vscode.ThemeIcon(name, new vscode.ThemeColor(colour));
}

/** `Nano · 3 forks · $0.31`: what is on the task, as the cockpit's row says it. */
export function description(t: Task): string {
  const parts: string[] = [];
  if (t.model) parts.push(t.model);
  if (t.forks.length) parts.push(`${t.forks.length} forks${t.kept ? ` · kept ${t.kept.letter}` : ""}`);
  const spent = usd(t.usd);
  if (spent) parts.push(spent);
  if (!parts.length && t.state !== "running") parts.push(t.state);
  return parts.join(" · ");
}

/** The task's contract on hover: the markup is ours, every word of the plan's goes in as text (`mdText`). */
export function tooltip(t: Task, goals: Goal[]): vscode.MarkdownString {
  const md = new vscode.MarkdownString(undefined, true);
  const x = mdText;
  md.appendMarkdown(`**${x(t.title)}** · ${x(t.id)} · ${x(t.state)}${t.needs_you ? " · needs you" : ""}\n\n`);
  if (t.full) md.appendMarkdown(`${x(t.full)}\n\n`);
  const under = goals.find((g) => g.id === t.parent);
  if (under) md.appendMarkdown(`under **${x(under.title)}**\n\n`);
  if (t.scope.length) md.appendMarkdown(`scope: ${x(t.scope.join("  "))}\n\n`);
  if (t.check) md.appendMarkdown(`check: ${x(t.check)}\n\n`);
  if (t.needs.length) md.appendMarkdown(`needs: ${x(t.needs.join(", "))}\n\n`);
  if (t.agent) md.appendMarkdown(`agent ${x(`${t.agent}${t.model ? ` · ${t.model}` : ""}${usd(t.usd) ? ` · ${usd(t.usd)}` : ""}`)}\n\n`);
  for (const f of t.forks) {
    const kept = t.kept?.letter === f.letter ? " · ✓ kept" : "";
    md.appendMarkdown(`- fork ${x(`${f.letter} · ${f.model} · ${f.state}${f.lines !== null ? ` · ${f.lines} lines` : ""}${kept}`)}\n`);
  }
  if (t.forks.length) md.appendMarkdown("\n");
  if (t.tail.length) md.appendMarkdown(t.tail.slice(-4).map((l) => `- ${x(l)}`).join("\n") + "\n");
  if (t.note) md.appendMarkdown(`\nnote: ${x(t.note)}\n`);
  return md;
}

export class PlanTree implements vscode.TreeDataProvider<Node> {
  private emitter = new vscode.EventEmitter<void>();
  readonly onDidChangeTreeData = this.emitter.event;
  private state: State | null = null;

  set(state: State | null) {
    this.state = state;
    this.emitter.fire();
  }

  getTreeItem(n: Node): vscode.TreeItem {
    if (n.kind === "goal") {
      const under = this.state?.tasks.filter((t) => t.parent === n.goal.id) ?? [];
      const done = under.filter((t) => t.state === "done").length;
      const item = new vscode.TreeItem(n.goal.title, vscode.TreeItemCollapsibleState.Expanded);
      item.id = `goal:${n.goal.id}`;
      item.iconPath = new vscode.ThemeIcon("target");
      item.description = under.length ? `${done} of ${under.length} done` : "";
      item.contextValue = "goal";
      item.tooltip = n.goal.check ? `check: ${n.goal.check}` : n.goal.id;
      return item;
    }
    const t = n.task;
    const item = new vscode.TreeItem(t.title, vscode.TreeItemCollapsibleState.None);
    item.id = `task:${t.id}`;
    item.description = description(t);
    item.iconPath = icon(t.state);
    item.tooltip = tooltip(t, this.state?.goals ?? []);
    item.contextValue = `task:${t.state.replace(" ", "-")}`;
    item.command = { command: "graphene.showGraph", title: "Show Plan Graph", arguments: [{ id: t.id }] };
    return item;
  }

  getChildren(n?: Node): Node[] {
    const s = this.state;
    if (!s) return [];
    const goalIds = new Set(s.goals.map((g) => g.id));
    const parent = n ? (n.kind === "goal" ? n.goal.id : "") : null;
    if (n?.kind === "task") return [];
    const goals = s.goals.filter((g) => (parent === null ? g.parent === null || !goalIds.has(g.parent) : g.parent === parent));
    const tasks = s.tasks.filter((t) => (parent === null ? t.parent === null || !goalIds.has(t.parent) : t.parent === parent));
    return [...goals.map((goal) => ({ kind: "goal", goal }) as Node), ...tasks.map((task) => ({ kind: "task", task }) as Node)];
  }

  getParent(n: Node): Node | undefined {
    const pid = n.kind === "goal" ? n.goal.parent : n.task.parent;
    const goal = this.state?.goals.find((g) => g.id === pid);
    return goal ? { kind: "goal", goal } : undefined;
  }
}
