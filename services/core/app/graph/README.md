# Граф доказательств — `app/graph`

Доказательства «факт → навык», доверие к навыкам, пересчёт профиля, факты ФСП, командные сигналы, эмбеддинг профиля. Пишет `evidence.changed` и `skills.profile.updated`.

| Файл | Что |
|---|---|
| `service.py` | `upsert_evidence` (идемпотентно), выборки для подбора |
| `trust.py` | затухание, noisy-OR, уровни, наследование |
| `recompute.py` | пересчёт `candidate_skills`, роли, сигнального грейда, эмбеддинга |
| `fsp_ingest.py` | события `fsp.*` → факты → доказательства |
| `fsp_strength.py` | сила доказательства ФСП и слагаемое F |
| `team_signals.py` | сигналы L/T/R/G и `K_soft` |
| `category.py` | роль и стек профиля по покрытию профессий |
| `grade.py` | сигнальный грейд анкеты |
| `subgraph.py` | подграф для UI |
| `embedding.py` | текст профиля и вызов ml-api |
| `handlers.py` | очереди `core.recompute`, `core.ingest` |

Подробнее: [skills.md](../../../../docs/mechanics/skills.md), [fsp.md](../../../../docs/mechanics/fsp.md).
