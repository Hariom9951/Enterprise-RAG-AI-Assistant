#!/usr/bin/env bash
# =============================================================================
# Enterprise RAG AI Assistant — Docker Integration Healthcheck Verify
# =============================================================================
# Starts the compose stack and polls service health statuses until healthy.
# Returns 0 on success, 1 on failure.
# =============================================================================

set -e

echo "[DockerTest] Starting production compose stack..."
docker compose -f docker-compose.yml up --build -d

echo "[DockerTest] Waiting for services to initialize health states..."

SERVICES=("rag_postgres" "rag_redis" "rag_backend" "rag_celery_worker")
MAX_WAIT_SECONDS=60
POLL_INTERVAL=5
ELAPSED=0

check_health() {
    local container_name="$1"
    local status
    status=$(docker inspect --format='{{json .State.Health.Status}}' "$container_name" 2>/dev/null || echo "offline")
    # Clean quotes
    status="${status%\"}"
    status="${status#\"}"
    echo "$status"
}

all_healthy=false

while [ "$ELAPSED" -lt "$MAX_WAIT_SECONDS" ]; do
    all_healthy=true
    echo "--- Health Check Poll (Elapsed: ${ELAPSED}s) ---"
    
    for service in "${SERVICES[@]}"; do
        status=$(check_health "$service")
        echo "Service: $service -> Health: $status"
        if [ "$status" != "healthy" ]; then
            all_healthy=false
        fi
    done
    
    if [ "$all_healthy" = true ]; then
        echo "[DockerTest] SUCCESS: All services are healthy!"
        break
    fi
    
    sleep "$POLL_INTERVAL"
    ELAPSED=$((ELAPSED + POLL_INTERVAL))
done

if [ "$all_healthy" = false ]; then
    echo "[DockerTest] ERROR: Health check timeout reached. Not all services became healthy."
    exit 1
fi

echo "[DockerTest] Complete stack verified successfully."
exit 0
