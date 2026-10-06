# tools/seed

Демо-витрина (evaluation.md §4): детерминированный по `SEED` план → данные fsp-mock + наполнение core.

## Команды
- `make seed [SEED=n]` — всё в живой стек (`make up` уже выполнен): JSON мока, БД core, перезапуск fsp-mock.
- `make seed-plan` — только сводка плана; `make seed-fsp-mock` — только JSON мока.
- `make demo-snapshot` — дамп БД core и fsp_connector (pg_dump -Fc) + `fsp-mock.json` в `infra/snapshots/` (в git не идёт, `.gitignore`); `make demo-reset` — стоп сервисов, восстановление, `FLUSHALL` Redis, перезапуск (~50 с); `make demo-warm` — логины и первый поиск/профиль. Скрипт — `infra/scripts/demo.sh`. Снапшот делать на чистой витрине сразу после `make seed`.
- `uv run pytest -q tools/tests/test_seed.py`.

## Файлы
- `config.yaml` — объёмы, тестовый пароль демо-аккаунтов, вымышленные компании.
- `heroes/*.yaml` — Аня, Дима, Ольга (ручные фикстуры).
- `plan.py` — чистый план (без БД); `loader.py` — запись через сервисы core; `__main__.py` — CLI.
- `grades.py` — seed-грейды блока 1 (`make seed` вызывает `python -m tools.seed grades`): 6 профессий × 3 грейда через `assessment.seed_grade`, идемпотентно.
- `jury.py` — аккаунты жюри (E32-4b): `jury-candidate@` (без грейда) и `jury-hr@demo.fsp.test` (проверенная компания «Жюри Демо»); создаются в конце `make seed`, идемпотентно. Лендинг показывает кнопки входа при сборке с `VITE_JURY_MODE=true` (`apps/web/src/features/landing/JuryEntry.tsx`): кандидат попадает на `/me/assessment?mode=express`, работодатель — на `/employer/search`.
- `demo_v2.yaml` + `demo_v2.py` — демо v2 (E34-1): герои Борис/Вика/Глеб/Мира/Тимур с историей теста (через `grading.on_finished`), 3 компании и вакансии, офферы и отклики, регулярные задания; команда `python -m tools.seed demo2` (в `make seed`).
- `make demo-reset` возвращает снапшот (`make demo-snapshot` сразу после `make seed`); `make demo-warm` прогревает кеши.

## Правила
- Только вымышленные люди и компании; пароли тестовые.
- Идемпотентность: по email, `Idempotency-Key` офферов, пометке бэкфилла аналитики.
- Доверие/грейд считает `recompute_profile`, а не seed.
