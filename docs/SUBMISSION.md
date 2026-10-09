# Submission sheet — AML Cycle 2 (Textual, Open-source Methods)

Fill-in sheet mirroring the official evaluation-access form and the Create Eval Job form (field names checked against agentmemoryleaderboard.ai on 2026-10-07). `TBD` = not decided yet. Keep issued keys and personal contact details out of this file; enter them only in the form.

## Evaluation access request

| Field | Value |
|---|---|
| System name | `aml-memory` |
| Version | TBD — `v1.0` at freeze (code is `0.3.0` today) |
| Contact details | TBD (enter in the form only; do not commit) |
| Organization or team | TBD |
| Intended evaluation type | Textual Memory track · Open-source Methods division |
| Method or product description | Deterministic retrieval service for the AML Add/Search contract. Raw conversation turns are stored in SQLite and indexed with FTS5 (porter-stemmed words, plus character trigrams for CJK text); Search ranks them with BM25 over the question and its options, orders near-equal hits newest-first so overwritten values do not outrank their replacements, places the user's standing rules after the leading hits, expands each hit with the two turns around it, de-duplicates, and renders every turn with its UTC timestamp and role. No LLM, embedding or reranker is used; the same input always returns the same evidence. |
| Information approved for public display | System name, version, the method description above, the public repository URL and the fixed commit. |
| Complete submission notes | Deployed API version `TBD`; endpoints below; auth `X-Api-Key`; capacity below; operational constraints: single instance, SQLite, no server-side request timeout, Add is synchronous; prior-work attribution and method changes in `docs/METHOD_CARD.md`. |
| Deployed Add endpoint URL | `https://memory.azorashopping.site/v1/memories/add` (Alibaba Cloud box, Caddy TLS; live since 2026-10-07) |
| Deployed Search endpoint URL | `https://memory.azorashopping.site/v1/memories/search` |
| Health URL | `https://memory.azorashopping.site/health` (unauthenticated GET, returns 200; re-checked 2026-10-08) |
| Authentication | `X-Api-Key: <Memory System Key>` (declared scheme). The service also accepts `Authorization: Bearer <key>` and `Authorization: Token <key>`. The scheme chosen in the form must be the one used; a mismatch is a 401. `none` is allowed only for public smoke. |
| Memory System Key | the value of `MEMORY_API_KEY` in the server's `.env` (≥ 16 characters); never committed |
| Capacity declaration | Max add concurrency 16 · Search concurrency 16 · `top_k` 1–1000 (official runs use 100) · Add synchronous, persisted and searchable before the 200 · no server-side timeout (platform limit 30 min/request) · single instance |
| Typical latency (FAQ Q5) | Measured 2026-10-08 through TLS at 16-way concurrency: Add p50 234 ms / p99 454 ms; Search p50 2.2 s / p99 5.0 s with the gpt-4o-mini planner (≈ 40 ms without it) |
| Request body & storage capacity (FAQ Q5) | Add body up to 20 messages / 2,000 words per platform chunk (no explicit body limit enforced below FastAPI defaults); storage ≈ 5× raw text at rest, 34 GB free on the box (≥ 20 GB needed for the Textual track) |
| Models & external dependencies (FAQ Q5/Q7) | `gpt-4o-mini` (via OpenRouter, model id `openai/gpt-4o-mini`) as the Search-time query planner only; no generative model in Add (N/A); no embedding model, no reranker in the current version (if a dense channel is added it will be `text-embedding-v4` only); SQLite FTS5; Caddy TLS |
| Multimodal processing declaration (FAQ Q5) | N/A — Textual track only |
| Service maintenance (FAQ Q5) | Single operator; health monitored via `/health`; Docker `restart: unless-stopped`; no planned changes during a Full run (FAQ Q29); idempotency records and data volume kept until the run is closed (FAQ Q26/Q27), deleted within 30 days after (FAQ Q31) |
| Public repository URL | `https://github.com/Janettbella69/aml-memory` (created 2026-10-08 as private; switch to public before submitting: `gh repo edit Janettbella69/aml-memory --visibility public --accept-visibility-change-consequences`) |
| Fixed commit hash | TBD at freeze |
| Attribution of prior work | `docs/METHOD_CARD.md` § "Prior work and attribution" (FTS5 baseline pattern, idea only — the 0.1 draft's adapted lines were rewritten in 0.2; ReFind: timestamp rendering, context window, ordinal ordering, porter, RRF, service shape — MIT, notice in `NOTICE`) |
| Method changes | `docs/METHOD_CARD.md` § "Method changes by version" |

## Create Eval Job

| Field | Value |
|---|---|
| Evaluation track | Textual |
| System name | `aml-memory` |
| Version name | the bound version (`v1.0` after freeze) |
| Run label | `aml-memory-v1.0-smoke-01`, `-smoke-02`, … then `aml-memory-v1.0-full-01` (labels must be unique per key) |
| Mode | `smoke` first; `full` once smoke passes and the checklist is confirmed. The form also offers `light` and `scriptmem`; `full` is the only formal participant mode. |
| Max add concurrency | 16 |
| Search concurrency | 16 |

## Quotas and dates (official, 2026-10-07)

- Smoke: 1 per hour; at most 30 per track this edition. Private, never public-eligible.
- Full: at most 2 per AML Key per track; the second unlocks 30 days after the first completes — with evaluation closing on 2026-11-04 this means one Full run in practice. A failed or cancelled Full resumes from its last checkpoint and does not consume a new Full.
- Evaluation keys are issued by 19:00 Beijing time on the day after the request.
- Materials deadline: 2026-10-31 23:59 (UTC+8). Evaluation closes: 2026-11-04 23:59 (UTC+8). Official leaderboard: mid-November 2026.
- Once a Full evaluation is accepted the version cannot be replaced or withdrawn because of an unfavourable result; freeze the version before applying.
- Endpoints need not stay online after the evaluation closes.
- Before every Full run the 8-item gate in `docs/CHECKLIST.md` must be confirmed.
