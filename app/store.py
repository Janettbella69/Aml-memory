from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterator, Optional

from .models import AddRequest

# Statements that read like standing instructions / preferences. They are tagged at
# Add time and always offered to Search (the "rule execution" capability is where
# every system on the cycle-1 board collapsed).
RULE_RE = re.compile(
    r"\b(always|never|from now on|going forward|in the future|remember (?:that|to)|"
    r"don'?t|do not|make sure|please (?:call|refer|use|avoid|stop|keep|only)|"
    r"i (?:prefer|would prefer|'d prefer|like it when|want you to|need you to)|"
    r"my (?:preference|rule)|whenever|every time|only use|stop (?:doing|using|calling))\b",
    re.IGNORECASE,
)
CHUNK_ORDINAL_RE = re.compile(r"(?:chunk|part|seg|msg)[-_:](\d+)", re.IGNORECASE)


class ConflictingRequestError(Exception):
    """request_id reused with a different payload."""


@dataclass(frozen=True)
class Chunk:
    id: str
    user_id: str
    session_id: str
    role: str
    content: str
    ts: Optional[int]
    seq: int
    is_rule: bool
    created_at: str


def user_token(user_id: str) -> str:
    return "u" + hashlib.sha1(user_id.encode("utf-8")).hexdigest()[:24]


def render(chunk: Chunk) -> str:
    stamp = ""
    if chunk.ts is not None:
        try:
            stamp = "[" + datetime.fromtimestamp(chunk.ts / 1000, tz=timezone.utc).strftime("%Y-%m-%d %H:%M UTC") + "] "
        except (OverflowError, OSError, ValueError):
            stamp = ""
    return f"{stamp}{chunk.role.upper()}: {chunk.content}"


class MemoryStore:
    def __init__(self, database_path: str, retention_days: int = 30) -> None:
        self.database_path = database_path
        self.retention_days = retention_days
        self.initialize()

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.database_path, timeout=30.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA busy_timeout = 30000")
        try:
            yield conn
        finally:
            conn.close()

    def initialize(self) -> None:
        Path(self.database_path).parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as conn:
            conn.execute("PRAGMA journal_mode = WAL")
            conn.execute("PRAGMA synchronous = NORMAL")
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS add_requests (
                    request_id TEXT PRIMARY KEY,
                    payload_hash TEXT NOT NULL,
                    user_id TEXT NOT NULL,
                    session_id TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS memories (
                    rowid INTEGER PRIMARY KEY,
                    id TEXT UNIQUE NOT NULL,
                    request_id TEXT NOT NULL,
                    user_id TEXT NOT NULL,
                    session_id TEXT NOT NULL,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    ts INTEGER,
                    seq INTEGER NOT NULL,
                    is_rule INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_mem_user_seq ON memories(user_id, session_id, seq);
                CREATE INDEX IF NOT EXISTS idx_mem_user_rule ON memories(user_id, is_rule);
                CREATE INDEX IF NOT EXISTS idx_mem_user_created ON memories(user_id, created_at);
                CREATE VIRTUAL TABLE IF NOT EXISTS memories_fts USING fts5(
                    utok, content, mem_id UNINDEXED,
                    tokenize = 'unicode61 remove_diacritics 2'
                );
                """
            )
            conn.commit()

    # ---------------------------------------------------------------- add
    def add(self, payload: AddRequest) -> int:
        """Persist synchronously. Returns number of chunks written (0 if idempotent replay)."""
        body = payload.model_dump()
        digest = hashlib.sha256(json.dumps(body, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
        now = datetime.now(timezone.utc).isoformat()
        with self.connect() as conn:
            existing = conn.execute(
                "SELECT payload_hash FROM add_requests WHERE request_id = ?", (payload.request_id,)
            ).fetchone()
            if existing is not None:
                if existing["payload_hash"] != digest:
                    raise ConflictingRequestError(f"request_id {payload.request_id!r} already used with a different payload")
                return 0
            ordinal = CHUNK_ORDINAL_RE.search(payload.request_id)
            base_seq = int(ordinal.group(1)) * 1000 if ordinal else self._next_seq(conn, payload.user_id, payload.session_id)
            conn.execute(
                "INSERT INTO add_requests(request_id, payload_hash, user_id, session_id, created_at) VALUES (?,?,?,?,?)",
                (payload.request_id, digest, payload.user_id, payload.session_id, now),
            )
            utok = user_token(payload.user_id)
            written = 0
            for index, message in enumerate(payload.messages):
                text = message.text().strip()
                if not text:
                    continue
                mem_id = "mem_" + hashlib.sha1(f"{payload.request_id}#{index}".encode()).hexdigest()[:20]
                is_rule = 1 if (message.role == "user" and RULE_RE.search(text)) else 0
                cur = conn.execute(
                    "INSERT INTO memories(id, request_id, user_id, session_id, role, content, ts, seq, is_rule, created_at)"
                    " VALUES (?,?,?,?,?,?,?,?,?,?)",
                    (mem_id, payload.request_id, payload.user_id, payload.session_id, message.role, text,
                     message.timestamp, base_seq + index, is_rule, now),
                )
                conn.execute(
                    "INSERT INTO memories_fts(rowid, utok, content, mem_id) VALUES (?,?,?,?)",
                    (cur.lastrowid, utok, text, mem_id),
                )
                written += 1
            conn.commit()
        return written

    @staticmethod
    def _next_seq(conn: sqlite3.Connection, user_id: str, session_id: str) -> int:
        row = conn.execute(
            "SELECT COALESCE(MAX(seq), -1) AS m FROM memories WHERE user_id = ? AND session_id = ?",
            (user_id, session_id),
        ).fetchone()
        return (int(row["m"]) // 1000 + 1) * 1000

    # ------------------------------------------------------------- search
    @staticmethod
    def _row_to_chunk(row: sqlite3.Row) -> Chunk:
        return Chunk(
            id=row["id"], user_id=row["user_id"], session_id=row["session_id"], role=row["role"],
            content=row["content"], ts=row["ts"], seq=row["seq"], is_rule=bool(row["is_rule"]),
            created_at=row["created_at"],
        )

    def fts_search(self, user_id: str, match_expr: str, limit: int) -> list[tuple[Chunk, float]]:
        if not match_expr:
            return []
        utok = user_token(user_id)
        sql = (
            "SELECT m.*, bm25(memories_fts, 0.0, 1.0) AS rank FROM memories_fts f"
            " JOIN memories m ON m.rowid = f.rowid"
            " WHERE memories_fts MATCH ? ORDER BY rank LIMIT ?"
        )
        expr = f'utok:{utok} AND ({match_expr})'
        with self.connect() as conn:
            try:
                rows = conn.execute(sql, (expr, limit)).fetchall()
            except sqlite3.OperationalError:
                return []
        # bm25() returns negative numbers (lower is better); flip sign so higher is better.
        return [(self._row_to_chunk(r), -float(r["rank"])) for r in rows]

    def neighbors(self, chunk: Chunk, window: int) -> list[Chunk]:
        if window <= 0:
            return [chunk]
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM memories WHERE user_id = ? AND session_id = ? AND seq BETWEEN ? AND ? ORDER BY seq",
                (chunk.user_id, chunk.session_id, chunk.seq - window, chunk.seq + window),
            ).fetchall()
        return [self._row_to_chunk(r) for r in rows] or [chunk]

    def rules(self, user_id: str, limit: int) -> list[Chunk]:
        if limit <= 0:
            return []
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM memories WHERE user_id = ? AND is_rule = 1 ORDER BY ts DESC, rowid DESC LIMIT ?",
                (user_id, limit),
            ).fetchall()
        return [self._row_to_chunk(r) for r in rows]

    def latest(self, user_id: str, limit: int) -> list[Chunk]:
        if limit <= 0:
            return []
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM memories WHERE user_id = ? ORDER BY ts DESC, rowid DESC LIMIT ?",
                (user_id, limit),
            ).fetchall()
        return [self._row_to_chunk(r) for r in rows]

    def count(self, user_id: str) -> int:
        with self.connect() as conn:
            return int(conn.execute("SELECT COUNT(*) FROM memories WHERE user_id = ?", (user_id,)).fetchone()[0])

    # --------------------------------------------------------- governance
    def delete_expired(self) -> int:
        cutoff = (datetime.now(timezone.utc) - timedelta(days=self.retention_days)).isoformat()
        with self.connect() as conn:
            old = conn.execute("SELECT rowid FROM memories WHERE created_at < ?", (cutoff,)).fetchall()
            ids = [r["rowid"] for r in old]
            for rid in ids:
                conn.execute("DELETE FROM memories_fts WHERE rowid = ?", (rid,))
                conn.execute("DELETE FROM memories WHERE rowid = ?", (rid,))
            conn.execute("DELETE FROM add_requests WHERE created_at < ?", (cutoff,))
            conn.commit()
        return len(ids)
