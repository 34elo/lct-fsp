# Прогон после E41 (E41-18)

Ветка `block2`, 2026-10-10. Локальный стек `up-lite` пересобран с E41-17 (gateway :28080), сид `all/grades/families/demo2/fsp-registry`. Playwright, Chrome.

## Итог

Пунктов E41-1…E41-17: **17 закрыто**, закрыто с решением **0**, не закрыто **0**. Замечания P3 — внизу.

## Проверки

| Что | Результат |
|---|---|
| `uv run ruff check .` | чисто |
| `pnpm lint`, `pnpm typecheck` | чисто |
| `pnpm test` (vitest) | 493 из 496; падали `offers.test.tsx` (известный нестабильный) и ещё два теста при первом прогоне под нагрузкой сборки Docker (`settings.test.tsx` при повторе — 18 из 18) |
| pytest core по E41 (suggest, explain, trust, mermaid, offers, company_roles, companies, constructor, profile_data, taxonomy_suggest, search) | 200 passed |
| e2e desktop: register-flow, task-guide (с черновиком), employer-onboarding, employer-search (режим «Кандидаты» → навык → шорт-лист), landing-links, joint-demo | 14 из 14 |
| `b2-admin-audit` ×4, `joint-e39-check` (публичные, кандидат, работодатель, админ × 1440/375 × светлая/тёмная) | 16 + 4 + 4 из 24, ошибок консоли и 5xx нет |

Снимки: `reports/e41-check/shots` (админка, работодатель) и `reports/e39-check/shots` (публичные, кандидат), 1440 и 375, обе темы; в git не идут (каталог `reports/` в .gitignore). Не запускались: e2e с LLM, бот, `mobile-375` проект Playwright (ширина 375 покрыта joint-e39-check).

Повтор: `cd apps/web && E2E_CHANNEL=chrome pnpm exec playwright test e2e/joint-e39-check.spec.ts e2e/joint-demo.spec.ts e2e/b1-task-guide.spec.ts e2e/b2-employer-search.spec.ts --project=desktop`

## Сверка

| ID | Статус | Чем подтверждено |
|---|---|---|
| E41-1 | закрыто | радиусы из токенов `--radius-*`, произвольных `rounded-[` нет; Modal/Sheet с крестиком «Закрыть»; тест в primitives |
| E41-2 | закрыто | `AdminSidebar` sticky, группы и иконки (снимок реестра); «жёстк» в текстах не найдено |
| E41-3 | закрыто | тост «@elo_34», `ml` без фикстуры (test_fake), подсказки на Главной (home.test) |
| E41-4 | закрыто | e2e приглашение, offers.test, test_offers; ответа с текстом кандидата нет |
| E41-5 | закрыто | `scoring.yaml evidence.max_strength 0.75`, test_trust, test_assessment_explain |
| E41-6 | закрыто | profile-edit.test (kind=soft, профессии), test_assessment |
| E41-7 | закрыто | Caddyfile 302 на `dashboard.`, `VITE_APP_URL`, prod.env, landing.test; применение на VPS — человеку |
| E41-8 | закрыто | снимок Главной: EvidenceGraph с сеткой, graph.test |
| E41-9 | закрыто | `Diagram` в ui, `families-check` проверяет Mermaid, test_assessment_mermaid |
| E41-10 | закрыто | jobs.test, joint-demo |
| E41-11 | закрыто | e2e «Кандидаты → навык → шорт-лист», match.test |
| E41-12 | закрыто | company.test, test_candidates_profile_data (аватар не в анонимной карточке) |
| E41-13 | закрыто | test_candidate_pdf (кириллица, нет «почему такой грейд») |
| E41-14 | закрыто | e2e черновик → «Готово» → «Готовые», test_assessment_constructor |
| E41-15 | закрыто | один маршрут реестра, `/admin/quality` → redirect, analytics.test |
| E41-16 | закрыто | test_company_roles, password-setup.test, company.test; реализовано в коммите `7567d9c` |
| E41-17 | закрыто | test_profession_suggest, seed (`profession_suggestion: 1`), admin-taxonomy.test, снимок `admin_demo_new-profession` |

## Что проверить человеку

- Закреплённость фильтров `/jobs` и шторка на 375 (E41-10), радиусы и «i» везде (E41-1) — глазами на снимках.
- E41-16: письмо не уходит; карточка доступа показывает `WEB_BASE_URL` — на стенде проверить, что адрес не localhost.
- E41-7: применить `infra/vps/fsp.caddy` и `prod.env` на VPS.

## Замечания P3

- Реальная проверка E41-5 «один тест + ФСП = ●●●●» только юнитом; на сиде не смотрели.
- Фиксов кода в рамках E41-18 не потребовалось.
