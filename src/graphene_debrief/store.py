"""SQLite store at .graphene/graphene.db. Hooks write concurrently, so WAL + busy timeout."""

from __future__ import annotations

import contextlib
import json
import os
import sqlite3
from pathlib import Path

from .model import Agent, Commit, DebriefRun, Prompt, Session, ToolEvent

TIMEOUT = 5.0  # seconds to wait for another process's write lock before giving up
RESPONSE_CAP = 256 * 1024
STRING_CAP = 8 * 1024  # a recorded string longer than this keeps its first and last KEEP bytes only
KEEP = 4 * 1024
CONTENT_CAP = 2 * 1024 * 1024
SCHEMA_VERSION = 2  # a hook-recorded session may outlive its transcript: migrate in place, never rebuild

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

# Additive only: a step adds tables and columns and never drops or rewrites one. Step n takes a
# store from version n-1 to n; SCHEMA above is version 1 and stays as it was.
MIGRATIONS: dict[int, tuple[str, ...]] = {
    2: (
        "ALTER TABLE tool_events ADD COLUMN cwd TEXT",
        """CREATE TABLE agents (
             id TEXT NOT NULL,
             session_id TEXT NOT NULL,
             parent_tool_use_id TEXT,
             parent_agent_id TEXT,
             type TEXT,
             task TEXT,
             prompt TEXT,
             cwd TEXT,
             worktree TEXT,
             workflow_run TEXT,
             phase TEXT,
             label TEXT,
             depth INTEGER,
             started_at TEXT,
             ended_at TEXT,
             closing TEXT,
             source TEXT NOT NULL DEFAULT 'claude-code',
             PRIMARY KEY (session_id, id)
           )""",
        """CREATE TABLE commits (
             sha TEXT PRIMARY KEY,
             committed_at TEXT NOT NULL,
             subject TEXT NOT NULL,
             session_id TEXT,
             agent_id TEXT,
             event_id TEXT,
             origin_sha TEXT
           )""",
        "CREATE INDEX commits_by_time ON commits (committed_at)",
        """CREATE TABLE commit_files (
             sha TEXT NOT NULL,
             path TEXT NOT NULL,
             status TEXT,
             PRIMARY KEY (sha, path)
           )""",
        # Sessions read before this version have no agents, no cwd and no worktree mapping. Forget
        # only that their transcripts were read, so the next command reads again those that still
        # exist; a session whose transcript is gone has no file to be re-read from and stays as it is.
        "UPDATE sessions SET transcript_size = NULL, transcript_mtime = NULL",
    ),
}


class StaleStore(Exception):
    """The file on disk cannot be used as it is, and ``tag`` says why: ``corrupt`` for a file SQLite
    will not read (the CLI moves that one aside), ``newer`` for a store a later Graphene wrote
    (left exactly where it is)."""

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


# Values kept whole however long they are: the vendor's list of files a command changed, what it
# says about the git operation and the interrupt, and the error text of a failed call.
RESPONSE_KEPT = frozenset({"bashEditDiff", "gitOperation", "interrupted", "is_interrupt"})
# The same on the way in: a path or a name is never cut, however deep in the payload it sits.
INPUT_KEPT = frozenset({"file_path", "notebook_path", "path", "description", "subagent_type"})


def _trim(text: str) -> str:
    """A long string as its head and its tail. The tail is the point: agents run
    `git commit -q … && git log --oneline -1`, so the new SHA is on the very last line."""
    if len(text) <= STRING_CAP:
        return text
    return f"{text[:KEEP]}\n… [{len(text) - 2 * KEEP} chars omitted] …\n{text[-KEEP:]}"


def _trimmed(value: object, kept: frozenset[str]) -> object:
    """``_trim`` every string in a payload, except the values of the keys named in ``kept``."""
    if isinstance(value, str):
        return _trim(value)
    if isinstance(value, dict):
        return {k: v if k in kept else _trimmed(v, kept) for k, v in value.items()}
    if isinstance(value, list):
        return [_trimmed(v, kept) for v in value]
    return value


def capped_json(value: object, cap: int = RESPONSE_CAP) -> str | None:
    """Serialise a tool response: long output strings keep their head and tail, then the vendor's
    change list loses its hunks (never its paths), and only then the response is given up whole."""
    if value is None:
        return None
    value = _trimmed(value, RESPONSE_KEPT)
    text = json.dumps(value, ensure_ascii=False, default=str)
    if len(text) <= cap:
        return text
    if isinstance(value, dict) and isinstance(value.get("bashEditDiff"), dict):
        value = {**value, "bashEditDiff": _without_hunks(value["bashEditDiff"])}
        text = json.dumps(value, ensure_ascii=False, default=str)
        if len(text) <= cap:
            return text
    return json.dumps({"truncated": True, "bytes": len(text)})


def _without_hunks(diff: dict) -> dict:
    """The change list minus the diff bodies: which files changed is what the records read."""
    if not isinstance(diff.get("files"), list):
        return diff
    kept = [{k: v for k, v in f.items() if k != "hunks"} if isinstance(f, dict) else f for f in diff["files"]]
    return {**diff, "files": kept}


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
            if self._version() > SCHEMA_VERSION:
                raise StaleStore("newer")
            if self._version() < SCHEMA_VERSION:
                self._migrate()
        except sqlite3.DatabaseError as exc:
            self.conn.close()
            if isinstance(exc, sqlite3.OperationalError):
                raise  # a locked database is fine, just busy: never move that aside
            raise StaleStore("corrupt") from exc
        except BaseException:
            self.conn.close()
            raise

    def _version(self) -> int:
        return int(self.conn.execute("PRAGMA user_version").fetchone()[0])

    def _migrate(self) -> None:
        """Bring an older store up to date in place. Version 0 is a new file or a store from before
        versioning, whose tables are version 1's. One transaction, and the version is read again
        inside it, so two processes opening an old store at once apply each step once."""
        self.conn.execute("BEGIN IMMEDIATE")
        try:
            version = self._version()
            if version < 1:
                for statement in SCHEMA.split(";"):
                    if statement.strip():
                        self.conn.execute(statement)
            for step in range(max(version, 1) + 1, SCHEMA_VERSION + 1):
                for statement in MIGRATIONS[step]:
                    self.conn.execute(statement)
            self.conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
        except BaseException:
            self.conn.execute("ROLLBACK")
            raise
        self.conn.execute("COMMIT")

    @classmethod
    def open(cls, repo_root: Path, quick: bool = False) -> Store:
        """Open (creating) the repo's store. ``quick`` is the hook path: give up on a lock after 250 ms.

        The directory is private to the user and git-ignored on every open, not only by `init`,
        because whichever command creates it fills it with transcript content.

        An older store is migrated in place by whoever opens it, the hook included (the steps only
        add tables and columns). Only a file SQLite cannot read is moved aside and replaced by an
        empty one (the caller backfills it); ``rebuilt_from`` then holds the backup path. The hook
        path never does that, and nobody touches a store a newer Graphene wrote: both raise
        ``StaleStore``.
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
            if quick or stale.tag != "corrupt":
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

    def did_something(self, session_id: str) -> bool:
        """Did this session leave a recorded write in the repo, or a commit credited to it?"""
        row = self.conn.execute(
            """SELECT EXISTS (SELECT 1 FROM tool_events WHERE session_id = ?1 AND success IS NOT 0 AND (
                   (file_path IS NOT NULL AND file_path NOT LIKE '/%')
                   OR (tool = 'Bash' AND response LIKE '%"bashEditDiff"%')))
               OR EXISTS (SELECT 1 FROM commits WHERE session_id = ?1)""",
            (session_id,),
        ).fetchone()
        return bool(row[0])

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
        """Drop prompts, events and agents before a reload from the transcript. Commits are git's
        and stay (the reload credits them again); stored explanations are left alone too."""
        self.conn.execute("DELETE FROM tool_events WHERE session_id = ?", (session_id,))
        self.conn.execute("DELETE FROM agents WHERE session_id = ?", (session_id,))
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
                file_path, old_content, new_content, cwd)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                e.id,
                e.session_id,
                e.prompt_id,
                e.timestamp,
                e.tool,
                json.dumps(_trimmed(e.input, INPUT_KEPT), ensure_ascii=False, default=str),
                # A Read's response is the file it read: nothing here ever reads it back, and on
                # the author's store those copies were 10 MB of 73 MB.
                None if e.tool == "Read" else capped_json(e.response),
                None if e.success is None else int(e.success),
                e.agent_id,
                e.file_path,
                _content(e.old_content),
                _content(e.new_content),
                e.cwd,
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

    # -- agents and commits -------------------------------------------------------------------

    def upsert_agent(self, a: Agent) -> None:
        """Insert, or fill in what a later record knows: a hook event sees the start, the transcript
        the task, the handback the closing message."""
        cols = [f for f in Agent.__slots__ if f not in ("id", "session_id")]
        self.conn.execute(
            f"INSERT INTO agents (id, session_id, {', '.join(cols)}) "
            f"VALUES (?, ?, {', '.join('?' for _ in cols)}) ON CONFLICT (session_id, id) DO UPDATE SET "
            + ", ".join(f"{c} = COALESCE(excluded.{c}, agents.{c})" for c in cols),
            (a.id, a.session_id, *(getattr(a, c) for c in cols)),
        )

    def agents(self, session_id: str) -> list[Agent]:
        rows = self.conn.execute(
            "SELECT * FROM agents WHERE session_id = ? ORDER BY started_at, id", (session_id,)
        ).fetchall()
        return [Agent(**{f: r[f] for f in Agent.__slots__}) for r in rows]

    def add_commit(self, c: Commit) -> None:
        """Insert a commit and its files, or credit one already known: the first credit stands."""
        self.conn.execute(
            """INSERT INTO commits (sha, committed_at, subject, session_id, agent_id, event_id, origin_sha)
               VALUES (?, ?, ?, ?, ?, ?, ?) ON CONFLICT (sha) DO UPDATE SET
                 session_id = COALESCE(commits.session_id, excluded.session_id),
                 agent_id = IIF(commits.session_id IS NULL, excluded.agent_id, commits.agent_id),
                 event_id = IIF(commits.session_id IS NULL, excluded.event_id, commits.event_id),
                 origin_sha = COALESCE(commits.origin_sha, excluded.origin_sha)""",
            (c.sha, c.committed_at, c.subject, c.session_id, c.agent_id, c.event_id, c.origin_sha),
        )
        self.conn.executemany(
            "INSERT OR IGNORE INTO commit_files (sha, path, status) VALUES (?, ?, ?)",
            [(c.sha, path, status) for path, status in c.files],
        )

    def commits_between(self, start: str, end: str) -> list[Commit]:
        """Commits whose commit time lies in the window, oldest first, each with its files."""
        rows = self.conn.execute(
            "SELECT * FROM commits WHERE committed_at >= ? AND committed_at <= ? ORDER BY committed_at, sha",
            (start, end),
        ).fetchall()
        return [
            Commit(
                **{f: r[f] for f in Commit.__slots__ if f != "files"},
                files=[
                    (f["path"], f["status"])
                    for f in self.conn.execute(
                        "SELECT path, status FROM commit_files WHERE sha = ? ORDER BY path", (r["sha"],)
                    )
                ],
            )
            for r in rows
        ]

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

    def recorded_path_count(self) -> int:
        row = self.conn.execute(
            "SELECT COUNT(DISTINCT file_path) FROM tool_events "
            "WHERE file_path IS NOT NULL AND file_path NOT LIKE '/%'"
        ).fetchone()
        return int(row[0])


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
        cwd=r["cwd"],
    )
