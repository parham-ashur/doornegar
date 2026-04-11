# Doornegar - OVHcloud VPS Migration Plan

**Last updated**: 2026-04-12 (after the maintenance pipeline audit session)

## Strategic context — when to migrate

Do **not** migrate right now. We hardened the Railway + Neon setup this session with connection keepalives, retry backoffs, memory caps, and batched queries. That code is good. Moving infra now would be churn.

**Migrate when any of these become true:**

| Trigger | Why it matters |
|---|---|
| Railway free credit runs out (~$5/month) | Hard cost event |
| Steady-state monthly bill on Railway > $20 | OVH VPS Value plan is $6/month fixed |
| You need > 512 MB RAM sustained (frequent OOM) | OVH gives 4 GB on $6 plan |
| You get > 10 concurrent users / Neon pool exhausts | Self-hosted Postgres removes the cap |
| IID (nonprofit) is legally formed and has a bank account | Proper entity to own infra contracts |
| A co-maintainer joins who can share ops burden | VPS requires ~1 hour/month ongoing work |

**Also migrate if the data-sovereignty narrative becomes strategically important** — e.g., applying for French civic-tech grants, or public messaging that "Iranian reader data lives on French soil under GDPR." OVH is a French company; Railway and Neon are US-based.

## What moving to OVH actually fixes vs what it doesn't

### Fixes ✅
- **Container restart killing async tasks** — a VPS runs systemd; restarts only happen when you ask for them. No more Railway-rebuilds-mid-run frustrations.
- **Ephemeral filesystem** — real disk; `maintenance.log` survives, durable file history possible.
- **Memory ceiling** — 4 GB vs 512 MB. No OOM anxiety.
- **Cron reliability** — systemd timers with `journalctl` logs, much more observable than Railway's cron.
- **Cost predictability** — $6/month fixed.
- **Data sovereignty** — French compute + (optionally) French Postgres.
- **Deploy control** — no auto-deploy unless you wire it up yourself.

### Doesn't fix ❌
- **Neon idle-connection timeout** — this is a Neon thing, not a Railway thing. Moving compute to OVH but keeping Neon as the DB still requires the `_keepalive` patches we added on 2026-04-11/12. Only way to truly eliminate it is to self-host Postgres on the same VPS.
- **OpenAI LLM costs** — same bills either way.
- **Deploy discipline** — if you set up auto-deploy on OVH (e.g. via GitHub Actions), same "don't push during a run" issue applies.
- **Actual code bugs** (clustering drift, retry loops, image relevance) — all code-level, infra-independent.

## Overview

Migrate all Doornegar services from multiple cloud providers to a single OVHcloud VPS to reduce costs and simplify infrastructure.

## Current Cloud Services to Migrate

| Service | Current Provider | Monthly Cost | Migration Target |
|---------|-----------------|--------------|------------------|
| Backend API (web) | Railway | $5 free credit, then ~$10-20 | VPS: Docker + FastAPI via Nginx |
| Maintenance cron | Railway cron service | Included in Railway credit | VPS: systemd timer |
| PostgreSQL | Neon (free tier) | $0 | VPS Option A: self-hosted with pgvector<br>VPS Option B: keep Neon |
| Redis | Upstash (free tier) | $0 | VPS: Redis 7 (or keep Upstash) |
| Frontend | Vercel (free tier) | $0 | VPS: Nginx + Next.js standalone<br>OR keep Vercel (simpler) |
| Image storage | Cloudflare R2 | $0 (under 10 GB) | **Keep R2** — CDN-backed, cheap, portable |
| LLM APIs | OpenAI + (unused) Anthropic | ~$8-10 (post 3-tier refactor) | No change |
| Domain/DNS | (to be purchased) | ~$10/year | OVHcloud DNS or Cloudflare |

**Estimated VPS cost**: **~$6/month** for OVH VPS Value (2 vCPUs, 4 GB RAM,
80 GB SSD) — the recommended plan. Bigger tiers are available if you outgrow
it, but for prelaunch this is plenty.

**Total monthly cost after migration**:
- **Option A (self-hosted Postgres + keep R2 + keep Vercel)**: ~$14-16/month ($6 VPS + $8-10 LLM)
- **Option B (keep Neon + keep R2 + keep Vercel)**: same ~$14-16/month
- **Option C (everything on VPS, no Vercel, no R2)**: still ~$14-16/month,
  but you own more ops burden — not recommended unless scale demands it.

## Prerequisites

Before starting the migration:

- [ ] Purchase OVHcloud VPS (recommended: VPS Comfort or higher, Ubuntu 22.04)
- [ ] Register a domain name (if not already done)
- [ ] Have SSH access to the VPS
- [ ] Back up all data from current services (especially the Neon database)

## Step-by-Step Migration Checklist

### Phase 1: VPS Setup (Day 1)

- [ ] **1.1** SSH into VPS and update the system
  ```bash
  sudo apt update && sudo apt upgrade -y
  ```
- [ ] **1.2** Install Docker and Docker Compose
  ```bash
  sudo apt install -y docker.io docker-compose-plugin
  sudo usermod -aG docker $USER
  ```
- [ ] **1.3** Install Nginx
  ```bash
  sudo apt install -y nginx
  ```
- [ ] **1.4** Install Certbot for SSL certificates
  ```bash
  sudo apt install -y certbot python3-certbot-nginx
  ```
- [ ] **1.5** Set up firewall (UFW)
  ```bash
  sudo ufw allow 22/tcp    # SSH
  sudo ufw allow 80/tcp    # HTTP
  sudo ufw allow 443/tcp   # HTTPS
  sudo ufw enable
  ```
- [ ] **1.6** Create a non-root user for running services
  ```bash
  sudo adduser doornegar
  sudo usermod -aG docker doornegar
  ```

### Phase 2: Docker Compose Production Setup (Day 1-2)

- [ ] **2.1** Create production directory on VPS
  ```bash
  mkdir -p /opt/doornegar
  ```
- [ ] **2.2** Create production `docker-compose.prod.yml`:
  ```yaml
  services:
    db:
      image: pgvector/pgvector:pg16
      restart: always
      environment:
        POSTGRES_DB: doornegar
        POSTGRES_USER: doornegar
        POSTGRES_PASSWORD: ${DB_PASSWORD}
      volumes:
        - pgdata:/var/lib/postgresql/data
      healthcheck:
        test: ["CMD-SHELL", "pg_isready -U doornegar"]
        interval: 10s
        timeout: 5s
        retries: 5

    redis:
      image: redis:7-alpine
      restart: always
      command: redis-server --requirepass ${REDIS_PASSWORD}
      volumes:
        - redisdata:/data
      healthcheck:
        test: ["CMD", "redis-cli", "-a", "${REDIS_PASSWORD}", "ping"]
        interval: 10s
        timeout: 5s
        retries: 5

    backend:
      build:
        context: ./backend
        dockerfile: Dockerfile
      restart: always
      command: uvicorn app.main:app --host 0.0.0.0 --port 8000
      ports:
        - "127.0.0.1:8000:8000"
      env_file: .env
      depends_on:
        db:
          condition: service_healthy
        redis:
          condition: service_healthy

    # Maintenance cron: runs auto_maintenance.py once a day.
    # NOTE: we don't use Celery in production anymore. The maintenance
    # pipeline is a standalone script (backend/auto_maintenance.py) and
    # the web service exposes /admin/maintenance/run for on-demand runs
    # via the dashboard. For scheduled runs on a VPS, use a HOST crontab
    # or systemd timer instead of a long-running container. Example
    # systemd unit files are in section "Phase 2b" below.

    frontend:
      build:
        context: ./frontend
        dockerfile: Dockerfile
      restart: always
      ports:
        - "127.0.0.1:3000:3000"
      environment:
        - NEXT_PUBLIC_API_URL=https://api.yourdomain.com

  volumes:
    pgdata:
    redisdata:
  ```

- [ ] **2.3** Create production `.env` file (store securely, never commit). The
  canonical reference for every variable is `backend/.env.example` — keep
  that file in sync whenever config fields are added. Current set:
  ```
  # --- Core app ---
  ENVIRONMENT=production
  DEBUG=false
  PORT=8000
  SECRET_KEY=GENERATE_WITH_openssl_rand_hex_48
  ADMIN_TOKEN=GENERATE_WITH_openssl_rand_hex_48
  CORS_ORIGINS=https://doornegar.yourdomain.com,https://www.yourdomain.com

  # --- Database ---
  # If self-hosted on this VPS:
  DATABASE_URL=postgresql+asyncpg://doornegar:STRONG_PASSWORD@db:5432/doornegar
  DB_PASSWORD=STRONG_PASSWORD
  # OR keep Neon (no change needed) — still requires the _keepalive fixes in
  # clustering.py, bias_scoring.py, and auto_maintenance.step_summarize

  # --- Redis ---
  REDIS_URL=redis://:REDIS_STRONG_PASSWORD@redis:6379/0
  REDIS_PASSWORD=REDIS_STRONG_PASSWORD

  # --- LLM (3-tier strategy) ---
  OPENAI_API_KEY=sk-...
  ANTHROPIC_API_KEY=               # optional fallback, not required
  BIAS_SCORING_MODEL=gpt-4o-mini
  STORY_ANALYSIS_MODEL=gpt-4o-mini
  STORY_ANALYSIS_PREMIUM_MODEL=gpt-5-mini
  TRANSLATION_MODEL=gpt-4.1-nano
  CLUSTERING_MODEL=gpt-5-mini
  PREMIUM_STORY_TOP_N=30

  # --- Clustering safety limits ---
  MAX_CLUSTER_SIZE=30
  CLUSTERING_TIME_WINDOW_DAYS=7
  CLUSTERING_SIMILARITY_THRESHOLD=0.45
  STORY_MERGE_THRESHOLD=0.55

  # --- Cloudflare R2 (keep even on OVH — migrating images is not worth it) ---
  R2_ACCOUNT_ID=...
  R2_ACCESS_KEY_ID=...
  R2_SECRET_ACCESS_KEY=...
  R2_BUCKET_NAME=doornegar-images
  R2_PUBLIC_URL=https://pub-xxx.r2.dev

  # --- Telegram ---
  TELEGRAM_API_ID=0
  TELEGRAM_API_HASH=
  TELEGRAM_CHANNEL_USERNAME=

  # --- Ingestion tunables ---
  INGESTION_INTERVAL_MINUTES=15
  INGESTION_TIMEOUT_SECONDS=30
  MAX_ARTICLES_PER_FEED=50
  ```

  **Generate secrets**:
  ```bash
  python3 -c "import secrets; print(secrets.token_urlsafe(48))"
  # run 4x for SECRET_KEY, ADMIN_TOKEN, DB_PASSWORD, REDIS_PASSWORD
  ```

### Phase 2b: Maintenance cron via systemd timer (Day 1-2)

Instead of running Celery workers, schedule the maintenance pipeline with
a host-level systemd timer that `docker exec`s into the backend container.
More transparent than Railway's cron service, with `journalctl` logs.

- [ ] **2b.1** Create `/etc/systemd/system/doornegar-maintenance.service`:
  ```ini
  [Unit]
  Description=Doornegar maintenance pipeline (one-shot)
  After=docker.service network-online.target
  Requires=docker.service

  [Service]
  Type=oneshot
  WorkingDirectory=/opt/doornegar
  User=doornegar
  ExecStart=/usr/bin/docker exec doornegar-backend python auto_maintenance.py
  TimeoutStartSec=3600
  StandardOutput=journal
  StandardError=journal
  ```

- [ ] **2b.2** Create `/etc/systemd/system/doornegar-maintenance.timer`:
  ```ini
  [Unit]
  Description=Run Doornegar maintenance nightly
  After=docker.service

  [Timer]
  OnCalendar=*-*-* 04:00:00 Europe/Paris
  # 06:00 summer time / 05:00 winter time — runs while you're asleep
  Persistent=true

  [Install]
  WantedBy=timers.target
  ```

- [ ] **2b.3** Enable and start:
  ```bash
  sudo systemctl daemon-reload
  sudo systemctl enable --now doornegar-maintenance.timer
  systemctl list-timers doornegar-maintenance.timer
  journalctl -u doornegar-maintenance.service -n 100 --follow
  ```

- [ ] **2b.4** Manual trigger (for testing):
  ```bash
  sudo systemctl start doornegar-maintenance.service
  journalctl -u doornegar-maintenance.service -f
  ```

**Why not Celery beat?**: we don't use it in production anymore. The pipeline
is a single script (`auto_maintenance.py`) and the dashboard triggers on-demand
runs via `POST /admin/maintenance/run` (fire-and-forget asyncio task). On a
VPS, systemd timers + journalctl give more durability and visibility than
a Celery beat container — and the daily cadence means no long-lived worker
is needed.

### Phase 3: Database Migration (Day 2)

- [ ] **3.1** Export data from Neon PostgreSQL
  ```bash
  pg_dump -h your-neon-host.neon.tech -U doornegar -d doornegar -F c -f doornegar_backup.dump
  ```
- [ ] **3.2** Copy dump file to VPS
  ```bash
  scp doornegar_backup.dump user@vps-ip:/opt/doornegar/
  ```
- [ ] **3.3** Start only the database container
  ```bash
  docker compose -f docker-compose.prod.yml up -d db
  ```
- [ ] **3.4** Install pgvector extension
  ```bash
  docker exec -i doornegar-db psql -U doornegar -d doornegar -c "CREATE EXTENSION IF NOT EXISTS vector;"
  ```
- [ ] **3.5** Restore the database
  ```bash
  docker exec -i doornegar-db pg_restore -U doornegar -d doornegar < doornegar_backup.dump
  ```
- [ ] **3.6** Verify data was restored correctly
  ```bash
  docker exec -i doornegar-db psql -U doornegar -d doornegar -c "SELECT count(*) FROM articles;"
  ```

### Phase 4: Deploy Application (Day 2-3)

- [ ] **4.1** Clone the repository to VPS
  ```bash
  cd /opt/doornegar
  git clone <repo-url> .
  ```
- [ ] **4.2** Build and start all services
  ```bash
  docker compose -f docker-compose.prod.yml up -d --build
  ```
- [ ] **4.3** Run database migrations
  ```bash
  docker exec -i doornegar-backend alembic upgrade head
  ```
- [ ] **4.4** Verify backend is responding
  ```bash
  curl http://localhost:8000/health
  ```
- [ ] **4.5** Verify frontend is responding
  ```bash
  curl http://localhost:3000
  ```

### Phase 5: Domain and SSL (Day 3)

- [ ] **5.1** Point domain DNS to VPS IP address
  - A record: `yourdomain.com` -> VPS IP
  - A record: `api.yourdomain.com` -> VPS IP
  - A record: `www.yourdomain.com` -> VPS IP

- [ ] **5.2** Configure Nginx as reverse proxy. Create `/etc/nginx/sites-available/doornegar`:
  ```nginx
  # Frontend
  server {
      listen 80;
      server_name yourdomain.com www.yourdomain.com;

      location / {
          proxy_pass http://127.0.0.1:3000;
          proxy_set_header Host $host;
          proxy_set_header X-Real-IP $remote_addr;
          proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
          proxy_set_header X-Forwarded-Proto $scheme;
      }
  }

  # Backend API
  server {
      listen 80;
      server_name api.yourdomain.com;

      location / {
          proxy_pass http://127.0.0.1:8000;
          proxy_set_header Host $host;
          proxy_set_header X-Real-IP $remote_addr;
          proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
          proxy_set_header X-Forwarded-Proto $scheme;
      }
  }
  ```

- [ ] **5.3** Enable the site
  ```bash
  sudo ln -s /etc/nginx/sites-available/doornegar /etc/nginx/sites-enabled/
  sudo nginx -t
  sudo systemctl reload nginx
  ```

- [ ] **5.4** Get SSL certificates from Let's Encrypt
  ```bash
  sudo certbot --nginx -d yourdomain.com -d www.yourdomain.com -d api.yourdomain.com
  ```

- [ ] **5.5** Set up auto-renewal
  ```bash
  sudo certbot renew --dry-run
  # Certbot adds a cron job automatically
  ```

### Phase 6: Monitoring and Backups (Day 3-4)

- [ ] **6.1** Set up automated database backups
  ```bash
  # Create backup script at /opt/doornegar/backup.sh
  #!/bin/bash
  DATE=$(date +%Y%m%d_%H%M%S)
  docker exec doornegar-db pg_dump -U doornegar doornegar | gzip > /opt/doornegar/backups/doornegar_${DATE}.sql.gz
  # Keep only last 7 days
  find /opt/doornegar/backups/ -name "*.sql.gz" -mtime +7 -delete
  ```
- [ ] **6.2** Add backup cron job
  ```bash
  # Run daily at 3 AM
  0 3 * * * /opt/doornegar/backup.sh
  ```
- [ ] **6.3** Set up basic monitoring with Docker logs
  ```bash
  # View logs
  docker compose -f docker-compose.prod.yml logs -f backend
  docker compose -f docker-compose.prod.yml logs -f worker
  ```
- [ ] **6.4** (Optional) Install a simple monitoring tool like Uptime Kuma
  ```bash
  docker run -d --restart=always -p 127.0.0.1:3001:3001 --name uptime-kuma louislam/uptime-kuma
  ```

### Phase 7: Verify and Cut Over (Day 4)

- [ ] **7.1** Test all frontend pages work correctly
- [ ] **7.2** Test all API endpoints respond
- [ ] **7.3** Run the pipeline on the VPS and verify data flows
- [ ] **7.4** Verify Celery worker and beat are running
- [ ] **7.5** Check SSL certificates are valid
- [ ] **7.6** Update any environment variables in the old services to point to new URLs
- [ ] **7.7** Remove or stop old Railway and Vercel deployments
- [ ] **7.8** Monitor for 48 hours for any issues

## Backup Strategy

| What | How | Frequency | Retention |
|------|-----|-----------|-----------|
| PostgreSQL database | pg_dump to compressed file | Daily at 3 AM | 7 days |
| Redis data | RDB snapshot (automatic) | Every 15 minutes | 3 snapshots |
| Application code | Git repository | On every deploy | Full history |
| .env file | Manual backup to secure location | On every change | Keep all versions |
| SSL certificates | Auto-renewed by Certbot | Every 60 days | Automatic |

## Monitoring and Logging

- **Docker logs**: `docker compose logs -f <service>` for real-time logs
- **Nginx access logs**: `/var/log/nginx/access.log`
- **Nginx error logs**: `/var/log/nginx/error.log`
- **Health check**: `curl https://api.yourdomain.com/health`
- **Optional**: Uptime Kuma for uptime monitoring with alerts

## Estimated Timeline

| Day | Tasks |
|-----|-------|
| Day 1 | VPS setup, Docker install, security hardening |
| Day 2 | Database migration, deploy application |
| Day 3 | Domain/DNS, SSL, Nginx configuration |
| Day 4 | Testing, monitoring setup, cutover |
| Day 5+ | Monitor, fix issues, decommission old services |

**Total estimated time**: 4-5 days of work sessions

## Rollback Plan

If something goes wrong during migration:

1. The old services (Railway, Vercel, Neon) remain running during migration
2. DNS can be pointed back to old services within minutes
3. Database backup from Neon is preserved
4. Do not decommission old services until the VPS has been stable for at least 48 hours

## Security Considerations

- Use strong, unique passwords for PostgreSQL and Redis (generate with `openssl rand -hex 32`)
- Keep the `.env` file outside the git repository
- Enable UFW firewall (only ports 22, 80, 443 open)
- Use SSH key authentication, disable password login
- Keep the VPS updated (`sudo apt update && sudo apt upgrade` regularly)
- Consider fail2ban for SSH brute-force protection
- All traffic through HTTPS (redirect HTTP to HTTPS in Nginx)
- Backend only listens on 127.0.0.1 (not exposed to internet directly)
- `ADMIN_TOKEN` must be rotated if it was ever exposed (e.g. shared in chat
  or committed accidentally). Check `backend/.env.example` for the full
  list of secrets that need rotation.

## Postgres strategy: self-host vs keep Neon

You have two reasonable options for the database when migrating to OVH.
Pick ONE.

### Option A — Self-host Postgres on the same VPS (recommended long-term)
```
Pros:
+ Zero idle-connection timeout (same-machine, no Neon 5-min kill)
+ No external DB dependency
+ Lower latency (Unix socket or localhost TCP)
+ Full data sovereignty
+ No separate backup provider needed (backups live on the same VPS)
Cons:
- You're now responsible for PostgreSQL operations:
  - Daily backups + offsite copies
  - Point-in-time recovery if you need it
  - Security patches
  - pgvector extension installation
- If the VPS dies, BOTH the app and the database die with it
```

**When to pick this**: if you're migrating anyway, and you want to fully
decommission Neon for cost/sovereignty reasons.

### Option B — Keep Neon as the database
```
Pros:
+ Zero DB operations work for you
+ Neon handles backups, PITR, failover
+ Simpler cutover (only compute moves)
+ Can roll back by pointing Railway DNS at Neon
Cons:
- Still requires the _keepalive patches we added on 2026-04-11
  (Neon doesn't care which compute host connects to it)
- US-based; weaker data sovereignty story
- Additional network hop from OVH → Neon EU region (~20-50ms)
- You still have an external dependency
```

**When to pick this**: if you want the LEAST risky migration. Move compute
first, prove it works, then migrate Postgres later in a separate session.

### Hybrid phased approach (safest)

Phase A (now): keep Neon, move everything else to OVH. 2-3 days of work, low
risk because the DB stays stable.

Phase B (later, 1-3 months): export Neon → restore onto the VPS's Postgres
container. Cutover during a maintenance window. ~1 day of work.

## Pre-migration checklist (do these BEFORE starting Phase 1)

- [ ] Full Neon DB snapshot downloaded (`pg_dump` → local file)
- [ ] All env vars documented in `backend/.env.example` (already done)
- [ ] All secrets rotated if they were ever shared in chat:
      R2 token, Neon password, Upstash password, Anthropic key, ADMIN_TOKEN
- [ ] Current deployment URLs documented so you can update DNS later
- [ ] `maintenance.log` and any local artifacts either committed or archived
- [ ] Decide Postgres strategy (A, B, or hybrid A)
- [ ] Domain name purchased (if not already) — needed for DNS cutover
- [ ] Railway + Vercel + Neon accounts' billing status confirmed (don't
      accidentally get surprised by a charge mid-migration)

## Post-migration verification checklist

Run these after Phase 7 to confirm everything works:

- [ ] `/health` endpoint returns 200 on HTTPS
- [ ] `/fa` homepage loads, shows trending stories with images
- [ ] `/fa/dashboard` loads after admin password + token
- [ ] Diagnostics panel shows the new DB URL, LLM keys set
- [ ] Recently re-summarized stories card lists stories
- [ ] Click "Run Maintenance" from the dashboard — watch for all 23 steps
      complete in green (no connection-closed errors, no OOM)
- [ ] Verify systemd timer fires the next cron run: `journalctl -u doornegar-maintenance.service --since "1 hour ago"`
- [ ] Check no Railway/Vercel references remain in the frontend API config
- [ ] SSL cert auto-renewal test: `sudo certbot renew --dry-run`
- [ ] Firewall status: `sudo ufw status verbose`
- [ ] Backup script ran overnight: `ls -lah /opt/doornegar/backups/`
- [ ] Disk usage sane: `df -h`
- [ ] Memory usage sane at rest: `free -h`
- [ ] Uptime monitoring configured (Uptime Kuma or UptimeRobot) and pinging
- [ ] At least one full maintenance run completed on the VPS without
      manual intervention

## Post-migration code changes (none required, but consider these)

Once you're running on OVH with self-hosted Postgres (Option A above), the
following defensive code from 2026-04-11/12 is no longer strictly necessary,
but it's harmless to keep:

- `app/services/clustering.py` `_keepalive()` calls (Neon-specific defense)
- `app/services/bias_scoring.py` `_keepalive()` calls (same)
- `auto_maintenance.step_summarize` keepalive inner function (same)
- `app/database.py` `pool_recycle=240` (can go back to default `pool_recycle=3600`)

**Recommendation**: leave them in. They cost nothing, and if you ever move
back to a managed DB (or a Postgres that does have idle timeouts) you'll
thank yourself.

## Lessons learned before migration (2026-04-11/12)

Things we fixed in the Railway/Neon setup that you MUST verify still work
on OVH:

1. **Neon idle timeout** — fixed via `_keepalive()` pings. Only matters if
   you keep Neon. If self-hosting Postgres, the underlying issue goes away.
2. **Asyncio background tasks dying on deploy** — fixed by splitting the
   web service (uvicorn) from the maintenance trigger (fire-and-forget via
   shared state). On OVH, systemd-based deploys don't have this problem
   at all because you restart the service explicitly.
3. **Container ephemeral filesystem** — `maintenance.log` was never
   reliably written on Railway. OVH has a real disk; the log will work.
4. **Local-only image URLs** (`http://localhost:8000/images/*`) — legacy
   dev artifacts that need one-shot nullification. Use the admin endpoint
   `POST /admin/nullify-localhost-images` before or after migration.
5. **Clustering drift (209-article attractor clusters)** — fixed via size
   ceiling + time window + strict prompt + article content in prompt.
   Works the same on either host.
6. **LLM retry loops** — fixed via `llm_failed_at` column added in the
   `b5e9f3a1c2d8` Alembic migration. Runs automatically on first deploy.

See `CHANGELOG.md` entry for April 11-12 for the full list of changes.
