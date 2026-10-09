# Deploy runbook (Window B)

**Current production box (10-07):** Alibaba Cloud `root@47.77.196.181`, repo at `/root/aml-memory`, stack `deploy/docker-compose.prod.yml` (project name `deploy`). Update with `git archive --format=tar HEAD | ssh root@47.77.196.181 'tar -x -C /root/aml-memory'` then `docker compose -f deploy/docker-compose.prod.yml --env-file .env up -d --build` there. The AZORA VPS is NOT used for this project.

Target: a public HTTPS endpoint `https://memory.<domain>` on the existing 腾讯云 VPS, next to AZORA.
Everything below is idempotent; re-run `deploy/deploy.sh` after every `git pull`.

## Other sites on the same box
The Caddy container owns ports 80/443, so any other app on this box is published through it. Put a
complete site block into `deploy/sites/<name>.caddy` on the server and reload:
`docker exec deploy-caddy-1 caddy reload --config /etc/caddy/Caddyfile --adapter caddyfile`.
The directory is git-ignored and is not part of `git archive`, so updating this stack leaves it alone.
A site file that does not parse stops Caddy from starting, and with it this service's endpoint: check
it first with `docker exec deploy-caddy-1 caddy adapt --config /etc/caddy/Caddyfile --adapter caddyfile`.
`down -v` drops Caddy's certificates for those sites too; they are issued again on the next start.
TradeMind (`trademind.store`) has been served this way since 2026-10-09; its runbook is
`/opt/trademind/deploy/README.md` on the box.

## One-time
1. DNS: `A` record `memory.<domain>` → VPS public IP. Wait until `dig +short memory.<domain>` answers.
2. Firewall / security group: allow TCP 80 and 443 (Caddy needs 80 for the certificate challenge).
   If AZORA's own nginx/Caddy already owns 80/443, do NOT start the caddy service here; instead add a
   `memory.<domain>` server block to that proxy pointing at `127.0.0.1:8000` and run the dev
   `docker-compose.yml` (which binds 127.0.0.1:8000). Proxy timeouts ≥ 60 s.
3. Disk: `df -h /` must show ≥ 20 GB free (official textual volume ≈ 300 M tokens). Docker volume `memory-data` holds the DB.
4. `git clone <repo> && cd aml-memory && cp .env.example .env`, then set in `.env`:
   - `MEMORY_API_KEY=` a random secret ≥ 16 chars (`openssl rand -hex 24`), declared as `X-Api-Key` in the submission form
   - `MEMORY_DOMAIN=memory.<domain>`
   - `MEMORY_ALT_DOMAIN=` optional second hostname served alongside it, e.g. `<ip-with-dashes>.sslip.io` (resolves to the box with no DNS setup; useful until the real record exists)
   - `DATA_DIR=/data` (default; one SQLite file per user_id under `/data/users/`)
   - `UVICORN_WORKERS=` number of CPU cores (`nproc`); keep `SEARCH_PARALLELISM=1`, `WRITE_PARALLELISM=2`

## v0.5 upgrade (dense channel) — one-time
The schema changed (SCHEMA_VERSION 6: `vec` column + `meta`), so existing user files are refused: wipe the volume
(`docker compose -f deploy/docker-compose.prod.yml --env-file .env down -v`) before starting the new image. Add to the
server `.env`: `EMBED_MODEL=text-embedding-v4`, `EMBED_DIMS=256`, `DASHSCOPE_API_KEY=…`, `DASHSCOPE_BASE_URL=…`,
`EMBED_RPS=14` (published key limits: 1,000 req/min on one Alibaba page, 1,800 on another; 14/s ≈ 840/min is safe under both), `VECTOR_CACHE_USERS=16` (the box has 1.6 GB; a cached user costs
turns × dims × 4 bytes per worker). Then `bash deploy/deploy.sh`; the log must show `dense channel enabled: text-embedding-v4 (256 dims)`.

## v0.7 reranker — one-time
Add to the server `.env` (the Model Studio key is already there): `RERANK_PROVIDER=dashscope`, `RERANK_MODEL=qwen3-rerank`,
`RERANK_MODE=replace`, `RERANK_CANDIDATES=40`. Then `bash deploy/deploy.sh`; the log must show `reranker enabled: dashscope/qwen3-rerank`.

## Every deploy
```bash
bash deploy/deploy.sh          # build, start, wait for health, run the smoke test with the real key
docker compose -f deploy/docker-compose.prod.yml --env-file .env logs -f --tail 100 memory
```

## Checks before requesting an AML key
- `curl https://memory.<domain>/health` → `{"status":"ok","version":"..."}`
- `uv run python scripts/eval_local.py --base https://memory.<domain> --api-key $MEMORY_API_KEY` from the laptop (end-to-end through TLS)
- `uv run python scripts/soak_local.py --base https://memory.<domain> --api-key $MEMORY_API_KEY --users 200` (16-way concurrent Add + Search; record p50/p99 in docs/METHOD_CARD.md)

## Before the Full run
Drop the soak/smoke data so the evaluation starts from an empty store, then redeploy:
```bash
docker compose -f deploy/docker-compose.prod.yml --env-file .env down -v && bash deploy/deploy.sh
```

## After the Full run (within 30 days, rule)
```bash
docker compose -f deploy/docker-compose.prod.yml --env-file .env down -v   # drops memory-data (evaluation data)
```
Endpoints need not stay up after 2026-11-04.
