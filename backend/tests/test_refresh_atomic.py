"""[23] refresh-token rotation atomicity regression.

The old flow verified the token (SELECT in ``verify_refresh_token``) and
rotated it (DELETE in ``rotate_refresh_token``) as two separate steps, so two
concurrent ``/auth/refresh`` calls with the *same* token both passed
verification and both rotated — a stolen token stayed usable after the
legitimate client had already rotated it. ``rotate_refresh_token`` now does
DELETE...RETURNING + expiry check + mint-successor inside one transaction, so
the second presentation of a token finds the row already gone.

These tests lock that: a token rotates exactly once, replay is rejected both
at the function level and at the HTTP endpoint, and the successor keeps the
chain valid.
"""
import uuid

from backend.app.database import get_db
from backend.app.services.auth_service import (
    create_refresh_token, rotate_refresh_token,
)


async def test_rotate_rejects_unknown_and_empty(client):
    """Unknown / empty token → None without raising (no row to RETURN)."""
    assert await rotate_refresh_token("deadbeef" * 12) is None
    assert await rotate_refresh_token("") is None


async def test_rotate_is_single_use(client, make_user):
    """[23] a token rotates exactly once; replay returns None; the successor
    keeps the chain valid (legitimate rotation still works)."""
    uid, _ = await make_user(f"u_{uuid.uuid4().hex[:6]}")

    # mint a refresh token directly
    async with get_db() as db:
        raw = await create_refresh_token(uid, conn=db)

    first = await rotate_refresh_token(raw)
    assert first is not None
    assert first[0] == uid

    # replay the same (now-deleted) token → None (atomic DELETE already happened)
    assert await rotate_refresh_token(raw) is None

    # the successor rotates again — the legitimate chain stays alive
    second = await rotate_refresh_token(first[1])
    assert second is not None
    assert second[0] == uid
    # and the now-used successor is also single-use
    assert await rotate_refresh_token(first[1]) is None


async def test_refresh_endpoint_replay_is_401(client, make_user):
    """[23] end-to-end: POST /auth/refresh twice with the same refresh_token.
    First call succeeds (200) and rotates; second call is rejected (401)."""
    username = f"u_{uuid.uuid4().hex[:6]}"
    await make_user(username)
    login = await client.post(
        "/api/v1/auth/login",
        json={"username": username, "password": "Test12345!"},
    )
    assert login.status_code == 200, login.text
    refresh_token = login.json()["refresh_token"]

    r1 = await client.post("/api/v1/auth/refresh", json={"refresh_token": refresh_token})
    assert r1.status_code == 200, r1.text
    # a brand-new refresh token is issued
    assert r1.json()["refresh_token"] != refresh_token

    r2 = await client.post("/api/v1/auth/refresh", json={"refresh_token": refresh_token})
    assert r2.status_code == 401, r2.text


async def test_refresh_rejects_missing_token(client):
    """[23] missing refresh_token → 400 (input validation, not 401)."""
    r = await client.post("/api/v1/auth/refresh", json={})
    assert r.status_code == 400
