# Идентичность — `app/identity`

Пользователи, регистрация, вход, токены, подтверждение email, личный профиль сотрудника.

- Вход: email + пароль (Argon2), Telegram Login Widget, одноразовая magic-ссылка из бота.
- Access JWT на 15 минут, refresh-токен в cookie `rt` с ротацией по семьям.
- Подтверждение email кодом; обязательность — `EMAIL_VERIFICATION_REQUIRED`.
- Зависимости FastAPI: `get_current_user`, `require_roles(...)`.

| Файл | Что |
|---|---|
| `router.py` | `/auth/*`, `/me` |
| `service.py` | регистрация, вход, refresh-семьи, коды email |
| `deps.py` | текущий пользователь и проверка роли |
| `profile.py` | `/me/profile`: имя, должность, аватар сотрудника |
| `mailer.py` | отправка писем по SMTP |

Подробнее: [security.md](../../../../docs/architecture/security.md).
