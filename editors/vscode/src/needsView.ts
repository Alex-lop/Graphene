// The Needs You view: a row for each thing that needs the person (needs.ts), its move on its click and inline,
// a badge with the count; the commands graphene.answer, graphene.handBack, graphene.markDone and graphene.setKey.
import * as vscode from "vscode";
import * as C from "./commands.ts";
import { answerWords, count, markDone, needs, offerWords, pickOption, takeDefault, type Need } from "./needs.ts";
import type { Session, UI } from "./session.ts";
import { mdText, type State } from "./state.ts";

const ICONS: Record<Need["kind"], [string, string]> = {
  auto: ["warning", "charts.orange"], question: ["comment-discussion", "charts.purple"], proposal: ["diff-added", "charts.blue"],
  "hand-back": ["debug-step-back", "charts.red"], "sign-off": ["eye", "charts.purple"], yours: ["person", "charts.purple"],
  stopped: ["shield", "charts.orange"],
};

/** One row: its words, its icon, the command its click runs. */
export function item(n: Need, s: State): vscode.TreeItem {
  const [icon, colour] = ICONS[n.kind];
  const it = new vscode.TreeItem("", vscode.TreeItemCollapsibleState.None);
  it.iconPath = new vscode.ThemeIcon(icon, new vscode.ThemeColor(colour));
  it.contextValue = `need:${n.kind}`;
  const md = new vscode.MarkdownString(undefined, true);
  if (n.kind === "auto") {
    it.id = "need:auto";
    it.label = "auto waits for you";
    it.description = n.why;
    md.appendMarkdown(`**auto waits for you**\n\n${mdText(n.why)}\n\n${n.key ? "Set Key runs `graphene key set` in a terminal." : "Answer the question below, or change the plan."}`);
    if (n.key) it.command = { command: "graphene.setKey", title: "Set Key", arguments: [n.endpoint] };
    else if (s.questions[0]) it.command = { command: "graphene.answer", title: "Answer", arguments: [{ id: s.questions[0].id }] };
  } else if (n.kind === "question") {
    it.id = `need:q:${n.q.id}`;
    it.label = n.q.text;
    it.description = n.q.default ? `default: ${n.q.default}` : n.q.options.length ? `${n.q.options.length} options` : "in your own words";
    const about = s.tasks.find((t) => t.id === n.q.about);
    md.appendMarkdown(`**${mdText(n.q.text)}**\n\n`);
    if (about) md.appendMarkdown(`about **${mdText(about.title)}**\n\n`);
    if (n.q.default) md.appendMarkdown(`default: ${mdText(n.q.default)}\n\n`);
    for (const o of n.q.options) md.appendMarkdown(`- ${mdText(o)}\n`);
    md.appendMarkdown("\nClick to answer: its default, one of its options, or your own words.");
    it.command = { command: "graphene.answer", title: "Answer", arguments: [{ id: n.q.id }] };
  } else {
    const t = n.t;
    it.id = `need:t:${t.id}`;
    it.label = t.title;
    md.appendMarkdown(`**${mdText(t.title)}** · ${mdText(t.id)} · ${mdText(t.state)}\n\n`);
    if (t.full) md.appendMarkdown(`${mdText(t.full)}\n\n`);
    const arg = { id: t.id };
    if (n.kind === "proposal") {
      it.description = `proposed · ${t.scope.length ? t.scope.join("  ") : "no files yet"}`;
      md.appendMarkdown(`scope: ${mdText(t.scope.join("  ") || "none")}\n\ncheck: ${mdText(t.check ?? "none")}\n\nClick to accept it; the trash can drops it (\`graphene plan undo\` puts it back).`);
      it.command = { command: "graphene.accept", title: "Accept", arguments: [arg] };
    } else if (n.kind === "hand-back") {
      const why = t.why || t.note || "stuck";
      it.description = `came back · ${why}`;
      md.appendMarkdown(`came back: ${mdText(why)}\n\nClick for its moves: ${offerWords(t).map((o) => mdText(o.label.toLowerCase())).join(", ")}.`);
      it.command = { command: "graphene.handBack", title: "Take Up the Hand-Back", arguments: [arg] };
    } else if (n.kind === "sign-off") {
      it.description = `${t.hollow ? "passed before the work" : "check passed"} · sign off`;
      md.appendMarkdown(`${t.changed.length ? `changed: ${mdText(t.changed.join("  "))}` : "its check passed"}\n\nClick to open its changes; the check mark signs it off.`);
      it.command = { command: "graphene.openDiff", title: "Open Changes", arguments: [arg] };
    } else if (n.kind === "yours") {
      it.description = "yours · mark done";
      md.appendMarkdown("Your own task. Click when it is done: its check runs in a terminal.");
      it.command = { command: "graphene.markDone", title: "Mark Done", arguments: [arg] };
    } else {
      const path = t.stopped[t.stopped.length - 1] ?? "";
      it.description = `agent ${t.agent || "?"} stopped writing ${path}`;
      md.appendMarkdown(`The gate stopped a write to ${mdText(path)}: it is outside the task's scope. Click to widen the scope to it.`);
      it.command = { command: "graphene.handBack", title: "Widen", arguments: [arg] };
    }
  }
  it.tooltip = md;
  return it;
}

export class NeedsTree implements vscode.TreeDataProvider<Need> {
  private emitter = new vscode.EventEmitter<void>();
  readonly onDidChangeTreeData = this.emitter.event;
  private state: State | null = null;
  list: Need[] = [];

  set(state: State | null) {
    this.state = state;
    this.list = state ? needs(state) : [];
    this.emitter.fire();
  }

  getTreeItem(n: Need): vscode.TreeItem {
    return item(n, this.state!);
  }

  getChildren(n?: Need): Need[] {
    return n ? [] : this.list;
  }
}

type Arg = string | { id?: string } | undefined;
const idOf = (arg: Arg) => (typeof arg === "string" ? arg : arg?.id);

export function register(context: vscode.ExtensionContext, session: Session, _ui: UI) {
  const tree = new NeedsTree();
  const view = vscode.window.createTreeView("graphene.needs", { treeDataProvider: tree });
  context.subscriptions.push(view, session.onDidChange(() => {
    tree.set(session.state);
    view.badge = tree.list.length ? { value: tree.list.length, tooltip: count(tree.list) } : undefined;
  }));

  const cmd = (name: string, fn: (arg?: Arg) => unknown) =>
    context.subscriptions.push(vscode.commands.registerCommand(`graphene.${name}`, (arg?: Arg) => fn(arg)));

  cmd("answer", async (arg) => {
    const qs = session.state?.questions ?? [];
    let q = qs.find((x) => x.id === idOf(arg));
    if (!q) {
      if (!qs.length) return void vscode.window.showInformationMessage("No question is open.");
      q = qs.length === 1 ? qs[0] : (await vscode.window.showQuickPick(qs.map((x) => ({ label: x.text, description: x.id, q: x })), { placeHolder: "the question to answer" }))?.q;
      if (!q) return;
    }
    type Pick = vscode.QuickPickItem & { argv?: string[]; own?: boolean };
    const items: Pick[] = [];
    if (q.default) items.push({ label: `$(check) ${q.default}`, description: "the default", argv: takeDefault(q.id) });
    q.options.forEach((o, i) => items.push({ label: o, description: `option ${i + 1}`, argv: pickOption(q.id, i + 1) }));
    items.push({ label: "$(edit) In your own words…", description: "your words go to the agents as written", own: true });
    const chosen = await vscode.window.showQuickPick(items, { placeHolder: q.text, ignoreFocusOut: true });
    if (!chosen) return;
    if (chosen.own) {
      const words = await vscode.window.showInputBox({ prompt: q.text, placeHolder: "your answer", ignoreFocusOut: true });
      if (words?.trim()) await session.act(answerWords(q.id, words.trim()));
    } else if (chosen.argv) {
      await session.act(chosen.argv);
    }
  });

  cmd("handBack", async (arg) => {
    const back = session.tasks().filter((t) => t.state === "came back" || (t.state === "running" && t.stopped.length));
    let t = back.find((x) => x.id === idOf(arg));
    if (!t) {
      if (!back.length) return void vscode.window.showInformationMessage("No task came back.");
      t = back.length === 1 ? back[0] : (await vscode.window.showQuickPick(back.map((x) => ({ label: x.title, description: x.why || x.note, t: x })), { placeHolder: "the task that came back" }))?.t;
      if (!t) return;
    }
    const titles = Object.fromEntries(session.tasks().map((x) => [x.id, x.title]));
    const why = t.state === "running" ? `agent ${t.agent || "?"} was stopped writing ${t.stopped[t.stopped.length - 1]}` : t.why || t.note || "it came back";
    const chosen = await vscode.window.showQuickPick(offerWords(t, titles), { placeHolder: `${t.title}: ${why}`, ignoreFocusOut: true });
    if (!chosen) return;
    if (chosen.long) session.terminal(`graphene ${chosen.argv.slice(0, 2).join(" ")}`, chosen.argv);
    else await session.act(chosen.argv);
  });

  cmd("markDone", async (arg) => {
    const yours = session.tasks().filter((t) => t.state === "yours");
    const t = yours.find((x) => x.id === idOf(arg)) ?? (yours.length === 1 ? yours[0] : undefined)
      ?? (await vscode.window.showQuickPick(yours.map((x) => ({ label: x.title, t: x })), { placeHolder: "your task that is done" }))?.t;
    if (t) session.terminal("graphene node done", markDone(t.id));
  });

  cmd("setKey", (arg) => session.terminal("graphene key set", C.keySet(typeof arg === "string" ? arg : undefined)));
}
