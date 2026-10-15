# --- 1. Сборка фронтенда ---------------------------------------------------------------------
FROM node:24-alpine AS web
WORKDIR /web
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

# --- 2. Python-сервер, который отдаёт и API, и собранный фронтенд ----------------------------
FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_DISABLE_PIP_VERSION_CHECK=1
WORKDIR /app/backend

# Сначала только зависимости — слой кэшируется, пока не меняется pyproject.toml
COPY backend/pyproject.toml ./
RUN mkdir app && touch app/__init__.py && pip install --no-cache-dir -e . && rm -rf app

COPY backend/app ./app
COPY backend/demo ./demo
COPY --from=web /web/dist /app/frontend/dist

# Не root: данные — в /app/data (том с хоста)
RUN useradd --uid 1000 --create-home appuser && mkdir -p /app/data && chown appuser /app/data
USER appuser

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/health')" || exit 1
# Наружу порт не публикуется: запросы приходят только от Caddy из docker-сети
CMD ["uvicorn", "app.api.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--forwarded-allow-ips", "*"]
