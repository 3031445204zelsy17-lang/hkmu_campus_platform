from contextlib import asynccontextmanager
import secrets

from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.responses import Response
import os

from .database import init_db, close_db
from .config import API_PREFIX, SECRET_KEY
from .routers import auth, posts, courses, users, news, lostfound, messages


@asynccontextmanager
async def lifespan(app: FastAPI):
    if SECRET_KEY == "change-me-in-production":
        import warnings
        warnings.warn("WARNING: Using default SECRET_KEY. Set SECRET_KEY in .env for production!")
    await init_db()
    yield
    await close_db()


app = FastAPI(title="HKMU Campus Platform", version="0.1.0", lifespan=lifespan)

cors_origins = os.getenv("CORS_ORIGINS", "http://localhost:8000,http://localhost:3000")
allowed_origins = [o.strip() for o in cors_origins.split(",") if o.strip()]
# Auto-detect cloud platform URLs
for env_var in ["RENDER_EXTERNAL_URL", "RAILWAY_STATIC_URL", "RAILWAY_PUBLIC_DOMAIN"]:
    val = os.getenv(env_var)
    if val:
        if not val.startswith("http"):
            val = f"https://{val}"
        allowed_origins.append(val)

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def no_cache_dev(request: Request, call_next):
    response: Response = await call_next(request)
    if request.url.path.startswith(("/js/", "/css/")) or request.url.path == "/sw.js":
        response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    return response


# CSRF double-submit cookie
CSRF_COOKIE = "csrf_token"
CSRF_HEADER = "X-CSRF-Token"
SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}


@app.middleware("http")
async def csrf_protect(request: Request, call_next):
    # Set CSRF cookie on every response if not present
    response: Response = await call_next(request)

    if request.method in SAFE_METHODS:
        cookie_val = request.cookies.get(CSRF_COOKIE)
        if not cookie_val:
            response.set_cookie(
                CSRF_COOKIE,
                secrets.token_hex(32),
                httponly=False,
                samesite="lax",
                path="/",
            )
        return response

    # Mutating requests: validate header matches cookie
    cookie_val = request.cookies.get(CSRF_COOKIE)
    header_val = request.headers.get(CSRF_HEADER)
    if not cookie_val or not header_val or not secrets.compare_digest(cookie_val, header_val):
        return JSONResponse({"detail": "CSRF token missing or invalid"}, status_code=403)

    return response


app.include_router(auth.router, prefix=API_PREFIX)
app.include_router(posts.router, prefix=API_PREFIX)
app.include_router(courses.router, prefix=API_PREFIX)
app.include_router(users.router, prefix=API_PREFIX)
app.include_router(news.router, prefix=API_PREFIX)
app.include_router(lostfound.router, prefix=API_PREFIX)
app.include_router(messages.router, prefix=API_PREFIX)


@app.get("/api/health")
async def health():
    return {"status": "ok"}


frontend_path = os.path.join(os.path.dirname(__file__), "..", "..", "frontend")
if os.path.isdir(frontend_path):
    app.mount("/", StaticFiles(directory=frontend_path, html=True), name="frontend")
