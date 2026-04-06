from celery import Celery
from celery.schedules import crontab

from app.config import settings

celery_app = Celery(
    "doornegar",
    broker=settings.redis_url,
    backend=settings.redis_url,
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
)

# Periodic task schedule
celery_app.conf.beat_schedule = {
    "ingest-all-feeds": {
        "task": "app.workers.ingest_task.ingest_all_feeds_task",
        "schedule": settings.ingestion_interval_minutes * 60,  # every 15 min
    },
    "process-nlp-batch": {
        "task": "app.workers.nlp_task.process_nlp_batch_task",
        "schedule": settings.ingestion_interval_minutes * 60,  # every 15 min, after ingest
    },
    "cluster-stories": {
        "task": "app.workers.nlp_task.cluster_stories_task",
        "schedule": 30 * 60,  # every 30 min
    },
    "score-bias-batch": {
        "task": "app.workers.nlp_task.score_bias_batch_task",
        "schedule": 60 * 60,  # every 60 min
    },
    "ingest-telegram": {
        "task": "app.workers.social_task.ingest_telegram_task",
        "schedule": settings.telegram_fetch_interval_minutes * 60,  # every 30 min
    },
    "link-telegram-posts": {
        "task": "app.workers.social_task.link_posts_task",
        "schedule": 30 * 60,  # every 30 min
    },
    "compute-social-sentiment": {
        "task": "app.workers.social_task.compute_sentiment_task",
        "schedule": 60 * 60,  # every 60 min
    },
}

# Auto-discover tasks
celery_app.autodiscover_tasks(["app.workers"])
