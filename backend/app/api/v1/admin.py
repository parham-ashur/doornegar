"""Admin endpoints for managing ingestion and NLP pipeline."""

import asyncio
import logging
import os
import re
import traceback
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy import text as _sa_text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db


async def require_admin(authorization: str = Header("")) -> None:
    """Simple token-based admin auth. Set ADMIN_TOKEN env var."""
    admin_token = getattr(settings, "admin_token", "") or ""
    if not admin_token:
        # No token configured — block all admin access in production
        if settings.environment == "production":
            raise HTTPException(status_code=403, detail="Admin access disabled")
        return  # Allow in development
    token = authorization.replace("Bearer ", "").strip()
    if token != admin_token:
        raise HTTPException(status_code=401, detail="Invalid admin token")
from app.models.article import Article
from app.models.bias_score import BiasScore
from app.models.ingestion_log import IngestionLog
from app.models.social import TelegramChannel, TelegramPost
from app.models.source import Source
from app.models.story import Story

router = APIRouter(dependencies=[Depends(require_admin)])
logger = logging.getLogger(__name__)

# Path to maintenance log (relative to backend/)
MAINTENANCE_LOG_PATH = Path(__file__).parent.parent.parent.parent / "maintenance.log"


async def _get_maintenance_info(db: AsyncSession) -> dict:
    """Return last maintenance run info from three sources (in priority order):

    1. In-memory STATE (accurate for runs in the current container lifetime)
    2. DB evidence (survives deploys — looks at max(ingested_at) as a proxy
       for "when did the pipeline last run?")
    3. File fallback (local dev only)

    The key insight: in-memory state resets on every Railway deploy, and
    the log file is ephemeral. The DB is the only durable source. We use
    max(Article.ingested_at) as a reliable proxy because step_ingest is
    always the first step — if it ran, the pipeline ran.
    """
    info = {"last_run": None, "last_result": "unknown", "next_run_approx": None}

    # ── 1. In-memory state (current container only) ─────────────────
    try:
        from app.services import maintenance_state as _ms

        state = _ms.STATE
        status = state.get("status")
        started = state.get("started_at")

        if status == "running" and started:
            info["last_run"] = started
            info["last_result"] = "in_progress_or_incomplete"
            return info

        if status in ("success", "error") and started:
            info["last_run"] = started
            any_error = any(s.get("status") != "ok" for s in state.get("steps", []))
            info["last_result"] = "partial_success" if (status == "error" or any_error) else "success"
            try:
                dt = datetime.fromisoformat(started.replace("Z", "+00:00"))
                info["next_run_approx"] = (dt + timedelta(hours=24)).isoformat()
            except (ValueError, AttributeError):
                pass
            return info
    except Exception as e:
        logger.warning("Could not read maintenance state file: %s", e)

    # ── 2. DB evidence (survives deploys) ───────────────────────────
    try:
        latest_ingested = (await db.execute(
            select(func.max(Article.ingested_at))
        )).scalar()

        if latest_ingested:
            info["last_run"] = latest_ingested.isoformat()
            hours_ago = (datetime.now(timezone.utc) - latest_ingested).total_seconds() / 3600
            info["last_result"] = "success" if hours_ago < 26 else "unknown"
            info["next_run_approx"] = (latest_ingested + timedelta(hours=24)).isoformat()
            return info
    except Exception as e:
        logger.warning(f"Could not query DB for maintenance info: {e}")

    # ── 3. File fallback (local dev) ────────────────────────────────
    if MAINTENANCE_LOG_PATH.exists():
        try:
            lines = MAINTENANCE_LOG_PATH.read_text(encoding="utf-8", errors="replace").splitlines()[-200:]
            last_start = None
            for line in lines:
                if "Maintenance started at" in line:
                    m = re.match(r"(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})", line)
                    if m:
                        last_start = m.group(1)
            if last_start:
                dt = datetime.strptime(last_start, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
                info["last_run"] = dt.isoformat()
                info["last_result"] = "success"
                info["next_run_approx"] = (dt + timedelta(hours=24)).isoformat()
        except Exception as e:
            logger.warning("Could not parse maintenance log file: %s", e)

    return info


# Simple in-memory cache for the dashboard response. Avoids hitting Neon
# with 10+ aggregate queries on every poll (was 3-5s, now 30s, but still
# wasteful if multiple browser tabs are open).
_dashboard_cache: dict = {"data": None, "expires": 0}
_DASHBOARD_CACHE_TTL = 300  # seconds (5 min — saves ~80% of dashboard DB queries)


@router.get("/dashboard")
async def get_dashboard(db: AsyncSession = Depends(get_db)):
    """Comprehensive dashboard data: counts, maintenance status, costs, issues.

    Cached for 60 seconds to reduce Neon network transfer. The dashboard
    frontend polls every 30s, so most requests hit the cache.
    """
    import time as _time
    if _dashboard_cache["data"] and _time.time() < _dashboard_cache["expires"]:
        return _dashboard_cache["data"]

    # --- Data counts ---
    now = datetime.now(timezone.utc)
    day_ago = now - timedelta(hours=24)

    total_articles = (await db.execute(select(func.count(Article.id)))).scalar() or 0
    articles_24h = (await db.execute(
        select(func.count(Article.id)).where(Article.ingested_at >= day_ago)
    )).scalar() or 0
    with_fa_title = (await db.execute(
        select(func.count(Article.id)).where(Article.title_fa.isnot(None))
    )).scalar() or 0
    without_fa_title = total_articles - with_fa_title

    total_stories = (await db.execute(select(func.count(Story.id)))).scalar() or 0
    visible_stories = (await db.execute(
        select(func.count(Story.id)).where(Story.article_count >= 5)
    )).scalar() or 0
    stories_with_summary = (await db.execute(
        select(func.count(Story.id)).where(Story.summary_fa.isnot(None))
    )).scalar() or 0
    hidden_stories = total_stories - visible_stories
    new_stories_24h = (await db.execute(
        select(func.count(Story.id)).where(Story.created_at >= day_ago)
    )).scalar() or 0
    frozen_total = (await db.execute(
        select(func.count(Story.id)).where(Story.frozen_at.isnot(None))
    )).scalar() or 0
    frozen_24h = (await db.execute(
        select(func.count(Story.id)).where(Story.frozen_at >= day_ago)
    )).scalar() or 0
    archived_total = (await db.execute(
        select(func.count(Story.id)).where(Story.archived_at.isnot(None))
    )).scalar() or 0
    archived_24h = (await db.execute(
        select(func.count(Story.id)).where(Story.archived_at >= day_ago)
    )).scalar() or 0

    total_channels = (await db.execute(select(func.count(TelegramChannel.id)))).scalar() or 0
    active_channels = (await db.execute(
        select(func.count(TelegramChannel.id)).where(TelegramChannel.is_active.is_(True))
    )).scalar() or 0
    total_posts = (await db.execute(select(func.count(TelegramPost.id)))).scalar() or 0
    posts_24h = (await db.execute(
        select(func.count(TelegramPost.id)).where(TelegramPost.date >= day_ago)
    )).scalar() or 0

    total_sources = (await db.execute(select(func.count(Source.id)))).scalar() or 0
    state_sources = (await db.execute(
        select(func.count(Source.id)).where(Source.state_alignment == "state")
    )).scalar() or 0
    diaspora_sources = (await db.execute(
        select(func.count(Source.id)).where(Source.state_alignment == "diaspora")
    )).scalar() or 0
    independent_sources = (await db.execute(
        select(func.count(Source.id)).where(Source.state_alignment == "independent")
    )).scalar() or 0
    other_sources = total_sources - state_sources - diaspora_sources - independent_sources

    total_bias = (await db.execute(select(func.count(BiasScore.id)))).scalar() or 0
    bias_pct = round(total_bias * 100 / max(total_articles, 1))

    # --- Maintenance info ---
    maintenance = await _get_maintenance_info(db)

    # --- Issues detection ---
    issues = []
    actions_needed = []

    if without_fa_title > 0:
        severity = "warning" if without_fa_title > 50 else "info"
        issues.append({
            "severity": severity,
            "message": f"{without_fa_title} articles without Farsi title",
        })
        if without_fa_title > 50:
            actions_needed.append("Run: python manage.py process (translate remaining titles)")

    # Freshness check
    latest_ingested = (await db.execute(
        select(func.max(Article.ingested_at))
    )).scalar()
    if latest_ingested:
        hours_ago = (now - latest_ingested).total_seconds() / 3600
        if hours_ago > 24:
            issues.append({
                "severity": "error",
                "message": f"Last ingestion: {hours_ago:.0f}h ago (>24h — stale data)",
            })
            actions_needed.append("Run: python manage.py ingest (fetch new articles)")
        elif hours_ago > 6:
            issues.append({
                "severity": "warning",
                "message": f"Last ingestion: {hours_ago:.0f}h ago",
            })
        else:
            issues.append({
                "severity": "info",
                "message": f"Data fresh: last ingested {hours_ago:.1f}h ago",
            })
        freshness_hours = hours_ago
    else:
        issues.append({"severity": "error", "message": "No articles ingested yet"})
        freshness_hours = None
        actions_needed.append("Run: python manage.py pipeline (initial setup)")

    # Stories without summary
    missing_summaries = visible_stories - stories_with_summary
    if missing_summaries > 0:
        issues.append({
            "severity": "warning",
            "message": f"{missing_summaries} visible stories without summary",
        })
        actions_needed.append("Run: python manage.py summarize (generate summaries)")

    # Low bias coverage
    if bias_pct < 20 and total_articles > 100:
        issues.append({
            "severity": "info",
            "message": f"Bias score coverage: {bias_pct}% of articles",
        })
        actions_needed.append("Run: python manage.py score (score more articles)")

    # ── Pipeline health checks (added after the 2026-04-27 NLP UnboundLocalError
    #     incident: 14d of silent damage like the 2026-04-24 zero-embedding bug
    #     because no metric watched the symptoms). Each check converts a known
    #     silent-failure pattern into a visible Attention-list item.

    # H1 — clustering stalled. articles_24h > 0 but new_stories_24h == 0 means
    # fresh ingestion is happening yet not a single new cluster formed → matcher
    # or cluster_new is broken (typically because embeddings are NULL).
    if articles_24h >= 50 and new_stories_24h == 0:
        issues.append({
            "severity": "error",
            "message": (
                f"0 new stories in 24h despite {articles_24h} new articles — "
                "clustering is producing nothing. Check NLP step + embedding health."
            ),
        })
        actions_needed.append("Check /admin/maintenance/logs and /admin/embedding/health")

    # H2 — embedding null rate. Sample last 24h: if >10% of articles have NULL
    # embeddings, the matcher can't find candidates and cluster_new can't group.
    embed_row = (await db.execute(_sa_text(
        "SELECT count(*) AS total, "
        "count(*) FILTER (WHERE embedding IS NULL) AS nulls "
        "FROM articles WHERE ingested_at >= NOW() - interval '24 hours'"
    ))).one()
    embed_total = embed_row.total or 0
    embed_nulls = embed_row.nulls or 0
    embed_null_pct = round(100 * embed_nulls / max(1, embed_total), 1)
    if embed_total >= 50 and embed_null_pct >= 50:
        issues.append({
            "severity": "error",
            "message": (
                f"{embed_nulls}/{embed_total} ({embed_null_pct}%) articles in last 24h "
                "have NULL embedding — NLP pipeline likely crashing on import or first query."
            ),
        })
    elif embed_total >= 50 and embed_null_pct >= 10:
        issues.append({
            "severity": "warning",
            "message": (
                f"{embed_nulls}/{embed_total} ({embed_null_pct}%) articles in last 24h "
                "have NULL embedding — NLP pipeline degraded."
            ),
        })

    # H3 — last maintenance run had failed steps. Surface the count + names so
    # the operator sees errored steps without scrolling through Railway logs.
    last_run = (await db.execute(_sa_text(
        "SELECT run_at, steps FROM maintenance_logs "
        "ORDER BY run_at DESC LIMIT 1"
    ))).first()
    if last_run and last_run.steps:
        import json as _hjson
        try:
            steps = _hjson.loads(last_run.steps) if isinstance(last_run.steps, str) else last_run.steps
        except Exception:
            steps = None
        if isinstance(steps, list):
            failed = [s for s in steps if isinstance(s, dict) and s.get("status") == "error"]
            if failed:
                names = ", ".join(s.get("name", "?")[:40] for s in failed[:3])
                more = f" (+{len(failed) - 3} more)" if len(failed) > 3 else ""
                issues.append({
                    "severity": "error" if len(failed) >= 3 else "warning",
                    "message": f"Last maintenance had {len(failed)} failed step(s): {names}{more}",
                })

    response = {
        "data": {
            "articles": {
                "total": total_articles,
                "last_24h": articles_24h,
                "with_farsi_title": with_fa_title,
                "without_farsi_title": without_fa_title,
            },
            "stories": {
                "total": total_stories,
                "visible": visible_stories,
                "with_summary": stories_with_summary,
                "hidden": hidden_stories,
                "new_24h": new_stories_24h,
                "frozen": frozen_total,
                "frozen_24h": frozen_24h,
                "archived": archived_total,
                "archived_24h": archived_24h,
            },
            "telegram": {
                "channels": total_channels,
                "active": active_channels,
                "total_posts": total_posts,
                "posts_24h": posts_24h,
            },
            "sources": {
                "total": total_sources,
                "state": state_sources,
                "diaspora": diaspora_sources,
                "independent": independent_sources,
                "other": other_sources,
            },
            "bias_scores": {
                "total": total_bias,
                "coverage_pct": bias_pct,
            },
        },
        "maintenance": maintenance,
        "api_costs": {
            "note": "برای هزینه دقیق داشبورد OpenAI را بررسی کنید",
            "estimated_monthly": "$8-10",
            "clustering_per_run": "~$0.02",
            "summary_per_story": "~$0.01",
        },
        "issues": issues,
        "actions_needed": actions_needed,
        "freshness_hours": freshness_hours,
    }

    # Cache for 60s to reduce Neon transfer on repeated dashboard polls
    _dashboard_cache["data"] = response
    _dashboard_cache["expires"] = _time.time() + _DASHBOARD_CACHE_TTL
    return response


@router.post("/force-resummarize")
async def force_resummarize(
    limit: int = Query(5, ge=1, le=200),
    mode: str = Query("immediate", pattern="^(immediate|queue)$"),
    order: str = Query("trending", pattern="^(trending|recent)$"),
    db: AsyncSession = Depends(get_db),
):
    """Force re-generation of summaries with the current model.

    Modes:
      - "immediate" (default): kicks off a BACKGROUND task that clears
        summary_fa and runs story_analysis inline for each story, then
        returns immediately with a job id. Poll /admin/force-resummarize/status
        for progress. Previously this blocked the HTTP request for the
        full duration, which got killed by Cloudflare's 100s edge timeout
        on runs longer than 3-4 stories.
      - "queue": just clears summary_fa on N stories so the next maintenance
        run picks them up via step_summarize. Fast response, no background
        work.

    Order:
      - "trending" (default): same order as the homepage /trending endpoint
        (priority DESC, trending_score DESC). Ensures the stories visible
        to users get refreshed first.
      - "recent": most recently updated/published first.

    Only picks visible, non-edited stories (article_count >= 5,
    is_edited=False). is_edited stories stay untouched so Niloofar's
    hand-curation isn't clobbered.
    """
    import json as _json
    from sqlalchemy.orm import selectinload
    from app.models.article import Article
    from app.models.story import Story

    # Protect Niloofar's edits: the endpoint used to overwrite every story
    # with a fresh LLM pass, which wiped hand-curated titles, summaries,
    # and bias comparisons. Now we skip `is_edited=True` — those stories
    # need to be re-edited through Niloofar-in-chat if Parham wants new
    # depth, not through the auto prompt.
    query = (
        select(Story)
        .options(selectinload(Story.articles).selectinload(Article.source))
        .where(Story.article_count >= 5)
        .where(Story.is_edited.is_(False))
    )
    if order == "trending":
        # Match /api/v1/stories/trending: priority DESC, trending_score DESC
        query = query.order_by(Story.priority.desc(), Story.trending_score.desc())
    else:
        query = query.order_by(
            Story.updated_at.desc().nullslast(),
            Story.first_published_at.desc().nullslast(),
        )
    query = query.limit(limit)

    result = await db.execute(query)
    stories = list(result.scalars().all())

    if not stories:
        return {"status": "ok", "cleared": 0, "regenerated": 0, "message": "No visible stories found"}

    if mode == "queue":
        for story in stories:
            story.summary_fa = None
        await db.commit()
        return {
            "status": "ok",
            "cleared": len(stories),
            "regenerated": 0,
            "message": f"Cleared summary_fa on {len(stories)} stories. Next maintenance run will regenerate them.",
            "story_ids": [str(s.id) for s in stories],
        }

    # Immediate mode: kick off a BACKGROUND task and return right away.
    # Always use the PREMIUM model — if Parham is manually regenerating,
    # it's worth the cost for the best output.
    from app.services import force_resummarize_state as _frs

    # Refuse to start a second concurrent job — one LLM loop at a time.
    if _frs.STATE.get("status") == "running":
        return {
            "status": "busy",
            "message": f"A force-resummarize job is already running ({_frs.STATE.get('processed', 0)}/{_frs.STATE.get('total', 0)}). Wait for it to finish or poll /admin/force-resummarize/status.",
            "job_id": _frs.STATE.get("job_id"),
        }

    chosen_model = settings.story_analysis_premium_model
    story_ids = [str(s.id) for s in stories]
    job_id = _frs.start_job(total=len(stories), story_ids=story_ids, model=chosen_model)

    # Detach the stories from this request's session before handing them
    # to the background task — the background task opens its own session
    # so it doesn't inherit this one's lifecycle.
    story_id_list = list(story_ids)

    import asyncio
    asyncio.create_task(_run_force_resummarize_job(story_id_list, chosen_model))

    return {
        "status": "ok",
        "job_id": job_id,
        "cleared": len(stories),
        "regenerated": 0,
        "failed": 0,
        "message": f"Started background resummarize of {len(stories)} stories with {chosen_model}. Poll /admin/force-resummarize/status for progress.",
        "story_ids": story_ids,
    }


async def _run_force_resummarize_job(story_ids: list[str], chosen_model: str) -> None:
    """Background worker that re-runs story_analysis for each story id.

    Opens its own DB session and updates the shared force_resummarize_state
    dict as it processes. Survives HTTP-client timeouts (which is the whole
    point). Dies if the backend restarts — next status poll returns idle.
    At the end, writes a durable row into maintenance_logs so the result
    (including per-story failures) outlives a Railway redeploy.
    """
    import json as _json
    from datetime import datetime, timezone
    from sqlalchemy import text
    from sqlalchemy.orm import selectinload
    from app.database import async_session
    from app.models.article import Article
    from app.models.story import Story
    from app.services import force_resummarize_state as _frs
    from app.services.story_analysis import generate_story_analysis

    # Collect detailed per-story outcomes so we can write them to
    # maintenance_logs on completion. STATE only keeps the last 10 errors;
    # this captures everything.
    story_results: list[dict] = []
    started_at = datetime.now(timezone.utc)
    fatal_error: str | None = None

    try:
        for sid in story_ids:
            async with async_session() as db:
                r = await db.execute(
                    select(Story)
                    .options(selectinload(Story.articles).selectinload(Article.source))
                    .where(Story.id == sid)
                )
                story = r.scalars().first()
                if not story:
                    _frs.mark_story_done(success=False, error_msg=f"{sid[:8]}: story not found")
                    story_results.append({
                        "story_id": sid,
                        "title": None,
                        "article_count": 0,
                        "status": "not_found",
                        "error": "story not found",
                    })
                    continue

                _frs.mark_story_start(story.title_fa or story.title_en or sid[:8])

                # Per-article content cap: 3000 chars for premium runs. At
                # 6000 the prompt was blowing past the model's comfortable
                # token budget for 30+ article clusters, producing
                # truncated JSON and silent failures. 3000 halves the input
                # size and lets big clusters fit while still giving the
                # LLM enough excerpt to read coverage nuance.
                CONTENT_CAP = 3000
                articles_info = [
                    {
                        "title": a.title_original or a.title_fa or a.title_en or "",
                        "content": (a.content_text or a.summary or "")[:CONTENT_CAP],
                        "source_name_fa": a.source.name_fa if a.source else "نامشخص",
                        "state_alignment": a.source.state_alignment if a.source else "",
                        "published_at": a.published_at.isoformat() if a.published_at else "",
                    }
                    for a in story.articles
                ]
                try:
                    analysis = await generate_story_analysis(
                        story, articles_info,
                        model=chosen_model,
                        include_analyst_factors=True,
                    )
                    story.summary_fa = analysis.get("summary_fa")
                    # Preserve manual_image_url set via update_image
                    manual_image = None
                    if story.summary_en:
                        try:
                            _prev = _json.loads(story.summary_en)
                            manual_image = _prev.get("manual_image_url")
                        except Exception:
                            pass
                    extras = {
                        "state_summary_fa": analysis.get("state_summary_fa"),
                        "diaspora_summary_fa": analysis.get("diaspora_summary_fa"),
                        "independent_summary_fa": analysis.get("independent_summary_fa"),
                        "bias_explanation_fa": analysis.get("bias_explanation_fa"),
                        "scores": analysis.get("scores"),
                        "narrative": analysis.get("narrative"),
                        "dispute_score": analysis.get("dispute_score"),
                        "loaded_words": analysis.get("loaded_words"),
                        "narrative_arc": analysis.get("narrative_arc"),
                        "source_neutrality": analysis.get("source_neutrality"),
                        "llm_model_used": chosen_model,
                    }
                    if manual_image:
                        extras["manual_image_url"] = manual_image
                    if analysis.get("analyst"):
                        extras["analyst"] = analysis["analyst"]
                    story.summary_en = _json.dumps(extras, ensure_ascii=False)
                    await db.commit()
                    _frs.mark_story_done(success=True)
                    story_results.append({
                        "story_id": sid,
                        "title": story.title_fa,
                        "article_count": story.article_count,
                        "status": "ok",
                        "error": None,
                    })
                except Exception as e:
                    err_msg = str(e)
                    err_type = type(e).__name__
                    _frs.mark_story_done(success=False, error_msg=f"{sid[:8]}: {err_msg}")
                    logger.warning(f"Force-resummarize failed for {sid} ({err_type}): {err_msg}")
                    story_results.append({
                        "story_id": sid,
                        "title": story.title_fa,
                        "article_count": story.article_count,
                        "status": "failed",
                        "error_type": err_type,
                        "error": err_msg[:500],
                    })
        _frs.finish_job()
    except Exception as e:
        fatal_error = str(e)
        logger.exception("Force-resummarize background job crashed")
        _frs.finish_job(error=fatal_error)

    # Write a durable summary row to maintenance_logs. Survives Railway
    # restart so we can diagnose failures after the fact.
    try:
        async with async_session() as db:
            finished_at = datetime.now(timezone.utc)
            elapsed_s = (finished_at - started_at).total_seconds()
            total = len(story_ids)
            regenerated = sum(1 for r in story_results if r.get("status") == "ok")
            failed = sum(1 for r in story_results if r.get("status") in ("failed", "not_found"))
            results_payload = {
                "mode": "force_resummarize",
                "model": chosen_model,
                "total": total,
                "regenerated": regenerated,
                "failed": failed,
                "stories": story_results,
            }
            await db.execute(
                text(
                    "INSERT INTO maintenance_logs (id, run_at, status, elapsed_s, results, error) "
                    "VALUES (gen_random_uuid(), :run_at, :status, :elapsed_s, CAST(:results AS JSONB), :error)"
                ),
                {
                    "run_at": started_at,
                    "status": "force_resummarize_error" if fatal_error else (
                        "force_resummarize_partial" if failed > 0 else "force_resummarize_ok"
                    ),
                    "elapsed_s": elapsed_s,
                    "results": _json.dumps(results_payload, ensure_ascii=False),
                    "error": fatal_error,
                },
            )
            await db.commit()
    except Exception as log_err:
        logger.exception(f"Failed to persist force-resummarize log: {log_err}")


@router.get("/force-resummarize/status")
async def force_resummarize_status():
    """Current state of the /admin/force-resummarize background job.

    Shape:
    {
      status: idle | running | success | error,
      job_id: str | null,
      started_at, started_at_iso, elapsed_s,
      total, processed, regenerated, failed,
      current_story_title: str | null,
      model: str | null,
      errors: [str, ...],
      error: str | null,
    }
    """
    from app.services import force_resummarize_state as _frs
    return _frs.snapshot()


@router.get("/recently-summarized")
async def recently_summarized(
    limit: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    """List stories ordered by updated_at desc, with summary previews.

    Useful for verifying that a new LLM model's output is live — sort by
    most recently updated and read the new-style prompt signals
    (guillemet-quoted terms, explicit tone labels, etc.) in the
    bias_explanation_fa field.
    """
    import json as _json
    from app.models.story import Story

    result = await db.execute(
        select(Story)
        .where(Story.summary_fa.isnot(None))
        .order_by(Story.updated_at.desc())
        .limit(limit)
    )
    stories = list(result.scalars().all())

    items = []
    for s in stories:
        extras: dict = {}
        # State/diaspora/bias extras are stashed in summary_en as JSON
        if s.summary_en:
            try:
                extras = _json.loads(s.summary_en)
            except Exception:
                extras = {}
        analyst = extras.get("analyst")
        items.append({
            "id": str(s.id),
            "title_fa": s.title_fa,
            "updated_at": s.updated_at.isoformat() if s.updated_at else None,
            "article_count": s.article_count,
            "summary_fa_preview": (s.summary_fa or "")[:200],
            "bias_explanation_fa": extras.get("bias_explanation_fa"),
            "has_state_summary": bool(extras.get("state_summary_fa")),
            "has_diaspora_summary": bool(extras.get("diaspora_summary_fa")),
            "has_analyst": bool(analyst),
            "analyst_risk": analyst.get("risk_assessment") if analyst else None,
            "analyst_framing_gap": analyst.get("framing_gap") if analyst else None,
            "analyst_hidden": analyst.get("what_is_hidden") if analyst else None,
        })
    return {"items": items}


@router.get("/diagnostics")
async def diagnostics(db: AsyncSession = Depends(get_db)):
    """Diagnostic info to explain why backfills aren't fully catching up.

    Returns:
    - articles: counts broken down by what's missing
    - bias_eligible: how many articles are eligible for bias scoring
    - llm_keys: which LLM keys are configured (true/false, never the value)
    """
    from app.config import settings
    from sqlalchemy import and_

    total = (await db.execute(select(func.count(Article.id)))).scalar() or 0
    no_title_fa = (await db.execute(
        select(func.count(Article.id)).where(Article.title_fa.is_(None))
    )).scalar() or 0
    no_title_original = (await db.execute(
        select(func.count(Article.id)).where(Article.title_original.is_(None))
    )).scalar() or 0
    no_title_fa_but_has_original = (await db.execute(
        select(func.count(Article.id)).where(
            and_(Article.title_fa.is_(None), Article.title_original.isnot(None))
        )
    )).scalar() or 0
    unprocessed = (await db.execute(
        select(func.count(Article.id)).where(Article.processed_at.is_(None))
    )).scalar() or 0

    # Clustering coverage
    clustered = (await db.execute(
        select(func.count(Article.id)).where(Article.story_id.isnot(None))
    )).scalar() or 0
    has_content = (await db.execute(
        select(func.count(Article.id)).where(
            (Article.content_text.isnot(None)) | (Article.summary.isnot(None))
        )
    )).scalar() or 0

    # Bias-eligible = clustered AND has content
    bias_eligible = (await db.execute(
        select(func.count(Article.id)).where(
            and_(
                Article.story_id.isnot(None),
                (Article.content_text.isnot(None)) | (Article.summary.isnot(None)),
            )
        )
    )).scalar() or 0
    already_scored = (await db.execute(select(func.count(BiasScore.id)))).scalar() or 0

    return {
        "articles": {
            "total": total,
            "no_title_fa": no_title_fa,
            "no_title_original": no_title_original,
            "translatable_now": no_title_fa_but_has_original,
            "unprocessed": unprocessed,
            "clustered_into_story": clustered,
            "has_content_or_summary": has_content,
        },
        "bias": {
            "total_articles": total,
            "eligible_for_scoring": bias_eligible,
            "already_scored": already_scored,
            "remaining_to_score": max(0, bias_eligible - already_scored),
            "coverage_of_eligible_pct": round(already_scored * 100 / max(bias_eligible, 1)),
        },
        "llm_keys": {
            "openai_set": bool(settings.openai_api_key),
            "anthropic_set": bool(settings.anthropic_api_key),
        },
        "notes": [
            "translatable_now = articles the backfill step can actually translate (have title_original but no title_fa)",
            "if translatable_now is small, the remaining no_title_fa articles have broken ingestion (no title_original either)",
            "bias scoring requires: clustered into story AND has content/summary AND LLM key set",
        ],
    }


# Lock so we don't start two maintenance runs at once.
_maintenance_lock = asyncio.Lock()


async def _run_maintenance_background():
    """Run the full maintenance cycle as a background task.

    The per-step progress is tracked in app.services.maintenance_state.STATE
    (populated by auto_maintenance.run_maintenance).
    """
    import sys
    from app.services import maintenance_state

    try:
        backend_dir = str(Path(__file__).parent.parent.parent.parent)
        if backend_dir not in sys.path:
            sys.path.insert(0, backend_dir)
        from auto_maintenance import run_maintenance

        await run_maintenance()
    except Exception as e:
        logger.exception("Background maintenance failed")
        maintenance_state.finish_run("error", error=str(e))


@router.post("/maintenance/run")
async def run_maintenance_endpoint():
    """Kick off a maintenance run in the background and return immediately.

    Poll /maintenance/status to see per-step progress. The previous
    synchronous implementation hit Railway's 2-minute proxy timeout.
    """
    from app.services import maintenance_state as _ms

    async with _maintenance_lock:
        if _ms.STATE.get("status") == "running":
            return {
                "status": "already_running",
                "message": "A maintenance run is already in progress",
                "state": _ms.STATE,
            }
        # Fire and forget — uvicorn keeps the coroutine alive
        asyncio.create_task(_run_maintenance_background())
    return {
        "status": "started",
        "message": "Maintenance is running in the background. Poll /admin/maintenance/status.",
    }


@router.get("/maintenance/logs")
async def maintenance_logs(
    limit: int = Query(5, ge=1, le=20),
    db: AsyncSession = Depends(get_db),
):
    """Return recent maintenance run logs from the database.

    Survives container restarts — use this to check what happened at 4am.
    """
    from sqlalchemy import text
    try:
        result = await db.execute(text(
            "SELECT run_at, status, elapsed_s, results, steps, error "
            "FROM maintenance_logs ORDER BY run_at DESC LIMIT :limit"
        ), {"limit": limit})
        rows = result.all()
        import json as _json
        return [
            {
                "run_at": str(r[0]),
                "status": r[1],
                "elapsed_s": r[2],
                "results": _json.loads(r[3]) if r[3] else None,
                "steps": _json.loads(r[4]) if r[4] else None,
                "error": r[5],
            }
            for r in rows
        ]
    except Exception as e:
        return {"error": str(e), "hint": "Run /admin/create-tables to create the maintenance_logs table"}


@router.get("/maintenance/status")
async def maintenance_status():
    """Return the current maintenance run state (for dashboard polling).

    Shape:
    {
      status: idle | running | success | error,
      started_at, finished_at, elapsed_s,
      current_step: str | null,             # step currently executing
      current_step_started: float | null,
      steps: [{name, status, elapsed_s, stats}, ...],  # completed so far
      results: dict | null,                 # final results (populated at end)
      error: str | null,
    }
    """
    from app.services import maintenance_state as _ms
    import time

    state = dict(_ms.STATE)
    # Add current step elapsed for a live ticker
    if state.get("current_step") and state.get("current_step_started"):
        state["current_step_elapsed_s"] = round(time.time() - state["current_step_started"], 1)
    # Total steps so frontend can show accurate progress bar
    state["total_steps"] = _ms.STATE.get("total_steps", 14)
    return state


@router.post("/ingest/trigger")
async def trigger_ingestion(db: AsyncSession = Depends(get_db)):
    """Manually trigger RSS feed ingestion."""
    try:
        from app.services.ingestion import ingest_all_sources
        stats = await ingest_all_sources(db)
        return {"status": "ok", "stats": stats}
    except Exception as e:
        logger.exception("Ingestion failed")
        return {"status": "error", "error": str(e), "detail": "Check server logs"}


@router.post("/nlp/trigger")
async def trigger_nlp_processing(db: AsyncSession = Depends(get_db)):
    """Manually trigger NLP processing on unprocessed articles."""
    try:
        from app.services.nlp_pipeline import process_unprocessed_articles
        stats = await process_unprocessed_articles(db)
        return {"status": "ok", "stats": stats}
    except Exception as e:
        logger.exception("NLP processing failed")
        return {"status": "error", "error": str(e), "detail": "Check server logs"}


@router.post("/cluster/trigger")
async def trigger_clustering(db: AsyncSession = Depends(get_db)):
    """Manually trigger story clustering."""
    try:
        from app.services.clustering import cluster_articles
        stats = await cluster_articles(db)
        return {"status": "ok", "stats": stats}
    except Exception as e:
        logger.exception("Clustering failed")
        return {"status": "error", "error": str(e), "detail": "Check server logs"}


@router.post("/bias/trigger")
async def trigger_bias_scoring(
    batch_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    """Manually trigger LLM bias scoring on unscored articles."""
    try:
        from app.services.bias_scoring import score_unscored_articles
        stats = await score_unscored_articles(db, batch_size=batch_size)
        return {"status": "ok", "stats": stats}
    except Exception as e:
        logger.exception("Bias scoring failed")
        return {"status": "error", "error": str(e), "detail": "Check server logs"}


@router.get("/sources/stats", dependencies=[Depends(require_admin)])
async def sources_stats(db: AsyncSession = Depends(get_db)):
    """Per-source article counts + freshness for the admin fetch dashboard.

    Returns one row per source with total / 24h / 7d counts and the
    timestamp of the last ingested article.
    """
    now = datetime.now(timezone.utc)
    day_ago = now - timedelta(hours=24)
    week_ago = now - timedelta(days=7)

    result = await db.execute(
        select(
            Source.id,
            Source.slug,
            Source.name_fa,
            Source.name_en,
            Source.state_alignment,
            Source.is_active,
            func.count(Article.id).label("total"),
            func.count(Article.id).filter(Article.ingested_at >= day_ago).label("last_24h"),
            func.count(Article.id).filter(Article.ingested_at >= week_ago).label("last_7d"),
            func.max(Article.ingested_at).label("last_ingested_at"),
        )
        .outerjoin(Article, Article.source_id == Source.id)
        .group_by(Source.id)
        .order_by(Source.name_en)
    )

    rows = []
    for r in result.all():
        last_seen = r.last_ingested_at
        hours_since = None
        if last_seen:
            hours_since = round((now - last_seen).total_seconds() / 3600, 1)
        rows.append({
            "id": str(r.id),
            "slug": r.slug,
            "name_fa": r.name_fa,
            "name_en": r.name_en,
            "state_alignment": r.state_alignment,
            "is_active": r.is_active,
            "total": r.total,
            "last_24h": r.last_24h,
            "last_7d": r.last_7d,
            "last_ingested_at": last_seen.isoformat() if last_seen else None,
            "hours_since_last": hours_since,
        })
    return {"sources": rows, "generated_at": now.isoformat()}


@router.get("/content-type/stats", dependencies=[Depends(require_admin)])
async def content_type_stats(
    days: int = Query(7, ge=1, le=90),
    hours: int | None = Query(None, ge=1, le=2160),
    db: AsyncSession = Depends(get_db),
):
    """Per-source breakdown of how the content-type filter has labelled
    articles. Drives /dashboard/content-filter.

    Window: pass `hours` for sub-day windows (e.g. last hour), otherwise
    `days`. `hours` takes precedence when both are present.

    Returns:
      - rollup: total, kept, dropped, unclassified for the window
      - by_label: count per content_type label
      - sources: per-source rows (top 60 by total) with kept/dropped split
    """
    from app.services.content_type import LABELS

    now = datetime.now(timezone.utc)
    window_start = now - (timedelta(hours=hours) if hours else timedelta(days=days))

    rollup_result = await db.execute(
        select(
            func.count(Article.id).label("total"),
            func.count(Article.id).filter(Article.content_type.is_(None)).label("unclassified"),
            func.count(Article.id).filter(Article.content_type == "news").label("news"),
            func.count(Article.id).filter(Article.content_type == "opinion").label("opinion"),
            func.count(Article.id).filter(Article.content_type == "discussion").label("discussion"),
            func.count(Article.id).filter(Article.content_type == "aggregation").label("aggregation"),
            func.count(Article.id).filter(Article.content_type == "other").label("other"),
        )
        .where(Article.ingested_at >= window_start)
    )
    r = rollup_result.one()
    by_label = {
        "news": int(r.news or 0),
        "opinion": int(r.opinion or 0),
        "discussion": int(r.discussion or 0),
        "aggregation": int(r.aggregation or 0),
        "other": int(r.other or 0),
    }
    total = int(r.total or 0)
    unclassified = int(r.unclassified or 0)
    kept = by_label["news"]
    dropped = total - kept - unclassified

    # Per-source breakdown.
    src_result = await db.execute(
        select(
            Source.id,
            Source.slug,
            Source.name_fa,
            Source.name_en,
            Source.state_alignment,
            Source.content_filters,
            func.count(Article.id).label("total"),
            func.count(Article.id).filter(Article.content_type.is_(None)).label("unclassified"),
            func.count(Article.id).filter(Article.content_type == "news").label("news"),
            func.count(Article.id).filter(Article.content_type == "opinion").label("opinion"),
            func.count(Article.id).filter(Article.content_type == "discussion").label("discussion"),
            func.count(Article.id).filter(Article.content_type == "aggregation").label("aggregation"),
            func.count(Article.id).filter(Article.content_type == "other").label("other"),
        )
        .join(Article, Article.source_id == Source.id)
        .where(Article.ingested_at >= window_start)
        .group_by(Source.id)
        .order_by(func.count(Article.id).desc())
        .limit(60)
    )

    sources_rows = []
    for s in src_result.all():
        s_total = int(s.total or 0)
        s_news = int(s.news or 0)
        s_unclassified = int(s.unclassified or 0)
        s_dropped = s_total - s_news - s_unclassified
        sources_rows.append({
            "id": str(s.id),
            "slug": s.slug,
            "name_fa": s.name_fa,
            "name_en": s.name_en,
            "state_alignment": s.state_alignment,
            "allowed": (s.content_filters or {}).get("allowed", ["news"]),
            "total": s_total,
            "kept": s_news,
            "dropped": s_dropped,
            "unclassified": s_unclassified,
            "by_label": {
                "news": int(s.news or 0),
                "opinion": int(s.opinion or 0),
                "discussion": int(s.discussion or 0),
                "aggregation": int(s.aggregation or 0),
                "other": int(s.other or 0),
            },
        })

    return {
        "window_days": days if not hours else None,
        "window_hours": hours,
        "generated_at": now.isoformat(),
        "rollup": {
            "total": total,
            "kept": kept,
            "dropped": dropped,
            "unclassified": unclassified,
        },
        "by_label": by_label,
        "labels": list(LABELS),
        "sources": sources_rows,
    }


@router.get("/channels/stats", dependencies=[Depends(require_admin)])
async def channels_stats(db: AsyncSession = Depends(get_db)):
    """Per-channel Telegram post counts + freshness for the admin fetch dashboard."""
    now = datetime.now(timezone.utc)
    day_ago = now - timedelta(hours=24)
    week_ago = now - timedelta(days=7)

    result = await db.execute(
        select(
            TelegramChannel.id,
            TelegramChannel.username,
            TelegramChannel.title,
            TelegramChannel.channel_type,
            TelegramChannel.is_active,
            func.count(TelegramPost.id).label("total"),
            func.count(TelegramPost.id).filter(TelegramPost.date >= day_ago).label("last_24h"),
            func.count(TelegramPost.id).filter(TelegramPost.date >= week_ago).label("last_7d"),
            func.max(TelegramPost.date).label("last_post_at"),
        )
        .outerjoin(TelegramPost, TelegramPost.channel_id == TelegramChannel.id)
        .group_by(TelegramChannel.id)
        .order_by(TelegramChannel.username)
    )

    rows = []
    for r in result.all():
        last_seen = r.last_post_at
        hours_since = None
        if last_seen:
            hours_since = round((now - last_seen).total_seconds() / 3600, 1)
        rows.append({
            "id": str(r.id),
            "username": r.username,
            "title": r.title,
            "channel_type": r.channel_type,
            "is_active": r.is_active,
            "total": r.total,
            "last_24h": r.last_24h,
            "last_7d": r.last_7d,
            "last_post_at": last_seen.isoformat() if last_seen else None,
            "hours_since_last": hours_since,
        })
    return {"channels": rows, "generated_at": now.isoformat()}


@router.get("/ingest/log")
async def get_ingestion_log(
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
):
    """Get recent ingestion log entries."""
    result = await db.execute(
        select(IngestionLog)
        .order_by(IngestionLog.started_at.desc())
        .limit(limit)
    )
    logs = result.scalars().all()
    return {
        "logs": [
            {
                "id": str(log.id),
                "source_id": str(log.source_id),
                "feed_url": log.feed_url,
                "status": log.status,
                "articles_found": log.articles_found,
                "articles_new": log.articles_new,
                "error_message": log.error_message,
                "started_at": log.started_at.isoformat() if log.started_at else None,
                "completed_at": log.completed_at.isoformat() if log.completed_at else None,
            }
            for log in logs
        ]
    }


@router.post("/pipeline/run-all")
async def run_full_pipeline(db: AsyncSession = Depends(get_db)):
    """Run the full pipeline: ingest → NLP → cluster → score."""
    results = {}

    try:
        from app.services.ingestion import ingest_all_sources
        results["ingestion"] = await ingest_all_sources(db)
    except Exception as e:
        results["ingestion"] = {"error": str(e)}

    try:
        from app.services.nlp_pipeline import process_unprocessed_articles
        results["nlp"] = await process_unprocessed_articles(db)
    except Exception as e:
        results["nlp"] = {"error": str(e)}

    try:
        from app.services.clustering import cluster_articles
        results["clustering"] = await cluster_articles(db)
    except Exception as e:
        results["clustering"] = {"error": str(e)}

    try:
        from app.services.bias_scoring import score_unscored_articles
        results["bias_scoring"] = await score_unscored_articles(db)
    except Exception as e:
        results["bias_scoring"] = {"error": str(e)}

    return {"status": "ok", "results": results}


@router.get("/debug/llm")
async def debug_llm():
    """Test if the LLM API keys work."""
    from app.config import settings
    result = {
        "has_anthropic_key": bool(settings.anthropic_api_key),
        "anthropic_prefix": settings.anthropic_api_key[:15] + "..." if settings.anthropic_api_key else "NONE",
        "has_openai_key": bool(settings.openai_api_key),
        "openai_prefix": settings.openai_api_key[:10] + "..." if settings.openai_api_key else "NONE",
    }

    # Test OpenAI first
    if settings.openai_api_key:
        try:
            import openai
            client = openai.AsyncOpenAI(api_key=settings.openai_api_key)
            resp = await client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{"role": "user", "content": "Say 'hello' in one word"}],
                max_tokens=10,
            )
            result["openai_test"] = "OK"
            result["openai_response"] = resp.choices[0].message.content
        except Exception as e:
            result["openai_test"] = "FAILED"
            result["openai_error"] = str(e)

    # Test Anthropic
    if settings.anthropic_api_key:
        try:
            import anthropic
            client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
            msg = await client.messages.create(
                model=settings.bias_scoring_model,
                max_tokens=10,
                messages=[{"role": "user", "content": "Say 'hello' in one word"}],
            )
            result["anthropic_test"] = "OK"
            result["anthropic_response"] = msg.content[0].text
        except Exception as e:
            result["anthropic_test"] = "FAILED"
            result["anthropic_error"] = str(e)

    return result


# === Rater Management (Admin Only) ===

from pydantic import BaseModel as _BaseModel

class _CreateRaterRequest(_BaseModel):
    username: str
    email: str
    password: str
    display_name: str | None = None
    rater_level: str = "trained"

@router.post("/raters/create")
async def create_rater_account(
    request: _CreateRaterRequest,
    db: AsyncSession = Depends(get_db),
):
    """Create a new rater account. Admin-only — no public signup."""
    from app.services.auth import create_rater
    try:
        user = await create_rater(
            db, request.username, request.email, request.password,
            request.display_name, request.rater_level,
        )
        return {
            "status": "ok",
            "user_id": str(user.id),
            "username": user.username,
            "rater_level": user.rater_level,
        }
    except Exception as e:
        return {"status": "error", "error": str(e)}


@router.get("/raters")
async def list_raters(db: AsyncSession = Depends(get_db)):
    """List all rater accounts and their stats."""
    from sqlalchemy import select
    from app.models.user import User

    result = await db.execute(
        select(User).where(User.is_rater.is_(True)).order_by(User.created_at.desc())
    )
    raters = result.scalars().all()

    return {
        "raters": [
            {
                "id": str(r.id),
                "username": r.username,
                "display_name": r.display_name,
                "email": r.email,
                "rater_level": r.rater_level,
                "total_ratings": r.total_ratings,
                "reliability_score": r.rater_reliability_score,
                "is_active": r.is_active,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in raters
        ],
        "total": len(raters),
    }


@router.post("/raters/{username}/deactivate")
async def deactivate_rater(username: str, db: AsyncSession = Depends(get_db)):
    """Deactivate a rater account."""
    from sqlalchemy import select, update
    from app.models.user import User

    result = await db.execute(select(User).where(User.username == username))
    user = result.scalar_one_or_none()
    if not user:
        return {"status": "error", "error": "User not found"}

    user.is_active = False
    await db.commit()
    return {"status": "ok", "username": username, "is_active": False}


class _EditStoryRequest(_BaseModel):
    title_fa: str | None = None
    title_en: str | None = None
    summary_fa: str | None = None
    priority: int | None = None
    # Narrative fields — live inside the JSON blob stored in story.summary_en
    state_summary_fa: str | None = None
    diaspora_summary_fa: str | None = None
    bias_explanation_fa: str | None = None


@router.patch("/stories/{story_id}")
async def edit_story(story_id: str, request: _EditStoryRequest, db: AsyncSession = Depends(get_db)):
    """Edit a story's title, narratives, or priority. Admin-only.

    Narrative fields (state_summary_fa, diaspora_summary_fa, bias_explanation_fa)
    are stored as JSON inside the story.summary_en column. This endpoint reads
    the current blob, merges any provided fields, and writes it back.

    Any edit to a narrative or title flips story.is_edited = True so the
    nightly maintenance pipeline skips regeneration for this story.

    To HIDE a story from the homepage, set priority = -100.
    """
    import json as _json
    import uuid

    from sqlalchemy import select

    from app.models.story import Story

    result = await db.execute(select(Story).where(Story.id == uuid.UUID(story_id)))
    story = result.scalar_one_or_none()
    if not story:
        return {"status": "error", "error": "Story not found"}

    editorial_change = False

    if request.title_fa is not None:
        story.title_fa = request.title_fa
        editorial_change = True
    if request.title_en is not None:
        story.title_en = request.title_en
        editorial_change = True
    if request.summary_fa is not None:
        story.summary_fa = request.summary_fa
        editorial_change = True
    if request.priority is not None:
        story.priority = request.priority

    # Narrative fields live inside the JSON blob in summary_en.
    if (
        request.state_summary_fa is not None
        or request.diaspora_summary_fa is not None
        or request.bias_explanation_fa is not None
    ):
        try:
            blob = _json.loads(story.summary_en) if story.summary_en else {}
        except Exception:
            blob = {}
        if request.state_summary_fa is not None:
            blob["state_summary_fa"] = request.state_summary_fa
        if request.diaspora_summary_fa is not None:
            blob["diaspora_summary_fa"] = request.diaspora_summary_fa
        if request.bias_explanation_fa is not None:
            blob["bias_explanation_fa"] = request.bias_explanation_fa
        story.summary_en = _json.dumps(blob, ensure_ascii=False)
        editorial_change = True

    if editorial_change:
        # #6 — instead of freezing forever via is_edited=True, write
        # the edited fields into summary_anchor. The nightly cron
        # treats anchored stories as eligible for refresh but instructs
        # the LLM to preserve the anchor's tone/vocabulary while
        # incorporating new articles. is_edited stays False so the
        # nightly maintenance picks the story up.
        from datetime import datetime as _dt
        anchor = dict(story.summary_anchor or {})
        if request.title_fa is not None:
            anchor["title_fa"] = request.title_fa
        if request.summary_fa is not None:
            anchor["summary_fa"] = request.summary_fa
        if request.state_summary_fa is not None:
            anchor["state_summary_fa"] = request.state_summary_fa
        if request.diaspora_summary_fa is not None:
            anchor["diaspora_summary_fa"] = request.diaspora_summary_fa
        if request.bias_explanation_fa is not None:
            anchor["bias_explanation_fa"] = request.bias_explanation_fa
        anchor["anchored_at"] = _dt.utcnow().isoformat() + "Z"
        story.summary_anchor = anchor
        # Keep is_edited=False so nightly picks the story up.
        story.is_edited = False

    await db.commit()

    return {
        "status": "ok",
        "story_id": str(story.id),
        "is_edited": story.is_edited,
        "summary_anchor_set": bool(story.summary_anchor),
        "title_fa": story.title_fa,
        "title_en": story.title_en,
        "priority": story.priority,
    }


@router.post("/re-embed-all")
async def re_embed_all_articles(
    limit: int = Query(500, ge=1, le=5000),
    db: AsyncSession = Depends(get_db),
):
    """Re-generate embeddings for all articles using OpenAI text-embedding-3-small.

    Processes in batches of 100. Safe to re-run — overwrites existing embeddings.
    Cost: ~2200 articles ≈ $0.01 total.
    """
    from sqlalchemy import text as _text
    from app.models.article import Article
    from app.nlp.embeddings import generate_embeddings_batch
    from app.nlp.persian import extract_text_for_embedding, normalize

    result = await db.execute(
        select(Article)
        .where(Article.content_text.isnot(None) | Article.summary.isnot(None))
        .order_by(Article.ingested_at.desc())
        .limit(limit)
    )
    articles = list(result.scalars().all())

    if not articles:
        return {"status": "ok", "embedded": 0}

    # Build texts for embedding
    texts = []
    for a in articles:
        title = a.title_original or a.title_fa or a.title_en or ""
        body = a.content_text or a.summary or ""
        raw = f"{title}. {body[:2000]}"
        try:
            raw = normalize(raw)
        except Exception:
            pass
        texts.append(raw)

    # Generate in batches — offload to thread so retries don't block
    # the API event loop.
    import asyncio as _asyncio
    embeddings = await _asyncio.to_thread(
        generate_embeddings_batch, texts, 100
    )

    updated = 0
    for article, embedding in zip(articles, embeddings):
        if embedding and any(v != 0.0 for v in embedding[:10]):
            article.embedding = embedding
            updated += 1

    await db.commit()
    logger.info(f"Re-embedded {updated}/{len(articles)} articles with OpenAI")
    return {"status": "ok", "total": len(articles), "embedded": updated}


@router.get("/embedding/health")
async def embedding_health(db: AsyncSession = Depends(get_db)):
    """Zero-vector rate across recent articles — catches silent embedding failures.

    A zero-filled 384-dim vector passes `is not None` but breaks every
    cosine downstream. Watch this endpoint (or the log line on each
    pipeline run) if cluster_new cost or orphan rate spikes — rising
    zero rate is the earliest signal that OpenAI's embeddings endpoint
    is degraded.
    """
    from sqlalchemy import text as _text
    windows = [("1h", "1 hour"), ("24h", "24 hours"), ("7d", "7 days"), ("30d", "30 days")]
    out: dict = {}
    for label, interval in windows:
        row = (await db.execute(_text(
            f"""
            SELECT
              count(*) FILTER (WHERE embedding IS NOT NULL) AS with_emb,
              count(*) FILTER (WHERE embedding IS NULL) AS null_emb,
              count(*) FILTER (
                WHERE embedding IS NOT NULL
                  AND NOT EXISTS (
                    SELECT 1 FROM jsonb_array_elements_text(embedding) v
                    WHERE v::float <> 0
                  )
              ) AS all_zero,
              count(*) AS total
            FROM articles
            WHERE ingested_at >= NOW() - interval '{interval}'
            """
        ))).one()
        total = row.total or 0
        all_zero = row.all_zero or 0
        null_emb = row.null_emb or 0
        out[label] = {
            "total": total,
            "with_embedding": row.with_emb or 0,
            "null_embedding": null_emb,
            "all_zero": all_zero,
            "healthy": max(0, total - null_emb - all_zero),
            "zero_pct": round(100 * all_zero / max(1, total), 1),
            "null_pct": round(100 * null_emb / max(1, total), 1),
        }
    # Worst-recent as the top-level alert flag
    worst = out["24h"]
    out["alert"] = worst["zero_pct"] >= 10 or worst["null_pct"] >= 10
    return out


@router.post("/nullify-localhost-images")
async def nullify_localhost_images(db: AsyncSession = Depends(get_db)):
    """Nullify all article.image_url values pointing to http://localhost:*

    Background: 14/15 articles in a sample had image_url values like
    'http://localhost:8000/images/HASH.jpg' from the dev-only image
    server. These files were never migrated to R2 (verified — R2
    returns 404 for those hashes). Nulling them triggers
    step_fix_images to re-fetch og:image from the article URL on
    the next maintenance run.
    """
    from sqlalchemy import update
    from app.models.article import Article

    result = await db.execute(
        update(Article)
        .where(Article.image_url.like("http://localhost%"))
        .values(image_url=None)
        .execution_options(synchronize_session=False)
    )
    await db.commit()
    return {"status": "ok", "nullified": result.rowcount}


@router.post("/stories/{story_id}/unclaim-articles")
async def unclaim_story_articles(
    story_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Detach all articles from a story so they re-cluster in the next run.

    Useful for nuking a badly-clustered story (e.g. the Hormuz story with
    209 mixed articles). The story itself is kept but becomes empty; it
    falls below the visibility threshold (article_count < 5) and
    disappears from the homepage until the next clustering run
    re-populates OR rebuilds a cleaner version.
    """
    import uuid
    from sqlalchemy import update as _update
    from app.models.article import Article
    from app.models.story import Story

    story_uuid = uuid.UUID(story_id)
    result = await db.execute(
        _update(Article)
        .where(Article.story_id == story_uuid)
        .values(story_id=None)
        .execution_options(synchronize_session=False)
    )
    # Zero out the story row's counts so it disappears from the homepage
    await db.execute(
        _update(Story)
        .where(Story.id == story_uuid)
        .values(article_count=0, source_count=0, priority=-100, trending_score=0)
    )
    await db.commit()
    return {
        "status": "ok",
        "story_id": story_id,
        "articles_unclaimed": result.rowcount,
        "message": "Articles detached and story hidden. Next clustering run will redistribute them.",
    }


@router.post("/stories/{story_id}/resync", dependencies=[Depends(require_admin)])
async def resync_story(
    story_id: str,
    recount: bool = True,
    regenerate_summary: bool = False,
    regenerate_telegram: bool = False,
    force_edited: bool = False,
    db: AsyncSession = Depends(get_db),
):
    """Fix drift in denormalized fields on a single story and optionally
    trigger regeneration of its summary / telegram analysis.

    Typical use: rater flags a mismatch between the article count in the
    page header ("5 مقاله") and the actual length of the articles list
    (6). That happens when story.article_count got stale vs the current
    Article.story_id membership. This endpoint recomputes article_count
    and source_count from live data.

    regenerate_summary=True additionally clears summary_fa + summary_en
    so the next auto_maintenance cycle re-runs story_analysis with the
    current article mix. Useful when the bias-comparison narratives are
    stale relative to the current source set — e.g. a rater notes that
    "radical media didn't cover this" is no longer accurate after a
    radical source was linked.

    is_edited=True stories are protected by default (Niloofar's
    hand-curated summaries survive). Pass force_edited=true to override.

    regenerate_telegram=True clears telegram_analysis so the next
    auto_maintenance cycle re-runs the Telegram pipeline.
    """
    import uuid as _uuid
    from sqlalchemy import func as _func
    from app.models.article import Article
    from app.models.story import Story

    try:
        story_uuid = _uuid.UUID(story_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid story_id")

    story_result = await db.execute(select(Story).where(Story.id == story_uuid))
    story = story_result.scalar_one_or_none()
    if not story:
        raise HTTPException(status_code=404, detail="Story not found")

    out: dict = {"status": "ok", "story_id": story_id, "actions": []}

    if recount:
        actual_articles = (await db.execute(
            select(_func.count(Article.id)).where(Article.story_id == story_uuid)
        )).scalar() or 0
        actual_sources = (await db.execute(
            select(_func.count(_func.distinct(Article.source_id))).where(Article.story_id == story_uuid)
        )).scalar() or 0
        out["article_count"] = {"old": story.article_count, "new": int(actual_articles)}
        out["source_count"] = {"old": story.source_count, "new": int(actual_sources)}
        story.article_count = int(actual_articles)
        story.source_count = int(actual_sources)
        out["actions"].append("recount")

    if regenerate_summary:
        if story.is_edited and not force_edited:
            out["summary_skipped"] = "is_edited=True (pass force_edited=true to override)"
        else:
            story.summary_fa = None
            story.summary_en = None
            # Clearing is_edited too so the auto pipeline stops skipping it.
            if story.is_edited and force_edited:
                story.is_edited = False
                out["actions"].append("is_edited_reset")
            out["actions"].append("summary_cleared")

    if regenerate_telegram:
        story.telegram_analysis = None
        out["actions"].append("telegram_cleared")

    await db.commit()
    return out


@router.patch("/sources/{slug}", dependencies=[Depends(require_admin)])
async def patch_source(
    slug: str,
    body: dict,
    db: AsyncSession = Depends(get_db),
):
    """Update editable fields on a source.

    Editable fields:
      - is_active: skip source in next ingest run (for dead/geo-blocked feeds)
      - logo_url, name_fa, name_en: display metadata
      - state_alignment: one of state/semi_state/independent/diaspora
      - production_location: inside_iran / outside_iran
      - factional_alignment: hardline/principlist/reformist/opposition/monarchist/radical/null
      - irgc_affiliated: bool
    The three classification fields drive the 4-subgroup narrative
    taxonomy — edit them to reclassify a source from the HITL sources page.
    """
    result = await db.execute(select(Source).where(Source.slug == slug))
    source = result.scalar_one_or_none()
    if not source:
        raise HTTPException(status_code=404, detail="Source not found")

    STATE_ALIGNMENTS = {"state", "semi_state", "independent", "diaspora"}
    PRODUCTION_LOCATIONS = {"inside_iran", "outside_iran"}
    FACTION_VALUES = {"hardline", "principlist", "reformist", "opposition", "monarchist", "radical", None, ""}

    allowed = {
        "logo_url", "name_fa", "name_en", "is_active",
        "state_alignment", "production_location", "factional_alignment",
        "irgc_affiliated",
    }
    changed = []
    for key in allowed:
        if key not in body:
            continue
        value = body[key]
        if key == "state_alignment" and value not in STATE_ALIGNMENTS:
            raise HTTPException(status_code=400, detail=f"state_alignment must be one of {sorted(STATE_ALIGNMENTS)}")
        if key == "production_location" and value not in PRODUCTION_LOCATIONS:
            raise HTTPException(status_code=400, detail=f"production_location must be one of {sorted(PRODUCTION_LOCATIONS)}")
        if key == "factional_alignment":
            if value not in FACTION_VALUES:
                raise HTTPException(status_code=400, detail=f"factional_alignment must be one of {sorted(v for v in FACTION_VALUES if v)} or null")
            if value == "":
                value = None
        setattr(source, key, value)
        changed.append(key)
    if not changed:
        raise HTTPException(status_code=400, detail=f"No valid fields. Allowed: {sorted(allowed)}")
    await db.commit()
    return {"status": "ok", "slug": slug, "updated": changed, "is_active": source.is_active}


@router.patch("/channels/{channel_id}", dependencies=[Depends(require_admin)])
async def patch_channel(
    channel_id: uuid.UUID,
    body: dict,
    db: AsyncSession = Depends(get_db),
):
    """Update editable fields on a Telegram channel (is_active, etc.).

    Setting is_active=false skips the channel on the next Telegram fetch.
    """
    result = await db.execute(select(TelegramChannel).where(TelegramChannel.id == channel_id))
    channel = result.scalar_one_or_none()
    if not channel:
        raise HTTPException(status_code=404, detail="Channel not found")
    allowed = {"is_active", "title", "channel_type"}
    changed = []
    for key in allowed:
        if key in body:
            setattr(channel, key, body[key])
            changed.append(key)
    if not changed:
        raise HTTPException(status_code=400, detail=f"No valid fields. Allowed: {allowed}")
    await db.commit()
    return {"status": "ok", "channel_id": str(channel_id), "updated": changed, "is_active": channel.is_active}


@router.post("/create-tables")
async def create_tables():
    """Create any missing database tables from SQLAlchemy models. Safe to run multiple times."""
    from app.database import engine, Base
    # Import all models so they're registered
    import app.models  # noqa
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    return {"status": "ok", "message": "All tables created/verified"}


@router.post("/migrate-and-seed")
async def migrate_and_seed(db: AsyncSession = Depends(get_db)):
    """Run alembic migration + seed new sources and analysts. One-time setup."""
    import subprocess
    import sys
    from pathlib import Path

    backend_dir = Path(__file__).parent.parent.parent.parent
    results = {"migration": None, "seed": None}

    # 1. Run alembic autogenerate + upgrade
    try:
        env = {**__import__("os").environ, "PYTHONPATH": str(backend_dir)}
        rev = subprocess.run(
            [sys.executable, "-m", "alembic", "revision", "--autogenerate", "-m", "add_analysts_table"],
            cwd=str(backend_dir), capture_output=True, text=True, timeout=30, env=env,
        )
        upgrade = subprocess.run(
            [sys.executable, "-m", "alembic", "upgrade", "head"],
            cwd=str(backend_dir), capture_output=True, text=True, timeout=30, env=env,
        )
        results["migration"] = {
            "revision": rev.stdout[-200:] if rev.returncode == 0 else rev.stderr[-200:],
            "upgrade": upgrade.stdout[-200:] if upgrade.returncode == 0 else upgrade.stderr[-200:],
            "success": upgrade.returncode == 0,
        }
    except Exception as e:
        results["migration"] = {"error": str(e), "success": False}

    # 2. Run seed script
    try:
        seed_script = backend_dir / "scripts" / "seed_sources_v2.py"
        if seed_script.exists():
            seed = subprocess.run(
                [sys.executable, str(seed_script)],
                cwd=str(backend_dir), capture_output=True, text=True, timeout=60,
                env={**__import__("os").environ, "PYTHONPATH": str(backend_dir)},
            )
            results["seed"] = {
                "output": seed.stdout[-500:],
                "errors": seed.stderr[-200:] if seed.returncode != 0 else None,
                "success": seed.returncode == 0,
            }
        else:
            results["seed"] = {"error": "seed script not found", "success": False}
    except Exception as e:
        results["seed"] = {"error": str(e), "success": False}

    return {"status": "ok", "results": results}


@router.post("/telegram/seed")
async def seed_telegram_channels_endpoint(db: AsyncSession = Depends(get_db)):
    """Seed Telegram channels into the database (no Telethon needed)."""
    from app.services.seed_telegram import seed_telegram_channels
    count = await seed_telegram_channels(db)
    # Return current channel list
    result = await db.execute(
        select(TelegramChannel).order_by(TelegramChannel.username)
    )
    channels = result.scalars().all()
    return {
        "status": "ok",
        "new_channels": count,
        "total_channels": len(channels),
        "channels": [{"username": c.username, "title": c.title, "type": c.channel_type} for c in channels],
    }


@router.post("/telegram/run")
async def run_telegram_collection(db: AsyncSession = Depends(get_db)):
    """Run just the Telegram ingestion step (fetch posts, convert to articles, link to stories).
    Requires Telethon session to be authorized."""
    from app.services.telegram_service import (
        ingest_all_channels,
        convert_telegram_posts_to_articles,
        extract_articles_from_aggregators,
    )
    results = {}
    try:
        ingest_stats = await ingest_all_channels(db)
        results["ingest"] = ingest_stats
    except Exception as e:
        results["ingest"] = {"error": str(e)}

    try:
        convert_stats = await convert_telegram_posts_to_articles(db)
        results["convert"] = convert_stats
    except Exception as e:
        results["convert"] = {"error": str(e)}

    try:
        agg_stats = await extract_articles_from_aggregators(db)
        results["aggregators"] = agg_stats
    except Exception as e:
        results["aggregators"] = {"error": str(e)}

    return {"status": "ok", "results": results}


@router.post("/cleanup-unrelated")
async def cleanup_unrelated_articles(
    threshold: float = Query(0.20, ge=0.0, le=1.0),
    dry_run: bool = Query(True),
    db: AsyncSession = Depends(get_db),
):
    """Find and optionally remove articles with low similarity to their story centroid.

    This directly addresses the problem of unrelated articles polluting bias comparison.

    Args:
        threshold: cosine similarity below this = unrelated (default 0.20)
        dry_run: if True, just report what would be removed (default True)
    """
    from app.nlp.embeddings import cosine_similarity

    result = await db.execute(
        select(Story).where(
            Story.article_count >= 5,
            Story.centroid_embedding.isnot(None),
        )
    )
    stories = list(result.scalars().all())

    flagged = []
    for story in stories:
        centroid = story.centroid_embedding
        if not centroid:
            continue

        art_result = await db.execute(
            select(Article).where(
                Article.story_id == story.id,
                Article.embedding.isnot(None),
            )
        )
        articles = list(art_result.scalars().all())

        for article in articles:
            if not article.embedding:
                continue
            sim = cosine_similarity(article.embedding, centroid)
            if sim < threshold:
                flagged.append({
                    "article_id": str(article.id),
                    "story_id": str(story.id),
                    "story_title": (story.title_fa or "")[:50],
                    "article_title": (article.title_fa or article.title_original or "")[:50],
                    "similarity": round(sim, 3),
                })

                if not dry_run:
                    article.story_id = None  # detach from story

    if not dry_run and flagged:
        # Refresh affected stories
        affected_ids = {f["story_id"] for f in flagged}
        for sid in affected_ids:
            story_obj = await db.execute(select(Story).where(Story.id == sid))
            s = story_obj.scalar_one_or_none()
            if s:
                # Recount
                count_result = await db.execute(
                    select(func.count(Article.id)).where(Article.story_id == s.id)
                )
                s.article_count = count_result.scalar() or 0
                s.summary_fa = None  # force re-summarize
                s.summary_en = None
        await db.commit()

    return {
        "status": "ok",
        "dry_run": dry_run,
        "threshold": threshold,
        "flagged_count": len(flagged),
        "flagged": flagged[:50],  # cap response size
        "message": f"{'Would remove' if dry_run else 'Removed'} {len(flagged)} unrelated articles",
    }


@router.patch("/articles/{article_id}")
async def patch_article(
    article_id: str,
    body: dict,
    db: AsyncSession = Depends(get_db),
):
    """Update image_url on an article (for fixing missing images)."""
    import uuid
    article_uuid = uuid.UUID(article_id)
    result = await db.execute(select(Article).where(Article.id == article_uuid))
    article = result.scalar_one_or_none()
    if not article:
        raise HTTPException(status_code=404, detail="Article not found")
    if "image_url" in body:
        article.image_url = body["image_url"]
    await db.commit()
    return {"status": "ok", "article_id": article_id, "image_url": article.image_url}


# NOTE: a previous duplicate PATCH /stories/{story_id} handler was defined
# here. Removed because the earlier `edit_story` handler (search for
# _EditStoryRequest above) already owns this route and is authoritative.

@router.post("/cluster-llm/trigger")
async def trigger_llm_clustering(db: AsyncSession = Depends(get_db)):
    """Cluster articles using LLM topic extraction (more accurate, costs ~$0.001/article)."""
    try:
        from app.services.topic_clustering import cluster_with_llm
        stats = await cluster_with_llm(db)
        return {"status": "ok", "stats": stats}
    except Exception as e:
        logger.exception("LLM clustering failed")
        return {"status": "error", "error": str(e)}


@router.get("/costs")
async def get_llm_costs():
    """Legacy in-process session stats. Dashboard uses /cost/* instead."""
    from app.services.llm_utils import get_session_stats
    return get_session_stats()


# === LLM cost dashboard ===
# All endpoints below read from llm_usage_logs, populated on every LLM
# call via app.services.llm_usage.log_llm_usage. Admin-gated.

_COST_WINDOWS = {
    "24h": "1 day",
    "7d":  "7 days",
    "30d": "30 days",
    "90d": "90 days",
}


@router.get("/cost/summary", dependencies=[Depends(require_admin)])
async def cost_summary(
    window: str = "7d",
    db: AsyncSession = Depends(get_db),
):
    """Aggregated cost picture for a rolling window.

    Returns total $, call count, and breakdowns by model + purpose.
    window: one of 24h / 7d / 30d / 90d.
    """
    interval = _COST_WINDOWS.get(window, "7 days")
    from sqlalchemy import text as _text
    totals = (await db.execute(_text(f"""
        SELECT
            COALESCE(SUM(total_cost), 0) AS total_cost,
            COALESCE(SUM(input_cost), 0) AS input_cost,
            COALESCE(SUM(cached_cost), 0) AS cached_cost,
            COALESCE(SUM(output_cost), 0) AS output_cost,
            COALESCE(SUM(input_tokens), 0) AS input_tokens,
            COALESCE(SUM(cached_input_tokens), 0) AS cached_input_tokens,
            COALESCE(SUM(output_tokens), 0) AS output_tokens,
            COUNT(*) AS calls
        FROM llm_usage_logs
        WHERE timestamp >= NOW() - INTERVAL '{interval}'
    """))).mappings().one()

    by_model = (await db.execute(_text(f"""
        SELECT model,
               COUNT(*) AS calls,
               SUM(total_cost) AS cost,
               SUM(input_tokens) AS input_tokens,
               SUM(output_tokens) AS output_tokens
        FROM llm_usage_logs
        WHERE timestamp >= NOW() - INTERVAL '{interval}'
        GROUP BY model
        ORDER BY cost DESC
    """))).mappings().all()

    by_purpose = (await db.execute(_text(f"""
        SELECT purpose,
               COUNT(*) AS calls,
               SUM(total_cost) AS cost,
               SUM(input_tokens) AS input_tokens,
               SUM(output_tokens) AS output_tokens
        FROM llm_usage_logs
        WHERE timestamp >= NOW() - INTERVAL '{interval}'
        GROUP BY purpose
        ORDER BY cost DESC
    """))).mappings().all()

    # Daily series for the stacked bar
    daily = (await db.execute(_text(f"""
        SELECT DATE_TRUNC('day', timestamp) AS day,
               purpose,
               SUM(total_cost) AS cost
        FROM llm_usage_logs
        WHERE timestamp >= NOW() - INTERVAL '{interval}'
        GROUP BY day, purpose
        ORDER BY day ASC
    """))).mappings().all()

    # Today vs yesterday deltas
    today = (await db.execute(_text("""
        SELECT COALESCE(SUM(total_cost), 0) AS cost, COUNT(*) AS calls
        FROM llm_usage_logs
        WHERE timestamp >= DATE_TRUNC('day', NOW())
    """))).mappings().one()
    yesterday = (await db.execute(_text("""
        SELECT COALESCE(SUM(total_cost), 0) AS cost, COUNT(*) AS calls
        FROM llm_usage_logs
        WHERE timestamp >= DATE_TRUNC('day', NOW() - INTERVAL '1 day')
          AND timestamp < DATE_TRUNC('day', NOW())
    """))).mappings().one()

    unpriced_count = (await db.execute(_text(f"""
        SELECT COUNT(*) FROM llm_usage_logs
        WHERE timestamp >= NOW() - INTERVAL '{interval}' AND priced = FALSE
    """))).scalar() or 0

    return {
        "window": window,
        "totals": dict(totals),
        "today": dict(today),
        "yesterday": dict(yesterday),
        "by_model": [dict(r) for r in by_model],
        "by_purpose": [dict(r) for r in by_purpose],
        "daily": [dict(r) for r in daily],
        "unpriced_count": unpriced_count,
    }


@router.get("/cost/calls", dependencies=[Depends(require_admin)])
async def cost_calls(
    limit: int = 100,
    model: str | None = None,
    purpose: str | None = None,
    db: AsyncSession = Depends(get_db),
):
    """Recent LLM call rows. Optional filters by model and/or purpose."""
    limit = max(1, min(limit, 500))
    from sqlalchemy import text as _text
    where = ["1=1"]
    params: dict = {"limit": limit}
    if model:
        where.append("model = :model")
        params["model"] = model
    if purpose:
        where.append("purpose = :purpose")
        params["purpose"] = purpose

    sql = f"""
        SELECT id, timestamp, model, purpose,
               input_tokens, cached_input_tokens, output_tokens,
               input_cost, cached_cost, output_cost, total_cost,
               story_id, article_id, priced, meta
        FROM llm_usage_logs
        WHERE {' AND '.join(where)}
        ORDER BY timestamp DESC
        LIMIT :limit
    """
    rows = (await db.execute(_text(sql), params)).mappings().all()
    return {"calls": [dict(r) for r in rows]}


@router.get("/cost/top-stories", dependencies=[Depends(require_admin)])
async def cost_top_stories(
    days: int = 7,
    limit: int = 20,
    db: AsyncSession = Depends(get_db),
):
    """Top stories by LLM spend over the last `days` days.

    Each row also includes a `by_purpose` list — the same call data
    grouped by purpose tag — so the cost dashboard can explain where
    an expensive story's calls came from without a second round-trip.
    """
    days = max(1, min(days, 90))
    limit = max(1, min(limit, 100))
    from sqlalchemy import text as _text
    rows = (await db.execute(_text(f"""
        SELECT l.story_id,
               s.title_fa,
               s.article_count,
               COUNT(*) AS calls,
               SUM(l.total_cost) AS cost
        FROM llm_usage_logs l
        LEFT JOIN stories s ON s.id = l.story_id
        WHERE l.story_id IS NOT NULL
          AND l.timestamp >= NOW() - INTERVAL '{days} days'
        GROUP BY l.story_id, s.title_fa, s.article_count
        ORDER BY cost DESC
        LIMIT {limit}
    """))).mappings().all()

    stories = [dict(r) for r in rows]
    if not stories:
        return {"stories": stories}

    # Per-story purpose breakdown, in one query. Keeps the endpoint O(1)
    # round-trips regardless of how many stories we return.
    story_ids = [s["story_id"] for s in stories]
    purpose_rows = (await db.execute(_text(f"""
        SELECT story_id,
               purpose,
               COUNT(*) AS calls,
               SUM(total_cost) AS cost
        FROM llm_usage_logs
        WHERE story_id = ANY(:ids)
          AND timestamp >= NOW() - INTERVAL '{days} days'
        GROUP BY story_id, purpose
        ORDER BY cost DESC
    """), {"ids": story_ids})).mappings().all()

    by_story: dict = {}
    for r in purpose_rows:
        by_story.setdefault(r["story_id"], []).append({
            "purpose": r["purpose"],
            "calls": r["calls"],
            "cost": float(r["cost"] or 0),
        })
    for s in stories:
        s["by_purpose"] = by_story.get(s["story_id"], [])
    return {"stories": stories}


@router.get("/cost/pricing", dependencies=[Depends(require_admin)])
async def cost_pricing():
    """Static pricing-table reference + list of models we've seen but
    can't price yet."""
    from app.services.llm_pricing import pricing_table, unknown_models_seen
    return {
        "pricing": pricing_table(),
        "unknown_models": unknown_models_seen(),
    }


# === Maintenance step triggers (for the /dashboard/actions page) ===
# These expose individual maintenance steps as one-click buttons on the
# admin dashboard. All are admin-gated. Responses include stats so the
# dashboard can render "what just happened" without a second call.

@router.post("/maintenance/recluster-orphans", dependencies=[Depends(require_admin)])
async def trigger_recluster_orphans():
    """Retry-cluster orphan articles older than 6h with a looser 0.40
    cosine threshold. Pure math, zero LLM. Caps at 500/run."""
    try:
        import sys
        from pathlib import Path
        root = Path(__file__).resolve().parents[3]
        if str(root) not in sys.path:
            sys.path.insert(0, str(root))
        from auto_maintenance import step_recluster_orphans
        stats = await step_recluster_orphans()
        return {"status": "ok", "stats": stats}
    except Exception as e:
        logger.exception("recluster-orphans failed")
        return {"status": "error", "error": str(e)}


@router.post("/maintenance/merge-tiny-cosine", dependencies=[Depends(require_admin)])
async def trigger_merge_tiny_cosine():
    """Deterministic pre-merge: fold pairs of stories with
    article_count ≤ 4 and centroid cosine ≥ 0.60 into the larger one.
    Pure math, zero LLM."""
    try:
        from app.database import async_session
        from app.services.clustering import _merge_tiny_by_cosine
        async with async_session() as db:
            merged = await _merge_tiny_by_cosine(db)
        return {"status": "ok", "stats": {"merged": merged}}
    except Exception as e:
        logger.exception("merge-tiny-cosine failed")
        return {"status": "error", "error": str(e)}


@router.post("/maintenance/prune-stagnant", dependencies=[Depends(require_admin)])
async def trigger_prune_stagnant():
    """Delete 1-article stories older than 48h and 2-4 article stories
    older than 14 days. Safe — is_edited stories are preserved."""
    try:
        import sys
        from pathlib import Path
        root = Path(__file__).resolve().parents[3]
        if str(root) not in sys.path:
            sys.path.insert(0, str(root))
        from auto_maintenance import step_prune_stagnant
        stats = await step_prune_stagnant()
        return {"status": "ok", "stats": stats}
    except Exception as e:
        logger.exception("prune-stagnant failed")
        return {"status": "error", "error": str(e)}


@router.post("/maintenance/prune-noise", dependencies=[Depends(require_admin)])
async def trigger_prune_noise():
    """Drop unlinked/unprocessed articles and Telegram posts with
    too-short content. Includes the <200-char RSS orphan sweep."""
    try:
        import sys
        from pathlib import Path
        root = Path(__file__).resolve().parents[3]
        if str(root) not in sys.path:
            sys.path.insert(0, str(root))
        from auto_maintenance import step_prune_noise
        stats = await step_prune_noise()
        return {"status": "ok", "stats": stats}
    except Exception as e:
        logger.exception("prune-noise failed")
        return {"status": "error", "error": str(e)}


@router.post("/maintenance/recompute-centroids", dependencies=[Depends(require_admin)])
async def trigger_recompute_centroids():
    """Recompute centroid_embedding for stories whose centroid is NULL.
    Needed after merges and manual article moves. Pure math."""
    try:
        import sys
        from pathlib import Path
        root = Path(__file__).resolve().parents[3]
        if str(root) not in sys.path:
            sys.path.insert(0, str(root))
        from auto_maintenance import step_recompute_centroids
        stats = await step_recompute_centroids()
        return {"status": "ok", "stats": stats}
    except Exception as e:
        logger.exception("recompute-centroids failed")
        return {"status": "error", "error": str(e)}


@router.get("/neutrality/export", dependencies=[Depends(require_admin)])
async def export_neutrality_audit(
    top: int = 20,
    include_scored: bool = False,
    db: AsyncSession = Depends(get_db),
):
    """Return the JSON payload for a human-in-Claude neutrality audit.

    Matches the shape scripts/neutrality_audit.py writes to disk. The
    operator saves the response, pastes it to a Claude conversation for
    scoring, then POSTs the scored JSON back to /admin/neutrality/apply.

    Default top=20 to keep the response under a reasonable size for
    a single paste. Each article's content is already trimmed to 3000
    chars server-side.
    """
    from app.services.neutrality_audit_service import export_for_audit
    payload = await export_for_audit(db, top_n=top, include_scored=include_scored)
    return payload


@router.post("/neutrality/apply", dependencies=[Depends(require_admin)])
async def apply_neutrality_audit(
    payload: list[dict],
    db: AsyncSession = Depends(get_db),
):
    """Accept scored JSON and write source_neutrality into each story.

    Body shape (array of):
      {"story_id": "...", "article_neutrality": {"<article_id>": float}}

    Invalid entries (missing ids, non-numeric scores, unknown stories)
    are silently skipped — scores that aren't provided stay absent
    rather than being defaulted to 0.
    """
    from app.services.neutrality_audit_service import apply_scores
    stats = await apply_scores(db, payload)
    return {"status": "ok", **stats}


# === Social Media Posting ===

@router.get("/social/preview")
async def preview_social_posts(db: AsyncSession = Depends(get_db)):
    """Preview what would be posted to social media (review before posting)."""
    from app.services.social_posting import get_post_preview, get_platform_status
    try:
        queue = await get_post_preview(db)
        platforms = await get_platform_status()
        return {"status": "ok", "posts": queue, "count": len(queue), "platforms": platforms}
    except Exception as e:
        return {"status": "error", "error": str(e)}


class _SocialPostRequest(_BaseModel):
    story_id: str
    platform: str  # telegram, twitter, instagram, whatsapp, bluesky, linkedin

@router.post("/social/post")
async def post_to_social(request: _SocialPostRequest, db: AsyncSession = Depends(get_db)):
    """Post a specific story to any social media platform."""
    from app.services.social_posting import get_post_preview, post_story

    queue = await get_post_preview(db, limit=20)
    post_data = next((p for p in queue if p["story_id"] == request.story_id), None)

    if not post_data:
        return {"status": "error", "error": "Story not found or already posted"}

    text = post_data["posts"].get(request.platform)
    if not text:
        return {"status": "error", "error": f"No post generated for {request.platform}"}

    kwargs = {}
    if request.platform == "instagram":
        kwargs["image_url"] = post_data.get("image_url")

    result = await post_story(request.story_id, request.platform, text, **kwargs)
    return {"status": "ok", "result": result}


@router.get("/social/status")
async def social_platform_status():
    """Check which social platforms are configured."""
    from app.services.social_posting import get_platform_status
    return await get_platform_status()


# ─── Feedback-impact telemetry ────────────────────────────────────
# Drives /dashboard/learning. Two slices:
#   1. /feedback-impact/events — recent story_events from feedback +
#      clustering decisions, joined to story / article titles.
#   2. /feedback-impact/source-trust — current Source.cluster_quality_score
#      with the 30d flag rate that drove it.

# Event types this endpoint surfaces. Anything else is hidden so the
# feed stays focused on feedback-driven learning, not the full event log.
_LEARNING_EVENT_TYPES = (
    "feedback_orphan_rater",
    "feedback_orphan_anon",
    "feedback_rehome",
    "feedback_summary_regen",
    "feedback_niloofar_orphan",
    "feedback_niloofar_dismiss",
    "cluster_block_negative",
    "cluster_block_low_trust",
    "source_trust_change",
)


@router.get("/feedback-impact/events")
async def feedback_impact_events(
    limit: int = Query(100, ge=1, le=500),
    event_type: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
):
    """Recent feedback-impact events. Joined to story title + article
    title where applicable so the dashboard can render human-readable
    rows without per-row round-trips."""
    from sqlalchemy import text as _text

    types_filter = list(_LEARNING_EVENT_TYPES)
    if event_type and event_type in _LEARNING_EVENT_TYPES:
        types_filter = [event_type]

    rows = await db.execute(
        _text("""
            SELECT
                e.id, e.event_type, e.actor, e.story_id, e.article_id,
                e.signals, e.confidence, e.created_at,
                s.title_fa AS story_title,
                a.title_fa AS article_title,
                a.title_original AS article_title_original
            FROM story_events e
            LEFT JOIN stories s ON s.id = e.story_id
            LEFT JOIN articles a ON a.id = e.article_id
            WHERE e.event_type = ANY(:types)
            ORDER BY e.created_at DESC
            LIMIT :lim
        """),
        {"types": types_filter, "lim": limit},
    )
    items = []
    for r in rows.mappings():
        items.append({
            "id": str(r["id"]),
            "event_type": r["event_type"],
            "actor": r["actor"],
            "story_id": str(r["story_id"]) if r["story_id"] else None,
            "article_id": str(r["article_id"]) if r["article_id"] else None,
            "story_title": r["story_title"],
            "article_title": r["article_title"] or r["article_title_original"],
            "signals": r["signals"] or {},
            "confidence": r["confidence"],
            "created_at": r["created_at"].isoformat() if r["created_at"] else None,
        })
    return {"items": items, "count": len(items)}


@router.get("/feedback-impact/source-trust")
async def feedback_impact_source_trust(db: AsyncSession = Depends(get_db)):
    """Per-source trust score + 30-day flag rate.

    Same arithmetic as step_source_trust_recompute but read-only — the
    dashboard table needs to show the current score *and* what's driving
    it without waiting for the next maintenance tick.
    """
    from sqlalchemy import text as _text

    cutoff = datetime.now(timezone.utc) - timedelta(days=30)

    totals_q = await db.execute(
        select(Article.source_id, func.count(Article.id))
        .where(Article.ingested_at >= cutoff)
        .group_by(Article.source_id)
    )
    totals = {sid: cnt for sid, cnt in totals_q.all()}

    flag_q = await db.execute(
        _text("""
            SELECT a.source_id, COUNT(DISTINCT a.id) AS flagged
            FROM articles a
            WHERE a.ingested_at >= :cutoff
              AND (
                EXISTS (
                  SELECT 1 FROM rater_feedback rf
                  WHERE rf.article_id = a.id
                    AND rf.feedback_type = 'article_relevance'
                    AND rf.is_relevant = false
                )
                OR EXISTS (
                  SELECT 1 FROM improvement_feedback ifb
                  WHERE ifb.target_id = a.id::text
                    AND ifb.target_type = 'article'
                    AND ifb.issue_type = 'wrong_clustering'
                    AND ifb.status <> 'open'
                )
              )
            GROUP BY a.source_id
        """),
        {"cutoff": cutoff},
    )
    flagged = {row[0]: row[1] for row in flag_q.all()}

    sources_q = await db.execute(
        select(Source).order_by(Source.cluster_quality_score.asc(), Source.slug.asc())
    )
    sources = list(sources_q.scalars().all())

    items = []
    for s in sources:
        total = totals.get(s.id, 0)
        flag_count = flagged.get(s.id, 0)
        rate = (flag_count / total) if total else 0.0
        items.append({
            "source_id": str(s.id),
            "slug": s.slug,
            "name_fa": s.name_fa,
            "name_en": s.name_en,
            "state_alignment": s.state_alignment,
            "cluster_quality_score": round(float(s.cluster_quality_score or 1.0), 3),
            "articles_30d": total,
            "flagged_30d": flag_count,
            "flag_rate_30d": round(rate, 4),
        })
    return {"items": items, "count": len(items)}
