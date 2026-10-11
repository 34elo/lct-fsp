# Фронтенд

Одно SPA для всех ролей: `apps/web` — React 19, Vite, TypeScript strict, Tailwind 4, TanStack Query, React Router 7. Компоненты и токены — пакет `@fsp/ui` ([design.md](../design.md)). Почему SPA — [ADR-0002](../adr/0002-python-and-react-spa.md).

## Устройство

- **Маршруты** — `src/app/routes.ts`: карта путей, раздел (публичный, вход, кандидат, работодатель, администратор) и пункты меню. Роль определяется разделом; `RequireRole` не пускает чужую роль. Тест `routes.test.ts` проверяет, что у каждого пункта меню есть работающий экран.
- **Каркасы** — `src/app/layouts`: шапка с меню по роли, нижняя панель на телефоне, боковая панель администратора по группам.
- **Данные** — только через клиент, сгенерированный orval из OpenAPI (`src/api`, `make api-gen`): хуки TanStack Query с типами. Ошибки — Problem Details с машинным `code`, тексты по коду — в `text.ts` раздела.
- **Авторизация** — access-токен в памяти, refresh по cookie `rt`; тихое обновление при 401.
- **Живые обновления** — SSE `/events/stream` (`useEventStream`): новые приглашения, статусы, готовность разбора резюме.
- **Раздел** `src/features/<имя>/`: экраны, модель (`*-model.ts` — чистые функции, покрыты тестами), тексты (`text.ts`), тесты.

## Экраны

| Роль | Маршруты |
|---|---|
| Гость | `/` лендинг, `/jobs` вакансии, `/login`, `/register`, `/verify-email`, `/consents`, `/run/:token` живой прогон |
| Кандидат | `/me` главная, `/me/assessment` опрос и тест, `/me/assessment/attempts/:id` прохождение, `…/result`, `…/review`, `/me/assessment/history`, `/me/profile` профиль (обзор, навыки, граф, данные), `/me/profile/edit`, `/me/skills/:slug`, `/me/offers` приглашения, интересы и отклики, `/me/stats`, `/me/navigator`, `/me/tasks`, `/settings` |
| Работодатель | `/employer` подбор (категории / кандидаты), `/employer/categories/:profession/:grade`, `/employer/candidates/:id`, `/employer/shortlist`, `/employer/offers`, `/employer/offers/new`, `/employer/vacancies`, `/employer/vacancies/:id/shortlist`, `/employer/tasks`, `/employer/families/new` конструктор, `/employer/company`, `/employer/subscriptions` |
| Администратор | `/federation` главная, `/admin/families` допуск заданий, `/federation/moderation`, `/federation/registry` реестр ФСП, `/admin/professions`, `/admin/skills`, `/federation/funnel`, `/federation/analytics`, демо-экраны `/admin/demo/*` |

## UX-правила

- Нет пункта меню, ссылки или кнопки без работающего экрана: не готово — скрыто.
- Каждый экран отвечает на «где я?» и «что делать дальше?»: одно главное действие.
- Пустые состояния всегда с действием («Пройдите тест», «Опишите, кого ищете»).
- Каждый экран проверяется на ширине 375 px и в тёмной теме (e2e-проект `mobile-375`).
- Тексты — по-русски, без внутренних терминов; формулы — во всплывающих пояснениях глоссария (`src/shared/glossary.ts`).

## Тесты

- vitest + Testing Library: модели разделов и экраны с замоканным API (`pnpm -r test`).
- Playwright e2e на стенде с демо-данными (`make e2e`): сквозной демо-сценарий кандидата и работодателя, регистрация → тест, подбор, реестр ФСП, доступ HR, лендинг.
