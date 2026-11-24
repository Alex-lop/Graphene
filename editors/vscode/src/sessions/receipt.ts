// A receipt: what a card says about the work after it happened, from its tool calls and nothing else. The
// files it changed; the tests and checks it ran, the last run of each deciding; and what is worth a second
// look. Three honest states for tests: passed, failed, ran none (and a fourth it will not hide: ran, and the
// result was not seen). A tick only for a pass that was seen. A flag is a fact with the line that shows it,
// never a verdict, and a guess is labelled as a guess. Pure: calls in, a receipt out.
import * as path from "node:path";
import type { Changed, Check, Flag, FlagKind, Receipt } from "../state.ts";
import { COMMAND, str, WRITES } from "./events.ts";
import type { Call } from "./model.ts";

export type { Changed, Check, Flag, FlagKind, Receipt, Tests } from "../state.ts";

/** A path as a person reads it, and whether it is outside the session's folder. */
function place(file: string, cwd: string): { file: string; outside: boolean } {
  if (!file) return { file, outside: false };
  if (!path.isAbsolute(file)) return { file, outside: file.startsWith("..") };
  if (!cwd) return { file, outside: false };
  const r = path.relative(cwd, file);
  return r && !r.startsWith("..") && !path.isAbsolute(r) ? { file: r.split(path.sep).join("/"), outside: false } : { file, outside: true };
}

/** A command line as its simple commands, each with what joins it to the next (`&&`, `||`, `;`, `|`, `&`, or ""
 *  for the last). Quotes are respected; a subshell or a here-document is read as words, which is enough to find a
 *  tool's name and never enough to prove an exit code (`simple` below says when one is). */
export function commands(line: string): { text: string; then: string }[] {
  const out: { text: string; then: string }[] = [];
  let text = "", quote = "";
  for (let i = 0; i < line.length; i++) {
    const c = line[i]!, two = line.slice(i, i + 2);
    if (quote) { text += c; if (c === quote) quote = ""; else if (c === "\\" && quote === '"') text += line[++i] ?? ""; continue; }
    if (c === "'" || c === '"') { quote = c; text += c; continue; }
    if (c === "\\") { text += c + (line[++i] ?? ""); continue; }
    const op = two === "&&" || two === "||" ? two : c === ";" || c === "\n" ? ";" : c === "|" || c === "&" ? c : "";
    // `2>&1` and `&>file` are redirections, not a join
    if (!op || (c === "&" && two !== "&&" && (/[0-9>]$/.test(text) || line[i + 1] === ">"))) { text += c; continue; }
    if (text.trim()) out.push({ text: text.trim(), then: op }); // an operator with nothing before it (`&` then a new line) joins nothing new
    text = "";
    if (op.length === 2) i++;
  }
  if (text.trim()) out.push({ text: text.trim(), then: "" });
  else if (out.length && out.at(-1)!.then === ";") out.at(-1)!.then = "";
  return out;
}

/** The words a simple command starts with once what merely carries it is taken off: variables set for it, `time`,
 *  `sudo`, and the runners (`uv run`, `npx`, `python -m`, …). */
function bare(text: string): string {
  let t = text.replace(/^\(+\s*/, "");
  for (let was = ""; was !== t;) {
    was = t;
    t = t.replace(/^[A-Za-z_][A-Za-z0-9_]*=("[^"]*"|'[^']*'|\S*)\s+/, "")
      .replace(/^(time|sudo|command|exec|nohup|env)\s+/, "")
      .replace(/^(uv|poetry|pipenv|pdm|hatch|rye)\s+run\s+(-\S+\s+)*/, "")
      .replace(/^(npx|bunx|pnpx)\s+(-\S+\s+)*/, "")
      .replace(/^(pnpm|yarn)\s+(exec|dlx)\s+/, "")
      .replace(/^python[0-9.]*\s+-m\s+(?=pytest|mypy|ruff|unittest)/, "");
  }
  return t;
}

interface Tool { tool: string; kind: "test" | "check"; is: RegExp; passed?: RegExp; failed?: RegExp }
/** The tests and checks a receipt knows, by how a command names them and how their output sums up. A summary that
 *  says failed wins over one that says passed: `1 failed, 2 passed` is a failure. */
const TOOLS: readonly Tool[] = [
  { tool: "pytest", kind: "test", is: /^(pytest|py\.test)\b/, passed: /\b\d+ passed\b/, failed: /\b\d+ (failed|errors?)\b/ },
  { tool: "unittest", kind: "test", is: /^unittest\b/, passed: /^OK\b/m, failed: /^FAILED \(/m },
  { tool: "vitest", kind: "test", is: /^vitest\b/, passed: /Tests?\s+\d+ passed/, failed: /\b\d+ failed\b/ },
  { tool: "jest", kind: "test", is: /^jest\b/, passed: /Tests:\s+(\d+ \w+, )*\d+ passed/, failed: /Tests:\s+\d+ failed/ },
  { tool: "npm test", kind: "test", is: /^npm\s+(run\s+)?(test|t)\b(?![:-])/, passed: /Tests?:?\s+(\d+ \w+, )*\d+ passed|\b\d+ passed\b|^ℹ fail 0$|^# fail 0$/m, failed: /\b[1-9]\d* failed\b|^ℹ fail [1-9]|^# fail [1-9]|npm ERR! Test failed/m },
  { tool: "pnpm test", kind: "test", is: /^pnpm\s+(run\s+)?test\b(?![:-])/, passed: /\b\d+ passed\b|^ℹ fail 0$/m, failed: /\b[1-9]\d* failed\b|^ℹ fail [1-9]/m },
  { tool: "yarn test", kind: "test", is: /^yarn\s+(run\s+)?test\b(?![:-])/, passed: /\b\d+ passed\b|^ℹ fail 0$/m, failed: /\b[1-9]\d* failed\b|^ℹ fail [1-9]/m },
  { tool: "node --test", kind: "test", is: /^node\b.*\s--test\b/, passed: /^(ℹ|#) fail 0$/m, failed: /^(ℹ|#) fail [1-9]/m },
  { tool: "go test", kind: "test", is: /^go\s+test\b/, passed: /^ok\s/m, failed: /^(FAIL|--- FAIL)/m },
  { tool: "cargo test", kind: "test", is: /^cargo\s+(test|nextest)\b/, passed: /test result: ok\./, failed: /test result: FAILED|error(\[E\d+\])?:/ },
  { tool: "make test", kind: "test", is: /^make\s+(-\S+\s+)*test\b/ },
  { tool: "ruff", kind: "check", is: /^ruff\s+(check\b|format\s+--check\b|\.|$)/, passed: /All checks passed!/, failed: /Found \d+ errors?/ },
  { tool: "eslint", kind: "check", is: /^eslint\b/, failed: /✖ \d+ problems?/ },
  { tool: "tsc", kind: "check", is: /^tsc\b/, failed: /error TS\d+/ },
  { tool: "mypy", kind: "check", is: /^mypy\b/, passed: /Success: no issues found/, failed: /Found \d+ errors?/ },
];

/** One command's verdict for one tool it ran. The output's own summary decides where there is one. Without one
 *  the exit code decides, but only when it is that tool's: the tool is the line's last command, nothing is piped
 *  after it, and for a failure nothing before it could have failed in its place. Otherwise the result was not
 *  seen, and is said so. */
function verdict(t: Tool, c: Call, parts: readonly { text: string; then: string }[], at: number): Pick<Check, "verdict" | "why"> {
  const out = `${c.out}\n${c.err}`;
  if (c.interrupted) return { verdict: "unseen", why: "it was interrupted" };
  const failed = t.failed?.exec(out)?.[0], passed = t.passed?.exec(out)?.[0];
  if (failed) return { verdict: "failed", why: `its output says ${failed.trim()}` };
  if (passed) return { verdict: "passed", why: `its output says ${passed.trim()}` };
  const last = at === parts.length - 1;
  if (!last || c.exit === null) return { verdict: "unseen", why: !last ? "its output has no summary, and the exit code is a later command's" : "its exit code was not recorded" };
  if (c.exit === 0) return { verdict: "passed", why: "it exited 0" };
  const alone = parts.slice(0, at).every((p) => /^cd\s/.test(p.text) || p.then === ";" || p.then === "||");
  return alone ? { verdict: "failed", why: `it exited ${c.exit}` } : { verdict: "unseen", why: `the line exited ${c.exit}, and its output does not say this ran` };
}

/** A file that looks like a test's, by its name or its folder. */
export const isTest = (file: string): boolean => /(^|\/)(test_[^/]+\.py|[^/]+_test\.(py|go|rb)|[^/]+\.(test|spec)\.[cm]?[jt]sx?|conftest\.py)$|(^|\/)(tests?|__tests__|spec)\//.test(file);

const PUSH = /^git\s+(-\S+\s+)*push\b/, FORCE = /\s(--force(-with-lease)?(=\S+)?|-f|--no-verify)\b/;
const flagsOf = (text: string): { kind: FlagKind; note: string }[] => {
  const t = bare(text), out: { kind: FlagKind; note: string }[] = [];
  if (PUSH.test(t)) out.push({ kind: "push", note: "it pushed to a remote" });
  if (/^gh\s+pr\s+(create|merge|ready|close|edit)\b/.test(t)) out.push({ kind: "pull request", note: `it ran gh pr ${/^gh\s+pr\s+(\w+)/.exec(t)![1]}` });
  if (/^git\s+(-\S+\s+)*reset\s+(.*\s)?--hard\b/.test(t)) out.push({ kind: "hard reset", note: "it discarded uncommitted work and moved the branch" });
  if (/^(rm|rmdir|unlink|shred)\s/.test(t) || /^git\s+(rm|clean)\b/.test(t) || /^find\s.*\s-delete\b/.test(t)) out.push({ kind: "delete", note: "it deleted files with a command" });
  if (/^git\s/.test(t) && FORCE.test(t) && !/^git\s+(rm|clean)\b/.test(t)) out.push({ kind: "force", note: /--no-verify/.test(t) ? "it skipped the repository's hooks" : "it forced a git command" });
  return out;
};

/** The receipt of a card's calls, in the order they were made. */
export function receipt(calls: readonly Call[], cwd: string): Receipt {
  const changed = new Map<string, Changed>(), runs = new Map<string, Check>(), flags: Flag[] = [];
  const flag = (f: Flag) => { if (!flags.some((x) => x.kind === f.kind && x.line === f.line)) flags.push(f); };
  const last: { failed: { tool: string; out: string } | null } = { failed: null }; // the last test run that failed, until one passes
  for (const c of calls) {
    if (WRITES.includes(c.name) && c.done && !c.error) {
      const at = place(str(c.input.file_path) || str(c.input.notebook_path), cwd);
      if (!at.file) continue;
      const kind = str(c.more.type), how = kind === "delete" ? "deleted" : kind === "create" ? "created" : "edited";
      const was = changed.get(at.file);
      changed.set(at.file, { ...at, how: was?.how === "created" && how === "edited" ? "created" : how });
      if (at.outside) flag({ kind: "outside the folder", line: at.file, note: "it wrote a file outside the session's folder", guess: false });
      if (how === "deleted") flag({ kind: "delete", line: at.file, note: "it deleted this file", guess: false });
      const failedAt = last.failed;
      if (failedAt && isTest(at.file)) {
        // a fact: a test file was edited after a test run failed. Whether it is the failing test's file is proven only when the run's output names it
        const named = failedAt.out.includes(path.basename(at.file));
        flag({ kind: "test edited after it failed", line: at.file, guess: !named,
               note: named ? `edited after ${failedAt.tool} failed; the failing run's output names this file` : `edited after ${failedAt.tool} failed; the run's output does not name this file` });
      }
      continue;
    }
    if (c.name !== COMMAND) continue;
    const line = str(c.input.command), parts = commands(line);
    // a command that was refused did not run: it changed nothing and tested nothing
    const ran = c.done && !(c.error && c.exit === null);
    parts.forEach((p, i) => {
      const t = bare(p.text);
      if (ran) for (const f of flagsOf(p.text)) flag({ kind: f.kind, line: p.text, note: f.note, guess: false });
      const tool = TOOLS.find((x) => x.is.test(t));
      if (!tool || !ran) return;
      const v = verdict(tool, c, parts, i);
      runs.set(tool.tool, { tool: tool.tool, kind: tool.kind, command: p.text, ...v, at: c.endAt || c.at });
      if (tool.kind !== "test") return;
      if (v.verdict === "failed") last.failed = { tool: tool.tool, out: `${c.out}\n${c.err}` };
      else if (v.verdict === "passed") last.failed = null;
    });
  }
  const checks = [...runs.values()], tests = checks.filter((x) => x.kind === "test");
  return { changed: [...changed.values()], checks, flags,
           tests: !tests.length ? "none" : tests.some((x) => x.verdict === "failed") ? "failed" : tests.every((x) => x.verdict === "passed") ? "passed" : "unseen" };
}

/** A file two sessions wrote is worth a second look on both: said on each card that wrote it, with who else did. */
export function shared(mine: Receipt, others: readonly { title: string; files: readonly string[] }[]): Flag[] {
  const out: Flag[] = [];
  for (const f of mine.changed) {
    const who = others.filter((o) => o.files.includes(f.file)).map((o) => o.title);
    if (who.length) out.push({ kind: "written by two sessions", line: f.file, note: `also written by “${who.join("”, “")}”`, guess: false });
  }
  return out;
}
