# Аудит сетки и отступов (E39-4)

Метод: по коду, без скриншотов (стек для снимков в этой сессии не поднимали). Проверены классы корня каждой страницы на трёх ширинах: 1440 (колонка по `max-w`), 768 и 375 (поля `px-4`, без горизонтальной прокрутки). Снимки 1440/768/375 стоит снять при ближайшем прогоне `reports/shots`.

## Правило

Каркас `PageContainer` — максимум 1440, без полей. Страница берёт ширину из `PAGE` (`apps/web/src/shared/lib/page.ts`): `narrow` 768 (формы), `normal` 1328 (списки и кабинеты), `wide` во всю ширину (таблицы, админка). Поля `px-4 md:px-6`, `py-4 md:py-6`, промежуток между блоками `gap-4`; ритм 8/16/24/32 = `gap-2/4/6/8`.

## Найдено и исправлено

| Маршрут | Было | Стало |
|---|---|---|
| `/me/responses` | `max-w-3xl`, карточки уже остальных экранов | `normal` |
| `/me/offers`, `/employer/offers`, `/employer/responses` | 3xl / 6xl, свои поля `p-4 md:p-6` | `normal` |
| `/me/interests` | `LIST_PAGE` 1328 | `normal` (без изменений по ширине) |
| `/me/tasks`, `/employer/tasks` | 3xl / 4xl | `normal` |
| `/me/assessment`, `/history`, `/attempts/:id/result` (`assessment/ui.tsx`) | колонка без полей: на 375 текст впритык к краю | `narrow` / `normal` с полями |
| `/me/assessment/attempts/:id` | 760, без полей | `narrow` |
| Баннер пути «опрос → тест» | `max-w-5xl`, уже контента | 1328 |
| `/onboarding` | 3xl, без боковых полей | `narrow` |
| `/me`, `/me/profile`, `/me/settings`, `/me/stats` | 1328 (копия строки в 4 файлах) | `normal` из общего `PAGE` |
| `/employer`, `/employer/shortlist`, `/employer/categories/...`, `/employer/needs/:id`, `/employer/search` | разные поля (`lg:px-10`, `py-6/8`) | `normal`, общий ритм |
| `/employer/needs/new` | 880, `py-8` | `narrow` |
| `/employer/subscriptions` | 5xl, две колонки | `normal`, две колонки с `lg` |
| `/employer/vacancies`, `/employer/candidates/:id` | 5xl / 1328 | `normal` |
| `/employer/company`, `/employer/offers/new`, `/me/profile/edit`, `/me/navigator`, `/jobs/:id`, `/me/skills/:slug` | 2xl–3xl, часть без полей | `narrow` |
| `/employer/vacancies/:id`, админка, демо, качество, федерация | 6xl или без `max-w`, свои поля | `wide` |
| `/login`, `/register`, `/auth/magic`, `/consents`, `/verify-email` | карточка у верхнего края | по центру экрана (`min-h` и `items-center`) |
| Вкладки раздела | вторая полоса под шапкой на всю ширину | внутри страницы, над содержимым, в ширине страницы |

## Не менялось

- Публичные `/jobs`, `/terms`, `/privacy`: колонка `PublicLayout` (6xl, `p-4 md:p-6`), текст `Legal` 2xl — это чтение, не кабинет.
- Лендинг `/` и `/run/:token` рисуют свою сетку.

## Открытые пункты

Нет. Меню без подвкладок и слияние «Интересов» с приглашениями — отдельные задачи E39-25 и E39-18.
