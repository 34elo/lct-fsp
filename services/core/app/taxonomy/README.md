# Справочник навыков и профессий — `app/taxonomy`

Навыки, синонимы, связи, профессии с весами навыков, дисциплины ФСП; загрузка из `data/taxonomy`, версия и снимок для ml; очередь новых навыков, слияния, пары «точно разные», стоп-лист; рост связей и предложения новых профессий.

| Файл | Что |
|---|---|
| `loader.py` | YAML → проверка |
| `service.py` | синхронизация в БД, версия, снимок, профессии (`list_professions`) |
| `router.py` | `/taxonomy/*`, `/internal/taxonomy/snapshot` |
| `admin.py` | профессии и карточки для админа |
| `admin_router.py` | `/admin/professions*`, `/admin/skill-cards*` |
| `skills_admin.py` | очередь навыков, слияния |
| `skills_router.py` | `/admin/skills/*` |
| `decisions.py` | применение решений конвейера навыков |
| `growth.py` | NPMI, lift, продвижение `provisional → active` |
| `profession_suggest.py` | кластеры навыков → предложения профессий |
| `suggest.py` | подсказки ввода навыков и профессий |
| `cards.py` | схема карточек навыков |

Подробнее: [skills.md](../../../../docs/mechanics/skills.md).
