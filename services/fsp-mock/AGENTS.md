# AGENTS.md — fsp-mock

Назначение: имитация API ФСП для разработки и демо (docs/architecture/fsp.md §3). Данные в памяти, вымышленные; полный seed (~600 участников) — E5-2.

## Команды
- `uv run --package fsp-fsp-mock uvicorn fsp_mock.main:app --reload` — запуск
- `uv run pytest services/fsp-mock -q` — тесты
- `uv run ruff check services/fsp-mock` — линтер
- `/docs` — OpenAPI мока (описание всех групп методов)

## Ключевые файлы
- `fsp_mock/main.py` — `build_app()`: API v1, верификация, OAuth+PKCE со страницей, `/mock/*`, вебхук
- `fsp_mock/data.py` — `Store` и стартовые данные (герои `p-anya`, `p-dima`, 15 соревнований)
- `fsp_mock/config.py` — `FSP_MOCK_API_KEY`, `FSP_WEBHOOK_URL`, `FSP_WEBHOOK_SECRET`, TTL и попытки кода

## Правила
- Пакет `fsp_mock` (не `app`). Ответы валидируются DTO из `fsp_contracts.fsp`.
- Код верификации: 6 цифр, 5 попыток, TTL 10 мин, одноразовый. OAuth-код одноразовый, PKCE только S256.
- Вебхук ставит подпись `X-Signature`, сбой доставки не роняет `/mock/results`.
- Документы: docs/architecture/fsp.md §3–4.

## Docker
Образ: `infra/docker/python.Dockerfile` (`PACKAGE=fsp-fsp-mock`, `SERVICE_DIR=services/fsp-mock`), в compose — сервис `fsp-mock` (:8200), gateway отдаёт его на `mock.fsp.patissons.tech` и `/oauth/*`; профиль `core`. Запуск стека: `make up`.
