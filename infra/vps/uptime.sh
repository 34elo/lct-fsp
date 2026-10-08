#!/bin/sh
# Внешняя проверка стенда с VPS (cron раз в 5 минут): ловит то, чего не видит healthcheck на самом сервере —
# выключенный домашний ПК, упавший Tailscale, просроченный сертификат. Алерт только при смене состояния.
# Настройки — /etc/fsp-uptime.env (ALERT_BOT_TOKEN, ALERT_CHAT_ID, необязательно ALERT_THREAD_ID), права 600.
#   */5 * * * * /usr/local/bin/fsp-uptime.sh
set -u
. /etc/fsp-uptime.env
STATE=/var/tmp/fsp-uptime.state
fail=""
for u in https://dashboard.fsp.patissons.tech/ https://dashboard.fsp.patissons.tech/api/v1/healthz; do
  curl -fsS -m 15 -o /dev/null "$u" || fail="$fail $u"
done
send() {
  curl -fsS -m 10 -o /dev/null "https://api.telegram.org/bot${ALERT_BOT_TOKEN}/sendMessage" \
    --data-urlencode "chat_id=${ALERT_CHAT_ID}" ${ALERT_THREAD_ID:+--data-urlencode "message_thread_id=${ALERT_THREAD_ID}"} \
    --data-urlencode "text=[ФСП Карьера · VPS] $1" || true
}
prev=$(cat "$STATE" 2>/dev/null || echo ok)
if [ -n "$fail" ]; then
  echo fail > "$STATE"; [ "$prev" = fail ] || send "🔴 Стенд недоступен снаружи:$fail"
else
  echo ok > "$STATE"; [ "$prev" = ok ] || send "🟢 Стенд снова доступен снаружи"
fi
