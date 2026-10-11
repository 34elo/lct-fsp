# infra

Инфраструктура запуска. Описание — [infrastructure.md](../docs/operations/infrastructure.md).

| Путь | Что |
|---|---|
| `docker/python.Dockerfile` | Общий образ Python-сервисов (`PACKAGE`, `SERVICE_DIR`): uv, системные библиотеки WeasyPrint, кеш моделей эмбеддингов |
| `docker/pdf_smoke.py` | Смоук-проверка генерации PDF внутри образа (CI) |
| `caddy/Caddyfile` | Gateway: роутинг по Host и пути, `/internal/*` закрыт, SSE без буферизации |
| `postgres/init.sh` | Базы `core` и `fsp_connector`, роли сервисов, расширения `vector` и `pg_trgm` |
| `rabbitmq/init.sh` | vhost `fsp`, пользователи сервисов с правами |
| `redis.conf` | Redis как кеш: 1 ГБ, `allkeys-lru`, без сохранения на диск |
| `env/prod.env` | Несекретные настройки продового стенда |
| `test/docker-compose.yml` | Временные PostgreSQL и RabbitMQ для интеграционных тестов |
| `scripts/gen-demo-env.sh` | `.env.demo` со случайными секретами, если нет `.env` |
| `scripts/demo.sh` | Снапшот, сброс и прогрев демо-данных |
| `scripts/deploy.sh`, `install-prod.sh`, `install-runner.sh`, `render-env.sh`, `gen-server-secrets.sh` | Развёртывание на сервер и раннер CD |
| `scripts/backup.sh`, `restore.sh` | Резервные копии БД и MinIO |
| `scripts/notify.sh`, `smoke-ml.sh` | Уведомления деплоя, смоук ml-api |
| `vps/` | Внешний Caddy на VPS: TLS и проксирование на стенд ([vps/README.md](vps/README.md)) |
