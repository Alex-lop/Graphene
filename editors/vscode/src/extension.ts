// Graphene for VS Code: a thin client over the CLI. It reads `graphene state --json` in the folder that
// holds the plan, again when the store's files change or on a poll while a view is open, and every change
// it makes is a graphene command run as the person (the agent marks are taken out of the environment).
import * as path from "node:path";
import * as vscode from "vscode";
import * as C from "./commands.ts";
import { GraphHost } from "./graph.ts";
import { owner } from "./owners.ts";
import { autoNews, mdText, summary, type Task } from "./state.ts";
import { parseLog, rounds, type LogRow } from "./rounds.ts";
import { RoundsTree } from "./roundsView.ts";
import { PlanTree } from "./tree.ts";
import { planFolder, Session, type UI } from "./session.ts";
import * as needs from "./needsView.ts";
import * as agents from "./agentsView.ts";
import * as find from "./setup.ts";
import * as diff from "./diff.ts";
import * as planDoc from "./planDoc.ts";
import * as step from "./step.ts";
import * as demo from "./demo.ts";
import * as files from "./files.ts";

export { Session } from "./session.ts";

type Arg = string | { id?: string; task?: Task; after?: boolean; under?: boolean } | undefined;

export function activate(context: vscode.ExtensionContext) {
  const session = new Session();
  const tree = new PlanTree();
  const treeView = vscode.window.createTreeView("graphene.plan", { treeDataProvider: tree, showCollapseAll: true });
  const roundsTree = new RoundsTree();
  const roundsView = vscode.window.createTreeView("graphene.rounds", { treeDataProvider: roundsTree });
  // auto mode's rounds, from the plan's log while their view is open: only the rows after the last read, none
  // asked for when the snapshot's cursor says nothing was logged since, and all again if the log starts over
  let logged: LogRow[] = [];
  let read = 0;
  let reading = false;
  const readRounds = async () => {
    const s = session.state;
    if (!roundsView.visible || !s || reading) return;
    if (s.cursor < read) [logged, read] = [[], 0]; // a new store: its ids start again
    if (read > 0 && s.cursor === read) return;
    reading = true;
    try {
      const out = await session.run(C.logJson(read));
      if (out.code !== 0) return;
      const fresh = parseLog(out.stdout).filter((r) => r.id > read);
      logged = logged.concat(fresh);
      read = Math.max(read, ...fresh.map((r) => r.id));
      roundsTree.set(rounds(logged));
    } finally {
      reading = false;
    }
  };
  context.subscriptions.push(roundsView, roundsView.onDidChangeVisibility(() => void readRounds()));
  const graph = new GraphHost(context, session);
  const bar = vscode.window.createStatusBarItem("graphene", vscode.StatusBarAlignment.Left, 50);
  bar.name = "Graphene";
  bar.command = "graphene.showGraph";
  bar.text = "◆ Graphene";
  bar.show();
  context.subscriptions.push(treeView, bar, vscode.window.registerWebviewViewProvider("graphene.graph", graph, { webviewOptions: { retainContextWhenHidden: true } }));

  // the Explorer marks each file a live task owns, a running one's with its agent's number: whose is whose
  const owners = new vscode.EventEmitter<undefined>();
  const colours: Record<string, string> = { running: "charts.yellow", review: "charts.purple", "came back": "charts.red" };
  let held = "";
  context.subscriptions.push(owners, vscode.window.registerFileDecorationProvider({
    onDidChangeFileDecorations: owners.event,
    provideFileDecoration(uri) {
      const root = session.folder?.uri.fsPath;
      if (!root || !session.state || uri.scheme !== "file") return undefined;
      const rel = path.relative(root, uri.fsPath).split(path.sep).join("/");
      if (rel.startsWith("../") || rel === ".." || path.isAbsolute(rel)) return undefined;
      const o = owner(rel, session.state.tasks);
      if (!o) return undefined;
      const colour = colours[o.state];
      return new vscode.FileDecoration(o.badge, o.tooltip, colour ? new vscode.ThemeColor(colour) : undefined);
    },
  }));

  session.onDidChange(() => {
    tree.set(session.state);
    const now = JSON.stringify((session.state?.tasks ?? []).filter((t) => t.state !== "done" && t.state !== "proposed")
      .map((t) => [t.id, t.state, t.agent, t.model, t.scope, t.forks.length]));
    if (now !== held) { held = now; owners.fire(undefined); } // only when whose is whose changed
    void readRounds();
    const s = session.state;
    const said = s ? autoNews(session.before, s) : null; // auto mode needs you, plans a fix, or is done
    if (said) {
      const show = said.kind === "waits" ? vscode.window.showWarningMessage : vscode.window.showInformationMessage;
      const key = /`graphene key set(?: --endpoint (\w+))?`/.exec(said.text); // it waits on a key: set it from here
      void show(said.text, ...(key ? ["Set Key", "Needs You"] : said.kind === "waits" ? ["Needs You", "Show Plan Graph"] : ["Show Plan Graph", "Rounds"])).then((pick) => {
        if (pick === "Set Key") void vscode.commands.executeCommand("graphene.setKey", key?.[1]);
        if (pick === "Needs You") void vscode.commands.executeCommand("graphene.needs.focus");
        if (pick === "Show Plan Graph") void vscode.commands.executeCommand("graphene.showGraph");
        if (pick === "Rounds") void vscode.commands.executeCommand("graphene.rounds.focus");
      });
    }
    if (s && (session.status.kind === "ok" || session.status.kind === "empty")) {
      bar.text = `◆ ${summary(s)}`;
      const md = new vscode.MarkdownString(undefined, true);
      md.appendMarkdown(`**${mdText(s.goal || "no goal yet")}**\n\n`); // the plan's words as text, not markup
      for (const line of s.news.slice(-4)) md.appendMarkdown(`- ${mdText(line)}\n`);
      md.appendMarkdown(session.found ? `\ngraphene from ${mdText(session.found)}, off this editor's PATH\n\n` : "\n");
      md.appendMarkdown(session.stream.live ? "live: `graphene state --json --watch`\n\n" : "");
      md.appendMarkdown("Graphene: Show Plan Graph");
      bar.tooltip = md;
    } else {
      bar.text = `◆ Graphene · ${session.status.kind === "missing" ? "not installed" : session.status.kind === "uninitialised" ? "no plan" : session.status.kind}`;
      bar.tooltip = session.status.text;
    }
  });

  // read again when the store's own files change (graphene.db, its WAL, the run lock: not an agent's save
  // under the worktrees) and on a poll while a view is open; a burst of changes is one read. While the stream
  // is live (`state --json --watch`) it brings every change, and both rest.
  let due: NodeJS.Timeout | undefined;
  const soon = () => { if (session.stream.live) return; clearTimeout(due); due = setTimeout(() => void session.refresh(), 250); };
  if (session.folder) {
    const watcher = vscode.workspace.createFileSystemWatcher(new vscode.RelativePattern(session.folder, ".graphene/{graphene.db,graphene.db-wal,run.lock}"));
    watcher.onDidChange(soon); watcher.onDidCreate(soon); watcher.onDidDelete(soon);
    context.subscriptions.push(watcher);
  }
  let poll: NodeJS.Timeout | undefined;
  const arm = () => {
    clearInterval(poll);
    poll = setInterval(() => { if ((treeView.visible || graph.open) && !session.stream.live) void session.refresh(); }, session.pollMs);
  };
  arm();
  context.subscriptions.push(session, { dispose: () => { clearInterval(poll); clearTimeout(due); } });
  context.subscriptions.push(vscode.workspace.onDidChangeConfiguration((e) => {
    if (e.affectsConfiguration("graphene")) { arm(); session.moved(); void session.refresh(); }
  }));
  context.subscriptions.push(vscode.workspace.onDidChangeWorkspaceFolders(() => { session.folder = planFolder(); session.moved(); void session.refresh(); }));

  const taskOf = (arg: Arg): Task | undefined => {
    const id = typeof arg === "string" ? arg : arg?.task?.id ?? arg?.id;
    return id ? session.tasks().find((t) => t.id === id) : undefined;
  };
  const pick = async (arg: Arg, placeHolder: string, among = session.tasks()): Promise<Task | undefined> => {
    const given = taskOf(arg);
    if (given) return given;
    if (!among.length) { void vscode.window.showInformationMessage("No task to choose from."); return undefined; }
    const chosen = await vscode.window.showQuickPick(
      among.map((t) => ({ label: t.title, description: `${t.state} · ${t.id}`, detail: t.scope.join("  "), t })), { placeHolder });
    return chosen?.t;
  };
  const cmd = (name: string, fn: (arg?: Arg) => unknown) =>
    context.subscriptions.push(vscode.commands.registerCommand(`graphene.${name}`, (arg?: Arg) => fn(arg)));

  cmd("refresh", () => session.refresh());
  cmd("showGraph", (arg) => graph.show(taskOf(arg)?.id));
  cmd("openCockpit", () => session.terminal("graphene watch", C.watch()));
  cmd("runReady", () => session.terminal("graphene run", C.runReady()));
  cmd("stop", () => session.act(C.stop()));
  cmd("auto", async () => {
    const goal = await vscode.window.showInputBox({ prompt: "The goal Graphene plans and runs on its own", placeHolder: "what you want, in a sentence",
                                                   ignoreFocusOut: true, validateInput: (v) => (v.trim() ? undefined : "say what you want") });
    if (!goal?.trim()) return;
    const budget = await vscode.window.showInputBox({ prompt: "A budget in dollars for the whole run (empty: the configured one)", placeHolder: "2",
                                                     ignoreFocusOut: true, validateInput: (v) => (!v.trim() || Number(v) > 0 ? undefined : "a number of dollars, or nothing") });
    if (budget === undefined) return;
    const how = await vscode.window.showQuickPick(
      [{ label: "Plan and run", description: "plan, race, land, check the goal, fix", planOnly: false },
       { label: "Plan first", description: "--plan: see what your envelope accepts; Auto… again, or graphene auto, runs it", planOnly: true }],
      { placeHolder: "run it now, or look at the plan first?" });
    if (!how) return;
    session.terminal("graphene auto", C.auto(goal.trim(), budget.trim() ? Number(budget) : null, how.planOnly));
  });
  cmd("envelope", async () => {
    // the settings `graphene auto` and an agent's proposals stay inside, set once, as `graphene config set` does
    const e = session.state?.envelope;
    const now = (v: unknown, unset: string) => (v === null || v === undefined || v === "" ? unset : String(v));
    const items = [
      { key: "auto", label: "Auto", description: now(e?.auto, "off"), detail: "on: a plan that fits the envelope is accepted at once, from any agent" },
      { key: "budget", label: "Budget", description: e?.budget != null ? `$${e.budget}` : "unset", detail: "dollars every run may spend while auto is on" },
      { key: "tasks", label: "Tasks", description: now(e?.tasks, "12"), detail: "how many tasks the envelope may accept for you, all told" },
      { key: "rounds", label: "Rounds", description: now(e?.rounds, "2"), detail: "fix rounds after the goal's check fails" },
      { key: "forks", label: "Forks", description: now(e?.forks, "1"), detail: "agents at once on every task; its check keeps one" },
      { key: "checks", label: "Checks", description: e?.checks?.length ? e.checks.join(", ") : "any one plain command",
        detail: "the commands the envelope runs as a task's check, comma-separated" },
    ];
    const chosen = await vscode.window.showQuickPick(items, { placeHolder: "the envelope: what Graphene may do without asking you" });
    if (!chosen) return;
    const value = chosen.key === "auto"
      ? (await vscode.window.showQuickPick(["on", "off"], { placeHolder: "auto" }))
      : await vscode.window.showInputBox({ prompt: `${chosen.label}: ${chosen.detail}`,
                                           value: chosen.key === "checks" ? (e?.checks ?? []).join(", ") : chosen.description.replace(/^\$/, "").replace("unset", ""),
                                           ignoreFocusOut: true,
                                           validateInput: (v) => (chosen.key === "checks" || (Number(v) >= 0 && v.trim()) ? undefined : "a number") });
    if (value === undefined || !value.trim()) return;
    await session.act(C.setting(chosen.key, value.trim()));
  });
  cmd("accept", async (arg) => {
    const t = await pick(arg, "the proposed task to accept", session.tasks().filter((x) => x.state === "proposed"));
    if (t) await session.act(C.accept(t.id));
  });
  cmd("acceptAll", async () => {
    const n = session.tasks().filter((x) => x.state === "proposed").length;
    if (!n) return void vscode.window.showInformationMessage("Nothing is proposed.");
    const ok = await vscode.window.showWarningMessage(`Accept all ${n} proposed task${n > 1 ? "s" : ""}?`, { modal: true }, "Accept");
    if (ok) await session.act(C.acceptAll());
  });
  cmd("link", async (arg) => {
    const a = await pick(arg, "the task that must land first");
    if (!a) return;
    const b = await pick(undefined, `the task that waits on “${a.title}”`, session.tasks().filter((t) => t.id !== a.id));
    if (b) await session.act(C.link(a.id, b.id));
  });
  cmd("editStep", async (arg) => {
    const t = await pick(arg, "the task to edit");
    if (!t) return;
    const field = await vscode.window.showQuickPick([
      { label: "title", description: t.title, f: "title" as C.Field },
      { label: "scope", description: t.scope.join("  ") || "none", f: "scope" as C.Field },
      { label: "check", description: t.check ?? "none", f: "check" as C.Field },
    ], { placeHolder: `what to change on “${t.title}”` });
    if (!field) return;
    const value = await vscode.window.showInputBox({
      prompt: field.f === "scope" ? "The files it may write (globs, spaces or commas between)" : field.f === "check" ? "The command that passes only when it is done" : "The title",
      value: field.f === "scope" ? t.scope.join(" ") : field.f === "check" ? t.check ?? "" : t.title, ignoreFocusOut: true,
    });
    if (value === undefined || !value.trim()) return;
    await session.act(C.editStep(t.id, field.f, field.f === "scope" ? C.globs(value) : value.trim()));
  });
  cmd("dropStep", async (arg) => {
    const t = await pick(arg, "the task to drop", session.tasks().filter((x) => ["proposed", "ready", "waiting"].includes(x.state)));
    if (!t) return;
    const ok = await vscode.window.showWarningMessage(`Drop “${t.title}”? \`graphene plan undo\` puts it back.`, { modal: true }, "Drop");
    if (ok) await session.act(C.dropStep(t.id));
  });
  cmd("tell", async (arg) => {
    const t = await pick(arg, "the task whose agent hears it");
    if (!t) return;
    const text = await vscode.window.showInputBox({ prompt: `A line for the agent on “${t.title}”`, placeHolder: "keep both routes", ignoreFocusOut: true });
    if (text?.trim()) await session.act(C.tell(t.id, text.trim()));
  });

  // the features, each in a module of its own (dev/process/editor/CONTRACT.md says who writes which)
  const ui: UI = { graph, tree, treeView };
  for (const m of [needs, agents, find, diff, planDoc, step, demo, files]) m.register(context, session, ui);

  void session.refresh();
}

export function deactivate() {}
