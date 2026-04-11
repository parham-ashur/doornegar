# API Cost Log

Tracks estimated OpenAI API costs per maintenance run.

## Current cost model (2026-04-11, post 3-tier refactor)

### Per-task breakdown (monthly, 1 maintenance run/day)

| Task | Model | Tokens/run (approx) | Cost/run | Cost/month |
|---|---|---|---|---|
| Clustering (matching + new cluster creation) | gpt-5-mini | ~50K in + ~2K out | $0.016 | ~$0.48 |
| Title translation backfill (up to 300/run) | gpt-4.1-nano | ~15K in + ~15K out | $0.008 | ~$0.24 |
| Bias scoring (up to 150 articles/run, cache-eligible prompt) | gpt-4o-mini | ~400K in + ~75K out | $0.105 | ~$3.15 |
| Story analysis — long tail (~5-10 new/run) | gpt-4o-mini | ~60K in + ~15K out | $0.018 | ~$0.54 |
| Story analysis — top-30 premium (~1-3 new/run) | gpt-5-mini | ~18K in + ~6K out | $0.017 | ~$0.50 |
| Maintenance housekeeping (no LLM) | — | — | $0 | $0 |
| **Total** | | | **~$0.16** | **~$5/month** |

**Notes**:
- Prompt caching on `gpt-4o-mini` gives 50% discount on cached input; on `gpt-5-mini` / `gpt-4.1-nano` it's 90%. The bias scoring prompt has a 2,200-token static prefix so subsequent calls within a run benefit.
- Force re-summarize via dashboard ("Refresh 30" button) always uses the premium model: ~$1-2 per one-shot refresh.
- Expected monthly total with normal usage + occasional manual refreshes: **~$8-10/month**.
- Cost can spike during backlog clearing (multiple Run Maintenance clicks in a day).

### Pre-refactor baseline (2026-04-11, uniform gpt-5-mini, all tasks)
- Total estimated: **~$12-15/month**
- Why we moved away: quality didn't meaningfully differ between gpt-5-mini and gpt-4o-mini on bias scoring + long-tail summaries, so the extra cost was wasted.


| Date | Trigger | Est. Cost | Operations |
|------|---------|-----------|------------|
| 2026-04-08 12:52 | auto-maintenance | Est. ~$0.01-0.05 | Cluster + Summarize + Translate |
| 2026-04-08 16:02 | auto-maintenance | Est. ~$0.01-0.05 | Cluster + Summarize + Translate |
| 2026-04-08 20:28 | auto-maintenance | Est. ~$0.01-0.05 | Cluster + Summarize + Translate |
| 2026-04-09 07:51 | auto-maintenance | Est. ~$0.01-0.05 | Cluster + Summarize + Translate |
| 2026-04-09 11:58 | auto-maintenance | Est. ~$0.01-0.05 | Cluster + Summarize + Translate |
| 2026-04-09 16:07 | auto-maintenance | Est. ~$0.01-0.05 | Cluster + Summarize + Translate |
| 2026-04-09 20:16 | auto-maintenance | Est. ~$0.01-0.05 | Cluster + Summarize + Translate |
| 2026-04-10 00:24 | auto-maintenance | Est. ~$0.01-0.05 | Cluster + Summarize + Translate |
| 2026-04-10 07:37 | auto-maintenance | Est. ~$0.01-0.05 | Cluster + Summarize + Translate |
| 2026-04-10 11:55 | auto-maintenance | Est. ~$0.01-0.05 | Cluster + Summarize + Translate |
| 2026-04-10 16:29 | auto-maintenance | Est. ~$0.01-0.05 | Cluster + Summarize + Translate |
| 2026-04-10 20:48 | auto-maintenance | Est. ~$0.01-0.05 | Cluster + Summarize + Translate |
| 2026-04-11 12:37 | auto-maintenance | Est. ~$0.01-0.05 | Cluster + Summarize + Translate |
| 2026-04-11 17:20 | auto-maintenance | Est. ~$0.01-0.05 | Cluster + Summarize + Translate |
