#!/bin/sh
# Смоук ML-части стенда после деплоя: ml-api, эмбеддинги, LLM, бот.
# Каждая проверка при сбое печатает в stderr строку «FAIL <что>: <причина>» (её deploy.sh кладёт в алерт),
# в конце — код 1, если упала хотя бы одна. Секреты и ключи в вывод не попадают.
#   ml-api /healthz   — отвечает, embedder не down (fallback допустим: запасные векторы);
#                       поле llm не смотрим: у ml-api оно отражает режим ML_FAKE, а не доступность llama-server
#   /v1/embeddings    — 200 и непустой ответ
#   LLM               — короткий запрос к LLM_BASE_URL изнутри ml-api, если LLM_ENABLED=true
#   бот               — контейнер запущен и не перезапускается, если в env-файле задан TG_BOT_TOKEN
# Переменные: ENV_FILE (по умолчанию как у deploy.sh), SMOKE_TRIES (6) и SMOKE_SLEEP (5) — повторы на прогрев.
set -u
ENVF="${ENV_FILE:-}"
if [ -z "$ENVF" ]; then
  if grep -qs -E '^JWT_SECRET=.+' .env; then ENVF=.env; else ENVF=.env.demo; fi
fi
TRIES="${SMOKE_TRIES:-6}"; PAUSE="${SMOKE_SLEEP:-5}"
getv() { sed -n "s/^$1=//p" "$ENVF" 2>/dev/null | tail -1; }
LLM_ENABLED=$(getv LLM_ENABLED); BOT_TOKEN=$(getv TG_BOT_TOKEN)
BOT_PROFILE=""; [ -n "$BOT_TOKEN" ] && BOT_PROFILE="--profile bot"
# shellcheck disable=SC2086
dc() { docker compose --env-file "$ENVF" -p fsp --profile core --profile ml --profile llm $BOT_PROFILE "$@"; }
# Python внутри ml-api: порт и окружение сервиса уже настроены, наружу порты не публикуются
inml() { dc exec -T ml-api python -c "$1" 2>&1; }

FAILED=0
fail() { echo "FAIL $1: $2" >&2; FAILED=1; }
# retry <команда…>: до TRIES попыток, вывод последней — в $OUT
retry() {
  n=0
  while :; do
    n=$((n + 1))
    if OUT=$("$@"); then return 0; fi
    [ "$n" -ge "$TRIES" ] && return 1
    sleep "$PAUSE"
  done
}

# Проверки печатают в stdout либо итог (успех), либо причину (сбой); retry кладёт вывод в OUT
check_healthz() {
  out=$(inml 'import urllib.request as u; print(u.urlopen("http://127.0.0.1:8100/healthz", timeout=10).read().decode())')     || { echo "ml-api не ответил: $(echo "$out" | tail -n 1 | cut -c1-200)"; return 1; }
  case "$out" in *'"embedder"'*) ;; *) echo "ответ без поля embedder: $(echo "$out" | tail -n 1 | cut -c1-200)"; return 1 ;; esac
  if echo "$out" | grep -q -E '"embedder" *: *"down"'; then echo "embedder=down (модель эмбеддингов не работает)"; return 1; fi
  echo "$out" | tail -n 1 | cut -c1-200
}

check_embeddings() {
  out=$(inml 'import json, urllib.request as u
r = u.Request("http://127.0.0.1:8100/v1/embeddings", json.dumps({"texts": ["smoke"], "kind": "query"}).encode(), {"Content-Type": "application/json"})
b = json.load(u.urlopen(r, timeout=30))
assert b, "пустой ответ"
print("ok")') || { echo "$out" | tail -n 1 | cut -c1-200; return 1; }
}

check_llm() {
  out=$(inml 'import json, os, urllib.request as u
base = os.environ.get("LLM_BASE_URL", "").rstrip("/")
assert base, "LLM_BASE_URL не задан"
assert os.environ.get("LLM_API_KEY"), "LLM_API_KEY не задан"
h = {"Content-Type": "application/json", "Authorization": "Bearer " + os.environ["LLM_API_KEY"]}
body = {"model": os.environ.get("LLM_MODEL", ""), "max_tokens": 4, "messages": [{"role": "user", "content": "ping"}]}
u.urlopen(u.Request(base + "/chat/completions", json.dumps(body).encode(), h), timeout=60).read()
print("ok")') || { echo "$out" | tail -n 1 | cut -c1-200; return 1; }
}

check_bot() {
  cid=$(dc ps -q bot 2>/dev/null | head -n 1)
  if [ -z "$cid" ]; then echo "контейнер bot не создан"; return 1; fi
  st=$(docker inspect -f '{{.State.Running}} {{.State.Restarting}}' "$cid" 2>&1 | tail -n 1)
  if [ "$st" != "true false" ]; then echo "контейнер bot не работает или перезапускается (running/restarting: $st)"; return 1; fi
}

if retry check_healthz; then echo "ok ml-api /healthz: $OUT"; else fail "ml-api /healthz" "$OUT"; fi
if retry check_embeddings; then echo "ok /v1/embeddings"; else fail "/v1/embeddings" "$OUT"; fi
if [ "$LLM_ENABLED" = "true" ]; then
  if retry check_llm; then echo "ok LLM отвечает"; else fail "LLM" "не ответил на короткий запрос ($OUT); проверьте llama-server и LLM_API_KEY"; fi
else
  echo "skip LLM: LLM_ENABLED не true"
fi
if [ -n "$BOT_TOKEN" ]; then
  if retry check_bot; then echo "ok bot запущен"; else fail "bot" "$OUT"; fi
else
  echo "skip bot: TG_BOT_TOKEN не задан"
fi
exit "$FAILED"
