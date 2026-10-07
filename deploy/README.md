# Deploy runbook (Window B)

Target: a public HTTPS endpoint `https://memory.<domain>` on the existing 腾讯云 VPS, next to AZORA.
Everything below is idempotent; re-run `deploy/deploy.sh` after every `git pull`.

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
   - `DATA_DIR=/data` (default; one SQLite file per user_id under `/data/users/`)
   - `UVICORN_WORKERS=` number of CPU cores (`nproc`); keep `SEARCH_PARALLELISM=1`, `WRITE_PARALLELISM=2`

## Every deploy
```bash
bash deploy/deploy.sh          # build, start, wait for health, run the smoke test with the real key
docker compose -f deploy/docker-compose.prod.yml --env-file .env logs -f --tail 100 memory
```

## Checks before requesting an AML key
- `curl https://memory.<domain>/health` → `{"status":"ok","version":"..."}`
- `uv run python scripts/eval_local.py --base https://memory.<domain> --api-key $MEMORY_API_KEY` from the laptop (end-to-end through TLS)
- `uv run python scripts/soak_local.py --base https://memory.<domain> --api-key $MEMORY_API_KEY --users 200` (16-way concurrent Add + Search; record p50/p99 in docs/METHOD_CARD.md)

## After the Full run (within 30 days, rule)
```bash
docker compose -f deploy/docker-compose.prod.yml --env-file .env down -v   # drops memory-data (evaluation data)
```
Endpoints need not stay up after 2026-11-04.
