"""SQLite store at .graphene/graphene.db. Hooks write concurrently, so WAL + busy timeout."""

from __future__ import annotations

import contextlib
import json
import os
import sqlite3
from pathlib import Path

from .model import DebriefRun, Prompt, Session, ToolEvent

TIMEOUT = 5.0  # seconds to wait for another process's write lock before giving up
RESPONSE_CAP = 256 * 1024
CONTENT_CAP = 2 * 1024 * 1024
SCHEMA_VERSION = 1  # everything here is regenerable, so a mismatch is rebuilt, never migrated

SCHEMA = """
CREATE TABLE IF NOT EXISTS sessions (
  id TEXT PRIMARY KEY,
  repo TEXT NOT NULL,
  started_at TEXT,
  ended_at TEXT,
  head_at_start TEXT,
  source TEXT NOT NULL,
  transcript_path TEXT,
  transcript_size INTEGER,
  transcript_mtime REAL
);
CREATE TABLE IF NOT EXISTS prompts (
  id TEXT NOT NULL,
  session_id TEXT NOT NULL,
  ordinal INTEGER NOT NULL,
  timestamp TEXT NOT NULL,
  text TEXT NOT NULL,
  PRIMARY KEY (session_id, id),
  UNIQUE (session_id, ordinal)
);
CREATE TABLE IF NOT EXISTS tool_events (
  id TEXT NOT NULL,
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
  new_content TEXT,
  PRIMARY KEY (session_id, id)
);
CREATE INDEX IF NOT EXISTS tool_events_by_session ON tool_events (session_id, timestamp);
CREATE TABLE IF NOT EXISTS explanations (
  prompt_id TEXT NOT NULL,
  path TEXT NOT NULL,
  text TEXT NOT NULL,
  source TEXT NOT NULL,
  created_at TEXT NOT NULL,
  model TEXT,
  PRIMARY KEY (prompt_id, path)
);
CREATE TABLE IF NOT EXISTS debrief_runs (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  session_ids TEXT NOT NULL,
  timestamp TEXT NOT NULL
);
"""


class StaleStore(Exception):
    """The file on disk is not a store of this schema version (or not a database at all).

    ``tag`` names the backup the CLI moves it to: ``v0`` for an older schema, ``corrupt`` for a
    file SQLite will not read.
    """

    def __init__(self, tag: str) -> None:
        super().__init__(tag)
        self.tag = tag


def set_aside(path: Path, tag: str) -> Path:
    """Move an unusable store and its WAL sidecars out of the way; never overwrite an older backup."""
    backup = path.with_name(f"{path.name}.{tag}.bak")
    n = 2
    while backup.exists():
        backup = path.with_name(f"{path.name}.{tag}.{n}.bak")
        n += 1
    os.replace(path, backup)
    for sidecar in ("-wal", "-shm"):  # else SQLite would replay them into the new file
        side = Path(str(path) + sidecar)
        if side.exists():
            os.replace(side, Path(str(backup) + sidecar))
    return backup


def ignore_store_dir(root: Path) -> bool:
    """Make .graphene/ ignore itself with a `.gitignore` of its own (the .venv/ trick), so the repo's
    own .gitignore is never touched. Returns True when the file was written."""
    path = root / ".graphene" / ".gitignore"
    if path.exists():
        return False
    path.parent.mkdir(exist_ok=True)
    path.write_text("*\n", encoding="utf-8")
    return True


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


def _content(text: object) -> str | None:
    return text if isinstance(text, str) and len(text) <= CONTENT_CAP else None


class Store:
    def __init__(self, path: Path, timeout: float = 5.0) -> None:
        self.path = path
        self.rebuilt_from: str | None = None  # set by open() when this store replaced an unusable one
        self.conn = sqlite3.connect(path, timeout=timeout, isolation_level=None)
        self.conn.row_factory = sqlite3.Row
        try:
            self.conn.execute(f"PRAGMA busy_timeout={int(timeout * 1000)}")
            self.conn.execute("PRAGMA journal_mode=WAL")
            self.conn.execute("PRAGMA synchronous=NORMAL")
            version = int(self.conn.execute("PRAGMA user_version").fetchone()[0])
            written = self.conn.execute("SELECT COUNT(*) FROM sqlite_master").fetchone()[0]
            if version != SCHEMA_VERSION and written:  # a brand new file is version 0 and empty
                raise StaleStore(f"v{version}")
            self.conn.executescript(SCHEMA)
            self.conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
        except sqlite3.DatabaseError as exc:
            self.conn.close()
            if isinstance(exc, sqlite3.OperationalError):
                raise  # a locked database is fine, just busy: never move that aside
            raise StaleStore("corrupt") from exc
        except BaseException:
            self.conn.close()
            raise

    @classmethod
    def open(cls, repo_root: Path, quick: bool = False) -> Store:
        """Open (creating) the repo's store. ``quick`` is the hook path: give up on a lock after 250 ms.

        The directory is private to the user and git-ignored on every open, not only by `init`,
        because whichever command creates it fills it with transcript content.

        A store from another schema version, or a file SQLite cannot read, is moved aside and
        replaced by an empty one (the caller backfills it); ``rebuilt_from`` then holds the backup
        path. The hook path never rebuilds: it raises ``StaleStore`` and skips the event.
        """
        directory = repo_root / ".graphene"
        directory.mkdir(exist_ok=True)
        os.chmod(directory, 0o700)
        ignore_store_dir(repo_root)
        path = directory / "graphene.db"
        timeout = 0.25 if quick else TIMEOUT
        try:
            store = cls(path, timeout=timeout)
        except StaleStore as stale:
            if quick:
                raise
            backup = set_aside(path, stale.tag)
            store = cls(path, timeout=timeout)
            store.rebuilt_from = str(backup.relative_to(repo_root))
        with contextlib.suppress(OSError):
            os.chmod(path, 0o600)  # the file too, not only the directory: transcripts can hold secrets
        return store

    def close(self) -> None:
        self.conn.close()

    @contextlib.contextmanager
    def transaction(self):
        """Group writes (the store is autocommit otherwise): all or nothing, one WAL append."""
        self.conn.execute("BEGIN")
        try:
            yield
        except BaseException:
            self.conn.execute("ROLLBACK")
            raise
        self.conn.execute("COMMIT")

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

    def transcript_stat(self, session_id: str) -> tuple[int, float] | None:
        """Size and mtime of the transcript when this session was last read from it."""
        row = self.conn.execute(
            "SELECT transcript_size, transcript_mtime FROM sessions WHERE id = ?", (session_id,)
        ).fetchone()
        return None if row is None or row[0] is None else (int(row[0]), float(row[1]))

    def set_transcript_stat(self, session_id: str, stat: tuple[int, float]) -> None:
        self.conn.execute(
            "UPDATE sessions SET transcript_size = ?, transcript_mtime = ? WHERE id = ?",
            (stat[0], stat[1], session_id),
        )

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

    def prompt(self, session_id: str, prompt_id: str) -> Prompt | None:
        row = self.conn.execute(
            "SELECT * FROM prompts WHERE session_id = ? AND id = ?", (session_id, prompt_id)
        ).fetchone()
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

    def event_count(self, session_id: str) -> int:
        return int(
            self.conn.execute(
                "SELECT COUNT(*) FROM tool_events WHERE session_id = ?", (session_id,)
            ).fetchone()[0]
        )

    # -- explanations -------------------------------------------------------------------------

    def set_explanation(
        self,
        prompt_id: str,
        path: str,
        text: str,
        source: str,
        created_at: str,
        model: str | None = None,
    ) -> None:
        self.conn.execute(
            "INSERT OR REPLACE INTO explanations (prompt_id, path, text, source, created_at, model) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (prompt_id, path, text, source, created_at, model),
        )

    def explanation(self, prompt_id: str, path: str) -> tuple[str, str, str | None] | None:
        """(sentence, who wrote it, which model wrote it if any)."""
        row = self.conn.execute(
            "SELECT text, source, model FROM explanations WHERE prompt_id = ? AND path = ?",
            (prompt_id, path),
        ).fetchone()
        return (row[0], row[1], row[2]) if row else None

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

    def recent_paths(self, limit: int = 5) -> list[tuple[str, str]]:
        """(repo-relative path, last time it was touched), newest first: what `why` suggests."""
        rows = self.conn.execute(
            "SELECT file_path, MAX(timestamp) AS last FROM tool_events "
            "WHERE file_path IS NOT NULL AND file_path NOT LIKE '/%' "
            "GROUP BY file_path ORDER BY last DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [(r["file_path"], r["last"]) for r in rows]


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
