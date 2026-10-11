# Резюме — `app/resumes`

Загрузка PDF/DOCX → MinIO → команда `ml.resume.parse` → результат событием `ml.resume.completed|failed` → кандидат проверяет и подтверждает → доказательства `resume` (0.25–0.40) и `self` (0.15), опыт и образование.

| Файл | Что |
|---|---|
| `router.py` | `/candidates/me/resumes/*` |
| `service.py` | загрузка, сигнатура файла, подтверждение → доказательства |
| `handlers.py` | приём результата разбора, SSE |

Подробнее: [ml.md](../../../../docs/mechanics/ml.md#разбор-резюме).
