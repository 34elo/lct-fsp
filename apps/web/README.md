# web

SPA для трёх ролей: кандидат, работодатель, администратор ФСП. React 19 + Vite + TypeScript (strict), Tailwind 4, TanStack Query, React Router 7, компоненты — [`@fsp/ui`](../../packages/ui/README.md). Описание — [frontend.md](../../docs/architecture/frontend.md).

| Каталог (`src/`) | Что |
|---|---|
| `app/` | Маршруты (`routes.ts` — карта и меню по ролям), провайдеры, каркасы страниц по ролям (`layouts/`) |
| `features/<раздел>/` | Экраны и их модели: `assessment`, `profile`, `offers`, `employer`, `needs`, `constructor`, `tasks`, `jobs`, `navigator`, `graph`, `fsp`, `fsp-registry`, `admin`, `admin-taxonomy`, `demo`, `landing`, `auth`, `onboarding`, `responses`, `runs`, `quality` |
| `pages/` | Вход, регистрация, согласия, онбординг, 404 |
| `shared/` | Авторизация, SSE, тема, аналитика, глоссарий, работа с изображениями |
| `api/` | Клиент, сгенерированный orval из `openapi.json` (руками не правится: `make api-gen`) |

## Команды

```bash
pnpm install
pnpm --filter fsp-web dev            # http://localhost:28173, API проксируется на gateway
pnpm --filter fsp-web test           # vitest
pnpm --filter fsp-web lint
pnpm --filter fsp-web typecheck
make e2e                              # Playwright на стенде с демо-данными (make up && make seed)
```

Сборка для compose — `apps/web/Dockerfile` (Caddy отдаёт статику). Переменные сборки: `VITE_JURY_MODE` (кнопки входа жюри), `VITE_APP_URL` (кабинет на отдельном домене).

e2e (`e2e/`): сквозной демо-сценарий, регистрация → тест, подбор работодателя, реестр ФСП, пароль HR, ссылки лендинга, статистика после теста; проекты `desktop` и `mobile-375`.
