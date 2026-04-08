# Risk Register

| ID | Risk | Likelihood | Impact | Mitigation | Owner | Status |
|----|------|-----------|--------|------------|-------|--------|
| R1 | **Iranian state blocks Telegram API** | Medium | High | Maintain RSS fallback, use proxy/VPN for Telegram | Parham | Monitor |
| R2 | **OpenAI API costs exceed budget** | Medium | Medium | Monitor usage, set spending limits, consider local LLM fallback | Parham | Monitor |
| R3 | **Source websites geo-block our server** | High | Medium | Use proxy for geo-blocked sources, Telegram as backup | Claude | Partial mitigation |
| R4 | **Raters don't engage** | Medium | Medium | Start with close contacts, make rating UX frictionless | Parham | Not started |
| R5 | **LLM clustering merges unrelated events** | Medium | Low | Stricter prompts, human review, rater feedback loop | Claude | Mitigated |
| R6 | **Security: API keys exposed** | Low | Critical | .gitignore for .env, rotate keys if exposed, use env vars in CI | Both | Active |
| R7 | **Production database data loss** | Low | Critical | Automated daily backups, test restore procedure | Parham | Not started |
| R8 | **Telegram session expires** | Medium | Medium | Re-authenticate, document the process in RUNBOOK | Parham | Documented |
| R9 | **Legal risk: content aggregation** | Low | High | Fair use (linking, not copying), attribute sources | Parham | Monitor |
| R10 | **User safety: Iranian raters at risk** | Medium | Critical | No public user data, encrypted connections, no user tracking | Both | Designed |
| R11 | **Railway/Vercel free tier limits** | Medium | Medium | OVHcloud migration planned | Parham | In progress |
| R12 | **Single point of failure: one developer (Claude)** | Medium | High | Document everything, use standard tools, keep code clean | Both | Mitigated by docs |

## Risk Response Plan

### If R1 happens (Telegram blocked):
1. Fall back to RSS-only ingestion
2. Set up a proxy server in a non-blocked region
3. Consider scraping website versions of Telegram channels

### If R2 happens (costs too high):
1. Reduce clustering frequency (every 6h instead of 30min)
2. Switch to cheaper model (gpt-4o-mini is already cheapest)
3. Cache summaries aggressively (already doing this)
4. Consider local LLM (Llama 3) for non-critical tasks

### If R7 happens (data loss):
1. Restore from latest backup
2. Re-run pipeline to recover articles (RSS feeds have history)
3. Telegram posts cannot be recovered — prioritize backup automation

### If R10 happens (rater safety concern):
1. All rater accounts use pseudonyms
2. No real names or locations stored
3. All connections over HTTPS
4. Database encrypted at rest (Neon default, configure on VPS)
5. No analytics or tracking pixels
