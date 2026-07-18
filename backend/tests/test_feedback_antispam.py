"""[16] Feedback anti-abuse regression.

``POST /feedback`` was auth-required but otherwise uncapped — any user could
spam unbounded rows (DB bloat / abuse). Now three controls: per-user rate
(burst), per-user quota (lifetime count), and opportunistic retention (prune
rows older than the window).
"""
import uuid
from datetime import datetime, timedelta, timezone

import pytest

from backend.app.routers import feedback as fb_module
from backend.app.database import get_db


def _payload(msg="looks good"):
    return {"rating": 5, "content": f"{msg} {uuid.uuid4().hex[:6]}"}


async def test_feedback_rate_limits_bursts(client, make_user):
    """Per-user rate (FEEDBACK_PER_HOUR=3): the 4th submit in an hour is 429."""
    _, token = await make_user(f"u_{uuid.uuid4().hex[:6]}")
    headers = {"Authorization": f"Bearer {token}"}
    for i in range(fb_module.FEEDBACK_PER_HOUR):
        r = await client.post("/api/v1/feedback", headers=headers, json=_payload(str(i)))
        assert r.status_code == 201, r.text
    r = await client.post("/api/v1/feedback", headers=headers, json=_payload("one too many"))
    assert r.status_code == 429, r.text


async def test_feedback_quota_caps_lifetime_count(client, make_user, monkeypatch):
    """Per-user quota: at MAX_FEEDBACK_PER_USER rows, the next submit is 409.
    MAX is lowered to 2 so rate (3/hr) doesn't bind first — 3rd submit passes
    rate then hits the quota."""
    monkeypatch.setattr(fb_module, "MAX_FEEDBACK_PER_USER", 2)
    _, token = await make_user(f"u_{uuid.uuid4().hex[:6]}")
    headers = {"Authorization": f"Bearer {token}"}
    assert (await client.post("/api/v1/feedback", headers=headers, json=_payload("a"))).status_code == 201
    assert (await client.post("/api/v1/feedback", headers=headers, json=_payload("b"))).status_code == 201
    r = await client.post("/api/v1/feedback", headers=headers, json=_payload("c"))
    assert r.status_code == 409, r.text


async def test_feedback_retention_prunes_expired_rows(client, make_user):
    """Opportunistic retention: a row older than the window is deleted on the
    next submit (and no longer counts against the quota)."""
    uid, token = await make_user(f"u_{uuid.uuid4().hex[:6]}")
    headers = {"Authorization": f"Bearer {token}"}

    # plant an expired feedback row directly
    old = datetime.now(timezone.utc) - timedelta(days=fb_module.FEEDBACK_RETENTION_DAYS + 1)
    async with get_db() as db:
        planted = await db.fetchval(
            "INSERT INTO feedback (user_id, rating, content, created_at) "
            "VALUES ($1, 1, 'stale', $2) RETURNING id",
            uid, old,
        )

    # a fresh submit triggers the in-txn retention delete
    r = await client.post("/api/v1/feedback", headers=headers, json=_payload("fresh"))
    assert r.status_code == 201, r.text

    # the planted expired row is gone; the fresh one remains
    async with get_db() as db:
        row = await db.fetchrow(
            "SELECT COUNT(*) AS c, "
            "COUNT(*) FILTER (WHERE id = $1) AS planted "
            "FROM feedback WHERE user_id = $2",
            planted, uid,
        )
    assert row["planted"] == 0, "expired feedback should have been pruned"
    assert row["c"] == 1, "only the fresh feedback should remain"


async def test_feedback_requires_auth(client):
    r = await client.post("/api/v1/feedback", json=_payload("anon"))
    assert r.status_code == 401
