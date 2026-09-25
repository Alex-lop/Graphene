import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

// The built page is committed under the Python package and ships in the wheel, so installing
// needs no Node. Asset names are fixed: `graphene ui --export` inlines them by name, and CI
// fails when a build changes a committed file.
export default defineConfig({
  plugins: [react()],
  base: "./",
  build: {
    outDir: "../src/graphene_map/ui/static",
    emptyOutDir: true,
    sourcemap: false,
    cssCodeSplit: false,
    rollupOptions: {
      output: {
        entryFileNames: "assets/app.js",
        chunkFileNames: "assets/[name].js",
        assetFileNames: "assets/app[extname]",
        codeSplitting: false,
      },
    },
  },
  // a component test renders to a string with react-dom/server: no browser, no jsdom, no new dependency
  test: { environment: "node", include: ["src/**/*.test.ts", "src/**/*.test.tsx"] },
});
