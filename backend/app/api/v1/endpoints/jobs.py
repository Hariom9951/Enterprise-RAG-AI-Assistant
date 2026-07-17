"""
Enterprise RAG AI Assistant — Celery Background Jobs API Router
=============================================================
Defines endpoint for checking current task queues and task metadata states.
"""

from __future__ import annotations

from typing import Any

from celery.result import AsyncResult
from fastapi import APIRouter, Depends

from app.dependencies import get_current_active_user
from app.models.user import User
from app.tasks.celery_app import celery_app

router = APIRouter()


@router.get(
    "/{job_id}",
    summary="Get background task execution details.",
    description="Poll task execution status, execution result, or exception error messages.",
)
async def get_job_status(
    job_id: str,
    current_user: User = Depends(get_current_active_user),
) -> dict[str, Any]:
    """Retrieve state and payload metrics from Celery's result backend."""
    # Instantiates result inspector
    res = AsyncResult(job_id, app=celery_app)

    # Process return body format
    result_data: Any = None
    error_data: str | None = None

    if res.state == "SUCCESS":
        result_data = res.result
    elif res.state == "FAILURE":
        error_data = str(res.result)

    return {
        "job_id": job_id,
        "state": res.state,
        "completed": res.ready(),
        "result": result_data,
        "error": error_data,
    }
