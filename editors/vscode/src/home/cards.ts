// Home, pure: what a person sees first in Graphene's side bar, from the snapshot, in plain words. Sections come
// in the order a person acts on them (what needs you, the suggested plan, who is working, what is up next, what
// is done); each card says what its task is for and what proves it, with its buttons. No VS Code and no DOM
// here: home.ts sends what this returns, home/main.ts draws it, and checkHome reads what the page sends back.
import { checkCut } from "../graph/marks.ts";
import { filesChip, forkWord, pipeline, PROVES_NOTHING, stopAfterPlan, type Stage } from "../graph/words.ts";
import { needs, OFFERS, offerOn } from "../needs.ts";
import { headline, SAY, usd, type Question, type State, type Task } from "../state.ts";
import { WHO } from "./who.ts";

export const ACTS = ["startAll", "discardAll", "run", "stop", "drop", "answer", "openDiff", "compare", "keep",
                     "approve", "sendBack", "offer", "tryAgain", "allow", "message", "markDone", "showGraph", "demo", "setup",
                     "install", "setKey", "refresh", "openFolder", "exact", "stopAfter", "review", "runWorkflow"] as const;
export type Act = (typeof ACTS)[number];

/** ``main``: the card's one filled button, if any. ``note``: a dim word after the label (a question's default). */
export interface Btn { label: string; act: Act; id?: string; arg?: string; main?: boolean; title?: string; off?: boolean; note?: string }
/** ``paths``: the value is these files, drawn one a line, a deep one from its last folder (``v`` says them all).
 *  A ``v`` of several lines (attempts, last actions) is drawn a line each. ``hover``: the whole, where ``v`` is short.
 *  ``short``: the label where a side bar has no row for it, run into the value (`glance`). */
export interface Line { k?: string; v: string; mono?: boolean; warn?: boolean; paths?: string[]; hover?: string; short?: string }
export type Tone = "question" | "proposed" | "running" | "review" | "came-back" | "ready" | "waiting" | "done" | "yours";
/** ``tag``: the state in a word, where its section does not say it already (Needs you, Up next); else empty. */
export interface Card { key: string; tone: Tone; title: string; tag: string; lines: Line[]; buttons: Btn[] }
export interface Section { key: string; title: string; note: string; buttons: Btn[]; cards: Card[]; folded: boolean }
/** ``stages``: Plan, Run, Review, and where the work is. ``stopAfter``: the one switch, on by default. */
export interface Home { banner: string; goal: string; counts: string; stages: Stage[]; stopAfter: boolean; sections: Section[]; empty: boolean }
export { PROVES_NOTHING };

const cut = (s: string, n: number) => (s.length > n ? `${s.slice(0, n - 1).trimEnd()}…` : s);
const bare = (s: string) => s.trim().replace(/^(an?|the)\s+/i, "").toLowerCase();
const files = (paths: string[]) => paths.join(", ");
const fileLine = (k: string, paths: string[], none: string): Line[] =>
  paths.length ? [{ k, v: files(paths), mono: true, paths }] : line(k, none);
const plural = (n: number, word: string) => `${n} ${word}${n === 1 ? "" : "s"}`;
const line = (k: string, v: string, more: Partial<Line> = {}): Line[] => (v ? [{ k, v, ...more }] : []);
/** `a: passed, 9 lines`, then `b: working`: each attempt at a task, a line of its own (no dot left at a line's end). */
const attempts = (t: Task) => t.forks.map((f) => `${f.letter}: ${forkWord(f)}${f.lines !== null ? `, ${f.lines} lines` : ""}`).join("\n");

/** The first words on the page when this is not a real run: a replay, or a race against the scripted stand-in. */
export function banner(s: State): string {
  if (s.replay) return `Demo replay: ${s.replay.shown}`;
  return s.stand_in ? "Practice run: a scripted stand-in answers for the AI, so nothing is spent" : "";
}

/** `3 of 6 done · $0.42 at list price`: who is working and what needs you are said just under it, by the stages
 *  and the Needs you section. The cost is everything this repository's planners and agents have cost so far, a
 *  dropped plan's included, at list price as the CLI says it: on a subscription nothing is billed, so it is never
 *  "spent", nor "planned for" (the snapshot cannot tell the planner's share). A practice run spends nothing, so
 *  it shows no cost: the stand-in's is a list price. */
export function countsLine(s: State): string {
  const sb = s.scoreboard;
  const cost = s.stand_in ? "" : usd(s.spent);
  return [sb.total ? `${sb.proven} of ${sb.total} done` : "", cost ? `${cost} at list price` : ""].filter(Boolean).join(" · ");
}

/** The open questions with no default: one stops the run either way, so Start waits for its answer as auto does. */
export const unanswered = (s: Pick<State, "questions">): number => s.questions.filter((q) => !q.default).length;

/** A command step whose command failed stays open, and reads as it did before it ran: once the terminal is gone,
 *  this line is all that says it ran. */
const failed = (t: Task): Line[] => (t.command && t.checked.after === "failed" && t.state !== "done"
  ? [{ v: `Its command failed the last time it ran: the terminal said why. ${t.leaves ? "Approve and run" : "Run"} tries it again.`, warn: true }] : []);

/** What a task is for, past its title: none when it says the title again (with an "an" before it), and only what
 *  is new when it starts with the title (`Librarian service: collections, …`). */
function whatFor(t: Task): string {
  const head = `${bare(t.title)}:`, at = t.full.toLowerCase().indexOf(head);
  const rest = bare(t.full).startsWith(head) ? t.full.slice(at + head.length).trim() : t.full;
  if (rest === t.full) return bare(t.full) === bare(t.title) ? "" : t.full;
  return rest && rest[0]!.toUpperCase() + rest.slice(1);
}

/** A mono line cut short, the whole on hover when it says more. */
const brief1 = (k: string, v: string, whole: string): Line[] => [{ k, v, mono: true, ...(whole !== v ? { hover: whole } : {}) }];
/** A scope by its last name (`CookServiceImpl.java`, `api` for `src/api/`); a glob from its last plain folder on
 *  (`docs/**\/*.md`), so two tasks' Markdown in two folders do not read the same. */
function tail(p: string): string {
  const d = p.replace(/\/+$/, "").split("/");
  let i = d.length - 1;
  while (i > 0 && /[*?]/.test(d[i]!)) i--;
  return d.slice(i).join("/");
}

/** What a task is for, what it may change, and what proves it: the three lines a person reads before saying yes.
 *  ``brief``, for a task not started (Suggested plan, Up next): a line each, as the graph's card says them, its
 *  files by name (`CookServiceImpl.java +2`) and its check by what it runs on, the whole of each on hover and in
 *  the graph's pane; a side bar is for a glance, and a whole gradlew command wraps there over four lines. */
function contract(t: Task, name: (id: string) => string, brief = false): Line[] {
  if (t.command) return [ // a command step: no agent and no files; what runs, and whether it asks first
    { k: "Runs", v: t.command, mono: true },
    { v: t.leaves ? "It leaves your machine, so it asks you before it runs." : "A command, with no agent: its exit code is its check." },
    ...failed(t),
    ...line("After", t.needs.map(name).join(", ")),
  ];
  return [
    ...line("What for", whatFor(t)),
    ...(brief && t.scope.length ? brief1("May change", filesChip(t.scope.map(tail)).replace(/ (?=\+\d+$)/, " "), t.scope.join("\n")) // no +2 alone
      : fileLine("May change", t.scope, "no files named")),
    ...(brief && t.check ? brief1("Done when", `${checkCut(t.check, 28)} passes`, `${t.check} passes`)
      : [{ k: "Done when", v: t.check ? `${t.check} passes` : "you approve it", mono: Boolean(t.check) }]),
    ...(t.hollow ? [{ v: PROVES_NOTHING, warn: true }] : []), // the check ran once on the code as it is, before the run
    ...line("After", t.needs.map(name).join(", ")),
  ];
}

/** A task not started, at a glance: in Cursor's side bar beside its chat a label has no room beside its value
 *  (home.css), and a row of its own each made six cards a page and a half. There each line runs on from a short
 *  label instead, as the graph's card says it: What for with none, its files after ▤, its check after done when. */
const SHORT: Record<string, string> = { "What for": "", "May change": "▤", Runs: "$" };
const glance = (ls: Line[]): Line[] => ls.map((l) => (l.k ? { ...l, short: SHORT[l.k] ?? l.k.toLowerCase() } : l));

/** A finished task's evidence: what changed, the check that proved it, and the attempt that was kept. */
function evidence(t: Task): Line[] {
  const kept = t.kept && t.forks.length > 1 ? `attempt ${t.kept.letter} of ${t.forks.length}${t.kept.why ? `: ${t.kept.why}` : ""}` : "";
  return [
    ...fileLine("Changed", t.changed, "no files"),
    { k: "Check", v: t.check ? `${t.check} passed` : "none: your approval finishes it", mono: Boolean(t.check) },
    ...(t.hollow ? [{ v: "This check passed before the work too, so it does not prove the change. Read the changes.", warn: true }] : []),
    ...line("Kept", kept),
  ];
}

function question(q: Question, name: (id: string) => string): Card {
  const options = [...new Set([...(q.default ? [q.default] : []), ...q.options])];
  return {
    key: `q:${q.id}`, tone: "question", title: q.text, tag: "question",
    lines: q.about ? [{ v: `About ${name(q.about)}` }] : [], // one row: a label column for one short word leaves a hole
    // none filled: a default that looks chosen is skipped past; it says it is the default instead
    buttons: [
      ...options.map((o) => ({ label: cut(o, 80), act: "answer" as const, id: q.id, arg: o, ...(o === q.default ? { note: "default" } : {}),
                               title: o === q.default ? `${o}: the default, what happens if nobody answers` : o })),
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
  return [{ label: "Try again", act: "tryAgain", id: t.id, main: true, title: "a new agent, told why the last one stopped" }, ...offers,
          { label: "Open changes", act: "openDiff", id: t.id }, { label: "Remove task", act: "drop", id: t.id }];
}

/** A workflow as Home lists it: a graph saved to workflows/, with the inputs Run asks for. */
export interface Listed { name: string; goal: string; inputs: { name: string; default: string | null }[]; error: string | null }

/** ``exact``: the switch is on, so Start waits while anything the plan asks is open (its default's button confirms it).
 *  ``workflows``: the repository's saved graphs, each with a Run that proposes its plan with no planner call. */
export function home(s: State, seen: ReadonlySet<string> = new Set(), exact = false, workflows: readonly Listed[] = []): Home {
  const titles: Record<string, string> = Object.fromEntries(s.tasks.map((t) => [t.id, t.title]));
  // a sub-goal by its name: no "? " (the plan text's mark for a suggestion), nor what follows its first ": "
  const goals: Record<string, string> = Object.fromEntries(s.goals.map((g) => [g.id, g.title.replace(/^\? /, "").split(": ")[0]!]));
  const name = (id: string) => titles[id] ?? goals[id] ?? id;
  const sections: Section[] = [];
  const section = (key: string, title: string, cards: Card[], more: Partial<Section> = {}) => {
    if (cards.length) sections.push({ key, title, note: "", buttons: [], cards, folded: false, ...more });
  };

  const waiting: Card[] = [];
  for (const n of needs(s)) {
    if (n.kind === "auto") {
      waiting.push({ key: "auto", tone: "came-back", title: "Auto mode is waiting for you", tag: "", lines: [{ v: n.why }],
                     buttons: n.key ? [{ label: "Set API key", act: "setKey", arg: n.endpoint ?? undefined, main: true }] : [] });
    } else if (n.kind === "question") {
      waiting.push(question(n.q, name));
    } else if (n.kind === "sign-off") {
      const t = n.t, opened = seen.has(t.id);
      const back: Btn = { label: "Send back…", act: "sendBack", id: t.id, title: "say what is wrong; an agent takes it again" };
      const passed = t.forks.filter((f) => f.state === "passed");
      if (passed.length > 1 && !t.kept) { // its check could not choose between them: the person keeps one first
        waiting.push({ key: `review:${t.id}`, tone: "review", title: t.title, tag: SAY.review,
                       lines: [{ k: "Attempts", v: attempts(t) },
                               { v: `${plural(passed.length, "attempt")} passed the check. Compare them and keep one, then approve it.`, warn: true }],
                       buttons: [{ label: "Compare attempts", act: "compare", id: t.id, main: true },
                                 ...passed.map((f) => ({ label: `Keep ${f.letter}`, act: "keep" as const, id: t.id, arg: f.letter, title: `attempt ${f.letter} becomes this task's work` })),
                                 back] });
        continue;
      }
      waiting.push({ key: `review:${t.id}`, tone: "review", title: t.title, tag: SAY.review,
                     lines: [...evidence(t), ...line("Last actions", t.tail.slice(-3).join("\n"), { mono: true }), // did it run its check itself?
                             { v: opened ? "You opened these changes." : "You have not opened these changes yet.", warn: !opened }],
                     buttons: [{ label: "Open changes", act: "openDiff", id: t.id, main: !opened },
                               { label: "Approve", act: "approve", id: t.id, main: opened, title: "it lands in your repository" }, back] });
    } else if (n.kind === "hand-back") {
      const t = n.t;
      waiting.push({ key: `help:${t.id}`, tone: "came-back", title: t.title, tag: SAY["came back"],
                     lines: [{ k: "Why", v: t.why || t.note || "it stopped before its check passed", warn: true },
                             ...line("Tries", t.attempts > 1 ? String(t.attempts) : ""), ...fileLine("Wanted", t.outside, "")],
                     buttons: help(t, titles) });
    } else if (n.kind === "stopped") {
      const t = n.t, path = t.stopped[t.stopped.length - 1] ?? "a file";
      waiting.push({ key: `blocked:${t.id}`, tone: "came-back", title: t.title, tag: "blocked",
                     lines: [{ v: `Agent ${t.agent || "?"} tried to change ${path}, which is outside the files this task may change.`, warn: true }],
                     buttons: [{ label: `Allow it to change ${cut(path, 60)}`, act: "allow", id: t.id, main: true },
                               { label: "Open changes so far", act: "openDiff", id: t.id }] });
    } else if (n.kind === "yours" && n.t.leaves && n.t.command) { // a step past the line: approving it runs its command
      const t = n.t;
      waiting.push({ key: `yours:${t.id}`, tone: "yours", title: t.title, tag: "asks you",
                     lines: [{ v: "This task leaves your machine, so it asks you first. Approving it runs its command, with no agent." },
                             { k: "Runs", v: t.command!, mono: true }, ...failed(t), ...line("After", t.needs.map(name).join(", "))],
                     buttons: [{ label: "Approve and run", act: "markDone", id: t.id, main: true, title: "graphene node done runs the command, in a terminal you can watch" }] });
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
    key: `p:${t.id}`, tone: "proposed" as const, title: t.title, tag: "", lines: glance(contract(t, name, true)),
    buttons: [{ label: "Remove", act: "drop" as const, id: t.id, title: "leave this task out of the plan" }],
  })), {
    note: exact && s.questions.length
      ? `Start waits for every answer: answer the ${plural(s.questions.length, "open question")} under Needs you first (a default's button confirms it).`
      : unanswered(s) ? `Answer the ${plural(unanswered(s), "question")} with no default under Needs you first: a question with no default stops the run.`
      : "Read what each task may change and what proves it done. A\u00a0card's\u00a0× leaves it out.", // held together: no "A" or "×" alone at a line's end
    buttons: [{ label: "Start", act: "startAll", main: true, off: (exact && s.questions.length > 0) || unanswered(s) > 0,
                title: exact && s.questions.length ? "it waits for every answer, as Settings say" : unanswered(s) ? "it waits for an answer: a question with no default is open"
                  : "accept these tasks and start an agent on each" },
              { label: "Discard all", act: "discardAll" }],
  });

  const working = s.tasks.filter((t) => t.state === "running" && !t.stopped.length);
  section("working", `Working now · ${working.length}`, working.map((t) => {
    const quiet = t.idle !== null && t.idle > 8 ? `${Math.round(t.idle)} s` : "";
    return {
      key: `w:${t.id}`, tone: "running" as const, title: t.title, tag: "",
      lines: [...line("Agent", `${t.agent || "?"}${t.model ? ` · ${t.model}` : ""}`), ...line("Now", t.tail[t.tail.length - 1] ?? "", { mono: true }),
              ...line("Quiet for", quiet), ...line("Cost", s.stand_in ? "" : usd(t.usd)), ...line("Attempts", attempts(t)),
              ...(t.hollow ? [{ v: PROVES_NOTHING, warn: true }] : [])],
      buttons: [{ label: "Open changes so far", act: "openDiff" as const, id: t.id },
                { label: "Message agent…", act: "message" as const, id: t.id, title: "it reads your line with its next move" },
                ...(t.forks.length > 1 ? [{ label: "Compare attempts", act: "compare" as const, id: t.id }] : [])],
    };
  }), { buttons: [{ label: "Stop all", act: "stop", title: "stop every agent: their tasks go back to the plan" }] });

  const next = s.tasks.filter((t) => t.state === "ready" || t.state === "waiting");
  section("next", `Up next · ${next.length}`, next.map((t) => ({
    key: `n:${t.id}`, tone: t.state === "ready" ? "ready" as const : "waiting" as const, title: t.title, tag: SAY[t.state],
    lines: glance([...line("Waits for", t.state === "waiting" ? t.needs.map(name).join(", ") : ""), ...contract(t, name, true).filter((l) => l.k !== "After")]),
    buttons: [{ label: "Remove", act: "drop" as const, id: t.id, title: "take this task out of the plan" }],
  })), { buttons: [{ label: "Run", act: "run", main: !s.run.going, title: s.run.going ? "hand these to the run that is going"
                                                                            : "start an agent on every task that is ready" }] });

  section("workflows", `Workflows · ${workflows.length}`, workflows.map((w) => ({
    key: `wf:${w.name}`, tone: "ready" as const, title: w.name, tag: "",
    lines: w.error ? [{ v: w.error, warn: true }]
      : [...line("Does", w.goal), ...line("Asks for", w.inputs.map((i) => (i.default === null ? i.name : `${i.name} (${i.default})`)).join(", "))],
    buttons: w.error ? [] : [{ label: "Run", act: "runWorkflow" as const, arg: w.name, main: true, title: "fill its inputs and propose its plan: no planner is called" }],
  })), { note: "A graph saved to workflows/. Run asks for its inputs and proposes its plan with no planner call; then it goes on as any plan does.",
         folded: s.tasks.length > 0 });

  const done = s.tasks.filter((t) => t.state === "done");
  section("done", `Done · ${done.length}`, done.map((t) => ({
    key: `d:${t.id}`, tone: "done" as const, title: t.title, tag: "", lines: evidence(t),
    buttons: [{ label: "Open changes", act: "openDiff" as const, id: t.id },
              { label: "Send back…", act: "sendBack" as const, id: t.id, title: "say what is wrong; an agent takes it again" }],
  })), { folded: true });

  return { banner: banner(s), goal: headline(s), counts: countsLine(s), stages: pipeline(s), stopAfter: stopAfterPlan(s), sections,
           empty: !s.tasks.length && !s.questions.length };
}

export type FromHome = { type: "ready" } | { type: "act"; act: Act; id: string; arg?: string; flag?: boolean };

/** The acts that take no task: each still checked for what it carries. */
const GLOBAL: readonly Act[] = ["startAll", "discardAll", "run", "stop", "showGraph", "demo", "setup", "install",
                                "setKey", "refresh", "openFolder", "exact", "stopAfter", "review", "runWorkflow"];

/** A message from the page, checked against the plan before anything runs: a known act; a planner the Set Up
 *  offers; a task the plan has (a question, for answer); an option the question has; an offer
 *  the task carries. Null for anything else. */
export function checkHome(m: unknown, s: State | null, workflows: readonly Pick<Listed, "name" | "error">[] = []): FromHome | null {
  if (!m || typeof m !== "object") return null;
  const r = m as Record<string, unknown>;
  if (r.type === "ready") return { type: "ready" };
  if (r.type !== "act" || typeof r.act !== "string" || !(ACTS as readonly string[]).includes(r.act)) return null;
  const act = r.act as Act;
  const id = typeof r.id === "string" ? r.id : "";
  const arg = typeof r.arg === "string" ? r.arg : undefined;
  if (act === "exact" || act === "stopAfter" || act === "review") return typeof r.flag === "boolean" ? { type: "act", act, id: "", flag: r.flag } : null;
  if (act === "runWorkflow") return workflows.some((w) => w.name === arg && !w.error) ? { type: "act", act, id: "", arg } : null; // one the repository has
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
