# aml-memory — method card

Entry for the Agent Memory Leaderboard (AML) Cycle 2, Textual Memory track, Open-source Methods division.
This is the disclosure the platform requires for reused work: original authors, technical report, and every method change.
Describes code version **0.2.0** (2026-10-07). Repository facts about prior work were checked on 2026-10-07 (repository pages, GitHub REST API, LICENSE files, arXiv).

## System overview

aml-memory is a fully deterministic retrieval service. Add stores every incoming turn as raw text in SQLite (one database file per `user_id`) and indexes it twice: a porter-stemmed FTS5 word index, and a character-trigram FTS5 index that only receives turns containing CJK text. Search turns the question (plus any multiple-choice options) into OR-joined FTS5 queries, ranks turns with BM25 (reciprocal-rank fusion when both indexes fire), orders near-equal hits newest-first, places the user's standing rules and preferences after the first few hits, expands each hit with the two turns before and after it, renders every turn as `[YYYY-MM-DD HH:MM UTC] ROLE: text`, de-duplicates turns already shown, and stops at `top_k` results or ~100k tokens. Nothing matched → the newest turns. There is no LLM, embedding model or reranker; the same input always produces the same output. Search returns evidence only and never generates or paraphrases an answer.

## Add pipeline (`POST /v1/memories/add`, alias `/add`)

1. Validate the body (`request_id`, `messages[≥1]`, `user_id`, `session_id`; unknown fields ignored; blank identifiers → 422).
2. Fingerprint the canonical JSON of the body (SHA-256, sorted keys). `INSERT OR IGNORE` the `request_id` into `ingest_log`: a replay with the same fingerprint returns 200 without writing; the same `request_id` with a different fingerprint returns 409. The insert takes SQLite's write lock, so concurrent replays serialise correctly.
3. Position inside the conversation: `pos = 1000 × N + message_index`, `N` = ordinal parsed from `request_id` (`chunk-N`, also `part|seg|msg`). Without an ordinal, the next free block of that `(user_id, session_id)` is used.
4. For each message: flatten the content to text (strings as-is; multimodal `text` parts concatenated, `image_url` parts dropped); skip empty text; `id = "mem_" + blake2b(request_id ␟ index)`; `standing = 1` when the role is `user` and the text matches the standing-rule patterns (English: `from now on`, `whenever`, `please always/never/don't …`, `don't/never/always/only + assistant-facing verb`, `remember that/to`, `call me`, `I prefer`, `my rule`, `new/ground/format rule`, `forget what/the …`, `must be/use/…`, `no longer`, `remind me`, allergy/dietary words; Chinese: 以后/今后/别再/不要/一定要/记住/规则/只做/过敏/素食/叫我/忘掉 …).
5. Insert into `memories` (role, text, `event_ms` = message timestamp if supplied, `pos`, `standing`, `stored_at`), into the word index (`porter unicode61 remove_diacritics 2`, an external-content FTS5 table so the text is stored once), and — only when the text contains CJK characters — into the trigram index, as the CJK-only string (punctuation, spaces and Latin tokens removed so trigrams span them). All of this lives in the user's own database file `<DATA_DIR>/users/ab/cd/<blake2b(user_id)>.db`, so a query can only ever see one user's turns.
6. Commit (SQLite WAL, `synchronous=NORMAL`, 30 s busy timeout) and only then return `{"success": true, request_id, user_id, session_id}` echoed byte-for-byte.

## Search pipeline (`POST /v1/memories/search`, alias `/search`)

Input `{query, options?, user_id, top_k}` (`top_k` 1–1000, default 100). Output `{"data": [{id, content, score, created_at}]}` in rank order, never more than `top_k` items.

1. **Word hits.** Terms = `\w+` tokens of `query` + `options`, lower-cased, ≥ 2 characters, stop list removed (our own 120-word list), CJK tokens excluded, de-duplicated in order. Terms of ≥ 5 characters also match as prefixes (`"term"*`); all OR-joined so partial matches still rank. FTS5 `bm25()` with weight 0 on `utok`, 1 on `content`; limit `2 × top_k`.
2. **Trigram hits.** Overlapping character trigrams of the CJK-only text of `query` + `options`, OR-joined, against the trigram index. When both lists are non-empty they are fused by reciprocal rank fusion (k = 60); otherwise the non-empty one is used.
3. **Recency band.** Scores are normalised to the best hit. Hits are grouped into bands of width `RECENCY_BAND` (0.2); inside a band the newer memory (`event_ms`, then `pos`) comes first. Purpose: a value that was later overwritten must not outrank its replacement merely because the older sentence is shorter.
4. **Standing rules.** The user's newest `standing` turns (up to 4 × the budget) are sorted by "also a hit for this query" first, then newest; the first `min(RULE_SLOTS=6, top_k // 4)` are kept.
5. **Order.** The first `LEAD_HITS=5` hits, then the rules, then the remaining hits. No hits at all → the newest `FALLBACK_RESULTS=10` turns with `score = 0`.
6. **Assembly.** Walk the ordered list; skip a hit whose turn is already visible inside an earlier block (rules are never skipped); each hit and each rule becomes a block of its `±CONTEXT_WINDOW=2` neighbouring turns in conversation order (`pos`, crossing Add-chunk boundaries), one rendered turn per line; fallback turns are returned alone. Stop at `top_k` results or `MAX_RESPONSE_CHARS=400 000` characters (≈ 100 k tokens; the platform keeps a 117 760-token prefix in rank order). `score` = normalised BM25 (4 dp; rules without a hit score get 1.0); `created_at` = storage time; a malformed MATCH expression is treated as "no hits"; an unknown `user_id` yields `[]`.

Rendering: `[2024-01-01 00:00 UTC] USER: I adopted a cat named Luna.`; the stamp is omitted when the message has no valid timestamp.

## Models used

- **0.2 (default configuration): none.** No LLM, no embedding model, no reranker. Add and Search are pure SQLite/FTS5 code paths.
- **0.3 (optional, off unless `PLANNER_MODEL=gpt-4o-mini` is set):** one `gpt-4o-mini` chat call per Search, temperature 0, JSON output, ≤ 200 output tokens. Input: the question (and options) plus the first 8 first-pass results truncated to 400 characters each. Output: up to 3 extra keyword queries and an optional date range. The extra queries are run through the same BM25 indexes and fused by reciprocal rank fusion; in-range hits are moved ahead when a date range is given. The model's text is never returned to the caller; on timeout (20 s) or any error the deterministic result is returned. The submitted configuration runs with it ON (`PLANNER_MODEL=gpt-4o-mini`); the frozen `.env` values are listed under 1.0.
- Platform rule, verbatim from the Full-evaluation checklist (2026-10-07): "Open-source Methods entries are expected to use gpt-4o-mini during Add. Commercial Products entries have no Add/Search model restriction." The competition FAQ (Chinese) adds: embedding models on the open-source board must be `text-embedding-v4`, LLM components must be `gpt-4o-mini`, rerankers are unrestricted, and systems using self-trained or other open-weight models are directed to the commercial board.
- Commitment: if a later version adds any model call it will be `gpt-4o-mini` only (Add and/or Search); any embedding would be `text-embedding-v4` only. The declared configuration will name every model used; "no model" is declared explicitly for 0.2.

## Prior work and attribution

### 1. `FantaSmallhamster/ldbd-sqlite-fts-baseline` — https://github.com/FantaSmallhamster/ldbd-sqlite-fts-baseline

- **Exists:** yes, public. Created 2026-07-29, default branch `main`, 0 stars. Description: "Minimal LDBD-compatible memory baseline using FastAPI, SQLite FTS5, and BM25." Author: GitHub user FantaSmallhamster. README (Chinese) says it is the author's own process-validation baseline and that the README is its technical report.
- **License:** none. No LICENSE file (`main/LICENSE` → 404, GitHub license API → 404, repository `license: null`), no license statement in the README. Under default copyright this grants no permission to copy, modify or redistribute its code.
- **What it is:** one FastAPI file (`app/main.py`, ~570 lines): SQLite WAL persistence, FTS5/BM25 over raw messages, `request_id` idempotency via a payload hash (409 on conflict), `user_id` scoping, `X-Api-Key` auth, no message-body logging, a recency fallback when no lexical match exists, single-worker Docker deployment.
- **Idea borrowed:** the pattern "store raw turns in SQLite FTS5, return BM25 hits, fall back to the newest turns". That is all that remains of it in 0.2.
- **History, disclosed:** our first draft (0.1.0, commit `f09d825`, 2026-10-07) contained roughly 30 non-trivial lines adapted from that file (pydantic validators and their error strings, the environment-variable parser, the `add_requests` table, the FTS tokenizer line, the query tokenizer and the first 47 stop words in the same order, the `.env.example` placeholder). Found while writing this card on the same day. In 0.2.0 `app/models.py`, `app/config.py`, `app/store.py`, `app/search.py` and `app/main.py` were rewritten from scratch (different table and column names, insert-first idempotency, our own validators, stop list, env parser, placeholder and smoke flow); a line-level re-comparison after the rewrite (every stripped line longer than 20 characters) found no shared lines apart from names dictated by the API contract (`AddRequest`, `SearchResponse`, `request_id TEXT NOT NULL`, …) and standard idioms (`@dataclass(frozen=True)`, `def initialize(self)`). The 0.1 commit stays in the history for transparency and is not the submitted code.

### 2. `imlrz/ReFind` — https://github.com/imlrz/ReFind

- **Exists:** yes, public. Created 2026-08-07, last push 2026-08-14, 16 stars. README states it ranked #2 on the Cycle-1 Academic Textual board with 44.97.
- **License:** MIT — "Copyright (c) 2026 ReFind Authors". Notice recorded in `NOTICE`; no ReFind source files are included here.
- **Technical report:** Ruizhe Li, Licheng Zhang, Benfeng Xu, Mingxuan Du, Zheren Fu, Weidong Chen. "When Your Agent Opens the Chat App: Agent-Controlled Search over Raw Chat Logs Rivals Structured Memory." arXiv:2608.12888 (v1 2026-08-13). The repository's own method card cites an earlier manuscript title and author list; we cite the arXiv version.
- **What it is:** an agentic retriever. Raw Add chunks in SQLite; turns ordered by source timestamp then by the `request_id` ordinal and paired into adjacent-turn records; BM25 (k1 = 1.2, b = 0.75, Porter stemming, stop words) with reciprocal rank fusion (k = 60) of conversation-level and session-level rankings; a GPT-4o-mini planner issues up to four search / note / finish actions and may apply date filters; each result is expanded with two neighbouring chunks on either side; only ordered evidence is returned.
- **Ideas we borrowed:** (a) rendering each turn with its UTC timestamp and upper-cased role (`[stamp] ROLE: text`; we use `YYYY-MM-DD HH:MM UTC`); (b) returning the neighbouring turns of a hit as a context window (±2, as in ReFind); (c) ordering turns by the `chunk-N` ordinal parsed from `request_id`, with timestamps for recency; (d) Porter stemming for BM25; (e) reciprocal rank fusion with k = 60 — applied here across the word and trigram indexes rather than across conversation/session levels; (f) the general shape of the service: a `create_app` factory with a retention sweep in the FastAPI lifespan, a conflict error mapped to 409, `/v1/memories/*` with `/add` and `/search` aliases, `RETENTION_DAYS` capped at 30, a smoke script, and the method-card + submission-sheet pair of documents.
- **Not adopted:** the GPT-4o-mini planner loop and note-taking, date filtering, adjacent-turn pairing, session-level RRF, seen-chunk filtering across planner steps.

### 3. Platform contract (not prior work)

Synchronous Add with exact ID echo, idempotent `request_id`, `user_id` isolation, unauthenticated `GET /health`, and the `X-Api-Key` / `Bearer` / `Token` schemes are requirements of the official API guide; both repositories above and this one implement them independently.

### 4. Other entries consulted

Opened on 2026-10-07 (GitHub README and metadata) while writing this card; nothing here is taken from them.

1. https://github.com/rickywesker/AgentMEM — Postgres; verbatim turn rows plus extracted fact rows that resolve back to their source turn; BM25 + cosine + time fused with RRF. No license file.
2. https://github.com/madao2588/624agent — FTS5/BM25 with CJK bigrams, source-backed facets, event-state governance, preference/rule channels, bounded three-hop relations; optional embedding RRF. MIT.
3. https://github.com/richrichgo/aml-memory-baseline — SQLite FTS5 BM25 fused with query-term coverage, exact match and mild time weighting; CJK n-grams; options join recall. Custom license.
4. https://github.com/haowenGuo/ailis-agent-memory-challenge — Node.js "lossless lexical" memory with no model calls; declares "no model" and notes the same gpt-4o-mini ambiguity. MIT.
5. https://github.com/wenxiaof345-ctrl/vanilla-rag-memory — vector RAG baseline (bge-small embeddings, SQLite-persisted vectors). No license file.

## Method changes by version

Numbers are from our own written mini-set (`evalset/`, fictional conversations, 7 capability groups; never leaderboard data), retrieval-only metrics at `top_k = 100`.

- **0.1 (2026-10-07, commit `f09d825`).** Plain FTS5/BM25 over raw turns plus: `is_rule` tagging at Add; in-conversation ordering from the `request_id` ordinal; user scoping inside the FTS table; prefix matching from 4 characters; 8 newest rules prepended with score 1.0; ±1 neighbour context; timestamp/role rendering; recency fallback; multimodal parts flattened; three auth schemes; retention sweep at start. 65 questions: hit@10 0.78, hit@100 0.97, MRR 0.20, trap-order 0.17.
- **0.2 (2026-10-07).** Rewritten (see §1 above) and re-ranked:
  - Porter-stemmed word index (`targeting` now finds `target`); prefix matching from 5 characters.
  - Character-trigram index for CJK turns (unicode61 cannot segment Chinese), fused by RRF; Chinese standing-rule patterns.
  - Recency band 0.2: newest-first among near-equal scores ("latest value wins"). Rules relevance-sorted and placed after the first 5 hits instead of before everything; budget 6 instead of 8; tighter rule patterns (assistant-facing verbs; "he always does" is no longer a rule).
  - Context ±2 crossing Add-chunk boundaries; blocks de-duplicated (a hit already visible in an earlier block is skipped); `MAX_RESPONSE_CHARS` cap.
  - One SQLite file per `user_id` (physical isolation; query cost independent of the corpus size), cached connections with per-file locks, per-process search/write gates, external-content word index, WAL size limits and idle eviction; insert-first idempotency; CJK-only trigram index (English corpora pay nothing for it); periodic retention sweep every 6 h in addition to start-up; uvicorn factory mode (no import-time side effects); Docker image installs from `uv.lock`.
  - Chosen by `scripts/sweep_local.py` over `RECENCY_BAND ∈ {0, .1, .2, .3, .5} × LEAD_HITS ∈ {3, 5} × RULE_SLOTS ∈ {4, 6, 8} × CONTEXT_WINDOW ∈ {1, 2}`.
  - 71 questions (65 + a Chinese sample): hit@10 0.92, hit@100 1.00, MRR 0.72, trap-order 0.85, ≈ 2.1 k tokens per response. Remaining misses: a two-hop question with no lexical overlap between hops (`lt-co-03`), and a stance change where the older statement is shorter (`lt-te-02`).
  - Tests: 21 (`tests/test_api.py`, `tests/test_search_v02.py`, `tests/test_evalset.py`).
- **0.3 (2026-10-07, implemented, default off).** `app/planner.py`: one-step gpt-4o-mini query planner (see "Models used"), after ReFind's agent-controlled search idea but reduced to a single bounded step with a deterministic fallback; `scripts/judge_local.py`: end-to-end proxy scoring (gpt-4o-mini answers from our Search output, gpt-4o-mini grades against the reference). Decision to enable it at freeze depends on the judge comparison on our own set (TODO: needs a working API key; the one in the environment returned 401 on 2026-10-07). Tests: `tests/test_planner.py` (fake planner).
- **1.0 (freeze, by 2026-10-28).** Tag, fixed commit hash, final declared configuration (`RETENTION_DAYS=30 CONTEXT_WINDOW=2 RULE_SLOTS=6 LEAD_HITS=5 RECENCY_BAND=0.2 MAX_RESPONSE_CHARS=400000 FALLBACK_RESULTS=10 UVICORN_WORKERS=2 SEARCH_PARALLELISM=1 WRITE_PARALLELISM=2` unless changed above).

## Data handling

- No query or memory text in logs: Add logs nothing per request; Search logs the result count and `top_k` only; uvicorn access logs carry path and status only.
- Strict isolation is physical: each `user_id` has its own SQLite file; a Search opens the file of the `user_id` it was given and nothing else, and an unknown `user_id` creates no file and returns `[]`. `session_id` is only used to find neighbours. Covered by `test_user_isolation` and `test_users_live_in_separate_files`.
- Retention: `RETENTION_DAYS` (1–30, default 30). `delete_expired()` runs at process start and every `SWEEP_HOURS` (6) while the service is up and deletes every user database whose last write is older than the window. After the Full run the operator additionally deletes the volume (`docker compose down -v`) — platform rule: delete within 30 days after job completion.
- Evaluation data is used only to serve the run: no training, no fine-tuning, no analysis outside the job, no redistribution. Local tuning uses our own written mini-set under `evalset/`.
- Secrets: `MEMORY_API_KEY` comes from the environment (`.env`, git-ignored); nothing is committed.

## Capacity declaration

- Add concurrency: 16. Search concurrency: 16. `top_k`: 1–1000 (outside → 422); official runs use 100.
- Add is synchronous: the turns are committed to the user's SQLite file (WAL) and indexed before the 200 is returned; idempotent replay is safe; concurrent replays serialise on the `ingest_log` insert.
- Deployment: `UVICORN_WORKERS` (default 2) uvicorn processes; inside each process a gate allows `SEARCH_PARALLELISM=1` search and `WRITE_PARALLELISM=2` Add transactions at a time (SQLite serialises allocations behind one process-wide mutex, so more threads per process only add contention); connections are cached per user file (LRU 512, closed after 120 s idle, which also checkpoints and removes the WAL). Docker image from `ghcr.io/astral-sh/uv:python3.12-bookworm-slim` with dependencies installed from `uv.lock`; volume `/data`; health check every 30 s; the production compose file in `deploy/` runs Caddy for TLS.
- Measured on 2026-10-07 (Apple M-series laptop, synthetic Zipf text, 300 users × 600 turns, 16 concurrent clients, `scripts/soak_local.py` + ApacheBench): one worker — Add 1,313 calls/s (p50 12 ms, p99 21 ms), Search 293 q/s (p50 53 ms, p99 60 ms, 135 k-character responses at `top_k=100`); the same server with 16 searches allowed per process managed 24 q/s at 412 % CPU, which is why the gate exists. A single search on a 2,000-turn user costs 5 ms end-to-end over HTTP. With the default two workers: Add 2,290 calls/s (p50 7 ms, p99 12 ms), Search 497 q/s (p50 28 ms, p99 39 ms).
- Timeouts: no server-side request timeout; the platform allows up to 30 minutes per request. Proxy timeout should be ≥ 60 s (the Caddyfile sets 1800 s).
- Storage: the official site states the Textual track spans ≈ 300 M tokens (~1.2 GB of text). Measured: 38 MB of synthetic text → 184 MB on disk at rest (memories table + porter index + per-file overhead), i.e. ≈ 5×, so ≈ 6 GB for the whole track plus ≤ 4 MB of WAL per active user. Budget ≥ 20 GB of disk. TODO before freeze: repeat the soak on the deployed VPS and record p50/p99 here.

## Reproduction

```bash
uv sync
uv run pytest -q                                   # 21 passed
uv run python scripts/eval_local.py --label v0.2   # local mini-set, prints the per-capability table
uv run uvicorn --factory app.main:create_app --port 8000
uv run python scripts/smoke_test.py http://127.0.0.1:8000 [api_key]
cp .env.example .env                               # set MEMORY_API_KEY (>= 16 chars)
docker compose up -d --build                       # 127.0.0.1:8000; TLS proxy in front
```

- Python ≥ 3.12; dependencies pinned in `uv.lock` (fastapi, uvicorn[standard], pydantic; dev: pytest, httpx) and installed from the lock in Docker. Load test: `uv run python scripts/soak_local.py --base <url> --api-key <key> --users 300 --chunks 30`.
- Fixed commit hash: **TBD at freeze**. The frozen commit, the `v1.0` tag and the declared environment values above are what the platform binds.
