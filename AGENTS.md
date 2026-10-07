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
- Open-source division: if any LLM is used inside the system, use `gpt-4o-mini` (the docs say "during Add"; we apply it to Search too, like ReFind did); any embedding must be `text-embedding-v4`; rerankers are unrestricted; no self-trained/open-weight models. v0.2 uses no model at all (whether that satisfies "expected to use gpt-4o-mini" is an open question for the organisers).
- Evaluation data: do not log query/memory text, do not train on it, do not analyse it outside the run, delete within 30 days (`RETENTION_DAYS`, swept at startup).
- Public repo + fixed commit hash + attribution of prior work + method card are required at submission. "Undisclosed reuse may be treated as plagiarism": never adapt lines from another entry's code; ideas are fine when attributed in `docs/METHOD_CARD.md` and `NOTICE`.

## Layout
- `app/store.py` one SQLite file per `user_id` under `DATA_DIR/users/ab/cd/<hash>.db` (WAL): `ingest_log` (idempotency by fingerprint), `memories` (one row per turn; `pos` = chunk ordinal × 1000 + index, `event_ms`, `standing` rule tag), FTS5 word index (porter, external content) + FTS5 trigram index (CJK-only turns). Connections cached per file with a lock (LRU 512, idle 120 s). `SCHEMA_VERSION` mismatch fails loudly (no migration; wipe the data dir between versions).
- `app/search.py` evidence assembly: word BM25 (+ trigram BM25 fused by RRF when the query has CJK) → recency band (near-equal scores newest-first) → first `LEAD_HITS` hits, then `RULE_SLOTS` standing rules (query-matching first), then the rest → ±`CONTEXT_WINDOW` spans crossing chunk boundaries, de-duplicated → `MAX_RESPONSE_CHARS` budget → newest-turns fallback. Content rendered as `[YYYY-MM-DD HH:MM UTC] ROLE: text`. The docstring at the top of the file is the authoritative description.
- `app/planner.py` optional v0.3 query planner: one gpt-4o-mini call per Search (question + first 8 snippets → ≤3 extra keyword queries + date range), fused by RRF; never produces answer text; any failure = deterministic fallback. Enabled only by `PLANNER_MODEL=gpt-4o-mini` + `OPENAI_API_KEY`; the LLM call runs outside the SQLite gate.
- `app/main.py` FastAPI factory `create_app()` (run with `uvicorn --factory`); auth; periodic retention sweep; per-process gates `SEARCH_PARALLELISM=1` / `WRITE_PARALLELISM=2` (SQLite mutex contention makes more threads slower; scale with `UVICORN_WORKERS`).
- `evalset/` our own fictional samples + questions (never leaderboard data); `scripts/eval_local.py` prints hit@k / MRR / trap-order / tokens per capability; `scripts/sweep_local.py` grids env knobs. Every ranking change is judged there first.
- `docs/METHOD_CARD.md` (attribution + method changes per version), `docs/SUBMISSION.md` (form fields), `docs/CHECKLIST.md` (the 8-item gate), `NOTICE` (ReFind MIT notice; the rewritten-baseline history). `deploy/` Caddy + prod compose + runbook; `scripts/soak_local.py` load test.

## Commands
- `uv sync` · `uv run pytest -q` · `uv run uvicorn --factory app.main:create_app --port 8000`
- `uv run python scripts/smoke_test.py http://127.0.0.1:8000 [api_key]` · `uv run python scripts/eval_local.py --label <name> -v` · `uv run python scripts/soak_local.py --base http://127.0.0.1:8000`
- Docker: `docker compose up -d --build` (reads `.env`; see `.env.example`).

## Conventions
- Python 3.12, type hints, no new dependencies without a reason written in PLAN.md.
- Any ranking change needs a test in `tests/`, a before/after line from `scripts/eval_local.py`, and a line in `docs/METHOD_CARD.md`.
- Never commit `.env`, keys, or evaluation data. `data/` is git-ignored.
