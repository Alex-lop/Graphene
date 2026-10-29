// Home, pure: what a person sees first in Graphene's side bar, from the snapshot, in plain words. Sections come
// in the order a person acts on them (what needs you, the suggested plan, who is working, what is up next, what
// is done); each card says what its task is for and what proves it, with its buttons. No VS Code and no DOM
// here: home.ts sends what this returns, home/main.ts draws it, and checkHome reads what the page sends back.
import { needs, OFFERS, offerOn } from "../needs.ts";
import { headline, SAY, usd, type Question, type State, type Task } from "../state.ts";
import { WHO } from "./who.ts";

export const ACTS = ["ask", "cancel", "startAll", "discardAll", "run", "stop", "drop", "answer", "openDiff", "compare", "keep",
                     "approve", "sendBack", "offer", "tryAgain", "allow", "message", "markDone", "showGraph", "demo", "setup",
                     "install", "setKey", "refresh", "openFolder"] as const;
export type Act = (typeof ACTS)[number];

export interface Btn { label: string; act: Act; id?: string; arg?: string; main?: boolean; title?: string }
export interface Line { k?: string; v: string; mono?: boolean; warn?: boolean }
export type Tone = "question" | "proposed" | "running" | "review" | "came-back" | "ready" | "waiting" | "done" | "yours";
export interface Card { key: string; tone: Tone; title: string; tag: string; lines: Line[]; buttons: Btn[] }
export interface Section { key: string; title: string; note: string; buttons: Btn[]; cards: Card[]; folded: boolean }
export interface Home { banner: string; goal: string; counts: string; sections: Section[]; empty: boolean }

const cut = (s: string, n: number) => (s.length > n ? `${s.slice(0, n - 1).trimEnd()}…` : s);
const files = (paths: string[]) => paths.join(", ");
const plural = (n: number, word: string) => `${n} ${word}${n === 1 ? "" : "s"}`;
const line = (k: string, v: string, more: Partial<Line> = {}): Line[] => (v ? [{ k, v, ...more }] : []);
/** `a: passed, 9 lines · b: running`: each attempt at a task, as one line. */
const attempts = (t: Task) => t.forks.map((f) => `${f.letter}: ${f.state || "waiting"}${f.lines !== null ? `, ${f.lines} lines` : ""}`).join(" · ");

/** The first words on the page when this is not a real run: a replay, or a race against the scripted stand-in. */
export function banner(s: State): string {
  if (s.replay) return `Demo replay: ${s.replay.shown}`;
  return s.stand_in ? "Practice run: a scripted stand-in answers for the AI, so nothing is spent" : "";
}

/** `2 working · 1 needs you · 3 of 6 done · $0.42 spent` */
export function countsLine(s: State): string {
  const sb = s.scoreboard;
  const parts: string[] = [];
  if (sb.running) parts.push(`${sb.running} working`);
  if (sb.need_you) parts.push(`${sb.need_you} need${sb.need_you === 1 ? "s" : ""} you`);
  if (sb.total) parts.push(`${sb.proven} of ${sb.total} done`);
  const spent = usd(s.spent);
  if (spent) parts.push(`${spent} spent`);
  return parts.join(" · ");
}

/** What a task is for, what it may change, and what proves it: the three lines a person reads before saying yes. */
function contract(t: Task, name: (id: string) => string): Line[] {
  return [
    ...line("What for", t.full && t.full !== t.title ? t.full : ""),
    { k: "May change", v: files(t.scope) || "no files named", mono: Boolean(t.scope.length) },
    { k: "Done when", v: t.check ? `${t.check} passes` : "you approve it", mono: Boolean(t.check) },
    ...line("After", t.needs.map(name).join(", ")),
  ];
}

/** A finished task's evidence: what changed, the check that proved it, and the attempt that was kept. */
function evidence(t: Task): Line[] {
  const kept = t.kept && t.forks.length > 1 ? `attempt ${t.kept.letter} of ${t.forks.length}${t.kept.why ? `: ${t.kept.why}` : ""}` : "";
  return [
    { k: "Changed", v: files(t.changed) || "no files", mono: Boolean(t.changed.length) },
    { k: "Check", v: t.check ? `${t.check} passed` : "none: your approval finishes it", mono: Boolean(t.check) },
    ...(t.hollow ? [{ v: "This check passed before the work too, so it does not prove the change. Read the changes.", warn: true }] : []),
    ...line("Kept", kept),
  ];
}

function question(q: Question, name: (id: string) => string): Card {
  const options = [...new Set([...(q.default ? [q.default] : []), ...q.options])];
  return {
    key: `q:${q.id}`, tone: "question", title: q.text, tag: "question",
    lines: [...line("About", q.about ? name(q.about) : ""), ...line("If unanswered", q.default ?? "")],
    buttons: [
      ...options.map((o) => ({ label: cut(o, 80), act: "answer" as const, id: q.id, arg: o, main: o === q.default,
                               title: o === q.default ? "the default: what happens if nobody answers" : o })),
      { label: "In your own words…", act: "answer", id: q.id },
    ],
  };
}

/** The moves a task that came back offers, in the cockpit's order and in plain words, then trying it again. */
function help(t: Task, titles: Record<string, string>): Btn[] {
  const words: Record<string, (on: string) => string> = {
    w: (on) => (on ? `Allow it to change ${on}` : "Allow the files it needs"),
    b: (on) => (on ? `Add a task for ${on}` : "Add a task for what it needs"),
    n: (on) => (on ? `Wait for ${on} first` : "Wait for another task first"),
    r: (on) => (on ? `Reopen ${on}` : "Reopen the task it needs"),
  };
  const offers = OFFERS.filter(([k]) => t.offers[k]).map(([k]) =>
    ({ label: cut(words[k]!(offerOn(k, t.offers[k]!, t, titles)), 80), act: "offer" as const, id: t.id, arg: k }));
  return [{ label: "Try again", act: "tryAgain", id: t.id, main: true, title: "a new agent, told why it came back" }, ...offers,
          { label: "Open changes", act: "openDiff", id: t.id }, { label: "Remove task", act: "drop", id: t.id }];
}

export function home(s: State, seen: ReadonlySet<string> = new Set()): Home {
  const titles: Record<string, string> = Object.fromEntries(s.tasks.map((t) => [t.id, t.title]));
  const name = (id: string) => titles[id] ?? id;
  const sections: Section[] = [];
  const section = (key: string, title: string, cards: Card[], more: Partial<Section> = {}) => {
    if (cards.length) sections.push({ key, title, note: "", buttons: [], cards, folded: false, ...more });
  };

  const waiting: Card[] = [];
  for (const n of needs(s)) {
    if (n.kind === "auto") {
      waiting.push({ key: "auto", tone: "came-back", title: "Auto mode is waiting for you", tag: "auto", lines: [{ v: n.why }],
                     buttons: n.key ? [{ label: "Set API key", act: "setKey", arg: n.endpoint ?? undefined, main: true }] : [] });
    } else if (n.kind === "question") {
      waiting.push(question(n.q, name));
    } else if (n.kind === "sign-off") {
      const t = n.t, opened = seen.has(t.id);
      const back: Btn = { label: "Send back…", act: "sendBack", id: t.id, title: "say what is wrong; an agent takes it again" };
      const passed = t.forks.filter((f) => f.state === "passed");
      if (passed.length > 1 && !t.kept) { // its check could not choose between them: the person keeps one first
        waiting.push({ key: `review:${t.id}`, tone: "review", title: t.title, tag: SAY.review,
                       lines: [{ k: "Attempts", v: attempts(t), mono: true },
                               { v: `${plural(passed.length, "attempt")} passed the check. Compare them and keep one, then approve it.`, warn: true }],
                       buttons: [{ label: "Compare attempts", act: "compare", id: t.id, main: true },
                                 ...passed.map((f) => ({ label: `Keep ${f.letter}`, act: "keep" as const, id: t.id, arg: f.letter, title: `attempt ${f.letter} becomes this task's work` })),
                                 back] });
        continue;
      }
      waiting.push({ key: `review:${t.id}`, tone: "review", title: t.title, tag: SAY.review,
                     lines: [...evidence(t), ...line("Last steps", t.tail.slice(-3).join(" · "), { mono: true }), // did it run its check itself?
                             { v: opened ? "You opened these changes." : "You have not opened these changes yet.", warn: !opened }],
                     buttons: [{ label: "Open changes", act: "openDiff", id: t.id, main: !opened },
                               { label: "Approve", act: "approve", id: t.id, main: opened, title: "it lands in your repository" }, back] });
    } else if (n.kind === "hand-back") {
      const t = n.t;
      waiting.push({ key: `help:${t.id}`, tone: "came-back", title: t.title, tag: SAY["came back"],
                     lines: [{ k: "Why", v: t.why || t.note || "it stopped before its check passed", warn: true },
                             ...line("Tries", t.attempts > 1 ? String(t.attempts) : ""), ...line("Wanted", files(t.outside), { mono: true })],
                     buttons: help(t, titles) });
    } else if (n.kind === "stopped") {
      const t = n.t, path = t.stopped[t.stopped.length - 1] ?? "a file";
      waiting.push({ key: `blocked:${t.id}`, tone: "came-back", title: t.title, tag: "blocked",
                     lines: [{ v: `Agent ${t.agent || "?"} tried to change ${path}, which is outside the files this task may change.`, warn: true }],
                     buttons: [{ label: `Allow it to change ${cut(path, 60)}`, act: "allow", id: t.id, main: true },
                               { label: "Open changes so far", act: "openDiff", id: t.id }] });
    } else if (n.kind === "yours") {
      const t = n.t;
      waiting.push({ key: `yours:${t.id}`, tone: "yours", title: t.title, tag: SAY.yours,
                     lines: [{ v: "This task is yours to do. When you have done it, its check runs." }, ...contract(t, name)],
                     buttons: [{ label: "Mark done", act: "markDone", id: t.id, main: true }] });
    }
  }
  section("needs", "Needs you", waiting);

  const suggested = s.tasks.filter((t) => t.state === "proposed");
  section("suggested", `Suggested plan · ${plural(suggested.length, "task")}`, suggested.map((t) => ({
    key: `p:${t.id}`, tone: "proposed" as const, title: t.title, tag: SAY.proposed, lines: contract(t, name),
    buttons: [{ label: "Remove", act: "drop" as const, id: t.id, title: "leave this task out of the plan" }],
  })), {
    note: "Read each task: what it may change, and what proves it is done. Remove what you do not want, then start.",
    buttons: [{ label: "Start", act: "startAll", main: true, title: "accept these tasks and start an agent on each" },
              { label: "Discard all", act: "discardAll" }],
  });

  const working = s.tasks.filter((t) => t.state === "running" && !t.stopped.length);
  section("working", `Working now · ${working.length}`, working.map((t) => {
    const quiet = t.idle !== null && t.idle > 8 ? `${Math.round(t.idle)} s` : "";
    return {
      key: `w:${t.id}`, tone: "running" as const, title: t.title, tag: SAY.running,
      lines: [...line("Agent", `${t.agent || "?"}${t.model ? ` · ${t.model}` : ""}`), ...line("Now", t.tail[t.tail.length - 1] ?? "", { mono: true }),
              ...line("Quiet for", quiet), ...line("Cost", usd(t.usd)), ...line("Attempts", attempts(t), { mono: true })],
      buttons: [{ label: "Open changes so far", act: "openDiff" as const, id: t.id },
                { label: "Message agent…", act: "message" as const, id: t.id, title: "it reads your line with its next step" },
                ...(t.forks.length > 1 ? [{ label: "Compare attempts", act: "compare" as const, id: t.id }] : [])],
    };
  }), { buttons: [{ label: "Stop all", act: "stop", title: "stop every agent: their tasks go back to the plan" }] });

  const next = s.tasks.filter((t) => t.state === "ready" || t.state === "waiting");
  section("next", `Up next · ${next.length}`, next.map((t) => ({
    key: `n:${t.id}`, tone: t.state === "ready" ? "ready" as const : "waiting" as const, title: t.title, tag: SAY[t.state],
    lines: [...line("Waits for", t.state === "waiting" ? t.needs.map(name).join(", ") : ""), ...contract(t, name).filter((l) => l.k !== "After")],
    buttons: [{ label: "Remove", act: "drop" as const, id: t.id }],
  })), { buttons: [{ label: "Run", act: "run", main: true, title: s.run.going ? "hand these to the run that is going"
                                                                            : "start an agent on every task that is ready" }] });

  const done = s.tasks.filter((t) => t.state === "done");
  section("done", `Done · ${done.length}`, done.map((t) => ({
    key: `d:${t.id}`, tone: "done" as const, title: t.title, tag: SAY.done, lines: evidence(t),
    buttons: [{ label: "Open changes", act: "openDiff" as const, id: t.id },
              { label: "Send back…", act: "sendBack" as const, id: t.id, title: "say what is wrong; an agent takes it again" }],
  })), { folded: true });

  return { banner: banner(s), goal: headline(s), counts: countsLine(s), sections, empty: !s.tasks.length && !s.questions.length };
}

/** What `graphene ask` printed that a person wants to read: the planner's own words, and what planning cost. */
export function said(stdout: string): string[] {
  const lines = stdout.split(/\r?\n/);
  const out: string[] = [];
  const at = lines.findIndex((l) => l.trim() === "the planner says:");
  if (at >= 0) for (const l of lines.slice(at + 1)) { if (!/^\s+\S/.test(l)) break; out.push(l.trim()); }
  const cost = lines.find((l) => /^the planner \(/.test(l))?.match(/\$[\d.]+/);
  if (cost) out.push(`Planning cost ${cost[0]}.`);
  return out;
}

export type FromHome = { type: "ready" } | { type: "act"; act: Act; id: string; arg?: string; flag?: boolean };

/** The acts that take no task: each still checked for what it carries. */
const GLOBAL: readonly Act[] = ["ask", "cancel", "startAll", "discardAll", "run", "stop", "showGraph", "demo", "setup", "install",
                                "setKey", "refresh", "openFolder"];

/** A message from the page, checked against the plan before anything runs: a known act; the text of an ask; a
 *  planner the Set Up offers; a task the plan has (a question, for answer); an option the question has; an offer
 *  the task carries. Null for anything else. */
export function checkHome(m: unknown, s: State | null): FromHome | null {
  if (!m || typeof m !== "object") return null;
  const r = m as Record<string, unknown>;
  if (r.type === "ready") return { type: "ready" };
  if (r.type !== "act" || typeof r.act !== "string" || !(ACTS as readonly string[]).includes(r.act)) return null;
  const act = r.act as Act;
  const id = typeof r.id === "string" ? r.id : "";
  const arg = typeof r.arg === "string" ? r.arg : undefined;
  if (act === "ask") return arg?.trim() && arg.length <= 4000 ? { type: "act", act, id: "", arg: arg.trim() } : null;
  if (act === "setup") return WHO.some((w) => w.word === arg) ? { type: "act", act, id: "", arg, flag: r.flag === true } : null;
  if (act === "setKey") return arg === undefined || /^\w+$/.test(arg) ? { type: "act", act, id: "", arg } : null;
  if (act === "answer") {
    const q = s?.questions.find((x) => x.id === id);
    if (!q || (arg !== undefined && arg !== q.default && !q.options.includes(arg))) return null;
    return { type: "act", act, id, arg };
  }
  if (act === "showGraph") return !id || s?.tasks.some((t) => t.id === id) ? { type: "act", act, id } : null;
  if (GLOBAL.includes(act)) return { type: "act", act, id: "" };
  const t = s?.tasks.find((x) => x.id === id);
  if (!t) return null;
  if (act === "offer") return arg && Object.hasOwn(t.offers, arg) ? { type: "act", act, id, arg } : null;
  if (act === "keep") return arg && t.forks.some((f) => f.letter === arg) ? { type: "act", act, id, arg } : null;
  return { type: "act", act, id };
}
