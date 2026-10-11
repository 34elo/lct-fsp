# Сборка SPA (Vite) → статика в caddy. API-клиент ходит на относительный /api/v1 через gateway.
# Контекст — корень репозитория: pnpm-workspace (apps/web + packages/ui).
FROM node:22-alpine AS build
RUN corepack enable
WORKDIR /repo
COPY package.json pnpm-workspace.yaml pnpm-lock.yaml ./
COPY apps/web/package.json apps/web/
COPY packages/ui/package.json packages/ui/
RUN pnpm install --frozen-lockfile --filter fsp-web...
COPY packages/ui/ packages/ui/
COPY apps/web/ apps/web/
# Режим жюри вшивается при сборке (import.meta.env), см. features/landing/jury.ts
ARG VITE_JURY_MODE=false
ENV VITE_JURY_MODE=$VITE_JURY_MODE
# Адрес кабинета для кнопок лендинга на корневом домене; пусто — всё на одном origin
ARG VITE_APP_URL=
ENV VITE_APP_URL=$VITE_APP_URL
RUN pnpm --filter fsp-web exec vite build

FROM caddy:2-alpine
COPY --from=build /repo/apps/web/dist /srv
COPY apps/web/Caddyfile /etc/caddy/Caddyfile
ENV XDG_DATA_HOME=/tmp XDG_CONFIG_HOME=/tmp
USER 65532:65532
EXPOSE 8080
