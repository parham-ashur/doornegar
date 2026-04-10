# Decision Log

Tracks key decisions, their reasoning, and any alternatives considered.

## 2026-04-07

### D001: Use OpenAI LLM for clustering instead of embeddings
**Decision**: Replace cosine-similarity clustering with GPT-4o-mini-based grouping.
**Why**: Embedding similarity maxed at 0.62 across Farsi/English articles — too low for reliable clustering. LLM understands semantic similarity across languages.
**Alternatives considered**: Lower similarity threshold (caused bad groupings), multilingual BERT (too slow and expensive to run locally).
**Cost impact**: ~$0.01 per clustering run (100 articles). Acceptable.
**Status**: Implemented ✓

### D002: Telegram as primary source for inside-Iran media
**Decision**: Treat Telegram posts as articles (not just social reactions) since many Iranian media channels are only accessible via Telegram.
**Why**: RSS feeds for Tasnim, Fars, ISNA, Mehr are geo-blocked. Telegram channels are the only reliable way to get their content.
**Impact**: 478 additional articles from 9 channels.
**Status**: Implemented ✓

### D003: Minimum 5 articles to show a story
**Decision**: Stories with fewer than 5 articles are hidden from the homepage.
**Why**: Small clusters are often noise or single-source stories. 5+ articles indicate genuine multi-source coverage worth analyzing.
**Trade-off**: Some real stories might be hidden if coverage is thin. Mitigated by incremental clustering (articles get added over time).
**Status**: Implemented ✓

### D004: Incremental clustering (not rebuild)
**Decision**: New articles are first matched to existing stories, then remaining ones are clustered into new stories.
**Why**: Rebuilding from scratch every time loses generated summaries, wastes OpenAI credits, and creates unstable story IDs.
**Status**: Implemented ✓

### D005: NYTimes-style design with system dark mode
**Decision**: Clean newspaper layout, no rounded corners, thin borders, white default with system-based dark mode.
**Why**: Parham's preference after multiple design iterations. Professional, readable, content-focused.
**Status**: Implemented ✓

### D006: Invite-only rating system
**Decision**: No public signup. Raters are hand-picked by Parham.
**Why**: Quality control. Public voting would be gamed. Trusted raters produce reliable ground truth for bias calibration.
**Status**: Built, not yet tested with real raters.

### D007: Store images locally
**Decision**: Download and serve images from the backend instead of hotlinking to source URLs.
**Why**: Telegram CDN links expire. Source websites may go offline or change URLs. Local storage is reliable.
**Trade-off**: Increases storage needs (~50MB for 500 images). Fine for VPS, needs cloud solution for Railway.
**Status**: Implemented locally, needs cloud solution for production.

## 2026-04-10

### D008: Cloudflare R2 for image storage
**Decision**: Store all article images in Cloudflare R2 (S3-compatible object storage).
**Why**: Telegram CDN URLs expire within hours. Local filesystem doesn't survive Railway deploys. R2 is:
- Free tier covers our use (~1% of 10 GB quota)
- Free egress (no bandwidth charges, unlike S3)
- Portable: works on Railway today, OVH tomorrow, anywhere
- CDN-backed globally (Cloudflare edge)
- Survives compute restarts
**Alternatives considered**:
- Railway persistent volume: simpler but tied to Railway, not portable
- Vercel Blob: tied to Vercel, more expensive
- S3: free tier smaller, paid egress
- Local disk: dies on restart
**Implementation**: `aioboto3` + `image_downloader.py` uploads to R2; URLs stored as permanent `https://pub-*.r2.dev/*` paths.
**Status**: Implemented ✓ (765 images migrated 2026-04-10)

### D009: slowapi for application-layer rate limiting
**Decision**: Add `slowapi` with default 200/min per IP, aggressive 10/hour on LLM endpoints.
**Why**: Cost abuse prevention. Even if an attacker gets past auth, they hit the cap. Admin-only auth is the primary defense; rate limiting is defense-in-depth.
**Alternatives considered**:
- `fastapi-limiter` (requires Redis, more ops overhead)
- Cloudflare-only rate limiting (edge-only, can't protect against authenticated abuse)
- No rate limiting (too risky after shipping public-facing LLM endpoints)
**Status**: Implemented ✓

### D010: Cloudflare CDN/WAF in front of Railway (planned)
**Decision**: Proxy all production traffic through Cloudflare before hitting Railway/Vercel.
**Why**: Free tier gives volumetric DDoS protection, bot detection, WAF, edge-level rate limiting, and "Under Attack" mode for emergencies. This is the highest-impact security improvement we can make.
**Requires**: Custom domain purchase (~$10/year) and DNS migration.
**Status**: Planned — not yet implemented.

### D011: sessionStorage over localStorage for UI state
**Decision**: Use `sessionStorage` for the welcome modal's "seen" flag.
**Why**: Better UX for testing (resets on tab close) and aligns with privacy stance (no long-term client tracking). Also added `?welcome=1` URL override for manual re-showing.
**Status**: Implemented ✓

### D012: Admin-only gating for all LLM-triggering endpoints
**Decision**: Every endpoint that can cause a billable LLM call is admin-only.
**Affected**: `POST /stories/{id}/summarize`, `POST /lab/topics/{id}/analyze`, `POST /lab/topics/{id}/generate-analysts`, all lab mutation endpoints.
**Why**: Primary defense against cost abuse. Even a successful DDoS against these endpoints only wastes bandwidth, not API credits.
**Status**: Implemented ✓

## Pending Decisions

### P001: Cloud provider for production (partially resolved)
**Options**: OVHcloud VPS still planned for Phase 7. For now, Railway + Neon + R2 works.

### P002: Domain name
**Options**: doornegar.com, doornegar.ir, doornegar.org — need to check availability and Iranian domain regulations. **Required before Cloudflare setup**.

### P003: Image storage (resolved)
**Resolved**: Cloudflare R2 (see D008).

### P004: How to handle rater disagreements
**Options**: Majority vote, weighted by rater trust score, flagged for admin review. Not yet needed (no raters active).

### P005: OpenAI hard spending cap
**Decision needed**: What monthly cap to set. Current spend is ~$1-5/month. Suggested: $30/month hard, $15/month soft alert. **Needs Parham to set on OpenAI dashboard.**
