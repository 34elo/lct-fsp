# tools/seed

Демо-витрина (evaluation.md §4): детерминированный по `SEED` план → данные fsp-mock + наполнение core.

## Команды
- `make seed [SEED=n]` — всё в живой стек (`make up` уже выполнен): JSON мока, БД core, перезапуск fsp-mock.
- `make seed-plan` — только сводка плана; `make seed-fsp-mock` — только JSON мока.
- `make demo-snapshot` — снапшот только демо-строк (`is_demo`, E40-1) в таблицы `demo_snap__*` БД core и fsp_connector (`python -m app.demo`, `python -m fsp_connector.demo`) + `fsp-mock.json` в `infra/snapshots/`; `make demo-reset` — сброс только демо к снапшоту без остановки стека, реальные регистрации не трогаются; `make demo-warm` — логины и первый поиск/профиль. Скрипт — `infra/scripts/demo.sh`. Снапшот делать на чистой витрине сразу после `make seed`. Демо-пометка ставится сама: аккаунты `*@demo.fsp.test`, их компании, вакансии и приглашения.
- `uv run pytest -q tools/tests/test_seed.py`.

## Файлы
- `config.yaml` — объёмы, тестовый пароль демо-аккаунтов, вымышленные компании.
- `heroes/*.yaml` — Аня, Дима, Ольга (ручные фикстуры).
- `plan.py` — чистый план (без БД); `loader.py` — запись через сервисы core; `__main__.py` — CLI.
- `families.py` — демо-очередь допуска заданий (E39-31): 7 профессий × 3 грейда = 21 семейство-спецификация (pilot, draft, quarantine; часть не проходит пороги), команда `python -m tools.seed families` (в `make seed`), идемпотентно; там же `professions.py` — демо-предложение новой профессии «Разработчик 1С» (E41-17).
- `grades.py` — seed-грейды блока 1 (`make seed` вызывает `python -m tools.seed grades`): 6 профессий × 3 грейда через `assessment.seed_grade`, идемпотентно.
- `jury.py` — аккаунты жюри (E32-4b): `jury-candidate@` (без грейда) и `jury-hr@demo.fsp.test` (проверенная компания «Жюри Демо»); создаются в конце `make seed`, идемпотентно. Кнопки лендинга (`VITE_JURY_MODE=true`, `JuryEntry.tsx`) с E40-1 входят не в них, а в свою песочницу (`POST /auth/jury`, `services/core/app/demo/service.py`): кандидат попадает на `/me/assessment?mode=express`, работодатель — на `/employer/search`.
- `demo_v2.yaml` + `demo_v2.py` — демо v2 (E34-1): герои Борис/Вика/Глеб/Мира/Тимур с историей теста (через `grading.on_finished`), 3 компании и вакансии, офферы и отклики, регулярные задания; команда `python -m tools.seed demo2` (в `make seed`).
- `fsp_registry.yaml` + `fsp_registry.py` — демо-реестр ФСП (E39-28): герои (ID источника, email аккаунта) и `jury-candidate@` (`r-jury` с результатами) в БД fsp-connector; команда `python -m tools.seed fsp-registry` (`FSP_CONNECTOR_DATABASE_URL` или `--env-file`, шаг `make seed`); привязок не создаёт.
- `make demo-reset` возвращает снапшот (`make demo-snapshot` сразу после `make seed`); `make demo-warm` прогревает кеши.

## Правила
- Только вымышленные люди и компании; пароли тестовые.
- Идемпотентность: по email, `Idempotency-Key` офферов, пометке бэкфилла аналитики.
- Доверие/грейд считает `recompute_profile`, а не seed.
- `demo_v2.py::shortlists` (E39-23): у `olga@`, `jury-hr@`, `hr02…hr05@` потребность «Демо: кандидаты на заметку» с 3–5 видимыми кандидатами в шорт-листе (идемпотентно; шаг `make seed` → `demo2`).
