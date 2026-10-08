#!/bin/sh
# Разовая (идемпотентная) настройка: vhost fsp и пользователь на сервис через management API.
set -eu
API="http://rabbitmq:15672/api"
AUTH="$RABBITMQ_ADMIN_USER:$RABBITMQ_ADMIN_PASSWORD"
put() { curl -fsS -u "$AUTH" -H 'content-type: application/json' -X PUT "$API/$1" -d "$2" >/dev/null; }

# ждём management API
until curl -fsS -u "$AUTH" "$API/overview" >/dev/null 2>&1; do sleep 2; done

put "vhosts/fsp" '{}'
for pair in core:"$RABBITMQ_CORE_PASSWORD" ml:"$RABBITMQ_ML_PASSWORD" fspc:"$RABBITMQ_FSPC_PASSWORD" bot:"$RABBITMQ_BOT_PASSWORD"; do
  user="${pair%%:*}"; pass="${pair#*:}"
  put "users/$user" "{\"password\":\"$pass\",\"tags\":\"\"}"
  put "permissions/fsp/$user" '{"configure":".*","write":".*","read":".*"}'
done
put "permissions/fsp/$RABBITMQ_ADMIN_USER" '{"configure":".*","write":".*","read":".*"}'
echo "rabbitmq: vhost fsp и пользователи готовы"
