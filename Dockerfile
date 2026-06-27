FROM python:3.12-slim

WORKDIR /app

# All requirements ship manylinux wheels (bcrypt/cryptography/asyncpg/pydantic-core),
# so no build tools needed — and this avoids the apt/deb.debian.org layer entirely.
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/ ./backend/
COPY frontend/ ./frontend/
COPY scripts/ ./scripts/

EXPOSE 8000

# Use shell form to allow $PORT env var expansion
CMD ["sh", "-c", "uvicorn backend.app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
