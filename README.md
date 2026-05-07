# HKMU Campus Platform

Full-stack campus platform combining community forum, academic planner, messaging, and campus services for HKMU students.

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Backend | FastAPI + SQLite (aiosqlite) |
| Auth | JWT (python-jose) + bcrypt |
| Frontend | Vanilla HTML/CSS/JS + Tailwind CDN |
| Routing | Hash-based SPA |
| Messaging | WebSocket + REST polling fallback |
| Mobile | PWA (manifest + Service Worker) |
| i18n | data-i18n system (3 languages) |

## Quick Start

```bash
# 1. Install dependencies
pip install -r backend/requirements.txt

# 2. Configure environment
cp .env.example .env
# Edit .env — set a strong SECRET_KEY

# 3. Seed the database (creates tables + 43 courses + test accounts)
python scripts/seed_courses.py

# 4. Start dev server
python -m uvicorn backend.app.main:app --reload --port 8000
```

Open http://localhost:8000 — Swagger UI at http://localhost:8000/docs

### Test Accounts

| Username | Password | Role |
|----------|----------|------|
| testuser | testpass123 | Student |

## Project Structure

```
hkmu-campus-platform/
├── backend/
│   ├── app/
│   │   ├── main.py              # FastAPI entry, CORS, static mount
│   │   ├── config.py            # Env-based config
│   │   ├── database.py          # SQLite connection + 9 tables
│   │   ├── models.py            # Pydantic schemas
│   │   ├── routers/             # REST + WebSocket endpoints
│   │   └── services/            # Auth, sanitizer, WS manager
│   └── requirements.txt
├── frontend/
│   ├── index.html               # SPA shell + PWA meta
│   ├── manifest.json            # PWA manifest
│   ├── sw.js                    # Service worker (tiered caching)
│   ├── css/                     # Page-scoped styles (data-page)
│   ├── js/
│   │   ├── app.js               # Init + auth state
│   │   ├── router.js            # Hash router
│   │   ├── api.js               # Fetch wrapper (JWT inject)
│   │   ├── components/          # Toast, Skeleton, Modal, Nav
│   │   ├── pages/               # Page modules
│   │   └── utils/               # i18n, time, storage
│   └── icons/                   # PWA icons (72–512px)
├── scripts/
│   ├── dev.py                   # Dev launcher
│   └── seed_courses.py          # DB seeding
└── progress.json                # Task tracking
```

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/v1/auth/register` | Register |
| POST | `/api/v1/auth/login` | Login → JWT |
| GET | `/api/v1/auth/me` | Current user |
| GET | `/api/v1/posts` | Post list (paginated, sorted, filtered) |
| POST | `/api/v1/posts` | Create post |
| GET | `/api/v1/courses` | Course catalog (43 courses) |
| GET/POST | `/api/v1/courses/progress` | User course progress |
| GET | `/api/v1/messages/conversations` | Chat conversations |
| WS | `/api/v1/messages/ws` | Real-time messaging |
| GET | `/api/v1/news` | News link aggregation |
| GET | `/api/v1/lostfound` | Lost & found items |
| GET | `/api/v1/users/search` | User search |

Full interactive docs: http://localhost:8000/docs

## Features

- **Community Forum** — Posts, comments, likes, category filtering, search, glass-morphism UI
- **Academic Planner** — 43 DSAI courses, progress tracking, prerequisite checking, one-click DSAI template
- **Private Messaging** — Real-time WebSocket chat with REST polling fallback, unread counts
- **Campus News** — Link aggregation with external URL previews
- **Lost & Found** — Report/claim items, status tracking, filtering
- **User Profiles** — Avatar, bio, post history, academic progress summary
- **PWA** — Installable, offline-capable with tiered caching
- **i18n** — Trilingual support (data-i18n system)
- **Security** — JWT auth, bcrypt hashing, XSS prevention, CORS hardening, rate limiting

## Development

```bash
# Run with auto-reload
python -m uvicorn backend.app.main:app --reload --port 8000

# Or use the dev script
python scripts/dev.py

# Verify backend syntax
python -m py_compile backend/app/main.py

# Check API health
curl http://localhost:8000/api/health
```

### Code Conventions

- CSS isolation via `data-page` attribute
- Function-based UI components, no scattered DOM string concatenation
- XSS prevention: backend HTML escaping + frontend `textContent`
- API prefix: `/api/v1/`
- Git commits: `feat:` / `fix:` / `chore:` prefix

## Deployment

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `SECRET_KEY` | (required) | JWT signing key — **must change in production** |
| `DATABASE_URL` | `campus.db` | SQLite database path |
| `CORS_ORIGINS` | `http://localhost:8000,...` | Comma-separated allowed origins |

### Production Checklist

1. Set a cryptographically random `SECRET_KEY`
2. Restrict `CORS_ORIGINS` to your domain
3. Run behind a reverse proxy (nginx/Caddy) with HTTPS
4. Set `DATABASE_URL` to a persistent volume path
5. Add rate limiting (Redis-backed for multi-process)

## License

MIT
