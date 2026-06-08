import ssl as _ssl
import asyncpg
from .config import DATABASE_URL, DB_POOL_MIN, DB_POOL_MAX, ADMIN_USERNAMES

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
"""


async def init_db():
    global _pool
    # Auto-detect SSL: remote hosts need it, local socket/TCP does not
    _ssl_ctx = None
    if not DATABASE_URL.startswith("postgresql:///"):
        _ssl_ctx = _ssl.create_default_context()
        _ssl_ctx.check_hostname = False
        _ssl_ctx.verify_mode = _ssl.CERT_NONE

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

    # Auto-promote configured admin users
    if ADMIN_USERNAMES:
        async with _pool.acquire() as conn:
            for username in ADMIN_USERNAMES:
                result = await conn.execute(
                    "UPDATE users SET identity = 'admin' WHERE username = $1 AND identity != 'admin'",
                    username,
                )
                if result.endswith("1"):
                    import logging
                    logging.getLogger("app").info(f"Auto-promoted '{username}' to admin")
