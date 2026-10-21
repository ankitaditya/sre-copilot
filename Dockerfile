# syntax=docker/dockerfile:1.7

FROM node:22-bookworm-slim AS ui-builder
WORKDIR /ui
COPY ui/package.json ui/package-lock.json* ./
RUN npm ci --no-audit --no-fund
COPY ui/ ./
RUN npm run build

FROM python:3.12-slim AS python-builder
ENV VIRTUAL_ENV=/opt/venv PATH=/opt/venv/bin:$PATH
RUN python -m venv "$VIRTUAL_ENV"
WORKDIR /build
COPY pyproject.toml README.md ./
COPY src ./src
RUN python -m pip install --no-cache-dir .

FROM python:3.12-slim AS runtime
ENV VIRTUAL_ENV=/opt/venv \
    PATH=/opt/venv/bin:$PATH \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    ENVIRONMENT=production \
    DATABASE_PATH=/app/data/sre-copilot.db \
    UI_BUILD_DIR=/app/ui/dist \
    RUNBOOKS_DIR=/app/runbooks \
    SANDBOX_STATE_PATH=/app/sandbox/runtime/state.json
RUN useradd --system --uid 1001 --create-home app
WORKDIR /app
COPY --from=python-builder /opt/venv /opt/venv
COPY --from=ui-builder --chown=app:app /ui/dist ./ui/dist
COPY --chown=app:app runbooks ./runbooks
COPY --chown=app:app sandbox/chaos.py ./sandbox/chaos.py
COPY --chown=app:app sandbox/runtime ./sandbox/runtime
RUN mkdir -p /app/data && chown -R app:app /app/data /app/sandbox/runtime
USER app
EXPOSE 8000
VOLUME ["/app/data", "/app/sandbox/runtime"]
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health')"
CMD ["sre-copilot"]
