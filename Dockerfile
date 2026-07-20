# ── Stage 1: build the Tailwind CSS bundle ─────────────────────────────────
# The frontend ships as static ESM (no JS bundler). This stage only compiles
# css/app.min.css — Tailwind utilities + the eight custom component CSS files —
# via the tailwindcss CLI (frontend/build-css.sh). node:20-alpine keeps it
# small and npm deps are dropped (not copied into the runtime image).
FROM node:20-alpine AS css
WORKDIR /build/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
RUN sh build-css.sh
# → /build/frontend/css/app.min.css now exists (alongside the source frontend/)

# ── Stage 2: Python runtime ────────────────────────────────────────────────
FROM python:3.12-slim

WORKDIR /app

# All requirements ship manylinux wheels (bcrypt/cryptography/asyncpg/pydantic-core),
# so no build tools needed — and this avoids the apt/deb.debian.org layer entirely.
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/ ./backend/
# Copy the frontend FROM the css stage so it carries the built css/app.min.css
# (the source frontend/ has no app.min.css — it is a build artifact, gitignored).
COPY --from=css /build/frontend/ ./frontend/
COPY scripts/ ./scripts/

EXPOSE 8000

# Use shell form to allow $PORT env var expansion
CMD ["sh", "-c", "uvicorn backend.app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
