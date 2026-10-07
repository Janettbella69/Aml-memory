# PLAN — AML Cycle 2 (textual, Open-source Methods)

Start 2026-10-07. Materials deadline 2026-10-31. Evaluation closes 2026-11-04.

## Why we can place
Cycle-1 open-source board: a plain SQLite-FTS5 baseline scored 41.8 (#22 of 50); #1 was 45.1. The whole open-source field sits in a 4-point band. Commercial systems collapse on **Execution** (rule-system application, workflow, format constraints: mean 23.3) and **Temporal** (mean 24.9). Those two are where cheap, deterministic tricks can move the needle.

## Seven capabilities (leaf names from the board's own data)
1. Fact Recall — single fact / entity-speaker attribution / structured set extraction
2. Composition — cross-session aggregation / causal chain / evidence validity / common-sense completion
3. Temporal — dates & intervals / event ordering / stance change over time
4. Governance — new-value overwrite / contradiction / deletion & forgetting / long-history synthesis
5. Personalization — preference recall / anti-stereotype robustness / background & care
6. Execution — domain reasoning / rule-system application / workflow / empirical data / format constraints
7. Safety — abstention on insufficient evidence / privacy minimization

## Versions
- **v0.1 (done 10-07)**: FTS5 BM25 + timestamp rendering + ±1 context + rule slots + recency fallback. Tests green, smoke green.
- **v0.2 (week 1)**: (a) session-level RRF like ReFind; (b) options-aware boosting (multiple-choice options as extra terms, already partial); (c) "latest value wins" for Governance: when several chunks share the same entity/attribute words, surface the newest first; (d) return a compact "timeline" block (first/last dated mention of top entities) to help Temporal.
- **v0.3 (week 2, optional, gpt-4o-mini only)**: query rewriting into 2–3 keyword sets + date filter (ReFind-style planner, ≤2 calls). Decide by ablation on our own mini-set, not by feel.
- **Freeze (by 10-28)**: tag v1.0, write METHOD_CARD, register, smoke on platform, run Full.

## Windows (parallel work)
- **A · service** — this repo; keep tests green; implement v0.2 items.
- **B · deploy** — subdomain on the existing 腾讯云 VPS that hosts AZORA (`memory.<domain>`), Caddy or nginx TLS, `docker compose up`, public `/health`, api key in `.env`. Then run `scripts/smoke_test.py https://memory.<domain> <key>`.
- **C · method & eval** — build a 30–50 question local mini-set in the 7 capabilities (our own writing, NOT leaderboard data) under `evalset/`; a runner that calls add/search and checks whether gold evidence appears in top-k. Every ranking change is judged on this.
- **D · submission** — GitHub public repo, MIT license, METHOD_CARD.md, SUBMISSION.md (system name, version, endpoints, auth, concurrency), registration form on agentmemoryleaderboard.ai by 10-31.

## Status board (each window writes its own line; commit after every milestone)
- 10-07 · **C evalset + A ranking** — claimed by the window opened 10-07 afternoon. Building `evalset/` (own-written samples, 7 capabilities) + `scripts/eval_local.py`, then v0.2 ranking judged on it.
- 10-07 · **D docs** — drafting `LICENSE`, `docs/METHOD_CARD.md`, `docs/SUBMISSION.md` (sub-agent of the same window). Registration itself waits for domain + repo decisions.
- **B deploy** — not started; blocked on: which domain/subdomain, VPS ssh access or self-deploy.

## Facts re-confirmed from the official docs on 10-07
- Add: `request_id` like `eval:run_x:locomo_refined:conv-0:chunk-0`; `user_id` like `eval:run_x:locomo:conv-0`; `session_id` like `eval:run_x:sample:0` (one sample = one session_id, so chunk order comes from the `chunk-N` ordinal, not from session_id).
- Chunking: "splits deterministically at either 20 messages or 2,000 Adapter-counted words"; Streaming sub-suite "writes frozen incremental session or task units".
- Answer model keeps "a token-counted prefix of Search candidates in returned rank order" within 117,760 input tokens → total returned text should stay under ~110k tokens; rank order matters only for truncation.
- Open-source: "expected to use gpt-4o-mini during Add"; Search has no stated model rule. Prizes only for open-source; first ≈ USD 3,000 per track.
- Submission form: system name + version, contact, org/team, evaluation type, method description, public-display info, endpoints, auth + capacity declaration, public repo URL, fixed commit, attribution, method changes. Eval job form: track, system name/version, run label, mode (full/light/smoke), max add concurrency, search concurrency.

## Capacity assumptions to declare
Add concurrency 16, Search concurrency 16, top_k 1–1000. SQLite WAL on one box is enough for ~1.5e8 chars; keep Add synchronous.

## Rest days
Build in two free days per week. Nothing here needs a late night.
