#!/bin/sh
# Снапшоты демо-витрины (evaluation.md §4). Вызывается из Makefile:
#   COMPOSE="docker compose ..." GATEWAY_PORT=28080 sh infra/scripts/demo.sh snapshot|reset|warm
# snapshot: pg_dump core и fsp_connector (формат custom) + reports/seed/fsp-mock.json -> infra/snapshots/ (в git не идёт).
# reset: остановить сервисы -> восстановить БД -> FLUSHALL Redis -> вернуть fsp-mock -> поднять сервисы.
# warm: логин демо-аккаунтов, первый поиск, профиль (прогрев кешей).
set -eu
: "${COMPOSE:?нужен COMPOSE (см. Makefile)}"
SNAP=infra/snapshots
SEED=reports/seed/fsp-mock.json
APP="core-api core-worker core-scheduler fsp-connector fsp-connector-worker ml-worker-llm ml-worker-code fsp-mock"
DBS="core fsp_connector"
PW="${DEMO_PASSWORD:-demo-pass-1234}"
BASE="http://127.0.0.1:${GATEWAY_PORT:-28080}"

pg() { $COMPOSE exec -T postgres sh -c "$1"; }

case "${1:-}" in
snapshot)
  mkdir -p "$SNAP"
  for db in $DBS; do
    pg "pg_dump -U \"\$POSTGRES_USER\" -Fc $db" > "$SNAP/$db.dump.tmp"
    mv "$SNAP/$db.dump.tmp" "$SNAP/$db.dump"
  done
  [ -f "$SEED" ] && cp "$SEED" "$SNAP/fsp-mock.json"
  ls -la "$SNAP"
  ;;
reset)
  for f in $DBS; do [ -s "$SNAP/$f.dump" ] || { echo "нет $SNAP/$f.dump: сначала make demo-snapshot" >&2; exit 1; }; done
  START=$(date +%s)
  $COMPOSE stop $APP
  for db in $DBS; do
    owner=core; [ "$db" = fsp_connector ] && owner=fspc
    pg "psql -q -v ON_ERROR_STOP=1 -U \"\$POSTGRES_USER\" -d postgres -c 'DROP DATABASE IF EXISTS $db WITH (FORCE)' -c 'CREATE DATABASE $db OWNER $owner'"
    $COMPOSE exec -T postgres sh -c "pg_restore -U \"\$POSTGRES_USER\" -d $db --exit-on-error" < "$SNAP/$db.dump"
  done
  # кеши, лимиты, idempotency-ключи, сессии
  $COMPOSE exec -T redis redis-cli FLUSHALL
  if [ -f "$SNAP/fsp-mock.json" ]; then mkdir -p reports/seed; cp "$SNAP/fsp-mock.json" "$SEED"; fi
  $COMPOSE up -d --no-deps --force-recreate fsp-mock
  $COMPOSE up -d --no-deps --wait $APP
  echo "reset: $(( $(date +%s) - START )) c"
  ;;
warm)
  for u in olga anya dima admin; do
    code=$(curl -s -o /dev/null -w '%{http_code}' -X POST "$BASE/api/v1/auth/login" -H 'Content-Type: application/json' \
      -d "{\"email\":\"$u@demo.fsp.test\",\"password\":\"$PW\"}")
    echo "login $u: $code"
  done
  tok() { curl -s -X POST "$BASE/api/v1/auth/login" -H 'Content-Type: application/json' \
      -d "{\"email\":\"$1@demo.fsp.test\",\"password\":\"$PW\"}" | sed -n 's/.*"access_token":"\([^"]*\)".*/\1/p'; }
  T=$(tok olga); A=$(tok anya)
  echo "search olga: $(curl -s -o /dev/null -w '%{http_code} %{time_total}s' -X POST "$BASE/api/v1/search/candidates" \
    -H "Authorization: Bearer $T" -H 'Content-Type: application/json' -d '{"filters":{},"sort":"match"}')"
  echo "vacancies olga: $(curl -s -o /dev/null -w '%{http_code}' "$BASE/api/v1/vacancies" -H "Authorization: Bearer $T")"
  echo "profile anya: $(curl -s -o /dev/null -w '%{http_code} %{time_total}s' "$BASE/api/v1/candidates/me/profile" -H "Authorization: Bearer $A")"
  ;;
*) echo "usage: demo.sh snapshot|reset|warm" >&2; exit 2 ;;
esac
