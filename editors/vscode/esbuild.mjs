// Two bundles: the extension (Node, run by VS Code) and the graph (the webview's script); a third, the
// preview's, puts a fixture state into the graph with no VS Code around (media/preview.html).
import { build } from "esbuild";

const common = { bundle: true, sourcemap: false, logLevel: "warning", legalComments: "none" };
await Promise.all([
  build({ ...common, entryPoints: ["src/extension.ts"], outfile: "dist/extension.js",
          platform: "node", format: "cjs", target: "node20", external: ["vscode"] }),
  build({ ...common, entryPoints: ["src/graph/main.ts"], outfile: "dist/graph.js",
          platform: "browser", format: "iife", target: "es2022" }),
  build({ ...common, entryPoints: ["src/graph/preview.ts"], outfile: "dist/preview.js",
          platform: "browser", format: "iife", target: "es2022" }),
]);
