# Risk Register

**Last updated**: 2026-04-17

| ID | Risk | Likelihood | Impact | Mitigation | Owner | Status |
|----|------|-----------|--------|------------|-------|--------|
| R1 | **Iranian state blocks Telegram API** | Medium | High | Maintain RSS fallback, use proxy/VPN for Telegram | Parham | Monitor |
| R2 | **OpenAI/Anthropic API costs exceed budget** | Medium | High | `max_tokens=4096` cap, LLM endpoints admin-only with 10/hour limit, hard monthly cap on OpenAI dashboard (set 2026-04-17) | Parham | Mitigated |
| R3 | **Source websites geo-block our server** | High | Medium | Telegram as backup for state media; 16 channels cover the gap | Claude | Mitigated |
| R4 | **Raters don't engage** | Medium | Medium | Start with close contacts, frictionless rating UX | Parham | Not started |
| R5 | **LLM clustering merges unrelated events** | Medium | Low | Stricter prompts, dedup after clustering, human review | Claude | Mitigated |
| R6 | **API keys / secrets exposed** | Low | Critical | `.env` gitignored, env vars on Railway, rotation policy. **Several keys shared in chat history — pending rotation** | Both | **Needs action** |
| R7 | **Production database data loss** | Low | Critical | Neon has point-in-time recovery (7 days on free). **Automated daily backup TODO** | Parham | Partial |
| R8 | **Telegram session expires** | Medium | Medium | Re-authenticate, documented in RUNBOOK | Parham | Documented |
| R9 | **Legal risk: content aggregation** | Low | High | Fair use (linking, not copying), attribute sources | Parham | Monitor |
| R10 | **User safety: Iranian raters at risk** | Medium | Critical | No public user data, HTTPS only, no analytics/tracking, privacy notice in footer, sessionStorage only | Both | Designed |
| R11 | **Railway/Vercel free tier limits** | Medium | Medium | Migrate to OVHcloud when needed | Parham | In progress |
| R12 | **Single point of failure: one developer (Claude)** | Medium | High | Document everything, use standard tools | Both | Mitigated |
| R13 | **Image URLs expire (Telegram CDN)** | High | Medium | All images now stored in Cloudflare R2 with stable URLs | Claude | **Mitigated (2026-04-10)** |
| R14 | **Volumetric DDoS on backend** | Medium | High | Rate limiting at app layer; Cloudflare Bot Fight Mode on (2026-04-17); WAF managed ruleset deferred (requires paid tier) | Both | Partial (WAF deferred) |
| R15 | **Application-layer DoS (spamming expensive endpoints)** | Medium | Medium | slowapi: 200/min default, 10/hour on LLM endpoints | Claude | Mitigated |
| R16 | **LLM cost abuse via public endpoint** | Low | High | `POST /summarize` and lab LLM endpoints now admin-only + rate limited | Claude | Mitigated |
| R17 | **Mass assignment attacks** | Low | High | Allowed field whitelists in admin/lab PUT endpoints | Claude | Mitigated |
| R18 | **Bot scraping / content theft** | Medium | Medium | Rate limiting + Cloudflare Bot Fight Mode on (2026-04-17) | Both | Mitigated |
| R19 | **No outage detection** | High | Medium | UptimeRobot monitor on `/health` added 2026-04-17 | Parham | Mitigated |
| R20 | **Backend memory exhaustion via large request body** | Low | Medium | 1 MB request size limit middleware | Claude | Mitigated |
| R21 | **Deployment failure on dependency change** | Medium | Medium | R2 env vars set on Railway; backend live; CI typecheck + unit tests added 2026-04-17 to catch regressions earlier | Claude | Mitigated |

## Risk Response Plans

### R2 (LLM cost overrun)
1. First line: `max_tokens=4096` per call caps worst-case
2. Second line: slowapi 10/hour limit on LLM endpoints
3. Third line: admin-only auth (leaked token is the only way abuse happens)
4. **Fourth line (TODO)**: hard spending cap on OpenAI dashboard — if all else fails, API just refuses requests
5. Monitor weekly via COST_LOG.md

### R6 (keys exposed)
1. **Rotate all credentials that appeared in chat history**:
   - R2 API token (shared 2026-04-10)
   - Neon DB password (shared earlier)
   - Upstash Redis password (shared earlier)
   - Anthropic API key (shared earlier)
2. Set new values on Railway + local .env
3. Going forward: generate secrets with `openssl rand -hex 32`, never paste in chat

### R14 (DDoS)
1. Current: slowapi catches sustained flooding at ~200 req/min per IP
2. Weak against: distributed attack (many IPs), cached endpoints getting bypassed
3. **Fix: Cloudflare proxy in front of Railway** → edge-level DDoS protection, bot detection, WAF rules
4. Emergency: enable "Under Attack" mode in Cloudflare (one click)

### R19 (no monitoring)
1. Right now: we don't know the site is down until a user complains
2. **Fix: UptimeRobot free tier** → pings /health every 5 min, emails on failure
3. Also consider: Sentry for error tracking (free tier)

### R21 (Railway 502)
1. Current state: backend fails to start after 2026-04-10 deploy
2. Likely cause: missing R2 env vars → aioboto3 client init fails on fill-images call, OR slowapi import error
3. Actions:
   a. Check Railway build logs for stack trace
   b. Set R2 env vars in Railway dashboard
   c. Verify `slowapi` and `aioboto3` are in the installed deps
   d. If needed, temporarily comment out the fill-images pipeline step to isolate the issue

## Legacy Risk Response Plans

### R1 (Telegram blocked)
1. Fall back to RSS-only ingestion
2. Set up proxy in non-blocked region
3. Scrape website versions of Telegram channels

### R7 (data loss)
1. Restore from Neon point-in-time recovery
2. Re-run pipeline to recover articles (RSS feeds have history)
3. Telegram posts cannot be recovered — automate backups first

### R10 (rater safety)
1. All rater accounts use pseudonyms
2. No real names or locations stored
3. HTTPS only
4. Database encrypted at rest (Neon default)
5. No analytics or tracking pixels
6. sessionStorage (not localStorage) for UI state
