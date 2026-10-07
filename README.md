# aml-memory

A small, fully deterministic memory service for the [Agent Memory Leaderboard](https://agentmemoryleaderboard.ai/) Add/Search contract.
Raw conversation chunks go into SQLite FTS5; Search returns BM25 hits with their neighbouring turns, rendered with UTC timestamps, plus the user's standing rules and preferences.

See `AGENTS.md` for the contract and rules, `PLAN.md` for the roadmap.

```bash
uv sync && uv run pytest -q
uv run uvicorn app.main:app --port 8000
uv run python scripts/smoke_test.py http://127.0.0.1:8000
```
