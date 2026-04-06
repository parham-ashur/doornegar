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
