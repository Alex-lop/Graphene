// A file read as it grows: only the bytes written since the last read, and only whole lines. A last line with
// no newline yet is a write in progress, kept back until its end arrives. A file that shrank (replaced, or
// rewritten) is read from its start again. It never throws: a file it cannot read says so in one line.
import { open, stat } from "node:fs/promises";

/** `n`: how many lines were read; `lines`: the lines themselves, unless they were handed to `each`. */
export interface Read { lines: string[]; n: number; reset: boolean; error: string }

const CHUNK = 1 << 20;

export class Tail {
  readonly file: string;
  private offset = 0;
  private rest: Buffer = Buffer.alloc(0); // the bytes after the last newline: a line still being written
  private busy: Promise<Read> | null = null;
  /** How many times the file was found shorter than what was read of it, and read from its start again: it moves
   *  before the first line of the new reading is handed over. */
  resets = 0;

  constructor(file: string) { this.file = file; }

  /** The bytes read so far: what `size` is compared with to know whether there is more. */
  get at(): number { return this.offset; }

  /** The whole lines written since the last read, in order. With `each`, a line is handed over as it is read
   *  and none is kept: the first read of a long session holds a line at a time, not the file. One read at a
   *  time: a second call while one runs gets the same answer. */
  read(each?: (line: string) => void): Promise<Read> {
    return this.busy ??= this.next(each).finally(() => { this.busy = null; });
  }

  private async next(each?: (line: string) => void): Promise<Read> {
    const lines: string[] = [];
    let n = 0;
    let reset = false;
    try {
      const size = (await stat(this.file)).size;
      if (size < this.offset) { this.offset = 0; this.rest = Buffer.alloc(0); reset = true; this.resets++; }
      if (size === this.offset) return { lines, n, reset, error: "" };
      const fh = await open(this.file, "r");
      try {
        const buf = Buffer.alloc(CHUNK);
        while (this.offset < size) {
          const { bytesRead } = await fh.read(buf, 0, Math.min(CHUNK, size - this.offset), this.offset);
          if (!bytesRead) break;
          this.offset += bytesRead;
          let from = 0;
          for (let nl = buf.indexOf(10, from); nl !== -1 && nl < bytesRead; nl = buf.indexOf(10, from)) {
            // a line is decoded whole, so a character cut in two by a chunk's end is never read as two halves
            const line = Buffer.concat([this.rest, buf.subarray(from, nl)]).toString("utf8");
            this.rest = Buffer.alloc(0);
            from = nl + 1;
            if (!line.trim()) continue;
            n++;
            if (each) each(line); else lines.push(line);
          }
          this.rest = Buffer.concat([this.rest, buf.subarray(from, bytesRead)]);
        }
      } finally {
        await fh.close();
      }
      return { lines, n, reset, error: "" };
    } catch (e) {
      return { lines, n, reset, error: `cannot read ${this.file}: ${(e as NodeJS.ErrnoException).code ?? (e as Error).message}` };
    }
  }
}
