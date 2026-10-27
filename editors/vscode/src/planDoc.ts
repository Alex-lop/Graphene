// The plan as a text document: Edit Plan as Text opens what `graphene plan --text` prints in a real editor
// tab, under this module's own file system, so save is the editor's own save. A save goes through
// `graphene plan edit --from -` with the cursor from when the text was read; a refusal leaves the tab dirty
// and puts each fault on its line; an applied save shows the plan as it is now.
import * as vscode from "vscode";
import * as C from "./commands.ts";
import type { Session, UI } from "./session.ts";

export const SCHEME = "graphene-plan";
export const URI = vscode.Uri.from({ scheme: SCHEME, path: "/plan.txt" });

export function register(context: vscode.ExtensionContext, session: Session, _ui: UI) {
  const faults = vscode.languages.createDiagnosticCollection("graphene");
  const changed = new vscode.EventEmitter<vscode.FileChangeEvent[]>();
  let cursor = 0; // the snapshot's, when the text was last read
  let mtime = Date.now();
  let text = "";

  const fail = (why: string) => { throw vscode.FileSystemError.Unavailable(why); };

  const fs: vscode.FileSystemProvider = {
    onDidChangeFile: changed.event,
    watch: () => ({ dispose() {} }),
    stat: () => ({ type: vscode.FileType.File, ctime: 0, mtime, size: Buffer.byteLength(text) }),
    readDirectory: () => [],
    createDirectory: () => fail("the plan is one document"),
    delete: () => fail("the plan is not a file to delete; drop its steps"),
    rename: () => fail("the plan is not a file to rename"),
    async readFile() {
      await session.refresh(); // the cursor the save is checked against is from no later than the text
      cursor = session.state?.cursor ?? 0;
      const out = await session.run(C.planText());
      if (out.code !== 0) fail(out.code === -1 ? "graphene was not found" : C.firstLine(out.stderr, out.stdout));
      text = out.stdout;
      return Buffer.from(text);
    },
    async writeFile(uri, content) {
      const typed = Buffer.from(content).toString();
      const out = await session.run(C.planApply(cursor), typed);
      const r = C.parseApplied(out.stdout, out.stderr);
      if (!r.applied && out.code !== 0) {
        faults.set(uri, C.faultRanges(r.faults, typed.split(/\r?\n/)).map((f) =>
          new vscode.Diagnostic(new vscode.Range(f.line, f.start, f.line, f.end), f.text, vscode.DiagnosticSeverity.Error)));
        fail(r.faults.map((f) => f.text).join("; ") || C.firstLine(out.stderr, out.stdout, "the plan refused it"));
      }
      faults.delete(uri);
      vscode.window.setStatusBarMessage(`$(check) ${r.said[0] ?? "the plan is as you wrote it"}`, 6000);
      text = typed;
      mtime = Date.now();
      void session.refresh();
      // the editor then reads the plan as it is now (ids given, "?" accepted), once its save is over
      setTimeout(() => changed.fire([{ type: vscode.FileChangeType.Changed, uri }]), 400);
    },
  };
  context.subscriptions.push(faults, changed, vscode.workspace.registerFileSystemProvider(SCHEME, fs, { isCaseSensitive: true }));

  context.subscriptions.push(vscode.commands.registerCommand("graphene.editPlan", async () => {
    if (!session.folder) return void vscode.window.showInformationMessage("Open a folder to edit its plan.");
    const doc = await vscode.workspace.openTextDocument(URI);
    await vscode.window.showTextDocument(doc, { preview: false });
  }));
}
