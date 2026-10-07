from __future__ import annotations

import os
from dataclasses import dataclass


def _int_env(name: str, default: int, lo: int, hi: int) -> int:
    raw = os.environ.get(name, str(default))
    try:
        value = int(raw)
    except ValueError as exc:
        raise RuntimeError(f"{name} must be an integer") from exc
    if not lo <= value <= hi:
        raise RuntimeError(f"{name} must be between {lo} and {hi}")
    return value


@dataclass(frozen=True)
class Settings:
    api_key: str = ""
    database_path: str = "data/memory.db"
    retention_days: int = 30
    context_window: int = 1
    rule_slots: int = 8
    fallback_results: int = 10
    log_level: str = "INFO"

    @classmethod
    def from_env(cls) -> "Settings":
        api_key = os.environ.get("MEMORY_API_KEY", "")
        if api_key and (len(api_key) < 16 or api_key.startswith("replace-with")):
            raise RuntimeError("MEMORY_API_KEY must be >= 16 chars and not the placeholder")
        return cls(
            api_key=api_key,
            database_path=os.environ.get("DATABASE_PATH", "data/memory.db"),
            retention_days=_int_env("RETENTION_DAYS", 30, 1, 30),
            context_window=_int_env("CONTEXT_WINDOW", 1, 0, 5),
            rule_slots=_int_env("RULE_SLOTS", 8, 0, 50),
            fallback_results=_int_env("FALLBACK_RESULTS", 10, 0, 100),
            log_level=os.environ.get("LOG_LEVEL", "INFO").upper(),
        )
