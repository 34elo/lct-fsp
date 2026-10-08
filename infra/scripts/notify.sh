#!/bin/sh
# Сообщение в чат алертов команды через Telegram Bot API. Токен и чат — ALERT_BOT_TOKEN, ALERT_CHAT_ID
# (и необязательный ALERT_THREAD_ID — тема в группе) из окружения или из .env текущего каталога.
# Без них молча ничего не делает. Ошибка отправки не роняет вызывающий скрипт.
#   sh infra/scripts/notify.sh "текст"
TEXT="${1:?нужен текст}"
if [ -z "${ALERT_BOT_TOKEN:-}" ] && [ -f .env ]; then
  ALERT_BOT_TOKEN=$(sed -n 's/^ALERT_BOT_TOKEN=//p' .env)
  ALERT_CHAT_ID=$(sed -n 's/^ALERT_CHAT_ID=//p' .env)
  ALERT_THREAD_ID=$(sed -n 's/^ALERT_THREAD_ID=//p' .env)
fi
[ -n "${ALERT_BOT_TOKEN:-}" ] && [ -n "${ALERT_CHAT_ID:-}" ] || exit 0
curl -fsS -m 10 -o /dev/null "https://api.telegram.org/bot${ALERT_BOT_TOKEN}/sendMessage" \
  --data-urlencode "chat_id=${ALERT_CHAT_ID}" \
  ${ALERT_THREAD_ID:+--data-urlencode "message_thread_id=${ALERT_THREAD_ID}"} \
  --data-urlencode "text=[ФСП Карьера] ${TEXT}" \
  --data-urlencode "disable_web_page_preview=true" || echo "notify: не отправилось" >&2
exit 0
