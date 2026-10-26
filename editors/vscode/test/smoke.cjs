// The smoke test: the local VS Code (VSCODE_EXECUTABLE, or the Mac's /Applications one) opens a temp
// workspace with the extension, and test/smoke-suite.cjs checks it activates and its commands register.
// Skipped, exit 0, when no VS Code is there (CI).
const { existsSync, mkdtempSync, mkdirSync, rmSync, writeFileSync } = require("node:fs");
const { tmpdir } = require("node:os");
const path = require("node:path");

// VS Code listens on a Unix socket under --user-data-dir, and a socket path longer than 103 bytes fails on
// macOS; a long TMPDIR (a sandbox's, a session's scratch) would break it, so /tmp then
const SHORT = tmpdir().length <= 50 ? tmpdir() : "/tmp";

const MAC = ["Code", "Electron"].map((n) => `/Applications/Visual Studio Code.app/Contents/MacOS/${n}`); // 1.143 names it Code
const exe = process.env.VSCODE_EXECUTABLE || MAC.find(existsSync) || MAC[0];
if (!existsSync(exe)) {
  console.log(`smoke: skipped, no VS Code at ${exe} (set VSCODE_EXECUTABLE to run it)`);
  process.exit(0);
}
if (!existsSync(path.join(__dirname, "..", "dist", "extension.js"))) {
  console.error("smoke: build first (npm run build)");
  process.exit(1);
}

(async () => {
  const { runTests } = require("@vscode/test-electron");
  const base = mkdtempSync(path.join(SHORT, "graphene-vscode-"));
  const workspace = path.join(base, "repo");
  mkdirSync(path.join(workspace, ".graphene"), { recursive: true }); // the store's directory makes the extension activate
  writeFileSync(path.join(workspace, ".graphene", "graphene.db"), "");
  writeFileSync(path.join(workspace, "README.md"), "a repo with a plan\n");
  try {
    await runTests({
      vscodeExecutablePath: exe,
      extensionDevelopmentPath: path.join(__dirname, ".."),
      extensionTestsPath: path.join(__dirname, "smoke-suite.cjs"),
      launchArgs: [workspace, "--disable-extensions", "--disable-workspace-trust", "--skip-welcome", "--skip-release-notes",
                   "--user-data-dir", path.join(base, "user"), "--extensions-dir", path.join(base, "ext")],
      extensionTestsEnv: { GRAPHENE_SMOKE: "1", CLAUDECODE: "1" }, // the mark the extension must take out
    });
    console.log("smoke: the extension activated in the local VS Code and its commands are registered");
  } catch (err) {
    console.error("smoke: failed", err);
    process.exitCode = 1;
  } finally {
    rmSync(base, { recursive: true, force: true });
  }
})();
