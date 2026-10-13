# InvoiceReferee single-process image (plan T10).
# One Uvicorn process serving the FastAPI app + the built static frontend.
# SQLite and uploads live on a persistent volume; secrets come from the env.

FROM python:3.12-slim AS base
ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    UV_LINK_MODE=copy

# uv is the pinned dependency resolver (uv.lock is the source of truth).
COPY --from=ghcr.io/astral-sh/uv:0.12.9 /uv /uvx /bin/

WORKDIR /app

# Python deps first (cached layer), locked install.
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

# Node 24 to build the frontend once, then discard the toolchain.
FROM node:24-slim AS frontend
WORKDIR /web
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM base AS runtime
# App source, assets (font + license), demo context and the synthetic dataset.
COPY src/ ./src/
COPY assets/ ./assets/
COPY data/ ./data/
COPY scripts/ ./scripts/
COPY frontend/index.html frontend/vite.config.ts frontend/tsconfig.json ./
COPY --from=frontend /web/dist ./frontend/dist

ENV INVOICE_REFEREE_DB=/data/invoice-referee.sqlite \
    INVOICE_REFEREE_UPLOADS=/data/uploads \
    PORT=8000
VOLUME ["/data"]
EXPOSE 8000

# One entry: the same scripts/dev.py the pilot uses, against the volume.
CMD ["uv", "run", "--frozen", "--no-dev", "python", "scripts/dev.py", \
     "--mode", "stub", "--host", "0.0.0.0", "--port", "8000", \
     "--db", "/data/invoice-referee.sqlite", "--uploads", "/data/uploads"]
