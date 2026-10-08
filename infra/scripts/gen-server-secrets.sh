#!/bin/sh
# Внутренние секреты продового стенда (пароли БД, RabbitMQ, MinIO, JWT, ключи шифрования, сервисные токены).
# Создаются на сервере один раз в <каталог стенда>/.env.server (права 600) и никуда не уходят.
# Существующий файл не трогает: новые пароли не подойдут к уже созданным томам БД.
#   sh infra/scripts/gen-server-secrets.sh [каталог стенда]
set -eu
DIR="${1:-$(pwd)}"
OUT="$DIR/.env.server"
if [ -e "$OUT" ]; then
  echo "gen-server-secrets: $OUT уже есть, не перезаписываю"
  exit 0
fi
rnd() { openssl rand -hex "${1:-24}"; }
fernet() { openssl rand -base64 32 | tr '+/' '-_' | tr -d '\n'; }
umask 077
cat > "$OUT" <<ENV
# Внутренние секреты стенда, сгенерированы $(date -u +%Y-%m-%dT%H:%M:%SZ). Не коммитить, не копировать.
POSTGRES_USER=postgres
POSTGRES_PASSWORD=$(rnd)
CORE_DB_PASSWORD=$(rnd)
FSPC_DB_PASSWORD=$(rnd)
RABBITMQ_ADMIN_USER=admin
RABBITMQ_ADMIN_PASSWORD=$(rnd)
RABBITMQ_CORE_PASSWORD=$(rnd)
RABBITMQ_ML_PASSWORD=$(rnd)
RABBITMQ_FSPC_PASSWORD=$(rnd)
RABBITMQ_BOT_PASSWORD=$(rnd)
S3_SECRET_KEY=$(rnd)
JWT_SECRET=$(rnd 32)
PII_KEY=$(fernet)
PSEUDO_ID_SECRET=$(rnd 32)
ANALYTICS_SALT=$(rnd 16)
SERVICE_TOKEN_BOT=$(rnd)
SERVICE_TOKEN_ML=$(rnd)
SERVICE_TOKEN_CORE=$(rnd)
SERVICE_TOKEN_MOCK=$(rnd)
FSP_API_KEY=$(rnd)
FSP_WEBHOOK_SECRET=$(rnd)
FSP_OAUTH_CLIENT_SECRET=$(rnd)
ENV
echo "gen-server-secrets: создан $OUT"
