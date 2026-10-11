# Анкета кандидата — `app/candidates`

Профиль кандидата: псевдоним и `pseudo_id`, предпочтения, видимость, стоп-лист, аватар, зашифрованные ФИО и контакты, PDF-резюме, спор категории, удаление аккаунта. Отдаёт подбору пул анкет с жёсткими фильтрами.

| Файл | Что |
|---|---|
| `router.py` | `/candidates/me/*` |
| `service.py` | анкета, видимость, пул поиска (`search_pool`), удаление |
| `pdf.py` | PDF-резюме (WeasyPrint) |
| `pii.py` | шифрование ПДн (Fernet) |
| `models.py` | `candidates`, `category_disputes`, умолчания видимости |

Подробнее: [features.md](../../../../docs/product/features.md#кандидат), [security.md](../../../../docs/architecture/security.md).
