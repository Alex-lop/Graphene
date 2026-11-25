// Codex's rollout, a line at a time: ~/.codex/sessions/YYYY/MM/DD/rollout-<time>-<id>.jsonl. Its first line is
// `session_meta`; a turn runs from `task_started` to `task_complete` (or `turn_aborted`); and what happened in
// it is said twice, as the model's own calls (a script in Codex's tool language) and as `item_completed`
// records that name the command, its exit code and the files a patch changed. This reads the records: they
// say what ran, not how it was asked for. Undocumented, and read here as 0.150 to 0.170 write it.
// A record arrives when its work is over, so a command shows once it has ended. Pure: a line in, events out.
import { clip, COMMAND, json, list, obj, str, type Ev, type Raw } from "./events.ts";

/** A command as a person would type it: Codex wraps each in `shell -lc "<command>"`. */
function typed(command: unknown): string {
  const argv = list(command).filter((x): x is string => typeof x === "string");
  if (argv.length === 3 && /^-l?c$/.test(argv[1]!)) return argv[2]!;
  return argv.join(" ") || str(command);
}

const texts = (content: unknown): string => list(content).map(obj).map((c) => str(c.text)).filter(Boolean).join("\n");

/** One line of a Codex rollout as events; none for a line it does not understand. */
export function codexLine(line: string): Ev[] {
  const o = json(line);
  if (!o) return [];
  const at = str(o.timestamp), p = obj(o.payload), type = str(o.type), kind = str(p.type);
  if (type === "session_meta") {
    const git = obj(p.git);
    return [{ k: "meta", id: str(p.id) || undefined, cwd: str(p.cwd) || undefined, branch: str(git.branch) || undefined, head: str(git.commit_hash) || undefined }];
  }
  if (type === "event_msg" && kind === "task_complete") return [{ k: "end", at, side: "" }];
  if (type === "event_msg" && kind === "turn_aborted") return [{ k: "stop", at, side: "" }];
  // a subagent launched: the call names it; Codex says its end nowhere in this file
  if (type === "response_item" && kind === "function_call" && str(p.name) === "spawn_agent" && str(p.call_id)) {
    const args = json(str(p.arguments)) ?? {};
    const id = str(p.call_id);
    // launched, and left running behind the request: the call itself is answered at once
    return [{ k: "tool", at, id, name: "Agent", input: { description: str(args.task_name), prompt: str(args.message), model: str(args.model) }, side: "" },
            { k: "result", at, id, error: false, out: "", err: "", interrupted: false, exit: null, more: { isAsync: true, status: "async_launched" } }];
  }
  if (type !== "event_msg" || kind !== "item_completed") return [];
  const item = obj(p.item), id = str(item.id);
  switch (str(item.type)) {
    case "UserMessage": {
      const text = texts(item.content).trim();
      return text ? [{ k: "ask", at, text, side: "" }] : [];
    }
    case "AgentMessage": {
      const text = texts(item.content).trim();
      return text ? [{ k: "say", at, text, side: "", model: "" }] : [];
    }
    case "CommandExecution": {
      if (!id) return [];
      const exit = typeof item.exit_code === "number" ? item.exit_code : null;
      return [
        { k: "tool", at, id, name: COMMAND, input: { command: typed(item.command) }, side: "" },
        { k: "result", at, id, error: exit !== 0, out: clip(str(item.aggregated_output) || str(item.stdout)), err: clip(str(item.stderr)), interrupted: false, exit, more: {} },
      ];
    }
    case "FileChange": {
      // one patch may change several files: a write each, named as Claude Code names its own
      const out: Ev[] = [], failed = str(item.status) !== "completed";
      for (const [file, change] of Object.entries(obj(item.changes))) {
        const how = str(obj(change).type), call = `${id}:${file}`;
        const more: Raw = how === "add" ? { type: "create" } : how === "delete" ? { type: "delete" } : {};
        out.push({ k: "tool", at, id: call, name: how === "add" ? "Write" : "Edit", input: { file_path: str(obj(change).move_path) || file }, side: "" },
                 { k: "result", at, id: call, error: failed, out: "", err: failed ? str(item.stderr) : "", interrupted: false, exit: null, more });
      }
      return out;
    }
  }
  return [];
}
