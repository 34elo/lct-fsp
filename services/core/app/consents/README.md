# Согласия — `app/consents`

История согласий пользователя по типам (`ConsentType`). `pd_processing` обязателен; `profile_publication` открывает кандидата работодателям.

| Файл | Что |
|---|---|
| `router.py` | `GET/PUT /me/consents` |
| `service.py` | выдача, отзыв, проверка, версия для кеша выдачи |
| `deps.py` | `require_consent(type)` → 403 `consent_required` |

Подробнее: [security.md](../../../../docs/architecture/security.md#персональные-данные-152-фз).
