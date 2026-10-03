# tools/seed

Демо-витрина (evaluation.md §4): детерминированный по `SEED` план → данные fsp-mock + наполнение core.

## Команды
- `make seed [SEED=n]` — всё в живой стек (`make up` уже выполнен): JSON мока, БД core, перезапуск fsp-mock.
- `make seed-plan` — только сводка плана; `make seed-fsp-mock` — только JSON мока.
- `uv run pytest -q tools/tests/test_seed.py`.

## Файлы
- `config.yaml` — объёмы, тестовый пароль демо-аккаунтов, вымышленные компании.
- `heroes/*.yaml` — Аня, Дима, Ольга (ручные фикстуры).
- `plan.py` — чистый план (без БД); `loader.py` — запись через сервисы core; `__main__.py` — CLI.

## Правила
- Только вымышленные люди и компании; пароли тестовые.
- Идемпотентность: по email, `Idempotency-Key` офферов, пометке бэкфилла аналитики.
- Доверие/грейд считает `recompute_profile`, а не seed.
