# Общий Dockerfile python-сервисов воркспейса (контекст сборки — корень репозитория).
#   docker build -f infra/docker/python.Dockerfile --build-arg PACKAGE=fsp-core --build-arg SERVICE_DIR=services/core .
# Раскладка /repo/... как в репозитории: core читает data/ относительно исходников (parents[4]).
FROM python:3.12-slim AS builder
COPY --from=ghcr.io/astral-sh/uv:0.8 /uv /usr/local/bin/uv
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never
ARG PACKAGE
ARG SERVICE_DIR
WORKDIR /repo
# слой зависимостей: манифесты всего воркспейса + lock
COPY pyproject.toml uv.lock ./
COPY packages/contracts/pyproject.toml packages/contracts/pyproject.toml
COPY packages/platform/pyproject.toml packages/platform/pyproject.toml
COPY services/core/pyproject.toml services/core/pyproject.toml
COPY services/ml/pyproject.toml services/ml/pyproject.toml
COPY services/bot/pyproject.toml services/bot/pyproject.toml
COPY services/fsp-connector/pyproject.toml services/fsp-connector/pyproject.toml
COPY services/fsp-mock/pyproject.toml services/fsp-mock/pyproject.toml
RUN uv sync --frozen --no-dev --no-install-workspace --package ${PACKAGE}
# исходники: пакеты и сам сервис (editable-установка указывает в /repo)
COPY packages packages
COPY ${SERVICE_DIR} ${SERVICE_DIR}
COPY data data
RUN uv sync --frozen --no-dev --package ${PACKAGE}

FROM python:3.12-slim
ARG SERVICE_DIR
# рантайм-библиотеки WeasyPrint (PDF-профиль, E39-20): pango тянет gobject/cairo/harfbuzz;
# шрифты — кириллица в PDF. Ставятся только в финальный образ.
RUN apt-get update \
 && apt-get install -y --no-install-recommends \
      libpango-1.0-0 libpangoft2-1.0-0 libharfbuzz0b libffi8 shared-mime-info \
      fonts-dejavu-core fonts-liberation \
 && rm -rf /var/lib/apt/lists/*
RUN useradd --system --uid 10001 --home-dir /nonexistent --shell /usr/sbin/nologin app
COPY --from=builder /repo /repo
ENV PATH=/repo/.venv/bin:$PATH PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
WORKDIR /repo/${SERVICE_DIR}
USER app
