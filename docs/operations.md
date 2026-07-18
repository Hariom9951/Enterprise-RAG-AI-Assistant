# Enterprise RAG AI Assistant — Operations & Disaster Recovery Guide

This guide details database backup, storage replication, and disaster recovery procedures.

---

## 1. Automated Backups

Backups are executed using the `./scripts/backup.sh` utility. The script handles:
- Hot-dumping PostgreSQL schemas and data.
- Packaging upload volume attachments.
- Enforcing a 7-day retention window.

### Setting Up a Backup Cron Job:

To back up production data daily at 2:00 AM, register a cron job on the host machine:

```bash
crontab -e
```

Append the following line:
```cron
0 2 * * * cd /path/to/Enterprise-RAG-AI-Assistant && ./scripts/backup.sh >> ./backups/backup.log 2>&1
```

---

## 2. Restoring from Backups

Restorations are destructive operations that replace the active schema and file storage with historical states.

To restore, execute:

```bash
./scripts/restore.sh <TIMESTAMP>
```

Example:
```bash
./scripts/restore.sh 20260718_120000
```

Confirm the overwrite prompt to execute the schema drop and data reload.

---

## 3. Disaster Recovery Scenarios

### Scenario A: PostgreSQL Volume Corruption
If the postgres database fails to mount or reports disk block errors:
1. Stop the container stack: `docker compose down`
2. Delete the corrupted volume directory: `docker volume rm rag_postgres_data`
3. Spin up fresh containers: `docker compose up -d`
4. Execute restoration of the latest timestamp: `./scripts/restore.sh <LATEST_TIMESTAMP>`

### Scenario B: Storage Host Drive Full
If the document upload storage volume `/app/storage` runs out of space:
1. Attach a larger disk drive (or AWS EBS block) to the host.
2. Mount the volume path to the new directory.
3. Migrate existing assets:
   ```bash
   rsync -avz /var/lib/docker/volumes/rag_storage/_data/ /mnt/new_disk/rag_storage/
   ```
4. Update the `docker-compose.yml` volumes block to target the new path.
