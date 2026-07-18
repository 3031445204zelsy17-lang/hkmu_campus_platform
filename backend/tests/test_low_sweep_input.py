"""Codex low-sweep input-validation regression: [17][18] login input bounds,
[21] client-error type length, [25] batch progress cap + dedup."""
import pytest
from pydantic import ValidationError

from backend.app.routers.courses import BatchProgressUpdate, _MAX_BATCH_PROGRESS


# --- [17][18] login input bounds (also bound the in-memory lockout-dict key) ---

async def test_login_rejects_oversize_username(client):
    r = await client.post(
        "/api/v1/auth/login", json={"username": "x" * 31, "password": "pw123456"}
    )
    assert r.status_code == 422  # max_length=30


async def test_email_login_rejects_oversize_email(client):
    r = await client.post(
        "/api/v1/auth/email/login",
        json={"email": "a" * 250 + "@b.co", "password": "pw123456"},  # >254
    )
    assert r.status_code == 422


async def test_email_login_rejects_oversize_password(client):
    r = await client.post(
        "/api/v1/auth/email/login",
        json={"email": "a@b.co", "password": "p" * 129},  # >128
    )
    assert r.status_code == 422


# --- [21] client-error type length ---

async def test_client_error_rejects_oversize_type(client):
    r = await client.post("/api/v1/log/client-error", json={"type": "x" * 65})
    assert r.status_code == 422  # max_length=64


async def test_client_error_accepts_normal_type(client):
    # no auth required for /log; a normal payload returns 204
    r = await client.post(
        "/api/v1/log/client-error",
        json={"type": "error", "message": "boom"},
    )
    assert r.status_code == 204


# --- [25] batch progress cap + dedup ---

def _item(cid, status="completed"):
    return {"course_id": cid, "status": status}


def test_batch_progress_rejects_over_cap():
    items = [_item(f"c{i}") for i in range(_MAX_BATCH_PROGRESS + 1)]
    with pytest.raises(ValidationError):
        BatchProgressUpdate(items=items)


def test_batch_progress_accepts_at_cap():
    items = [_item(f"c{i}") for i in range(_MAX_BATCH_PROGRESS)]
    assert len(BatchProgressUpdate(items=items).items) == _MAX_BATCH_PROGRESS


def test_batch_progress_dedups_by_course_id_last_wins():
    items = [
        _item("c1", "not_started"),
        _item("c1", "completed"),  # duplicate course_id — last occurrence wins
        _item("c2", "in_progress"),
    ]
    m = BatchProgressUpdate(items=items)
    by_id = {i.course_id: i.status for i in m.items}
    assert by_id == {"c1": "completed", "c2": "in_progress"}
    assert len(m.items) == 2
