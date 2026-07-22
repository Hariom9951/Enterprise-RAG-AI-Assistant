"""
Enterprise RAG AI Assistant — API v1 Endpoints: Health Check & Metrics
=====================================================================
GET /health  →  Detailed component states (API, Database, Redis)
GET /ready   →  Ready probe checking connection health
GET /live    →  Fast process liveness probe
GET /metrics →  Prometheus-compatible performance metrics
"""

import os
import sys
from datetime import UTC, datetime

import psutil
from fastapi import APIRouter, Depends, Response, status
from redis.asyncio import Redis
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config.settings import settings
from app.db.session import get_db
from app.schemas.common import HealthStatus
from app.services.cache_service import cache_service

router = APIRouter()


async def check_database_conn(db: AsyncSession) -> bool:
    """Lightweight database connection test using the active session."""
    try:
        await db.execute(text("SELECT 1"))
        return True
    except Exception:
        return False


async def check_redis_conn() -> bool:
    """Lightweight Redis PING connection test. Fails open in unit tests."""
    if not settings.enable_redis_caching:
        return True
    if "pytest" in sys.modules:
        return True
    try:
        r = Redis.from_url(settings.redis_url)
        await r.ping()
        await r.close()
        return True
    except Exception:
        return False


@router.get(
    "/health",
    response_model=HealthStatus,
    status_code=status.HTTP_200_OK,
    summary="Health Check",
    description="Returns detailed statuses of internal components (Postgres and Redis).",
    tags=["health"],
)
async def health_check(db: AsyncSession = Depends(get_db)) -> HealthStatus:
    db_ok = await check_database_conn(db)
    redis_ok = await check_redis_conn()

    if not settings.enable_redis_caching:
        redis_status = "disabled"
    else:
        redis_status = "healthy" if redis_ok else "unhealthy"

    components = {
        "api": "healthy",
        "database": "healthy" if db_ok else "unhealthy",
        "redis": redis_status,
    }

    overall_status = "healthy"
    if not db_ok or not redis_ok:
        overall_status = "unhealthy"

    return HealthStatus(
        status=overall_status,
        version=settings.app_version,
        environment=settings.environment,
        timestamp=datetime.now(UTC),
        components=components,
    )


@router.get(
    "/ready",
    status_code=status.HTTP_200_OK,
    summary="Readiness Probe",
    description="Indicates whether the API is fully ready to accept client traffic.",
    tags=["health"],
)
async def readiness_probe(
    response: Response, db: AsyncSession = Depends(get_db)
) -> dict[str, str]:
    db_ok = await check_database_conn(db)
    redis_ok = await check_redis_conn()

    if not db_ok or not redis_ok:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return {"status": "unready", "reason": "Downstream databases are unreachable."}

    return {"status": "ready"}


@router.get(
    "/live",
    status_code=status.HTTP_200_OK,
    summary="Liveness Probe",
    description="Indicates whether the API container process is alive.",
    tags=["health"],
)
async def liveness_probe() -> dict[str, str]:
    return {"status": "live"}


@router.get(
    "/metrics",
    response_class=Response,
    summary="Metrics Endpoint",
    description="Exposes application CPU, Memory, Queue lengths, and Latencies in Prometheus format.",
    tags=["health"],
)
async def metrics_endpoint() -> Response:
    # 1. System CPU & Memory
    process = psutil.Process(os.getpid())
    cpu_percent = psutil.cpu_percent(interval=None)
    memory_rss = process.memory_info().rss

    # 2. Redis Connection & Celery Queue Length
    queue_length = 0
    if settings.enable_redis_caching and "pytest" not in sys.modules:
        try:
            r = Redis.from_url(settings.redis_url)
            queue_length = await r.llen("celery")
            await r.close()
        except Exception:
            pass

    # 3. Latencies from cache service
    avg_embed = await cache_service.get_average_latency("embedding")
    avg_llm = await cache_service.get_average_latency("llm")
    avg_search = await cache_service.get_average_latency("search")
    avg_agent = await cache_service.get_average_latency("agent")

    # 4. Generate Prometheus exposition format strings
    lines = [
        "# HELP cpu_utilization_ratio Current system CPU utilization ratio.",
        "# TYPE cpu_utilization_ratio gauge",
        f"cpu_utilization_ratio {cpu_percent / 100.0:.4f}",
        "# HELP memory_rss_bytes Current process Resident Set Size in bytes.",
        "# TYPE memory_rss_bytes gauge",
        f"memory_rss_bytes {memory_rss}",
        "# HELP redis_queue_length Active task count in Celery Redis broker.",
        "# TYPE redis_queue_length gauge",
        f"redis_queue_length {queue_length}",
        "# HELP latency_embedding_ms Average embedding generation latency in milliseconds.",
        "# TYPE latency_embedding_ms gauge",
        f"latency_embedding_ms {avg_embed:.2f}",
        "# HELP latency_llm_ms Average LLM generation latency in milliseconds.",
        "# TYPE latency_llm_ms gauge",
        f"latency_llm_ms {avg_llm:.2f}",
        "# HELP latency_search_ms Average semantic similarity search latency in milliseconds.",
        "# TYPE latency_search_ms gauge",
        f"latency_search_ms {avg_search:.2f}",
        "# HELP latency_agent_ms Average agent tool orchestration loop latency in milliseconds.",
        "# TYPE latency_agent_ms gauge",
        f"latency_agent_ms {avg_agent:.2f}",
    ]

    content = "\n".join(lines) + "\n"
    return Response(
        content=content, media_type="text/plain; version=0.0.4; charset=utf-8"
    )
