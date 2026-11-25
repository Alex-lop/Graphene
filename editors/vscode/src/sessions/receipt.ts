// A receipt: what a card says about the work after it happened, from its tool calls and nothing else. The
// files it changed; the tests and checks it ran, the last run of each command deciding; and what is worth a
// second look. Three honest states for tests: passed, failed, ran none (and a fourth it will not hide: ran, and
// the result was not seen). A tick only for a pass that was seen: the tool's own summary saying so, or its own
// exit code of 0, and never against an exit code that says otherwise. A flag is a fact with the line that
// shows it (what was run, never what it did), and a guess is labelled as a guess. Pure: calls in, a receipt out.
import * as path from "node:path";
import type { Changed, Check, Flag, FlagKind, Receipt } from "../state.ts";
import { COMMAND, str, WRITES } from "./events.ts";
import type { Call } from "./model.ts";

export type { Changed, Check, Flag, FlagKind, Receipt, Tests } from "../state.ts";

/** A path as a person reads it, and whether it is outside the session's folder. */
function place(file: string, cwd: string): { file: string; outside: boolean } {
  const out = (r: string) => r === ".." || r.startsWith("../") || r.startsWith("..\\"); // `..env` is a name, not a way out
  if (!file) return { file, outside: false };
  if (!path.isAbsolute(file)) return { file, outside: out(file) };
  if (!cwd) return { file, outside: false };
  const r = path.relative(cwd, file);
  return r && !out(r) && !path.isAbsolute(r) ? { file: r.split(path.sep).join("/"), outside: false } : { file, outside: true };
}

/** One simple command of a line. `then`: what joins it to the next (`&&`, `||`, `;`, `|`, `&`, or "" for the
 *  last). `loose`: it runs inside a `sh -c`, whose exit code is not its own. */
export interface Part { text: string; then: string; loose?: boolean }

/** A command line as its simple commands. Quotes are respected, and a `sh -c '…'` is read for what it runs. A
 *  subshell or a here-document is read as words, which is enough to find a tool's name and never enough to prove
 *  an exit code. */
export function commands(line: string): Part[] {
  const out: Part[] = [];
  let text = "", quote = "";
  const push = (t: string, then: string) => {
    const inner = /^(?:ba|z|da)?sh\s+-[a-z]*c\s+(['"])([\s\S]*)\1$/.exec(t.trim()); // `bash -lc "pytest -q"`: what it runs
    if (inner) for (const p of commands(inner[2]!)) out.push({ ...p, then: p.then || then, loose: true });
    else out.push({ text: t.trim(), then });
  };
  for (let i = 0; i < line.length; i++) {
    const c = line[i]!, two = line.slice(i, i + 2);
    if (quote) { text += c; if (c === quote) quote = ""; else if (c === "\\" && quote === '"') text += line[++i] ?? ""; continue; }
    if (c === "'" || c === '"') { quote = c; text += c; continue; }
    if (c === "\\") { text += c + (line[++i] ?? ""); continue; }
    const op = two === "&&" || two === "||" ? two : c === ";" || c === "\n" ? ";" : c === "|" || c === "&" ? c : "";
    // `2>&1` and `&>file` are redirections, not a join
    if (!op || (c === "&" && two !== "&&" && (/[0-9>]$/.test(text) || line[i + 1] === ">"))) { text += c; continue; }
    if (text.trim()) push(text, op); // an operator with nothing before it (`&` then a new line) joins nothing new
    text = "";
    if (op.length === 2) i++;
  }
  if (text.trim()) push(text, "");
  else if (out.length && out.at(-1)!.then === ";") out.at(-1)!.then = "";
  return out;
}

/** A command with what is inside its quotes taken out: a flag named in a commit's message is not a flag given. */
const unquoted = (text: string): string => text.replace(/"(?:[^"\\]|\\.)*"|'[^']*'/g, '""');

/** The words a simple command starts with once what merely carries it is taken off: variables set for it, `time`,
 *  `sudo`, `timeout 60`, a path to it, and the runners (`uv run`, `npx`, `python -m`, …). `loose`: it was carried
 *  by something that keeps its exit code from being the line's (`!`, `if`, a loop's `do`, `xargs`). */
function bare(text: string): { text: string; loose: boolean } {
  let t = text.replace(/^\(+\s*/, ""), loose = false;
  for (let was = ""; was !== t;) {
    was = t;
    const freed = t.replace(/^(!|if|then|else|elif|do|while|until|xargs(\s+-\S+)*)\s+/, "");
    if (freed !== t) { t = freed; loose = true; }
    t = t.replace(/^[A-Za-z_][A-Za-z0-9_]*=("[^"]*"|'[^']*'|\S*)\s+/, "")
      .replace(/^(time|sudo|command|exec|nohup|env|caffeinate(\s+-\S+)*|nice(\s+-n\s*\S+)?|timeout\s+(-\S+\s+)*\S+)\s+/, "")
      .replace(/^(uv|poetry|pipenv|pdm|hatch|rye)\s+run\s+(-\S+\s+)*/, "")
      .replace(/^(npx|bunx|pnpx)\s+(-\S+\s+)*/, "")
      .replace(/^(pnpm|yarn)\s+(exec|dlx)\s+/, "")
      .replace(/^bundle\s+exec\s+/, "")
      // `docker compose run app pytest`: what runs in the container, whose exit code docker hands on
      .replace(/^docker(-compose|\s+compose)?\s+(run|exec)\s+.*?\s(?=(pytest|py\.test|python[0-9.]*|npm|pnpm|yarn|bun|jest|vitest|go|cargo|make|rspec|mvn|gradle)(\s|$))/, "")
      .replace(/^python[0-9.]*\s+-m\s+(?=pytest|mypy|ruff|unittest)/, "")
      .replace(/^(\/[^\s/]+)+\/(?=[^\s/]+(\s|$))/, ""); // /bin/rm is rm
  }
  return { text: t, loose };
}

/** What a tool's output says of a run, read from the shape of its own summary and never from a word that happens
 *  to be there: that tests passed, that some failed, or that none ran. */
interface Said { passed?: string; failed?: string; none?: string; n?: number }
interface Tool {
  tool: string; kind: "test" | "check"; is: RegExp;
  /** A run of it that runs no test, by its arguments: it lists, compiles or prints help. */
  dry?: RegExp;
  says(out: string): Said;
  /** Its output has no last line that sums up the whole run: a pass read from it needs the output whole. */
  whole?: boolean;
}
const last = (out: string, re: RegExp): string => [...out.matchAll(re)].at(-1)?.[0].trim() ?? "";
const first = (out: string, re: RegExp): string => re.exec(out)?.[0].trim() ?? "";
const plain = (s: string): string => s.replace(/^=+\s*|\s*=+$/g, "");

/** pytest's summary is its last line of counts, ending in the time it took: `1 failed, 2 passed in 0.31s`. */
function pytest(out: string): Said {
  // every summary in the output is read: a line that ran pytest twice, or a loop, is failed by any of them
  const sums = [...out.matchAll(/^[= ]*(?:\d+ [a-z]+(?:, )?)+ in [\d.]+s(?: \([\d:]+\))?[= ]*$/gm)].map((m) => plain(m[0].trim()));
  if (!sums.length) return /^(=+ )?no tests ran\b|\bcollected 0 items\b/m.test(out) ? { none: "its output says no tests ran" } : {};
  const bad = sums.find((s) => /\b[1-9]\d* (failed|errors?)\b/.test(s)), good = sums.filter((s) => /\b[1-9]\d* passed\b/.test(s)).at(-1);
  if (bad) return { failed: bad };
  return good ? { passed: good, n: sums.length } : { none: `its output says ${sums.at(-1)}: no test passed or failed` };
}
/** unittest ends in `OK` or `FAILED (…)` under `Ran N tests in …`. */
function unittest(out: string): Said {
  const ran = last(out, /^Ran \d+ tests? in [\d.]+s$/gm);
  if (/^FAILED \(/m.test(out)) return { failed: first(out, /^FAILED \([^)]*\)/m) };
  if (/^NO TESTS RAN\b/m.test(out) || ran.startsWith("Ran 0 tests")) return { none: "its output says it ran 0 tests" };
  return ran && /^OK\b/m.test(out) ? { passed: `${ran}, OK` } : {};
}
/** Node's test runner counts: `ℹ pass 4`, `ℹ fail 0` (as TAP, `# pass 4`). */
function nodeTest(out: string): Said {
  const fails = [...out.matchAll(/^(?:ℹ|#) fail (\d+)$/gm)], passes = [...out.matchAll(/^(?:ℹ|#) pass (\d+)$/gm)];
  const bad = fails.find((m) => m[1] !== "0"), good = passes.filter((m) => m[1] !== "0").at(-1);
  if (bad) return { failed: bad[0] };
  if (!passes.length || !fails.length) return {};
  return good ? { passed: `${good[0]}, ${fails.at(-1)![0]}`, n: fails.length } : { none: "its output says 0 tests passed" };
}
/** Bun's ` 3 pass` and ` 0 fail`. */
function bunTest(out: string): Said {
  const fail = /^\s*(\d+) fail$/m.exec(out), pass = /^\s*(\d+) pass$/m.exec(out);
  if (fail && fail[1] !== "0") return { failed: fail[0].trim() };
  return pass && fail ? (pass[1] === "0" ? { none: "its output says 0 pass" } : { passed: `${pass[0].trim()}, ${fail[0].trim()}` }) : {};
}
/** Jest's `Tests: 1 failed, 2 passed, 3 total`, Vitest's `Tests  2 failed | 3 passed (5)`, mocha's `3 passing`;
 *  a script that runs Node's own runner says it as Node does. */
function jsTests(out: string): Said {
  // a suite or a file that failed to run fails the run, whatever its Tests line counts
  const lines = [...out.matchAll(/^\s*(?:Tests|Test Suites|Test Files):?\s+.*\b\d+ (?:passed|failed|total)\b.*$/gm), ...out.matchAll(/^\s*\d+ (?:passing|failing)\b.*$/gm)].map((m) => m[0].trim());
  if (!lines.length) return nodeTest(out);
  const bad = lines.find((l) => /\b[1-9]\d* (failed|failing)\b/.test(l)), tests = lines.filter((l) => !/^Test (Suites|Files)/.test(l));
  if (bad) return { failed: bad };
  const good = tests.filter((l) => /\b[1-9]\d* (passed|passing)\b/.test(l)).at(-1);
  return good ? { passed: good, n: tests.length } : tests.length ? { none: `its output says ${tests.at(-1)}` } : {};
}
/** go test says a line a package (`ok  pkg 0.01s`, `FAIL pkg`, `? pkg [no test files]`), and no line sums them up. */
function goTest(out: string): Said {
  if (/^(FAIL|--- FAIL)\b/m.test(out)) return { failed: first(out, /^(--- FAIL.*|FAIL\b.*)$/m).replace(/\s+/g, " ") };
  const ok = [...out.matchAll(/^ok\s+\S+.*$/gm)].map((m) => m[0]).filter((l) => !l.includes("[no tests to run]"));
  if (ok.length) return { passed: ok.at(-1)!.replace(/\s+/g, " ") };
  return /\[no test files\]|\[no tests to run\]/.test(out) ? { none: "its output says there were no tests to run" } : {};
}
function cargo(out: string): Said {
  const bad = first(out, /^(test result: FAILED\..*|error(\[E\d+\])?: .*)$/m);
  if (bad) return { failed: bad };
  const ok = [...out.matchAll(/^test result: ok\. (\d+) passed.*$/gm)], some = ok.find((m) => m[1] !== "0");
  return some ? { passed: some[0] } : ok.length ? { none: "its output says 0 tests passed" } : {};
}
const says = (passed: RegExp | null, failed: RegExp | null) => (out: string): Said => {
  const f = failed ? first(out, failed) : "", p = passed ? first(out, passed) : "";
  return f ? { failed: f } : p ? { passed: p } : {};
};

const JS_DRY = /\s(--help|--version|--listTests|--showConfig|--clearCache)(\s|$)/;
/** The tests and checks a receipt knows, by how a command names them and how their output sums up. */
const TOOLS: readonly Tool[] = [
  { tool: "pytest", kind: "test", is: /^(pytest|py\.test)\b/, dry: /\s(--collect-only|--co|--help|-h|--version|-V|--setup-plan|--fixtures|--markers)(\s|$)/, says: pytest },
  { tool: "unittest", kind: "test", is: /^unittest\b/, dry: /\s(--help|-h)(\s|$)/, says: unittest },
  { tool: "vitest", kind: "test", is: /^vitest\b/, dry: /\s(--help|--version|list)(\s|$)/, says: jsTests },
  { tool: "jest", kind: "test", is: /^jest\b/, dry: JS_DRY, says: jsTests },
  // a script named for the tests it runs (`npm run test:unit`) is a test run too
  { tool: "npm test", kind: "test", is: /^npm\s+((test|t)(\s|$)|run\s+test[\w:-]*(\s|$))/, dry: JS_DRY, says: jsTests },
  { tool: "pnpm test", kind: "test", is: /^pnpm\s+(run\s+)?test[\w:-]*(\s|$)/, dry: JS_DRY, says: jsTests },
  { tool: "yarn test", kind: "test", is: /^yarn\s+(run\s+)?test[\w:-]*(\s|$)/, dry: JS_DRY, says: jsTests },
  { tool: "bun test", kind: "test", is: /^bun\s+(run\s+)?test[\w:-]*(\s|$)/, dry: JS_DRY, says: bunTest },
  { tool: "node --test", kind: "test", is: /^node\b.*\s--test(\s|=|$)/, says: nodeTest },
  { tool: "go test", kind: "test", is: /^go\s+test\b/, dry: /\s(-c|-list(=\S+)?|-h|-help)(\s|$)/, says: goTest, whole: true },
  { tool: "cargo test", kind: "test", is: /^cargo\s+(test|nextest)\b/, dry: /\s(--no-run|--help|-h|--list|list)(\s|$)/, says: cargo },
  { tool: "make test", kind: "test", is: /^make\s+(-\S+\s+)*test(\s|$)/, dry: /\s(-n|--dry-run|--just-print)(\s|$)/, says: () => ({}) },
  // runners known by name alone: their own exit code decides, and where it is not theirs the result was not seen
  ...([["mvn", /^(\.\/)?mvnw?\s+(.*\s)?(test|verify)(\s|$)/], ["gradle", /^(\.\/)?gradlew?\s+(.*\s)?(test|check)(\s|$)/], ["rspec", /^rspec(\s|$)/],
        ["dotnet test", /^dotnet\s+test(\s|$)/], ["deno test", /^deno\s+test(\s|$)/], ["phpunit", /^(\.\/)?(vendor\/bin\/)?phpunit(\s|$)/], ["tox", /^tox(\s|$)/],
        ["nox", /^nox(\s|$)/], ["ctest", /^ctest(\s|$)/], ["swift test", /^swift\s+test(\s|$)/], ["mix test", /^mix\s+test(\s|$)/], ["rake test", /^rake\s+(test|spec)(\s|$)/]] as const)
    .map(([tool, is]): Tool => ({ tool, kind: "test", is, dry: /\s(--help|-h|--version|--list-tests)(\s|$)/, says: () => ({}) })),
  { tool: "ruff", kind: "check", is: /^ruff\s+(check\b|format\s+--check\b|\.|$)/, says: says(/All checks passed!/, /Found \d+ errors?/) },
  { tool: "eslint", kind: "check", is: /^eslint\b/, says: says(null, /✖ \d+ problems? \([1-9]\d* errors?/) },
  { tool: "tsc", kind: "check", is: /^tsc\b/, dry: /\s(--help|-h|--version|-v|--showConfig)(\s|$)/, says: says(null, /error TS\d+/) },
  { tool: "mypy", kind: "check", is: /^mypy\b/, says: says(/Success: no issues found/, /Found \d+ errors?/) },
];

/** clip() (events.ts) keeps a long output's start and its end: what it took out, it marks so. */
const clipped = (c: Call): boolean => c.out.includes("\n…\n") || c.err.includes("\n…\n");

/** One command's verdict for one tool it ran. The line's exit code is the tool's own when the tool is the line's
 *  last command, nothing is piped after it, nothing carries it that has an exit code of its own, and it did not
 *  run in the background. Where it is the tool's own: 0 with no word of a failure is a pass (unless the output
 *  says no test ran), and anything else is never a pass, whatever the output says. Where it is not, only the
 *  output's own summary decides, and without one the result was not seen. */
function verdict(t: Tool, c: Call, parts: readonly Part[], at: number, loose: boolean): Pick<Check, "verdict" | "why"> {
  if (c.interrupted) return { verdict: "unseen", why: "it was interrupted" };
  if (c.input.run_in_background === true || /^Command running in background\b/.test(c.out) || parts[at]!.then === "&") {
    return { verdict: "unseen", why: "it ran in the background: its result is not in this call" };
  }
  // after an `||` it ran only if what was before it failed: the line's exit code does not say that it ran
  const said = t.says(`${c.out}\n${c.err}`), own = at === parts.length - 1 && !loose && c.exit !== null && parts[at - 1]?.then !== "||";
  // how many times the line runs this tool: a failure in the output is one of theirs, and not the last one's
  // where that one's own exit code says it passed
  const times = parts.filter((p) => t.is.test(bare(p.text).text)).length;
  if (said.failed && !(own && c.exit === 0 && times > 1)) return { verdict: "failed", why: `its output says ${said.failed}` };
  if (own && c.exit !== 0) {
    // pytest and unittest exit 5 when they found nothing to run: no test ran, and none failed
    if (c.exit === 5 && (t.tool === "pytest" || t.tool === "unittest") && !said.passed) return { verdict: "none", why: "it exited 5: it found no test to run" };
    // nothing before it could have failed in its place: it is first, or what precedes it is joined by `;` or `||`
    const alone = parts.slice(0, at).every((p) => p.then === ";" || p.then === "||");
    if (alone || said.passed || said.none) return { verdict: "failed", why: `it exited ${c.exit}${said.passed ? `, though its output says ${said.passed}` : ""}` };
    return { verdict: "unseen", why: `the line exited ${c.exit}, and its output does not say this ran` };
  }
  if (said.none) return { verdict: "none", why: said.none };
  if (said.passed && !own) {
    // a pass read from the output alone needs the output to be all of it, and to be this run's
    if (t.whole && (clipped(c) || parts[at]!.then === "|")) return { verdict: "unseen", why: "its output was cut (a pipe, or its length), and no last line sums it up" };
    if (times > 1 && (said.n ?? 1) < times) return { verdict: "unseen", why: `the line ran it ${times} times, and its output sums up fewer` };
  }
  if (said.passed && !said.failed) return { verdict: "passed", why: `its output says ${said.passed}` };
  if (own) return { verdict: "passed", why: "it exited 0" };
  return { verdict: "unseen", why: c.exit === null ? "its exit code was not recorded" : "its output has no summary, and the exit code is another command's" };
}

/** A file that looks like a test's, by its name or its folder. */
export const isTest = (file: string): boolean =>
  /(^|\/)(tests?\.py|test_[^/]+\.py|[^/]+_tests?\.(py|go|rb)|[^/]+_spec\.rb|[^/]+\.(test|spec)\.[cm]?[jt]sx?|[^/]+Tests?\.(java|kt|cs|swift)|conftest\.py)$|(^|\/)(tests?|__tests__|spec)\//.test(file);

/** git's own options before its subcommand (`-C dir`, `-c k=v`, `--git-dir=…`) taken off: `git -C sub push` is a push. */
const git = (t: string): string => t.replace(/^git\s+((-C|-c|--git-dir|--work-tree|--namespace)(=\S+|\s+\S+)\s+|--\S+\s+|-[pP]\s+)*/, "git ");
const FORCE = /\s(--force(-with-lease)?(=\S+)?|-f|--no-verify)(\s|$)/, DRY = /\s(--dry-run|-n)(\s|$)/;

/** What of a simple command is worth a second look, named as what was run: `git push`, never "it pushed". */
function flagsOf(text: string): { kind: FlagKind; ran: string }[] {
  const t = git(unquoted(bare(text).text)), out: { kind: FlagKind; ran: string }[] = [];
  const dry = DRY.test(t), word = (re: RegExp) => re.exec(t)![0].replace(/\s+/g, " ");
  if (/^git push\b/.test(t) && !dry) out.push({ kind: "push", ran: "git push" });
  if (/^gh\s+pr\s+(create|merge|ready|close|edit)\b/.test(t)) out.push({ kind: "pull request", ran: word(/^gh\s+pr\s+\w+/) });
  else if (/^gh\s+api\s+\S*\/pulls\b/.test(t) && /\s(-f|-F|--field|--raw-field|(-X|--method)\s*(POST|PATCH|PUT))(\s|$)/.test(t)) out.push({ kind: "pull request", ran: "gh api on a pull request, with something to write" });
  if (/^git reset\s+(.*\s)?--hard\b/.test(t)) out.push({ kind: "hard reset", ran: "git reset --hard" });
  if (/^(rm|rmdir|unlink|shred)(\s|$)/.test(t) || /^find\s.*\s(-delete\b|-exec\s+rm\b)/.test(t)) out.push({ kind: "delete", ran: /^find\b/.test(t) ? "find with a delete" : word(/^\S+/) });
  else if (/^git (rm|clean)\b/.test(t) ? !dry : /^git (branch\s+(.*\s)?-D\b|stash\s+(drop|clear)\b)/.test(t)) out.push({ kind: "delete", ran: word(/^git \S+(\s+(drop|clear|-D))?/) });
  if (/^git\s/.test(t) && FORCE.test(t) && !/^git (rm|clean|branch)\b/.test(t)) out.push({ kind: "force", ran: /--no-verify/.test(t) ? "git with --no-verify (it skips the repository's hooks)" : "git with a force flag" });
  return out;
}

/** Two runs are of the same command when they run the same tool on the same things: how loudly it reports, and
 *  where its output goes, do not make it another. */
const same = (text: string): string => bare(text).text.replace(/\s+\d*>{1,2}&?\s*\S+/g, "")
  .replace(/\s(-q+|-v+|-s|--quiet|--verbose|--no-header|--tb=\S+|--color(=\S+)?|-p\s+no:\S+|-n\s+\S+)(?=\s|$)/g, "").replace(/\s+/g, " ").trim();

const escaped = (s: string) => s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");

/** The receipt of a card's calls, in the order they were made: by their time, since a subagent's file is read
 *  after its session's and its calls are not later for that. */
export function receipt(calls: readonly Call[], cwd: string): Receipt {
  const changed = new Map<string, Changed>(), runs = new Map<string, Check>(), flags: Flag[] = [];
  const flag = (f: Flag) => { if (!flags.some((x) => x.kind === f.kind && x.line === f.line)) flags.push(f); };
  const failing = new Map<string, string>(); // a test tool whose last run failed -> that run's output, until that tool passes
  let dir = ""; // where its commands run, as far as its own `cd`s say: the same command in another folder is another run
  const ordered = calls.map((c, i) => ({ c, i })).sort((a, b) => (a.c.at && b.c.at && a.c.at !== b.c.at ? (a.c.at < b.c.at ? -1 : 1) : a.i - b.i)).map((x) => x.c);
  for (const c of ordered) {
    if (WRITES.includes(c.name) && c.done && !c.error) {
      const at = place(str(c.input.file_path) || str(c.input.notebook_path), cwd);
      if (!at.file) continue;
      const kind = str(c.more.type), how = kind === "delete" ? "deleted" : kind === "create" ? "created" : "edited";
      const was = changed.get(at.file);
      changed.set(at.file, { ...at, how: was?.how === "created" && how === "edited" ? "created" : how });
      if (at.outside) flag({ kind: "outside the folder", line: at.file, note: "it wrote a file outside the session's folder", guess: false });
      if (how === "deleted") flag({ kind: "delete", line: at.file, note: "it deleted this file", guess: false });
      if (failing.size && isTest(at.file)) {
        // a fact: a test file was edited after a test run failed. That it is the failing test's own file is shown only
        // where that run's output names the file by its path; otherwise it is a guess, and said to be one
        const by = [...failing].find(([, out]) => new RegExp(`(^|[\\s"'(:=])(\\S*/)?${escaped(at.file)}(?![\\w.-])`, "m").test(out));
        const tool = (by ?? [...failing].at(-1)!)[0];
        flag({ kind: "test edited after it failed", line: at.file, guess: !by,
               note: by ? `edited after ${tool} failed; the failing run's output names this file` : `edited after ${tool} failed; the run's output does not name this file` });
      }
      continue;
    }
    if (c.name !== COMMAND) continue;
    const parts = commands(str(c.input.command));
    // a command that was refused did not run: it changed nothing and tested nothing
    const ran = c.done && !(c.error && c.exit === null);
    parts.forEach((p, i) => {
      const b = bare(p.text), loose = Boolean(p.loose) || b.loose;
      const to = /^cd\s+("[^"]*"|'[^']*'|\S+)\s*$/.exec(b.text)?.[1]?.replace(/^["']|["']$/g, "");
      if (to !== undefined && ran) dir = to === "-" ? `${dir}/-` : path.isAbsolute(to) || to.startsWith("~") ? to : path.posix.join(dir || ".", to);
      if (ran) {
        // the line exited 0 and this command had to succeed for it to: it is not after an `||`, and from it to the
        // line's end every command is joined by `&&`. Then it ran, and worked. Alone on a line that failed, it ran
        // and that is its own exit code. Anything else: it is on a line that ran, and no more is seen
        const sure = c.exit === 0 && !loose && parts[i - 1]?.then !== "||" && parts.slice(i).every((x) => x.then === "" || x.then === "&&");
        const only = parts.length === 1 && !loose && c.exit !== null;
        const exit = c.exit === null ? "with no exit code recorded" : `exited ${c.exit}`;
        for (const f of flagsOf(p.text)) {
          flag({ kind: f.kind, line: p.text, guess: !sure && !only,
                 note: sure ? `it ran ${f.ran}` : only ? `it ran ${f.ran}, which ${exit}` : `${f.ran} is on a line that ${exit}: whether it ran, or worked, is not seen` });
        }
      }
      const tool = TOOLS.find((x) => x.is.test(b.text));
      if (!tool || !ran || tool.dry?.test(unquoted(b.text))) return; // a run that lists, compiles or prints help runs no test
      const v = verdict(tool, c, parts, i, loose);
      runs.set(`${tool.tool}\n${same(p.text)}\n${dir}`, { tool: tool.tool, kind: tool.kind, command: p.text, ...v, at: c.endAt || c.at });
      if (tool.kind !== "test") return;
      if (v.verdict === "failed") failing.set(tool.tool, `${c.out}\n${c.err}`);
      else if (v.verdict === "passed") failing.delete(tool.tool);
    });
  }
  // every command's last run has its say: a pass of one does not clear another's failure, and a run that ran no
  // test is not a test that ran
  const checks = [...runs.values()], tests = checks.filter((x) => x.kind === "test" && x.verdict !== "none");
  return { changed: [...changed.values()], checks, flags,
           tests: !tests.length ? "none" : tests.some((x) => x.verdict === "failed") ? "failed" : tests.every((x) => x.verdict === "passed") ? "passed" : "unseen" };
}

/** A file two sessions wrote is worth a second look on both: said on each card that wrote it, with who else did.
 *  Files are compared as they are on disk, each from its own session's folder: two folders' README.md are two files. */
export function shared(mine: Receipt, cwd: string, others: readonly { title: string; cwd: string; files: readonly string[] }[]): Flag[] {
  const out: Flag[] = [];
  for (const f of mine.changed) {
    const at = path.resolve(cwd || "/", f.file);
    const who = others.filter((o) => o.files.some((x) => path.resolve(o.cwd || "/", x) === at)).map((o) => o.title);
    if (who.length) out.push({ kind: "written by two sessions", line: f.file, note: `also written by “${who.join("”, “")}”`, guess: false });
  }
  return out;
}
