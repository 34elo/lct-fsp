#!/bin/sh
# Собирает .env продового стенда: infra/env/prod.env + .env.server + внешние токены из окружения
# (их передаёт cd.yml из окружения GitHub `prod`). Значения секретов не печатает.
#   sh infra/scripts/render-env.sh   (из каталога стенда)
set -eu
[ -s .env.server ] || { echo "render-env: нет .env.server — sh infra/scripts/gen-server-secrets.sh" >&2; exit 1; }
missing=""
for k in TG_BOT_TOKEN TG_BOT_USERNAME LLM_API_KEY; do
  eval "v=\${$k:-}"; [ -n "$v" ] || missing="$missing $k"
done
[ -z "$missing" ] || { echo "render-env: не заданы в окружении GitHub prod:$missing" >&2; exit 1; }
umask 077
tmp=.env.tmp
{
  echo "# Собрано infra/scripts/render-env.sh $(date -u +%Y-%m-%dT%H:%M:%SZ). Не править руками: правки — в infra/env/prod.env, .env.server или секретах GitHub."
  cat infra/env/prod.env
  echo
  cat .env.server
  echo
  echo "# --- внешние токены (окружение GitHub prod) ---"
  for k in TG_BOT_TOKEN TG_BOT_USERNAME LLM_API_KEY GITHUB_TOKEN ALERT_BOT_TOKEN ALERT_CHAT_ID ALERT_THREAD_ID; do
    eval "v=\${$k:-}"
    printf '%s=%s\n' "$k" "$v"
  done
} > "$tmp"
mv "$tmp" .env
echo "render-env: .env собран"
