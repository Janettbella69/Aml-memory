from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Callable, TypeVar

T = TypeVar("T", int, float)

PLACEHOLDER_PREFIX = "change-me"


def _bounded(name: str, parse: Callable[[str], T], default: T, lo: T, hi: T) -> T:
    raw = os.environ.get(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        value = parse(raw.strip())
    except ValueError:
        raise RuntimeError(f"invalid {name}={raw!r}: expected a number in [{lo}, {hi}]") from None
    if value < lo or value > hi:
        raise RuntimeError(f"invalid {name}={raw!r}: expected a number in [{lo}, {hi}]")
    return value


@dataclass(frozen=True)
class Settings:
    api_key: str = ""                  # empty = auth disabled (local use only)
    data_dir: str = "data"             # one SQLite file per user under <data_dir>/users/
    retention_days: int = 30           # evaluation data must be deleted within 30 days of a run
    context_window: int = 2            # turns before/after each hit (sweep 10-07: 2 beats 1 on every metric)
    rule_slots: int = 6                # standing rules offered per search (also capped at top_k // 4)
    lead_hits: int = 5                 # BM25 hits placed before the rule slots
    recency_band: float = 0.2          # hits whose normalised score differs by less than this are ordered newest-first
    max_response_chars: int = 400_000  # ~100k tokens; the platform keeps a 117,760-token prefix in rank order
    fallback_results: int = 10         # newest memories returned when nothing matches
    sweep_hours: int = 6               # how often the retention sweep runs while the service is up
    search_parallelism: int = 1        # SQLite searches executed at once per process; soak 10-07: 1 -> 293 q/s, 16 -> 24 q/s (mutex contention)
    write_parallelism: int = 2         # Add transactions executed at once per process; soak 10-07: 2 -> 1,313 adds/s, 16 -> 627 adds/s
    planner_model: str = ""           # "" = deterministic only; "gpt-4o-mini" enables the one-step query planner
    planner_max_queries: int = 3
    planner_timeout: float = 20.0
    planner_snippets: int = 8          # first-pass results shown to the planner
    log_level: str = "INFO"

    @classmethod
    def from_env(cls) -> "Settings":
        key = os.environ.get("MEMORY_API_KEY", "").strip()
        if key and (len(key) < 16 or key.startswith(PLACEHOLDER_PREFIX)):
            raise RuntimeError("MEMORY_API_KEY must be a real secret of at least 16 characters (or empty to disable auth)")
        return cls(
            api_key=key,
            data_dir=os.environ.get("DATA_DIR", "data"),
            retention_days=_bounded("RETENTION_DAYS", int, 30, 1, 30),
            context_window=_bounded("CONTEXT_WINDOW", int, 2, 0, 5),
            rule_slots=_bounded("RULE_SLOTS", int, 6, 0, 50),
            lead_hits=_bounded("LEAD_HITS", int, 5, 0, 20),
            recency_band=_bounded("RECENCY_BAND", float, 0.2, 0.0, 1.0),
            max_response_chars=_bounded("MAX_RESPONSE_CHARS", int, 400_000, 10_000, 2_000_000),
            fallback_results=_bounded("FALLBACK_RESULTS", int, 10, 0, 100),
            sweep_hours=_bounded("SWEEP_HOURS", int, 6, 1, 168),
            search_parallelism=_bounded("SEARCH_PARALLELISM", int, 1, 1, 64),
            write_parallelism=_bounded("WRITE_PARALLELISM", int, 2, 1, 64),
            planner_model=os.environ.get("PLANNER_MODEL", "").strip(),
            planner_max_queries=_bounded("PLANNER_MAX_QUERIES", int, 3, 1, 6),
            planner_timeout=_bounded("PLANNER_TIMEOUT", float, 20.0, 1.0, 120.0),
            planner_snippets=_bounded("PLANNER_SNIPPETS", int, 8, 0, 30),
            log_level=os.environ.get("LOG_LEVEL", "INFO").strip().upper() or "INFO",
        )
