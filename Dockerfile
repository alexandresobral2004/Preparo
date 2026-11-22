# --- Etapa 1: build do frontend (React + Vite) ---
FROM node:22-alpine AS frontend
WORKDIR /build
RUN corepack enable
COPY frontend/package.json frontend/pnpm-lock.yaml frontend/pnpm-workspace.yaml ./
RUN pnpm install --frozen-lockfile
COPY frontend/ ./
RUN pnpm build

# --- Etapa 2: servidor FastAPI + frontend já buildado, em porta única ---
FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PREPARO_DB_PATH=/data/preparo.db \
    PREPARO_COOKIE_SECURE=1

WORKDIR /srv/app
COPY backend/pyproject.toml backend/pyproject.toml
COPY backend/app backend/app
# Instala só as dependências; o código roda a partir de /srv/app/backend (config.py acha frontend/dist por caminho relativo).
RUN pip install --no-cache-dir ./backend
COPY --from=frontend /build/dist frontend/dist

RUN useradd --system --uid 10001 app && mkdir -p /data && chown app /data
USER app
VOLUME /data
EXPOSE 8000

# Um único worker: o bloqueio de tentativas de login fica na memória do processo e o SQLite aceita um escritor por vez.
CMD ["sh", "-c", "exec uvicorn app.main:app --app-dir /srv/app/backend --host 0.0.0.0 --port ${PORT:-8000} --workers 1 --proxy-headers --forwarded-allow-ips='*'"]
