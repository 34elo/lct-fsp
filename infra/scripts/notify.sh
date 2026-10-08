#!/bin/sh
# Сообщение команде от бота алертов hostwatch (@patissons_alerts_bot) всем его подписчикам.
# Токен — из HOSTWATCH_DIR/config.toml, чаты — из HOSTWATCH_DIR/state.json; Bot API — через TG_API_BASE
# (ретранслятор на VPS: с сервера Telegram недоступен напрямую). Настройки — из .env текущего каталога.
# Без hostwatch молча ничего не делает; ошибка отправки не роняет вызывающий скрипт.
#   sh infra/scripts/notify.sh "текст"
TEXT="${1:?нужен текст}"
get() { sed -n "s/^$1=//p" .env 2>/dev/null | tail -1; }
HOSTWATCH_DIR="${HOSTWATCH_DIR:-$(get HOSTWATCH_DIR)}"
TG_API_BASE="${TG_API_BASE:-$(get TG_API_BASE)}"
[ -n "$HOSTWATCH_DIR" ] && [ -f "$HOSTWATCH_DIR/config.toml" ] || exit 0
HOSTWATCH_DIR="$HOSTWATCH_DIR" TG_API_BASE="${TG_API_BASE:-https://api.telegram.org}" TEXT="[ФСП Карьера] $TEXT" python3 - <<'PY' || echo "notify: не отправилось" >&2
import json, os, tomllib, urllib.parse, urllib.request
d = os.environ["HOSTWATCH_DIR"]
token = tomllib.load(open(f"{d}/config.toml", "rb"))["telegram"]["token"]
chats = json.load(open(f"{d}/state.json")).get("chats", {})
base = os.environ["TG_API_BASE"].rstrip("/")
for chat in chats:
    body = urllib.parse.urlencode({"chat_id": chat, "text": os.environ["TEXT"], "disable_web_page_preview": "true"}).encode()
    try:
        urllib.request.urlopen(f"{base}/bot{token}/sendMessage", body, timeout=10)
    except Exception as e:  # один недоступный чат не мешает остальным
        print(f"notify: чат не принял сообщение ({type(e).__name__})")
PY
exit 0
