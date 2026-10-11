# Компании — `app/companies`

Регистрация компании, профиль и логотип, команда (владелец и HR), приглашения в команду по ссылке, доступ HR с временным паролем, журнал доступа, модерация администратором (`pending → verified | rejected | blocked`).

| Файл | Что |
|---|---|
| `router.py` | `/companies/*`, `/company-invites/*`, `/admin/companies/*` |
| `service.py` | компания, участники, приглашения, модерация |

Подробнее: [features.md](../../../../docs/product/features.md#работодатель).
