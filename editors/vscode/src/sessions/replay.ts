// A recorded session played back, so a person sees a graph before they have a session of their own: the
// lines of media/replay.jsonl (a real Claude Code session in a scratch repository, its paths made generic by
// dev/process/sessions/record.py) fed to the same reader and the same model, a few events at a time.
// Pure: no VS Code, no file system.
import { claudeLine } from "./claude.ts";
import type { Ev } from "./events.ts";
import { empty, fold, type Model } from "./model.ts";

export class Replay {
  readonly model: Model = empty("claude", "", "replay");
  private readonly evs: Ev[];
  private at = 0;

  constructor(text: string) {
    this.evs = text.split("\n").flatMap((line) => { try { return claudeLine(line); } catch { return []; } });
  }

  get over(): boolean { return this.at >= this.evs.length; }

  /** The recording's own clock: when its last event played was written. What "now" is, for a replay. */
  get clock(): number {
    const t = Date.parse(this.model.last);
    return Number.isFinite(t) ? t : 0;
  }

  /** Play the next `n` events that show (a session's own facts, its folder and branch, come with them). False once
   *  the recording is over. */
  step(n = 1): boolean {
    for (let shown = 0; shown < n && !this.over;) {
      const ev = this.evs[this.at++]!;
      fold(this.model, ev);
      if (ev.k !== "meta") shown++;
    }
    return !this.over;
  }
}
