// The Rounds view: auto mode's iterations, a row a round (`roundLine`), opened on what the envelope accepted, the
// fork each task kept and why, what landed, and what the goal's check failed on.
import * as vscode from "vscode";
import { type Round, roundLine } from "./rounds.ts";

class Item extends vscode.TreeItem {
  readonly round: Round | undefined;
  constructor(label: string, round?: Round, icon?: string) {
    super(label, round ? vscode.TreeItemCollapsibleState.Expanded : vscode.TreeItemCollapsibleState.None);
    this.round = round;
    if (icon) this.iconPath = new vscode.ThemeIcon(icon);
  }
}

export class RoundsTree implements vscode.TreeDataProvider<Item> {
  private readonly emitter = new vscode.EventEmitter<void>();
  readonly onDidChangeTreeData = this.emitter.event;
  private list: Round[] = [];

  set(list: Round[]): void {
    this.list = list;
    this.emitter.fire();
  }

  getTreeItem(item: Item): vscode.TreeItem {
    return item;
  }

  getChildren(item?: Item): Item[] {
    // a round's icon: its goal check passed or failed (a failed round sent the next to fix it), it waits, or it goes
    const icon = (r: Round) => (r.check === "pass" ? "pass" : r.check === "fail" ? "error" : r.stage === "waits" ? "warning" : "sync");
    if (!item) return this.list.map((r) => new Item(roundLine(r), r, icon(r)));
    const r = item.round!;
    const kids: Item[] = [];
    if (r.failed) kids.push(new Item(`the goal's check failed: ${r.failed}, so this round plans the fix`, undefined, "error"));
    if (r.accepted.length) kids.push(new Item(`accepted inside your envelope: ${r.accepted.join(", ")}`, undefined, "check"));
    for (const k of r.kept) kids.push(new Item(k, undefined, "git-merge"));
    if (r.landed.length) kids.push(new Item(`landed: ${r.landed.join(", ")}`, undefined, "git-commit"));
    if (r.stage === "waits" && r.why) kids.push(new Item(`waits for you: ${r.why}`, undefined, "warning"));
    return kids;
  }
}
