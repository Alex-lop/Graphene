// Run inside the extension host by test/smoke.cjs: the extension is active (the workspace holds the store),
// every contributed command is registered, and the two views resolve without throwing.
const assert = require("node:assert/strict");
const vscode = require("vscode");

const COMMANDS = ["showGraph", "openCockpit", "auto", "envelope", "runReady", "stop", "accept", "acceptAll", "addStep", "link",
                  "editStep", "dropStep", "tell", "init", "refresh"].map((c) => `graphene.${c}`);

exports.run = async () => {
  const ext = vscode.extensions.getExtension("alex-lop.graphene-vscode");
  assert.ok(ext, "the extension is installed in the test host");
  await ext.activate();
  assert.ok(ext.isActive, "the extension activated");
  const all = await vscode.commands.getCommands(true);
  for (const c of COMMANDS) assert.ok(all.includes(c), `${c} is registered`);
  const contributed = ext.packageJSON.contributes.commands.map((c) => c.command).sort();
  assert.deepEqual(contributed, [...COMMANDS].sort(), "package.json names exactly these commands");
  await vscode.commands.executeCommand("graphene.refresh"); // reads the plan: graphene may be missing here, and that is a state, not a throw
  await vscode.commands.executeCommand("graphene.showGraph"); // the panel opens
  await vscode.commands.executeCommand("workbench.view.extension.graphene"); // the container with the tree and the graph view
  await vscode.commands.executeCommand("workbench.action.openWalkthrough", `${ext.id}#start`, false); // Get started
  await new Promise((r) => setTimeout(r, 1500));
};
