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
- **v0.2 (done 10-07)**: porter stemming; CJK trigram index fused by RRF; recency band ("latest value wins" inside near-equal scores); rules relevance-sorted and placed after the first 5 hits; ±2 spans crossing Add-chunk boundaries with de-duplication; response char budget; periodic retention sweep. Dropped (d) "timeline block": derived text risks the "disguised answer" rule.
- **v0.3 (implemented 10-07; code default OFF, deployed config ON per user decision)**: `app/planner.py` one-step gpt-4o-mini query planner (≤3 extra queries + date range, RRF-fused, deterministic fallback) and `scripts/judge_local.py` end-to-end proxy scoring. Decide ON/OFF by the judge on our own set once a working key exists (env key → 401 on 10-07). Cost estimate for a Full run: ~1.5k tokens per Search → 10k searches ≈ $2–3, 100k searches ≈ $25 at gpt-4o-mini prices.
- **Freeze (by 10-28)**: tag v1.0, write METHOD_CARD, register, smoke on platform, run Full.

## Windows (parallel work)
- **A · service** — this repo; keep tests green; implement v0.2 items.
- **B · deploy** — subdomain on the existing 腾讯云 VPS that hosts AZORA (`memory.<domain>`), Caddy or nginx TLS, `docker compose up`, public `/health`, api key in `.env`. Then run `scripts/smoke_test.py https://memory.<domain> <key>`.
- **C · method & eval** — build a 30–50 question local mini-set in the 7 capabilities (our own writing, NOT leaderboard data) under `evalset/`; a runner that calls add/search and checks whether gold evidence appears in top-k. Every ranking change is judged on this.
- **D · submission** — GitHub public repo, MIT license, METHOD_CARD.md, SUBMISSION.md (system name, version, endpoints, auth, concurrency), registration form on agentmemoryleaderboard.ai by 10-31.

## Status board (each window writes its own line; commit after every milestone)
- 10-07 · **C evalset** — DONE. `evalset/` 5 samples / 292 turns / 71 questions across the 7 capabilities (+ a Chinese sample), `scripts/eval_local.py` (hit@k, MRR, trap order, token cost), `scripts/sweep_local.py` (grid over env knobs).
- 10-07 · **A ranking v0.2** — DONE, tagged in code as 0.2.0. Local set: MRR 0.20 → 0.72, hit@10 0.78 → 0.92, hit@100 0.97 → 1.00, trap order 0.17 → 0.85, ~2.1k tokens per response. Known limits: pure multi-hop with no lexical overlap (`lt-co-03`), near-equal stance statements where the older one is shorter (`lt-te-02`).
- 10-07 · **D docs** — DONE as drafts: `LICENSE` (MIT), `NOTICE`, `docs/METHOD_CARD.md`, `docs/SUBMISSION.md`, `docs/CHECKLIST.md`. Registration waits on domain + repo decisions.
- 10-07 · **Attribution fix** — v0.1 had ~30 lines adapted from the unlicensed FantaSmallhamster baseline; v0.2 rewrote models/config/store/search/main so none remain (table/column names, validators, stop list, env parsing all our own). Recorded in NOTICE and the method card.
- 10-07 · **Scale work** — DONE: one SQLite file per user (soak at 1/35 of the official volume showed a shared index needs 0.9 s per search), cached connections, per-process gates (SQLite mutex contention: 16 threads = 24 q/s, 1 thread = 293 q/s), external-content index, WAL limits. `scripts/soak_local.py`. One worker: 1,313 adds/s, 293 searches/s.
- 10-07 · **v0.3 planner + judge** — code DONE (28 tests), measurement BLOCKED on a working OpenAI key. GitHub repo creation was denied by the session's permission classifier → the user creates it (`gh repo create aml-memory --private --source . --push`).
- 10-07 · **B deploy — service LIVE on the new box, cert pending DNS.** Alibaba Cloud (intl) `root@47.77.196.181` (Ubuntu 24.04, 2 vCPU / 1.6 GB / 35 GB free; ssh key `~/.ssh/id_ed25519` is passphrase-protected → needs `ssh-add --apple-use-keychain` in the session first). Docker 29 installed; repo at `/root/aml-memory`; `deploy/docker-compose.prod.yml` running (containers `deploy-memory-1` healthy, `deploy-caddy-1` on 80/443; security group lets 80/443 through). Internal smoke passed; real `MEMORY_API_KEY` in `/root/aml-memory/.env`. **Waiting for:** DNSPod A record `memory.azorashopping.site → 47.77.196.181` (then restart caddy to issue the cert), OpenAI key for the planner, GitHub repo.
- 10-07 · **Deploy kit** — DONE: `deploy/` (Caddyfile, prod compose, `deploy.sh`, runbook). **B deploy itself** still blocked on: which domain/subdomain, VPS ssh access or self-deploy. Needs ≥ 20 GB free disk.
- 10-07 · **Decision (user):** do not ask the organisers; a model is expected, so the submitted configuration runs the v0.3 gpt-4o-mini planner (`PLANNER_MODEL=gpt-4o-mini` in the deployed `.env`). Still to measure with the judge once a working key exists.
- 10-08 · **D repo + public endpoint** — DONE. `https://memory.azorashopping.site/health` returns 200 over TLS (the "cert pending DNS" note above is stale). GitHub repo `https://github.com/Janettbella69/aml-memory` created by the user (private; make public before submitting), `origin/main` = local `main`; no `.env` or keys tracked. `docs/SUBMISSION.md` now carries the endpoints and repo URL. 30 tests green. **Still open:** working OpenAI key → judge run → planner ON/OFF decision; 16-way soak on the box; evaluation-access request on the platform.
- 10-08 · **C judge: planner ON confirmed.** Key = the AZORA project's OpenRouter key (`openai/gpt-4o-mini` = the same OpenAI model, routed); local `.env` holds it, git-ignored; run as `env -u OPENAI_API_KEY uv run --env-file .env python scripts/judge_local.py …` because the login shell exports a dead `OPENAI_API_KEY`. Two runs each on the 76-question set: OFF 0.868 / 0.868, ON 0.908 / 0.908 (temporal 0.75 → 1.00, governance 0.70 → 0.70 / 0.80, execution 0.93 → 0.87 incl. grader noise). ≈ $0.035 per run. Remaining ON failures to target next: `mia-go-04`, `lt-go-03`, `lt-co-05`, `dv-ex-03`, `dv-ex-05`, `mia-sa-02` (privacy abstention), and `mia-co-02`/`lt-go-02` which flip between runs. **Next:** push the OpenRouter planner config to the box (`.env` on the server still has the dead key), then the 16-way soak through TLS.
- 10-08 · **B deploy + soak — DONE.** The user pushed HEAD + the OpenRouter config to the box (`git archive | ssh tar -x`, `deploy/deploy.sh`): health ok, smoke passed, both workers log `query planner enabled: openai/gpt-4o-mini`, 34 GB free. 16-way soak from the laptop through TLS: 6,000 Adds in 96 s (62.5/s, p99 454 ms, 0 errors), 288 Searches at 6.2 q/s (p50 2.2 s, p99 5.0 s; planner call dominates), median response 135 k chars. Numbers in the method card; checklist item 4 done. Soak data (200 `soak*` users) is still in the production volume → `down -v` before the Full run (runbook § Before the Full run). **Still open:** register on the platform (needs the repo public + a fixed commit), then smoke on the platform, then Full.

## Facts re-confirmed from the official docs on 10-07
- Add: `request_id` like `eval:run_x:locomo_refined:conv-0:chunk-0`; `user_id` like `eval:run_x:locomo:conv-0`; `session_id` like `eval:run_x:sample:0` (one sample = one session_id, so chunk order comes from the `chunk-N` ordinal, not from session_id).
- Chunking: "splits deterministically at either 20 messages or 2,000 Adapter-counted words"; Streaming sub-suite "writes frozen incremental session or task units".
- Answer model keeps "a token-counted prefix of Search candidates in returned rank order" within 117,760 input tokens → total returned text should stay under ~110k tokens; rank order matters only for truncation.
- Open-source: "expected to use gpt-4o-mini during Add"; Search has no stated model rule. Prizes only for open-source; first ≈ USD 3,000 per track.
- Competition FAQ (via docs window 10-07): embeddings, if any, must be `text-embedding-v4`; LLM components `gpt-4o-mini`; rerankers unrestricted; self-trained/open-weight models belong on the commercial board. Textual track ≈ 300 M tokens / 6,000+ instances / 32 sources; 30-minute per-request limit; auth `none` only for public smoke; Add 409 is retried by the platform with the same body.
- Submission form: system name + version, contact, org/team, evaluation type, method description, public-display info, endpoints, auth + capacity declaration, public repo URL, fixed commit, attribution, method changes. Eval job form: track, system name/version, run label, mode (full/light/smoke), max add concurrency, search concurrency.

## Capacity assumptions to declare
Add concurrency 16, Search concurrency 16, top_k 1–1000. Official textual volume ≈ 300 M tokens (~1.2 GB text): SQLite WAL + porter FTS5 index ≈ 3–4 GB, trigram index only for CJK turns; budget ≥ 20 GB disk and soak-test Add throughput before the Full run. Keep Add synchronous.

## Rest days
Build in two free days per week. Nothing here needs a late night.
