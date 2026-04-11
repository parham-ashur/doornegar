"""Admin endpoints for managing ingestion and NLP pipeline."""

import asyncio
import logging
import os
import re
import traceback
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from sqlalchemy import func, select
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


def _parse_maintenance_log() -> dict:
    """Read last maintenance run info from maintenance.log."""
    info = {"last_run": None, "last_result": "unknown", "next_run_approx": None}
    if not MAINTENANCE_LOG_PATH.exists():
        return info

    try:
        # Read last 200 lines to find the most recent run
        lines = MAINTENANCE_LOG_PATH.read_text(encoding="utf-8", errors="replace").splitlines()
        last_lines = lines[-200:] if len(lines) > 200 else lines

        last_start = None
        last_complete = None
        has_error = False

        for line in last_lines:
            if "Maintenance started at" in line:
                # Extract timestamp from log line: 2026-04-08 11:35:03,085 [INFO] ...
                m = re.match(r"(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})", line)
                if m:
                    last_start = m.group(1)
                    has_error = False  # reset for new run
            if "Maintenance complete in" in line:
                m = re.match(r"(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})", line)
                if m:
                    last_complete = m.group(1)
            if "[ERROR]" in line:
                has_error = True

        if last_start:
            try:
                dt = datetime.strptime(last_start, "%Y-%m-%d %H:%M:%S")
                dt = dt.replace(tzinfo=timezone.utc)
                info["last_run"] = dt.isoformat()
                # Approximate next run: 4 hours after last
                info["next_run_approx"] = (dt + timedelta(hours=4)).isoformat()
            except ValueError:
                pass

        if last_complete:
            info["last_result"] = "success" if not has_error else "partial_success"
        elif last_start:
            info["last_result"] = "in_progress_or_incomplete"

    except Exception as e:
        logger.warning(f"Could not parse maintenance log: {e}")

    return info


@router.get("/dashboard")
async def get_dashboard(db: AsyncSession = Depends(get_db)):
    """Comprehensive dashboard data: counts, maintenance status, costs, issues."""

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
    maintenance = _parse_maintenance_log()

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

    return {
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
            "estimated_monthly": "$15-25",
            "clustering_per_run": "~$0.02",
            "summary_per_story": "~$0.01",
        },
        "issues": issues,
        "actions_needed": actions_needed,
        "freshness_hours": freshness_hours,
    }


@router.post("/force-resummarize")
async def force_resummarize(
    limit: int = Query(5, ge=1, le=200),
    mode: str = Query("immediate", pattern="^(immediate|queue)$"),
    order: str = Query("trending", pattern="^(trending|recent)$"),
    db: AsyncSession = Depends(get_db),
):
    """Force re-generation of summaries with the current model.

    Modes:
      - "immediate" (default): clears summary_fa AND runs story_analysis
        inline for each story, returning once done.
      - "queue": just clears summary_fa on N stories so the next maintenance
        run picks them up via step_summarize.

    Order:
      - "trending" (default): same order as the homepage /trending endpoint
        (priority DESC, trending_score DESC). Ensures the stories visible
        to users get refreshed first.
      - "recent": most recently updated/published first.

    Only picks visible stories (article_count >= 5).
    """
    import json as _json
    from sqlalchemy.orm import selectinload
    from app.models.article import Article
    from app.models.story import Story

    query = (
        select(Story)
        .options(selectinload(Story.articles).selectinload(Article.source))
        .where(Story.article_count >= 5)
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

    # Immediate mode: run story_analysis inline.
    # Always use the PREMIUM model for force-refreshes — if Parham is
    # manually regenerating, it's worth the cost for the best output.
    from app.services.story_analysis import generate_story_analysis

    chosen_model = settings.story_analysis_premium_model
    regenerated = 0
    failed = 0
    errors = []
    for story in stories:
        articles_info = [
            {
                "title": a.title_original or a.title_fa or a.title_en or "",
                "content": (a.content_text or a.summary or "")[:1500],
                "source_name_fa": a.source.name_fa if a.source else "نامشخص",
                "state_alignment": a.source.state_alignment if a.source else "",
            }
            for a in story.articles
        ]
        try:
            analysis = await generate_story_analysis(story, articles_info, model=chosen_model)
            story.summary_fa = analysis.get("summary_fa")
            story.summary_en = _json.dumps({
                "state_summary_fa": analysis.get("state_summary_fa"),
                "diaspora_summary_fa": analysis.get("diaspora_summary_fa"),
                "independent_summary_fa": analysis.get("independent_summary_fa"),
                "bias_explanation_fa": analysis.get("bias_explanation_fa"),
                "scores": analysis.get("scores"),
                "llm_model_used": chosen_model,
            }, ensure_ascii=False)
            await db.commit()
            regenerated += 1
        except Exception as e:
            failed += 1
            errors.append(f"{str(story.id)[:8]}: {e}")
            logger.warning(f"Force-resummarize failed for {story.id}: {e}")

    return {
        "status": "ok",
        "cleared": len(stories),
        "regenerated": regenerated,
        "failed": failed,
        "errors": errors[:10],
        "message": f"Regenerated {regenerated}/{len(stories)} stories with {chosen_model}.",
        "story_ids": [str(s.id) for s in stories],
    }


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
        items.append({
            "id": str(s.id),
            "title_fa": s.title_fa,
            "updated_at": s.updated_at.isoformat() if s.updated_at else None,
            "article_count": s.article_count,
            "summary_fa_preview": (s.summary_fa or "")[:200],
            "bias_explanation_fa": extras.get("bias_explanation_fa"),
            "has_state_summary": bool(extras.get("state_summary_fa")),
            "has_diaspora_summary": bool(extras.get("diaspora_summary_fa")),
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

@router.patch("/stories/{story_id}")
async def edit_story(story_id: str, request: _EditStoryRequest, db: AsyncSession = Depends(get_db)):
    """Edit a story's title or summary. Admin-only."""
    from sqlalchemy import select
    from app.models.story import Story
    import uuid

    result = await db.execute(select(Story).where(Story.id == uuid.UUID(story_id)))
    story = result.scalar_one_or_none()
    if not story:
        return {"status": "error", "error": "Story not found"}

    if request.title_fa is not None:
        story.title_fa = request.title_fa
    if request.title_en is not None:
        story.title_en = request.title_en
    if request.summary_fa is not None:
        story.summary_fa = request.summary_fa
    if request.priority is not None:
        story.priority = request.priority
    await db.commit()

    return {
        "status": "ok",
        "story_id": str(story.id),
        "title_fa": story.title_fa,
        "title_en": story.title_en,
    }


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
    """Get current session LLM cost tracking."""
    from app.services.llm_utils import get_session_stats
    return get_session_stats()


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
