#!/bin/sh
# Мониторинг продового стенда (таймер fsp-healthcheck, раз в 5 минут, install-prod.sh). Проверяет API, SPA,
# справочник (БД), LLM-сервер на хосте и состояние контейнеров. Алерт в Telegram только при смене
# состояния (упало / восстановилось), без спама. Состояние — в .health-state каталога стенда.
#   sh infra/scripts/healthcheck.sh   (из каталога стенда)
set -u
PORT=$(sed -n 's/^GATEWAY_PORT=//p' .env | tail -1); BASE="http://127.0.0.1:${PORT:-28080}"
PROJECT=$(sed -n 's/^COMPOSE_PROJECT_NAME=//p' .env | tail -1); PROJECT="${PROJECT:-fsp}"
problems=""
check() { curl -fsS -m 10 -o /dev/null "$2" || problems="$problems\n- $1 не отвечает"; }
check "API" "$BASE/api/v1/healthz"
check "Сайт" "$BASE/"
check "БД (справочник)" "$BASE/api/v1/taxonomy/professions"
check "LLM-сервер" "http://127.0.0.1:18090/health"
bad=$(docker ps -a --filter "label=com.docker.compose.project=$PROJECT" --format '{{.Names}} {{.Status}}' \
  | grep -v -E 'init|migrate' | grep -E 'unhealthy|Exited|Restarting' || true)
[ -z "$bad" ] || problems="$problems\n- контейнеры:\n$bad"

STATE=.health-state
prev=$(cat "$STATE" 2>/dev/null || echo ok)
if [ -n "$problems" ]; then
  echo fail > "$STATE"
  [ "$prev" = fail ] || sh infra/scripts/notify.sh "$(printf '🔴 Стенд неисправен%b' "$problems")"
  printf 'healthcheck: FAIL%b\n' "$problems"
  exit 1
fi
echo ok > "$STATE"
[ "$prev" = ok ] || sh infra/scripts/notify.sh "🟢 Стенд снова в порядке"
echo "healthcheck: ok"
