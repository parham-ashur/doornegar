# API Cost Log

Tracks estimated OpenAI API costs per maintenance run.

## Current cost model (2026-04-12, post embedding-prefilter + analyst-factors)

### Per-task breakdown (monthly, 1 maintenance run/day)

| Task | Model | Tokens/run (approx) | Cost/run | Cost/month |
|---|---|---|---|---|
| Clustering (embedding pre-filter → LLM confirm) | gpt-5-mini | ~40K in + ~2K out | $0.014 | ~$0.42 |
| Embeddings (articles + centroids) | text-embedding-3-small | ~20K tokens | $0.0004 | ~$0.05 |
| Title translation backfill (up to 300/run) | gpt-4.1-nano | ~15K in + ~15K out | $0.008 | ~$0.24 |
| Bias scoring (up to 150 articles/run, cache-eligible prompt) | gpt-4o-mini | ~400K in + ~75K out | $0.105 | ~$3.15 |
| Story analysis — long tail (~5-10 new/run) | gpt-4o-mini | ~60K in + ~15K out | $0.018 | ~$0.54 |
| Story analysis — top-16 premium + analyst factors (~1-3 new/run) | gpt-5-mini | ~22K in + ~8K out | $0.022 | ~$0.66 |
| Maintenance housekeeping (no LLM) | — | — | $0 | $0 |
| **Total** | | | **~$0.17** | **~$5/month** |

**Notes**:
- Embedding pre-filter reduces clustering LLM calls (only stories with cosine ≥ 0.30 sent to LLM).
- Analyst factors add ~500 extra tokens per premium story but only run for top-16 (not top-30).
- Prompt caching on `gpt-4o-mini` gives 50% discount on cached input; on `gpt-5-mini` / `gpt-4.1-nano` it's 90%. The bias scoring prompt has a 2,200-token static prefix so subsequent calls within a run benefit.
- Force re-summarize via dashboard ("Refresh 16" button) always uses the premium model: ~$0.80-1.50 per one-shot refresh.
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
| 2026-04-11 22:46 | auto-maintenance | Est. ~$0.01-0.05 | Cluster + Summarize + Translate |
| 2026-04-12 09:19 | auto-maintenance | Est. ~$0.01-0.05 | Cluster + Summarize + Translate |
| 2026-04-12 13:20 | auto-maintenance | Est. ~$0.01-0.05 | Cluster + Summarize + Translate |
| 2026-04-12 17:22 | auto-maintenance | Est. ~$0.01-0.05 | Cluster + Summarize + Translate |
| 2026-04-12 21:24 | auto-maintenance | Est. ~$0.01-0.05 | Cluster + Summarize + Translate |
| 2026-04-13 01:26 | auto-maintenance | Est. ~$0.01-0.05 | Cluster + Summarize + Translate |
| 2026-04-13 11:52 | auto-maintenance | Est. ~$0.01-0.05 | Cluster + Summarize + Translate |
| 2026-04-13 15:54 | auto-maintenance | Est. ~$0.01-0.05 | Cluster + Summarize + Translate |
| 2026-04-13 19:55 | auto-maintenance | Est. ~$0.01-0.05 | Cluster + Summarize + Translate |
| 2026-04-14 07:58 | auto-maintenance | Est. ~$0.01-0.05 | Cluster + Summarize + Translate |
| 2026-04-14 11:58 | auto-maintenance | Est. ~$0.01-0.05 | Cluster + Summarize + Translate |
| 2026-04-14 15:58 | auto-maintenance | Est. ~$0.01-0.05 | Cluster + Summarize + Translate |
| 2026-04-14 19:58 | auto-maintenance | Est. ~$0.01-0.05 | Cluster + Summarize + Translate |
| 2026-04-14 23:58 | auto-maintenance | Est. ~$0.01-0.05 | Cluster + Summarize + Translate |
| 2026-04-15 09:32 | auto-maintenance | Est. ~$0.01-0.05 | Cluster + Summarize + Translate |
| 2026-04-15 13:33 | auto-maintenance | Est. ~$0.01-0.05 | Cluster + Summarize + Translate |
| 2026-04-15 17:33 | auto-maintenance | Est. ~$0.01-0.05 | Cluster + Summarize + Translate |
| 2026-04-15 21:34 | auto-maintenance | Est. ~$0.01-0.05 | Cluster + Summarize + Translate |
| 2026-04-16 10:57 | auto-maintenance | Est. ~$0.01-0.05 | Cluster + Summarize + Translate |
| 2026-04-16 14:57 | auto-maintenance | Est. ~$0.01-0.05 | Cluster + Summarize + Translate |
| 2026-04-16 18:58 | auto-maintenance | Est. ~$0.01-0.05 | Cluster + Summarize + Translate |
| 2026-04-16 22:58 | auto-maintenance | Est. ~$0.01-0.05 | Cluster + Summarize + Translate |
| 2026-04-17 08:14 | auto-maintenance | Est. ~$0.01-0.05 | Cluster + Summarize + Translate |
