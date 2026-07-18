# Enterprise RAG AI Assistant — Scalability & Queue Tuning Guide

This guide details options for scaling the RAG Assistant, database pooling, and worker allocation.

---

## 1. FastAPI Web Server Scaling

FastAPI runs on Uvicorn. In production:
- Configure multiple workers per API instance using the `WORKERS` env variable (recommended: `2 * CPUs + 1`).
- Run multiple container instances behind a round-robin load-balancer (e.g. Nginx, HAProxy, AWS ALB).
- The API is fully stateless. User sessions and conversation memory are loaded dynamically from the Database and Redis, allowing horizontal scaling.

---

## 2. Celery Worker Queue Tuning

### Adjusting Concurrency:
Celery workers default to the number of CPU cores. You can tune this in the Docker Compose command:

```yaml
command: celery -A app.tasks.celery_app worker --loglevel=info --concurrency=4
```

- **I/O bound workloads** (e.g., text extraction, HTTP calls): Higher concurrency is fine (e.g. `8` or `16`).
- **CPU bound workloads** (e.g., local sentence embedding models): Set concurrency equal to the number of CPU cores or CPU-bound threads (e.g. `2` or `4`) to prevent core thrashing.

### Prefetch Multiplier:
We configure `worker_prefetch_multiplier = 1` in `celery_app.py`. This ensures workers only grab 1 task at a time, preventing imbalance when processing documents of widely varying sizes.

---

## 3. Database Pooling Tuning

Configure SQLAlchemy connection pools in `settings.py` or `.env.production`:
- **`DATABASE_POOL_SIZE`** (default: `20`): Maximum persistent connection pool size.
- **`DATABASE_MAX_OVERFLOW`** (default: `30`): Allow up to 30 additional connection bursts under heavy API traffic spikes.
- Connection pre-ping check is enabled (`pool_pre_ping=True`) to automatically discard stale database sockets.
