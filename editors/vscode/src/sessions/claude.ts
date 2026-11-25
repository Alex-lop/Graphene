// Claude Code's transcript, a line at a time: ~/.claude/projects/<folder>/<session id>.jsonl, one JSON object a
// line. The format is undocumented and changes between versions (read here as 2.1.317 to 2.1.331 write it), so
// every field is optional, a line of a type this does not know says nothing, and nothing here throws.
// Pure: a line in, events out.
import { clip, json, kept, list, obj, slim, str, type Ev, type Raw } from "./events.ts";

/** What a person's line starts with when Claude Code wrote it for them: a slash command's echo, a `!` command's
 *  output, a reminder, a background task's notice, the summary a compacted session continues from. None is a
 *  request. */
const NOT_ASKED = /^\s*(<(local-command-[a-z]+|command-(message|args)|system-reminder|task-notification|bash-(input|stdout|stderr)|user-prompt-submit-hook)>|Caveat:|This session is being continued from|\[(Your previous response|Usage limit|Earlier usage))/;
const INTERRUPTED = /^\s*\[Request interrupted by user/;
/** An exit code as Claude Code says it at the start of a failed command's result. */
const EXIT = /^(?:Error: )?Exit code (\d+)/;

/** A person's words out of a line's content: a string, or the text blocks of a list. */
function words(content: unknown): string {
  if (typeof content === "string") return content;
  return list(content).map(obj).filter((b) => b.type === "text").map((b) => str(b.text)).join("\n");
}

/** A slash command as the person typed it (`/review 12`), out of the tags Claude Code records it in. */
function slash(text: string): string {
  const name = /<command-name>\s*([^<]+?)\s*<\/command-name>/.exec(text)?.[1];
  if (!name) return "";
  const args = /<command-args>\s*([^<]*?)\s*<\/command-args>/.exec(text)?.[1] ?? "";
  return `${name.startsWith("/") ? name : `/${name}`}${args ? ` ${args}` : ""}`;
}

/** A tool result's text: a string, or the text blocks of a list (an image is not text). */
function resultText(content: unknown): string {
  if (typeof content === "string") return content;
  return list(content).map(obj).map((b) => str(b.text)).filter(Boolean).join("\n");
}

/** One line of a Claude Code transcript as events; none for a line it does not understand. */
export function claudeLine(line: string): Ev[] {
  const o = json(line);
  if (!o) return [];
  const type = str(o.type), at = str(o.timestamp);
  if (type === "ai-title") return str(o.aiTitle) ? [{ k: "meta", title: str(o.aiTitle) }] : [];
  // a subagent's lines carry its id; on the session's own thread there is none. An older Claude Code wrote a
  // subagent's lines into the session's own file with no id: they are a thread apart all the same, never the session's
  const side = o.isSidechain === true ? str(o.agentId) || "sidechain" : "";
  if (type === "system") return str(o.subtype) === "turn_duration" ? [{ k: "end", at, side }] : [];
  if (type !== "user" && type !== "assistant") return [];
  const out: Ev[] = [];
  const meta: Ev = { k: "meta", id: str(o.sessionId) || undefined, cwd: str(o.cwd) || undefined, branch: str(o.gitBranch) || undefined };
  if (meta.id || meta.cwd) out.push(meta);
  const message = obj(o.message), content = message.content;
  if (type === "assistant") {
    for (const b of list(content).map(obj)) {
      if (b.type === "text" && str(b.text).trim()) out.push({ k: "say", at, text: str(b.text), side, model: str(message.model) });
      if (b.type === "tool_use" && str(b.id)) out.push({ k: "tool", at, id: str(b.id), name: str(b.name), input: slim(obj(b.input)), side });
    }
    // the last line of a reply says why it stopped: by itself, or to wait for a tool. A reply's thinking is a line
    // of its own before its words, and carries the same reason: the turn ends once, with the words
    const why = str(message.stop_reason), blocks = list(content).map(obj);
    const last = !blocks.length || blocks.some((b) => b.type !== "thinking" && b.type !== "redacted_thinking");
    if (why && why !== "tool_use" && why !== "pause_turn" && last) out.push({ k: "end", at, side });
    return out;
  }
  const results = list(content).map(obj).filter((b) => b.type === "tool_result" && str(b.tool_use_id));
  for (const b of results) {
    const r = o.toolUseResult, more: Raw = obj(r), text = resultText(b.content);
    const exit = EXIT.exec(text)?.[1];
    out.push({
      k: "result", at, id: str(b.tool_use_id), error: b.is_error === true,
      out: clip(str(more.stdout) || text), err: clip(str(more.stderr)), interrupted: more.interrupted === true, // a failed command: what the agent was shown
      // Claude Code says a failed command's code and nothing for one that exited 0; a refusal has neither
      exit: exit !== undefined ? Number(exit) : b.is_error === true ? null : 0, more: kept(more),
    });
  }
  if (results.length) return out;
  const text = words(content);
  if (INTERRUPTED.test(text)) return [...out, { k: "stop", at, side }];
  // what Claude Code wrote into the person's turn is not a request: flagged so, or come from somewhere else
  const origin = str(obj(o.origin).kind);
  if (o.isMeta === true || o.isCompactSummary === true || (origin && origin !== "human")) return out;
  const asked = slash(text) || (NOT_ASKED.test(text) ? "" : text.trim());
  if (asked) out.push({ k: "ask", at, text: asked, side });
  return out;
}
