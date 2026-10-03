# Сборка SPA (Vite) → статика в caddy. API-клиент ходит на относительный /api/v1 через gateway.
FROM node:22-alpine AS build
RUN corepack enable
WORKDIR /app
COPY apps/web/package.json apps/web/pnpm-lock.yaml apps/web/pnpm-workspace.yaml ./
RUN pnpm install --frozen-lockfile
COPY apps/web/ ./
RUN pnpm exec vite build

FROM caddy:2-alpine
COPY --from=build /app/dist /srv
COPY apps/web/Caddyfile /etc/caddy/Caddyfile
ENV XDG_DATA_HOME=/tmp XDG_CONFIG_HOME=/tmp
USER 65532:65532
EXPOSE 8080
