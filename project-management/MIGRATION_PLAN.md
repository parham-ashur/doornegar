# Doornegar - OVHcloud VPS Migration Plan

## Overview

Migrate all Doornegar services from multiple cloud providers to a single OVHcloud VPS to reduce costs and simplify infrastructure.

## Current Cloud Services to Migrate

| Service | Current Provider | Monthly Cost | Migration Target |
|---------|-----------------|--------------|------------------|
| Backend API | Railway | ~$5-20 | VPS: Docker + FastAPI |
| PostgreSQL | Neon (free tier) | $0 | VPS: PostgreSQL 16 + pgvector |
| Redis | Upstash (free tier) | $0 | VPS: Redis 7 |
| Frontend | Vercel (free tier) | $0 | VPS: Nginx + Next.js standalone |
| Domain/DNS | (current provider) | varies | OVHcloud DNS or Cloudflare |

**Estimated VPS cost**: ~$6-12/month for a VPS with 4GB RAM, 2 vCPUs, 80GB SSD

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

    worker:
      build:
        context: ./backend
        dockerfile: Dockerfile
      restart: always
      command: celery -A app.workers.celery_app worker --loglevel=info --concurrency=2
      env_file: .env
      depends_on:
        db:
          condition: service_healthy
        redis:
          condition: service_healthy

    beat:
      build:
        context: ./backend
        dockerfile: Dockerfile
      restart: always
      command: celery -A app.workers.celery_app beat --loglevel=info
      env_file: .env
      depends_on:
        db:
          condition: service_healthy
        redis:
          condition: service_healthy

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

- [ ] **2.3** Create production `.env` file (store securely, never commit):
  ```
  # Database
  DATABASE_URL=postgresql+asyncpg://doornegar:STRONG_PASSWORD@db:5432/doornegar
  DB_PASSWORD=STRONG_PASSWORD

  # Redis
  REDIS_URL=redis://:REDIS_STRONG_PASSWORD@redis:6379/0
  REDIS_PASSWORD=REDIS_STRONG_PASSWORD

  # App
  ENVIRONMENT=production
  DEBUG=false
  SECRET_KEY=GENERATE_A_LONG_RANDOM_STRING
  CORS_ORIGINS=https://yourdomain.com,https://www.yourdomain.com

  # LLM
  ANTHROPIC_API_KEY=sk-ant-...
  BIAS_SCORING_MODEL=claude-haiku-4-5-20251001

  # Telegram
  TELEGRAM_API_ID=your_api_id
  TELEGRAM_API_HASH=your_api_hash
  ```

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
