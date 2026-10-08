#!/bin/sh
# Бэкап продового стенда: pg_dump баз core и fsp_connector (custom), архив тома MinIO, проверка дампов
# (pg_restore --list), удаление старше BACKUP_KEEP_DAYS. Каталог — BACKUP_DIR из .env (вне репозитория).
# Запуск из каталога стенда: ночью таймером fsp-backup (install-prod.sh) и перед каждым деплоем (deploy.sh).
#   [ENV_FILE=.env] sh infra/scripts/backup.sh [метка]
set -eu
LABEL="${1:-nightly}"
ENV_FILE="${ENV_FILE:-.env}"
env_get() { sed -n "s/^$1=//p" "$ENV_FILE" | tail -1; }
DIR="$(env_get BACKUP_DIR)"; DIR="${DIR:-$HOME/fsp-backups}"
KEEP="$(env_get BACKUP_KEEP_DAYS)"; KEEP="${KEEP:-7}"
PROJECT="$(env_get COMPOSE_PROJECT_NAME)"; PROJECT="${PROJECT:-fsp}"
TS=$(date -u +%Y%m%dT%H%M%SZ)
OUT="$DIR/$TS-$LABEL"
umask 077
mkdir -p "$OUT"

for db in core fsp_connector; do
  docker compose --env-file "$ENV_FILE" -p "$PROJECT" --profile core exec -T postgres \
    sh -c "pg_dump -U \"\$POSTGRES_USER\" -Fc $db" > "$OUT/$db.dump"
  docker compose --env-file "$ENV_FILE" -p "$PROJECT" --profile core exec -T postgres pg_restore --list < "$OUT/$db.dump" > /dev/null
done
docker run --rm -v "${PROJECT}_minio:/data:ro" -v "$OUT:/b" alpine tar czf /b/minio.tar.gz -C /data .
git rev-parse HEAD > "$OUT/commit" 2>/dev/null || true

# хранение: старше KEEP дней удаляем (бэкапы перед деплоем — тоже)
find "$DIR" -mindepth 1 -maxdepth 1 -type d -mtime +"$KEEP" -exec rm -rf {} +
echo "backup: $OUT ($(du -sh "$OUT" | cut -f1))"
