#!/bin/sh
# Создаёт .env.demo со случайными тестовыми секретами, если файла ещё нет. Существующий не трогает.
# Использование: infra/scripts/gen-demo-env.sh [путь]   (по умолчанию <корень>/.env.demo)
set -eu
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
OUT="${1:-$ROOT/.env.demo}"
if [ -e "$OUT" ]; then
  echo "gen-demo-env: $OUT уже есть, не перезаписываю"
  exit 0
fi
# hex без спецсимволов: безопасно для URL, YAML и shell
rnd() { openssl rand -hex "${1:-16}"; }
fernet() { openssl rand -base64 32 | tr '+/' '-_' | tr -d '\n'; }
umask 077
cat > "$OUT" <<ENV
# Сгенерировано infra/scripts/gen-demo-env.sh: тестовые секреты для локального запуска. Не коммитить.
ENV=dev
COMPOSE_PROJECT_NAME=fsp
DOMAIN=fsp.patissons.tech
GATEWAY_PORT=28080
WEB_BASE_URL=http://localhost:28080
ALLOWED_ORIGINS=["http://localhost:28080","http://127.0.0.1:28080"]
AUTH_COOKIE_PATH=/api/v1/auth
S3_PUBLIC_URL=http://s3.fsp.patissons.tech
DEMO_MODE=true

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

S3_ACCESS_KEY=fsp
S3_SECRET_KEY=$(rnd)
S3_BUCKET=fsp

JWT_SECRET=$(rnd 32)
PII_KEY=$(fernet)
PSEUDO_ID_SECRET=$(rnd 32)
ANALYTICS_SALT=$(rnd 16)
SERVICE_TOKEN_BOT=$(rnd 24)
SERVICE_TOKEN_ML=$(rnd 24)
SERVICE_TOKEN_CORE=$(rnd 24)
SERVICE_TOKEN_MOCK=$(rnd 24)

FSP_ADAPTER=mock
FSP_API_KEY=$(rnd 24)
FSP_WEBHOOK_SECRET=$(rnd 24)
FSP_OAUTH_CLIENT_ID=platform
FSP_OAUTH_CLIENT_SECRET=$(rnd 24)
FSP_PUBLIC_URL=http://localhost:28080
FSP_OAUTH_REDIRECT_URI=http://localhost:28080/api/v1/auth/fsp/callback

# Telegram: пусто — профиль bot не включается
TG_BOT_TOKEN=
TG_BOT_USERNAME=

ML_FAKE=true
LLM_BASE_URL=http://host.docker.internal:18090/v1
LLM_API_KEY=
LLM_MODEL=qwen3-vl-4b
ENV
echo "gen-demo-env: создан $OUT"
