# aml-memory

A small, fully deterministic memory service for the [Agent Memory Leaderboard](https://agentmemoryleaderboard.ai/) Add/Search contract (Cycle 2, textual track, open-source division).

Raw conversation turns go into SQLite FTS5 (porter-stemmed words, plus character trigrams for CJK text). Search returns BM25 hits with the two turns around each, rendered with UTC timestamps and roles; near-equal hits are ordered newest-first so an overwritten value never outranks its replacement, and the user's standing rules and preferences ride along. No LLM, no embeddings.

See `AGENTS.md` for the contract and rules, `PLAN.md` for the roadmap and status, `docs/METHOD_CARD.md` for attribution and the change log, `evalset/README.md` for the local evaluation set.

```bash
uv sync && uv run pytest -q
uv run python scripts/eval_local.py --label dev -v      # local mini-set, per-capability table
uv run uvicorn --factory app.main:create_app --port 8000
uv run python scripts/smoke_test.py http://127.0.0.1:8000
```

Docker: `cp .env.example .env`, set `MEMORY_API_KEY`, then `docker compose up -d --build` (binds 127.0.0.1:8000; put a TLS proxy in front).

License: MIT. Prior work is credited in `NOTICE` and `docs/METHOD_CARD.md`.
