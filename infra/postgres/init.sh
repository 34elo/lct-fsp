#!/bin/sh
# Выполняется один раз при создании тома: роли и базы сервисов.
set -eu
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname postgres <<SQL
CREATE ROLE core LOGIN PASSWORD '${CORE_DB_PASSWORD}';
CREATE ROLE fspc LOGIN PASSWORD '${FSPC_DB_PASSWORD}';
CREATE DATABASE core OWNER core;
CREATE DATABASE fsp_connector OWNER fspc;
SQL
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname core -c 'CREATE EXTENSION IF NOT EXISTS vector; CREATE EXTENSION IF NOT EXISTS pg_trgm;'
