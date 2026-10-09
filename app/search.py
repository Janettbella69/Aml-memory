"""Search = evidence assembly. No generation anywhere: every returned string is conversation text
rendered with its timestamp and role.

Pipeline (v0.2):
  1. word index  : porter-stemmed BM25 over the query + answer options (Latin-script terms)
  2. trigram index: BM25 over CJK character trigrams, fused with (1) by reciprocal rank fusion
  3. recency band: hits whose score is within RECENCY_BAND of each other are ordered newest-first,
                   so a value that was later overwritten does not outrank its replacement
  4. standing rules: the user's tagged instructions/preferences, query-matching ones first, then newest,
                   placed after the first LEAD_HITS results
  5. spans      : each returned hit carries CONTEXT_WINDOW turns before/after it (crossing Add chunks);
                   a hit already visible inside an earlier span is skipped
  6. fallback   : nothing matched -> the newest FALLBACK_RESULTS turns
  7. budget     : stop at top_k results or MAX_RESPONSE_CHARS characters
v0.4: turns are rendered with resolved relative-time notes (app/timex.py, TIME_NOTES) and answer options enter
retrieval per OPTIONS_MODE (append | none | channel with OPTIONS_WEIGHT).
"""
from __future__ import annotations

import re

from contextlib import nullcontext
from typing import ContextManager, Optional

from .config import Settings
from .models import MemoryResult
from .planner import Plan, Planner
from .store import Chunk, MemoryStore, cjk_only, render

WORD_RE = re.compile(r"\w+", re.UNICODE)
CJK_CHAR = re.compile(r"[぀-ヿ㐀-䶿一-鿿가-힯]")
# Function words that carry no retrieval signal in English questions. Own list; alphabetical.
STOPWORDS = frozenset("""
a about after again against all also am an and any are as at be because been before being between both but by can
could did do does doing done down during each few for from further had has have having he her here hers herself him
himself his how however i if in into is it its itself just let may me might more most much must my myself no nor not
now of off on once only or other our ours ourselves out over own same she should so some still such than that the
their theirs them themselves then there these they this those through to too under until up us very was we were what
when where whether which while who whom why will with would yes yet you your yours yourself yourselves
""".split())
PREFIX_MIN = 5   # terms at least this long also match as prefixes ("illustrat"* covers what the stemmer misses)
RRF_K = 60


def word_terms(query: str, options: list[str] | None) -> list[str]:
    terms: list[str] = []
    for text in (query, *(options or ())):
        for raw in WORD_RE.findall(text.lower()):
            tok = raw.strip("_")
            if len(tok) < 2 or tok in STOPWORDS or CJK_CHAR.search(tok) or tok in terms:
                continue
            terms.append(tok)
    return terms


def cjk_terms(query: str, options: list[str] | None) -> list[str]:
    """Overlapping character trigrams of the CJK text (same normalisation as the index)."""
    grams: list[str] = []
    for text in (query, *(options or ())):
        run = cjk_only(text)
        for i in range(len(run) - 2):
            g = run[i:i + 3]
            if g not in grams:
                grams.append(g)
    return grams


def fts_expression(terms: list[str], prefixes: bool = True) -> str:
    """FTS5 MATCH expression: quoted terms joined by OR so BM25 can rank partial matches."""
    parts = []
    for t in terms:
        quoted = '"' + t.replace('"', '""') + '"'
        parts.append(quoted + "*" if prefixes and len(t) >= PREFIX_MIN else quoted)
    return " OR ".join(parts)


def fuse(primary: list[tuple[Chunk, float]], secondary: list[tuple[Chunk, float]],
         weight: float = 1.0) -> list[tuple[Chunk, float]]:
    """Reciprocal rank fusion (the secondary list's contributions scaled by `weight`); a no-op when only one list has hits."""
    if not secondary:
        return primary
    if not primary:
        return secondary
    score: dict[str, float] = {}
    seen: dict[str, Chunk] = {}
    for ranked, w in ((primary, 1.0), (secondary, weight)):
        for position, (chunk, _) in enumerate(ranked, start=1):
            score[chunk.id] = score.get(chunk.id, 0.0) + w / (RRF_K + position)
            seen[chunk.id] = chunk
    return sorted(((seen[i], s) for i, s in score.items()), key=lambda pair: -pair[1])


def newest_first_within_band(hits: list[tuple[Chunk, float]], band: float) -> list[tuple[Chunk, float]]:
    """Group hits into bands of near-equal normalised score; inside a band the newer memory comes first."""
    if len(hits) < 2 or band <= 0:
        return hits
    top = hits[0][1] or 1.0

    def key(pair: tuple[Chunk, float]) -> tuple[int, int, int]:
        chunk, s = pair
        return (-int(round((s / top) / band)), -chunk.order_key[0], -chunk.order_key[1])

    return sorted(hits, key=key)


def search(store: MemoryStore, settings: Settings, query: str, options: list[str] | None,
           user_id: str, top_k: int, planner: Optional[Planner] = None,
           gate: Optional[ContextManager] = None) -> list[MemoryResult]:
    """Two gated SQLite passes around one optional planner call (network time must not hold the gate)."""
    gate = gate or nullcontext()
    with gate, store.connect(user_id, create=False) as conn:   # one connection per Search; None = unknown user
        if conn is None:
            return []
        hits = _first_pass(store, conn, settings, query, options, user_id, top_k)
        if planner is None:
            return _assemble(store, conn, settings, query, options, user_id, top_k, hits)
        snippets = [render(c, settings.time_notes)[:400] for c, _ in hits[:settings.planner_snippets]]
    plan = planner.plan(query, options, snippets)          # outside the gate
    with gate, store.connect(user_id, create=False) as conn:
        if conn is None:
            return []
        if plan is not None and (plan.queries or plan.has_dates):
            hits = _expand(store, conn, settings, user_id, top_k, query, options, hits, plan)
        if plan is not None and plan.has_dates:
            hits = _prefer_dates(hits, plan)
        return _assemble(store, conn, settings, query, options, user_id, top_k, hits)


def _first_pass(store: MemoryStore, conn, settings: Settings, query: str, options: list[str] | None,
                user_id: str, top_k: int) -> list[tuple[Chunk, float]]:
    pool = top_k * 2
    opts = options if settings.options_mode == "append" else None
    by_words = store.fts_search(user_id, fts_expression(word_terms(query, opts)), pool, conn)
    by_trigrams = store.trigram_search(user_id, fts_expression(cjk_terms(query, opts), prefixes=False), pool, conn)
    hits = fuse(by_words, by_trigrams)
    if settings.options_mode == "channel" and options:
        # v0.4: the options as their own channel (idea: Hybrid Episodic Memory, Cycle-1 #6), so the question's terms
        # keep the lead and a distractor option alone cannot outrank evidence for the question itself
        o_words = word_terms("", options)
        o_grams = cjk_terms("", options)
        by_opts = fuse(store.fts_search(user_id, fts_expression(o_words), pool, conn) if o_words else [],
                       store.trigram_search(user_id, fts_expression(o_grams, prefixes=False), pool, conn) if o_grams else [])
        hits = fuse(hits, by_opts, weight=settings.options_weight)
    return newest_first_within_band(hits, settings.recency_band)


def _expand(store: MemoryStore, conn, settings: Settings, user_id: str, top_k: int, query: str,
            options: list[str] | None, hits: list[tuple[Chunk, float]], plan: Plan) -> list[tuple[Chunk, float]]:
    """Fold the planner's extra queries (and, with a date range, date-restricted searches of every query)
    into the first pass by reciprocal rank fusion, first pass first."""
    pool = top_k * 2
    fused = hits
    rng = (plan.date_from_ms, plan.date_to_ms) if plan.has_dates else None
    queries: list[tuple[str, list[str] | None]] = [(extra, None) for extra in plan.queries]
    if rng is not None:
        opts = options if settings.options_mode == "append" else None
        queries = [(query, opts)] + queries   # the original question, restricted to the period
    for text, opts in queries:
        words = fts_expression(word_terms(text, opts))
        grams = fts_expression(cjk_terms(text, opts), prefixes=False)
        more = fuse(store.fts_search(user_id, words, pool, conn), store.trigram_search(user_id, grams, pool, conn))
        if rng is not None:
            ranged = fuse(store.fts_search(user_id, words, pool, conn, rng), store.trigram_search(user_id, grams, pool, conn, rng))
            more = fuse(ranged, more)
        fused = fuse(fused, more)
    return newest_first_within_band(fused, settings.recency_band)


def _prefer_dates(hits: list[tuple[Chunk, float]], plan: Plan) -> list[tuple[Chunk, float]]:
    """Hits inside the planner's date range come first, each group keeping its order."""
    inside = [h for h in hits if plan.in_range(h[0].event_ms)]
    outside = [h for h in hits if not plan.in_range(h[0].event_ms)]
    return inside + outside


def _assemble(store: MemoryStore, conn, settings: Settings, query: str, options: list[str] | None,
              user_id: str, top_k: int, hits: list[tuple[Chunk, float]]) -> list[MemoryResult]:
    top_score = hits[0][1] if hits else 1.0
    score_of = {chunk.id: s for chunk, s in hits}

    rule_budget = min(settings.rule_slots, top_k // 4)
    rules = store.standing_rules(user_id, rule_budget * 4, conn) if rule_budget > 0 else []
    rules.sort(key=lambda c: (-score_of.get(c.id, 0.0), -c.order_key[0], -c.order_key[1]))
    rules = rules[:rule_budget]

    queue: list[tuple[Chunk, float]] = []
    queued: set[str] = set()

    def enqueue(chunk: Chunk, s: float) -> None:
        if chunk.id not in queued:
            queued.add(chunk.id)
            queue.append((chunk, s))

    for chunk, s in hits[:settings.lead_hits]:
        enqueue(chunk, s)
    for chunk in rules:
        enqueue(chunk, score_of.get(chunk.id, top_score))
    for chunk, s in hits[settings.lead_hits:]:
        enqueue(chunk, s)
    if not hits:
        for chunk in store.newest(user_id, settings.fallback_results, conn):
            enqueue(chunk, 0.0)

    results: list[MemoryResult] = []
    visible: set[int] = set()   # positions already shown inside an earlier span
    used = 0
    for chunk, s in queue:
        if len(results) >= top_k or used >= settings.max_response_chars:
            break
        if chunk.pos in visible and not chunk.standing:
            continue
        turns = store.span(chunk, settings.context_window, conn) if s > 0 or chunk.standing else [chunk]
        visible.update(t.pos for t in turns)
        text = "\n".join(render(t, settings.time_notes) for t in turns)
        used += len(text)
        results.append(MemoryResult(id=chunk.id, content=text, created_at=chunk.stored_at,
                                    score=round(min(s / top_score, 1.0), 4) if top_score else None))
    return results
