from contextlib import asynccontextmanager
import logging
import secrets

from fastapi import FastAPI, Request, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.responses import Response
import os

from .database import init_db, close_db
from .config import API_PREFIX, SECRET_KEY, RATE_LIMIT_PER_MIN
from .routers import auth, posts, courses, users, news, lostfound, messages, push, upload, feedback, log
from .services.rate_limiter import check_rate_limit

# Security/observability logger. Propagates to uvicorn root → stdout → Azure Log
# Stream + Application Insights. WARNING+ surfaces in App Insights failure views.
logger = logging.getLogger("hkmu.security")


def _init_app_insights(app: FastAPI) -> None:
    """Wire Azure Monitor OpenTelemetry (Application Insights) when a connection
    string is present. Dormant by default — no env, no telemetry, no behavior
    change. configure_azure_monitor covers logging/exporter + the FastAPI
    instrumentor; we also call instrument_app explicitly.

    MUST be called at import time (after the app is fully built — see the
    tail-of-file call), NOT inside lifespan: Starlette builds middleware_stack
    in FastAPI.__init__, so adding the OTel ASGI middleware in lifespan startup
    is too late — it never enters uvicorn's serve stack and AppRequests stays
    empty (FR2 v1 ran it from lifespan → AppRequests=0; v2 moves it here)."""
    conn = os.getenv("APPLICATIONINSIGHTS_CONNECTION_STRING", "").strip()
    if not conn:
        return
    try:
        from azure.monitor.opentelemetry import configure_azure_monitor
        configure_azure_monitor()  # reads APPLICATIONINSIGHTS_CONNECTION_STRING from env
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
        FastAPIInstrumentor.instrument_app(app)
        logger.info("app_insights enabled")
    except Exception as e:
        # Never let monitoring break the app.
        logger.warning("app_insights init failed: %s", e)


@asynccontextmanager
def _validate_secret_key(key: str) -> None:
    """[13] fail-closed: 空/default SECRET_KEY → 拒绝启动。

    JWT 用 SECRET_KEY 签名;若为 default/空,任何人可伪造 token(含 admin)冒充账号。
    本地 .env / CI(ci-secret-key) / 生产 均已设非 default 值,此校验只拦未来误配。
    """
    if not key or key == "change-me-in-production":
        raise RuntimeError(
            "SECRET_KEY is empty or the default. Set a strong random SECRET_KEY "
            "(e.g. `openssl rand -hex 32`) in the environment before starting."
        )


async def lifespan(app: FastAPI):
    _validate_secret_key(SECRET_KEY)
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
CLIENT_PLATFORM_HEADER = "X-Client-Platform"
CSRF_BYPASS_CLIENTS = {"wechat-miniprogram"}
SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}


@app.middleware("http")
async def csrf_protect(request: Request, call_next):
    if request.url.path.startswith(API_PREFIX):
        return await call_next(request)

    client_platform = request.headers.get(CLIENT_PLATFORM_HEADER, "").strip().lower()
    if client_platform in CSRF_BYPASS_CLIENTS:
        return await call_next(request)

    if request.method in SAFE_METHODS:
        response: Response = await call_next(request)
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

    return await call_next(request)


def _client_ip(request: Request) -> str:
    """Best-effort client IP. Prefers first X-Forwarded-For hop (Azure front-end
    sets this), falls back to the direct peer."""
    xff = request.headers.get("x-forwarded-for", "")
    if xff:
        return xff.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


# Optional global per-IP rate limit (defense-in-depth vs scraping / blunt abuse).
# DISABLED by default (RATE_LIMIT_PER_MIN=0) so it cannot throttle real users on
# deploy; enable via Azure app settings once tuned. In-memory → per-instance; needs
# Redis once we go multi-instance.
@app.middleware("http")
async def global_ip_rate_limit(request: Request, call_next):
    if RATE_LIMIT_PER_MIN > 0:
        path = request.url.path
        if path.startswith(API_PREFIX) and not path.endswith("/health"):
            ip = _client_ip(request)
            try:
                check_rate_limit(f"ip:{ip}", max_requests=RATE_LIMIT_PER_MIN, window_seconds=60)
            except HTTPException:
                # security_audit (outer) logs this 429 with ip/path.
                return JSONResponse(
                    {"detail": "Too many requests. Try again later."},
                    status_code=429,
                )
    return await call_next(request)


# Security audit (outermost middleware): single chokepoint that logs auth/abuse-
# relevant responses so App Insights + Azure Log Stream surface attack patterns
# (brute-force login, scraping, CSRF attempts, server errors).
_AUDITED_STATUS = {401, 403, 429}


@app.middleware("http")
async def security_audit(request: Request, call_next):
    response: Response = await call_next(request)
    path = request.url.path
    if (
        path.startswith(API_PREFIX)
        and request.method != "OPTIONS"
        and not path.endswith("/health")
        and (response.status_code in _AUDITED_STATUS or response.status_code >= 500)
    ):
        logger.warning(
            "sec_audit status=%s method=%s path=%s ip=%s",
            response.status_code, request.method, path, _client_ip(request),
        )
    return response


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    """Last-resort for unhandled errors: log full traceback server-side, return a
    generic 500 so DB host / SQL / stack internals never reach the client. Note:
    HTTPException / RequestValidationError keep their dedicated FastAPI handlers."""
    logger.exception("Unhandled error %s %s", request.method, request.url.path)
    return JSONResponse({"detail": "Internal server error"}, status_code=500)


app.include_router(auth.router, prefix=API_PREFIX)
app.include_router(posts.router, prefix=API_PREFIX)
app.include_router(courses.router, prefix=API_PREFIX)
app.include_router(users.router, prefix=API_PREFIX)
app.include_router(news.router, prefix=API_PREFIX)
app.include_router(lostfound.router, prefix=API_PREFIX)
app.include_router(messages.router, prefix=API_PREFIX)
app.include_router(push.router, prefix=API_PREFIX)
app.include_router(upload.router, prefix=API_PREFIX)
app.include_router(feedback.router, prefix=API_PREFIX)
app.include_router(log.router, prefix=API_PREFIX)


@app.get("/api/health")
async def health():
    """Liveness + DB readiness probe. Returns 503 when the database is
    unreachable, so monitoring reflects real availability instead of a
    hardcoded ok (which previously masked a paused Supabase project)."""
    try:
        from .database import get_db
        async with get_db() as db:
            await db.fetchval("SELECT 1")
        return {"status": "ok", "database": "up"}
    except Exception as e:
        # Log the real error server-side only; asyncpg exceptions can embed the DB
        # host / DSN, which must not leak to clients or scrapers in the response body.
        logger.warning("health probe failed: %s", e)
        return JSONResponse(
            {"status": "degraded", "database": "down"},
            status_code=503,
        )


frontend_path = os.path.join(os.path.dirname(__file__), "..", "..", "frontend")
if os.path.isdir(frontend_path):
    app.mount("/", StaticFiles(directory=frontend_path, html=True), name="frontend")

# Wire App Insights at import time — AFTER the app is fully built (middleware +
# routers + mount). See _init_app_insights docstring for why this can't live in
# lifespan (Starlette builds middleware_stack in FastAPI.__init__).
_init_app_insights(app)
