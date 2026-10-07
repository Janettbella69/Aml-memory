from __future__ import annotations

import re
from collections import OrderedDict

from .config import Settings
from .models import MemoryResult
from .store import Chunk, MemoryStore, render

TOKEN_RE = re.compile(r"[^\W_]+", re.UNICODE)
STOP = set(
    "a an and are as at be by did do does for from had has have he her his how i in is it its of on or she "
    "that the their them they this to was were what when where which who why with you your me my we our us "
    "about did does not no yes can could would should will just so than then there these those into over "
    "under up down out if but also any some all one two three".split()
)


def terms_for(query: str, options: list[str] | None) -> list[str]:
    seen: OrderedDict[str, None] = OrderedDict()
    for text in [query, *(options or [])]:
        for tok in TOKEN_RE.findall(text.lower()):
            if len(tok) < 2 or tok in STOP:
                continue
            seen.setdefault(tok, None)
    return list(seen)


def match_expr(terms: list[str]) -> str:
    # FTS5: quote each term; OR lets BM25 rank partial matches; prefix match helps inflections.
    parts = []
    for t in terms:
        safe = t.replace('"', '""')
        parts.append(f'"{safe}"*' if len(safe) >= 4 else f'"{safe}"')
    return " OR ".join(parts)


def _block(chunks: list[Chunk]) -> str:
    return "\n".join(render(c) for c in chunks)


def search(store: MemoryStore, settings: Settings, query: str, options: list[str] | None,
           user_id: str, top_k: int) -> list[MemoryResult]:
    results: OrderedDict[str, MemoryResult] = OrderedDict()

    # 1. Standing rules / preferences always ride along (bounded by RULE_SLOTS and top_k).
    rule_budget = min(settings.rule_slots, max(0, top_k // 4))
    for chunk in store.rules(user_id, rule_budget):
        results[chunk.id] = MemoryResult(id=chunk.id, content=render(chunk), score=1.0, created_at=chunk.created_at)

    # 2. BM25 hits, each expanded with its neighbours so the answer model sees the exchange.
    hits = store.fts_search(user_id, match_expr(terms_for(query, options)), limit=top_k * 2)
    best = hits[0][1] if hits else 1.0
    for chunk, score in hits:
        if len(results) >= top_k:
            break
        if chunk.id in results:
            continue
        ctx = store.neighbors(chunk, settings.context_window)
        results[chunk.id] = MemoryResult(
            id=chunk.id, content=_block(ctx), score=round(score / best, 4) if best else None,
            created_at=chunk.created_at,
        )

    # 3. Nothing matched: return the most recent memories rather than an empty list.
    if not hits:
        for chunk in store.latest(user_id, min(settings.fallback_results, top_k)):
            if chunk.id not in results and len(results) < top_k:
                results[chunk.id] = MemoryResult(id=chunk.id, content=render(chunk), score=0.0, created_at=chunk.created_at)

    return list(results.values())[:top_k]
