"""SQLite store at .graphene/graphene.db. Hooks write concurrently, so WAL + busy timeout."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from .model import DebriefRun, Prompt, Session, ToolEvent

RESPONSE_CAP = 256 * 1024
CONTENT_CAP = 2 * 1024 * 1024

SCHEMA = """
CREATE TABLE IF NOT EXISTS sessions (
  id TEXT PRIMARY KEY,
  repo TEXT NOT NULL,
  started_at TEXT,
  ended_at TEXT,
  head_at_start TEXT,
  source TEXT NOT NULL,
  transcript_path TEXT
);
CREATE TABLE IF NOT EXISTS prompts (
  id TEXT PRIMARY KEY,
  session_id TEXT NOT NULL,
  ordinal INTEGER NOT NULL,
  timestamp TEXT NOT NULL,
  text TEXT NOT NULL,
  UNIQUE (session_id, ordinal)
);
CREATE TABLE IF NOT EXISTS tool_events (
  id TEXT PRIMARY KEY,
  session_id TEXT NOT NULL,
  prompt_id TEXT,
  timestamp TEXT NOT NULL,
  tool TEXT NOT NULL,
  input TEXT NOT NULL,
  response TEXT,
  success INTEGER,
  agent_id TEXT,
  file_path TEXT,
  old_content TEXT,
  new_content TEXT
);
CREATE INDEX IF NOT EXISTS tool_events_by_session ON tool_events (session_id, timestamp);
CREATE INDEX IF NOT EXISTS tool_events_by_path ON tool_events (file_path);
CREATE TABLE IF NOT EXISTS explanations (
  prompt_id TEXT NOT NULL,
  path TEXT NOT NULL,
  text TEXT NOT NULL,
  source TEXT NOT NULL,
  created_at TEXT NOT NULL,
  PRIMARY KEY (prompt_id, path)
);
CREATE TABLE IF NOT EXISTS debrief_runs (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  session_ids TEXT NOT NULL,
  timestamp TEXT NOT NULL
);
"""


def capped_json(value: object, cap: int = RESPONSE_CAP) -> str | None:
    """Serialise a tool response, shrinking oversized string fields, then giving up."""
    if value is None:
        return None
    text = json.dumps(value, ensure_ascii=False, default=str)
    if len(text) <= cap:
        return text
    if isinstance(value, dict):
        shrunk = {
            k: (
                v[:4096] + f"… [{len(v) - 4096} chars truncated]"
                if isinstance(v, str) and len(v) > 4096
                else v
            )
            for k, v in value.items()
        }
        text = json.dumps(shrunk, ensure_ascii=False, default=str)
        if len(text) <= cap:
            return text
    return json.dumps({"truncated": True, "bytes": len(text)})


def _content(text: str | None) -> str | None:
    return None if text is None or len(text) > CONTENT_CAP else text


class Store:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.conn = sqlite3.connect(path, timeout=5.0, isolation_level=None)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA busy_timeout=5000")
        self.conn.execute("PRAGMA synchronous=NORMAL")
        self.conn.executescript(SCHEMA)

    @classmethod
    def open(cls, repo_root: Path) -> Store:
        directory = repo_root / ".graphene"
        directory.mkdir(exist_ok=True)
        return cls(directory / "graphene.db")

    def close(self) -> None:
        self.conn.close()

    def __enter__(self) -> Store:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    # -- sessions -----------------------------------------------------------------------------

    def upsert_session(self, s: Session) -> None:
        """Insert, or fill in blanks on an existing row. Never overwrites a known start/HEAD."""
        self.conn.execute(
            """INSERT INTO sessions (id, repo, started_at, ended_at, head_at_start, source, transcript_path)
               VALUES (?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT (id) DO UPDATE SET
                 started_at = COALESCE(sessions.started_at, excluded.started_at),
                 ended_at = COALESCE(excluded.ended_at, sessions.ended_at),
                 head_at_start = COALESCE(sessions.head_at_start, excluded.head_at_start),
                 transcript_path = COALESCE(excluded.transcript_path, sessions.transcript_path)""",
            (s.id, s.repo, s.started_at, s.ended_at, s.head_at_start, s.source, s.transcript_path),
        )

    def end_session(self, session_id: str, timestamp: str) -> None:
        self.conn.execute("UPDATE sessions SET ended_at = ? WHERE id = ?", (timestamp, session_id))

    def session(self, session_id: str) -> Session | None:
        row = self.conn.execute("SELECT * FROM sessions WHERE id = ?", (session_id,)).fetchone()
        return _session(row) if row else None

    def sessions(self) -> list[Session]:
        rows = self.conn.execute("SELECT * FROM sessions ORDER BY started_at, id").fetchall()
        return [_session(r) for r in rows]

    def delete_session_data(self, session_id: str) -> None:
        """Drop prompts and events (explanations are kept so `why` never re-calls a model)."""
        self.conn.execute("DELETE FROM tool_events WHERE session_id = ?", (session_id,))
        self.conn.execute("DELETE FROM prompts WHERE session_id = ?", (session_id,))
        self.conn.execute("DELETE FROM sessions WHERE id = ?", (session_id,))

    # -- prompts ------------------------------------------------------------------------------

    def add_prompt(self, p: Prompt) -> None:
        self.conn.execute(
            "INSERT OR IGNORE INTO prompts (id, session_id, ordinal, timestamp, text) VALUES (?, ?, ?, ?, ?)",
            (p.id, p.session_id, p.ordinal, p.timestamp, p.text),
        )

    def next_ordinal(self, session_id: str) -> int:
        row = self.conn.execute(
            "SELECT COALESCE(MAX(ordinal), 0) + 1 FROM prompts WHERE session_id = ?", (session_id,)
        ).fetchone()
        return int(row[0])

    def prompts(self, session_id: str) -> list[Prompt]:
        rows = self.conn.execute(
            "SELECT * FROM prompts WHERE session_id = ? ORDER BY ordinal", (session_id,)
        ).fetchall()
        return [_prompt(r) for r in rows]

    def prompt(self, prompt_id: str) -> Prompt | None:
        row = self.conn.execute("SELECT * FROM prompts WHERE id = ?", (prompt_id,)).fetchone()
        return _prompt(row) if row else None

    def latest_prompt_id(self, session_id: str) -> str | None:
        row = self.conn.execute(
            "SELECT id FROM prompts WHERE session_id = ? ORDER BY ordinal DESC LIMIT 1", (session_id,)
        ).fetchone()
        return row[0] if row else None

    # -- tool events --------------------------------------------------------------------------

    def add_event(self, e: ToolEvent) -> None:
        self.conn.execute(
            """INSERT OR REPLACE INTO tool_events
               (id, session_id, prompt_id, timestamp, tool, input, response, success, agent_id,
                file_path, old_content, new_content)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                e.id,
                e.session_id,
                e.prompt_id,
                e.timestamp,
                e.tool,
                json.dumps(e.input, ensure_ascii=False, default=str),
                capped_json(e.response),
                None if e.success is None else int(e.success),
                e.agent_id,
                e.file_path,
                _content(e.old_content),
                _content(e.new_content),
            ),
        )

    def events(self, session_id: str) -> list[ToolEvent]:
        rows = self.conn.execute(
            "SELECT * FROM tool_events WHERE session_id = ? ORDER BY timestamp, rowid", (session_id,)
        ).fetchall()
        return [_event(r) for r in rows]

    def events_for_path(self, path: str) -> list[ToolEvent]:
        rows = self.conn.execute(
            "SELECT * FROM tool_events WHERE file_path = ? ORDER BY timestamp, rowid", (path,)
        ).fetchall()
        return [_event(r) for r in rows]

    def event_count(self, session_id: str) -> int:
        return int(
            self.conn.execute(
                "SELECT COUNT(*) FROM tool_events WHERE session_id = ?", (session_id,)
            ).fetchone()[0]
        )

    # -- explanations -------------------------------------------------------------------------

    def set_explanation(self, prompt_id: str, path: str, text: str, source: str, created_at: str) -> None:
        self.conn.execute(
            "INSERT OR REPLACE INTO explanations (prompt_id, path, text, source, created_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (prompt_id, path, text, source, created_at),
        )

    def explanation(self, prompt_id: str, path: str) -> tuple[str, str] | None:
        row = self.conn.execute(
            "SELECT text, source FROM explanations WHERE prompt_id = ? AND path = ?", (prompt_id, path)
        ).fetchone()
        return (row[0], row[1]) if row else None

    # -- debrief runs -------------------------------------------------------------------------

    def add_debrief_run(self, session_ids: list[str], timestamp: str) -> DebriefRun:
        cur = self.conn.execute(
            "INSERT INTO debrief_runs (session_ids, timestamp) VALUES (?, ?)",
            (json.dumps(session_ids), timestamp),
        )
        return DebriefRun(int(cur.lastrowid), list(session_ids), timestamp)

    def last_debrief_run(self) -> DebriefRun | None:
        row = self.conn.execute("SELECT * FROM debrief_runs ORDER BY id DESC LIMIT 1").fetchone()
        return DebriefRun(row["id"], json.loads(row["session_ids"]), row["timestamp"]) if row else None


def _session(r: sqlite3.Row) -> Session:
    return Session(
        id=r["id"],
        repo=r["repo"],
        started_at=r["started_at"],
        ended_at=r["ended_at"],
        head_at_start=r["head_at_start"],
        source=r["source"],
        transcript_path=r["transcript_path"],
    )


def _prompt(r: sqlite3.Row) -> Prompt:
    return Prompt(
        id=r["id"], session_id=r["session_id"], ordinal=r["ordinal"], timestamp=r["timestamp"], text=r["text"]
    )


def _event(r: sqlite3.Row) -> ToolEvent:
    return ToolEvent(
        id=r["id"],
        session_id=r["session_id"],
        prompt_id=r["prompt_id"],
        timestamp=r["timestamp"],
        tool=r["tool"],
        input=json.loads(r["input"]),
        response=json.loads(r["response"]) if r["response"] else None,
        success=None if r["success"] is None else bool(r["success"]),
        agent_id=r["agent_id"],
        file_path=r["file_path"],
        old_content=r["old_content"],
        new_content=r["new_content"],
    )
