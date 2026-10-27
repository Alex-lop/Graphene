// A task's or a fork's changes in VS Code's own diff editor, multi-file where it can; a race's forks side by
// side; picking a fork and signing off from there. Every side at a revision comes from `git show` in the
// snapshot's repo, read-only, under this module's own scheme; a running agent's side is its file on disk.
import { execFile } from "node:child_process";
import * as path from "node:path";
import * as vscode from "vscode";
import * as C from "./commands.ts";
import type { Session, UI } from "./session.ts";

export const SCHEME = "graphene-git";

type Arg = string | { id?: string; fork?: string; task?: { id: string } } | undefined;
/** Which diff a side belongs to, kept in its URI so a title action knows what it acts on. */
interface Query { repo: string; rev: string; id: string; fork: string | null }

/** A side as a URI: the file on disk, or `git show REV:PATH` under this module's scheme. */
export function sideUri(side: C.Side, id: string, fork: string | null): vscode.Uri {
  const file = vscode.Uri.file(path.join(side.repo, side.path));
  if (side.rev === null) return file;
  const q: Query = { repo: side.repo, rev: side.rev, id, fork };
  return file.with({ scheme: SCHEME, query: JSON.stringify(q) });
}

function queryOf(uri: vscode.Uri | undefined): Query | null {
  if (!uri || uri.scheme !== SCHEME) return null;
  try { return JSON.parse(uri.query) as Query; } catch { return null; }
}

/** The diff the active tab shows, when it is one of ours. */
function activeDiff(): { id: string; fork: string | null } | null {
  const input = vscode.window.tabGroups.activeTabGroup.activeTab?.input;
  if (input instanceof vscode.TabInputTextDiff) {
    const q = queryOf(input.original) ?? queryOf(input.modified);
    if (q) return { id: q.id, fork: q.fork };
  }
  return null;
}

/** Is a tab one of our diffs: a diff editor with a side of ours, or a multi-file one (its input class is newer
 *  than the API this extension is typed against, so it is read loosely). */
function ours(input: unknown): boolean {
  if (input instanceof vscode.TabInputTextDiff) return Boolean(queryOf(input.original) ?? queryOf(input.modified));
  const multi = input as { textDiffs?: { original: vscode.Uri }[] } | undefined;
  return Boolean(multi?.textDiffs?.some((d) => queryOf(d.original)));
}

export function register(context: vscode.ExtensionContext, session: Session, _ui: UI) {
  // what one of our diffs showed last: the multi-file editor's tab has no URI an action can read
  let last: { id: string; fork: string | null } | null = null;
  const current = () => activeDiff() ?? last;

  context.subscriptions.push(vscode.workspace.registerTextDocumentContentProvider(SCHEME, {
    provideTextDocumentContent(uri) {
      const q = queryOf(uri);
      if (!q || !q.rev) return ""; // a side the file is not on
      const rel = path.relative(q.repo, uri.fsPath);
      return new Promise<string>((resolve) =>
        execFile("git", ["-C", q.repo, "show", `${q.rev}:${rel}`], { maxBuffer: 64 * 1024 * 1024 }, (err, out) =>
          resolve(err ? "" : String(out)))); // not in that revision: nothing there
    },
  }));

  // the title actions (Keep This Fork, Sign Off) show on our diffs: lane 2a's package.json reads these keys
  const keys = () => {
    const d = current();
    const t = d && session.tasks().find((x) => x.id === d.id);
    void vscode.commands.executeCommand("setContext", "graphene.diff.fork", Boolean(d?.fork && t && t.state !== "done"));
    void vscode.commands.executeCommand("setContext", "graphene.diff.review", Boolean(d && t?.state === "review"));
  };
  context.subscriptions.push(vscode.window.tabGroups.onDidChangeTabs(() => {
    const open = vscode.window.tabGroups.all.flatMap((g) => g.tabs).some((tab) => ours(tab.input));
    if (!open) last = null; // every diff of ours is closed
    keys();
  }), vscode.window.onDidChangeActiveTextEditor(keys), session.onDidChange(keys));

  const idOf = (arg: Arg) => (typeof arg === "string" ? arg : arg?.task?.id ?? arg?.id);
  const name = (id: string) => session.tasks().find((t) => t.id === id)?.title ?? id;

  /** `graphene node diff --json`, or the refusal said to the person and null. */
  const read = async (id: string, fork: string | null): Promise<C.Diff | null> => {
    const out = await session.run(C.nodeDiff(id, fork));
    if (out.code !== 0) {
      void vscode.window.showInformationMessage(`Graphene: ${C.firstLine(out.stderr, out.stdout)}`);
      return null;
    }
    try { return C.parseDiff(out.stdout); } catch {
      // nothing to show yet is said in words, on stdout, exit 0 (the CLI as it is)
      void vscode.window.showInformationMessage(`Graphene: ${C.firstLine(out.stdout, out.stderr, "node diff gave no JSON")}`);
      return null;
    }
  };

  /** All of a diff's files in one multi-file editor (vscode.changes), else one diff editor a file. */
  const open = async (id: string, fork: string | null, d: C.Diff, column?: vscode.ViewColumn) => {
    last = { id, fork };
    const title = C.diffTitle(name(id), fork, d);
    const pairs = C.diffPairs(d);
    if (!pairs.length) {
      void vscode.window.showInformationMessage(`Graphene: ${d.said[0] ?? `${name(id)} changed no file`}`);
      return;
    }
    if (d.said.length) vscode.window.setStatusBarMessage(`$(info) ${d.said.join(" · ")}`, 8000);
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

  cmd("openDiff", async (arg) => {
    const id = idOf(arg);
    if (!id) return;
    const fork = typeof arg === "object" ? arg.fork ?? null : null;
    const d = await read(id, fork);
    if (d) await open(id, fork, d);
  });

  cmd("compareForks", async (arg) => {
    const id = idOf(arg);
    const t = id ? session.tasks().find((x) => x.id === id) : undefined;
    if (!t) return;
    const letters = t.forks.map((f) => f.letter).filter(Boolean);
    if (!letters.length) return void vscode.window.showInformationMessage(`Graphene: ${t.title} has no forks racing.`);
    const columns = [vscode.ViewColumn.One, vscode.ViewColumn.Two, vscode.ViewColumn.Three, vscode.ViewColumn.Four,
                     vscode.ViewColumn.Five, vscode.ViewColumn.Six, vscode.ViewColumn.Seven, vscode.ViewColumn.Eight, vscode.ViewColumn.Nine];
    for (const [i, letter] of letters.slice(0, columns.length).entries()) {
      const d = await read(t.id, letter);
      if (d) await open(t.id, letter, d, columns[i]);
    }
  });

  cmd("pickFork", async (arg) => {
    const given = typeof arg === "object" ? arg : undefined;
    const d = given?.id && given.fork ? { id: given.id, fork: given.fork } : current();
    if (!d?.fork) return void vscode.window.showInformationMessage("Graphene: open a fork's diff first, then keep it.");
    if (await session.act(C.pickFork(d.id, d.fork))) {
      const land = await vscode.window.showInformationMessage(`Fork ${d.fork} is now ${name(d.id)}'s work. Sign off to land it.`, "Sign Off");
      if (land) await session.act(C.signOff(d.id));
    }
  });

  cmd("signOff", async (arg) => {
    const id = idOf(arg) ?? current()?.id;
    if (!id) return void vscode.window.showInformationMessage("Graphene: open a task's diff first, then sign off.");
    await session.act(C.signOff(id));
  });
}
