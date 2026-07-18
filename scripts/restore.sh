#!/usr/bin/env bash
# =============================================================================
# Enterprise RAG AI Assistant — Production Restore Script
# =============================================================================
# Restores the PostgreSQL database and local storage from a specific backup timestamp.
# Warning: This is a destructive operation that replaces active data.
#
# Usage:
#   ./restore.sh <backup_timestamp>
#
# Example:
#   ./restore.sh 20260718_120000
# =============================================================================

set -eo pipefail

if [ -z "$1" ]; then
    echo "Usage: $0 <backup_timestamp>"
    echo "Available backups in ./backups:"
    ls -la ./backups || echo "No backups folder found."
    exit 1
fi

TIMESTAMP="$1"
BACKUP_DIR="./backups"
DB_CONTAINER="rag_postgres"
BACKEND_CONTAINER="rag_backend"

DB_BACKUP="$BACKUP_DIR/db_backup_$TIMESTAMP.sql.gz"
STORAGE_BACKUP="$BACKUP_DIR/storage_backup_$TIMESTAMP.tar.gz"

# ── 1. Check Backup Files Existence ──────────────────────────────────────────
if [ ! -f "$DB_BACKUP" ]; then
    echo "Error: Database backup file not found: $DB_BACKUP"
    exit 1
fi

if [ ! -f "$STORAGE_BACKUP" ]; then
    echo "Error: Storage backup file not found: $STORAGE_BACKUP"
    exit 1
fi

read -p "WARNING: This will overwrite active database records and document files. Proceed? (y/N) " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo "Restore cancelled."
    exit 0
fi

echo "[Restore] Initiating restoration process..."

# ── 2. Restore PostgreSQL Database ───────────────────────────────────────────
echo "[Restore] Restoring database schema and records..."
# Drop and recreate schema to clean old tables
docker exec -i "$DB_CONTAINER" psql -U raguser -d ragdb -c "DROP SCHEMA public CASCADE; CREATE SCHEMA public;"
# Decompress and feed SQL dump directly to PostgreSQL
gunzip -c "$DB_BACKUP" | docker exec -i "$DB_CONTAINER" psql -U raguser -d ragdb

echo "[Restore] Database restored successfully."

# ── 3. Restore Local Documents Storage ───────────────────────────────────────
echo "[Restore] Restoring storage volume files..."
TEMP_RESTORE_DIR="$BACKUP_DIR/storage_restore_temp"
mkdir -p "$TEMP_RESTORE_DIR"

# Decompress files to temp directory
tar -xzf "$STORAGE_BACKUP" -C "$TEMP_RESTORE_DIR"

# Clear existing uploads in the container
docker exec "$BACKEND_CONTAINER" rm -rf /app/storage/*

# Copy new files into the container storage directory
docker cp "$TEMP_RESTORE_DIR/." "$BACKEND_CONTAINER:/app/storage/"
rm -rf "$TEMP_RESTORE_DIR"

# Ensure correct permissions in container
docker exec "$BACKEND_CONTAINER" chown -R appuser:appgroup /app/storage

echo "[Restore] Storage volume files restored successfully."
echo "[Restore] Complete restoration finished successfully!"
