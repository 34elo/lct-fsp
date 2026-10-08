#!/bin/sh
# Собирает .env продового стенда: infra/env/prod.env + .env.server + ключ LLM из файла ключей сервера +
# токен бота платформы из окружения (его передаёт cd.yml из окружения GitHub `prod`). Значения не печатает.
#   sh infra/scripts/render-env.sh   (из каталога стенда)
set -eu
[ -s .env.server ] || { echo "render-env: нет .env.server — sh infra/scripts/gen-server-secrets.sh" >&2; exit 1; }
cfg() { sed -n "s/^$1=//p" infra/env/prod.env | tail -1; }

missing=""
for k in TG_BOT_TOKEN TG_BOT_USERNAME; do
  eval "v=\${$k:-}"; [ -n "$v" ] || missing="$missing $k"
done
[ -z "$missing" ] || { echo "render-env: не заданы в окружении GitHub prod:$missing" >&2; exit 1; }

KEY_FILE=$(cfg LLM_API_KEY_FILE); KEY_LINE=$(cfg LLM_API_KEY_LINE)
LLM_API_KEY=$(sed -n "${KEY_LINE:-1}p" "$KEY_FILE" 2>/dev/null | tr -d '\r\n' || true)
[ -n "$LLM_API_KEY" ] || { echo "render-env: нет ключа LLM в строке ${KEY_LINE:-1} файла $KEY_FILE" >&2; exit 1; }

umask 077
tmp=.env.tmp
{
  echo "# Собрано infra/scripts/render-env.sh $(date -u +%Y-%m-%dT%H:%M:%SZ). Не править руками: правки — в infra/env/prod.env, .env.server или секретах GitHub."
  cat infra/env/prod.env
  echo
  cat .env.server
  echo
  echo "# --- внешние ключи ---"
  printf 'TG_BOT_TOKEN=%s\nTG_BOT_USERNAME=%s\nLLM_API_KEY=%s\n' "$TG_BOT_TOKEN" "$TG_BOT_USERNAME" "$LLM_API_KEY"
} > "$tmp"
mv "$tmp" .env
echo "render-env: .env собран"
