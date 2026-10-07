# aml-memory — Agent Memory Leaderboard (AML 记忆之巅) submission

Open-source Methods entry for the Cycle 2 textual-memory track. Deadline: materials by 2026-10-31 23:59 UTC+8; evaluation closes 2026-11-04; results mid-November.

## What this service is
A participant-hosted HTTP service with two endpoints the evaluator calls:
- `POST /v1/memories/add` (alias `/add`): synchronous ingest; return 200 only after the chunk is persisted and searchable; echo `request_id`, `user_id`, `session_id` exactly; replays of the same `request_id` are idempotent, conflicting replays return 409.
- `POST /v1/memories/search` (alias `/search`): `{query, options?, user_id, top_k}` → `{data:[{id, content, score?, created_at?}]}`; never more than `top_k` items; official runs use `top_k=100`.
- `GET /health`: unauthenticated, any 2xx.
Auth: evaluator sends `X-Api-Key`, `Authorization: Bearer`, or `Authorization: Token`. `MEMORY_API_KEY` env enables it; empty disables (local only).

## Hard rules (from the competition docs; violating any = disqualification)
- Search returns evidence only. It must never generate or disguise an answer.
- Strict isolation by `user_id`. Never read across users/samples.
- Open-source division: if any LLM is used inside the system, use `gpt-4o-mini` (the docs say "during Add"; we apply it to Search too, like ReFind did). No other model in the declared configuration.
- Evaluation data: do not log query/memory text, do not train on it, do not analyse it outside the run, delete within 30 days (`RETENTION_DAYS`, swept at startup).
- Public repo + fixed commit hash + attribution of prior work + method card are required at submission.

## Layout
- `app/store.py` SQLite (WAL) + FTS5 index; chunk ordering = `ts` then ordinal parsed from `request_id` (`chunk-N`); `is_rule` tag at Add time.
- `app/search.py` ranking: standing rules first (≤ `RULE_SLOTS`, ≤ top_k/4) → BM25 hits with ±`CONTEXT_WINDOW` neighbours → recency fallback. Content is rendered as `[YYYY-MM-DD HH:MM UTC] ROLE: text` so the shared answer model can reason about time.
- `app/main.py` FastAPI app; `scripts/smoke_test.py` contract smoke; `tests/` pytest.
- `docs/METHOD_CARD.md` (to write) must disclose prior work: FantaSmallhamster/ldbd-sqlite-fts-baseline (FTS5 pattern), imlrz/ReFind (timestamp rendering, context window, session ordering).

## Commands
- `uv sync` · `uv run pytest -q` · `uv run uvicorn app.main:app --port 8000`
- `uv run python scripts/smoke_test.py http://127.0.0.1:8000 [api_key]`
- Docker: `docker compose up -d --build` (reads `.env`; see `.env.example`).

## Conventions
- Python 3.12, type hints, no new dependencies without a reason written in PLAN.md.
- Any ranking change needs a test in `tests/` and a line in `docs/METHOD_CARD.md`.
- Never commit `.env`, keys, or evaluation data. `data/` is git-ignored.
