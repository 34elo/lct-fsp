# Фронтенд (web)

> React 19 + Vite + TypeScript, один SPA с ленивыми разделами по ролям. Почему не Next.js — [stack.md §2](stack.md#2-фронт-react-spa-nextjs-или-два-проекта). Визуальная часть — [design/brief.md](../design/brief.md).

## 1. Карта маршрутов

Маршруты приняты из макетов (таблица экран → файл → маршрут — [design/brief.md §0](../design/brief.md#0-дизайн-получен-2026-10-02--с-чего-начинать-фронтенду)).

| Маршрут | Роль | Экран (макет) |
|---|---|---|
| `/` | все | Лендинг (L1, L2) |
| `/login`, `/register`, `/auth/magic` | — | Вход (возврат из ФСП — API `/api/v1/auth/fsp/callback`, своей страницы нет) |
| `/consents` | любая | Согласия после входа или регистрации, пока не выдан `pd_processing` (шаг 1 из M1) |
| `/onboarding` | C | Онбординг: согласия → резюме → ФСП → GitHub (M1) |
| `/me` | C | Мой профиль: категория, грейд, навыки с доверием, командные сигналы, «Быстрый рост» (D) |
| `/me/graph` | C | Граф доказательств (G1, G2) |
| `/me/skills/:slug` | C | Доказательства навыка |
| `/me/offers`, `/me/offers/:id` | C | Офферы и переписка (M2) |
| `/me/growth` | C | Переадресация на `/me/navigator` (своего экрана нет, E35-1) |
| `/me/navigator` | C | Навигатор роста (Б2, E12-3): `NavigatorPath`, uplift-карточки, соревнования ФСП; «Пройти тест» ведёт на `/me/assessment?profession=&grade=` |
| `/jobs`, `/jobs/:id` | — | Публичные вакансии (Б2, E20-7b, J1): фильтры профессия/город/текст, вилка на карточке; отклик с сообщением после входа (состояния: не вошёл, не кандидат, `email_not_verified`, отправлено, `already_applied`). Отдельного публичного `GET` вакансии нет: деталь берётся из `GET /vacancies/public?limit=100` |
| `/me/responses` | C | Мои отклики (R1): вкладки, отзыв из `sent/viewed`, переход к приглашению |
| `/me/interests` | C | «Вами интересуются» (E33-7, ADR-026): агрегат `GET /candidates/me/interests`, карточки без контактов с «почему вы» и рейтингом ответственности, «открыть» / «не интересно» с причиной; плашка со счётчиком на `/me/offers` |
| `/employer/needs/new` | E | Потребность текстом (N1): `POST /needs {text}`, 422 `need_empty` → ссылка на форму поиска |
| `/employer/needs/:id` | E | Рекомендованные категории (N1): `GET /needs/{id}/categories`, чипсы «поняли так» из ответа создания (router state), карточка профессия × грейд со счётчиками |
| `/employer/categories/:profession/:grade?need_id=` | E | Кандидаты категории (N2): `GET /categories/{p}/{g}/candidates`, «заявлено vs подтверждено» (`card.grade` против `categories`), шорт-лист `POST/DELETE /needs/{id}/shortlist/{pseudo_id}`, фильтры и сортировка на клиенте поверх загруженных карточек (отмеченные не пропадают), «Пригласить» → `/employer/offers/new?candidate=` |
| `/employer/responses` | E | Отклики на вакансии (R1): `GET /offers?initiator=candidate`, «Пригласить» → `interview`, «Отказать» → `not_hired`. Приглашение без вакансии — в окне оффера (название, описание, способ связи, вилка) |
| `/employer/subscriptions` | E | Подписки на категорию (E33-4): профессия, грейды, формат, бюджет, навыки с уровнем, «только подтверждённые»; список и удаление. Ссылка из «Кандидаты категории» |
| `/me/settings` | C | Переадресация на `/me` до экрана настроек (E36-4) |
| `/employer/search` | E | Поиск: текст → чипсы → карточки (A, E2) |
| `/employer/candidates/:id` | E | Карточка кандидата (B) |
| `/employer/offers/new` | E | Модалка оффера (C) |
| `/employer/vacancies`, `/employer/vacancies/new`, `/employer/vacancies/:id` | E | Вакансии и редактор вакансии (E3) |
| `/employer/vacancies/:id/shortlist` | E | Подборка по вакансии (E4) |
| `/employer/offers` | E | Мои офферы, канбан (E5) |
| `/employer/company` | EA | Компания, участники, статус модерации |
| `/federation`, `/federation/moderation` | A | Дашборд ФСП, модерация (F1, F3) |
| `/admin/skills` | A | Граф навыков: очередь, слияния, рост (G3) |
| `/admin/demo/two-worlds`, `/admin/demo/llm-exam`, `/admin/demo/new-profession` | A | Вау-экраны питча: два мира, LLM сдаёт тест, новая профессия (E34-3) |
| `/admin/quality`, `/admin/quality/fairness`, `/admin/quality/runs` | A | Качество, справедливость, живые прогоны (Q1–Q3) |
| `/run/:token` | испытатель | Живой прогон + SUS (Q3) |

**Меню (E35-1, `NAV` в `app/routes.ts`).** Кандидат: Главная (`/me`) · Тест и грейд (`/me/assessment`) · Приглашения (`/me/offers`; вкладки: интересы, отклики) · Профиль (`/me/profile/edit`; вкладки: резюме и ФСП, граф, задания); на ≤768 px те же 4 пункта внизу. Работодатель: Подбор (`/employer/search`; вкладка «Кого ищете») · Приглашения (`/employer/offers`; вкладка «Отклики») · Компания (вкладки: вакансии, задания, подписки); «Шорт-лист» — с общим экраном E35-4. Админ (≤ 6): Дашборд · Допуск заданий · Профессии · Граф навыков · Модерация · Качество. Меню аватара: тема, выход; настройки и согласия — с экраном E36-4. Пункт подсвечивается по самому длинному префиксу пути (`activeNav`), вкладки раздела — строка под шапкой (`SectionTabs`). Заглушек нет: маршрут без экрана удаляется или получает `redirect`; это проверяет `routes.test.ts`. Публичная карточка `/athlete/:id`, проверка бейджа `/verify/:id`, рынок E1, граф и интервью в карточке работодателя, матрица, демо-пульт и «Здоровье» убраны до появления экранов.

Бейдж `/badge/:id.svg` отдаёт бэкенд (P2). Кабинет кандидата — **mobile-first** (основной макет 390), работодатель и админка — desktop-first (1440/1024).

## 2. Структура проекта

pnpm-workspace в корне репозитория (`package.json`, `pnpm-workspace.yaml`, один `pnpm-lock.yaml`): `apps/web` и `packages/ui`. Команды из корня: `pnpm install`, `pnpm -r lint|typecheck|test|build`, `pnpm shot`. Решение — [ADR-050](decisions.md).

```
packages/ui/              # @fsp/ui — дизайн-система, без сборки (экспорт из src/index.ts)
├── src/
│   ├── styles/           # tokens.css (CSS-переменные), index.css (@theme для Tailwind 4) → "@fsp/ui/styles.css"
│   ├── primitives/       # базовые компоненты (Button…)
│   ├── brand/            # TrustDots, SkillChip, ConstellationAvatar, MatchRing, Logo
│   ├── v2/               # макеты v2 (E38-0): примитивы (Panel, H1/H2, Lbl, SkillTag/StatusTag/GradeTag, MeterBar),
│   │                     #   графики (MetricTile, SkillConstellation, ScatterPlot, ActivityHeatmap, GradeScale, TypeBar),
│   │                     #   карточки (CategoryCard, CandidateCardV2, FeedEvent, QueryBar, OfferCardV2),
│   │                     #   тест (TaskHeader, OptionRow, CodeLines, ErrorBlock), каркас (AppBar, TabBar, MobileBar, AccountMenu)
│   ├── lib/cn.ts
│   └── index.ts
├── playground/           # витрина: Токены / Базовые / Фирменные / v2 (доска v2_components), обе темы (порт 28174)
└── scripts/shot.mjs      # pnpm shot <маршрут> [--as candidate|employer|admin] [--playground]
                          #   → reports/shots/<имя>-<1440|1024|390>-<light|dark>.png
    scripts/design-shots.mjs  # make design-shots: PNG всех docs/design/v2/screens/*.html → docs/design/v2/png/

apps/web/
├── src/
│   ├── app/              # роутер, провайдеры (QueryClient, Auth, Theme, SSE), layout'ы по ролям
│   ├── api/              # сгенерировано orval: hooks + zod (не редактировать руками)
│   ├── shared/
│   │   ├── ui/, brand/   # временные реэкспорты из @fsp/ui (уберёт E19-15)
│   │   ├── charts/       # Heatmap, Radar, Funnel, RussiaMap (ECharts-обёртки)
│   │   ├── lib/          # format (деньги, даты, грейды), sse, auth
│   │   └── i18n/         # словари перечислений: роли, грейды, причины отказа
│   ├── features/         # бизнес-фичи: resume-upload, fsp-link, github-link, offer-create, nl-search, test-runner…
│   ├── pages/            # страницы по маршрутам
│   └── styles/           # tailwind.css: импорт @fsp/ui/styles.css, @source на packages/ui/src, анимации
├── vite.config.ts        # прокси /api → VITE_API_TARGET (по умолчанию http://localhost:28080)
└── e2e/                  # Playwright: демо-сценарий целиком
```

## 3. Данные и состояние

- **Серверное состояние** — только TanStack Query. Ключи из orval, `staleTime` 30 с для справочников и 0 для офферов.
- **Клиентское состояние** — минимально: auth (access-токен в памяти), тема, черновики форм. Zustand при необходимости.
- **Фильтры поиска** — в URL (`?q=&roles=backend&skills=python:3`), чтобы ссылкой можно было поделиться и вернуться назад.
- **Генерация клиента:** `pnpm api:gen` (`make api-gen`, нужен Node 22) берёт схему из `OPENAPI_URL` (например, `http://localhost:28080/api/v1/openapi.json`), без неё — снимок схемы core `apps/web/openapi.json` (без `/internal/*`; обновляется выгрузкой `app.openapi()`) → `src/api` (orval, fetch-мутатор `src/api/mutator.ts`: Bearer, один refresh на 401). В CI проверяем, что сгенерированный клиент совпадает со схемой.
- **Авторизация:** access в памяти, при 401 один раз `POST /auth/refresh` (cookie), затем повтор запроса. При старте приложения тихий refresh.
- **Вход (E1-4):** `/login`, `/register`, `/auth/magic?token=&redirect=` (одноразовый токен, `redirect` — только путь SPA) и `/consents` (отдельный чекбокс на каждое согласие, список и `current_version` из `GET /me/consents`). После любого входа, если в `GET /me` нет `pd_processing`, ведём на `/consents`; `RequireRole` делает то же для кабинетов. Telegram Login Widget пока не подключён.
- **Онбординг (E3-5):** `/onboarding` (кандидат) — шаги на схемной линии: согласия (уже выданы, иначе `RequireRole` ведёт на `/consents`) → резюме → ФСП → GitHub → готово, каждый шаг пропускается. Шаг «Резюме»: `POST /candidates/me/resumes`, `BuildLog` строится из SSE `job.progress` (`job_id` = `resume_id`; опрос `GET …/resumes/{id}` раз в 3 с как страховка), по `parsed` показывается «Вот что я понял» с правкой опыта, образования и навыков на месте, «Всё верно» → `POST …/confirm` (правки уходят только если что-то менялось). Шаг GitHub пока заглушка «подключим позже». Шаг ФСП (E5-7): `FspLinkPanel` — «Войти через ФСП» (`GET /auth/fsp/start` → `location.assign` на мок/ФСП, возврат с `?fsp=linked|error&reason=` на `/onboarding` или `/me`), запасной путь — ID/email → код (`/fsp/link`, `/fsp/verify`) или «привязать без кода»; после привязки «Обновить из ФСП» (`/fsp/sync`). Тот же блок — в карточке «Достижения ФСП» на `/me`; SSE `fsp.imported` инвалидирует профиль и обзор ФСП, выросшие навыки «загораются» волной (`.fsp-ignite`, только без `prefers-reduced-motion`). «Сила профиля» и радар ДНК кода не показываются. Автоматического перехода на `/onboarding` после регистрации пока нет.

## 4. Realtime (SSE)

- Хук `useEventStream()` в корневом провайдере: один `EventSource` на вкладку, переподключение с экспоненциальной паузой.
- Обработчики событий инвалидируют запросы (`profile.updated` → `['profile']`, `offer.updated` → `['offers', id]`) и показывают тосты.
- `job.progress` → компонент `BuildLog` (терминальный лог этапов, см. дизайн-бриф).
- `profile.updated.diff` → анимация «значки загораются» на экране профиля.

## 5. Тема и токены

**Из дизайна** (v1 — [design/pack/components](../design/pack/components/) и [pack/tokens](../design/pack/tokens/); v2 — [design/v2](../design/v2/README.md)):
- `globals.css` → `packages/ui/src/styles/tokens.css` (`@fsp/ui`): CSS-переменные, светлая в `:root`, тёмная в `.dark` (переключение классом на `<html>`, по умолчанию светлая, режим «как в системе» выбирает пользователь; `<ThemeScope dark>` включает тёмную тему для области; шкала текста `text-11…text-48`, метка `lbl`, тени `shadow-xs`/`shadow-card`). **v2:** имена из `docs/design/v2/fsp2.css` (`--deep`, `--mid`, `--t50…t200`, `--hair`, `--ok`, `--warn*`, `--err*`) — алиасы тех же токенов, плюс `--chip-fg`, `--code-*`, `--err-border`, `--shadow-menu`; `<ThemeScope light>` (класс `.light`) — светлая область внутри тёмной (`.dark .lt` макетов). Утилиты `num`, `skl`. Шапка `.hd`, нижняя панель `.tb` и меню аватара — `AppBar`/`TabBar`/`AccountMenu` из `@fsp/ui`, приложение передаёт `renderLink`.
- **Tailwind 4** (CSS-first): цвета из `tailwind.config.ts` переносятся в `@theme inline` и **ссылаются на переменные**, например `--color-brand: var(--brand)`, `--color-tint-50: var(--tint-50)`. Тогда классы `bg-brand`, `border-tint-200`, `text-brand-deep` из `fsp-ui.tsx` работают в обеих темах.
- `fsp-ui.tsx` → `packages/ui/src/brand/`. Захардкоженные цвета заменить токенами (см. [design/brief.md §0](../design/brief.md#0-дизайн-получен-2026-10-02--с-чего-начинать-фронтенду)).
- shadcn/ui: Dialog, Sheet, Drawer, Tabs, Tooltip, Popover, Select, Toast — макеты на них и рассчитаны.

Прежние правила ниже остаются в силе.


- CSS-переменные в `tokens.css` (светлая и тёмная темы), Tailwind берёт значения из них. Палитра и шрифты — [brand.md](../design/brand.md).
- Фирменные компоненты (`TrustDots`, `ConstellationAvatar`, `CircuitLine`) — SVG, без растровых картинок.
- Графики ECharts получают цвета из тех же токенов (тема ECharts собирается из CSS-переменных при монтировании).

## 6. Ключевые компоненты

| Компонент | Где | Заметки |
|---|---|---|
| `TrustDots level={0..4} sources=[]` | везде | Четыре точки, тултип/поповер с источниками. Анимация заполнения при росте |
| `SkillChip` | профиль, карточки, вакансии | Навык + TrustDots; `claimed_only` — контурный стиль |
| `EvidenceTimeline` | `/me/skills/:slug`, карточка | Источники по датам с силой |
| `GradeBadge` | профиль, карточки | Грейд + «предварительно» + уверенность |
| `CategoryExplainer` | профиль | Почему такая категория и грейд, разбивка по сигналам, «как подняться» |
| `ConstellationAvatar seed=` | анонимные карточки | Генеративный аватар-созвездие в стиле логотипа ФСП |
| `CandidateCard` | выдача | Псевдоним, грейд, стек, топ-навыки, ФСП-хайлайты, ожидания, совпадение |
| `MatchScore` + `ExplanationList` | карточки, вакансия | Кольцо процента + ✓/⚠ со ссылками на доказательства |
| `NLSearchBar` | `/employer/search` | Текст → чипсы с анимацией. Чипсы редактируются и удаляются. Реализация — `features/employer/QueryBar.tsx` (E19-6): `POST /search/parse` → форма фильтров; чипс виден, пока его условие есть в фильтрах слева; `~` и пунктир — `semantic_text`, `source=llm` или `confidence < 0.7`; при `prefers-reduced-motion` чипсы сразу без перехода |
| `MarketHeatmap` | `/employer/market` | Роль × грейд, переключатель метрики, клик → поиск |
| `CodeRadar` | профиль, карточка | 6 осей |
| `OfferComposer` | карточка | Выбор вакансии, вилка (обязательна), сообщение, `SalaryHint` в реальном времени |
| `OfferCard` | офферы | Вилка крупно, статус, рейтинг компании, действия |
| `BuildLog` | онбординг | Этапы долгих задач в стиле терминала |
| `NavigatorPath` | навигатор | Схемная линия от текущего грейда к следующему, узлы — навыки, флажки — соревнования |
| `AdaptiveTest` | проверка навыков | Вопрос, таймер, прогресс, результат с ростом уровня |
| `EvidenceGraph` | профиль, карточка | Граф доказательств из `GET …/graph`: force-layout (ECharts graph), узлы в стиле знака ФСП, подсветка путей под вакансию, клик по ✓ в объяснении подсвечивает путь ([graph.md §6](graph.md#6-api-подграфа)) |
| `UpliftCard` | профиль, навигатор | «Подтверди Docker — +64% вакансий (14 → 23)», способы подтверждения, комбинация навыков |
| `TeamSignals` | профиль, карточка | Командные сигналы словами без точек: «Лидерство — сильное подтверждение» + факты |
| `NewSkillBadge` | навыки | Пометка «новый навык» для `provisional` |
| `RecFeedback` | выдача, карточка | Кнопки «В шорт-лист» и «Не подходит» (с причиной), чипсы «Учли: …» с крестиком сброса |
| `QualitiesPicker` | редактор вакансии | «Важные качества»: лидерство, командная работа — удваивают их вес в подборе |
| `SalaryRangeWarning` | редактор вакансии, оффер | «Слишком широкая вилка» при `to/from > 1.6` |
| `AcceptanceMeter` | оффер, подборка | `p_accept`: «Вероятность принятия: средняя», живой пересчёт при вводе вилки |
| `InterviewKit` | карточка кандидата | Вопросы для структурированного интервью с рубриками, печать |
| `CredentialExport` | профиль | Выпуск Open Badge 3.0, ссылка на проверку, скачивание JSON |
| `QualityPage`, `FairnessPanel`, `LiveRuns`, `SusForm`, `HealthPanel` | админка, испытатель | Страница качества, справедливость, живые прогоны, анкета SUS, SLO |
| `useTrack()` | везде | Трекер событий: очередь, батч раз в 5 с, `sendBeacon` при уходе со страницы |
| `SkillsAdmin` | админка | Очередь спорных решений графа навыков, слияние, «точно разные», стоп-лист, рост графа |

## 7. Качество

- TypeScript strict, ESLint + Prettier.
- vitest для форматтеров и логики компонентов.
- **Playwright e2e на демо-сценарий** (герой Аня → Ольга → оффер → принятие через internal API имитацией бота). Прогоняется перед каждой репетицией демо.
- Lighthouse на мобильном для `/me` и лендинга: ≥ 85 по производительности.
