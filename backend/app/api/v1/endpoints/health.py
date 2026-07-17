"""
Enterprise RAG AI Assistant — API v1 Endpoints: Health Check
=============================================================
GET /health  →  {"status": "healthy", ...}

This endpoint is designed for:
  - Kubernetes liveness / readiness probes
  - Load-balancer health checks
  - Uptime monitoring services

It intentionally requires no authentication so that infrastructure
can poll it without credentials.
"""

from datetime import UTC, datetime

from fastapi import APIRouter, status

from app.config.settings import settings
from app.schemas.common import HealthStatus

router = APIRouter()


@router.get(
    "/health",
    response_model=HealthStatus,
    status_code=status.HTTP_200_OK,
    summary="Health Check",
    description=(
        "Returns the overall health status of the API and its downstream components. "
        "A 200 response with status='healthy' indicates the service is ready to serve traffic."
    ),
    tags=["health"],
)
async def health_check() -> HealthStatus:
    """
    **Liveness & readiness probe endpoint.**

    Returns:
        A ``HealthStatus`` object containing:
        - ``status``: Overall health (healthy | degraded | unhealthy)
        - ``version``: Current application version
        - ``environment``: Deployment environment
        - ``timestamp``: UTC time of the check
        - ``components``: Per-component health map (expanded in later phases)
    """
    # In later phases, check real downstream dependencies here.
    # Example:
    #   db_ok = await check_database_connection()
    #   vector_ok = await check_vector_store()
    # For Phase 1, all components are trivially "healthy".
    components: dict[str, str] = {
        "api": "healthy",
        # Phase 3: "database": "healthy" | "unhealthy"
        # Phase 4: "vector_store": "healthy" | "unhealthy"
        # Phase 4: "llm_provider": "healthy" | "unhealthy"
    }

    # Determine overall status from component statuses.
    if all(v == "healthy" for v in components.values()):
        overall_status = "healthy"
    elif any(v == "unhealthy" for v in components.values()):
        overall_status = "unhealthy"
    else:
        overall_status = "degraded"

    return HealthStatus(
        status=overall_status,
        version=settings.app_version,
        environment=settings.environment,
        timestamp=datetime.now(UTC),
        components=components,
    )
