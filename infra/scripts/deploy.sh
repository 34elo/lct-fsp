#!/bin/sh
# Деплой и обслуживание стенда (docs/deploy.md «Прод»). Запускает self-hosted раннер из .github/workflows/cd.yml.
# Прод — каталог стенда с .env.server: .env собирается render-env.sh из infra/env/prod.env, .env.server и секретов
# окружения GitHub `prod`. Без .env.server (старый стенд на .env.demo) — деплой как раньше, без сборки .env.
#   deploy       — STAND_DIR на коммит SHA (из копии SRC_DIR), бэкап, сборка и запуск (миграции — core-migrate),
#                  проверка здоровья и смоук ML/LLM/бота (smoke-ml.sh); при сбое — откат кода на прежний коммит. Данные не трогаются.
#   backup       — внеочередной бэкап.
#   demo-reset   — демо-данные из снапшота (make demo-reset) и прогрев.
#   demo-reseed  — заново наполнить демо (make seed) и снять новый снапшот.
#   prod-init    — ОДИН РАЗ: перевести стенд в прод с нуля. Бэкап старого, удаление томов (БД, MinIO, очереди),
#                  новые внутренние секреты, запуск, демо-данные, снапшот, таймеры. Нужен CONFIRM=ПЕРЕСОЗДАТЬ.
set -eu
ACTION="${1:-deploy}"
: "${STAND_DIR:?задайте переменную репозитория STAND_DIR — каталог стенда на сервере}"
export PATH="$HOME/.local/bin:$PATH"
cd "$STAND_DIR"
SHORT=$(printf '%.7s' "${SHA:-}")
notify() { sh infra/scripts/notify.sh "$1" || true; }
is_prod() { [ -s .env.server ]; }
pg_running() { docker ps -q --filter label=com.docker.compose.project=fsp --filter label=com.docker.compose.service=postgres | grep -q .; }

env_file() {
  if grep -qs -E '^JWT_SECRET=.+' .env; then echo .env
  elif [ -s .env.demo ]; then echo .env.demo
  else echo "deploy: в $STAND_DIR нет .env или .env.demo" >&2; return 1
  fi
}
base() { p=$(sed -n 's/^GATEWAY_PORT=//p' "$(env_file)" | tail -1); echo "http://127.0.0.1:${p:-28080}"; }

# Здоровье: API, SPA и справочник (читает БД) — до 3 минут
health() {
  B=$(base); i=0
  while [ "$i" -lt 36 ]; do
    if curl -fsS -o /dev/null "$B/api/v1/healthz" && curl -fsS -o /dev/null "$B/" \
      && curl -fsS -o /dev/null "$B/api/v1/taxonomy/professions"; then return 0; fi
    i=$((i + 1)); sleep 5
  done
  return 1
}

# Смоук ML, LLM и бота (E42-6); причина сбоя остаётся в SMOKE_FAIL для алерта
smoke() {
  mkdir -p reports/seed
  if sh infra/scripts/smoke-ml.sh >reports/seed/smoke-ml.log 2>&1; then cat reports/seed/smoke-ml.log; return 0; fi
  cat reports/seed/smoke-ml.log >&2
  SMOKE_FAIL=$(grep '^FAIL' reports/seed/smoke-ml.log | cut -c1-300 | tr '
' ';')
  return 1
}

# reports/seed монтируется в fsp-mock: создаём заранее, иначе Docker создаст его от root
up() { mkdir -p reports/seed && make up; }

# Забрать коммит SHA из копии раннера (без своих ключей к GitHub) и перейти на него
checkout_sha() {
  : "${SHA:?нужен SHA}" "${SRC_DIR:?нужен SRC_DIR}"
  git fetch --quiet "$SRC_DIR" HEAD
  [ "$(git rev-parse FETCH_HEAD)" = "$SHA" ] || { echo "deploy: в $SRC_DIR не $SHA" >&2; exit 1; }
  git checkout --quiet --detach "$SHA"
}

# Шаг наполнения: при сбое печатаем хвост вывода и шлём его в алерт (E42-3); сид идемпотентен — повтор безопасен
run_step() {
  name="$1"; shift
  LOG="reports/seed/step-$name.log"
  if "$@" >"$LOG" 2>&1; then tail -n 5 "$LOG"; return 0; fi
  echo "deploy: шаг «$name» упал, хвост вывода:" >&2
  tail -n 30 "$LOG" >&2
  notify "🔴 Шаг «$name» упал: $(tail -n 8 "$LOG" | cut -c1-300)"
  return 1
}

seed_demo() {
  uv sync --all-packages --quiet
  mkdir -p reports/seed
  run_step seed make seed
  run_step demo-snapshot make demo-snapshot
}

case "$ACTION" in
deploy)
  PREV=$(git rev-parse HEAD)
  checkout_sha
  echo "deploy: $PREV → $SHA"
  if is_prod; then
    sh infra/scripts/render-env.sh
    if pg_running; then sh infra/scripts/backup.sh "pre-$SHORT"; fi
  fi
  SMOKE_FAIL=""
  if up && health && smoke; then
    docker image prune -f >/dev/null
    if is_prod; then sh infra/scripts/install-prod.sh; fi
    notify "✅ Развёрнут $SHORT: $(printf "%s" "${MSG:-}" | head -1)"
    echo "deploy: готово"
  else
    # Откат кода. Миграции назад не откатываются: новая миграция должна быть совместима с прежним кодом
    WHY="${SMOKE_FAIL:-API/SPA не ответили}"
    echo "deploy: сбой ($WHY), откат на $PREV" >&2
    make ps || true
    git checkout --quiet --detach "$PREV"
    if is_prod; then sh infra/scripts/render-env.sh; fi
    if up && health; then notify "❌ Деплой $SHORT упал: $WHY. Откатились на $(printf '%.7s' "$PREV")"
    else notify "🔴 Деплой $SHORT упал ($WHY), откат тоже не поднялся — нужен человек"; fi
    exit 1
  fi
  ;;
backup)
  sh infra/scripts/backup.sh manual
  ;;
demo-reset)
  make demo-reset
  make demo-warm
  notify "♻️ Демо-данные сброшены из снапшота"
  ;;
demo-reseed)
  seed_demo
  notify "🌱 Демо-данные пересозданы, снапшот обновлён"
  ;;
prod-init)
  [ "${CONFIRM:-}" = "ПЕРЕСОЗДАТЬ" ] || { echo "prod-init: нужен CONFIRM=ПЕРЕСОЗДАТЬ — тома стенда будут удалены" >&2; exit 2; }
  OLD=$(env_file || true)
  checkout_sha
  ALL="--profile core --profile ml --profile llm --profile bot --profile dev --profile obs"
  if [ -n "$OLD" ] && pg_running; then
    ENV_FILE="$OLD" sh infra/scripts/backup.sh before-prod-init
  fi
  if [ -n "$OLD" ]; then docker compose --env-file "$OLD" -p fsp $ALL down -v --remove-orphans; fi
  sh infra/scripts/gen-server-secrets.sh "$STAND_DIR"
  sh infra/scripts/render-env.sh
  SMOKE_FAIL=""
  up && health && smoke || { notify "🔴 prod-init: стенд не поднялся${SMOKE_FAIL:+: $SMOKE_FAIL}"; exit 1; }
  seed_demo
  sh infra/scripts/install-prod.sh
  sh infra/scripts/backup.sh after-prod-init
  notify "🚀 Прод развёрнут с нуля на $SHORT, демо-данные загружены"
  ;;
*)
  echo "deploy: неизвестное действие $ACTION" >&2; exit 2
  ;;
esac
