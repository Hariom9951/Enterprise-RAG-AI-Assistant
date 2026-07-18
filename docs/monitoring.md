# Enterprise RAG AI Assistant — Production Monitoring Guide

This guide describes healthcheck probes, metrics collection, and logging aggregations.

---

## 1. Health Checks Probes

Probes are exposed on public API gateway endpoints and require no authentication to accommodate infrastructure health polling.

| Target | Path | Purpose | Success | Failure |
|---|---|---|---|---|
| Liveness | `/api/v1/live` | Confirms ASGI runner is active. | `200 OK` | Container crash (no response) |
| Readiness | `/api/v1/ready` | Confirms db & redis connections are open. | `200 OK` | `503 Service Unavailable` |
| Health | `/api/v1/health` | Detailed JSON status of components. | `200 OK` | `200 OK` (checks JSON fields) |

---

## 2. Prometheus Metrics

Performance metrics are exposed on `/api/v1/metrics` in the Prometheus standard exposition format.

### Key Metrics Exposed:
- `cpu_utilization_ratio`: System CPU utilization gauge.
- `memory_rss_bytes`: Resident Set Size memory consumption in bytes.
- `redis_queue_length`: Length of active Celery task queues in Redis.
- `latency_embedding_ms`: Average duration of embedding runs.
- `latency_llm_ms`: Average duration of LLM generation calls.
- `latency_search_ms`: Average duration of semantic vector searches.
- `latency_agent_ms`: Average duration of agent tool calling loops.

---

## 3. Logs Routing

Loguru routes JSON logs to separate rotating files under the `logs/` directory:

1. **`app.log`**: General FastAPI runtime events.
2. **`api.log`**: HTTP request/response traces (contains request IDs, paths, statuses, durations).
3. **`worker.log`**: Celery background processing and beat execution traces.
4. **`error.log`**: Warnings and exceptions (level `>= WARNING`).
5. **`audit.log`**: Compliance records (user logins, registrations, upload actions).
