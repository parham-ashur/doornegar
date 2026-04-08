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

## Pending Decisions

### P001: Cloud provider for production
**Options**: OVHcloud VPS (decided), but specifics TBD — which plan, which region, managed DB or self-hosted?

### P002: Domain name
**Options**: doornegar.com, doornegar.ir, doornegar.org — need to check availability and Iranian domain regulations.

### P003: Image storage in production
**Options**: VPS filesystem, Vercel Blob, Cloudflare R2, MinIO on VPS. Need to decide based on cost and complexity.

### P004: How to handle rater disagreements
**Options**: Majority vote, weighted by rater trust score, flagged for admin review. Not yet needed (no raters active).
