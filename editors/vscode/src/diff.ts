// A task's or a fork's changes in VS Code's own diff editor, multi-file where it can; a race's forks side by
// side; picking a fork and signing off from there. Every side is read-only, under this module's own scheme:
// `git show` in the snapshot's repo at a revision, or a running agent's file on disk, read again as the plan
// changes. Nothing here writes into an agent's directory.
import { execFile } from "node:child_process";
import { readFile } from "node:fs/promises";
import * as path from "node:path";
import * as vscode from "vscode";
import * as C from "./commands.ts";
import type { Session, UI } from "./session.ts";
import type { Task } from "./state.ts";

export const SCHEME = C.SCHEME;

type Arg = string | { id?: string; fork?: string; task?: { id: string } } | undefined;

/** A side as a URI under this module's scheme. The query says which revision it is at (null: the file on
 *  disk) and which diff it is in, so a title action knows what it acts on. */
export function sideUri(side: C.Side, id: string, fork: string | null): vscode.Uri {
  const q: C.Query = { repo: side.repo, rev: side.rev, id, fork };
  return vscode.Uri.file(path.join(side.repo, side.path)).with({ scheme: SCHEME, query: JSON.stringify(q) });
}

function queryOf(uri: vscode.Uri | undefined): C.Query | null {
  if (!uri || uri.scheme !== SCHEME) return null;
  try { return JSON.parse(uri.query) as C.Query; } catch { return null; }
}

/** A side's text: nothing for a side the file is not on; the file on disk for a running agent's changes so
 *  far; else `git show REV:PATH`. A file missing either place is empty. */
export function contentOf(q: C.Query, fsPath: string): Promise<string> {
  if (q.rev === "") return Promise.resolve("");
  if (q.rev === null) return readFile(fsPath, "utf8").catch(() => "");
  const rel = path.relative(q.repo, fsPath);
  return new Promise((resolve) =>
    execFile("git", ["-C", q.repo, "show", `${q.rev}:${rel}`], { maxBuffer: 64 * 1024 * 1024 }, (err, out) =>
      resolve(err ? "" : String(out))));
}

/** The diff the active tab shows, when it is one of ours: a diff editor or a multi-file one. */
const activeDiff = () => C.diffOf(vscode.window.tabGroups.activeTabGroup.activeTab?.input);

export function register(context: vscode.ExtensionContext, session: Session, _ui: UI) {
  // what one of our diffs showed last, for an action run while none of them is the active tab
  let last: { id: string; fork: string | null } | null = null;
  const current = () => activeDiff() ?? last;

  const changed = new vscode.EventEmitter<vscode.Uri>();
  context.subscriptions.push(changed, vscode.workspace.registerTextDocumentContentProvider(SCHEME, {
    onDidChange: changed.event,
    provideTextDocumentContent(uri) {
      const q = queryOf(uri);
      return q ? contentOf(q, uri.fsPath) : "";
    },
  }));
  // an agent's side on disk is read again as the plan changes: its changes so far, still read-only
  context.subscriptions.push(session.onDidChange(() => {
    for (const d of vscode.workspace.textDocuments) if (queryOf(d.uri)?.rev === null) changed.fire(d.uri);
  }));

  // the title actions (Keep This Fork, Sign Off) show on our diffs: lane 2a's package.json reads these keys
  const keys = () => {
    const d = current();
    const t = d && session.tasks().find((x) => x.id === d.id);
    void vscode.commands.executeCommand("setContext", "graphene.diff.fork", Boolean(d?.fork && t && t.state !== "done"));
    void vscode.commands.executeCommand("setContext", "graphene.diff.review", Boolean(d && t?.state === "review"));
  };
  context.subscriptions.push(vscode.window.tabGroups.onDidChangeTabs(() => {
    const open = vscode.window.tabGroups.all.flatMap((g) => g.tabs).some((tab) => C.diffOf(tab.input));
    if (!open) last = null; // every diff of ours is closed
    keys();
  }), vscode.window.onDidChangeActiveTextEditor(keys), session.onDidChange(keys));

  const idOf = (arg: Arg) => (typeof arg === "string" ? arg : arg?.task?.id ?? arg?.id);
  const name = (id: string) => session.tasks().find((t) => t.id === id)?.title ?? id;

  /** `graphene node diff --json`, or the refusal said to the person and null. */
  const read = async (id: string, fork: string | null): Promise<C.Diff | null> => {
    const out = await session.run(C.nodeDiff(id, fork));
    if (out.code !== 0) {
      void vscode.window.showInformationMessage(`Graphene: ${C.plain(C.firstLine(out.stderr, out.stdout))}`);
      return null;
    }
    try { return C.parseDiff(out.stdout); } catch {
      // nothing to show yet is said in words, on stdout, exit 0 (the CLI as it is)
      void vscode.window.showInformationMessage(`Graphene: ${C.plain(C.firstLine(out.stdout, out.stderr, "node diff gave no JSON"))}`);
      return null;
    }
  };

  /** All of a diff's files in one multi-file editor (vscode.changes), else one diff editor a file. */
  const open = async (id: string, fork: string | null, d: C.Diff, column?: vscode.ViewColumn) => {
    last = { id, fork };
    const title = C.diffTitle(name(id), fork, d);
    const pairs = C.diffPairs(d);
    if (!pairs.length) {
      void vscode.window.showInformationMessage(`Graphene: ${C.plain(d.said[0] ?? `${name(id)} changed no file`)}`);
      return;
    }
    session.see(id); // its changes are on screen: Home's Approve no longer asks
    if (d.said.length) vscode.window.setStatusBarMessage(`$(info) ${C.plain(d.said.join(" · "))}`, 8000);
    const uris = pairs.map((p) => [sideUri(p.left, id, fork), sideUri(p.right, id, fork)] as const);
    if (pairs.length > 1 && !column) {
      try {
        await vscode.commands.executeCommand("vscode.changes", title, uris.map(([l, r]) => [r, l, r]));
        keys();
        return;
      } catch { /* an editor without the multi-file diff: one editor a file */ }
    }
    for (const [i, [l, r]] of uris.entries()) {
      await vscode.commands.executeCommand("vscode.diff", l, r, pairs.length === 1 ? title : `${pairs[i]!.path} · ${title}`,
                                           { viewColumn: column ?? vscode.ViewColumn.Active, preview: false, preserveFocus: i > 0 });
    }
    keys();
  };

  const cmd = (n: string, fn: (arg?: Arg) => unknown) =>
    context.subscriptions.push(vscode.commands.registerCommand(`graphene.${n}`, (arg?: Arg) => fn(arg)));

  /** The task the palette did not name: a quick pick among those the command can act on, or why none. */
  const pick = async (among: Task[], placeHolder: string, none: string): Promise<Task | undefined> => {
    if (!among.length) return void vscode.window.showInformationMessage(`Graphene: ${none}`);
    const chosen = await vscode.window.showQuickPick(
      among.map((t) => ({ label: C.plain(t.title), description: `${t.state} · ${t.id}`, t })), { placeHolder });
    return chosen?.t;
  };

  cmd("openDiff", async (arg) => {
    const id = idOf(arg) ?? (await pick(C.withChanges(session.tasks()), "the task whose changes to open", "no task has changes to show yet."))?.id;
    if (!id) return;
    const fork = typeof arg === "object" ? arg.fork ?? null : null;
    const d = await read(id, fork);
    if (d) await open(id, fork, d);
  });

  cmd("compareForks", async (arg) => {
    const id = idOf(arg);
    const t = id ? session.tasks().find((x) => x.id === id)
                 : await pick(C.forked(session.tasks()), "the task whose attempts to compare", "no task has attempts racing.");
    if (!t) return;
    const letters = t.forks.map((f) => f.letter).filter(Boolean);
    if (!letters.length) return void vscode.window.showInformationMessage(`Graphene: ${C.plain(t.title)} has no attempts racing.`);
    const columns = [vscode.ViewColumn.One, vscode.ViewColumn.Two, vscode.ViewColumn.Three, vscode.ViewColumn.Four,
                     vscode.ViewColumn.Five, vscode.ViewColumn.Six, vscode.ViewColumn.Seven, vscode.ViewColumn.Eight, vscode.ViewColumn.Nine];
    for (const [i, letter] of letters.slice(0, columns.length).entries()) {
      const d = await read(t.id, letter);
      if (d) await open(t.id, letter, d, columns[i]);
    }
  });

  /** Approve lands the task. Its changes never opened in this window, the person is asked once first: approving
   *  unread work is the failure Graphene is for. Every Approve comes here: Home's, the graph's, a diff's title's. */
  const approve = async (id: string) => {
    if (!session.seen.has(id)) {
      const pick = await vscode.window.showWarningMessage(C.plain(`You have not opened the changes of “${name(id)}” yet.`),
                                                          { modal: true, detail: "Approving lands them in your repository." },
                                                          "Open Changes", "Approve Anyway");
      if (pick === "Open Changes") return void vscode.commands.executeCommand("graphene.openDiff", { id });
      if (pick !== "Approve Anyway") return;
    }
    await session.act(C.signOff(id));
  };

  cmd("pickFork", async (arg) => {
    const given = typeof arg === "object" ? arg : undefined;
    const d = given?.id && given.fork ? { id: given.id, fork: given.fork } : current();
    if (!d?.fork) return void vscode.window.showInformationMessage("Graphene: open an attempt's changes first, then keep it.");
    if (await session.act(C.pickFork(d.id, d.fork))) {
      const land = await vscode.window.showInformationMessage(`Attempt ${d.fork} is kept for “${C.plain(name(d.id))}”. Approve it to land it.`, "Approve");
      if (land) await approve(d.id);
    }
  });

  cmd("signOff", async (arg) => {
    const id = idOf(arg) ?? current()?.id;
    if (!id) return void vscode.window.showInformationMessage("Graphene: open a task's changes first, then approve it.");
    await approve(id);
  });
}
