# @fsp/ui — дизайн-система ФСП Карьеры

Владелец — блок 2 (`docs/process/blocks.md` §3.2). Блок 1 только использует; нужен новый общий компонент — заявка (§9).

## Назначение
Токены, `@theme` для Tailwind 4, базовые и фирменные компоненты. Пакет **без сборки**: `apps/web` импортирует исходники (`exports` в `package.json`). Эталон вида — `docs/design/pack` (ADR-050).

## Команды (из корня репозитория)
- `pnpm install` — один lock на workspace (`apps/web`, `packages/ui`).
- `pnpm --filter @fsp/ui dev` — playground на http://localhost:28174 (Токены / Базовые / Фирменные, переключатель темы).
- `pnpm --filter @fsp/ui test | lint | typecheck | build`.
- `pnpm shot <маршрут> [--as candidate|employer|admin]` — 6 PNG (1440/1024/390 × светлая/тёмная) в `reports/shots/`. Приложение ждём на :28173, `--playground` — на :28174, `SHOT_BASE` — своя база. В Git Bash маршрут можно писать без ведущего `/`. Нет Chromium Playwright — берётся системный Edge/Chrome (`SHOT_CHANNEL`).

## Ключевые файлы
- `src/styles/tokens.css` — CSS-переменные, светлая в `:root`, тёмная в `.dark`.
- `src/styles/index.css` — `@theme inline`, `dark`-вариант, базовые стили (импорт: `@fsp/ui/styles.css`).
- `src/primitives/` — базовые компоненты; `src/brand/` — фирменные; `src/lib/cn.ts`; `src/index.ts` — публичный экспорт.
- `playground/data.ts` — демо-данные из `docs/design/pack/docs/DATA.md` (только playground и тесты).

## Правила
- Только относительные импорты внутри пакета (алиаса `@/` здесь нет).
- Цвета, шрифты, радиусы — только из токенов; бренд не меняем (`docs/design/pack/AGENTS.md`).
- Подключение в приложении: `@import "@fsp/ui/styles.css"` + `@source` на `packages/ui/src` в `apps/web/src/styles/tailwind.css`.

## Документы
- `docs/architecture/frontend.md` §2, §5; `docs/process/backlog.md` §E19; `docs/design/pack/`.
