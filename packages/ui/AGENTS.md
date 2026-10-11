# @fsp/ui — дизайн-система ФСП Карьеры

Владелец — блок 2 (`docs/process/blocks.md` §3.2). Блок 1 только использует; нужен новый общий компонент — заявка (§9).

## Назначение
Токены, `@theme` для Tailwind 4, базовые и фирменные компоненты. Пакет **без сборки**: `apps/web` импортирует исходники (`exports` в `package.json`). Эталон вида — `docs/design/v2` (v2, E38), прежний (v1) — пакет макетов в истории git (ADR-050).

## Команды (из корня репозитория)
- `pnpm install` — один lock на workspace (`apps/web`, `packages/ui`).
- `pnpm --filter @fsp/ui dev` — playground на http://localhost:28174 (Токены / Базовые / Фирменные, переключатель темы).
- `pnpm --filter @fsp/ui test | lint | typecheck | build`.
- `pnpm shot <маршрут> [--as candidate|employer|admin]` — 6 PNG (1440/1024/390 × светлая/тёмная) в `reports/shots/`. Приложение ждём на :28173, `--playground` — на :28174, `SHOT_BASE` — своя база. В Git Bash маршрут можно писать без ведущего `/`. Нет Chromium Playwright — берётся системный Edge/Chrome (`SHOT_CHANNEL`).

## Ключевые файлы
- `src/styles/tokens.css` — CSS-переменные, светлая в `:root`, тёмная в `.dark`.
- `src/styles/index.css` — `@theme inline`, `dark`-вариант, базовые стили (импорт: `@fsp/ui/styles.css`).
- `src/primitives/` — базовые (`button`, `form`, `overlay`, `display`: Radix + lucide + sonner; Skeleton, EmptyState, ErrorState, NotFound общие для Б1 и Б2); `src/brand/` — фирменные (`index.tsx`: TrustDots, SkillChip, аватар, MatchRing; `protocol.tsx`: GradeBadge, FspProtocol, TeamSignal, SectionLabel, VerifiedMark, `pseudonymLabel`; `match.tsx`: MatchWhy, SalaryRange, StatusBadge, AcceptanceMeter, UpliftCard, CircuitLine, BuildLog; `cards.tsx`: CandidateCard, OfferCard); `src/lib/format.ts` — `formatRub`; `src/lib/cn.ts`; `src/index.ts` — публичный экспорт.
- `src/v2/` — компоненты макетов v2 (`docs/design/v2`, E38-0): `primitives.tsx`, `charts.tsx`, `cards.tsx`, `assessment.tsx`, `shell.tsx`; тесты — `v2.test.tsx`; доска в playground — `#v2` (`playground/V2Board.tsx`).
- `src/v3/` — свои контролы (E39-1): `combobox.tsx` (Select/Combobox/MultiSelect), `inputs.tsx` (SkillInput, ProfessionInput, NumberInput, SalaryRangeInput), `content.tsx` (InfoTip, Markdown, MarkdownEditor, ScrollTabs, Avatar; блок ```` ```mermaid ```` в Markdown → `Diagram`), `diagram.tsx` (Diagram: mermaid лениво, тема по токенам, полноэкранный просмотр с масштабом и сдвигом, E41-9), `skeletons.tsx`, `roadmap.tsx`, `graph.tsx` + `graph-model.ts` (EvidenceGraph, E39-14); тесты — `v3.test.tsx`; доска — `#v3` (`playground/V3Board.tsx`).
- `scripts/design-shots.mjs` — `make design-shots` / `pnpm --filter @fsp/ui design-shots [--only <подстрока>]`: PNG макетов v2 в `docs/design/v2/png/`.
- `playground/data.ts` — демо-данные (из пакета макетов v1) (только playground и тесты).

## Правила
- Только относительные импорты внутри пакета (алиаса `@/` здесь нет).
- Цвета, шрифты, радиусы — только из токенов; бренд не меняем.
- Подключение в приложении: `@import "@fsp/ui/styles.css"` + `@source` на `packages/ui/src` в `apps/web/src/styles/tailwind.css`.

## Документы
- `docs/architecture/frontend.md` §2, §5; `docs/process/backlog.md` §E19.
