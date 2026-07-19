"""Phase 4 perf — TTL cache primitive + identity freshness + anonymous feed cache.

Locks the three Phase 4 guarantees:
  * ``TTLCache`` honours TTL / clear / cap (the shared primitive).
  * ``identity`` is read from the DB on every request via ``get_current_user``'s
    SELECT — so a permission change takes effect immediately on the SAME token,
    without re-login. This is why identity is NOT a JWT claim (no stale perms).
  * Anonymous ``GET /posts`` is cached short-term; logged-in responses are NOT
    cached (personalized like-state would leak across users).
"""
import asyncio
import uuid

import pytest

from backend.app.services.cache import TTLCache


# ── TTLCache primitive ──────────────────────────────────────────────────────

def test_cache_miss_then_hit():
    c = TTLCache(ttl_seconds=10)
    assert c.get("x") is None
    c.set("x", {"a": 1})
    assert c.get("x") == {"a": 1}


def test_cache_expires_after_ttl():
    c = TTLCache(ttl_seconds=0.05)
    c.set("k", "v")
    assert c.get("k") == "v"
    # asyncio.sleep needs an event loop; TTLCache uses time.monotonic so a plain
    # time.sleep is fine here (this is a sync test).
    import time
    time.sleep(0.07)
    assert c.get("k") is None


def test_cache_clear_and_cap():
    c = TTLCache(ttl_seconds=10, max_entries=2)
    c.set("a", 1); c.set("b", 2)
    assert c.get("a") == 1
    c.set("c", 3)  # at cap → clears
    assert c.get("a") is None
    assert c.get("c") == 3
    c.clear()
    assert c.get("c") is None


# ── identity freshness (NOT a JWT claim) ─────────────────────────────────────

@pytest.mark.asyncio
async def test_identity_reflects_db_change_without_relogin(client, make_user):
    uid, token = await make_user(f"u_{uuid.uuid4().hex[:6]}")
    from backend.app.services.auth_service import get_current_user
    from backend.app.database import get_db

    user = await get_current_user(token)
    assert "identity" in user
    assert user["identity"] != "admin"

    # Promote to admin directly in the DB — same token, no re-login.
    async with get_db() as db:
        await db.execute("UPDATE users SET identity = 'admin' WHERE id = $1", uid)

    user_after = await get_current_user(token)
    assert user_after["identity"] == "admin"  # fresh per-request, not stale JWT


# ── _is_admin is dict-based (no DB hop) ──────────────────────────────────────

def test_is_admin_reads_dict_not_db():
    from backend.app.routers.posts import _is_admin as posts_is_admin
    from backend.app.routers.news import _is_admin as news_is_admin

    for is_admin in (posts_is_admin, news_is_admin):
        assert is_admin({"identity": "admin"}) is True
        assert is_admin({"identity": "user"}) is False
        assert is_admin(None) is False
        assert is_admin({}) is False  # missing key → not admin


# ── anonymous list_posts cache; logged-in NOT cached ────────────────────────

@pytest.mark.asyncio
async def test_anonymous_list_posts_is_cached(client, make_user):
    from backend.app.routers.posts import _ANON_LIST_CACHE

    _ANON_LIST_CACHE.clear()
    # Seed a post so the list is non-empty.
    await make_user(f"seed_{uuid.uuid4().hex[:6]}")
    r = await client.post(
        "/api/v1/posts",
        json={"title": "cache-test", "content": "hi", "category": "discussion"},
        # anonymous → no Authorization header
    )
    # If the above 401s (posts create requires auth), seed via a user instead.
    if r.status_code != 201:
        uid, token = await make_user(f"seed_{uuid.uuid4().hex[:6]}")
        await client.post(
            "/api/v1/posts",
            json={"title": "cache-test", "content": "hi", "category": "discussion"},
            headers={"Authorization": f"Bearer {token}"},
        )

    _ANON_LIST_CACHE.clear()
    # First anonymous call populates the cache.
    r1 = await client.get("/api/v1/posts?page=1&page_size=20&sort=newest")
    assert r1.status_code == 200, r1.text
    cached = _ANON_LIST_CACHE.get((1, 20, "newest", "", ""))
    assert cached is not None, "anonymous list_posts should populate the cache"
    # Second call is served from cache (same payload).
    r2 = await client.get("/api/v1/posts?page=1&page_size=20&sort=newest")
    assert r2.json()["total"] == r1.json()["total"]


@pytest.mark.asyncio
async def test_logged_in_list_posts_is_not_cached(client, make_user):
    from backend.app.routers.posts import _ANON_LIST_CACHE

    _uid, token = await make_user(f"li_{uuid.uuid4().hex[:6]}")
    _ANON_LIST_CACHE.clear()
    await client.get(
        "/api/v1/posts?page=1&page_size=20",
        headers={"Authorization": f"Bearer {token}"},
    )
    # Logged-in responses must NOT enter the shared anonymous cache.
    assert _ANON_LIST_CACHE.get((1, 20, "newest", "", "")) is None


# ── catalogue cache ─────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_catalogue_programmes_is_cached(client):
    from backend.app.routers.courses import _CATALOGUE_CACHE

    _CATALOGUE_CACHE.clear()
    r = await client.get("/api/v1/courses/catalogue/programmes")
    assert r.status_code == 200, r.text
    assert _CATALOGUE_CACHE.get("programmes") is not None
