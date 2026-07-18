#!/usr/bin/env bash
# =============================================================================
# Enterprise RAG AI Assistant — Production Backup Script
# =============================================================================
# Performs a hot-backup of the PostgreSQL pgvector database and local storage.
# Retains backups for 7 days.
#
# Usage:
#   ./backup.sh
# =============================================================================

set -eo pipefail

TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
BACKUP_DIR="./backups"
DB_CONTAINER="rag_postgres"
BACKEND_CONTAINER="rag_backend"
RETENTION_DAYS=7

echo "[Backup] Starting backup at $(date)..."

# Ensure backup directory exists
mkdir -p "$BACKUP_DIR"

# ── 1. Backup PostgreSQL pgvector Database ───────────────────────────────────
echo "[Backup] Dumping database from $DB_CONTAINER..."
docker exec -t "$DB_CONTAINER" pg_dump -U raguser -d ragdb -F p | gzip > "$BACKUP_DIR/db_backup_$TIMESTAMP.sql.gz"
echo "[Backup] Database backup saved to $BACKUP_DIR/db_backup_$TIMESTAMP.sql.gz"

# ── 2. Backup Local Documents Storage Volume ─────────────────────────────────
echo "[Backup] Backing up storage files from $BACKEND_CONTAINER..."
TEMP_STORAGE_DIR="$BACKUP_DIR/storage_temp_$TIMESTAMP"
mkdir -p "$TEMP_STORAGE_DIR"

# Copy files from backend container to temporary host dir
docker cp "$BACKEND_CONTAINER:/app/storage/." "$TEMP_STORAGE_DIR"

# Remove any temporary ingestion folders in the backup copy to save space
rm -rf "$TEMP_STORAGE_DIR/temp"

# Tar and compress the document storage files
tar -czf "$BACKUP_DIR/storage_backup_$TIMESTAMP.tar.gz" -C "$TEMP_STORAGE_DIR" .
rm -rf "$TEMP_STORAGE_DIR"

echo "[Backup] Storage files backup saved to $BACKUP_DIR/storage_backup_$TIMESTAMP.tar.gz"

# ── 3. Retention Policy Check (Delete older than RETENTION_DAYS) ─────────────
echo "[Backup] Applying retention policy (keeping last $RETENTION_DAYS days)..."
find "$BACKUP_DIR" -name "db_backup_*" -mtime +$RETENTION_DAYS -delete
find "$BACKUP_DIR" -name "storage_backup_*" -mtime +$RETENTION_DAYS -delete

echo "[Backup] Backup process successfully completed at $(date)!"
