// One session followed as it grows: its file, and beside a Claude Code session the transcripts of the
// subagents it launched (<session id>/subagents/agent-<id>.jsonl; a workflow's under workflows/<run>/). Each
// file is read once and then only for what is new (tail.ts), every line into the one model (model.ts). It
// never throws: a file that cannot be read says so in the model's `error`. Node's file system only.
import { readdir, readFile } from "node:fs/promises";
import * as path from "node:path";
import type { Ev } from "./events.ts";
import { readerOf, type Found, type Reader } from "./find.ts";
import { empty, fold, sideOf, type Model } from "./model.ts";
import { Tail } from "./tail.ts";

/** A subagent's transcript beside its session: its id, the workflow run it belongs to, the call that launched it. */
interface SideFile { id: string; file: string; run: string; tail: Tail; named: boolean }

export class Follow {
  readonly found: Found;
  readonly model: Model;
  private readonly reader: Reader;
  private readonly tail: Tail;
  private readonly sides = new Map<string, SideFile>();
  private reading: Promise<boolean> | null = null;

  constructor(found: Found) {
    this.found = found;
    this.reader = readerOf(found.agent);
    this.model = empty(found.agent, found.file, found.id);
    this.model.cwd = found.cwd;
    this.tail = new Tail(found.file);
  }

  /** Read what is new. True when something was: the page is drawn again only then. One read at a time. */
  read(): Promise<boolean> {
    return this.reading ??= this.next().finally(() => { this.reading = null; });
  }

  private async next(): Promise<boolean> {
    const m = this.model;
    let changed = await this.take(this.tail, "");
    if (this.found.agent !== "claude") return changed;
    for (const s of await this.subagents()) {
      if (!s.named) { // its own note beside it: the call that launched it, where Claude Code says so
        s.named = true;
        const side = sideOf(m, s.id);
        side.run = s.run;
        side.file = s.file;
        try { side.call = String((JSON.parse(await readFile(s.file.replace(/\.jsonl$/, ".meta.json"), "utf8")) as { toolUseId?: unknown }).toolUseId ?? ""); } catch { /* an older version writes none */ }
        changed = true;
      }
      if (await this.take(s.tail, s.id)) changed = true;
    }
    return changed;
  }

  /** A file's new lines into the model. A subagent's lines are its thread's whatever they say of themselves. */
  private async take(tail: Tail, side: string): Promise<boolean> {
    const m = this.model, r = await tail.read();
    const said = !side && r.error !== m.error; // the session's own file: said, and unsaid once it reads again
    if (said) m.error = r.error;
    for (const line of r.lines) {
      let evs: Ev[];
      try { evs = this.reader.line(line); } catch { continue; } // a line it does not understand takes nothing down
      for (const ev of evs) {
        if (side && ev.k !== "meta" && ev.k !== "result") ev.side = side;
        if (side && ev.k === "meta") continue; // the session is its own file's, not a subagent's
        try { fold(m, ev); } catch { /* as above */ }
      }
    }
    return r.lines.length > 0 || r.reset || said;
  }

  /** The subagent transcripts beside the session, the ones seen before and any new. */
  private async subagents(): Promise<SideFile[]> {
    const dir = path.join(this.found.file.replace(/\.jsonl$/, ""), "subagents");
    const add = (file: string, run: string) => {
      const id = /^agent-(.+)\.jsonl$/.exec(path.basename(file))?.[1];
      if (id && !this.sides.has(id)) this.sides.set(id, { id, file, run, tail: new Tail(file), named: false });
    };
    try {
      for (const e of await readdir(dir, { withFileTypes: true })) {
        if (e.isFile()) add(path.join(dir, e.name), "");
        if (!e.isDirectory() || e.name !== "workflows") continue;
        for (const run of await readdir(path.join(dir, e.name), { withFileTypes: true })) {
          if (!run.isDirectory()) continue;
          for (const f of await readdir(path.join(dir, e.name, run.name))) add(path.join(dir, e.name, run.name, f), run.name);
        }
      }
    } catch { /* no subagents yet */ }
    return [...this.sides.values()];
  }
}
