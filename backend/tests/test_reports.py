"""UGC report (举报) regression.

Two layers:
  - pure model validation (no DB): the target_type / reason_code enums and the
    detail length cap are enforced by ReportCreate, and ReportStatusUpdate only
    accepts terminal states. These run anywhere.
  - DB-backed behaviour (needs the CI postgres service via the `client` fixture):
    auth required, per-target dedup (UNIQUE → 409 on repeat), target-must-exist
    (404), lifetime quota, and admin-only list/resolve.
"""
import uuid

import pytest
from pydantic import ValidationError

from backend.app.routers import reports as rpt
from backend.app.models import ReportCreate, ReportStatusUpdate
from backend.app.database import get_db


# ── pure model validation (runs with no DB) ──────────────────────────────────

def test_report_create_accepts_all_reason_codes():
    for code in ("spam", "abuse", "porn", "illegal", "other"):
        assert ReportCreate(target_type="post", target_id=1, reason_code=code).reason_code == code


def test_report_create_accepts_all_target_types():
    for tt in ("post", "comment", "lostfound", "news_comment", "user"):
        assert ReportCreate(target_type=tt, target_id=1, reason_code="spam").target_type == tt


def test_report_create_rejects_unknown_reason_code():
    with pytest.raises(ValidationError):
        ReportCreate(target_type="post", target_id=1, reason_code="violence")


def test_report_create_rejects_unknown_target_type():
    with pytest.raises(ValidationError):
        ReportCreate(target_type="profile", target_id=1, reason_code="spam")


def test_report_create_rejects_nonpositive_target_id():
    with pytest.raises(ValidationError):
        ReportCreate(target_type="post", target_id=0, reason_code="spam")


def test_report_create_rejects_oversized_detail():
    with pytest.raises(ValidationError):
        ReportCreate(target_type="post", target_id=1, reason_code="other", detail="x" * 501)


def test_report_status_update_only_accepts_terminal():
    with pytest.raises(ValidationError):
        ReportStatusUpdate(status="open")
    for s in ("resolved", "dismissed"):
        assert ReportStatusUpdate(status=s).status == s


# ── DB-backed behaviour ───────────────────────────────────────────────────────

def _post_payload():
    return {"title": f"t-{uuid.uuid4().hex[:6]}", "content": "c", "category": "general"}


async def _make_post(client, token):
    r = await client.post(
        "/api/v1/posts", headers={"Authorization": f"Bearer {token}"}, json=_post_payload(),
    )
    assert r.status_code == 201, r.text
    return r.json()["id"]


async def test_reports_requires_auth(client):
    r = await client.post(
        "/api/v1/reports",
        json={"target_type": "post", "target_id": 1, "reason_code": "spam"},
    )
    assert r.status_code == 401


async def test_report_dedup_returns_409(client, make_user):
    _, token = await make_user(f"u_{uuid.uuid4().hex[:6]}")
    h = {"Authorization": f"Bearer {token}"}
    pid = await _make_post(client, token)
    body = {"target_type": "post", "target_id": pid, "reason_code": "spam"}
    assert (await client.post("/api/v1/reports", headers=h, json=body)).status_code == 201
    assert (await client.post("/api/v1/reports", headers=h, json=body)).status_code == 409


async def test_report_unknown_target_returns_404(client, make_user):
    _, token = await make_user(f"u_{uuid.uuid4().hex[:6]}")
    h = {"Authorization": f"Bearer {token}"}
    body = {"target_type": "post", "target_id": 9_999_999, "reason_code": "spam"}
    assert (await client.post("/api/v1/reports", headers=h, json=body)).status_code == 404


async def test_report_quota_caps_distinct_targets(client, make_user, monkeypatch):
    # quota lowered to 1 so the 2nd DISTINCT target hits the lifetime cap (rate
    # default 5/hr does not bind first).
    monkeypatch.setattr(rpt, "MAX_REPORTS_PER_USER", 1)
    _, token = await make_user(f"u_{uuid.uuid4().hex[:6]}")
    h = {"Authorization": f"Bearer {token}"}
    p1 = await _make_post(client, token)
    p2 = await _make_post(client, token)
    assert (await client.post("/api/v1/reports", headers=h, json={
        "target_type": "post", "target_id": p1, "reason_code": "spam",
    })).status_code == 201
    assert (await client.post("/api/v1/reports", headers=h, json={
        "target_type": "post", "target_id": p2, "reason_code": "spam",
    })).status_code == 409


async def test_admin_can_list_and_resolve_reports(client, make_user):
    # reporter flags a post
    _, reporter_token = await make_user(f"u_{uuid.uuid4().hex[:6]}")
    pid = await _make_post(client, reporter_token)
    h = {"Authorization": f"Bearer {reporter_token}"}
    res = await client.post("/api/v1/reports", headers=h, json={
        "target_type": "post", "target_id": pid, "reason_code": "abuse", "detail": "bad",
    })
    assert res.status_code == 201, res.text
    rid = res.json()["id"]

    # non-admin cannot list
    assert (await client.get("/api/v1/reports/admin", headers=h)).status_code == 403

    # promote a second user to admin (identity is re-read per request, so the
    # existing token picks up the new role without re-login) and act on it
    admin_uid, admin_token = await make_user(f"u_{uuid.uuid4().hex[:6]}")
    async with get_db() as db:
        await db.execute("UPDATE users SET identity = 'admin' WHERE id = $1", admin_uid)
    ah = {"Authorization": f"Bearer {admin_token}"}
    lst = await client.get("/api/v1/reports/admin", headers=ah)
    assert lst.status_code == 200, lst.text
    assert any(r["id"] == rid for r in lst.json())

    upd = await client.put(f"/api/v1/reports/{rid}", headers=ah, json={"status": "resolved"})
    assert upd.status_code == 200, upd.text
