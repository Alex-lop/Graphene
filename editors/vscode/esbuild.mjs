// The bundles: the extension (Node, run by VS Code), the graph's and Home's webview scripts; and the preview's,
// and the previews', which put a fixture state into the graph and Home with no VS Code around (media/preview.html,
// media/home-preview.html).
import { build } from "esbuild";

const common = { bundle: true, sourcemap: false, logLevel: "warning", legalComments: "none" };
await Promise.all([
  build({ ...common, entryPoints: ["src/extension.ts"], outfile: "dist/extension.js",
          platform: "node", format: "cjs", target: "node20", external: ["vscode"] }),
  build({ ...common, entryPoints: ["src/graph/main.ts"], outfile: "dist/graph.js",
          platform: "browser", format: "iife", target: "es2022" }),
  build({ ...common, entryPoints: ["src/home/main.ts"], outfile: "dist/home.js",
          platform: "browser", format: "iife", target: "es2022" }),
  build({ ...common, entryPoints: ["src/graph/preview.ts"], outfile: "dist/preview.js",
          platform: "browser", format: "iife", target: "es2022" }),
  // Home's model is the host's (cards.ts), whose commands join paths: a browser's stand-in for node:path will do
  build({ ...common, entryPoints: ["src/home/preview.ts"], outfile: "dist/home-preview.js",
          platform: "browser", format: "iife", target: "es2022", alias: { "node:path": "./src/home/path.ts" } }),
]);
