"""Shared fixtures + repo-root path bootstrap for backend security regression
tests (security roadmap G).

Putting the repo root on sys.path here (before any test module imports) lets
tests do ``from backend.app... import ...`` regardless of how pytest is
invoked — same trick scripts/test_content_security.py already uses.
"""
import sys
from pathlib import Path

_REPO_ROOT = str(Path(__file__).resolve().parents[2])
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

import httpx
import pytest
import pytest_asyncio
from httpx import ASGITransport


@pytest_asyncio.fixture
async def client():
    """In-process async HTTP client bound to the app on the TEST's event loop.

    Entering ``app.router.lifespan_context`` runs the app's lifespan startup —
    i.e. ``init_db()`` — which creates the asyncpg pool on THIS loop. Because
    httpx ASGITransport dispatches the ASGI app on the same loop, and our
    direct ``get_db()`` calls reuse that pool, HTTP + direct DB share one loop
    (asyncpg connections are loop-bound, so this is required). Lifespan
    shutdown closes the pool at the end of each test.

    Needs ``DATABASE_URL`` pointing at a reachable Postgres (CI service, or a
    local `docker run postgres:16`). The WS unit test does not use this fixture
    and runs with no DB at all.
    """
    from backend.app.main import app

    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as c:
            yield c


@pytest.fixture
def make_user(client):
    """Factory: register a user, flip email_verified=TRUE, log in.

    Returns an async ``_(username, password="Test12345!") -> (user_id, token)``.
    ``/auth/login`` refuses unverified users (403 email_not_verified) and CI has
    no SMTP, so we set the flag directly — email verification is orthogonal to
    the A/E behaviours under test.
    """

    async def _make(username: str, password: str = "Test12345!"):
        reg = await client.post(
            "/api/v1/auth/register",
            json={"username": username, "password": password, "nickname": username},
        )
        assert reg.status_code == 201, reg.text
        user_id = reg.json()["id"]

        from backend.app.database import get_db

        async with get_db() as db:
            await db.execute(
                "UPDATE users SET email_verified = TRUE WHERE id = $1", user_id
            )

        login = await client.post(
            "/api/v1/auth/login",
            json={"username": username, "password": password},
        )
        assert login.status_code == 200, login.text
        return user_id, login.json()["access_token"]

    return _make
