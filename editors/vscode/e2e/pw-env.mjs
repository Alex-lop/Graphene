// Imported before playwright-core: its ffmpeg (for video) lives in e2e/.pw, not in the person's cache.
import path from "node:path";
import { fileURLToPath } from "node:url";

process.env.PLAYWRIGHT_BROWSERS_PATH ||= path.join(path.dirname(fileURLToPath(import.meta.url)), ".pw");
