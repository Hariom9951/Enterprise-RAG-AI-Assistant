"""
Enterprise RAG AI Assistant — Celery Core Configuration
======================================================
Configures the Celery application client, message broker connections,
serialization structures, and concurrency parameters.
"""

from __future__ import annotations

from celery import Celery
from celery.schedules import crontab

from app.config.settings import settings

# ── Celery App Instantiation ──────────────────────────────────────────────────
celery_app = Celery(
    "rag_tasks",
    broker=settings.redis_url,
    backend=settings.redis_url,
    include=["app.tasks.document_tasks"],
)

# ── Celery Configurations ─────────────────────────────────────────────────────
celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_acks_late=True,  # Acknowledge tasks after execution completes (not before)
    worker_prefetch_multiplier=1,  # Prefetch 1 task at a time to prevent task pooling imbalances
    task_reject_on_worker_lost=True,  # Reject task if worker dies so it is requeued automatically
    task_track_started=True,  # Expose "STARTED" state updates
)

# Auto-discover tasks under app.tasks.document_tasks
celery_app.autodiscover_tasks(["app.tasks"], force=True)

# ── Celery Beat Schedule ──────────────────────────────────────────────────────
celery_app.conf.beat_schedule = {
    "daily-cleanup-temp-storage": {
        "task": "app.tasks.cleanup_temp_storage",
        "schedule": crontab(hour=0, minute=0),  # Run daily at midnight UTC
    }
}
