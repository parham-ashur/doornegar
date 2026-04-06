"""Admin endpoints for managing ingestion and NLP pipeline."""

import logging
import traceback

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.ingestion_log import IngestionLog

router = APIRouter()
logger = logging.getLogger(__name__)


@router.post("/ingest/trigger")
async def trigger_ingestion(db: AsyncSession = Depends(get_db)):
    """Manually trigger RSS feed ingestion."""
    try:
        from app.services.ingestion import ingest_all_sources
        stats = await ingest_all_sources(db)
        return {"status": "ok", "stats": stats}
    except Exception as e:
        logger.exception("Ingestion failed")
        return {"status": "error", "error": str(e), "traceback": traceback.format_exc()[-500:]}


@router.post("/nlp/trigger")
async def trigger_nlp_processing(db: AsyncSession = Depends(get_db)):
    """Manually trigger NLP processing on unprocessed articles."""
    try:
        from app.services.nlp_pipeline import process_unprocessed_articles
        stats = await process_unprocessed_articles(db)
        return {"status": "ok", "stats": stats}
    except Exception as e:
        logger.exception("NLP processing failed")
        return {"status": "error", "error": str(e), "traceback": traceback.format_exc()[-500:]}


@router.post("/cluster/trigger")
async def trigger_clustering(db: AsyncSession = Depends(get_db)):
    """Manually trigger story clustering."""
    try:
        from app.services.clustering import cluster_articles
        stats = await cluster_articles(db)
        return {"status": "ok", "stats": stats}
    except Exception as e:
        logger.exception("Clustering failed")
        return {"status": "error", "error": str(e), "traceback": traceback.format_exc()[-500:]}


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
        return {"status": "error", "error": str(e), "traceback": traceback.format_exc()[-500:]}


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

@router.post("/raters/create")
async def create_rater_account(
    username: str,
    email: str,
    password: str,
    display_name: str = None,
    rater_level: str = "trained",
    db: AsyncSession = Depends(get_db),
):
    """Create a new rater account. Admin-only — no public signup."""
    from app.services.auth import create_rater
    try:
        user = await create_rater(db, username, email, password, display_name, rater_level)
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
