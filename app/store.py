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

SCHEMA_VERSION = 3  # bump whenever the FTS tokenizer or table layout changes; the FTS indexes are rebuilt on mismatch

# Statements that read like standing instructions, constraints or preferences. Tagged at Add time
# (user role only) so Search can always offer them: "rule execution" is where every system on the
# cycle-1 board collapsed. Verbs are restricted to assistant-facing behaviour so that chatter such as
# "he always does" or "don't be smug" is not tagged.
_VERBS = (r"(?:suggest|recommend|bring\ up|mention|assume|use|call|refer|apply|deploy|order|put|include|propose|"
          r"write|add|answer|reply|respond|format|give|keep|flag|check|ask|send|show|say|talk|treat|address|serve|cook|offer|run|install)")
RULE_RE = re.compile(
    r"""(?x)\b(?:
        from\ now\ on | going\ forward | in\ (?:the\ )?future |
        whenever | every\ time | each\ time | when(?:ever)?\ (?:i|you)\ (?:ask|review|write|recommend|suggest|talk|give|send|plan|cook|book) |
        please\ (?:always|never|don'?t|do\ not|stop|only|keep|avoid|call|refer|use|check|make\ sure|remember) |
        (?:don'?t|do\ not|never|always|only)\ (?:ever\ )?""" + _VERBS + r""" |
        remember\ (?:that|to|this|:) | i\ want\ you\ to | i\ need\ you\ to | i\ expect\ you\ to |
        call\ me\b | refer\ to\ me | address\ me |
        (?:i|we)\ (?:prefer|'d\ prefer|would\ prefer|like\ it\ when) |
        my\ (?:preference|rule)s? | (?:ground|house|new|one|another|first|second|third|format(?:ting)?)\ rules?\b | one\ more\ rule | rules?\ for\ you | rules?\s*[:.] |
        forget\ (?:what|everything|about|the|that) | disregard | ignore\ what |
        must\ (?:be|always|never|use|follow|include|return|run|go|have|stay) | has\ to\ be | have\ to\ be | should\ (?:always|never) | (?:must|should)\ not |
        no\ longer | no\ more | only\ use | stop\ (?:doing|using|suggesting|calling|recommending) |
        remind\ me | so\ you\ (?:can\ )?remember | for\ (?:the|your)\ record | note\ (?:this|that)\ down |
        allerg(?:y|ic|ies) | vegetarian | vegan | gluten[- ]free | lactose | kosher | halal
    )\b""",
    re.IGNORECASE,
)
RULE_RE_CJK = re.compile(
    r"以后|今后|从今以后|从现在开始|别再|不要再|不要|永远不|一定要|务必|记住|请不要|请一定|每次|规则|只做|只用|"
    r"我喜欢|我不喜欢|我讨厌|我偏好|过敏|素食|不吃|叫我|称呼我|忘掉|忘记我|不用再"
)
CHUNK_ORDINAL_RE = re.compile(r"(?:chunk|part|seg|msg)[-_:](\d+)", re.IGNORECASE)
CJK_RE = re.compile(r"[぀-ヿ㐀-䶿一-鿿가-힯]")
POS_STRIDE = 1000  # positions inside one Add chunk: ordinal * POS_STRIDE + message index


class ConflictingRequestError(Exception):
    """request_id reused with a different payload."""


@dataclass(frozen=True)
class Chunk:
    id: str
    user_id: str
    session_id: str
    role: str
    content: str
    event_ms: Optional[int]   # message timestamp (unix ms) if the adapter sent one
    pos: int                  # conversation position (ordinal * POS_STRIDE + index)
    standing: bool            # tagged as a standing rule / preference at Add time
    stored_at: str

    @property
    def order_key(self) -> tuple[int, int]:
        """Larger = newer. Falls back to the Add position when no timestamp was sent."""
        return (self.event_ms or 0, self.pos)


def user_token(user_id: str) -> str:
    """Opaque per-user token stored in the FTS indexes so a MATCH can be scoped without a JOIN filter."""
    return "u" + hashlib.blake2b(user_id.encode("utf-8"), digest_size=12).hexdigest()


def cjk_only(text: str) -> str:
    """CJK characters of a text with everything else removed, so trigram matching ignores punctuation,
    spaces and interleaved Latin tokens (those are served by the word index)."""
    return "".join(CJK_RE.findall(text))


def render(chunk: Chunk) -> str:
    stamp = ""
    if chunk.event_ms is not None:
        try:
            stamp = "[" + datetime.fromtimestamp(chunk.event_ms / 1000, tz=timezone.utc).strftime("%Y-%m-%d %H:%M UTC") + "] "
        except (OverflowError, OSError, ValueError):
            stamp = ""
    return f"{stamp}{chunk.role.upper()}: {chunk.content}"


def looks_like_rule(role: str, text: str) -> bool:
    if role != "user":
        return False
    if RULE_RE.search(text):
        return True
    return CJK_RE.search(text) is not None and RULE_RE_CJK.search(text) is not None


_SCHEMA = """
CREATE TABLE IF NOT EXISTS ingest_log (
    request_id  TEXT PRIMARY KEY,
    fingerprint TEXT NOT NULL,
    user_id     TEXT NOT NULL,
    session_id  TEXT NOT NULL,
    received_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS memories (
    rowid      INTEGER PRIMARY KEY,
    id         TEXT UNIQUE NOT NULL,
    request_id TEXT NOT NULL,
    user_id    TEXT NOT NULL,
    session_id TEXT NOT NULL,
    role       TEXT NOT NULL,
    content    TEXT NOT NULL,
    event_ms   INTEGER,
    pos        INTEGER NOT NULL,
    standing   INTEGER NOT NULL DEFAULT 0,
    stored_at  TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_mem_order    ON memories(user_id, session_id, pos);
CREATE INDEX IF NOT EXISTS ix_mem_standing ON memories(user_id, standing, event_ms);
CREATE INDEX IF NOT EXISTS ix_mem_stored   ON memories(stored_at);
"""

_FTS = """
DROP TABLE IF EXISTS memories_fts;
DROP TABLE IF EXISTS memories_fts_tri;
CREATE VIRTUAL TABLE memories_fts USING fts5(utok, content, mem_id UNINDEXED, tokenize = 'porter unicode61 remove_diacritics 2');
CREATE VIRTUAL TABLE memories_fts_tri USING fts5(utok, content, mem_id UNINDEXED, tokenize = 'trigram');
"""


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
            columns = {r["name"] for r in conn.execute("PRAGMA table_info(memories)")}
            if columns and "pos" not in columns:
                raise RuntimeError(f"{self.database_path} has a pre-0.2 layout; move it away or point DATABASE_PATH at a new file")
            conn.executescript(_SCHEMA)
            if int(conn.execute("PRAGMA user_version").fetchone()[0]) != SCHEMA_VERSION:
                conn.executescript(_FTS)
                for r in conn.execute("SELECT rowid, user_id, content, id FROM memories"):
                    self._index(conn, r["rowid"], user_token(r["user_id"]), r["content"], r["id"])
                conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
            conn.commit()

    @staticmethod
    def _index(conn: sqlite3.Connection, rowid: int, utok: str, content: str, mem_id: str) -> None:
        conn.execute("INSERT INTO memories_fts(rowid, utok, content, mem_id) VALUES (?,?,?,?)", (rowid, utok, content, mem_id))
        cjk = cjk_only(content)
        if cjk:  # the trigram index only carries CJK text; English corpora pay nothing for it
            conn.execute("INSERT INTO memories_fts_tri(rowid, utok, content, mem_id) VALUES (?,?,?,?)", (rowid, utok, cjk, mem_id))

    # ---------------------------------------------------------------- add
    def add(self, payload: AddRequest) -> int:
        """Persist one Add call in a single transaction. Returns the number of turns stored
        (0 for an idempotent replay). Raises ConflictingRequestError when the request_id was already
        used with a different body."""
        canonical = json.dumps(payload.model_dump(), sort_keys=True, ensure_ascii=False, separators=(",", ":"))
        fingerprint = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
        received_at = datetime.now(timezone.utc).isoformat(timespec="milliseconds")
        ordinal = CHUNK_ORDINAL_RE.search(payload.request_id)
        with self.connect() as conn:
            claimed = conn.execute(
                "INSERT OR IGNORE INTO ingest_log(request_id, fingerprint, user_id, session_id, received_at) VALUES (?,?,?,?,?)",
                (payload.request_id, fingerprint, payload.user_id, payload.session_id, received_at),
            ).rowcount
            if claimed == 0:  # already ingested (or being ingested by another worker): replay or conflict
                prior = conn.execute("SELECT fingerprint FROM ingest_log WHERE request_id = ?", (payload.request_id,)).fetchone()
                if prior is not None and prior["fingerprint"] != fingerprint:
                    raise ConflictingRequestError(f"request_id {payload.request_id!r} was already used with a different body")
                return 0
            base = int(ordinal.group(1)) * POS_STRIDE if ordinal else self._next_block(conn, payload.user_id, payload.session_id)
            utok = user_token(payload.user_id)
            stored = 0
            for index, message in enumerate(payload.messages):
                text = message.text().strip()
                if not text:
                    continue
                mem_id = "mem_" + hashlib.blake2b(f"{payload.request_id}\x1f{index}".encode("utf-8"), digest_size=10).hexdigest()
                row = conn.execute(
                    "INSERT INTO memories(id, request_id, user_id, session_id, role, content, event_ms, pos, standing, stored_at)"
                    " VALUES (?,?,?,?,?,?,?,?,?,?)",
                    (mem_id, payload.request_id, payload.user_id, payload.session_id, message.role, text,
                     message.timestamp, base + index, int(looks_like_rule(message.role, text)), received_at),
                )
                self._index(conn, row.lastrowid, utok, text, mem_id)
                stored += 1
            conn.commit()
        return stored

    @staticmethod
    def _next_block(conn: sqlite3.Connection, user_id: str, session_id: str) -> int:
        row = conn.execute("SELECT MAX(pos) AS p FROM memories WHERE user_id = ? AND session_id = ?", (user_id, session_id)).fetchone()
        last = row["p"] if row and row["p"] is not None else -1
        return (int(last) // POS_STRIDE + 1) * POS_STRIDE

    # ------------------------------------------------------------- search
    @staticmethod
    def _chunk(row: sqlite3.Row) -> Chunk:
        return Chunk(id=row["id"], user_id=row["user_id"], session_id=row["session_id"], role=row["role"],
                     content=row["content"], event_ms=row["event_ms"], pos=row["pos"], standing=bool(row["standing"]),
                     stored_at=row["stored_at"])

    def _match(self, table: str, user_id: str, expr: str, limit: int) -> list[tuple[Chunk, float]]:
        if not expr:
            return []
        scoped = f'utok:"{user_token(user_id)}" AND ({expr})'
        sql = (f"SELECT m.*, bm25({table}, 0.0, 1.0) AS r FROM {table} JOIN memories m ON m.rowid = {table}.rowid"
               f" WHERE {table} MATCH ? ORDER BY r LIMIT ?")
        with self.connect() as conn:
            try:
                rows = conn.execute(sql, (scoped, limit)).fetchall()
            except sqlite3.OperationalError:  # malformed MATCH expression -> treat as no hits
                return []
        return [(self._chunk(r), -float(r["r"])) for r in rows]  # bm25() is negative; flip so higher is better

    def fts_search(self, user_id: str, expr: str, limit: int) -> list[tuple[Chunk, float]]:
        """Word-level (porter-stemmed) BM25 search."""
        return self._match("memories_fts", user_id, expr, limit)

    def trigram_search(self, user_id: str, expr: str, limit: int) -> list[tuple[Chunk, float]]:
        """Character-trigram BM25 search over the CJK text of each turn."""
        return self._match("memories_fts_tri", user_id, expr, limit)

    def span(self, chunk: Chunk, window: int) -> list[Chunk]:
        """The turn plus `window` turns before and after it, in conversation order. Crosses Add-chunk
        boundaries (pos jumps by POS_STRIDE there, so a BETWEEN would stop short)."""
        if window <= 0:
            return [chunk]
        with self.connect() as conn:
            before = conn.execute(
                "SELECT * FROM memories WHERE user_id = ? AND session_id = ? AND pos < ? ORDER BY pos DESC LIMIT ?",
                (chunk.user_id, chunk.session_id, chunk.pos, window)).fetchall()
            after = conn.execute(
                "SELECT * FROM memories WHERE user_id = ? AND session_id = ? AND pos > ? ORDER BY pos LIMIT ?",
                (chunk.user_id, chunk.session_id, chunk.pos, window)).fetchall()
        return [self._chunk(r) for r in reversed(before)] + [chunk] + [self._chunk(r) for r in after]

    def standing_rules(self, user_id: str, limit: int) -> list[Chunk]:
        if limit <= 0:
            return []
        with self.connect() as conn:
            rows = conn.execute("SELECT * FROM memories WHERE user_id = ? AND standing = 1 ORDER BY event_ms DESC, pos DESC LIMIT ?",
                                (user_id, limit)).fetchall()
        return [self._chunk(r) for r in rows]

    def newest(self, user_id: str, limit: int) -> list[Chunk]:
        if limit <= 0:
            return []
        with self.connect() as conn:
            rows = conn.execute("SELECT * FROM memories WHERE user_id = ? ORDER BY event_ms DESC, pos DESC LIMIT ?",
                                (user_id, limit)).fetchall()
        return [self._chunk(r) for r in rows]

    def count(self, user_id: str) -> int:
        with self.connect() as conn:
            return int(conn.execute("SELECT COUNT(*) FROM memories WHERE user_id = ?", (user_id,)).fetchone()[0])

    # --------------------------------------------------------- governance
    def delete_expired(self) -> int:
        """Drop everything stored more than `retention_days` ago (competition rule: delete within 30 days)."""
        cutoff = (datetime.now(timezone.utc) - timedelta(days=self.retention_days)).isoformat(timespec="milliseconds")
        with self.connect() as conn:
            stale = [r["rowid"] for r in conn.execute("SELECT rowid FROM memories WHERE stored_at < ?", (cutoff,))]
            for table in ("memories_fts", "memories_fts_tri", "memories"):
                conn.executemany(f"DELETE FROM {table} WHERE rowid = ?", [(rid,) for rid in stale])
            conn.execute("DELETE FROM ingest_log WHERE received_at < ?", (cutoff,))
            conn.commit()
        return len(stale)
