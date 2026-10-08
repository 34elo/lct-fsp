#!/bin/sh
# Деплой стенда (docs/deploy.md «CI/CD»). Запускает self-hosted раннер из .github/workflows/cd.yml.
#   deploy       — STAND_DIR на коммит SHA (из копии SRC_DIR), пересборка и запуск (миграции — сервис core-migrate),
#                  проверка здоровья; при сбое — откат на прежний коммит. Данные стенда не трогаются.
#   demo-reset   — демо-данные из снапшота (make demo-reset) и прогрев.
#   demo-reseed  — заново наполнить демо (make seed) и снять новый снапшот.
# Секреты стенда (.env или .env.demo в STAND_DIR) скрипт не создаёт: новые случайные пароли не подошли бы к томам БД.
set -eu
ACTION="${1:-deploy}"
: "${STAND_DIR:?задайте переменную репозитория STAND_DIR — каталог стенда на сервере}"
export PATH="$HOME/.local/bin:$PATH"
cd "$STAND_DIR"

if grep -qs -E '^JWT_SECRET=.+' .env; then ENV_FILE=.env
elif [ -s .env.demo ]; then ENV_FILE=.env.demo
else echo "deploy: в $STAND_DIR нет .env или .env.demo" >&2; exit 1
fi
PORT=$(sed -n 's/^GATEWAY_PORT=//p' "$ENV_FILE"); BASE="http://127.0.0.1:${PORT:-28080}"

# Здоровье: API, SPA и справочник (читает БД) — до 3 минут
health() {
  i=0
  while [ "$i" -lt 36 ]; do
    if curl -fsS -o /dev/null "$BASE/api/v1/healthz" \
      && curl -fsS -o /dev/null "$BASE/" \
      && curl -fsS -o /dev/null "$BASE/api/v1/taxonomy/professions"; then
      return 0
    fi
    i=$((i + 1)); sleep 5
  done
  return 1
}

# reports/seed монтируется в fsp-mock: создаём заранее, иначе Docker создаст его от root
up() { mkdir -p reports/seed && make up; }

case "$ACTION" in
deploy)
  : "${SHA:?нужен SHA}" "${SRC_DIR:?нужен SRC_DIR}"
  PREV=$(git rev-parse HEAD)
  # копия раннера стоит на нужном коммите: забираем её HEAD и сверяем с SHA
  git fetch --quiet "$SRC_DIR" HEAD
  [ "$(git rev-parse FETCH_HEAD)" = "$SHA" ] || { echo "deploy: в $SRC_DIR не $SHA" >&2; exit 1; }
  git checkout --quiet --detach "$SHA"
  echo "deploy: $PREV → $SHA"
  if up && health; then
    docker image prune -f >/dev/null
    echo "deploy: готово, $BASE"
  else
    # Откат кода. Миграции назад не откатываются: новая миграция должна быть совместима с прежним кодом
    echo "deploy: сбой, откат на $PREV" >&2
    make ps || true
    git checkout --quiet --detach "$PREV"
    up && health || echo "deploy: откат тоже не поднялся, нужен человек" >&2
    exit 1
  fi
  ;;
demo-reset)
  make demo-reset
  make demo-warm
  ;;
demo-reseed)
  uv sync --all-packages --quiet
  mkdir -p reports/seed
  make seed
  make demo-snapshot
  ;;
*)
  echo "deploy: неизвестное действие $ACTION (deploy | demo-reset | demo-reseed)" >&2; exit 2
  ;;
esac
