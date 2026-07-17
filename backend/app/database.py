import os
import ssl as _ssl
from urllib.parse import urlparse
import asyncpg
from .config import DATABASE_URL, DB_POOL_MIN, DB_POOL_MAX, ADMIN_USER_IDS, ADMIN_USERNAMES

_pool: asyncpg.Pool | None = None


class DbConnection:
    """Context manager that acquires a connection from the pool."""

    def __init__(self):
        self._conn: asyncpg.Connection | None = None

    async def __aenter__(self) -> asyncpg.Connection:
        if _pool is None:
            raise RuntimeError("Database pool not initialized. Call init_db() first.")
        self._conn = await _pool.acquire()
        return self._conn

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self._conn is not None:
            await _pool.release(self._conn)
            self._conn = None


def get_db():
    """Return a context manager that yields a pooled connection.

    Usage in routers::

        async with get_db() as db:
            row = await db.fetchrow("SELECT ...")
    """
    return DbConnection()


async def close_db():
    global _pool
    if _pool:
        await _pool.close()
        _pool = None


# ── DDL: PostgreSQL schema ──────────────────────────────────────

_DDL = """
CREATE TABLE IF NOT EXISTS users (
    id SERIAL PRIMARY KEY,
    student_id TEXT UNIQUE,
    username TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    nickname TEXT NOT NULL,
    avatar_url TEXT,
    bio TEXT DEFAULT '',
    identity TEXT DEFAULT 'student',
    email TEXT,
    oauth_provider TEXT,
    oauth_id TEXT,
    email_verified BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS posts (
    id SERIAL PRIMARY KEY,
    author_id INTEGER NOT NULL REFERENCES users(id),
    title TEXT NOT NULL,
    content TEXT NOT NULL,
    category TEXT NOT NULL,
    likes_count INTEGER DEFAULT 0,
    comments_count INTEGER DEFAULT 0,
    parent_post_id INTEGER REFERENCES posts(id) ON DELETE SET NULL,
    is_anonymous BOOLEAN DEFAULT FALSE,
    image_url TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS post_likes (
    user_id INTEGER REFERENCES users(id),
    post_id INTEGER REFERENCES posts(id),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    PRIMARY KEY (user_id, post_id)
);

CREATE TABLE IF NOT EXISTS comments (
    id SERIAL PRIMARY KEY,
    post_id INTEGER NOT NULL REFERENCES posts(id),
    author_id INTEGER NOT NULL REFERENCES users(id),
    content TEXT NOT NULL,
    likes_count INTEGER DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS courses (
    id TEXT PRIMARY KEY,
    code TEXT NOT NULL,
    name TEXT NOT NULL,
    credits INTEGER NOT NULL,
    category TEXT NOT NULL,
    year INTEGER NOT NULL,
    semester TEXT NOT NULL,
    prerequisites TEXT DEFAULT '[]',
    description TEXT
);

CREATE TABLE IF NOT EXISTS user_courses (
    user_id INTEGER REFERENCES users(id),
    course_id TEXT REFERENCES courses(id),
    status TEXT DEFAULT 'not_started',
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    PRIMARY KEY (user_id, course_id)
);

CREATE TABLE IF NOT EXISTS course_reviews (
    id SERIAL PRIMARY KEY,
    course_id TEXT REFERENCES courses(id),
    author_id INTEGER NOT NULL REFERENCES users(id),
    rating INTEGER CHECK(rating BETWEEN 1 AND 5),
    content TEXT NOT NULL,
    helpful_count INTEGER DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS news (
    id SERIAL PRIMARY KEY,
    author_id INTEGER REFERENCES users(id),
    title TEXT NOT NULL,
    summary TEXT,
    image_url TEXT,
    category TEXT,
    source_url TEXT NOT NULL,
    published_at TIMESTAMPTZ DEFAULT NOW(),
    comments_count INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS news_comments (
    id SERIAL PRIMARY KEY,
    news_id INTEGER NOT NULL REFERENCES news(id),
    author_id INTEGER NOT NULL REFERENCES users(id),
    content TEXT NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS lostfound (
    id SERIAL PRIMARY KEY,
    author_id INTEGER NOT NULL REFERENCES users(id),
    title TEXT NOT NULL,
    description TEXT NOT NULL,
    item_type TEXT NOT NULL,
    category TEXT,
    location TEXT,
    image_url TEXT,
    status TEXT DEFAULT 'active',
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS messages (
    id SERIAL PRIMARY KEY,
    sender_id INTEGER NOT NULL REFERENCES users(id),
    receiver_id INTEGER NOT NULL REFERENCES users(id),
    content TEXT NOT NULL,
    is_read BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS refresh_tokens (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id),
    token_hash TEXT UNIQUE NOT NULL,
    expires_at TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS push_subscriptions (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    endpoint TEXT NOT NULL,
    p256dh_key TEXT NOT NULL,
    auth_key TEXT NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS email_tokens (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id),
    token_hash TEXT UNIQUE NOT NULL,
    token_type TEXT NOT NULL CHECK(token_type IN ('password_reset', 'email_verify')),
    expires_at TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_posts_author ON posts(author_id);
CREATE INDEX IF NOT EXISTS idx_posts_category ON posts(category);
CREATE INDEX IF NOT EXISTS idx_posts_created ON posts(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_comments_post ON comments(post_id);
CREATE INDEX IF NOT EXISTS idx_messages_participants ON messages(sender_id, receiver_id);
CREATE INDEX IF NOT EXISTS idx_messages_created ON messages(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_lostfound_status ON lostfound(status);
CREATE INDEX IF NOT EXISTS idx_messages_receiver_read ON messages(receiver_id, is_read);
CREATE INDEX IF NOT EXISTS idx_posts_search_fts ON posts(title);
CREATE INDEX IF NOT EXISTS idx_comments_author ON comments(author_id);
CREATE INDEX IF NOT EXISTS idx_refresh_tokens_user ON refresh_tokens(user_id);
CREATE UNIQUE INDEX IF NOT EXISTS idx_push_sub_endpoint ON push_subscriptions(endpoint);
CREATE INDEX IF NOT EXISTS idx_push_sub_user ON push_subscriptions(user_id);
CREATE INDEX IF NOT EXISTS idx_news_comments_news ON news_comments(news_id);
CREATE INDEX IF NOT EXISTS idx_news_comments_author ON news_comments(author_id);
CREATE INDEX IF NOT EXISTS idx_email_tokens_user ON email_tokens(user_id);
CREATE INDEX IF NOT EXISTS idx_email_tokens_hash ON email_tokens(token_hash);
CREATE UNIQUE INDEX IF NOT EXISTS idx_users_email ON users(email) WHERE email IS NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS idx_users_oauth ON users(oauth_provider, oauth_id) WHERE oauth_provider IS NOT NULL;

-- Add programme_code column for course planner (safe for existing DBs)
DO $$ BEGIN
    ALTER TABLE users ADD COLUMN programme_code TEXT;
EXCEPTION WHEN duplicate_column THEN NULL;
END $$;

-- Add image_url column for post images (safe for existing DBs)
DO $$ BEGIN
    ALTER TABLE posts ADD COLUMN image_url TEXT;
EXCEPTION WHEN duplicate_column THEN NULL;
END $$;

-- Add lang column for news. UNIQUE(lang, source_url) index is created by
-- sync_news.py (not here) to avoid failing on legacy seed rows that share
-- a source_url value
DO $$ BEGIN
    ALTER TABLE news ADD COLUMN lang TEXT NOT NULL DEFAULT 'zh-hant';
EXCEPTION WHEN duplicate_column THEN NULL;
END $$;

-- Add hkmu_verified column for HKMU email verification tier (safe for existing DBs)
DO $$ BEGIN
    ALTER TABLE users ADD COLUMN hkmu_verified BOOLEAN DEFAULT FALSE;
EXCEPTION WHEN duplicate_column THEN NULL;
END $$;

-- Add invite_code column for invite-share flow, lazily generated, NULL by default
DO $$ BEGIN
    ALTER TABLE users ADD COLUMN invite_code TEXT;
EXCEPTION WHEN duplicate_column THEN NULL;
END $$;

-- Partial unique index invite_code non-NULL unique multiple NULLs allowed matches idx_users_email
CREATE UNIQUE INDEX IF NOT EXISTS idx_users_invite_code ON users(invite_code) WHERE invite_code IS NOT NULL;

-- friendships table for invite-based auto-friend and future friend-request flow
CREATE TABLE IF NOT EXISTS friendships (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    friend_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    status TEXT NOT NULL DEFAULT 'accepted',
    source TEXT DEFAULT 'invite',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(user_id, friend_id)
);

-- Index for WHERE user_id = me AND status = accepted queries
CREATE INDEX IF NOT EXISTS idx_friendships_user_status ON friendships(user_id, status);

-- friend_id index defensive for CASCADE row lookup redundant under bidirectional storage
CREATE INDEX IF NOT EXISTS idx_friendships_friend ON friendships(friend_id);

-- feedback submitted via the in-app feedback page
CREATE TABLE IF NOT EXISTS feedback (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
    rating INTEGER NOT NULL CHECK (rating BETWEEN 1 AND 5),
    content TEXT NOT NULL,
    contact TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_feedback_created ON feedback(created_at DESC);

CREATE TABLE IF NOT EXISTS programmes_catalogue (
    programme_code    TEXT PRIMARY KEY,
    programme_name    TEXT NOT NULL,
    name_zh_cn        TEXT,
    name_zh_tw        TEXT,
    school            TEXT NOT NULL,
    school_order      INTEGER NOT NULL DEFAULT 0,
    prog_order        INTEGER NOT NULL DEFAULT 0,
    course_count      INTEGER NOT NULL DEFAULT 0,
    has_full_planning BOOLEAN NOT NULL DEFAULT FALSE,
    source_code_system TEXT
);

CREATE TABLE IF NOT EXISTS course_catalogue (
    id               SERIAL PRIMARY KEY,
    programme_code   TEXT NOT NULL REFERENCES programmes_catalogue(programme_code) ON DELETE CASCADE,
    school           TEXT NOT NULL,
    official_group   TEXT NOT NULL,
    canonical_bucket TEXT NOT NULL,
    bucket_order     INTEGER NOT NULL,
    course_code      TEXT NOT NULL,
    course_code_sort TEXT NOT NULL,
    display_name     TEXT NOT NULL,
    raw_name         TEXT,
    credits          INTEGER NOT NULL,
    code_system      TEXT NOT NULL,
    source_line_no   INTEGER
);

CREATE INDEX IF NOT EXISTS idx_course_catalogue_prog ON course_catalogue(programme_code);
CREATE INDEX IF NOT EXISTS idx_cc_prog_bucket ON course_catalogue(programme_code, bucket_order);
CREATE UNIQUE INDEX IF NOT EXISTS idx_cc_unique ON course_catalogue(programme_code, course_code, official_group);
CREATE INDEX IF NOT EXISTS idx_pc_school ON programmes_catalogue(school_order, prog_order);
"""


# Supabase pooler presents a chain signed by Supabase's own CA (not a public CA),
# so DB TLS verification (verify-full) needs Supabase's root as the trust anchor.
# Bundled at build time; override path via DB_SSL_ROOT_CERT if you ever rotate it.
_DB_SSL_ROOT_CERT_DEFAULT = os.path.join(
    os.path.dirname(__file__), "certs", "supabase_root_2021.pem"
)


def _build_db_ssl_context():
    """Build an SSLContext for a remote DB connection.

    Controlled by DB_SSL_MODE (default ``verify-full``):
      * verify-full : TLS + verify cert chain against the shipped Supabase root
                      CA *and* check hostname (strongest; default).
      * verify-ca   : TLS + verify cert chain, skip hostname check.
      * require     : TLS encryption only, NO cert verification. Preserves the
                      pre-F behaviour as a no-redeploy escape hatch.
      * disable     : no TLS (not recommended).

    Why X509_STRICT is cleared: ssl.create_default_context() sets
    X509_V_FLAG_X509_STRICT, which rejects Supabase's *intermediate* CA because
    it omits the keyUsage extension. That strictness is stricter than what
    ``openssl verify`` and libpq/psql enforce by default — both accept the very
    same chain. We drop the flag so verification matches OpenSSL's default: the
    shipped root CA is properly formed (keyUsage = Certificate Sign, CRL Sign),
    and chain signatures, validity, basicConstraints (CA:TRUE) and hostname are
    all still checked, so the MITM protection that is the whole point of
    verify-full stays intact. (See F in the security repair roadmap.)
    """
    mode = os.getenv("DB_SSL_MODE", "verify-full").strip().lower()
    if mode == "disable":
        return None

    if mode == "require":
        ctx = _ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = _ssl.CERT_NONE
        return ctx

    # verify-full / verify-ca → trust the shipped Supabase root CA.
    ca_path = os.getenv("DB_SSL_ROOT_CERT", _DB_SSL_ROOT_CERT_DEFAULT)
    ctx = _ssl.create_default_context(cafile=ca_path)
    ctx.verify_flags &= ~_ssl.VERIFY_X509_STRICT  # see docstring
    if mode == "verify-ca":
        ctx.check_hostname = False
    return ctx


async def init_db():
    global _pool
    # Local/Unix-socket DBs (dev, CI) never use SSL; remote hosts (Supabase
    # pooler in prod) always negotiate TLS, verified by _build_db_ssl_context().
    parsed_url = urlparse(DATABASE_URL)
    local_hosts = {"", "localhost", "127.0.0.1", "::1"}
    is_remote = (
        parsed_url.hostname not in local_hosts
        and not DATABASE_URL.startswith("postgresql:///")
    )
    _ssl_ctx = _build_db_ssl_context() if is_remote else None

    _pool = await asyncpg.create_pool(
        DATABASE_URL,
        min_size=DB_POOL_MIN,
        max_size=DB_POOL_MAX,
        ssl=_ssl_ctx,
        statement_cache_size=0,  # required for pgbouncer / Supabase pooler (transaction mode)
    )

    async with _pool.acquire() as conn:
        # Execute DDL — split by ; but keep DO $$ ... $$ blocks together
        parts = _DDL.strip().split(";")
        buffer = []
        dollar_depth = 0
        for part in parts:
            buffer.append(part)
            dollar_depth += part.count("$$")
            if dollar_depth % 2 == 0:
                stmt = ";".join(buffer).strip()
                if stmt:
                    await conn.execute(stmt)
                buffer = []

    # Auto-promote configured admins AT STARTUP. [4] login-time promotion removed —
    # it let anyone register an ADMIN_USERNAMES entry and become admin on login.
    # Prefer ADMIN_USER_IDS (immutable); ADMIN_USERNAMES is a one-shot fallback whose
    # usernames MUST be pre-registered by a trusted party before startup.
    import logging
    _log = logging.getLogger("app")
    if ADMIN_USER_IDS:
        async with _pool.acquire() as conn:
            for uid in ADMIN_USER_IDS:
                result = await conn.execute(
                    "UPDATE users SET identity = 'admin' WHERE id = $1 AND identity != 'admin'",
                    uid,
                )
                if result.endswith("1"):
                    _log.info(f"Auto-promoted user_id={uid} to admin")
    if ADMIN_USERNAMES:
        async with _pool.acquire() as conn:
            for username in ADMIN_USERNAMES:
                result = await conn.execute(
                    "UPDATE users SET identity = 'admin' WHERE username = $1 AND identity != 'admin'",
                    username,
                )
                if result.endswith("1"):
                    _log.info(f"Auto-promoted '{username}' to admin (username-based; prefer ADMIN_USER_IDS)")
