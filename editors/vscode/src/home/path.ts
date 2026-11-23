// node:path for Home's preview in a browser (esbuild.mjs): only `join`, which the commands use.
export const join = (...parts: string[]) => parts.join("/").replace(/\/+/g, "/");
