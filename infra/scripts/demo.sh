#!/bin/sh
# Демо-витрина. Вызывается из Makefile:
#   COMPOSE="docker compose ..." GATEWAY_PORT=28080 sh infra/scripts/demo.sh snapshot|reset|warm
# Сбрасываются только демо-данные (is_demo): реальные регистрации и их данные не трогаются.
# snapshot: демо-строки core и fsp_connector -> таблицы demo_snap__* тех же БД (python -m app.demo,
#           python -m fsp_connector.demo) + reports/seed/fsp-mock.json -> infra/snapshots/.
#           Делать на чистой витрине сразу после make seed.
# reset: удалить всё, что касается демо (герои, жюри и их песочницы, попытки, интересы,
#        приглашения, ФСП-привязки), вернуть демо из снапшота, вернуть fsp-mock. Без остановки стека.
# warm: логин демо-аккаунтов, первый поиск, профиль (прогрев кешей).
set -eu
: "${COMPOSE:?нужен COMPOSE (см. Makefile)}"
SNAP=infra/snapshots
SEED=reports/seed/fsp-mock.json
PW="${DEMO_PASSWORD:-demo-pass-1234}"
BASE="http://127.0.0.1:${GATEWAY_PORT:-28080}"

core_demo() { $COMPOSE exec -T core-api python -m app.demo "$1"; }
fspc_demo() { $COMPOSE exec -T fsp-connector python -m fsp_connector.demo "$1"; }

case "${1:-}" in
snapshot)
  mkdir -p "$SNAP"
  IDS=$(core_demo snapshot)
  echo "$IDS" | fspc_demo snapshot
  [ -f "$SEED" ] && cp "$SEED" "$SNAP/fsp-mock.json"
  echo "snapshot: $(echo "$IDS" | grep -c '^DEMO_ID ') демо-аккаунтов"
  ;;
reset)
  START=$(date +%s)
  IDS=$(core_demo reset)
  echo "$IDS" | fspc_demo reset
  if [ -f "$SNAP/fsp-mock.json" ]; then
    mkdir -p reports/seed; cp "$SNAP/fsp-mock.json" "$SEED"
    $COMPOSE up -d --no-deps --force-recreate fsp-mock
  fi
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
