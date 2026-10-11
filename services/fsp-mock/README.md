# fsp-mock

Имитация API ФСП для разработки и демо. Данные в памяти, люди и соревнования вымышленные; полный набор (≈ 600 участников) пишет `make seed` в `reports/seed/fsp-mock.json`, каталог смонтирован в контейнер.

| Группа | Пути |
|---|---|
| Данные | `GET /api/v1/participants[/{id}[/results]]`, `/competitions[/{id}/standings]`, `/teams/{id}` (ключ `FSP_MOCK_API_KEY`) |
| Верификация | `POST /api/v1/verification/send|check` — код 6 цифр, 5 попыток, 10 минут |
| OAuth / OIDC | `/oauth/authorize` (страница входа), `/oauth/token` (PKCE S256), `/oauth/userinfo`, `/oauth/jwks`, `/.well-known/openid-configuration` |
| Демо | `POST /mock/results` (новый результат + подписанный вебхук), `GET /mock/codes`, `POST /mock/reset` |

Ключевые файлы: `fsp_mock/main.py` (приложение), `data.py` (хранилище и стартовые данные), `config.py`.

```bash
uv run --package fsp-fsp-mock uvicorn fsp_mock.main:app --reload --port 8200
uv run pytest services/fsp-mock -q
```

Ответы валидируются теми же DTO `fsp_contracts.fsp`, что использует `fsp-connector`. Описание интеграции — [fsp.md](../../docs/mechanics/fsp.md).
