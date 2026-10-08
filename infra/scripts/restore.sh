#!/bin/sh
# Восстановление продового стенда из бэкапа backup.sh. Останавливает приложение, пересоздаёт базы,
# возвращает том MinIO, чистит Redis, поднимает сервисы. Только по явному подтверждению.
#   sh infra/scripts/restore.sh <каталог бэкапа> --yes   (из каталога стенда)
set -eu
SRC="${1:?нужен каталог бэкапа}"; [ "${2:-}" = "--yes" ] || { echo "restore: добавьте --yes — данные стенда будут заменены" >&2; exit 2; }
for f in core.dump fsp_connector.dump minio.tar.gz; do [ -s "$SRC/$f" ] || { echo "restore: нет $SRC/$f" >&2; exit 1; }; done
PROJECT=$(sed -n 's/^COMPOSE_PROJECT_NAME=//p' .env | tail -1); PROJECT="${PROJECT:-fsp}"
C="docker compose --env-file .env -p $PROJECT --profile core --profile ml --profile llm --profile bot"
APP="core-api core-worker core-scheduler fsp-connector fsp-connector-worker ml-api ml-worker-llm ml-worker-code bot gateway"
$C stop $APP minio || true
for db in core fsp_connector; do
  owner=core; [ "$db" = fsp_connector ] && owner=fspc
  $C exec -T postgres sh -c "psql -q -v ON_ERROR_STOP=1 -U \"\$POSTGRES_USER\" -d postgres -c 'DROP DATABASE IF EXISTS $db WITH (FORCE)' -c 'CREATE DATABASE $db OWNER $owner'"
  $C exec -T postgres sh -c "pg_restore -U \"\$POSTGRES_USER\" -d $db --exit-on-error" < "$SRC/$db.dump"
done
docker run --rm -v "${PROJECT}_minio:/data" -v "$SRC:/b:ro" alpine sh -c 'rm -rf /data/* /data/.[!.]* 2>/dev/null; tar xzf /b/minio.tar.gz -C /data'
$C exec -T redis redis-cli FLUSHALL
make up
echo "restore: стенд восстановлен из $SRC"
